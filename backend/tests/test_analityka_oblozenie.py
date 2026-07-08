"""Slice v2 S8: analityka obłożenia (stołowe/miejscowe) + RevPASH dzienny/agregat.
Stołogodziny = aktywne stoły × godziny serwisów; blackout zeruje dzień; RevPASH = utarg netto / stołogodziny.
2026-07-13 = poniedziałek (weekday 0)."""

import datetime as dt

PON = "2026-07-13"


def _stolik(admin_client, nazwa, poj=4):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": poj})
    assert r.status_code == 201
    return r.json()["id"]


def _serwis(admin_client, dzien=0):
    assert admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": dzien, "godz_od": "12:00", "godz_do": "22:00",
        "dlugosc_slotu_min": 120}).status_code == 201     # 10 h otwarcia, turn-time 120 min


def _rez(admin_client, godz, osoby, stolik_id):
    assert admin_client.post("/api/rezerwacje-stolik", json={
        "data": PON, "godz_od": godz, "liczba_osob": osoby, "nazwisko": "G",
        "stolik_id": stolik_id}).status_code == 201


def test_oblozenie_i_revpash_licza_sie(admin_client, db):
    import models
    s1 = _stolik(admin_client, "S1", 4)
    _stolik(admin_client, "S2", 4)                        # 2 stoły × 10 h = 20 stołogodzin
    _serwis(admin_client)
    _rez(admin_client, "18:00", 2, s1)                    # 1 stół × 2 h = 2 stołogodziny; 4 miejscogodziny
    db.add(models.UtargDnia(data=dt.date(2026, 7, 13), zrodlo="reczny", netto=1000.0,
                            aktualizacja_at=dt.datetime.utcnow()))
    db.commit()
    dzien = admin_client.get(f"/api/analityka/oblozenie?start={PON}&end={PON}").json()["per_dzien"][0]
    assert dzien["dostepne_stologodziny"] == 20.0
    assert dzien["wykorzystane_stologodziny"] == 2.0
    assert dzien["oblozenie_stolowe_proc"] == 10       # 2/20
    assert dzien["oblozenie_miejscowe_proc"] == 5      # 4 / (8 miejsc × 10 h = 80)
    assert dzien["revpash"] == 50.0                    # 1000 / 20


def test_utarg_max_po_zrodlach(admin_client, db):
    import models
    _stolik(admin_client, "S1", 4)
    _serwis(admin_client)
    # dwa źródła raportują ten sam dzień → bierzemy MAX (bez podwójnego liczenia)
    db.add(models.UtargDnia(data=dt.date(2026, 7, 13), zrodlo="reczny", netto=800.0, aktualizacja_at=dt.datetime.utcnow()))
    db.add(models.UtargDnia(data=dt.date(2026, 7, 13), zrodlo="csv", netto=1000.0, aktualizacja_at=dt.datetime.utcnow()))
    db.commit()
    dzien = admin_client.get(f"/api/analityka/oblozenie?start={PON}&end={PON}").json()["per_dzien"][0]
    assert dzien["utarg_netto"] == 1000.0 and dzien["revpash"] == 100.0   # 1000 / (1×10)


def test_oblozenie_blackout_zeruje_dzien(admin_client):
    _stolik(admin_client, "S1", 4)
    _serwis(admin_client)
    admin_client.post("/api/wyjatki-kalendarza", json={"data": PON, "typ": "blackout"})
    dzien = admin_client.get(f"/api/analityka/oblozenie?start={PON}&end={PON}").json()["per_dzien"][0]
    assert dzien["dostepne_stologodziny"] == 0.0 and dzien["revpash"] is None


def test_oblozenie_bez_utargu_revpash_none(admin_client):
    _stolik(admin_client, "S1", 4)
    _serwis(admin_client)
    dzien = admin_client.get(f"/api/analityka/oblozenie?start={PON}&end={PON}").json()["per_dzien"][0]
    assert dzien["revpash"] is None and dzien["oblozenie_stolowe_proc"] == 0


def test_oblozenie_gating_pro(admin_client):
    admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False})
    assert admin_client.get(f"/api/analityka/oblozenie?start={PON}&end={PON}").status_code == 403
