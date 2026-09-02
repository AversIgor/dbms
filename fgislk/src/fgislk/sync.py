from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy.engine import Engine

from fgislk.mapper import row_from_payload
from fgislk.settings import max_workers
from fgislk.spd import SpdClient, SpdError, kill_all_curl
from fgislk.store import (
    last_ok_day,
    recent_read_ids,
    try_lock_subject,
    unlock_subject,
    upsert_pieces,
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

FLUSH_BATCH = 100


class AlreadyRunning(Exception):
    def __init__(self, subject: str) -> None:
        super().__init__(f"импорт субъекта {subject} уже идёт")
        self.subject = subject


class RunningSet:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._halted = False
        self._generation = 0

    def halted(self) -> bool:
        return self._halted

    def same_gen(self, gen: int) -> bool:
        return gen == self._generation

    def reset(self) -> None:
        self._halted = False

    def track(self, task: asyncio.Task) -> asyncio.Task:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def cancel_tasks(self) -> int:
        n = 0
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
                n += 1
        return n

    async def drain(self) -> None:
        tasks = [task for task in list(self._tasks) if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def halt(self) -> list[str]:
        async with self._lock:
            self._halted = True
            self._generation += 1
            codes = sorted(self._jobs)
            self._jobs.clear()
            return codes

    async def claim(self, subject: str, **info: Any) -> int | None:
        async with self._lock:
            if self._halted or subject in self._jobs:
                return None
            self._jobs[subject] = {**info, "_gen": self._generation}
            return self._generation

    async def update(self, subject: str, **fields: Any) -> None:
        async with self._lock:
            current = self._jobs.get(subject)
            if current is not None:
                current.update(fields)

    async def release(self, subject: str, gen: int | None = None) -> None:
        async with self._lock:
            current = self._jobs.get(subject)
            if current is None:
                return
            if gen is not None and current.get("_gen") != gen:
                return
            self._jobs.pop(subject, None)

    async def codes(self) -> list[str]:
        async with self._lock:
            return sorted(self._jobs)

    async def inflight(self) -> bool:
        async with self._lock:
            if self._jobs:
                return True
        return any(not task.done() for task in list(self._tasks))

    async def snapshot(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {
                    "subject": code,
                    **{k: v for k, v in data.items() if k != "_gen"},
                }
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
    conn = engine.connect()
    period_start: date | None = None
    period_end: date | None = None
    gen: int | None = None
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
            start, end = window
            period_start, period_end = start, end
            gen = await running.claim(
                subject,
                mode="audit" if audit else "incremental",
                period_start=start.isoformat(),
                period_end=end.isoformat(),
                updated_count=0,
            )
            if gen is None:
                if require_lock:
                    raise AlreadyRunning(subject)
                return "busy"
            history_day = yesterday(today)
            updated = await _import_window(
                conn,
                spd,
                subject,
                start,
                end,
                shrink=audit,
                running=running,
                gen=gen,
                commit_every=FLUSH_BATCH if audit else None,
                skip_fresh=True,
                fresh_since=(
                    audit_read_since(today) if audit else yesterday(today)
                ),
                read_at=today,
                history_day=history_day,
            )
            if not running.same_gen(gen) or running.halted():
                return "stopped"
            write_history(
                conn,
                subject=subject,
                day=history_day,
                result="ok",
                updated_count=updated,
                error=None,
                period_start=start,
                period_end=end,
            )
            return "ok"
        except asyncio.CancelledError:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            if gen is not None and (
                not running.same_gen(gen) or running.halted()
            ):
                return "stopped"
            try:
                n = 0
                if gen is not None:
                    for job in await running.snapshot():
                        if job["subject"] == subject:
                            n = int(job.get("updated_count") or 0)
                            break
                write_history(
                    conn,
                    subject=subject,
                    day=yesterday(),
                    result="error",
                    updated_count=n,
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
        if gen is not None:
            await running.release(subject, gen)


async def _import_window(
    conn,
    spd: SpdClient,
    subject: str,
    start: date,
    end: date,
    *,
    shrink: bool,
    running: RunningSet,
    gen: int,
    commit_every: int | None = None,
    skip_fresh: bool = False,
    fresh_since: date | None = None,
    read_at: date | None = None,
    history_day: date | None = None,
) -> int:
    async def on_window(query_start: date, query_end: date) -> None:
        if not running.same_gen(gen) or running.halted():
            raise asyncio.CancelledError
        await running.update(
            subject,
            period_start=query_start.isoformat(),
            period_end=query_end.isoformat(),
        )

    if not running.same_gen(gen) or running.halted():
        raise asyncio.CancelledError
    ids = await spd.changed_ids(
        subject, start, end, shrink=shrink, on_window=on_window
    )
    if not running.same_gen(gen) or running.halted():
        raise asyncio.CancelledError
    today = read_at or moscow_today()
    to_fetch = ids
    skipped = 0
    if skip_fresh:
        since = fresh_since or audit_read_since(today)
        fresh = recent_read_ids(conn, subject, since, ids)
        to_fetch = [fgis_id for fgis_id in ids if fgis_id not in fresh]
        skipped = len(ids) - len(to_fetch)
        if skipped:
            log.info(
                "субъект %s: пропуск %s из %s (read_at >= %s)",
                subject,
                skipped,
                len(ids),
                since.isoformat(),
            )
    fgis_count = len(ids)
    upserted = skipped
    await running.update(
        subject, updated_count=upserted, changed_total=fgis_count
    )
    for offset in range(0, len(to_fetch), FLUSH_BATCH):
        if not running.same_gen(gen) or running.halted():
            raise asyncio.CancelledError
        await asyncio.sleep(0)
        chunk = to_fetch[offset : offset + FLUSH_BATCH]
        payloads: list[dict[str, Any] | None] | None = None
        for attempt in range(3):
            try:
                payloads = await spd.taxation_pieces(chunk)
                break
            except SpdError:
                log.warning(
                    "пачка карточек субъекта %s, попытка %s",
                    subject,
                    attempt + 1,
                )
        if payloads is None:
            log.warning("пачка карточек субъекта %s недоступна", subject)
            continue
        rows: list[dict[str, Any]] = []
        for fgis_id, payload in zip(chunk, payloads, strict=True):
            if not payload:
                continue
            row = row_from_payload(subject, fgis_id, payload)
            row["read_at"] = today
            rows.append(row)
        if rows:
            upsert_pieces(conn, rows)
            upserted += len(rows)
        conn.commit()
        await running.update(subject, updated_count=upserted)
        if commit_every is not None and history_day is not None:
            write_history(
                conn,
                subject=subject,
                day=history_day,
                result="partial",
                updated_count=upserted,
                error=None,
                period_start=start,
                period_end=end,
            )
    await running.update(subject, updated_count=upserted)
    return upserted


async def stop_import(running: RunningSet) -> int:
    codes = await running.halt()
    cancelled = running.cancel_tasks()
    kill_all_curl()
    await running.drain()
    return max(len(codes), cancelled)


async def _wait_next_run(
    stop: asyncio.Event,
    kick: asyncio.Event,
    timeout: float,
) -> bool:
    """True — полуночь или start=1; False — выключение процесса."""
    if stop.is_set():
        return False
    if kick.is_set():
        return True
    stop_task = asyncio.create_task(stop.wait())
    kick_task = asyncio.create_task(kick.wait())
    try:
        _done, pending = await asyncio.wait(
            {stop_task, kick_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return not stop.is_set()
    except asyncio.CancelledError:
        stop_task.cancel()
        kick_task.cancel()
        await asyncio.gather(stop_task, kick_task, return_exceptions=True)
        raise


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

    tasks = [running.track(asyncio.create_task(one(code))) for code in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for item in results:
        if isinstance(item, AlreadyRunning) and require_lock and len(targets) == 1:
            raise item
        if isinstance(item, BaseException) and not isinstance(
            item, (AlreadyRunning, asyncio.CancelledError)
        ):
            log.exception("фоновый импорт", exc_info=item)


async def daily_loop(
    engine: Engine,
    running: RunningSet,
    stop: asyncio.Event,
    kick: asyncio.Event,
) -> None:
    from fgislk.windows import seconds_until_moscow_midnight

    first = True
    while not stop.is_set():
        if not first:
            if not kick.is_set() and not stop.is_set():
                if not await _wait_next_run(
                    stop, kick, seconds_until_moscow_midnight()
                ):
                    return
        first = False
        kick.clear()
        if await running.inflight():
            log.info("ежедневный импорт ждёт текущий прогон")
            await running.drain()
            if stop.is_set():
                return
            if await running.inflight():
                await asyncio.sleep(1)
                continue
        try:
            running.reset()

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

            task = running.track(asyncio.create_task(once()))
            try:
                await task
            except asyncio.CancelledError:
                me = asyncio.current_task()
                if me is not None and me.cancelling():
                    raise
                log.info("ежедневный импорт остановлен")
        except Exception:
            log.exception("ежедневный импорт")
