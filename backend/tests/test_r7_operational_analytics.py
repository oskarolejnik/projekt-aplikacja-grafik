"""R7.1: measured turn time, frozen allocations and PII-free analytics."""

from datetime import date, datetime, time

import factories
import models
import reservation_operational
import uprawnienia
from auth import create_access_token


DAY = date(2026, 7, 20)


def _published_floor(db):
    room = models.SalaRezerwacyjna(
        nazwa="Main room",
        nazwa_klucz="main room",
        aktywna=True,
        kolejnosc=0,
        priorytet=0,
        strategia_zapelniania="preferuj",
    )
    db.add(room)
    db.flush()
    plan = models.PlanSali(sala_id=room.id, nazwa="Main room plan")
    db.add(plan)
    db.flush()
    table_a = models.Stolik(
        nazwa="Current A",
        strefa=room.nazwa,
        sala_id=room.id,
        pojemnosc=4,
        aktywny=True,
        kolejnosc=0,
    )
    table_b = models.Stolik(
        nazwa="Current B",
        strefa=room.nazwa,
        sala_id=room.id,
        pojemnosc=4,
        aktywny=True,
        kolejnosc=1,
    )
    db.add_all((table_a, table_b))
    db.flush()
    now = datetime(2026, 7, 1, 12, 0)
    version = models.WersjaPlanuSali(
        plan_id=plan.id,
        numer=1,
        status="published",
        rewizja=0,
        utworzono_at=now,
        zaktualizowano_at=now,
        opublikowano_at=now,
    )
    db.add(version)
    db.flush()
    db.add_all((
        models.PozycjaStolikaPlanu(
            wersja_id=version.id,
            stolik_id=table_a.id,
            plan_x=10,
            plan_y=10,
            szerokosc=12,
            wysokosc=12,
            obrot=0,
            aktywny_w_planie=True,
            nazwa="Historic A",
            pojemnosc=4,
            pojemnosc_min=1,
            kolejnosc=0,
        ),
        models.PozycjaStolikaPlanu(
            wersja_id=version.id,
            stolik_id=table_b.id,
            plan_x=30,
            plan_y=10,
            szerokosc=12,
            wysokosc=12,
            obrot=0,
            aktywny_w_planie=True,
            nazwa="Historic B",
            pojemnosc=4,
            pojemnosc_min=1,
            kolejnosc=1,
        ),
    ))
    db.flush()
    combination = models.KombinacjaStolowPlanu(
        wersja_id=version.id,
        nazwa="Historic A + Historic B",
        sklad_klucz=f"{table_a.id},{table_b.id}",
        pojemnosc_min=5,
        pojemnosc_max=8,
        priorytet=0,
        kanal="oba",
        aktywna_w_planie=True,
    )
    db.add(combination)
    db.flush()
    db.add_all((
        models.SkladnikKombinacjiPlanu(
            kombinacja_id=combination.id,
            wersja_id=version.id,
            stolik_id=table_a.id,
        ),
        models.SkladnikKombinacjiPlanu(
            kombinacja_id=combination.id,
            wersja_id=version.id,
            stolik_id=table_b.id,
        ),
    ))
    db.commit()
    return room, table_a, table_b, version, combination


def _reservation(
    db,
    *,
    day=DAY,
    surname="Private Guest",
    phone="600100200",
    email="private@example.com",
    people=2,
    planned_start=time(18, 0),
    planned_end=time(19, 30),
    seated=None,
    left=None,
    table=None,
    extra_tables=None,
    version=None,
    combination=None,
):
    row = models.Termin(
        rodzaj="stolik",
        kanal="reczna",
        nazwisko=surname,
        telefon=phone,
        email=email,
        data=day,
        status="odbyla",
        liczba_osob=people,
        zadatek=0,
        utworzono_at=datetime(2026, 7, 1, 9, 0),
        godz_od=planned_start,
        godz_do=planned_end,
        host_seated_at=seated,
        host_left_at=left,
        stolik_id=table.id if table is not None else None,
        stoliki_dodatkowe=[item.id for item in (extra_tables or [])] or None,
        przydzial_wersja_planu_id=version.id if version is not None else None,
        przydzial_kombinacja_planu_id=(
            combination.id if combination is not None else None
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_crm_history_exposes_complete_missing_invalid_and_frozen_names(
    admin_client,
    db,
):
    room, table_a, table_b, version, combination = _published_floor(db)
    complete = _reservation(
        db,
        day=date(2026, 7, 20),
        people=6,
        planned_start=time(18, 0),
        planned_end=time(20, 0),
        seated=datetime(2026, 7, 20, 18, 10),
        left=datetime(2026, 7, 20, 19, 32),
        table=table_a,
        extra_tables=[table_b],
        version=version,
        combination=combination,
    )
    _reservation(
        db,
        day=date(2026, 7, 19),
        seated=datetime(2026, 7, 19, 18, 0),
        left=None,
    )
    _reservation(
        db,
        day=date(2026, 7, 18),
        seated=datetime(2026, 7, 18, 19, 0),
        left=datetime(2026, 7, 18, 18, 0),
    )

    response = admin_client.get(f"/api/crm/rezerwacje/{complete.id}/profil")

    assert response.status_code == 200, response.text
    history = response.json()["historia"]
    assert [row["pomiar"] for row in history] == ["complete", "missing", "invalid"]
    measured = history[0]
    assert measured["planowany_czas_min"] == 120
    assert measured["rzeczywisty_czas_min"] == 82
    assert measured["odchylenie_min"] == -38
    assert measured["przydzial"] == {
        "sala_id": room.id,
        "sala_nazwa": "Main room",
        "stoliki": [
            {"id": table_a.id, "nazwa": "Historic A"},
            {"id": table_b.id, "nazwa": "Historic B"},
        ],
        "kombinacja": {
            "id": combination.id,
            "wersja_id": version.id,
            "nazwa": "Historic A + Historic B",
        },
        "proweniencja": "frozen",
    }
    assert history[1]["rzeczywisty_czas_min"] is None
    assert history[1]["odchylenie_min"] is None
    assert history[2]["rzeczywisty_czas_min"] is None
    assert history[2]["odchylenie_min"] is None


def test_planned_turn_supports_visit_ending_after_midnight():
    reservation = models.Termin(
        data=DAY,
        nazwisko="Overnight",
        godz_od=time(23, 0),
        godz_do=time(1, 0),
    )

    assert reservation_operational.planned_turn_minutes(reservation) == 120


def test_planned_turn_rejects_zero_length_plan():
    reservation = models.Termin(
        data=DAY,
        nazwisko="Zero length",
        godz_od=time(18, 0),
        godz_do=time(18, 0),
    )

    assert reservation_operational.planned_turn_minutes(reservation) is None


def test_table_ids_ignore_malformed_scalar_additional_tables():
    reservation = models.Termin(
        data=DAY,
        nazwisko="Legacy record",
        stolik_id=7,
        stoliki_dodatkowe=13,
    )

    assert reservation_operational._table_ids(reservation) == [7]


def test_missing_party_size_is_not_imputed_into_smallest_bucket():
    assert reservation_operational.party_bucket(None) is None
    assert reservation_operational.party_bucket(0) is None
    assert reservation_operational.party_bucket(2) == "1-2"


def test_operational_analytics_counts_measurements_resources_and_moves(
    admin_client,
    db,
):
    room, table_a, table_b, version, combination = _published_floor(db)
    combo_visit = _reservation(
        db,
        people=6,
        planned_start=time(18, 0),
        planned_end=time(20, 0),
        seated=datetime(2026, 7, 20, 18, 10),
        left=datetime(2026, 7, 20, 19, 32),
        table=table_a,
        extra_tables=[table_b],
        version=version,
        combination=combination,
    )
    _reservation(
        db,
        surname="Second Private Guest",
        phone="700200300",
        email="second@example.com",
        people=2,
        planned_start=time(17, 0),
        planned_end=time(18, 30),
        seated=datetime(2026, 7, 20, 17, 0),
        left=datetime(2026, 7, 20, 18, 30),
        table=table_a,
        version=version,
    )
    _reservation(
        db,
        surname="Missing Private Guest",
        phone="700200301",
        email="missing@example.com",
        people=4,
        seated=datetime(2026, 7, 20, 16, 0),
        left=None,
    )
    _reservation(
        db,
        surname="Invalid Private Guest",
        phone="700200302",
        email="invalid@example.com",
        people=8,
        seated=datetime(2026, 7, 20, 20, 0),
        left=datetime(2026, 7, 20, 19, 0),
    )
    moved = _reservation(
        db,
        surname="Moved Private Guest",
        phone="700200303",
        email="moved@example.com",
        people=8,
        planned_start=time(20, 0),
        planned_end=time(22, 0),
        seated=datetime(2026, 7, 20, 20, 0),
        left=datetime(2026, 7, 20, 21, 40),
        table=table_b,
        version=version,
    )
    no_assignment = _reservation(
        db,
        surname="Unassigned Private Guest",
        phone="700200304",
        email="unassigned@example.com",
        people=3,
        planned_start=time(22, 0),
        planned_end=time(23, 0),
        seated=datetime(2026, 7, 20, 22, 0),
        left=datetime(2026, 7, 20, 23, 10),
    )
    db.add(models.ReservationAudit(
        created_at=datetime(2026, 7, 20, 20, 45),
        reservation_ref="a" * 64,
        termin_id=moved.id,
        actor_kind="system",
        actor_user_id=None,
        actor_login=None,
        action="assign",
        reason="system_automation",
        diff={"changes": {"stolik_id": {"before": table_b.id, "after": table_a.id}}},
    ))
    db.commit()

    response = admin_client.get(
        "/api/analityka/rezerwacje/operacyjna?start=2026-07-20&end=2026-07-20",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"jakosc_danych", "turn_time", "wykorzystanie"}
    assert body["jakosc_danych"] == {
        "zakonczone_wizyty": 6,
        "z_pelnym_pomiarem": 4,
        "bez_pomiaru": 1,
        "nieprawidlowy_pomiar": 1,
        "pominiete_przeniesienia": 1,
        "kompletnosc_proc": 67,
    }
    assert body["turn_time"] == {
        "proba": 4,
        "mediana_min": 86.0,
        "srednia_min": 85.5,
        "planowana_mediana_min": 105.0,
        "odchylenie_min": -10.0,
        "wg_wielkosci_grupy": [
            {
                "grupa": "1-2",
                "proba": 1,
                "mediana_min": 90,
                "srednia_min": 90.0,
                "planowana_mediana_min": 90,
                "odchylenie_min": 0,
            },
            {
                "grupa": "3-4",
                "proba": 1,
                "mediana_min": 70,
                "srednia_min": 70.0,
                "planowana_mediana_min": 60,
                "odchylenie_min": 10,
            },
            {
                "grupa": "5-6",
                "proba": 1,
                "mediana_min": 82,
                "srednia_min": 82.0,
                "planowana_mediana_min": 120,
                "odchylenie_min": -38,
            },
            {
                "grupa": "7+",
                "proba": 1,
                "mediana_min": 100,
                "srednia_min": 100.0,
                "planowana_mediana_min": 120,
                "odchylenie_min": -20,
            },
        ],
    }
    usage = body["wykorzystanie"]
    assert usage["sale"] == [{
        "sala_id": room.id,
        "nazwa": "Main room",
        "wizyty": 2,
        "covery": 8,
        "rzeczywiste_minuty": 172,
        "pomiary": 2,
    }]
    assert usage["stoliki"] == [
        {
            "stolik_id": table_a.id,
            "nazwa": "Historic A",
            "sala_id": room.id,
            "sala_nazwa": "Main room",
            "wizyty": 2,
            "covery": 8,
            "rzeczywiste_minuty": 172,
            "pomiary": 2,
        },
        {
            "stolik_id": table_b.id,
            "nazwa": "Historic B",
            "sala_id": room.id,
            "sala_nazwa": "Main room",
            "wizyty": 1,
            "covery": 6,
            "rzeczywiste_minuty": 82,
            "pomiary": 1,
        },
    ]
    assert usage["kombinacje"] == [{
        "kombinacja_id": combination.id,
        "wersja_id": version.id,
        "nazwa": "Historic A + Historic B",
        "sala_id": room.id,
        "sala_nazwa": "Main room",
        "stoliki": [
            {"id": table_a.id, "nazwa": "Historic A"},
            {"id": table_b.id, "nazwa": "Historic B"},
        ],
        "wizyty": 1,
        "covery": 6,
        "rzeczywiste_minuty": 82,
        "pomiary": 1,
    }]
    assert usage["bez_przydzialu"] == {
        "wizyty": 1,
        "covery": 3,
        "rzeczywiste_minuty": 70,
        "pomiary": 1,
    }
    serialized = response.text
    for pii in (
        combo_visit.nazwisko,
        combo_visit.telefon,
        combo_visit.email,
        no_assignment.nazwisko,
        no_assignment.telefon,
        no_assignment.email,
    ):
        assert pii not in serialized


def test_operational_analytics_groups_a_combination_as_an_exact_unordered_set(
    admin_client,
    db,
):
    _room, table_a, table_b, version, combination = _published_floor(db)
    _reservation(
        db,
        people=6,
        seated=datetime(2026, 7, 20, 18, 0),
        left=datetime(2026, 7, 20, 19, 0),
        table=table_a,
        extra_tables=[table_b],
        version=version,
        combination=combination,
    )
    _reservation(
        db,
        people=6,
        seated=datetime(2026, 7, 20, 20, 0),
        left=datetime(2026, 7, 20, 21, 10),
        table=table_b,
        extra_tables=[table_a],
        version=version,
        combination=combination,
    )

    response = admin_client.get(
        "/api/analityka/rezerwacje/operacyjna?start=2026-07-20&end=2026-07-20",
    )

    assert response.status_code == 200, response.text
    combinations = response.json()["wykorzystanie"]["kombinacje"]
    assert len(combinations) == 1
    assert combinations[0]["wizyty"] == 2
    assert combinations[0]["covery"] == 12
    assert combinations[0]["rzeczywiste_minuty"] == 130


def test_operational_analytics_requires_exact_permission_and_fails_closed(
    client,
):
    analyst = factories.UserFactory(
        login="r7_analyst",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.analityka": True},
    )
    reception = factories.UserFactory(
        login="r7_reception",
        rola="szef",
        pracownik=None,
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )
    path = "/api/analityka/rezerwacje/operacyjna?start=2026-07-20&end=2026-07-20"

    assert client.get(path, headers=_headers(analyst)).status_code == 200
    assert client.get(path, headers=_headers(reception)).status_code == 403
    assert client.get(
        "/api/analityka/rezerwacje/operacyjna/przyszla",
        headers=_headers(analyst),
    ).status_code == 403


def test_operational_analytics_rejects_invalid_and_overlong_ranges(admin_client):
    assert admin_client.get(
        "/api/analityka/rezerwacje/operacyjna?start=2026-07-21&end=2026-07-20",
    ).status_code == 400
    assert admin_client.get(
        "/api/analityka/rezerwacje/operacyjna?start=2025-01-01&end=2026-07-20",
    ).status_code == 400
