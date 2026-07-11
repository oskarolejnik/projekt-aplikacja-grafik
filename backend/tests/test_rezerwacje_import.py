"""Regresje kontrolowanego cutoveru legacy rezerwacji do ``Termin``."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy.exc import IntegrityError

import models
import reconcile_rezerwacje as reconciliation_cli
import reservation_service
from rezerwacje_import import (
    WARSAW,
    ExternalReservation,
    InvalidExternalReservation,
    NormalizedExternalBatch,
    failed_source_batch,
    google_source_external_id,
    normalize_google_events,
    normalize_ical_payload,
    reconcile_reservations,
)


RANGE_START = datetime(2026, 6, 1, tzinfo=WARSAW)
RANGE_END = datetime(2026, 8, 1, tzinfo=WARSAW)
CUTOVER = date(2026, 7, 1)


def _external(
    external_id: str,
    day: date,
    *,
    hour: int = 18,
    party_size: int = 4,
    guest_name: str = "Gość Testowy",
    phone: str | None = None,
    email: str | None = None,
) -> ExternalReservation:
    start = datetime(day.year, day.month, day.day, hour, tzinfo=WARSAW)
    return ExternalReservation(
        source_type="google",
        source_external_id=external_id,
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        party_size=party_size,
        guest_name=guest_name,
        phone=phone,
        email=email,
    )


def _batch(*records: ExternalReservation) -> NormalizedExternalBatch:
    return NormalizedExternalBatch(
        source_type="google",
        records=tuple(records),
        received_count=len(records),
    )


def _reconcile(db, batch, *, apply=False):
    return reconcile_reservations(
        db,
        batch=batch,
        range_start=RANGE_START,
        range_end=RANGE_END,
        cutover_date=CUTOVER,
        coverage_through=RANGE_END,
        apply=apply,
        generated_at=datetime(2026, 6, 15, 10, tzinfo=WARSAW),
    )


def test_dry_run_nie_zapisuje_i_ma_jawny_zakres(db):
    report = _reconcile(db, _batch(_external("google-1", date(2026, 7, 10))))

    assert db.query(models.Termin).count() == 0
    assert db.query(models.RezerwacjaDzienLedger).count() == 0
    assert db.query(models.RezerwacjaPacingLedger).count() == 0
    assert db.query(models.RezerwacjaStolikClaim).count() == 0
    assert report["future"]["missing_in_termin"] == 1
    assert report["historical"]["missing_in_termin"] == 0
    assert report["range"]["end_exclusive"] is True
    assert report["coverage"]["includes_cutover_and_future"] is True
    assert report["cutover_date"] == "2026-07-01"
    assert report["source"] == {
        "type": "google",
        "status": "ok",
        "received": 1,
        "valid": 1,
        "invalid": 0,
    }
    assert report["apply"] == {"requested": False, "inserted": 0, "status": "ok"}
    assert report["safe_to_cutover"] is False
    assert len(report["issues"]) == 1
    issue = report["issues"][0]
    assert issue == {
        "ref": issue["ref"],
        "category": "missing_in_termin",
        "bucket": "future",
        "date": "2026-07-10",
        "time": "18:00",
        "party_size": 4,
        "termin_id": None,
        "changed_fields": [],
    }
    assert issue["ref"].startswith("res_")
    assert "google-1" not in json.dumps(report)


def test_apply_dwa_razy_tworzy_jeden_termin_i_zachowuje_kontakt(db):
    record = _external(
        "google-idempotent",
        date(2026, 7, 10),
        phone="+48 600 700 800",
        email="gosc@example.com",
    )

    first = _reconcile(db, _batch(record), apply=True)
    second = _reconcile(db, _batch(record), apply=True)

    assert first["apply"]["inserted"] == 1
    assert second["apply"]["inserted"] == 0
    assert second["future"]["matched"] == 1
    assert second["safe_to_cutover"] is True
    assert db.query(models.Termin).count() == 1
    termin = db.query(models.Termin).one()
    assert termin.rodzaj == "stolik"
    assert termin.status == "potwierdzona"
    assert termin.stolik_id is None
    assert termin.telefon == "+48 600 700 800"
    assert termin.email == "gosc@example.com"
    assert termin.utworzono_at == datetime(2026, 6, 15, 8)
    assert (termin.source_type, termin.source_external_id) == ("google", "google-idempotent")
    pacing = db.query(models.RezerwacjaPacingLedger).one()
    assert pacing.termin_id == termin.id
    assert pacing.data == termin.data
    assert pacing.start_minute == 18 * 60
    assert pacing.covers == 4
    assert pacing.override is True
    assert db.query(models.RezerwacjaStolikClaim).count() == 0  # import pozostaje bez stołu
    day = db.query(models.RezerwacjaDzienLedger).one()
    assert day.data == termin.data and day.revision == 1


def test_apply_blokuje_dni_deterministycznie_i_tworzy_ledger_dla_kazdego_importu(
    db, monkeypatch
):
    captured_dates = []
    original = reservation_service.begin_locked_write

    def capture(db_session, dates):
        captured_dates.append(tuple(dates))
        return original(db_session, dates)

    monkeypatch.setattr(reservation_service, "begin_locked_write", capture)
    records = _batch(
        _external("later", date(2026, 7, 11)),
        _external("earlier", date(2026, 7, 10)),
    )

    report = _reconcile(db, records, apply=True)

    assert report["apply"]["inserted"] == 2
    assert captured_dates == [(date(2026, 7, 10), date(2026, 7, 11))]
    assert db.query(models.Termin).count() == 2
    assert db.query(models.RezerwacjaPacingLedger).count() == 2
    assert db.query(models.RezerwacjaStolikClaim).count() == 0
    days = db.query(models.RezerwacjaDzienLedger).order_by(
        models.RezerwacjaDzienLedger.data
    ).all()
    assert [(day.data, day.revision) for day in days] == [
        (date(2026, 7, 10), 1),
        (date(2026, 7, 11), 1),
    ]


def test_apply_ponawia_blokady_gdy_przeniesienie_ujawnia_brak_na_inny_dzien(
    db, monkeypatch
):
    first_day = date(2026, 7, 10)
    newly_missing_day = date(2026, 7, 11)
    moved_to_day = date(2026, 7, 12)
    first_record = _external("initially-missing", first_day)
    moving_record = _external("becomes-missing", newly_missing_day)
    moving_start = moving_record.starts_at.astimezone(WARSAW)
    moving_end = moving_record.ends_at.astimezone(WARSAW)
    legacy = models.Termin(
        data=newly_missing_day,
        nazwisko=moving_record.guest_name,
        liczba_osob=moving_record.party_size,
        godz_od=moving_start.time().replace(tzinfo=None),
        godz_do=moving_end.time().replace(tzinfo=None),
        rodzaj="stolik",
        status="potwierdzona",
    )
    db.add(legacy)
    db.commit()

    captured_dates = []
    moved = False
    original = reservation_service.begin_locked_write

    def move_between_classifications(db_session, dates):
        nonlocal moved
        captured_dates.append(tuple(sorted(dates)))
        if not moved:
            db_session.get(models.Termin, legacy.id).data = moved_to_day
            db_session.commit()
            moved = True
        return original(db_session, dates)

    monkeypatch.setattr(
        reservation_service,
        "begin_locked_write",
        move_between_classifications,
    )

    report = _reconcile(
        db,
        _batch(first_record, moving_record),
        apply=True,
    )

    assert report["apply"]["inserted"] == 2
    assert captured_dates == [
        (first_day,),
        (first_day, newly_missing_day),
    ]
    assert db.get(models.Termin, legacy.id).data == moved_to_day
    imported = db.query(models.Termin).filter(
        models.Termin.source_type == "google"
    ).all()
    assert {(termin.source_external_id, termin.data) for termin in imported} == {
        ("initially-missing", first_day),
        ("becomes-missing", newly_missing_day),
    }
    days = db.query(models.RezerwacjaDzienLedger).order_by(
        models.RezerwacjaDzienLedger.data
    ).all()
    assert [(day.data, day.revision) for day in days] == [
        (first_day, 1),
        (newly_missing_day, 1),
    ]


def test_raport_rozdziela_historyczne_i_przyszle(db):
    report = _reconcile(
        db,
        _batch(
            _external("old", date(2026, 6, 10)),
            _external("future", date(2026, 7, 10)),
        ),
    )

    assert report["historical"]["missing_in_termin"] == 1
    assert report["future"]["missing_in_termin"] == 1


def test_fallback_wykrywa_mozliwy_duplikat_bez_automatycznego_importu(db):
    db.add(
        models.Termin(
            data=date(2026, 7, 10),
            nazwisko="Żaneta Łącka",
            liczba_osob=6,
            godz_od=datetime(2026, 7, 10, 18).time(),
            godz_do=datetime(2026, 7, 10, 20).time(),
            rodzaj="stolik",
            status="potwierdzona",
        )
    )
    db.commit()
    record = _external(
        "new-source-id",
        date(2026, 7, 10),
        party_size=6,
        guest_name="zaneta lacka",
    )

    report = _reconcile(db, _batch(record), apply=True)

    assert report["future"]["possible_duplicate"] == 1
    assert report["future"]["missing_in_termin"] == 0
    assert report["future"]["canonical_only"] == 1
    assert report["apply"]["inserted"] == 0
    assert db.query(models.Termin).count() == 1
    assert report["issues"][0]["termin_id"] is not None


def test_changed_nie_nadpisuje_a_source_missing_nie_usuwa(db):
    changed = models.Termin(
        data=date(2026, 7, 10),
        nazwisko="Gość Testowy",
        liczba_osob=99,
        godz_od=datetime(2026, 7, 10, 18).time(),
        godz_do=datetime(2026, 7, 10, 20).time(),
        rodzaj="stolik",
        status="potwierdzona",
        source_type="google",
        source_external_id="changed",
    )
    source_missing = models.Termin(
        data=date(2026, 7, 11),
        nazwisko="Inny Gość",
        liczba_osob=3,
        godz_od=datetime(2026, 7, 11, 18).time(),
        godz_do=datetime(2026, 7, 11, 20).time(),
        rodzaj="stolik",
        status="potwierdzona",
        source_type="google",
        source_external_id="not-returned-by-source",
    )
    db.add_all((changed, source_missing))
    db.commit()

    report = _reconcile(
        db,
        _batch(_external("changed", date(2026, 7, 10), party_size=4)),
        apply=True,
    )

    assert report["future"]["changed"] == 1
    assert report["future"]["source_missing"] == 1
    assert report["apply"]["inserted"] == 0
    assert db.get(models.Termin, changed.id).liczba_osob == 99
    assert db.get(models.Termin, source_missing.id) is not None
    changed_issue = next(item for item in report["issues"] if item["category"] == "changed")
    missing_issue = next(
        item for item in report["issues"] if item["category"] == "source_missing"
    )
    assert changed_issue["termin_id"] == changed.id
    assert changed_issue["changed_fields"] == ["liczba_osob"]
    assert missing_issue["termin_id"] == source_missing.id


def test_exact_identity_jest_globalne_i_konflikt_imprezy_nie_importuje(db):
    legacy_event = models.Termin(
        data=date(2025, 12, 31),
        nazwisko="Stara Impreza",
        liczba_osob=80,
        rodzaj="impreza",
        status="rezerwacja",
        source_type="ical",
        source_external_id="same-global-uid",
    )
    db.add(legacy_event)
    db.commit()
    starts_at = datetime(2026, 7, 12, 18, tzinfo=WARSAW)
    incoming = ExternalReservation(
        source_type="ical",
        source_external_id="same-global-uid",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        party_size=4,
        guest_name="Nowa Rezerwacja",
    )

    report = _reconcile(
        db,
        NormalizedExternalBatch(source_type="ical", records=(incoming,), received_count=1),
        apply=True,
    )

    assert report["future"]["changed"] == 1
    assert report["future"]["missing_in_termin"] == 0
    assert report["apply"]["inserted"] == 0
    assert db.query(models.Termin).count() == 1
    issue = report["issues"][0]
    assert issue["termin_id"] == legacy_event.id
    assert {"data", "rodzaj"}.issubset(issue["changed_fields"])


def test_exact_identity_wykrywa_wylacznie_zmieniony_telefon_i_email(db):
    termin = models.Termin(
        data=date(2026, 7, 10),
        nazwisko="Gość Testowy",
        liczba_osob=4,
        telefon="600 111 222",
        email="stary@example.com",
        godz_od=datetime(2026, 7, 10, 18).time(),
        godz_do=datetime(2026, 7, 10, 20).time(),
        rodzaj="stolik",
        status="potwierdzona",
        source_type="google",
        source_external_id="contact-change",
    )
    db.add(termin)
    db.commit()
    incoming = _external(
        "contact-change",
        date(2026, 7, 10),
        phone="+48 600 999 888",
        email="nowy@example.com",
    )

    report = _reconcile(db, _batch(incoming), apply=True)

    issue = report["issues"][0]
    assert issue["category"] == "changed"
    assert issue["changed_fields"] == ["telefon", "email"]
    assert report["apply"]["inserted"] == 0
    assert db.get(models.Termin, termin.id).telefon == "600 111 222"
    assert db.get(models.Termin, termin.id).email == "stary@example.com"


def test_znormalizowany_ten_sam_kontakt_nie_jest_zmiana(db):
    termin = models.Termin(
        data=date(2026, 7, 10),
        nazwisko="Gość Testowy",
        liczba_osob=4,
        telefon="600-700-800",
        email="GOSC@EXAMPLE.COM",
        godz_od=datetime(2026, 7, 10, 18).time(),
        godz_do=datetime(2026, 7, 10, 20).time(),
        rodzaj="stolik",
        status="potwierdzona",
        source_type="google",
        source_external_id="same-contact",
    )
    db.add(termin)
    db.commit()

    report = _reconcile(
        db,
        _batch(
            _external(
                "same-contact",
                date(2026, 7, 10),
                phone="+48 600 700 800",
                email="gosc@example.com",
            )
        ),
    )

    assert report["future"]["matched"] == 1
    assert report["issues"] == []
    assert report["safe_to_cutover"] is True


def test_google_normalizuje_namespace_kontakt_i_time_max_exclusive(db):
    description = (
        "REZERWACJA STOLIKA\nLiczba osób: 4\nTelefon: +48 600 700 800\n"
        "E-mail: sekret@example.com\nAlergia: brak\nUwagi: brak\nNotatka: -"
    )
    events = [
        {
            "id": "opaque-event",
            "status": "confirmed",
            "start": {"dateTime": "2026-07-10T18:00:00+02:00"},
            "end": {"dateTime": "2026-07-10T20:00:00+02:00"},
            "summary": "Rezerwacja stolika - Anna Tajna",
            "description": description,
        },
        {
            "id": "at-exclusive-end",
            "status": "confirmed",
            "start": {"dateTime": "2026-08-01T00:00:00+02:00"},
            "end": {"dateTime": "2026-08-01T02:00:00+02:00"},
            "summary": "Poza zakresem",
            "description": "Liczba osób: 2",
        },
        {
            "id": "manual-sensitive-review",
            "status": "confirmed",
            "start": {"dateTime": "2026-07-11T18:00:00+02:00"},
            "end": {"dateTime": "2026-07-11T20:00:00+02:00"},
            "summary": "Rezerwacja stolika - Inny Gość",
            "description": "Liczba osob: 3\nProsze o stolik przy oknie",
        },
    ]
    batch = normalize_google_events(
        events,
        calendar_id="calendar@example.com",
        range_start=RANGE_START,
        range_end=RANGE_END,
    )

    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.source_external_id == google_source_external_id(
        "calendar@example.com", "opaque-event"
    )
    assert record.phone == "+48 600 700 800"
    assert record.email == "sekret@example.com"
    report = _reconcile(db, batch)
    invalid_issue = next(
        item for item in report["issues"] if item["category"] == "invalid_external"
    )
    assert invalid_issue["invalid_reason"] == "unsupported_guest_notes"
    assert invalid_issue["party_size"] == 3
    serialized = json.dumps(report, ensure_ascii=False)
    for pii in (
        "Anna Tajna",
        "+48 600 700 800",
        "sekret@example.com",
        "Prosze o stolik przy oknie",
    ):
        assert pii not in serialized


def test_ical_identity_recurrence_i_invalidne_strefy_oraz_rrule(db):
    payload = "\r\n".join(
        (
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "UID:opaque-uid",
            "RECURRENCE-ID;TZID=Europe/Warsaw:20260710T180000",
            "DTSTART;TZID=Europe/Warsaw:20260710T180000",
            "DTEND;TZID=Europe/Warsaw:20260710T200000",
            "SUMMARY:Rezerwacja - Gość Prywatny",
            "DESCRIPTION:Liczba osób: 4\\nTelefon: 600 111 222\\nEmail: prywatny@example.com",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:recurring-historical",
            "DTSTART;TZID=Europe/Warsaw:20260610T180000",
            "DTEND;TZID=Europe/Warsaw:20260610T200000",
            "RRULE:FREQ=WEEKLY",
            "SUMMARY:Nie raportuj mnie",
            "DESCRIPTION:Liczba osób: 2",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:floating-future",
            "DTSTART:20260711T180000",
            "DTEND:20260711T200000",
            "SUMMARY:Też prywatne",
            "DESCRIPTION:Liczba osób: 2",
            "END:VEVENT",
            "END:VCALENDAR",
        )
    )
    batch = normalize_ical_payload(payload, range_start=RANGE_START, range_end=RANGE_END)

    assert len(batch.records) == 1
    assert batch.records[0].source_external_id == "opaque-uid#20260710T160000Z"
    assert batch.records[0].phone == "600 111 222"
    assert batch.records[0].email == "prywatny@example.com"
    report = _reconcile(db, batch)
    assert report["historical"]["invalid_external"] == 1
    assert report["future"]["invalid_external"] == 1
    serialized = json.dumps(report, ensure_ascii=False)
    for pii in ("Gość Prywatny", "600 111 222", "prywatny@example.com", "Nie raportuj mnie"):
        assert pii not in serialized


def test_ical_wymaga_pelnej_koperty_a_pusty_kalendarz_jest_poprawny(db):
    for malformed in (
        "garbage",
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nEND:VCALENDAR",
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nEND:VEVENT",
    ):
        batch = normalize_ical_payload(
            malformed,
            range_start=RANGE_START,
            range_end=RANGE_END,
        )
        assert batch.source_status == "error"
        assert batch.source_error_code == "invalid_ical_structure"
        report = _reconcile(db, batch)
        assert report["safe_to_cutover"] is False
        assert report["future"]["invalid_external"] == 1
        assert report["issues"][0]["invalid_reason"] == "source_error"

    empty = normalize_ical_payload(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
        range_start=RANGE_START,
        range_end=RANGE_END,
    )
    report = _reconcile(db, empty)
    assert empty.source_status == "ok"
    assert report["issues"] == []
    assert report["safe_to_cutover"] is True


def test_ical_wolny_tekst_description_wymaga_recznego_rozstrzygniecia(db):
    payload = "\r\n".join(
        (
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "UID:free-text-uid",
            "DTSTART;TZID=Europe/Warsaw:20260710T180000",
            "DTEND;TZID=Europe/Warsaw:20260710T200000",
            "SUMMARY:Gość Prywatny",
            "DESCRIPTION:Liczba osob: 4\\nProsze o stolik przy oknie",
            "END:VEVENT",
            "END:VCALENDAR",
        )
    )
    batch = normalize_ical_payload(payload, range_start=RANGE_START, range_end=RANGE_END)

    report = _reconcile(db, batch, apply=True)

    assert batch.records == ()
    assert batch.invalid[0].code == "unsupported_guest_notes"
    assert report["safe_to_cutover"] is False
    assert report["future"]["invalid_external"] == 1
    assert "Prosze o stolik przy oknie" not in json.dumps(report, ensure_ascii=False)
    assert db.query(models.Termin).count() == 0


def test_google_tentative_nie_jest_importowane_jako_potwierdzone(db):
    batch = normalize_google_events(
        [
            {
                "id": "tentative",
                "status": "tentative",
                "start": {"dateTime": "2026-07-10T18:00:00+02:00"},
                "end": {"dateTime": "2026-07-10T20:00:00+02:00"},
                "summary": "Gość Prywatny",
                "description": "Liczba osób: 5",
            }
        ],
        calendar_id="calendar@example.com",
        range_start=RANGE_START,
        range_end=RANGE_END,
    )

    report = _reconcile(db, batch, apply=True)

    assert report["future"]["invalid_external"] == 1
    assert report["issues"][0]["party_size"] == 5
    assert report["issues"][0]["invalid_reason"] == "unconfirmed_status"
    assert report["apply"]["inserted"] == 0
    assert db.query(models.Termin).count() == 0


def test_google_odrzuca_rezerwacje_przecinajace_obie_zmiany_dst():
    events = [
        {
            "id": "spring-forward",
            "status": "confirmed",
            "start": {"dateTime": "2026-03-29T01:30:00+01:00"},
            "end": {"dateTime": "2026-03-29T03:30:00+02:00"},
            "summary": "Gość Wiosenny",
            "description": "Liczba osob: 2",
        },
        {
            "id": "fall-back",
            "status": "confirmed",
            "start": {"dateTime": "2026-10-25T01:30:00+02:00"},
            "end": {"dateTime": "2026-10-25T03:30:00+01:00"},
            "summary": "Gość Jesienny",
            "description": "Liczba osob: 3",
        },
        {
            "id": "fall-back-second-fold",
            "status": "confirmed",
            "start": {"dateTime": "2026-10-25T02:10:00+01:00"},
            "end": {"dateTime": "2026-10-25T02:50:00+01:00"},
            "summary": "Gość Drugiej Godziny",
            "description": "Liczba osob: 4",
        },
    ]

    batch = normalize_google_events(
        events,
        calendar_id="calendar@example.com",
        range_start=datetime(2026, 3, 1, tzinfo=WARSAW),
        range_end=datetime(2026, 11, 1, tzinfo=WARSAW),
    )

    assert batch.records == ()
    assert len(batch.invalid) == 3
    assert {item.code for item in batch.invalid} == {"unsupported_dst_transition"}
    assert {item.party_size for item in batch.invalid} == {2, 3, 4}


def test_cutover_wymaga_zakresu_obejmujacego_cutover_i_przyszlosc(db):
    report = reconcile_reservations(
        db,
        batch=NormalizedExternalBatch(source_type="google"),
        range_start=datetime(2026, 7, 2, tzinfo=WARSAW),
        range_end=datetime(2026, 8, 1, tzinfo=WARSAW),
        cutover_date=CUTOVER,
        coverage_through=datetime(2026, 8, 1, tzinfo=WARSAW),
    )

    assert report["historical"] == {category: 0 for category in report["historical"]}
    assert report["future"] == {category: 0 for category in report["future"]}
    assert report["coverage"]["includes_cutover_and_future"] is False
    assert report["safe_to_cutover"] is False


def test_cutover_wymaga_jawnego_horyzontu_i_pokrycia_calego_horyzontu(db):
    generated_at = datetime(2026, 7, 11, 10, tzinfo=WARSAW)
    one_minute_after_cutover = datetime(2026, 7, 1, 0, 1, tzinfo=WARSAW)
    without_horizon = reconcile_reservations(
        db,
        batch=NormalizedExternalBatch(source_type="google"),
        range_start=RANGE_START,
        range_end=RANGE_END,
        cutover_date=CUTOVER,
        generated_at=generated_at,
    )
    short_range = reconcile_reservations(
        db,
        batch=NormalizedExternalBatch(source_type="google"),
        range_start=datetime(2026, 7, 1, tzinfo=WARSAW),
        range_end=one_minute_after_cutover,
        cutover_date=CUTOVER,
        coverage_through=RANGE_END,
        generated_at=generated_at,
    )
    stale_horizon = reconcile_reservations(
        db,
        batch=NormalizedExternalBatch(source_type="google"),
        range_start=RANGE_START,
        range_end=RANGE_END,
        cutover_date=CUTOVER,
        coverage_through=generated_at,
        generated_at=generated_at,
    )
    before_future_cutover = reconcile_reservations(
        db,
        batch=NormalizedExternalBatch(source_type="google"),
        range_start=RANGE_START,
        range_end=RANGE_END,
        cutover_date=date(2026, 7, 20),
        coverage_through=datetime(2026, 7, 12, tzinfo=WARSAW),
        generated_at=generated_at,
    )

    assert without_horizon["coverage"]["through"] is None
    assert without_horizon["coverage"]["sufficient"] is False
    assert without_horizon["safe_to_cutover"] is False
    assert short_range["coverage"]["includes_cutover_and_future"] is True
    assert short_range["coverage"]["range_covers_through"] is False
    assert short_range["safe_to_cutover"] is False
    assert stale_horizon["coverage"]["through_is_after_generated_at"] is False
    assert stale_horizon["safe_to_cutover"] is False
    assert before_future_cutover["coverage"]["through_is_after_generated_at"] is True
    assert before_future_cutover["coverage"]["through_is_after_cutover"] is False
    assert before_future_cutover["safe_to_cutover"] is False


def test_source_error_zawsze_blokuje_cutover(db):
    report = _reconcile(db, failed_source_batch("google", RuntimeError("sekret w błędzie")))

    assert report["source"]["status"] == "error"
    assert report["source"]["error_code"] == "RuntimeError"
    assert "sekret w błędzie" not in json.dumps(report, ensure_ascii=False)
    assert report["safe_to_cutover"] is False


def test_unique_race_rollbackuje_caly_import_i_zwraca_bezpieczny_raport(db, monkeypatch):
    records = _batch(
        _external("race-1", date(2026, 7, 10)),
        _external("race-2", date(2026, 7, 11)),
    )

    def conflict():
        raise IntegrityError("unique conflict", {}, RuntimeError("database detail"))

    monkeypatch.setattr(db, "commit", conflict)
    report = _reconcile(db, records, apply=True)

    assert report["apply"] == {
        "requested": True,
        "inserted": 0,
        "status": "error",
        "error_code": "source_identity_conflict",
    }
    assert report["safe_to_cutover"] is False
    assert db.query(models.Termin).count() == 0
    assert db.query(models.RezerwacjaDzienLedger).count() == 0
    assert db.query(models.RezerwacjaPacingLedger).count() == 0
    assert db.query(models.RezerwacjaStolikClaim).count() == 0


def test_cli_apply_bez_encryption_key_konczy_sie_bledem_bez_bazy(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    report_path = tmp_path / "report.json"

    def forbidden_session():
        raise AssertionError("session must not be opened")

    exit_code = reconciliation_cli.run(
        (
            "--source", "ical",
            "--ics", str(tmp_path / "not-read.ics"),
            "--start", "2026-06-01",
            "--end", "2026-08-01",
            "--cutover-date", "2026-07-01",
            "--coverage-through", "2026-08-01",
            "--apply",
            "--report", str(report_path),
        ),
        session_factory=forbidden_session,
    )

    assert exit_code == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["apply"]["error_code"] == "encryption_key_required"
    assert report["safe_to_cutover"] is False


def test_cli_exit_nonzero_dla_bledu_apply(tmp_path, monkeypatch):
    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(
        reconciliation_cli,
        "_ical_batch",
        lambda *args: NormalizedExternalBatch(source_type="ical"),
    )
    monkeypatch.setattr(
        reconciliation_cli,
        "reconcile_reservations",
        lambda *args, **kwargs: {
            "source": {"status": "ok"},
            "apply": {"requested": True, "inserted": 0, "status": "error"},
            "safe_to_cutover": False,
        },
    )
    report_path = tmp_path / "apply-error.json"

    exit_code = reconciliation_cli.run(
        (
            "--source", "ical",
            "--ics", str(tmp_path / "unused.ics"),
            "--start", "2026-06-01",
            "--end", "2026-08-01",
            "--cutover-date", "2026-07-01",
            "--coverage-through", "2026-08-01",
            "--apply",
            "--report", str(report_path),
        ),
        session_factory=FakeSession,
    )

    assert exit_code == 2
    assert json.loads(report_path.read_text(encoding="utf-8"))["apply"]["status"] == "error"


def test_cli_nie_kopiuje_bledu_bazy_do_raportu(tmp_path, monkeypatch):
    class FakeSession:
        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(
        reconciliation_cli,
        "_ical_batch",
        lambda *args: NormalizedExternalBatch(source_type="ical"),
    )
    monkeypatch.setattr(
        reconciliation_cli,
        "reconcile_reservations",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("PII: Tajny Gość")),
    )
    report_path = tmp_path / "safe-db-error.json"

    exit_code = reconciliation_cli.run(
        (
            "--source", "ical",
            "--ics", str(tmp_path / "unused.ics"),
            "--start", "2026-06-01",
            "--end", "2026-08-01",
            "--cutover-date", "2026-07-01",
            "--coverage-through", "2026-08-01",
            "--report", str(report_path),
        ),
        session_factory=FakeSession,
    )

    serialized = report_path.read_text(encoding="utf-8")
    assert exit_code == 2
    assert "Tajny Gość" not in serialized
    assert json.loads(serialized)["apply"]["error_code"] == "reconciliation_failed"
