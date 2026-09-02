from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from fgislk.settings import fgis_tls, pub_fgis_base_url
from fgislk.spd import (
    _active_curl,
    find_curl,
    fgis_ssl_context,
    parse_curl_responses,
)

_RETRY_ATTEMPTS = 3
_TIMEOUT_SECONDS = 180
_LAYER = "FOREST_LAYERS:TAXATION_PIECE"
WFS_BATCH = 100

log = logging.getLogger(__name__)


class WfsError(Exception):
    pass


def wfs_referer() -> str:
    return f"{pub_fgis_base_url()}/map/"


def wfs_endpoint() -> str:
    return f"{pub_fgis_base_url()}/map/geo/geoserver/wms"


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def wfs_get_feature_xml(fgis_ids: Sequence[str]) -> str:
    equals = [
        (
            "<fes:PropertyIsEqualTo>"
            "<fes:ValueReference>externalid</fes:ValueReference>"
            f"<fes:Literal>{_xml_escape(fgis_id)}</fes:Literal>"
            "</fes:PropertyIsEqualTo>"
        )
        for fgis_id in fgis_ids
    ]
    if not equals:
        raise ValueError("wfs_get_feature_xml: нужен хотя бы один id")
    filt = equals[0] if len(equals) == 1 else f"<fes:Or>{''.join(equals)}</fes:Or>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<wfs:GetFeature service="WFS" version="2.0.0" '
        'outputFormat="application/json" '
        'xmlns:wfs="http://www.opengis.net/wfs/2.0" '
        'xmlns:fes="http://www.opengis.net/fes/2.0">'
        f'<wfs:Query typeNames="{_LAYER}" srsName="EPSG:4326">'
        f"<fes:Filter>{filt}</fes:Filter>"
        "</wfs:Query></wfs:GetFeature>"
    )


def _semantic_id(feature: dict[str, Any]) -> int | None:
    raw_id = feature.get("id")
    if isinstance(raw_id, str) and "." in raw_id:
        tail = raw_id.rsplit(".", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def _geom_json(feature: dict[str, Any]) -> str | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return None
    return json.dumps(geometry, separators=(",", ":"))


def _feature_externalid(feature: dict[str, Any]) -> str | None:
    props = feature.get("properties")
    if not isinstance(props, dict):
        return None
    for key in ("externalid", "EXTERNALID", "externalId"):
        value = props.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def contour_from_feature(
    feature: dict[str, Any],
) -> tuple[int | None, str | None]:
    return _semantic_id(feature), _geom_json(feature)


def contours_from_geojson(
    data: dict[str, Any], fgis_ids: Sequence[str]
) -> list[tuple[int | None, str | None] | None]:
    by_id: dict[str, tuple[int | None, str | None]] = {}
    features = data.get("features")
    if isinstance(features, list):
        for feature in features:
            if not isinstance(feature, dict):
                continue
            fgis_id = _feature_externalid(feature)
            if fgis_id is None or fgis_id in by_id:
                continue
            by_id[fgis_id] = contour_from_feature(feature)
    return [by_id.get(fgis_id) for fgis_id in fgis_ids]


def _curl_config_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _curl_post_config(url: str, referer: str, body: str, *, schannel: bool) -> str:
    lines = [
        "silent",
        "show-error",
        "http1.1",
        f"connect-timeout = {min(30, _TIMEOUT_SECONDS)}",
        f"max-time = {_TIMEOUT_SECONDS}",
        f'header = "Referer: {_curl_config_escape(referer)}"',
        'header = "Content-Type: text/xml"',
        f'url = "{_curl_config_escape(url)}"',
        f'data-binary = "{_curl_config_escape(body)}"',
        'write-out = "\\n__HTTPSTATUS__%{http_code}\\n"',
    ]
    if not schannel:
        lines.insert(0, "tlsv1.2")
        lines.insert(1, 'ciphers = "DEFAULT:@SECLEVEL=1"')
    return "\n".join(lines)


class WfsClient:
    def __init__(self) -> None:
        self._schannel = fgis_tls() == "schannel"
        self._curl = find_curl()
        self._referer = wfs_referer()
        self._url = wfs_endpoint()
        self._http: httpx.AsyncClient | None = None
        if self._schannel and not self._curl:
            raise WfsError(
                "WFS pub.fgislk.gov.ru принимает TLS только через Windows Schannel "
                "(curl.exe). Запустите fgislk на хосте: .\\fgislk\\run.ps1 — "
                "не в Linux-контейнере Docker. Либо FGIS_TLS=openssl."
            )
        if not self._curl:
            self._http = httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS,
                verify=fgis_ssl_context(),
                headers={"Referer": self._referer},
            )

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def _curl_post(self, body: str) -> tuple[int, str]:
        if not self._curl:
            raise RuntimeError("curl не найден")
        config = _curl_post_config(
            self._url, self._referer, body, schannel=self._schannel
        )
        proc = await asyncio.create_subprocess_exec(
            self._curl,
            "--config",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _active_curl.add(proc)
        try:
            stdout, stderr = await proc.communicate(config.encode("utf-8"))
        except (asyncio.CancelledError, Exception):
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await proc.wait()
                except Exception:
                    pass
            raise
        finally:
            _active_curl.discard(proc)
        text = stdout.decode("utf-8", errors="replace")
        parsed = parse_curl_responses(text)
        if proc.returncode not in (0, 22) and not any(status for status, _ in parsed):
            err = stderr.decode("utf-8", errors="replace").strip() or (
                f"curl exit {proc.returncode}"
            )
            raise WfsError(err)
        if len(parsed) != 1:
            raise WfsError(f"curl ответов {len(parsed)}, ожидали 1")
        return parsed[0]

    async def _post_geojson(self, fgis_ids: list[str]) -> dict[str, Any] | None:
        body = wfs_get_feature_xml(fgis_ids)
        last_error: Exception | None = None
        for _ in range(_RETRY_ATTEMPTS):
            try:
                if self._curl:
                    status, text = await self._curl_post(body)
                    if status >= 500:
                        last_error = WfsError(f"WFS {status}: {text[:500]}")
                        continue
                    if status >= 400:
                        log.warning("WFS пачка %s: HTTP %s", len(fgis_ids), status)
                        return None
                    try:
                        data = json.loads(text) if text.strip() else {}
                    except json.JSONDecodeError:
                        log.warning("WFS пачка %s: не JSON", len(fgis_ids))
                        return None
                    if not isinstance(data, dict):
                        return None
                    return data
                assert self._http is not None
                response = await self._http.post(
                    self._url,
                    content=body.encode("utf-8"),
                    headers={"Content-Type": "text/xml"},
                )
                if response.status_code >= 500:
                    last_error = WfsError(
                        f"WFS {response.status_code}: {response.text[:500]}"
                    )
                    continue
                if response.status_code >= 400:
                    log.warning(
                        "WFS пачка %s: HTTP %s",
                        len(fgis_ids),
                        response.status_code,
                    )
                    return None
                try:
                    data = response.json()
                except ValueError:
                    log.warning("WFS пачка %s: не JSON", len(fgis_ids))
                    return None
                if not isinstance(data, dict):
                    return None
                return data
            except (httpx.HTTPError, WfsError) as exc:
                last_error = exc if isinstance(exc, WfsError) else WfsError(str(exc))
                continue
        log.warning("WFS пачка %s недоступна: %s", len(fgis_ids), last_error)
        return None

    async def taxation_piece_contours(
        self, fgis_ids: Sequence[str]
    ) -> list[tuple[int | None, str | None] | None]:
        ids = list(fgis_ids)
        if not ids:
            return []
        out: list[tuple[int | None, str | None] | None] = []
        for offset in range(0, len(ids), WFS_BATCH):
            chunk = ids[offset : offset + WFS_BATCH]
            data = await self._post_geojson(chunk)
            if data is None:
                out.extend([None] * len(chunk))
                continue
            mapped = contours_from_geojson(data, chunk)
            for fgis_id, contour in zip(chunk, mapped, strict=True):
                if contour is None:
                    log.warning("контур %s: нет feature", fgis_id)
            out.extend(mapped)
        return out
