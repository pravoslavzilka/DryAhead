import { useCallback, useEffect, useRef, useState } from 'react'
import { useInView, useReducedMotion, useLang, fmtDate } from './ui'

// ------------------------------------------------------- a sensor's 20 minutes

const STEPS = {
  sk: [
    { t: 'Spí', p: 'Väčšinu času. Elektronika je úplne odpojená, beží len hodiny. Odber 11–12 µA.' },
    { t: 'Zobudí sa', p: 'Presne vo svojom časovom okne. Každý uzol má iné minúty, aby sa rádiá nestretli.' },
    { t: 'Zmeria', p: 'Vlhkosť pôdy pri koreňoch a teplotu.' },
    { t: 'Uloží si to', p: 'Najprv do vlastnej pamäte. Keby sa správa stratila, dá sa poslať znova.' },
    { t: 'Pošle', p: 'Krátka rádiová správa LoRa na 433 MHz do stanice. Každé 2 hodiny chvíľu aj počúva.' },
    { t: 'Znova zaspí', p: 'A o 20 minút sa to celé zopakuje.' },
  ],
  en: [
    { t: 'Sleeps', p: 'Most of the time. The electronics are fully cut off and only the clock runs, drawing 11–12 µA.' },
    { t: 'Wakes up', p: 'Exactly in its own time slot. Each node has different minutes so the radios never collide.' },
    { t: 'Measures', p: 'Soil moisture at the roots, and temperature.' },
    { t: 'Saves it', p: 'To its own flash memory first, so a lost message can be sent again.' },
    { t: 'Sends', p: 'A short LoRa radio message on 433 MHz to the base station. Every 2 hours it also listens briefly.' },
    { t: 'Sleeps again', p: 'And 20 minutes later it all repeats.' },
  ],
}
const STEPS_NOTE = {
  sk: 'Kroky 2 až 5 trvajú len krátky okamih, zvyšok z 20 minút uzol spí. Preto mu stačí tak málo energie.',
  en: 'Steps 2 to 5 take only a moment; the node sleeps for the rest of the 20 minutes. That’s why it needs so little energy.',
}

export function SensorDay() {
  const lang = useLang()
  const steps = STEPS[lang]
  const [ref, inView] = useInView()
  const reduced = useReducedMotion()
  const [on, setOn] = useState(0)
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (!inView || reduced || paused) return
    const id = setInterval(() => setOn((i) => (i + 1) % steps.length), 1800)
    return () => clearInterval(id)
  }, [inView, reduced, paused, steps.length])
  return (
    <div ref={ref}>
      <ol className="day-steps" style={{ listStyle: 'none', padding: 0, margin: 0 }}
        onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
        {steps.map((s, i) => (
          <li key={s.t} className={`day-step ${!reduced && i === on ? 'on' : ''}`}>
            <div className="n">{i + 1}.</div>
            <div className="t">{s.t}</div>
            <p>{s.p}</p>
          </li>
        ))}
      </ol>
      <p className="small muted" style={{ marginTop: 10 }}>{STEPS_NOTE[lang]}</p>
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

// Photos in frontend/public/blue/foto/: WebP, 640 px for the grid and 1600 px
// for the lightbox, metadata (incl. GPS) stripped. `w`/`h` = 1600 version.
export const PHOTOS = [
  { name: 'uzol-pri-mladom-strome', w: 1600, h: 1200, caption: 'Uzol pri mladom strome na lúke', alt: 'Sivá rúrka senzorového uzla v tráve vedľa mladého stromu v ochrannom pletive',
    en: { caption: 'A node next to a young tree in a meadow', alt: 'Grey pipe of a sensor node in the grass next to a young tree in a protective mesh' } },
  { name: 'uzol-v-rade-vysadby', w: 1600, h: 1200, caption: 'Uzol v rade novovysadených stromov', alt: 'Senzorový uzol na lúke pri rade mladých stromov v pletivách',
    en: { caption: 'A node in a row of newly planted trees', alt: 'Sensor node in a meadow by a row of young trees in meshes' } },
  { name: 'uzol-v-lese', w: 1600, h: 1200, caption: 'Uzol v lese medzi mladými stromami', alt: 'Senzorový uzol na lesnej pôde pokrytej lístím, v pozadí mladé stromy',
    en: { caption: 'A node in the forest among young trees', alt: 'Sensor node on leaf-covered forest floor, young trees behind it' } },
  { name: 'sadenica-v-lese', w: 1600, h: 1200, caption: 'Mladá sadenica v lese, uzol v pozadí', alt: 'Mladá ihličnatá sadenica medzi kameňmi a lístím, v pozadí senzorový uzol',
    en: { caption: 'A young seedling in the forest, node behind it', alt: 'Young conifer seedling among stones and leaves, a sensor node in the background' } },
  { name: 'uzol-pri-oplotenom-strome', w: 1200, h: 1600, caption: 'Uzol pri oplotenom strome', alt: 'Senzorový uzol v tráve vedľa mladého stromu za drôteným plotom',
    en: { caption: 'A node by a fenced tree', alt: 'Sensor node in the grass next to a young tree behind a wire fence' } },
  { name: 'uzol-a-sadenica-v-lese', w: 1200, h: 1600, caption: 'Uzol pri chránenej sadenici v lese', alt: 'Senzorový uzol a sadenica s ochranným pletivom na lesnej pôde',
    en: { caption: 'A node by a protected seedling in the forest', alt: 'Sensor node and a seedling with a protective mesh on the forest floor' } },
  { name: 'vysadba-na-luke', w: 1600, h: 1200, caption: 'Nová výsadba stromov na lúke', alt: 'Lúka s mladými stromami v ochranných pletivách a senzorovým uzlom',
    en: { caption: 'New tree planting in a meadow', alt: 'Meadow with young trees in protective meshes and a sensor node' } },
  { name: 'uzol-za-sumraku', w: 1200, h: 1600, caption: 'Uzol pri strome za súmraku', alt: 'Senzorový uzol a mladý strom v pletive na lúke pri západe slnka',
    en: { caption: 'A node by a tree at dusk', alt: 'Sensor node and a young tree in a mesh in a meadow at sunset' } },
]

const GALLERY_T = {
  sk: { missing: 'Fotka sa nenačítala', enlarge: 'Zväčšiť fotku', close: 'Zavrieť', prev: 'Predchádzajúca fotka', next: 'Ďalšia fotka' },
  en: { missing: 'Photo failed to load', enlarge: 'Enlarge photo', close: 'Close', prev: 'Previous photo', next: 'Next photo' },
}
const photoText = (photo, lang) => (lang === 'en' ? photo.en : photo)

function Photo({ photo, big }) {
  const lang = useLang()
  const [missing, setMissing] = useState(false)
  if (missing) {
    return (
      <div className="g-ph" style={big ? { minHeight: 300, color: '#ddd' } : undefined}>
        <span>{GALLERY_T[lang].missing}: {photoText(photo, lang).caption}</span>
      </div>
    )
  }
  const base = `/blue/foto/${photo.name}`
  return (
    <img
      src={`${base}-${big ? 1600 : 640}.webp`}
      srcSet={`${base}-640.webp 640w, ${base}-1600.webp 1600w`}
      sizes={big ? '100vw' : '(min-width: 880px) 25vw, 50vw'}
      alt={photoText(photo, lang).alt}
      loading={big ? 'eager' : 'lazy'}
      decoding="async"
      width={photo.w}
      height={photo.h}
      onError={() => setMissing(true)}
    />
  )
}

export function Gallery() {
  const lang = useLang()
  const t = GALLERY_T[lang]
  const cap = (ph) => photoText(ph, lang).caption
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
          <button key={ph.name} className="g-item" onClick={(e) => { lastFocus.current = e.currentTarget; setOpen(i) }}
            aria-label={`${t.enlarge}: ${cap(ph)}`}>
            <div className="g-img"><Photo photo={ph} /></div>
            <div className="g-cap">{cap(ph)}</div>
          </button>
        ))}
      </div>
      {open != null && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label={cap(PHOTOS[open])} onClick={close}>
          <figure onClick={(e) => e.stopPropagation()}>
            <div className="g-img"><Photo photo={PHOTOS[open]} big /></div>
            <figcaption>{cap(PHOTOS[open])} <span style={{ opacity: 0.7 }}>({open + 1}/{PHOTOS.length})</span></figcaption>
          </figure>
          <button ref={closeBtn} className="lb-btn" style={{ top: 12, right: 12 }} onClick={close} aria-label={t.close}>✕</button>
          <button className="lb-btn" style={{ left: 8, top: '50%' }} aria-label={t.prev}
            onClick={(e) => { e.stopPropagation(); setOpen((i) => (i - 1 + PHOTOS.length) % PHOTOS.length) }}>‹</button>
          <button className="lb-btn" style={{ right: 8, top: '50%' }} aria-label={t.next}
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
const LIVE_T = {
  sk: {
    live: 'Práve teraz, priamo zo senzorov',
    saved: (d) => `Stav k ${d} (uložené dáta)`,
    loading: 'Načítavam aktuálne hodnoty…',
    node: 'Uzol',
    moisture: 'vlhkosť pôdy',
  },
  en: {
    live: 'Right now, straight from the sensors',
    saved: (d) => `As of ${d} (saved data)`,
    loading: 'Loading current values…',
    node: 'Node',
    moisture: 'soil moisture',
  },
}

export function LiveWidget({ snapshot }) {
  const lang = useLang()
  const t = LIVE_T[lang]
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
        {live ? <><span className="pulse" aria-hidden="true" />{t.live}</>
          : failed ? t.saved(fmtDate(snapshot.days[lastIdx], { day: 'numeric', month: 'long' }, lang))
            : t.loading}
      </div>
      <div className="live">
        {LIVE_NODES.map((id) => {
          const v = live ? live[id]?.pct : fallback[id]
          return (
            <div key={id} className="live-node">
              <div className="small muted">{t.node} {id}</div>
              <div className="v">{v == null ? '–' : `${Math.round(v)} %`}</div>
              <div className="small muted">{t.moisture}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
