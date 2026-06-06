"""Raport godzin: odbicia RCP (kopia na VPS) × stanowiska z OPUBLIKOWANEGO grafiku.

VPS nie łączy się z bazą RCP — czyta własną tabelę `OdbicieRcp` (zasilaną przez lokalnego
agenta). Tu następuje złączenie:
  • godziny przepracowane  ← z odbicia (wyjście − wejście, policzone przy ingest),
  • stanowisko             ← z grafiku (PrzydzialZmiany) z tego dnia, TYLKO jeśli tydzień
                              jest opublikowany (PublikacjaGrafiku); inaczej kubełek osobny,
  • pracownik              ← `pracownik_id` rozwiązany przy ingest (fallback: kubełek niedopasowanych).

`raport_godzin_miesiac` przyjmuje opcjonalnie wstrzyknięte `odbicia` (test) lub czyta z bazy.
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time

import models

BUCKET_NIEOPUBLIKOWANY = "(grafik nieopublikowany)"
BUCKET_POZA_GRAFIKIEM = "(poza grafikiem)"


def wczytaj_odbicia(db, start: date, end: date):
    """Zakończone zmiany (mają wyjście i policzone godziny) z zakresu."""
    rows = (
        db.query(models.OdbicieRcp)
        .filter(
            models.OdbicieRcp.data >= start,
            models.OdbicieRcp.data <= end,
            models.OdbicieRcp.wyjscie.isnot(None),
        )
        .all()
    )
    return [
        {
            "pracownik_id": o.pracownik_id,
            "imie_nazwisko": o.imie_nazwisko,
            "data": o.data,
            "godziny": float(o.godziny or 0.0),
            "wejscie": o.wejscie,
        }
        for o in rows
    ]


def _as_time(v):
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, time):
        return v
    if not v:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(str(v)[: len(fmt) + 2], fmt).time()
        except ValueError:
            continue
    return None


def _wybierz_przydzial(przydzialy, wejscie_time):
    """Przy zmianie dzielonej (>1 przydział) wybiera tę, którą pracownik realnie rozpoczął
    (najpóźniejsze godz_od ≤ czas wejścia). Fallback: pierwszy."""
    if len(przydzialy) == 1 or wejscie_time is None:
        return przydzialy[0]
    pasujace = [a for a in przydzialy if a.godz_od and a.godz_od <= wejscie_time]
    return max(pasujace, key=lambda a: a.godz_od) if pasujace else przydzialy[0]


def _zakresy_publikacji(db):
    return [(p.start, p.koniec) for p in db.query(models.PublikacjaGrafiku).all()]


def _opublikowany(d: date, zakresy) -> bool:
    return any(s <= d <= k for s, k in zakresy)


def raport_godzin_miesiac(db, rok: int, miesiac: int, odbicia=None, tylko_pracownik_id=None):
    start = date(rok, miesiac, 1)
    end = date(rok, miesiac, monthrange(rok, miesiac)[1])
    if odbicia is None:
        odbicia = wczytaj_odbicia(db, start, end)

    zakresy_pub = _zakresy_publikacji(db)
    stan_nazwa = {s.id: s.nazwa for s in db.query(models.Stanowisko).all()}
    prac_nazwa = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}

    przydzialy = (
        db.query(models.PrzydzialZmiany)
        .filter(models.PrzydzialZmiany.data >= start, models.PrzydzialZmiany.data <= end)
        .all()
    )
    graf = defaultdict(list)
    for a in przydzialy:
        graf[(a.pracownik_id, a.data)].append(a)

    godziny = defaultdict(lambda: defaultdict(float))  # pracownik_id -> stanowisko -> godziny
    niedopasowani = defaultdict(float)

    for z in odbicia:
        d = z["data"]
        if isinstance(d, datetime):
            d = d.date()
        h = float(z.get("godziny") or 0.0)
        if not (start <= d <= end) or h <= 0:
            continue

        pid = z.get("pracownik_id")
        if tylko_pracownik_id is not None and pid != tylko_pracownik_id:
            continue
        if pid is None:
            niedopasowani[(z.get("imie_nazwisko") or "").strip()] += h
            continue

        if not _opublikowany(d, zakresy_pub):
            bucket = BUCKET_NIEOPUBLIKOWANY
        else:
            przy = graf.get((pid, d), [])
            if not przy:
                bucket = BUCKET_POZA_GRAFIKIEM
            else:
                wybrany = _wybierz_przydzial(przy, _as_time(z.get("wejscie")))
                bucket = stan_nazwa.get(wybrany.stanowisko_id, "?")
        godziny[pid][bucket] += h

    pracownicy_out = []
    for pid, rozb in godziny.items():
        rozbicie = sorted(
            ({"stanowisko": k, "godziny": round(v, 2)} for k, v in rozb.items()),
            key=lambda x: -x["godziny"],
        )
        pracownicy_out.append({
            "pracownik_id": pid,
            "pracownik": prac_nazwa.get(pid, "?"),
            "suma_godzin": round(sum(rozb.values()), 2),
            "stanowiska": rozbicie,
        })
    pracownicy_out.sort(key=lambda x: x["pracownik"])

    return {
        "rok": rok,
        "miesiac": miesiac,
        "pracownicy": pracownicy_out,
        "niedopasowani_rcp": [
            {"imie_nazwisko": k, "godziny": round(v, 2)} for k, v in sorted(niedopasowani.items())
        ],
    }
