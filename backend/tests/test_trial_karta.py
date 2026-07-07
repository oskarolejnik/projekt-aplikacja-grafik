"""Trial planu płatnego z kartą → auto-obciążenie po 14 dniach (deps.synchronizuj_subskrypcje).
Trial BEZ karty (stary/operatorski) → spadek do Free. Nie-wygasły trial → bez zmian."""

from datetime import date, timedelta

import models
from deps import get_subskrypcja, synchronizuj_subskrypcje


def _ustaw(db, *, tier, status, dni, karta_token=None, karta_ostatnie4=None):
    s = get_subskrypcja(db)
    s.tier, s.status = tier, status
    s.data_od = date.today() - timedelta(days=20)
    s.data_do = date.today() + timedelta(days=dni)   # dni<0 → już po terminie
    s.karta_token, s.karta_ostatnie4 = karta_token, karta_ostatnie4
    db.commit()
    return s


def test_trial_z_karta_po_terminie_obciaza_i_zostaje_na_planie(db):
    _ustaw(db, tier="pro", status="trial", dni=-1, karta_token="sandbox_abc", karta_ostatnie4="4242")
    s = synchronizuj_subskrypcje(db)
    # Auto-obciążenie: trial → aktywna, tier zostaje (plan wybrany), opłacony okres +30 dni.
    assert s.status == "aktywna" and s.tier == "pro"
    assert s.data_do == date.today() + timedelta(days=30)
    # Wpis audytu obciążenia.
    h = db.query(models.HistoriaSubskrypcji).filter_by(akcja="odnowienie").all()
    assert len(h) == 1 and h[0].tier_na == "pro"


def test_trial_z_karta_idempotentny(db):
    _ustaw(db, tier="premium", status="trial", dni=-3, karta_token="sandbox_x", karta_ostatnie4="1111")
    synchronizuj_subskrypcje(db)
    synchronizuj_subskrypcje(db)   # drugie wywołanie nie obciąża ponownie
    assert db.query(models.HistoriaSubskrypcji).filter_by(akcja="odnowienie").count() == 1


def test_trial_bez_karty_po_terminie_spada_do_free(db):
    _ustaw(db, tier="premium", status="trial", dni=-1)   # brak karty (stary trial)
    s = synchronizuj_subskrypcje(db)
    assert s.status == "aktywna" and s.tier == "free" and s.data_do is None
    assert db.query(models.HistoriaSubskrypcji).filter_by(akcja="odnowienie").count() == 0


def test_trial_niewygasly_bez_zmian(db):
    _ustaw(db, tier="pro", status="trial", dni=5, karta_token="sandbox_y", karta_ostatnie4="4242")
    s = synchronizuj_subskrypcje(db)
    assert s.status == "trial" and s.tier == "pro"   # jeszcze trwa
