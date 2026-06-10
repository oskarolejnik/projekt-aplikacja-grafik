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
from datetime import date, datetime, time, timedelta

import models

BUCKET_NIEOPUBLIKOWANY = "(grafik nieopublikowany)"
BUCKET_POZA_GRAFIKIEM = "(poza grafikiem)"
# „Noc imprezowa": odbicie z wejściem przed tą godziną doliczamy do imprezy z DNIA POPRZEDNIEGO
# (impreza ciągnie się po północy, np. 15:00 → 3:20). Pierwsze wejście po tej godzinie = nowy dzień.
GRANICA_NOCY = time(9, 0)
# Cięcia godzin (wejście wcześniej niż grafik) — raport admina je wyróżnia. Pokazujemy
# wszystko powyżej 10 minut, z podziałem: „duże" (>1h, zwykle zmiana w grafiku) i „małe" (10 min–1h).
PROG_MALE_CIECIE = 10 / 60   # od >10 min w ogóle pokazujemy
PROG_DUZE_CIECIE = 1.0       # >1h = duże; 10 min–1h = małe
# Pracownik techniczny: nikt nie układa mu grafiku — liczymy pełne godziny RCP × stawka,
# na to jedno stanowisko (stawka ustawiana per osoba, jak w kuchni).
TECHNICZNY_NAZWA = "Techniczny"
# Stanowisko kuchni. Pracownik działu „kuchnia" dostaje stawkę za WSZYSTKIE godziny RCP —
# także te BEZ wpisu w grafiku (np. obieranie warzyw: pracuje, choć nikt go nie wpisał).
# Gdy JEST wpisany w opublikowany grafik → start przycinamy normalnie (Zaoszczędzone);
# gdy go nie ma → pełne godziny na to stanowisko (stawka per osoba).
KUCHNIA_NAZWA = "Kuchnia"


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
            "wyjscie": o.wyjscie,
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


def _hhmm(v):
    """Czas (datetime/time/str) → 'HH:MM' albo None."""
    t = _as_time(v)
    return t.strftime("%H:%M") if t else None


def _minuty(t: time) -> float:
    return t.hour * 60 + t.minute + t.second / 60.0


def efektywne_i_oszczednosc(wej_t, godz_od, h):
    """Przytnij START zmiany do grafiku: godziny liczone dopiero od zaplanowanej godziny (godz_od).
    Kto odbije się wcześniej, nie dostaje tych minut. Zwraca (godziny_liczone, zaoszczedzone_godziny).
    Bez godz_od albo bez czasu wejścia → bez przycinania (pełne godziny, 0 zaoszczędzone)."""
    if godz_od and wej_t is not None:
        saved = min(h, max(0.0, (_minuty(godz_od) - _minuty(wej_t)) / 60.0))
        return h - saved, saved
    return h, 0.0


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
    _stanowiska = db.query(models.Stanowisko).all()
    stan_nazwa = {s.id: s.nazwa for s in _stanowiska}
    nazwa_to_id = {s.nazwa: s.id for s in _stanowiska}
    # Stanowiska imprezowe (po nazwie zawierającej „imprez") — dla reguły nocy imprezowej.
    imprezy_ids = {s.id for s in _stanowiska if "imprez" in (s.nazwa or "").lower()}
    _prac = db.query(models.Pracownik).all()
    prac_nazwa = {p.id: f"{p.imie} {p.nazwisko}" for p in _prac}
    prac_dzial = {p.id: (p.dzial or "obsluga") for p in _prac}
    techniczny_ids = {pid for pid, dz in prac_dzial.items() if dz == "techniczny"}
    kuchnia_ids = {pid for pid, dz in prac_dzial.items() if dz == "kuchnia"}
    stawki_map = {(r.pracownik_id, r.stanowisko_id): float(r.stawka or 0.0)
                  for r in db.query(models.StawkaPracownika).all()}

    # Wczytujemy też przydziały z dnia POPRZEDZAJĄCEGO miesiąc — impreza z 31. może mieć
    # „ogon" odbity 1. dnia kolejnego miesiąca (regułą nocy imprezowej dolicza się wstecz).
    przydzialy = (
        db.query(models.PrzydzialZmiany)
        .filter(models.PrzydzialZmiany.data >= start - timedelta(days=1),
                models.PrzydzialZmiany.data <= end)
        .all()
    )
    graf = defaultdict(list)
    for a in przydzialy:
        graf[(a.pracownik_id, a.data)].append(a)

    godziny = defaultdict(lambda: defaultdict(float))       # pracownik_id -> stanowisko -> godziny (przycięte)
    oszczednosci = defaultdict(lambda: defaultdict(float))  # pracownik_id -> stanowisko -> zaoszczędzone godz
    niedopasowani = defaultdict(float)
    duze_ciecia = []  # ucięcia > 1h (tylko dla admina)
    male_ciecia = []  # ucięcia 10 min – 1h (tylko dla admina)
    poza_szczegoly = defaultdict(list)  # pid -> [ {data, od, do, godziny} ] — konkretne zmiany poza grafikiem

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

        # Pracownik techniczny: bez grafiku — pełne godziny RCP na stanowisko „Techniczny".
        if pid in techniczny_ids:
            godziny[pid][TECHNICZNY_NAZWA] += h
            continue

        # Reguła nocy imprezowej: wejście przed 9:00, a poprzedniego dnia pracownik miał
        # przydział na Imprezy (i tamten dzień jest opublikowany) → godziny należą do tamtej
        # imprezy (impreza 15:00 → 3:20 lub ogon odbity po północy). Liczymy na stanowisko Imprezy.
        wej_t = _as_time(z.get("wejscie"))
        if wej_t is not None and wej_t < GRANICA_NOCY:
            poprzedni = d - timedelta(days=1)
            if _opublikowany(poprzedni, zakresy_pub):
                event = next((a for a in graf.get((pid, poprzedni), [])
                              if a.stanowisko_id in imprezy_ids), None)
                if event is not None:
                    godziny[pid][stan_nazwa.get(event.stanowisko_id, "?")] += h
                    continue

        opub = _opublikowany(d, zakresy_pub)
        przy = graf.get((pid, d), []) if opub else []   # przydziały liczymy tylko z OPUBLIKOWANEGO grafiku
        if not przy:
            # Brak przydziału w grafiku (tydzień nieopublikowany albo po prostu brak wpisu).
            if pid in kuchnia_ids:
                # KUCHNIA: płacimy za WSZYSTKIE godziny RCP, także bez wpisu w grafiku
                # (np. obieranie warzyw). Pełne godziny na stanowisko „Kuchnia" (stawka per osoba).
                godziny[pid][KUCHNIA_NAZWA] += h
            else:
                bucket = BUCKET_NIEOPUBLIKOWANY if not opub else BUCKET_POZA_GRAFIKIEM
                godziny[pid][bucket] += h     # bez przycinania (brak grafiku) — osobny kubełek, 0 zł
                poza_szczegoly[pid].append({"data": str(d), "od": _hhmm(z.get("wejscie")),
                                            "do": _hhmm(z.get("wyjscie")), "godziny": round(h, 2)})
        else:
            wybrany = _wybierz_przydzial(przy, wej_t)
            bucket = stan_nazwa.get(wybrany.stanowisko_id, "?")
            # Przytnij start do grafiku: licz dopiero od zaplanowanej godziny (godz_od).
            liczone, saved = efektywne_i_oszczednosc(wej_t, wybrany.godz_od, h)
            godziny[pid][bucket] += liczone
            if saved > 0:
                oszczednosci[pid][bucket] += saved
                if saved > PROG_MALE_CIECIE:  # >10 min — wyróżnij dla admina (duże/małe)
                    wpis = {
                        "pracownik_id": pid,
                        "pracownik": prac_nazwa.get(pid, "?"),
                        "data": str(d),
                        "stanowisko": bucket,
                        "godziny_uciete": round(saved, 2),
                        "wejscie": wej_t.strftime("%H:%M") if wej_t else None,
                        "planowane": wybrany.godz_od.strftime("%H:%M") if wybrany.godz_od else None,
                    }
                    (duze_ciecia if saved > PROG_DUZE_CIECIE else male_ciecia).append(wpis)

    stanowiska_agg = defaultdict(lambda: {"godziny": 0.0, "kwota": 0.0})  # koszt/godziny per stanowisko (wszyscy)
    poza_grafikiem = []  # pracownicy z godzinami NIEPRZYPISANYMI do grafiku (poza grafikiem / nieopublikowany)
    bez_stawki = []      # godziny na stanowisku BEZ ustawionej stawki (liczą się jako 0 zł)
    pracownicy_out = []
    for pid, rozb in godziny.items():
        rozbicie = []
        do_wyplaty = 0.0
        zaosz_godz = 0.0
        zaosz_kwota = 0.0
        for k, v in sorted(rozb.items(), key=lambda x: -x[1]):
            sid = nazwa_to_id.get(k)
            stawka = stawki_map.get((pid, sid), 0.0) if sid is not None else 0.0
            kwota = round(v * stawka, 2)
            do_wyplaty += kwota
            rozbicie.append({"stanowisko": k, "godziny": round(v, 2),
                             "stawka": round(stawka, 2), "kwota": kwota})
            stanowiska_agg[k]["godziny"] += v
            stanowiska_agg[k]["kwota"] += kwota
            if sid is not None and stawka == 0 and v > 0:  # godziny na stanowisku, ale BRAK stawki → 0 zł
                bez_stawki.append({"pracownik_id": pid, "pracownik": prac_nazwa.get(pid, "?"),
                                   "stanowisko": k, "godziny": round(v, 2)})
            sg = oszczednosci.get(pid, {}).get(k, 0.0)  # zaoszczędzone na tym stanowisku
            if sg > 0:
                zaosz_godz += sg
                zaosz_kwota += sg * stawka
        pracownicy_out.append({
            "pracownik_id": pid,
            "pracownik": prac_nazwa.get(pid, "?"),
            "dzial": prac_dzial.get(pid, "obsluga"),
            "suma_godzin": round(sum(rozb.values()), 2),
            "stanowiska": rozbicie,
            "do_wyplaty": round(do_wyplaty, 2),
            "zaoszczedzone_godziny": round(zaosz_godz, 2),
            "zaoszczedzone_kwota": round(zaosz_kwota, 2),
        })
        # Godziny nieprzypisane do grafiku (odbił się, ale nie ma go w grafiku / tydzień nieopublikowany)
        # — z rozbiciem na konkretne dni.
        poza_p = poza_szczegoly.get(pid, [])
        if poza_p:
            poza_grafikiem.append({
                "pracownik_id": pid,
                "pracownik": prac_nazwa.get(pid, "?"),
                "godziny": round(sum(x["godziny"] for x in poza_p), 2),
                "zmiany": sorted(poza_p, key=lambda x: (x["data"], x["od"] or "")),
            })
    pracownicy_out.sort(key=lambda x: (-x["do_wyplaty"], x["pracownik"]))  # malejąco wg wypłaty

    return {
        "rok": rok,
        "miesiac": miesiac,
        "pracownicy": pracownicy_out,
        # Ile zaoszczędziliśmy przez liczenie wg grafiku (kto odbija się wcześniej niż wpisany).
        "zaoszczedzone": {
            "godziny": round(sum(p["zaoszczedzone_godziny"] for p in pracownicy_out), 2),
            "kwota": round(sum(p["zaoszczedzone_kwota"] for p in pracownicy_out), 2),
        },
        # Koszt i godziny w rozbiciu na stanowiska (sumarycznie, wszyscy pracownicy).
        "stanowiska_podsumowanie": [
            {"stanowisko": k, "godziny": round(d["godziny"], 2), "kwota": round(d["kwota"], 2)}
            for k, d in sorted(stanowiska_agg.items(), key=lambda x: -x[1]["godziny"])
        ],
        # Godziny NIEPRZYPISANE do grafiku (kto, ile) — sumarycznie, malejąco.
        "poza_grafikiem": sorted(poza_grafikiem, key=lambda x: -x["godziny"]),
        # Godziny na stanowisku BEZ ustawionej stawki (kto, stanowisko, ile) — liczą się jako 0 zł.
        "bez_stawki": sorted(bez_stawki, key=lambda x: -x["godziny"]),
        # Cięcia godzin (wejście wcześniej niż grafik) — pojedyncze przypadki, TYLKO dla admina.
        "duze_ciecia": sorted(duze_ciecia, key=lambda x: -x["godziny_uciete"]),
        "male_ciecia": sorted(male_ciecia, key=lambda x: -x["godziny_uciete"]),
        "niedopasowani_rcp": [
            {"imie_nazwisko": k, "godziny": round(v, 2)} for k, v in sorted(niedopasowani.items())
        ],
    }
