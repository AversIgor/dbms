from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

KINDS = ("string", "number", "date", "boolean")


class ConstantTypeError(ValueError):
    pass


def to_stored(kind: str, raw: Any) -> str:
    if kind == "string":
        if raw is None:
            return ""
        if isinstance(raw, bool) or isinstance(raw, (int, float, Decimal)):
            raise ConstantTypeError("string — строка")
        return str(raw)
    if kind == "number":
        if isinstance(raw, bool) or raw is None:
            raise ConstantTypeError("number — число")
        if isinstance(raw, (int, float, Decimal)):
            dec = Decimal(str(raw))
        elif isinstance(raw, str) and raw.strip():
            try:
                dec = Decimal(raw.strip())
            except InvalidOperation as exc:
                raise ConstantTypeError("number — число") from exc
        else:
            raise ConstantTypeError("number — число")
        if not dec.is_finite():
            raise ConstantTypeError("number — конечное число")
        text = format(dec, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    if kind == "date":
        if isinstance(raw, datetime):
            return raw.date().isoformat()
        if isinstance(raw, date):
            return raw.isoformat()
        if isinstance(raw, str) and raw.strip():
            try:
                return date.fromisoformat(raw.strip()).isoformat()
            except ValueError as exc:
                raise ConstantTypeError("date — YYYY-MM-DD") from exc
        raise ConstantTypeError("date — YYYY-MM-DD")
    if kind == "boolean":
        if isinstance(raw, bool):
            return "true" if raw else "false"
        if isinstance(raw, (int, float)) and raw in (0, 1) and not isinstance(raw, bool):
            return "true" if int(raw) == 1 else "false"
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"true", "1"}:
                return "true"
            if lowered in {"false", "0"}:
                return "false"
        raise ConstantTypeError("boolean — true/false")
    raise ConstantTypeError(f"неизвестный kind {kind}")


def to_json_value(kind: str, stored: str) -> Any:
    if kind == "string":
        return stored
    if kind == "number":
        dec = Decimal(stored)
        if dec == dec.to_integral_value():
            return int(dec)
        return float(dec)
    if kind == "date":
        return stored
    if kind == "boolean":
        return stored == "true"
    raise ConstantTypeError(f"неизвестный kind {kind}")
