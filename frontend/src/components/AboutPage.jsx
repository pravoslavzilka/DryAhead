function Section({ title, children }) {
  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-orange-100 bg-white p-5 shadow-sm sm:p-6">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-500">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed text-stone-600">{children}</div>
    </section>
  )
}

export default function AboutPage({ onBack }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <button
        onClick={onBack}
        className="mb-6 inline-flex items-center gap-1 text-sm font-medium text-orange-700 hover:text-orange-800"
      >
        ← Back to dashboard
      </button>

      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-stone-800">About DryAhead</h1>
        <p className="mt-1 text-sm text-stone-500">
          Forecast-primary drought early warning — from a sensor in the soil to a prediction on
          the screen.
        </p>
      </header>

      <Section title="What it is">
        <p>
          DryAhead is an end-to-end platform that measures soil moisture in the field, transmits
          it over long-range radio, and combines it with weather forecasts to predict drought
          stress <em>before</em> it happens. The name says the goal: see the dry conditions{' '}
          <strong>ahead</strong> of time, while there's still time to act.
        </p>
      </Section>

      <Section title="Why">
        <p>
          Growers and land managers usually learn about drought stress once the damage is already
          visible. DryAhead moves that signal earlier by fusing two things:
        </p>
        <ol className="list-decimal space-y-1 pl-5">
          <li><strong>Ground truth</strong> — real soil-moisture readings from cheap, rugged, battery-powered field nodes.</li>
          <li><strong>The forecast</strong> — weather predictions, corrected against those ground-truth readings through data assimilation.</li>
        </ol>
        <p>
          The result is a <em>forecast-primary</em> drought prediction: not just "how dry is it
          now," but "how dry is it about to get, here, in this specific plot." Built for
          viticulture, orchards, and forestry operations, with a second track for institutional
          buyers such as parametric-insurance and risk modelling.
        </p>
      </Section>

      <Section title="How it works">
        <ol className="list-decimal space-y-1 pl-5">
          <li>A field sensor node measures soil moisture and packs the reading into a compact message.</li>
          <li>It's sent over long-range radio (LoRa) to a base station.</li>
          <li>The backend stores every reading in a database.</li>
          <li>A machine-learning model fuses the readings with the weather forecast into a drought prediction.</li>
          <li>This dashboard shows the result — live sensor status on the map and cards, forecasts to follow.</li>
        </ol>
      </Section>

      <Section title="The sensor node">
        <p>
          Each field node is a low-power microcontroller that wakes on a schedule, takes a
          reading, transmits it over LoRa, and goes back to sleep — built to run for months on a
          single battery charge inside a sealed enclosure in the field.
        </p>
      </Section>

      <Section title="The model">
        <p>
          The prediction is <em>forecast-primary</em>: the backbone of the estimate is the
          weather forecast, and field readings are used to correct and anchor that forecast to
          real local conditions. A forecast alone doesn't know the state of your soil, and a
          sensor alone can't see the future — combining them gives a per-location, forward-looking
          drought signal.
        </p>
      </Section>

      <Section title="The name">
        <p>
          <strong>DryAhead</strong> — a drought forecast is a warning that dry conditions lie{' '}
          <em>ahead</em>, and a good early-warning system keeps you a step <em>ahead</em> of them.
          Say it out loud and it also reads as "dry ahead": that's the whole product in two words.
        </p>
      </Section>

      <p className="text-center text-sm text-stone-500">
        <a
          href="https://github.com/pravoslavzilka/DryAhead"
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-orange-700 hover:text-orange-800"
        >
          View the project on GitHub ↗
        </a>
      </p>
    </div>
  )
}
