"""R1b.2: bezpieczny handoff reservation_id → CRM i kontrakt cache PII."""

from datetime import date, datetime, time, timedelta

import factories
import main
import models
import uprawnienia
from auth import create_access_token
from crm_identity import hash_key, reservation_fallback_hash


DAY = date(2026, 7, 20)


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _user(login, *permissions):
    return factories.UserFactory(
        login=login,
        rola="szef",
        pracownik=None,
        uprawnienia_override={permission: True for permission in permissions},
    )


def _reception():
    return factories.UserFactory(
        login="recepcja_crm_r1b2",
        rola="szef",
        pracownik=None,
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )


def _reservation(
    db,
    *,
    reservation_date=DAY,
    nazwisko="Anna Kowalska",
    telefon="600100200",
    email="anna@example.test",
    status="odbyla",
    rodzaj="stolik",
):
    termin = models.Termin(
        data=reservation_date,
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        nazwisko=nazwisko,
        telefon=telefon,
        email=email,
        liczba_osob=2,
        status=status,
        rodzaj=rodzaj,
        kanal="reczna",
        zadatek=0,
        utworzono_at=datetime(2026, 7, 1, 12, 0),
    )
    db.add(termin)
    db.commit()
    db.refresh(termin)
    return termin


def _path(termin):
    return f"/api/crm/rezerwacje/{termin.id}/profil"


def _profile_payload():
    return {
        "nazwisko": "Anna Kowalska",
        "tagi": ["VIP", "alergik"],
        "vip": True,
        "alergie": "orzechy",
        "dieta": "bez glutenu",
        "preferowana_strefa": "ogród",
        "notatka": "Lubi spokojny stolik",
        "okazja_typ": "urodziny",
        "okazja_data": "05-12",
        "marketing_zgoda": True,
    }


def _edit_stolik(admin_client, termin, *, telefon, email=None):
    return admin_client.put(
        f"/api/rezerwacje-stolik/{termin.id}",
        json={
            "data": str(termin.data),
            "godz_od": "18:00",
            "godz_do": "20:00",
            "stolik_id": None,
            "liczba_osob": 2,
            "nazwisko": termin.nazwisko,
            "telefon": telefon,
            "email": email,
            "notatka": None,
            "zadatek": 0,
        },
    )


def test_admin_put_i_get_uzywaja_wylacznie_reservation_id(admin_client, db):
    termin = _reservation(db)
    response = admin_client.put(_path(termin), json=_profile_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reservation_id"] == termin.id and body["profil_ref"] == termin.id
    assert body["identity"] == {"source": "telefon", "confident": True}
    assert body["profil"]["alergie"] == "orzechy"
    assert body["capabilities"] == {
        "can_edit": True,
        "can_view_sensitive": True,
        "can_view_internal_notes": True,
    }
    assert body["ukryte_pola"] == []
    assert "klucz" not in body and "klucz_hash" not in str(body)
    assert "600100200" not in response.text and "anna@example.test" not in response.text

    readback = admin_client.get(_path(termin))
    assert readback.status_code == 200
    assert readback.json() == body


def test_recepcja_widzi_profil_bez_notatek_i_danych_wrazliwych(admin_client, client, db):
    termin = _reservation(db)
    assert admin_client.put(_path(termin), json=_profile_payload()).status_code == 200

    response = client.get(_path(termin), headers=_headers(_reception()))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profil"] == {
        "nazwisko": "Anna Kowalska",
        "tagi": [],
        "vip": True,
        "alergie": None,
        "dieta": None,
        "preferowana_strefa": "ogród",
        "notatka": None,
        "okazja_typ": "urodziny",
        "okazja_data": "05-12",
        "marketing_zgoda": False,
        "marketing_legacy_unverified": False,
    }
    assert set(body["ukryte_pola"]) == {
        "profil.tagi", "profil.alergie", "profil.dieta", "profil.notatka",
    }
    assert body["capabilities"] == {
        "can_edit": False,
        "can_view_sensitive": False,
        "can_view_internal_notes": False,
    }
    assert "orzechy" not in response.text and "spokojny stolik" not in response.text


def test_prawa_wrazliwe_i_notatki_sa_niezalezne(admin_client, client, db):
    termin = _reservation(db)
    admin_client.put(_path(termin), json=_profile_payload())

    sensitive = _user(
        "crm_sensitive",
        "rezerwacje.operacje",
        "rezerwacje.dane_kontaktowe",
        "rezerwacje.dane_wrazliwe",
    )
    sensitive_body = client.get(_path(termin), headers=_headers(sensitive)).json()
    assert sensitive_body["profil"]["alergie"] == "orzechy"
    assert sensitive_body["profil"]["dieta"] == "bez glutenu"
    assert sensitive_body["profil"]["tagi"] == ["VIP", "alergik"]
    assert sensitive_body["profil"]["notatka"] is None
    assert sensitive_body["ukryte_pola"] == ["profil.notatka"]

    notes = _user(
        "crm_notes",
        "rezerwacje.operacje",
        "rezerwacje.dane_kontaktowe",
        "rezerwacje.notatki_wewnetrzne",
    )
    notes_body = client.get(_path(termin), headers=_headers(notes)).json()
    assert notes_body["profil"]["notatka"] == "Lubi spokojny stolik"
    assert notes_body["profil"]["alergie"] is None
    assert notes_body["profil"]["dieta"] is None
    assert notes_body["profil"]["tagi"] == []


def test_get_wymaga_operacji_i_kontaktu_a_put_pozostaje_admin_only(admin_client, client, db):
    termin = _reservation(db)
    reception = _reception()
    assert client.get(_path(termin), headers=_headers(reception)).status_code == 200
    assert client.put(
        _path(termin), headers=_headers(reception), json=_profile_payload(),
    ).status_code == 403

    operations_only = _user("crm_ops_only", "rezerwacje.operacje")
    contact_only = _user("crm_contact_only", "rezerwacje.dane_kontaktowe")
    assert client.get(_path(termin), headers=_headers(operations_only)).status_code == 403
    assert client.get(_path(termin), headers=_headers(contact_only)).status_code == 403


def test_cofniecie_praw_blokuje_ten_sam_token_natychmiast(client, db):
    termin = _reservation(db)
    user = _user(
        "crm_revoked",
        "rezerwacje.operacje",
        "rezerwacje.dane_kontaktowe",
    )
    headers = _headers(user)
    assert client.get(_path(termin), headers=headers).status_code == 200

    saved = db.get(models.User, user.id)
    saved.uprawnienia_override = {"rezerwacje.operacje": True}
    db.commit()

    assert client.get(_path(termin), headers=headers).status_code == 403


def test_brak_kontaktu_jest_scoped_do_rezerwacji(admin_client, db):
    first = _reservation(db, nazwisko="Nowak", telefon=None, email=None)
    second = _reservation(
        db,
        reservation_date=DAY + timedelta(days=1),
        nazwisko="Nowak",
        telefon=None,
        email=None,
    )
    admin_client.put(_path(first), json={"vip": True})

    first_body = admin_client.get(_path(first)).json()
    second_body = admin_client.get(_path(second)).json()
    assert first_body["identity"] == {"source": "reservation", "confident": False}
    assert second_body["identity"] == {"source": "reservation", "confident": False}
    assert first_body["profil"]["vip"] is True
    assert second_body["profil"] is None
    assert first_body["historia_total"] == second_body["historia_total"] == 1


def test_dopisanie_kontaktu_migruje_profil_fallbacku(admin_client, db):
    termin = _reservation(db, telefon=None, email=None)
    fallback_hash = reservation_fallback_hash(termin.id)
    assert admin_client.put(
        _path(termin),
        json={"vip": True, "tagi": ["staly"], "alergie": "orzechy"},
    ).status_code == 200
    assert db.query(models.ProfilGoscia).filter_by(klucz_hash=fallback_hash).one()

    response = admin_client.put(
        f"/api/rezerwacje-stolik/{termin.id}",
        json={
            "data": str(termin.data),
            "godz_od": "18:00",
            "godz_do": "20:00",
            "stolik_id": None,
            "liczba_osob": 2,
            "nazwisko": "Anna Kowalska",
            "telefon": "600100200",
            "email": None,
            "notatka": None,
            "zadatek": 0,
        },
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    contact_hash = hash_key("+48600100200")
    migrated = db.query(models.ProfilGoscia).filter_by(klucz_hash=contact_hash).one()
    assert migrated.vip is True
    assert migrated.tagi == ["staly"]
    assert migrated.alergie == "orzechy"
    assert db.query(models.ProfilGoscia).filter_by(klucz_hash=fallback_hash).first() is None
    assert admin_client.get(_path(termin)).json()["profil"]["alergie"] == "orzechy"


def test_dopisanie_istniejacego_kontaktu_nie_scala_profili_automatycznie(
    admin_client,
    db,
):
    contact = _reservation(db, telefon="600777888", email=None)
    fallback = _reservation(
        db,
        reservation_date=DAY + timedelta(days=1),
        telefon=None,
        email=None,
    )
    assert admin_client.put(
        _path(contact),
        json={
            "tagi": ["staly"],
            "alergie": "gluten",
            "dieta": "weganska",
            "notatka": "Kontakt preferuje cichy stolik",
            "marketing_zgoda": False,
        },
    ).status_code == 200
    assert admin_client.put(
        _path(fallback),
        json={
            "tagi": ["VIP"],
            "vip": True,
            "alergie": "orzechy",
            "dieta": "inna",
            "notatka": "Fallback prosi o miejsce przy oknie",
            "marketing_zgoda": True,
        },
    ).status_code == 200

    response = admin_client.put(
        f"/api/rezerwacje-stolik/{fallback.id}",
        json={
            "data": str(fallback.data),
            "godz_od": "18:00",
            "godz_do": "20:00",
            "stolik_id": None,
            "liczba_osob": 2,
            "nazwisko": "Anna Kowalska",
            "telefon": "600777888",
            "email": None,
            "notatka": None,
            "zadatek": 0,
        },
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    profiles = db.query(models.ProfilGoscia).all()
    assert len(profiles) == 2
    contact_profile = next(
        profile for profile in profiles
        if profile.klucz_hash == hash_key("+48600777888")
    )
    fallback_profile = next(
        profile for profile in profiles
        if profile.klucz_hash == reservation_fallback_hash(fallback.id)
    )
    assert contact_profile.tagi == ["staly"]
    assert contact_profile.vip is False
    assert contact_profile.alergie == "gluten"
    assert contact_profile.dieta == "weganska"
    assert contact_profile.notatka == "Kontakt preferuje cichy stolik"
    assert fallback_profile.tagi == ["VIP"]
    assert fallback_profile.vip is True
    assert fallback_profile.alergie == "orzechy"
    assert fallback_profile.dieta == "inna"
    assert fallback_profile.notatka == "Fallback prosi o miejsce przy oknie"
    assert db.query(models.CrmGuestMerge).count() == 0


def test_zmiana_jedynego_kontaktu_przenosi_profil_bez_sieroty(admin_client, db):
    termin = _reservation(db, telefon="600111222", email=None)
    assert admin_client.put(
        _path(termin), json={"vip": True, "alergie": "orzechy", "notatka": "Cichy stolik"},
    ).status_code == 200

    response = _edit_stolik(admin_client, termin, telefon="600333444")

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(models.ProfilGoscia).filter_by(
        klucz_hash=hash_key("+48600111222"),
    ).first() is None
    moved = db.query(models.ProfilGoscia).filter_by(
        klucz_hash=hash_key("+48600333444"),
    ).one()
    assert moved.alergie == "orzechy" and moved.notatka == "Cichy stolik"


def test_usuniecie_jedynego_kontaktu_przenosi_profil_do_rezerwacji(admin_client, db):
    termin = _reservation(db, telefon="600111222", email=None)
    assert admin_client.put(
        _path(termin), json={"vip": True, "alergie": "orzechy"},
    ).status_code == 200

    response = _edit_stolik(admin_client, termin, telefon=None, email=None)

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(models.ProfilGoscia).filter_by(
        klucz_hash=hash_key("+48600111222"),
    ).first() is None
    moved = db.query(models.ProfilGoscia).filter_by(
        klucz_hash=reservation_fallback_hash(termin.id),
    ).one()
    assert moved.vip is True and moved.alergie == "orzechy"


def test_zmiana_jednej_z_wielu_wizyt_nie_przenosi_wspolnego_profilu(admin_client, db):
    changed = _reservation(db, telefon="600111222", email=None)
    remaining = _reservation(
        db,
        reservation_date=DAY + timedelta(days=1),
        telefon="600111222",
        email=None,
    )
    assert admin_client.put(
        _path(changed), json={"vip": True, "alergie": "orzechy"},
    ).status_code == 200

    response = _edit_stolik(admin_client, changed, telefon="600333444")

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(models.ProfilGoscia).filter_by(
        klucz_hash=hash_key("+48600111222"),
    ).one().alergie == "orzechy"
    assert admin_client.get(_path(remaining)).json()["profil"]["alergie"] == "orzechy"
    assert admin_client.get(_path(changed)).json()["profil"] is None


def test_delete_usuwa_fallback_zanim_sqlite_ponownie_uzyje_id(admin_client, db):
    first = _reservation(db, nazwisko="Pierwszy", telefon=None, email=None)
    first_id = first.id
    fallback_hash = reservation_fallback_hash(first_id)
    assert admin_client.put(
        _path(first),
        json={"vip": True, "alergie": "orzechy", "notatka": "Tylko pierwszy gosc"},
    ).status_code == 200

    assert admin_client.delete(f"/api/rezerwacje-stolik/{first_id}").status_code == 204
    db.expunge_all()
    assert db.query(models.ProfilGoscia).filter_by(klucz_hash=fallback_hash).first() is None

    second = _reservation(db, nazwisko="Drugi", telefon=None, email=None)
    assert second.id == first_id  # SQLite bez AUTOINCREMENT ponownie uzywa zwolnionego ROWID.
    second_body = admin_client.get(_path(second)).json()
    assert second_body["profil"] is None
    assert "orzechy" not in str(second_body)
    assert "Tylko pierwszy gosc" not in str(second_body)


def test_historia_jest_ograniczona_i_deterministyczna(admin_client, db):
    rows = [
        _reservation(
            db,
            reservation_date=date(2026, 1, 1) + timedelta(days=index),
            telefon="600333444",
            email=None,
        )
        for index in range(55)
    ]

    body = admin_client.get(_path(rows[0])).json()

    assert body["historia_total"] == 55
    assert body["historia_limit"] == 50
    assert len(body["historia"]) == 50
    assert body["historia"][0]["reservation_id"] == rows[-1].id
    assert body["historia"][-1]["reservation_id"] == rows[5].id


def test_missing_i_inny_rodzaj_maja_ten_sam_bezpieczny_404(admin_client, db):
    event = _reservation(db, rodzaj="impreza")
    missing = admin_client.get("/api/crm/rezerwacje/999999/profil")
    wrong_kind = admin_client.get(_path(event))

    assert missing.status_code == wrong_kind.status_code == 404
    assert missing.json() == wrong_kind.json() == {"detail": "Brak rezerwacji."}


def test_adminowy_crm_zachowuje_sale_bez_otwierania_ich_recepcji(admin_client, client, db):
    hall = _reservation(db, rodzaj="sala")

    assert admin_client.get(_path(hall)).status_code == 200
    assert client.get(_path(hall), headers=_headers(_reception())).status_code == 404


def test_sala_migruje_fallback_po_dopisaniu_kontaktu(admin_client, db):
    hall = _reservation(db, rodzaj="sala", telefon=None, email=None)
    fallback_hash = reservation_fallback_hash(hall.id)
    assert admin_client.put(_path(hall), json={"vip": True, "alergie": "orzechy"}).status_code == 200

    response = admin_client.put(
        f"/api/terminy/{hall.id}",
        json={
            "data": str(hall.data),
            "nazwisko": "Anna Kowalska",
            "liczba_osob": 2,
            "telefon": "600222333",
            "sala": "Glowna",
            "notatka": None,
            "status": "odbyla",
            "zadatek": 0,
        },
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(models.ProfilGoscia).filter_by(klucz_hash=fallback_hash).first() is None
    assert db.query(models.ProfilGoscia).filter_by(klucz_hash=hash_key("+48600222333")).one().vip is True
    assert admin_client.get(_path(hall)).json()["profil"]["alergie"] == "orzechy"


def test_delete_sali_usuwa_rezerwacyjny_fallback_profilu(admin_client, db):
    hall = _reservation(db, rodzaj="sala", telefon=None, email=None)
    fallback_hash = reservation_fallback_hash(hall.id)
    assert admin_client.put(
        _path(hall), json={"vip": True, "notatka": "Tylko ta sala"},
    ).status_code == 200

    assert admin_client.delete(f"/api/terminy/{hall.id}").status_code == 204
    db.expunge_all()
    assert db.query(models.ProfilGoscia).filter_by(klucz_hash=fallback_hash).first() is None


def test_polityka_jest_dokladna_i_fail_closed(admin_client, client, db):
    termin = _reservation(db)
    path = _path(termin)
    get_requirement = main.reservation_access.requirement_for("GET", path)
    put_requirement = main.reservation_access.requirement_for("PUT", path)
    unknown = main.reservation_access.requirement_for("GET", f"{path}/przyszla-akcja")

    assert get_requirement.all_of == (
        "rezerwacje.operacje", "rezerwacje.dane_kontaktowe",
    )
    assert put_requirement.admin_only is True
    assert unknown.admin_only is True
    assert client.get(
        f"{path}/przyszla-akcja", headers=_headers(_reception()),
    ).status_code == 403


def test_handoff_respektuje_modul_i_read_only_subskrypcji(admin_client, db):
    termin = _reservation(db)
    assert admin_client.put(
        "/api/lokal/config", json={"modul_rezerwacje": False},
    ).status_code == 200
    assert admin_client.get(_path(termin)).status_code == 403
    assert admin_client.get("/api/crm/goscie").status_code == 403

    assert admin_client.put(
        "/api/lokal/config", json={"modul_rezerwacje": True},
    ).status_code == 200
    assert admin_client.put(
        "/api/subskrypcja", json={"tier": "premium", "status": "wygasla"},
    ).status_code == 200
    assert admin_client.get(_path(termin)).status_code == 200


def test_przestrzenie_pii_maja_no_store_i_vary_authorization(admin_client, db):
    termin = _reservation(db)
    response = admin_client.get(
        _path(termin), headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    vary = {part.strip().casefold() for part in response.headers["vary"].split(",")}
    assert {"authorization", "origin"} <= vary

    detail = admin_client.get(f"/api/rezerwacje-stolik/{termin.id}")
    host = admin_client.get(f"/api/host/kolejka?data={DAY}")
    waitlist = admin_client.get(f"/api/lista-oczekujacych?data={DAY}")
    events = admin_client.get(f"/api/terminy?start={DAY}&end={DAY}")
    assert all(
        item.headers.get("cache-control") == "private, no-store"
        for item in (detail, host, waitlist, events)
    )

    unrelated = admin_client.get("/api/crm-zly")
    assert unrelated.headers.get("cache-control") is None
