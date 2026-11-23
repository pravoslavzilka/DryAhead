import { useEffect, useState } from 'react'
import snapshot from './snapshot.json'
import { Reveal, Counter, Source, ThemeToggle, fmtDate } from './ui'
import SoilFigure from './SoilFigure'
import { DataChart, ForecastChart, WateringCompare } from './charts'
import { SensorDay, Coverage, Gallery, LiveWidget } from './parts'

const SECTIONS = [
  ['uvod', 'Úvod'],
  ['problem', 'Problém'],
  ['preco', 'Prečo nie viac vody'],
  ['riesenie', 'Riešenie'],
  ['sporenie', 'Šetrenie vody'],
  ['ako', 'Ako to funguje'],
  ['prax', 'V praxi'],
  ['plan', 'Plán'],
  ['rozpocet', '1 000 €'],
  ['technika', 'Technika'],
]

const SRC = {
  shmu: 'https://www.teraz.sk/slovensko/shmu-ocakava-do-5-augusta-prehlbeni/981016-clanok.html',
  sme: 'https://www.sme.sk/domov/c/vysoke-teploty-a-nedostatok-zrazok-mali-vplyv-na-povrchovu-aj-podzemnu-vodu',
  topky: 'https://www.topky.sk/cl/10/9470211/ZUFALSTVO-na-vychode-Slovenska--V-obciach-vyschli-studne--nemaju-cim-splachovat-a-varit--Vodovod-nemaju',
  konopka: 'https://www.los.sk//asfeu/konopkaJ_2013.pdf',
  lesy: 'https://www.lesy.sk/lesy/media/aktuality/aktuality-tlacove-spravy-novinky/tlacove-spravy/sucasne-sucho-negativne-ovplyvnuje-vitalitu-lesov.html',
  lepsiden: 'https://lepsiden.sk/sucho-sposobuje-studne-vysychaju-co-ak-ubuda-voda/',
  noviny: 'https://www.noviny.sk/slovensko/1241527-zapasime-so-silnym-suchom-hydrolog-narovinu-o-tom-s-cim-musia-slovaci-prestat',
  bn: 'https://www.bratislavskenoviny.sk/nasa-tema/51524-novovysadene-stromy-v-hlavnom-meste-vysychaju-preco-je-to-tak',
  ucanr: 'https://ucanr.edu/site/irrigation-and-nutrient-management/soil-moisture-sensors',
  pmc: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC11902337/',
  meteo: 'https://meteotekov.sk/@zajezova',
  fao: 'https://www.fao.org/4/x0490e/x0490e00.htm',
}

const pp = (v) => Math.abs(v).toFixed(0)
const fmtInt = (n) => n.toLocaleString('sk-SK')

function useActiveSection() {
  const [active, setActive] = useState('uvod')
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
    <nav className="nav" aria-label="Sekcie stránky">
      <div className="wrap nav-inner">
        <a className="brand" href="#uvod">
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
    <a href="#uvod" className={`icon-btn to-top ${show ? 'show' : ''}`} aria-label="Späť hore" tabIndex={show ? 0 : -1}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true"><path d="M6 14l6-6 6 6" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </a>
  )
}

function StatCard({ value, sub, children, sources }) {
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
  const node3End = snapshot.nodes['3']?.last_day
  const dryDrops = Object.values(dry.change_pp).filter((v) => v != null).map((v) => Math.abs(v))

  return (
    <>
      <a className="skip" href="#obsah">Preskočiť na obsah</a>
      <Nav />
      <main id="obsah">
        {/* 1. Úvod */}
        <section id="uvod" className="hero">
          <div className="wrap hero-grid">
            <div>
              <span className="badge">Blue Challenge 2026 · Udržateľnosť</span>
              <h1 style={{ marginTop: 16 }}>DryAhead: senzory, ktoré počujú smäd pôdy</h1>
              <p className="lead">Zalievať len vtedy, keď to pôda naozaj potrebuje, a zachrániť mladé stromy skôr, než uschnú.</p>
              <p>
                Sucho dnes na Slovensku nie je výnimka, ale pravidlo. Postavil som sieť lacných senzorov pôdnej vlhkosti,
                ktorá už funguje na našej rodinnej pôde pri Zvolene. Meria vlahu priamo pri koreňoch, a tak ukazuje,
                kedy stromy a pôda naozaj potrebujú vodu a kedy nie. Cieľ je jednoduchý: menej vody z vyčerpaných studní,
                viac prežitých stromov.
              </p>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 20 }}>
                <a className="btn" href="#prax">Pozrieť reálne dáta</a>
                <a className="btn ghost" href="#ako">Ako to funguje</a>
              </div>
            </div>
            <SoilFigure />
          </div>
        </section>

        {/* 2. Problém */}
        <section id="problem" className="alt">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">Problém</div>
              <h2>Sucho sa vracia každé leto</h2>
              <p className="lead">
                Na našej pôde pri Zvolene chováme ovce a sadíme stromy. Posledné roky vidím, ako sa sucho vracia každé leto
                a trvá dlhšie. Nie je to len náš problém.
              </p>
            </Reveal>
            <div className="grid grid-2" style={{ marginTop: 24 }}>
              <StatCard value={<Counter to={93} suffix=" %" />} sub="Slovenska v pôdnom suchu" sources={[[SRC.shmu, 'SHMÚ (cez TASR, teraz.sk)']]}>
                Koncom júla 2026 bolo začínajúce až extrémne pôdne sucho na 93 % územia. Extrémne sucho v profile do jedného
                metra zasahovalo <b><Counter to={38} suffix=" %" /></b> územia, vrátane Pohronia, kam patrí aj Zvolen.
              </StatCard>
              <StatCard value={<Counter to={0.9} decimals={1} suffix=" mm" />} sub="zrážok za celý júl" sources={[[SRC.shmu, 'SHMÚ (cez TASR, teraz.sk)']]}>
                V Hurbanove, kde sa meria od roku 1872, bol najsuchší júl v roku 2024: spadlo len 0,9 mm zrážok.
              </StatCard>
              <StatCard value="↓" sub="Klesá podzemná voda" sources={[[SRC.sme, 'sme.sk'], [SRC.topky, 'topky.sk']]}>
                V lete 2026 boli podkročené minimálne hladiny podzemnej vody aj výdatnosti prameňov a zásoby sa dopĺňajú
                pomalšie. V obciach Nižný a Vyšný Čaj vyschli ľuďom studne a vyhlásili mimoriadnu situáciu.
              </StatCard>
              <StatCard value={<><Counter to={21} />–<Counter to={38} suffix=" %" /></>} sub="Mladé stromy umierajú ako prvé" sources={[[SRC.konopka, 'los.sk (Konôpka, 2013, PDF)'], [SRC.lesy, 'Lesy SR']]}>
                Pri obnove lesa sa straty sadeníc od roku 1951 pohybovali v priemere od 21 do 38 % za desaťročie. V suchom
                roku 2022 odhadovala jedna lesná správa Lesov SR straty z jesenného zalesňovania až na <b><Counter to={90} suffix=" %" /></b>.
              </StatCard>
            </div>
            <Reveal className="narrow">
              <blockquote className="callout">
                Keď je sucho, prirodzene chceme zalievať viac. Voda na zálievku však často pochádza zo studní a podzemných
                zdrojov, ktoré sú počas sucha najzraniteľnejšie. Zalievať naslepo „pre istotu“ znamená brať vodu, ktorá
                chýba inde. Nezaliať včas zas znamená prísť o stromy. Chýba informácia, ktorá by povedala, kedy je ten
                správny čas.
              </blockquote>
            </Reveal>
          </div>
        </section>

        {/* 3. Prečo nestačí zalievať viac */}
        <section id="preco">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">Prečo nestačí zalievať viac</div>
              <h2>Voda sa niekde musí vziať</h2>
              <p className="lead">
                Keď príde sucho, prvý reflex je zalievať viac. Lenže voda na zálievku sa niekde musí vziať, a v suchu je jej
                najmenej práve tam, odkiaľ ju berieme.
              </p>
            </Reveal>
            <div className="grid grid-2" style={{ marginTop: 20 }}>
              <Reveal className="card">
                <h3>Podzemná voda sa dopĺňa pomaly</h3>
                <p>Jej zásoby závisia od dlhodobých zrážok, stavu pôdy aj vegetácie. Keď na jeseň, v zime a na jar neprší dosť, voda sa nestihne vsiaknuť do hlbších vrstiev a hladina klesá. Čo z nej v lete vyčerpáme, sa nevráti za pár dní.</p>
                <Source href={SRC.lepsiden} />
              </Reveal>
              <Reveal className="card">
                <h3>Viac čerpania počas sucha škodí aj okoliu</h3>
                <p>Hydrológovia upozorňujú, že nadmerný odber počas sucha môže studne vysušiť alebo zhoršiť stav okolitých zdrojov. Voda, ktorú zbytočne vylejem na pole, môže chýbať susedovi v studni.</p>
                <Source href={SRC.noviny} />
              </Reveal>
              <Reveal className="card">
                <h3>Viac vody nie je vždy lepšie ani pre strom</h3>
                <p>Pri výsadbe nesmie v jame stáť voda, inak korene zhnijú. Stromom škodí sucho aj premokrenie.</p>
                <Source href={SRC.bn} />
              </Reveal>
              <Reveal className="card">
                <h3>Dlhodobé riešenie je krajina, ktorá vodu zadrží</h3>
                <p>Podľa hydrológov je najlacnejším a najefektívnejším riešením pestrá krajina, ktorá vodu v daždi zadrží a v suchu postupne uvoľňuje. Technické riešenia sú doplnok, nie náhrada.</p>
                <Source href={SRC.noviny} />
              </Reveal>
            </div>
            <Reveal className="narrow">
              <p className="lead" style={{ marginTop: 28 }}>
                Preto je prvým krokom šetriť: dať vodu presne tam a presne vtedy, kde a kedy chýba. A na to treba vedieť,
                čo sa deje v pôde.
              </p>
            </Reveal>
          </div>
        </section>

        {/* 4. Riešenie */}
        <section id="riesenie" className="alt">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">Riešenie</div>
              <h2>Merať tam, kde sú korene</h2>
              <p className="lead">
                DryAhead meria vlhkosť pôdy priamo v zemi, tam, kde sú korene. Namiesto odhadu podľa počasia alebo pocitu
                tak vidno, koľko vody pôda naozaj má.
              </p>
            </Reveal>
            <div className="grid grid-3" style={{ marginTop: 20 }}>
              <Reveal className="card icon-card">
                <div className="ico" aria-hidden="true">💧</div>
                <h3>Menej vody zo studní</h3>
                <p style={{ margin: 0 }}>Zalievať len vtedy, keď pôda vodu naozaj potrebuje. Každý liter, ktorý netreba načerpať, zostáva v krajine.</p>
              </Reveal>
              <Reveal className="card icon-card">
                <div className="ico" aria-hidden="true">🌱</div>
                <h3>Viac prežitých mladých stromov</h3>
                <p>
                  Novovysadený strom nemá rozvinuté korene a prvé roky je odkázaný na zálievku. Podľa arboristov je najčastejšou
                  príčinou úhynu mladých stromov po výsadbe to, že sú polievané málo alebo zle. Na dashboarde DryAhead vidno,
                  keď vlhkosť pri koreňoch klesá k hranici, pri ktorej strom začína trpieť.
                </p>
                <Source href={SRC.bn} />
              </Reveal>
              <Reveal className="card icon-card">
                <div className="ico" aria-hidden="true">⏱️</div>
                <h3>Včasné varovanie pred suchom</h3>
                <p style={{ margin: 0 }}>
                  Pracujem na modeli vodnej bilancie pôdy, ktorý má vopred upozorniť, že sa blíži nebezpečné sucho. Zatiaľ ho
                  testujem na reálnych dátach a ešte nie je dosť presný na ostré použitie. Otvorene to priznávam, lebo varovanie
                  má zmysel len vtedy, keď sa naň dá spoľahnúť.
                </p>
              </Reveal>
            </div>
          </div>
        </section>

        {/* 5. Ako senzory pomáhajú šetriť vodu */}
        <section id="sporenie">
          <div className="wrap two-col">
            <Reveal>
              <div className="eyebrow">Šetrenie vody v praxi</div>
              <h2>Povrch pôdy klame</h2>
              <p>
                Väčšina ľudí zalieva podľa kalendára alebo podľa toho, ako vyzerá povrch pôdy. Povrch však klame: môže byť
                suchý, kým pri koreňoch je vlahy dosť, alebo naopak. Senzor v zemi ukazuje, čo sa deje tam, kde to rozhoduje.
              </p>
              <ul className="clean">
                <li><b>Nezalievať zbytočne.</b> Po daždi senzor ukáže, že pôda má zásobu, a zálievku možno vynechať.</li>
                <li><b>Zalievať včas.</b> Keď vlhkosť pri koreňoch klesá k hranici stresu, človek to vie skôr, než strom začne vädnúť.</li>
                <li><b>Zalievať správne.</b> Z dát vidno, ako rýchlo pôda vysychá a ako hlboko voda vsiakne. Namiesto častého plytkého polievania sa dá zalievať menej často, ale tak, aby sa voda dostala ku koreňom.</li>
                <li><b>Rozhodnúť, kam vodu dať.</b> Ak je vody málo, dáta ukážu, ktoré miesto alebo ktoré stromy ju potrebujú najviac.</li>
              </ul>
            </Reveal>
            <div>
              <Reveal><WateringCompare /></Reveal>
              <Reveal className="card" style={{ marginTop: 16 }}>
                <p style={{ margin: 0 }}>
                  <b>Výskum ukazuje</b>, že zavlažovanie podľa pôdnych senzorov šetrí vodu: o 10–16 % pri jahodách a mandliach
                  bez straty úrody, o 28,8 % v poľnom pokuse s lacnými senzormi. Koľko ušetrí DryAhead pri stromoch, chcem
                  zmerať v najbližšej fáze projektu.
                </p>
                <Source href={SRC.ucanr}>UC Agriculture and Natural Resources</Source>
                <Source href={SRC.pmc}>PMC, článok PMC11902337</Source>
              </Reveal>
            </div>
          </div>
        </section>

        {/* 6. Ako to funguje */}
        <section id="ako" className="alt">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">Ako to funguje</div>
              <h2>Uzol v zemi, rádio a web</h2>
              <p>
                Senzorové uzly sú zakopané v pôde a každých 20 minút merajú vlhkosť. Dáta posielajú rádiom (LoRa) na
                vzdialenosť, kde nie je mobilný signál ani WiFi, do centrálnej stanice a odtiaľ na web. Väčšinu času spia,
                takže spotrebujú minimum energie. Všetko som navrhol, postavil a naprogramoval sám.
              </p>
            </Reveal>
            <Reveal style={{ marginTop: 12 }}>
              <h3>20 minút v živote senzora</h3>
              <SensorDay />
            </Reveal>
            <div className="two-col" style={{ marginTop: 36 }}>
              <Reveal>
                <h3>Čo najmenej elektroniky v prírode</h3>
                <p>
                  Nechcem zaplniť lesy a polia elektronikou. Preto DryAhead nestavia na senzore pri každom strome. Pôda
                  s podobným typom, sklonom a porastom sa správa podobne, takže niekoľko dobre umiestnených uzlov môže
                  reprezentovať celú plochu. Cieľom je, aby malá sieť senzorov spolu s modelom vodnej bilancie odhadla stav
                  vlahy pre celé územie.
                </p>
                <h3>Dlhá životnosť</h3>
                <p>
                  Uzly väčšinu času spia a spotrebúvajú len zlomok energie. Sú uložené v odolných krytoch proti dažďu,
                  vlhkosti a teplotným výkyvom. Keď sa niečo pokazí, uzol sa dá opraviť, netreba ho vyhodiť a nahradiť novým.
                </p>
              </Reveal>
              <Reveal><Coverage /></Reveal>
            </div>
          </div>
        </section>

        {/* 7. DryAhead v praxi */}
        <section id="prax">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">DryAhead v praxi</div>
              <h2>Nie plán, ale reálne merania</h2>
              <p className="lead">
                Od konca júna 2026 sú na našej pôde pri Zvolene v prevádzke senzorové uzly. Doteraz nazbierali{' '}
                <b>{fmtInt(snapshot.total_measurements)}</b> meraní. Uzly 1, 4 a 5 merajú bez prestávky
                {node3End && <>, uzol 3 posielal dáta do {fmtDate(node3End, { day: 'numeric', month: 'numeric' })}</>}
              </p>
            </Reveal>

            <Reveal style={{ marginTop: 20 }}><LiveWidget snapshot={snapshot} /></Reveal>

            <Reveal className="card" style={{ marginTop: 20 }}>
              <h3>Vlhkosť pôdy na štyroch miestach pozemku</h3>
              <DataChart snapshot={snapshot} />
            </Reveal>

            <div className="two-col" style={{ marginTop: 20 }}>
              <Reveal className="card">
                <h3>Čo hovoria dáta</h3>
                <ul className="clean">
                  <li>
                    <b>Rovnaký dážď, úplne iná odozva.</b> Po búrke {fmtDate('2026-07-15', { day: 'numeric', month: 'numeric' })}{' '}
                    ({String(storm.rain_mm).replace('.', ',')} mm) stúpla vlhkosť za jeden deň pri uzle 3 o {pp(storm.change_pp['3'])} bodov,
                    pri uzle 4 o {pp(storm.change_pp['4'])}, pri uzle 5 o {pp(storm.change_pp['5'])} a pri uzle 1 len o {pp(storm.change_pp['1'])}.
                    Každé miesto na pozemku potrebuje vodu inak.
                  </li>
                  <li>
                    <b>Výdatný dážď vydrží týždne.</b> Pri uzle 4 stúpla vlhkosť po tej búrke z {pp(f.node4_after_storm.before)} % na{' '}
                    {pp(f.node4_after_storm.day_after)} % a ešte o 35 dní neskôr bola {pp(f.node4_after_storm.after_35_days)} %.
                  </li>
                  <li>
                    <b>Slabý dážď ku koreňom nedôjde.</b> Ani jeden zo šiestich dažďov s 1–3 mm nezvýšil vlhkosť pri uzloch 4 a 5.
                    A počas {dry.days} dní bez dažďa (24. 7. – 16. 8.) klesla vlhkosť o {Math.round(Math.min(...dryDrops))} až{' '}
                    {Math.round(Math.max(...dryDrops))} bodov.
                  </li>
                </ul>
                <p className="small muted" style={{ margin: 0 }}>Vypočítané z nameraných dát (denné mediány) a zo zrážok meteostanice Zaježová.</p>
              </Reveal>
              <Reveal className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <h3 style={{ margin: 0 }}>Predpoveď vysychania</h3>
                  <span className="tag-exp">experimentálne</span>
                </div>
                <p className="small" style={{ marginTop: 8 }}>
                  Model som spustil z jediného merania ({fmtDate(snapshot.forecast_demo.dates[0], { day: 'numeric', month: 'numeric' })},
                  uzol {snapshot.forecast_demo.node}) a nechal ho predpovedať ďalšie dni. Tieto dni pri učení nevidel.
                </p>
                <ForecastChart demo={snapshot.forecast_demo} />
                <div className="table-scroll">
                  <table style={{ marginTop: 10 }}>
                    <caption className="small muted" style={{ captionSide: 'bottom', textAlign: 'left', paddingTop: 6 }}>
                      Priemerná chyba predpovede na 7 dní dopredu, v percentuálnych bodoch vlhkosti (menej je lepšie). Počet 7-dňových predpovedí na uzol: {Object.values(s7).map((v) => v.n).join(', ')}.
                    </caption>
                    <thead><tr><th>Uzol</th><th className="num">Model</th><th className="num">„Zostane to tak“</th></tr></thead>
                    <tbody>
                      {Object.entries(s7).map(([id, v]) => (
                        <tr key={id}>
                          <td>{id}</td>
                          <td className="num"><b>{v.model.toFixed(1).replace('.', ',')}</b></td>
                          <td className="num">{v.persistence.toFixed(1).replace('.', ',')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="small" style={{ margin: '10px 0 0' }}>
                  Na dňoch, ktoré model nevidel, predpovedal vysychanie presnejšie ako odhad „zostane to tak“. Stojí to však
                  len na pár týždňoch letných dát a niekoľkých predpovediach na uzol, preto ho zatiaľ nepoužívam na ostré
                  varovania.
                </p>
              </Reveal>
            </div>

            <Reveal style={{ marginTop: 28 }}>
              <h3>Z terénu</h3>
              <Gallery />
            </Reveal>

            <Reveal style={{ marginTop: 24, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <a className="btn" href="/">Otvoriť živý dashboard</a>
              <span className="small muted">Aktuálne merania zo všetkých uzlov a experimentálna predpoveď sucha.</span>
            </Reveal>
          </div>
        </section>

        {/* 8. Stav a plán */}
        <section id="plan" className="alt">
          <div className="wrap">
            <Reveal className="narrow">
              <div className="eyebrow">Stav projektu a plán</div>
              <h2>DryAhead je vo vývoji</h2>
              <p>
                Senzorová sieť už reálne funguje v teréne, zber dát beží a model včasného varovania testujem. Nejde však
                o hotový produkt a netvárim sa, že je.
              </p>
              <h3>Od jednej pôdy k ďalším projektom</h3>
              <p>
                Mám rozbehnutú spoluprácu s Nadáciou Partnerství v Česku, ktorá podporuje ľudí a obce pri výsadbe stromov.
                Nadácia by mohla DryAhead odporúčať ľuďom, ktorí stromy sadia, aby ich mladé stromy prežili prvé kritické
                roky s čo najmenšou spotrebou vody. Začínam práve s ňou. Na Slovensku chcem projekt postupne rozšíriť cez
                Ekopolis na projekty, ktoré sadia stromy.
              </p>
              <p className="lead">
                Cieľ: aby ľudia, ktorí sadia stromy a starajú sa o krajinu, hospodárili s vodou lepšie a zároveň im prežilo
                viac vysadených stromov.
              </p>
            </Reveal>
            <Reveal>
              <ol className="timeline" style={{ marginTop: 20 }}>
                <li className="now"><div className="when">Dnes</div><b>Uzly v teréne pri Zvolene</b><p className="small" style={{ margin: 0 }}>Zber dát beží od konca júna 2026, model testujem.</p></li>
                <li><div className="when">Ďalší krok</div><b>Pilot na ďalšej lokalite</b><p className="small" style={{ margin: 0 }}>Overiť, koľko vody sa pri mladých stromoch reálne ušetrí.</p></li>
                <li><div className="when">Potom</div><b>Odporúčanie cez Nadáciu Partnerství</b><p className="small" style={{ margin: 0 }}>Ľuďom, ktorí v Česku sadia stromy.</p></li>
                <li><div className="when">Cieľ</div><b>Rozšírenie cez Ekopolis</b><p className="small" style={{ margin: 0 }}>Na projekty, ktoré na Slovensku sadia stromy.</p></li>
              </ol>
            </Reveal>
          </div>
        </section>

        {/* 9. 1 000 € */}
        <section id="rozpocet">
          <div className="wrap narrow">
            <Reveal>
              <div className="eyebrow">Rozpočet</div>
              <h2>Na čo pôjde 1 000 €</h2>
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Položka</th><th className="num">Suma</th></tr></thead>
                  <tbody>
                    <tr><td>Uzly na pilotnú lokalitu: 12 uzlov × 45 € <span className="muted small">(30 € elektronika, 15 € kryt)</span></td><td className="num">540 €</td></tr>
                    <tr><td>Centrálna stanica pre pilotnú lokalitu</td><td className="num">60 €</td></tr>
                    <tr><td>Batérie a náhradné senzory</td><td className="num">150 €</td></tr>
                    <tr><td>Vyhodnotenie a zdieľanie výsledkov <span className="muted small">(meranie spotreby vody, cesty na lokalitu, návod pre ďalších)</span></td><td className="num">250 €</td></tr>
                    <tr><td><b>Spolu</b></td><td className="num"><b>1 000 €</b></td></tr>
                  </tbody>
                </table>
              </div>
            </Reveal>
          </div>
        </section>

        {/* 10. Technické detaily */}
        <section id="technika" className="alt">
          <div className="wrap">
            <Reveal>
              <details className="tech">
                <summary>Technické detaily (pre zvedavých)</summary>
                <div className="tech-body">
                  <h3>Hardvér uzla</h3>
                  <ul className="clean">
                    <li>Mikropočítač ESP32, rádio LoRa (SX127x, 433 MHz), hodiny reálneho času DS3231 so záložnou batériou, kapacitný senzor pôdnej vlhkosti, kryty z rúr DN160.</li>
                    <li>Hlboký spánok s odberom 11–12 µA. Celú periférnu elektroniku (rádio, senzor, hodiny) odpája jeden spínaný pin a komunikačné linky sa pred spánkom stiahnu na nulu, aby cez ne neunikal prúd.</li>
                    <li>Dĺžku spánku si uzol vypočíta z hodín ešte pred odpojením napájania, a tak sa zobudí presne vo svojom okne.</li>
                  </ul>

                  <h3>Ako putujú dáta</h3>
                  <div className="flow">
                    <div className="flow-box"><b>Uzol v zemi</b>zmeria vlhkosť a teplotu, uloží záznam do vlastnej pamäte</div>
                    <div className="flow-box"><b>Rádio LoRa 433 MHz</b>krátka správa vo vlastnom časovom okne uzla</div>
                    <div className="flow-box"><b>Centrálna stanica</b>stále zapnutá, najprv uloží, potom posiela</div>
                    <div className="flow-box"><b>Databáza Supabase</b>cez WiFi a internet</div>
                    <div className="flow-box"><b>Web</b>dashboard a táto stránka</div>
                  </div>
                  <ul className="clean" style={{ marginTop: 18 }}>
                    <li><b>Bez kolízií:</b> každý uzol vysiela v iných minútach (uzol 1 o :04, :24, :44, uzol 2 o :08 atď.), takže sa rádiá nestretnú.</li>
                    <li><b>Nič sa nestratí:</b> uzol si každé meranie uloží do pamäte flash. Stanica si záznam tiež najprv uloží a zmaže ho až vtedy, keď databáza potvrdí zápis. Keď vypadne internet, dáta čakajú a odošlú sa neskôr.</li>
                    <li><b>Dohľadanie chýbajúcich dát:</b> každé 2 hodiny uzol po odoslaní 3 sekundy počúva. Stanica mu vtedy môže poslať presný čas alebo si vyžiadať staršie záznamy, ktoré uzol pošle po dávkach.</li>
                    <li><b>Žiadne duplikáty:</b> záznam má jednoznačný kľúč (uzol + čas merania), takže opakované odoslanie nevytvorí dvojitý riadok.</li>
                    <li><b>Kontrola zdravia:</b> stanica raz za hodinu hlási, či beží, koľko záznamov čaká na odoslanie a akú má silu WiFi.</li>
                    <li>Dnes putuje správa ako krátky text (<code>uzol,hodnota,teplota,čas,L:0|1</code>). Pripravený je úspornejší binárny formát s pevnou dĺžkou 13 bajtov.</li>
                  </ul>

                  <h3>Čistenie dát</h3>
                  <p>
                    Z reálnej prevádzky som sa naučil, že surové dáta nie sú čisté: asi 9 % správ prišlo dvakrát (rovnaký
                    obsah, iný čas príjmu), hodiny niektorých uzlov občas ukazovali nezmyselný dátum a menej ako 1 % hodnôt
                    boli zjavné chyby merania. Všetko to pred modelovaním odfiltrujem. Prvé dva dni po osadení tiež vynechávam,
                    lebo senzor sa v pôde ešte usádza.
                  </p>

                  <h3>Ako som zlepšil predpoveď sucha</h3>
                  <p>
                    Prvá verzia bol jeden model vodnej bilancie podľa FAO-56 („vedro“ vody v koreňovej zóne) s deviatimi
                    parametrami, do ktorého vstupoval dážď aj výpar z globálneho modelu počasia. Na dátach, ktoré nevidel,
                    prehral na všetkých uzloch s najjednoduchším odhadom „zajtra bude rovnako ako dnes“. Hľadal som prečo:
                  </p>
                  <ul className="clean">
                    <li><b>Dážď z globálneho modelu nesedel.</b> Búrku 15. 7., keď na miestnej meteostanici spadlo 24,7 mm, odhadol na 1,3 mm. Denné súčty sa s meraním zhodovali len slabo (korelácia 0,58).</li>
                    <li><b>Model sa učil dve rôzne veci naraz.</b> Chyba v daždi pokazila aj to, ako sa model naučil vysychanie.</li>
                    <li><b>Percentá orezané na 0–100 %</b> strácali informáciu pri veľmi mokrej aj veľmi suchej pôde.</li>
                    <li><b>Príliš veľa parametrov</b>, ktoré sa z dát nedali od seba odlíšiť.</li>
                  </ul>
                  <p>Preto som model prestaval:</p>
                  <ol>
                    <li><b>Miestne počasie.</b> Dáta z meteostanice <a href={SRC.meteo} target="_blank" rel="noopener noreferrer">Zaježová</a> v susedstve pozemku, meranie každú minútu. Z nich počítam aj výpar (FAO-56 Penman-Monteith).</li>
                    <li><b>Dva samostatné modely:</b> jeden len pre vysychanie, druhý pre to, ako pôdu zvlhčí dážď.</li>
                    <li><b>Surové hodnoty senzora</b> namiesto orezaných percent. Na percentá sa dajú prepočítať kedykoľvek, naspäť nie.</li>
                    <li><b>Obdobia vysychania určuje samotný uzol</b>, nie dážď na stanici. Dáta ukázali, že uzly občas zvlhli aj po prehánke, ktorá stanicu obišla.</li>
                    <li><b>Len toľko parametrov, koľko dáta naozaj určia.</b> Hĺbka koreňov, spotreba rastlín a mierka senzora sa pri vysychaní prejavujú len ako jeden súčin, tak ich model učí ako jedno číslo.</li>
                    <li><b>Test, či je dôležitejšie slnko, alebo suchý vietor.</b> Výpar som rozdelil na časť zo slnka a časť zo suchého vzduchu a vetra. Model dal váhu vzduchu, no predpoveď to nezlepšilo, preto zatiaľ ostávam pri jednoduchšej verzii.</li>
                  </ol>
                  <p>Model vysychania každý deň počíta:</p>
                  <div className="eq">{`x   = hodnota senzora (vyššia = suchšia pôda)
ET0 = referenčný výpar z meteostanice (mm/deň)

1. prebytok vody odteká:  ak je pôda mokrejšia než poľná kapacita x_fc,
                          x += (x_fc − x) · (1 − e^(−1/τ))
2. stres rastlín:         Ks = 1, kým je vody dosť;
                          od bodu stresu klesá k 0 pri bode vädnutia x_wp
3. vysychanie:            x += Ks · k · ET0`}</div>
                  <p className="small muted">
                    Päť parametrov (x_fc, x_wp, bod stresu, τ, k) hľadám pre každý uzol zvlášť globálnou optimalizáciou
                    (diferenciálna evolúcia). Presnosť overujem len na dňoch, ktoré model pri učení nevidel.
                  </p>
                  <p>
                    Model zvlhčovania si predstavuje hornú vrstvu pôdy ako malú nádrž: dážď ju najprv naplní a až prebytok
                    dotečie k senzoru. Medzi dažďami nádrž vysychá. Pri uzle 4 to sedí dobre: prvé asi 4–5 mm zadrží pôda nad
                    senzorom, potom vlhkosť stúpa do 1–2 hodín. Uzol 5 reaguje úmerne dažďu, ale s oneskorením až 11–50 hodín.
                    Uzol 1 dážď zo stanice vôbec nevysvetľuje, zrejme k nemu voda prichádza inou cestou.
                  </p>
                  <p>
                    <b>Bod stresu</b> je vlhkosť, pod ktorou rastliny začínajú ťažšie čerpať vodu a vysychanie sa spomalí. Pre
                    každý uzol ho model odhadol z dát a dashboard podľa neho ukazuje, o koľko dní by pri súčasnej predpovedi
                    počasia bez dažďa nastal.
                  </p>

                  <h3>Softvér</h3>
                  <ul className="clean">
                    <li>Databáza Supabase (PostgreSQL), web v Reacte (Vite), nasadený na Vercel.</li>
                    <li>Modely v Pythone (NumPy, SciPy, pandas). Predpoveď na dashboarde beží priamo v prehliadači.</li>
                    <li>Backend vo FastAPI je zatiaľ v začiatkoch.</li>
                  </ul>

                  <h3>Odkazy</h3>
                  <ul className="clean">
                    <li><a href="/">Živý dashboard</a></li>
                    <li>Zdrojový kód: <a href="https://github.com/pravoslavzilka/DryAhead" target="_blank" rel="noopener noreferrer">github.com/pravoslavzilka/DryAhead</a></li>
                    <li>Metodika výparu: <a href={SRC.fao} target="_blank" rel="noopener noreferrer">FAO-56, Crop evapotranspiration</a></li>
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
              Študent strojného inžinierstva na VUT v Brne. DryAhead staviam pre našu rodinnú pôdu na strednom Slovensku,
              kde každé leto vidím, ako sucho berie mladé stromy aj vodu zo studní.
            </p>
            <p>Kontakt: <a href="mailto:pravoslav.zilka@gmail.com">pravoslav.zilka@gmail.com</a></p>
            <p className="small muted">Dáta na tejto stránke: snapshot k {fmtDate(snapshot.generated, { day: 'numeric', month: 'numeric', year: 'numeric' })}. Grafy fungujú aj bez pripojenia k databáze.</p>
          </div>
          <div>
            <h3>Zdroje</h3>
            <ol>
              <li>SHMÚ cez TASR: <a href={SRC.shmu}>teraz.sk</a></li>
              <li>Podzemná voda 2026: <a href={SRC.sme}>sme.sk</a></li>
              <li>Vyschnuté studne, Nižný a Vyšný Čaj: <a href={SRC.topky}>topky.sk</a></li>
              <li>Straty sadeníc od 1951: <a href={SRC.konopka}>los.sk (Konôpka, 2013)</a></li>
              <li>Sucho 2022, Lesy SR: <a href={SRC.lesy}>lesy.sk</a></li>
              <li>Dopĺňanie podzemnej vody: <a href={SRC.lepsiden}>lepsiden.sk</a></li>
              <li>Hydrológ o suchu: <a href={SRC.noviny}>noviny.sk</a></li>
              <li>Mladé stromy a zálievka: <a href={SRC.bn}>bratislavskenoviny.sk</a></li>
              <li>Pôdne senzory, 10–16 %: <a href={SRC.ucanr}>ucanr.edu</a></li>
              <li>Lacné senzory, 28,8 %: <a href={SRC.pmc}>PMC11902337</a></li>
              <li>Meteostanica Zaježová: <a href={SRC.meteo}>meteotekov.sk</a></li>
              <li>FAO-56: <a href={SRC.fao}>fao.org</a></li>
            </ol>
          </div>
        </div>
      </footer>
      <BackToTop />
    </>
  )
}
