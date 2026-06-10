from pydantic import BaseModel, ConfigDict
from datetime import date, time
from typing import Optional, List

class StanowiskoBase(BaseModel):
    nazwa: str; tylko_weekend: bool = False
    widoczny_dla_wszystkich: bool = False
    grupa_widocznosci: Optional[str] = None
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