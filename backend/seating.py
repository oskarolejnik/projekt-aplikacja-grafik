"""Silnik sadzania (weighted greedy best-fit) — czysta logika, bez HTTP/DB, w pełni testowalna.

Buduje kandydatów (pojedyncze stoły + predefiniowane kombinacje), odrzuca zajęte oraz nie-
mieszczące grupy, ocenia funkcją kosztu i zwraca posortowanych (najtańszy = najlepszy).
Wołany przez endpointy /api/host/sugestia-stolika (top-N) i /api/rezerwacje-stolik/{id}/auto-przydziel.

Wejście to zwykłe słowniki (odseparowane od SQLAlchemy):
  stolik:     {"id", "nazwa", "pojemnosc", "pojemnosc_min"?, "cechy"?, "priorytet"?, "strefa"?}
  kombinacja: {"id", "nazwa", "stoliki":[id,…], "pojemnosc_min"?, "pojemnosc_max"?}
  zajete:     zbiór/lista id stołów zajętych w rozważanym oknie czasu
  preferencje:{"strefa"?, "cechy"?[...]}
"""

DOMYSLNE_WAGI = {
    "marnowanie": 1.0,    # kara za pusty stół (nadmiar miejsc = pojemność − osoby)
    "kombinacja": 2.0,    # kara za łączenie stołów (wolimy jeden stół, gdy się mieści)
    "priorytet": 0.3,     # priorytet stołu (mniejszy = chętniej sadzany)
    "preferencja": 1.5,   # bonus (obniża koszt) za zgodność cech z preferencją gościa
    "strefa": 0.4,        # kara za niezgodność strefy z preferencją
}


def _poj(stol):
    return stol.get("pojemnosc") or 0


def _poj_min(stol):
    return stol.get("pojemnosc_min") or 1


def kandydaci(osoby, stoliki, kombinacje):
    """Zbiory stołów mieszczące grupę: pojedyncze (pojemnosc_min ≤ osoby ≤ pojemnosc) oraz
    kombinacje (pojemnosc_min ≤ osoby ≤ pojemnosc_max). Zwraca listę dictów z metadanymi."""
    out = []
    for s in stoliki:
        if _poj_min(s) <= osoby <= _poj(s):
            out.append({"stoliki": [s["id"]], "nazwa": s.get("nazwa"),
                        "suma_pojemnosci": _poj(s), "kombinacja": False, "_stoly": [s]})
    by_id = {s["id"]: s for s in stoliki}
    for k in kombinacje:
        czlonkowie = [by_id[i] for i in (k.get("stoliki") or []) if i in by_id]
        if len(czlonkowie) < 2:
            continue                                  # niekompletna kombinacja (usunięty stół) — pomiń
        poj_max = k.get("pojemnosc_max") or sum(_poj(s) for s in czlonkowie)
        poj_min = k.get("pojemnosc_min") or 1
        if poj_min <= osoby <= poj_max:
            out.append({"stoliki": [s["id"] for s in czlonkowie], "nazwa": k.get("nazwa"),
                        "suma_pojemnosci": poj_max, "kombinacja": True, "_stoly": czlonkowie})
    return out


def koszt(kand, osoby, zajete, preferencje, wagi):
    """Koszt kandydata (niżej = lepiej). None gdy którykolwiek stół zbioru jest zajęty."""
    if set(kand["stoliki"]) & set(zajete or ()):
        return None
    w = {**DOMYSLNE_WAGI, **(wagi or {})}
    c = w["marnowanie"] * max(0, kand["suma_pojemnosci"] - osoby)
    c += w["kombinacja"] * (len(kand["stoliki"]) - 1)
    prio = [(s.get("priorytet") or 0) for s in kand["_stoly"]]
    c += w["priorytet"] * (sum(prio) / len(prio) if prio else 0)
    pref = preferencje or {}
    if pref.get("strefa") and not all(s.get("strefa") == pref["strefa"] for s in kand["_stoly"]):
        c += w["strefa"]
    if pref.get("cechy"):
        want = set(pref["cechy"])
        have = set().union(*[set(s.get("cechy") or []) for s in kand["_stoly"]])
        c -= w["preferencja"] * len(want & have)
    return c


def dopasuj(osoby, stoliki, kombinacje, zajete=(), preferencje=None, wagi=None, limit=3):
    """Top-N kandydatów posortowanych po koszcie. [] gdy brak dopasowania.
    Sortowanie remisów: mniej stołów (prostota), potem id (deterministycznie)."""
    osoby = max(1, int(osoby or 1))
    wynik = []
    for kand in kandydaci(osoby, stoliki, kombinacje):
        c = koszt(kand, osoby, zajete, preferencje, wagi)
        if c is None:
            continue
        skladniki = {
            "marnowanie": max(0, kand["suma_pojemnosci"] - osoby),
            "kombinacja": len(kand["stoliki"]) - 1,
        }
        wynik.append({
            "stoliki": kand["stoliki"], "nazwa": kand["nazwa"],
            "suma_pojemnosci": kand["suma_pojemnosci"], "kombinacja": kand["kombinacja"],
            "nadmiar_miejsc": max(0, kand["suma_pojemnosci"] - osoby),
            "koszt": round(c, 3), "skladniki": skladniki,
        })
    wynik.sort(key=lambda x: (x["koszt"], len(x["stoliki"]), x["stoliki"]))
    return wynik[:limit] if limit else wynik
