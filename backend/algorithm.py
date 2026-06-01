"""
Udoskonalony algorytm automatycznego przydziału zmian.
Uwzględnia kwalifikacje, dostępność godzinową z CSV (Google Forms)
oraz podział na rewiry robocze (np. tygodniowe / weekendowe).
"""

from datetime import date, timedelta, time
from collections import defaultdict
from sqlalchemy.orm import Session
import models


def auto_assign(db: Session, start: date, end: date) -> dict:
    # ── 1. Pobranie danych z bazy ───────────────────────────────────────
    pracownicy = db.query(models.Pracownik).filter(models.Pracownik.aktywny == True).all()
    stanowiska = {s.id: s for s in db.query(models.Stanowisko).all()}
    wymagania  = db.query(models.WymaganiaDnia).filter(
        models.WymaganiaDnia.data >= start,
        models.WymaganiaDnia.data <= end,
    ).all()
    dyspozycje = db.query(models.Dyspozycja).filter(
        models.Dyspozycja.data >= start,
        models.Dyspozycja.data <= end,
    ).all()

    # ── 2. Słowniki pomocnicze i mapy ───────────────────────────────────
    dys_map: dict = {}
    for d in dyspozycje:
        dys_map[(d.pracownik_id, d.data)] = d

    kwal_map: dict[int, set] = {}
    for p in pracownicy:
        kwal_map[p.id] = {s.id for s in p.kwalifikacje}

    shift_count: dict[int, int] = defaultdict(int)
    station_count: dict[tuple, int] = defaultdict(int)

    # Wczytanie istniejących grafików (wpisanych ręcznie przed uruchomieniem auto)
    existing = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= start,
        models.PrzydzialZmiany.data <= end,
    ).all()
    
    assigned_slots_count = defaultdict(int) # (data, stanowisko_id, godz_od, rewir) -> int
    busy_workers_per_day = set() # (data, pracownik_id)

    for a in existing:
        shift_count[a.pracownik_id] += 1
        station_count[(a.pracownik_id, a.stanowisko_id)] += 1
        busy_workers_per_day.add((a.data, a.pracownik_id))
        # Grupowanie obsadzonych miejsc, uwzględniając unikalne parametry zmian
        key = (a.data, a.stanowisko_id, a.godz_od, getattr(a, 'rewir', None))
        assigned_slots_count[key] += 1

    # Funkcja weryfikująca, czy godziny dyspozycji pracownika pasują do wymagań zmiany
    def is_time_compatible(p_id, check_date, req_od: time, req_do: time) -> bool:
        dys = dys_map.get((p_id, check_date))
        if dys is None or not dys.dostepnosc:
            return False
        
        # Jeśli pracownik zaznaczył czyste "TAK" (brak sprecyzowanych godzin), pasuje do każdej zmiany
        if dys.godz_od is None and dys.godz_do is None:
            return True
            
        # Sprawdzamy godzinę wejścia: dyspozycja pracownika musi być wcześniejsza lub równa wymaganiu zmiany
        if dys.godz_od and req_od and dys.godz_od > req_od:
            return False
            
        # Sprawdzamy godzinę wyjścia: dyspozycja pracownika musi pozwalać na pracę do końca zmiany
        if dys.godz_do and req_do and dys.godz_do < req_do:
            return False
            
        return True

    niedobory: list[dict] = []
    nowe_przydzialy: list[models.PrzydzialZmiany] = []

    # ── 3. Główna pętla harmonogramowania dzień po dniu ─────────────────
    current = start
    while current <= end:
        is_weekend = current.weekday() >= 5

        # Odfiltrowujemy wymagania na bieżący dzień
        dzisiejsze_wymagania = [w for w in wymagania if w.data == current]

        # Budujemy precyzyjne sloty robocze na dzisiaj
        slots = []
        for w in dzisiejsze_wymagania:
            stan = stanowiska.get(w.stanowisko_id)
            if stan is None or (stan.tylko_weekend and not is_weekend):
                continue
                
            # Sprawdzamy, ile z tych konkretnych zmian (godzina + rewir) obsadzono ręcznie
            already_filled = assigned_slots_count[(current, w.stanowisko_id, w.godz_od, w.rewir)]
            wolne_miejsca = max(0, w.liczba_osob - already_filled)
            
            for _ in range(wolne_miejsca):
                slots.append(w)

        # Funkcja pomocnicza: ocenia trudność obsadzenia danej zmiany (sortowanie heurystyczne)
        def evaluate_slot_difficulty(req) -> int:
            cnt = 0
            for p in pracownicy:
                if req.stanowisko_id not in kwal_map.get(p.id, set()):
                    continue
                if (current, p.id) in busy_workers_per_day:
                    continue
                if not is_time_compatible(p.id, current, req.godz_od, req.godz_do):
                    continue
                cnt += 1
            return cnt

        # Sortujemy sloty: najtrudniejsze zmiany (z najmniejszą liczbą pasujących osób) idą na początek
        slots.sort(key=lambda s: evaluate_slot_difficulty(s))

        # Rozdzielanie slotów pracownikom
        for req in slots:
            stan = stanowiska[req.stanowisko_id]
            candidates = []
            
            for p in pracownicy:
                # Sprawdzenie 1: Kwalifikacja stanowiskowa
                if req.stanowisko_id not in kwal_map.get(p.id, set()):
                    continue
                # Sprawdzenie 2: Czy ma już przypisaną pracę w tym dniu
                if (current, p.id) in busy_workers_per_day:
                    continue
                # Sprawdzenie 3: Kompatybilność godzinowa z Formularza Google
                if not is_time_compatible(p.id, current, req.godz_od, req.godz_do):
                    continue
                    
                candidates.append(p)

            if not candidates:
                # Obsługa niedoborów — generowanie jasnych powodów dla menedżera
                powody = []
                for p in pracownicy:
                    if req.stanowisko_id not in kwal_map.get(p.id, set()):
                        continue
                    dys = dys_map.get((p.id, current))
                    if dys is None or not dys.dostepnosc:
                        powody.append(f"{p.imie}: brak dysp.")
                    elif (current, p.id) in busy_workers_per_day:
                        powody.append(f"{p.imie}: zajęty/a")
                    else:
                        godz_str = f"od {dys.godz_od.strftime('%H:%M')}" if dys.godz_od else "b/d"
                        powody.append(f"{p.imie}: dysp. {godz_str}")
                
                nazwa_wyswietlana = stan.nazwa
                if req.rewir:
                    nazwa_wyswietlana += f" ({req.rewir})"
                if req.godz_od:
                    nazwa_wyswietlana += f" [{req.godz_od.strftime('%H:%M')}]"

                powod_finalny = "Brak dostępnych osób" if not powody else "; ".join(powody[:2])
                niedobory.append({
                    "data": str(current),
                    "stanowisko": nazwa_wyswietlana,
                    "powod": powod_finalny,
                })
                continue

            # Sortowanie kandydatów: sprawiedliwy podział (kto pracował najmniej, ten na zmianę)
            candidates.sort(key=lambda p: (shift_count[p.id], station_count[(p.id, req.stanowisko_id)]))
            wybrany = candidates[0]

            # Budowanie obiektu przydziału z godzinami i rewirem z wymagań
            nowy_przydzial = models.PrzydzialZmiany(
                data=current,
                stanowisko_id=req.stanowisko_id,
                pracownik_id=wybrany.id,
                godz_od=req.godz_od,
                godz_do=req.godz_do
                # Jeśli w przyszłości dodasz kolumnę 'rewir' do PrzydzialZmiany, można ją tu przypisać
            )
            
            nowe_przydzialy.append(nowy_przydzial)
            busy_workers_per_day.add((current, wybrany.id))
            shift_count[wybrany.id] += 1
            station_count[(wybrany.id, req.stanowisko_id)] += 1

        current += timedelta(days=1)

    # Zapisanie ułożonego harmonogramu
    for p in nowe_przydzialy:
        db.add(p)
    db.commit()

    return {
        "przydzielone": len(nowe_przydzialy),
        "niedobory": niedobory,
    }
