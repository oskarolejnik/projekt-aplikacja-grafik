// [7.5–18 s] Trzy funkcje: pulpit na żywo → rezerwacje 0% → wypłaty.
// Okna pojawiają się na miejscu (fade + scale); mikrointerakcje robią resztę.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { pojaw } from '../helpers/anim'
import { PulpitOkno, RezerwacjaOkno, WyplataOkno } from '../components/Okna'
import { Kinetic } from '../components/Kinetic'
import { C, F } from '../theme'
import { Scena } from './Scena'

const Podpis: FC<{ tekst: string; delay?: number }> = ({ tekst, delay = 44 }) => {
  const frame = useCurrentFrame()
  return (
    <div style={{ ...pojaw(frame, delay, 20, 0.99), marginTop: 14 }}>
      <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 25, color: C.muted }}>{tekst}</span>
    </div>
  )
}

export const S3Pulpit: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur}>
      <AbsoluteFill style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 90, padding: '0 110px' }}>
        <div style={{ width: 560 }}>
          <Kinetic text="Liczby na żywo." size={78} delay={10} stagger={4} align="left" />
          <Podpis tekst="przychód · ruch · koszt pracy — bez dzwonienia na zmianę" delay={34} />
        </div>
        <div style={pojaw(frame, 4, 26)}>
          <PulpitOkno w={900} start={14} />
        </div>
      </AbsoluteFill>
    </Scena>
  )
}

export const S3Rezerwacje: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur}>
      <AbsoluteFill style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 90, padding: '0 110px' }}>
        <div style={pojaw(frame, 4, 26)}>
          <RezerwacjaOkno w={640} start={12} />
        </div>
        <div style={{ width: 620 }}>
          <Kinetic text="Rezerwacje online." size={78} delay={10} stagger={4} align="left" />
          <div style={{ marginTop: 6 }}>
            <Kinetic text="0% prowizji." size={78} delay={24} stagger={4} align="left" color={C.zloto2} />
          </div>
          <Podpis tekst="widget na Twojej stronie · SMS + e-mail · CRM gościa" delay={44} />
        </div>
      </AbsoluteFill>
    </Scena>
  )
}

export const S3Wyplaty: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur}>
      <AbsoluteFill style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 90, padding: '0 110px' }}>
        <div style={{ width: 560 }}>
          <Kinetic text="Wypłaty co do minuty." size={78} delay={10} stagger={4} align="left" />
          <Podpis tekst="RCP → godziny → kwota · portfel pracownika na żywo" delay={36} />
        </div>
        <div style={pojaw(frame, 4, 26)}>
          <WyplataOkno w={640} start={12} />
        </div>
      </AbsoluteFill>
    </Scena>
  )
}
