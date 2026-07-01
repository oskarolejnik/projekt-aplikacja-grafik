---
name: Grafik Pracy
description: System operacyjny dla lokalu gastro — pastelowy neon na czerni
colors:
  ink: "#F4F4F5"
  muted: "#A1A1AA"
  bg: "#1C1C1E"
  bg-elevated: "#232326"
  surface: "#2A2A2D"
  surface-raised: "#323236"
  line: "#FFFFFF14"
  cream: "#F5F0E6"
  mint: "#A7D7C5"
  lemon: "#F4E2A0"
  blush: "#F2B8CB"
  coral: "#F2A2A2"
  success: "#86E0B0"
  danger: "#F26D6D"
  info: "#8FBCFF"
typography:
  display:
    fontFamily: "\"Space Grotesk\", \"Space Grotesk Fallback\", ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2.5rem, 6vw, 5rem)"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "\"Space Grotesk\", \"Space Grotesk Fallback\", sans-serif"
    fontSize: "clamp(1.75rem, 3vw, 2.5rem)"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  title:
    fontFamily: "\"Space Grotesk\", \"Space Grotesk Fallback\", sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, \"Inter Fallback\", ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, \"Inter Fallback\", sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.06em"
rounded:
  sm: "8px"
  md: "12px"
  lg: "16px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "20px"
  lg: "32px"
components:
  button-primary:
    backgroundColor: "{colors.cream}"
    textColor: "{colors.bg}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-ghost:
    backgroundColor: "#FFFFFF0A"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "24px"
  input:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  label:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
---

# Design System: Grafik Pracy

## 1. Overview

**Creative North Star: „Pastelowy neon na czerni"**

Interfejs żyje na prawie-czarnym tle (`#1C1C1E`) i świeci pastelem. Cała tożsamość opiera się na jednym gescie: **miękkie, cukierkowe akcenty — mięta, cytryna, róż, krem — jarzą się na głębokiej czerni jak neon widziany po zamknięciu lokalu.** To nie jest „ciemny motyw, bo tak wygodnie". Ciemność jest sceną; pastel jest światłem. Ta polaryzacja — spokojna czerń, ciepłe pastele — daje efekt premium bez zimna korporacji i bez krzykliwości startupu.

Gęstość jest **komfortowa, nie ściśnięta**: dużo przestrzeni, wyraźny rytm, karty realnie uniesione nad tło. Komponenty są **dopracowane i spokojne** — miękkie pigułki, subtelny feedback przy naciśnięciu (scale 0.97), mocne krzywe ease-out zamiast odbić. Nic nie krzyczy; klasa bierze się z precyzji i powściągliwości, nie z liczby ozdób.

System **odrzuca** wprost: generyczny szablon SaaS 2026 (kremowe/beżowe tło, hero-metric, identyczne karty ikona+nagłówek, uppercase-eyebrow nad każdą sekcją, numerki 01/02/03), zimny ton korporacyjny (stockowe garnitury, puste hasła) oraz zabawowość startupu (tęczowe gradienty, emoji-driven, „🚀"). To narzędzie do zarządzania pieniędzmi i ludźmi realnego lokalu — powaga bez sztywności.

**Key Characteristics:**
- Prawie-czarne tło jako scena; pastele jako jedyne światło.
- Pastel używany **oszczędnie** — akcent, nie wypełnienie ekranu.
- Karty realnie uniesione (miękki cień), spokojna głębia.
- Typografia: grotesk display + neutralny sans body, mocny kontrast osi.
- Ruch celowy, mocny ease-out, zawsze z wariantem reduced-motion.

## 2. Colors

Ciemna, prawie-monochromatyczna baza z pięcioma pastelowymi akcentami, które są jedynym źródłem koloru — użyte rzadko i celowo.

### Primary
- **Krem** (`#F5F0E6`): kolor głównego CTA. Kremowa pigułka na czerni to najmocniejszy przycisk „zrób to teraz" (jak „TICKETS" z referencji). Zarezerwowany dla akcji nadrzędnej na ekranie.
- **Mięta** (`#A7D7C5`): kolor stanu i uwagi systemu — focus (obrys 2px), poświata aktywnych elementów, sygnał „to jest interaktywne / OK". Nasza barwa sygnałowa.

### Secondary
- **Cytryna** (`#F4E2A0`): pierwszy akcent gradientu, ostrzeżenia miękkie, wyróżnienia liczb/kwot dodatnich.
- **Róż** (`#F2B8CB`): trzeci akcent gradientu, akcent dekoracyjny i „delight", znaczniki premium/VIP.
- **Koral** (`#F2A2A2`): cieplejszy akcent ostrzegawczy, odróżnia się od twardego `danger`.

### Neutral
- **Ink** (`#F4F4F5`): tekst podstawowy. Prawie-biały, kontrast na `bg` ~16:1.
- **Muted** (`#A1A1AA`): tekst drugorzędny, etykiety, metadane. Nigdy dla treści krytycznej — kontrast ~7:1 na `bg`, wystarczający, ale to jest tekst pomocniczy.
- **Line** (`#FFFFFF14`, biel 8%): jedyny obrys/dzielnik. Delikatny, nigdy pełny biały.
- **Bg / Bg-elevated / Surface / Surface-raised** (`#1C1C1E` → `#232326` → `#2A2A2D` → `#323236`): czterostopniowa rampa ciemności budująca warstwy. Im wyżej w hierarchii, tym jaśniejsza powierzchnia.

### Tertiary (semantyka)
- **Success** (`#86E0B0`), **Danger** (`#F26D6D`), **Info** (`#8FBCFF`): stany komunikatów. Danger jest jedynym „głośnym" kolorem — używany wyłącznie dla błędów i zniszczeń.

### Named Rules
**Reguła Jednego Światła.** Pastel to światło na scenie — na dowolnym ekranie akcenty (krem/mięta/cytryna/róż/koral łącznie) pokrywają ≤15% powierzchni. Ich rzadkość jest sensem. Ekran w większości jest czernią i tekstem; pastel prowadzi wzrok do jednej-dwóch rzeczy.

**Reguła Gradientu-Akcentu.** Gradient `accent-gradient` (cytryna→mięta→róż) jest tożsamością marki (logo, aktywne elementy, wyróżnione CTA). Nigdy jako `background-clip: text` na zwykłych nagłówkach treści i nigdy jako duże tło sekcji — to znak rozpoznawczy, nie tapeta.

## 3. Typography

**Display Font:** Space Grotesk (z „Space Grotesk Fallback" o dopasowanych metrykach — zero CLS)
**Body Font:** Inter (z „Inter Fallback")

**Character:** Kontrast na osi charakteru, nie tylko wielkości. Space Grotesk — grotesk o lekko technicznym, „zaprojektowanym" sznycie — niesie nagłówki i markę. Inter — neutralny, humanistyczny, znakomicie czytelny — niesie całą treść i UI. Para działa, bo faktury są różne (grotesk vs. neutralny sans), nie dwa podobne geometryczne sansy.

### Hierarchy
- **Display** (700, `clamp(2.5rem, 6vw, 5rem)`, line-height 1.02, tracking -0.03em): hero landingu i wielkie liczby. Sufit ~5rem — strona ma projektować, nie krzyczeć.
- **Headline** (700, `clamp(1.75rem, 3vw, 2.5rem)`, 1.1, -0.02em): tytuły sekcji.
- **Title** (600, 1.25rem, 1.25): nagłówki kart i bloków (`font-display`).
- **Body** (400, 1rem, 1.6): treść. Długość wiersza ograniczona do 65–75ch dla czytelności.
- **Label** (600, 0.75rem, tracking 0.06em, UPPERCASE): etykiety pól, drobne metadane. Uppercase TYLKO tutaj — jako mikro-etykieta funkcjonalna, nigdy jako dekoracyjny eyebrow nad sekcją.

### Named Rules
**Reguła Dwóch Faktur.** Nagłówek zawsze Space Grotesk, treść zawsze Inter. Nie mieszać w obrębie jednej roli. `text-wrap: balance` na nagłówkach, `text-wrap: pretty` na dłuższej prozie.

## 4. Elevation

System jest **ciemny i realnie warstwowy** — „uniesione karty". Głębię budują dwa mechanizmy naraz: (1) rampa tonalna powierzchni (`bg` → `surface` → `surface-raised`) unosi elementy tonalnie, i (2) miękki cień pod kartami daje im fizyczne uniesienie nad tłem. Na wierzchu tego pastelowa **poświata** służy wyłącznie jako reakcja na akcent/stan (CTA, focus, aktywność) — świecenie, nie cień.

### Shadow Vocabulary
- **Soft** (`box-shadow: 0 10px 40px -12px rgba(0,0,0,0.55)`): domyślne uniesienie kart i modali nad ciemne tło. Głęboki, rozmyty, nisko osadzony.
- **Glow / mięta** (`box-shadow: 0 0 60px -10px rgba(167,215,197,0.25)`): poświata pod aktywnym/akcentowym elementem (mięta). Sygnał „to żyje".
- **CTA / krem** (`box-shadow: 0 8px 30px -8px rgba(245,240,230,0.35)`): ciepła poświata pod głównym kremowym CTA na hover.

### Named Rules
**Reguła Cień-vs-Poświata.** Czarny cień = fizyczne uniesienie (karty, modale). Kolorowa poświata = sygnał stanu/akcentu (CTA, focus, aktywne). Nie mieszać ról: karta w spoczynku nie świeci, CTA nie rzuca czarnego cienia.

## 5. Components

### Buttons
- **Shape:** miękka pigułka, promień 12px (`rounded-xl`), `font-semibold tracking-tight`, `transition ease-snap`, `active:scale-[0.97]`.
- **Primary:** kremowe wypełnienie (`#F5F0E6`) + ciemny tekst (`#1C1C1E`), padding `10px 20px` (md). Hover: ciepła poświata CTA + subtelny `brightness(1.03)`. Najmocniejszy przycisk — jeden nadrzędny na widok.
- **Accent (rzadko):** wypełnienie `accent-gradient` (cytryna→mięta→róż) + ciemny tekst — dla wyróżnionych, brandowych akcji.
- **Ghost / Subtle:** obrys `line` + tło `rgba(255,255,255,0.04)`, tekst `ink`/`muted`; hover rozjaśnia tło. Akcje drugorzędne.
- **Danger:** wypełnienie `#F26D6D` + biały tekst — tylko akcje destrukcyjne.

### Cards / Containers
- **Corner Style:** 16px (`rounded-2xl`).
- **Background:** subtelny pionowy gradient powierzchni (`surface-grad`: `#2A2A2D` → `#202022`) — daje karcie miękką objętość zamiast płaskiej płyty.
- **Shadow Strategy:** `soft` w spoczynku (uniesienie). Patrz Elevation.
- **Border:** 1px `line` (biel 8%).
- **Internal Padding:** 24–32px (`p-6`/`p-8`). **Nigdy nie zagnieżdżać kart w kartach.**

### Inputs / Fields
- **Style:** tło `surface-raised` (`#323236`), obrys `line`, promień 12px, padding `10px 16px`, tekst `ink`, placeholder `muted/50`.
- **Focus:** obrys przechodzi na miętę (`mint/60`) + pierścień `ring-2 ring-mint/20`. Spokojny, wyraźny.
- **Label:** `label` (uppercase, 0.75rem, tracking 0.06em, `muted`) nad polem.

### Navigation
- **Styl:** przewijany pasek pigułek. Aktywna zakładka: wypełnienie `accent-gradient` + ciemny tekst + `shadow-glow`. Nieaktywna: obrys `line`, tło `white/3%`, tekst `muted` → `ink` na hover.
- **Mobile:** poziomy scroll zakładek; dotykowe cele ≥44px.

### Focus (globalnie)
- **`:focus-visible`:** obrys 2px mięta, offset 2px, promień 8px. Nieusuwalny — dostępność klawiaturowa jest wymogiem.

## 6. Do's and Don'ts

### Do:
- **Do** trzymaj prawie-czarne tło (`#1C1C1E`) jako scenę i używaj pasteli jako światła — akcenty łącznie ≤15% powierzchni ekranu (Reguła Jednego Światła).
- **Do** rezerwuj kremowe CTA (`#F5F0E6`) dla JEDNEJ nadrzędnej akcji na widok; reszta to ghost/subtle.
- **Do** unoś karty realnie: `surface-grad` + cień `soft` + obrys `line` 1px.
- **Do** paruj Space Grotesk (nagłówki) z Inter (treść) — dwie różne faktury, nie dwa podobne sansy.
- **Do** dawaj każdej animacji wariant `@media (prefers-reduced-motion: reduce)` i mocny ease-out (`cubic-bezier(0.23,1,0.32,1)`), nie bounce.
- **Do** trzymaj focus miętowy (2px, offset 2px) na każdym elemencie interaktywnym.

### Don't:
- **Don't** rób generycznego szablonu SaaS 2026: żadnego kremowego/beżowego TŁA, hero-metric (wielka liczba + label), identycznych kart ikona+nagłówek w kółko, ani drobnego uppercase-eyebrow nad każdą sekcją, ani numerków 01/02/03 jako scaffoldu.
- **Don't** wpadaj w zimny ton korporacyjny — żadnych stockowych garniturów i pustych haseł („synergia", „empowering businesses"). Mów językiem kogoś, kto prowadził salę.
- **Don't** rób zabawki/startupu — żadnych tęczowych jaskrawych gradientów, emoji-driven nagłówków, „🚀".
- **Don't** używaj `background-clip: text` z gradientem na zwykłych nagłówkach treści — gradient akcentowy to znak marki (logo, aktywne), nie tapeta.
- **Don't** zagnieżdżaj kart w kartach i nie używaj kolorowych pasków `border-left`/`border-right` >1px jako akcentu.
- **Don't** rozlewaj pastelu na duże płaszczyzny — traci sens „neonu" i robi się cukierkowo.
