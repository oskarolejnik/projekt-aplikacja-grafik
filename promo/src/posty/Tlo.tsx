// Wspólna scena postów Instagram 4:5 (1080×1350): noc + złote światło + winieta.
// Posty są STATYCZNE (render przez `remotion still`) — bez animacji.
import type { FC, ReactNode } from 'react'
import { AbsoluteFill } from 'remotion'
import { C } from '../theme'

export const Tlo: FC<{ children: ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: C.noc }}>
    <AbsoluteFill
      style={{
        background: `
          radial-gradient(820px 640px at 50% -6%, rgba(201,169,106,0.08), transparent 62%),
          radial-gradient(720px 560px at 50% 106%, rgba(201,169,106,0.05), transparent 65%),
          radial-gradient(640px 460px at 90% 30%, rgba(255,255,255,0.035), transparent 60%)
        `,
      }}
    />
    <AbsoluteFill style={{ padding: '90px 72px' }}>{children}</AbsoluteFill>
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background: 'radial-gradient(115% 100% at 50% 50%, transparent 68%, rgba(0,0,0,0.42) 100%)',
      }}
    />
  </AbsoluteFill>
)

// Stopka posta: znak + nazwa — spójna sygnatura karuzeli.
export { C }
