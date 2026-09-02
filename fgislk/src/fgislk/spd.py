from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import ssl
import sys
import tempfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from fgislk.settings import fgis_credentials, fgis_host, fgis_tls, http_workers
from fgislk.windows import add_month

_RETRY_ATTEMPTS = 3
_TIMEOUT_SECONDS = 180
_STATUS_MARKER = "\n__HTTPSTATUS__"

log = logging.getLogger(__name__)
_active_curl: set[asyncio.subprocess.Process] = set()
_transfer_sem: asyncio.Semaphore | None = None


def _transfers() -> asyncio.Semaphore:
    """Живых HTTP к СПД на процесс = FGIS_MAX_WORKERS × FGIS_BATCH_WORKERS."""
    global _transfer_sem
    if _transfer_sem is None:
        _transfer_sem = asyncio.Semaphore(http_workers())
    return _transfer_sem


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


_GOST_CIPHER = "GOST2012-GOST8912-GOST8912"
_GOST_SO_CANDIDATES = (
    Path("/usr/lib/x86_64-linux-gnu/engines-3/gost.so"),
    Path("/usr/lib/aarch64-linux-gnu/engines-3/gost.so"),
    Path("/usr/lib/engines-3/gost.so"),
)
_GOST_CNF_TEMPLATE = """\
openssl_conf = openssl_def

[openssl_def]
engines = engine_section

[engine_section]
gost = gost_section

[gost_section]
engine_id = gost
dynamic_path = {path}
default_algorithms = ALL
init = 1
"""


def find_curl() -> str | None:
    """schannel: Windows curl.exe; openssl — системный curl."""
    if fgis_tls() == "schannel":
        return shutil.which("curl.exe")
    return shutil.which("curl")


def gost_engine_path() -> Path | None:
    raw = os.environ.get("FGIS_GOST_ENGINE", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_file() else None
    for path in _GOST_SO_CANDIDATES:
        if path.is_file():
            return path
    return None


def openssl_gost_conf_path() -> str | None:
    """Конфиг OpenSSL с gost-engine. Windows / schannel не вызывают."""
    raw = os.environ.get("FGIS_OPENSSL_CONF", "").strip()
    if raw:
        path = Path(raw)
        return str(path) if path.is_file() else None
    so = gost_engine_path()
    if so is None:
        return None
    system = Path("/etc/ssl/fgislk-openssl-gost.cnf")
    if system.is_file():
        return str(system)
    bundled = Path(__file__).resolve().parent.parent.parent / "openssl-gost.cnf"
    if bundled.is_file() and so.as_posix() in bundled.read_text(encoding="utf-8"):
        return str(bundled)
    generated = Path(tempfile.gettempdir()) / "fgislk-openssl-gost.cnf"
    payload = _GOST_CNF_TEMPLATE.format(path=so.as_posix())
    try:
        if not generated.is_file() or generated.read_text(encoding="utf-8") != payload:
            generated.write_text(payload, encoding="utf-8")
    except OSError:
        return None
    return str(generated)


def _linux_openssl_gost() -> bool:
    return fgis_tls() == "openssl" and sys.platform != "win32"


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
    url: str, login: str, password: str, *, schannel: bool, gost: bool = False
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
    if schannel:
        return lines
    if gost:
        lines[0:0] = [
            "tlsv1.2",
            "tls-max = 1.2",
            f'ciphers = "{_GOST_CIPHER}"',
            "ipv4",
            "insecure",
        ]
        return lines
    lines.insert(0, "tlsv1.2")
    lines.insert(1, 'ciphers = "DEFAULT:@SECLEVEL=1"')
    return lines


def curl_config(
    url: str | Sequence[str],
    login: str,
    password: str,
    *,
    schannel: bool,
    gost: bool = False,
) -> str:
    urls = [url] if isinstance(url, str) else list(url)
    if not urls:
        raise ValueError("curl_config: нужен хотя бы один url")
    lines: list[str] = []
    for index, item in enumerate(urls):
        if index:
            lines.append("next")
        lines.extend(
            _curl_transfer_lines(
                item, login, password, schannel=schannel, gost=gost
            )
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
        self._gost = _linux_openssl_gost()
        self._gost_conf = openssl_gost_conf_path() if self._gost else None
        self._curl = find_curl()
        self._http: httpx.AsyncClient | None = None
        if self._schannel and not self._curl:
            raise SpdError(
                "Портал fgislk.gov.ru принимает TLS только через Windows Schannel "
                "(curl.exe). Запустите fgislk на хосте: .\\fgislk\\run.ps1 — "
                "не в Linux-контейнере Docker. Либо FGIS_TLS=openssl."
            )
        if self._gost:
            if not self._curl:
                raise SpdError(
                    "FGIS_TLS=openssl: нужен системный curl "
                    "(sudo apt install curl)"
                )
            if not self._gost_conf:
                raise SpdError(
                    "fgislk.gov.ru требует GOST-TLS "
                    f"(шифр {_GOST_CIPHER}). На Ubuntu: "
                    "sudo bash fgislk/install_gost_engine.sh"
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
            url_list,
            self._login,
            self._password,
            schannel=self._schannel,
            gost=self._gost,
        )
        env = None
        if self._gost_conf:
            env = os.environ.copy()
            env["OPENSSL_CONF"] = self._gost_conf
        async with _transfers():
            proc = await asyncio.create_subprocess_exec(
                self._curl,
                "--config",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
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
            if "0A000410" in err or "handshake failure" in err.lower():
                err = (
                    f"{err}; СПД требует gost-engine: "
                    "sudo bash fgislk/install_gost_engine.sh"
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
                async with _transfers():
                    response = await self._http.get(
                        self._url(path, params)
                        if params
                        else f"{self._base}/{path.lstrip('/')}"
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
        """Пачка карточек: один curl на пачку; живых HTTP к СПД не больше http_workers() на процесс."""
        ids = list(fgis_ids)
        if not ids:
            return []
        if not self._curl:
            return list(
                await asyncio.gather(
                    *[self._card_via_http(fgis_id) for fgis_id in ids]
                )
            )
        urls = [self._url(f"taxationPiece/{fgis_id}") for fgis_id in ids]
        parsed: list[tuple[int, str]] | None = None
        last_error: Exception | None = None
        for _attempt in range(_RETRY_ATTEMPTS):
            try:
                parsed = await self._curl_exec(urls)
                break
            except SpdError as exc:
                last_error = exc
                log.warning("пачка карточек СПД: %s", exc)
        if parsed is None:
            log.warning(
                "пачка %s карточек недоступна, по одной: %s",
                len(ids),
                last_error,
            )
            return list(
                await asyncio.gather(
                    *[self._card_via_http(fgis_id) for fgis_id in ids]
                )
            )
        out: list[dict[str, Any] | None] = []
        retry_ids: list[str] = []
        retry_at: list[int] = []
        for index, (status, body) in enumerate(parsed):
            kind, card = _card_from_status(status, body)
            if kind == "retry":
                retry_at.append(index)
                retry_ids.append(ids[index])
                out.append(None)
            else:
                out.append(card)
        if retry_ids:
            recovered = await asyncio.gather(
                *[self._card_via_http(fgis_id) for fgis_id in retry_ids]
            )
            for index, card in zip(retry_at, recovered, strict=True):
                out[index] = card
        return out

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


def _card_from_status(
    status: int, body: str
) -> tuple[str, dict[str, Any] | None]:
    if status >= 500 or status == 0:
        return "retry", None
    if status >= 400:
        return "skip", None
    try:
        data = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        return "retry", None
    if not isinstance(data, dict):
        return "skip", None
    return "ok", _card_from_response(data)
