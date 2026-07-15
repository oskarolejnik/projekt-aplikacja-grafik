"""Silnik sadzania (weighted greedy best-fit) — czysta logika, bez HTTP/DB, w pełni testowalna.

Buduje kandydatów (pojedyncze stoły + predefiniowane kombinacje + auto-kombinacje z grafu sąsiedztwa),
odrzuca zajęte oraz nie-mieszczące grupy, ocenia funkcją kosztu i zwraca posortowanych (najtańszy =
najlepszy). Wołany przez /api/host/sugestia-stolika (top-N) i /api/rezerwacje-stolik/{id}/auto-przydziel.

Wejście to zwykłe słowniki (odseparowane od SQLAlchemy):
  stolik:     {"id","nazwa","pojemnosc",...,"sala_id"?,"strategia_zapelniania"?,
               "priorytet_sali"?,"kolejnosc_sali"?,"wersja_id"?}
  kombinacja: {"id","wersja_id"?,"nazwa","stoliki":[id,…],"pojemnosc_min"?,
               "pojemnosc_max"?,"priorytet"?}
  zajete:     zbiór/lista id stołów zajętych w rozważanym oknie czasu
  sasiedztwo: lista krawędzi [(id_a,id_b),…] — które stoły da się złączyć (auto-kombinacje)
  obciazenie_sekcji: {sekcja: liczba_zajętych} — do balansu obłożenia kelnerów
  preferencje:{"strefa"?,"cechy"?[...]}
"""

DOMYSLNE_WAGI = {
    "marnowanie": 1.0,    # kara za pusty stół (nadmiar miejsc = pojemność − osoby)
    "kombinacja": 2.0,    # kara za łączenie stołów (wolimy jeden stół, gdy się mieści)
    "priorytet": 0.3,     # priorytet stołu/kombinacji (mniejszy = chętniej sadzany)
    "preferencja": 1.5,   # bonus (obniża koszt) za zgodność cech z preferencją gościa
    "strefa": 0.4,        # kara za niezgodność strefy z preferencją
    "balans_sekcji": 0.5,  # kara za dokładanie do już obłożonej sekcji kelnerskiej
    "holdback": 0.6,      # kwadratowa kara za DUŻY nadmiar (rezerwuj duże stoły dla dużych grup)
    "priorytet_sali": 0.5,  # miękki koszt sal ``preferuj``; ścisłe są filtrowane osobno
}
HOLDBACK_PROG = 4            # nadmiar ≥ tylu miejsc uruchamia hold-back
MAX_STOLOW_KOMBINACJI = 4    # ile stołów max w auto-kombinacji z grafu


def _poj(stol):
    return stol.get("pojemnosc") or 0


def _poj_min(stol):
    return stol.get("pojemnosc_min") or 1


def _metadane_sali(stoly):
    """Wspólna sala/snapshot kandydata; zestaw między salami nie dostaje polityki."""
    if not stoly:
        return {
            "_sala_id": None,
            "_strategia_zapelniania": "preferuj",
            "_priorytet_sali": 0,
            "_kolejnosc_sali": 0,
            "_wersja_planu_id": None,
        }
    room_ids = {stol.get("sala_id") for stol in stoly}
    if len(room_ids) != 1:
        return {
            "_sala_id": None,
            "_strategia_zapelniania": "preferuj",
            "_priorytet_sali": 0,
            "_kolejnosc_sali": 0,
            "_wersja_planu_id": None,
        }
    first = stoly[0]
    version_ids = {stol.get("wersja_id") for stol in stoly}
    return {
        "_sala_id": first.get("sala_id"),
        "_strategia_zapelniania": first.get("strategia_zapelniania") or "preferuj",
        "_priorytet_sali": first.get("priorytet_sali") or 0,
        "_kolejnosc_sali": first.get("kolejnosc_sali") or 0,
        "_wersja_planu_id": next(iter(version_ids)) if len(version_ids) == 1 else None,
    }


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
                        "suma_pojemnosci": suma, "kombinacja": True, "_stoly": czlonkowie,
                        **_metadane_sali(czlonkowie),
                        "_kombinacja_planu_id": None}
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
                        "suma_pojemnosci": _poj(s), "kombinacja": False, "_stoly": [s],
                        **_metadane_sali([s]), "_kombinacja_planu_id": None})
    by_id = {s["id"]: s for s in stoliki}
    for k in kombinacje:
        raw_stoliki = k.get("stoliki")
        if not isinstance(raw_stoliki, (list, tuple)):
            continue
        try:
            requested = [int(i) for i in raw_stoliki]
        except (TypeError, ValueError):
            continue
        if len(requested) < 2 or len(set(requested)) != len(requested):
            continue                                  # uszkodzony/zdublowany skład — pomiń
        czlonkowie = [by_id[i] for i in requested if i in by_id]
        if len(czlonkowie) != len(requested):
            continue                                  # choć jeden brakujący stół unieważnia CAŁĄ kombinację
        poj_max = k.get("pojemnosc_max") or sum(_poj(s) for s in czlonkowie)
        poj_min = k.get("pojemnosc_min") or 1
        if poj_min <= osoby <= poj_max:
            room_meta = _metadane_sali(czlonkowie)
            version_id = k.get("wersja_id")
            if version_id is not None:
                room_meta["_wersja_planu_id"] = version_id
            out.append({"stoliki": [s["id"] for s in czlonkowie], "nazwa": k.get("nazwa"),
                        "suma_pojemnosci": poj_max, "kombinacja": True, "_stoly": czlonkowie,
                        **room_meta,
                        "_kombinacja_planu_id": (k.get("id") if version_id is not None else None),
                        "_priorytet_kombinacji": k.get("priorytet") or 0})
    if sasiedztwo:
        widziane = {frozenset(k["stoliki"]) for k in out}
        # Jawna definicja administratora ma pierwszeństwo nad grafem także wtedy, gdy dana
        # grupa wypada poza jej min/max. Graf nie może obchodzić ustawionego zakresu.
        for definicja in kombinacje:
            raw_stoliki = definicja.get("stoliki")
            if not isinstance(raw_stoliki, (list, tuple)):
                continue
            try:
                ids = [int(i) for i in raw_stoliki]
            except (TypeError, ValueError):
                continue
            if len(ids) >= 2 and len(set(ids)) == len(ids):
                widziane.add(frozenset(ids))
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
    c += w["priorytet"] * (kand.get("_priorytet_kombinacji") or 0)
    if kand.get("_strategia_zapelniania") != "wypelniaj_kolejno":
        c += w["priorytet_sali"] * (kand.get("_priorytet_sali") or 0)
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
            sasiedztwo=None, obciazenie_sekcji=None, respect_room_fill=True):
    """Top-N kandydatów posortowanych po koszcie. [] gdy brak dopasowania.
    Sortowanie remisów: mniej stołów (prostota), potem id (deterministycznie)."""
    osoby = max(1, int(osoby or 1))
    najlepsze_zestawy = {}
    for kand in kandydaci(osoby, stoliki, kombinacje, sasiedztwo=sasiedztwo):
        c = koszt(kand, osoby, zajete, preferencje, wagi, obciazenie_sekcji=obciazenie_sekcji)
        if c is None:
            continue
        oceniony = {
            "stoliki": kand["stoliki"], "nazwa": kand["nazwa"],
            "suma_pojemnosci": kand["suma_pojemnosci"], "kombinacja": kand["kombinacja"],
            "sala_id": kand.get("_sala_id"),
            "strategia_zapelniania": kand.get("_strategia_zapelniania") or "preferuj",
            "priorytet_sali": kand.get("_priorytet_sali") or 0,
            "kolejnosc_sali": kand.get("_kolejnosc_sali") or 0,
            "wersja_planu_id": kand.get("_wersja_planu_id"),
            "kombinacja_planu_id": kand.get("_kombinacja_planu_id"),
            "nadmiar_miejsc": max(0, kand["suma_pojemnosci"] - osoby),
            "koszt": round(c, 3),
            "skladniki": {"marnowanie": max(0, kand["suma_pojemnosci"] - osoby),
                          "kombinacja": len(kand["stoliki"]) - 1},
        }
        klucz = frozenset(kand["stoliki"])
        poprzedni = najlepsze_zestawy.get(klucz)
        if poprzedni is None or (
            oceniony["koszt"], oceniony["nazwa"] or ""
        ) < (
            poprzedni["koszt"], poprzedni["nazwa"] or ""
        ):
            najlepsze_zestawy[klucz] = oceniony
    wynik = list(najlepsze_zestawy.values())
    scisle = [
        kandydat for kandydat in wynik
        if kandydat["strategia_zapelniania"] == "wypelniaj_kolejno"
        and kandydat["sala_id"] is not None
    ]
    if scisle and respect_room_fill:
        pierwsza_sala = min(
            (
                kandydat["priorytet_sali"],
                kandydat["kolejnosc_sali"],
                kandydat["sala_id"],
            )
            for kandydat in scisle
        )
        wynik = [
            kandydat for kandydat in scisle
            if (
                kandydat["priorytet_sali"],
                kandydat["kolejnosc_sali"],
                kandydat["sala_id"],
            ) == pierwsza_sala
        ]
    wynik.sort(key=lambda x: (x["koszt"], len(x["stoliki"]), x["stoliki"]))
    return wynik[:limit] if limit else wynik
