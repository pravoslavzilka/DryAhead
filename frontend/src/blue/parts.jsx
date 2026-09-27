import { useCallback, useEffect, useRef, useState } from 'react'
import { useInView, useReducedMotion, fmtDate } from './ui'

// ------------------------------------------------------- a sensor's 20 minutes

const STEPS = [
  { t: 'Spí', p: 'Väčšinu času. Elektronika je úplne odpojená, beží len hodiny. Odber 11–12 µA.' },
  { t: 'Zobudí sa', p: 'Presne vo svojom časovom okne. Každý uzol má iné minúty, aby sa rádiá nestretli.' },
  { t: 'Zmeria', p: 'Vlhkosť pôdy pri koreňoch a teplotu.' },
  { t: 'Uloží si to', p: 'Najprv do vlastnej pamäte. Keby sa správa stratila, dá sa poslať znova.' },
  { t: 'Pošle', p: 'Krátka rádiová správa LoRa na 433 MHz do stanice. Každé 2 hodiny chvíľu aj počúva.' },
  { t: 'Znova zaspí', p: 'A o 20 minút sa to celé zopakuje.' },
]

export function SensorDay() {
  const [ref, inView] = useInView()
  const reduced = useReducedMotion()
  const [on, setOn] = useState(0)
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (!inView || reduced || paused) return
    const id = setInterval(() => setOn((i) => (i + 1) % STEPS.length), 1800)
    return () => clearInterval(id)
  }, [inView, reduced, paused])
  return (
    <div ref={ref}>
      <ol className="day-steps" style={{ listStyle: 'none', padding: 0, margin: 0 }}
        onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
        {STEPS.map((s, i) => (
          <li key={s.t} className={`day-step ${!reduced && i === on ? 'on' : ''}`}>
            <div className="n">{i + 1}.</div>
            <div className="t">{s.t}</div>
            <p>{s.p}</p>
          </li>
        ))}
      </ol>
      <p className="small muted" style={{ marginTop: 10 }}>
        Kroky 2 až 5 trvajú len krátky okamih, zvyšok z 20 minút uzol spí. Preto mu stačí tak málo energie.
      </p>
    </div>
  )
}

// ------------------------------------------------------------------ coverage

const ZONES = [
  { id: 'a', name: 'Svah pod lesom', color: '#8fb07a', path: 'M0 0 H170 L150 110 L0 130 Z', sensor: [70, 60] },
  { id: 'b', name: 'Pasienok', color: '#d7c07a', path: 'M170 0 H400 V90 L260 120 L150 110 Z', sensor: [280, 50] },
  { id: 'c', name: 'Nová výsadba stromov', color: '#b99b78', path: 'M0 130 L150 110 L260 120 L400 90 V220 H0 Z', sensor: [210, 170] },
]

export function Coverage() {
  const [active, setActive] = useState(null)
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
        <b>Jeden uzol pre celú zónu s podobnou pôdou</b>
        <span className="tag-illu">cieľový princíp, nie hotová funkcia</span>
      </div>
      <svg viewBox="0 0 400 220" style={{ width: '100%', height: 'auto', borderRadius: 12 }} role="img"
        aria-label="Schéma: pozemok rozdelený na tri zóny s podobnou pôdou, sklonom a porastom. V každej zóne je jeden senzor, ktorý ju reprezentuje.">
        {ZONES.map((z) => (
          <path key={z.id} d={z.path} fill={z.color} stroke="#fff" strokeWidth="2"
            opacity={active && active !== z.id ? 0.35 : 0.9} style={{ transition: 'opacity .25s' }} />
        ))}
        {ZONES.map((z) => (
          <g key={z.id} transform={`translate(${z.sensor[0]},${z.sensor[1]})`}>
            <circle r="16" fill="#fff" opacity={active === z.id ? 0.55 : 0} style={{ transition: 'opacity .25s' }} />
            <circle r="7" fill="#2b2620" />
            <circle r="3" fill="#7fd07a" />
          </g>
        ))}
      </svg>
      <div className="legend" role="group" aria-label="Zóny">
        {ZONES.map((z) => (
          <button key={z.id} className="chip" aria-pressed={active === z.id}
            onClick={() => setActive((a) => (a === z.id ? null : z.id))}
            onMouseEnter={() => setActive(z.id)} onMouseLeave={() => setActive(null)}>
            <span className="dot" style={{ background: z.color }} />{z.name}
          </button>
        ))}
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        Model vodnej bilancie z uzla odhadne stav vlahy pre celú zónu, ktorá sa správa podobne. Menej elektroniky v prírode, rovnaký prehľad.
      </p>
    </div>
  )
}

// ------------------------------------------------------------------- gallery

// Photos go to frontend/public/blue/foto/ as WebP (about 1600 px wide).
export const PHOTOS = [
  { file: 'uzol-v-terene.webp', caption: 'Senzorový uzol v teréne', alt: 'Senzorový uzol zakopaný v tráve na pozemku' },
  { file: 'osadzovanie.webp', caption: 'Osadzovanie senzora do hĺbky koreňov', alt: 'Osadzovanie senzora do vykopanej jamy' },
  { file: 'kryt.webp', caption: 'Odolný kryt DN160', alt: 'Kryt uzla z rúry DN160' },
  { file: 'elektronika.webp', caption: 'Elektronika uzla: ESP32, LoRa, hodiny', alt: 'Doska s mikropočítačom ESP32 a rádiovým modulom' },
  { file: 'stanica.webp', caption: 'Centrálna stanica', alt: 'Centrálna stanica, ktorá prijíma dáta z uzlov' },
  { file: 'pozemok.webp', caption: 'Pozemok s mladými stromami pri Zvolene', alt: 'Pozemok s mladými stromami a ovcami' },
]

function Photo({ photo, big }) {
  const [missing, setMissing] = useState(false)
  if (missing) {
    return (
      <div className="g-ph" style={big ? { minHeight: 300, color: '#ddd' } : undefined}>
        <span>[DOPLNIŤ: fotka – {photo.caption.toLowerCase()}]<br /><small>public/blue/foto/{photo.file}</small></span>
      </div>
    )
  }
  return (
    <img src={`/blue/foto/${photo.file}`} alt={photo.alt} loading={big ? 'eager' : 'lazy'} decoding="async"
      width="1600" height="1200" onError={() => setMissing(true)} />
  )
}

export function Gallery() {
  const [open, setOpen] = useState(null)
  const closeBtn = useRef(null)
  const lastFocus = useRef(null)
  const close = useCallback(() => {
    setOpen(null)
    lastFocus.current?.focus()
  }, [])
  useEffect(() => {
    if (open == null) return
    closeBtn.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') close()
      if (e.key === 'ArrowRight') setOpen((i) => (i + 1) % PHOTOS.length)
      if (e.key === 'ArrowLeft') setOpen((i) => (i - 1 + PHOTOS.length) % PHOTOS.length)
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [open, close])

  return (
    <>
      <div className="gallery">
        {PHOTOS.map((ph, i) => (
          <button key={ph.file} className="g-item" onClick={(e) => { lastFocus.current = e.currentTarget; setOpen(i) }}
            aria-label={`Zväčšiť fotku: ${ph.caption}`}>
            <div className="g-img"><Photo photo={ph} /></div>
            <div className="g-cap">{ph.caption}</div>
          </button>
        ))}
      </div>
      {open != null && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label={PHOTOS[open].caption} onClick={close}>
          <figure onClick={(e) => e.stopPropagation()}>
            <div className="g-img"><Photo photo={PHOTOS[open]} big /></div>
            <figcaption>{PHOTOS[open].caption} <span style={{ opacity: 0.7 }}>({open + 1}/{PHOTOS.length})</span></figcaption>
          </figure>
          <button ref={closeBtn} className="lb-btn" style={{ top: 12, right: 12 }} onClick={close} aria-label="Zavrieť">✕</button>
          <button className="lb-btn" style={{ left: 8, top: '50%' }} aria-label="Predchádzajúca fotka"
            onClick={(e) => { e.stopPropagation(); setOpen((i) => (i - 1 + PHOTOS.length) % PHOTOS.length) }}>‹</button>
          <button className="lb-btn" style={{ right: 8, top: '50%' }} aria-label="Ďalšia fotka"
            onClick={(e) => { e.stopPropagation(); setOpen((i) => (i + 1) % PHOTOS.length) }}>›</button>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------- live widget

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
const SUPABASE_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY
const LIVE_NODES = [1, 4, 5]
const LIVE_TIMEOUT_MS = 4000
const STALE_MS = 3 * 3600 * 1000

async function fetchLive() {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('not configured')
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), LIVE_TIMEOUT_MS)
  const get = (path) => fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` }, signal: ctrl.signal,
  }).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
  try {
    const [cal, rows] = await Promise.all([
      get(`sensor_calibration?select=node_id,air,water&node_id=in.(${LIVE_NODES})`),
      get(`readings?select=node_id,raw,received_at&node_id=in.(${LIVE_NODES})&order=received_at.desc&limit=60`),
    ])
    const out = {}
    for (const id of LIVE_NODES) {
      const c = cal.find((x) => x.node_id === id)
      const r = rows.find((x) => x.node_id === id)
      if (!c || !r || Date.now() - Date.parse(r.received_at) > STALE_MS) continue
      out[id] = { pct: Math.min(100, Math.max(0, ((c.air - r.raw) / (c.air - c.water)) * 100)), at: Date.parse(r.received_at) }
    }
    if (!Object.keys(out).length) throw new Error('no fresh data')
    return out
  } finally {
    clearTimeout(timer)
  }
}

/** Latest humidity per node; silently falls back to the snapshot's last day. */
export function LiveWidget({ snapshot }) {
  const [live, setLive] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let cancelled = false
    fetchLive().then((v) => !cancelled && setLive(v)).catch(() => !cancelled && setFailed(true))
    return () => { cancelled = true }
  }, [])
  const lastIdx = snapshot.days.length - 1
  const fallback = Object.fromEntries(LIVE_NODES.map((id) => [id, snapshot.nodes[id]?.humidity[lastIdx]]))
  return (
    <div>
      <div className="small muted" style={{ marginBottom: 8 }} aria-live="polite">
        {live ? <><span className="pulse" aria-hidden="true" />Práve teraz, priamo zo senzorov</>
          : failed ? <>Stav k {fmtDate(snapshot.days[lastIdx], { day: 'numeric', month: 'long' })} (uložené dáta)</>
            : 'Načítavam aktuálne hodnoty…'}
      </div>
      <div className="live">
        {LIVE_NODES.map((id) => {
          const v = live ? live[id]?.pct : fallback[id]
          return (
            <div key={id} className="live-node">
              <div className="small muted">Uzol {id}</div>
              <div className="v">{v == null ? '–' : `${Math.round(v)} %`}</div>
              <div className="small muted">vlhkosť pôdy</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
