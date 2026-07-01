"""Giełda wymiany zmian (roadmapa v1.5) — /api/me/gielda/* (pracownik) + /api/gielda/* (manager).

Przepływ: pracownik wystawia swój przyszły przydział → wykwalifikowany kolega przejmuje
→ manager akceptuje → przydział przepięty. Odrzucenie cofa ofertę na giełdę.
"""

from datetime import date, time, timedelta

import factories
import models

PRZYSZLOSC = date.today() + timedelta(days=3)
GODZ = time(10, 0)


def _stan_z_dwoma(db):
    """Stanowisko + dwaj wykwalifikowani pracownicy (A=właściciel zmiany, B=chętny) + przydział A."""
    stan = factories.StanowiskoFactory(nazwa="Obsługa sali")
    a = factories.PracownikFactory(imie="Ala", nazwisko="Kowalska")
    b = factories.PracownikFactory(imie="Bartek", nazwisko="Nowak")
    a.kwalifikacje = [stan]
    b.kwalifikacje = [stan]
    factories.Session.commit()
    przydzial = factories.PrzydzialFactory(pracownik=a, stanowisko=stan, data=PRZYSZLOSC, godz_od=GODZ)
    return stan, a, b, przydzial


def test_wystaw_oferte(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    r = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id, "powod": "wesele"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "otwarta"
    assert o["wystawiajacy_id"] == a.id
    assert o["stanowisko"] == "Obsługa sali"
    assert db.query(models.OfertaZmiany).count() == 1


def test_nie_moge_wystawic_cudzej_zmiany(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    cb, _ = make_employee_client(b)                       # B wystawia zmianę A
    r = cb.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id})
    assert r.status_code == 403


def test_nie_moge_wystawic_minionej_zmiany(make_employee_client, db):
    stan = factories.StanowiskoFactory(nazwa="Bar")
    a = factories.PracownikFactory()
    a.kwalifikacje = [stan]; factories.Session.commit()
    miniona = factories.PrzydzialFactory(pracownik=a, stanowisko=stan,
                                         data=date.today() - timedelta(days=1), godz_od=GODZ)
    ca, _ = make_employee_client(a)
    r = ca.post("/api/me/gielda/oferty", json={"przydzial_id": miniona.id})
    assert r.status_code == 400


def test_podwojne_wystawienie_konflikt(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    assert ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).status_code == 201
    r = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id})
    assert r.status_code == 409


def test_przejecie_wymaga_kwalifikacji(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    c = factories.PracownikFactory()                     # C bez kwalifikacji na stan
    ca, _ = make_employee_client(a)
    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]
    cc, _ = make_employee_client(c)
    r = cc.post(f"/api/me/gielda/oferty/{oid}/przejmij")
    assert r.status_code == 403


def test_nie_moge_przejac_wlasnej(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]
    r = ca.post(f"/api/me/gielda/oferty/{oid}/przejmij")
    assert r.status_code == 400


def test_pelny_przeplyw_przejecie_i_akceptacja(make_employee_client, admin_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    cb, _ = make_employee_client(b)
    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]

    r = cb.post(f"/api/me/gielda/oferty/{oid}/przejmij")
    assert r.status_code == 200 and r.json()["status"] == "zajeta"
    assert r.json()["przejmujacy_id"] == b.id

    r = admin_client.post(f"/api/gielda/oferty/{oid}/akceptuj")
    assert r.status_code == 200 and r.json()["status"] == "zaakceptowana"
    # Przydział został przepięty na B.
    db.expire_all()
    assert db.get(models.PrzydzialZmiany, przydzial.id).pracownik_id == b.id


def test_odrzucenie_wraca_na_gielde(make_employee_client, admin_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    cb, _ = make_employee_client(b)
    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]
    cb.post(f"/api/me/gielda/oferty/{oid}/przejmij")

    r = admin_client.post(f"/api/gielda/oferty/{oid}/odrzuc")
    assert r.status_code == 200
    assert r.json()["status"] == "otwarta"
    assert r.json()["przejmujacy_id"] is None
    # Przydział NIE został przepięty.
    db.expire_all()
    assert db.get(models.PrzydzialZmiany, przydzial.id).pracownik_id == a.id


def test_anulowanie_tylko_przez_wystawiajacego(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    cb, _ = make_employee_client(b)
    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]
    assert cb.post(f"/api/me/gielda/oferty/{oid}/anuluj").status_code == 403   # B nie może
    r = ca.post(f"/api/me/gielda/oferty/{oid}/anuluj")                          # A może
    assert r.status_code == 200 and r.json()["status"] == "anulowana"


def test_widok_moje_oferty(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    cb, _ = make_employee_client(b)
    ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id})

    widok_b = cb.get("/api/me/gielda/oferty").json()
    assert len(widok_b["dostepne"]) == 1                 # B jest wykwalifikowany → widzi ofertę
    assert widok_b["dostepne"][0]["wystawiajacy"] == "Ala Kowalska"
    assert widok_b["moje"] == []

    widok_a = ca.get("/api/me/gielda/oferty").json()
    assert widok_a["dostepne"] == []                     # nie widzę własnej w „dostępne"
    assert len(widok_a["moje"]) == 1


def test_podwojne_obsadzenie_blokuje_przejecie(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    # B ma już własną zmianę tego samego dnia o tej samej godzinie (kolizja).
    factories.PrzydzialFactory(pracownik=b, stanowisko=stan, data=PRZYSZLOSC, godz_od=GODZ)
    ca, _ = make_employee_client(a)
    cb, _ = make_employee_client(b)
    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]
    r = cb.post(f"/api/me/gielda/oferty/{oid}/przejmij")
    assert r.status_code == 409


def test_admin_lista_i_filtr(make_employee_client, admin_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id})
    assert len(admin_client.get("/api/gielda/oferty").json()) == 1
    assert len(admin_client.get("/api/gielda/oferty?status_filtr=otwarta").json()) == 1
    assert admin_client.get("/api/gielda/oferty?status_filtr=zaakceptowana").json() == []


def test_pracownik_nie_ma_dostepu_do_endpointow_managera(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    assert ca.get("/api/gielda/oferty").status_code == 403


def test_moje_przydzialy_do_wystawienia(make_employee_client, db):
    stan, a, b, przydzial = _stan_z_dwoma(db)
    # Miniona zmiana A — nie powinna być kandydatem.
    factories.PrzydzialFactory(pracownik=a, stanowisko=stan,
                               data=date.today() - timedelta(days=2), godz_od=GODZ)
    ca, _ = make_employee_client(a)
    lista = ca.get("/api/me/gielda/przydzialy").json()
    assert len(lista) == 1                                  # tylko przyszła zmiana
    assert lista[0]["przydzial_id"] == przydzial.id
    assert lista[0]["wystawiony"] is False
    # Po wystawieniu flaga się zmienia.
    ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id})
    assert ca.get("/api/me/gielda/przydzialy").json()[0]["wystawiony"] is True


def test_gielda_maskuje_nazwe_klienta_imprezy_pracownikowi(make_employee_client, admin_client, db):
    """Prywatność (regresja): rewir imprezy „IMPREZA: {klient} ({sala})" NIE może ujawnić
    pracownikowi nazwiska klienta na giełdzie — tak jak w /api/me/grafik. Manager (admin) widzi surowy."""
    stan = factories.StanowiskoFactory(nazwa="Kelner")
    a = factories.PracownikFactory(imie="Ala", nazwisko="Kowalska")
    b = factories.PracownikFactory(imie="Bartek", nazwisko="Nowak")
    a.kwalifikacje = [stan]; b.kwalifikacje = [stan]; factories.Session.commit()
    przydzial = factories.PrzydzialFactory(pracownik=a, stanowisko=stan, data=PRZYSZLOSC,
                                           godz_od=GODZ, rewir="IMPREZA: Nowakowscy (Sala Kominkowa)")
    ca, _ = make_employee_client(a)
    cb, _ = make_employee_client(b)

    # A widzi swój przydział do wystawienia — bez nazwiska klienta.
    moje_przydz = ca.get("/api/me/gielda/przydzialy").json()
    assert moje_przydz[0]["rewir"] == "Impreza (Sala Kominkowa)"
    assert "Nowakowscy" not in str(moje_przydz)

    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]
    # A wystawił → w jego „moje" rewir zamaskowany.
    widok_a = ca.get("/api/me/gielda/oferty").json()
    assert widok_a["moje"][0]["rewir"] == "Impreza (Sala Kominkowa)"
    # B (chętny) w „dostepne" też nie widzi klienta.
    widok_b = cb.get("/api/me/gielda/oferty").json()
    assert widok_b["dostepne"][0]["rewir"] == "Impreza (Sala Kominkowa)"
    assert "Nowakowscy" not in str(widok_b)

    # Manager (admin) — surowy rewir z nazwiskiem klienta (ma pełny wgląd w grafik).
    widok_admin = admin_client.get("/api/gielda/oferty").json()
    assert widok_admin[0]["rewir"] == "IMPREZA: Nowakowscy (Sala Kominkowa)"


def test_push_na_zdarzeniach_gieldy(make_employee_client, admin_client, monkeypatch, db):
    import push
    zdarzenia = []
    monkeypatch.setattr(push, "wyslij_push_do_pracownika",
                        lambda *a, **k: zdarzenia.append(("prac", a[2])) or 0)
    monkeypatch.setattr(push, "wyslij_push_do_adminow",
                        lambda *a, **k: zdarzenia.append(("admin", a[1])) or 0)

    stan, a, b, przydzial = _stan_z_dwoma(db)
    ca, _ = make_employee_client(a)
    cb, _ = make_employee_client(b)

    # Wystawienie → push do wykwalifikowanego kolegi (b), nie do wystawiającego (a).
    oid = ca.post("/api/me/gielda/oferty", json={"przydzial_id": przydzial.id}).json()["id"]
    assert any(e[0] == "prac" for e in zdarzenia)
    zdarzenia.clear()

    # Przejęcie → push do adminów + do wystawiającego.
    cb.post(f"/api/me/gielda/oferty/{oid}/przejmij")
    assert any(e[0] == "admin" for e in zdarzenia)
    assert any(e[0] == "prac" for e in zdarzenia)
    zdarzenia.clear()

    # Akceptacja → push do przejmującego i wystawiającego.
    admin_client.post(f"/api/gielda/oferty/{oid}/akceptuj")
    assert sum(1 for e in zdarzenia if e[0] == "prac") >= 1
