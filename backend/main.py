import csv
import io
import re
import os
from datetime import date, time, timedelta
from typing import Optional, List  # POPRAWKA TYPOWANIA DLA PYTHON 3.9
from collections import defaultdict

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import models, schemas
from database import get_db, init_db
from algorithm import auto_assign as _auto_assign

app = FastAPI(title="Scheduler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()


# ═══════════════════════════════════════════════════════════════════════════
# POMOCNICZE
# ═══════════════════════════════════════════════════════════════════════════

def parse_date(s: str) -> date:
    """Obsługuje YYYY-MM-DD and DD.MM.YYYY."""
    s = s.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return date.fromisoformat(s)
    if re.match(r"\d{2}\.\d{2}\.\d{4}", s):
        d, m, y = s.split(".")
        return date(int(y), int(m), int(d))
    raise ValueError(f"Nieznany format daty: {s}")

def parse_time(s: str) -> Optional[time]:
    if not s or not s.strip():
        return None
    parts = s.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


# ═══════════════════════════════════════════════════════════════════════════
# STANOWISKA
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/stanowiska", response_model=List[schemas.StanowiskoOut])
def get_stanowiska(db: Session = Depends(get_db)):
    return db.query(models.Stanowisko).all()

@app.post("/api/stanowiska", response_model=schemas.StanowiskoOut, status_code=201)
def create_stanowisko(data: schemas.StanowiskoCreate, db: Session = Depends(get_db)):
    if db.query(models.Stanowisko).filter_by(nazwa=data.nazwa).first():
        raise HTTPException(400, "Stanowisko o tej nazwie już istnieje.")
    s = models.Stanowisko(**data.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return s

@app.put("/api/stanowiska/{sid}", response_model=schemas.StanowiskoOut)
def update_stanowisko(sid: int, data: schemas.StanowiskoCreate, db: Session = Depends(get_db)):
    s = db.get(models.Stanowisko, sid)
    if not s:
        raise HTTPException(404, "Nie znaleziono.")
    s.nazwa = data.nazwa
    s.tylko_weekend = data.tylko_weekend
    db.commit(); db.refresh(s)
    return s

@app.delete("/api/stanowiska/{sid}", status_code=204)
def delete_stanowisko(sid: int, db: Session = Depends(get_db)):
    s = db.get(models.Stanowisko, sid)
    if not s:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(s); db.commit()

@app.post("/api/stanowiska/{sid}/podkategorie", response_model=schemas.PodkategoriaOut)
def create_podkategoria(sid: int, data: schemas.PodkategoriaCreate, db: Session = Depends(get_db)):
    p = models.Podkategoria(**data.model_dump(), stanowisko_id=sid)
    db.add(p); db.commit(); db.refresh(p)
    return p

@app.delete("/api/podkategorie/{pid}", status_code=204)
def delete_podkategoria(pid: int, db: Session = Depends(get_db)):
    p = db.get(models.Podkategoria, pid)
    if p:
        db.delete(p); db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# PRACOWNICY
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/pracownicy", response_model=List[schemas.PracownikOut])
def get_pracownicy(db: Session = Depends(get_db)):
    return db.query(models.Pracownik).all()

@app.post("/api/pracownicy", response_model=schemas.PracownikOut, status_code=201)
def create_pracownik(data: schemas.PracownikCreate, db: Session = Depends(get_db)):
    p = models.Pracownik(imie=data.imie, nazwisko=data.nazwisko, aktywny=data.aktywny)
    if data.kwalifikacje_ids:
        p.kwalifikacje = db.query(models.Stanowisko).filter(
            models.Stanowisko.id.in_(data.kwalifikacje_ids)
        ).all()
    db.add(p); db.commit(); db.refresh(p)
    return p

@app.put("/api/pracownicy/{pid}", response_model=schemas.PracownikOut)
def update_pracownik(pid: int, data: schemas.PracownikCreate, db: Session = Depends(get_db)):
    p = db.get(models.Pracownik, pid)
    if not p:
        raise HTTPException(404, "Nie znaleziono.")
    p.imie = data.imie
    p.nazwisko = data.nazwisko
    p.aktywny = data.aktywny
    p.kwalifikacje = db.query(models.Stanowisko).filter(
        models.Stanowisko.id.in_(data.kwalifikacje_ids)
    ).all()
    db.commit(); db.refresh(p)
    return p

@app.delete("/api/pracownicy/{pid}", status_code=204)
def delete_pracownik(pid: int, db: Session = Depends(get_db)):
    p = db.get(models.Pracownik, pid)
    if not p:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(p); db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# WYMAGANIA DNIA
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/wymagania", response_model=List[schemas.WymaganiaOut])
def get_wymagania(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    q = db.query(models.WymaganiaDnia)
    if start: q = q.filter(models.WymaganiaDnia.data >= start)
    if end:   q = q.filter(models.WymaganiaDnia.data <= end)
    return q.all()

@app.post("/api/wymagania", response_model=schemas.WymaganiaOut, status_code=201)
def create_wymagania(data: schemas.WymaganiaCreate, db: Session = Depends(get_db)):
    existing = db.query(models.WymaganiaDnia).filter_by(
        data=data.data,
        stanowisko_id=data.stanowisko_id,
        godz_od=data.godz_od,
        rewir=data.rewir
    ).first()
    
    if existing:
        existing.liczba_osob = data.liczba_osob
        existing.godz_do = data.godz_do
        db.commit(); db.refresh(existing)
        return existing
        
    w = models.WymaganiaDnia(**data.model_dump())
    db.add(w); db.commit(); db.refresh(w)
    return w

@app.delete("/api/wymagania/{wid}", status_code=204)
def delete_wymagania(wid: int, db: Session = Depends(get_db)):
    w = db.get(models.WymaganiaDnia, wid)
    if not w:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(w); db.commit()

@app.post("/api/wymagania/kopiuj", status_code=200)
def kopiuj_wymagania(body: dict, db: Session = Depends(get_db)):
    source = date.fromisoformat(body["source_date"])
    start  = date.fromisoformat(body["start_date"])
    end    = date.fromisoformat(body["end_date"])

    source_reqs = db.query(models.WymaganiaDnia).filter_by(data=source).all()
    if not source_reqs:
        raise HTTPException(404, "Brak wymagań dla dnia źródłowego.")

    count = 0
    current = start
    while current <= end:
        if current == source:
            current += timedelta(days=1)
            continue
        for req in source_reqs:
            existing = db.query(models.WymaganiaDnia).filter_by(
                data=current,
                stanowisko_id=req.stanowisko_id,
                godz_od=req.godz_od,
                rewir=req.rewir
            ).first()
            
            if existing:
                existing.liczba_osob = req.liczba_osob
                existing.godz_do = req.godz_do
            else:
                db.add(models.WymaganiaDnia(
                    data=current,
                    stanowisko_id=req.stanowisko_id,
                    godz_od=req.godz_od,
                    godz_do=req.godz_do,
                    rewir=req.rewir,
                    liczba_osob=req.liczba_osob,
                ))
            count += 1
        current += timedelta(days=1)
    db.commit()
    return {"skopiowano": count}


# ═══════════════════════════════════════════════════════════════════════════
# DYSPOZYCJE (ZAKŁADKA IMPORtowania
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/dyspozycje", response_model=List[schemas.DyspozycjaOut])
def get_dyspozycje(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    q = db.query(models.Dyspozycja)
    if start: q = q.filter(models.Dyspozycja.data >= start)
    if end:   q = q.filter(models.Dyspozycja.data <= end)
    return q.all()

@app.post("/api/dyspozycje", response_model=schemas.DyspozycjaOut, status_code=201)
def create_dyspozycja(data: schemas.DyspozycjaCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Dyspozycja).filter_by(
        pracownik_id=data.pracownik_id, data=data.data
    ).first()
    if existing:
        for k, v in data.model_dump().items():
            setattr(existing, k, v)
        db.commit(); db.refresh(existing)
        return existing
    d = models.Dyspozycja(**data.model_dump())
    db.add(d); db.commit(); db.refresh(d)
    return d

@app.post("/api/dyspozycje/import-csv")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    text = content.decode("utf-8-sig")
    
    first_line = text.split("\n")[0] if text else ""
    delimiter = ";" if ";" in first_line else ","
    
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fieldnames = reader.fieldnames or []
    fieldnames_lower = [f.lower().strip() for f in fieldnames]
    rows = list(reader)

    if not rows:
        return {"zapisano": 0, "podglad": [], "konflikty": []}

    wszyscy = db.query(models.Pracownik).all()

    def find_pracownik(raw_name: str):
        name_clean = raw_name.lower().strip()
        if not name_clean:
            return None
        for p in wszyscy:
            if f"{p.imie} {p.nazwisko}".lower().strip() == name_clean:
                return p
        matches = [p for p in wszyscy if p.imie.lower().strip() == name_clean]
        if len(matches) == 1:
            return matches[0]
        matches_partial = []
        for p in wszyscy:
            full = f"{p.imie} {p.nazwisko}".lower().strip()
            if full in name_clean or name_clean in full:
                matches_partial.append(p)
        if len(matches_partial) >= 1:
            return matches_partial[0]
        return None

    def parse_availability_text(val_str: str):
        t_lower = val_str.lower().strip()
        if t_lower == "nie" or not t_lower:
            return False, None, None
        
        dostepnosc = True
        godz_od = None
        godz_do = None
        
        od_match = re.search(r'\bod\s*(\d{1,2})(?::(\d{2}))?', t_lower)
        if od_match:
            h = int(od_match.group(1))
            m = int(od_match.group(2)) if od_match.group(2) else 0
            godz_od = time(h, m)
            
        do_match = re.search(r'\bdo\s*(\d{1,2})(?::(\d{2}))?', t_lower)
        if do_match:
            h = int(do_match.group(1))
            m = int(do_match.group(2)) if do_match.group(2) else 0
            godz_do = time(h, m)
            
        na_match = re.search(r'\bna\s*(\d{1,2})\b', t_lower)
        if na_match and not godz_od and "18stk" not in t_lower:
            h = int(na_match.group(1))
            godz_od = time(h, 0)
            
        if "od 12/13" in t_lower:
            godz_od = time(12, 0)
            
        return dostepnosc, godz_od, godz_do

    podglad = []
    konflikty = []
    zapisano = 0

    is_wide_format = "imię i nazwisko" in fieldnames_lower or any("-" in f for f in fieldnames)

    if is_wide_format:
        name_col = next((f for f in fieldnames if f.lower().strip() == "imię i nazwisko"), fieldnames[1])
        
        year = 2026
        ts_col = next((f for f in fieldnames if "sygnatura" in f.lower() or "timestamp" in f.lower()), None)
        if ts_col and rows[0].get(ts_col):
            match_year = re.match(r"(\d{4})", rows[0].get(ts_col).strip())
            if match_year:
                year = int(match_year.group(1))

        date_cols = []
        for col in fieldnames:
            date_match = re.search(r"(\d+)\.(\d+)", col)
            if date_match:
                d_day = int(date_match.group(1))
                d_month = int(date_match.group(2))
                parsed_d = date(year, d_month, d_day)
                date_cols.append((col, parsed_d))

        lokalne_przydzialy = {}

        for row in rows:
            raw_name = (row.get(name_col) or "").strip()
            if not raw_name:
                continue
                
            p = find_pracownik(raw_name)
            if not p:
                konflikty.append({"wiersz": raw_name, "problem": "Nie znaleziono pracownika w bazie danych"})
                continue

            for col_name, parsed_date in date_cols:
                val = (row.get(col_name) or "").strip()
                dostepnosc, godz_od, godz_do = parse_availability_text(val)
                klucz = (p.id, parsed_date)

                podglad.append({
                    "pracownik": f"{p.imie} {p.nazwisko}",
                    "data": str(parsed_date),
                    "dostepnosc": dostepnosc,
                    "od": str(godz_od) if godz_od else "",
                    "do": str(godz_do) if godz_do else "",
                })

                if klucz in lokalne_przydzialy:
                    existing = lokalne_przydzialy[klucz]
                    existing.dostepnosc = dostepnosc
                    existing.godz_od = godz_od
                    existing.godz_do = godz_do
                else:
                    existing = db.query(models.Dyspozycja).filter_by(pracownik_id=p.id, data=parsed_date).first()
                    if existing:
                        existing.dostepnosc = dostepnosc
                        existing.godz_od = godz_od
                        existing.godz_do = godz_do
                        lokalne_przydzialy[klucz] = existing
                    else:
                        nowa_dyspozycja = models.Dyspozycja(
                            pracownik_id=p.id,
                            data=parsed_date,
                            dostepnosc=dostepnosc,
                            godz_od=godz_od,
                            godz_do=godz_do,
                        )
                        db.add(nowa_dyspozycja)
                        lokalne_przydzialy[klucz] = nowa_dyspozycja
                        zapisano += 1
    else:
        lokalne_przydzialy = {}
        for row in rows:
            raw_name = (row.get("pracownik") or "").strip()
            raw_date = (row.get("data") or row.get("date") or "").strip()
            raw_dost = (row.get("dostępność") or row.get("dostepnosc") or row.get("available") or "1").strip()
            raw_od   = (row.get("od") or row.get("from") or "").strip()
            raw_do   = (row.get("do") or row.get("to") or "").strip()

            p = find_pracownik(raw_name)
            if not p:
                konflikty.append({"wiersz": raw_name, "problem": "Nie znaleziono pracownika"})
                continue

            try:
                parsed_date = parse_date(raw_date)
            except ValueError as e:
                konflikty.append({"wiersz": raw_name, "problem": str(e)})
                continue

            dostepnosc = raw_dost in ("1", "true", "tak", "yes", "t")
            godz_od = parse_time(raw_od)
            godz_do = parse_time(raw_do)
            klucz = (p.id, parsed_date)

            podglad.append({
                "pracownik": f"{p.imie} {p.nazwisko}",
                "data": str(parsed_date),
                "dostepnosc": dostepnosc,
                "od": str(godz_od) if godz_od else "",
                "do": str(godz_do) if godz_do else "",
            })

            if klucz in lokalne_przydzialy:
                existing = lokalne_przydzialy[klucz]
                existing.dostepnosc = dostepnosc
                existing.godz_od = godz_od
                existing.godz_do = godz_do
            else:
                existing = db.query(models.Dyspozycja).filter_by(pracownik_id=p.id, data=parsed_date).first()
                if existing:
                    existing.dostepnosc = dostepnosc
                    existing.godz_od = godz_od
                    existing.godz_do = godz_do
                    lokalne_przydzialy[klucz] = existing
                else:
                    nowa_dyspozycja = models.Dyspozycja(
                        pracownik_id=p.id,
                        data=parsed_date,
                        dostepnosc=dostepnosc,
                        godz_od=godz_od,
                        godz_do=godz_do,
                    )
                    db.add(nowa_dyspozycja)
                    lokalne_przydzialy[klucz] = nowa_dyspozycja
                    zapisano += 1

    db.commit()
    return {"zapisano": zapisano, "podglad": podglad, "konflikty": konflikty}


# ═══════════════════════════════════════════════════════════════════════════
# PRZYDZIAŁY (ZAKTUALIZOWANE DLA WIELU ZMIAN CZASOWYCH)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/przydzialy", response_model=List[schemas.PrzydzialOut])
def get_przydzialy(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    q = db.query(models.PrzydzialZmiany)
    if start: q = q.filter(models.PrzydzialZmiany.data >= start)
    if end:   q = q.filter(models.PrzydzialZmiany.data <= end)
    return q.all()

@app.post("/api/przydzialy", response_model=schemas.PrzydzialOut, status_code=201)
def create_przydział(data: schemas.PrzydzialCreate, db: Session = Depends(get_db)):
    stan = db.get(models.Stanowisko, data.stanowisko_id)
    if stan and stan.tylko_weekend and data.data.weekday() < 5:
        raise HTTPException(400, f"Stanowisko '{stan.nazwa}' jest aktywne tylko w weekendy.")
    
    # POPRAWKA KRYTYCZNA: Sprawdzamy, czy pracownik nie ma już przypisanej zmiany DOKŁADNIE w tych samych godzinach,
    # zamiast blokować mu cały dzień roboczy na inne, niezależne zmiany.
    overlapping_shift = db.query(models.PrzydzialZmiany).filter_by(
        data=data.data, 
        pracownik_id=data.pracownik_id,
        godz_od=data.godz_od
    ).first()
    
    if overlapping_shift:
        raise HTTPException(400, "Pracownik ma już przydział na tę konkretną godzinę w tym dniu.")

    a = models.PrzydzialZmiany(**data.model_dump())
    db.add(a); db.commit(); db.refresh(a)
    return a

@app.put("/api/przydzialy/{aid}", response_model=schemas.PrzydzialOut)
def update_przydział(aid: int, data: schemas.PrzydzialCreate, db: Session = Depends(get_db)):
    a = db.get(models.PrzydzialZmiany, aid)
    if not a:
        raise HTTPException(404, "Nie znaleziono.")
    stan = db.get(models.Stanowisko, data.stanowisko_id)
    if stan and stan.tylko_weekend and data.data.weekday() < 5:
        raise HTTPException(400, f"Stanowisko '{stan.nazwa}' jest aktywne tylko w weekendy.")
        
    for k, v in data.model_dump().items():
        setattr(a, k, v)
    db.commit(); db.refresh(a)
    return a

@app.delete("/api/przydzialy/{aid}", status_code=204)
def delete_przydział(aid: int, db: Session = Depends(get_db)):
    a = db.get(models.PrzydzialZmiany, aid)
    if not a:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(a); db.commit()

@app.delete("/api/przydzialy", status_code=204)
def clear_przydzialy(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db)
):
    db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= start,
        models.PrzydzialZmiany.data <= end,
    ).delete()
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-ASSIGN
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/auto-assign", response_model=schemas.AutoAssignResult)
def auto_assign_endpoint(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db)
):
    result = _auto_assign(db, start, end)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# EKSPORT CSV
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/eksport-csv")
def eksport_csv(start: date, end: date, db: Session = Depends(get_db)):
    # 1. Pobieramy wszystkie przydziały z wybranego zakresu dat
    przydzialy = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= start,
        models.PrzydzialZmiany.data <= end
    ).all()
    
    # 2. Pobieramy wyłącznie pracowników, którzy są w grafiku "Aktywni"
    pracownicy = db.query(models.Pracownik).filter(models.Pracownik.aktywny == True).all()
    
    # 3. Pobieramy nazwy stanowisk ze słownika (żeby nie wyświetlać samych numerów ID)
    stanowiska_db = db.query(models.Stanowisko).all()
    stanowiska_slownik = {s.id: s.nazwa for s in stanowiska_db}
    
    # 4. Matematyka dat: Tworzymy listę wszystkich dni pomiędzy 'start' i 'end'
    ilosc_dni = (end - start).days
    lista_dat = [start + timedelta(days=i) for i in range(ilosc_dni + 1)]
    
    # 5. Tworzymy specjalny słownik do sortowania przydziałów w konkretne "kratki" tabeli
    # Kluczem jest (pracownik_id, data), a wartością lista tekstów ze zmianami
    przydzialy_w_kratkach = defaultdict(list)
    
    for p in przydzialy:
        # Odczytanie nazwy stanowiska
        nazwa_stanowiska = stanowiska_slownik.get(p.stanowisko_id, "Nieznane")
        
        # Przygotowanie ładnego formatu godzin
        g_od = p.godz_od.strftime("%H:%M") if p.godz_od else ""
        g_do = p.godz_do.strftime("%H:%M") if p.godz_do else "Koniec"
        
        if g_od:
            tekst_zmiany = f"{nazwa_stanowiska} ({g_od}-{g_do})"
        else:
            tekst_zmiany = f"{nazwa_stanowiska} (Cały dzień)"
            
        przydzialy_w_kratkach[(p.pracownik_id, p.data)].append(tekst_zmiany)

    # 6. Tworzymy wirtualny plik CSV w pamięci serwera
    output = io.StringIO()
    # Używamy średnika! Polski Excel często psuje układ, jeśli użyje się standardowego przecinka
    writer = csv.writer(output, delimiter=';')
    
    # ---- TWORZENIE NAGŁÓWKA TABELI ----
    # Wygląda tak: ["Pracownik", "2026-06-01", "2026-06-02", "2026-06-03"...]
    naglowek = ["Pracownik"] + [d.strftime("%d.%m.%Y") for d in lista_dat]
    writer.writerow(naglowek)
    
    # ---- TWORZENIE WIERSZY PRACOWNIKÓW ----
    for pracownik in pracownicy:
        wiersz = [f"{pracownik.imie} {pracownik.nazwisko}"]
        
        for d in lista_dat:
            # Szukamy, czy pracownik ma w danym dniu wpisane zmiany
            zmiany = przydzialy_w_kratkach.get((pracownik.id, d), [])
            
            if zmiany:
                # Łączymy wszystkie zmiany pracownika z tego dnia znakiem |
                # (Zabezpieczenie na wypadek, gdyby pracował np. rano na Barze, a po południu na Sali)
                wiersz.append(" | ".join(zmiany))
            else:
                # Jeśli w tym dniu ma wolne, zostawiamy pustą komórkę
                wiersz.append("")
                
        writer.writerow(wiersz)
        
    # Przygotowanie pliku do wysłania
    output.seek(0)
    
    headers = {
        "Content-Disposition": f"attachment; filename=grafik_{start}_do_{end}.csv"
    }
    
    # Konwersja na bajty z ukrytym znacznikiem 'utf-8-sig'. 
    # Bez tego polskie znaki takie jak ą, ę, ł wyglądałyby w Excelu jak błędy (np. "krzaczki").
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]), 
        media_type="text/csv", 
        headers=headers
    )

# ── SERWOWANIE FRONTENDU (Z PEŁNĄ ŚCIEŻKĄ) ─────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
frontend_path = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

print(f"--- SERWER PROWADZI DO: {frontend_path} ---")

app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")