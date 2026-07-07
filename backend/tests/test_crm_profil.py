"""Slice 5b: profil gościa 360 — upsert/GET, szyfrowanie alergii (RODO art. 9) at-rest,
klucz jako hash (nie plaintext PII), wzbogacenie listy CRM o flagi profilu.
Gość bez telefonu/e-maila → klucz CRM = nazwisko.lower()."""

import datetime as dt

from sqlalchemy import text

import models


def _rez(db, nazwisko="Kowalski", status="odbyla"):
    db.add(models.Termin(rodzaj="stolik", data=dt.date(2026, 7, 13), nazwisko=nazwisko, status=status,
                         kanal="reczna", zadatek=0.0, liczba_osob=2, utworzono_at=dt.datetime.utcnow(),
                         godz_od=dt.time(18, 0)))
    db.commit()


def test_profil_upsert_i_get_360(admin_client, db):
    _rez(db)                                             # klucz CRM = "kowalski"
    r = admin_client.put("/api/crm/goscie/kowalski/profil", json={
        "vip": True, "tagi": ["stały", "okno"], "alergie": "orzechy", "preferowana_strefa": "ogród",
        "okazja_typ": "urodziny", "okazja_data": "05-12", "marketing_zgoda": True})
    assert r.status_code == 200 and r.json()["vip"] is True and r.json()["alergie"] == "orzechy"
    g = admin_client.get("/api/crm/goscie/kowalski").json()
    assert g["profil"]["vip"] is True and g["profil"]["alergie"] == "orzechy"
    assert g["profil"]["tagi"] == ["stały", "okno"] and g["profil"]["preferowana_strefa"] == "ogród"
    assert g["statystyki"]["wizyt"] == 1 and g["statystyki"]["odbyte"] == 1
    assert len(g["historia"]) == 1 and g["historia"][0]["status"] == "odbyla"


def test_alergie_szyfrowane_a_klucz_zahaszowany(admin_client, db):
    _rez(db, nazwisko="Nowak")
    admin_client.put("/api/crm/goscie/nowak/profil", json={"alergie": "gluten"})
    p = db.query(models.ProfilGoscia).first()
    assert len(p.klucz_hash) == 64 and p.klucz_hash != "nowak"      # sha256, nie plaintext
    # alergie w bazie leżą zaszyfrowane (prefiks enc:v1:), a ORM zwraca jawny tekst
    surowe = db.execute(text("SELECT alergie FROM profile_gosci")).scalar()
    assert surowe.startswith("enc:v1:")
    assert p.alergie == "gluten"                                    # transparentne odszyfrowanie


def test_lista_crm_pokazuje_flagi_profilu(admin_client, db):
    _rez(db, nazwisko="Kowalski", status="odbyla")
    admin_client.put("/api/crm/goscie/kowalski/profil", json={"vip": True, "tagi": ["VIP"], "alergie": "orzechy"})
    goscie = admin_client.get("/api/crm/goscie").json()
    g = next(x for x in goscie if x["klucz"] == "kowalski")
    assert g["vip"] is True and g["tagi"] == ["VIP"] and g["ma_alergie"] is True and g["ma_profil"] is True


def test_vip_auto_z_wizyt_lub_reczny(admin_client, db):
    # 5 odbytych wizyt → vip auto = True (bez profilu)
    for _ in range(5):
        _rez(db, nazwisko="Stalybywalec", status="odbyla")
    g = next(x for x in admin_client.get("/api/crm/goscie").json() if x["klucz"] == "stalybywalec")
    assert g["vip"] is True and g["ma_profil"] is False


def test_gosc_bez_profilu(admin_client, db):
    _rez(db, nazwisko="Bezprofilu")
    g = admin_client.get("/api/crm/goscie/bezprofilu").json()
    assert g["profil"] is None and g["statystyki"]["wizyt"] == 1


def test_profil_pusty_klucz_400(admin_client):
    assert admin_client.put("/api/crm/goscie/%20/profil", json={"vip": True}).status_code == 400
