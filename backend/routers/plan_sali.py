"""Sale rezerwacyjne oraz wersjonowany, publikowany plan stolików (R2.1)."""

from collections import defaultdict
from datetime import date, datetime, time
import math
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import reservation_service
import schemas
import uprawnienia
from auth import get_current_user
from database import get_db
from deps import _teraz_lokalnie, modul_aktywny
from reservation_names import room_name_key

router = APIRouter()

_AKTYWNE = ("rezerwacja", "potwierdzona")
_SZEROKOSC_DOMYSLNA = 12
_WYSOKOSC_DOMYSLNA = 12
_ODSTEP_DOMYSLNY = 4
_SNAPSHOT_PROPS = (
    "nazwa", "kolejnosc", "pojemnosc", "pojemnosc_min",
    "ksztalt", "cechy", "priorytet", "sekcja",
)

# Te pola sa prawdziwie nullable w wersjonowanym kontrakcie. Dla nich jawne
# ``null`` oznacza wyczyszczenie, a brak pola w payloadzie zachowanie snapshotu.
_CLEARABLE_SNAPSHOT_PROPS = {"ksztalt", "cechy", "priorytet", "sekcja"}
_ROOM_NAME_CONFLICT = {
    "code": "ROOM_NAME_CONFLICT",
    "message": "Sala o tej nazwie już istnieje.",
}


def _wymagaj_modul_rezerwacje(db: Session = Depends(get_db)):
    if not modul_aktywny(db, "modul_rezerwacje"):
        raise HTTPException(
            403,
            "Moduł rezerwacji jest niedostępny w tym planie — odblokujesz go w pakiecie Pro.",
        )


def _teraz() -> datetime:
    return _teraz_lokalnie() or datetime.now()


def _dzis_lokalnie() -> date:
    return _teraz().date()


def _ids_stolikow(wartosci):
    if not isinstance(wartosci, (list, tuple, set)):
        return set()
    ids = set()
    for wartosc in wartosci:
        try:
            ids.add(int(wartosc))
        except (TypeError, ValueError):
            continue
    return ids


def _rez_out(t: models.Termin, user: models.User) -> dict:
    return {
        "id": t.id,
        "nazwisko": (
            t.nazwisko
            if uprawnienia.ma_user(user, "rezerwacje.dane_kontaktowe")
            else "Gość"
        ),
        "godz_od": t.godz_od.strftime("%H:%M") if t.godz_od else None,
        "godz_do": t.godz_do.strftime("%H:%M") if t.godz_do else None,
        "liczba_osob": t.liczba_osob,
        "status": t.status,
        "kanal": t.kanal,
    }


def _sala_or_404(db: Session, sala_id: int) -> models.SalaRezerwacyjna:
    sala = db.get(models.SalaRezerwacyjna, sala_id)
    if sala is None:
        raise HTTPException(404, "Brak sali rezerwacyjnej.")
    return sala


def _plan_dla_sali(db: Session, sala: models.SalaRezerwacyjna) -> models.PlanSali:
    plan = db.query(models.PlanSali).filter_by(sala_id=sala.id).first()
    if plan is None:
        plan = models.PlanSali(sala_id=sala.id, nazwa="Plan główny")
        db.add(plan)
        db.flush()
    return plan


def _istniejacy_plan(db: Session, sala_id: int):
    return db.query(models.PlanSali).filter_by(sala_id=sala_id).first()


def _wersja(db: Session, plan_id: int, status: str):
    return (
        db.query(models.WersjaPlanuSali)
        .filter_by(plan_id=plan_id, status=status)
        .order_by(models.WersjaPlanuSali.numer.desc())
        .first()
    )


def _meta_wersji(wersja):
    if wersja is None:
        return None
    return {
        "id": wersja.id,
        "numer": wersja.numer,
        "status": wersja.status,
        "rewizja": wersja.rewizja,
    }


def _stoliki_sali(db: Session, sala: models.SalaRezerwacyjna):
    """Relacja jest źródłem prawdy; nazwa strefy obsługuje niezmigrowane rekordy."""
    nazwa = (sala.nazwa or "").strip().casefold()
    rows = db.query(models.Stolik).order_by(models.Stolik.kolejnosc, models.Stolik.id).all()
    return [
        stolik
        for stolik in rows
        if stolik.sala_id == sala.id
        or (
            stolik.sala_id is None
            and (stolik.strefa or "").strip().casefold() == nazwa
        )
    ]


def _sala_out(db: Session, sala: models.SalaRezerwacyjna):
    plan = db.query(models.PlanSali).filter_by(sala_id=sala.id).first()
    published = _wersja(db, plan.id, "published") if plan else None
    draft = _wersja(db, plan.id, "draft") if plan else None
    return {
        "id": sala.id,
        "nazwa": sala.nazwa,
        "aktywna": sala.aktywna,
        "kolejnosc": sala.kolejnosc,
        "plan_id": plan.id if plan else None,
        "liczba_stolikow": len(_stoliki_sali(db, sala)),
        "wersja_opublikowana": _meta_wersji(published),
        "szkic": _meta_wersji(draft),
    }


def _domyslna_geometria(stolik, index: int, count: int = 1):
    columns = max(1, math.ceil(math.sqrt(max(1, count) * 1.6)))
    rows = max(1, math.ceil(max(1, count) / columns))
    fallback_x = round((((index % columns) + 0.5) / columns) * 84 + 8)
    fallback_y = round(((math.floor(index / columns) + 0.5) / rows) * 84 + 8)
    return {
        "plan_x": stolik.plan_x if stolik.plan_x is not None else fallback_x,
        "plan_y": stolik.plan_y if stolik.plan_y is not None else fallback_y,
        "szerokosc": _SZEROKOSC_DOMYSLNA,
        "wysokosc": _WYSOKOSC_DOMYSLNA,
        "obrot": 0,
        "aktywny_w_planie": bool(stolik.aktywny),
    }


def _polowy_obwiedni(source):
    """Polowy osiowej obwiedni prostokata po uwzglednieniu obrotu."""
    width = float(_wartosc(source, "szerokosc", _SZEROKOSC_DOMYSLNA))
    height = float(_wartosc(source, "wysokosc", _WYSOKOSC_DOMYSLNA))
    angle = math.radians(float(_wartosc(source, "obrot", 0) or 0))
    cosine, sine = abs(math.cos(angle)), abs(math.sin(angle))
    return (
        (width * cosine + height * sine) / 2,
        (width * sine + height * cosine) / 2,
    )


def _miejsce_wolne(candidate, existing, gap: int = _ODSTEP_DOMYSLNY):
    candidate_half_x, candidate_half_y = _polowy_obwiedni(candidate)
    for position in existing:
        existing_half_x, existing_half_y = _polowy_obwiedni(position)
        if (
            abs(candidate["plan_x"] - position.plan_x)
            < candidate_half_x + existing_half_x + gap
            and abs(candidate["plan_y"] - position.plan_y)
            < candidate_half_y + existing_half_y + gap
        ):
            return False
    return True


def _domyslna_geometria_bez_kolizji(db: Session, draft_id: int, stolik, index, count):
    """Zachowuje preferowany punkt albo znajduje najblizsze wolne pole stalej siatki."""
    preferred = _domyslna_geometria(stolik, index, count)
    existing = db.query(models.PozycjaStolikaPlanu).filter_by(
        wersja_id=draft_id,
    ).all()
    if _miejsce_wolne(preferred, existing):
        return preferred

    half_x, half_y = _polowy_obwiedni(preferred)
    min_x, max_x = math.ceil(half_x), math.floor(100 - half_x)
    min_y, max_y = math.ceil(half_y), math.floor(100 - half_y)

    # Stala siatka 6x6 daje stolom 12% co najmniej 4 p.p. odstepu.
    grid_axis = range(8, 93, 16)
    grid = [
        (x, y)
        for y in grid_axis
        for x in grid_axis
        if min_x <= x <= max_x and min_y <= y <= max_y
    ]
    grid.sort(key=lambda point: (
        (point[0] - preferred["plan_x"]) ** 2
        + (point[1] - preferred["plan_y"]) ** 2,
        point[1],
        point[0],
    ))
    for x, y in grid:
        candidate = {**preferred, "plan_x": x, "plan_y": y}
        if _miejsce_wolne(candidate, existing):
            return candidate

    # Nietypowo duze/obrocone elementy moga nie pasowac do stalej siatki.
    dense = [
        (x, y)
        for y in range(min_y, max_y + 1, 2)
        for x in range(min_x, max_x + 1, 2)
    ]
    dense.sort(key=lambda point: (
        (point[0] - preferred["plan_x"]) ** 2
        + (point[1] - preferred["plan_y"]) ** 2,
        point[1],
        point[0],
    ))
    for x, y in dense:
        candidate = {**preferred, "plan_x": x, "plan_y": y}
        if _miejsce_wolne(candidate, existing):
            return candidate

    raise HTTPException(
        409,
        detail={
            "code": "FLOOR_PLAN_NO_SPACE",
            "message": "Brak wolnego miejsca na kolejny stolik w szkicu.",
        },
    )


def _wartosc(source, field, default=None):
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(field, default)
    return getattr(source, field, default)


def _wlasciwosci_snapshotu(stolik, source=None, incoming=None):
    """Rozwiazuje pola R2.2 z rozroznieniem braku pola i jawnego ``null``."""
    out = {}
    for field in _SNAPSHOT_PROPS:
        incoming_fields = getattr(incoming, "model_fields_set", None)
        incoming_has_field = (
            field in incoming
            if isinstance(incoming, dict)
            else incoming_fields is not None and field in incoming_fields
        )
        if incoming_has_field:
            value = _wartosc(incoming, field)
            if value is not None or field in _CLEARABLE_SNAPSHOT_PROPS:
                out[field] = list(value) if field == "cechy" and value is not None else value
                continue

        if source is not None:
            value = _wartosc(source, field)
            if value is not None or field in _CLEARABLE_SNAPSHOT_PROPS:
                out[field] = list(value) if field == "cechy" and value is not None else value
                continue

        value = getattr(stolik, field, None)
        if field == "cechy" and value is not None:
            value = list(value)
        out[field] = value
    return out


def _stoliki_wersji(db: Session, sala, wersja):
    if wersja is None:
        # Brak opublikowanej wersji nie oznacza zgody na legacy fallback.
        # W szczególności rekordy utworzone wyłącznie w pierwszym szkicu
        # pozostają niewidoczne dla hosta aż do atomowej publikacji.
        return []
    stoliki = _stoliki_sali(db, sala)
    pozycje = {
        pozycja.stolik_id: pozycja
        for pozycja in (
            db.query(models.PozycjaStolikaPlanu)
            .filter_by(wersja_id=wersja.id)
            .all()
        )
    }
    if getattr(wersja, "status", None) == "published":
        # Nowy, jeszcze nieopublikowany stół nie może domieszać się do
        # działającego planu tylko dlatego, że ma już stabilny rekord.
        stoliki = [stolik for stolik in stoliki if stolik.id in pozycje]
    by_id = {stolik.id: stolik for stolik in stoliki}
    out = []
    for index, stolik in enumerate(stoliki):
        pozycja = pozycje.get(stolik.id)
        geometria = (
            {
                "plan_x": pozycja.plan_x,
                "plan_y": pozycja.plan_y,
                "szerokosc": pozycja.szerokosc,
                "wysokosc": pozycja.wysokosc,
                "obrot": pozycja.obrot,
                "aktywny_w_planie": pozycja.aktywny_w_planie,
            }
            if pozycja is not None
            else _domyslna_geometria(stolik, index, len(stoliki))
        )
        wlasciwosci = _wlasciwosci_snapshotu(stolik, pozycja)
        out.append({
            "id": stolik.id,
            **wlasciwosci,
            **geometria,
        })
    out.sort(key=lambda row: (
        row["kolejnosc"] if row["kolejnosc"] is not None else 2**31,
        row["id"],
    ))
    # Uszkodzona/osierocona pozycja nie może wyciec do kontraktu ani blokować odczytu.
    assert set(by_id) == {row["id"] for row in out}
    return out


def _krawedzie_wersji(db: Session, wersja):
    if wersja is None:
        return []
    return [
        {"stolik_a_id": row.stolik_a_id, "stolik_b_id": row.stolik_b_id}
        for row in db.query(models.KrawedzSasiedztwaPlanu).filter_by(
            wersja_id=wersja.id,
        ).order_by(
            models.KrawedzSasiedztwaPlanu.stolik_a_id,
            models.KrawedzSasiedztwaPlanu.stolik_b_id,
        ).all()
    ]


def _kombinacje_wersji(db: Session, wersja):
    if wersja is None:
        return []
    rows = db.query(models.KombinacjaStolowPlanu).filter_by(
        wersja_id=wersja.id,
    ).order_by(
        models.KombinacjaStolowPlanu.priorytet,
        models.KombinacjaStolowPlanu.id,
    ).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    skladniki = defaultdict(list)
    for skladnik in db.query(models.SkladnikKombinacjiPlanu).filter(
        models.SkladnikKombinacjiPlanu.kombinacja_id.in_(ids),
    ).order_by(
        models.SkladnikKombinacjiPlanu.kombinacja_id,
        models.SkladnikKombinacjiPlanu.stolik_id,
    ).all():
        skladniki[skladnik.kombinacja_id].append(skladnik.stolik_id)
    return [
        {
            "id": row.id,
            "nazwa": row.nazwa,
            "stoliki": skladniki[row.id],
            "pojemnosc_min": row.pojemnosc_min,
            "pojemnosc_max": row.pojemnosc_max,
            "priorytet": row.priorytet,
            "kanal": row.kanal,
            "aktywna_w_planie": row.aktywna_w_planie,
        }
        for row in rows
    ]


def _plan_out(db: Session, sala, wersja):
    return {
        "sala": {
            "id": sala.id,
            "nazwa": sala.nazwa,
            "aktywna": sala.aktywna,
            "kolejnosc": sala.kolejnosc,
        },
        "wersja": _meta_wersji(wersja),
        "stoliki": _stoliki_wersji(db, sala, wersja),
        "krawedzie": _krawedzie_wersji(db, wersja),
        "kombinacje": _kombinacje_wersji(db, wersja),
    }


def _revision_conflict(wersja):
    raise HTTPException(
        409,
        detail={
            "code": "PLAN_REVISION_CONFLICT",
            "message": "Szkic został zmieniony w innej sesji. Odśwież plan i spróbuj ponownie.",
            "current_revision": getattr(wersja, "rewizja", None),
        },
    )


def _waliduj_pelny_snapshot(db: Session, sala, pozycje):
    ids = [int(_wartosc(pozycja, "stolik_id")) for pozycja in pozycje]
    oczekiwane = {stolik.id for stolik in _stoliki_sali(db, sala)}
    if len(ids) != len(set(ids)) or set(ids) != oczekiwane:
        raise HTTPException(
            422,
            detail={
                "code": "PLAN_SNAPSHOT_INVALID",
                "message": "Szkic musi zawierać każdy stolik sali dokładnie raz.",
                "missing_table_ids": sorted(oczekiwane - set(ids)),
                "unexpected_table_ids": sorted(set(ids) - oczekiwane),
            },
        )
    nazwy = {}
    for pozycja in pozycje:
        nazwa = (_wartosc(pozycja, "nazwa") or "").strip()
        name_key = nazwa.casefold()
        if name_key and name_key in nazwy:
            raise HTTPException(
                422,
                detail={
                    "code": "PLAN_TABLE_NAME_CONFLICT",
                    "message": "Nazwy stolikow w jednej sali musza byc unikalne.",
                    "table_ids": sorted([
                        nazwy[name_key], int(_wartosc(pozycja, "stolik_id")),
                    ]),
                },
            )
        if name_key:
            nazwy[name_key] = int(_wartosc(pozycja, "stolik_id"))
        pojemnosc = _wartosc(pozycja, "pojemnosc")
        minimum = _wartosc(pozycja, "pojemnosc_min")
        if not nazwa or pojemnosc is None or int(pojemnosc) < 1:
            raise HTTPException(
                422,
                detail={
                    "code": "PLAN_TABLE_PROPERTIES_INVALID",
                    "message": "KaĹĽdy stolik snapshotu musi mieÄ‡ nazwÄ™ i dodatniÄ… pojemnoĹ›Ä‡.",
                    "table_id": pozycja.stolik_id if hasattr(pozycja, "stolik_id") else pozycja["stolik_id"],
                },
            )
        if minimum is not None and (
            int(minimum) < 1 or int(minimum) > int(pojemnosc)
        ):
            raise HTTPException(
                422,
                detail={
                    "code": "PLAN_TABLE_CAPACITY_INVALID",
                    "message": "Minimalna liczba osĂłb nie moĹĽe przekraczaÄ‡ pojemnoĹ›ci stolika.",
                    "table_id": pozycja.stolik_id if hasattr(pozycja, "stolik_id") else pozycja["stolik_id"],
                },
            )


def _topology_error(message, **extra):
    raise HTTPException(
        422,
        detail={"code": "PLAN_TOPOLOGY_INVALID", "message": message, **extra},
    )


def _waliduj_topologie(pozycje, krawedzie, kombinacje):
    """Normalizuje caĹ‚Ä… topologiÄ™ i zwraca dane gotowe do atomowego zapisu."""
    pozycje_by_id = {
        int(_wartosc(row, "stolik_id")): row for row in pozycje
    }
    table_ids = set(pozycje_by_id)

    normalized_edges = []
    edge_keys = set()
    for edge in krawedzie or []:
        raw_a = int(_wartosc(edge, "stolik_a_id"))
        raw_b = int(_wartosc(edge, "stolik_b_id"))
        if raw_a == raw_b:
            _topology_error("KrawÄ™dĹş musi Ĺ‚Ä…czyÄ‡ dwa rĂłĹĽne stoliki.", table_ids=[raw_a])
        a, b = sorted((raw_a, raw_b))
        if a not in table_ids or b not in table_ids:
            _topology_error(
                "KrawÄ™dĹş nie moĹĽe Ĺ‚Ä…czyÄ‡ stolikĂłw spoza tej sali.",
                table_ids=[a, b],
            )
        key = (a, b)
        if key in edge_keys:
            _topology_error("Ta para stolikĂłw wystÄ™puje w grafie wiÄ™cej niĹĽ raz.", table_ids=[a, b])
        edge_keys.add(key)
        normalized_edges.append({"stolik_a_id": a, "stolik_b_id": b})
    normalized_edges.sort(key=lambda row: (row["stolik_a_id"], row["stolik_b_id"]))

    adjacency = defaultdict(set)
    for a, b in edge_keys:
        adjacency[a].add(b)
        adjacency[b].add(a)

    normalized_combinations = []
    combination_keys = set()
    for combination in kombinacje or []:
        ids = sorted(int(value) for value in (_wartosc(combination, "stoliki") or []))
        if len(ids) < 2 or len(ids) != len(set(ids)):
            _topology_error("Kombinacja musi zawieraÄ‡ co najmniej dwa rĂłĽne stoliki.", table_ids=ids)
        missing = sorted(set(ids) - table_ids)
        if missing:
            _topology_error(
                "Kombinacja nie moĹĽe zawieraÄ‡ stolikĂłw spoza tej sali.",
                table_ids=missing,
            )
        key = ",".join(str(value) for value in ids)
        if key in combination_keys:
            _topology_error("Ten sam zestaw stolikĂłw wystÄ™puje wiÄ™cej niĹĽ raz.", table_ids=ids)
        combination_keys.add(key)

        member_set = set(ids)
        visited = {ids[0]}
        pending = [ids[0]]
        while pending:
            current = pending.pop()
            for neighbour in adjacency[current] & member_set:
                if neighbour not in visited:
                    visited.add(neighbour)
                    pending.append(neighbour)
        if visited != member_set:
            _topology_error("Kombinacja musi byÄ‡ spĂłjna w grafie sÄ…siedztwa.", table_ids=ids)

        active = bool(_wartosc(combination, "aktywna_w_planie", True))
        inactive = [
            table_id for table_id in ids
            if not bool(_wartosc(pozycje_by_id[table_id], "aktywny_w_planie", True))
        ]
        if active and inactive:
            _topology_error(
                "Aktywna kombinacja moĹĽe zawieraÄ‡ wyĹ‚Ä…cznie aktywne stoliki.",
                table_ids=inactive,
            )
        physical_capacity = sum(
            int(_wartosc(pozycje_by_id[table_id], "pojemnosc") or 0)
            for table_id in ids
        )
        raw_minimum = _wartosc(combination, "pojemnosc_min")
        raw_maximum = _wartosc(combination, "pojemnosc_max")
        minimum = 1 if raw_minimum is None else int(raw_minimum)
        maximum = physical_capacity if raw_maximum is None else int(raw_maximum)
        if (
            physical_capacity < 1
            or minimum < 1
            or maximum < minimum
            or maximum > physical_capacity
        ):
            _topology_error("Kombinacja ma nieprawidĹ‚owy zakres pojemnoĹ›ci.", table_ids=ids)
        name = str(_wartosc(combination, "nazwa") or "").strip()
        if not name:
            _topology_error("Kombinacja musi mieÄ‡ nazwÄ™.", table_ids=ids)
        channel = _wartosc(combination, "kanal", "oba") or "oba"
        if channel not in {"online", "wewnetrzna", "oba"}:
            _topology_error("Kombinacja ma nieznany kanaĹ‚.", table_ids=ids)
        normalized_combinations.append({
            "nazwa": name,
            "stoliki": ids,
            "sklad_klucz": key,
            "pojemnosc_min": minimum,
            "pojemnosc_max": maximum,
            "priorytet": int(_wartosc(combination, "priorytet", 0) or 0),
            "kanal": channel,
            "aktywna_w_planie": active,
        })
    normalized_combinations.sort(
        key=lambda row: (row["priorytet"], row["sklad_klucz"]),
    )
    return normalized_edges, normalized_combinations


def _dodaj_pozycje(db: Session, wersja_id: int, pozycje):
    for pozycja in pozycje:
        dane = pozycja.model_dump() if hasattr(pozycja, "model_dump") else dict(pozycja)
        db.add(models.PozycjaStolikaPlanu(wersja_id=wersja_id, **dane))


def _dodaj_topologie(db: Session, wersja_id: int, krawedzie, kombinacje):
    for edge in krawedzie:
        db.add(models.KrawedzSasiedztwaPlanu(wersja_id=wersja_id, **edge))
    for payload in kombinacje:
        ids = payload["stoliki"]
        combination = models.KombinacjaStolowPlanu(
            wersja_id=wersja_id,
            **{key: value for key, value in payload.items() if key != "stoliki"},
        )
        db.add(combination)
        db.flush()
        for table_id in ids:
            db.add(models.SkladnikKombinacjiPlanu(
                kombinacja_id=combination.id,
                wersja_id=wersja_id,
                stolik_id=table_id,
            ))


def _kopiuj_topologie(db: Session, source_id: int, target_id: int):
    edges = _krawedzie_wersji(db, db.get(models.WersjaPlanuSali, source_id))
    combinations = _kombinacje_wersji(db, db.get(models.WersjaPlanuSali, source_id))
    normalized = []
    for combination in combinations:
        normalized.append({
            **{key: value for key, value in combination.items() if key != "id"},
            "sklad_klucz": ",".join(str(value) for value in combination["stoliki"]),
        })
    _dodaj_topologie(db, target_id, edges, normalized)


def _pozycje_startowe(db: Session, sala, published):
    by_id = {
        pozycja.stolik_id: pozycja
        for pozycja in (
            db.query(models.PozycjaStolikaPlanu)
            .filter_by(wersja_id=published.id)
            .all()
            if published else []
        )
    }
    out = []
    stoliki = _stoliki_sali(db, sala)
    for index, stolik in enumerate(stoliki):
        source = by_id.get(stolik.id)
        geometria = (
            {
                "plan_x": source.plan_x,
                "plan_y": source.plan_y,
                "szerokosc": source.szerokosc,
                "wysokosc": source.wysokosc,
                "obrot": source.obrot,
                "aktywny_w_planie": source.aktywny_w_planie,
            }
            if source else _domyslna_geometria(stolik, index, len(stoliki))
        )
        out.append({
            "stolik_id": stolik.id,
            **geometria,
            **_wlasciwosci_snapshotu(stolik, source),
        })
    return out


def _sprawdz_ids_pelnego_snapshotu(db: Session, sala, pozycje):
    ids = [int(_wartosc(pozycja, "stolik_id")) for pozycja in pozycje]
    expected = {stolik.id for stolik in _stoliki_sali(db, sala)}
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise HTTPException(
            422,
            detail={
                "code": "PLAN_SNAPSHOT_INVALID",
                "message": "Szkic musi zawieraÄ‡ kaĹĽdy stolik sali dokĹ‚adnie raz.",
                "missing_table_ids": sorted(expected - set(ids)),
                "unexpected_table_ids": sorted(set(ids) - expected),
            },
        )


def _rozwiaz_pozycje_payloadu(db: Session, sala, wersja, pozycje):
    _sprawdz_ids_pelnego_snapshotu(db, sala, pozycje)
    current = {
        row.stolik_id: row
        for row in db.query(models.PozycjaStolikaPlanu).filter_by(
            wersja_id=wersja.id,
        ).all()
    }
    tables = {stolik.id: stolik for stolik in _stoliki_sali(db, sala)}
    out = []
    for incoming in pozycje:
        table_id = int(incoming.stolik_id)
        source = current.get(table_id)
        out.append({
            "stolik_id": table_id,
            "plan_x": incoming.plan_x,
            "plan_y": incoming.plan_y,
            "szerokosc": incoming.szerokosc,
            "wysokosc": incoming.wysokosc,
            "obrot": incoming.obrot,
            "aktywny_w_planie": incoming.aktywny_w_planie,
            **_wlasciwosci_snapshotu(tables[table_id], source, incoming),
        })
    _waliduj_pelny_snapshot(db, sala, out)
    return out


def _snapshot_z_bazy(db: Session, sala, wersja):
    tables = {stolik.id: stolik for stolik in _stoliki_sali(db, sala)}
    rows = db.query(models.PozycjaStolikaPlanu).filter_by(
        wersja_id=wersja.id,
    ).order_by(models.PozycjaStolikaPlanu.stolik_id).all()
    _sprawdz_ids_pelnego_snapshotu(db, sala, rows)
    out = []
    for row in rows:
        stolik = tables.get(row.stolik_id)
        if stolik is None:
            # PeĹ‚na walidacja poniĹĽej zwrĂłci kontrolowany bĹ‚Ä…d brakujÄ…cego/obcego ID.
            continue
        out.append({
            "stolik_id": row.stolik_id,
            "plan_x": row.plan_x,
            "plan_y": row.plan_y,
            "szerokosc": row.szerokosc,
            "wysokosc": row.wysokosc,
            "obrot": row.obrot,
            "aktywny_w_planie": row.aktywny_w_planie,
            **_wlasciwosci_snapshotu(stolik, row),
        })
    _waliduj_pelny_snapshot(db, sala, out)
    return out


def _konflikty_dezaktywacji(db: Session, stoliki_ids):
    ids = set(stoliki_ids)
    if not ids:
        return [], []
    future = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.data >= _dzis_lokalnie(),
        models.Termin.status.in_(_AKTYWNE),
    ).all()
    reservation_ids = []
    for termin in future:
        zajete = _ids_stolikow(termin.stoliki_dodatkowe)
        if termin.stolik_id:
            zajete.add(termin.stolik_id)
        if ids & zajete:
            reservation_ids.append(termin.id)
    hold_ids = [
        claim.id
        for claim in db.query(models.RezerwacjaStolikClaim).filter(
            models.RezerwacjaStolikClaim.stolik_id.in_(ids),
            models.RezerwacjaStolikClaim.waitlist_id.isnot(None),
            models.RezerwacjaStolikClaim.expires_at > _teraz(),
        ).all()
    ]
    return sorted(set(reservation_ids)), sorted(set(hold_ids))


def _konflikty_redukcji_pojemnosci(db: Session, pojemnosci):
    """Chroni istniejace przydzialy; edycja szkicu pozostaje dozwolona."""
    room_ids = set(pojemnosci)
    if not room_ids:
        return [], [], []
    live_capacity = {
        table_id: int(capacity or 0)
        for table_id, capacity in db.query(
            models.Stolik.id, models.Stolik.pojemnosc,
        ).all()
    }

    def assigned_capacity(table_ids):
        return sum(
            int(pojemnosci.get(table_id, live_capacity.get(table_id, 0)) or 0)
            for table_id in table_ids
        )

    reservation_ids = set()
    conflict_table_ids = set()
    reservations = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.data >= _dzis_lokalnie(),
        models.Termin.status.in_(_AKTYWNE),
    ).all()
    for reservation in reservations:
        table_ids = _ids_stolikow(reservation.stoliki_dodatkowe)
        if reservation.stolik_id:
            table_ids.add(reservation.stolik_id)
        people = int(reservation.liczba_osob or 0)
        if table_ids & room_ids and people > assigned_capacity(table_ids):
            reservation_ids.add(reservation.id)
            conflict_table_ids.update(table_ids & room_ids)

    claims = db.query(models.RezerwacjaStolikClaim).filter(
        models.RezerwacjaStolikClaim.waitlist_id.isnot(None),
        models.RezerwacjaStolikClaim.expires_at > _teraz(),
    ).all()
    claims_by_waitlist = defaultdict(list)
    for claim in claims:
        claims_by_waitlist[claim.waitlist_id].append(claim)
    hold_ids = set()
    if claims_by_waitlist:
        waitlist_rows = db.query(models.ListaOczekujacych).filter(
            models.ListaOczekujacych.id.in_(claims_by_waitlist),
            models.ListaOczekujacych.status == "oczekuje",
        ).all()
        for waitlist in waitlist_rows:
            owned_claims = claims_by_waitlist[waitlist.id]
            table_ids = {claim.stolik_id for claim in owned_claims}
            people = int(waitlist.liczba_osob or 0)
            if table_ids & room_ids and people > assigned_capacity(table_ids):
                hold_ids.update(claim.id for claim in owned_claims)
                conflict_table_ids.update(table_ids & room_ids)

    return (
        sorted(reservation_ids),
        sorted(hold_ids),
        sorted(conflict_table_ids),
    )


def _nowe_nieaktywne_stoliki_szkicu(db: Session, draft_id: int):
    """Stoły utworzone wyłącznie w tym szkicu, które można usunąć z nim bez historii."""
    ids = {
        stolik_id
        for (stolik_id,) in db.query(models.PozycjaStolikaPlanu.stolik_id).filter_by(
            wersja_id=draft_id,
        ).all()
    }
    if not ids:
        return []
    ids_z_innej_wersji = {
        stolik_id
        for (stolik_id,) in db.query(models.PozycjaStolikaPlanu.stolik_id).filter(
            models.PozycjaStolikaPlanu.stolik_id.in_(ids),
            models.PozycjaStolikaPlanu.wersja_id != draft_id,
        ).distinct().all()
    }
    chronione = set(ids_z_innej_wersji)
    chronione.update(
        stolik_id
        for (stolik_id,) in db.query(models.Termin.stolik_id).filter(
            models.Termin.stolik_id.in_(ids),
        ).distinct().all()
    )
    chronione.update(
        stolik_id
        for (stolik_id,) in db.query(models.RezerwacjaStolikClaim.stolik_id).filter(
            models.RezerwacjaStolikClaim.stolik_id.in_(ids),
        ).distinct().all()
    )
    for (wartosci,) in db.query(models.Termin.stoliki_dodatkowe).filter(
        models.Termin.stoliki_dodatkowe.isnot(None),
    ).all():
        chronione.update(ids & _ids_stolikow(wartosci))
    for (wartosci,) in db.query(models.KombinacjaStolow.stoliki).all():
        chronione.update(ids & _ids_stolikow(wartosci))
    return [
        stolik for stolik in db.query(models.Stolik).filter(
            models.Stolik.id.in_(ids - chronione),
            models.Stolik.aktywny.is_(False),
        ).all()
    ]


@router.get(
    "/api/sale-rezerwacyjne",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def get_sale_rezerwacyjne(db: Session = Depends(get_db)):
    sale = db.query(models.SalaRezerwacyjna).order_by(
        models.SalaRezerwacyjna.kolejnosc, models.SalaRezerwacyjna.id,
    ).all()
    return {"sale": [_sala_out(db, sala) for sala in sale]}


@router.post(
    "/api/sale-rezerwacyjne",
    status_code=201,
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def dodaj_sale_rezerwacyjna(
    dane: schemas.SalaRezerwacyjnaIn,
    db: Session = Depends(get_db),
):
    name_key = room_name_key(dane.nazwa)
    duplicate = db.query(models.SalaRezerwacyjna).filter_by(
        nazwa_klucz=name_key,
    ).first()
    if duplicate:
        raise HTTPException(409, detail=_ROOM_NAME_CONFLICT)
    sala = models.SalaRezerwacyjna(
        **dane.model_dump(),
        nazwa_klucz=name_key,
    )
    db.add(sala)
    try:
        db.flush()
        _plan_dla_sali(db, sala)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail=_ROOM_NAME_CONFLICT) from exc
    db.refresh(sala)
    return _sala_out(db, sala)


@router.put(
    "/api/sale-rezerwacyjne/{sala_id}",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def edytuj_sale_rezerwacyjna(
    sala_id: int,
    dane: schemas.SalaRezerwacyjnaIn,
    db: Session = Depends(get_db),
):
    sala = _sala_or_404(db, sala_id)
    name_key = room_name_key(dane.nazwa)
    duplicate = db.query(models.SalaRezerwacyjna).filter(
        models.SalaRezerwacyjna.id != sala.id,
        models.SalaRezerwacyjna.nazwa_klucz == name_key,
    ).first()
    if duplicate:
        raise HTTPException(409, detail=_ROOM_NAME_CONFLICT)
    for key, value in dane.model_dump().items():
        setattr(sala, key, value)
    sala.nazwa_klucz = name_key
    for stolik in db.query(models.Stolik).filter_by(sala_id=sala.id).all():
        stolik.strefa = sala.nazwa
    _plan_dla_sali(db, sala)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail=_ROOM_NAME_CONFLICT) from exc
    db.refresh(sala)
    return _sala_out(db, sala)


@router.get(
    "/api/sale-rezerwacyjne/{sala_id}/plan",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def get_opublikowany_plan(sala_id: int, db: Session = Depends(get_db)):
    sala = _sala_or_404(db, sala_id)
    plan = _istniejacy_plan(db, sala.id)
    published = _wersja(db, plan.id, "published") if plan else None
    return _plan_out(db, sala, published)


@router.get(
    "/api/sale-rezerwacyjne/{sala_id}/plan/szkic",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def get_szkic_planu(sala_id: int, db: Session = Depends(get_db)):
    sala = _sala_or_404(db, sala_id)
    plan = _istniejacy_plan(db, sala.id)
    return _plan_out(db, sala, _wersja(db, plan.id, "draft") if plan else None)


@router.post(
    "/api/sale-rezerwacyjne/{sala_id}/plan/szkic",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def utworz_szkic_planu(
    sala_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sala = _sala_or_404(db, sala_id)
    plan = _plan_dla_sali(db, sala)
    existing = _wersja(db, plan.id, "draft")
    if existing is not None:
        return _plan_out(db, sala, existing)
    published = _wersja(db, plan.id, "published")
    max_numer = db.query(func.max(models.WersjaPlanuSali.numer)).filter_by(plan_id=plan.id).scalar()
    now = _teraz()
    draft = models.WersjaPlanuSali(
        plan_id=plan.id,
        numer=(max_numer or 0) + 1,
        status="draft",
        rewizja=0,
        autor_id=getattr(user, "id", None),
        utworzono_at=now,
        zaktualizowano_at=now,
    )
    db.add(draft)
    try:
        db.flush()
        _dodaj_pozycje(db, draft.id, _pozycje_startowe(db, sala, published))
        db.flush()
        if published is not None:
            _kopiuj_topologie(db, published.id, draft.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _wersja(db, plan.id, "draft")
        if existing is None:
            raise
        draft = existing
    db.refresh(draft)
    return _plan_out(db, sala, draft)


@router.put(
    "/api/sale-rezerwacyjne/{sala_id}/plan/szkic",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def zapisz_szkic_planu(
    sala_id: int,
    dane: schemas.SzkicPlanuSaliIn,
    db: Session = Depends(get_db),
):
    sala = _sala_or_404(db, sala_id)
    plan = _istniejacy_plan(db, sala.id)
    if plan is None:
        raise HTTPException(404, "Brak szkicu planu.")
    draft = _wersja(db, plan.id, "draft")
    if draft is None:
        raise HTTPException(404, "Brak szkicu planu.")
    if draft.rewizja != dane.expected_revision:
        _revision_conflict(draft)
    pozycje = _rozwiaz_pozycje_payloadu(db, sala, draft, dane.pozycje)
    istniejace_krawedzie = _krawedzie_wersji(db, draft)
    istniejace_kombinacje = _kombinacje_wersji(db, draft)
    krawedzie, kombinacje = _waliduj_topologie(
        pozycje,
        istniejace_krawedzie if dane.krawedzie is None else dane.krawedzie,
        istniejace_kombinacje if dane.kombinacje is None else dane.kombinacje,
    )
    now = _teraz()
    claimed = db.query(models.WersjaPlanuSali).filter(
        models.WersjaPlanuSali.id == draft.id,
        models.WersjaPlanuSali.status == "draft",
        models.WersjaPlanuSali.rewizja == dane.expected_revision,
    ).update(
        {
            models.WersjaPlanuSali.rewizja: dane.expected_revision + 1,
            models.WersjaPlanuSali.zaktualizowano_at: now,
        },
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        _revision_conflict(_wersja(db, plan.id, "draft"))
    try:
        pozycje_by_id = {
            row.stolik_id: row
            for row in db.query(models.PozycjaStolikaPlanu).filter_by(
                wersja_id=draft.id,
            ).all()
        }
        for payload in pozycje:
            row = pozycje_by_id[payload["stolik_id"]]
            for field, value in payload.items():
                if field != "stolik_id":
                    setattr(row, field, value)

        if dane.krawedzie is not None:
            db.query(models.KrawedzSasiedztwaPlanu).filter_by(
                wersja_id=draft.id,
            ).delete(synchronize_session=False)
        if dane.kombinacje is not None:
            db.query(models.SkladnikKombinacjiPlanu).filter_by(
                wersja_id=draft.id,
            ).delete(synchronize_session=False)
            db.query(models.KombinacjaStolowPlanu).filter_by(
                wersja_id=draft.id,
            ).delete(synchronize_session=False)

        _dodaj_topologie(
            db,
            draft.id,
            krawedzie if dane.krawedzie is not None else [],
            kombinacje if dane.kombinacje is not None else [],
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            422,
            detail={
                "code": "PLAN_TOPOLOGY_INVALID",
                "message": "Nie mozna zapisac niespojnej topologii planu.",
            },
        ) from exc
    draft = db.get(models.WersjaPlanuSali, draft.id)
    return _plan_out(db, sala, draft)


@router.post(
    "/api/sale-rezerwacyjne/{sala_id}/plan/szkic/stoliki",
    status_code=201,
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def dodaj_stolik_do_szkicu(
    sala_id: int,
    dane: schemas.NowyStolikSzkicuIn,
    db: Session = Depends(get_db),
):
    """Atomowo dodaje nieaktywny rekord stołu i jego aktywną pozycję w szkicu."""
    sala = _sala_or_404(db, sala_id)
    plan = _plan_dla_sali(db, sala)
    draft = _wersja(db, plan.id, "draft")
    if draft is None:
        raise HTTPException(404, "Brak szkicu planu.")
    if draft.rewizja != dane.expected_revision:
        _revision_conflict(draft)
    duplicate = next(
        (
            stolik for stolik in _stoliki_sali(db, sala)
            if (stolik.nazwa or "").strip().casefold() == dane.nazwa.casefold()
        ),
        None,
    )
    if duplicate is not None:
        raise HTTPException(
            409,
            detail={
                "code": "TABLE_NAME_CONFLICT",
                "message": "W tej sali istnieje już stół o tej nazwie.",
            },
        )
    now = _teraz()
    claimed = db.query(models.WersjaPlanuSali).filter(
        models.WersjaPlanuSali.id == draft.id,
        models.WersjaPlanuSali.status == "draft",
        models.WersjaPlanuSali.rewizja == dane.expected_revision,
    ).update(
        {
            models.WersjaPlanuSali.rewizja: dane.expected_revision + 1,
            models.WersjaPlanuSali.zaktualizowano_at: now,
        },
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        _revision_conflict(_wersja(db, plan.id, "draft"))
    stoliki = _stoliki_sali(db, sala)
    stolik = models.Stolik(
        nazwa=dane.nazwa,
        sala_id=sala.id,
        strefa=sala.nazwa,
        pojemnosc=dane.pojemnosc,
        pojemnosc_min=dane.pojemnosc_min,
        ksztalt=dane.ksztalt,
        cechy=dane.cechy,
        priorytet=dane.priorytet,
        sekcja=dane.sekcja,
        aktywny=False,
        kolejnosc=len(stoliki),
    )
    db.add(stolik)
    db.flush()
    geometria = _domyslna_geometria_bez_kolizji(
        db,
        draft.id,
        stolik,
        len(stoliki),
        len(stoliki) + 1,
    )
    db.add(models.PozycjaStolikaPlanu(
        wersja_id=draft.id,
        stolik_id=stolik.id,
        **{**geometria, "aktywny_w_planie": True},
        **_wlasciwosci_snapshotu(stolik),
    ))
    db.commit()
    draft = db.get(models.WersjaPlanuSali, draft.id)
    return _plan_out(db, sala, draft)


@router.delete(
    "/api/sale-rezerwacyjne/{sala_id}/plan/szkic",
    status_code=204,
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def odrzuc_szkic_planu(
    sala_id: int,
    expected_revision: int = Query(..., ge=0),
    db: Session = Depends(get_db),
):
    sala = _sala_or_404(db, sala_id)
    plan = _istniejacy_plan(db, sala.id)
    if plan is None:
        raise HTTPException(404, "Brak szkicu planu.")
    draft = _wersja(db, plan.id, "draft")
    if draft is None:
        raise HTTPException(404, "Brak szkicu planu.")
    if draft.rewizja != expected_revision:
        _revision_conflict(draft)
    pending_tables = _nowe_nieaktywne_stoliki_szkicu(db, draft.id)
    db.query(models.PozycjaStolikaPlanu).filter_by(wersja_id=draft.id).delete(
        synchronize_session=False,
    )
    deleted = db.query(models.WersjaPlanuSali).filter(
        models.WersjaPlanuSali.id == draft.id,
        models.WersjaPlanuSali.status == "draft",
        models.WersjaPlanuSali.rewizja == expected_revision,
    ).delete(synchronize_session=False)
    if deleted != 1:
        db.rollback()
        _revision_conflict(_wersja(db, plan.id, "draft"))
    for stolik in pending_tables:
        db.delete(stolik)
    db.commit()


@router.post(
    "/api/sale-rezerwacyjne/{sala_id}/plan/publikuj",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def publikuj_plan(
    sala_id: int,
    dane: schemas.PublikujPlanSaliIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    try:
        reservation_service.begin_floor_plan_write(db)
    except reservation_service.ReservationError as exc:
        raise HTTPException(
            exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    sala = _sala_or_404(db, sala_id)
    plan = _istniejacy_plan(db, sala.id)
    if plan is None:
        raise HTTPException(404, "Brak szkicu planu.")
    draft = _wersja(db, plan.id, "draft")
    if draft is None:
        raise HTTPException(404, "Brak szkicu planu.")
    if draft.rewizja != dane.expected_revision:
        _revision_conflict(draft)
    pozycje = _snapshot_z_bazy(db, sala, draft)
    # Walidacja pełnego snapshotu również przy publikacji chroni przed uszkodzeniem poza API.
    _waliduj_topologie(
        pozycje,
        _krawedzie_wersji(db, draft),
        _kombinacje_wersji(db, draft),
    )
    room_table_ids = [stolik.id for stolik in _stoliki_sali(db, sala)]
    locked_tables = reservation_service.lock_tables(db, room_table_ids)
    by_id = {stolik.id: stolik for stolik in locked_tables}
    deaktywowane = [
        pozycja["stolik_id"]
        for pozycja in pozycje
        if not pozycja["aktywny_w_planie"] and by_id[pozycja["stolik_id"]].aktywny
    ]
    reservation_ids, hold_ids = _konflikty_dezaktywacji(db, deaktywowane)
    capacity_reservation_ids, capacity_hold_ids, capacity_table_ids = (
        _konflikty_redukcji_pojemnosci(
            db,
            {
                pozycja["stolik_id"]: int(pozycja["pojemnosc"])
                for pozycja in pozycje
            },
        )
    )
    reservation_ids = sorted(set(reservation_ids) | set(capacity_reservation_ids))
    hold_ids = sorted(set(hold_ids) | set(capacity_hold_ids))
    conflict_table_ids = sorted(set(deaktywowane) | set(capacity_table_ids))
    if reservation_ids or hold_ids:
        raise HTTPException(
            409,
            detail={
                "code": "PLAN_PUBLISH_CONFLICT",
                "message": "Nie można wyłączyć stolika używanego przez przyszłą rezerwację lub hold.",
                "table_ids": conflict_table_ids,
                "reservation_ids": reservation_ids,
                "hold_ids": hold_ids,
            },
        )
    now = _teraz()
    # Najpierw zwalniamy częściowy indeks "jedna published". Całość pozostaje w jednej
    # transakcji, więc nieudane przejęcie szkicu przywróci poprzednią wersję przez rollback.
    db.query(models.WersjaPlanuSali).filter(
        models.WersjaPlanuSali.plan_id == plan.id,
        models.WersjaPlanuSali.status == "published",
        models.WersjaPlanuSali.id != draft.id,
    ).update(
        {models.WersjaPlanuSali.status: "retired"},
        synchronize_session=False,
    )
    claimed = db.query(models.WersjaPlanuSali).filter(
        models.WersjaPlanuSali.id == draft.id,
        models.WersjaPlanuSali.status == "draft",
        models.WersjaPlanuSali.rewizja == dane.expected_revision,
    ).update(
        {
            models.WersjaPlanuSali.status: "published",
            models.WersjaPlanuSali.opublikowal_id: getattr(user, "id", None),
            models.WersjaPlanuSali.opublikowano_at: now,
            models.WersjaPlanuSali.zaktualizowano_at: now,
        },
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        _revision_conflict(_wersja(db, plan.id, "draft"))
    for pozycja in pozycje:
        stolik = by_id[pozycja["stolik_id"]]
        stolik.plan_x = pozycja["plan_x"]
        stolik.plan_y = pozycja["plan_y"]
        stolik.aktywny = pozycja["aktywny_w_planie"]
        for field in _SNAPSHOT_PROPS:
            value = pozycja[field]
            if field == "cechy" and value is not None:
                value = list(value)
            setattr(stolik, field, value)
    db.commit()
    published = db.get(models.WersjaPlanuSali, draft.id)
    return _plan_out(db, sala, published)


@router.get(
    "/api/plan-sali",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def plan_sali(
    data: date = Query(None),
    sala_id: int = Query(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Operacyjny plan dnia; geometria pochodzi z published, status z rezerwacji."""
    dzien = data or _dzis_lokalnie()
    selected_sala = _sala_or_404(db, sala_id) if sala_id is not None else None
    sale = db.query(models.SalaRezerwacyjna).order_by(
        models.SalaRezerwacyjna.kolejnosc, models.SalaRezerwacyjna.id,
    ).all()
    geometria = {}
    opublikowane_kombinacje = []
    sale_z_wersjonowanym_planem = set()
    sale_do_geometrii = [selected_sala] if selected_sala else sale
    for sala in sale_do_geometrii:
        plan = db.query(models.PlanSali).filter_by(sala_id=sala.id).first()
        if plan:
            sale_z_wersjonowanym_planem.add(sala.id)
        published = _wersja(db, plan.id, "published") if plan else None
        if published:
            for pozycja in db.query(models.PozycjaStolikaPlanu).filter_by(
                wersja_id=published.id,
            ).all():
                geometria[pozycja.stolik_id] = pozycja
            opublikowane_kombinacje.extend(
                combination
                for combination in _kombinacje_wersji(db, published)
                if combination["aktywna_w_planie"]
            )

    if selected_sala:
        stoliki = _stoliki_sali(db, selected_sala)
    else:
        stoliki = db.query(models.Stolik).order_by(
            models.Stolik.kolejnosc, models.Stolik.id,
        ).all()
    sala_po_nazwie = {
        (sala.nazwa or "").strip().casefold(): sala.id for sala in sale
    }
    stoliki = [
        stolik
        for stolik in stoliki
        if (
            (
                stolik.sala_id
                or sala_po_nazwie.get((stolik.strefa or "").strip().casefold())
            ) not in sale_z_wersjonowanym_planem
            or stolik.id in geometria
        )
    ]

    rezerwacje = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.data == dzien,
        models.Termin.status.in_(_AKTYWNE),
    ).all()
    per_stolik = defaultdict(list)
    for termin in rezerwacje:
        stoly_terminu = _ids_stolikow(termin.stoliki_dodatkowe)
        if termin.stolik_id:
            stoly_terminu.add(termin.stolik_id)
        for sid in stoly_terminu:
            per_stolik[sid].append(termin)

    hold_table_ids = {
        stolik_id
        for (stolik_id,) in db.query(models.RezerwacjaStolikClaim.stolik_id).filter(
            models.RezerwacjaStolikClaim.data == dzien,
            models.RezerwacjaStolikClaim.waitlist_id.isnot(None),
            models.RezerwacjaStolikClaim.expires_at > _teraz(),
        ).distinct().all()
    }
    stan = {snapshot.rewir_nr: snapshot for snapshot in db.query(models.StanStolow).all()}
    out = []
    for stolik in stoliki:
        rez = sorted(per_stolik.get(stolik.id, []), key=lambda termin: termin.godz_od or time.min)
        pozycja = geometria.get(stolik.id)
        wlasciwosci = _wlasciwosci_snapshotu(stolik, pozycja)
        aktywny_w_planie = (
            pozycja.aktywny_w_planie if pozycja is not None else stolik.aktywny
        )
        live_snapshot = stan.get(stolik.rewir_nr) if stolik.rewir_nr else None
        if not aktywny_w_planie:
            status = "nieaktywny"
        elif any(termin.status == "potwierdzona" for termin in rez):
            status = "potwierdzony"
        elif rez:
            status = "zarezerwowany"
        elif stolik.id in hold_table_ids:
            status = "wstrzymany"
        elif live_snapshot is not None and (live_snapshot.otwarte or 0) > 0:
            status = "zajety_live"
        else:
            # Brak wpisu nie jest obietnicą dostępności przed ewaluatorem R3/R4.
            status = "bez_rezerwacji"
        live = None if live_snapshot is None else {
            "otwarte": live_snapshot.otwarte or 0,
            "zajete": (live_snapshot.otwarte or 0) > 0,
            "aktualizacja": (
                live_snapshot.zaktualizowano_at.isoformat()
                if live_snapshot.zaktualizowano_at else None
            ),
        }
        out.append({
            "id": stolik.id,
            "nazwa": wlasciwosci["nazwa"],
            "sala_id": stolik.sala_id,
            "strefa": stolik.strefa,
            "kolejnosc": wlasciwosci["kolejnosc"],
            "pojemnosc": wlasciwosci["pojemnosc"],
            "pojemnosc_min": wlasciwosci["pojemnosc_min"],
            "ksztalt": wlasciwosci["ksztalt"],
            "cechy": wlasciwosci["cechy"] or [],
            "priorytet": wlasciwosci["priorytet"],
            "sekcja": wlasciwosci["sekcja"],
            "aktywny": aktywny_w_planie,
            "plan_x": pozycja.plan_x if pozycja else stolik.plan_x,
            "plan_y": pozycja.plan_y if pozycja else stolik.plan_y,
            "szerokosc": pozycja.szerokosc if pozycja else None,
            "wysokosc": pozycja.wysokosc if pozycja else None,
            "obrot": pozycja.obrot if pozycja else 0,
            "aktywny_w_planie": aktywny_w_planie,
            "rewir_nr": stolik.rewir_nr,
            "status": status,
            "rezerwacje": [_rez_out(termin, user) for termin in rez],
            "live": live,
        })

    widoczne_ids = {stolik.id for stolik in stoliki}
    wersjonowane_ids = {
        stolik.id
        for stolik in db.query(models.Stolik).all()
        if (
            stolik.sala_id
            or sala_po_nazwie.get((stolik.strefa or "").strip().casefold())
        ) in sale_z_wersjonowanym_planem
    }
    legacy_kombinacje = db.query(models.KombinacjaStolow).filter_by(aktywna=True).order_by(
        models.KombinacjaStolow.priorytet, models.KombinacjaStolow.id,
    ).all()
    legacy_kombinacje = [
        {
            "id": kombinacja.id,
            "nazwa": kombinacja.nazwa,
            "stoliki": sorted(_ids_stolikow(kombinacja.stoliki)),
            "pojemnosc_min": kombinacja.pojemnosc_min,
            "pojemnosc_max": kombinacja.pojemnosc_max,
            "priorytet": kombinacja.priorytet,
            "kanal": "oba",
            "aktywna_w_planie": True,
        }
        for kombinacja in legacy_kombinacje
        if _ids_stolikow(kombinacja.stoliki)
        and _ids_stolikow(kombinacja.stoliki) <= widoczne_ids
        and not (_ids_stolikow(kombinacja.stoliki) & wersjonowane_ids)
    ]
    kombinacje = [
        combination
        for combination in opublikowane_kombinacje
        if set(combination["stoliki"]) <= widoczne_ids
    ] + legacy_kombinacje
    kombinacje.sort(key=lambda row: (row["priorytet"], row["id"]))
    strefy = sorted({stolik.strefa for stolik in stoliki if stolik.strefa})
    return {
        "data": str(dzien),
        "sala_id": selected_sala.id if selected_sala else None,
        "sale": [
            {
                "id": sala.id,
                "nazwa": sala.nazwa,
                "aktywna": sala.aktywna,
                "kolejnosc": sala.kolejnosc,
            }
            for sala in sale
        ],
        "strefy": strefy,
        "stoliki": out,
        "kombinacje": [
            {
                "id": kombinacja["id"],
                "nazwa": kombinacja["nazwa"],
                "stoliki": kombinacja["stoliki"],
                "pojemnosc_min": kombinacja["pojemnosc_min"],
                "pojemnosc_max": kombinacja["pojemnosc_max"],
                "priorytet": kombinacja["priorytet"],
                "kanal": kombinacja["kanal"],
            }
            for kombinacja in kombinacje
        ],
        "podsumowanie": {
            "bez_rezerwacji": sum(
                1 for stolik in out if stolik["status"] == "bez_rezerwacji"
            ),
            "zarezerwowane": sum(
                1 for stolik in out
                if stolik["status"] in ("zarezerwowany", "potwierdzony")
            ),
            "wstrzymane": sum(
                1 for stolik in out if stolik["status"] == "wstrzymany"
            ),
            "nieaktywne": sum(1 for stolik in out if stolik["status"] == "nieaktywny"),
            "zajete_live": sum(
                1 for stolik in out if stolik["live"] and stolik["live"]["zajete"]
            ),
        },
    }


@router.put(
    "/api/plan-sali/pozycje",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def zapisz_pozycje(
    pozycje: List[schemas.PlanPozycjaIn],
    db: Session = Depends(get_db),
):
    """Legacy zapis pozycji działa wyłącznie dla sal bez wersjonowanego planu."""
    by_id = {stolik.id: stolik for stolik in db.query(models.Stolik).all()}
    sale = db.query(models.SalaRezerwacyjna).all()
    planowane_sale = {
        plan.sala_id for plan in db.query(models.PlanSali).all()
    }
    sale_po_nazwie = {
        (sala.nazwa or "").strip().casefold(): sala.id for sala in sale
    }
    for pozycja in pozycje:
        stolik = by_id.get(pozycja.id)
        if stolik is None:
            continue
        fallback_sala_id = sale_po_nazwie.get((stolik.strefa or "").strip().casefold())
        if stolik.sala_id in planowane_sale or fallback_sala_id in planowane_sale:
            raise HTTPException(
                409,
                detail={
                    "code": "FLOOR_PLAN_VERSIONING_REQUIRED",
                    "message": "Ta sala korzysta z wersjonowanego planu. Zapisz zmianę w szkicu.",
                },
            )
    zapisane = 0
    for pozycja in pozycje:
        stolik = by_id.get(pozycja.id)
        if stolik is None:
            continue
        stolik.plan_x = max(0, min(100, int(pozycja.plan_x)))
        stolik.plan_y = max(0, min(100, int(pozycja.plan_y)))
        zapisane += 1
    db.commit()
    return {"zapisane": zapisane}
