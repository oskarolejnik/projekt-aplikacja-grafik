/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Tła i powierzchnie — „Cicha scena" (ciemny premium, rampa jak w iOS dark)
        bg: '#1C1C1E',
        'bg-2': '#232326',
        surface: '#2A2A2D',
        'surface-2': '#323236',
        line: 'rgba(255,255,255,0.08)',
        // Tekst
        ink: '#F4F4F5',
        muted: '#A1A1AA',
        // Akcent marki: szałwiowa mięta — JEDYNY kolor niesemantyczny w UI.
        // Reszta dawnych pasteli zdegradowana do ról semantycznych i wyciszona.
        cream: '#F4F4F5',      // dawny warm-CTA → neutralny „paper" (primary button)
        mint: '#9DC4B1',       // szałwia — akcent, focus, selekcja
        lemon: '#E8D9A8',      // wyciszona — tylko semantyka „uwaga/kwota"
        blush: '#C9B6C1',      // wyciszona — resztkowe użycia dekoracyjne gasną
        coral: '#DFA9A2',      // wyciszona — miękkie ostrzeżenie
        success: '#8AD3AC',
        danger: '#F26D6D',
        info: '#9BBBE3',
      },
      fontFamily: {
        display: ['"Space Grotesk"', '"Space Grotesk Fallback"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['Inter', '"Inter Fallback"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        // Dwuwarstwowy, dyskretny cień (kontakt + otoczenie) — zamiast dramatycznego halo.
        soft: '0 1px 2px rgba(0,0,0,0.28), 0 12px 32px -16px rgba(0,0,0,0.55)',
        // Dawne poświaty — zneutralizowane do zwykłej elewacji (siatka bezpieczeństwa,
        // docelowo klasy shadow-glow/shadow-cta znikają z użycia).
        glow: '0 1px 2px rgba(0,0,0,0.28), 0 12px 32px -16px rgba(0,0,0,0.55)',
        cta: '0 2px 12px -4px rgba(0,0,0,0.45)',
      },
      backgroundImage: {
        // Gradienty marki zneutralizowane: jednolita szałwia (siatka bezpieczeństwa —
        // docelowo użycia zamienione na bg-mint / tinty). Gradient żyje tylko w logo.
        'accent-gradient': 'linear-gradient(90deg,#9DC4B1,#9DC4B1)',
        'accent-flow': 'linear-gradient(90deg,#9DC4B1,#9DC4B1)',
        'page-glow': 'radial-gradient(closest-side, rgba(157,196,177,0.05), transparent)',
        // Ledwo zauważalna objętość karty (Apple-like) zamiast wyraźnego gradientu.
        'surface-grad': 'linear-gradient(180deg,#26262A 0%,#222225 100%)',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        // Wejście treści/karty (stagger) — nigdy ze scale(0); subtelny translateY + opacity
        fadeUp: { '0%': { opacity: '0', transform: 'translateY(8px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        // Kierunkowe wejście widoku przy przełączaniu zakładek (dyspozycyjność ↔ grafik)
        slideInR: { '0%': { opacity: '0', transform: 'translateX(10px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        slideInL: { '0%': { opacity: '0', transform: 'translateX(-10px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        // Modal: skalowanie od środka — start scale(0.97), nie 0
        modalIn: { '0%': { opacity: '0', transform: 'scale(0.97) translateY(4px)' }, '100%': { opacity: '1', transform: 'scale(1) translateY(0)' } },
        overlayIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        // Toast: zjazd z góry + lekka skala
        toastIn: { '0%': { opacity: '0', transform: 'translateY(-10px) scale(0.97)' }, '100%': { opacity: '1', transform: 'translateY(0) scale(1)' } },
        // Wejście treści zakładki — krótkie, bez teatru (użytkownik jest w zadaniu).
        tabIn: { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
      },
      // Mocne krzywe ease-out (bez odbić i elastyczności)
      transitionTimingFunction: {
        snap: 'cubic-bezier(0.23, 1, 0.32, 1)', // silny ease-out (wejścia, feedback)
        drawer: 'cubic-bezier(0.32, 0.72, 0, 1)', // krzywa szuflady iOS
        smooth: 'cubic-bezier(0.77, 0, 0.175, 1)', // ruch po ekranie
      },
      animation: {
        'fade-in': 'fadeIn 0.24s cubic-bezier(0.23, 1, 0.32, 1) both',
        'fade-up': 'fadeUp 0.26s cubic-bezier(0.23, 1, 0.32, 1) both',
        'slide-in-r': 'slideInR 0.22s cubic-bezier(0.23, 1, 0.32, 1) both',
        'slide-in-l': 'slideInL 0.22s cubic-bezier(0.23, 1, 0.32, 1) both',
        'modal-in': 'modalIn 0.22s cubic-bezier(0.23, 1, 0.32, 1) both',
        'overlay-in': 'overlayIn 0.18s ease-out both',
        'toast-in': 'toastIn 0.24s cubic-bezier(0.23, 1, 0.32, 1) both',
        'tab-in': 'tabIn 0.24s cubic-bezier(0.23, 1, 0.32, 1) both',
      },
    },
  },
  plugins: [],
}
