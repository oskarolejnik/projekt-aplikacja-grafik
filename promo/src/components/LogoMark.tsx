// PRAWDZIWY znak Lokalo — 1:1 z brand/lokalo-icon.svg (i Logo.jsx w aplikacji):
// gradientowy kafel mięta→cytryna→róż, monogram L i DUŻY punkt akcentu
// (talerz/miejsce). Inline SVG, bez plików zewnętrznych.
import type { FC } from 'react'

export const LogoMark: FC<{ size?: number }> = ({ size = 120 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 64 64"
    xmlns="http://www.w3.org/2000/svg"
    role="img"
    aria-label="Lokalo"
    style={{ filter: 'drop-shadow(0 24px 48px rgba(0,0,0,0.55))' }}
  >
    <defs>
      <linearGradient id="lokaloTilePromo" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#A7D7C5" />
        <stop offset="0.52" stopColor="#F4E2A0" />
        <stop offset="1" stopColor="#F2A2A2" />
      </linearGradient>
    </defs>
    <rect x="0" y="0" width="64" height="64" rx="15" fill="url(#lokaloTilePromo)" />
    <path d="M21 16 H28.5 V41 H45 V48.5 H21 Z" fill="#1C1C1E" />
    <circle cx="43.5" cy="21.5" r="4.6" fill="#1C1C1E" />
  </svg>
)
