import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from './ui'

// Illustrative moisture story over scroll progress p (0..1):
// soil dries, it rains, it soaks up, it slowly dries again.
const RAIN_FROM = 0.52
const RAIN_TO = 0.68
function moistureAt(p) {
  const ease = (a, b, t) => a + (b - a) * (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, t)))) / 2
  if (p < RAIN_FROM) return ease(0.72, 0.16, p / RAIN_FROM)
  if (p < RAIN_TO) return ease(0.16, 0.92, (p - RAIN_FROM) / (RAIN_TO - RAIN_FROM))
  return ease(0.92, 0.62, (p - RAIN_TO) / (1 - RAIN_TO))
}

function statusText(m, raining) {
  if (raining) return 'Prší – pôda nasakuje vodu'
  if (m < 0.3) return 'Pri koreňoch chýba voda – čas zaliať'
  if (m < 0.5) return 'Pôda vysychá – zatiaľ netreba zalievať'
  return 'Vlahy je dosť – zálievka by bola zbytočná'
}

const DROPS = Array.from({ length: 22 }, (_, i) => ({ x: 18 + ((i * 53) % 370), y: 8 + ((i * 29) % 70), d: (i % 5) * 0.12 }))
const BUBBLES = Array.from({ length: 26 }, (_, i) => ({ x: 20 + ((i * 67) % 360), y: 142 + ((i * 41) % 140), r: 2 + (i % 3) }))

export default function SoilFigure() {
  const ref = useRef(null)
  const reduced = useReducedMotion()
  const [p, setP] = useState(0.3)

  useEffect(() => {
    if (reduced) return
    let raf = 0
    const update = () => {
      raf = 0
      const el = ref.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const vh = window.innerHeight
      setP(Math.min(1, Math.max(0, (vh - r.top) / (vh + r.height))))
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update) }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [reduced])

  const m = moistureAt(p)
  const raining = p >= RAIN_FROM && p < RAIN_TO
  const pct = Math.round(m * 100)

  return (
    <figure className="soil-fig" ref={ref} style={{ margin: 0 }}>
      <svg viewBox="0 0 400 300" role="img" aria-label={`Ilustrácia: prierez pôdou so stromom, koreňmi a senzorom pri koreňoch. Vlhkosť pôdy ${pct} %. ${statusText(m, raining)}.`}>
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" style={{ stopColor: raining ? '#9fb2c2' : '#cfe3ee' }} />
            <stop offset="1" style={{ stopColor: raining ? '#c9d3da' : '#eef4f2' }} />
          </linearGradient>
          <linearGradient id="soil-depth" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity="0.18" />
          </linearGradient>
        </defs>

        {/* sky */}
        <rect width="400" height="122" fill="url(#sky)" />
        {!raining && <circle cx="340" cy="34" r="16" fill="#f2c14e" opacity={0.9 - m * 0.4} />}
        <g opacity={raining ? 1 : 0.35} style={{ transition: 'opacity .4s' }}>
          <ellipse cx="110" cy="28" rx="44" ry="13" fill="#e8edf0" />
          <ellipse cx="140" cy="22" rx="30" ry="12" fill="#f3f6f7" />
          <ellipse cx="260" cy="36" rx="38" ry="11" fill="#e8edf0" />
        </g>
        {raining && DROPS.map((d, i) => (
          <line key={i} x1={d.x} y1={d.y + 30} x2={d.x - 3} y2={d.y + 40} stroke="#4f8fba" strokeWidth="2" strokeLinecap="round" opacity={0.75} />
        ))}

        {/* soil: dry base + wet layer whose opacity follows moisture */}
        <rect y="120" width="400" height="180" style={{ fill: '#c9a47a' }} />
        <rect y="120" width="400" height="180" fill="#4a2f1f" opacity={0.15 + m * 0.7} style={{ transition: 'opacity .25s' }} />
        <rect y="120" width="400" height="180" fill="url(#soil-depth)" />
        {BUBBLES.map((b, i) => (
          <circle key={i} cx={b.x} cy={b.y} r={b.r} fill="#7fb8dc" opacity={Math.max(0, m - 0.25) * 0.9} />
        ))}
        {/* cracks when dry */}
        <g stroke="#6e4b30" strokeWidth="1.5" fill="none" opacity={Math.max(0, 0.45 - m) * 2}>
          <path d="M40 121 l6 10 -4 8 7 9" /><path d="M300 121 l-5 9 6 7 -3 10" /><path d="M360 121 l4 7 -6 8" />
        </g>

        {/* grass line */}
        <path d="M0 121 H400" stroke="#5f8f4e" strokeWidth="3" />
        {[20, 60, 95, 150, 230, 275, 320, 375].map((x) => (
          <path key={x} d={`M${x} 121 l-3 -8 M${x} 121 l1 -10 M${x} 121 l4 -7`} stroke="#5f8f4e" strokeWidth="1.6" strokeLinecap="round" />
        ))}

        {/* roots */}
        <g stroke="#6b4a2f" strokeLinecap="round" fill="none">
          <path d="M200 122 C 196 150 180 175 150 200" strokeWidth="4" />
          <path d="M200 122 C 205 155 222 180 256 205" strokeWidth="4" />
          <path d="M200 122 C 199 160 198 190 196 228" strokeWidth="3.5" />
          <path d="M172 180 C 160 188 140 190 122 188" strokeWidth="2" />
          <path d="M236 190 C 250 200 268 206 290 205" strokeWidth="2" />
          <path d="M197 205 C 186 220 178 232 170 250" strokeWidth="2" />
        </g>

        {/* tree */}
        <path d="M194 122 L197 62 L203 62 L206 122 Z" fill="#6b4a2f" />
        <g>
          <circle cx="200" cy="48" r="30" fill="#b59b4a" />
          <circle cx="178" cy="60" r="20" fill="#a98f45" />
          <circle cx="222" cy="60" r="20" fill="#a98f45" />
          <g opacity={Math.min(1, 0.2 + m * 1.2)} style={{ transition: 'opacity .25s' }}>
            <circle cx="200" cy="48" r="30" fill="#4f8a45" />
            <circle cx="178" cy="60" r="20" fill="#447a3c" />
            <circle cx="222" cy="60" r="20" fill="#447a3c" />
          </g>
        </g>

        {/* sensor: DN160 housing, probe at root depth */}
        <rect x="266" y="112" width="26" height="12" rx="3" fill="#e9e4da" stroke="#8b8378" />
        <line x1="279" y1="112" x2="279" y2="94" stroke="#8b8378" strokeWidth="2" />
        <circle cx="279" cy="92" r="2.5" fill="#8b8378" />
        <rect x="272" y="124" width="14" height="78" rx="3" fill="#dcd6ca" stroke="#8b8378" />
        <rect x="275" y="196" width="8" height="22" rx="2" fill="#3f7d4a" />
        {!reduced && (
          <g stroke="#2f6f9a" strokeWidth="1.5" fill="none" opacity="0.8">
            <path d="M286 86 a10 10 0 0 1 0 12"><animate attributeName="opacity" values="0;1;0" dur="2.4s" repeatCount="indefinite" /></path>
            <path d="M291 81 a17 17 0 0 1 0 22"><animate attributeName="opacity" values="0;1;0" dur="2.4s" begin=".4s" repeatCount="indefinite" /></path>
          </g>
        )}
        <g>
          <rect x="288" y="200" width="108" height="22" rx="11" fill="rgba(255,255,255,.88)" />
          <text x="342" y="215" textAnchor="middle" fontSize="11" fill="#2b2620" fontFamily="system-ui">senzor pri koreňoch</text>
        </g>
      </svg>
      <div className="soil-readout">
        <span className="tag-illu">ilustračné</span>
        <span style={{ minWidth: 220 }}><b>{statusText(m, raining)}</b></span>
        <span className="meter" aria-hidden="true"><span style={{ width: `${pct}%` }} /></span>
      </div>
      <div style={{ padding: '0 16px 14px' }}>
        <label className="small muted" htmlFor="soil-slider">
          {reduced ? 'Posuňte a pozrite sa, ako sa mení vlhkosť:' : 'Pri scrollovaní sa pôda mení. Môžete posúvať aj ručne:'}
        </label>
        <input
          id="soil-slider"
          className="range"
          type="range"
          min="0"
          max="100"
          value={Math.round(p * 100)}
          onChange={(e) => setP(Number(e.target.value) / 100)}
          aria-valuetext={`${statusText(m, raining)}, vlhkosť ${pct} %`}
        />
      </div>
    </figure>
  )
}
