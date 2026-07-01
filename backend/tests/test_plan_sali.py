"""Plan sali (/api/plan-sali) — pozycje stolików + status z rezerwacji dnia (roadmapa v1.5)."""

import datetime as dt

import models


def _stolik(db, nazwa, **kw):
    s = models.Stolik(nazwa=nazwa, **kw)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _rez(db, stolik, data, godz, status="rezerwacja", nazwisko="Gość"):
    t = models.Termin(data=data, nazwisko=nazwisko, rodzaj="stolik",
                      stolik_id=stolik.id, godz_od=godz, status=status, liczba_osob=2)
    db.add(t); db.commit()
    return t


def test_plan_pusty(admin_client):
    b = admin_client.get("/api/plan-sali").json()
    assert b["stoliki"] == []
    assert b["podsumowanie"] == {"wolne": 0, "zarezerwowane": 0, "nieaktywne": 0}


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


def test_zapisz_pozycje_z_clampem(admin_client, db):
    s = _stolik(db, "P1")
    r = admin_client.put("/api/plan-sali/pozycje", json=[{"id": s.id, "plan_x": 40, "plan_y": 150}])
    assert r.status_code == 200 and r.json()["zapisane"] == 1
    st = admin_client.get("/api/plan-sali").json()["stoliki"][0]
    assert st["plan_x"] == 40
    assert st["plan_y"] == 100  # 150 przycięte do 0–100
