from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy.engine import Engine

from fgislk.mapper import row_from_payload
from fgislk.settings import max_workers
from fgislk.spd import SpdClient, SpdError
from fgislk.store import (
    last_ok_day,
    recent_read_ids,
    try_lock_subject,
    unlock_subject,
    upsert_piece,
    write_history,
)
from fgislk.windows import (
    all_subjects,
    audit_read_since,
    audit_window,
    incremental_window,
    moscow_today,
    yesterday,
)

log = logging.getLogger(__name__)

UPSERT_BATCH = 1000


class AlreadyRunning(Exception):
    def __init__(self, subject: str) -> None:
        super().__init__(f"импорт субъекта {subject} уже идёт")
        self.subject = subject


class JobSet:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def track(self, task: asyncio.Task) -> asyncio.Task:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def cancel_all(self) -> int:
        n = 0
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
                n += 1
        return n


class RunningSet:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def claim(self, subject: str, **info: Any) -> bool:
        async with self._lock:
            if subject in self._jobs:
                return False
            self._jobs[subject] = dict(info)
            return True

    async def update(self, subject: str, **fields: Any) -> None:
        async with self._lock:
            current = self._jobs.get(subject)
            if current is not None:
                current.update(fields)

    async def release(self, subject: str) -> None:
        async with self._lock:
            self._jobs.pop(subject, None)

    async def codes(self) -> list[str]:
        async with self._lock:
            return sorted(self._jobs)

    async def snapshot(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {"subject": code, **dict(data)}
                for code, data in sorted(self._jobs.items())
            ]


async def run_subject(
    *,
    engine: Engine,
    spd: SpdClient,
    running: RunningSet,
    subject: str,
    audit: bool,
    require_lock: bool,
    audit_from: date | None = None,
) -> str:
    if not await running.claim(
        subject, mode="audit" if audit else "incremental"
    ):
        if require_lock:
            raise AlreadyRunning(subject)
        return "busy"
    conn = engine.connect()
    period_start: date | None = None
    period_end: date | None = None
    try:
        if not try_lock_subject(conn, subject):
            if require_lock:
                raise AlreadyRunning(subject)
            return "busy"
        try:
            today = moscow_today()
            if audit:
                window = audit_window(today, start=audit_from)
            else:
                window = incremental_window(last_ok_day(conn, subject), today)
            if window is None:
                return "skip"
            start, end = window
            period_start, period_end = start, end
            await running.update(
                subject,
                period_start=start.isoformat(),
                period_end=end.isoformat(),
            )
            updated = await _import_window(
                conn,
                spd,
                subject,
                start,
                end,
                shrink=audit,
                running=running,
                commit_every=UPSERT_BATCH if audit else None,
                skip_fresh=audit,
                read_at=today,
            )
            write_history(
                conn,
                subject=subject,
                day=end if audit else yesterday(today),
                result="ok",
                updated_count=updated,
                error=None,
                period_start=start,
                period_end=end,
            )
            return "ok"
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                write_history(
                    conn,
                    subject=subject,
                    day=period_end if period_end is not None else _window_end(audit),
                    result="error",
                    updated_count=0,
                    error=str(exc)[:2000],
                    period_start=period_start,
                    period_end=period_end,
                )
            except Exception:
                log.exception("не записали историю ошибки субъекта %s", subject)
            log.exception("импорт субъекта %s", subject)
            if require_lock:
                raise
            return "error"
        finally:
            try:
                unlock_subject(conn, subject)
            except Exception:
                log.exception("не сняли lock субъекта %s", subject)
    finally:
        conn.close()
        await running.release(subject)


def _window_end(audit: bool) -> date:
    today = moscow_today()
    if audit:
        return audit_window(today)[1]
    return yesterday(today)


async def _import_window(
    conn,
    spd: SpdClient,
    subject: str,
    start: date,
    end: date,
    *,
    shrink: bool,
    running: RunningSet,
    commit_every: int | None = None,
    skip_fresh: bool = False,
    read_at: date | None = None,
) -> int:
    async def on_window(query_start: date, query_end: date) -> None:
        await running.update(
            subject,
            period_start=query_start.isoformat(),
            period_end=query_end.isoformat(),
        )

    ids = await spd.changed_ids(
        subject, start, end, shrink=shrink, on_window=on_window
    )
    today = read_at or moscow_today()
    to_fetch = ids
    skipped = 0
    if skip_fresh:
        fresh = recent_read_ids(conn, subject, audit_read_since(today))
        to_fetch = [fgis_id for fgis_id in ids if fgis_id not in fresh]
        skipped = len(ids) - len(to_fetch)
        if skipped:
            log.info(
                "аудит субъекта %s: пропуск %s из %s (read_at за 2 дня)",
                subject,
                skipped,
                len(ids),
            )
    fgis_count = len(ids)
    upserted = skipped
    await running.update(
        subject, updated_count=upserted, changed_total=fgis_count
    )
    pending = 0
    step = commit_every or UPSERT_BATCH
    for offset in range(0, len(to_fetch), step):
        await asyncio.sleep(0)
        chunk = to_fetch[offset : offset + step]
        try:
            payloads = await spd.taxation_pieces(chunk)
        except SpdError:
            log.warning("пачка карточек субъекта %s недоступна", subject)
            continue
        for fgis_id, payload in zip(chunk, payloads, strict=True):
            if not payload:
                continue
            row = row_from_payload(subject, fgis_id, payload)
            row["read_at"] = today
            upsert_piece(conn, row)
            upserted += 1
            pending += 1
        if commit_every is not None:
            conn.commit()
            pending = 0
            await running.update(subject, updated_count=upserted)
    if pending or commit_every is None:
        conn.commit()
    await running.update(subject, updated_count=upserted)
    return fgis_count


async def run_subjects(
    *,
    engine: Engine,
    spd: SpdClient,
    running: RunningSet,
    subjects: list[str] | None,
    audit: bool,
    require_lock: bool,
    audit_from: date | None = None,
) -> None:
    targets = subjects if subjects is not None else all_subjects()
    semaphore = asyncio.Semaphore(max_workers())

    async def one(code: str) -> None:
        async with semaphore:
            await run_subject(
                engine=engine,
                spd=spd,
                running=running,
                subject=code,
                audit=audit,
                require_lock=require_lock,
                audit_from=audit_from,
            )

    results = await asyncio.gather(
        *(one(code) for code in targets),
        return_exceptions=True,
    )
    for item in results:
        if isinstance(item, AlreadyRunning) and require_lock and len(targets) == 1:
            raise item
        if isinstance(item, Exception) and not isinstance(item, AlreadyRunning):
            log.exception("фоновый импорт", exc_info=item)


async def daily_loop(
    engine: Engine,
    running: RunningSet,
    stop: asyncio.Event,
    jobs: JobSet,
) -> None:
    from fgislk.windows import seconds_until_moscow_midnight

    while not stop.is_set():
        try:

            async def once() -> None:
                spd = SpdClient()
                try:
                    await run_subjects(
                        engine=engine,
                        spd=spd,
                        running=running,
                        subjects=None,
                        audit=False,
                        require_lock=False,
                    )
                finally:
                    await spd.aclose()

            task = jobs.track(asyncio.create_task(once()))
            try:
                await task
            except asyncio.CancelledError:
                me = asyncio.current_task()
                if me is not None and me.cancelling():
                    raise
                log.info("ежедневный импорт остановлен")
        except Exception:
            log.exception("ежедневный импорт")
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=seconds_until_moscow_midnight()
            )
        except TimeoutError:
            continue
