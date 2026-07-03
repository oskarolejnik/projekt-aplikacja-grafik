// [5.7–13.2 s] Trzy szybkie feature'y: pulpit na żywo → rezerwacje 0% → wypłaty.
// Dynamiczna zmiana stron (okno raz z lewej, raz z prawej), kamera zawsze płynie.
import type { FC } from 'react'
import { AbsoluteFill, useCurrentFrame } from 'remotion'
import { wjazd } from '../helpers/anim'
import { PulpitOkno, RezerwacjaOkno, WyplataOkno } from '../components/Okna'
import { Kinetic } from '../components/Kinetic'
import { C, F } from '../theme'
import { Scena } from './Scena'

const Podpis: FC<{ tekst: string; delay?: number }> = ({ tekst, delay = 34 }) => {
  const frame = useCurrentFrame()
  return (
    <div style={{ ...wjazd(frame, delay, 14, 'up', 30), marginTop: 14 }}>
      <span style={{ fontFamily: F.body, fontWeight: 600, fontSize: 25, color: C.muted }}>{tekst}</span>
    </div>
  )
}

export const S3Pulpit: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur} odSkali={1.04} doSkali={1.1} panX={26}>
      <AbsoluteFill style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 90, padding: '0 110px' }}>
        <div style={{ width: 560 }}>
          <Kinetic text="Liczby na żywo." size={78} delay={6} align="left" />
          <Podpis tekst="przychód · ruch · koszt pracy — bez dzwonienia na zmianę" delay={22} />
        </div>
        <div style={wjazd(frame, 2, 18, 'left', 200)}>
          <PulpitOkno w={900} start={8} />
        </div>
      </AbsoluteFill>
    </Scena>
  )
}

export const S3Rezerwacje: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur} odSkali={1.04} doSkali={1.1} panX={-26}>
      <AbsoluteFill style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 90, padding: '0 110px' }}>
        <div style={wjazd(frame, 2, 18, 'right', 200)}>
          <RezerwacjaOkno w={640} start={6} />
        </div>
        <div style={{ width: 620 }}>
          <Kinetic text="Rezerwacje online." size={78} delay={6} align="left" />
          <div style={{ marginTop: 6 }}>
            <Kinetic text="0% prowizji." size={78} delay={16} align="left" color={C.zloto2} />
          </div>
          <Podpis tekst="widget na Twojej stronie · SMS + e-mail · CRM gościa" delay={30} />
        </div>
      </AbsoluteFill>
    </Scena>
  )
}

export const S3Wyplaty: FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame()
  return (
    <Scena dur={dur} odSkali={1.04} doSkali={1.1} panY={-18}>
      <AbsoluteFill style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 90, padding: '0 110px' }}>
        <div style={{ width: 560 }}>
          <Kinetic text="Wypłaty co do minuty." size={78} delay={6} align="left" />
          <Podpis tekst="RCP → godziny → kwota · portfel pracownika na żywo" delay={24} />
        </div>
        <div style={wjazd(frame, 2, 18, 'left', 200)}>
          <WyplataOkno w={640} start={6} />
        </div>
      </AbsoluteFill>
    </Scena>
  )
}
