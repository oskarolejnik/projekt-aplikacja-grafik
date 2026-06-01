from pydantic import BaseModel, ConfigDict
from datetime import date, time
from typing import Optional, List

# ═══════════════════════════════════════════════════════════════════════════
# SCHEMATY: STANOWISKA
# ═══════════════════════════════════════════════════════════════════════════
class StanowiskoBase(BaseModel):
    nazwa: str
    tylko_weekend: bool = False

class StanowiskoCreate(StanowiskoBase):
    pass

class StanowiskoOut(StanowiskoBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ═══════════════════════════════════════════════════════════════════════════
# SCHEMATY: WYMAGANIA DNIA (ZAKTUALIZOWANE)
# ═══════════════════════════════════════════════════════════════════════════
class WymaganiaBase(BaseModel):
    data: date
    stanowisko_id: int
    liczba_osob: int = 1
    # NOWE POLA DODANE DO WALIDACJI:
    godz_od: Optional[time] = None
    godz_do: Optional[time] = None
    rewir: Optional[str] = None

class WymaganiaCreate(WymaganiaBase):
    pass

class WymaganiaOut(WymaganiaBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ═══════════════════════════════════════════════════════════════════════════
# SCHEMATY: DYSPOZYCJE
# ═══════════════════════════════════════════════════════════════════════════
class DyspozycjaBase(BaseModel):
    pracownik_id: int
    data: date
    dostepnosc: bool = True
    godz_od: Optional[time] = None
    godz_do: Optional[time] = None

class DyspozycjaCreate(DyspozycjaBase):
    pass

class DyspozycjaOut(DyspozycjaBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ═══════════════════════════════════════════════════════════════════════════
# SCHEMATY: PRZYDZIAŁY ZMIAN
# ═══════════════════════════════════════════════════════════════════════════
class PrzydzialBase(BaseModel):
    data: date
    stanowisko_id: int
    pracownik_id: int
    godz_od: Optional[time] = None
    godz_do: Optional[time] = None

class PrzydzialCreate(PrzydzialBase):
    pass

class PrzydzialOut(PrzydzialBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ═══════════════════════════════════════════════════════════════════════════
# SCHEMATY: PRACOWNICY
# ═══════════════════════════════════════════════════════════════════════════
class PracownikBase(BaseModel):
    imie: str
    nazwisko: str
    aktywny: bool = True

class PracownikCreate(PracownikBase):
    kwalifikacje_ids: List[int] = []

class PracownikOut(PracownikBase):
    id: int
    kwalifikacje: List[StanowiskoOut] = []
    model_config = ConfigDict(from_attributes=True)

# ═══════════════════════════════════════════════════════════════════════════
# RESULT AUTO-ASSIGN
# ═══════════════════════════════════════════════════════════════════════════
class AutoAssignResult(BaseModel):
    przydzielone: int
    niedobory: List[dict]