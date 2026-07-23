"""Small HTTP helpers for legacy reservation tests migrated to the v2 widget."""

from uuid import uuid4


DEFAULT_SESSION = "public-widget-regression-session-0001"


def enable_widget_v2(admin_client, **extra):
    response = admin_client.put(
        "/api/lokal/config",
        json={
            "rezerwacje_online": True,
            "rezerwacje_widget_v2": True,
            "rezerwacje_rodo_kontakt": "rodo@lokalo.test",
            "rezerwacje_rodo_adres": "ul. Testowa 1, Warszawa",
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response


def public_create_v2(
    client,
    *,
    data,
    godz_od,
    liczba_osob,
    nazwisko,
    email=None,
    telefon=None,
    headers=None,
    session=DEFAULT_SESSION,
):
    request_headers = headers if headers is not None else {}
    if "X-Reservation-Hold" not in request_headers:
        hold = client.post(
            "/api/online/hold",
            json={
                "data": str(data),
                "godz_od": godz_od,
                "liczba_osob": liczba_osob,
            },
            headers={
                "X-Reservation-Session": session,
                "Idempotency-Key": f"test-hold-{uuid4().hex}",
            },
        )
        if hold.status_code != 201:
            return hold
        request_headers["X-Reservation-Session"] = session
        request_headers["X-Reservation-Hold"] = hold.json()["hold_token"]
    request_headers.setdefault(
        "Idempotency-Key",
        f"test-create-{uuid4().hex}",
    )

    config = client.get("/api/online/widget-config")
    assert config.status_code == 200, config.text
    versions = config.json()
    contact_email = email or (None if telefon else "public-widget@example.test")
    return client.post(
        "/api/online/rezerwacja",
        json={
            "data": str(data),
            "godz_od": godz_od,
            "liczba_osob": liczba_osob,
            "nazwisko": nazwisko,
            "email": contact_email,
            "telefon": telefon,
            "privacy_notice_acknowledged": True,
            "privacy_notice_version": versions["privacy"]["notice_version"],
            "marketing_consent": False,
            "marketing_consent_version": versions["marketing"]["version"],
            "sensitive_data_consent": False,
        },
        headers=request_headers,
    )


def public_waitlist_v2(
    client,
    *,
    data,
    godz_od,
    liczba_osob,
    nazwisko,
    email=None,
    telefon=None,
    headers=None,
    session=DEFAULT_SESSION,
):
    request_headers = dict(headers or {})
    request_headers.setdefault("X-Reservation-Session", session)
    request_headers.setdefault(
        "Idempotency-Key",
        f"test-waitlist-{uuid4().hex}",
    )
    config = client.get("/api/online/widget-config")
    assert config.status_code == 200, config.text
    versions = config.json()
    return client.post(
        "/api/online/lista-oczekujacych",
        json={
            "data": str(data),
            "godz_od": godz_od,
            "liczba_osob": liczba_osob,
            "nazwisko": nazwisko,
            "email": email or (None if telefon else "waitlist@example.test"),
            "telefon": telefon,
            "privacy_notice_acknowledged": True,
            "privacy_notice_version": versions["privacy"]["notice_version"],
            "marketing_consent": False,
            "marketing_consent_version": versions["marketing"]["version"],
            "sensitive_data_consent": False,
        },
        headers=request_headers,
    )
