from pydantic import BaseModel, ConfigDict
from datetime import date, time
from typing import Optional, List

class StanowiskoBase(BaseModel):
    nazwa: str; tylko_weekend: bool = False
    widoczny_dla_wszystkich: bool = False
    grupa_widocznosci: Optional[str] = None
    rola: Optional[str] = None                    # 'sala'|'kuchnia'|'techniczny'|'imprezy'|None
    daje_dostep_zamowien: bool = False            # dostęp do formularza zamówień (np. Sprzątaczka)
class StanowiskoCreate(StanowiskoBase): pass

class PodkategoriaCreate(BaseModel):
    nazwa: str; godz_od: Optional[time] = None
class PodkategoriaOut(PodkategoriaCreate):
    id: int; stanowisko_id: int
    model_config = ConfigDict(from_attributes=True)

class StanowiskoOut(StanowiskoBase):
    id: int; podkategorie: List[PodkategoriaOut] = []
    model_config = ConfigDict(from_attributes=True)

class WymaganiaBase(BaseModel):
    data: date; stanowisko_id: int; liczba_osob: int = 1
    godz_od: Optional[time] = None
    rewir: Optional[str] = None
    jest_impreza: bool = False
class WymaganiaCreate(WymaganiaBase): pass
class WymaganiaOut(WymaganiaBase):
    id: int; model_config = ConfigDict(from_attributes=True)

class DyspozycjaBase(BaseModel):
    pracownik_id: int; data: date; dostepnosc: bool = True; godz_od: Optional[time] = None; godz_do: Optional[time] = None
class DyspozycjaCreate(DyspozycjaBase): pass
class DyspozycjaOut(DyspozycjaBase):
    id: int; model_config = ConfigDict(from_attributes=True)

class PrzydzialBase(BaseModel):
    data: date; stanowisko_id: int; pracownik_id: int; godz_od: Optional[time] = None
    rewir: Optional[str] = None; zamyka: bool = False
    zamyka_rewir: bool = False; rozlicza_imprize: bool = False
class PrzydzialCreate(PrzydzialBase): pass
class PrzydzialOut(PrzydzialBase):
    id: int; zamyka_reczny: bool = False; model_config = ConfigDict(from_attributes=True)

class PracownikBase(BaseModel):
    imie: str; nazwisko: str; aktywny: bool = True; kolor: Optional[str] = None; dzial: str = "obsluga"
class StawkaIn(BaseModel):
    stanowisko_id: int
    stawka: float = 0.0
class StawkaOut(BaseModel):
    stanowisko_id: int
    stawka: float
    model_config = ConfigDict(from_attributes=True)
class PracownikCreate(PracownikBase):
    kwalifikacje_ids: List[int] = []
    stawki: List[StawkaIn] = []
class PracownikOut(PracownikBase):
    id: int; kwalifikacje: List[StanowiskoOut] = []
    stawki: List[StawkaOut] = []
    kolejnosc: int = 0
    model_config = ConfigDict(from_attributes=True)

class KolejnoscIn(BaseModel):
    ids: List[int] = []

class AutoAssignResult(BaseModel):
    przydzielone: int; niedobory: List[dict]

# --- NOWE SCHEMATY DLA IMPREZ ---

class ImprezaBase(BaseModel):
    data: date
    klient: str
    liczba_osob: Optional[int] = None
    godzina: Optional[str] = None
    sala: Optional[str] = None
    sciezka_pliku: str

class ImprezaOut(ImprezaBase):
    id: int

    class Config:
        from_attributes = True  # Jeśli używasz starszej wersji Pydantic, zamień to na: orm_mode = True

# --- AUTH / UŻYTKOWNICY ---

class LoginIn(BaseModel):
    login: str
    haslo: str

class RegisterIn(BaseModel):
    login: str
    haslo: str
    imie: str
    nazwisko: str

class UserOut(BaseModel):
    id: int
    login: str
    rola: str
    aktywny: bool = True
    pracownik_id: Optional[int] = None
    dzial: Optional[str] = None       # dział powiązanego Pracownika (obsluga/kuchnia/techniczny)
    sprzataczka: bool = False         # techniczny z kwalifikacją „Sprzątaczka" (dostęp do zamówień)
    imie: Optional[str] = None        # uzupełniane z powiązanego Pracownika
    nazwisko: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class UserCreate(BaseModel):
    login: str
    haslo: str
    rola: str = "employee"
    pracownik_id: Optional[int] = None

class UserUpdate(BaseModel):
    rola: Optional[str] = None
    aktywny: Optional[bool] = None
    pracownik_id: Optional[int] = None

class ResetHasloIn(BaseModel):
    haslo: str

class MojaDyspozycjaIn(BaseModel):
    data: date
    dostepnosc: bool = True
    godz_od: Optional[time] = None
    godz_do: Optional[time] = None

class MojeDyspozycjeBatch(BaseModel):
    dyspozycje: List[MojaDyspozycjaIn]

# --- GRAFIK SPRZĄTANIA ---

class SprzatanieZrobioneIn(BaseModel):
    data: date
    sala: str
    zrobione: bool = True

class SprzatanieKorektaIn(BaseModel):
    data: date
    sala: str
    akcja: str  # 'dodaj' | 'usun' (przeciwna akcja kasuje istniejącą korektę = powrót do automatu)

# --- ZAMÓWIENIA SPRZĄTACZKI ---

class ZamowienieIn(BaseModel):
    nazwa: str
    ilosc: Optional[str] = None
    notatka: Optional[str] = None
    zdjecie: Optional[str] = None   # data URL (base64), opcjonalne — zmniejszone na froncie

class ZamowienieStatusIn(BaseModel):
    status: str   # 'odczytane' | 'zamowione'

# --- URLOPY (obsługa) ---

class UrlopIn(BaseModel):
    start: date
    koniec: date
    powod: Optional[str] = None

class UrlopStatusIn(BaseModel):
    status: str   # 'zaakceptowany' | 'odrzucony'

# --- ROZLICZANIE IMPREZ ---

class ImprezaPozycjaIn(BaseModel):
    forma: str            # 'gotowka' | 'karta' | 'przelew'
    kwota: float = 0.0
    sfiskalizowane: bool = False   # tylko dla gotówki

class RozliczenieImprezyIn(BaseModel):
    data: date
    opis: Optional[str] = None
    pozycje: List[ImprezaPozycjaIn] = []

# --- ROZLICZENIE DNIA (sala) ---

class RozliczenieKelnerIn(BaseModel):
    pracownik_id: int
    gotowka: float = 0.0
    karta: float = 0.0
    fv: float = 0.0
    kw: float = 0.0

class PozycjaKasaIn(BaseModel):
    etykieta: Optional[str] = None
    kwota: float = 0.0
    rewir: Optional[str] = None

class RozliczenieDniaIn(BaseModel):
    zadatek_gotowka: float = 0.0
    zadatek_karta: float = 0.0
    imp_reczny: bool = False
    imp_gotowka: float = 0.0
    imp_karta: float = 0.0
    przelew: float = 0.0
    kelnerzy: List[RozliczenieKelnerIn] = []
    terminale: List[PozycjaKasaIn] = []
    kasy: List[PozycjaKasaIn] = []

class MojRozliczenieIn(BaseModel):
    gotowka: float = 0.0
    karta: float = 0.0
    kw: float = 0.0
    terminale: List[PozycjaKasaIn] = []   # tylko gdy zamyka rewir (terminale jego rewiru)
    kasy: List[PozycjaKasaIn] = []        # tylko gdy zamyka zmianę (raporty dobowe kas)

# --- ZESZYT KASOWY ---

class ZeszytPozycjaIn(BaseModel):
    data: date
    kolumna: str            # 'towar' | 'koszty' | 'wyplaty' | 'inne'
    opis: Optional[str] = None
    kwota: float = 0.0

class ZeszytPrzychodIn(BaseModel):
    data: date
    zrodlo: Optional[str] = None
    gotowka: float = 0.0
    terminal: float = 0.0
    przelew: float = 0.0
    impreza: float = 0.0

class ZeszytConfigIn(BaseModel):
    stan_poczatkowy: float = 0.0
    stan_poczatkowy_data: Optional[date] = None

# --- KALENDARZ IMPREZ ---

class TerminIn(BaseModel):
    data: date
    nazwisko: str
    typ: Optional[str] = None
    liczba_osob: Optional[int] = None
    telefon: Optional[str] = None
    sala: Optional[str] = None
    notatka: Optional[str] = None
    status: str = "rezerwacja"
    zadatek: float = 0.0

# --- KONFIGURACJA LOKALU (white-label + moduły) ---

class LokalBrandingOut(BaseModel):
    """Publiczne dane brandingu (bez sekretów) — do strony logowania / PWA."""
    nazwa_lokalu: str = "Grafik Pracy"
    logo_url: Optional[str] = None
    kolor_primary: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class LokalConfigOut(LokalBrandingOut):
    poczatek_tygodnia: int = 2
    modul_rozliczenia: bool = True
    modul_imprezy: bool = True
    modul_pos: bool = True
    modul_sprzatanie: bool = True
    modul_rezerwacje: bool = True

class LokalConfigIn(BaseModel):
    """Częściowa aktualizacja (tylko podane pola są zmieniane)."""
    nazwa_lokalu: Optional[str] = None
    logo_url: Optional[str] = None
    kolor_primary: Optional[str] = None
    poczatek_tygodnia: Optional[int] = None
    modul_rozliczenia: Optional[bool] = None
    modul_imprezy: Optional[bool] = None
    modul_pos: Optional[bool] = None
    modul_sprzatanie: Optional[bool] = None
    modul_rezerwacje: Optional[bool] = None

# --- MODUŁ REZERWACJI ---

class StolikIn(BaseModel):
    nazwa: str
    strefa: Optional[str] = None
    pojemnosc: int = 2
    laczy_sie: bool = False
    aktywny: bool = True
    kolejnosc: int = 0
class StolikOut(StolikIn):
    id: int
    model_config = ConfigDict(from_attributes=True)

class GodzinyOtwarciaIn(BaseModel):
    dzien_tygodnia: int            # 0=poniedziałek … 6=niedziela
    godz_od: time
    godz_do: time
    ostatni_zasiadek: Optional[time] = None
    dlugosc_slotu_min: int = 120
    aktywny: bool = True
class GodzinyOtwarciaOut(GodzinyOtwarciaIn):
    id: int
    model_config = ConfigDict(from_attributes=True)

class RezerwacjaIn(BaseModel):
    """Rezerwacja stolika (rodzaj=stolik). godz_do liczone z długości slotu, gdy puste."""
    data: date
    godz_od: Optional[time] = None
    godz_do: Optional[time] = None
    stolik_id: Optional[int] = None
    liczba_osob: Optional[int] = None
    nazwisko: str                  # klient
    telefon: Optional[str] = None
    email: Optional[str] = None
    notatka: Optional[str] = None
    zadatek: float = 0.0

class RezerwacjaStatusIn(BaseModel):
    status: str                    # potwierdzona | odbyla | no_show | odwolana