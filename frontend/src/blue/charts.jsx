import { useMemo, useState } from 'react'
import { useWidth, fmtDate } from './ui'

const NODE_META = {
  1: { color: 'var(--n1)', label: 'Uzol 1' },
  3: { color: 'var(--n3)', label: 'Uzol 3' },
  4: { color: 'var(--n4)', label: 'Uzol 4' },
  5: { color: 'var(--n5)', label: 'Uzol 5' },
}

const fmtNum = (v, d = 1) => (v == null ? '–' : v.toFixed(d).replace('.', ','))

/** SVG path through points, breaking at nulls. */
function linePath(values, x, y) {
  let d = ''
  let pen = false
  values.forEach((v, i) => {
    if (v == null) { pen = false; return }
    d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`
    pen = true
  })
  return d
}

/** Pointer + keyboard cursor over a day index. */
function useCursor(n, x0, step) {
  const [idx, setIdx] = useState(null)
  const fromEvent = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = (e.clientX - rect.left) * (e.currentTarget.viewBox.baseVal.width / rect.width)
    setIdx(Math.max(0, Math.min(n - 1, Math.round((px - x0) / step))))
  }
  const onKeyDown = (e) => {
    if (e.key === 'ArrowRight') { setIdx((i) => Math.min(n - 1, (i ?? -1) + 1)); e.preventDefault() }
    else if (e.key === 'ArrowLeft') { setIdx((i) => Math.max(0, (i ?? n) - 1)); e.preventDefault() }
    else if (e.key === 'Home') { setIdx(0); e.preventDefault() }
    else if (e.key === 'End') { setIdx(n - 1); e.preventDefault() }
    else if (e.key === 'Escape') setIdx(null)
  }
  return {
    idx,
    handlers: {
      onPointerMove: fromEvent,
      onPointerDown: fromEvent,
      onPointerLeave: (e) => e.pointerType === 'mouse' && setIdx(null),
      onKeyDown,
      onBlur: () => setIdx(null),
    },
  }
}

// ---------------------------------------------------------------- real data

export function DataChart({ snapshot }) {
  const [ref, width] = useWidth()
  const [shown, setShown] = useState({ 1: true, 3: true, 4: true, 5: true })
  const days = snapshot.days
  const n = days.length
  const narrow = width < 560
  const H = narrow ? 300 : 340
  const m = { l: 34, r: 30, t: 48, b: 26 }
  const pw = width - m.l - m.r
  const ph = H - m.t - m.b
  const step = pw / (n - 1)
  const x = (i) => m.l + i * step
  const y = (v) => m.t + ph - (v / 100) * ph
  const rainMax = 25
  const rainH = ph * 0.32
  const yr = (mm) => m.t + ph - (Math.min(mm, rainMax) / rainMax) * rainH
  const { idx, handlers } = useCursor(n, m.l, step)

  const dayIdx = (iso) => days.indexOf(iso)
  const storms = days.map((d, i) => ({ d, i, mm: snapshot.rain_mm[i] })).filter((r) => r.mm >= 10)
  const dryFrom = dayIdx('2026-07-24')
  const dryTo = dayIdx('2026-08-16')
  const months = days.map((d, i) => ({ d, i })).filter(({ d }) => d.endsWith('-01'))

  const nodes = Object.keys(snapshot.nodes).map(Number)
  const summary = `Graf dennej vlhkosti pôdy pre uzly ${nodes.join(', ')} od ${fmtDate(days[0])} do ${fmtDate(days[n - 1])}, s dennými zrážkami zo stanice Zaježová. Najväčšie dažde: ${storms.map((s) => `${fmtDate(s.d)} ${fmtNum(s.mm)} mm`).join(', ')}.`

  return (
    <div>
      <div className="legend" role="group" aria-label="Zobraziť uzly">
        {nodes.map((id) => (
          <button
            key={id}
            className="chip"
            aria-pressed={shown[id]}
            onClick={() => setShown((s) => ({ ...s, [id]: !s[id] }))}
          >
            <span className="dot" style={{ background: NODE_META[id].color }} />
            {NODE_META[id].label}
            {snapshot.nodes[id].last_day < days[n - 1] && (
              <span className="muted small">(do {fmtDate(snapshot.nodes[id].last_day)})</span>
            )}
          </button>
        ))}
        <span className="small muted" style={{ alignSelf: 'center' }}>
          <span className="sw" style={{ background: 'var(--water-2)', height: 8, width: 10, opacity: 0.6 }} />dážď (mm, stanica Zaježová)
        </span>
      </div>
      <div className="chart" ref={ref}>
        <svg
          viewBox={`0 0 ${width} ${H}`}
          height={H}
          tabIndex={0}
          role="img"
          aria-label={summary}
          {...handlers}
        >
          {[0, 25, 50, 75, 100].map((v) => (
            <g key={v}>
              <line className="grid-line" x1={m.l} x2={width - m.r} y1={y(v)} y2={y(v)} />
              <text x={m.l - 6} y={y(v) + 4} textAnchor="end">{v} %</text>
            </g>
          ))}
          {months.map(({ d, i }) => (
            <text key={d} x={x(i)} y={H - 6} textAnchor="middle">
              {new Date(`${d}T12:00:00`).toLocaleDateString('sk-SK', { month: narrow ? 'short' : 'long' })}
            </text>
          ))}

          {/* dry spell */}
          {dryFrom >= 0 && dryTo > dryFrom && (
            <g>
              <rect x={x(dryFrom)} y={m.t} width={x(dryTo) - x(dryFrom)} height={ph} fill="var(--sun)" opacity="0.08" />
              <text x={(x(dryFrom) + x(dryTo)) / 2} y={m.t - 26} textAnchor="middle" style={{ fill: 'var(--ink-2)', fontWeight: 600 }}>
                {narrow ? '24 dní bez dažďa' : 'tu pôda vysychá: 24 dní bez dažďa'}
              </text>
            </g>
          )}

          {/* rain */}
          {snapshot.rain_mm.map((mm, i) => mm > 0.2 && (
            <rect key={i} x={x(i) - Math.max(1.5, step * 0.35)} y={yr(mm)} width={Math.max(3, step * 0.7)} height={m.t + ph - yr(mm)} fill="var(--water-2)" opacity="0.55" rx="1" />
          ))}
          {storms.map((s, k) => (
            <g key={s.d}>
              <line x1={x(s.i)} x2={x(s.i)} y1={m.t - 6} y2={m.t + ph} stroke="var(--water)" strokeDasharray="3 4" opacity="0.6" />
              {(k === 0 || (!narrow && s.i - storms[k - 1].i > 3)) && (
                <text x={x(s.i) + 4} y={m.t - 9} style={{ fill: 'var(--water)', fontWeight: 600 }}>
                  {k === 0 ? `tu pršalo (${fmtNum(s.mm)} mm)` : `${fmtNum(s.mm)} mm`}
                </text>
              )}
            </g>
          ))}

          {/* humidity lines */}
          {nodes.filter((id) => shown[id]).map((id) => (
            <path key={id} d={linePath(snapshot.nodes[id].humidity, x, y)} fill="none" stroke={NODE_META[id].color} strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" />
          ))}

          {idx != null && (
            <g>
              <line x1={x(idx)} x2={x(idx)} y1={m.t} y2={m.t + ph} stroke="var(--ink-2)" strokeWidth="1" />
              {nodes.filter((id) => shown[id] && snapshot.nodes[id].humidity[idx] != null).map((id) => (
                <circle key={id} cx={x(idx)} cy={y(snapshot.nodes[id].humidity[idx])} r="4" fill={NODE_META[id].color} stroke="var(--card)" strokeWidth="2" />
              ))}
            </g>
          )}
        </svg>
        {idx != null && (
          <div
            className="chart-tip"
            style={{ left: Math.min(width - 170, Math.max(0, x(idx) + 10)), top: 36 }}
            aria-live="polite"
          >
            <b>{fmtDate(days[idx], { day: 'numeric', month: 'long' })}</b>
            <div className="muted">dážď: {fmtNum(snapshot.rain_mm[idx])} mm</div>
            {nodes.filter((id) => shown[id]).map((id) => (
              <div key={id}>
                <span className="dot" style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 9, background: NODE_META[id].color, marginRight: 6 }} />
                {NODE_META[id].label}: <b>{fmtNum(snapshot.nodes[id].humidity[idx])} %</b>
              </div>
            ))}
          </div>
        )}
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        Denný medián vlhkosti pôdy (0 % = senzor na vzduchu, 100 % = senzor vo vode). Ťuknite alebo prejdite myšou
        na graf, prípadne ho vyberte klávesom Tab a použite šípky.
      </p>
    </div>
  )
}

// ----------------------------------------------------------------- forecast

export function ForecastChart({ demo }) {
  const [ref, width] = useWidth()
  const n = demo.dates.length
  const H = 260
  const m = { l: 40, r: 16, t: 16, b: 28 }
  const pw = width - m.l - m.r
  const ph = H - m.t - m.b
  const vals = [...demo.measured.filter((v) => v != null), ...demo.model, demo.persistence]
  const lo = Math.floor(Math.min(...vals) - 1)
  const hi = Math.min(100, Math.ceil(Math.max(...vals) + 1))
  const step = pw / (n - 1)
  const x = (i) => m.l + i * step
  const y = (v) => m.t + ((hi - v) / (hi - lo)) * ph
  const { idx, handlers } = useCursor(n, m.l, step)
  const ticks = Array.from({ length: 5 }, (_, k) => lo + ((hi - lo) * k) / 4)

  return (
    <div>
      <div className="legend">
        <span><span className="sw" style={{ background: 'var(--ink)' }} />meranie</span>
        <span><span className="sw" style={{ background: 'var(--leaf)' }} />predpoveď modelu</span>
        <span><span className="sw" style={{ background: 'var(--warn)', backgroundImage: 'none', opacity: 0.7 }} />„zostane to tak“ (baseline)</span>
      </div>
      <div className="chart" ref={ref}>
        <svg viewBox={`0 0 ${width} ${H}`} height={H} tabIndex={0} role="img"
          aria-label={`Experimentálna predpoveď vysychania pre uzol ${demo.node} od ${fmtDate(demo.dates[0])} do ${fmtDate(demo.dates[n - 1])}: model spustený z prvého merania, porovnaný s meraním a s odhadom, že vlhkosť zostane rovnaká.`}
          {...handlers}>
          {ticks.map((v) => (
            <g key={v}>
              <line className="grid-line" x1={m.l} x2={width - m.r} y1={y(v)} y2={y(v)} />
              <text x={m.l - 6} y={y(v) + 4} textAnchor="end">{fmtNum(v, 0)} %</text>
            </g>
          ))}
          {demo.dates.map((d, i) => (i % 3 === 0 || (i === n - 1 && i % 3 === 2)) && (
            <text key={d} x={x(i)} y={H - 8} textAnchor="middle">{fmtDate(d)}</text>
          ))}
          <line x1={m.l} x2={width - m.r} y1={y(demo.persistence)} y2={y(demo.persistence)} stroke="var(--warn)" strokeWidth="2" strokeDasharray="6 5" opacity="0.8" />
          <path d={linePath(demo.model, x, y)} fill="none" stroke="var(--leaf)" strokeWidth="3" strokeLinecap="round" />
          <path d={linePath(demo.measured, x, y)} fill="none" stroke="var(--ink)" strokeWidth="1.5" opacity="0.6" />
          {demo.measured.map((v, i) => v != null && <circle key={i} cx={x(i)} cy={y(v)} r="3.5" fill="var(--ink)" />)}
          {idx != null && <line x1={x(idx)} x2={x(idx)} y1={m.t} y2={m.t + ph} stroke="var(--ink-2)" />}
        </svg>
        {idx != null && (
          <div className="chart-tip" style={{ left: Math.min(width - 170, Math.max(0, x(idx) + 10)), top: 20 }} aria-live="polite">
            <b>{fmtDate(demo.dates[idx], { day: 'numeric', month: 'long' })}</b> (deň {idx})
            <div>meranie: <b>{fmtNum(demo.measured[idx])} %</b></div>
            <div>model: <b>{fmtNum(demo.model[idx])} %</b></div>
            <div>„zostane to tak“: <b>{fmtNum(demo.persistence)} %</b></div>
          </div>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------- blind vs soil-based watering

const DAYS = 28
const RAIN = { 7: 42, 19: 26 } // illustrative rain days -> moisture gain
const THRESHOLD = 35
function simulate(mode) {
  let v = 62
  const series = []
  const waterings = []
  for (let d = 0; d < DAYS; d++) {
    if (RAIN[d]) v += RAIN[d]
    let watered = false
    if (mode === 'blind' && d % 4 === 1) { v += 16; watered = true }
    if (mode === 'soil' && v < THRESHOLD) { v += 30; watered = true }
    v = Math.min(100, v)
    if (watered) waterings.push({ d, wasted: v - 16 > 60 && mode === 'blind' })
    series.push(v)
    v -= 3.4 + (v > 70 ? 2 : 0) // drains faster when very wet
  }
  return { series, waterings }
}

export function WateringCompare() {
  const [mode, setMode] = useState('blind')
  const [ref, width] = useWidth()
  const sims = useMemo(() => ({ blind: simulate('blind'), soil: simulate('soil') }), [])
  const sim = sims[mode]
  const other = sims[mode === 'blind' ? 'soil' : 'blind']
  const H = 240
  const m = { l: 12, r: 12, t: 30, b: 26 }
  const pw = width - m.l - m.r
  const ph = H - m.t - m.b
  const x = (i) => m.l + (i / (DAYS - 1)) * pw
  const y = (v) => m.t + ph - (v / 100) * ph

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
        <div className="seg" role="group" aria-label="Spôsob zalievania">
          <button aria-pressed={mode === 'blind'} onClick={() => setMode('blind')}>Podľa kalendára</button>
          <button aria-pressed={mode === 'soil'} onClick={() => setMode('soil')}>Podľa pôdy</button>
        </div>
        <span className="tag-illu">ilustračné</span>
      </div>
      <div className="chart" ref={ref}>
        <svg viewBox={`0 0 ${width} ${H}`} height={H} role="img"
          aria-label={mode === 'blind'
            ? 'Ilustrácia: zalievanie každé štyri dni podľa kalendára, aj hneď po daždi, keď pôda vodu nepotrebuje.'
            : 'Ilustrácia: zalievanie len vtedy, keď vlhkosť pôdy klesne k hranici stresu; po daždi sa zálievka vynechá.'}>
          <rect x={m.l} y={y(THRESHOLD)} width={pw} height={y(0) - y(THRESHOLD)} fill="var(--warn)" opacity="0.07" />
          <line x1={m.l} x2={width - m.r} y1={y(THRESHOLD)} y2={y(THRESHOLD)} stroke="var(--warn)" strokeDasharray="5 4" />
          <text x={width - m.r} y={y(THRESHOLD) + 14} textAnchor="end" style={{ fill: 'var(--warn)' }}>hranica stresu stromu</text>
          {Object.entries(RAIN).map(([d]) => (
            <g key={d}>
              <text x={x(+d)} y={m.t - 12} textAnchor="middle" style={{ fill: 'var(--water)', fontWeight: 600 }}>dážď</text>
              <line x1={x(+d)} x2={x(+d)} y1={m.t - 8} y2={m.t + ph} stroke="var(--water)" strokeDasharray="2 4" opacity="0.6" />
            </g>
          ))}
          <path d={linePath(other.series, x, y)} fill="none" stroke="var(--muted)" strokeWidth="1.5" strokeDasharray="3 4" opacity="0.5" />
          <path d={linePath(sim.series, x, y)} fill="none" stroke="var(--soil)" strokeWidth="3" strokeLinejoin="round" />
          {sim.waterings.map((w) => (
            <g key={w.d} transform={`translate(${x(w.d)},${y(sim.series[w.d]) - 16})`}>
              <path d="M0 -8 C 4 -2 6 1 6 4 A6 6 0 0 1 -6 4 C -6 1 -4 -2 0 -8 Z" fill={w.wasted ? 'var(--sun)' : 'var(--water)'} stroke="var(--card)" strokeWidth="1.2" />
            </g>
          ))}
          <text x={m.l} y={H - 6}>deň 1</text>
          <text x={width - m.r} y={H - 6} textAnchor="end">deň {DAYS}</text>
        </svg>
      </div>
      <p className="small" style={{ margin: '8px 0 0' }}>
        {mode === 'blind' ? (
          <>Kvapky sú zálievky. <b style={{ color: 'var(--sun-text)' }}>Žlté</b> prišli hneď po daždi, keď mala pôda vody dosť a zálievka bola zbytočná.</>
        ) : (
          <>Zalieva sa až vtedy, keď vlhkosť pri koreňoch klesne k hranici stresu, zato výdatnejšie. Po daždi sa zálievka jednoducho vynechá.</>
        )}{' '}
        <span className="muted">Prerušovaná čiara je druhý spôsob, na porovnanie.</span>
      </p>
    </div>
  )
}
