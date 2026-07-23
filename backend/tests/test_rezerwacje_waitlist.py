"""Slice v2 S5: waitlist v2 — powiadomienie „stolik gotowy", HOLD stołu (blokada w rdzeniu zajętości),
publiczny zapis online. HOLD blokuje AUTOMATYCZNY dobór (auto-przydział / online), nie ręczny admina."""

from datetime import date, timedelta

import models
from public_widget_v2_helpers import enable_widget_v2, public_waitlist_v2

DZIEN = (date.today() + timedelta(days=30)).isoformat()


def _stolik(admin_client, nazwa, poj=4):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": poj})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait(admin_client, data, godz, osoby, nazwisko="Czekacz", email=None):
    body = {"data": data, "godz_od": godz, "liczba_osob": osoby, "nazwisko": nazwisko}
    if email:
        body["email"] = email
    r = admin_client.post("/api/lista-oczekujacych", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _rez(admin_client, data, godz, osoby):
    r = admin_client.post("/api/rezerwacje-stolik",
                          json={"data": data, "godz_od": godz, "liczba_osob": osoby, "nazwisko": "Gość"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_hold_blokuje_auto_przydzial(admin_client):
    s1, s2 = _stolik(admin_client, "S1", 2), _stolik(admin_client, "S2", 2)
    e = _wait(admin_client, DZIEN, "18:00", 2)
    assert admin_client.post(f"/api/lista-oczekujacych/{e}/hold",
                             json={"stolik_id": s1, "minuty": 30}).status_code == 200
    r = _rez(admin_client, DZIEN, "18:00", 2)
    przydzial = admin_client.post(f"/api/rezerwacje-stolik/{r}/auto-przydziel").json()["przydzial"]
    assert przydzial["stoliki"] == [s2]                 # S1 pod holdem → silnik go pomija


def test_zwolnienie_holdu_odblokowuje(admin_client):
    s1 = _stolik(admin_client, "S1", 2)
    e = _wait(admin_client, DZIEN, "18:00", 2)
    admin_client.post(f"/api/lista-oczekujacych/{e}/hold", json={"stolik_id": s1, "minuty": 30})
    r = _rez(admin_client, DZIEN, "18:00", 2)
    # jedyny stół trzymany → brak wolnego
    assert admin_client.post(f"/api/rezerwacje-stolik/{r}/auto-przydziel").status_code == 409
    assert admin_client.post(f"/api/lista-oczekujacych/{e}/zwolnij-hold").status_code == 200
    # po zwolnieniu holdu stół wraca do puli
    assert admin_client.post(f"/api/rezerwacje-stolik/{r}/auto-przydziel").status_code == 200


def test_hold_waliduje_stolik(admin_client):
    e = _wait(admin_client, DZIEN, "18:00", 2)
    assert admin_client.post(f"/api/lista-oczekujacych/{e}/hold",
                             json={"stolik_id": 999999, "minuty": 30}).status_code == 400


def test_realizacja_konczy_wlasny_hold(admin_client):
    s1 = _stolik(admin_client, "S1", 4)
    e = _wait(admin_client, DZIEN, "18:00", 2)
    admin_client.post(f"/api/lista-oczekujacych/{e}/hold", json={"stolik_id": s1, "minuty": 30})
    # realizacja na TRZYMANYM stole nie może kolidować z własnym holdem (hold czyszczony przed walidacją)
    r = admin_client.post(f"/api/lista-oczekujacych/{e}/zrealizuj", json={"stolik_id": s1})
    assert r.status_code == 200, r.text
    wpis = r.json()["wpis"]
    assert wpis["status"] == "zaakceptowano" and wpis["hold_stolik_id"] is None


def test_wielostolowy_hold_jest_czasowy_i_realizuje_walk_in(admin_client, db):
    tables = [_stolik(admin_client, f"R4-{index}", 6) for index in range(1, 4)]
    combination = admin_client.post("/api/kombinacje", json={
        "nazwa": "R4 6+6+6",
        "stoliki": tables,
        "pojemnosc_min": 18,
        "pojemnosc_max": 18,
    })
    assert combination.status_code == 201, combination.text
    waitlist_id = _wait(admin_client, DZIEN, "18:00", 18)

    held = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/hold",
        json={"stoliki": tables, "minuty": 30},
    )
    assert held.status_code == 200, held.text
    assert held.json()["hold_stolik_id"] == tables[0]
    assert held.json()["hold_stoliki_dodatkowe"] == tables[1:]
    assert held.json()["hold_godz_od"] == "18:00"
    assert held.json()["hold_godz_do"] == "20:00"
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 3 * 120

    later_id = _rez(admin_client, DZIEN, "21:00", 18)
    later = admin_client.post(f"/api/rezerwacje-stolik/{later_id}/auto-przydziel")
    assert later.status_code == 200, later.text
    assert set(later.json()["przydzial"]["stoliki"]) == set(tables)

    realised = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zrealizuj",
        json={"tryb": "walk_in"},
    )
    assert realised.status_code == 200, realised.text
    reservation = realised.json()["rezerwacja"]
    assert reservation["kanal"] == "walk_in"
    assert reservation["faza_hosta"] == "posadzony"
    assert {reservation["stolik_id"], *reservation["stoliki_dodatkowe"]} == set(tables)
    assert realised.json()["wpis"]["hold_stolik_id"] is None


def test_override_required_przy_realizacji_zachowuje_pelny_wielostolowy_hold(
    admin_client, db,
):
    booking_date = date.fromisoformat(DZIEN)
    service = admin_client.post("/api/godziny-otwarcia", json={
        "nazwa": "Kolacja R4 rollback",
        "dzien_tygodnia": booking_date.weekday(),
        "godz_od": "12:00",
        "godz_do": "22:00",
        "ostatni_zasiadek": "21:00",
        "krok_slotu_min": 15,
        "domyslny_turn_time_min": 90,
        "max_jednoczesnych_rez": 1,
    })
    assert service.status_code == 201, service.text
    policy = admin_client.post("/api/nadpisania-regul-rezerwacji", json={
        "serwis_id": service.json()["id"],
        "kanal": "oba",
        "bufor_min": 15,
    })
    assert policy.status_code == 201, policy.text

    held_tables = [_stolik(admin_client, f"R4-RB-{index}", 4) for index in range(1, 3)]
    blocker_table = _stolik(admin_client, "R4-RB-bloker", 4)
    combination = admin_client.post("/api/kombinacje", json={
        "nazwa": "R4 rollback 4+4",
        "stoliki": held_tables,
        "pojemnosc_min": 8,
        "pojemnosc_max": 8,
    })
    assert combination.status_code == 201, combination.text

    waitlist_id = _wait(admin_client, DZIEN, "18:00", 8, nazwisko="Rollback hold")
    held = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/hold",
        json={"stoliki": held_tables, "minuty": 30},
    )
    assert held.status_code == 200, held.text

    blocker = admin_client.post("/api/rezerwacje-stolik", json={
        "data": DZIEN,
        "godz_od": "18:00",
        "stolik_id": blocker_table,
        "liczba_osob": 2,
        "nazwisko": "Zajmuje limit R4",
    })
    assert blocker.status_code == 201, blocker.text

    db.expire_all()
    waitlist = db.get(models.ListaOczekujacych, waitlist_id)
    projection_before = (
        waitlist.status,
        waitlist.termin_id,
        waitlist.hold_stolik_id,
        tuple(waitlist.hold_stoliki_dodatkowe or ()),
        waitlist.hold_godz_od,
        waitlist.hold_godz_do,
        waitlist.hold_bufor_min,
        waitlist.hold_do,
    )
    claims_before = [
        (
            claim.id,
            claim.stolik_id,
            claim.data,
            claim.minute,
            claim.expires_at,
            claim.created_at,
        )
        for claim in db.query(models.RezerwacjaStolikClaim).filter_by(
            waitlist_id=waitlist_id,
        ).order_by(models.RezerwacjaStolikClaim.id).all()
    ]
    assert projection_before[2] == held_tables[0]
    assert projection_before[3] == tuple(held_tables[1:])
    assert projection_before[6] == 15
    assert len(claims_before) == len(held_tables) * (90 + 15)
    assert {
        minute
        for _, _, _, minute, _, _ in claims_before
    } == set(range(18 * 60, 19 * 60 + 45))
    db.rollback()

    warning = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zrealizuj",
        json={"tryb": "walk_in"},
    )
    assert warning.status_code == 409, warning.text
    assert warning.json()["code"] == "CONCURRENT_RESERVATION_LIMIT"
    assert warning.json()["availability"]["decision"] == "override_required"

    db.expire_all()
    waitlist = db.get(models.ListaOczekujacych, waitlist_id)
    projection_after = (
        waitlist.status,
        waitlist.termin_id,
        waitlist.hold_stolik_id,
        tuple(waitlist.hold_stoliki_dodatkowe or ()),
        waitlist.hold_godz_od,
        waitlist.hold_godz_do,
        waitlist.hold_bufor_min,
        waitlist.hold_do,
    )
    claims_after = [
        (
            claim.id,
            claim.stolik_id,
            claim.data,
            claim.minute,
            claim.expires_at,
            claim.created_at,
        )
        for claim in db.query(models.RezerwacjaStolikClaim).filter_by(
            waitlist_id=waitlist_id,
        ).order_by(models.RezerwacjaStolikClaim.id).all()
    ]
    assert projection_after == projection_before
    assert claims_after == claims_before


def test_powiadom_kolejkuje_bez_stempla_i_nie_dubluje(admin_client, db):
    table_id = _stolik(admin_client, "Notify", 2)
    e = _wait(admin_client, DZIEN, "18:00", 2, email="g@x.pl")
    offered = admin_client.post(
        f"/api/lista-oczekujacych/{e}/oferta",
        json={"stolik_id": table_id, "minuty": 30, "expected_offer_version": 0},
        headers={"Idempotency-Key": "waitlist-notify-offer"},
    )
    assert offered.status_code == 200, offered.text
    message_id = offered.json()["messages"][0]["id"]
    r1 = admin_client.post(f"/api/lista-oczekujacych/{e}/powiadom")
    assert r1.status_code == 200
    assert r1.json()["queued"] is True
    assert r1.json()["wpis"]["powiadomiono_at"] is None
    assert r1.json()["messages"][0]["state"] == "queued"
    assert r1.json()["messages"][0]["id"] == message_id
    r2 = admin_client.post(f"/api/lista-oczekujacych/{e}/powiadom")
    assert r2.json()["queued"] is True
    assert r2.json()["juz_powiadomiony"] is False
    assert r2.json()["messages"][0]["id"] == message_id
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=e,
        typ_zdarzenia="table_ready",
    ).count() == 1


def test_online_zapis_na_liste_oczekujacych(admin_client, client):
    enable_widget_v2(admin_client)
    r = public_waitlist_v2(
        client,
        data=DZIEN,
        godz_od="18:00",
        liczba_osob=2,
        nazwisko="Online Gość",
    )
    assert r.status_code == 201, r.text
    assert "token" not in r.json()
    assert r.json()["wpis"]["status"] == "oczekuje"
    lista = admin_client.get(f"/api/lista-oczekujacych?data={DZIEN}").json()["lista"]
    assert any(w["kanal"] == "online" for w in lista)


def test_online_zapis_wymaga_wlaczonego_online(admin_client, client):
    admin_client.put("/api/lokal/config", json={"rezerwacje_online": False})
    r = client.post("/api/online/lista-oczekujacych",
                    json={"data": DZIEN, "godz_od": "18:00", "liczba_osob": 2, "nazwisko": "X"})
    assert r.status_code == 404          # moduł online wyłączony


def test_realizacja_online_waitlisty_zachowuje_kanal_i_nie_sadza(admin_client, client):
    enable_widget_v2(admin_client)
    table_id = _stolik(admin_client, "Online-W", 4)
    created = public_waitlist_v2(
        client,
        data=DZIEN,
        godz_od="18:00",
        liczba_osob=2,
        nazwisko="Online oczekujący",
    )
    assert created.status_code == 201, created.text
    waitlist = admin_client.get(
        f"/api/lista-oczekujacych?data={DZIEN}"
    ).json()["lista"]
    waitlist_id = next(item["id"] for item in waitlist if item["kanal"] == "online")

    realised = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zrealizuj",
        json={"stolik_id": table_id},
    )
    assert realised.status_code == 409
    assert realised.json()["code"] == "DATE_CLOSED"
    realised = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zrealizuj",
        json={
            "stolik_id": table_id,
            "przekrocz_limity": True,
            "nadpisanie_limitow": {
                "powod": "operational_decision",
                "notatka": "Potwierdzono realizację wpisu online",
                "potwierdzone": True,
            },
        },
    )
    assert realised.status_code == 200, realised.text
    assert realised.json()["rezerwacja"]["kanal"] == "online"
    assert realised.json()["rezerwacja"]["faza_hosta"] is None
