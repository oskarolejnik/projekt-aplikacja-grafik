"""Status integracji (/api/integracje/status) — secret store / foundation."""


def test_integracje_status(admin_client):
    r = admin_client.get("/api/integracje/status")
    assert r.status_code == 200
    items = r.json()["integracje"]
    klucze = {i["klucz"] for i in items}
    assert {"push", "pos", "email", "sms", "platnosci"} <= klucze
    # conftest ustawia RCP_INGEST_TOKEN -> integracja POS skonfigurowana
    assert next(i for i in items if i["klucz"] == "pos")["skonfigurowane"] is True
    # brak sekretów SMTP -> e-mail niezskonfigurowany (integracja wyłączona, nie crash)
    assert next(i for i in items if i["klucz"] == "email")["skonfigurowane"] is False
    # nie ujawniamy wartości sekretów — tylko nazwy zmiennych w 'wymaga'
    for i in items:
        assert isinstance(i["wymaga"], list) and all(isinstance(k, str) for k in i["wymaga"])


def test_integracje_status_wymaga_logowania(client):
    assert client.get("/api/integracje/status").status_code == 401
