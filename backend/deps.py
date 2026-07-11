"""Współdzielone helpery używane zarówno przez main.py, jak i przez routery.

Wydzielone tutaj, aby routery mogły z nich korzystać BEZ importowania main.py
(co dawałoby cykl importów: main → router → main). Zależą tylko od models.
"""

import hashlib
import os
import re
import secrets
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import cennik
import models
import schemas


def utcnow_naive() -> datetime:
    """Bieżący czas UTC jako NAIWNY datetime (bez tzinfo) — zamiennik przestarzałego
    `datetime.utcnow()` (deprecated od Pythona 3.12). Zachowuje dotychczasowy format
    zapisu w kolumnach DateTime (naiwny UTC, spójny na SQLite i PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_subskrypcja(db) -> models.Subskrypcja:
    """Singleton subskrypcji/licencji instancji (id=1). Tworzony leniwie (domyślnie aktywny)."""
    s = db.get(models.Subskrypcja, 1)
    if s is None:
        s = models.Subskrypcja(id=1)
        db.add(s)
        try:
            db.commit(); db.refresh(s)
        except Exception:
            db.rollback()
            s = db.get(models.Subskrypcja, 1)   # wyścig przy pierwszym zapisie — ktoś już utworzył
    return s


# Grace period: ile dni po data_do zapisy są jeszcze dozwolone (miękka degradacja
# z banerem „faktura po terminie") zanim instancja wpadnie w twarde READ_ONLY.
GRACE_DNI = 7


def stan_subskrypcji(db) -> str:
    """Stan subskrypcji instancji: 'aktywna' | 'grace' | 'zablokowana'.
    - manualne wygasla/zawieszona → zablokowana od razu (bez grace),
    - opłacony okres (data_do w przyszłości / bezterminowa) → aktywna,
    - do GRACE_DNI po data_do → grace (zapisy jeszcze przechodzą, baner),
    - dalej → zablokowana (READ_ONLY)."""
    s = get_subskrypcja(db)
    if s is None or s.status not in ("aktywna", "trial"):
        return "zablokowana"
    if s.data_do is None:
        return "aktywna"
    dzis = date.today()
    if dzis <= s.data_do:
        return "aktywna"
    if dzis <= s.data_do + timedelta(days=GRACE_DNI):
        return "grace"
    return "zablokowana"


def data_grace(db):
    """Ostatni dzień, w którym zapisy jeszcze przechodzą (data_do + GRACE_DNI). None = bezterminowa."""
    s = get_subskrypcja(db)
    return None if (s is None or s.data_do is None) else s.data_do + timedelta(days=GRACE_DNI)


def subskrypcja_aktywna(db) -> bool:
    """Czy zapisy są dozwolone (aktywna LUB w okresie grace). Używane przez middleware 402."""
    return stan_subskrypcji(db) != "zablokowana"


def get_lokal_config(db) -> models.LokalConfig:
    """Singleton konfiguracji lokalu (id=1). Tworzony leniwie z domyślnymi wartościami."""
    cfg = db.get(models.LokalConfig, 1)
    if cfg is None:
        cfg = models.LokalConfig(id=1)
        db.add(cfg)
        try:
            db.commit(); db.refresh(cfg)
        except Exception:
            db.rollback()
            cfg = db.get(models.LokalConfig, 1)   # wyścig przy pierwszym zapisie — ktoś już utworzył
    return cfg


# ── Trial + tier-gating modułów ──────────────────────────────────────────────
TRIAL_DNI = 14


def _obciaz_po_trialu(db, s) -> None:
    """Auto-obciążenie po wygaśnięciu triala planu płatnego (karta zapięta): trial → aktywna,
    opłacony okres +30 dni, tier ZOSTAJE (plan wybrany przy zakładaniu). Zapisuje wpis audytu
    w HistoriaSubskrypcji. SANDBOX: realnego pobrania nie ma dopóki nie wpięty Stripe — wtedy
    ten punkt obciąża zapisaną metodę (karta_token). Nie commituje (robi to wołający)."""
    netto = cennik.cena_netto(s.tier, s.cena_netto)
    s.status = "aktywna"
    s.data_od = date.today()
    s.data_do = date.today() + timedelta(days=30)
    db.add(models.HistoriaSubskrypcji(
        ts=utcnow_naive(), akcja="odnowienie", tier_z=s.tier, tier_na=s.tier, kwota_netto=netto,
        szczegoly=f"Auto-obciążenie po 14-dniowym trialu (karta •••• {s.karta_ostatnie4 or '????'})"))


def synchronizuj_subskrypcje(db) -> models.Subskrypcja:
    """Leniwe przejście po wygaśnięciu triala (woła middleware + odczyty subskrypcji/configu):
    - trial z zapiętą KARTĄ (plan płatny) → auto-obciążenie i przejście na aktywny plan (tier
      zostaje, +30 dni) — „po dwóch tygodniach ściąga z konta",
    - trial BEZ karty (stary/darmowy trial) → spada do Free (rdzeń działa, płatne moduły blokuje
      tier-gating — NIE read-only).
    Idempotentne: po przejściu status!=trial, więc kolejne wywołania to zwykły odczyt."""
    s = get_subskrypcja(db)
    if s.status == "trial" and s.data_do is not None and date.today() > s.data_do:
        if s.karta_token:
            _obciaz_po_trialu(db, s)
        else:
            s.tier, s.status, s.data_do = "free", "aktywna", None
        db.commit(); db.refresh(s)
    return s


def moduly_efektywne_dla_sub(s) -> set:
    """Moduły DOSTĘPNE wg subskrypcji: trial = wszystkie (pełny Premium); inaczej wg tier."""
    if s is not None and s.status == "trial":
        return set(cennik.WSZYSTKIE_MODULY)
    return cennik.moduly_dostepne(s.tier if s else "free")


def dostepne_moduly(db) -> set:
    """Zbiór modułów odblokowanych przez bieżącą subskrypcję (po ewentualnym trial→free)."""
    return moduly_efektywne_dla_sub(synchronizuj_subskrypcje(db))


def modul_aktywny(db, modul: str) -> bool:
    """Kanoniczny check tier-gatingu: funkcja modułu jest DOSTĘPNA gdy włączona w configu
    I odblokowana w planie (tier/trial). NIE sprawdza read-only — degradację zapisów (402 przy
    nieaktywnej subskrypcji) egzekwuje osobno middleware, żeby odczyty działały w trybie tylko-odczyt."""
    s = synchronizuj_subskrypcje(db)
    return bool(getattr(get_lokal_config(db), modul, False)) and modul in moduly_efektywne_dla_sub(s)


def dni_trialu(db):
    """Ile dni triala zostało (do banera). None = nie trial."""
    s = synchronizuj_subskrypcje(db)
    if s.status != "trial" or s.data_do is None:
        return None
    return max(0, (s.data_do - date.today()).days)


def limit_pracownikow_stan(db) -> dict:
    """Stan limitu aktywnych pracowników wg planu. Trial = jak Premium (bez limitu).
    {'limit': int|None, 'aktywni': int, 'przekroczony': bool}."""
    s = synchronizuj_subskrypcje(db)
    tier = "premium" if s.status == "trial" else s.tier
    limit = cennik.limit_pracownikow(tier)
    aktywni = db.query(models.Pracownik).filter(models.Pracownik.aktywny.is_(True)).count()
    return {"limit": limit, "aktywni": aktywni,
            "przekroczony": limit is not None and aktywni >= limit}


def token_agenta_ok(request, db) -> bool:
    """Autoryzacja ingestu POS/RCP: token wygenerowany w panelu (hash SHA-256
    w konfiguracji lokalu, unieważnialny) LUB stały env RCP_INGEST_TOKEN (legacy —
    zostaje na zawsze, żeby wdrożone agenty przeżyły każdy deploy).
    Token przyjmowany w X-RCP-Token oraz Authorization: Bearer."""
    podany = request.headers.get("x-rcp-token") or ""
    if not podany:
        naglowek = request.headers.get("authorization") or ""
        if naglowek.startswith("Bearer "):
            podany = naglowek[7:]
    if not podany:
        return False
    # Porównania w STAŁYM czasie (secrets.compare_digest) — brak kanału timing na sekretnym tokenie.
    env_token = os.environ.get("RCP_INGEST_TOKEN", "")
    if env_token and secrets.compare_digest(podany, env_token):
        return True
    hash_db = getattr(get_lokal_config(db), "pos_token_hash", None)
    return bool(hash_db) and secrets.compare_digest(
        hashlib.sha256(podany.encode("utf-8")).hexdigest(), hash_db)


def rewir_dla_pracownika(rewir):
    """Ukrywa nazwę klienta/imprezy przed pracownikiem (model prywatności). Rewir imprezy ma
    postać „IMPREZA: {klient} ({sala})" — zwracamy tylko „Impreza ({sala})". Zwykłe rewiry bez zmian.
    Współdzielone przez main (/api/me/grafik, rozliczenia) i routery (giełda), żeby nazwisko klienta
    NIGDY nie wyciekło pracownikowi. Widoki managera (admin) mogą pokazywać surowy rewir."""
    if rewir and rewir.startswith("IMPREZA:"):
        sala = rewir[rewir.rfind("(") + 1 : -1].strip() if rewir.endswith(")") and "(" in rewir else ""
        return f"Impreza ({sala})" if sala and sala.lower() not in ("brak", "none") else "Impreza"
    return rewir


# Kwalifikacja działu technicznego dająca dostęp do formularza zamówień
# (por. _ensure_kwalifikacje_techniczne w routers/kadry.py — tam Sprzątaczka/Stróż są dosiewane).
SPRZATACZKA_NAZWA = "Sprzątaczka"


def _jest_sprzataczka(prac: models.Pracownik) -> bool:
    """Dostęp do formularza zamówień: dział techniczny + kwalifikacja z flagą `daje_dostep_zamowien`
    (fallback po nazwie „Sprzątaczka" dla danych sprzed migracji)."""
    return bool(prac and prac.dzial == "techniczny"
                and any(getattr(s, "daje_dostep_zamowien", False) or (s.nazwa or "") == SPRZATACZKA_NAZWA
                        for s in prac.kwalifikacje))


def _user_out(u: models.User) -> schemas.UserOut:
    """Konto użytkownika do odpowiedzi API (współdzielone: auth w main + /api/users w kadrach)."""
    import uprawnienia

    return schemas.UserOut(
        id=u.id, login=u.login, email=u.email, rola=u.rola, aktywny=bool(u.aktywny),
        pracownik_id=u.pracownik_id,
        dzial=u.pracownik.dzial if u.pracownik else None,
        sprzataczka=_jest_sprzataczka(u.pracownik) if u.pracownik else False,
        imie=u.pracownik.imie if u.pracownik else None,
        nazwisko=u.pracownik.nazwisko if u.pracownik else None,
        preset=uprawnienia.rozpoznaj_preset(u),
        uprawnienia_override=dict(u.uprawnienia_override or {}),
        uprawnienia=uprawnienia.efektywne(u),
    )


def unikalny_login_z_emaila(db, email: str) -> str:
    """Syntetyzuje wewnętrzny, unikalny `login` dla konta zakładanego e-mailem.
    Login pozostaje notnull i zasila denormalizacje (audyt/ogłoszenia), ale nie jest już
    kanałem logowania — użytkownik loguje się e-mailem. Bazujemy na części lokalnej adresu
    (alfanumeryczna, min. 5 znaków), rozwiązując kolizje sufiksem liczbowym."""
    baza = re.sub(r"[^a-z0-9]", "", (email or "").split("@")[0].lower()) or "konto"
    if len(baza) < 5:
        baza = (baza + "konto")[:5]
    baza = baza[:56]  # zostaw miejsce na sufiks w limicie 64 znaków
    kand, i = baza, 1
    while db.query(models.User).filter(models.User.login == kand).first() is not None:
        i += 1
        kand = f"{baza}{i}"
    return kand


# Litery 'ł/Ł' (i kilka innych) NIE rozkładają się przez NFKD — mapujemy je ręcznie,
# inaczej wypadłyby z dopasowania imion (np. „Łukasz" → „ukasz").
_PL_SPEC = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D"})


def _norm_nazwa(s: str) -> str:
    s = (s or "").translate(_PL_SPEC)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _przypisz_odbicia_do_pracownika(db, prac) -> int:
    """Po dodaniu/edycji pracownika podlinkuj wczesniej NIEDOPASOWANE odbicia RCP
    (pracownik_id IS NULL), ktorych znormalizowane imie+nazwisko pasuje do tego pracownika.
    Dzieki temu godziny z RCP trafiaja na konto od razu, bez czekania na okno agenta
    (agent dosyla tylko ostatnie OKNO_DNI dni). Zwraca liczbe podlinkowanych odbic."""
    cele = {
        _norm_nazwa(f"{prac.imie} {prac.nazwisko}"),
        _norm_nazwa(f"{prac.nazwisko} {prac.imie}"),
    }
    cele.discard("")
    if not cele:
        return 0
    n = 0
    for o in db.query(models.OdbicieRcp).filter(models.OdbicieRcp.pracownik_id.is_(None)).all():
        if _norm_nazwa(o.imie_nazwisko or "") in cele:
            o.pracownik_id = prac.id
            n += 1
    if n:
        db.commit()
    return n


# „Parkiet": stanowiska, których nazwa zaczyna się od „Sala" (Sala, Sala-ABC, Sala-RZP,
# Sala-Bar...). Spośród nich wybieramy osobę ZAMYKAJĄCĄ lokal — patrz _przelicz_zamykajacego (main).
SALA_PREFIX = "sala"


def _data_env(nazwa: str, domyslnie: str):
    """Czyta datę (RRRR-MM-DD) ze zmiennej środowiskowej; puste/niepoprawne -> None."""
    s = (os.environ.get(nazwa, domyslnie) or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# Rozliczenia sali liczymy DOPIERO od dnia startu systemu — inaczej kelnerom wyskakują
# „zaległe" rozliczenia ze zmian Gastro sprzed wdrożenia (które nigdy nie były potwierdzane
# w aplikacji). Sterowane env ROZLICZENIA_START=RRRR-MM-DD (ustawiane na serwerze na dzień
# uruchomienia; puste/brak = bez cięcia). Po ~21 dniach naturalne okno (dziś−21) i tak wyprzedza
# tę datę, więc cięcie samo przestaje cokolwiek zmieniać.
ROZLICZENIA_START = _data_env("ROZLICZENIA_START", "")


def _sala_stanowisko_ids(db) -> set:
    """Stanowiska parkietu (kelnerzy). Rola 'sala' albo — fallback — nazwa zaczyna się od „Sala"."""
    return {s.id for s in db.query(models.Stanowisko).all()
            if s.rola == "sala" or (s.nazwa or "").strip().lower().startswith(SALA_PREFIX)}


def _zamowienie_out(z, prac_map):
    # Lista NIE zawiera samego zdjęcia (może być ciężkie) — tylko flagę; obrazek pobiera się osobno.
    return {
        "id": z.id, "pracownik": prac_map.get(z.pracownik_id),
        "nazwa": z.nazwa, "ilosc": z.ilosc, "notatka": z.notatka,
        "ma_zdjecie": bool(z.zdjecie), "status": z.status,
        "utworzono_at": z.utworzono_at.isoformat() if z.utworzono_at else None,
    }


def _urlop_out(u, prac_map):
    return {
        "id": u.id, "pracownik": prac_map.get(u.pracownik_id), "pracownik_id": u.pracownik_id,
        "start": str(u.start), "koniec": str(u.koniec), "powod": u.powod,
        "status": u.status, "utworzono_at": u.utworzono_at.isoformat() if u.utworzono_at else None,
    }


def _gastro_dla_kelnera(db, pid: int, data: date) -> dict:
    """Prefill kelnera z Gastro: G/T = zadeklarowane gotówka/karta, FV = sprzedaż KARTA_FV+GOTÓWKA_FV.
    (BON pomijamy — nie przechodzi przez kasę i nie wchodzi do utargu.)"""
    rows = db.query(models.RozliczenieGastro).filter_by(pracownik_id=pid, data=data).all()
    g = sum(r.deklarowane for r in rows if r.forma == "GOTÓWKA")
    t = sum(r.deklarowane for r in rows if r.forma == "KARTA")
    fv = sum(r.sprzedaz for r in rows if r.forma in ("KARTA_FV", "GOTÓWKA_FV"))
    return {"gotowka": round(g, 2), "karta": round(t, 2), "fv": round(fv, 2)}


def _pids_sali_dnia(db, data: date) -> set:
    """Kandydaci do rozliczenia sali danego dnia: grafik Sali + faktycznie pracujący
    (zamknięte rozliczenie Gastro tego dnia ∩ obsada sali w oknie ±21 dni — radzi sobie
    z rozjazdem: data zmiany w grafiku ≠ DataOtwarcia rozliczenia w Gastro)."""
    sala_ids = _sala_stanowisko_ids(db)
    if not sala_ids:
        return set()
    pids = {a.pracownik_id for a in db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data == data, models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).all()}
    sala_staff = {a.pracownik_id for a in db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= data - timedelta(days=21),
        models.PrzydzialZmiany.data <= data + timedelta(days=21),
        models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).all()}
    gastro_pids = {r.pracownik_id for r in db.query(models.RozliczenieGastro).filter(
        models.RozliczenieGastro.data == data, models.RozliczenieGastro.pracownik_id.isnot(None)).all()}
    return pids | (gastro_pids & sala_staff)


def _zbuduj_rozliczenie(db, data: date) -> models.RozliczenieDnia:
    """Get-or-create rozliczenia dnia. Tryb 'indywidualnie': wiersze kelnerów z grafiku Sali
    (prefill z Gastro). Tryb 'pula': jeden zbiorczy zestaw — prefill z AGREGATU Gastro całej
    obsady, ustawiany raz przy tworzeniu (żeby nie nadpisywać ręcznych korekt przy każdym GET)."""
    tryb = get_lokal_config(db).rozliczenia_tryb_kelnera or "indywidualnie"
    roz = db.query(models.RozliczenieDnia).filter_by(data=data).first()
    swiezy = roz is None
    if roz is None:
        roz = models.RozliczenieDnia(data=data, status="robocze", utworzono_at=utcnow_naive(),
                                     terminale=[], kasy=[])
        db.add(roz)
        try:
            db.flush()
        except Exception:
            # Wyścig przy pierwszym dostępie do nowego dnia (kolumna data ma UNIQUE) — ktoś już
            # utworzył rozliczenie. Rollback + ponowny odczyt istniejącego zamiast 500.
            db.rollback()
            roz = db.query(models.RozliczenieDnia).filter_by(data=data).first()
            swiezy = False

    pids = _pids_sali_dnia(db, data)
    if tryb == "pula":
        if swiezy and pids:   # prefill puli agregatem Gastro — tylko przy tworzeniu
            g = t = fv = 0.0
            for pid in pids:
                d = _gastro_dla_kelnera(db, pid, data)
                g += d["gotowka"]; t += d["karta"]; fv += d["fv"]
            roz.pula_gotowka = round(g, 2); roz.pula_karta = round(t, 2); roz.pula_fv = round(fv, 2)
    else:
        istn = {k.pracownik_id for k in roz.kelnerzy}
        for pid in pids:
            if pid in istn:
                continue
            g = _gastro_dla_kelnera(db, pid, data)
            roz.kelnerzy.append(models.RozliczenieKelner(
                pracownik_id=pid, gotowka=g["gotowka"], karta=g["karta"], fv=g["fv"]))
            istn.add(pid)
    db.commit(); db.refresh(roz)
    return roz


# ── NAPIWKI (pula dnia dzielona między obsługę sali wg godzin z RCP) ──────────
def _rozdziel_kwote(kwota: float, wagi):
    """Dzieli kwotę (w złotych) na len(wagi) części proporcjonalnie do `wagi`, DOKŁADNIE co do
    grosza (metoda największej reszty) — suma części = kwota. Zerowe/ujemne wagi → podział równy."""
    n = len(wagi)
    if n == 0:
        return []
    grosze = round(float(kwota) * 100)
    suma = sum(wagi)
    if grosze <= 0:
        return [0.0] * n
    if suma <= 0:                                  # brak wag → po równo
        baza, reszta = divmod(grosze, n)
        return [round((baza + (1 if i < reszta else 0)) / 100, 2) for i in range(n)]
    surowe = [grosze * w / suma for w in wagi]
    podl = [int(x) for x in surowe]
    reszta = grosze - sum(podl)
    for i in sorted(range(n), key=lambda i: surowe[i] - podl[i], reverse=True)[:reszta]:
        podl[i] += 1
    return [round(g / 100, 2) for g in podl]


def _napiwki_obsada(db, data: date):
    """Obsada sali danego dnia (kandydaci do napiwków) + godziny z RCP. Baza = pracownicy z
    przydziałem na Sali tego dnia; godziny sumowane z odbić RCP (0, gdy brak odbicia)."""
    sala_ids = _sala_stanowisko_ids(db)
    if not sala_ids:
        return []
    pids = {a.pracownik_id for a in db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data == data,
        models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).all()}
    if not pids:
        return []
    godz = defaultdict(float)
    for o in db.query(models.OdbicieRcp).filter(
            models.OdbicieRcp.data == data, models.OdbicieRcp.pracownik_id.in_(pids)).all():
        godz[o.pracownik_id] += float(o.godziny or 0.0)
    prac = {p.id: f"{p.imie} {p.nazwisko}"
            for p in db.query(models.Pracownik).filter(models.Pracownik.id.in_(pids)).all()}
    out = [{"pracownik_id": pid, "pracownik": prac.get(pid, "—"), "godziny": round(godz.get(pid, 0.0), 2)}
           for pid in pids]
    out.sort(key=lambda x: x["pracownik"])
    return out


def _napiwki_podzial(db, data: date) -> dict:
    """Buduje podział napiwków dnia: kwota + sposób + lista {pracownik, godziny, kwota}."""
    rec = db.query(models.NapiwkiDnia).filter_by(data=data).first()
    kwota = float(rec.kwota) if rec else 0.0
    sposob = rec.sposob if (rec and rec.sposob in ("godziny", "rowno")) else "godziny"
    obsada = _napiwki_obsada(db, data)
    if sposob == "godziny" and sum(o["godziny"] for o in obsada) > 0:
        wagi = [o["godziny"] for o in obsada]
    else:
        wagi = [1] * len(obsada)                   # „rowno" albo brak godzin RCP → po równo
    kwoty = _rozdziel_kwote(kwota, wagi)
    podzial = [{**o, "kwota": k} for o, k in zip(obsada, kwoty)]
    return {"data": str(data), "kwota": round(kwota, 2), "sposob": sposob,
            "suma_godzin": round(sum(o["godziny"] for o in obsada), 2), "podzial": podzial}


def _teraz_lokalnie():
    """Czas sciany zegarowej w strefie RCP (Europe/Warsaw) jako naive datetime — timestampy
    z RCP sa lokalne i naive. Gdy strefa niedostepna -> None (wtedy NIE blokujemy powiadomien)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None)
    except Exception:
        return None
