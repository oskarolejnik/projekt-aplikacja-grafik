import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Float, Environment, Lightformer } from '@react-three/drei'

// Ambientowa scena 3D hero „Lokalo Noir" — kilka fasetowanych, kutych ze złota brył
// (metafora „złotej nitki" marki jako fizyczne odłamki światła) powoli dryfujących w głębi.
// SUBTELNA: niska nieprzezroczystość, brak postprocessingu, tanie materiały. Ten plik jest
// ŁADOWANY LENIWIE (React.lazy) — three.js nie wchodzi do initial bundle. Renderowana tylko
// na desktopie z WebGL i bez reduced-motion (bramka w Ambient3D.jsx). Płótno przezroczyste.

function Odlamek({ position, scale, rot, speed = 1, detail = 0, color = '#C9A96A', roughness = 0.3 }) {
  const ref = useRef()
  useFrame((_, dt) => {
    if (!ref.current) return
    // Bardzo powolny obrót — ma sprawiać wrażenie „prawie nieruchomego" (nie latać).
    ref.current.rotation.x += dt * 0.018 * speed
    ref.current.rotation.y += dt * 0.024 * speed
  })
  return (
    <Float speed={0.5 * speed} rotationIntensity={0.15} floatIntensity={0.3}>
      <mesh ref={ref} position={position} scale={scale} rotation={rot}>
        <icosahedronGeometry args={[1, detail]} />
        <meshStandardMaterial color={color} metalness={1} roughness={roughness} flatShading />
      </mesh>
    </Float>
  )
}

function Piescien() {
  const ref = useRef()
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.z += dt * 0.015 })
  return (
    <Float speed={0.35} rotationIntensity={0.1} floatIntensity={0.25}>
      <mesh ref={ref} position={[1.8, -0.5, -2.4]} rotation={[1.1, 0.3, 0]}>
        <torusGeometry args={[1.6, 0.045, 24, 96]} />
        <meshStandardMaterial color="#E7CF9B" metalness={1} roughness={0.22} />
      </mesh>
    </Float>
  )
}

export default function Scene({ frameloop = 'always' }) {
  return (
    <Canvas
      frameloop={frameloop}
      dpr={[1, 1.5]}
      gl={{ alpha: true, antialias: true, powerPreference: 'high-performance' }}
      camera={{ position: [0, 0, 6], fov: 42 }}
      style={{ background: 'transparent' }}
    >
      <ambientLight intensity={0.3} />
      <directionalLight position={[3, 4, 2]} intensity={1.0} color="#E7CF9B" />
      <pointLight position={[-4, -2, 1]} intensity={14} color="#5EA8FF" distance={14} />

      {/* Mniej brył, dalej w tle — spokojna, dyskretna scena zamiast „latających kształtów". */}
      <Odlamek position={[-2.0, 0.7, -0.8]} scale={1.0} rot={[0.4, 0.8, 0.1]} speed={1} />
      <Odlamek position={[2.1, 1.1, -1.6]} scale={0.6} rot={[1.2, 0.2, 0.5]} speed={1.15} color="#E7CF9B" roughness={0.24} />
      <Piescien />

      {/* Środowisko z Lightformerów (BEZ zewnętrznego HDR) — daje metalowi co odbijać. */}
      <Environment resolution={256}>
        <Lightformer intensity={2.2} color="#E7CF9B" position={[0, 2.5, 4]} scale={[7, 7, 1]} />
        <Lightformer intensity={0.9} color="#ffffff" position={[3, -1, -3]} scale={[4, 4, 1]} />
        <Lightformer intensity={0.5} color="#5EA8FF" position={[-4, 1, 2]} scale={[4, 4, 1]} />
      </Environment>
    </Canvas>
  )
}
