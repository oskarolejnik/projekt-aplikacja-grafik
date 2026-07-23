"""Publiczne rezerwacje online (widget): dostępność, tworzenie, token (confirm/cancel), anty-spam."""

import datetime as dt
import hashlib


PUBLIC_SESSION = "online-regression-session-0001"


def _fut(days=7):
    return dt.date.today() + dt.timedelta(days=days)


def _enable(admin_client, **extra):
    assert admin_client.put(
        "/api/lokal/config",
        json={
            "rezerwacje_online": True,
            "rezerwacje_widget_v2": True,
            "rezerwacje_rodo_kontakt": "rodo@lokalo.test",
            "rezerwacje_rodo_adres": "ul. Testowa 1, Warszawa",
            **extra,
        },
    ).status_code == 200


def _online_create(
    client,
    *,
    data,
    godz_od,
    liczba_osob,
    nazwisko,
    telefon=None,
    email=None,
):
    if not telefon and not email:
        email = "online-regression@example.test"
    fingerprint = hashlib.sha256(
        f"{data}:{godz_od}:{liczba_osob}:{nazwisko}:{telefon}:{email}".encode()
    ).hexdigest()[:20]
    hold = client.post(
        "/api/online/hold",
        json={
            "data": data,
            "godz_od": godz_od,
            "liczba_osob": liczba_osob,
        },
        headers={
            "X-Reservation-Session": PUBLIC_SESSION,
            "Idempotency-Key": f"online-hold-{fingerprint}",
        },
    )
    if hold.status_code != 201:
        return hold
    config = client.get("/api/online/widget-config")
    assert config.status_code == 200, config.text
    versions = config.json()
    return client.post(
        "/api/online/rezerwacja",
        json={
            "data": data,
            "godz_od": godz_od,
            "liczba_osob": liczba_osob,
            "nazwisko": nazwisko,
            "telefon": telefon,
            "email": email,
            "privacy_notice_acknowledged": True,
            "privacy_notice_version": versions["privacy"]["notice_version"],
            "marketing_consent": False,
            "marketing_consent_version": versions["marketing"]["version"],
            "sensitive_data_consent": False,
        },
        headers={
            "X-Reservation-Session": PUBLIC_SESSION,
            "X-Reservation-Hold": hold.json()["hold_token"],
            "Idempotency-Key": f"online-create-{fingerprint}",
        },
    )


def _serwis_dla_daty(admin_client, data, *, godz_od="10:00", godz_do="22:00"):
    response = admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": data.weekday(),
        "godz_od": godz_od,
        "godz_do": godz_do,
        "krok_slotu_min": 120,
        "domyslny_turn_time_min": 120,
    })
    assert response.status_code == 201, response.text


def test_online_wylaczone_404(admin_client, client):
    # domyślnie rezerwacje online wyłączone → publiczne endpointy 404
    assert client.get("/api/online/dostepnosc?data=2026-07-01").status_code == 404
    assert client.post("/api/online/rezerwacja", json={"data": "2026-07-01", "godz_od": "18:00", "nazwisko": "X"}).status_code == 404


def test_online_dostepnosc(admin_client, client):
    _enable(admin_client)
    fut = _fut()
    admin_client.post("/api/godziny-otwarcia", json={"dzien_tygodnia": fut.weekday(), "godz_od": "12:00", "godz_do": "22:00", "dlugosc_slotu_min": 120})
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    r = client.get(f"/api/online/dostepnosc?data={fut.isoformat()}&osoby=2")
    assert r.status_code == 200
    sloty = r.json()["sloty"]
    assert len(sloty) >= 1
    assert sloty[0]["godz_od"] == "12:00" and sloty[0]["wolne"] == 1


def test_online_rezerwacja_flow(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    fut = _fut()
    _serwis_dla_daty(admin_client, fut)
    r = _online_create(
        client,
        data=fut.isoformat(),
        godz_od="18:00",
        liczba_osob=3,
        nazwisko="Gość Online",
        email="gosc@example.pl",
    )
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["token"]
    assert token and body["rezerwacja"]["status"] == "rezerwacja"   # auto-potwierdzenie off
    assert "token" not in body["rezerwacja"]
    assert body["rezerwacja"]["stolik"] is None
    assert body["rezerwacja"]["godz_do"] == "20:00"
    # Token jest capability wyłącznie w nagłówku — nigdy w URL/logach.
    g = client.get(
        "/api/online/zarzadzanie/rezerwacja",
        headers={"X-Reservation-Token": token},
    ).json()
    assert g["nazwisko"] == "Gość Online"
    # potwierdzenie po tokenie
    confirmed = client.post(
        "/api/online/zarzadzanie/potwierdz",
        headers={
            "X-Reservation-Token": token,
            "Idempotency-Key": "online-confirm-flow-0001",
        },
    ).json()
    assert confirmed["status"] == "potwierdzona"
    token = confirmed["management_token"]
    # odwołanie po tokenie
    assert client.post(
        "/api/online/zarzadzanie/odwolaj",
        headers={
            "X-Reservation-Token": token,
            "Idempotency-Key": "online-cancel-flow-0001",
        },
    ).json()["status"] == "odwolana"
    # zły token → 404
    assert client.get(
        "/api/online/zarzadzanie/rezerwacja",
        headers={"X-Reservation-Token": "zly-token-zly-token"},
    ).status_code == 404


def test_online_auto_potwierdzenie(admin_client, client):
    _enable(admin_client, rezerwacje_auto_potwierdzenie=True)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    fut = _fut()
    _serwis_dla_daty(admin_client, fut)
    r = _online_create(
        client,
        data=fut.isoformat(),
        godz_od="18:00",
        liczba_osob=2,
        nazwisko="Auto",
    )
    assert r.json()["rezerwacja"]["status"] == "potwierdzona"


def test_online_brak_stolika_409(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 2})
    fut = _fut()
    _serwis_dla_daty(admin_client, fut)
    r = _online_create(
        client,
        data=fut.isoformat(),
        godz_od="18:00",
        liczba_osob=5,
        nazwisko="ZaDuzo",
    )
    assert r.status_code == 409
    assert "buffer_min" not in r.json()["availability"]


def test_online_wstecz_400(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    assert _online_create(
        client,
        data="2020-01-01",
        godz_od="18:00",
        liczba_osob=2,
        nazwisko="Wstecz",
    ).status_code == 400


def test_online_limit_per_ip_z_roznymi_kontaktami(admin_client, client, monkeypatch):
    """Limit IP nie może być ominięty przez podawanie innego kontaktu w każdej próbie."""
    import main
    monkeypatch.setattr(main, "ONLINE_LIMIT_IP_DZIENNY", 3)
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    fut_date = _fut()
    _serwis_dla_daty(admin_client, fut_date)
    fut = fut_date.isoformat()
    for index, g in enumerate(["10:00", "12:00", "14:00"]):
        assert _online_create(
            client,
            data=fut,
            godz_od=g,
            liczba_osob=2,
            nazwisko="Anon",
            email=f"anon-{index}@example.test",
        ).status_code == 201
    r4 = _online_create(
        client,
        data=fut,
        godz_od="16:00",
        liczba_osob=2,
        nazwisko="Anon",
        email="anon-4@example.test",
    )   # 4-ta z tego samego IP → blokada
    assert r4.status_code == 429


def test_online_antyspam_429(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    fut_date = _fut()
    _serwis_dla_daty(admin_client, fut_date)
    fut = fut_date.isoformat()
    for g in ["10:00", "12:00", "14:00", "16:00", "18:00"]:   # 5x, brak kolizji (sloty 120 min)
        rr = _online_create(
            client,
            data=fut,
            godz_od=g,
            liczba_osob=2,
            nazwisko="Spam",
            telefon="600100200",
        )
        assert rr.status_code == 201, rr.text
    r6 = _online_create(
        client,
        data=fut,
        godz_od="20:00",
        liczba_osob=2,
        nazwisko="Spam",
        telefon="600100200",
    )
    assert r6.status_code == 429
