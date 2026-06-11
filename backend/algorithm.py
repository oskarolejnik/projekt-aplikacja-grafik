from datetime import date, time, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from typing import List
import models

def auto_assign(db: Session, start: date, end: date) -> dict:
    """
    Algorytm automatycznego przydzielania pracowników do zmian.
    Uwzględnia kwalifikacje, dyspozycyjność oraz zbalansowanie liczby zmian.
    """
    pracownicy = db.query(models.Pracownik).filter(models.Pracownik.aktywny == True).all()
    stanowiska = {s.id: s for s in db.query(models.Stanowisko).all()}
    # Parkiet (stanowiska „Sala*") ma PRIORYTET przy obsadzaniu — jego sloty idą przed resztą.
    sala_ids = {sid for sid, st in stanowiska.items() if (st.nazwa or "").strip().lower().startswith("sala")}
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
            
            # Obliczamy ile osób jeszcze brakuje na dane stanowisko i godzinę
            wolne_miejsca = max(0, w.liczba_osob - assigned_slots_count[(current, w.stanowisko_id, w.godz_od, w.rewir)])
            slots.extend([w] * wolne_miejsca)

        # Sortowanie slotów: najpierw te, które najtrudniej obsadzić (mało kandydatów)
        def evaluate_slot_difficulty(req) -> int:
            cnt = sum(1 for p in pracownicy if req.stanowisko_id in kwal_map.get(p.id, set()) 
                      and (current, p.id) not in busy_workers_per_day 
                      and is_time_compatible(p.id, current, req.godz_od))
            return cnt

        # Najpierw PARKIET (Sala*), potem reszta; w obrębie grupy — najtrudniej obsadzić najpierw.
        slots.sort(key=lambda s: (0 if s.stanowisko_id in sala_ids else 1, evaluate_slot_difficulty(s)))

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

            # Wybór: osoba z najmniejszą liczbą zmian (zbalansowanie)
            candidates.sort(key=lambda p: (shift_count[p.id], station_count[(p.id, req.stanowisko_id)]))
            wybrany = candidates[0]

            nowy_przydzial = models.PrzydzialZmiany(
                data=current, stanowisko_id=req.stanowisko_id,
                pracownik_id=wybrany.id, godz_od=req.godz_od, rewir=req.rewir
            )
            nowe_przydzialy.append(nowy_przydzial)
            busy_workers_per_day.add((current, wybrany.id))
            shift_count[wybrany.id] += 1
            station_count[(wybrany.id, req.stanowisko_id)] += 1

        current += timedelta(days=1)

    # Zapis do bazy
    for p in nowe_przydzialy:
        db.add(p)
    db.commit()
    return {"przydzielone": len(nowe_przydzialy), "niedobory": niedobory}
# ... (twoja dotychczasowa funkcja auto_assign powyżej) ...

from datetime import datetime, timedelta

def przelicz_imprezy_na_wymagania(imprezy: List[models.Impreza]) -> List[dict]:
    wymagania_automatyczne = []
    
    for imp in imprezy:
        # --- USTALENIE WARTOŚCI DOMYŚLNYCH ---
        godzina_pracy = time(10, 0)
        
        # 1. Logika godziny
        # 1. Logika godziny
        try:
            godz_str = str(imp.godzina).strip().replace('.', ':')
            
            # Próba parsowania z sekundami (%H:%M:%S) lub bez (%H:%M)
            if len(godz_str) > 5:
                start_imp = datetime.strptime(godz_str, "%H:%M:%S")
            else:
                start_imp = datetime.strptime(godz_str, "%H:%M")
                
            start_pracy = start_imp - timedelta(hours=2)
            
            # Limit 10:00 rano
            limit_godzina = datetime.strptime("10:00", "%H:%M")
            start_pracy = max(start_pracy, limit_godzina)
            
            godzina_pracy = start_pracy.time()
        except Exception as e:
            print(f"DEBUG: Błąd godziny dla {imp.klient}: {e}")
        # 2. Logika liczby osób
        osoby = imp.liczba_osob or 0
        sala = imp.sala or ""
        min_osob = 2 if sala in ['R2Piw', 'R2G'] else 1
        # Wyliczenie potrzebnych pracowników
        potrzebni = max(min_osob, (osoby // 15) + (1 if osoby % 15 > 0 else 0))
        
        # 3. Dodanie do listy
        wymagania_automatyczne.append({
            "data": imp.data,
            "godz_od": godzina_pracy,
            "liczba_osob": potrzebni,
            "rewir": f"IMPREZA: {imp.klient} ({sala})",
            "jest_impreza": True
        })
        
    return wymagania_automatyczne
    """
    Przelicza listę imprez na listę słowników wymagań, 
    które zostaną zapisane w tabeli 'wymagania_dnia'.
    """
    wymagania_automatyczne = []
    
    for imp in imprezy:
        # 1. Logika godziny: -2h, najwcześniej 10:00
        try:
            # Zakładamy format godziny w bazie: "HH:MM"
            start_imp = datetime.strptime(imp.godzina, "%H:%M")
            start_pracy = start_imp - timedelta(hours=2)
            
            # Limit 10:00 rano
            limit_godzina = datetime.strptime("10:00", "%H:%M")
            start_pracy = max(start_pracy, limit_godzina)
            
            godzina_pracy = start_pracy.time()
        except (ValueError, TypeError):
            # W razie błędu parsowania, ustawiamy bezpieczne 10:00
            godzina_pracy = time(10, 0)

        # 2. Logika zapotrzebowania:
        # 1 pracownik na 15 osób, ale dla R2Piw/R2G minimum 2 osoby
        osoby = imp.liczba_osob or 0
        sala = imp.sala or ""
        
        # Sztywne minimum dla konkretnych sal
        min_osob = 2 if sala in ['R2Piw', 'R2G'] else 1
        
        # Wyliczenie: (osoby / 15) zaokrąglone w górę
        potrzebni = max(min_osob, (osoby // 15) + (1 if osoby % 15 > 0 else 0))
        
        # Przygotowanie słownika wymagań
        wymagania_automatyczne.append({
            "data": imp.data,
            "godz_od": godzina_pracy,
            "liczba_osob": potrzebni,
            "rewir": f"IMPREZA: {imp.klient} ({sala})",
            "jest_impreza": True
        })
        
    return wymagania_automatyczne