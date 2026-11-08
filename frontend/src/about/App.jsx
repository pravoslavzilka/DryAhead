import { useEffect, useState } from 'react'
import snapshot from './snapshot.json'
import { AS_OF, DEPLOYED, STATS, NODES, HISTORY } from './deployment'
import { Reveal, Counter, Source, ThemeToggle, fmtDate } from '../blue/ui'
import SoilFigure from '../blue/SoilFigure'
import { DataChart, ForecastChart } from '../blue/charts'
import { SensorDay, Gallery, LiveWidget } from '../blue/parts'

const SECTIONS = [
  ['intro', 'Intro'],
  ['problem', 'Problem'],
  ['how', 'How it works'],
  ['results', 'Results'],
  ['model', 'Forecast'],
  ['history', 'History'],
  ['next', 'Next'],
  ['tech', 'Technical'],
]

const SRC = {
  shmu: 'https://www.teraz.sk/slovensko/shmu-ocakava-do-5-augusta-prehlbeni/981016-clanok.html',
  sme: 'https://www.sme.sk/domov/c/vysoke-teploty-a-nedostatok-zrazok-mali-vplyv-na-povrchovu-aj-podzemnu-vodu',
  konopka: 'https://www.los.sk//asfeu/konopkaJ_2013.pdf',
  lesy: 'https://www.lesy.sk/lesy/media/aktuality/aktuality-tlacove-spravy-novinky/tlacove-spravy/sucasne-sucho-negativne-ovplyvnuje-vitalitu-lesov.html',
  bn: 'https://www.bratislavskenoviny.sk/nasa-tema/51524-novovysadene-stromy-v-hlavnom-meste-vysychaju-preco-je-to-tak',
  ucanr: 'https://ucanr.edu/site/irrigation-and-nutrient-management/soil-moisture-sensors',
  pmc: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC11902337/',
  meteo: 'https://meteotekov.sk/@zajezova',
  fao: 'https://www.fao.org/4/x0490e/x0490e00.htm',
  repo: 'https://github.com/pravoslavzilka/DryAhead',
}

const KINDS = [['field', 'Field'], ['data', 'Data'], ['model', 'Model'], ['fault', 'Fault'], ['fix', 'Fix']]

const pp = (v) => Math.abs(v).toFixed(0)
const fmtInt = (n) => n.toLocaleString('en-GB')
const d = (iso, opts = { day: 'numeric', month: 'short' }) => fmtDate(iso, opts, 'en')
const dLong = (iso) => d(iso, { day: 'numeric', month: 'long', year: 'numeric' })

function useActiveSection() {
  const [active, setActive] = useState(SECTIONS[0][0])
  useEffect(() => {
    const els = SECTIONS.map(([id]) => document.getElementById(id)).filter(Boolean)
    const io = new IntersectionObserver((entries) => {
      const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (vis[0]) setActive(vis[0].target.id)
    }, { rootMargin: '-45% 0px -50% 0px' })
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])
  return active
}

function Nav() {
  const active = useActiveSection()
  useEffect(() => {
    document.querySelector(`.nav-links a[href="#${active}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [active])
  return (
    <nav className="nav" aria-label="Page sections">
      <div className="wrap nav-inner">
        <a className="brand" href="#intro">
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 2c3.5 4.8 6 8.4 6 11.5A6 6 0 0 1 6 13.5C6 10.4 8.5 6.8 12 2Z" fill="var(--water)" />
            <path d="M9 15.5c1.5 1.6 4.5 1.6 6 0" stroke="var(--card)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          </svg>
          DryAhead
        </a>
        <div className="nav-links">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} className={active === id ? 'active' : ''} aria-current={active === id ? 'true' : undefined}>{label}</a>
          ))}
        </div>
        <ThemeToggle />
      </div>
    </nav>
  )
}

function BackToTop() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    const on = () => setShow(window.scrollY > 900)
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])
  return (
    <a href="#intro" className={`icon-btn to-top ${show ? 'show' : ''}`} aria-label="Back to top" tabIndex={show ? 0 : -1}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="M6 14l6-6 6 6" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </a>
  )
}

function StatCard({ value, sub, children, sources = [] }) {
  return (
    <Reveal className="card">
      <div className="stat">{value}</div>
      <div className="stat-sub">{sub}</div>
      <p style={{ margin: 0 }}>{children}</p>
      {sources.map(([href, label]) => <Source key={href} href={href}>{label}</Source>)}
    </Reveal>
  )
}

export default function App() {
  const f = snapshot.findings
  const s7 = snapshot.scores_7d_pp
  const storm = f.storm_0715
  const dry = f.dry_spell_0724_0816
  const dryDrops = Object.values(dry.change_pp).filter((v) => v != null).map((v) => Math.abs(v))
  const rate = (100 * STATS.slots) / STATS.expectedSlots

  return (
    <>
      <a className="skip" href="#content">Skip to content</a>
      <Nav />
      <main id="content">
        {/* Intro */}
        <section id="intro" className="hero">
          <div className="wrap hero-grid">
            <div>
              <span className="badge">In the field since {dLong(DEPLOYED)}</span>
              <h1 style={{ marginTop: 16 }}>DryAhead: sensors that hear the soil’s thirst</h1>
              <p className="lead">
                Water only when the soil really needs it, and save young trees before they dry out.
              </p>
              <p>
                DryAhead is a network of low-cost soil-moisture sensors running on a family plot near Zvolen in
                central Slovakia. Each node measures moisture right at the roots every 20 minutes and sends it by
                long-range radio to a live dashboard. A model fed by local weather predicts when each spot will
                reach plant stress. Everything, from the circuit boards to the forecast, is designed, built and
                programmed by one person.
              </p>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 20 }}>
                <a className="btn" href="#results">See the real data</a>
                <a className="btn ghost" href="/">Open the live dashboard</a>
              </div>
            </div>
            <SoilFigure />
          </div>
        </section>

        {/* Problem */}
        <section id="problem" className="alt">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">The problem</div>
              <h2>Drought comes back every summer</h2>
              <p className="lead">
                On our land we keep sheep and plant trees. Every year the dry spells come back and last longer. Young
                trees die first, and the water to save them comes from wells that are drying up too.
              </p>
            </Reveal>
            <div className="grid grid-3" style={{ marginTop: 24 }}>
              <StatCard value={<Counter to={93} suffix=" %" />} sub="of Slovakia in soil drought" sources={[[SRC.shmu, 'SHMÚ via TASR (teraz.sk)']]}>
                At the end of July 2026, 93 % of the country was in soil drought, from incipient to extreme. Extreme
                drought down to one metre covered <b><Counter to={38} suffix=" %" /></b>, including the Hron region
                around Zvolen.
              </StatCard>
              <StatCard value="↓" sub="Falling groundwater" sources={[[SRC.sme, 'sme.sk']]}>
                In summer 2026, minimum groundwater levels and spring yields were undercut, and reserves are
                refilling more slowly.
              </StatCard>
              <StatCard value={<><Counter to={21} />–<Counter to={38} suffix=" %" /></>} sub="Young trees die first" sources={[[SRC.konopka, 'los.sk (Konôpka, 2013)'], [SRC.lesy, 'Lesy SR']]}>
                Seedling losses in Slovak forest renewal have averaged 21–38 % per decade since 1951. In the dry
                year 2022, one forest district estimated up to <b><Counter to={90} suffix=" %" /></b> losses from
                autumn planting.
              </StatCard>
            </div>
            <Reveal className="narrow">
              <blockquote className="callout">
                Watering blindly “just in case” takes water that is missing elsewhere. Watering too late costs the
                trees. What’s missing is the one piece of information that says when the right time is, and that
                information is in the soil, not on its surface.
              </blockquote>
              <p className="small muted">
                Research on sensor-based irrigation reports water savings of 10–16 % for strawberries and almonds
                without yield loss, and 28.8 % in a field trial with low-cost sensors.
                <Source href={SRC.ucanr}>UC ANR</Source> <Source href={SRC.pmc}>PMC11902337</Source>
              </p>
            </Reveal>
          </div>
        </section>

        {/* How it works */}
        <section id="how">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">How it works</div>
              <h2>A node in the soil, a radio link and the web</h2>
              <p>
                Sensor nodes are buried at the roots and measure every 20 minutes. They send their readings by LoRa
                radio, which works where there is no mobile signal or Wi-Fi, to a base station, and from there to a
                cloud database and the dashboard. They sleep almost all the time, so a battery lasts for months.
              </p>
            </Reveal>
            <Reveal style={{ marginTop: 12 }}>
              <h3>20 minutes in the life of a node</h3>
              <SensorDay />
            </Reveal>
            <Reveal style={{ marginTop: 32 }}>
              <h3>How the data travels</h3>
              <div className="flow">
                <div className="flow-box"><b>Node in the soil</b>measures moisture and temperature, saves the reading to its own flash</div>
                <div className="flow-box"><b>LoRa radio, 433 MHz</b>a short message in the node’s own time slot</div>
                <div className="flow-box"><b>Base station</b>always on; saves first, then uploads</div>
                <div className="flow-box"><b>Supabase database</b>over Wi-Fi and the internet</div>
                <div className="flow-box"><b>Web</b>the live dashboard and this page</div>
              </div>
            </Reveal>
            <div className="grid grid-3" style={{ marginTop: 28 }}>
              <Reveal className="card">
                <h3>Nothing gets lost</h3>
                <p style={{ margin: 0 }}>
                  Every reading is stored on the node before it’s sent, and the base station deletes a reading only
                  once the database confirms it. Every 2 hours a node listens for 3 seconds after sending, so the
                  station can correct its clock or ask for missed readings.
                </p>
              </Reveal>
              <Reveal className="card">
                <h3>As little electronics in nature as possible</h3>
                <p style={{ margin: 0 }}>
                  Not a sensor per tree: soil with a similar type, slope and cover behaves alike, so a few
                  well-placed nodes together with a water-balance model can represent a whole area.
                </p>
              </Reveal>
              <Reveal className="card">
                <h3>Built to be repaired</h3>
                <p style={{ margin: 0 }}>
                  Nodes sit in rugged DN160 sewer-pipe enclosures. When something breaks, it gets fixed, not
                  thrown away. Node 2 is running again today on a board rescued from node 3.
                </p>
              </Reveal>
            </div>
          </div>
        </section>

        {/* Results */}
        <section id="results" className="alt">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">Results</div>
              <h2>Not a plan: {STATS.days} days of real measurements</h2>
              <p className="lead">
                By {dLong(AS_OF)} the five nodes had stored <b>{fmtInt(STATS.readings)}</b> readings, filling{' '}
                <b>{fmtInt(STATS.slots)}</b> of the 20-minute slots since deployment ({rate.toFixed(0)} %). The nodes
                without a hardware fault deliver 81–87 % of their slots.
              </p>
            </Reveal>

            <Reveal style={{ marginTop: 20 }}><LiveWidget snapshot={snapshot} /></Reveal>

            <Reveal className="card" style={{ marginTop: 20 }}>
              <h3>Soil moisture at four spots on the land</h3>
              <DataChart snapshot={snapshot} />
            </Reveal>

            <div className="two-col" style={{ marginTop: 20 }}>
              <Reveal className="card">
                <h3>What the data says</h3>
                <ul className="clean">
                  <li>
                    <b>Same rain, completely different response.</b> After the storm of {d('2026-07-15', { day: 'numeric', month: 'long' })}{' '}
                    ({storm.rain_mm} mm), moisture rose within a day by {pp(storm.change_pp['3'])} points at node 3,{' '}
                    {pp(storm.change_pp['4'])} at node 4, {pp(storm.change_pp['5'])} at node 5 and only{' '}
                    {pp(storm.change_pp['1'])} at node 1. Every spot needs water differently.
                  </li>
                  <li>
                    <b>A good soaking lasts for weeks.</b> At node 4 that storm took moisture from{' '}
                    {pp(f.node4_after_storm.before)} % to {pp(f.node4_after_storm.day_after)} %, and 35 days later it
                    was still {pp(f.node4_after_storm.after_35_days)} %.
                  </li>
                  <li>
                    <b>Light rain never reaches the roots.</b> None of six 1–3 mm rains raised moisture at nodes 4 and
                    5. Over {dry.days} days without rain (24 July – 16 August), moisture fell by{' '}
                    {Math.round(Math.min(...dryDrops))} to {Math.round(Math.max(...dryDrops))} points.
                  </li>
                </ul>
                <p className="small muted" style={{ margin: 0 }}>Computed from the measured data (daily medians) and the Zaježová weather station’s rain.</p>
              </Reveal>
              <Reveal className="card">
                <h3>Delivery per node</h3>
                <div className="table-scroll">
                  <table>
                    <caption className="small muted" style={{ captionSide: 'bottom', textAlign: 'left', paddingTop: 6 }}>
                      Share of the {fmtInt(STATS.expectedSlots / NODES.length)} 20-minute slots per node between {d(DEPLOYED)} and{' '}
                      {d(AS_OF)} that have a reading. Low numbers are hardware faults, not the radio: signal stayed
                      between −95 and −97 dBm.
                    </caption>
                    <thead><tr><th>Node</th><th>Status</th><th className="num">Days</th><th className="num">Delivered</th></tr></thead>
                    <tbody>
                      {NODES.map((n) => (
                        <tr key={n.id}>
                          <td>{n.id}</td>
                          <td className="status"><span className={`pill ${n.tone}`}>{n.status}</span></td>
                          <td className="num">{n.days}</td>
                          <td className="num"><b>{n.rate.toFixed(1)} %</b></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Reveal>
            </div>

            <Reveal style={{ marginTop: 28 }}>
              <h3>From the field</h3>
              <Gallery />
            </Reveal>
          </div>
        </section>

        {/* Model */}
        <section id="model">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">The forecast</div>
              <h2>When will the soil reach plant stress?</h2>
              <p>
                For nodes 1, 4 and 5 the live dashboard shows how many days remain until the soil gets so dry that
                plants struggle to draw water if no rain falls, plus a second line that includes the rain in the
                16-day weather forecast. Both run in the browser from two small physically-based models, fitted for
                each node separately:
              </p>
            </Reveal>
            <div className="grid grid-2" style={{ marginTop: 16 }}>
              <Reveal className="card">
                <h3>Drying model</h3>
                <p style={{ margin: 0 }}>
                  How the soil dries between rains. Excess water drains first, then plants and sun take water in
                  proportion to evaporation demand computed from the local weather station (FAO-56 Penman–Monteith),
                  slowing down once plants are stressed. Five parameters per node.
                </p>
              </Reveal>
              <Reveal className="card">
                <h3>Wetting model</h3>
                <p style={{ margin: 0 }}>
                  How far the soil gets wetter when rain falls. At node 4 the top layer holds the first ~4.4 mm, and
                  after that moisture rises within 1–2 hours. Node 5 responds in proportion to rain but 11–50 hours
                  later. Node 1 doesn’t follow the station’s rain at all, so water seems to reach it another way.
                </p>
              </Reveal>
            </div>
            <div className="two-col" style={{ marginTop: 20 }}>
              <Reveal className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <h3 style={{ margin: 0 }}>Forecast vs reality</h3>
                  <span className="tag-exp">held-out days</span>
                </div>
                <p className="small" style={{ marginTop: 8 }}>
                  The model started from a single measurement ({d(snapshot.forecast_demo.dates[0], { day: 'numeric', month: 'long' })},
                  node {snapshot.forecast_demo.node}) and forecast the following days, none of which it saw while learning.
                </p>
                <ForecastChart demo={snapshot.forecast_demo} />
              </Reveal>
              <Reveal className="card">
                <h3>How good is it?</h3>
                <div className="table-scroll">
                  <table>
                    <caption className="small muted" style={{ captionSide: 'bottom', textAlign: 'left', paddingTop: 6 }}>
                      Average error 7 days ahead, in moisture percentage points (lower is better), on days the model
                      never saw. 7-day forecasts per node: {Object.values(s7).map((v) => v.n).join(', ')}.
                    </caption>
                    <thead><tr><th>Node</th><th className="num">Model</th><th className="num">“Stays the same”</th><th className="num">Average trend</th></tr></thead>
                    <tbody>
                      {Object.entries(s7).map(([id, v]) => (
                        <tr key={id}>
                          <td>{id}</td>
                          <td className="num"><b>{v.model.toFixed(1)}</b></td>
                          <td className="num">{v.persistence.toFixed(1)}</td>
                          <td className="num">{v.drift.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="small" style={{ margin: '10px 0 0' }}>
                  The drying model beats both simple baselines on every node. It’s honest to say what it rests on:
                  one summer of data and a handful of forecasts per node. Autumn and winter drying is still
                  extrapolation, and the models get refitted as the record grows.
                </p>
              </Reveal>
            </div>
            <Reveal className="narrow" style={{ marginTop: 24 }}>
              <h3>How it got here</h3>
              <p>
                The first model was a single FAO-56 “bucket” of root-zone water with nine parameters, driven by rain
                and evaporation from a global weather model. On unseen days it lost to “tomorrow is the same as today”
                on every node. The reasons: the global model badly misplaced local storms (1.3 mm forecast for a
                24.7 mm storm), one model was learning rain and drying at once, percentages clipped at 0–100 % threw
                information away, and there were more parameters than the data could tell apart. Local station
                weather, raw sensor values, separate drying and wetting models and fewer parameters fixed it.
              </p>
            </Reveal>
          </div>
        </section>

        {/* History */}
        <section id="history" className="alt">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">History</div>
              <h2>{STATS.days} days in the field</h2>
              <p>
                What happened since the nodes went into the ground, including what broke. Both real hardware failures
                were build-quality problems, not the radio, the firmware or the cloud.
              </p>
            </Reveal>
            <Reveal className="narrow">
              <div className="history-key" aria-hidden="true">
                {KINDS.map(([k, label]) => <span key={k} style={{ '--k': `var(--${{ field: 'soil', data: 'water', model: 'leaf', fault: 'warn', fix: 'water-2' }[k]})` }}>{label}</span>)}
              </div>
              <ol className="history">
                {HISTORY.map((h) => (
                  <li key={h.date + h.title} className={`k-${h.kind}`}>
                    <div className="when">{d(h.date, { day: 'numeric', month: 'long' })}</div>
                    <b>{h.title}</b>
                    <p>{h.text}</p>
                  </li>
                ))}
              </ol>
            </Reveal>
          </div>
        </section>

        {/* Next */}
        <section id="next">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">What’s next</div>
              <h2>Lessons from the field, turned into a plan</h2>
            </Reveal>
            <div className="grid grid-2" style={{ marginTop: 16 }}>
              <Reveal className="card">
                <h3>Sealed, checked enclosures</h3>
                <p style={{ margin: 0 }}>IP67 with cable glands and a gasketed antenna feedthrough, plus a solder and assembly check before deployment, the two things that took out nodes 2 and 3.</p>
              </Reveal>
              <Reveal className="card">
                <h3>A health channel in the firmware</h3>
                <p style={{ margin: 0 }}>Battery voltage, reset reason and sensor health in every message, so a draining battery or a failing clock shows up in days, not after the node goes silent.</p>
              </Reveal>
              <Reveal className="card">
                <h3>Calibrated moisture</h3>
                <p style={{ margin: 0 }}>Readings are a relative signal today. Calibrating against oven-dried soil samples per soil type will turn them into true volumetric moisture.</p>
              </Reveal>
              <Reveal className="card">
                <h3>A second site</h3>
                <p style={{ margin: 0 }}>A pilot on another plot with different soil, to measure how much water soil-based watering really saves at young trees, and to give the model something to generalise across.</p>
              </Reveal>
            </div>
          </div>
        </section>

        {/* Technical */}
        <section id="tech" className="alt">
          <div className="wrap">
            <Reveal>
              <details className="tech">
                <summary>Technical details</summary>
                <div className="tech-body">
                  <h3>Node hardware</h3>
                  <ul className="clean">
                    <li>LaskaKit ESP32-DevKit, LoRa radio (Semtech SX127x, 433 MHz), DS3231 real-time clock with backup cell, capacitive soil-moisture probe, 3000 mAh Li-Po, DN160 pipe enclosure.</li>
                    <li>Deep sleep at 11–12 µA. One switched pin (GPIO2) cuts power to radio, sensor and clock, and the I²C lines are pulled low before sleep so no current leaks through them.</li>
                    <li>The node computes its sleep time from the clock before cutting power, so it wakes exactly in its own slot (node 1 at :04, :24, :44, node 2 at :08, and so on).</li>
                    <li>Every reading is kept in on-board flash (LittleFS). When node 3’s radio failed, its full log could still be read out over USB.</li>
                  </ul>

                  <h3>Data quality</h3>
                  <ul className="clean">
                    <li>Each reading has a unique key (node + measurement time), so a resent message never creates a duplicate row.</li>
                    <li>About 9 % of messages arrived twice with the same content, nodes often log two readings 8–13 s apart in one slot, and a failing clock writes time zero. All of it is filtered before modelling.</li>
                    <li>The first two days after installation are left out while the sensors settle into the soil.</li>
                  </ul>

                  <h3>The drying model</h3>
                  <div className="eq">{`x   = sensor value (higher = drier soil)
ET0 = reference evaporation from the weather station (mm/day)

1. excess water drains:  if the soil is wetter than field capacity x_fc,
                         x += (x_fc − x) · (1 − e^(−1/τ))
2. plant stress:         Ks = 1 while water is plentiful;
                         falls to 0 at the wilting point x_wp past the stress point
3. drying:               x += Ks · k · ET0`}</div>
                  <p className="small muted">
                    Five parameters (x_fc, x_wp, stress point, τ, k) are fitted per node with differential evolution
                    and scored only on days the model never saw.
                  </p>

                  <h3>Software</h3>
                  <ul className="clean">
                    <li>Firmware in C++ (Arduino framework) on the nodes and the hub; the hub writes to Supabase (PostgreSQL) over its REST API.</li>
                    <li>Web in React + Vite on Vercel. The forecast runs in the browser from exported model parameters.</li>
                    <li>Models in Python (NumPy, SciPy, pandas), weather from the <a href={SRC.meteo} target="_blank" rel="noopener noreferrer">Zaježová station</a> next to the land, measured every minute.</li>
                  </ul>

                  <h3>Links</h3>
                  <ul className="clean">
                    <li><a href="/">Live dashboard</a></li>
                    <li><a href="/blue/">Blue Challenge presentation (Slovak)</a></li>
                    <li>Source code: <a href={SRC.repo} target="_blank" rel="noopener noreferrer">github.com/pravoslavzilka/DryAhead</a></li>
                    <li>Evaporation method: <a href={SRC.fao} target="_blank" rel="noopener noreferrer">FAO-56, Crop evapotranspiration</a></li>
                  </ul>
                </div>
              </details>
            </Reveal>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap two-col">
          <div>
            <h2 style={{ fontSize: '1.5rem' }}>Pravoslav Žilka</h2>
            <p>
              Mechanical engineering student at Brno University of Technology. I’m building DryAhead for our family
              land in central Slovakia, where every summer I watch drought take young trees and water from the wells.
            </p>
            <p>Contact: <a href="mailto:pravoslav.zilka@gmail.com">pravoslav.zilka@gmail.com</a></p>
            <p className="small muted">
              Deployment figures as of {dLong(AS_OF)}; charts from a data snapshot of {dLong(snapshot.generated)}. The
              page works without a connection to the database.
            </p>
          </div>
          <div>
            <h3>Sources</h3>
            <ol>
              <li>SHMÚ via TASR: <a href={SRC.shmu}>teraz.sk</a></li>
              <li>Groundwater 2026: <a href={SRC.sme}>sme.sk</a></li>
              <li>Seedling losses since 1951: <a href={SRC.konopka}>los.sk (Konôpka, 2013)</a></li>
              <li>Drought 2022, Lesy SR: <a href={SRC.lesy}>lesy.sk</a></li>
              <li>Young trees and watering: <a href={SRC.bn}>bratislavskenoviny.sk</a></li>
              <li>Soil sensors, 10–16 %: <a href={SRC.ucanr}>ucanr.edu</a></li>
              <li>Low-cost sensors, 28.8 %: <a href={SRC.pmc}>PMC11902337</a></li>
              <li>Zaježová weather station: <a href={SRC.meteo}>meteotekov.sk</a></li>
              <li>FAO-56: <a href={SRC.fao}>fao.org</a></li>
            </ol>
          </div>
        </div>
      </footer>
      <BackToTop />
    </>
  )
}
