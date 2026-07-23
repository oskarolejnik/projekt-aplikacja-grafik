from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import main
import models
import reservation_recommendations as recommendations
import reservation_rules


HISTORY_START = date(2026, 1, 5)  # Monday
HISTORY_END = date(2026, 2, 2)
SIMULATION_TODAY = date(2026, 3, 1)


def _service(db, *, thresholds=None):
    row = models.GodzinyOtwarcia(
        dzien_tygodnia=0,
        godz_od=time(12, 0),
        godz_do=time(16, 0),
        ostatni_zasiadek=time(16, 0),
        dlugosc_slotu_min=120,
        krok_slotu_min=120,
        domyslny_turn_time_min=120,
        aktywny=True,
        nazwa="Lunch",
        turn_time_progi=thresholds,
    )
    db.add(row)
    db.flush()
    return row


def _history(
    db,
    *,
    people=2,
    complete=20,
    missing=5,
    actual_minutes=160,
):
    service_days = [
        HISTORY_START + timedelta(days=offset)
        for offset in (0, 7, 14, 21, 28)
    ]
    for index in range(complete + missing):
        booking_date = service_days[index % len(service_days)]
        seated = datetime.combine(booking_date, time(12, 0))
        row = models.Termin(
            data=booking_date,
            nazwisko=f"PII-{index}",
            liczba_osob=people,
            status="odbyla",
            rodzaj="stolik",
            kanal="reczna",
            godz_od=time(12, 0),
            host_seated_at=seated if index < complete else None,
            host_left_at=(
                seated + timedelta(minutes=actual_minutes)
                if index < complete else None
            ),
        )
        db.add(row)
    db.flush()


def _candidate(db):
    result = recommendations.list_recommendations(
        db,
        HISTORY_START,
        HISTORY_END,
    )
    assert len(result["rekomendacje"]) == 1
    return result["rekomendacje"][0]


def _fake_allocator(db, *, data, godz_od, osoby, **_kwargs):
    service = reservation_rules.serwis_dla_godziny(db, data, godz_od)
    minutes = reservation_rules.turn_time(service, osoby)
    return SimpleNamespace(
        decision="allow" if minutes <= 120 else "deny",
        selected=object() if minutes <= 120 else None,
        available=minutes <= 120,
    )


def _simulate(db, monkeypatch, user):
    candidate = _candidate(db)
    monkeypatch.setattr(recommendations, "_today_warsaw", lambda: SIMULATION_TODAY)
    monkeypatch.setattr(main, "_ocen_przydzial_rezerwacji", _fake_allocator)
    result = recommendations.simulate(
        db,
        candidate["hash"],
        HISTORY_START,
        HISTORY_END,
        user,
    )
    return candidate, result


def _decision_payload(simulation, decision, reason):
    return {
        "start": HISTORY_START,
        "end": HISTORY_END,
        "simulation_hash": simulation["simulation_hash"],
        "decyzja": decision,
        "powod": reason,
    }


def test_evidence_gates_segments_percentile_and_allowed_threshold_shape(db):
    service = _service(db)
    _history(db, complete=20, missing=5, actual_minutes=160)
    # A second segment stays below the sample gate.
    _history(db, people=4, complete=19, missing=0, actual_minutes=180)

    result = recommendations.list_recommendations(
        db,
        HISTORY_START,
        HISTORY_END,
    )

    assert result["progi"] == {
        "minimalna_proba": 20,
        "minimalna_kompletnosc_proc": 70,
        "minimalne_dni_serwisu": 4,
        "minimalna_roznica_min": 15,
        "percentyl": 75,
        "zaokraglenie_min": 15,
    }
    assert len(result["rekomendacje"]) == 1
    candidate = result["rekomendacje"][0]
    assert candidate["serwis"] == {"id": service.id, "nazwa": "Lunch"}
    assert candidate["segment"] == "1-2"
    assert candidate["proba"] == 20
    assert candidate["zakonczone_wizyty"] == 25
    assert candidate["kompletnosc_proc"] == 80
    assert candidate["dni_serwisu"] == 5
    assert candidate["p75_min"] == 160
    assert candidate["obecnie_min"] == 120
    assert candidate["proponowane_min"] == 165
    assert len(candidate["hash"]) == 64
    assert "PII-" not in str(result)

    service.turn_time_progi = [
        {"do_osob": 2, "min": 120},
        {"do_osob": 6, "min": 120},
        {"do_osob": 999, "min": 120},
    ]
    db.flush()
    assert recommendations.list_recommendations(
        db,
        HISTORY_START,
        HISTORY_END,
    )["rekomendacje"] == []


def test_simulation_uses_shared_allocator_and_never_persists_settings(
    db,
    admin,
    monkeypatch,
):
    service = _service(db)
    _history(db)
    candidate, result = _simulate(db, monkeypatch, admin)

    assert result["recommendation_hash"] == candidate["hash"]
    assert len(result["simulation_hash"]) == 64
    assert result["summary"] == {
        "sprawdzone_sloty": 12,
        "dostepne_przed": 12,
        "dostepne_po": 0,
        "roznica": -12,
        "decyzje_przed": {"allow": 12},
        "decyzje_po": {"deny": 12},
        "opis": (
            "Snapshot kolejnych 28 dni; istniejące rezerwacje i ustawienia "
            "nie zostały zmienione."
        ),
    }
    assert service.turn_time_progi is None
    db.expire(service, ["turn_time_progi"])
    assert service.turn_time_progi is None
    review = db.query(models.ReservationRecommendationReview).one()
    assert review.status == "simulated"
    assert review.simulated_by_user_id == admin.id
    assert "PII-" not in str(review.recommendation)
    assert "PII-" not in str(review.simulation)

    # The same recommendation is a durable replay, not a second calculation.
    monkeypatch.setattr(
        main,
        "_ocen_przydzial_rezerwacji",
        lambda *_args, **_kwargs: pytest.fail("replay reran the allocator"),
    )
    replay = recommendations.simulate(
        db,
        candidate["hash"],
        HISTORY_START,
        HISTORY_END,
        admin,
    )
    assert replay["replay"] is True
    assert replay["simulation_hash"] == result["simulation_hash"]


def test_accept_is_atomic_audited_and_idempotent(db, admin, monkeypatch):
    service = _service(db)
    _history(db)
    candidate, simulation = _simulate(db, monkeypatch, admin)
    payload = _decision_payload(
        simulation,
        "accepted",
        "confirmed_after_simulation",
    )

    result = recommendations.decide(
        db,
        candidate["hash"],
        payload,
        "r74-accept-one-window",
        admin,
    )

    assert result["decyzja"] == "accepted"
    assert result["replay"] is False
    assert service.turn_time_progi == [
        {"do_osob": 2, "min": 165},
        {"do_osob": 4, "min": 120},
        {"do_osob": 999, "min": 120},
    ]
    review = db.query(models.ReservationRecommendationReview).one()
    assert review.status == "accepted"
    assert review.decision_reason == "confirmed_after_simulation"
    audits = db.query(models.AuditLog).all()
    assert len(audits) == 1
    assert audits[0].akcja == "reservation_recommendation_decision"
    assert "PII-" not in (audits[0].szczegoly or "")
    assert "r74-accept-one-window" not in (audits[0].szczegoly or "")

    replay = recommendations.decide(
        db,
        candidate["hash"],
        payload,
        "r74-accept-one-window",
        admin,
    )
    assert replay["replay"] is True
    assert db.query(models.AuditLog).count() == 1

    changed_payload = {
        **payload,
        "decyzja": "rejected",
        "powod": "keep_current_policy",
    }
    with pytest.raises(HTTPException) as conflict:
        recommendations.decide(
            db,
            candidate["hash"],
            changed_payload,
            "r74-accept-one-window",
            admin,
        )
    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_reject_keeps_configuration(
    db,
    admin,
    monkeypatch,
):
    service = _service(db)
    _history(db)
    candidate, simulation = _simulate(db, monkeypatch, admin)
    payload = _decision_payload(
        simulation,
        "rejected",
        "operational_decision",
    )

    rejected = recommendations.decide(
        db,
        candidate["hash"],
        payload,
        "r74-reject-current-policy",
        admin,
    )
    assert rejected["decyzja"] == "rejected"
    assert service.turn_time_progi is None
    assert db.query(models.ReservationRecommendationReview).one().status == "rejected"


def test_stale_evidence_fails_closed(db, admin, monkeypatch):
    service = _service(db)
    _history(db)
    candidate, simulation = _simulate(db, monkeypatch, admin)
    service.domyslny_turn_time_min = 165
    db.flush()

    with pytest.raises(HTTPException) as stale:
        recommendations.decide(
            db,
            candidate["hash"],
            _decision_payload(
                simulation,
                "accepted",
                "confirmed_after_simulation",
            ),
            "r74-stale-after-change",
            admin,
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "RECOMMENDATION_STALE"
    assert (
        db.query(models.ReservationRecommendationReview).one().status
        == "simulated"
    )
