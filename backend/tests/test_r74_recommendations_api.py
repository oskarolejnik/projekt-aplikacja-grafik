from datetime import date

import factories
from auth import create_access_token
from routers import analityka_rezerwacji as analytics_router


START = date(2026, 6, 1)
END = date(2026, 6, 30)
RECOMMENDATION_HASH = "a" * 64
SIMULATION_HASH = "b" * 64


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _manager(login, *permissions):
    return factories.UserFactory(
        login=login,
        rola="szef",
        pracownik=None,
        uprawnienia_override={permission: True for permission in permissions},
    )


def test_recommendation_http_contract_and_exact_permissions(client, monkeypatch):
    analyst = _manager("r74_analyst", "rezerwacje.analityka")
    approver = _manager(
        "r74_approver",
        "rezerwacje.analityka",
        "rezerwacje.reguly",
    )
    reception = _manager("r74_reception", "rezerwacje.operacje")
    calls = []

    monkeypatch.setattr(
        analytics_router.reservation_recommendations,
        "list_recommendations",
        lambda _db, start, end: {
            "start": str(start),
            "end": str(end),
            "progi": {},
            "rekomendacje": [],
            "decyzje": [],
        },
    )

    def fake_simulate(_db, recommendation_hash, start, end, user):
        calls.append(("simulate", recommendation_hash, start, end, user.login))
        return {
            "recommendation_hash": recommendation_hash,
            "simulation_hash": SIMULATION_HASH,
            "summary": {},
            "replay": False,
        }

    def fake_decide(_db, recommendation_hash, payload, key, user):
        calls.append(
            (
                "decide",
                recommendation_hash,
                payload.decyzja,
                key,
                user.login,
            ),
        )
        return {
            "recommendation_hash": recommendation_hash,
            "simulation_hash": payload.simulation_hash,
            "decyzja": payload.decyzja,
            "replay": False,
        }

    monkeypatch.setattr(
        analytics_router.reservation_recommendations,
        "simulate",
        fake_simulate,
    )
    monkeypatch.setattr(
        analytics_router.reservation_recommendations,
        "decide",
        fake_decide,
    )

    list_path = "/api/analityka/rezerwacje/rekomendacje"
    query = {"start": str(START), "end": str(END)}
    assert client.get(list_path, params=query).status_code == 401
    assert client.get(
        list_path,
        params=query,
        headers=_headers(reception),
    ).status_code == 403
    listed = client.get(list_path, params=query, headers=_headers(analyst))
    assert listed.status_code == 200, listed.text
    assert listed.json()["rekomendacje"] == []

    simulate_path = f"{list_path}/{RECOMMENDATION_HASH}/symulacja"
    simulated = client.post(
        simulate_path,
        headers=_headers(analyst),
        json={"start": str(START), "end": str(END)},
    )
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["simulation_hash"] == SIMULATION_HASH

    decision_path = f"{list_path}/{RECOMMENDATION_HASH}/decyzja"
    decision_body = {
        "start": str(START),
        "end": str(END),
        "simulation_hash": SIMULATION_HASH,
        "decyzja": "accepted",
        "powod": "confirmed_after_simulation",
    }
    assert client.post(
        decision_path,
        headers={
            **_headers(analyst),
            "Idempotency-Key": "r74-http-analyst-denied",
        },
        json=decision_body,
    ).status_code == 403
    decided = client.post(
        decision_path,
        headers={
            **_headers(approver),
            "Idempotency-Key": "r74-http-approver-accepted",
        },
        json=decision_body,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["decyzja"] == "accepted"
    assert calls == [
        ("simulate", RECOMMENDATION_HASH, START, END, "r74_analyst"),
        (
            "decide",
            RECOMMENDATION_HASH,
            "accepted",
            "r74-http-approver-accepted",
            "r74_approver",
        ),
    ]

    assert client.get(
        f"{list_path}/{RECOMMENDATION_HASH}/przyszla",
        headers=_headers(analyst),
    ).status_code == 403
