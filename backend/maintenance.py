"""Lekkie, procesowe zadania utrzymaniowe backendu.

Nie wymagają zewnętrznego schedulera. Każdy worker uruchamia pętlę, ale transakcyjny
lock i dzienny wpis audytu sprawiają, że retencję wykonuje najwyżej jeden worker.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
import os
import threading
from typing import Optional

from sqlalchemy import text

import models
from database import SessionLocal
from deps import utcnow_naive
from routers.rodo import RETENTION_AUDIT_ACTION, wykonaj_retencje_rodo


logger = logging.getLogger(__name__)

_RETENTION_LOCK_ID = 1_281_315_151  # stabilny 64-bit key: "LOKALO"
_DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60
_MIN_INTERVAL_SECONDS = 5 * 60
_stop_event = threading.Event()
_state_lock = threading.Lock()
_thread: Optional[threading.Thread] = None


def _interval_seconds() -> int:
    try:
        configured = int(os.environ.get(
            "RODO_RETENTION_INTERVAL_SECONDS",
            str(_DEFAULT_INTERVAL_SECONDS),
        ))
    except (TypeError, ValueError):
        configured = _DEFAULT_INTERVAL_SECONDS
    return max(_MIN_INTERVAL_SECONDS, configured)


def _try_acquire_retention_lock(db) -> bool:
    """Serializuje workery bez dodatkowej tabeli ani zależności.

    PostgreSQL używa transakcyjnego advisory locka. SQLite blokuje zapis przez
    ``BEGIN IMMEDIATE``; funkcja jest wywoływana wyłącznie na świeżej sesji.
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return bool(db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": _RETENTION_LOCK_ID},
        ).scalar())
    if dialect == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    return True


def run_retention_maintenance_once(*, now: Optional[datetime] = None) -> dict:
    """Uruchamia jeden przebieg, atomowo i najwyżej raz dziennie przy realnej pracy."""
    effective_now = now or utcnow_naive()
    db = SessionLocal()
    try:
        if not _try_acquire_retention_lock(db):
            db.rollback()
            return {"status": "locked", "liczba_zmian": 0}

        day_start = datetime.combine(effective_now.date(), time.min)
        day_end = day_start + timedelta(days=1)
        already_ran = db.query(models.AuditLog.id).filter(
            models.AuditLog.akcja == RETENTION_AUDIT_ACTION,
            models.AuditLog.ts >= day_start,
            models.AuditLog.ts < day_end,
        ).first()
        if already_ran is not None:
            db.rollback()
            return {"status": "already_run", "liczba_zmian": 0}

        wynik = wykonaj_retencje_rodo(
            db,
            now=effective_now,
            actor=None,
            zrodlo="maintenance",
            audit_action=RETENTION_AUDIT_ACTION,
            audituj_pusty=False,
        )
        if wynik["liczba_zmian"]:
            db.commit()
            return {"status": "executed", **wynik}

        # Cleanup używa tej samej transakcji; przy braku zmian rollback zwalnia lock
        # i nie tworzy codziennych pustych wpisów w dzienniku audytu.
        db.rollback()
        return {"status": "no_changes", **wynik}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _run_safely() -> None:
    try:
        run_retention_maintenance_once()
    except Exception:
        logger.exception("Automatyczna retencja RODO nie powiodła się; ponowi ją kolejny przebieg.")


def _maintenance_loop() -> None:
    while not _stop_event.is_set():
        _run_safely()
        if _stop_event.wait(_interval_seconds()):
            return


def _uses_ephemeral_sqlite() -> bool:
    """In-memory DB nie przechowuje danych między startami i bywa współdzielona jednym połączeniem."""
    bind = SessionLocal.kw.get("bind")
    return bool(
        bind is not None
        and bind.dialect.name == "sqlite"
        and not bind.url.database
    )


def start_maintenance() -> None:
    """Uruchamia lekką pętlę; pierwszy skan odbywa się poza krytyczną ścieżką startupu."""
    global _thread
    with _state_lock:
        if _thread is not None and _thread.is_alive():
            return
        if _uses_ephemeral_sqlite():
            return
        _stop_event.clear()
        _thread = threading.Thread(
            target=_maintenance_loop,
            name="lokalo-maintenance",
            daemon=True,
        )
        _thread.start()


def stop_maintenance() -> None:
    """Kończy pętlę bez czekania na pełny interwał."""
    global _thread
    with _state_lock:
        thread = _thread
        _stop_event.set()
    if thread is not None:
        thread.join(timeout=2)
    with _state_lock:
        if _thread is thread and (thread is None or not thread.is_alive()):
            _thread = None
