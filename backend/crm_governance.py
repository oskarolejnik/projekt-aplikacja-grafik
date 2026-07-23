"""R7.3 CRM governance: reversible identity links and versioned consent facts.

This module never exposes identity hashes through HTTP and never merges profile
rows destructively.  Candidate detection uses exact contact evidence only;
every merge remains an explicit operator decision.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timezone
import hashlib
from itertools import combinations
import json
from typing import Iterable

from fastapi import HTTPException

import models
from crm_identity import identity_hash, identity_parts
from sms import _normalizuj_numer


MAX_DUPLICATE_CANDIDATES = 100


def lock_governance_graph(db):
    """Serialize CRM identity/consent mutations on the venue singleton.

    PostgreSQL row locks make graph validation and writes one global critical
    section. SQLite ignores ``FOR UPDATE`` but still serializes writers; keeping
    the same call in tests preserves the production lock order.
    """
    config = (
        db.query(models.LokalConfig)
        .filter(models.LokalConfig.id == 1)
        .with_for_update()
        .one_or_none()
    )
    if config is None:
        raise HTTPException(
            503,
            "Brak konfiguracji lokalu wymaganej do bezpiecznej operacji CRM.",
        )
    return config


def idempotency_hash(raw: str | None) -> str:
    value = (raw or "").strip()
    if len(value) < 8 or len(value) > 128:
        raise HTTPException(
            400,
            "Idempotency-Key musi mieć od 8 do 128 znaków.",
        )
    if any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise HTTPException(400, "Niepoprawny nagłówek Idempotency-Key.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalised_event_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="microseconds")


def consent_request_fingerprint(
    *,
    reservation_id: int,
    decision: str,
    source: str,
    document_version: str,
    captured_at: datetime | None,
) -> str:
    """Hash the complete semantic consent command, including omitted time."""
    payload = {
        "reservation_id": int(reservation_id),
        "decision": decision,
        "source": source,
        "document_version": document_version.strip(),
        "captured_at_supplied": captured_at is not None,
        "captured_at": _normalised_event_time(captured_at),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def active_merges(db) -> list[models.CrmGuestMerge]:
    return (
        db.query(models.CrmGuestMerge)
        .filter(models.CrmGuestMerge.status == "active")
        .order_by(models.CrmGuestMerge.id)
        .all()
    )


def alias_map(db) -> dict[str, str]:
    return {row.source_hash: row.target_hash for row in active_merges(db)}


def canonical_hash(value: str, aliases: dict[str, str]) -> str:
    """Resolve a defensive, bounded alias chain.

    Mutation code rejects chains, but a bounded resolver keeps reads safe when
    inspecting an adopted or manually repaired database.
    """
    current = value
    seen = set()
    for _ in range(32):
        target = aliases.get(current)
        if not target:
            return current
        if current in seen or target in seen:
            return value
        seen.add(current)
        current = target
    return value


def group_reservations(
    reservations: Iterable[models.Termin],
    aliases: dict[str, str],
) -> dict[str, list[models.Termin]]:
    grouped: dict[str, list[models.Termin]] = defaultdict(list)
    for reservation in reservations:
        raw_hash = identity_hash(reservation)
        if raw_hash:
            grouped[canonical_hash(raw_hash, aliases)].append(reservation)
    return grouped


def member_hashes(
    reservations: Iterable[models.Termin],
) -> set[str]:
    return {identity_hash(row) for row in reservations if identity_hash(row)}


def profiles_for_group(db, reservations: Iterable[models.Termin]):
    hashes = member_hashes(reservations)
    if not hashes:
        return []
    return (
        db.query(models.ProfilGoscia)
        .filter(models.ProfilGoscia.klucz_hash.in_(hashes))
        .order_by(models.ProfilGoscia.id)
        .all()
    )


def composite_profile(profiles, *, preferred_hash: str | None = None):
    """Return a read-only composite without mutating any source profile."""
    profiles = list(profiles)
    if not profiles:
        return None
    profiles.sort(
        key=lambda row: (
            0 if preferred_hash and row.klucz_hash == preferred_hash else 1,
            row.id,
        )
    )
    primary = profiles[0]

    def first(field):
        for profile in profiles:
            value = getattr(profile, field, None)
            if value not in (None, "", []):
                return value
        return None

    def joined(field, separator="\n---\n"):
        values = []
        seen = set()
        for profile in profiles:
            raw = getattr(profile, field, None)
            for part in str(raw or "").split(separator):
                value = part.strip()
                key = value.casefold()
                if value and key not in seen:
                    seen.add(key)
                    values.append(value)
        return separator.join(values) or None

    tags = []
    for profile in profiles:
        for tag in profile.tagi or []:
            if tag not in tags:
                tags.append(tag)

    # A plain legacy boolean is intentionally not promoted to legal proof.
    return {
        "nazwisko": first("nazwisko"),
        "tagi": tags,
        "vip": any(bool(profile.vip) for profile in profiles),
        "alergie": joined("alergie"),
        "dieta": joined("dieta"),
        "preferowana_strefa": first("preferowana_strefa"),
        "notatka": joined("notatka"),
        "okazja_typ": first("okazja_typ"),
        "okazja_data": first("okazja_data"),
        "marketing_zgoda": False,
        "legacy_marketing_unverified": any(
            bool(profile.marketing_zgoda) for profile in profiles
        ),
        "_primary": primary,
    }


def _normalised_contacts(reservations: Iterable[models.Termin]) -> dict[str, set[str]]:
    phones: set[str] = set()
    emails: set[str] = set()
    for row in reservations:
        phone = _normalizuj_numer(row.telefon or "")
        email = (row.email or "").strip().casefold()
        if phone:
            phones.add(phone)
        if email:
            emails.add(email)
    return {"phones": phones, "emails": emails}


def exact_evidence(
    source: Iterable[models.Termin],
    target: Iterable[models.Termin],
) -> list[str]:
    left = _normalised_contacts(source)
    right = _normalised_contacts(target)
    evidence = []
    if left["phones"] & right["phones"]:
        evidence.append("exact_phone")
    if left["emails"] & right["emails"]:
        evidence.append("exact_email")
    return evidence


def _safe_group_summary(reservations: list[models.Termin]) -> dict:
    ordered = sorted(
        reservations,
        key=lambda row: (row.data, row.godz_od or time.min, row.id or 0),
        reverse=True,
    )
    latest = ordered[0]
    return {
        "profil_ref": latest.id,
        "nazwisko": latest.nazwisko,
        "telefon": latest.telefon,
        "email": latest.email,
        "wizyt": len(ordered),
        "ostatnia_data": str(latest.data),
        "identity": identity_parts(latest)[1],
    }


def duplicate_candidates(
    grouped: dict[str, list[models.Termin]],
) -> list[dict]:
    phone_index: dict[str, set[str]] = defaultdict(set)
    email_index: dict[str, set[str]] = defaultdict(set)
    for group_hash, reservations in grouped.items():
        contacts = _normalised_contacts(reservations)
        for value in contacts["phones"]:
            phone_index[value].add(group_hash)
        for value in contacts["emails"]:
            email_index[value].add(group_hash)

    pair_reasons: dict[tuple[str, str], set[str]] = defaultdict(set)
    for reason, index in (
        ("exact_phone", phone_index),
        ("exact_email", email_index),
    ):
        for hashes in index.values():
            for left, right in combinations(sorted(hashes), 2):
                pair_reasons[(left, right)].add(reason)
                if len(pair_reasons) >= MAX_DUPLICATE_CANDIDATES * 2:
                    break

    result = []
    for (left, right), reasons in sorted(pair_reasons.items()):
        left_rows, right_rows = grouped[left], grouped[right]
        left_score = (len(left_rows), max(row.data for row in left_rows))
        right_score = (len(right_rows), max(row.data for row in right_rows))
        target_hash, source_hash = (
            (left, right) if left_score >= right_score else (right, left)
        )
        result.append({
            "source_hash": source_hash,
            "target_hash": target_hash,
            "source_ref": _safe_group_summary(grouped[source_hash])["profil_ref"],
            "target_ref": _safe_group_summary(grouped[target_hash])["profil_ref"],
            "powod": sorted(reasons),
            "source": _safe_group_summary(grouped[source_hash]),
            "target": _safe_group_summary(grouped[target_hash]),
        })
        if len(result) >= MAX_DUPLICATE_CANDIDATES:
            break
    return result


def _all_reservation_groups(db):
    rows = (
        db.query(models.Termin)
        .filter(models.Termin.rodzaj.in_(("stolik", "sala")))
        .all()
    )
    aliases = alias_map(db)
    return rows, aliases, group_reservations(rows, aliases)


def group_for_ref(db, reservation_id: int):
    anchor = db.get(models.Termin, reservation_id)
    if anchor is None or anchor.rodzaj not in {"stolik", "sala"}:
        raise HTTPException(404, "Brak profilu gościa.")
    rows, aliases, grouped = _all_reservation_groups(db)
    raw_hash = identity_hash(anchor)
    key = canonical_hash(raw_hash, aliases)
    reservations = grouped.get(key) or []
    if not reservations:
        raise HTTPException(404, "Brak profilu gościa.")
    return {
        "anchor": anchor,
        "raw_hash": raw_hash,
        "canonical_hash": key,
        "reservations": reservations,
        "all_rows": rows,
        "aliases": aliases,
        "grouped": grouped,
    }


def merge_preview(db, source_ref: int, target_ref: int) -> dict:
    source = group_for_ref(db, source_ref)
    target = group_for_ref(db, target_ref)
    if source["canonical_hash"] == target["canonical_hash"]:
        raise HTTPException(409, "Te wpisy są już połączone.")
    evidence = exact_evidence(source["reservations"], target["reservations"])
    if not evidence:
        raise HTTPException(
            409,
            "Brak dokładnego wspólnego telefonu lub e-maila. "
            "System nie pozwoli połączyć tych osób.",
        )
    source_summary = _safe_group_summary(source["reservations"])
    target_summary = _safe_group_summary(target["reservations"])
    conflicts = []
    for field in ("nazwisko", "telefon", "email"):
        left = source_summary.get(field)
        right = target_summary.get(field)
        if (left or right) and left != right:
            conflicts.append({
                "field": field,
                "label": {
                    "nazwisko": "Nazwisko",
                    "telefon": "Telefon",
                    "email": "E-mail",
                }[field],
                "source": left or "Brak danych",
                "target": right or "Brak danych",
            })
    return {
        "source_ref": source_ref,
        "target_ref": target_ref,
        "source": source_summary,
        "target": target_summary,
        "evidence": evidence,
        "conflicts": conflicts,
        "expected_version": 0,
        "warnings": [
            "Wspólny kontakt może należeć do rodziny albo firmy. Potwierdź, że to ta sama osoba.",
            "Zgody marketingowe pozostaną przypisane do pierwotnych tożsamości.",
        ],
        "warning": (
            "Połączenie grupuje historię w CRM, ale nie przenosi zgód "
            "marketingowych i nie usuwa żadnego profilu."
        ),
    }


def create_merge(
    db,
    *,
    source_ref: int,
    target_ref: int,
    expected_version: int,
    raw_idempotency_key: str,
    user,
) -> tuple[models.CrmGuestMerge, bool]:
    key_hash = idempotency_hash(raw_idempotency_key)
    lock_governance_graph(db)
    replay = (
        db.query(models.CrmGuestMerge)
        .filter(models.CrmGuestMerge.create_key_hash == key_hash)
        .first()
    )
    if replay is not None:
        if (
            replay.source_reservation_id == source_ref
            and replay.target_reservation_id == target_ref
            and expected_version == 0
        ):
            return replay, True
        raise HTTPException(
            409,
            "Ten Idempotency-Key został użyty dla innego scalenia.",
        )
    if expected_version != 0:
        raise HTTPException(409, "Nieaktualna wersja scalenia.")
    preview = merge_preview(db, source_ref, target_ref)
    source = group_for_ref(db, source_ref)
    target = group_for_ref(db, target_ref)
    active = active_merges(db)
    if any(
        row.source_hash == source["canonical_hash"]
        or row.target_hash == source["canonical_hash"]
        for row in active
    ):
        raise HTTPException(
            409,
            "Źródłowy profil uczestniczy już w aktywnym scaleniu.",
        )
    if any(row.source_hash == target["canonical_hash"] for row in active):
        raise HTTPException(
            409,
            "Profil docelowy jest źródłem innego scalenia. Cofnij je najpierw.",
        )
    now = datetime.utcnow()
    row = models.CrmGuestMerge(
        source_hash=source["canonical_hash"],
        target_hash=target["canonical_hash"],
        source_reservation_id=source_ref,
        target_reservation_id=target_ref,
        evidence={"types": preview["evidence"]},
        reason_code="duplicate_confirmed",
        status="active",
        version=1,
        create_key_hash=key_hash,
        created_by_user_id=getattr(user, "id", None),
        created_by_login=getattr(user, "login", None),
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row, False


def converge_create_merge(
    db,
    *,
    source_ref: int,
    target_ref: int,
    expected_version: int,
    raw_idempotency_key: str,
) -> models.CrmGuestMerge | None:
    """Resolve a unique-key race to the already committed identical command."""
    key_hash = idempotency_hash(raw_idempotency_key)
    lock_governance_graph(db)
    row = (
        db.query(models.CrmGuestMerge)
        .filter(models.CrmGuestMerge.create_key_hash == key_hash)
        .first()
    )
    if row is None:
        return None
    if (
        row.source_reservation_id == source_ref
        and row.target_reservation_id == target_ref
        and expected_version == 0
    ):
        return row
    raise HTTPException(
        409,
        "Ten Idempotency-Key został użyty dla innego scalenia.",
    )


def undo_merge(
    db,
    *,
    merge_id: int,
    expected_version: int,
    raw_idempotency_key: str,
    user,
) -> tuple[models.CrmGuestMerge, bool]:
    key_hash = idempotency_hash(raw_idempotency_key)
    lock_governance_graph(db)
    replay = (
        db.query(models.CrmGuestMerge)
        .filter(models.CrmGuestMerge.revert_key_hash == key_hash)
        .first()
    )
    if replay is not None:
        if replay.id == merge_id and replay.version == expected_version + 1:
            return replay, True
        raise HTTPException(
            409,
            "Ten Idempotency-Key został użyty dla innego cofnięcia.",
        )
    row = (
        db.query(models.CrmGuestMerge)
        .filter(models.CrmGuestMerge.id == merge_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Brak scalenia.")
    if row.status != "active":
        raise HTTPException(409, "Scalenie zostało już cofnięte.")
    if row.version != expected_version:
        raise HTTPException(409, "Nieaktualna wersja scalenia.")
    row.status = "reverted"
    row.version += 1
    row.revert_key_hash = key_hash
    row.reverted_by_user_id = getattr(user, "id", None)
    row.reverted_by_login = getattr(user, "login", None)
    row.reverted_at = datetime.utcnow()
    db.flush()
    return row, False


def converge_undo_merge(
    db,
    *,
    merge_id: int,
    expected_version: int,
    raw_idempotency_key: str,
) -> models.CrmGuestMerge | None:
    key_hash = idempotency_hash(raw_idempotency_key)
    lock_governance_graph(db)
    row = (
        db.query(models.CrmGuestMerge)
        .filter(models.CrmGuestMerge.revert_key_hash == key_hash)
        .first()
    )
    if row is None:
        return None
    if row.id == merge_id and row.version == expected_version + 1:
        return row
    raise HTTPException(
        409,
        "Ten Idempotency-Key został użyty dla innego cofnięcia.",
    )


def revert_orphaned_identity_merges_after_contact_change(
    db,
    *,
    reservation_id: int,
    previous_identity_key: str,
    actor,
) -> list[int]:
    """Revert direct edges only after the previous identity loses its last row.

    Call this after assigning the new phone/e-mail to ``Termin`` and before the
    surrounding transaction commits. The helper never rewrites or traverses the
    counterpart identity.
    """
    previous_key = (previous_identity_key or "").strip()
    if not previous_key:
        return []
    reservation = db.get(models.Termin, reservation_id)
    if reservation is None or reservation.rodzaj not in {"stolik", "sala"}:
        return []
    previous_hash = hashlib.sha256(previous_key.encode("utf-8")).hexdigest()
    if identity_hash(reservation) == previous_hash:
        return []

    lock_governance_graph(db)
    other_rows = (
        db.query(models.Termin)
        .filter(
            models.Termin.rodzaj.in_(("stolik", "sala")),
            models.Termin.id != reservation_id,
        )
        .all()
    )
    if any(identity_hash(row) == previous_hash for row in other_rows):
        return []

    rows = (
        db.query(models.CrmGuestMerge)
        .filter(
            models.CrmGuestMerge.status == "active",
            (
                (models.CrmGuestMerge.source_hash == previous_hash)
                | (models.CrmGuestMerge.target_hash == previous_hash)
            ),
        )
        .order_by(models.CrmGuestMerge.id)
        .with_for_update()
        .all()
    )
    now = datetime.utcnow()
    reverted_ids = []
    for row in rows:
        row.status = "reverted"
        row.version += 1
        row.reverted_by_user_id = getattr(actor, "id", None)
        row.reverted_by_login = getattr(actor, "login", None)
        row.reverted_at = now
        reverted_ids.append(row.id)
        db.add(models.AuditLog(
            ts=now,
            user_id=getattr(actor, "id", None),
            login=getattr(actor, "login", None),
            akcja="crm_guest_merge_contact_change_revert",
            zasob=f"merge:{row.id}",
            szczegoly=json.dumps(
                {
                    "merge_id": row.id,
                    "reservation_id": reservation_id,
                    "version": row.version,
                    "reason_code": "identity_orphaned_after_contact_change",
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ))
    if rows:
        db.flush()
    return reverted_ids


def _consent_facts(db, reservations, hashes: set[str]) -> list[dict]:
    reservation_by_id = {row.id: row for row in reservations if row.id is not None}
    termin_ids = tuple(reservation_by_id)
    facts = []
    if termin_ids:
        public_rows = (
            db.query(models.RezerwacjaZgodaPubliczna)
            .filter(models.RezerwacjaZgodaPubliczna.termin_id.in_(termin_ids))
            .order_by(
                models.RezerwacjaZgodaPubliczna.marketing_at,
                models.RezerwacjaZgodaPubliczna.id,
            )
            .all()
        )
        for row in public_rows:
            reservation = reservation_by_id.get(row.termin_id)
            if reservation is None:
                continue
            frozen_subject_hash = getattr(row, "subject_hash", None)
            if (
                not isinstance(frozen_subject_hash, str)
                or len(frozen_subject_hash) != 64
            ):
                frozen_subject_hash = None
            facts.append({
                # Never rebind an old grant to a mutable reservation contact.
                # Legacy rows without a frozen subject remain visible history
                # but cannot become an active consent fact.
                "identity_hash": frozen_subject_hash,
                "decision": "grant" if row.marketing else "decline",
                "document_version": row.marketing_version,
                "source": "public_widget",
                "captured_at": row.marketing_at,
                "reservation_ref": row.termin_id,
            })
    if hashes:
        manual_rows = (
            db.query(models.CrmConsentEvent)
            .filter(models.CrmConsentEvent.subject_hash.in_(hashes))
            .order_by(models.CrmConsentEvent.captured_at, models.CrmConsentEvent.id)
            .all()
        )
        for row in manual_rows:
            facts.append({
                "identity_hash": row.subject_hash,
                "decision": row.decision,
                "document_version": row.document_version,
                "source": row.source,
                "captured_at": row.captured_at,
                "reservation_ref": row.termin_id,
            })
    return sorted(
        facts,
        key=lambda item: (
            item["captured_at"] or datetime.min,
            item["source"],
        ),
    )


def consent_summary(db, reservations, profiles=()) -> dict:
    reservations = list(reservations)
    hashes = member_hashes(reservations)
    facts = _consent_facts(db, reservations, hashes)
    per_identity = {}
    for subject_hash in hashes:
        subject_facts = [
            item for item in facts if item["identity_hash"] == subject_hash
        ]
        explicit = [
            item for item in subject_facts
            if item["decision"] in {"grant", "withdraw"}
        ]
        latest = explicit[-1] if explicit else None
        if latest and latest["decision"] == "grant":
            state = "granted"
        elif latest and latest["decision"] == "withdraw":
            state = "withdrawn"
        elif any(item["decision"] == "decline" for item in subject_facts):
            state = "declined"
        else:
            state = "missing"
        per_identity[subject_hash] = state

    states = set(per_identity.values())
    if hashes and states == {"granted"}:
        state = "granted"
        active = True
    elif "withdrawn" in states:
        state = "withdrawn" if len(states) == 1 else "mixed"
        active = False
    elif len(states) > 1:
        state = "mixed"
        active = False
    elif states:
        state = next(iter(states))
        active = False
    else:
        state = "missing"
        active = False

    legacy_unverified = any(bool(row.marketing_zgoda) for row in profiles)
    if state == "missing" and legacy_unverified:
        state = "legacy_unverified"
    public_history = []
    for item in reversed(facts):
        public_history.append({
            key: (
                value.isoformat()
                if key == "captured_at" and value is not None
                else value
            )
            for key, value in item.items()
            if key != "identity_hash"
        })
    return {
        "purpose": "marketing",
        "state": state,
        "active": active,
        "legacy_unverified": legacy_unverified,
        "history": public_history[:100],
        "history_total": len(public_history),
    }


def record_consent(
    db,
    *,
    reservation_id: int,
    decision: str,
    source: str,
    document_version: str,
    captured_at: datetime | None,
    raw_idempotency_key: str,
    user,
) -> tuple[models.CrmConsentEvent, bool]:
    key_hash = idempotency_hash(raw_idempotency_key)
    request_fingerprint = consent_request_fingerprint(
        reservation_id=reservation_id,
        decision=decision,
        source=source,
        document_version=document_version,
        captured_at=captured_at,
    )
    lock_governance_graph(db)
    replay = (
        db.query(models.CrmConsentEvent)
        .filter(models.CrmConsentEvent.event_key_hash == key_hash)
        .first()
    )
    if replay is not None:
        if replay.request_fingerprint == request_fingerprint:
            return replay, True
        raise HTTPException(
            409,
            "Ten Idempotency-Key został użyty dla innego zdarzenia zgody.",
        )
    reservation = db.get(models.Termin, reservation_id)
    if reservation is None or reservation.rodzaj not in {"stolik", "sala"}:
        raise HTTPException(404, "Brak rezerwacji.")
    now = datetime.utcnow()
    occurred = captured_at or now
    if occurred.tzinfo is not None:
        occurred = occurred.astimezone(timezone.utc).replace(tzinfo=None)
    if occurred > now:
        raise HTTPException(400, "Czas pozyskania zgody nie może być w przyszłości.")
    row = models.CrmConsentEvent(
        subject_hash=identity_hash(reservation),
        purpose="marketing",
        decision=decision,
        document_version=document_version.strip(),
        source=source,
        captured_at=occurred,
        termin_id=reservation.id,
        actor_user_id=getattr(user, "id", None),
        actor_login=getattr(user, "login", None),
        event_key_hash=key_hash,
        request_fingerprint=request_fingerprint,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row, False


def converge_consent_event(
    db,
    *,
    reservation_id: int,
    decision: str,
    source: str,
    document_version: str,
    captured_at: datetime | None,
    raw_idempotency_key: str,
) -> models.CrmConsentEvent | None:
    """Resolve a concurrent unique-key race without accepting key reuse."""
    key_hash = idempotency_hash(raw_idempotency_key)
    request_fingerprint = consent_request_fingerprint(
        reservation_id=reservation_id,
        decision=decision,
        source=source,
        document_version=document_version,
        captured_at=captured_at,
    )
    lock_governance_graph(db)
    row = (
        db.query(models.CrmConsentEvent)
        .filter(models.CrmConsentEvent.event_key_hash == key_hash)
        .first()
    )
    if row is None:
        return None
    if row.request_fingerprint == request_fingerprint:
        return row
    raise HTTPException(
        409,
        "Ten Idempotency-Key został użyty dla innego zdarzenia zgody.",
    )


def active_merge_out(db, row: models.CrmGuestMerge) -> dict:
    all_rows = (
        db.query(models.Termin)
        .filter(models.Termin.rodzaj.in_(("stolik", "sala")))
        .all()
    )

    def summary(subject_hash, reservation_id):
        rows = [item for item in all_rows if identity_hash(item) == subject_hash]
        if rows:
            return _safe_group_summary(rows)
        reservation = db.get(models.Termin, reservation_id) if reservation_id else None
        if reservation is not None:
            return _safe_group_summary([reservation])
        return {
            "profil_ref": None,
            "nazwisko": "Dane usunięte",
            "telefon": None,
            "email": None,
            "wizyt": 0,
            "ostatnia_data": None,
        }

    return {
        "id": row.id,
        "status": row.status,
        "version": row.version,
        "source": summary(row.source_hash, row.source_reservation_id),
        "target": summary(row.target_hash, row.target_reservation_id),
        "utworzono_at": row.created_at.isoformat(),
        "cofnieto_at": row.reverted_at.isoformat() if row.reverted_at else None,
        "reason_code": row.reason_code,
    }


def csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text
