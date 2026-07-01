// Taksonomia typów lokali gastro → presety modułów (z analizy 6 kategorii + syntezy).
// Kreator zakładania lokalu customizuje ISTNIEJĄCE flagi z LokalConfig; nowych flag nie dodajemy.

// Definicje 6 modułów (kolejność w kroku „dostrój moduły"). `wymaga` = zależność (blokada w UI).
export const MODULY = [
  { key: 'modul_rezerwacje', ikona: 'pin', label: 'Rezerwacje stolików',
    opis: 'Rezerwacje stolików, baza gości (CRM) i scoring no-show.' },
  { key: 'rezerwacje_online', ikona: 'users', label: 'Widget rezerwacji online', wymaga: 'modul_rezerwacje',
    opis: 'Publiczny formularz rezerwacji dla gości — bez logowania. Wymaga modułu rezerwacji.' },
  { key: 'modul_imprezy', ikona: 'sparkles', label: 'Imprezy i wesela',
    opis: 'Kalendarz wydarzeń, obsada pod liczbę gości, zadatki, rozliczanie imprez i sal.' },
  { key: 'modul_rozliczenia', ikona: 'clipboard', label: 'Rozliczenia kasowe dnia',
    opis: 'Zeszyt utargu: gotówka, karty, terminale, kasy — z alertami anomalii.' },
  { key: 'modul_pos', ikona: 'server', label: 'Integracja POS / kasa',
    opis: 'Podgląd stołów na żywo i utarg z systemu POS (przez lokalnego agenta).' },
  { key: 'modul_sprzatanie', ikona: 'refresh', label: 'Grafik sprzątania',
    opis: 'Harmonogram sprzątania sal i zamówienia sprzątaczki.' },
]

export const KLUCZE_MODULOW = MODULY.map((m) => m.key)

// „Rdzeń" zawsze włączony (bez flagi) — pokazujemy w kreatorze, żeby było jasne co i tak dostają.
export const RDZEN = ['Auto-grafik + dyspozycyjność', 'Ewidencja czasu (RCP) → wypłaty', 'Prognoza obsady', 'Giełda wymiany zmian', 'Strażnik prawa pracy']

// 14 kuratorowanych typów. `moduly` = preset 6 flag. `popularny` → wyżej + znacznik.
export const TYPY = [
  { id: 'pizzeria', nazwa: 'Pizzeria', ikona: 'menu', popularny: true,
    opis: 'Grafik pod wieczorne i weekendowe szczyty, rozliczenie utargu z kasy i rezerwacja stolika online dla gości.',
    moduly: { modul_rezerwacje: true, modul_imprezy: false, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: false, rezerwacje_online: true } },
  { id: 'restauracja-a-la-carte', nazwa: 'Restauracja à la carte', ikona: 'sparkles', popularny: true,
    opis: 'Klasyczna restauracja na rezerwacjach: stoliki online, żywa sala na POS i domknięta kasa dnia. Od casualu po premium i steakhouse.',
    moduly: { modul_rezerwacje: true, modul_imprezy: false, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: false, rezerwacje_online: true } },
  { id: 'karczma-regionalna', nazwa: 'Karczma / restauracja regionalna', ikona: 'office', popularny: true,
    opis: 'Pełny profil lokalu grupowo-imprezowego z kuchnią: rezerwacje i widget, imprezy okolicznościowe z zadatkami, POS, rozliczenia i sprzątanie sal.',
    moduly: { modul_rezerwacje: true, modul_imprezy: true, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: true, rezerwacje_online: true } },
  { id: 'restauracja-z-sala-imprezowa', nazwa: 'Restauracja z salą imprezową', ikona: 'calendar', popularny: false,
    opis: 'Codzienny ruch à la carte z rezerwacjami stolików plus osobna sala na wesela i imprezy zamknięte — dwa modele w jednym.',
    moduly: { modul_rezerwacje: true, modul_imprezy: true, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: true, rezerwacje_online: true } },
  { id: 'dom-weselny', nazwa: 'Dom weselny / sala bankietowa', ikona: 'users', popularny: false,
    opis: 'Sprzedaż bloków imprez na sale: wesela i przyjęcia z zadatkami, obsada liczona pod liczbę gości i grafik sprzątania między eventami.',
    moduly: { modul_rezerwacje: false, modul_imprezy: true, modul_rozliczenia: true, modul_pos: false, modul_sprzatanie: true, rezerwacje_online: false } },
  { id: 'catering-wyjazdowy', nazwa: 'Catering wyjazdowy', ikona: 'upload', popularny: false,
    opis: 'Kalendarz zleceń i obsada per liczba gości na eventach u klienta, z rozliczeniem zaliczek i dopłat — bez lokalu i sali do sprzątania.',
    moduly: { modul_rezerwacje: false, modul_imprezy: true, modul_rozliczenia: true, modul_pos: false, modul_sprzatanie: false, rezerwacje_online: false } },
  { id: 'pub-bar', nazwa: 'Pub / bar', ikona: 'clock', popularny: false,
    opis: 'Grafik barmanów pod wieczorne szczyty i mecze, rezerwacja stolika na telefon i rozliczenie utargu zza baru z każdej zmiany.',
    moduly: { modul_rezerwacje: true, modul_imprezy: false, modul_rozliczenia: true, modul_pos: false, modul_sprzatanie: false, rezerwacje_online: false } },
  { id: 'bar-koktajlowy-winiarnia', nazwa: 'Koktajlbar / winiarnia', ikona: 'sparkles', popularny: false,
    opis: 'Kameralny lokal premium na rezerwacjach: stolik przy barze online, precyzyjny grafik barmanów-specjalistów i rozliczenie co do złotówki.',
    moduly: { modul_rezerwacje: true, modul_imprezy: false, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: false, rezerwacje_online: true } },
  { id: 'klub-muzyczny', nazwa: 'Klub / dyskoteka', ikona: 'pin', popularny: false,
    opis: 'Duża zmienna ekipa pod eventy, rezerwacje loż VIP, wiele punktów baru na POS i sprzątanie sali po nocy — najbardziej złożony profil.',
    moduly: { modul_rezerwacje: true, modul_imprezy: true, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: true, rezerwacje_online: true } },
  { id: 'kawiarnia', nazwa: 'Kawiarnia', ikona: 'bell', popularny: false,
    opis: 'Zmiany baristów, rozliczenie utargu dnia i podgląd kasy z POS. Ruch głównie walk-in, rezerwacja stolika opcjonalnie.',
    moduly: { modul_rezerwacje: true, modul_imprezy: false, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: false, rezerwacje_online: false } },
  { id: 'cukiernia-piekarnia', nazwa: 'Cukiernia / piekarnia z kawiarnią', ikona: 'check', popularny: false,
    opis: 'Obsada lady i produkcji o skrajnych godzinach, rozliczenie utargu z POS oraz zamówienia okolicznościowe (torty, wypieki) z zadatkiem.',
    moduly: { modul_rezerwacje: false, modul_imprezy: true, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: false, rezerwacje_online: false } },
  { id: 'fast-casual-bar-mleczny', nazwa: 'Fast-casual / bar mleczny', ikona: 'refresh', popularny: false,
    opis: 'Quick-service z kolejką: obsada pod szczyt lunchowy z prognozy, szybki obrót i rozliczenie utargu z POS. Bez rezerwacji i imprez.',
    moduly: { modul_rezerwacje: false, modul_imprezy: false, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: false, rezerwacje_online: false } },
  { id: 'food-truck', nazwa: 'Food truck', ikona: 'info', popularny: false,
    opis: 'Mały zespół na trasie, rozliczenie utargu po evencie i kalendarz wynajmu na imprezy z zadatkiem. Bez stacjonarnej kasy i sali.',
    moduly: { modul_rezerwacje: false, modul_imprezy: true, modul_rozliczenia: true, modul_pos: false, modul_sprzatanie: false, rezerwacje_online: false } },
  { id: 'siec-stolowka-foodcourt', nazwa: 'Sieć / stołówka / food court', ikona: 'server', popularny: false,
    opis: 'Żywienie zorganizowane i wielolokalowe: spójny grafik i RCP w każdym punkcie, rozliczenia kasowe z alertami anomalii, POS i sprzątanie wspólnej strefy.',
    moduly: { modul_rezerwacje: false, modul_imprezy: false, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: true, rezerwacje_online: false } },
]

// „Inny / od zera" — sensowny domyślny preset (à la carte) z pełną swobodą.
export const PRESET_INNY = { modul_rezerwacje: true, modul_imprezy: false, modul_rozliczenia: true, modul_pos: true, modul_sprzatanie: false, rezerwacje_online: true }

export const TYP_PO_ID = Object.fromEntries(TYPY.map((t) => [t.id, t]))

// Egzekwowanie zależności modułów (widget online ⇒ moduł rezerwacji).
export function znormalizujModuly(m) {
  const out = { ...m }
  if (out.rezerwacje_online) out.modul_rezerwacje = true
  if (!out.modul_rezerwacje) out.rezerwacje_online = false
  return out
}
