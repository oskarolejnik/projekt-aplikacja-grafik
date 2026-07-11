"""Plan sali (/api/plan-sali) — pozycje stolików + status z rezerwacji dnia (roadmapa v1.5)."""

import datetime as dt

import models


def _stolik(db, nazwa, **kw):
    s = models.Stolik(nazwa=nazwa, **kw)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _rez(
    db, stolik, data, godz, status="rezerwacja", nazwisko="Gość", stoliki_dodatkowe=None
):
    t = models.Termin(data=data, nazwisko=nazwisko, rodzaj="stolik",
                      stolik_id=stolik.id, stoliki_dodatkowe=stoliki_dodatkowe,
                      godz_od=godz, status=status, liczba_osob=2)
    db.add(t); db.commit()
    return t


def test_plan_pusty(admin_client):
    b = admin_client.get("/api/plan-sali").json()
    assert b["stoliki"] == []
    assert b["podsumowanie"] == {"wolne": 0, "zarezerwowane": 0, "nieaktywne": 0, "zajete_live": 0}


def test_status_z_rezerwacji(admin_client, db):
    dzis = dt.date.today()
    s1 = _stolik(db, "S1", pojemnosc=4, strefa="sala")
    s2 = _stolik(db, "S2", pojemnosc=2, strefa="ogród")
    s3 = _stolik(db, "S3", aktywny=False)
    _rez(db, s1, dzis, dt.time(18, 0), "rezerwacja")
    _rez(db, s2, dzis, dt.time(19, 0), "potwierdzona")

    b = admin_client.get(f"/api/plan-sali?data={dzis}").json()
    by = {s["nazwa"]: s for s in b["stoliki"]}
    assert by["S1"]["status"] == "zarezerwowany"
    assert by["S2"]["status"] == "potwierdzony"
    assert by["S3"]["status"] == "nieaktywny"
    assert by["S1"]["rezerwacje"][0]["godz_od"] == "18:00"
    assert b["podsumowanie"]["zarezerwowane"] == 2
    assert set(b["strefy"]) == {"sala", "ogród"}


def test_kombinacja_oznacza_wszystkie_stoly_jako_zarezerwowane(admin_client, db):
    dzis = dt.date.today()
    s1 = _stolik(db, "K1", pojemnosc=4)
    s2 = _stolik(db, "K2", pojemnosc=4)
    s3 = _stolik(db, "K3", pojemnosc=4)
    wolny = _stolik(db, "K4", pojemnosc=4)
    rezerwacja = _rez(
        db, s1, dzis, dt.time(18, 0), stoliki_dodatkowe=[s2.id, s3.id]
    )

    plan = admin_client.get(f"/api/plan-sali?data={dzis}").json()
    by_id = {s["id"]: s for s in plan["stoliki"]}

    for sid in (s1.id, s2.id, s3.id):
        assert by_id[sid]["status"] == "zarezerwowany"
        assert [r["id"] for r in by_id[sid]["rezerwacje"]] == [rezerwacja.id]
    assert by_id[wolny.id]["status"] == "wolny"
    assert plan["podsumowanie"]["zarezerwowane"] == 3


def test_plan_sali_pomija_uszkodzone_id_w_legacy_json(admin_client, db):
    dzis = dt.date.today()
    glowny = _stolik(db, "L1", pojemnosc=4)
    dodatkowy = _stolik(db, "L2", pojemnosc=4)
    scalar_main = _stolik(db, "L3", pojemnosc=4)
    _rez(db, glowny, dzis, dt.time(18, 0),
         stoliki_dodatkowe=[dodatkowy.id, "x", None, dodatkowy.id])
    _rez(db, scalar_main, dzis, dt.time(20, 0), stoliki_dodatkowe=123)

    odpowiedz = admin_client.get(f"/api/plan-sali?data={dzis}")
    assert odpowiedz.status_code == 200
    by_id = {s["id"]: s for s in odpowiedz.json()["stoliki"]}
    assert by_id[glowny.id]["status"] == "zarezerwowany"
    assert by_id[dodatkowy.id]["status"] == "zarezerwowany"
    assert by_id[scalar_main.id]["status"] == "zarezerwowany"


def test_status_wolny_w_inny_dzien(admin_client, db):
    s = _stolik(db, "A1")
    _rez(db, s, dt.date.today(), dt.time(18, 0))
    jutro = dt.date.today() + dt.timedelta(days=1)
    b = admin_client.get(f"/api/plan-sali?data={jutro}").json()
    assert b["stoliki"][0]["status"] == "wolny"


def test_odwolana_rezerwacja_nie_liczy_sie(admin_client, db):
    s = _stolik(db, "B1")
    _rez(db, s, dt.date.today(), dt.time(18, 0), status="odwolana")
    b = admin_client.get("/api/plan-sali").json()
    assert b["stoliki"][0]["status"] == "wolny"


def test_live_oblozenie_z_pos(admin_client, db):
    s = _stolik(db, "L1", rewir_nr=42)
    db.add(models.StanStolow(rewir_nr=42, otwarte=3)); db.commit()
    b = admin_client.get("/api/plan-sali").json()
    st = next(x for x in b["stoliki"] if x["nazwa"] == "L1")
    assert st["rewir_nr"] == 42
    assert st["live"]["zajete"] is True and st["live"]["otwarte"] == 3
    assert b["podsumowanie"]["zajete_live"] == 1


def test_brak_live_gdy_brak_rewiru(admin_client, db):
    _stolik(db, "L2")  # bez rewir_nr → brak podpięcia POS
    b = admin_client.get("/api/plan-sali").json()
    assert b["stoliki"][0]["live"] is None


def test_zapisz_pozycje_z_clampem(admin_client, db):
    s = _stolik(db, "P1")
    r = admin_client.put("/api/plan-sali/pozycje", json=[{"id": s.id, "plan_x": 40, "plan_y": 150}])
    assert r.status_code == 200 and r.json()["zapisane"] == 1
    st = admin_client.get("/api/plan-sali").json()["stoliki"][0]
    assert st["plan_x"] == 40
    assert st["plan_y"] == 100  # 150 przycięte do 0–100
