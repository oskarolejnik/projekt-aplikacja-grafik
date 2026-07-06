"""Monetyzacja Faza 3: generator FA(3) + wystawianie faktur + endpointy (tryb stub KSeF)."""

import xml.etree.ElementTree as ET
from datetime import date

import cennik
import faktury
import ksef
import models
from deps import get_lokal_config, get_subskrypcja

NS = ksef.NS


def _t(root, tag):
    """Pierwszy element o nazwie tag (bez względu na głębokość)."""
    return root.find(f".//{{{NS}}}{tag}")


def test_generator_fa3_ma_kluczowe_pola():
    xml = ksef.generuj_fa3(
        numer="LOK/2026/07/0001", data_wystawienia=date(2026, 7, 1),
        okres_od=date(2026, 7, 1), okres_do=date(2026, 7, 31),
        opis="Abonament Lokalo Pro — okres 2026-07-01–2026-07-31",
        netto=199.0, vat=45.77, brutto=244.77, stawka_vat_proc=23,
        nabywca={"nip": "1234567890", "nazwa": "Bar Testowy sp. z o.o.",
                 "adres_l1": "ul. Smaczna 5", "adres_l2": "00-123 Warszawa"})
    root = ET.fromstring(xml)
    assert _t(root, "WariantFormularza").text == "3"
    assert _t(root, "P_2").text == "LOK/2026/07/0001"
    assert _t(root, "P_15").text == "244.77"
    assert _t(root, "P_6_Od").text == "2026-07-01" and _t(root, "P_6_Do").text == "2026-07-31"
    # nabywca (Podmiot2) NIP obecny
    nipy = [e.text for e in root.iter(f"{{{NS}}}NIP")]
    assert "1234567890" in nipy
    assert _t(root, "P_7").text.startswith("Abonament Lokalo Pro")


def test_wyslij_stub_mockuje_ksef_number():
    n, upo, status = ksef.wyslij("<x/>", "LOK/2026/07/0001")
    assert status == "przyjeta" and n.startswith("TEST-") and upo.startswith("UPO-STUB-")


def test_numeracja_sekwencyjna(admin_client, db):
    dzis = date.today()
    n1 = faktury._nastepny_numer(db, dzis)
    assert n1.endswith("/0001")
    db.add(models.Faktura(numer=n1, netto=0, vat=0, brutto=0, status_ksef="roboczy"))
    db.commit()
    assert faktury._nastepny_numer(db, dzis).endswith("/0002")


def test_wystaw_z_platnosci_idempotentnie(admin_client, db):
    # dane firmowe nabywcy
    cfg = get_lokal_config(db)
    cfg.faktura_nip = "1234567890"; cfg.faktura_nazwa = "Bar Test sp. z o.o."; db.commit()
    p = models.PlatnoscSubskrypcji(rodzaj="abonament", tier="pro", netto=199.0,
                                   vat=cennik.vat(199), brutto=cennik.brutto(199),
                                   okres_od=date(2026, 7, 1), okres_do=date(2026, 7, 31), status="oplacona")
    db.add(p); db.commit(); db.refresh(p)

    f = faktury.wystaw_z_platnosci(db, p)
    assert f.numer.startswith("LOK/") and f.brutto == cennik.brutto(199)
    assert f.nabywca_nip == "1234567890" and f.ksef_number.startswith("TEST-")
    assert f.status_ksef == "przyjeta" and "<" in f.xml
    # idempotencja: druga próba zwraca tę samą fakturę
    assert faktury.wystaw_z_platnosci(db, p).id == f.id


def test_oplacenie_wystawia_fakture_endpointem(admin_client, db):
    cfg = get_lokal_config(db); cfg.faktura_nip = "9876543210"; db.commit()
    s = get_subskrypcja(db); s.tier = "pro"; s.status = "aktywna"; db.commit()

    p = admin_client.post("/api/subskrypcja/odnow").json()
    admin_client.post(f"/api/subskrypcja/platnosc/{p['external_id']}/oplac")

    lista = admin_client.get("/api/faktury").json()
    assert lista["tryb_ksef"] == "stub" and len(lista["faktury"]) == 1
    fak = lista["faktury"][0]
    assert fak["nabywca_nip"] == "9876543210" and fak["status_ksef"] == "przyjeta"
    # pobranie XML
    xml = admin_client.get(f"/api/faktury/{fak['id']}/xml")
    assert xml.status_code == 200 and xml.headers["content-type"].startswith("application/xml")
    assert b"Faktura" in xml.content


def test_faktury_tylko_admin(client):
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as anon:
        assert anon.get("/api/faktury").status_code == 401
