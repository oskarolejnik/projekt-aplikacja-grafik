---
name: Lokalo
description: System operacyjny dla lokalu gastro — „Cicha scena" (ciemny premium)
colors:
  ink: "#F4F4F5"
  muted: "#A1A1AA"
  bg: "#1C1C1E"
  bg-elevated: "#232326"
  surface: "#2A2A2D"
  surface-raised: "#323236"
  line: "#FFFFFF14"
  cream: "#F4F4F5"
  mint: "#9DC4B1"
  lemon: "#E8D9A8"
  coral: "#DFA9A2"
  success: "#8AD3AC"
  danger: "#F26D6D"
  info: "#9BBBE3"
typography:
  display:
    fontFamily: "\"Space Grotesk\", \"Space Grotesk Fallback\", ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2.25rem, 5vw, 4rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "\"Space Grotesk\", \"Space Grotesk Fallback\", sans-serif"
    fontSize: "clamp(1.5rem, 2.5vw, 2rem)"
    fontWeight: 600
    lineHeight: 1.15
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
    backgroundColor: "{colors.bg-elevated}"
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

# Design System: Lokalo

## 1. Overview

**Creative North Star: „Cicha scena"**

Interfejs żyje na prawie-czarnej scenie (`#1C1C1E` — ta sama baza co systemowy ciemny motyw
Apple) i mówi **typografią, światłem i rytmem — nie kolorem**. Poprzednia tożsamość („pastelowy
neon na czerni") została świadomie wyciszona: klasa nie bierze się z tego, co dodane, tylko z tego,
co odjęte. Zero gradientów w UI. Zero poświat. Zero dekoracyjnego ruchu. Jeden spokojny akcent —
**szałwiowa mięta** wyprowadzona z logo Lokalo — używany wyłącznie tam, gdzie niesie znaczenie:
selekcja, fokus, akcja brandowa.

Filtr każdej decyzji projektowej: **„Czy Apple by to shipnęło?"** Jeśli element czegoś nie
komunikuje — znika. Jeśli krzyczy — cichnie. Jeśli da się to samo osiągnąć hierarchią typografii
zamiast kolorem — wybieramy typografię. Narzędzie ma zniknąć w zadaniu; premium poznaje się po tym,
że nic nie zgrzyta.

Gradient marki (mięta→cytryna→koral) żyje **wyłącznie w znaku logo** — jak kolorowa ikona
aplikacji na spokojnym pulpicie macOS. Nigdy w komponentach.

**Key Characteristics:**
- Prawie-czarna scena; głębia budowana warstwami powierzchni i dyskretnym cieniem.
- Jeden akcent (szałwia `#9DC4B1`) — tylko selekcja, fokus, akcje brandowe.
- Primary CTA neutralne: jasna „papierowa" pigułka (`#F4F4F5`) z ciemnym tekstem.
- Typografia-first: hierarchia wagą i wielkością, nie kolorem i dekoracją.
- Ruch komunikuje stan (150–300 ms, ease-out, zero odbić); nigdy nie dekoruje.

## 2. Colors

Prawie-monochromatyczna rampa ciemności + jeden akcent + semantyka. Kolor jest informacją;
wszystko, co nie informuje, jest neutralne.

### Primary
- **Paper** (`#F4F4F5`): kolor głównego CTA — jasna pigułka na ciemnej scenie. Jedna nadrzędna
  akcja na widok. To także `ink` (tekst podstawowy) — jedna neutralna oś światła.
- **Szałwia** (`#9DC4B1`): jedyny niesemantyczny kolor systemu. Fokus (obrys 2px), aktywna pozycja
  nawigacji (tinta 12% + tekst szałwiowy), akcje brandowe. Kontrast na `bg` ~8.5:1.

### Neutral
- **Ink** (`#F4F4F5`): tekst podstawowy, kontrast ~15:1.
- **Muted** (`#A1A1AA`): tekst drugorzędny, etykiety, metadane (~7:1). Nigdy dla treści krytycznej.
- **Line** (`#FFFFFF14`, biel 8%): jedyny obrys/dzielnik — włoskowaty, nigdy pełna biel.
- **Bg → Bg-elevated → Surface → Surface-raised** (`#1C1C1E` → `#232326` → `#2A2A2D` → `#323236`):
  czterostopniowa rampa warstw. Im bliżej użytkownika, tym jaśniej — jak w ciemnym trybie iOS.

### Tertiary (semantyka — wyciszona)
- **Success** (`#8AD3AC`), **Danger** (`#F26D6D`), **Info** (`#9BBBE3`): stany komunikatów.
  Danger jest jedynym „głośnym" kolorem — wyłącznie błędy i akcje destrukcyjne.
- **Lemon** (`#E8D9A8`), **Coral** (`#DFA9A2`): miękkie ostrzeżenia i dane (kwoty, statusy
  w tabelach). Nigdy dekoracja.

### Named Rules
**Reguła Jednego Akcentu.** Szałwia to jedyny kolor „od marki" w UI. Na dowolnym ekranie kolor
niesemantyczny pokrywa ≤5% powierzchni. Jeśli element nie jest wybrany, aktywny albo fokusowany —
nie ma koloru.

**Reguła Gradientu-w-Logo.** Gradient marki istnieje tylko w znaku logo (SVG ikony). W komponentach,
tłach, tekstach i wskaźnikach — nigdy. Klasy `accent-gradient`/`text-gradient` istnieją wyłącznie
jako zneutralizowana siatka bezpieczeństwa (jednolita szałwia / jednolity ink).

## 3. Typography

**Display Font:** Space Grotesk (fallback o dopasowanych metrykach — zero CLS)
**Body Font:** Inter (fallback jw.)

**Character:** Inter niesie całe UI — to najbliższy wolny odpowiednik SF Pro: neutralny,
znakomicie czytelny, natywny w odbiorze. Space Grotesk pojawia się oszczędnie: nagłówki stron
i sekcji oraz momenty marki (logowanie, landing). Hierarchię buduje **waga i wielkość**, nie kolor.

### Hierarchy
- **Display** (700, `clamp(2.25rem, 5vw, 4rem)`, 1.05, -0.03em): wyłącznie hero landingu.
- **Headline** (600, `clamp(1.5rem, 2.5vw, 2rem)`, 1.15, -0.02em): tytuły sekcji landingu.
- **Title** (600, 1.25rem): nagłówki widoków w aplikacji (`font-display`).
- **Section** (600, 1.125–1.25rem, tracking -0.01em): nagłówki kart (SectionHeader).
- **Body** (400, 1rem, 1.6): treść; wiersz ≤72ch.
- **Label** (600, 0.75rem, tracking 0.06em, uppercase): etykiety pól i nagłówki grup w nawigacji —
  natywny wzorzec sekcji iOS. Uppercase TYLKO w tej roli, nigdy na przyciskach.

### Named Rules
**Reguła Spokojnej Wagi.** Kontrolki (przyciski, taby, segmenty) mają `font-semibold` — nigdy bold.
Bold zarezerwowany dla nagłówków display/headline. Duży tekst nigdy nie jest uppercase.

## 4. Elevation — „szkło i światło" (v2.1)

Głębia = **szkło + monochromatyczne światło sceny + dyskretny cień**. Żadnych kolorowych poświat.
Ewolucja v2.1 (07.2026, na życzenie właściciela wg referencji noir-glass): powierzchnie treści
stały się szkłem, chrome i modale — materiałem z prawdziwym rozmyciem, a scena dostała statyczne,
białe światło, które nadaje szkłu rację bytu.

### Materiały (index.css)
- **`.card` — szkło treści**: obrys `white/8%`, mgiełka `white/3%`, wewnętrzna kreska światła
  `inset 0 1px 0 white/6%` + cień soft. **Celowo BEZ backdrop-blur** — dziesiątki rozmywających
  kart na ekranie kosztowałyby GPU; szkło czyta się z obrysu, mgiełki i kreski światła.
- **`.material` — materiał chrome/modali**: jak `.card`, ale z prawdziwym `backdrop-blur(20px)`
  i głębszym cieniem. Wyłącznie: paski (header/sidebar — tam wariant `bg-bg/55–70 + blur-xl/2xl`),
  modale, toasty, elementy pływające, sekcja cennika na landingu. Dokładnie jak materiały Apple.
- **`.scena-swiatlo` — światło sceny**: dwa statyczne radialne rozjaśnienia bieli (≤4%), fixed,
  bez animacji. To JEDYNY usankcjonowany „gradient" systemu — światło, nie kolor.

### Shadow Vocabulary
- **Soft** (`0 1px 2px rgba(0,0,0,0.28), 0 12px 32px -16px rgba(0,0,0,0.55)`): dwuwarstwowy —
  krótki cień kontaktowy + miękkie otoczenie (wbudowany w `.card`).
- **Cta** (`0 2px 12px -4px rgba(0,0,0,0.45)`): drobne uniesienie wskaźnika segmented control.
- Hover pogłębia cień przez **offset/blur, nigdy przez ciemność** (alfa zostaje 0.55).

### Named Rules
**Reguła Bez Poświat.** Kolorowy `box-shadow` (glow) nie istnieje w systemie. Stan komunikują:
tinta tła (selekcja), obrys (fokus), waga tekstu (aktywność).
**Reguła Materiału.** Prawdziwe rozmycie (`backdrop-blur`) tylko tam, gdzie coś realnie „pod spodem"
się przewija lub prześwituje: chrome, modale, pływające pigułki. Treść = `.card` bez blur.
**Reguła Światła.** Światło sceny jest monochromatyczne, statyczne i ≤4% bieli. Kolorowe/duszące
bloby i animowane poświaty pozostają zakazane.

## 5. Components

### Buttons
- **Shape:** promień 12px, `font-semibold`, sentence case, `transition ease-snap`,
  `active:scale-[0.98]` (dyskretny docisk).
- **Primary (paper):** `#F4F4F5` + ciemny tekst; hover → czysta biel. Jedna nadrzędna akcja na widok.
- **Accent (szałwia, rzadko):** `bg-mint` + ciemny tekst — akcje brandowe.
- **Ghost / Subtle:** obrys `line` + tło `white/4%`; hover `white/8%`. Akcje drugorzędne.
- **Danger:** `#F26D6D` + biały tekst — tylko destrukcja.
- Stany: default, hover, focus-visible (szałwiowy obrys), active, disabled (opacity 50) — komplet.

### Cards / Containers
- **Corner Style:** 16px. **Materiał:** `.card` (szkło: obrys white/8%, mgiełka white/3%,
  kreska światła 1px inset, cień soft — bez blur). Modale/pływające: `.material` (z blur).
- **Padding:** 24–32px. **Nigdy karta w karcie.**

### Inputs / Fields
- Tło `surface-raised`, obrys `line`, promień 12px, tekst `ink`, placeholder `muted/50`.
- **Focus:** obrys szałwiowy (`mint/60`) + pierścień `ring-2 ring-mint/20`. Spokojny, wyraźny.
- **Label:** uppercase 0.75rem `muted` nad polem (wzorzec formularzy iOS).

### Navigation (sidebar)
- Pozycja aktywna: **tinta szałwii 12% + szałwiowy tekst + font-semibold** — jak selekcja
  w sidebarze iPadOS. Nieaktywna: `muted`, hover `white/5%` + `ink`.
- Nagłówki grup: label uppercase `muted/70`.
- Chrome (sidebar, header) na `bg-2` z `backdrop-blur` — translucentny pasek natywny.

### Segmented control (PillSwitch)
- Kontener: obrys `line`, tło `white/3%`. Wskaźnik: `surface-raised` + cień `cta`,
  przesuw `transform` 280 ms krzywą szuflady iOS (bez odbicia). Aktywny tekst: `ink`.

### Focus (globalnie)
- **`:focus-visible`:** obrys 2px szałwia, offset 2px. Nieusuwalny.

## 6. Motion

Filozofia: **ruch = komunikat o stanie.** Wejście treści, feedback dotyku, przesunięcie wskaźnika,
pojawienie modala/toastu. Nic poza tym — żadnych dryfujących blobów, unoszenia, animowanych
gradientów, orbit.

- Czasy 150–300 ms; wejścia zakładek 240 ms; krzywe `ease-snap` (silny ease-out) i `ease-drawer`
  (szuflada iOS). **Zero bounce/elastic** — sprężyny Framer Motion z `bounce: 0–0.05`.
- Feedback dotyku: `active:scale-[0.98]` — docisk, nie zabawka.
- Każda animacja ma wariant `prefers-reduced-motion: reduce` (globalny reset w index.css).
- Landing (powierzchnia marki) może mieć choreografię scrolla (reveals, Lenis) — ale tym samym
  słownikiem: fade+translate, bez neonu.

## 7. Do's and Don'ts

### Do:
- **Do** buduj hierarchię typografią (waga, wielkość, `muted` vs `ink`) zanim sięgniesz po kolor.
- **Do** trzymaj szałwię wyłącznie na selekcji, fokusie i akcjach brandowych (≤5% ekranu).
- **Do** rezerwuj papierowe CTA dla JEDNEJ nadrzędnej akcji na widok; reszta ghost/subtle.
- **Do** unoś karty rampą tonalną + cieniem `soft` + obrysem `line` 1px.
- **Do** używaj translucentnego chrome (`bg-2` + blur) na paskach — natywne, nie „szklane karty".
- **Do** dawaj każdemu ruchowi powód (stan) i wariant reduced-motion.

### Don't:
- **Don't** używaj gradientów w UI — ani w tle, ani w tekście, ani we wskaźnikach. Gradient żyje w logo.
- **Don't** dodawaj kolorowych poświat (`glow`) — elewacja tylko czarnym, dyskretnym cieniem.
- **Don't** pisz uppercase na przyciskach ani rozstrzelonych nagłówkach — uppercase tylko w mikro-etykietach.
- **Don't** animuj dekoracyjnie (dryf, float, orbity, animowane gradienty) — ruch bez komunikatu to szum.
- **Don't** zagnieżdżaj kart w kartach; nie używaj pasków `border-left/right` >1px jako akcentu.
- **Don't** stosuj bounce/overshoot — krzywe wyłącznie ease-out; „premium" osiada, nie odbija się.
- **Don't** wracaj do neonu: pastelowe akcenty rozlane po ekranie to poprzednia epoka tego produktu.
