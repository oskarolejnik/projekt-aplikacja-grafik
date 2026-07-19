"""R7.1: PII-safe CRM search with filters, sorting and pagination."""

from datetime import date, datetime

import factories
import models
from auth import create_access_token
from routers import crm


def _reservation(
    db,
    *,
    day,
    phone,
    surname,
    email,
    status="odbyla",
):
    row = models.Termin(
        rodzaj="stolik",
        kanal="reczna",
        nazwisko=surname,
        telefon=phone,
        email=email,
        data=day,
        status=status,
        liczba_osob=2,
        zadatek=0,
        utworzono_at=datetime(2026, 6, 1, 12, 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _profile(db, reservation, **extra):
    profile = models.ProfilGoscia(
        klucz_hash=crm._hash_klucz(crm._klucz_crm(reservation)),
        nazwisko=reservation.nazwisko,
        tagi=extra.pop("tagi", None),
        vip=extra.pop("vip", False),
        **extra,
    )
    db.add(profile)
    db.commit()
    return profile


def _seed_guests(db):
    risky = None
    for index, status in enumerate(("odbyla", "no_show", "odwolana"), start=1):
        risky = _reservation(
            db,
            day=date(2026, 7, index),
            phone="+48 600-100-200",
            surname="Zaneta Zurek",
            email="zaneta@example.com",
            status=status,
        )
    _profile(db, risky, vip=True, tagi=["VIP", "okno"])

    regular = None
    for index in (10, 11):
        regular = _reservation(
            db,
            day=date(2026, 7, index),
            phone="700 200 300",
            surname="Anna Nowak",
            email="anna@example.com",
        )
    return risky, regular


def test_crm_search_filters_pii_in_body_and_returns_exact_contract(admin_client, db):
    _seed_guests(db)

    response = admin_client.post("/api/crm/goscie/wyszukaj", json={
        "q": "VIP",
        "vip": True,
        "ryzyko": "wysokie",
        "min_wizyt": 3,
        "sort": "ryzyko_desc",
        "offset": 0,
        "limit": 20,
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"goscie", "total", "offset", "limit", "podsumowanie"}
    assert body["total"] == 1
    assert body["offset"] == 0 and body["limit"] == 20
    assert body["goscie"][0]["nazwisko"] == "Zaneta Zurek"
    assert body["goscie"][0]["ryzyko"] == "wysokie"
    assert body["podsumowanie"] == {
        "wizyt": 3,
        "odbyte": 1,
        "no_show": 1,
        "aktywne": 0,
        "vip": 1,
        "wysokie_ryzyko": 1,
    }


def test_crm_search_matches_surname_phone_email_and_tags(admin_client, db):
    _seed_guests(db)

    for query in ("zaneta", "600100", "ZANETA@EXAMPLE.COM", "okno"):
        response = admin_client.post(
            "/api/crm/goscie/wyszukaj",
            json={"q": query},
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert response.json()["goscie"][0]["nazwisko"] == "Zaneta Zurek"


def test_crm_search_sort_pagination_and_summary_use_full_filtered_set(admin_client, db):
    _seed_guests(db)

    first_page = admin_client.post("/api/crm/goscie/wyszukaj", json={
        "sort": "nazwisko_asc",
        "offset": 0,
        "limit": 1,
    }).json()
    second_page = admin_client.post("/api/crm/goscie/wyszukaj", json={
        "sort": "nazwisko_asc",
        "offset": 1,
        "limit": 1,
    }).json()

    assert first_page["total"] == second_page["total"] == 2
    assert [first_page["goscie"][0]["nazwisko"], second_page["goscie"][0]["nazwisko"]] == [
        "Anna Nowak",
        "Zaneta Zurek",
    ]
    assert first_page["podsumowanie"] == second_page["podsumowanie"]
    assert first_page["podsumowanie"]["wizyt"] == 5

    vip_only = admin_client.post(
        "/api/crm/goscie/wyszukaj",
        json={"vip": False, "min_wizyt": 2},
    ).json()
    assert vip_only["total"] == 1
    assert vip_only["goscie"][0]["nazwisko"] == "Anna Nowak"


def test_legacy_crm_get_keeps_array_contract(admin_client, db):
    _seed_guests(db)

    response = admin_client.get("/api/crm/goscie?min_wizyt=2&limit=1")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1


def test_crm_search_is_admin_only_and_allowed_in_read_only_subscription(
    admin_client,
    client,
    db,
):
    _seed_guests(db)
    subscription = db.get(models.Subskrypcja, 1)
    subscription.status = "wygasla"
    db.commit()

    assert admin_client.post(
        "/api/crm/goscie/wyszukaj", json={"q": "zaneta"},
    ).status_code == 200

    user = factories.UserFactory(
        login="crm_search_denied",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.analityka": True},
    )
    response = client.post(
        "/api/crm/goscie/wyszukaj",
        json={},
        headers={"Authorization": f"Bearer {create_access_token(user)}"},
    )
    assert response.status_code == 403
