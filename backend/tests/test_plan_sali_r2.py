"""R2.1: sale, izolowany szkic i atomowa publikacja planu."""

from datetime import date, datetime, time, timedelta

import factories
import models
import schemas
from auth import create_access_token
from deps import _teraz_lokalnie


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _sala(admin_client, nazwa="Sala główna"):
    response = admin_client.post(
        "/api/sale-rezerwacyjne",
        json={"nazwa": nazwa, "aktywna": True, "kolejnosc": 0},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _stolik(admin_client, sala_id, nazwa="S1", db=None, **extra):
    """Stan zastany/migracyjny; nowe stoły w wersjonowanej sali tworzy endpoint szkicu."""
    assert db is not None
    sala = db.get(models.SalaRezerwacyjna, sala_id)
    saved = models.Stolik(
        nazwa=nazwa,
        sala_id=sala_id,
        strefa=sala.nazwa,
        pojemnosc=4,
        aktywny=True,
        **extra,
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    # Utworzenie sali zakłada od razu PlanSali. Legacy GET jest od R2.2
    # adapterem published-only, więc migracyjny rekord seedowany bezpośrednio
    # nie może być widoczny przed pierwszą publikacją.
    assert all(
        row["id"] != saved.id
        for row in admin_client.get("/api/stoliki").json()["stoliki"]
    )
    return schemas.StolikOut.model_validate(saved).model_dump()


def _pozycje(body, overrides=None):
    overrides = overrides or {}
    rows = []
    for stolik in body["stoliki"]:
        row = {
            "stolik_id": stolik["id"],
            "plan_x": stolik["plan_x"],
            "plan_y": stolik["plan_y"],
            "szerokosc": stolik["szerokosc"],
            "wysokosc": stolik["wysokosc"],
            "obrot": stolik["obrot"],
            "aktywny_w_planie": stolik["aktywny_w_planie"],
        }
        row.update(overrides.get(stolik["id"], {}))
        rows.append(row)
    return rows


def test_nazwa_sali_ma_unicode_safe_klucz_i_jednolity_odstep(admin_client, db):
    created = _sala(admin_client, "  Żółta   Sala  ")
    assert created["nazwa"] == "Żółta Sala"
    saved = db.get(models.SalaRezerwacyjna, created["id"])
    assert saved.nazwa_klucz == "żółta sala"

    duplicate = admin_client.post(
        "/api/sale-rezerwacyjne",
        json={"nazwa": "żółta sala", "aktywna": True, "kolejnosc": 1},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "ROOM_NAME_CONFLICT"
    assert duplicate.json()["detail"]["message"] == "Sala o tej nazwie już istnieje."


def test_szkic_jest_izolowany_publikacja_syncuje_stolik_i_historia_zostaje(
    admin_client, db,
):
    sala = _sala(admin_client)
    stolik = _stolik(admin_client, sala["id"], db=db)
    saved = db.get(models.Stolik, stolik["id"])
    saved.plan_x, saved.plan_y = 10, 20
    db.commit()

    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    assert draft["wersja"] == {"id": draft["wersja"]["id"], "numer": 1,
                                "status": "draft", "rewizja": 0}
    assert draft["stoliki"][0]["plan_x"] == 10

    updated = admin_client.put(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
        json={
            "expected_revision": 0,
            "pozycje": _pozycje(draft, {
                stolik["id"]: {
                    "plan_x": 70, "plan_y": 80, "szerokosc": 18,
                    "wysokosc": 14, "obrot": 90,
                },
            }),
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["wersja"]["rewizja"] == 1
    # Sala ma już wersjonowany plan, więc przed pierwszą publikacją nie korzysta
    # z legacy fallbacku i nie ujawnia geometrii szkicu operacjom.
    assert admin_client.get(
        f"/api/plan-sali?sala_id={sala['id']}",
    ).json()["stoliki"] == []

    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert published.status_code == 200, published.text
    assert published.json()["wersja"]["status"] == "published"
    assert published.json()["stoliki"][0]["szerokosc"] == 18
    db.expire_all()
    saved = db.get(models.Stolik, stolik["id"])
    assert (saved.plan_x, saved.plan_y, saved.aktywny) == (70, 80, True)

    first = admin_client.post(f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic")
    second = admin_client.post(f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic")
    assert first.json()["wersja"]["numer"] == 2
    assert second.json()["wersja"]["id"] == first.json()["wersja"]["id"]
    assert db.query(models.WersjaPlanuSali).filter_by(
        plan_id=sala["plan_id"], status="published",
    ).count() == 1
    assert db.query(models.WersjaPlanuSali).filter_by(
        plan_id=sala["plan_id"], status="draft",
    ).count() == 1


def test_zapis_szkicu_wymaga_pelnego_snapshotu_i_aktualnej_rewizji(admin_client, db):
    sala = _sala(admin_client)
    first = _stolik(admin_client, sala["id"], "S1", db=db)
    _stolik(admin_client, sala["id"], "S2", db=db)
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()

    incomplete = admin_client.put(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
        json={"expected_revision": 0, "pozycje": _pozycje(draft)[:1]},
    )
    assert incomplete.status_code == 422
    assert incomplete.json()["detail"]["code"] == "PLAN_SNAPSHOT_INVALID"

    good = admin_client.put(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
        json={"expected_revision": 0, "pozycje": _pozycje(draft, {
            first["id"]: {"plan_x": 45},
        })},
    )
    assert good.status_code == 200
    stale = admin_client.put(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
        json={"expected_revision": 0, "pozycje": _pozycje(draft)},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "PLAN_REVISION_CONFLICT"
    assert stale.json()["detail"]["current_revision"] == 1
    stale_delete = admin_client.delete(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic?expected_revision=0",
    )
    assert stale_delete.status_code == 409
    assert stale_delete.json()["detail"]["code"] == "PLAN_REVISION_CONFLICT"
    assert admin_client.delete(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic?expected_revision=1",
    ).status_code == 204


def test_nowy_stol_jest_atomowa_czescia_szkicu_i_znika_po_odrzuceniu(
    admin_client, db,
):
    sala = _sala(admin_client)
    existing = _stolik(admin_client, sala["id"], "Istniejący", db=db)
    initial = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    assert admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/publikuj",
        json={"expected_revision": initial["wersja"]["rewizja"]},
    ).status_code == 200
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()

    created = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic/stoliki",
        json={
            "expected_revision": draft["wersja"]["rewizja"],
            "nazwa": "S1",
            "pojemnosc": 6,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["wersja"]["rewizja"] == 1
    assert len(body["stoliki"]) == 2
    new_table = next(row for row in body["stoliki"] if row["nazwa"] == "S1")
    assert new_table["aktywny_w_planie"] is True
    table_id = new_table["id"]
    db.expire_all()
    assert db.get(models.Stolik, table_id).aktywny is False

    discarded = admin_client.delete(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic?expected_revision=1",
    )
    assert discarded.status_code == 204
    db.expire_all()
    assert db.get(models.Stolik, table_id) is None
    assert db.get(models.Stolik, existing["id"]) is not None


def test_kolejne_nowe_stoly_dostaja_wolne_miejsce_bez_przestawiania(
    admin_client,
):
    sala = _sala(admin_client)
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    previous = {}
    body = draft

    for revision, name in enumerate(("S1", "S2", "S3")):
        response = admin_client.post(
            f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic/stoliki",
            json={
                "expected_revision": revision,
                "nazwa": name,
                "pojemnosc": 4,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        current = {
            row["id"]: (
                row["plan_x"], row["plan_y"],
                row["szerokosc"], row["wysokosc"],
            )
            for row in body["stoliki"]
        }
        assert all(current[table_id] == geometry for table_id, geometry in previous.items())
        previous = current

    tables = body["stoliki"]
    assert {row["nazwa"] for row in tables} == {"S1", "S2", "S3"}
    minimum_gap = 4
    for index, first in enumerate(tables):
        for second in tables[index + 1:]:
            horizontal_gap = (
                abs(first["plan_x"] - second["plan_x"])
                - (first["szerokosc"] + second["szerokosc"]) / 2
            )
            vertical_gap = (
                abs(first["plan_y"] - second["plan_y"])
                - (first["wysokosc"] + second["wysokosc"]) / 2
            )
            assert horizontal_gap >= minimum_gap or vertical_gap >= minimum_gap, (
                first, second
            )


def test_pierwszy_szkic_nie_wycieka_do_hosta_przed_publikacja(
    admin_client, client,
):
    sala = _sala(admin_client)
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    created = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic/stoliki",
        json={
            "expected_revision": draft["wersja"]["rewizja"],
            "nazwa": "Szkic 1",
            "pojemnosc": 4,
        },
    )
    assert created.status_code == 201, created.text
    table_id = created.json()["stoliki"][0]["id"]
    host = factories.UserFactory(
        login="host_first_draft", rola="szef", pracownik=None,
        uprawnienia_override={"rezerwacje.host": True},
    )
    headers = _headers(host)

    published_view = client.get(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan", headers=headers,
    )
    operational_view = client.get(
        f"/api/plan-sali?sala_id={sala['id']}", headers=headers,
    )
    assert published_view.status_code == 200
    assert published_view.json()["wersja"] is None
    assert published_view.json()["stoliki"] == []
    assert operational_view.status_code == 200
    assert operational_view.json()["stoliki"] == []

    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/publikuj",
        json={"expected_revision": created.json()["wersja"]["rewizja"]},
    )
    assert published.status_code == 200, published.text
    assert [row["id"] for row in client.get(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan", headers=headers,
    ).json()["stoliki"]] == [table_id]
    assert [row["id"] for row in client.get(
        f"/api/plan-sali?sala_id={sala['id']}", headers=headers,
    ).json()["stoliki"]] == [table_id]


def test_kombinacja_nie_moze_ochronic_draft_only_stolika_przed_discard(
    admin_client, db,
):
    sala = _sala(admin_client)
    first = _stolik(admin_client, sala["id"], "S1", db=db)
    second = _stolik(admin_client, sala["id"], "S2", db=db)
    rejected_existing = admin_client.post(
        "/api/kombinacje",
        json={"nazwa": "S1+S2", "stoliki": [first["id"], second["id"]]},
    )
    assert rejected_existing.status_code == 409
    assert rejected_existing.json()["detail"]["code"] == (
        "FLOOR_PLAN_VERSIONING_REQUIRED"
    )
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    created = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic/stoliki",
        json={
            "expected_revision": draft["wersja"]["rewizja"],
            "nazwa": "S3",
            "pojemnosc": 2,
        },
    )
    assert created.status_code == 201, created.text
    pending_id = next(
        row["id"] for row in created.json()["stoliki"] if row["nazwa"] == "S3"
    )

    rejected_post = admin_client.post(
        "/api/kombinacje",
        json={"nazwa": "S1+S3", "stoliki": [first["id"], pending_id]},
    )
    assert rejected_post.status_code == 409
    assert rejected_post.json()["detail"]["code"] == (
        "FLOOR_PLAN_VERSIONING_REQUIRED"
    )
    assert admin_client.get("/api/kombinacje").json()["kombinacje"] == []

    discarded = admin_client.delete(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic?expected_revision=1",
    )
    assert discarded.status_code == 204
    db.expire_all()
    assert db.get(models.Stolik, pending_id) is None


def test_publikacja_blokuje_dezaktywacje_stolu_z_przyszla_rezerwacja_w_kombinacji(
    admin_client, db,
):
    sala = _sala(admin_client)
    first = _stolik(admin_client, sala["id"], "S1", db=db)
    second = _stolik(admin_client, sala["id"], "S2", db=db)
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    updated = admin_client.put(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
        json={"expected_revision": 0, "pozycje": _pozycje(draft, {
            second["id"]: {"aktywny_w_planie": False},
        })},
    )
    assert updated.status_code == 200
    termin = models.Termin(
        data=date.today() + timedelta(days=2),
        nazwisko="Gość",
        rodzaj="stolik",
        status="potwierdzona",
        godz_od=time(18, 0),
        stolik_id=first["id"],
        stoliki_dodatkowe=[second["id"]],
        liczba_osob=6,
    )
    db.add(termin)
    db.commit()

    response = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PLAN_PUBLISH_CONFLICT"
    assert response.json()["detail"]["reservation_ids"] == [termin.id]
    db.expire_all()
    assert db.get(models.Stolik, second["id"]).aktywny is True


def test_publikacja_blokuje_dezaktywacje_stolu_z_aktywnym_holdem(admin_client, db):
    sala = _sala(admin_client)
    stolik = _stolik(admin_client, sala["id"], db=db)
    initial = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    assert admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/publikuj",
        json={"expected_revision": initial["wersja"]["rewizja"]},
    ).status_code == 200
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    admin_client.put(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
        json={"expected_revision": 0, "pozycje": _pozycje(draft, {
            stolik["id"]: {"aktywny_w_planie": False},
        })},
    )
    waitlist = models.ListaOczekujacych(
        data=date.today(),
        godz_od=time(18, 0),
        liczba_osob=2,
        nazwisko="Oczekujący",
        status="oczekuje",
        utworzono_at=datetime.utcnow(),
    )
    db.add(waitlist)
    db.flush()
    local_now = _teraz_lokalnie() or datetime.now()
    claim = models.RezerwacjaStolikClaim(
        waitlist_id=waitlist.id,
        stolik_id=stolik["id"],
        data=date.today(),
        minute=18 * 60,
        expires_at=local_now + timedelta(minutes=10),
        created_at=datetime.utcnow(),
    )
    db.add(claim)
    db.commit()

    live = admin_client.get(
        f"/api/plan-sali?data={local_now.date()}&sala_id={sala['id']}",
    ).json()
    assert live["stoliki"][0]["status"] == "wstrzymany"

    response = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/publikuj",
        json={"expected_revision": 1},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["hold_ids"] == [claim.id]


def test_stary_formularz_nie_dodaje_stolu_poza_wersjonowanym_szkicem(
    admin_client, db,
):
    sala = _sala(admin_client, "Ogródek")
    for payload in (
        {
            "nazwa": "O1", "strefa": " ogródek ", "pojemnosc": 4,
            "aktywny": False,
        },
        {
            "nazwa": "O2", "sala_id": sala["id"], "strefa": "Błędna",
            "pojemnosc": 4, "aktywny": False,
        },
    ):
        response = admin_client.post("/api/stoliki", json=payload)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "FLOOR_PLAN_VERSIONING_REQUIRED"
    assert db.query(models.Stolik).count() == 0


def test_zmiana_nazwy_sali_nadal_syncuje_stary_rekord_stolika(admin_client, db):
    sala = _sala(admin_client, "Ogródek")
    stolik = _stolik(admin_client, sala["id"], "O2", db=db)

    renamed = admin_client.put(
        f"/api/sale-rezerwacyjne/{sala['id']}",
        json={"nazwa": "Taras", "aktywna": True, "kolejnosc": 0},
    )
    assert renamed.status_code == 200
    legacy_edit = admin_client.put(
        f"/api/stoliki/{stolik['id']}",
        json={**stolik, "strefa": "Taras"},
    )
    assert legacy_edit.status_code == 200, legacy_edit.text
    assert legacy_edit.json()["sala_id"] == sala["id"]
    assert legacy_edit.json()["strefa"] == "Taras"


def test_rbac_planu_sali_jest_dokladny(admin_client, client):
    sala = _sala(admin_client)
    host = factories.UserFactory(
        login="host_r21", rola="szef", pracownik=None,
        uprawnienia_override={"rezerwacje.host": True},
    )
    floor = factories.UserFactory(
        login="floor_r21", rola="szef", pracownik=None,
        uprawnienia_override={"rezerwacje.sala": True},
    )
    operations = factories.UserFactory(
        login="operations_r21", rola="szef", pracownik=None,
        uprawnienia_override={"rezerwacje.operacje": True},
    )

    assert client.get("/api/sale-rezerwacyjne", headers=_headers(host)).status_code == 200
    assert client.get(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan", headers=_headers(host),
    ).status_code == 200
    assert client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic", headers=_headers(host),
    ).status_code == 403
    assert client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic", headers=_headers(floor),
    ).status_code == 200
    assert client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic/stoliki",
        headers=_headers(host),
        json={"expected_revision": 0, "nazwa": "S1", "pojemnosc": 2},
    ).status_code == 403
    assert client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic/stoliki",
        headers=_headers(floor),
        json={"expected_revision": 0, "nazwa": "S1", "pojemnosc": 2},
    ).status_code == 201
    assert client.get(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic", headers=_headers(host),
    ).status_code == 403
    assert client.get(
        "/api/sale-rezerwacyjne", headers=_headers(operations),
    ).status_code == 403
    assert client.get(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/rollback", headers=_headers(host),
    ).status_code == 403


def test_plan_ma_no_store_gating_i_legacy_put_nie_omija_szkicu(admin_client, db):
    sala = _sala(admin_client)
    stolik = _stolik(admin_client, sala["id"], db=db)
    list_response = admin_client.get("/api/sale-rezerwacyjne")
    plan_response = admin_client.get(f"/api/plan-sali?sala_id={sala['id']}")
    assert list_response.headers["cache-control"] == "private, no-store"
    assert plan_response.headers["cache-control"] == "private, no-store"
    assert "authorization" in list_response.headers["vary"].casefold()

    legacy_write = admin_client.put(
        "/api/plan-sali/pozycje",
        json=[{"id": stolik["id"], "plan_x": 20, "plan_y": 30}],
    )
    assert legacy_write.status_code == 409
    assert legacy_write.json()["detail"]["code"] == "FLOOR_PLAN_VERSIONING_REQUIRED"

    assert admin_client.put(
        "/api/lokal/config", json={"modul_rezerwacje": False},
    ).status_code == 200
    assert admin_client.get("/api/sale-rezerwacyjne").status_code == 403


def test_opublikowany_plan_blokuje_legacy_aktywacje_przeniesienie_i_delete(
    admin_client, db,
):
    sala = _sala(admin_client)
    stolik = _stolik(admin_client, sala["id"], db=db)
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/szkic",
    ).json()
    assert admin_client.post(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan/publikuj",
        json={"expected_revision": draft["wersja"]["rewizja"]},
    ).status_code == 200

    active_create = admin_client.post(
        "/api/stoliki",
        json={"nazwa": "S2", "sala_id": sala["id"], "pojemnosc": 2},
    )
    assert active_create.status_code == 409
    assert active_create.json()["detail"]["code"] == "FLOOR_PLAN_VERSIONING_REQUIRED"

    inactive_create = admin_client.post(
        "/api/stoliki",
        json={
            "nazwa": "S2", "sala_id": sala["id"], "pojemnosc": 2,
            "aktywny": False,
        },
    )
    assert inactive_create.status_code == 409
    assert inactive_create.json()["detail"]["code"] == "FLOOR_PLAN_VERSIONING_REQUIRED"
    # Nie powstaje osierocony rekord, który kolejny draft mógłby uznać za swój.
    assert [row["id"] for row in admin_client.get(
        f"/api/sale-rezerwacyjne/{sala['id']}/plan",
    ).json()["stoliki"]] == [stolik["id"]]
    assert [row["id"] for row in admin_client.get(
        f"/api/plan-sali?sala_id={sala['id']}",
    ).json()["stoliki"]] == [stolik["id"]]

    legacy_update = admin_client.put(
        f"/api/stoliki/{stolik['id']}",
        json={**stolik, "aktywny": False},
    )
    assert legacy_update.status_code == 409
    assert legacy_update.json()["detail"]["code"] == "FLOOR_PLAN_VERSIONING_REQUIRED"

    protected_delete = admin_client.delete(f"/api/stoliki/{stolik['id']}")
    assert protected_delete.status_code == 409
    assert "historii planu" in protected_delete.json()["detail"]
