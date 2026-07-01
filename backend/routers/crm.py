"""Router: CRM gości — historia rezerwacji, scoring no-show, VIP (roadmapa v1.5).

Dane gościa (PII) → tylko admin (wymusza role_guard). Agregacja PO STRONIE PYTHONA, bo
telefon/email są szyfrowane niedeterministycznie (EncryptedString) i nie da się ich GROUP BY
w SQL — pobieramy rezerwacje-gości i grupujemy po odszyfrowanym telefonie (fallback e-mail/nazwisko).
Bez nowych tabel/migracji (wzór jak /api/pulpit).
"""

from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import models
from database import get_db
from sms import _normalizuj_numer

router = APIRouter()

_AKTYWNE = ("rezerwacja", "potwierdzona")


@router.get("/api/crm/goscie")
def crm_goscie(min_wizyt: int = Query(1), limit: int = Query(500), db: Session = Depends(get_db)):
    """Lista gości z historią rezerwacji i scoringiem no-show. Sortowana malejąco po liczbie wizyt."""
    rezerwacje = db.query(models.Termin).filter(models.Termin.rodzaj.in_(("stolik", "sala"))).all()

    grupy = defaultdict(list)
    for t in rezerwacje:
        klucz = _normalizuj_numer(t.telefon or "") or (t.email or "").strip().lower() or (t.nazwisko or "").strip().lower()
        if klucz:
            grupy[klucz].append(t)

    goscie = []
    for klucz, lista in grupy.items():
        wizyt = len(lista)
        if wizyt < max(1, int(min_wizyt)):
            continue
        odbyte = sum(1 for t in lista if t.status == "odbyla")
        no_show = sum(1 for t in lista if t.status == "no_show")
        odwolane = sum(1 for t in lista if t.status == "odwolana")
        aktywne = sum(1 for t in lista if t.status in _AKTYWNE)
        # Współczynnik no-show liczymy TYLKO po wizytach zamkniętych (odbyte/no_show/odwołane) —
        # rezerwacje przyszłe/oczekujące (aktywne) nie są dowodem zachowania i rozwadniałyby ryzyko
        # (im więcej gość ma nadchodzących rezerwacji, tym niżej wychodziłby scoring — błąd).
        zamkniete = odbyte + no_show + odwolane
        no_show_proc = round(no_show / zamkniete * 100) if zamkniete else 0
        ryzyko = "wysokie" if (zamkniete >= 3 and no_show_proc >= 30) else ("srednie" if no_show_proc > 0 else "niskie")
        najnowsza = max(lista, key=lambda t: t.data)
        daty = [t.data for t in lista]
        goscie.append({
            "klucz": klucz,
            "nazwisko": najnowsza.nazwisko, "telefon": najnowsza.telefon, "email": najnowsza.email,
            "wizyt": wizyt, "odbyte": odbyte, "no_show": no_show, "odwolane": odwolane, "aktywne": aktywne,
            "no_show_proc": no_show_proc, "ryzyko": ryzyko, "vip": odbyte >= 5,
            "ostatnia_data": str(max(daty)), "pierwsza_data": str(min(daty)),
        })

    goscie.sort(key=lambda g: (g["wizyt"], g["odbyte"]), reverse=True)
    return goscie[:max(1, min(int(limit), 5000))]
