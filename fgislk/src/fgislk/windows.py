from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")
AUDIT_START = date(2023, 5, 1)
AUDIT_READ_DAYS = 2


def moscow_today(now: datetime | None = None) -> date:
    current = now or datetime.now(MSK)
    if current.tzinfo is None:
        current = current.replace(tzinfo=MSK)
    return current.astimezone(MSK).date()


def yesterday(today: date | None = None) -> date:
    return (today or moscow_today()) - timedelta(days=1)


def audit_read_since(today: date | None = None) -> date:
    """Аудит не читает карточку, если read_at >= этот день (как 1С, окно 2 дня)."""
    return (today or moscow_today()) - timedelta(days=AUDIT_READ_DAYS)


def incremental_window(
    last_ok: date | None, today: date | None = None
) -> tuple[date, date]:
    """Окно догона к СПД: (last_ok+1)…сегодня, старт не позже вчера.

    endDate для ФГИС — сегодня, иначе вчера в выборку не попадает.
    Закрываемый день журнала — вчера. Если вчера уже в watermark —
    всё равно вчера…сегодня: за вчера ещё могли прийти обновления.
    """
    today = today or moscow_today()
    closed = today - timedelta(days=1)
    start = closed if last_ok is None else last_ok + timedelta(days=1)
    if start > closed:
        start = closed
    return start, today


def parse_audit_day(value: str, today: date | None = None) -> date:
    today = today or moscow_today()
    text = value.strip()
    try:
        day = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("day — дата YYYY-MM-DD") from exc
    if day < AUDIT_START:
        raise ValueError(f"day не раньше {AUDIT_START.isoformat()}")
    if day > today:
        raise ValueError("day не позже сегодня (МСК)")
    return day


def audit_window(
    today: date | None = None, start: date | None = None
) -> tuple[date, date]:
    today = today or moscow_today()
    begin = AUDIT_START if start is None else start
    return begin, today


def add_month(day: date) -> date:
    if day.month == 12:
        year, month = day.year + 1, 1
    else:
        year, month = day.year, day.month + 1
    last = monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def all_subjects() -> list[str]:
    return [f"{n:02d}" for n in range(1, 100)]


def normalize_subject(value: str) -> str:
    text = value.strip()
    if not text.isdigit():
        raise ValueError("subject — код 01…99")
    number = int(text)
    if number < 1 or number > 99:
        raise ValueError("subject — код 01…99")
    return f"{number:02d}"


def parse_subjects(value: str) -> list[str]:
    """Один код или список через запятую: 07 или 07,16,21."""
    codes: list[str] = []
    seen: set[str] = set()
    for part in value.replace(";", ",").split(","):
        piece = part.strip()
        if not piece:
            continue
        code = normalize_subject(piece)
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    if not codes:
        raise ValueError("subject — код 01…99 или список через запятую")
    return codes


def seconds_until_moscow_midnight(now: datetime | None = None) -> float:
    current = now or datetime.now(MSK)
    if current.tzinfo is None:
        current = current.replace(tzinfo=MSK)
    current = current.astimezone(MSK)
    tomorrow = current.date() + timedelta(days=1)
    target = datetime.combine(tomorrow, datetime.min.time(), tzinfo=MSK)
    return max(1.0, (target - current).total_seconds())
