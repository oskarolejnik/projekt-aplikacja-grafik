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
        'page-glow': 'linear-gradient(120deg,#bfe3cd 0%,#f4e7c6 45%,#f1c2d2 100%)',
        'surface-grad': 'linear-gradient(160deg,#2A2A2D 0%,#202022 100%)',
      },
      keyframes: {
        spinOrbit: { '0%': { transform: 'rotate(0deg)' }, '100%': { transform: 'rotate(360deg)' } },
        spinOrbitRev: { '0%': { transform: 'rotate(360deg)' }, '100%': { transform: 'rotate(0deg)' } },
        float: { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-10px)' } },
        fadeIn: { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        // Kierunkowe wejście widoku przy przełączaniu zakładek (dyspozycyjność ↔ grafik)
        slideInR: { '0%': { opacity: '0', transform: 'translateX(12px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        slideInL: { '0%': { opacity: '0', transform: 'translateX(-12px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
      },
      animation: {
        'spin-orbit': 'spinOrbit 48s linear infinite',
        'spin-orbit-rev': 'spinOrbitRev 60s linear infinite',
        float: 'float 7s ease-in-out infinite',
        'fade-in': 'fadeIn 0.3s ease both',
        'slide-in-r': 'slideInR 0.28s ease both',
        'slide-in-l': 'slideInL 0.28s ease both',
      },
    },
  },
  plugins: [],
}
