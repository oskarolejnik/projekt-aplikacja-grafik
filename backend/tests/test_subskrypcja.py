"""Subskrypcja/licencja instancji + degradacja READ_ONLY (Rec#2 audytu)."""


def test_domyslnie_aktywna(admin_client):
    admin_client.put("/api/subskrypcja", json={"tier": "free"})   # baseline planu darmowego
    s = admin_client.get("/api/subskrypcja").json()
    assert s["status"] == "aktywna"
    assert s["tier"] == "free"
    assert s["aktywna"] is True
    # nowe pola tier-gatingu: Free odblokowuje tylko rdzeń (brak płatnych modułów)
    assert s["dostepne_moduly"] == [] and s["trial_dni"] is None


def test_aktywna_pozwala_zapisywac(admin_client):
    r = admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    assert r.status_code in (200, 201), r.text


def test_wygasla_blokuje_zapis_ale_odczyt_dziala(admin_client):
    admin_client.put("/api/subskrypcja", json={"status": "wygasla"})
    # Zapis zablokowany (402 Payment Required)...
    assert admin_client.post("/api/stoliki", json={"nazwa": "S2", "pojemnosc": 2}).status_code == 402
    # ...ale odczyt nadal działa (tryb tylko-odczyt).
    assert admin_client.get("/api/stoliki").status_code == 200


def test_zawieszona_blokuje_zapis(admin_client):
    admin_client.put("/api/subskrypcja", json={"status": "zawieszona"})
    assert admin_client.get("/api/subskrypcja").json()["aktywna"] is False
    assert admin_client.post("/api/stoliki", json={"nazwa": "S3", "pojemnosc": 2}).status_code == 402


def test_data_do_przeszla_blokuje(admin_client):
    admin_client.put("/api/subskrypcja", json={"status": "aktywna", "data_do": "2000-01-01"})
    assert admin_client.get("/api/subskrypcja").json()["aktywna"] is False
    assert admin_client.post("/api/stoliki", json={"nazwa": "S4", "pojemnosc": 2}).status_code == 402


def test_data_do_przyszla_nie_blokuje(admin_client):
    admin_client.put("/api/subskrypcja", json={"status": "aktywna", "data_do": "2999-12-31"})
    assert admin_client.get("/api/subskrypcja").json()["aktywna"] is True
    assert admin_client.post("/api/stoliki", json={"nazwa": "S5", "pojemnosc": 2}).status_code in (200, 201)


def test_auth_dziala_mimo_blokady(admin_client):
    admin_client.put("/api/subskrypcja", json={"status": "wygasla"})
    # Rejestracja i logowanie (/api/auth/*) są wyłączone spod blokady.
    r = admin_client.post("/api/auth/register",
                          json={"email": "userlock@lokal.pl", "haslo": "Haslo123!", "imie": "A", "nazwisko": "B"})
    assert r.status_code == 201, r.text
    r2 = admin_client.post("/api/auth/login", json={"email": "userlock@lokal.pl", "haslo": "Haslo123!"})
    assert r2.status_code == 200


def test_admin_odblokowuje_zmiana_statusu(admin_client):
    admin_client.put("/api/subskrypcja", json={"status": "wygasla"})
    assert admin_client.post("/api/stoliki", json={"nazwa": "X", "pojemnosc": 2}).status_code == 402
    admin_client.put("/api/subskrypcja", json={"status": "aktywna", "tier": "pro"})
    assert admin_client.post("/api/stoliki", json={"nazwa": "X", "pojemnosc": 2}).status_code in (200, 201)
    assert admin_client.get("/api/subskrypcja").json()["tier"] == "pro"
