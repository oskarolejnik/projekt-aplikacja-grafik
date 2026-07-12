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
        out.append({
            "id": stolik.id,
            "nazwa": stolik.nazwa,
            "pojemnosc": stolik.pojemnosc,
            **geometria,
        })
    # Uszkodzona/osierocona pozycja nie może wyciec do kontraktu ani blokować odczytu.
    assert set(by_id) == {row["id"] for row in out}
    return out


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
    ids = [pozycja.stolik_id for pozycja in pozycje]
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


def _dodaj_pozycje(db: Session, wersja_id: int, pozycje):
    for pozycja in pozycje:
        dane = pozycja.model_dump() if hasattr(pozycja, "model_dump") else dict(pozycja)
        db.add(models.PozycjaStolikaPlanu(wersja_id=wersja_id, **dane))


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
        out.append({"stolik_id": stolik.id, **geometria})
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
    _waliduj_pelny_snapshot(db, sala, dane.pozycje)
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
    db.query(models.PozycjaStolikaPlanu).filter_by(wersja_id=draft.id).delete(
        synchronize_session=False,
    )
    _dodaj_pozycje(db, draft.id, dane.pozycje)
    db.commit()
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
        aktywny=False,
        kolejnosc=len(stoliki),
    )
    db.add(stolik)
    db.flush()
    geometria = _domyslna_geometria(stolik, len(stoliki), len(stoliki) + 1)
    db.add(models.PozycjaStolikaPlanu(
        wersja_id=draft.id,
        stolik_id=stolik.id,
        **{**geometria, "aktywny_w_planie": True},
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
    pozycje = db.query(models.PozycjaStolikaPlanu).filter_by(wersja_id=draft.id).all()
    # Walidacja pełnego snapshotu również przy publikacji chroni przed uszkodzeniem poza API.
    class _PozycjaRef:
        def __init__(self, stolik_id):
            self.stolik_id = stolik_id
    _waliduj_pelny_snapshot(db, sala, [_PozycjaRef(p.stolik_id) for p in pozycje])
    room_table_ids = [stolik.id for stolik in _stoliki_sali(db, sala)]
    locked_tables = reservation_service.lock_tables(db, room_table_ids)
    by_id = {stolik.id: stolik for stolik in locked_tables}
    deaktywowane = [
        pozycja.stolik_id
        for pozycja in pozycje
        if not pozycja.aktywny_w_planie and by_id[pozycja.stolik_id].aktywny
    ]
    reservation_ids, hold_ids = _konflikty_dezaktywacji(db, deaktywowane)
    if reservation_ids or hold_ids:
        raise HTTPException(
            409,
            detail={
                "code": "PLAN_PUBLISH_CONFLICT",
                "message": "Nie można wyłączyć stolika używanego przez przyszłą rezerwację lub hold.",
                "table_ids": sorted(deaktywowane),
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
        stolik = by_id[pozycja.stolik_id]
        stolik.plan_x = pozycja.plan_x
        stolik.plan_y = pozycja.plan_y
        stolik.aktywny = pozycja.aktywny_w_planie
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
        snapshot = stan.get(stolik.rewir_nr) if stolik.rewir_nr else None
        if not stolik.aktywny:
            status = "nieaktywny"
        elif any(termin.status == "potwierdzona" for termin in rez):
            status = "potwierdzony"
        elif rez:
            status = "zarezerwowany"
        elif stolik.id in hold_table_ids:
            status = "wstrzymany"
        elif snapshot is not None and (snapshot.otwarte or 0) > 0:
            status = "zajety_live"
        else:
            # Brak wpisu nie jest obietnicą dostępności przed ewaluatorem R3/R4.
            status = "bez_rezerwacji"
        live = None if snapshot is None else {
            "otwarte": snapshot.otwarte or 0,
            "zajete": (snapshot.otwarte or 0) > 0,
            "aktualizacja": (
                snapshot.zaktualizowano_at.isoformat() if snapshot.zaktualizowano_at else None
            ),
        }
        pozycja = geometria.get(stolik.id)
        out.append({
            "id": stolik.id,
            "nazwa": stolik.nazwa,
            "sala_id": stolik.sala_id,
            "strefa": stolik.strefa,
            "pojemnosc": stolik.pojemnosc,
            "pojemnosc_min": stolik.pojemnosc_min,
            "ksztalt": stolik.ksztalt,
            "cechy": stolik.cechy or [],
            "aktywny": stolik.aktywny,
            "plan_x": pozycja.plan_x if pozycja else stolik.plan_x,
            "plan_y": pozycja.plan_y if pozycja else stolik.plan_y,
            "szerokosc": pozycja.szerokosc if pozycja else None,
            "wysokosc": pozycja.wysokosc if pozycja else None,
            "obrot": pozycja.obrot if pozycja else 0,
            "aktywny_w_planie": pozycja.aktywny_w_planie if pozycja else stolik.aktywny,
            "rewir_nr": stolik.rewir_nr,
            "status": status,
            "rezerwacje": [_rez_out(termin, user) for termin in rez],
            "live": live,
        })

    widoczne_ids = {stolik.id for stolik in stoliki}
    kombinacje = db.query(models.KombinacjaStolow).filter_by(aktywna=True).order_by(
        models.KombinacjaStolow.priorytet, models.KombinacjaStolow.id,
    ).all()
    kombinacje = [
        kombinacja for kombinacja in kombinacje
        if _ids_stolikow(kombinacja.stoliki)
        and _ids_stolikow(kombinacja.stoliki) <= widoczne_ids
    ]
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
                "id": kombinacja.id,
                "nazwa": kombinacja.nazwa,
                "stoliki": kombinacja.stoliki or [],
                "pojemnosc_min": kombinacja.pojemnosc_min,
                "pojemnosc_max": kombinacja.pojemnosc_max,
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
