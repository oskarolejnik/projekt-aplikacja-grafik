"""Mapowanie pracowników POS→Lokalo (POS faza 2). Jawna mapa (zrodlo, pos_id)→pracownik
ma pierwszeństwo nad dopasowaniem po imieniu; nierozpoznane tożsamości wypływają w kreatorze,
a zapis mapowania domyka historyczne odbicia (godziny wchodzą do wypłaty)."""

import factories
import models

TOKEN = {"X-RCP-Token": "test-rcp-token"}   # conftest wymusza RCP_INGEST_TOKEN


def _odbicie(rcp_id, nazwa, pos_id=None, d="2026-07-01"):
    o = {"rcp_id": rcp_id, "imie_nazwisko": nazwa, "data": d,
         "wejscie": f"{d} 10:00:00", "wyjscie": f"{d} 18:00:00"}
    if pos_id is not None:
        o["pos_pracownik_id"] = pos_id
    return o


def test_ingest_mapa_jawna_wygrywa_z_imieniem(client, admin_client, db):
    # dwóch pracowników o mylnie podobnych nazwach — dopasowanie po imieniu bywa kruche
    anna = factories.PracownikFactory(imie="Anna", nazwisko="Nowak")
    ania = factories.PracownikFactory(imie="Ania", nazwisko="Nowakowska")
    db.commit()
    # jawne mapowanie: pos_id 'U7' w źródle gastro_mssql → Anna
    admin_client.put("/api/pos/mapowanie", json={
        "zrodlo": "gastro_mssql", "pos_id": "U7", "pracownik_id": anna.id, "pos_nazwa": "A. Nowak"})

    r = client.post("/api/rcp/ingest", headers=TOKEN, json={
        "zrodlo": "gastro_mssql",
        "odbicia": [_odbicie("r1", "Ania Nowakowska", pos_id="U7")]})   # imię wskazuje Anię…
    assert r.status_code == 200
    rec = db.query(models.OdbicieRcp).filter_by(rcp_id="r1").first()
    assert rec.pracownik_id == anna.id                                  # …ale mapa jawna wygrywa


def test_ingest_fallback_na_imie_bez_mapy(client, db):
    p = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    db.commit()
    client.post("/api/rcp/ingest", headers=TOKEN, json={
        "zrodlo": "gastro_mssql", "odbicia": [_odbicie("r2", "Jan Kowalski", pos_id="U9")]})
    rec = db.query(models.OdbicieRcp).filter_by(rcp_id="r2").first()
    assert rec.pracownik_id == p.id                                     # dopasowanie po imieniu
    assert rec.pos_pracownik_id == "U9" and rec.zrodlo == "gastro_mssql"


def test_nierozpoznani_i_domkniecie_odbic(client, admin_client, db):
    p = factories.PracownikFactory(imie="Ewa", nazwisko="Zielona")
    db.commit()
    # odbicie tożsamości, której NIE ma wśród pracowników po imieniu
    client.post("/api/rcp/ingest", headers=TOKEN, json={
        "zrodlo": "soga_firebird", "odbicia": [_odbicie("r3", "PRACOWNIK 42", pos_id="42")]})
    rec = db.query(models.OdbicieRcp).filter_by(rcp_id="r3").first()
    assert rec.pracownik_id is None                                     # nierozpoznany

    stan = admin_client.get("/api/pos/mapowanie").json()
    assert any(n["pos_id"] == "42" and n["zrodlo"] == "soga_firebird"
               for n in stan["nierozpoznani"])

    # przypisanie mapowania domyka historyczne odbicie
    admin_client.put("/api/pos/mapowanie", json={
        "zrodlo": "soga_firebird", "pos_id": "42", "pracownik_id": p.id})
    db.refresh(rec)
    assert rec.pracownik_id == p.id
    stan2 = admin_client.get("/api/pos/mapowanie").json()
    assert not stan2["nierozpoznani"]                                   # już rozpoznany
    assert any(m["pos_id"] == "42" for m in stan2["mapowania"])


def test_mapowanie_crud_i_walidacja(admin_client, db):
    p = factories.PracownikFactory(imie="Test", nazwisko="Osoba"); db.commit()
    # nieistniejący pracownik → 404
    assert admin_client.put("/api/pos/mapowanie", json={
        "zrodlo": "x2_postgres", "pos_id": "1", "pracownik_id": 99999}).status_code == 404
    admin_client.put("/api/pos/mapowanie", json={
        "zrodlo": "x2_postgres", "pos_id": "1", "pracownik_id": p.id})
    mid = admin_client.get("/api/pos/mapowanie").json()["mapowania"][0]["id"]
    assert admin_client.delete(f"/api/pos/mapowanie/{mid}").status_code == 204
    assert admin_client.get("/api/pos/mapowanie").json()["mapowania"] == []


def test_mapowanie_tylko_admin(client):
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as anon:
        assert anon.get("/api/pos/mapowanie").status_code == 401
        assert anon.put("/api/pos/mapowanie", json={
            "zrodlo": "x", "pos_id": "1", "pracownik_id": 1}).status_code == 401
