from pydantic import BaseModel, ConfigDict, field_validator
from datetime import date, time
from typing import Optional, List

class OfertaZmianyIn(BaseModel):
    """Wystawienie przydziału na giełdę wymiany zmian."""
    przydzial_id: int
    powod: Optional[str] = None

class NapiwkiIn(BaseModel):
    """Pula napiwków dnia + sposób podziału ('godziny' | 'rowno')."""
    kwota: float = 0.0
    sposob: str = "godziny"

class WymaganiaZPrognozy(BaseModel):
    """Zastosowanie sugerowanej obsady z prognozy do wymagań na najbliższe 7 dni (dla stanowiska)."""
    stanowisko_id: int

class OgloszenieIn(BaseModel):
    """Utworzenie/edycja ogłoszenia zespołowego (tablica manager→pracownicy)."""
    tytul: str
    tresc: str
    przypiete: bool = False
    wazne_do: Optional[date] = None

class PlanPozycjaIn(BaseModel):
    """Pozycja stolika na planie sali (w % kontenera, 0–100)."""
    id: int
    plan_x: int
    plan_y: int

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
    """Logowanie e-mailem (nowe konta) LUB loginem (stare konta bez e-maila) — dokładnie jedno."""
    email: Optional[str] = None
    login: Optional[str] = None
    haslo: str

class RegisterIn(BaseModel):
    email: str
    haslo: str
    imie: str
    nazwisko: str

class ZaproszenieIn(BaseModel):
    """Zaproszenie pracownika do konta: istniejący (pracownik_id) ALBO nowy (imię+nazwisko)."""
    pracownik_id: Optional[int] = None
    imie: Optional[str] = None
    nazwisko: Optional[str] = None
    rola: str = "employee"          # employee|kuchnia|szef|szef_kuchni (admin tylko ręcznie)

class ZaproszenieRejestracjaIn(BaseModel):
    """Rejestracja z linku-zaproszenia: pracownik ustala e-mail (login logowania) i hasło."""
    email: str
    haslo: str

class OnboardingIn(BaseModel):
    """Pierwsza konfiguracja instancji (samoobsługowy kreator) — tworzy pierwszego admina.
    Właściciel loguje się e-mailem; wewnętrzny login syntetyzowany z adresu."""
    email: str
    haslo: str
    nazwa_lokalu: Optional[str] = None

class UserOut(BaseModel):
    id: int
    login: str
    email: Optional[str] = None
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
    # Zbiorcza pula sali (tryb rozliczenia_tryb_kelnera='pula'); None = pole nie zmieniane.
    pula_gotowka: Optional[float] = None
    pula_karta: Optional[float] = None
    pula_fv: Optional[float] = None
    pula_kw: Optional[float] = None

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
    """Publiczne dane brandingu (bez sekretów) — do strony logowania / PWA.
    Zawiera też początek tygodnia grafiku: potrzebny KAŻDEMU zalogowanemu (pracownik
    nie ma dostępu do /api/lokal/config), a nie jest niczym wrażliwym."""
    nazwa_lokalu: str = "Lokalo"
    logo_url: Optional[str] = None
    kolor_primary: Optional[str] = None
    poczatek_tygodnia: int = 2
    grafik_cykl: str = "tydzien"          # publiczny — pracownik też potrzebuje (ekran grafiku/dyspozycji)
    model_config = ConfigDict(from_attributes=True)

class LokalConfigOut(LokalBrandingOut):
    typ_lokalu: Optional[str] = None
    modul_rozliczenia: bool = True
    modul_imprezy: bool = True
    modul_pos: bool = True
    modul_sprzatanie: bool = True
    modul_rezerwacje: bool = True
    rezerwacje_online: bool = False
    rezerwacje_auto_potwierdzenie: bool = False
    rejestracja_otwarta: bool = False
    impreza_osoby_na_obsluge: int = 15
    impreza_wyprzedzenie_min: int = 120
    impreza_najwczesniej: str = "10:00"
    impreza_sale_min2: str = "R2Piw,R2G"
    obsada_rachunki_na_osobe: int = 20
    obsada_min: int = 1
    praca_min_odpoczynek_h: int = 11
    praca_max_dni_tydzien: int = 6
    praca_max_dni_miesiac: int = 22
    impreza_osobne_rozliczenie: bool = True
    rozliczenia_tryb_kelnera: str = "indywidualnie"
    rozliczenia_nazwy_kas: Optional[List[str]] = None
    rozliczenia_nazwy_terminali: Optional[List[str]] = None
    # grafik_cykl dziedziczone z LokalBrandingOut (publiczne)
    sale: Optional[List[str]] = None
    sprzatanie_sale_codziennie: Optional[List[str]] = None
    sprzatanie_sala_niedziela: Optional[str] = None
    imprezy_mapa_sal: Optional[dict] = None
    imprezy_excel_mapa: Optional[dict] = None
    zeszyt_kolumny: Optional[List[str]] = None
    faktura_nip: Optional[str] = None
    faktura_nazwa: Optional[str] = None
    faktura_adres_l1: Optional[str] = None
    faktura_adres_l2: Optional[str] = None

class LokalConfigIn(BaseModel):
    """Częściowa aktualizacja (tylko podane pola są zmieniane)."""
    nazwa_lokalu: Optional[str] = None
    typ_lokalu: Optional[str] = None
    logo_url: Optional[str] = None
    kolor_primary: Optional[str] = None
    poczatek_tygodnia: Optional[int] = None
    modul_rozliczenia: Optional[bool] = None
    modul_imprezy: Optional[bool] = None
    modul_pos: Optional[bool] = None
    modul_sprzatanie: Optional[bool] = None
    modul_rezerwacje: Optional[bool] = None
    rezerwacje_online: Optional[bool] = None
    rezerwacje_auto_potwierdzenie: Optional[bool] = None
    rejestracja_otwarta: Optional[bool] = None
    impreza_osoby_na_obsluge: Optional[int] = None
    impreza_wyprzedzenie_min: Optional[int] = None
    impreza_najwczesniej: Optional[str] = None
    impreza_sale_min2: Optional[str] = None
    obsada_rachunki_na_osobe: Optional[int] = None
    obsada_min: Optional[int] = None
    praca_min_odpoczynek_h: Optional[int] = None
    praca_max_dni_tydzien: Optional[int] = None
    praca_max_dni_miesiac: Optional[int] = None
    impreza_osobne_rozliczenie: Optional[bool] = None
    rozliczenia_tryb_kelnera: Optional[str] = None
    rozliczenia_nazwy_kas: Optional[List[str]] = None
    rozliczenia_nazwy_terminali: Optional[List[str]] = None
    grafik_cykl: Optional[str] = None
    sale: Optional[List[str]] = None
    sprzatanie_sale_codziennie: Optional[List[str]] = None
    # pusty string = reguła niedzieli wyłączona (None = bez zmiany pola)
    sprzatanie_sala_niedziela: Optional[str] = None
    imprezy_mapa_sal: Optional[dict] = None
    imprezy_excel_mapa: Optional[dict] = None
    zeszyt_kolumny: Optional[List[str]] = None
    faktura_nip: Optional[str] = None
    faktura_nazwa: Optional[str] = None
    faktura_adres_l1: Optional[str] = None
    faktura_adres_l2: Optional[str] = None

    @field_validator("rozliczenia_tryb_kelnera")
    @classmethod
    def _tryb_kelnera(cls, v):
        if v is not None and v not in ("indywidualnie", "pula"):
            raise ValueError("rozliczenia_tryb_kelnera: dozwolone 'indywidualnie' lub 'pula'")
        return v

    @field_validator("grafik_cykl")
    @classmethod
    def _cykl(cls, v):
        if v is not None and v not in ("tydzien", "miesiac"):
            raise ValueError("grafik_cykl: dozwolone 'tydzien' lub 'miesiac'")
        return v

    @field_validator("rozliczenia_nazwy_kas", "rozliczenia_nazwy_terminali",
                     "sale", "sprzatanie_sale_codziennie", "zeszyt_kolumny")
    @classmethod
    def _etykiety(cls, v):
        if v is None:
            return v
        czyste = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        if len(czyste) > 20:
            raise ValueError("Maksymalnie 20 etykiet.")
        return czyste or None   # pusta lista = wróć do wartości domyślnych

    @field_validator("imprezy_mapa_sal", "imprezy_excel_mapa")
    @classmethod
    def _mapy(cls, v):
        if v is None:
            return v
        czysta = {str(k).strip(): str(w).strip() for k, w in v.items()
                  if str(k).strip() and str(w).strip()}
        if len(czysta) > 20:
            raise ValueError("Maksymalnie 20 wpisów mapy.")
        return czysta or None   # pusta mapa = wróć do wartości domyślnych

class SubskrypcjaIn(BaseModel):
    """Częściowa aktualizacja subskrypcji/licencji instancji (admin)."""
    tier: Optional[str] = None
    status: Optional[str] = None
    data_od: Optional[date] = None
    data_do: Optional[date] = None
    uwagi: Optional[str] = None
    cena_netto: Optional[float] = None      # override (enterprise / rabat); NULL = wg cennika

class PlatnoscIn(BaseModel):
    """Utworzenie płatności zadatku (admin)."""
    termin_id: Optional[int] = None
    kwota: float

class UpgradeIn(BaseModel):
    """Zmiana pakietu subskrypcji (upgrade z dopłatą / downgrade z kredytem)."""
    tier: str

# --- MODUŁ REZERWACJI ---

class StolikIn(BaseModel):
    nazwa: str
    strefa: Optional[str] = None
    pojemnosc: int = 2
    laczy_sie: bool = False
    aktywny: bool = True
    kolejnosc: int = 0
    rewir_nr: Optional[int] = None   # powiązanie z rewirem POS (live obłożenie)
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
    nazwa: Optional[str] = None                       # etykieta serwisu (Lunch/Kolacja)
    turn_time_progi: Optional[List[dict]] = None       # [{do_osob,min}] — czas zasiadku wg grupy
    pacing_max_rez: Optional[int] = None               # limit rezerwacji na okno pacingu
    pacing_max_osob: Optional[int] = None              # limit osób na okno pacingu
    pacing_okno_min: Optional[int] = None              # długość okna pacingu (min); NULL = krok slotu

    @field_validator("turn_time_progi")
    @classmethod
    def _waliduj_progi(cls, v):
        """Sanityzacja progów turn-time: {do_osob>0, min>0}, posortowane rosnąco po do_osob."""
        if not v:
            return None
        out = []
        for p in v:
            if not isinstance(p, dict):
                continue
            do = int(p.get("do_osob") or 0)
            mn = int(p.get("min") or 0)
            if do > 0 and mn > 0:
                out.append({"do_osob": do, "min": mn})
        out.sort(key=lambda x: x["do_osob"])
        return out or None
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

class ListaOczekujacychIn(BaseModel):
    data: date
    godz_od: Optional[time] = None
    liczba_osob: Optional[int] = None
    nazwisko: str
    telefon: Optional[str] = None
    email: Optional[str] = None
    notatka: Optional[str] = None

class ZrealizujIn(BaseModel):
    """Realizacja wpisu z listy oczekujących → utworzenie rezerwacji stolika."""
    stolik_id: int
    godz_od: Optional[time] = None   # opcjonalne nadpisanie godziny z wpisu

class OnlineRezerwacjaIn(BaseModel):
    """Publiczna rezerwacja online (gość, bez logowania) — system sam dobiera wolny stolik."""
    data: date
    godz_od: time
    liczba_osob: int = 2
    nazwisko: str
    telefon: Optional[str] = None
    email: Optional[str] = None
    notatka: Optional[str] = None

# --- ZGODNOŚĆ LOKALU (badania pracowników + terminy lokalu) ---

class DokumentZgodnosciIn(BaseModel):
    pracownik_id: Optional[int] = None   # None = termin lokalu (koncesja/przegląd)
    typ: str = "inne"
    nazwa: str
    data_waznosci: date
    notatka: Optional[str] = None
    blokuje_grafik: bool = False
