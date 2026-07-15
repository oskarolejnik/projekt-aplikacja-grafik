"""Serwisy rezerwacyjne (Slice 1a): turn-time zależny od wielkości grupy, wiele serwisów na dzień
(lunch/kolacja) oraz pacing (limit coverów na okno). Publiczne endpointy online wołane przez
osobny `client` (bez tokenu); admin konfiguruje przez `admin_client`.

Daty testowe zawsze wskazują dwa kolejne przyszłe poniedziałki (weekday=0).
"""

from datetime import date, timedelta

import database
import models
import reservation_service

_DZIS = date.today()
_DNI_DO_PONIEDZIALKU = (7 - _DZIS.weekday()) % 7 or 7
_PONIEDZIALEK = _DZIS + timedelta(days=_DNI_DO_PONIEDZIALKU)
PON = _PONIEDZIALEK.isoformat()
PON2 = (_PONIEDZIALEK + timedelta(days=7)).isoformat()


def test_lock_tables_odswieza_stan_z_identity_map(db):
    stolik = models.Stolik(
        nazwa="S-lock", pojemnosc=4, aktywny=True, kolejnosc=0,
    )
    db.add(stolik)
    db.commit()
    stale = db.get(models.Stolik, stolik.id)
    assert stale.aktywny is True

    other = database.SessionLocal()
    try:
        changed = other.get(models.Stolik, stolik.id)
        changed.aktywny = False
        other.commit()
    finally:
        other.close()

    # Sesja A nadal ma starą instancję, ale odczyt blokujący musi zastąpić
    # jej stan najświeższymi wartościami z bazy po ewentualnym oczekiwaniu.
    assert stale.aktywny is True
    locked = reservation_service.lock_tables(db, [stolik.id])
    assert locked == (stale,)
    assert locked[0].aktywny is False


def _enable_online(admin_client):
    assert admin_client.put("/api/lokal/config", json={"rezerwacje_online": True}).status_code == 200


def _serwis(admin_client, **kw):
    dane = {"dzien_tygodnia": 0, "godz_od": "12:00", "godz_do": "23:00"}
    dane.update(kw)
    r = admin_client.post("/api/godziny-otwarcia", json=dane)
    assert r.status_code == 201, r.text
    return r.json()


def _stolik(admin_client, nazwa="S1", pojemnosc=4):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": pojemnosc})
    assert r.status_code == 201, r.text
    return r.json()


# ── Turn-time zależny od grupy ───────────────────────────────────────────────

def test_turn_time_zalezny_od_grupy(admin_client):
    _serwis(admin_client, turn_time_progi=[{"do_osob": 2, "min": 90}, {"do_osob": 8, "min": 150}])
    s = _stolik(admin_client, pojemnosc=8)
    para = admin_client.post("/api/rezerwacje-stolik", json={
        "data": PON, "godz_od": "18:00", "stolik_id": s["id"], "liczba_osob": 2, "nazwisko": "Para"}).json()
    assert para["godz_do"] == "19:30"          # 18:00 + 90 min
    grupa = admin_client.post("/api/rezerwacje-stolik", json={
        "data": PON2, "godz_od": "18:00", "stolik_id": s["id"], "liczba_osob": 6, "nazwisko": "Grupa"}).json()
    assert grupa["godz_do"] == "20:30"         # 18:00 + 150 min (próg do_osob=8)


def test_turn_time_powyzej_najwyzszego_progu(admin_client):
    # grupa większa niż najwyższy próg → najdłuższy zasiadek (ostatni próg)
    _serwis(admin_client, turn_time_progi=[{"do_osob": 4, "min": 90}, {"do_osob": 6, "min": 120}])
    s = _stolik(admin_client, pojemnosc=12)
    body = admin_client.post("/api/rezerwacje-stolik", json={
        "data": PON, "godz_od": "18:00", "stolik_id": s["id"], "liczba_osob": 10, "nazwisko": "Duza"}).json()
    assert body["godz_do"] == "20:00"          # 18:00 + 120 min


def test_progi_sortowane_niezaleznie_od_kolejnosci(admin_client):
    _serwis(admin_client, turn_time_progi=[{"do_osob": 8, "min": 150}, {"do_osob": 2, "min": 90}])
    g = admin_client.get("/api/godziny-otwarcia").json()["godziny"][0]
    assert [p["do_osob"] for p in g["turn_time_progi"]] == [2, 8]


def test_brak_progow_zachowuje_dlugosc_slotu(admin_client):
    # regresja: bez turn_time_progi liczy się dlugosc_slotu_min (zachowanie historyczne)
    _serwis(admin_client, dlugosc_slotu_min=90)
    s = _stolik(admin_client)
    body = admin_client.post("/api/rezerwacje-stolik", json={
        "data": PON, "godz_od": "18:00", "stolik_id": s["id"], "liczba_osob": 2, "nazwisko": "A"}).json()
    assert body["godz_do"] == "19:30"          # 18:00 + 90


# ── Wiele serwisów na dzień (lunch + kolacja) ────────────────────────────────

def test_dwa_serwisy_dnia_w_dostepnosci(admin_client, client):
    _enable_online(admin_client)
    _stolik(admin_client)
    _serwis(admin_client, nazwa="Lunch", godz_od="12:00", godz_do="15:00", dlugosc_slotu_min=60)
    _serwis(admin_client, nazwa="Kolacja", godz_od="18:00", godz_do="22:00", dlugosc_slotu_min=60)
    sloty = client.get(f"/api/online/dostepnosc?data={PON}&osoby=2").json()["sloty"]
    godziny = [s["godz_od"] for s in sloty]
    assert "12:00" in godziny and "18:00" in godziny
    assert "16:00" not in godziny              # przerwa między serwisami
    etykiety = {s["serwis"] for s in sloty}
    assert "Lunch" in etykiety and "Kolacja" in etykiety


# ── Pacing (limit coverów) ───────────────────────────────────────────────────

def test_pacing_limit_rezerwacji_blokuje_online(admin_client, client):
    _enable_online(admin_client)
    for i in range(5):
        _stolik(admin_client, nazwa=f"S{i}", pojemnosc=4)   # dużo stołów, ale pacing tnie
    _serwis(admin_client, dlugosc_slotu_min=120, pacing_max_rez=2)

    def rez():
        return client.post("/api/online/rezerwacja", json={
            "data": PON, "godz_od": "18:00", "liczba_osob": 2, "nazwisko": "X"})

    assert rez().status_code == 201
    assert rez().status_code == 201
    assert rez().status_code == 409            # 3. przekracza pacing mimo wolnych stołów
    slot = next(s for s in client.get(f"/api/online/dostepnosc?data={PON}&osoby=2").json()["sloty"]
                if s["godz_od"] == "18:00")
    assert slot["pacing_pelny"] is True
    assert slot["wolne"] == 0 and slot["wolne_stoly"] == 0
    assert slot["dostepny"] is False


def test_pacing_limit_osob(admin_client, client):
    _enable_online(admin_client)
    for i in range(5):
        _stolik(admin_client, nazwa=f"S{i}", pojemnosc=8)
    _serwis(admin_client, dlugosc_slotu_min=120, pacing_max_osob=6)

    def rez(osoby):
        return client.post("/api/online/rezerwacja", json={
            "data": PON, "godz_od": "18:00", "liczba_osob": osoby, "nazwisko": "X"})

    assert rez(4).status_code == 201           # 4 osoby
    assert rez(4).status_code == 409           # +4 = 8 > 6
    assert rez(2).status_code == 201           # +2 = 6 = limit (nie przekracza)


def test_admin_przekracza_pacing_dopiero_po_jawnym_ostrzezeniu(admin_client, db):
    # Pierwsza próba respektuje limit; druga musi być świadomym ponowieniem.
    s = _stolik(admin_client, nazwa="S1")
    s2 = _stolik(admin_client, nazwa="S2")
    _serwis(admin_client, pacing_max_rez=1)
    first = admin_client.post("/api/rezerwacje-stolik", json={"data": PON, "godz_od": "18:00",
        "stolik_id": s["id"], "liczba_osob": 2, "nazwisko": "A", "przekrocz_limity": True})
    assert first.status_code == 201
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=first.json()["id"], action="override",
    ).count() == 0
    body = {"data": PON, "godz_od": "18:00",
            "stolik_id": s2["id"], "liczba_osob": 2, "nazwisko": "B"}
    blocked = admin_client.post("/api/rezerwacje-stolik", json=body)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "PACING_RESERVATION_LIMIT"
    overridden = admin_client.post(
        "/api/rezerwacje-stolik", json={**body, "przekrocz_limity": True},
    )
    assert overridden.status_code == 201
    reservation_id = overridden.json()["id"]
    assert db.query(models.RezerwacjaPacingLedger).filter_by(
        termin_id=reservation_id, override=True,
    ).count() == 1
    audit = db.query(models.ReservationAudit).filter_by(
        termin_id=reservation_id, action="override",
    ).one()
    assert audit.reason == "pacing_override"
    assert audit.diff["override"] == {
        "violations": [{
            "rule": "pacing_reservations",
            "observed": 1,
            "limit": 1,
            "projected": 2,
        }],
    }


def test_ujemny_pacing_jest_odrzucany_a_historyczny_nie_blokuje_override(admin_client, db):
    invalid = admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": 0,
        "godz_od": "12:00",
        "godz_do": "23:00",
        "pacing_max_rez": -1,
    })
    assert invalid.status_code == 422

    service = _serwis(admin_client)
    legacy = db.get(models.GodzinyOtwarcia, service["id"])
    legacy.pacing_max_rez = -1
    legacy.pacing_max_osob = -5
    db.commit()
    listed = admin_client.get("/api/godziny-otwarcia")
    assert listed.status_code == 200, listed.text
    listed_service = next(row for row in listed.json()["godziny"] if row["id"] == service["id"])
    assert listed_service["pacing_max_rez"] is None
    assert listed_service["pacing_max_osob"] is None
    table = _stolik(admin_client, nazwa="LegacyLimit")
    created = admin_client.post("/api/rezerwacje-stolik", json={
        "data": PON,
        "godz_od": "18:00",
        "stolik_id": table["id"],
        "liczba_osob": 2,
        "nazwisko": "Historyczna konfiguracja",
        "przekrocz_limity": True,
    })
    assert created.status_code == 201, created.text
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=created.json()["id"], action="override",
    ).count() == 0
