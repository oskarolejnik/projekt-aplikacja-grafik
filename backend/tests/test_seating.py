"""Silnik sadzania (backend/seating.py) — testy jednostkowe czystej logiki (bez HTTP/DB)."""

import seating


def _t(id, poj, **kw):
    return {"id": id, "nazwa": f"S{id}", "pojemnosc": poj, **kw}


def test_best_fit_wybiera_najmniejszy():
    stoly = [_t(1, 2), _t(2, 4), _t(3, 8)]
    k = seating.dopasuj(2, stoly, [], zajete=set())
    assert k[0]["stoliki"] == [1] and k[0]["nadmiar_miejsc"] == 0


def test_pomija_zajete_stoly():
    stoly = [_t(1, 2), _t(2, 4)]
    k = seating.dopasuj(2, stoly, [], zajete={1})
    assert k[0]["stoliki"] == [2]


def test_respektuje_pojemnosc_min():
    # stół tylko dla ≥4 osób nie jest kandydatem dla pary
    stoly = [_t(1, 8, pojemnosc_min=4), _t(2, 4)]
    k = seating.dopasuj(2, stoly, [], zajete=set())
    assert all(1 not in c["stoliki"] for c in k)
    assert k[0]["stoliki"] == [2]


def test_kombinacja_dla_duzej_grupy():
    stoly = [_t(1, 4), _t(2, 4)]
    komb = [{"id": 10, "nazwa": "S1+S2", "stoliki": [1, 2], "pojemnosc_max": 8, "pojemnosc_min": 5}]
    k = seating.dopasuj(6, stoly, komb, zajete=set())
    assert k[0]["stoliki"] == [1, 2] and k[0]["kombinacja"] is True


def test_woli_pojedynczy_nad_kombinacje():
    stoly = [_t(1, 6), _t(2, 4), _t(3, 4)]
    komb = [{"id": 10, "nazwa": "S2+S3", "stoliki": [2, 3], "pojemnosc_max": 8}]
    k = seating.dopasuj(6, stoly, komb, zajete=set())
    assert k[0]["stoliki"] == [1]              # pojedynczy stół tańszy niż łączenie


def test_kombinacja_gdy_stol_skladowy_zajety_odpada():
    stoly = [_t(1, 4), _t(2, 4)]
    komb = [{"id": 10, "nazwa": "S1+S2", "stoliki": [1, 2], "pojemnosc_max": 8, "pojemnosc_min": 5}]
    assert seating.dopasuj(6, stoly, komb, zajete={2}) == []   # brak innej opcji na 6 os.


def test_preferencja_strefy():
    stoly = [_t(1, 4, strefa="sala"), _t(2, 4, strefa="ogród")]
    k = seating.dopasuj(4, stoly, [], zajete=set(), preferencje={"strefa": "ogród"})
    assert k[0]["stoliki"] == [2]


def test_preferencja_cechy():
    stoly = [_t(1, 4, cechy=[]), _t(2, 4, cechy=["okno"])]
    k = seating.dopasuj(4, stoly, [], zajete=set(), preferencje={"cechy": ["okno"]})
    assert k[0]["stoliki"] == [2]


def test_priorytet_rozstrzyga_remis():
    stoly = [_t(1, 4, priorytet=5), _t(2, 4, priorytet=1)]
    k = seating.dopasuj(4, stoly, [], zajete=set())
    assert k[0]["stoliki"] == [2]              # niższy priorytet = wcześniej


def test_top3_limit_i_kolejnosc():
    stoly = [_t(1, 2), _t(2, 4), _t(3, 6), _t(4, 8)]
    k = seating.dopasuj(2, stoly, [], zajete=set(), limit=3)
    assert len(k) == 3
    assert [c["nadmiar_miejsc"] for c in k] == [0, 2, 4]   # rosnące marnowanie


def test_brak_dopasowania():
    assert seating.dopasuj(20, [_t(1, 2)], [], zajete=set()) == []
