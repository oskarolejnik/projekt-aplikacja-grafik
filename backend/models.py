"""Modele ORM — tabele SQLite przez SQLAlchemy."""

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time,
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

class Pracownik(Base):
    __tablename__ = "pracownicy"
    id         = Column(Integer, primary_key=True, index=True)
    imie       = Column(String(64), nullable=False)
    nazwisko   = Column(String(64), nullable=False)
    aktywny    = Column(Boolean, default=True)

    kwalifikacje  = relationship("Stanowisko", secondary=pracownik_stanowisko, back_populates="uprawnieni")
    dyspozycje    = relationship("Dyspozycja", back_populates="pracownik", cascade="all, delete-orphan")
    przydzialy    = relationship("PrzydzialZmiany", back_populates="pracownik", cascade="all, delete-orphan")

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

    pracownik = relationship("Pracownik", back_populates="dyspozycje")

class PrzydzialZmiany(Base):
    __tablename__ = "przydzialy_zmian"
    __table_args__ = (UniqueConstraint("data", "stanowisko_id", "pracownik_id", "godz_od"),)
    id            = Column(Integer, primary_key=True, index=True)
    data          = Column(Date, nullable=False)
    stanowisko_id = Column(Integer, ForeignKey("stanowiska.id"), nullable=False)
    pracownik_id  = Column(Integer, ForeignKey("pracownicy.id"), nullable=False)
    godz_od       = Column(Time, nullable=True)

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