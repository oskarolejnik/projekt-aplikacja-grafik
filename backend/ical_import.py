"""Parser plików .ics (eksport z iCloud / Apple Calendar) dla importu imprez.

Bez zależności zewnętrznych. Dla każdego VEVENT zwraca: uid, datę (z DTSTART),
tytuł (SUMMARY), opis (DESCRIPTION), lokalizację (LOCATION). Z tytułu/opisu
wyciągamy pola imprezy: nazwisko, typ, liczba_osob, telefon, sala, zadatek.

WAŻNE: GODZINY NIE CZYTAMY ŚWIADOMIE. W kalendarzu „Imprezy Rajcula" godzina
to tylko orientacyjny slot — obsada liczona jest z liczby osób, nie z godziny
(impreza dostaje godzina='Brak'). Z DTSTART bierzemy wyłącznie datę.
"""

import re
from datetime import date


# ── NISKOPOZIOMOWY PARSER .ics ──────────────────────────────────────────────

def _odwin_linie(tekst):
    """RFC5545 line unfolding: linia złamana = następna zaczyna się od spacji/taba
    i jest doklejana do poprzedniej (bez tego wiodącego znaku)."""
    surowe = (tekst or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    linie = []
    for ln in surowe:
        if ln[:1] in (" ", "\t") and linie:
            linie[-1] += ln[1:]
        else:
            linie.append(ln)
    return linie


def _odkoduj(v):
    """Odkodowanie escapów tekstowych RFC5545 w wartości: \\n -> nowa linia, \\, \\; \\\\ dosłownie."""
    out = []
    i = 0
    n = len(v)
    while i < n:
        c = v[i]
        if c == "\\" and i + 1 < n:
            nx = v[i + 1]
            if nx in ("n", "N"):
                out.append("\n")
            else:  # ',', ';', '\\' i każdy inny -> znak dosłowny
                out.append(nx)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _rozbij_linie(ln):
    """'NAZWA;PARAM=...:wartość' -> ('NAZWA', 'wartość'). Dzielimy na pierwszym ':'.
    Nazwę odcinamy do pierwszego ';' (parametry pomijamy) i podajemy WIELKIMI literami."""
    dc = ln.find(":")
    if dc == -1:
        return None, None
    glowa = ln[:dc]
    wartosc = ln[dc + 1:]
    nazwa = glowa.split(";", 1)[0].strip().upper()
    return nazwa, wartosc


def _data_z_dtstart(wartosc):
    """Z wartości DTSTART bierzemy TYLKO datę (pierwsze 8 cyfr RRRRMMDD). Godzina nieistotna.
    Działa dla 'VALUE=DATE' (RRRRMMDD), 'RRRRMMDDTHHMMSS' oraz wariantu z 'Z' (UTC)."""
    cyfry = re.sub(r"[^0-9]", "", wartosc or "")
    if len(cyfry) < 8:
        return None
    try:
        return date(int(cyfry[0:4]), int(cyfry[4:6]), int(cyfry[6:8]))
    except ValueError:
        return None


def parsuj_ics(tekst):
    """Zwraca listę dict {uid, data, tytul, opis, lokalizacja} dla każdego VEVENT.
    Pomija VTIMEZONE (na poziomie kalendarza) oraz zagnieżdżone VALARM (wewnątrz VEVENT)."""
    linie = _odwin_linie(tekst)
    eventy = []
    biezacy = None
    w_alarm = 0          # licznik zagnieżdżonych VALARM (ich właściwości ignorujemy)
    w_vtimezone = 0      # VTIMEZONE na poziomie kalendarza (zawiera własne DTSTART)
    for raw in linie:
        s = raw.strip()
        if s == "BEGIN:VTIMEZONE":
            w_vtimezone += 1
            continue
        if s == "END:VTIMEZONE":
            if w_vtimezone:
                w_vtimezone -= 1
            continue
        if w_vtimezone:
            continue
        if s == "BEGIN:VEVENT":
            biezacy = {"uid": None, "data": None, "tytul": "", "opis": "", "lokalizacja": ""}
            w_alarm = 0
            continue
        if s == "END:VEVENT":
            if biezacy is not None:
                eventy.append(biezacy)
            biezacy = None
            continue
        if biezacy is None:
            continue
        if s == "BEGIN:VALARM":
            w_alarm += 1
            continue
        if s == "END:VALARM":
            if w_alarm:
                w_alarm -= 1
            continue
        if w_alarm:
            continue
        nazwa, wartosc = _rozbij_linie(raw)
        if not nazwa:
            continue
        if nazwa == "UID":
            biezacy["uid"] = wartosc.strip()
        elif nazwa == "SUMMARY":
            biezacy["tytul"] = _odkoduj(wartosc).strip()
        elif nazwa == "DESCRIPTION":
            biezacy["opis"] = _odkoduj(wartosc).strip()
        elif nazwa == "LOCATION":
            biezacy["lokalizacja"] = _odkoduj(wartosc).strip()
        elif nazwa == "DTSTART":
            biezacy["data"] = _data_z_dtstart(wartosc)
    return eventy


# ── MAPOWANIE TREŚCI NA POLA IMPREZY ────────────────────────────────────────

# Honoryfikatywy na początku tytułu: „P. Jarkowski", „P.Golda", „Państwo Nowak", „Pani …".
# Pojedyncze „P"/„p" usuwamy TYLKO gdy po nim jest kropka lub spacja (żeby nie obciąć imienia „Paweł").
_RE_HONOR = re.compile(r"^\s*(?:(?:pa[nń]stwo|pani|pan)\.?\s+|p\.\s*|p\s+)", re.IGNORECASE)

# Słowa-klucze typu imprezy -> wartość typ (jak w kalendarzu). Szukamy rdzeni (bez końcówek).
_TYPY = (
    ("wesel", "wesele"), ("poprawin", "wesele"),
    ("komuni", "komunia"),
    ("chrzcin", "chrzciny"), ("chrzest", "chrzciny"), ("chrzt", "chrzciny"),
    ("styp", "stypa"), ("konsolacj", "stypa"), ("pogrzeb", "stypa"),
    ("osiemnast", "urodziny"), ("urodzin", "urodziny"),
    ("firmow", "impreza firmowa"), ("integracj", "impreza firmowa"),
    ("chrzcin", "chrzciny"),
)

_RE_OSOB = re.compile(r"(\d{1,4})\s*os", re.IGNORECASE)            # „15 osób", „80 os", „30 osób,"
_RE_TEL = re.compile(r"(?<!\d)(\d{3})[\s\-]?(\d{3})[\s\-]?(\d{3})(?!\d)")  # polski numer 9-cyfrowy
_RE_ZADATEK = re.compile(r"(\d[\d \t]*(?:[.,]\d+)?)\s*z[lł]", re.IGNORECASE)  # „500 zł", „2000 zł", „1 500 zł" (spacja tysięcy OK, ale bez przeskoku przez nową linię)


def _wyczysc_nazwisko(tytul):
    """Z tytułu robi nazwisko klienta: zdejmuje honoryfikatyw z przodu. Gdy go brak (np. para
    weselna 'Mateusz Przybyła Czerwonka Weronika') — zwraca tytuł bez zmian."""
    t = (tytul or "").strip()
    if not t:
        return ""
    return _RE_HONOR.sub("", t).strip() or t


def _wykryj_typ(tekst):
    t = (tekst or "").lower()
    for klucz, typ in _TYPY:
        if klucz in t:
            return typ
    return None


def _wykryj_liczbe_osob(tekst):
    m = _RE_OSOB.search(tekst or "")
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _wykryj_telefon(tekst):
    m = _RE_TEL.search(tekst or "")
    if m:
        return f"{m.group(1)} {m.group(2)} {m.group(3)}"
    return None


def _wykryj_zadatek(tekst):
    m = _RE_ZADATEK.search(tekst or "")
    if not m:
        return 0.0
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _sala_z_lokalizacji(lok):
    """Z LOCATION bierzemy sam kod sali (pierwszy token przed adresem / przecinkiem)."""
    if not lok:
        return None
    token = re.split(r"[\n,]", lok, 1)[0].strip()
    return (token[:64] or None)


def pola_imprezy(ev):
    """Z surowego eventu (z parsuj_ics) liczy pola domenowe imprezy."""
    tytul = (ev.get("tytul") or "").strip()
    opis = (ev.get("opis") or "").strip()
    lok = (ev.get("lokalizacja") or "").strip()
    return {
        "nazwisko": _wyczysc_nazwisko(tytul),
        "typ": _wykryj_typ(opis) or _wykryj_typ(tytul),
        "liczba_osob": _wykryj_liczbe_osob(opis) or _wykryj_liczbe_osob(tytul),
        "telefon": _wykryj_telefon(opis) or _wykryj_telefon(tytul),
        "sala": _sala_z_lokalizacji(lok),
        "zadatek": _wykryj_zadatek(opis),
        "notatka": (opis or None),
    }


def wczytaj_imprezy_z_ics(tekst):
    """Wygodny wrapper: parsuje .ics i scala z polami domenowymi.
    Zwraca listę dict {uid, data, nazwisko, typ, liczba_osob, telefon, sala, zadatek, notatka}."""
    out = []
    for ev in parsuj_ics(tekst):
        rec = {"uid": ev.get("uid"), "data": ev.get("data")}
        rec.update(pola_imprezy(ev))
        out.append(rec)
    return out
