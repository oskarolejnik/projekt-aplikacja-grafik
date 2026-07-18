"""R6b.1: jeden, wersjonowany snapshot operacyjny stanowiska hosta."""

from datetime import datetime

import factories
import main
import models
from auth import create_access_token


DAY = "2035-07-16"


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _published_table(admin_client):
    room_response = admin_client.post(
        "/api/sale-rezerwacyjne",
        json={"nazwa": "Sala snapshotu", "aktywna": True, "kolejnosc": 0},
    )
    assert room_response.status_code == 201, room_response.text
    room = room_response.json()
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
    ).json()
    created_response = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic/stoliki",
        json={
            "expected_revision": draft["wersja"]["rewizja"],
            "nazwa": "P1",
            "pojemnosc": 4,
            "plan_x": 24,
            "plan_y": 36,
        },
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    table = next(row for row in created["stoliki"] if row["nazwa"] == "P1")
    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": created["wersja"]["rewizja"]},
    )
    assert published.status_code == 200, published.text
    return room, table


def _reservation(admin_client, table_id):
    response = admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            "data": DAY,
            "godz_od": "18:00",
            "stolik_id": table_id,
            "liczba_osob": 3,
            "nazwisko": "Kowalska-Snapshot",
            "telefon": "600700800",
            "email": "snapshot@example.com",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_snapshot_ma_stabilny_kontrakt_i_jest_zgodny_ze_starymi_endpointami(
    admin_client,
):
    room, table = _published_table(admin_client)
    reservation = _reservation(admin_client, table["id"])

    # Nowy szkic nie moze wyciec do operacyjnego, published-only snapshotu.
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
    ).json()
    draft_only = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic/stoliki",
        json={
            "expected_revision": draft["wersja"]["rewizja"],
            "nazwa": "Tylko szkic",
            "pojemnosc": 2,
        },
    )
    assert draft_only.status_code == 201, draft_only.text

    response = admin_client.get(f"/api/host/snapshot?data={DAY}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == {
        "version",
        "schema_version",
        "data",
        "generated_at",
        "kolejka",
        "os_czasu",
        "plan_sali",
    }
    assert body["schema_version"] == main.HOST_SNAPSHOT_SCHEMA_VERSION == 1
    assert body["version"] == body["generated_at"]
    assert body["generated_at"].endswith("Z")
    assert datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00")).tzinfo
    assert body["data"] == DAY

    assert body["kolejka"] == admin_client.get(
        f"/api/host/kolejka?data={DAY}",
    ).json()
    assert body["os_czasu"] == admin_client.get(
        f"/api/host/os-czasu?data={DAY}",
    ).json()
    assert body["plan_sali"] == admin_client.get(
        f"/api/plan-sali?data={DAY}",
    ).json()
    assert body["plan_sali"]["sala_id"] is None
    assert [row["id"] for row in body["plan_sali"]["stoliki"]] == [table["id"]]
    assert "Tylko szkic" not in response.text
    assert any(
        row["rezerwacja_id"] == reservation["id"]
        for row in body["os_czasu"]["zajetosci"]
    )

    assert response.headers["cache-control"] == "private, no-store"
    vary = {value.strip().casefold() for value in response.headers["vary"].split(",")}
    assert {"authorization", "cookie"} <= vary


def test_snapshot_stosuje_centralne_uprawnienie_hosta_i_redaguje_pii(
    admin_client,
    client,
    db,
):
    _, table = _published_table(admin_client)
    reservation = _reservation(admin_client, table["id"])
    waitlist = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": DAY,
            "godz_od": "19:00",
            "liczba_osob": 2,
            "nazwisko": "Waitlist-Sekret",
            "telefon": "500400300",
        },
    )
    assert waitlist.status_code == 201, waitlist.text
    termin = db.get(models.Termin, reservation["id"])
    db.add(models.ProfilGoscia(
        klucz_hash=main._crm_hash(termin),
        nazwisko="Profil-Sekret",
        alergie="orzechy-snapshot",
        tagi=["tag-snapshot"],
        vip=True,
    ))
    db.commit()

    host = factories.UserFactory(
        login="host_snapshot_no_pii",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.host": True},
    )
    response = client.get(
        f"/api/host/snapshot?data={DAY}",
        headers=_headers(host),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    queue_row = body["kolejka"]["nadchodzace"][0]
    assert queue_row["nazwisko"] == "Gość"
    assert queue_row["telefon"] is None and queue_row["email"] is None
    assert queue_row["gosc"] == {
        "vip": True,
        "ma_alergie": None,
        "alergie": None,
        "okazja_typ": None,
        "okazja_data": None,
        "tagi": [],
        "dane_wrazliwe_ukryte": False,
    }
    assert body["kolejka"]["waitlista"][0]["nazwisko"] == "Gość"
    assert body["os_czasu"]["zajetosci"][0]["nazwisko"] == "Gość"
    assert body["plan_sali"]["stoliki"][0]["rezerwacje"][0]["nazwisko"] == "Gość"
    for secret in (
        "Kowalska-Snapshot",
        "600700800",
        "snapshot@example.com",
        "Waitlist-Sekret",
        "500400300",
        "Profil-Sekret",
        "orzechy-snapshot",
        "tag-snapshot",
    ):
        assert secret not in response.text

    operations_only = factories.UserFactory(
        login="snapshot_operations_only",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.operacje": True},
    )
    denied = client.get(
        f"/api/host/snapshot?data={DAY}",
        headers=_headers(operations_only),
    )
    assert denied.status_code == 403
