from datetime import date, timedelta, time
from collections import defaultdict
from sqlalchemy.orm import Session
import models

def auto_assign(db: Session, start: date, end: date) -> dict:
    pracownicy = db.query(models.Pracownik).filter(models.Pracownik.aktywny == True).all()
    stanowiska = {s.id: s for s in db.query(models.Stanowisko).all()}
    wymagania  = db.query(models.WymaganiaDnia).filter(
        models.WymaganiaDnia.data >= start, models.WymaganiaDnia.data <= end
    ).all()
    dyspozycje = db.query(models.Dyspozycja).filter(
        models.Dyspozycja.data >= start, models.Dyspozycja.data <= end
    ).all()

    dys_map = {(d.pracownik_id, d.data): d for d in dyspozycje}
    kwal_map = {p.id: {s.id for s in p.kwalifikacje} for p in pracownicy}
    shift_count = defaultdict(int)
    station_count = defaultdict(int)
    assigned_slots_count = defaultdict(int) 
    busy_workers_per_day = set()

    existing = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= start, models.PrzydzialZmiany.data <= end
    ).all()
    
    for a in existing:
        shift_count[a.pracownik_id] += 1
        station_count[(a.pracownik_id, a.stanowisko_id)] += 1
        busy_workers_per_day.add((a.data, a.pracownik_id))
        key = (a.data, a.stanowisko_id, a.godz_od, getattr(a, 'rewir', None))
        assigned_slots_count[key] += 1

    # Uproszczona funkcja - interesuje nas tylko, by pracownik był na daną godzinę
    def is_time_compatible(p_id, check_date, req_od: time) -> bool:
        dys = dys_map.get((p_id, check_date))
        if dys is None or not dys.dostepnosc:
            return False
        if dys.godz_od is None:
            return True
        if dys.godz_od and req_od and dys.godz_od > req_od:
            return False
        return True

    niedobory = []
    nowe_przydzialy = []
    current = start
    
    while current <= end:
        is_weekend = current.weekday() >= 5
        dzisiejsze_wymagania = [w for w in wymagania if w.data == current]
        slots = []
        for w in dzisiejsze_wymagania:
            stan = stanowiska.get(w.stanowisko_id)
            if stan is None or (stan.tylko_weekend and not is_weekend): continue
            wolne_miejsca = max(0, w.liczba_osob - assigned_slots_count[(current, w.stanowisko_id, w.godz_od, w.rewir)])
            slots.extend([w] * wolne_miejsca)

        def evaluate_slot_difficulty(req) -> int:
            cnt = sum(1 for p in pracownicy if req.stanowisko_id in kwal_map.get(p.id, set()) 
                      and (current, p.id) not in busy_workers_per_day 
                      and is_time_compatible(p.id, current, req.godz_od))
            return cnt

        slots.sort(key=lambda s: evaluate_slot_difficulty(s))

        for req in slots:
            stan = stanowiska[req.stanowisko_id]
            candidates = [p for p in pracownicy if req.stanowisko_id in kwal_map.get(p.id, set()) 
                          and (current, p.id) not in busy_workers_per_day 
                          and is_time_compatible(p.id, current, req.godz_od)]

            if not candidates:
                powody = [f"{p.imie}: zajęty/niedost." for p in pracownicy if req.stanowisko_id in kwal_map.get(p.id, set())]
                
                # Rozbiliśmy to na osobne zmienne, żeby uniknąć zagnieżdżania cudzysłowów
                rewir_str = f"({req.rewir})" if req.rewir else ""
                godz_str = f"[{req.godz_od.strftime('%H:%M')}]" if req.godz_od else ""
                nazwa_wyswietlana = f"{stan.nazwa} {rewir_str} {godz_str}".strip().replace("  ", " ")
                
                niedobory.append({"data": str(current), "stanowisko": nazwa_wyswietlana, "powod": "; ".join(powody[:2]) or "Brak"})
                continue

            candidates.sort(key=lambda p: (shift_count[p.id], station_count[(p.id, req.stanowisko_id)]))
            wybrany = candidates[0]

            nowy_przydzial = models.PrzydzialZmiany(
                data=current, stanowisko_id=req.stanowisko_id,
                pracownik_id=wybrany.id, godz_od=req.godz_od
            )
            nowe_przydzialy.append(nowy_przydzial)
            busy_workers_per_day.add((current, wybrany.id))
            shift_count[wybrany.id] += 1
            station_count[(wybrany.id, req.stanowisko_id)] += 1

        current += timedelta(days=1)

    for p in nowe_przydzialy:
        db.add(p)
    db.commit()
    return {"przydzielone": len(nowe_przydzialy), "niedobory": niedobory}