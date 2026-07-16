"""Konfiguracja i podgląd reguł dostępności rezerwacji (R3)."""

from __future__ import annotations

from datetime import datetime, timedelta
import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import reservation_payments
import schemas
from auth import get_current_user
from database import get_db
from deps import _teraz_lokalnie, get_lokal_config, modul_aktywny, utcnow_naive


router = APIRouter()


def _wymagaj_modul_rezerwacje(db: Session = Depends(get_db)):
    if not modul_aktywny(db, "modul_rezerwacje"):
        raise HTTPException(
            403,
            "Moduł rezerwacji jest niedostępny w tym planie — odblokujesz go w pakiecie Pro.",
        )


def _polityka_out(cfg: models.LokalConfig) -> dict:
    return {
        "okno_wyprzedzenia_dni": int(cfg.rez_okno_wyprzedzenia_dni or 0),
        "cutoff_min": int(cfg.rez_cutoff_min or 0),
        "min_grupa_online": max(1, int(cfg.rez_min_grupa_online or 1)),
        "max_grupa_online": max(0, int(cfg.rez_max_grupa_online or 0)),
        "bufor_min": max(0, int(cfg.rez_bufor_min or 0)),
    }


def _sala_out(sala: models.SalaRezerwacyjna) -> dict:
    return {
        "id": sala.id,
        "nazwa": sala.nazwa,
        "aktywna": bool(sala.aktywna),
        "online_aktywna": bool(sala.online_aktywna),
        "wewnetrzna_aktywna": bool(sala.wewnetrzna_aktywna),
        "limit_jednoczesnych_rez": sala.limit_jednoczesnych_rez,
        "limit_jednoczesnych_osob": sala.limit_jednoczesnych_osob,
        "domyslny_bufor_min": sala.domyslny_bufor_min,
    }


def _polityka_platnosci_out(row: models.PolitykaPlatnosciRezerwacji) -> dict:
    return schemas.PolitykaPlatnosciRezerwacjiOut.model_validate(row).model_dump(mode="json")


def _polityki_platnosci(db: Session) -> list[models.PolitykaPlatnosciRezerwacji]:
    return db.query(models.PolitykaPlatnosciRezerwacji).order_by(
        models.PolitykaPlatnosciRezerwacji.priorytet,
        models.PolitykaPlatnosciRezerwacji.id,
    ).all()


def _waliduj_polityke_platnosci(
    db: Session,
    dane: schemas.PolitykaPlatnosciRezerwacjiIn,
) -> None:
    if dane.serwis_id is not None and db.get(models.GodzinyOtwarcia, dane.serwis_id) is None:
        raise HTTPException(400, "Nieznany serwis.")
    if dane.rodzaj != "brak" and dane.waluta == "PLN" and dane.kwota_minor < 200:
        raise HTTPException(400, "Minimalna kwota płatności w PLN to 2,00 zł.")
    if dane.aktywna and dane.rodzaj == "preautoryzacja":
        today = (_teraz_lokalnie() or datetime.now()).date()
        if dane.data is None:
            raise HTTPException(
                400,
                "Preautoryzacja bez schedulera wymaga konkretnego dnia wizyty. "
                "Dla stałej reguły wybierz zadatek.",
            )
        if dane.data < today or dane.data > today + timedelta(days=6):
            raise HTTPException(
                400,
                "Aktywną preautoryzację można ustawić tylko na dzień od dziś do 6 dni naprzód.",
            )


def _audyt_polityki_platnosci(
    db: Session,
    user: models.User,
    action: str,
    row: models.PolitykaPlatnosciRezerwacji,
    *,
    before: dict | None,
    after: dict | None,
) -> None:
    details = {
        "before": before,
        "after": after,
    }
    db.add(models.AuditLog(
        ts=utcnow_naive(),
        user_id=user.id,
        login=user.login,
        akcja=action,
        zasob=f"payment_policy:{row.id}",
        szczegoly=json.dumps(
            details,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    ))


@router.get(
    "/api/rezerwacje/reguly",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def get_reguly_rezerwacji(db: Session = Depends(get_db)):
    cfg = get_lokal_config(db)
    serwisy = db.query(models.GodzinyOtwarcia).order_by(
        models.GodzinyOtwarcia.dzien_tygodnia,
        models.GodzinyOtwarcia.godz_od,
        models.GodzinyOtwarcia.id,
    ).all()
    nadpisania = db.query(models.RegulaDostepnosciRezerwacji).order_by(
        models.RegulaDostepnosciRezerwacji.serwis_id,
        models.RegulaDostepnosciRezerwacji.sala_id,
        models.RegulaDostepnosciRezerwacji.kanal,
        models.RegulaDostepnosciRezerwacji.id,
    ).all()
    wyjatki = db.query(models.WyjatekKalendarza).order_by(
        models.WyjatekKalendarza.data,
        models.WyjatekKalendarza.id,
    ).all()
    sale = db.query(models.SalaRezerwacyjna).order_by(
        models.SalaRezerwacyjna.kolejnosc,
        models.SalaRezerwacyjna.id,
    ).all()
    polityki_platnosci = _polityki_platnosci(db)
    return {
        "wersja": 3,
        "polityka": _polityka_out(cfg),
        "serwisy": [
            schemas.GodzinyOtwarciaOut.model_validate(row).model_dump(mode="json")
            for row in serwisy
        ],
        "nadpisania": [
            schemas.RegulaDostepnosciRezerwacjiOut.model_validate(row).model_dump(mode="json")
            for row in nadpisania
        ],
        "polityki_platnosci": [
            _polityka_platnosci_out(row) for row in polityki_platnosci
        ],
        "legacy_zadatek_fallback": reservation_payments.legacy_fallback_public_dict(cfg),
        "wyjatki": [
            schemas.WyjatekKalendarzaOut.model_validate(row).model_dump(mode="json")
            for row in wyjatki
        ],
        "sale": [_sala_out(row) for row in sale],
    }


@router.get(
    "/api/polityki-platnosci-rezerwacji",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def lista_polityk_platnosci_rezerwacji(db: Session = Depends(get_db)):
    return [_polityka_platnosci_out(row) for row in _polityki_platnosci(db)]


@router.post(
    "/api/polityki-platnosci-rezerwacji",
    status_code=201,
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def dodaj_polityke_platnosci_rezerwacji(
    dane: schemas.PolitykaPlatnosciRezerwacjiIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _waliduj_polityke_platnosci(db, dane)
    now = utcnow_naive()
    row = models.PolitykaPlatnosciRezerwacji(
        **dane.model_dump(),
        utworzono_at=now,
        zaktualizowano_at=now,
    )
    db.add(row)
    try:
        db.flush()
        _audyt_polityki_platnosci(
            db,
            user,
            "platnosc_policy_create",
            row,
            before=None,
            after=_polityka_platnosci_out(row),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Nie udało się zapisać polityki płatności.") from exc
    db.refresh(row)
    return _polityka_platnosci_out(row)


@router.put(
    "/api/polityki-platnosci-rezerwacji/{polityka_id}",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def edytuj_polityke_platnosci_rezerwacji(
    polityka_id: int,
    dane: schemas.PolitykaPlatnosciRezerwacjiIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    row = db.get(models.PolitykaPlatnosciRezerwacji, polityka_id)
    if row is None:
        raise HTTPException(404, "Brak polityki płatności.")
    _waliduj_polityke_platnosci(db, dane)
    before = _polityka_platnosci_out(row)
    for key, value in dane.model_dump().items():
        setattr(row, key, value)
    row.zaktualizowano_at = utcnow_naive()
    try:
        db.flush()
        _audyt_polityki_platnosci(
            db,
            user,
            "platnosc_policy_update",
            row,
            before=before,
            after=_polityka_platnosci_out(row),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Nie udało się zapisać polityki płatności.") from exc
    db.refresh(row)
    return _polityka_platnosci_out(row)


@router.delete(
    "/api/polityki-platnosci-rezerwacji/{polityka_id}",
    status_code=204,
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def usun_polityke_platnosci_rezerwacji(
    polityka_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    row = db.get(models.PolitykaPlatnosciRezerwacji, polityka_id)
    if row is None:
        raise HTTPException(404, "Brak polityki płatności.")
    _audyt_polityki_platnosci(
        db,
        user,
        "platnosc_policy_delete",
        row,
        before=_polityka_platnosci_out(row),
        after=None,
    )
    db.delete(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Polityka jest nadal używana.") from exc
    return Response(status_code=204)


@router.put(
    "/api/rezerwacje/reguly/polityka",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def ustaw_polityke_rezerwacji(
    dane: schemas.PolitykaRezerwacjiR3In,
    db: Session = Depends(get_db),
):
    cfg = get_lokal_config(db)
    cfg.rez_okno_wyprzedzenia_dni = dane.okno_wyprzedzenia_dni
    cfg.rez_cutoff_min = dane.cutoff_min
    cfg.rez_min_grupa_online = dane.min_grupa_online
    cfg.rez_max_grupa_online = dane.max_grupa_online
    cfg.rez_bufor_min = dane.bufor_min
    db.commit()
    db.refresh(cfg)
    return _polityka_out(cfg)


@router.put(
    "/api/rezerwacje/reguly/sale/{sala_id}",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def ustaw_dostepnosc_sali(
    sala_id: int,
    dane: schemas.SalaDostepnoscR3In,
    db: Session = Depends(get_db),
):
    sala = db.get(models.SalaRezerwacyjna, sala_id)
    if sala is None:
        raise HTTPException(404, "Brak sali.")
    for key, value in dane.model_dump().items():
        setattr(sala, key, value)
    db.commit()
    db.refresh(sala)
    return _sala_out(sala)


def _waliduj_serwis(
    db: Session,
    dane: schemas.GodzinyOtwarciaIn,
    *,
    pomin_id: int | None = None,
) -> None:
    if dane.godz_do <= dane.godz_od:
        raise HTTPException(400, "Serwis musi kończyć się po godzinie rozpoczęcia.")
    if dane.ostatni_zasiadek is not None and not (
        dane.godz_od <= dane.ostatni_zasiadek <= dane.godz_do
    ):
        raise HTTPException(400, "Ostatnie przyjęcie musi mieścić się w godzinach serwisu.")
    if not dane.aktywny:
        return
    end = dane.ostatni_zasiadek or dane.godz_do
    query = db.query(models.GodzinyOtwarcia).filter(
        models.GodzinyOtwarcia.dzien_tygodnia == dane.dzien_tygodnia,
        models.GodzinyOtwarcia.aktywny.is_(True),
    )
    if pomin_id is not None:
        query = query.filter(models.GodzinyOtwarcia.id != pomin_id)
    for other in query.all():
        other_end = other.ostatni_zasiadek or other.godz_do
        if dane.godz_od <= other_end and other.godz_od <= end:
            raise HTTPException(
                409,
                "Godziny tego serwisu nakładają się na inny aktywny serwis w tym dniu.",
            )


@router.put(
    "/api/godziny-otwarcia/{serwis_id}",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def edytuj_serwis_rezerwacyjny(
    serwis_id: int,
    dane: schemas.GodzinyOtwarciaIn,
    db: Session = Depends(get_db),
):
    serwis = db.get(models.GodzinyOtwarcia, serwis_id)
    if serwis is None:
        raise HTTPException(404, "Brak serwisu.")
    _waliduj_serwis(db, dane, pomin_id=serwis_id)
    for key, value in dane.model_dump().items():
        setattr(serwis, key, value)
    # Adapter dla starej PWA zawsze śledzi krok oferowanych terminów.
    serwis.dlugosc_slotu_min = serwis.krok_slotu_min
    db.commit()
    db.refresh(serwis)
    return schemas.GodzinyOtwarciaOut.model_validate(serwis).model_dump(mode="json")


def _waliduj_scope_reguly(
    db: Session,
    dane: schemas.RegulaDostepnosciRezerwacjiIn,
) -> None:
    if dane.serwis_id is not None and db.get(models.GodzinyOtwarcia, dane.serwis_id) is None:
        raise HTTPException(400, "Nieznany serwis.")
    if dane.sala_id is not None and db.get(models.SalaRezerwacyjna, dane.sala_id) is None:
        raise HTTPException(400, "Nieznana sala.")


@router.post(
    "/api/nadpisania-regul-rezerwacji",
    status_code=201,
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def dodaj_nadpisanie_regul(
    dane: schemas.RegulaDostepnosciRezerwacjiIn,
    db: Session = Depends(get_db),
):
    _waliduj_scope_reguly(db, dane)
    row = models.RegulaDostepnosciRezerwacji(**dane.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Taki zakres reguł już istnieje.") from exc
    db.refresh(row)
    return schemas.RegulaDostepnosciRezerwacjiOut.model_validate(row).model_dump(mode="json")


@router.put(
    "/api/nadpisania-regul-rezerwacji/{regula_id}",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def edytuj_nadpisanie_regul(
    regula_id: int,
    dane: schemas.RegulaDostepnosciRezerwacjiIn,
    db: Session = Depends(get_db),
):
    row = db.get(models.RegulaDostepnosciRezerwacji, regula_id)
    if row is None:
        raise HTTPException(404, "Brak reguły.")
    _waliduj_scope_reguly(db, dane)
    for key, value in dane.model_dump().items():
        setattr(row, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Taki zakres reguł już istnieje.") from exc
    db.refresh(row)
    return schemas.RegulaDostepnosciRezerwacjiOut.model_validate(row).model_dump(mode="json")


@router.delete(
    "/api/nadpisania-regul-rezerwacji/{regula_id}",
    status_code=204,
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def usun_nadpisanie_regul(
    regula_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(models.RegulaDostepnosciRezerwacji, regula_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)
