from datetime import date, time, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from typing import List
import models
import prawo_pracy
from deps import get_lokal_config

def auto_assign(db: Session, start: date, end: date) -> dict:
    """
    Algorytm automatycznego przydzielania pracowników do zmian.
    Uwzględnia kwalifikacje, dyspozycyjność oraz zbalansowanie liczby zmian.
    """
    pracownicy = db.query(models.Pracownik).filter(models.Pracownik.aktywny == True).all()
    # Limity prawa pracy z konfiguracji lokalu — automat NIE może układać grafiku łamiącego KP
    # (odpoczynek, maks. dni w tygodniu/miesiącu), którego ręczny przydział by nie dopuścił. 0=wyłączony.
    _cfg = get_lokal_config(db)
    _limity = {"min_odpoczynek_h": _cfg.praca_min_odpoczynek_h or 0,
               "max_dni_tydzien": _cfg.praca_max_dni_tydzien or 0,
               "max_dni_miesiac": _cfg.praca_max_dni_miesiac or 0}
    stanowiska = {s.id: s for s in db.query(models.Stanowisko).all()}
    # Parkiet (rola 'sala' lub — fallback — nazwa „Sala*") ma PRIORYTET przy obsadzaniu.
    sala_ids = {sid for sid, st in stanowiska.items()
                if getattr(st, "rola", None) == "sala" or (st.nazwa or "").strip().lower().startswith("sala")}
    wymagania  = db.query(models.WymaganiaDnia).filter(
        models.WymaganiaDnia.data >= start, models.WymaganiaDnia.data <= end
    ).all()
    dyspozycje = db.query(models.Dyspozycja).filter(
        models.Dyspozycja.data >= start, models.Dyspozycja.data <= end
    ).all()

    # Zaakceptowane urlopy nakładające się na zakres — blokują AUTO-przydział w te dni
    # (ręczny wpis dalej możliwy; to tylko algorytm). Budujemy zbiór (pracownik_id, dzień).
    urlop_dni = set()
    urlopy = db.query(models.Urlop).filter(
        models.Urlop.status == "zaakceptowany",
        models.Urlop.start <= end, models.Urlop.koniec >= start,
    ).all()
    for u in urlopy:
        d = max(u.start, start)
        while d <= min(u.koniec, end):
            urlop_dni.add((u.pracownik_id, d))
            d += timedelta(days=1)

    # Mapowanie danych dla szybszego dostępu
    dys_map = {(d.pracownik_id, d.data): d for d in dyspozycje}
    kwal_map = {p.id: {s.id for s in p.kwalifikacje} for p in pracownicy}
    
    # Liczniki dla sprawiedliwego podziału zmian
    shift_count = defaultdict(int)
    station_count = defaultdict(int)
    assigned_slots_count = defaultdict(int)
    busy_workers_per_day = set()
    zmiany_prac = defaultdict(list)   # pracownik_id -> [(data, godz_od)] (do kontroli prawa pracy)

    # Ładowanie już istniejących przydziałów (np. wpisanych ręcznie)
    existing = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= start, models.PrzydzialZmiany.data <= end
    ).all()

    for a in existing:
        shift_count[a.pracownik_id] += 1
        station_count[(a.pracownik_id, a.stanowisko_id)] += 1
        busy_workers_per_day.add((a.data, a.pracownik_id))
        key = (a.data, a.stanowisko_id, a.godz_od, getattr(a, 'rewir', None))
        assigned_slots_count[key] += 1
        zmiany_prac[a.pracownik_id].append((a.data, a.godz_od))

    # Funkcja sprawdzająca czy pracownik może podjąć zmianę o konkretnej godzinie
    def is_time_compatible(p_id, check_date, req_od: time) -> bool:
        if (p_id, check_date) in urlop_dni:
            return False  # zaakceptowany urlop — auto-przydział pomija ten dzień
        dys = dys_map.get((p_id, check_date))
        if dys is None or not dys.dostepnosc:
            return False
        if dys.godz_od is None:
            return True # Dostępny cały dzień
        # Jeśli pracownik ma wpisaną godzinę rozpoczęcia, sprawdzamy czy nie jest za późno
        if dys.godz_od and req_od and dys.godz_od > req_od:
            return False
        return True

    niedobory = []
    nowe_przydzialy = []
    current = start
    
    # Pętla po dniach
    while current <= end:
        is_weekend = current.weekday() >= 5
        dzisiejsze_wymagania = [w for w in wymagania if w.data == current]
        
        # Tworzenie "koszyka" ze wszystkimi potrzebnymi slotami na dziś
        slots = []
        for w in dzisiejsze_wymagania:
            stan = stanowiska.get(w.stanowisko_id)
            if stan is None or (stan.tylko_weekend and not is_weekend): continue

            # Ile osób jeszcze brakuje na dane stanowisko/godzinę/rewir. KONSUMUJEMY licznik
            # istniejących przydziałów, by przy kilku wierszach WymaganiaDnia o TYM SAMYM kluczu
            # nie odejmować tych samych „existing" wielokrotnie (inaczej łączna obsada zaniżona).
            key = (current, w.stanowisko_id, w.godz_od, w.rewir)
            uzyte = min(w.liczba_osob, assigned_slots_count[key])
            assigned_slots_count[key] -= uzyte
            wolne_miejsca = w.liczba_osob - uzyte
            slots.extend([w] * wolne_miejsca)

        # Sortowanie slotów: najpierw te, które najtrudniej obsadzić (mało kandydatów)
        def evaluate_slot_difficulty(req) -> int:
            cnt = sum(1 for p in pracownicy if req.stanowisko_id in kwal_map.get(p.id, set()) 
                      and (current, p.id) not in busy_workers_per_day 
                      and is_time_compatible(p.id, current, req.godz_od))
            return cnt

        # Najpierw najtrudniej obsadzić (najmniej kandydatów), a PARKIET (Sala*) jako tie-break przy
        # równej trudności. Twardy priorytet sali PRZED trudnością potrafił zabrać jedynego kandydata
        # trudniejszego slotu poza salą i wygenerować niepotrzebny niedobór mimo pełnego rozwiązania.
        slots.sort(key=lambda s: (evaluate_slot_difficulty(s), 0 if s.stanowisko_id in sala_ids else 1))

        # Przydzielanie kandydatów
        for req in slots:
            stan = stanowiska[req.stanowisko_id]
            candidates = [p for p in pracownicy if req.stanowisko_id in kwal_map.get(p.id, set()) 
                          and (current, p.id) not in busy_workers_per_day 
                          and is_time_compatible(p.id, current, req.godz_od)]

            if not candidates:
                rewir_str = f"({req.rewir})" if req.rewir else ""
                godz_str = f"[{req.godz_od.strftime('%H:%M')}]" if req.godz_od else ""
                nazwa_wyswietlana = f"{stan.nazwa} {rewir_str} {godz_str}".strip().replace("  ", " ")
                niedobory.append({"data": str(current), "stanowisko": nazwa_wyswietlana, "powod": "Brak dostępnych pracowników"})
                continue

            # Wybór: osoba z najmniejszą liczbą zmian (zbalansowanie), ale POMIJAMY kandydatów, dla
            # których nowa zmiana złamałaby limity prawa pracy (odpoczynek/dni) — tak jak ręczny przydział.
            candidates.sort(key=lambda p: (shift_count[p.id], station_count[(p.id, req.stanowisko_id)]))
            wybrany = next(
                (c for c in candidates
                 if not prawo_pracy.sprawdz(zmiany_prac[c.id], current, req.godz_od, **_limity)),
                None,
            )
            if wybrany is None:
                rewir_str = f"({req.rewir})" if req.rewir else ""
                godz_str = f"[{req.godz_od.strftime('%H:%M')}]" if req.godz_od else ""
                nazwa_wyswietlana = f"{stan.nazwa} {rewir_str} {godz_str}".strip().replace("  ", " ")
                niedobory.append({"data": str(current), "stanowisko": nazwa_wyswietlana,
                                  "powod": "Limity prawa pracy (odpoczynek / dni pracy)"})
                continue

            nowy_przydzial = models.PrzydzialZmiany(
                data=current, stanowisko_id=req.stanowisko_id,
                pracownik_id=wybrany.id, godz_od=req.godz_od, rewir=req.rewir
            )
            nowe_przydzialy.append(nowy_przydzial)
            busy_workers_per_day.add((current, wybrany.id))
            shift_count[wybrany.id] += 1
            station_count[(wybrany.id, req.stanowisko_id)] += 1
            zmiany_prac[wybrany.id].append((current, req.godz_od))

        current += timedelta(days=1)

    # Zapis do bazy
    for p in nowe_przydzialy:
        db.add(p)
    db.commit()
    return {"przydzielone": len(nowe_przydzialy), "niedobory": niedobory}
# ... (twoja dotychczasowa funkcja auto_assign powyżej) ...

from datetime import datetime, timedelta

# Domyślne parametry obsady imprez (historycznie zaszyte pod jeden lokal; teraz konfigurowalne
# per lokal w LokalConfig). Domyślne wartości ZACHOWUJĄ dotychczasowe zachowanie.
IMPREZA_PARAMS_DOMYSLNE = {
    "osoby_na_obsluge": 15,          # 1 pracownik obsługi na tylu gości
    "wyprzedzenie_min": 120,         # obsługa zaczyna tyle minut przed startem imprezy
    "najwczesniej": "10:00",         # ale nie wcześniej niż ta godzina
    "sale_min2": ("R2Piw", "R2G"),   # sale wymagające minimum 2 osób obsady
}


def przelicz_imprezy_na_wymagania(imprezy: List[models.Impreza], params: dict = None) -> List[dict]:
    """Przelicza imprezy na wymagania obsady dnia (stanowisko imprez). Parametry obsady
    (goście na pracownika, wyprzedzenie startu, najwcześniejsza godzina, sale z minimum 2)
    są konfigurowalne per lokal przez LokalConfig — `params` None = wartości domyślne."""
    p = {**IMPREZA_PARAMS_DOMYSLNE, **(params or {})}
    osoby_na_obsluge = max(1, int(p["osoby_na_obsluge"]))
    wyprzedzenie = timedelta(minutes=int(p["wyprzedzenie_min"]))
    try:
        najwczesniej = datetime.strptime(str(p["najwczesniej"]), "%H:%M")
    except (ValueError, TypeError):
        najwczesniej = datetime.strptime("10:00", "%H:%M")
    sale_min2 = set(p["sale_min2"])

    wymagania_automatyczne = []
    for imp in imprezy:
        # 1. Godzina startu obsługi: start imprezy - wyprzedzenie, nie wcześniej niż `najwczesniej`.
        godzina_pracy = najwczesniej.time()
        try:
            godz_str = str(imp.godzina).strip().replace(".", ":")
            fmt = "%H:%M:%S" if len(godz_str) > 5 else "%H:%M"
            start_imp = datetime.strptime(godz_str, fmt)
            godzina_pracy = max(start_imp - wyprzedzenie, najwczesniej).time()
        except Exception:
            pass

        # 2. Liczba obsady: 1 na `osoby_na_obsluge` (w górę), minimum zależne od sali.
        osoby = imp.liczba_osob or 0
        sala = imp.sala or ""
        min_osob = 2 if sala in sale_min2 else 1
        potrzebni = max(min_osob, (osoby // osoby_na_obsluge) + (1 if osoby % osoby_na_obsluge > 0 else 0))

        wymagania_automatyczne.append({
            "data": imp.data,
            "godz_od": godzina_pracy,
            "liczba_osob": potrzebni,
            "rewir": f"IMPREZA: {imp.klient} ({sala})",
            "jest_impreza": True,
        })

    return wymagania_automatyczne