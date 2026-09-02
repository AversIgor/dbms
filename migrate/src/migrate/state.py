from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class UpgradeResult:
    ok: bool | None = None
    message: str = "upgrade в этом процессе не выполнялся"
    at: str | None = None
    revision: str | None = None


_last = UpgradeResult()


def last_upgrade() -> UpgradeResult:
    return _last


def record_upgrade(*, ok: bool, message: str, revision: str | None = None) -> UpgradeResult:
    global _last
    _last = UpgradeResult(
        ok=ok,
        message=message,
        at=datetime.now(timezone.utc).isoformat(),
        revision=revision,
    )
    return _last
