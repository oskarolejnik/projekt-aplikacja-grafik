"""Wspolne, pozbawione PII fakty operacyjne rezerwacji dla CRM i R7.

Modul nie utrwala agregatow. Czyta kanoniczny ``Termin`` oraz historyczne
snapshoty planu, dzieki czemu profil goscia i analityka uzywaja tych samych
definicji rzeczywistego czasu wizyty i przydzialu.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import time

from sqlalchemy.orm import Session

import models


MAX_ACTUAL_TURN_MINUTES = 24 * 60
_TABLE_CHANGE_FIELDS = frozenset({
    "stolik_id",
    "stoliki_dodatkowe",
    "przydzial_wersja_planu_id",
    "przydzial_kombinacja_planu_id",
})


def planned_turn_minutes(termin: models.Termin) -> int | None:
    start, end = termin.godz_od, termin.godz_do
    if not isinstance(start, time) or not isinstance(end, time):
        return None
    minutes = end.hour * 60 + end.minute - (start.hour * 60 + start.minute)
    if minutes < 0:
        minutes += 24 * 60
    return minutes if 0 < minutes <= 24 * 60 else None


def actual_turn_measurement(termin: models.Termin) -> dict:
    seated, left = termin.host_seated_at, termin.host_left_at
    if seated is None or left is None:
        return {"pomiar": "missing", "rzeczywisty_czas_min": None}
    seconds = (left - seated).total_seconds()
    minutes = max(1, int(round(seconds / 60))) if seconds > 0 else 0
    if seconds <= 0 or minutes > MAX_ACTUAL_TURN_MINUTES:
        return {"pomiar": "invalid", "rzeczywisty_czas_min": None}
    return {"pomiar": "complete", "rzeczywisty_czas_min": minutes}


def party_bucket(people: int | None) -> str | None:
    if isinstance(people, bool) or not isinstance(people, int) or people <= 0:
        return None
    if people <= 2:
        return "1-2"
    if people <= 4:
        return "3-4"
    if people <= 6:
        return "5-6"
    return "7+"


def _table_ids(termin: models.Termin) -> list[int]:
    additional = termin.stoliki_dodatkowe
    if not isinstance(additional, (list, tuple, set)):
        additional = []
    values = [termin.stolik_id, *additional]
    result = []
    seen = set()
    for raw in values:
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0 or raw in seen:
            continue
        seen.add(raw)
        result.append(raw)
    return result


def allocation_snapshots(
    db: Session,
    reservations: Iterable[models.Termin],
) -> dict[int, dict]:
    """Buduje bezpieczne historyczne etykiety przydzialu w stalych kilku zapytaniach."""
    rows = [row for row in reservations if row.id is not None]
    table_ids = {value for row in rows for value in _table_ids(row)}
    version_ids = {
        int(row.przydzial_wersja_planu_id)
        for row in rows if row.przydzial_wersja_planu_id is not None
    }
    combination_ids = {
        int(row.przydzial_kombinacja_planu_id)
        for row in rows if row.przydzial_kombinacja_planu_id is not None
    }

    tables = {
        row.id: row
        for row in (
            db.query(models.Stolik).filter(models.Stolik.id.in_(table_ids)).all()
            if table_ids else []
        )
    }
    versions = {
        row.id: row
        for row in (
            db.query(models.WersjaPlanuSali)
            .filter(models.WersjaPlanuSali.id.in_(version_ids)).all()
            if version_ids else []
        )
    }
    plan_ids = {row.plan_id for row in versions.values()}
    plans = {
        row.id: row
        for row in (
            db.query(models.PlanSali).filter(models.PlanSali.id.in_(plan_ids)).all()
            if plan_ids else []
        )
    }
    room_ids = {row.sala_id for row in plans.values()}
    room_ids.update(
        table.sala_id for table in tables.values() if table.sala_id is not None
    )
    rooms = {
        row.id: row
        for row in (
            db.query(models.SalaRezerwacyjna)
            .filter(models.SalaRezerwacyjna.id.in_(room_ids)).all()
            if room_ids else []
        )
    }
    positions = {
        (row.wersja_id, row.stolik_id): row
        for row in (
            db.query(models.PozycjaStolikaPlanu).filter(
                models.PozycjaStolikaPlanu.wersja_id.in_(version_ids),
                models.PozycjaStolikaPlanu.stolik_id.in_(table_ids),
            ).all()
            if version_ids and table_ids else []
        )
    }
    combinations = {
        (row.wersja_id, row.id): row
        for row in (
            db.query(models.KombinacjaStolowPlanu).filter(
                models.KombinacjaStolowPlanu.id.in_(combination_ids),
                models.KombinacjaStolowPlanu.wersja_id.in_(version_ids),
            ).all()
            if combination_ids and version_ids else []
        )
    }
    combination_members: dict[tuple[int, int], set[int]] = {}
    if combination_ids and version_ids:
        for member in db.query(models.SkladnikKombinacjiPlanu).filter(
            models.SkladnikKombinacjiPlanu.kombinacja_id.in_(combination_ids),
            models.SkladnikKombinacjiPlanu.wersja_id.in_(version_ids),
        ).all():
            combination_members.setdefault(
                (member.wersja_id, member.kombinacja_id), set(),
            ).add(member.stolik_id)

    result = {}
    for reservation in rows:
        ids = _table_ids(reservation)
        version_id = reservation.przydzial_wersja_planu_id
        frozen_positions = [positions.get((version_id, table_id)) for table_id in ids]
        frozen = bool(ids and version_id and all(frozen_positions))
        version = versions.get(version_id)
        plan = plans.get(version.plan_id) if version is not None else None
        room_id = plan.sala_id if plan is not None else None
        if room_id is None and ids:
            room_id = getattr(tables.get(ids[0]), "sala_id", None)
        room = rooms.get(room_id)
        room_name = getattr(room, "nazwa", None)
        if room_name is None:
            room_name = reservation.sala or (
                getattr(tables.get(ids[0]), "strefa", None) if ids else None
            )

        table_items = []
        for table_id, position in zip(ids, frozen_positions):
            table = tables.get(table_id)
            name = (
                getattr(position, "nazwa", None)
                or getattr(table, "nazwa", None)
                or f"Stolik {table_id}"
            )
            table_items.append({"id": table_id, "nazwa": name})

        combination = None
        combination_id = reservation.przydzial_kombinacja_planu_id
        frozen_combination = combinations.get((version_id, combination_id))
        if (
            frozen_combination is not None
            and combination_members.get((version_id, combination_id), set()) == set(ids)
        ):
            combination = {
                "id": frozen_combination.id,
                "wersja_id": frozen_combination.wersja_id,
                "nazwa": frozen_combination.nazwa,
            }
        elif len(ids) > 1:
            combination = {
                "id": None,
                "wersja_id": None,
                "nazwa": " + ".join(item["nazwa"] for item in table_items),
            }

        result[reservation.id] = {
            "sala_id": room_id,
            "sala_nazwa": room_name,
            "stoliki": table_items,
            "kombinacja": combination,
            "proweniencja": "frozen" if frozen else ("legacy" if ids else "brak"),
        }
    return result


def moved_during_visit_ids(
    db: Session,
    reservations: Iterable[models.Termin],
) -> set[int]:
    rows = {
        row.id: row
        for row in reservations
        if row.id is not None
        and actual_turn_measurement(row)["pomiar"] == "complete"
    }
    if not rows:
        return set()
    audits = db.query(models.ReservationAudit).filter(
        models.ReservationAudit.termin_id.in_(tuple(rows)),
        models.ReservationAudit.action.in_(("assign", "edit")),
    ).all()
    moved = set()
    for audit in audits:
        reservation = rows.get(audit.termin_id)
        if reservation is None or audit.created_at is None:
            continue
        if not (reservation.host_seated_at < audit.created_at < reservation.host_left_at):
            continue
        changes = (audit.diff or {}).get("changes") or {}
        if _TABLE_CHANGE_FIELDS & set(changes):
            moved.add(reservation.id)
    return moved
