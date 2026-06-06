/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Tła i powierzchnie (ciemny motyw "Creativity")
        bg: '#1C1C1E',
        'bg-2': '#232326',
        surface: '#2A2A2D',
        'surface-2': '#323236',
        line: 'rgba(255,255,255,0.08)',
        // Tekst
        ink: '#F4F4F5',
        muted: '#A1A1AA',
        // Akcenty pastelowe z referencji
        cream: '#F5F0E6',
        mint: '#A7D7C5',
        lemon: '#F4E2A0',
        blush: '#F2B8CB',
        coral: '#F2A2A2',
        // Semantyka (zachowana z poprzedniej aplikacji, dostrojona do ciemnego tła)
        success: '#86E0B0',
        danger: '#F26D6D',
        info: '#8FBcff',
      },
      fontFamily: {
        display: ['"Space Grotesk"', '"Space Grotesk Fallback"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['Inter', '"Inter Fallback"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 10px 40px -12px rgba(0,0,0,0.55)',
        glow: '0 0 60px -10px rgba(167,215,197,0.25)',
        cta: '0 8px 30px -8px rgba(245,240,230,0.35)',
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(90deg,#F4E2A0,#A7D7C5,#F2B8CB)',
        // Symetryczny wariant (złoto→mięta→róż→mięta→złoto) — przy background-size 200%
        // i przesuwaniu pozycji kolory płynnie „kołyszą się" bez szwu na zapętleniu.
        'accent-flow': 'linear-gradient(90deg,#F4E2A0,#A7D7C5,#F2B8CB,#A7D7C5,#F4E2A0)',
        'page-glow': 'linear-gradient(120deg,#bfe3cd 0%,#f4e7c6 45%,#f1c2d2 100%)',
        'surface-grad': 'linear-gradient(160deg,#2A2A2D 0%,#202022 100%)',
      },
      keyframes: {
        spinOrbit: { '0%': { transform: 'rotate(0deg)' }, '100%': { transform: 'rotate(360deg)' } },
        spinOrbitRev: { '0%': { transform: 'rotate(360deg)' }, '100%': { transform: 'rotate(0deg)' } },
        float: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-10px)' } },
        fadeIn: { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        // Wejście treści/karty (stagger) — nigdy ze scale(0); subtelny translateY + opacity
        fadeUp: { '0%': { opacity: '0', transform: 'translateY(10px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        // Kierunkowe wejście widoku przy przełączaniu zakładek (dyspozycyjność ↔ grafik)
        slideInR: { '0%': { opacity: '0', transform: 'translateX(12px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        slideInL: { '0%': { opacity: '0', transform: 'translateX(-12px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        // Modal: skalowanie od środka (modale wyjątek od origin-aware) — start scale(0.96), nie 0
        modalIn: { '0%': { opacity: '0', transform: 'scale(0.96) translateY(6px)' }, '100%': { opacity: '1', transform: 'scale(1) translateY(0)' } },
        overlayIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        // Toast: zjazd z góry + lekka skala (spójnie z pozycją top-right)
        toastIn: { '0%': { opacity: '0', transform: 'translateY(-12px) scale(0.96)' }, '100%': { opacity: '1', transform: 'translateY(0) scale(1)' } },
        // Wejście treści zakładki (CSS, bez rAF) — fade + lekki scale/y, gładki ease-out.
        tabIn: { '0%': { opacity: '0', transform: 'translateY(12px) scale(0.985)' }, '100%': { opacity: '1', transform: 'translateY(0) scale(1)' } },
        // Delikatne przesuwanie pozycji gradientu (kołysanie kolorów na logo i zegarze)
        gradientFlow: { '0%': { backgroundPosition: '0% 50%' }, '100%': { backgroundPosition: '100% 50%' } },
        // Powolny, organiczny dryf poświat w tle ekranu logowania (różne tory = brak rytmu)
        driftA: {
          '0%, 100%': { transform: 'translate3d(0,0,0) scale(1)' },
          '33%': { transform: 'translate3d(52px,34px,0) scale(1.12)' },
          '66%': { transform: 'translate3d(26px,-30px,0) scale(0.95)' },
        },
        driftB: {
          '0%, 100%': { transform: 'translate3d(0,0,0) scale(1)' },
          '50%': { transform: 'translate3d(-48px,-38px,0) scale(1.1)' },
        },
      },
      // Mocne krzywe wg Emila Kowalskiego (domyślne CSS są za słabe)
      transitionTimingFunction: {
        snap: 'cubic-bezier(0.23, 1, 0.32, 1)', // silny ease-out (wejścia, feedback)
        drawer: 'cubic-bezier(0.32, 0.72, 0, 1)', // krzywa szuflady iOS
        smooth: 'cubic-bezier(0.77, 0, 0.175, 1)', // ruch po ekranie
      },
      animation: {
        'spin-orbit': 'spinOrbit 48s linear infinite',
        'spin-orbit-rev': 'spinOrbitRev 60s linear infinite',
        // Skrzydła wiatraka w logo — powolny, równy obrót wokół piasty
        windmill: 'spinOrbit 12s linear infinite',
        float: 'float 7s ease-in-out infinite',
        'fade-in': 'fadeIn 0.3s cubic-bezier(0.23, 1, 0.32, 1) both',
        'fade-up': 'fadeUp 0.32s cubic-bezier(0.23, 1, 0.32, 1) both',
        'slide-in-r': 'slideInR 0.26s cubic-bezier(0.23, 1, 0.32, 1) both',
        'slide-in-l': 'slideInL 0.26s cubic-bezier(0.23, 1, 0.32, 1) both',
        'modal-in': 'modalIn 0.24s cubic-bezier(0.23, 1, 0.32, 1) both',
        'overlay-in': 'overlayIn 0.2s ease-out both',
        'toast-in': 'toastIn 0.28s cubic-bezier(0.23, 1, 0.32, 1) both',
        'tab-in': 'tabIn 0.42s cubic-bezier(0.23, 1, 0.32, 1) both',
        // Łagodne kołysanie gradientu w obie strony (logo + zegar) — trochę żywsze
        'gradient-flow': 'gradientFlow 7s ease-in-out infinite alternate',
        // Dryf poświat w tle (kompozytor — transform 3d, płynnie)
        'drift-a': 'driftA 20s ease-in-out infinite',
        'drift-b': 'driftB 16s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
