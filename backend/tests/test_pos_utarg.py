"""Tor A integracji POS: POST /api/pos/utarg-dnia + /api/pos/heartbeat.
Autoryzacja podwójna (token agenta LUB JWT admina), upsert idempotentny,
zasilanie stoliki_historia (prognoza) bez nadpisywania danych z agenta Gastro."""

from datetime import date, timedelta

import models

TOKEN = {"X-RCP-Token": "test-rcp-token"}   # conftest wymusza RCP_INGEST_TOKEN


def _paczka(zrodlo="reczny", **dzien):
    d = {"data": str(date.today()), "netto": 1200.50, **dzien}
    return {"zrodlo": zrodlo, "dni": [d]}


def test_utarg_wymaga_autoryzacji(client):
    assert client.post("/api/pos/utarg-dnia", json=_paczka()).status_code == 401
    assert client.post("/api/pos/utarg-dnia", json=_paczka(),
                       headers={"X-RCP-Token": "zly"}).status_code == 401
    assert client.post("/api/pos/heartbeat", json={"driver": "x"}).status_code == 401


def test_utarg_token_agenta_i_upsert(client, db):
    r = client.post("/api/pos/utarg-dnia", json=_paczka("gastro_mssql"), headers=TOKEN)
    assert r.status_code == 200 and r.json()["zapisane"] == 1
    # idempotencja: ten sam dzień/źródło nadpisuje, nie dubluje
    r2 = client.post("/api/pos/utarg-dnia",
                     json=_paczka("gastro_mssql", netto=999.0), headers=TOKEN)
    assert r2.status_code == 200
    rows = db.query(models.UtargDnia).filter_by(zrodlo="gastro_mssql").all()
    assert len(rows) == 1 and rows[0].netto == 999.0


def test_utarg_admin_jwt_i_zrodla_rozlaczne(admin_client, db):
    assert admin_client.post("/api/pos/utarg-dnia", json=_paczka("reczny")).status_code == 200
    assert admin_client.post("/api/pos/utarg-dnia", json=_paczka("csv")).status_code == 200
    assert db.query(models.UtargDnia).count() == 2   # osobne wiersze per źródło

    dz = str(date.today())
    lista = admin_client.get(f"/api/pos/utarg-dnia?start={dz}&end={dz}").json()["dni"]
    assert {x["zrodlo"] for x in lista} == {"reczny", "csv"}


def test_utarg_walidacja(admin_client):
    zle = {"zrodlo": "reczny", "dni": [{"data": str(date.today()), "netto": -5}]}
    assert admin_client.post("/api/pos/utarg-dnia", json=zle).status_code == 422
    assert admin_client.post("/api/pos/utarg-dnia", json={"zrodlo": "reczny", "dni": []}).status_code == 422


def test_liczba_rachunkow_zasila_prognoze_bez_nadpisu(admin_client, db):
    d1, d2 = date.today() - timedelta(days=2), date.today() - timedelta(days=1)
    # d2 ma już bogatsze dane z agenta Gastro — ręczny wpis NIE nadpisuje
    db.add(models.StolikiHistoria(data=d2, liczba=77)); db.commit()

    body = {"zrodlo": "reczny", "dni": [
        {"data": str(d1), "netto": 100, "liczba_rachunkow": 40},
        {"data": str(d2), "netto": 200, "liczba_rachunkow": 5},
    ]}
    assert admin_client.post("/api/pos/utarg-dnia", json=body).status_code == 200
    assert db.get(models.StolikiHistoria, d1).liczba == 40   # brakujący dzień uzupełniony
    assert db.get(models.StolikiHistoria, d2).liczba == 77   # dane agenta nietknięte


def test_heartbeat_upsert_i_status(client, admin_client, db):
    hb = {"driver": "gastro_mssql", "wersja": "1.4.0", "capabilities": ["utarg", "odbicia"],
          "bledy": ["timeout bazy 12:00"]}
    assert client.post("/api/pos/heartbeat", json=hb, headers=TOKEN).status_code == 200
    assert client.post("/api/pos/heartbeat", json={**hb, "wersja": "1.4.1"},
                       headers=TOKEN).status_code == 200
    assert db.query(models.AgentStatus).count() == 1
    assert db.query(models.AgentStatus).first().wersja == "1.4.1"

    s = admin_client.get("/api/pos/status")
    assert s.status_code == 200
    body = s.json()
    assert body["agenty"][0]["driver"] == "gastro_mssql"
    assert body["agenty"][0]["bledy"] == ["timeout bazy 12:00"]


def test_odczyty_tylko_admin(client):
    from fastapi.testclient import TestClient
    import main
    # GOTCHA: admin_client mutuje nagłówki współdzielonego clienta — anonim przez świeży TestClient
    with TestClient(main.app) as anon:
        dz = str(date.today())
        assert anon.get(f"/api/pos/utarg-dnia?start={dz}&end={dz}").status_code == 401
        assert anon.get("/api/pos/status").status_code == 401


def test_token_z_panelu_autoryzuje_ingest(admin_client, db, monkeypatch):
    # bez env-tokena zostaje wyłącznie token z panelu (hash w konfiguracji lokalu)
    monkeypatch.delenv("RCP_INGEST_TOKEN", raising=False)

    r = admin_client.post("/api/pos/token")
    assert r.status_code == 201
    token = r.json()["token"]
    assert len(token) > 30
    cfg = db.query(models.LokalConfig).get(1)
    db.refresh(cfg)
    assert cfg.pos_token_hash and token not in cfg.pos_token_hash   # w bazie tylko skrót

    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as agent:
        # token z panelu działa i w X-RCP-Token, i w Bearer — także na legacy /api/rcp/ingest
        assert agent.post("/api/pos/utarg-dnia", json=_paczka("gastro_mssql"),
                          headers={"X-RCP-Token": token}).status_code == 200
        assert agent.post("/api/pos/heartbeat", json={"driver": "gastro_mssql"},
                          headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert agent.post("/api/rcp/ingest", json={"odbicia": []},
                          headers={"X-RCP-Token": token}).status_code == 200
        assert agent.post("/api/pos/utarg-dnia", json=_paczka(),
                          headers={"X-RCP-Token": "zly-token"}).status_code == 401

    # status raportuje aktywny token; unieważnienie odcina agenta
    assert admin_client.get("/api/pos/status").json()["token_aktywny"] is True
    assert admin_client.delete("/api/pos/token").status_code == 204
    with TestClient(main.app) as agent:
        assert agent.post("/api/pos/utarg-dnia", json=_paczka("gastro_mssql"),
                          headers={"X-RCP-Token": token}).status_code == 401
    assert admin_client.get("/api/pos/status").json()["token_aktywny"] is False


def test_env_token_dziala_rownolegle_z_tokenem_panelu(client, admin_client):
    # conftest wymusza RCP_INGEST_TOKEN=test-rcp-token; token z panelu go NIE wyłącza
    admin_client.post("/api/pos/token")
    assert client.post("/api/pos/utarg-dnia", json=_paczka("gastro_mssql"),
                       headers=TOKEN).status_code == 200


def test_token_tylko_admin(client):
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as anon:
        assert anon.post("/api/pos/token").status_code == 401
        assert anon.delete("/api/pos/token").status_code == 401
