"""CRM gości (/api/crm/goscie) — agregacja historii + scoring no-show (roadmapa v1.5)."""

import datetime as dt

import models
from routers import crm


def _rez(db, data, telefon="600100200", nazwisko="Jan Kowalski", status="odbyla"):
    t = models.Termin(rodzaj="stolik", kanal="online", nazwisko=nazwisko, telefon=telefon,
                      data=data, status=status, utworzono_at=dt.datetime(2026, 7, 1))
    db.add(t); db.commit()
    return t


def test_pusta_baza_pusta_lista(admin_client):
    assert admin_client.get("/api/crm/goscie").json() == []


def test_agregacja_i_scoring_no_show(admin_client, db):
    # Ten sam gość (telefon): 3 rezerwacje — 2 odbyte, 1 no-show.
    for i, st in enumerate(["odbyla", "odbyla", "no_show"]):
        _rez(db, dt.date(2026, 7, 1 + i), status=st)
    b = admin_client.get("/api/crm/goscie").json()
    assert len(b) == 1
    g = b[0]
    assert g["wizyt"] == 3 and g["odbyte"] == 2 and g["no_show"] == 1
    assert g["no_show_proc"] == 33
    assert g["ryzyko"] == "wysokie"          # total>=3 i no_show_proc>=30
    assert g["vip"] is False                 # odbyte 2 < 5
    assert g["nazwisko"] == "Jan Kowalski"
    assert g["ostatnia_data"] == "2026-07-03"
    assert g["profil_ref"]
    assert g["identity"] == {"source": "telefon", "confident": True}
    assert "klucz" not in g and "klucz_hash" not in g


def test_no_show_liczony_tylko_po_zamknietych_wizytach(admin_client, db):
    """Regresja: współczynnik no-show NIE może być rozwadniany przyszłymi/oczekującymi rezerwacjami.
    Gość: 1 odbyla + 2 no_show (zamknięte) + 4 potwierdzona (przyszłe). Poprawnie: 2/3=67% → wysokie.
    Bug (mianownik = wszystkie 7 wizyt): 2/7=29% → błędnie „srednie"."""
    for i, st in enumerate(["odbyla", "no_show", "no_show", "potwierdzona", "potwierdzona", "potwierdzona", "potwierdzona"]):
        _rez(db, dt.date(2026, 7, 1 + i), status=st)
    g = admin_client.get("/api/crm/goscie").json()[0]
    assert g["wizyt"] == 7 and g["aktywne"] == 4 and g["no_show"] == 2
    assert g["no_show_proc"] == 67          # 2 / (1+2+0) zamknięte, nie 2/7
    assert g["ryzyko"] == "wysokie"


def test_rozni_goscie_osobne_wpisy(admin_client, db):
    _rez(db, dt.date(2026, 7, 1), telefon="600100200")
    _rez(db, dt.date(2026, 7, 2), telefon="700200300")
    assert len(admin_client.get("/api/crm/goscie").json()) == 2


def test_min_wizyt_filtruje(admin_client, db):
    _rez(db, dt.date(2026, 7, 1), telefon="600100200")                 # 1 wizyta
    _rez(db, dt.date(2026, 7, 2), telefon="700200300")                 # 2 wizyty
    _rez(db, dt.date(2026, 7, 3), telefon="700200300")
    b = admin_client.get("/api/crm/goscie?min_wizyt=2").json()
    assert len(b) == 1 and b[0]["telefon"] == "700200300"


def test_vip_po_pieciu_wizytach(admin_client, db):
    for i in range(5):
        _rez(db, dt.date(2026, 7, 1 + i), status="odbyla")
    g = admin_client.get("/api/crm/goscie").json()[0]
    assert g["vip"] is True and g["odbyte"] == 5 and g["ryzyko"] == "niskie"


def test_grupowanie_po_emailu_gdy_brak_telefonu(admin_client, db):
    _rez(db, dt.date(2026, 7, 1), telefon=None, nazwisko="Anna")
    # bez telefonu grupuje po e-mailu — ustaw e-mail ręcznie
    t = db.query(models.Termin).first(); t.email = "anna@example.com"; db.commit()
    b = admin_client.get("/api/crm/goscie").json()
    assert len(b) == 1 and b[0]["profil_ref"] == t.id
    assert b[0]["identity"] == {"source": "email", "confident": True}
    assert "klucz" not in b[0]


def test_brak_kontaktu_nie_grupuje_obcych_gosci_po_nazwisku(admin_client, db):
    first = _rez(db, dt.date(2026, 7, 1), telefon=None, nazwisko="Nowak")
    second = _rez(db, dt.date(2026, 7, 2), telefon=None, nazwisko="Nowak")

    body = admin_client.get("/api/crm/goscie").json()

    assert {row["profil_ref"] for row in body} == {first.id, second.id}
    assert all(row["wizyt"] == 1 for row in body)
    assert all(row["identity"] == {"source": "reservation", "confident": False} for row in body)
    assert all("klucz" not in row and "klucz_hash" not in row for row in body)
    assert crm._klucz_crm(first) == f"reservation:{first.id}"
    assert crm._klucz_crm(second) == f"reservation:{second.id}"


def test_crm_tylko_admin(client):
    tok = client.post("/api/auth/register",
                      json={"email": "kelnerx@lokal.pl", "haslo": "Haslo123!", "imie": "A", "nazwisko": "B"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {tok}"})
    assert client.get("/api/crm/goscie").status_code == 403
