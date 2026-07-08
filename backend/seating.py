"""Silnik sadzania (weighted greedy best-fit) — czysta logika, bez HTTP/DB, w pełni testowalna.

Buduje kandydatów (pojedyncze stoły + predefiniowane kombinacje + auto-kombinacje z grafu sąsiedztwa),
odrzuca zajęte oraz nie-mieszczące grupy, ocenia funkcją kosztu i zwraca posortowanych (najtańszy =
najlepszy). Wołany przez /api/host/sugestia-stolika (top-N) i /api/rezerwacje-stolik/{id}/auto-przydziel.

Wejście to zwykłe słowniki (odseparowane od SQLAlchemy):
  stolik:     {"id","nazwa","pojemnosc","pojemnosc_min"?,"cechy"?,"priorytet"?,"strefa"?,"sekcja"?}
  kombinacja: {"id","nazwa","stoliki":[id,…],"pojemnosc_min"?,"pojemnosc_max"?}
  zajete:     zbiór/lista id stołów zajętych w rozważanym oknie czasu
  sasiedztwo: lista krawędzi [(id_a,id_b),…] — które stoły da się złączyć (auto-kombinacje)
  obciazenie_sekcji: {sekcja: liczba_zajętych} — do balansu obłożenia kelnerów
  preferencje:{"strefa"?,"cechy"?[...]}
"""

DOMYSLNE_WAGI = {
    "marnowanie": 1.0,    # kara za pusty stół (nadmiar miejsc = pojemność − osoby)
    "kombinacja": 2.0,    # kara za łączenie stołów (wolimy jeden stół, gdy się mieści)
    "priorytet": 0.3,     # priorytet stołu (mniejszy = chętniej sadzany)
    "preferencja": 1.5,   # bonus (obniża koszt) za zgodność cech z preferencją gościa
    "strefa": 0.4,        # kara za niezgodność strefy z preferencją
    "balans_sekcji": 0.5,  # kara za dokładanie do już obłożonej sekcji kelnerskiej
    "holdback": 0.6,      # kwadratowa kara za DUŻY nadmiar (rezerwuj duże stoły dla dużych grup)
}
HOLDBACK_PROG = 4            # nadmiar ≥ tylu miejsc uruchamia hold-back
MAX_STOLOW_KOMBINACJI = 4    # ile stołów max w auto-kombinacji z grafu


def _poj(stol):
    return stol.get("pojemnosc") or 0


def _poj_min(stol):
    return stol.get("pojemnosc_min") or 1


def _kombinacje_z_grafu(osoby, stoliki, sasiedztwo):
    """Auto-kombinacje: MINIMALNE spójne podzbiory stołów (wg krawędzi grafu) o łącznej pojemności
    ≥ osoby. DFS rozszerza zbiór o sąsiadów; gdy pojemność wystarcza — zapisuje i nie rośnie dalej."""
    by_id = {s["id"]: s for s in stoliki}
    sasiad = {}
    for a, b in (sasiedztwo or []):
        if a in by_id and b in by_id:
            sasiad.setdefault(a, set()).add(b)
            sasiad.setdefault(b, set()).add(a)
    znalezione = {}

    def rozwin(zbior, suma):
        if suma >= osoby:
            if len(zbior) >= 2:                       # pojedyncze stoły obsługuje główna pętla
                fs = frozenset(zbior)
                if fs not in znalezione:
                    czlonkowie = [by_id[i] for i in sorted(zbior)]
                    znalezione[fs] = {
                        "stoliki": sorted(zbior),
                        "nazwa": "+".join(str(by_id[i].get("nazwa") or i) for i in sorted(zbior)),
                        "suma_pojemnosci": suma, "kombinacja": True, "_stoly": czlonkowie}
            return                                    # minimalny zbiór — nie rozszerzaj
        if len(zbior) >= MAX_STOLOW_KOMBINACJI:
            return
        sasiedzi = set().union(*[sasiad.get(i, set()) for i in zbior]) - zbior
        for j in sorted(sasiedzi):
            rozwin(zbior | {j}, suma + _poj(by_id[j]))

    for s in stoliki:
        rozwin({s["id"]}, _poj(s))
    return list(znalezione.values())


def kandydaci(osoby, stoliki, kombinacje, sasiedztwo=None):
    """Zbiory stołów mieszczące grupę: pojedyncze + predefiniowane kombinacje + (opcjonalnie)
    auto-kombinacje z grafu sąsiedztwa. Deduplikacja po zbiorze stołów."""
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
    if sasiedztwo:
        widziane = {frozenset(k["stoliki"]) for k in out}
        for k in _kombinacje_z_grafu(osoby, stoliki, sasiedztwo):
            fs = frozenset(k["stoliki"])
            if fs not in widziane:
                out.append(k)
                widziane.add(fs)
    return out


def koszt(kand, osoby, zajete, preferencje, wagi, obciazenie_sekcji=None):
    """Koszt kandydata (niżej = lepiej). None gdy którykolwiek stół zbioru jest zajęty."""
    if set(kand["stoliki"]) & set(zajete or ()):
        return None
    w = {**DOMYSLNE_WAGI, **(wagi or {})}
    nadmiar = max(0, kand["suma_pojemnosci"] - osoby)
    c = w["marnowanie"] * nadmiar
    c += w["kombinacja"] * (len(kand["stoliki"]) - 1)
    prio = [(s.get("priorytet") or 0) for s in kand["_stoly"]]
    c += w["priorytet"] * (sum(prio) / len(prio) if prio else 0)
    if nadmiar >= HOLDBACK_PROG:                      # hold-back: chroni duże stoły przed małą grupą
        c += w["holdback"] * nadmiar ** 2
    if obciazenie_sekcji:                             # balans: nie dokładaj do obłożonej sekcji
        sekcje = {s.get("sekcja") for s in kand["_stoly"] if s.get("sekcja")}
        c += w["balans_sekcji"] * max((obciazenie_sekcji.get(sek, 0) for sek in sekcje), default=0)
    pref = preferencje or {}
    if pref.get("strefa") and not all(s.get("strefa") == pref["strefa"] for s in kand["_stoly"]):
        c += w["strefa"]
    if pref.get("cechy"):
        want = set(pref["cechy"])
        have = set().union(*[set(s.get("cechy") or []) for s in kand["_stoly"]])
        c -= w["preferencja"] * len(want & have)
    return c


def dopasuj(osoby, stoliki, kombinacje, zajete=(), preferencje=None, wagi=None, limit=3,
            sasiedztwo=None, obciazenie_sekcji=None):
    """Top-N kandydatów posortowanych po koszcie. [] gdy brak dopasowania.
    Sortowanie remisów: mniej stołów (prostota), potem id (deterministycznie)."""
    osoby = max(1, int(osoby or 1))
    wynik = []
    for kand in kandydaci(osoby, stoliki, kombinacje, sasiedztwo=sasiedztwo):
        c = koszt(kand, osoby, zajete, preferencje, wagi, obciazenie_sekcji=obciazenie_sekcji)
        if c is None:
            continue
        wynik.append({
            "stoliki": kand["stoliki"], "nazwa": kand["nazwa"],
            "suma_pojemnosci": kand["suma_pojemnosci"], "kombinacja": kand["kombinacja"],
            "nadmiar_miejsc": max(0, kand["suma_pojemnosci"] - osoby),
            "koszt": round(c, 3),
            "skladniki": {"marnowanie": max(0, kand["suma_pojemnosci"] - osoby),
                          "kombinacja": len(kand["stoliki"]) - 1},
        })
    wynik.sort(key=lambda x: (x["koszt"], len(x["stoliki"]), x["stoliki"]))
    return wynik[:limit] if limit else wynik
