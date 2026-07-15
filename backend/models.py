"""Modele ORM — tabele SQLite przez SQLAlchemy."""

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time, DateTime, Float, JSON,
    ForeignKey, ForeignKeyConstraint, Table, UniqueConstraint, CheckConstraint, Index, text
)
from sqlalchemy.orm import relationship, declarative_base

from szyfrowanie import EncryptedString   # pola kontaktowe gości szyfrowane at-rest (RODO)

Base = declarative_base()

pracownik_stanowisko = Table(
    "pracownik_stanowisko",
    Base.metadata,
    Column("pracownik_id", Integer, ForeignKey("pracownicy.id"), primary_key=True),
    Column("stanowisko_id", Integer, ForeignKey("stanowiska.id"), primary_key=True),
)

class StawkaPracownika(Base):
    """Stawka GODZINOWA pracownika na danej kwalifikacji (stanowisku).
    Ta sama kwalifikacja (np. „sala") może mieć różną stawkę u różnych osób."""
    __tablename__ = "stawki_pracownikow"
    __table_args__ = (UniqueConstraint("pracownik_id", "stanowisko_id"),)
    id            = Column(Integer, primary_key=True, index=True)
    pracownik_id  = Column(Integer, ForeignKey("pracownicy.id", ondelete="CASCADE"), nullable=False, index=True)
    stanowisko_id = Column(Integer, ForeignKey("stanowiska.id", ondelete="CASCADE"), nullable=False, index=True)
    stawka        = Column(Float, nullable=False, default=0.0)

class Pracownik(Base):
    __tablename__ = "pracownicy"
    id         = Column(Integer, primary_key=True, index=True)
    imie       = Column(String(64), nullable=False)
    nazwisko   = Column(String(64), nullable=False)
    aktywny    = Column(Boolean, default=True)
    kolejnosc  = Column(Integer, nullable=False, default=0)   # ręczna kolejność wyświetlania
    kolor      = Column(String(16), nullable=True)            # tło za imieniem (#rrggbb) — ręczna paleta
    dzial      = Column(String(16), nullable=False, default="obsluga")  # 'obsluga' | 'kuchnia' — osobne grafiki

    kwalifikacje  = relationship("Stanowisko", secondary=pracownik_stanowisko, back_populates="uprawnieni")
    dyspozycje    = relationship("Dyspozycja", back_populates="pracownik", cascade="all, delete-orphan")
    przydzialy    = relationship("PrzydzialZmiany", back_populates="pracownik", cascade="all, delete-orphan")
    stawki        = relationship("StawkaPracownika", cascade="all, delete-orphan")

class Stanowisko(Base):
    __tablename__ = "stanowiska"
    id            = Column(Integer, primary_key=True, index=True)
    nazwa         = Column(String(64), nullable=False, unique=True)
    tylko_weekend = Column(Boolean, default=False)
    # Powiązania widoczności w „Moim grafiku":
    #  • widoczny_dla_wszystkich — holderzy tego stanowiska są widoczni dla KAŻDEGO pracownika (np. Menadżer),
    #  • grupa_widocznosci — stanowiska z tą samą (niepustą) grupą widzą się WZAJEMNIE (np. KOMP+Wydawka).
    widoczny_dla_wszystkich = Column(Boolean, nullable=False, default=False)
    grupa_widocznosci       = Column(String(64), nullable=True)
    # Semantyczna ROLA stanowiska — zastępuje rozpoznawanie po nazwie (które było zaszyte pod
    # jeden lokal). Pozwala dowolnie nazwać stanowisko, a zachowanie wynika z roli:
    #   'sala'       — parkiet/kelnerzy (rozliczenia dnia, wybór zamykającego, priorytet obsady),
    #   'kuchnia'    — ukryte stanowisko kuchni (pełne godziny RCP, stawka per osoba),
    #   'techniczny' — ukryte stanowisko działu technicznego (pełne godziny RCP),
    #   'imprezy'    — stanowisko obsługi imprez (reguła nocy imprezowej, wymagania imprez),
    #   NULL         — zwykłe stanowisko.
    # Logika honoruje też STARĄ konwencję nazw jako fallback (np. nazwa zaczyna się od „Sala").
    rola = Column(String(16), nullable=True, index=True)
    # Kwalifikacja dająca dostęp do formularza zamówień (dawniej rozpoznawane po nazwie „Sprzątaczka").
    daje_dostep_zamowien = Column(Boolean, nullable=False, default=False)

    uprawnieni = relationship("Pracownik", secondary=pracownik_stanowisko, back_populates="kwalifikacje")
    przydzialy = relationship("PrzydzialZmiany", back_populates="stanowisko", cascade="all, delete-orphan")
    podkategorie = relationship("Podkategoria", back_populates="stanowisko", cascade="all, delete-orphan")

class Podkategoria(Base):
    __tablename__ = "podkategorie"
    id = Column(Integer, primary_key=True, index=True)
    stanowisko_id = Column(Integer, ForeignKey("stanowiska.id", ondelete="CASCADE"), nullable=False)
    nazwa = Column(String(64), nullable=False) 
    godz_od = Column(Time, nullable=True)     # Zostawiamy tylko godz_od

    stanowisko = relationship("Stanowisko", back_populates="podkategorie")

class WymaganiaDnia(Base):
    __tablename__ = "wymagania_dnia"
    id = Column(Integer, primary_key=True, index=True)
    data = Column(Date, nullable=False)
    stanowisko_id = Column(Integer, ForeignKey("stanowiska.id"), nullable=False)
    godz_od = Column(Time, nullable=True)     
    rewir = Column(String, nullable=True)     
    liczba_osob = Column(Integer, default=1)
    jest_impreza = Column(Boolean, default=False)

class Dyspozycja(Base):
    __tablename__ = "dyspozycje"
    __table_args__ = (UniqueConstraint("pracownik_id", "data"),)
    id           = Column(Integer, primary_key=True, index=True)
    pracownik_id = Column(Integer, ForeignKey("pracownicy.id"), nullable=False)
    data         = Column(Date, nullable=False)
    dostepnosc   = Column(Boolean, nullable=False, default=True)
    godz_od      = Column(Time, nullable=True)
    godz_do      = Column(Time, nullable=True)

    pracownik = relationship("Pracownik", back_populates="dyspozycje")

class PrzydzialZmiany(Base):
    __tablename__ = "przydzialy_zmian"
    __table_args__ = (UniqueConstraint("data", "stanowisko_id", "pracownik_id", "godz_od"),)
    id            = Column(Integer, primary_key=True, index=True)
    data          = Column(Date, nullable=False)
    stanowisko_id = Column(Integer, ForeignKey("stanowiska.id"), nullable=False)
    pracownik_id  = Column(Integer, ForeignKey("pracownicy.id"), nullable=False)
    godz_od       = Column(Time, nullable=True)
    rewir         = Column(String, nullable=True)   # rewir/strefa zmiany (z wymagań lub ręcznie)
    zamyka        = Column(Boolean, nullable=False, default=False)  # ten pracownik zamyka lokal
    zamyka_reczny = Column(Boolean, nullable=False, default=False)  # zamyka ustawione RĘCZNIE (automat nie nadpisuje)
    zamyka_rewir    = Column(Boolean, nullable=False, default=False)  # zamyka SWÓJ rewir (drukuje kasę/terminale rewiru) — Etap D
    rozlicza_imprize = Column(Boolean, nullable=False, default=False)  # ta osoba rozlicza imprezę (fiskalizacja) — Etap D

    stanowisko = relationship("Stanowisko", back_populates="przydzialy")
    pracownik  = relationship("Pracownik",  back_populates="przydzialy")


class OfertaZmiany(Base):
    """Giełda wymiany zmian (roadmapa v1.5). Pracownik wystawia SWÓJ przydział
    (PrzydzialZmiany) do przejęcia; inny wykwalifikowany pracownik go przejmuje;
    admin (manager) akceptuje → przepięcie pracownik_id na przydziale.

    Cykl statusu:
      otwarta   — wystawiona, czeka na chętnego,
      zajeta    — ktoś ją przejął, czeka na decyzję managera,
      zaakceptowana — manager zaakceptował, przydział przepięty (stan końcowy),
      anulowana — wystawiający wycofał ofertę (stan końcowy).
    Odrzucenie przejęcia przez managera cofa ofertę do „otwarta" (nie jest osobnym stanem).
    """
    __tablename__ = "oferty_zmian"
    id              = Column(Integer, primary_key=True, index=True)
    przydzial_id    = Column(Integer, ForeignKey("przydzialy_zmian.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    wystawiajacy_id = Column(Integer, ForeignKey("pracownicy.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    przejmujacy_id  = Column(Integer, ForeignKey("pracownicy.id", ondelete="SET NULL"),
                             nullable=True, index=True)
    status          = Column(String(16), nullable=False, default="otwarta", index=True)
    powod           = Column(String(256), nullable=True)
    utworzono_at    = Column(DateTime, nullable=False)
    zajeto_at       = Column(DateTime, nullable=True)
    rozpatrzono_at  = Column(DateTime, nullable=True)

    przydzial    = relationship("PrzydzialZmiany")
    wystawiajacy = relationship("Pracownik", foreign_keys=[wystawiajacy_id])
    przejmujacy  = relationship("Pracownik", foreign_keys=[przejmujacy_id])

# --- NOWE MODELE ---

class Impreza(Base):
    __tablename__ = "imprezy"
    
    id            = Column(Integer, primary_key=True, index=True)
    data          = Column(Date, index=True, nullable=False)
    klient        = Column(String(128), index=True, nullable=False)
    liczba_osob   = Column(Integer, nullable=True)  # Czytane z komórki H8
    godzina       = Column(String(32), nullable=True) # Czytane z komórki J1
    sala          = Column(String(16), nullable=True) #czytanie z komórki J2
    sciezka_pliku = Column(String, unique=True, nullable=False) # Zabezpiecza przed duplikacją z tego samego pliku Excel

# --- UŻYTKOWNICY / LOGOWANIE ---

class User(Base):
    """Konto logowania. Pracownik (rola=employee) jest powiązany z rekordem
    Pracownik (1:1); administrator (rola=admin) może mieć pracownik_id = NULL."""
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    login        = Column(String(64), unique=True, nullable=False, index=True)  # wewnętrzny identyfikator (denormalizacje, audyt)
    email        = Column(String(255), unique=True, nullable=True, index=True)  # kanał logowania (nowe konta); stare konta mają NULL i logują się po login
    haslo_hash   = Column(String(255), nullable=False)          # bcrypt
    rola         = Column(String(16), nullable=False, default="employee")  # 'admin' | 'employee'
    aktywny      = Column(Boolean, default=True)
    # Tylko odchylenia od domyślnej macierzy roli, np. {"wyplaty.podglad": false}.
    # NULL oznacza brak wyjątków; resolver ignoruje nieznane/stare klucze.
    uprawnienia_override = Column(JSON, nullable=True)
    pracownik_id = Column(
        Integer,
        ForeignKey("pracownicy.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    pracownik = relationship("Pracownik")


class PublikacjaGrafiku(Base):
    """Zapis udostępnienia grafiku na dany tydzień (środa–wtorek)."""
    __tablename__ = "publikacje_grafiku"
    __table_args__ = (UniqueConstraint("start", "koniec"),)
    id              = Column(Integer, primary_key=True, index=True)
    start           = Column(Date, nullable=False)
    koniec          = Column(Date, nullable=False)
    opublikowano_at = Column(DateTime, nullable=False)


class PushSubscription(Base):
    """Subskrypcja Web Push (jedna na urządzenie/przeglądarkę użytkownika)."""
    __tablename__ = "push_subscriptions"
    id       = Column(Integer, primary_key=True, index=True)
    user_id  = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(String, unique=True, nullable=False)
    p256dh   = Column(String, nullable=False)
    auth     = Column(String, nullable=False)


class PushDeviceToken(Base):
    """Token powiadomień NATYWNYCH (aplikacja Capacitor). Web Push/VAPID nie działa w apce
    natywnej — Android idzie przez FCM, iOS przez APNs (pośrednio FCM). Osobny kanał obok
    PushSubscription; wysyłka w push._wyslij_fcm (wymaga konta Firebase operatora)."""
    __tablename__ = "push_device_tokens"
    id       = Column(Integer, primary_key=True, index=True)
    user_id  = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token    = Column(String, unique=True, nullable=False)
    platform = Column(String(16), nullable=True)   # android|ios


class OdbicieRcp(Base):
    """Odbicie z Rejestracji Czasu Pracy (RCP) — KOPIA wypchnięta na VPS przez lokalnego
    agenta. VPS NIGDY nie łączy się z bazą RCP/Gastro; to jest jego własny, lokalny zapis.

    Jeden rekord = jedna zmiana (wejście, opcjonalnie później wyjście). `rcp_id` to stabilny
    identyfikator rekordu w RCP — pozwala bezpiecznie aktualizować (upsert) i nie powiadamiać
    dwa razy o tym samym."""
    __tablename__ = "odbicia_rcp"
    id            = Column(Integer, primary_key=True, index=True)
    rcp_id        = Column(String(128), unique=True, nullable=False, index=True)
    imie_nazwisko = Column(String(128), nullable=False)
    pracownik_id  = Column(Integer, ForeignKey("pracownicy.id", ondelete="SET NULL"), nullable=True, index=True)
    # stabilny id pracownika w POS + źródło (driver) — do trwałego mapowania POS→Lokalo
    # (kreator „Integracja POS"); NULL dla wdrożeń sprzed fazy 2 mapowania.
    pos_pracownik_id = Column(String(64), nullable=True)
    zrodlo        = Column(String(32), nullable=True)
    data          = Column(Date, nullable=False, index=True)
    wejscie       = Column(DateTime, nullable=True)
    wyjscie       = Column(DateTime, nullable=True)
    godziny       = Column(Float, nullable=True)            # liczone z (wyjscie - wejscie)
    powiadomiono_wejscie = Column(Boolean, default=False)   # czy wysłano push „start zmiany"
    powiadomiono_wyjscie = Column(Boolean, default=False)   # czy wysłano push „koniec zmiany"
    zaktualizowano_at    = Column(DateTime, nullable=True)


class StanStolow(Base):
    """Snapshot zajętości stołów (live) z Gastro — wypychany przez lokalnego agenta.
    Jeden wiersz = jeden rewir (po numerze użytkownika Gastro). VPS tylko przechowuje
    ostatni stan; grupowanie na sale/zewnątrz/wynos robi endpoint. NIE dotyka RCP/godzin."""
    __tablename__ = "stan_stolow"
    rewir_nr          = Column(Integer, primary_key=True)   # NGastroUzytkownik.Numer
    otwarte           = Column(Integer, nullable=False, default=0)
    zaktualizowano_at = Column(DateTime, nullable=True)

class StolikiHistoria(Base):
    """Dzienna historia liczby obsłużonych stolików (rachunków) z Gastro — wypychana przez agenta.
    Jeden wiersz = jeden dzień (tylko liczba; bez gości i rewirów). NIE dotyka RCP/godzin."""
    __tablename__ = "stoliki_historia"
    data              = Column(Date, primary_key=True)      # dzień (data otwarcia rachunku)
    liczba            = Column(Integer, nullable=False, default=0)
    zaktualizowano_at = Column(DateTime, nullable=True)


class RozliczenieGastro(Base):
    """Pozycja rozliczenia zmiany kelnera z Gastro (per forma płatności) — wypychana przez
    lokalnego agenta (NGastroZmianaRozliczeniePracownika + Totalizer, tylko odczyt NOLOCK).
    Upsert po poz_id. `sprzedaz` = ile naliczył system, `deklarowane` = ile kelner wpisał
    przy rozliczeniu w POS. `zamkniete` 0→1 = kelner właśnie się rozliczył (trigger pusha
    „Raport gotowy" — dojdzie z formularzami rozliczeń). NIE dotyka RCP — osobna gałąź agenta."""
    __tablename__ = "rozliczenia_gastro"
    poz_id            = Column(String(36), primary_key=True)               # Totalizer.ID
    rozliczenie_id    = Column(String(36), index=True, nullable=False)    # ZmianaRozliczeniePracownika.ID
    imie_nazwisko     = Column(String(128), nullable=False, default="")
    pracownik_id      = Column(Integer, ForeignKey("pracownicy.id"), nullable=True)
    data              = Column(Date, index=True, nullable=False)           # dzień pracy (DataOtwarcia)
    zamknieto         = Column(DateTime, nullable=True)                     # moment rozliczenia w POS
    zamkniete         = Column(Boolean, nullable=False, default=False)
    forma             = Column(String(64), nullable=False, default="")     # GOTÓWKA / KARTA / KARTA_FV…
    sprzedaz          = Column(Float, nullable=False, default=0.0)
    deklarowane       = Column(Float, nullable=False, default=0.0)
    powiadomiono      = Column(Boolean, nullable=False, default=False)     # push „Raport gotowy" (użyjemy przy formularzach)
    zaktualizowano_at = Column(DateTime, nullable=True)


class KpZadatek(Base):
    """Zadatek z Gastro — dokument kasowy KP „Kasa przyjęła" (NGastroKasaDokument, TypOperacji=0),
    wypychany przez agenta (tylko odczyt NOLOCK). Upsert po id (GUID dokumentu). Gotówkowy.
    `opis` to wolny tekst (np. „Zadatek za komunię p.Nowak 15.05.2027") — parsowanie nazwiska/daty
    imprezy i przypisanie do kalendarza imprez to osobny etap; tu trzymamy surowe dane."""
    __tablename__ = "kp_zadatki"
    id                = Column(String(36), primary_key=True)            # NGastroKasaDokument.ID
    numer             = Column(String(64), nullable=True)              # _c_NumerCaly np. „120/2026"
    kwota             = Column(Float, nullable=False, default=0.0)
    opis              = Column(String, nullable=True)
    data              = Column(Date, index=True, nullable=False)        # data wystawienia (przyjęcia)
    nazwisko          = Column(String, nullable=True)                   # sparsowane z opisu
    data_imprezy      = Column(Date, nullable=True)                     # sparsowana data wydarzenia
    termin_id         = Column(Integer, ForeignKey("terminy.id"), nullable=True)   # przypisany termin
    zaktualizowano_at = Column(DateTime, nullable=True)


class Termin(Base):
    """Termin w kalendarzu imprez (ręczny, dodawany przez admina). Zadatek dopasowywany z KP
    (po nazwisku + dacie) lub przypisywany ręcznie ze skrzynki — osobny etap."""
    __tablename__ = "terminy"
    __table_args__ = (
        Index(
            "uq_terminy_source_identity",
            "source_type",
            "source_external_id",
            unique=True,
        ),
        ForeignKeyConstraint(
            ["przydzial_kombinacja_planu_id", "przydzial_wersja_planu_id"],
            ["kombinacje_stolow_planu.id", "kombinacje_stolow_planu.wersja_id"],
            name="fk_terminy_przydzial_kombinacja_wersja",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "przydzial_kombinacja_planu_id IS NULL "
            "OR przydzial_wersja_planu_id IS NOT NULL",
            name="ck_terminy_przydzial_kombinacja_wymaga_wersji",
        ),
        Index("ix_terminy_przydzial_wersja_planu_id", "przydzial_wersja_planu_id"),
        Index(
            "ix_terminy_przydzial_kombinacja_planu_id",
            "przydzial_kombinacja_planu_id",
        ),
    )
    id           = Column(Integer, primary_key=True, index=True)
    data         = Column(Date, nullable=False, index=True)   # data imprezy
    nazwisko     = Column(String, nullable=False)             # klient
    typ          = Column(String(32), nullable=True)          # wesele/komunia/chrzciny/...
    liczba_osob  = Column(Integer, nullable=True)
    telefon      = Column(EncryptedString(512), nullable=True)   # PII gościa — szyfrowane at-rest
    sala         = Column(String(64), nullable=True)
    notatka      = Column(String, nullable=True)
    # Rozszerzony cykl rezerwacji: rezerwacja|potwierdzona|odbyla|no_show|odwolana
    # (3 stare wartości zachowane wstecznie). Przejścia w endpointach /api/rezerwacje.
    status       = Column(String(16), nullable=False, default="rezerwacja")
    zadatek      = Column(Float, nullable=False, default=0.0)  # przypisany zadatek (z KP / ręcznie)
    utworzono_at = Column(DateTime, nullable=True)
    ical_uid     = Column(String, nullable=True, index=True)   # UID wydarzenia z iCloud (.ics) — klucz dedupu importu; NULL dla wpisów ręcznych
    # Stabilna proweniencja importu. Para identyfikuje rekord w systemie źródłowym
    # i umożliwia idempotentny import podczas kontrolowanego cutoveru rezerwacji.
    source_type        = Column(String(32), nullable=True)
    source_external_id = Column(String(512), nullable=True)
    # Portal klienta imprezy (roadmapa v2): sekretny token publicznego linku (/?impreza=TOKEN).
    # NULL = portal nie wygenerowany. Regeneracja unieważnia stary link.
    portal_token = Column(String(64), nullable=True, unique=True, index=True)
    # Portal Pary Młodej (etap 2): oferta menu wybrana przez klienta w portalu.
    menu_oferta_id = Column(Integer, ForeignKey("oferty_menu.id", ondelete="SET NULL"), nullable=True)
    # --- Moduł rezerwacji (stolik/sala/impreza w jednej encji) ---
    godz_od      = Column(Time, nullable=True)   # start rezerwacji (stolik); impreza może mieć NULL
    godz_do      = Column(Time, nullable=True)   # koniec/przewidywany koniec zasiadku
    kanal        = Column(String(16), nullable=False, default="reczna")   # reczna|online|google|ical
    rodzaj       = Column(String(16), nullable=False, default="impreza")  # stolik|sala|impreza
    stolik_id    = Column(Integer, ForeignKey("stoliki.id", ondelete="SET NULL"), nullable=True)
    email        = Column(EncryptedString(512), nullable=True)  # PII gościa — szyfrowane at-rest (potwierdzenia/przypomnienia)
    token_potwierdzenia = Column(String, nullable=True, index=True)  # link gościa (potwierdź/odwołaj) bez logowania
    potwierdzono_at     = Column(DateTime, nullable=True)
    odwolano_at         = Column(DateTime, nullable=True)
    # Kombinacja stołów: stolik_id = wiodący, stoliki_dodatkowe = pozostałe stoły złączki (JSON lista id).
    stoliki_dodatkowe   = Column(JSON, nullable=True)
    auto_przydzielony   = Column(Boolean, nullable=True)   # audyt: stół dobrał silnik sadzania, nie człowiek
    # Niezmienna proweniencja snapshotu użytego przy przydziale. Wersja pozostaje
    # ustawiona także dla pojedynczego stołu; kombinacja tylko dla jawnego zestawu.
    przydzial_wersja_planu_id = Column(
        Integer,
        ForeignKey(
            "wersje_planu_sali.id",
            name="fk_terminy_przydzial_wersja_planu",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    przydzial_kombinacja_planu_id = Column(Integer, nullable=True)
    # --- Faza operacyjna hosta (obok status księgowego): przybyl→posadzony→rachunek→oplacony→wyszedl ---
    faza_hosta      = Column(String(16), nullable=True)    # NULL = jeszcze nie przyszedł
    host_arrived_at = Column(DateTime, nullable=True)
    host_seated_at  = Column(DateTime, nullable=True)      # do timera obrotu na mapie sali
    host_left_at    = Column(DateTime, nullable=True)


class ZamowienieSprzataczki(Base):
    """Zamówienie produktu zgłoszone przez sprzątaczkę (dział techniczny, kwalifikacja Sprzątaczka).
    Obieg statusów: nowe -> odczytane -> zamowione. Push: nowe->admini, odczytane/zamowione->autorka.
    `zdjecie` to opcjonalny data URL (base64, zmniejszone na froncie)."""
    __tablename__ = "zamowienia_sprzataczki"
    id           = Column(Integer, primary_key=True, index=True)
    pracownik_id = Column(Integer, ForeignKey("pracownicy.id"), nullable=False)   # autorka
    utworzono_at = Column(DateTime, nullable=False)
    nazwa        = Column(String(128), nullable=False)
    ilosc        = Column(String(64), nullable=True)      # wolny tekst, np. „2 szt", „5 l"
    notatka      = Column(String, nullable=True)
    zdjecie      = Column(String, nullable=True)          # data URL (base64) — opcjonalne
    status       = Column(String(16), nullable=False, default="nowe")  # nowe | odczytane | zamowione
    odczytano_at = Column(DateTime, nullable=True)
    zamowiono_at = Column(DateTime, nullable=True)


class Urlop(Base):
    """Wniosek urlopowy pracownika OBSŁUGI. Status: oczekuje → zaakceptowany/odrzucony (admin).
    Zaakceptowany urlop blokuje AUTO-przydział w te dni (ręczny wpis nadal możliwy) i jest
    pokazywany w dyspozycjach. Powód opcjonalny."""
    __tablename__ = "urlopy"
    id             = Column(Integer, primary_key=True, index=True)
    pracownik_id   = Column(Integer, ForeignKey("pracownicy.id"), nullable=False)
    start          = Column(Date, nullable=False)
    koniec         = Column(Date, nullable=False)
    powod          = Column(String, nullable=True)
    status         = Column(String(16), nullable=False, default="oczekuje")  # oczekuje|zaakceptowany|odrzucony
    utworzono_at   = Column(DateTime, nullable=False)
    rozpatrzono_at = Column(DateTime, nullable=True)


class RozliczenieDnia(Base):
    """Rozliczenie zmiany (dnia) — sala. Kelnerzy wpisują G/T (+ opcjonalnie KP/KW), zamykający
    terminale/kasy, admin koryguje + zadatek; FV auto z Gastro, IMP auto z imprez. Obieg:
    robocze → u_szefa (po „Przekaż do szefa"). Liczenie 1:1 w rozliczenia.policz_dzien."""
    __tablename__ = "rozliczenia_dnia"
    id                 = Column(Integer, primary_key=True, index=True)
    data               = Column(Date, unique=True, nullable=False, index=True)
    status             = Column(String(16), nullable=False, default="robocze")   # robocze | u_szefa
    zadatek            = Column(Float, nullable=False, default=0.0)               # legacy (nieużywane)
    zadatek_gotowka    = Column(Float, nullable=False, default=0.0)               # zadatek (KP) zdjęty z gotówki
    zadatek_karta      = Column(Float, nullable=False, default=0.0)               # zadatek (KP) zdjęty z karty
    imp_reczny         = Column(Boolean, nullable=False, default=False)           # nadpisanie IMP z palca
    imp_gotowka        = Column(Float, nullable=False, default=0.0)               # IMP gotówka sfisk. (gdy ręcznie)
    imp_karta          = Column(Float, nullable=False, default=0.0)               # IMP karta (gdy ręcznie)
    przelew            = Column(Float, nullable=False, default=0.0)               # przelew dnia (admin z palca, poza kasą)
    terminale          = Column(JSON, nullable=True)   # [{"etykieta","kwota","rewir"}]
    kasy               = Column(JSON, nullable=True)    # [{"etykieta","kwota","rewir"}]
    # Tryb „pula": jeden zbiorczy zestaw G/T/FV/KW dla całej zmiany (bez deklaracji per kelner).
    # W trybie „indywidualnie" pola puli są nieużywane (dane siedzą w RozliczenieKelner).
    pula_gotowka       = Column(Float, nullable=False, default=0.0)
    pula_karta         = Column(Float, nullable=False, default=0.0)
    pula_fv            = Column(Float, nullable=False, default=0.0)
    pula_kw            = Column(Float, nullable=False, default=0.0)
    utworzono_at       = Column(DateTime, nullable=True)
    przekazano_szef_at = Column(DateTime, nullable=True)
    push_admin_at      = Column(DateTime, nullable=True)   # push „raport czeka na zatwierdzenie" (raz)
    kelnerzy = relationship("RozliczenieKelner", cascade="all, delete-orphan", backref="rozliczenie")


class RozliczenieKelner(Base):
    """Wiersz kelnera w rozliczeniu dnia. G/T = zadeklarowane; FV z Gastro; KP z opcją „jako zadatek"."""
    __tablename__ = "rozliczenia_dnia_kelnerzy"
    id             = Column(Integer, primary_key=True, index=True)
    rozliczenie_id = Column(Integer, ForeignKey("rozliczenia_dnia.id", ondelete="CASCADE"), nullable=False)
    pracownik_id   = Column(Integer, ForeignKey("pracownicy.id"), nullable=False)
    gotowka        = Column(Float, nullable=False, default=0.0)
    karta          = Column(Float, nullable=False, default=0.0)
    fv             = Column(Float, nullable=False, default=0.0)
    kp             = Column(Float, nullable=False, default=0.0)
    kp_zadatek     = Column(Boolean, nullable=False, default=False)   # KP przypisane jako zadatek
    kw             = Column(Float, nullable=False, default=0.0)
    potwierdzone   = Column(Boolean, nullable=False, default=False)   # kelner przesłał swój raport
    push_oczekuje_at = Column(DateTime, nullable=True)                # kiedy wysłano push „raport oczekuje"


class RozliczenieImprezy(Base):
    """Rozliczenie imprezy wpisane przez osobę wyznaczoną w grafiku (przydział rozlicza_imprize).
    Jedno na (pracownik, dzień). Pozycje = kwota+forma (gotówka/karta/przelew). Trafia do REJESTRU
    IMPREZ (osobno od raportu sali). Liczy IMP: gotówka sfiskalizowana → minus w kasach,
    karta → minus w terminalach i kasach (przelew wpisuje admin osobno)."""
    __tablename__ = "rozliczenia_imprez"
    id           = Column(Integer, primary_key=True, index=True)
    data         = Column(Date, index=True, nullable=False)
    pracownik_id = Column(Integer, ForeignKey("pracownicy.id"), nullable=False)
    opis         = Column(String, nullable=True)             # sala/klient z rewiru przydziału
    utworzono_at = Column(DateTime, nullable=False)
    pozycje      = relationship("RozliczenieImprezyPozycja", cascade="all, delete-orphan", backref="rozliczenie")


class RozliczenieImprezyPozycja(Base):
    __tablename__ = "rozliczenia_imprez_pozycje"
    id             = Column(Integer, primary_key=True, index=True)
    rozliczenie_id = Column(Integer, ForeignKey("rozliczenia_imprez.id", ondelete="CASCADE"), nullable=False)
    forma          = Column(String(16), nullable=False)      # 'gotowka' | 'karta' | 'przelew'
    kwota          = Column(Float, nullable=False, default=0.0)
    sfiskalizowane = Column(Boolean, nullable=False, default=False)   # dotyczy gotówki


class ZeszytPozycja(Base):
    """Ręczny wpis rozchodu w zeszycie kasowym (admin): TOWAR / KOSZTY / WYPŁATY / INNE.
    Przychód (SALA, imprezy) liczony automatycznie z rozliczeń — tu tylko rozchody."""
    __tablename__ = "zeszyt_pozycje"
    id     = Column(Integer, primary_key=True, index=True)
    data   = Column(Date, nullable=False, index=True)
    kolumna = Column(String(16), nullable=False)   # towar | koszty | wyplaty | inne
    opis   = Column(String, nullable=True)
    kwota  = Column(Float, nullable=False, default=0.0)


class ZeszytPrzychod(Base):
    """Ręczny wiersz przychodu w zeszycie (admin): źródło + gotówka/terminal/przelew/impreza.
    Dla wpływów spoza automatu (SALA z rozliczenia, imprezy) — np. autobus, probostwo, dopłaty."""
    __tablename__ = "zeszyt_przychody"
    id       = Column(Integer, primary_key=True, index=True)
    data     = Column(Date, nullable=False, index=True)
    zrodlo   = Column(String, nullable=True)
    gotowka  = Column(Float, nullable=False, default=0.0)
    terminal = Column(Float, nullable=False, default=0.0)
    przelew  = Column(Float, nullable=False, default=0.0)
    impreza  = Column(Float, nullable=False, default=0.0)


class ZeszytConfig(Base):
    """Singleton (id=1): stan początkowy kasy gotówkowej, od którego liczy się saldo narastająco."""
    __tablename__ = "zeszyt_config"
    id                   = Column(Integer, primary_key=True)
    stan_poczatkowy      = Column(Float, nullable=False, default=0.0)
    stan_poczatkowy_data = Column(Date, nullable=True)


class SprzatanieKorekta(Base):
    """Ręczna korekta grafiku sprzątania (admin): 'dodaj' pozycję spoza reguł albo 'usun'
    wygenerowaną. Przesunięcie = 'usun' na starym dniu + 'dodaj' na nowym. Jedna korekta
    na (dzień, salę); przeciwna akcja kasuje istniejącą = powrót do stanu z automatu."""
    __tablename__ = "sprzatanie_korekty"
    __table_args__ = (UniqueConstraint("data", "sala"),)
    id    = Column(Integer, primary_key=True, index=True)
    data  = Column(Date, nullable=False)
    sala  = Column(String(32), nullable=False)
    akcja = Column(String(8), nullable=False)   # 'dodaj' | 'usun'


class SprzatanieOdhaczenie(Base):
    """„Zrobione" ✓ w grafiku sprzątania — odhaczane przez sprzątaczkę (dzień + sala)."""
    __tablename__ = "sprzatanie_odhaczenia"
    __table_args__ = (UniqueConstraint("data", "sala"),)
    id           = Column(Integer, primary_key=True, index=True)
    data         = Column(Date, nullable=False)
    sala         = Column(String(32), nullable=False)
    pracownik_id = Column(Integer, ForeignKey("pracownicy.id"), nullable=True)
    odhaczono_at = Column(DateTime, nullable=False)


class LokalConfig(Base):
    """Singleton (id=1): konfiguracja lokalu. Zastępuje wartości zaszyte pod jeden lokal
    (branding, początek tygodnia, włączone moduły). Tworzony leniwie z domyślnymi wartościami
    przez get_lokal_config(). Fundament produktyzacji: nowy klient konfiguruje to zamiast
    przerabiać kod."""
    __tablename__ = "lokal_config"
    id                = Column(Integer, primary_key=True)
    # --- Branding (white-label) ---
    nazwa_lokalu      = Column(String(128), nullable=False, default="Lokalo")
    logo_url          = Column(String, nullable=True)
    kolor_primary     = Column(String(16), nullable=True)         # np. '#1f6feb'
    typ_lokalu        = Column(String(48), nullable=True)         # id typu z kreatora (np. 'pizzeria', 'dom-weselny')
    # --- Parametry grafiku ---
    # Dzień rozpoczęcia tygodnia grafiku: 0=poniedziałek … 6=niedziela. Domyślnie środa (2).
    poczatek_tygodnia = Column(Integer, nullable=False, default=2)
    # --- Włączone moduły (feature flags per lokal) ---
    modul_rozliczenia = Column(Boolean, nullable=False, default=True)   # rozliczenia kasowe (sala)
    modul_imprezy     = Column(Boolean, nullable=False, default=True)   # imprezy/wesela, zadatki
    modul_pos         = Column(Boolean, nullable=False, default=True)   # integracja POS/RCP (agent)
    modul_sprzatanie  = Column(Boolean, nullable=False, default=True)   # grafik sprzątania
    modul_rezerwacje  = Column(Boolean, nullable=False, default=True)   # rezerwacje stolików/terminów
    # --- Rezerwacje online (publiczny widget) ---
    rezerwacje_online             = Column(Boolean, nullable=False, default=False)  # gość rezerwuje bez logowania
    rezerwacje_auto_potwierdzenie = Column(Boolean, nullable=False, default=False)  # online od razu 'potwierdzona'
    # --- Polityka rezerwacji (v2). Defaulty = polityka wyłączona (zachowanie historyczne). ---
    rez_okno_wyprzedzenia_dni = Column(Integer, nullable=False, default=0)   # max dni w przód (0 = bez limitu)
    rez_cutoff_min            = Column(Integer, nullable=False, default=0)   # min. minut przed slotem (0 = wyłączone)
    rez_min_grupa_online      = Column(Integer, nullable=False, default=1)   # min. wielkość grupy online
    rez_max_grupa_online      = Column(Integer, nullable=False, default=0)   # max grupa online (0 = bez limitu)
    rez_bufor_min             = Column(Integer, nullable=False, default=0)   # bufor sprzątania między rezerwacjami
    rez_anulacja_do_h         = Column(Integer, nullable=False, default=0)   # anulacja online do X h przed (0 = zawsze)
    rez_no_show_po_min        = Column(Integer, nullable=False, default=0)   # auto-no-show po X min od godz_od (0 = off)
    # --- Zadatki + no-show fee (za flagą; realne pobieranie czeka na bramkę operatora → do tego sandbox) ---
    zadatek_wymagany   = Column(Boolean, nullable=False, default=False)  # wymagaj zadatku przy rezerwacji online
    zadatek_kwota_os   = Column(Float, nullable=False, default=0.0)      # kwota zadatku na osobę (0 = brak)
    zadatek_prog_osob  = Column(Integer, nullable=False, default=0)      # zadatek dopiero od tylu osób (0 = zawsze gdy wymagany)
    no_show_fee        = Column(Float, nullable=False, default=0.0)      # opłata za no-show (0 = brak)
    # --- Konta zespołu ---
    # False (domyślnie) = publiczna samodzielna rejestracja pracownika WYŁĄCZONA:
    # konto zakłada się wyłącznie z linku-zaproszenia wygenerowanego przez managera.
    rejestracja_otwarta = Column(Boolean, nullable=False, default=False)
    # --- Parametry obsady imprez (dawniej zaszyte pod jeden lokal; domyślne = zachowanie historyczne) ---
    impreza_osoby_na_obsluge = Column(Integer, nullable=False, default=15)             # 1 pracownik na tylu gości
    impreza_wyprzedzenie_min = Column(Integer, nullable=False, default=120)            # obsługa startuje tyle min przed
    impreza_najwczesniej     = Column(String(5), nullable=False, default="10:00")      # nie wcześniej niż
    impreza_sale_min2        = Column(String(128), nullable=False, default="")  # sale z min. 2 obsady (po przecinku; puste = brak, parametryzowane per lokal)
    # --- Prognoza obsady (sugerowana liczba osób na zmianę wg prognozowanego ruchu) ---
    obsada_rachunki_na_osobe = Column(Integer, nullable=False, default=20)  # ilu rachunków „obsługuje" 1 osoba
    obsada_min               = Column(Integer, nullable=False, default=1)   # minimalna obsada na zmianę
    # --- Strażnik prawa pracy (limity przy ręcznym przydziale zmian; 0 = limit wyłączony) ---
    praca_min_odpoczynek_h = Column(Integer, nullable=False, default=11)  # min. godzin przerwy między zmianami (KP art. 132)
    praca_max_dni_tydzien  = Column(Integer, nullable=False, default=6)   # maks. dni pracy w tygodniu (KP: 1 dzień wolny)
    praca_max_dni_miesiac  = Column(Integer, nullable=False, default=22)  # maks. dni pracy w miesiącu kalendarzowym
    # --- Profil rozliczeń i imprez (de-Rajculizacja; defaulty = zachowanie historyczne) ---
    # True = imprezy rozliczane OSOBNO (IMP odejmowany z kas, osobne wiersze w zeszycie, kafelek na
    # pulpicie). False = lokal nie wyodrębnia imprez — sprzedaż imprezowa siedzi w zwykłym obrocie.
    impreza_osobne_rozliczenie = Column(Boolean, nullable=False, default=True)
    # 'indywidualnie' = każdy kelner deklaruje swoje G/T (wiersz per osoba);
    # 'pula' = wspólna pula sali (bez deklaracji per kelner) — silnik w przygotowaniu.
    rozliczenia_tryb_kelnera   = Column(String(16), nullable=False, default="indywidualnie")
    # Predefiniowane etykiety kas/terminali w Rozliczeniu dnia (listy stringów).
    # NULL = wolny wpis (zachowanie historyczne — admin wpisuje etykiety ręcznie).
    rozliczenia_nazwy_kas       = Column(JSON, nullable=True)
    rozliczenia_nazwy_terminali = Column(JSON, nullable=True)
    # --- Cykl grafiku: 'tydzien' (domyślnie) | 'miesiac' (silnik w przygotowaniu) ---
    grafik_cykl = Column(String(16), nullable=False, default="tydzien")
    # --- Dane firmowe lokalu jako NABYWCY faktur za subskrypcję (KSeF/FA(3)) ---
    faktura_nip       = Column(String(16), nullable=True)
    faktura_nazwa     = Column(String(256), nullable=True)   # pełna nazwa firmy (może różnić się od nazwa_lokalu)
    faktura_adres_l1  = Column(String(256), nullable=True)   # ulica i numer
    faktura_adres_l2  = Column(String(256), nullable=True)   # kod pocztowy + miejscowość
    # --- Token agenta POS (kreator „Podłącz POS"): hash SHA-256, plaintext widzi tylko
    #     admin przy generowaniu; NULL = brak tokenu (zostaje env RCP_INGEST_TOKEN) ---
    pos_token_hash = Column(String(64), nullable=True)
    pos_token_od   = Column(DateTime, nullable=True)
    # --- Struktura lokalu (dawniej stałe zaszyte pod jeden lokal; NULL = wartości legacy) ---
    sale                       = Column(JSON, nullable=True)   # NULL = sale historyczne (sprzatanie.SALE)
    sprzatanie_sale_codziennie = Column(JSON, nullable=True)   # NULL = ("Parter (R1)","Góra (R1)")
    # NULL = legacy "Zielona"; pusty string = reguła niedzieli WYŁĄCZONA
    sprzatanie_sala_niedziela  = Column(String(32), nullable=True)
    imprezy_mapa_sal           = Column(JSON, nullable=True)   # kod z pliku imprezy → sala; NULL = mapa legacy
    zeszyt_kolumny             = Column(JSON, nullable=True)   # NULL = ["towar","koszty","wyplaty","inne"]
    pos_mapa_rewirow           = Column(JSON, nullable=True)   # NULL = stałe STOLY_* (main.py); patrz docs/POS-INTEGRACJA.md


class SalaRezerwacyjna(Base):
    """Pierwszoklasowa sala modułu rezerwacji."""
    __tablename__ = "sale_rezerwacyjne"
    __table_args__ = (
        UniqueConstraint("nazwa", name="uq_sale_rezerwacyjne_nazwa"),
        Index(
            "uq_sale_rezerwacyjne_nazwa_klucz",
            "nazwa_klucz",
            unique=True,
        ),
        CheckConstraint("length(trim(nazwa)) > 0", name="ck_sale_rezerwacyjne_nazwa"),
        CheckConstraint("kolejnosc >= 0", name="ck_sale_rezerwacyjne_kolejnosc"),
        CheckConstraint("priorytet >= 0", name="ck_sale_rezerwacyjne_priorytet"),
        CheckConstraint(
            "limit_jednoczesnych_rez IS NULL OR limit_jednoczesnych_rez >= 0",
            name="ck_sale_rezerwacyjne_limit_jednoczesnych_rez",
        ),
        CheckConstraint(
            "limit_jednoczesnych_osob IS NULL OR limit_jednoczesnych_osob >= 0",
            name="ck_sale_rezerwacyjne_limit_jednoczesnych_osob",
        ),
        CheckConstraint(
            "domyslny_bufor_min IS NULL OR domyslny_bufor_min >= 0",
            name="ck_sale_rezerwacyjne_domyslny_bufor_min",
        ),
        CheckConstraint(
            "strategia_zapelniania IN ('preferuj', 'wypelniaj_kolejno')",
            name="ck_sale_rezerwacyjne_strategia_zapelniania",
        ),
    )
    id        = Column(Integer, primary_key=True, index=True)
    # Legacy Stolik.strefa ma 32 znaki i pozostaje projekcją nazwy sali.
    nazwa     = Column(String(32), nullable=False)
    nazwa_klucz = Column(String(128), nullable=False)
    aktywna   = Column(Boolean, nullable=False, default=True)
    kolejnosc = Column(Integer, nullable=False, default=0)
    strategia_zapelniania = Column(
        String(24), nullable=False, default="preferuj", server_default="preferuj",
    )
    priorytet = Column(Integer, nullable=False, default=0, server_default="0")
    online_aktywna = Column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )
    wewnetrzna_aktywna = Column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )
    limit_jednoczesnych_rez = Column(Integer, nullable=True)
    limit_jednoczesnych_osob = Column(Integer, nullable=True)
    domyslny_bufor_min = Column(Integer, nullable=True)

    stoliki = relationship("Stolik", back_populates="sala")
    plany = relationship("PlanSali", back_populates="sala", cascade="all, delete-orphan")


class PlanSali(Base):
    """Kontener historii wersji układu jednej sali."""
    __tablename__ = "plany_sali"
    __table_args__ = (
        UniqueConstraint("sala_id", name="uq_plany_sali_sala"),
        CheckConstraint("length(trim(nazwa)) > 0", name="ck_plany_sali_nazwa"),
    )
    id      = Column(Integer, primary_key=True, index=True)
    sala_id = Column(
        Integer, ForeignKey("sale_rezerwacyjne.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    nazwa   = Column(String(64), nullable=False)

    sala = relationship("SalaRezerwacyjna", back_populates="plany")
    wersje = relationship(
        "WersjaPlanuSali", back_populates="plan", cascade="all, delete-orphan",
        order_by="WersjaPlanuSali.numer",
    )


class WersjaPlanuSali(Base):
    """Wersja robocza lub opublikowany, historyczny snapshot planu."""
    __tablename__ = "wersje_planu_sali"
    __table_args__ = (
        UniqueConstraint("plan_id", "numer", name="uq_wersje_planu_sali_plan_numer"),
        CheckConstraint("numer >= 1", name="ck_wersje_planu_sali_numer"),
        CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_wersje_planu_sali_status",
        ),
        CheckConstraint("rewizja >= 0", name="ck_wersje_planu_sali_rewizja"),
        CheckConstraint(
            "(status = 'draft' AND opublikowano_at IS NULL AND opublikowal_id IS NULL) OR "
            "(status = 'published' AND opublikowano_at IS NOT NULL) OR status = 'retired'",
            name="ck_wersje_planu_sali_publikacja",
        ),
        CheckConstraint(
            "zaktualizowano_at >= utworzono_at",
            name="ck_wersje_planu_sali_czas_aktualizacji",
        ),
        CheckConstraint(
            "opublikowano_at IS NULL OR opublikowano_at >= utworzono_at",
            name="ck_wersje_planu_sali_czas_publikacji",
        ),
        Index("ix_wersje_planu_sali_plan_status", "plan_id", "status"),
        Index(
            "uq_wersje_planu_sali_jeden_draft", "plan_id", unique=True,
            sqlite_where=text("status = 'draft'"),
            postgresql_where=text("status = 'draft'"),
        ),
        Index(
            "uq_wersje_planu_sali_jeden_published", "plan_id", unique=True,
            sqlite_where=text("status = 'published'"),
            postgresql_where=text("status = 'published'"),
        ),
    )
    id                = Column(Integer, primary_key=True, index=True)
    plan_id           = Column(
        Integer, ForeignKey("plany_sali.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    numer             = Column(Integer, nullable=False)
    status            = Column(String(16), nullable=False, default="draft")
    rewizja           = Column(Integer, nullable=False, default=0)
    autor_id          = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    opublikowal_id    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    utworzono_at      = Column(DateTime, nullable=False)
    zaktualizowano_at = Column(DateTime, nullable=False)
    opublikowano_at   = Column(DateTime, nullable=True)

    plan = relationship("PlanSali", back_populates="wersje")
    pozycje = relationship(
        "PozycjaStolikaPlanu", back_populates="wersja", cascade="all, delete-orphan",
    )
    krawedzie = relationship(
        "KrawedzSasiedztwaPlanu",
        back_populates="wersja",
        cascade="all, delete-orphan",
        order_by="KrawedzSasiedztwaPlanu.id",
        foreign_keys="KrawedzSasiedztwaPlanu.wersja_id",
    )
    kombinacje = relationship(
        "KombinacjaStolowPlanu",
        back_populates="wersja",
        cascade="all, delete-orphan",
        order_by="KombinacjaStolowPlanu.id",
        foreign_keys="KombinacjaStolowPlanu.wersja_id",
    )


class PozycjaStolikaPlanu(Base):
    """Geometria i widoczność stabilnego stolika w konkretnej wersji planu."""
    __tablename__ = "pozycje_stolikow_planu"
    __table_args__ = (
        UniqueConstraint(
            "wersja_id", "stolik_id", name="uq_pozycje_stolikow_wersja_stolik",
        ),
        CheckConstraint("plan_x >= 0 AND plan_x <= 100", name="ck_pozycje_stolikow_plan_x"),
        CheckConstraint("plan_y >= 0 AND plan_y <= 100", name="ck_pozycje_stolikow_plan_y"),
        CheckConstraint(
            "szerokosc >= 1 AND szerokosc <= 100", name="ck_pozycje_stolikow_szerokosc",
        ),
        CheckConstraint(
            "wysokosc >= 1 AND wysokosc <= 100", name="ck_pozycje_stolikow_wysokosc",
        ),
        CheckConstraint("obrot >= 0 AND obrot < 360", name="ck_pozycje_stolikow_obrot"),
        CheckConstraint(
            "kolejnosc IS NULL OR kolejnosc >= 0",
            name="ck_pozycje_stolikow_kolejnosc",
        ),
        CheckConstraint(
            "pojemnosc IS NULL OR pojemnosc >= 1",
            name="ck_pozycje_stolikow_pojemnosc",
        ),
        CheckConstraint(
            "pojemnosc_min IS NULL OR pojemnosc_min >= 1",
            name="ck_pozycje_stolikow_pojemnosc_min",
        ),
        CheckConstraint(
            "pojemnosc IS NULL OR pojemnosc_min IS NULL OR pojemnosc_min <= pojemnosc",
            name="ck_pozycje_stolikow_zakres_pojemnosci",
        ),
        Index("ix_pozycje_stolikow_planu_wersja_id", "wersja_id"),
        Index("ix_pozycje_stolikow_planu_stolik_id", "stolik_id"),
    )
    id               = Column(Integer, primary_key=True, index=True)
    wersja_id        = Column(
        Integer, ForeignKey("wersje_planu_sali.id", ondelete="CASCADE"),
        nullable=False,
    )
    stolik_id        = Column(
        Integer, ForeignKey("stoliki.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_x           = Column(Integer, nullable=False)
    plan_y           = Column(Integer, nullable=False)
    szerokosc        = Column(Integer, nullable=False, default=12)
    wysokosc         = Column(Integer, nullable=False, default=12)
    obrot            = Column(Integer, nullable=False, default=0)
    aktywny_w_planie = Column(Boolean, nullable=False, default=True)
    # WĹ‚aĹ›ciwoĹ›ci operacyjne sÄ… czÄ™Ĺ›ciÄ… snapshotu. NULL pozostaje wyĹ‚Ä…cznie
    # kompatybilnym znacznikiem starszego klienta/rekordu i przy odczycie dziedziczy
    # wartoĹ›Ä‡ z poprzedniego snapshotu lub stabilnego rekordu ``Stolik``.
    nazwa            = Column(String(32), nullable=True)
    kolejnosc        = Column(Integer, nullable=True)
    pojemnosc        = Column(Integer, nullable=True)
    pojemnosc_min    = Column(Integer, nullable=True)
    ksztalt          = Column(String(16), nullable=True)
    cechy            = Column(JSON, nullable=True)
    priorytet        = Column(Integer, nullable=True)
    sekcja           = Column(String(32), nullable=True)

    wersja = relationship("WersjaPlanuSali", back_populates="pozycje")
    stolik = relationship("Stolik")


class KrawedzSasiedztwaPlanu(Base):
    """Nieskierowana, wersjonowana krawÄ™dĹş fizycznego sÄ…siedztwa stolikĂłw."""
    __tablename__ = "krawedzie_sasiedztwa_planu"
    __table_args__ = (
        CheckConstraint(
            "stolik_a_id < stolik_b_id",
            name="ck_krawedzie_sasiedztwa_planu_kolejnosc",
        ),
        UniqueConstraint(
            "wersja_id", "stolik_a_id", "stolik_b_id",
            name="uq_krawedzie_sasiedztwa_planu_para",
        ),
        ForeignKeyConstraint(
            ["wersja_id", "stolik_a_id"],
            ["pozycje_stolikow_planu.wersja_id", "pozycje_stolikow_planu.stolik_id"],
            name="fk_krawedzie_sasiedztwa_planu_stolik_a",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["wersja_id", "stolik_b_id"],
            ["pozycje_stolikow_planu.wersja_id", "pozycje_stolikow_planu.stolik_id"],
            name="fk_krawedzie_sasiedztwa_planu_stolik_b",
            ondelete="CASCADE",
        ),
        Index("ix_krawedzie_sasiedztwa_planu_wersja_id", "wersja_id"),
    )
    id          = Column(Integer, primary_key=True, index=True)
    wersja_id   = Column(
        Integer, ForeignKey("wersje_planu_sali.id", ondelete="CASCADE"), nullable=False,
    )
    stolik_a_id = Column(Integer, nullable=False)
    stolik_b_id = Column(Integer, nullable=False)

    wersja = relationship(
        "WersjaPlanuSali", back_populates="krawedzie", foreign_keys=[wersja_id],
    )


class KombinacjaStolowPlanu(Base):
    """Jawna kombinacja stoĹ‚Ăłw zatwierdzana razem z wersjÄ… planu."""
    __tablename__ = "kombinacje_stolow_planu"
    __table_args__ = (
        UniqueConstraint(
            "wersja_id", "sklad_klucz",
            name="uq_kombinacje_stolow_planu_wersja_sklad",
        ),
        # Potrzebne dla kompozytowego FK skĹ‚adnika, ktĂłry pilnuje zgodnoĹ›ci wersji.
        UniqueConstraint(
            "id", "wersja_id",
            name="uq_kombinacje_stolow_planu_id_wersja",
        ),
        CheckConstraint(
            "length(trim(nazwa)) > 0",
            name="ck_kombinacje_stolow_planu_nazwa",
        ),
        CheckConstraint(
            "length(sklad_klucz) > 0",
            name="ck_kombinacje_stolow_planu_sklad",
        ),
        CheckConstraint(
            "pojemnosc_min >= 1 AND pojemnosc_max >= pojemnosc_min",
            name="ck_kombinacje_stolow_planu_pojemnosc",
        ),
        CheckConstraint(
            "kanal IN ('online', 'wewnetrzna', 'oba')",
            name="ck_kombinacje_stolow_planu_kanal",
        ),
        Index("ix_kombinacje_stolow_planu_wersja_id", "wersja_id"),
    )
    id                 = Column(Integer, primary_key=True, index=True)
    wersja_id          = Column(
        Integer, ForeignKey("wersje_planu_sali.id", ondelete="CASCADE"), nullable=False,
    )
    nazwa              = Column(String(64), nullable=False)
    sklad_klucz        = Column(String(512), nullable=False)
    pojemnosc_min      = Column(Integer, nullable=False, default=1)
    pojemnosc_max      = Column(Integer, nullable=False)
    priorytet          = Column(Integer, nullable=False, default=0)
    kanal              = Column(String(16), nullable=False, default="oba")
    aktywna_w_planie   = Column(Boolean, nullable=False, default=True)

    wersja = relationship(
        "WersjaPlanuSali", back_populates="kombinacje", foreign_keys=[wersja_id],
    )
    skladniki = relationship(
        "SkladnikKombinacjiPlanu",
        back_populates="kombinacja",
        cascade="all, delete-orphan",
        order_by="SkladnikKombinacjiPlanu.stolik_id",
        foreign_keys=(
            "[SkladnikKombinacjiPlanu.kombinacja_id, "
            "SkladnikKombinacjiPlanu.wersja_id]"
        ),
    )


class SkladnikKombinacjiPlanu(Base):
    """Relacyjny skĹ‚ad kombinacji, bez JSON-owych i osieroconych identyfikatorĂłw."""
    __tablename__ = "skladniki_kombinacji_planu"
    __table_args__ = (
        UniqueConstraint(
            "kombinacja_id", "stolik_id",
            name="uq_skladniki_kombinacji_planu_stolik",
        ),
        ForeignKeyConstraint(
            ["kombinacja_id", "wersja_id"],
            ["kombinacje_stolow_planu.id", "kombinacje_stolow_planu.wersja_id"],
            name="fk_skladniki_kombinacji_planu_kombinacja",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["wersja_id", "stolik_id"],
            ["pozycje_stolikow_planu.wersja_id", "pozycje_stolikow_planu.stolik_id"],
            name="fk_skladniki_kombinacji_planu_stolik",
            ondelete="CASCADE",
        ),
        Index("ix_skladniki_kombinacji_planu_kombinacja_id", "kombinacja_id"),
        Index("ix_skladniki_kombinacji_planu_wersja_id", "wersja_id"),
        Index("ix_skladniki_kombinacji_planu_stolik_id", "stolik_id"),
    )
    id             = Column(Integer, primary_key=True, index=True)
    kombinacja_id  = Column(Integer, nullable=False)
    wersja_id      = Column(Integer, nullable=False)
    stolik_id      = Column(Integer, nullable=False)

    kombinacja = relationship(
        "KombinacjaStolowPlanu",
        back_populates="skladniki",
        foreign_keys=[kombinacja_id, wersja_id],
    )


class Stolik(Base):
    """Stolik/zasób do rezerwacji (moduł rezerwacji). Strefa = sala/ogród (string, mapuje na
    Termin.sala). Pojemność kontroluje walidację rezerwacji."""
    __tablename__ = "stoliki"
    id        = Column(Integer, primary_key=True, index=True)
    nazwa     = Column(String(32), nullable=False)            # np. „S1", „Loża 3"
    strefa    = Column(String(32), nullable=True)             # sala/ogród/antresola
    sala_id   = Column(
        Integer, ForeignKey("sale_rezerwacyjne.id"),
        nullable=True, index=True,
    )
    pojemnosc = Column(Integer, nullable=False, default=2)
    laczy_sie = Column(Boolean, nullable=False, default=False)  # czy można łączyć (later)
    aktywny   = Column(Boolean, nullable=False, default=True)
    kolejnosc = Column(Integer, nullable=False, default=0)
    # --- Plan sali (wizualne rozmieszczenie): pozycja w % kontenera (0–100), NULL = auto-siatka ---
    plan_x    = Column(Integer, nullable=True)
    plan_y    = Column(Integer, nullable=True)
    # Powiązanie z rewirem POS (StanStolow.rewir_nr) — live obłożenie z Gastro. NULL = brak podpięcia.
    rewir_nr  = Column(Integer, nullable=True)
    # --- Rozszerzenia pod silnik sadzania (Slice 2) ---
    pojemnosc_min = Column(Integer, nullable=True)     # min. sensowna wielkość grupy; NULL = 1
    ksztalt       = Column(String(16), nullable=True)  # kwadrat/okragly/prostokat (render planu)
    cechy         = Column(JSON, nullable=True)        # ["okno","loza","ogrod","dostepny"]
    priorytet     = Column(Integer, nullable=True)     # kolejność sadzania (mniej = wcześniej); NULL = 0
    sekcja        = Column(String(32), nullable=True)  # sekcja kelnerska (do balansu); NULL = fallback do strefy
    sala = relationship("SalaRezerwacyjna", back_populates="stoliki")


class KombinacjaStolow(Base):
    """Predefiniowana kombinacja stołów do łączenia pod większe grupy (np. S1+S2 = 6 os.).
    Host jawnie definiuje, które stoły wolno łączyć — silnik sadzania buduje z tego kandydatów
    dla dużych grup. `stoliki` = lista id stołów składowych (JSON)."""
    __tablename__ = "kombinacje_stolow"
    id            = Column(Integer, primary_key=True, index=True)
    nazwa         = Column(String(64), nullable=False)          # np. „S1+S2"
    stoliki       = Column(JSON, nullable=False)                # [id_stolika, …] (≥2)
    pojemnosc_min = Column(Integer, nullable=True)              # min. grupa dla kombinacji; NULL = 1
    pojemnosc_max = Column(Integer, nullable=False, default=0)  # suma pojemności składowych (lub override)
    aktywna       = Column(Boolean, nullable=False, default=True)
    priorytet     = Column(Integer, nullable=False, default=0)  # kolejność preferencji (mniej = wcześniej)


class SasiedztwoStolow(Base):
    """Krawędź grafu sąsiedztwa (które stoły fizycznie da się złączyć). Nieskierowana —
    normalizowana stolik_a < stolik_b. Silnik sadzania auto-generuje z niej kombinacje dla dużych grup."""
    __tablename__ = "sasiedztwo_stolow"
    id       = Column(Integer, primary_key=True, index=True)
    stolik_a = Column(Integer, ForeignKey("stoliki.id", ondelete="CASCADE"), nullable=False)
    stolik_b = Column(Integer, ForeignKey("stoliki.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("stolik_a", "stolik_b", name="uq_sasiedztwo_para"),)


class GodzinyOtwarcia(Base):
    """Serwis rezerwacyjny (okno przyjęć) per dzień tygodnia — kilka wierszy na dzień = lunch/kolacja.
    Historycznie „godziny otwarcia"; rozszerzone o turn-time zależny od grupy i pacing (limit coverów)."""
    __tablename__ = "godziny_otwarcia"
    __table_args__ = (
        CheckConstraint(
            "krok_slotu_min >= 1 AND krok_slotu_min <= 1440",
            name="ck_godziny_otwarcia_krok_slotu_min",
        ),
        CheckConstraint(
            "domyslny_turn_time_min >= 1 AND domyslny_turn_time_min <= 1439",
            name="ck_godziny_otwarcia_domyslny_turn_time_min",
        ),
        CheckConstraint(
            "max_jednoczesnych_rez IS NULL OR max_jednoczesnych_rez >= 0",
            name="ck_godziny_otwarcia_max_jednoczesnych_rez",
        ),
        CheckConstraint(
            "max_jednoczesnych_osob IS NULL OR max_jednoczesnych_osob >= 0",
            name="ck_godziny_otwarcia_max_jednoczesnych_osob",
        ),
        CheckConstraint(
            "duza_grupa_od IS NULL OR duza_grupa_od > 0",
            name="ck_godziny_otwarcia_duza_grupa_od",
        ),
        CheckConstraint(
            "duza_grupa_tryb IS NULL OR duza_grupa_tryb IN "
            "('online', 'do_zatwierdzenia', 'telefon')",
            name="ck_godziny_otwarcia_duza_grupa_tryb",
        ),
        CheckConstraint(
            "(duza_grupa_od IS NULL AND duza_grupa_tryb IS NULL) OR "
            "(duza_grupa_od IS NOT NULL AND duza_grupa_tryb IS NOT NULL)",
            name="ck_godziny_otwarcia_duza_grupa_spojnosc",
        ),
    )
    id                = Column(Integer, primary_key=True, index=True)
    dzien_tygodnia    = Column(Integer, nullable=False)        # 0=poniedziałek … 6=niedziela
    godz_od           = Column(Time, nullable=False)
    godz_do           = Column(Time, nullable=False)
    ostatni_zasiadek  = Column(Time, nullable=True)            # ostatnia możliwa godzina rezerwacji
    dlugosc_slotu_min = Column(Integer, nullable=False, default=120)   # krok siatki + bazowy turn-time
    # R3 rozdziela częstotliwość oferowanych terminów od czasu zajęcia zasobu.
    # ``dlugosc_slotu_min`` pozostaje adapterem kompatybilności przez okres migracyjny.
    krok_slotu_min = Column(
        Integer, nullable=False, default=120, server_default="120",
    )
    domyslny_turn_time_min = Column(
        Integer, nullable=False, default=120, server_default="120",
    )
    aktywny           = Column(Boolean, nullable=False, default=True)
    nazwa             = Column(String(32), nullable=True)      # etykieta serwisu: „Lunch"/„Kolacja" (NULL = jeden serwis dnia)
    # Turn-time zależny od wielkości grupy: [{"do_osob":2,"min":90},{"do_osob":6,"min":120}] rosnąco.
    # NULL → używamy dlugosc_slotu_min (zachowanie historyczne).
    turn_time_progi   = Column(JSON, nullable=True)
    # Pacing: limit rezerwacji/osób startujących w oknie pacing_okno_min (NULL = bez limitu / krok slotu).
    pacing_max_rez    = Column(Integer, nullable=True)
    pacing_max_osob   = Column(Integer, nullable=True)
    pacing_okno_min   = Column(Integer, nullable=True)
    max_jednoczesnych_rez = Column(Integer, nullable=True)
    max_jednoczesnych_osob = Column(Integer, nullable=True)
    duza_grupa_od = Column(Integer, nullable=True)
    duza_grupa_tryb = Column(String(24), nullable=True)


class WyjatekKalendarza(Base):
    """Nadpisanie parametrów rezerwacji na konkretny dzień: blackout (zamknięte) lub godziny
    specjalne (inne okno/slot). Ma pierwszeństwo nad GodzinyOtwarcia w _serwisy_dnia."""
    __tablename__ = "wyjatki_kalendarza"
    __table_args__ = (
        CheckConstraint(
            "krok_slotu_min IS NULL OR "
            "(krok_slotu_min >= 1 AND krok_slotu_min <= 1440)",
            name="ck_wyjatki_kalendarza_krok_slotu_min",
        ),
        CheckConstraint(
            "domyslny_turn_time_min IS NULL OR "
            "(domyslny_turn_time_min >= 1 AND domyslny_turn_time_min <= 1439)",
            name="ck_wyjatki_kalendarza_domyslny_turn_time_min",
        ),
    )
    id                = Column(Integer, primary_key=True, index=True)
    data              = Column(Date, nullable=False, index=True)
    typ               = Column(String(16), nullable=False)      # blackout | godziny_specjalne
    godz_od           = Column(Time, nullable=True)             # dla godziny_specjalne
    godz_do           = Column(Time, nullable=True)
    ostatni_zasiadek  = Column(Time, nullable=True)
    dlugosc_slotu_min = Column(Integer, nullable=True)
    krok_slotu_min    = Column(Integer, nullable=True)
    domyslny_turn_time_min = Column(Integer, nullable=True)
    nazwa             = Column(String(64), nullable=True)       # np. „Sylwester", „Wielkanoc"


class RegulaDostepnosciRezerwacji(Base):
    """Typowane, dziedziczone nadpisanie reguł R3 dla serwisu, sali i kanału."""
    __tablename__ = "reguly_dostepnosci_rezerwacji"
    __table_args__ = (
        CheckConstraint(
            "kanal IN ('oba', 'online', 'wewnetrzna')",
            name="ck_reguly_dostepnosci_kanal",
        ),
        CheckConstraint(
            "pacing_okno_min IS NULL OR pacing_okno_min > 0",
            name="ck_reguly_dostepnosci_pacing_okno_min",
        ),
        CheckConstraint(
            "pacing_max_rez IS NULL OR pacing_max_rez >= 0",
            name="ck_reguly_dostepnosci_pacing_max_rez",
        ),
        CheckConstraint(
            "pacing_max_osob IS NULL OR pacing_max_osob >= 0",
            name="ck_reguly_dostepnosci_pacing_max_osob",
        ),
        CheckConstraint(
            "max_jednoczesnych_rez IS NULL OR max_jednoczesnych_rez >= 0",
            name="ck_reguly_dostepnosci_max_jednoczesnych_rez",
        ),
        CheckConstraint(
            "max_jednoczesnych_osob IS NULL OR max_jednoczesnych_osob >= 0",
            name="ck_reguly_dostepnosci_max_jednoczesnych_osob",
        ),
        CheckConstraint(
            "bufor_min IS NULL OR bufor_min >= 0",
            name="ck_reguly_dostepnosci_bufor_min",
        ),
        CheckConstraint(
            "okno_wyprzedzenia_dni IS NULL OR okno_wyprzedzenia_dni >= 0",
            name="ck_reguly_dostepnosci_okno_wyprzedzenia_dni",
        ),
        CheckConstraint(
            "cutoff_min IS NULL OR cutoff_min >= 0",
            name="ck_reguly_dostepnosci_cutoff_min",
        ),
        CheckConstraint(
            "min_grupa IS NULL OR min_grupa > 0",
            name="ck_reguly_dostepnosci_min_grupa",
        ),
        CheckConstraint(
            "max_grupa IS NULL OR max_grupa >= 0",
            name="ck_reguly_dostepnosci_max_grupa",
        ),
        CheckConstraint(
            "min_grupa IS NULL OR max_grupa IS NULL OR max_grupa = 0 "
            "OR max_grupa >= min_grupa",
            name="ck_reguly_dostepnosci_zakres_grupy",
        ),
        CheckConstraint(
            "duza_grupa_od IS NULL OR duza_grupa_od > 0",
            name="ck_reguly_dostepnosci_duza_grupa_od",
        ),
        CheckConstraint(
            "duza_grupa_tryb IS NULL OR duza_grupa_tryb IN "
            "('online', 'do_zatwierdzenia', 'telefon')",
            name="ck_reguly_dostepnosci_duza_grupa_tryb",
        ),
        CheckConstraint(
            "(duza_grupa_od IS NULL AND duza_grupa_tryb IS NULL) OR "
            "(duza_grupa_od IS NOT NULL AND duza_grupa_tryb IS NOT NULL)",
            name="ck_reguly_dostepnosci_duza_grupa_spojnosc",
        ),
        CheckConstraint(
            "pacing_okno_min IS NOT NULL OR pacing_max_rez IS NOT NULL OR "
            "pacing_max_osob IS NOT NULL OR max_jednoczesnych_rez IS NOT NULL OR "
            "max_jednoczesnych_osob IS NOT NULL OR bufor_min IS NOT NULL OR "
            "okno_wyprzedzenia_dni IS NOT NULL OR cutoff_min IS NOT NULL OR "
            "min_grupa IS NOT NULL OR max_grupa IS NOT NULL OR "
            "duza_grupa_od IS NOT NULL OR duza_grupa_tryb IS NOT NULL",
            name="ck_reguly_dostepnosci_nie_puste",
        ),
        Index(
            "uq_reguly_dostepnosci_global_kanal",
            "kanal",
            unique=True,
            sqlite_where=text("serwis_id IS NULL AND sala_id IS NULL"),
            postgresql_where=text("serwis_id IS NULL AND sala_id IS NULL"),
        ),
        Index(
            "uq_reguly_dostepnosci_serwis_kanal",
            "serwis_id", "kanal",
            unique=True,
            sqlite_where=text("serwis_id IS NOT NULL AND sala_id IS NULL"),
            postgresql_where=text("serwis_id IS NOT NULL AND sala_id IS NULL"),
        ),
        Index(
            "uq_reguly_dostepnosci_sala_kanal",
            "sala_id", "kanal",
            unique=True,
            sqlite_where=text("serwis_id IS NULL AND sala_id IS NOT NULL"),
            postgresql_where=text("serwis_id IS NULL AND sala_id IS NOT NULL"),
        ),
        Index(
            "uq_reguly_dostepnosci_serwis_sala_kanal",
            "serwis_id", "sala_id", "kanal",
            unique=True,
            sqlite_where=text("serwis_id IS NOT NULL AND sala_id IS NOT NULL"),
            postgresql_where=text("serwis_id IS NOT NULL AND sala_id IS NOT NULL"),
        ),
    )
    id = Column(Integer, primary_key=True)
    serwis_id = Column(
        Integer, ForeignKey("godziny_otwarcia.id", ondelete="CASCADE"), nullable=True,
    )
    sala_id = Column(
        Integer, ForeignKey("sale_rezerwacyjne.id", ondelete="CASCADE"), nullable=True,
    )
    kanal = Column(String(16), nullable=False, default="oba", server_default="oba")
    pacing_okno_min = Column(Integer, nullable=True)
    pacing_max_rez = Column(Integer, nullable=True)
    pacing_max_osob = Column(Integer, nullable=True)
    max_jednoczesnych_rez = Column(Integer, nullable=True)
    max_jednoczesnych_osob = Column(Integer, nullable=True)
    bufor_min = Column(Integer, nullable=True)
    okno_wyprzedzenia_dni = Column(Integer, nullable=True)
    cutoff_min = Column(Integer, nullable=True)
    min_grupa = Column(Integer, nullable=True)
    max_grupa = Column(Integer, nullable=True)
    duza_grupa_od = Column(Integer, nullable=True)
    duza_grupa_tryb = Column(String(24), nullable=True)


class ListaOczekujacych(Base):
    """Lista oczekujących (waitlist) — gość bez wolnego stolika. Po zwolnieniu miejsca
    (odwołanie / no-show) admin REALIZUJE wpis → tworzy rezerwację (Termin rodzaj=stolik)."""
    __tablename__ = "lista_oczekujacych"
    id              = Column(Integer, primary_key=True, index=True)
    data            = Column(Date, nullable=False, index=True)
    godz_od         = Column(Time, nullable=True)
    liczba_osob     = Column(Integer, nullable=True)
    nazwisko        = Column(String(128), nullable=False)
    telefon         = Column(EncryptedString(512), nullable=True)   # PII gościa — szyfrowane at-rest
    email           = Column(EncryptedString(512), nullable=True)   # PII gościa — szyfrowane at-rest
    notatka         = Column(String, nullable=True)
    status          = Column(String(16), nullable=False, default="oczekuje")  # oczekuje|zrealizowany|odwolany
    utworzono_at    = Column(DateTime, nullable=False)
    zrealizowano_at = Column(DateTime, nullable=True)
    termin_id       = Column(Integer, ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True)   # przypisany termin
    # Waitlist v2 (S5): powiadomienie „stolik gotowy", tymczasowy HOLD stołu, kanał zapisu.
    powiadomiono_at = Column(DateTime, nullable=True)                                         # kiedy wysłano „stolik gotowy”
    hold_stolik_id  = Column(Integer, ForeignKey("stoliki.id", ondelete="SET NULL"), nullable=True)  # trzymany stół
    hold_stoliki_dodatkowe = Column(JSON, nullable=True)                                      # pozostałe stoły atomowego zestawu
    hold_godz_od     = Column(Time, nullable=True)                                             # początek blokowanego okna
    hold_godz_do     = Column(Time, nullable=True)                                             # koniec wizyty (claim może obejmować też bufor)
    hold_bufor_min   = Column(Integer, nullable=True)                                          # zamrożony bufor po wizycie
    hold_do         = Column(DateTime, nullable=True)                                         # do kiedy trzymany
    token           = Column(String(64), nullable=True, index=True)                          # magic-link gościa (potwierdzenie holdu)
    kanal           = Column(String(16), nullable=False, default="reczna")                    # reczna|online


class RezerwacjaIdempotencja(Base):
    """Wynik operacji tworzenia rezerwacji chroniony kluczem idempotencji.

    Surowy klucz oraz treść żądania nie trafiają do bazy. ``key_hash`` jest SHA-256 klucza,
    a ``request_fingerprint`` HMAC-SHA256 znormalizowanego polecenia. Odpowiedź może zawierać
    dane gościa lub token zarządzania, dlatego jest szyfrowana at-rest.
    """
    __tablename__ = "rezerwacje_idempotencja"
    __table_args__ = (
        UniqueConstraint("operation", "key_hash", name="uq_rezerwacje_idempotencja_operation_key"),
        CheckConstraint("length(operation) > 0", name="ck_rezerwacje_idempotencja_operation"),
        CheckConstraint("length(key_hash) = 64", name="ck_rezerwacje_idempotencja_key_hash"),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_rezerwacje_idempotencja_fingerprint",
        ),
        CheckConstraint(
            "status IN ('processing', 'succeeded')",
            name="ck_rezerwacje_idempotencja_status",
        ),
        CheckConstraint(
            "(status = 'processing' AND http_status IS NULL AND response_enc IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'succeeded' AND http_status BETWEEN 200 AND 299 "
            "AND response_enc IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_rezerwacje_idempotencja_result",
        ),
        Index("ix_rezerwacje_idempotencja_expires_at", "expires_at"),
    )
    id                  = Column(Integer, primary_key=True)
    operation           = Column(String(64), nullable=False)
    key_hash            = Column(String(64), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    status              = Column(String(16), nullable=False, default="processing")
    http_status         = Column(Integer, nullable=True)
    response_enc        = Column(EncryptedString(), nullable=True)
    termin_id           = Column(Integer, ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True)
    created_at          = Column(DateTime, nullable=False)
    completed_at        = Column(DateTime, nullable=True)
    expires_at          = Column(DateTime, nullable=False)


class RezerwacjaDzienLedger(Base):
    """Trwały anchor transakcyjny dla zapisów dostępności jednego dnia."""
    __tablename__ = "rezerwacje_dni_ledger"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="ck_rezerwacje_dni_ledger_revision"),
    )
    data       = Column(Date, primary_key=True)
    revision   = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False)


class RezerwacjaStolikClaim(Base):
    """Jednominutowe, półotwarte zajęcie stołu przez rezerwację albo aktywny hold waitlisty."""
    __tablename__ = "rezerwacje_stoliki_claims"
    __table_args__ = (
        UniqueConstraint(
            "stolik_id", "data", "minute",
            name="uq_rezerwacje_stolik_claim_slot",
        ),
        UniqueConstraint(
            "termin_id", "stolik_id", "data", "minute",
            name="uq_rezerwacje_stolik_claim_termin_owner",
        ),
        UniqueConstraint(
            "waitlist_id", "stolik_id", "data", "minute",
            name="uq_rezerwacje_stolik_claim_waitlist_owner",
        ),
        CheckConstraint(
            "minute >= 0 AND minute < 1440",
            name="ck_rezerwacje_stolik_claim_minute",
        ),
        CheckConstraint(
            "(termin_id IS NOT NULL AND waitlist_id IS NULL AND expires_at IS NULL) OR "
            "(termin_id IS NULL AND waitlist_id IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_rezerwacje_stolik_claim_owner",
        ),
        Index("ix_rezerwacje_stolik_claim_termin_id", "termin_id"),
        Index("ix_rezerwacje_stolik_claim_waitlist_id", "waitlist_id"),
        Index("ix_rezerwacje_stolik_claim_expires_at", "expires_at"),
    )
    id          = Column(Integer, primary_key=True)
    termin_id   = Column(Integer, ForeignKey("terminy.id", ondelete="CASCADE"), nullable=True)
    waitlist_id = Column(
        Integer, ForeignKey("lista_oczekujacych.id", ondelete="CASCADE"), nullable=True,
    )
    stolik_id   = Column(Integer, ForeignKey("stoliki.id", ondelete="RESTRICT"), nullable=False)
    data        = Column(Date, nullable=False)
    minute      = Column(Integer, nullable=False)
    expires_at  = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, nullable=False)


class RezerwacjaPacingLedger(Base):
    """Surowy wkład aktywnej rezerwacji do limitów pacingu danego dnia."""
    __tablename__ = "rezerwacje_pacing_ledger"
    __table_args__ = (
        UniqueConstraint("termin_id", name="uq_rezerwacje_pacing_ledger_termin"),
        CheckConstraint(
            "start_minute >= 0 AND start_minute < 1440",
            name="ck_rezerwacje_pacing_ledger_start_minute",
        ),
        CheckConstraint("covers >= 0", name="ck_rezerwacje_pacing_ledger_covers"),
        Index("ix_rezerwacje_pacing_ledger_data_start", "data", "start_minute"),
    )
    id           = Column(Integer, primary_key=True)
    termin_id    = Column(Integer, ForeignKey("terminy.id", ondelete="CASCADE"), nullable=False)
    data         = Column(Date, nullable=False)
    start_minute = Column(Integer, nullable=False)
    covers       = Column(Integer, nullable=False, default=0)
    override     = Column(Boolean, nullable=False, default=False)
    created_at   = Column(DateTime, nullable=False)


class RezerwacjaOblozenieLedger(Base):
    """Minutowe buckety jednoczesnego obłożenia aktywnych rezerwacji R3."""
    __tablename__ = "rezerwacje_oblozenie_ledger"
    __table_args__ = (
        UniqueConstraint(
            "termin_id", "minute", name="uq_rezerwacje_oblozenie_termin_minute",
        ),
        CheckConstraint(
            "minute >= 0 AND minute < 1440",
            name="ck_rezerwacje_oblozenie_minute",
        ),
        CheckConstraint("covers >= 0", name="ck_rezerwacje_oblozenie_covers"),
        CheckConstraint(
            "kanal IN ('online', 'wewnetrzna')",
            name="ck_rezerwacje_oblozenie_kanal",
        ),
        Index(
            "ix_rezerwacje_oblozenie_data_minute_sala_kanal",
            "data", "minute", "sala_id", "kanal",
        ),
        Index("ix_rezerwacje_oblozenie_termin_id", "termin_id"),
    )
    id = Column(Integer, primary_key=True)
    termin_id = Column(
        Integer, ForeignKey("terminy.id", ondelete="CASCADE"), nullable=False,
    )
    data = Column(Date, nullable=False)
    minute = Column(Integer, nullable=False)
    sala_id = Column(
        Integer, ForeignKey("sale_rezerwacyjne.id", ondelete="RESTRICT"), nullable=True,
    )
    kanal = Column(
        String(16), nullable=False, default="wewnetrzna", server_default="wewnetrzna",
    )
    covers = Column(Integer, nullable=False, default=0, server_default="0")
    override = Column(
        Boolean, nullable=False, default=False, server_default=text("false"),
    )
    created_at = Column(DateTime, nullable=False)


class ReservationAudit(Base):
    """Transakcyjna historia operacji na rezerwacji stolika.

    ``reservation_ref`` jest nieodwracalnym identyfikatorem technicznym, dzięki któremu
    historia pozostaje spójna po twardym usunięciu ``Termin``. Login aktora jest
    denormalizowany z tego samego powodu. ``diff`` może zawierać wyłącznie pola
    operacyjne przygotowane przez moduł ``reservation_audit`` — bez danych gościa.
    """
    __tablename__ = "reservation_audit"
    __table_args__ = (
        CheckConstraint(
            "length(reservation_ref) = 64",
            name="ck_reservation_audit_ref",
        ),
        CheckConstraint(
            "actor_kind IN ('user', 'guest', 'system', 'migration')",
            name="ck_reservation_audit_actor_kind",
        ),
        CheckConstraint(
            "action IN ('create', 'edit', 'cancel', 'delete', 'status', "
            "'host', 'assign', 'override')",
            name="ck_reservation_audit_action",
        ),
        CheckConstraint(
            "reason IS NULL OR reason IN ("
            "'guest_request', 'operator_correction', 'capacity_override', "
            "'pacing_override', 'table_override', 'system_automation', "
            "'import_reconciliation', 'other')",
            name="ck_reservation_audit_reason",
        ),
        CheckConstraint(
            "actor_kind != 'user' OR "
            "(actor_login IS NOT NULL AND length(trim(actor_login)) > 0)",
            name="ck_reservation_audit_user_actor",
        ),
        CheckConstraint(
            "action != 'override' OR reason IS NOT NULL",
            name="ck_reservation_audit_override_reason",
        ),
        Index(
            "ix_reservation_audit_ref_created",
            "reservation_ref", "created_at",
        ),
        Index(
            "ix_reservation_audit_termin_created",
            "termin_id", "created_at",
        ),
        Index(
            "ix_reservation_audit_actor_created",
            "actor_user_id", "created_at",
        ),
    )
    id              = Column(Integer, primary_key=True)
    created_at      = Column(DateTime, nullable=False)
    reservation_ref = Column(String(64), nullable=False)
    termin_id       = Column(
        Integer, ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True,
    )
    actor_kind      = Column(String(16), nullable=False)
    actor_user_id   = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    actor_login     = Column(String(64), nullable=True)
    action          = Column(String(16), nullable=False)
    reason          = Column(String(64), nullable=True)
    diff            = Column(JSON, nullable=False)


class ReservationOverrideContext(Base):
    """Szyfrowany kontekst powodu jawnego przekroczenia reguły rezerwacji."""
    __tablename__ = "reservation_override_context"
    __table_args__ = (
        UniqueConstraint(
            "audit_id", name="uq_reservation_override_context_audit_id",
        ),
        CheckConstraint(
            "reason_code IN ("
            "'guest_request', 'large_group_confirmed', 'event_exception', "
            "'operational_decision', 'walk_in', 'other', 'legacy_confirmation')",
            name="ck_reservation_override_context_reason_code",
        ),
        Index(
            "ix_reservation_override_context_reason_code", "reason_code",
        ),
    )
    id = Column(Integer, primary_key=True)
    audit_id = Column(
        Integer,
        ForeignKey("reservation_audit.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason_code = Column(String(32), nullable=False)
    note = Column(EncryptedString(1024), nullable=True)


class ProfilGoscia(Base):
    """Trwały profil gościa (nadbudowa nad grupowaniem CRM po telefonie): tagi/VIP, alergie,
    preferencje, okazje. Statystyki wizyt NADAL liczone w locie z Termin — tu tylko to, czego
    nie da się policzyć. Klucz = sha256 znormalizowanego telefonu (NIE plaintext — inaczej PII
    wyciekłaby przez indeks). Alergie/notatka = dane wrażliwe → EncryptedString (RODO art. 9)."""
    __tablename__ = "profile_gosci"
    id                 = Column(Integer, primary_key=True, index=True)
    klucz_hash         = Column(String(64), unique=True, index=True, nullable=False)  # sha256(klucz CRM)
    nazwisko           = Column(String(128), nullable=True)                # cache do listy
    telefon            = Column(EncryptedString(512), nullable=True)       # PII szyfrowane
    email              = Column(EncryptedString(512), nullable=True)
    tagi               = Column(JSON, nullable=True)                       # ["VIP","stały","alergik"]
    vip                = Column(Boolean, nullable=False, default=False)    # ręczny override (obok auto: odbyte≥5)
    alergie            = Column(EncryptedString(512), nullable=True)       # RODO art. 9 (zdrowie) — szyfrowane
    dieta              = Column(String(128), nullable=True)
    preferowana_strefa = Column(String(64), nullable=True)
    notatka            = Column(EncryptedString(1024), nullable=True)      # szyfrowane
    okazja_typ         = Column(String(32), nullable=True)                 # urodziny/rocznica
    okazja_data        = Column(String(5), nullable=True)                  # „MM-DD" (dzień+miesiąc)
    marketing_zgoda    = Column(Boolean, nullable=False, default=False)    # podstawa przypomnień o okazjach
    utworzono_at       = Column(DateTime, nullable=True)
    zaktualizowano_at  = Column(DateTime, nullable=True)


class AuditLog(Base):
    """Dziennik audytu dostępu do danych wrażliwych (RODO). Rejestruje KTO, KIEDY i CZEGO
    dotyczył dostęp do danych płacowych/finansowych (raporty godzin ze stawkami, rozliczenia).
    `login` jest denormalizowany, by wpis przetrwał usunięcie konta (rozliczalność).
    `ts` przechowywane jako naiwny UTC (spójność SQLite/Postgres) — zapisuje je helper zapisz_audyt."""
    __tablename__ = "audit_log"
    id           = Column(Integer, primary_key=True, index=True)
    ts           = Column(DateTime, nullable=False, index=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    login        = Column(String(64), nullable=True)
    akcja        = Column(String(64), nullable=False)          # np. 'raport_godzin'
    zasob        = Column(String(128), nullable=True)          # czego dotyczy, np. '2026-07'
    pracownik_id = Column(Integer, ForeignKey("pracownicy.id", ondelete="SET NULL"), nullable=True)  # kogo dotyczy
    ip           = Column(String(64), nullable=True)
    szczegoly    = Column(String, nullable=True)


class Subskrypcja(Base):
    """Subskrypcja/licencja instancji (singleton id=1; model instance-per-tenant). Bez realnej
    bramki płatności — status ustawia operator SaaS. Subskrypcja NIEAKTYWNA (wygasła/zawieszona
    albo po dacie data_do) degraduje instancję do trybu TYLKO-ODCZYT (zapisy zwracają 402)."""
    __tablename__ = "subskrypcja"
    id      = Column(Integer, primary_key=True)
    tier    = Column(String(16), nullable=False, default="free")      # free|basic|pro|premium|enterprise
    status  = Column(String(16), nullable=False, default="aktywna")   # aktywna|trial|wygasla|zawieszona
    data_od = Column(Date, nullable=True)
    data_do = Column(Date, nullable=True)     # None = bezterminowa; koniec opłaconego okresu
    uwagi   = Column(String, nullable=True)
    # Cena netto override (enterprise / indywidualny rabat); NULL = wg cennika po tier.
    cena_netto    = Column(Float, nullable=True)
    # Kredyt z downgrade — pomniejsza kolejną dopłatę/fakturę.
    saldo_kredytu = Column(Float, nullable=False, default=0.0)
    # Metoda płatności zapięta w trialu → auto-obciążenie po 14 dniach. Token = referencja metody
    # (sandbox: udawany; docelowo Stripe pm_...). NIGDY nie trzymamy numeru karty (PAN) — tylko
    # ostatnie 4 cyfry (do wyświetlenia) i token (do obciążenia po trialu).
    karta_token     = Column(String(64), nullable=True)
    karta_ostatnie4 = Column(String(4), nullable=True)


class RejestracjaLokalu(Base):
    """Rejestracja oczekująca na płatność (instancja-MATKA). Kreator zbiera dane właściciela
    (e-mail + hasło), typ/moduły i wybrany plan, tworzy ten wpis (status=oczekuje) i kieruje do
    checkoutu. Dopiero po udanej płatności (sandbox lub webhook) provisioning stawia instancję
    z gotowym adminem i aktywną subskrypcją — wtedy powstaje konto+instancja. haslo_hash liczony
    na matce (bcrypt), NIGDY plaintext; external_id spina rejestrację z płatnością (idempotencja)."""
    __tablename__ = "rejestracje_lokalu"
    id           = Column(Integer, primary_key=True, index=True)
    email        = Column(String(255), nullable=False, index=True)
    haslo_hash   = Column(String(255), nullable=False)          # bcrypt (liczony na matce)
    nazwa        = Column(String(120), nullable=False)
    typ_lokalu   = Column(String(32), nullable=True)
    moduly       = Column(JSON, nullable=True)                  # {"modul_rezerwacje":true,...}
    sale         = Column(JSON, nullable=True)                  # sale/strefy lokalu z kreatora (sprzątanie + rezerwacje)
    tier         = Column(String(16), nullable=False, default="free")
    netto        = Column(Float, nullable=False, default=0.0)
    status       = Column(String(16), nullable=False, default="oczekuje", index=True)  # oczekuje|przetwarzanie|zrealizowana|blad
    external_id  = Column(String, nullable=False, unique=True, index=True)
    slug         = Column(String(40), nullable=True)
    url          = Column(String, nullable=True)
    utworzono_at    = Column(DateTime, nullable=True)
    zrealizowano_at = Column(DateTime, nullable=True)
    # Karta zapięta na trial planu płatnego (auto-obciążenie po 14 dniach). karta_fingerprint =
    # sha256(numer) → dedup: jedna karta = jeden trial (koniec wykorzystywania triala dwa razy).
    # PAN NIE jest przechowywany; token/ostatnie4 jadą do instancji, fingerprint zostaje na matce.
    karta_token       = Column(String(64), nullable=True)
    karta_ostatnie4   = Column(String(4), nullable=True)
    karta_fingerprint = Column(String(64), nullable=True, index=True)
    # Zgoda na Regulamin/Politykę/DPA przy zakładaniu konta (dowodliwość RODO: WERSJA + moment).
    zgoda_wersja      = Column(String(32), nullable=True)
    zgoda_at          = Column(DateTime, nullable=True)
    __table_args__ = (
        # Jedna karta = jeden AKTYWNY trial — dedup na poziomie bazy domyka wyścig TOCTOU
        # (dwa równoległe /rejestracja z tą samą kartą). Częściowy indeks: obejmuje tylko statusy
        # w toku/zrealizowane, więc 'blad' oraz brak karty (NULL) nie blokują ponownej próby.
        Index("uq_rejestracje_karta_aktywne", "karta_fingerprint", unique=True,
              sqlite_where=text("karta_fingerprint IS NOT NULL AND status IN ('przetwarzanie','zrealizowana')"),
              postgresql_where=text("karta_fingerprint IS NOT NULL AND status IN ('przetwarzanie','zrealizowana')")),
    )


class PlatnoscSubskrypcji(Base):
    """Płatność za subskrypcję lokalu (abonament / dopłata przy upgrade). Osobno od Platnosc
    (zadatki imprez). Bez realnej bramki — tryb sandbox (link + ręczne „opłacona"); docelowo
    webhook Stripe/P24 ustawia 'oplacona' i przedłuża Subskrypcja.data_do."""
    __tablename__ = "platnosci_subskrypcji"
    id           = Column(Integer, primary_key=True, index=True)
    rodzaj       = Column(String(16), nullable=False, default="abonament")  # abonament|doplata
    tier         = Column(String(16), nullable=True)          # tier, którego dotyczy
    netto        = Column(Float, nullable=False, default=0.0)
    vat          = Column(Float, nullable=False, default=0.0)
    brutto       = Column(Float, nullable=False, default=0.0)
    okres_od     = Column(Date, nullable=True)                # okres abonamentu (na fakturze)
    okres_do     = Column(Date, nullable=True)
    status       = Column(String(16), nullable=False, default="oczekuje")   # oczekuje|oplacona|anulowana
    provider     = Column(String(32), nullable=False, default="sandbox")    # sandbox|stripe|p24
    external_id  = Column(String, nullable=True, index=True)
    link         = Column(String, nullable=True)
    utworzono_at = Column(DateTime, nullable=True)
    oplacono_at  = Column(DateTime, nullable=True)


class Faktura(Base):
    """Faktura VAT za subskrypcję (KSeF/FA(3)). Nabywca = dane firmowe lokalu (snapshot w chwili
    wystawienia), sprzedawca = operator (z env). XML FA(3) generowany przy wystawieniu; numer KSeF
    i UPO wpisywane po przyjęciu przez KSeF (tryb produkcyjny) albo mockowane (tryb testowy/stub)."""
    __tablename__ = "faktury"
    id            = Column(Integer, primary_key=True, index=True)
    numer         = Column(String(32), nullable=False, unique=True)   # LOK/2026/07/0001
    platnosc_id   = Column(Integer, ForeignKey("platnosci_subskrypcji.id", ondelete="SET NULL"), nullable=True)
    rodzaj        = Column(String(8), nullable=False, default="VAT")   # VAT|KOR|ZAL
    nabywca_nip   = Column(String(16), nullable=True)
    nabywca_nazwa = Column(String(256), nullable=True)
    netto         = Column(Float, nullable=False, default=0.0)
    vat           = Column(Float, nullable=False, default=0.0)
    brutto        = Column(Float, nullable=False, default=0.0)
    okres_od      = Column(Date, nullable=True)
    okres_do      = Column(Date, nullable=True)
    opis          = Column(String(512), nullable=True)
    xml           = Column(String, nullable=True)                      # wygenerowany FA(3)
    ksef_number   = Column(String(64), nullable=True)                 # numer nadany przez KSeF
    upo           = Column(String, nullable=True)                      # Urzędowe Poświadczenie Odbioru
    status_ksef   = Column(String(16), nullable=False, default="roboczy")  # roboczy|wyslana|przyjeta|blad
    data_wystawienia = Column(Date, nullable=True)
    utworzono_at  = Column(DateTime, nullable=True)


class HistoriaSubskrypcji(Base):
    """Audyt zmian subskrypcji (upgrade/downgrade/odnowienie) — rozliczalność i podstawa faktur."""
    __tablename__ = "historia_subskrypcji"
    id          = Column(Integer, primary_key=True, index=True)
    ts          = Column(DateTime, nullable=False)
    akcja       = Column(String(24), nullable=False)          # upgrade|downgrade|odnowienie|zmiana_statusu
    tier_z      = Column(String(16), nullable=True)
    tier_na     = Column(String(16), nullable=True)
    kwota_netto = Column(Float, nullable=True)                # dopłata (upgrade) / kredyt (downgrade)
    login       = Column(String(64), nullable=True)
    szczegoly   = Column(String, nullable=True)


class Platnosc(Base):
    """Płatność zadatku online (Rec#7). Bez realnej bramki działa w trybie 'sandbox' (link do
    lokalnego potwierdzenia/demo); docelowo provider Stripe/Przelewy24. Status:
    oczekuje → oplacona (webhook bramki albo ręcznie przez admina) / anulowana."""
    __tablename__ = "platnosci"
    id           = Column(Integer, primary_key=True, index=True)
    termin_id    = Column(Integer, ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True, index=True)
    kwota        = Column(Float, nullable=False, default=0.0)
    status       = Column(String(16), nullable=False, default="oczekuje")  # oczekuje|oplacona|anulowana
    provider     = Column(String(32), nullable=False, default="sandbox")   # sandbox|api(Stripe/P24)
    external_id  = Column(String, nullable=True, index=True)   # token/id z bramki
    link         = Column(String, nullable=True)               # URL do zapłaty
    utworzono_at = Column(DateTime, nullable=False)
    oplacono_at  = Column(DateTime, nullable=True)


class NapiwkiDnia(Base):
    """Pula napiwków z danego dnia do podziału między obsługę sali. Manager wpisuje łączną kwotę
    i sposób podziału: 'godziny' (proporcjonalnie do przepracowanych godzin z RCP) lub 'rowno'
    (po równo). Sam podział liczony jest w locie z grafiku/RCP — tu trzymamy tylko wejście."""
    __tablename__ = "napiwki_dnia"
    id           = Column(Integer, primary_key=True, index=True)
    data         = Column(Date, unique=True, nullable=False, index=True)
    kwota        = Column(Float, nullable=False, default=0.0)
    sposob       = Column(String(16), nullable=False, default="godziny")   # godziny | rowno
    utworzono_at = Column(DateTime, nullable=False)


class Ogloszenie(Base):
    """Ogłoszenie zespołowe — tablica komunikatów manager→pracownicy. Widoczne dla WSZYSTKICH
    pracowników (przez /api/me/ogloszenia); przypięte trzyma się na górze; wygasa po `wazne_do`
    (opcjonalne). Potwierdzenia przeczytania (kto/kiedy) w OgloszeniePotwierdzenie."""
    __tablename__ = "ogloszenia"
    id           = Column(Integer, primary_key=True, index=True)
    tytul        = Column(String(160), nullable=False)
    tresc        = Column(String, nullable=False)
    autor_login  = Column(String, nullable=True)          # denormalizacja autora (rozliczalność), jak AuditLog
    przypiete    = Column(Boolean, nullable=False, default=False)
    wazne_do     = Column(Date, nullable=True)            # po tej dacie znika z widoku pracownika (None = bez limitu)
    utworzono_at = Column(DateTime, nullable=False)

    potwierdzenia = relationship("OgloszeniePotwierdzenie", cascade="all, delete-orphan",
                                 back_populates="ogloszenie")


class OgloszeniePotwierdzenie(Base):
    """Potwierdzenie przeczytania ogłoszenia przez pracownika (read-receipt) — jedno na parę."""
    __tablename__ = "ogloszenia_potwierdzenia"
    id              = Column(Integer, primary_key=True, index=True)
    ogloszenie_id   = Column(Integer, ForeignKey("ogloszenia.id", ondelete="CASCADE"), nullable=False, index=True)
    pracownik_id    = Column(Integer, ForeignKey("pracownicy.id", ondelete="CASCADE"), nullable=False, index=True)
    potwierdzono_at = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint("ogloszenie_id", "pracownik_id", name="uq_ogloszenie_pracownik"),)

    ogloszenie = relationship("Ogloszenie", back_populates="potwierdzenia")

class DokumentZgodnosci(Base):
    """Dokument zgodności — jedna tabela na dwa byty rozróżniane po pracownik_id:
    (a) dokument PRACOWNIKA (badania sanitarno-epidemiologiczne, medycyna pracy, BHP) — pracownik_id ustawione;
    (b) termin LOKALU (koncesja alkoholowa i jej raty, przeglądy gaśnic/wentylacji) — pracownik_id NULL.
    `blokuje_grafik=True` + data_waznosci w przeszłości ⇒ auto-przydział pomija pracownika
    (przeterminowane badania = nie wchodzi na zmianę), a UI grafiku pokazuje ostrzeżenie."""
    __tablename__ = "dokumenty_zgodnosci"
    id             = Column(Integer, primary_key=True, index=True)
    pracownik_id   = Column(Integer, ForeignKey("pracownicy.id", ondelete="CASCADE"), nullable=True, index=True)
    typ            = Column(String(32), nullable=False, default="inne")
    # typy: badania_sanepid | medycyna_pracy | szkolenie_bhp | koncesja | przeglad | inne
    nazwa          = Column(String(160), nullable=False)
    data_waznosci  = Column(Date, nullable=False, index=True)
    notatka        = Column(String, nullable=True)
    blokuje_grafik = Column(Boolean, nullable=False, default=False)
    utworzono_at   = Column(DateTime, nullable=False)

    pracownik = relationship("Pracownik")


class WiadomoscImprezy(Base):
    """Wątek ustaleń przy imprezie (portal klienta ↔ lokal). Pisemny ślad zamiast
    dziesiątek telefonów; autor: 'klient' (z portalu) | 'lokal' (admin) | 'system'
    (auto-notka np. o zmianie liczby gości)."""
    __tablename__ = "wiadomosci_imprez"
    id           = Column(Integer, primary_key=True, index=True)
    termin_id    = Column(Integer, ForeignKey("terminy.id", ondelete="CASCADE"), nullable=False, index=True)
    autor        = Column(String(16), nullable=False, default="klient")
    tresc        = Column(String, nullable=False)
    utworzono_at = Column(DateTime, nullable=False)

    termin = relationship("Termin")


class StornoGastro(Base):
    """Storno / rabat / anulacja z POS Gastro (antyfraud) — wypychane przez agenta lokalnego
    (odczyt NOLOCK, jednokierunkowo). Upsert po id (GUID pozycji/dokumentu POS).
    Mapowanie kelnera po znormalizowanym imieniu i nazwisku — jak odbicia RCP."""
    __tablename__ = "storna_gastro"
    id                = Column(String(36), primary_key=True)
    data              = Column(Date, index=True, nullable=False)
    imie_nazwisko     = Column(String(128), nullable=True)
    pracownik_id      = Column(Integer, ForeignKey("pracownicy.id", ondelete="SET NULL"),
                               nullable=True, index=True)
    typ               = Column(String(16), nullable=False, default="storno")   # storno|rabat|anulacja
    kwota             = Column(Float, nullable=False, default=0.0)
    opis              = Column(String, nullable=True)
    godzina           = Column(Time, nullable=True)
    zaktualizowano_at = Column(DateTime, nullable=False)


class OfertaMenu(Base):
    """Katalog ofert menu imprez (portal Pary Młodej) — definiowany per lokal w Ustawieniach.
    Klient wybiera ofertę w portalu; wybór zapisuje się na Terminie (menu_oferta_id)."""
    __tablename__ = "oferty_menu"
    id            = Column(Integer, primary_key=True, index=True)
    nazwa         = Column(String(120), nullable=False)
    opis          = Column(String, nullable=True)
    cena_od_osoby = Column(Float, nullable=False, default=0.0)
    aktywna       = Column(Boolean, nullable=False, default=True)
    kolejnosc     = Column(Integer, nullable=False, default=0)


class RataImprezy(Base):
    """Harmonogram wpłat imprezy (portal): rata z terminem płatności i statusem.
    „Zapłaconą" oznacza LOKAL (kasa/przelew weryfikowane po stronie lokalu) — portal
    tylko pokazuje statusy; płatności online to osobny etap."""
    __tablename__ = "raty_imprez"
    id               = Column(Integer, primary_key=True, index=True)
    termin_id        = Column(Integer, ForeignKey("terminy.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    nazwa            = Column(String(120), nullable=False)
    kwota            = Column(Float, nullable=False, default=0.0)
    termin_platnosci = Column(Date, nullable=True)
    zaplacona        = Column(Boolean, nullable=False, default=False)
    zaplacona_at     = Column(DateTime, nullable=True)


class Zaliczka(Base):
    """Wniosek o zaliczkę (Portfel pracownika, roadmapa v2). Pracownik wnioskuje do limitu
    procentu bieżącego zarobku; admin akceptuje/odrzuca (rozliczalność: kto+kiedy);
    zaakceptowane zaliczki miesiąca są POTRĄCANE w raporcie wypłat i eksporcie XLSX.
    To workflow potrącenia, NIE kredytowanie — wypłata środków po stronie lokalu (kasa)."""
    __tablename__ = "zaliczki"
    id            = Column(Integer, primary_key=True, index=True)
    pracownik_id  = Column(Integer, ForeignKey("pracownicy.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    miesiac       = Column(String(7), nullable=False, index=True)   # 'YYYY-MM' (miesiąc potrącenia)
    kwota         = Column(Float, nullable=False, default=0.0)
    status        = Column(String(16), nullable=False, default="oczekuje")  # oczekuje|zaakceptowana|odrzucona
    wniosek_at    = Column(DateTime, nullable=False)
    decyzja_at    = Column(DateTime, nullable=True)
    decyzja_login = Column(String, nullable=True)

    pracownik = relationship("Pracownik")


class Zaproszenie(Base):
    """Zaproszenie pracownika do założenia konta (jedyna ścieżka rejestracji przy
    rejestracja_otwarta=False). Manager tworzy wpis dla KONKRETNEGO pracownika
    (istniejącego lub zakładanego przy okazji) z docelową rolą konta; link z tokenem
    trafia do pracownika dowolnym kanałem. Rejestracja z tokenu tworzy konto już
    PRZYPIĘTE do pracownika (godziny/grafik od pierwszego logowania), oznacza
    zaproszenie jako użyte. Token jednorazowy, z terminem ważności."""
    __tablename__ = "zaproszenia"
    id            = Column(Integer, primary_key=True, index=True)
    token         = Column(String(64), nullable=False, unique=True, index=True)
    pracownik_id  = Column(Integer, ForeignKey("pracownicy.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    rola          = Column(String(16), nullable=False, default="employee")  # employee|kuchnia|szef|szef_kuchni
    utworzono_at  = Column(DateTime, nullable=False)
    wygasa_at     = Column(DateTime, nullable=False)
    uzyte_at      = Column(DateTime, nullable=True)
    utworzyl_login = Column(String, nullable=True)   # rozliczalność (denormalizacja jak AuditLog)

    pracownik = relationship("Pracownik")


class UtargDnia(Base):
    """Dzienny utarg z POS — tor A uniwersalnej integracji (docs/POS-INTEGRACJA.md).
    Wspólny mianownik WSZYSTKICH źródeł danych sprzedażowych: ręczny wpis w panelu,
    import CSV, lokalny agent (driver per POS), konektor chmurowy. Upsert po
    (data, zrodlo) — każde źródło nadpisuje własny wiersz, źródła nie gryzą się."""
    __tablename__ = "utarg_dnia"
    __table_args__ = (UniqueConstraint("data", "zrodlo"),)
    id               = Column(Integer, primary_key=True, index=True)
    data             = Column(Date, nullable=False, index=True)
    zrodlo           = Column(String(32), nullable=False, default="reczny")  # reczny|csv|gastro_mssql|dotykacka|...
    netto            = Column(Float, nullable=False, default=0.0)
    gotowka          = Column(Float, nullable=True)
    karta            = Column(Float, nullable=True)
    liczba_rachunkow = Column(Integer, nullable=True)
    aktualizacja_at  = Column(DateTime, nullable=False)


class PracownikPosId(Base):
    """Trwałe mapowanie identyfikatora pracownika z POS → pracownik Lokalo. Zastępuje kruche
    dopasowanie po imieniu (duplikaty, zdrobnienia, ogonki) — warunek skalowania na wiele lokali.
    Ustawiane w kreatorze „Integracja POS" (krok mapowań). Ingest woli mapę jawną, fallback = imię."""
    __tablename__ = "pracownik_pos_id"
    __table_args__ = (UniqueConstraint("zrodlo", "pos_id"),)
    id           = Column(Integer, primary_key=True, index=True)
    pracownik_id = Column(Integer, ForeignKey("pracownicy.id", ondelete="CASCADE"), nullable=False, index=True)
    zrodlo       = Column(String(32), nullable=False)   # driver/źródło: gastro_mssql|soga_firebird|...
    pos_id       = Column(String(64), nullable=False)   # stabilny id użytkownika w POS
    pos_nazwa    = Column(String(128), nullable=True)   # nazwa z POS (podgląd, nie do dopasowania)

    pracownik = relationship("Pracownik")


class AgentStatus(Base):
    """Zdrowie lokalnego agenta POS (heartbeat) — bez tego agent „umiera po cichu"
    u klienta. Jeden wiersz per driver; panel pokazuje wersję, capabilities i błędy,
    alarmuje gdy ostatni sync jest zbyt stary."""
    __tablename__ = "agent_status"
    id              = Column(Integer, primary_key=True)
    driver          = Column(String(48), nullable=False, unique=True)   # np. gastro_mssql
    wersja          = Column(String(32), nullable=True)
    capabilities    = Column(JSON, nullable=True)    # np. ["utarg","odbicia","stoly"]
    ostatni_sync    = Column(DateTime, nullable=True)
    bledy           = Column(JSON, nullable=True)    # ostatnie błędy agenta (lista stringów)
    aktualizacja_at = Column(DateTime, nullable=False)
