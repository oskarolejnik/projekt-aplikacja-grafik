"""Regresje integralności danych przy usuwaniu (audyt runda 4): kasowanie rekordu nadrzędnego
kasuje zależne (bez sierot na SQLite, bez FK RESTRICT 500 na PostgreSQL)."""

from datetime import datetime, time

import factories
import models


def test_delete_pracownik_czysci_zalezne_rekordy(admin_client, db):
    """#2/#3: usunięcie pracownika kasuje zależne rekordy bez kaskady ORM (RozliczenieKelner, Urlop) —
    nie zostaje sierota zawyżająca utarg dnia (SQLite), a na PostgreSQL delete nie rzuca 500."""
    k = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(0)
    roz = models.RozliczenieDnia(data=d)
    roz.kelnerzy.append(models.RozliczenieKelner(pracownik_id=k.id, gotowka=500))
    db.add(roz)
    db.add(models.Urlop(pracownik_id=k.id, start=d, koniec=d, status="zaakceptowany",
                        utworzono_at=datetime(2026, 7, 1)))
    db.commit()

    assert admin_client.delete(f"/api/pracownicy/{k.id}").status_code == 204
    assert db.query(models.RozliczenieKelner).filter_by(pracownik_id=k.id).count() == 0
    assert db.query(models.Urlop).filter_by(pracownik_id=k.id).count() == 0


def test_delete_stanowisko_czysci_wymagania(admin_client, db):
    """#3: usunięcie stanowiska kasuje zależne WymaganiaDnia (inaczej FK RESTRICT 500 na PostgreSQL)."""
    st = factories.StanowiskoFactory(nazwa="Bar")
    db.add(models.WymaganiaDnia(data=factories.dzien(0), stanowisko_id=st.id, liczba_osob=2))
    db.commit()

    assert admin_client.delete(f"/api/stanowiska/{st.id}").status_code == 204
    assert db.query(models.WymaganiaDnia).filter_by(stanowisko_id=st.id).count() == 0


def test_clear_przydzialy_czysci_oferty_gieldy(admin_client, db):
    """#8: bulk-czyszczenie przydziałów usuwa też powiązane oferty giełdy — bez sierot i ryzyka
    przepięcia cudzej zmiany przy odzysku id przydziału na SQLite."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    a = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(0)
    przy = models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=a.id, godz_od=time(10, 0))
    db.add(przy); db.commit()
    db.add(models.OfertaZmiany(przydzial_id=przy.id, wystawiajacy_id=a.id, status="otwarta",
                               utworzono_at=datetime(2026, 7, 1)))
    db.commit()

    assert admin_client.delete(f"/api/przydzialy?start={d}&end={d}").status_code == 204
    assert db.query(models.PrzydzialZmiany).count() == 0
    assert db.query(models.OfertaZmiany).count() == 0
