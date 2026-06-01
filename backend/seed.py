"""Dane startowe — uruchom raz: python seed.py"""

from database import SessionLocal, init_db
import models
from datetime import date

def seed():
    init_db()
    db = SessionLocal()

    if db.query(models.Stanowisko).count() > 0:
        print("Dane już istnieją, pomijam seed.")
        db.close()
        return

    # ── stanowiska ──────────────────────────────────────────────────────
    stanowiska_data = [
        ("Bar",      False),
        ("Kuchnia",  False),
        ("Sala",     False),
        ("Kasa",     False),
        ("Sala-ABC", True),   # tylko weekend
        ("Sala-RZP", True),   # tylko weekend
        ("Sala-Bar", True),   # tylko weekend
    ]
    stanowiska = {}
    for nazwa, weekend in stanowiska_data:
        s = models.Stanowisko(nazwa=nazwa, tylko_weekend=weekend)
        db.add(s)
        db.flush()
        stanowiska[nazwa] = s

    # ── pracownicy ──────────────────────────────────────────────────────
    pracownicy_data = [
        ("Jan",     "Kowalski",  ["Bar", "Kuchnia", "Sala", "Sala-ABC"]),
        ("Anna",    "Nowak",     ["Bar", "Sala-ABC", "Sala-RZP", "Sala-Bar"]),
        ("Piotr",   "Wiśniewski",["Kuchnia", "Sala", "Kasa"]),
        ("Maria",   "Kowalczyk", ["Bar", "Kasa", "Sala-Bar"]),
        ("Tomasz",  "Lewandowski",["Kuchnia", "Bar"]),
        ("Katarzyna","Wójcik",   ["Sala", "Kasa", "Sala-RZP", "Sala-ABC"]),
    ]
    for imie, nazwisko, kwal_nazwy in pracownicy_data:
        p = models.Pracownik(imie=imie, nazwisko=nazwisko, aktywny=True)
        p.kwalifikacje = [stanowiska[n] for n in kwal_nazwy if n in stanowiska]
        db.add(p)

    # ── przykładowe wymagania (na czerwiec 2026) ────────────────────────
    # dni powszednie: Bar×1, Kuchnia×2, Sala×2, Kasa×1
    # weekendy: Bar×1, Kuchnia×1, Sala-ABC×2, Sala-RZP×1, Sala-Bar×1
    from datetime import timedelta
    start = date(2026, 6, 1)
    for i in range(30):
        d = start + timedelta(days=i)
        is_weekend = d.weekday() >= 5
        if is_weekend:
            reqs = [
                ("Bar",      1),
                ("Kuchnia",  1),
                ("Sala-ABC", 2),
                ("Sala-RZP", 1),
                ("Sala-Bar", 1),
            ]
        else:
            reqs = [
                ("Bar",     1),
                ("Kuchnia", 2),
                ("Sala",    2),
                ("Kasa",    1),
            ]
        for nazwa, liczba in reqs:
            w = models.WymaganiaDnia(
                data=d,
                stanowisko_id=stanowiska[nazwa].id,
                liczba_osob=liczba,
            )
            db.add(w)

    db.commit()
    db.close()
    print("Seed zakończony pomyślnie.")

if __name__ == "__main__":
    seed()
