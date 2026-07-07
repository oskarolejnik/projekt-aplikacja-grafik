"""Modele ORM — tabele SQLite przez SQLAlchemy."""

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time, DateTime, Float, JSON,
    ForeignKey, Table, UniqueConstraint, Index, text
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
    # --- Konta zespołu ---
    # False (domyślnie) = publiczna samodzielna rejestracja pracownika WYŁĄCZONA:
    # konto zakłada się wyłącznie z linku-zaproszenia wygenerowanego przez managera.
    rejestracja_otwarta = Column(Boolean, nullable=False, default=False)
    # --- Parametry obsady imprez (dawniej zaszyte pod jeden lokal; domyślne = zachowanie historyczne) ---
    impreza_osoby_na_obsluge = Column(Integer, nullable=False, default=15)             # 1 pracownik na tylu gości
    impreza_wyprzedzenie_min = Column(Integer, nullable=False, default=120)            # obsługa startuje tyle min przed
    impreza_najwczesniej     = Column(String(5), nullable=False, default="10:00")      # nie wcześniej niż
    impreza_sale_min2        = Column(String(128), nullable=False, default="R2Piw,R2G")  # sale z min. 2 obsady (po przecinku)
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
    imprezy_excel_mapa         = Column(JSON, nullable=True)   # NULL = {"godzina":"J1","osoby":"H8","sala":"J2"}
    zeszyt_kolumny             = Column(JSON, nullable=True)   # NULL = ["towar","koszty","wyplaty","inne"]
    pos_mapa_rewirow           = Column(JSON, nullable=True)   # NULL = stałe STOLY_* (main.py); patrz docs/POS-INTEGRACJA.md


class Stolik(Base):
    """Stolik/zasób do rezerwacji (moduł rezerwacji). Strefa = sala/ogród (string, mapuje na
    Termin.sala). Pojemność kontroluje walidację rezerwacji."""
    __tablename__ = "stoliki"
    id        = Column(Integer, primary_key=True, index=True)
    nazwa     = Column(String(32), nullable=False)            # np. „S1", „Loża 3"
    strefa    = Column(String(32), nullable=True)             # sala/ogród/antresola
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


class GodzinyOtwarcia(Base):
    """Serwis rezerwacyjny (okno przyjęć) per dzień tygodnia — kilka wierszy na dzień = lunch/kolacja.
    Historycznie „godziny otwarcia"; rozszerzone o turn-time zależny od grupy i pacing (limit coverów)."""
    __tablename__ = "godziny_otwarcia"
    id                = Column(Integer, primary_key=True, index=True)
    dzien_tygodnia    = Column(Integer, nullable=False)        # 0=poniedziałek … 6=niedziela
    godz_od           = Column(Time, nullable=False)
    godz_do           = Column(Time, nullable=False)
    ostatni_zasiadek  = Column(Time, nullable=True)            # ostatnia możliwa godzina rezerwacji
    dlugosc_slotu_min = Column(Integer, nullable=False, default=120)   # krok siatki + bazowy turn-time
    aktywny           = Column(Boolean, nullable=False, default=True)
    nazwa             = Column(String(32), nullable=True)      # etykieta serwisu: „Lunch"/„Kolacja" (NULL = jeden serwis dnia)
    # Turn-time zależny od wielkości grupy: [{"do_osob":2,"min":90},{"do_osob":6,"min":120}] rosnąco.
    # NULL → używamy dlugosc_slotu_min (zachowanie historyczne).
    turn_time_progi   = Column(JSON, nullable=True)
    # Pacing: limit rezerwacji/osób startujących w oknie pacing_okno_min (NULL = bez limitu / krok slotu).
    pacing_max_rez    = Column(Integer, nullable=True)
    pacing_max_osob   = Column(Integer, nullable=True)
    pacing_okno_min   = Column(Integer, nullable=True)


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
