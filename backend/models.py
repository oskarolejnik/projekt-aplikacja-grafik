"""Modele ORM — tabele SQLite przez SQLAlchemy."""

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time, DateTime, Float,
    ForeignKey, Table, UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base

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

    kwalifikacje  = relationship("Stanowisko", secondary=pracownik_stanowisko, back_populates="uprawnieni")
    dyspozycje    = relationship("Dyspozycja", back_populates="pracownik", cascade="all, delete-orphan")
    przydzialy    = relationship("PrzydzialZmiany", back_populates="pracownik", cascade="all, delete-orphan")
    stawki        = relationship("StawkaPracownika", cascade="all, delete-orphan")

class Stanowisko(Base):
    __tablename__ = "stanowiska"
    id            = Column(Integer, primary_key=True, index=True)
    nazwa         = Column(String(64), nullable=False, unique=True)
    tylko_weekend = Column(Boolean, default=False)

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

    stanowisko = relationship("Stanowisko", back_populates="przydzialy")
    pracownik  = relationship("Pracownik",  back_populates="przydzialy")

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
    login        = Column(String(64), unique=True, nullable=False, index=True)
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