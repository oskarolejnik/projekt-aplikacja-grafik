"""Skupiony kontrakt czystego, wspólnego allocatora R4."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import models
from reservation_allocator import AllocationRequest, evaluate_allocation


BOOKING_DATE = date(2035, 7, 16)  # poniedziałek
NOW = datetime(2035, 7, 1, 12, 0, tzinfo=ZoneInfo("Europe/Warsaw"))


def _service(db, *, large_from=None, large_mode=None):
    service = models.GodzinyOtwarcia(
        dzien_tygodnia=BOOKING_DATE.weekday(),
        godz_od=time(17, 0),
        godz_do=time(23, 0),
        ostatni_zasiadek=time(21, 0),
        dlugosc_slotu_min=120,
        krok_slotu_min=30,
        domyslny_turn_time_min=120,
        aktywny=True,
        nazwa="Kolacja",
        duza_grupa_od=large_from,
        duza_grupa_tryb=large_mode,
    )
    db.add(service)
    db.commit()
    return service


def _room(db, name, *, priority=0, strategy="preferuj"):
    room = models.SalaRezerwacyjna(
        nazwa=name,
        nazwa_klucz=name.casefold(),
        aktywna=True,
        kolejnosc=0,
        strategia_zapelniania=strategy,
        priorytet=priority,
        online_aktywna=True,
        wewnetrzna_aktywna=True,
    )
    db.add(room)
    db.commit()
    return room


def _table(table_id, name, room, capacity=6):
    return {
        "id": table_id,
        "nazwa": name,
        "pojemnosc": capacity,
        "pojemnosc_min": 1,
        "cechy": [],
        "priorytet": 0,
        "sekcja": room.nazwa,
        "strefa": room.nazwa,
        "sala_id": room.id,
        "strategia_zapelniania": room.strategia_zapelniania,
        "priorytet_sali": room.priorytet,
        "kolejnosc_sali": room.kolejnosc,
        "wersja_id": 7,
    }


def _request(**kwargs):
    return AllocationRequest(
        data=BOOKING_DATE,
        godz_od=time(18, 0),
        liczba_osob=kwargs.pop("liczba_osob", 18),
        kanal=kwargs.pop("kanal", "wewnetrzna"),
        intent=kwargs.pop("intent", "simulate"),
        **kwargs,
    )


def test_assign_i_reoptimize_uzywaja_operacyjnego_intentu_regul():
    assert _request(intent="assign").rule_intent == "assign"
    assert _request(intent="reoptimize").rule_intent == "assign"


def test_wybiera_jawna_kombinacje_trzech_stolow_dla_18_osob(db):
    _service(db)
    room = _room(db, "Sala Główna")
    tables = [
        _table(101, "S1", room),
        _table(102, "S2", room),
        _table(103, "S3", room),
    ]
    combinations = [{
        "id": 44,
        "wersja_id": 7,
        "nazwa": "S1 + S2 + S3",
        "stoliki": [101, 102, 103],
        "pojemnosc_min": 18,
        "pojemnosc_max": 18,
        "priorytet": 0,
    }]

    result = evaluate_allocation(
        db,
        _request(),
        tables=tables,
        combinations=combinations,
        occupied_table_ids=set(),
        now=NOW,
    )

    assert result.decision == "allow"
    assert result.selected is not None
    assert result.selected.table_ids == (101, 102, 103)
    assert result.allocation == {
        "stolik_id": 101,
        "stoliki_dodatkowe": [102, 103],
        "stoliki": [101, 102, 103],
        "sala_id": room.id,
        "przydzial_wersja_planu_id": 7,
        "przydzial_kombinacja_planu_id": 44,
        "auto_przydzielony": True,
    }
    assert "TABLE_COMBINATION" in {reason.code for reason in result.reasons}
    assert "koszt" not in result.to_dict(expose_exact=True)


def test_zajety_skladnik_odrzuca_cala_kombinacje(db):
    _service(db)
    room = _room(db, "Sala Zajęta")
    tables = [_table(201 + index, f"Z{index + 1}", room) for index in range(3)]
    combination = [{
        "id": 51,
        "wersja_id": 7,
        "nazwa": "Z1 + Z2 + Z3",
        "stoliki": [201, 202, 203],
        "pojemnosc_min": 18,
        "pojemnosc_max": 18,
    }]

    result = evaluate_allocation(
        db,
        _request(),
        tables=tables,
        combinations=combination,
        occupied_table_ids={202},
        now=NOW,
    )

    assert result.decision == "deny"
    assert result.selected is None
    assert result.code == "NO_TABLE_CANDIDATE"
    assert result.reasons[0].code == "RESOURCE_COMPONENT_OCCUPIED"


def test_allocator_odrzuca_zestawy_laczace_rozne_sale(db):
    _service(db)
    first = _room(db, "Sala A")
    second = _room(db, "Sala B")
    tables = [
        _table(251, "A1", first, capacity=4),
        _table(252, "B1", second, capacity=4),
    ]
    cross_room_combination = [{
        "id": 55,
        "wersja_id": 7,
        "nazwa": "A1 + B1",
        "stoliki": [251, 252],
        "pojemnosc_min": 8,
        "pojemnosc_max": 8,
    }]

    explicit = evaluate_allocation(
        db,
        _request(liczba_osob=8),
        tables=tables,
        combinations=cross_room_combination,
        occupied_table_ids=set(),
        now=NOW,
    )
    automatic = evaluate_allocation(
        db,
        _request(liczba_osob=8),
        tables=tables,
        combinations=[],
        occupied_table_ids=set(),
        adjacency=[(251, 252)],
        now=NOW,
    )

    assert explicit.decision == "deny" and explicit.selected is None
    assert automatic.decision == "deny" and automatic.selected is None
    assert explicit.reasons[0].code == "NO_CAPACITY_MATCH"
    assert automatic.reasons[0].code == "NO_CAPACITY_MATCH"


def test_preferowana_sala_wygrywa_miekko_i_zwraca_alternatywe(db):
    _service(db)
    first = _room(db, "Pierwsza")
    preferred = _room(db, "Preferowana")
    tables = [
        _table(301, "P1", first, capacity=4),
        _table(302, "P2", preferred, capacity=4),
    ]

    result = evaluate_allocation(
        db,
        _request(liczba_osob=4, preferred_room_id=preferred.id),
        tables=tables,
        combinations=[],
        occupied_table_ids=set(),
        now=NOW,
    )

    assert result.selected is not None
    assert result.selected.room_id == preferred.id
    assert result.alternatives[0].room_id == first.id
    assert "PREFERRED_ROOM" in {reason.code for reason in result.reasons}


def test_nie_deklaruje_preferowanej_strefy_gdy_dostepny_jest_inny_stol(db):
    _service(db)
    preferred = _room(db, "Taras")
    fallback = _room(db, "Sala")
    tables = [
        _table(351, "T1", preferred, capacity=4),
        _table(352, "S1", fallback, capacity=4),
    ]

    result = evaluate_allocation(
        db,
        _request(liczba_osob=4, preferred_zone="Taras"),
        tables=tables,
        combinations=[],
        occupied_table_ids={351},
        now=NOW,
    )

    assert result.selected is not None
    assert result.selected.table_ids == (352,)
    assert "PREFERRED_ZONE" not in {reason.code for reason in result.reasons}


def test_zwraca_override_required_razem_z_kandydatem(db):
    _service(db, large_from=8, large_mode="do_zatwierdzenia")
    room = _room(db, "Duża Sala")
    tables = [_table(401 + index, f"D{index + 1}", room) for index in range(3)]
    combinations = [{
        "id": 61,
        "wersja_id": 7,
        "nazwa": "D1 + D2 + D3",
        "stoliki": [401, 402, 403],
        "pojemnosc_min": 18,
        "pojemnosc_max": 18,
    }]

    result = evaluate_allocation(
        db,
        _request(),
        tables=tables,
        combinations=combinations,
        occupied_table_ids=set(),
        now=NOW,
    )

    assert result.decision == "override_required"
    assert result.selected is not None
    assert result.to_dict()["can_override"] is True
    assert "LARGE_PARTY_APPROVAL_REQUIRED" in {
        reason.code for reason in result.reasons
    }


def test_twarda_regula_online_zwraca_deny_bez_rekomendacji(db):
    _service(db, large_from=8, large_mode="telefon")
    room = _room(db, "Sala Telefoniczna")
    tables = [_table(451 + index, f"T{index + 1}", room) for index in range(3)]
    combinations = [{
        "id": 71,
        "wersja_id": 7,
        "nazwa": "T1 + T2 + T3",
        "stoliki": [451, 452, 453],
        "pojemnosc_min": 18,
        "pojemnosc_max": 18,
    }]

    result = evaluate_allocation(
        db,
        _request(kanal="online"),
        tables=tables,
        combinations=combinations,
        occupied_table_ids=set(),
        now=NOW,
    )

    assert result.decision == "deny"
    assert result.selected is None
    assert result.code == "LARGE_PARTY_PHONE_ONLY"
    assert result.reasons[0].metadata == {"rule": "large_party"}


def test_publiczna_serializacja_redaguje_stoly_sale_i_nazwy(db):
    _service(db)
    room = _room(db, "Sala Prywatna")
    tables = [_table(501, "Sekretny stolik", room, capacity=4)]
    result = evaluate_allocation(
        db,
        _request(liczba_osob=4),
        tables=tables,
        combinations=[],
        occupied_table_ids=set(),
        now=NOW,
    )

    internal = result.to_dict(expose_exact=True)
    public = result.to_dict(expose_exact=False)

    assert internal["selected"]["table_ids"] == [501]
    assert internal["selected"]["room_id"] == room.id
    assert internal["allocation"]["room"] == {
        "id": room.id,
        "name": "Sala Prywatna",
    }
    assert internal["allocation"]["tables"] == [
        {"id": 501, "name": "Sekretny stolik"},
    ]
    assert public["selected"] == {"decision": "allow"}
    assert public["allocation"] == {
        "state": "preview",
        "visibility": "availability_only",
        "visit_end": "20:00",
    }
    assert "table_ids" not in public["selected"]
    assert "table_names" not in public["selected"]
    assert "room_id" not in public["selected"]
    assert "room_name" not in public["selected"]
    assert "name" not in public["selected"]
    assert public["candidates"] == [] and public["alternatives"] == []
    assert public["reasons"] == []
    assert public["checks"] == [] and public["applied_rules"] == []
    assert "buffer_min" not in public
    assert "koszt" not in internal["selected"]
