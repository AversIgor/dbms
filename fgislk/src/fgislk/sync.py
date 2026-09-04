from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from sqlalchemy.engine import Engine

from fgislk.mapper import (
    clearcut_row_from_payload,
    quarter_row_from_payload,
    row_from_payload,
)
from fgislk.settings import (
    IMPORT_ORDER,
    KIND_CLEARCUT,
    KIND_QUARTERS,
    KIND_TAXATION_PIECE,
    SPD_RESOURCE,
    batch_workers,
    max_workers,
)
from fgislk.spd import SpdClient, SpdError, kill_all_curl
from fgislk.store import (
    last_ok_day,
    ping_lock,
    quarters_for_clearcut,
    recent_read_ids,
    recent_read_ids_subject,
    stamp_clearcut_poll,
    stamp_clearcut_polls,
    try_lock_subject,
    unlock_subject,
    upsert_clearcuts,
    upsert_pieces,
    upsert_quarters,
    write_history,
)
from fgislk.windows import (
    all_subjects,
    audit_read_since,
    audit_window,
    clearcut_full_scan,
    incremental_window,
    moscow_today,
    yesterday,
)

log = logging.getLogger(__name__)

FLUSH_BATCH = 100
# Карточки с контуром: меньше тел в одном curl, иначе OOM на Linux.
AREA_BATCH = 5
_LOCK_PING_SEC = 20.0

_ROW_FROM = {
    KIND_QUARTERS: quarter_row_from_payload,
    KIND_TAXATION_PIECE: row_from_payload,
    KIND_CLEARCUT: clearcut_row_from_payload,
}
_UPSERT = {
    KIND_QUARTERS: upsert_quarters,
    KIND_TAXATION_PIECE: upsert_pieces,
    KIND_CLEARCUT: upsert_clearcuts,
}


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
        self._drain: asyncio.Task | None = None

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

    def schedule_drain(self) -> None:
        if self._drain is not None and not self._drain.done():
            return
        self._drain = asyncio.create_task(self.drain())

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


async def _hold_advisory(conn, subject: str) -> None:
    try:
        while True:
            await asyncio.sleep(_LOCK_PING_SEC)
            ping_lock(conn)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("потеряли lock-соединение субъекта %s", subject)


async def run_subject(
    *,
    engine: Engine,
    spd: SpdClient,
    running: RunningSet,
    subject: str,
    audit: bool,
    require_lock: bool,
    audit_from: date | None = None,
    kinds: list[str] | None = None,
    need_area: bool = True,
    quarter_id: str | None = None,
) -> str:
    lock_conn = engine.connect()
    gen: int | None = None
    ping: asyncio.Task | None = None
    try:
        if not try_lock_subject(lock_conn, subject):
            if require_lock:
                raise AlreadyRunning(subject)
            return "busy"
        ping = asyncio.create_task(_hold_advisory(lock_conn, subject))
        try:
            today = moscow_today()
            history_day = yesterday(today)
            order = kinds if kinds is not None else list(IMPORT_ORDER)
            gen = await running.claim(
                subject,
                mode="audit" if audit else "incremental",
                data_kind=order[0],
                updated_count=0,
            )
            if gen is None:
                if require_lock:
                    raise AlreadyRunning(subject)
                return "busy"
            last_error: Exception | None = None
            last_result = "ok"
            for kind in order:
                if not running.same_gen(gen) or running.halted():
                    return "stopped"
                period_start: date | None = None
                period_end: date | None = None
                try:
                    if audit:
                        window = audit_window(today, start=audit_from)
                    else:
                        with engine.connect() as conn:
                            watermark = last_ok_day(conn, subject, kind)
                        window = incremental_window(watermark, today)
                    start, end = window
                    period_start, period_end = start, end
                    await running.update(
                        subject,
                        data_kind=kind,
                        period_start=start.isoformat(),
                        period_end=end.isoformat(),
                        updated_count=0,
                        changed_total=None,
                    )
                    if kind == KIND_CLEARCUT:
                        updated = await _import_clearcuts(
                            engine,
                            spd,
                            subject,
                            start,
                            end,
                            audit=audit,
                            running=running,
                            gen=gen,
                            skip_fresh=quarter_id is None,
                            fresh_since=(
                                audit_read_since(today)
                                if audit
                                else yesterday(today)
                            ),
                            read_at=today,
                            history_day=history_day,
                            need_area=need_area,
                            quarter_id=quarter_id,
                        )
                    else:
                        updated = await _import_window(
                            engine,
                            spd,
                            subject,
                            start,
                            end,
                            kind=kind,
                            shrink=audit,
                            running=running,
                            gen=gen,
                            commit_every=FLUSH_BATCH if audit else None,
                            skip_fresh=True,
                            fresh_since=(
                                audit_read_since(today)
                                if audit
                                else yesterday(today)
                            ),
                            read_at=today,
                            history_day=history_day,
                            need_area=need_area,
                        )
                    if not running.same_gen(gen) or running.halted():
                        return "stopped"
                    with engine.connect() as conn:
                        write_history(
                            conn,
                            subject=subject,
                            day=history_day,
                            result="ok",
                            updated_count=updated,
                            error=None,
                            data_kind=kind,
                            period_start=start,
                            period_end=end,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
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
                        with engine.connect() as conn:
                            write_history(
                                conn,
                                subject=subject,
                                day=yesterday(),
                                result="error",
                                updated_count=n,
                                error=str(exc)[:2000],
                                data_kind=kind,
                                period_start=period_start,
                                period_end=period_end,
                            )
                    except Exception:
                        log.exception(
                            "не записали историю ошибки субъекта %s %s",
                            subject,
                            kind,
                        )
                    log.exception("импорт субъекта %s %s", subject, kind)
                    last_error = exc
                    last_result = "error"
                    continue
            if last_error is not None and require_lock:
                raise last_error
            return last_result
        finally:
            if ping is not None:
                ping.cancel()
                await asyncio.gather(ping, return_exceptions=True)
            try:
                unlock_subject(lock_conn, subject)
            except Exception:
                log.exception("не сняли lock субъекта %s", subject)
    finally:
        lock_conn.close()
        if gen is not None:
            await running.release(subject, gen)


async def _import_clearcuts(
    engine: Engine,
    spd: SpdClient,
    subject: str,
    start: date,
    end: date,
    *,
    audit: bool,
    running: RunningSet,
    gen: int,
    skip_fresh: bool,
    fresh_since: date | None,
    read_at: date,
    history_day: date,
    need_area: bool,
    quarter_id: str | None,
) -> int:
    if not running.same_gen(gen) or running.halted():
        raise asyncio.CancelledError
    with engine.connect() as conn:
        queue = quarters_for_clearcut(
            conn,
            subject,
            audit=audit,
            period_start=start,
            quarter_id=quarter_id,
            full_scan=(
                not audit
                and not quarter_id
                and clearcut_full_scan(subject, read_at)
            ),
            today=None if quarter_id else read_at,
        )
        since = fresh_since or audit_read_since(read_at)
        fresh: set[str] = set()
        if skip_fresh:
            fresh = recent_read_ids_subject(
                conn, subject, since, data_kind=KIND_CLEARCUT
            )
    total = len(queue)
    upserted = 0
    processed = 0
    await running.update(
        subject, updated_count=0, changed_total=total, progress_count=0
    )
    db_lock = asyncio.Lock()
    cursor = 0
    cursor_lock = asyncio.Lock()
    n_chunks = (total + FLUSH_BATCH - 1) // FLUSH_BATCH if total else 0
    n_workers = min(batch_workers(), n_chunks) if n_chunks else 0

    async def mark_progress(n_cards: int, n_quarters: int) -> None:
        nonlocal upserted, processed
        upserted += n_cards
        prev = processed
        processed += n_quarters
        await running.update(
            subject, updated_count=upserted, progress_count=processed
        )
        if (
            audit
            and n_quarters
            and processed // FLUSH_BATCH > prev // FLUSH_BATCH
        ):
            with engine.connect() as conn:
                write_history(
                    conn,
                    subject=subject,
                    day=history_day,
                    result="partial",
                    updated_count=upserted,
                    error=None,
                    data_kind=KIND_CLEARCUT,
                    period_start=start,
                    period_end=end,
                )

    async def fetch_quarter_cards(qid: str, ids: list[str]) -> int | None:
        to_fetch = ids
        skipped = 0
        if skip_fresh and ids:
            to_fetch = [fgis_id for fgis_id in ids if fgis_id not in fresh]
            skipped = len(ids) - len(to_fetch)
        n = skipped
        missing = False
        fetched: list[str] = []
        for offset in range(0, len(to_fetch), FLUSH_BATCH):
            if not running.same_gen(gen) or running.halted():
                raise asyncio.CancelledError
            chunk = to_fetch[offset : offset + FLUSH_BATCH]
            payloads: list[dict[str, Any] | None] | None = None
            for attempt in range(3):
                try:
                    payloads = await spd.cards(
                        chunk,
                        resource=SPD_RESOURCE[KIND_CLEARCUT],
                        need_area=need_area,
                    )
                    break
                except SpdError:
                    log.warning(
                        "карточки лесосек субъекта %s квартал %s, попытка %s",
                        subject,
                        qid,
                        attempt + 1,
                    )
            if payloads is None:
                missing = True
                break
            if any(item is None for item in payloads):
                log.warning(
                    "квартал %s: часть карточек лесосек без ответа", qid
                )
                missing = True
            rows = await asyncio.to_thread(
                _rows_from_payloads,
                KIND_CLEARCUT,
                subject,
                chunk,
                payloads,
                read_at,
            )
            async with db_lock:
                if not running.same_gen(gen) or running.halted():
                    raise asyncio.CancelledError
                with engine.connect() as conn:
                    if rows:
                        upsert_clearcuts(conn, rows)
                        fetched.extend(row["fgis_id"] for row in rows)
                    n += len(rows)
                    conn.commit()
        if missing:
            log.warning("квартал %s: не все карточки лесосек", qid)
            return None
        if fetched:
            fresh.update(fetched)
        return n

    async def process_chunk(qids: list[str]) -> None:
        if not running.same_gen(gen) or running.halted():
            raise asyncio.CancelledError
        lists = await spd.clearcut_ids_by_quarters(qids)
        empty: list[str] = []
        filled: list[tuple[str, list[str]]] = []
        for qid, ids in zip(qids, lists, strict=True):
            if ids is None:
                log.warning("список лесосек квартала %s: нет ответа", qid)
                async with db_lock:
                    if not running.same_gen(gen) or running.halted():
                        raise asyncio.CancelledError
                    await mark_progress(0, 1)
                continue
            if ids:
                filled.append((qid, ids))
            else:
                empty.append(qid)
        if empty:
            async with db_lock:
                if not running.same_gen(gen) or running.halted():
                    raise asyncio.CancelledError
                with engine.connect() as conn:
                    stamp_clearcut_polls(
                        conn,
                        subject,
                        empty,
                        polled_at=read_at,
                        has_clearcuts=False,
                    )
                    conn.commit()
                await mark_progress(0, len(empty))
        for qid, ids in filled:
            n = await fetch_quarter_cards(qid, ids)
            if n is None:
                async with db_lock:
                    if not running.same_gen(gen) or running.halted():
                        raise asyncio.CancelledError
                    await mark_progress(0, 1)
                continue
            async with db_lock:
                if not running.same_gen(gen) or running.halted():
                    raise asyncio.CancelledError
                with engine.connect() as conn:
                    stamp_clearcut_poll(
                        conn,
                        subject,
                        qid,
                        polled_at=read_at,
                        has_clearcuts=True,
                    )
                    conn.commit()
                await mark_progress(n, 1)

    async def worker() -> None:
        nonlocal cursor
        while True:
            async with cursor_lock:
                if cursor >= total:
                    return
                start_at = cursor
                cursor += FLUSH_BATCH
                chunk = queue[start_at:cursor]
            await process_chunk(chunk)

    if n_workers:
        await asyncio.gather(*[worker() for _ in range(n_workers)])
    await running.update(
        subject, updated_count=upserted, progress_count=processed
    )
    return upserted


async def _import_window(
    engine: Engine,
    spd: SpdClient,
    subject: str,
    start: date,
    end: date,
    *,
    kind: str,
    shrink: bool,
    running: RunningSet,
    gen: int,
    commit_every: int | None = None,
    skip_fresh: bool = False,
    fresh_since: date | None = None,
    read_at: date | None = None,
    history_day: date | None = None,
    need_area: bool = True,
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
        subject,
        start,
        end,
        resource=SPD_RESOURCE[kind],
        shrink=shrink,
        on_window=on_window,
    )
    if not running.same_gen(gen) or running.halted():
        raise asyncio.CancelledError
    today = read_at or moscow_today()
    to_fetch = ids
    skipped = 0
    if skip_fresh:
        since = fresh_since or audit_read_since(today)
        with engine.connect() as conn:
            fresh = recent_read_ids(conn, subject, since, ids, data_kind=kind)
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
    db_lock = asyncio.Lock()
    cursor = 0
    cursor_lock = asyncio.Lock()
    total = len(to_fetch)
    http_batch = AREA_BATCH if need_area else FLUSH_BATCH
    n_chunks = (total + FLUSH_BATCH - 1) // FLUSH_BATCH if total else 0
    n_workers = min(batch_workers(), n_chunks) if n_chunks else 0

    async def flush_http(chunk: list[str]) -> None:
        nonlocal upserted
        payloads: list[dict[str, Any] | None] | None = None
        for attempt in range(3):
            try:
                payloads = await spd.cards(
                    chunk, resource=SPD_RESOURCE[kind], need_area=need_area
                )
                break
            except SpdError:
                log.warning(
                    "пачка карточек субъекта %s, попытка %s",
                    subject,
                    attempt + 1,
                )
        if payloads is None:
            log.warning("пачка карточек субъекта %s недоступна", subject)
            return
        if not running.same_gen(gen) or running.halted():
            raise asyncio.CancelledError
        rows = await asyncio.to_thread(
            _rows_from_payloads, kind, subject, chunk, payloads, today
        )
        payloads.clear()
        async with db_lock:
            if not running.same_gen(gen) or running.halted():
                raise asyncio.CancelledError
            with engine.connect() as conn:
                if rows:
                    _UPSERT[kind](conn, rows)
                    upserted += len(rows)
                conn.commit()
                await running.update(subject, updated_count=upserted)

    async def process_chunk(chunk: list[str]) -> None:
        for offset in range(0, len(chunk), http_batch):
            if not running.same_gen(gen) or running.halted():
                raise asyncio.CancelledError
            await flush_http(chunk[offset : offset + http_batch])
        async with db_lock:
            if not running.same_gen(gen) or running.halted():
                raise asyncio.CancelledError
            await running.update(subject, updated_count=upserted)
            if commit_every is not None and history_day is not None:
                with engine.connect() as conn:
                    write_history(
                        conn,
                        subject=subject,
                        day=history_day,
                        result="partial",
                        updated_count=upserted,
                        error=None,
                        data_kind=kind,
                        period_start=start,
                        period_end=end,
                    )

    async def worker() -> None:
        nonlocal cursor
        while True:
            async with cursor_lock:
                if cursor >= total:
                    return
                start_at = cursor
                cursor += FLUSH_BATCH
                chunk = to_fetch[start_at:cursor]
            await process_chunk(chunk)

    if n_workers:
        await asyncio.gather(*[worker() for _ in range(n_workers)])
    await running.update(subject, updated_count=upserted)
    return upserted


def _rows_from_payloads(
    kind: str,
    subject: str,
    chunk: list[str],
    payloads: list[dict[str, Any] | None],
    today: date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (fgis_id, payload) in enumerate(
        zip(chunk, payloads, strict=True)
    ):
        if not payload:
            continue
        row = _ROW_FROM[kind](subject, fgis_id, payload)
        row["read_at"] = today
        rows.append(row)
        payloads[index] = None
    return rows


async def stop_import(running: RunningSet) -> int:
    codes = await running.halt()
    cancelled = running.cancel_tasks()
    kill_all_curl()
    running.schedule_drain()
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
    kinds: list[str] | None = None,
    need_area: bool = True,
    quarter_id: str | None = None,
) -> None:
    targets = subjects if subjects is not None else all_subjects()
    order = kinds if kinds is not None else list(IMPORT_ORDER)

    async def wave(code: str, wave_kind: str, slots: asyncio.Semaphore) -> None:
        async with slots:
            await run_subject(
                engine=engine,
                spd=spd,
                running=running,
                subject=code,
                audit=audit,
                require_lock=require_lock,
                audit_from=audit_from,
                kinds=[wave_kind],
                need_area=need_area,
                quarter_id=quarter_id,
            )

    for kind in order:
        if running.halted():
            return
        slots = asyncio.Semaphore(max_workers())
        tasks = [
            running.track(asyncio.create_task(wave(code, kind, slots)))
            for code in targets
        ]
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
