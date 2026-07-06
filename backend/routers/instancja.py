"""Router: operacje instancji SaaS — subskrypcja/licencja, dziennik audytu, status integracji.

Wydzielone z main.py (Rec#5 audytu — dekompozycja monolitu). Ścieżki URL bez zmian (1:1).
Autoryzacja (admin) i degradacja READ_ONLY są egzekwowane przez middleware role_guard w main.
"""

import os
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import cennik
import faktury
import integracje
import models
import platnosci_sub
import schemas
import subskrypcja_billing
from auth import require_admin
from database import get_db
from deps import (get_subskrypcja, subskrypcja_aktywna, get_lokal_config,
                  stan_subskrypcji, data_grace, utcnow_naive,
                  synchronizuj_subskrypcje, dostepne_moduly, dni_trialu, limit_pracownikow_stan)

router = APIRouter()


@router.get("/api/instancja/puls")
def instancja_puls(request: Request, db: Session = Depends(get_db)):
    """Podsumowanie instancji dla panelu floty operatora (instancja-matka). Autoryzacja
    współdzielonym FLEET_TOKEN (nagłówek X-Fleet-Token) — matka propaguje go do dzieci przez
    środowisko procesu. Zwraca TYLKO zagregowane, niewrażliwe dane (bez PII, płac, danych gości)."""
    token = os.getenv("FLEET_TOKEN", "")
    if not token or request.headers.get("x-fleet-token") != token:
        raise HTTPException(403, "Brak lub nieprawidłowy token floty.")
    s = get_subskrypcja(db)
    return {
        "nazwa_lokalu": get_lokal_config(db).nazwa_lokalu,
        "tier": s.tier, "status": s.status, "aktywna": subskrypcja_aktywna(db),
        "data_do": s.data_do.isoformat() if s.data_do else None,
        "liczba_uzytkownikow": db.query(models.User).filter_by(aktywny=True).count(),
        "liczba_pracownikow": db.query(models.Pracownik).count(),
    }


def _subskrypcja_out(s, db) -> dict:
    dg = data_grace(db)
    netto = cennik.cena_netto(s.tier, s.cena_netto)
    return {"tier": s.tier, "status": s.status,
            "data_od": s.data_od.isoformat() if s.data_od else None,
            "data_do": s.data_do.isoformat() if s.data_do else None,
            "uwagi": s.uwagi, "aktywna": subskrypcja_aktywna(db),
            "stan": stan_subskrypcji(db),              # aktywna | grace | zablokowana
            "data_grace": dg.isoformat() if dg else None,
            "cena_netto": netto, "cena_brutto": cennik.brutto(netto),
            "saldo_kredytu": round(s.saldo_kredytu or 0, 2),
            # ── tier-gating modułów + trial + limit (monetyzacja: pakiety zależne) ──
            "poziom": cennik.poziom(s.tier),
            "dostepne_moduly": sorted(dostepne_moduly(db)),   # które moduły odblokowane
            "moduly_wg_planu": cennik.MODUL_MIN_TIER,         # moduł → min. plan (do upsellu)
            "trial_dni": dni_trialu(db),                      # None gdy nie trial
            "limit_pracownikow": limit_pracownikow_stan(db)}


def _historia_zmian(db, akcja, tier_z, tier_na, kwota_netto=None, login=None, szczegoly=None):
    db.add(models.HistoriaSubskrypcji(ts=utcnow_naive(), akcja=akcja, tier_z=tier_z,
           tier_na=tier_na, kwota_netto=kwota_netto, login=login, szczegoly=szczegoly))


def _audit_out(w: models.AuditLog) -> dict:
    return {"id": w.id, "ts": w.ts.isoformat() if w.ts else None, "login": w.login,
            "akcja": w.akcja, "zasob": w.zasob, "pracownik_id": w.pracownik_id,
            "ip": w.ip, "szczegoly": w.szczegoly}


@router.get("/api/subskrypcja")
def subskrypcja_get(db: Session = Depends(get_db)):
    """Status subskrypcji/licencji instancji (admin). `aktywna` = czy zapisy są dozwolone.
    Odczyt synchronizuje trial: po 14 dniach automatycznie spada do Free (rdzeń dalej działa)."""
    return _subskrypcja_out(synchronizuj_subskrypcje(db), db)


@router.put("/api/subskrypcja")
def subskrypcja_update(data: schemas.SubskrypcjaIn, db: Session = Depends(get_db)):
    """Zmiana subskrypcji (admin) — status/tier/daty. Ustawienie statusu na aktywna odblokowuje zapisy."""
    s = get_subskrypcja(db)
    stary_tier, stary_status = s.tier, s.status
    for pole, wartosc in data.model_dump(exclude_unset=True).items():
        setattr(s, pole, wartosc)
    if s.tier != stary_tier:
        _historia_zmian(db, "zmiana_reczna", stary_tier, s.tier, szczegoly="PUT /api/subskrypcja")
    elif s.status != stary_status:
        _historia_zmian(db, "zmiana_statusu", stary_tier, s.tier, szczegoly=f"{stary_status}→{s.status}")
    db.commit(); db.refresh(s)
    return _subskrypcja_out(s, db)


@router.get("/api/subskrypcja/upgrade/podglad")
def upgrade_podglad(tier: str = Query(...), db: Session = Depends(get_db)):
    """Podgląd zmiany planu (nic nie zapisuje): dopłata za pozostałe dni (proration) lub kredyt."""
    if tier not in cennik.TIERY:
        raise HTTPException(400, "Nieznany pakiet.")
    s = get_subskrypcja(db)
    return subskrypcja_billing.oblicz_prorate(
        s.tier, tier, s.data_od, s.data_do,
        cena_override_nowy=(s.cena_netto if tier == s.tier else None),
        saldo_kredytu=s.saldo_kredytu or 0)


@router.post("/api/subskrypcja/upgrade")
def upgrade_wykonaj(dane: schemas.UpgradeIn, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    """Zmiana planu z proratą. Upgrade: podnosi tier NATYCHMIAST i tworzy płatność-dopłatę
    (sandbox: link do ręcznego opłacenia). Downgrade: dopisuje kredyt na saldo, obniża tier."""
    tier = dane.tier
    if tier not in cennik.TIERY:
        raise HTTPException(400, "Nieznany pakiet.")
    s = get_subskrypcja(db)
    if tier == s.tier:
        raise HTTPException(400, "Ten pakiet jest już aktywny.")
    r = subskrypcja_billing.oblicz_prorate(s.tier, tier, s.data_od, s.data_do,
                                           saldo_kredytu=s.saldo_kredytu or 0)
    stary = s.tier
    platnosc = None
    if r["kierunek"] == "upgrade":
        s.tier = tier                                   # dostęp do wyższego planu od razu
        s.saldo_kredytu = round(max(0.0, (s.saldo_kredytu or 0) - r["saldo_kredytu_uzyte"]), 2)
        if r["doplata_netto"] > 0:
            platnosc = platnosci_sub.utworz(db, "doplata", tier, r["doplata_netto"],
                                            okres_od=date.today(), okres_do=s.data_do)
        _historia_zmian(db, "upgrade", stary, tier, kwota_netto=r["doplata_netto"], login=admin.login)
    else:  # downgrade — kredyt na saldo, niższy tier
        s.tier = tier
        s.saldo_kredytu = round((s.saldo_kredytu or 0) + r["kredyt_netto"], 2)
        _historia_zmian(db, "downgrade", stary, tier, kwota_netto=r["kredyt_netto"], login=admin.login)
    db.commit(); db.refresh(s)
    return {"subskrypcja": _subskrypcja_out(s, db), "prorata": r,
            "platnosc": ({"external_id": platnosc.external_id, "brutto": platnosc.brutto,
                          "link": platnosc.link} if platnosc else None)}


@router.post("/api/subskrypcja/platnosc/{external_id}/oplac")
def oplac_sandbox(external_id: str, db: Session = Depends(get_db),
                  admin: models.User = Depends(require_admin)):
    """SANDBOX/ręcznie: oznacza płatność subskrypcji jako opłaconą. Abonament przedłuża
    data_do o miesiąc i odblokowuje instancję. (Docelowo robi to webhook bramki — Faza 4.)"""
    p = platnosci_sub.oznacz_oplacona(db, external_id)
    if p is None:
        raise HTTPException(404, "Brak takiej płatności.")
    s = get_subskrypcja(db)
    if p.rodzaj == "abonament":
        baza = s.data_do if (s.data_do and s.data_do >= date.today()) else date.today()
        s.data_do = baza + timedelta(days=30)
        if s.status not in ("aktywna", "trial"):
            s.status = "aktywna"
        if not s.data_od:
            s.data_od = date.today()
        db.commit(); db.refresh(s)
    # Faktura VAT (KSeF) za opłaconą płatność — abonament i dopłata (idempotentnie).
    faktury.wystaw_z_platnosci(db, p)
    return _subskrypcja_out(s, db)


@router.post("/api/subskrypcja/odnow")
def odnow_abonament(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Tworzy płatność za kolejny okres bieżącego pakietu (sandbox: link do opłacenia)."""
    s = get_subskrypcja(db)
    netto = cennik.cena_netto(s.tier, s.cena_netto)
    if netto <= 0:
        raise HTTPException(400, "Pakiet darmowy nie wymaga opłaty.")
    baza = s.data_do if (s.data_do and s.data_do >= date.today()) else date.today()
    p = platnosci_sub.utworz(db, "abonament", s.tier, netto,
                             okres_od=baza, okres_do=baza + timedelta(days=30))
    return {"external_id": p.external_id, "brutto": p.brutto, "link": p.link}


def _faktura_out(f: models.Faktura) -> dict:
    return {"id": f.id, "numer": f.numer, "rodzaj": f.rodzaj,
            "nabywca_nip": f.nabywca_nip, "nabywca_nazwa": f.nabywca_nazwa,
            "netto": f.netto, "vat": f.vat, "brutto": f.brutto,
            "okres_od": f.okres_od.isoformat() if f.okres_od else None,
            "okres_do": f.okres_do.isoformat() if f.okres_do else None,
            "opis": f.opis, "ksef_number": f.ksef_number, "status_ksef": f.status_ksef,
            "data_wystawienia": f.data_wystawienia.isoformat() if f.data_wystawienia else None}


@router.get("/api/faktury")
def faktury_lista(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Faktury za subskrypcję (najnowsze pierwsze) + tryb KSeF (stub/test/prod)."""
    import ksef as _ksef
    rows = db.query(models.Faktura).order_by(models.Faktura.id.desc()).limit(200).all()
    return {"tryb_ksef": _ksef.tryb(), "faktury": [_faktura_out(f) for f in rows]}


@router.get("/api/faktury/{fid}/xml")
def faktura_xml(fid: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Pobranie XML FA(3) faktury (do archiwum / ręcznego wysłania do KSeF)."""
    from fastapi.responses import Response
    f = db.get(models.Faktura, fid)
    if f is None or not f.xml:
        raise HTTPException(404, "Brak faktury lub XML.")
    return Response(content=f.xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{f.numer.replace("/", "_")}.xml"'})


@router.post("/api/faktury/{fid}/wyslij")
def faktura_wyslij(fid: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """Ponawia wysyłkę faktury do KSeF (gdy status='blad')."""
    f = db.get(models.Faktura, fid)
    if f is None:
        raise HTTPException(404, "Brak faktury.")
    return _faktura_out(faktury.wyslij_ponownie(db, f))


@router.get("/api/integracje/status")
def integracje_status():
    """Status integracji instancji (które mają komplet sekretów) — bez wartości sekretów. Admin."""
    return {"integracje": integracje.status()}


@router.get("/api/audit-log")
def audit_log_list(od: date = Query(None), do: date = Query(None), login: str = Query(None),
                   akcja: str = Query(None), limit: int = Query(200), db: Session = Depends(get_db)):
    """Dziennik audytu dostępu do danych wrażliwych (RODO). Tylko admin (wymusza middleware).
    Filtry: zakres dat (od/do), login, akcja; najnowsze najpierw."""
    q = db.query(models.AuditLog)
    if od:
        q = q.filter(models.AuditLog.ts >= datetime(od.year, od.month, od.day))
    if do:
        q = q.filter(models.AuditLog.ts < datetime(do.year, do.month, do.day) + timedelta(days=1))
    if login:
        q = q.filter(models.AuditLog.login == login)
    if akcja:
        q = q.filter(models.AuditLog.akcja == akcja)
    q = q.order_by(models.AuditLog.id.desc()).limit(max(1, min(int(limit), 1000)))
    return [_audit_out(w) for w in q.all()]
