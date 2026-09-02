from __future__ import annotations

import asyncio
import json
import logging
import shutil
import ssl
from collections.abc import Sequence
from datetime import date
from typing import Any
from urllib.parse import urlencode

import httpx

from fgislk.settings import fgis_credentials, fgis_host, fgis_tls
from fgislk.windows import add_month

_RETRY_ATTEMPTS = 3
_TIMEOUT_SECONDS = 180
_STATUS_MARKER = "\n__HTTPSTATUS__"
SPD_DETAIL_CONCURRENCY = 8

log = logging.getLogger(__name__)
_active_curl: set[asyncio.subprocess.Process] = set()


def kill_all_curl() -> int:
    n = 0
    for proc in list(_active_curl):
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                continue
            n += 1
    return n


class SpdError(Exception):
    pass


def _card_from_response(data: dict[str, Any]) -> dict[str, Any] | None:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("modifyDttm") in (None, "") and data.get("modifyDttm") not in (
        None,
        "",
    ):
        payload = {**payload, "modifyDttm": data["modifyDttm"]}
    return payload


def spd_base_url(host: str | None = None) -> str:
    value = (host or fgis_host()).rstrip("/")
    if not value.startswith("http://") and not value.startswith("https://"):
        value = f"https://{value}"
    return (
        f"{value}/rmdl/pvv/backend/gateway-adapter-spd"
        "/gateway/services/external"
    )


def find_curl() -> str | None:
    """schannel: curl.exe; openssl — системный curl (SECLEVEL=1)."""
    if fgis_tls() == "schannel":
        return shutil.which("curl.exe")
    return shutil.which("curl")


def _curl_config_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def parse_curl_responses(text: str) -> list[tuple[int, str]]:
    if _STATUS_MARKER not in text:
        return [(0, text)]
    parts = text.split(_STATUS_MARKER)
    results: list[tuple[int, str]] = []
    body = parts[0]
    for part in parts[1:]:
        status_line, _, rest = part.partition("\n")
        try:
            status = int(status_line.strip() or "0")
        except ValueError:
            status = 0
        results.append((status, body))
        body = rest
    return results


def _curl_transfer_lines(
    url: str, login: str, password: str, *, schannel: bool
) -> list[str]:
    lines = [
        "silent",
        "show-error",
        "http1.1",
        f"connect-timeout = {min(30, _TIMEOUT_SECONDS)}",
        f"max-time = {_TIMEOUT_SECONDS}",
        f'header = "login: {_curl_config_escape(login)}"',
        f'header = "password: {_curl_config_escape(password)}"',
        f'url = "{_curl_config_escape(url)}"',
        'write-out = "\\n__HTTPSTATUS__%{http_code}\\n"',
    ]
    if not schannel:
        lines.insert(0, "tlsv1.2")
        lines.insert(1, 'ciphers = "DEFAULT:@SECLEVEL=1"')
    return lines


def curl_config(
    url: str | Sequence[str], login: str, password: str, *, schannel: bool
) -> str:
    urls = [url] if isinstance(url, str) else list(url)
    if not urls:
        raise ValueError("curl_config: нужен хотя бы один url")
    lines: list[str] = []
    for index, item in enumerate(urls):
        if index:
            lines.append("next")
        lines.extend(
            _curl_transfer_lines(item, login, password, schannel=schannel)
        )
    return "\n".join(lines)


def fgis_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


class SpdClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or spd_base_url()).rstrip("/")
        self._login, self._password = fgis_credentials()
        self._schannel = fgis_tls() == "schannel"
        self._curl = find_curl()
        self._http: httpx.AsyncClient | None = None
        if self._schannel and not self._curl:
            raise SpdError(
                "Портал fgislk.gov.ru принимает TLS только через Windows Schannel "
                "(curl.exe). Запустите fgislk на хосте: .\\fgislk\\run.ps1 — "
                "не в Linux-контейнере Docker. Либо FGIS_TLS=openssl."
            )
        if not self._curl:
            self._http = httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS,
                verify=fgis_ssl_context(),
                headers={
                    "login": self._login,
                    "password": self._password,
                },
            )

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    def _url(self, path: str, params: dict[str, str] | None = None) -> str:
        url = f"{self._base}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    async def _curl_exec(self, urls: Sequence[str]) -> list[tuple[int, str]]:
        if not self._curl:
            raise RuntimeError("curl не найден")
        url_list = list(urls)
        config = curl_config(
            url_list, self._login, self._password, schannel=self._schannel
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
        if proc.returncode not in (0, 22) and not any(
            status for status, _ in parsed
        ):
            err = stderr.decode("utf-8", errors="replace").strip() or (
                f"curl exit {proc.returncode}"
            )
            raise SpdError(err)
        if len(parsed) != len(url_list):
            raise SpdError(
                f"curl ответов {len(parsed)}, ожидали {len(url_list)}"
            )
        return parsed

    async def _curl_get(self, url: str) -> tuple[int, str]:
        return (await self._curl_exec([url]))[0]

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                if self._curl:
                    status, body = await self._curl_get(self._url(path, params))
                    if status >= 500:
                        last_error = SpdError(f"СПД {status} {path}: {body[:500]}")
                        continue
                    if status >= 400:
                        raise SpdError(f"СПД {status} {path}: {body[:500]}")
                    try:
                        return json.loads(body) if body.strip() else {}
                    except json.JSONDecodeError as exc:
                        raise SpdError(f"СПД не JSON {path}: {exc}") from exc
                assert self._http is not None
                response = await self._http.get(
                    self._url(path, params) if params else f"{self._base}/{path.lstrip('/')}"
                )
                if response.status_code >= 500:
                    last_error = SpdError(
                        f"СПД {response.status_code} {path}: {response.text[:500]}"
                    )
                    continue
                if response.status_code >= 400:
                    raise SpdError(
                        f"СПД {response.status_code} {path}: {response.text[:500]}"
                    )
                try:
                    return response.json()
                except ValueError as exc:
                    raise SpdError(f"СПД не JSON {path}: {exc}") from exc
            except (httpx.HTTPError, SpdError) as exc:
                last_error = exc if isinstance(exc, SpdError) else SpdError(str(exc))
                if isinstance(exc, SpdError) and "СПД 4" in str(exc):
                    raise
                continue
        raise last_error or SpdError(f"СПД недоступен {path}")

    async def changed_over_period(
        self, subject: str, start: date, end: date
    ) -> dict[str, Any]:
        data = await self._get(
            "taxationPiece/changedOverPeriod",
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "regionCode": subject,
            },
        )
        if not isinstance(data, dict):
            raise SpdError("changedOverPeriod: ожидался объект JSON")
        return data

    async def _card_via_http(self, fgis_id: str) -> dict[str, Any] | None:
        path = f"taxationPiece/{fgis_id}"
        try:
            data = await self._get(path)
        except SpdError as exc:
            log.warning("карточка %s недоступна: %s", fgis_id, exc)
            return None
        if not isinstance(data, dict):
            return None
        return _card_from_response(data)

    async def taxation_piece(self, fgis_id: str) -> dict[str, Any] | None:
        return await self._card_via_http(fgis_id)

    async def taxation_pieces(
        self, fgis_ids: Sequence[str]
    ) -> list[dict[str, Any] | None]:
        """Карточки параллельно, не больше SPD_DETAIL_CONCURRENCY GET сразу."""
        ids = list(fgis_ids)
        if not ids:
            return []
        sem = asyncio.Semaphore(SPD_DETAIL_CONCURRENCY)

        async def one(fgis_id: str) -> dict[str, Any] | None:
            async with sem:
                return await self._card_via_http(fgis_id)

        return list(await asyncio.gather(*[one(fgis_id) for fgis_id in ids]))

    async def changed_ids(
        self,
        subject: str,
        start: date,
        end: date,
        *,
        shrink: bool = False,
        on_window=None,
    ) -> list[str]:
        """Список id за окно. Аудит (`shrink`): сначала весь период; нет payload —
        start += месяц, endDate без изменения (как 1С). Инкремент — один запрос."""
        from fgislk.mapper import ids_from_payload

        current = start
        while current <= end:
            if on_window is not None:
                await on_window(current, end)
            data = await self.changed_over_period(subject, current, end)
            if "payload" not in data or data["payload"] is None:
                if not shrink:
                    return []
                current = add_month(current)
                continue
            return ids_from_payload(data["payload"])
        return []
