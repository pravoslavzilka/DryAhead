// Field deployment facts for the about page, maintained by hand: delivery
// counts come from Supabase `readings` (nodes 1-5; a slot is one 20-minute
// interval with at least one reading), history from the field log. Update
// AS_OF together with the numbers. The charts read snapshot.json instead
// (ml/option_one/export_presentation_snapshot.py --out ...).

export const AS_OF = '2026-10-12'
export const DEPLOYED = '2026-06-29'

export const STATS = {
  days: 105,
  readings: 42003,
  slots: 22008,
  expectedSlots: 37975,
}

// tone: ok | warn | off
export const NODES = [
  { id: 1, tone: 'ok', status: 'In operation', days: 106, slots: 6121, rate: 80.6 },
  { id: 2, tone: 'ok', status: 'Rebuilt, in operation since 11 Oct', days: 12, slots: 469, rate: 6.2 },
  { id: 3, tone: 'off', status: 'Retired; its board now runs node 2', days: 46, slots: 2598, rate: 34.2 },
  { id: 4, tone: 'ok', status: 'In operation', days: 106, slots: 6624, rate: 87.2 },
  { id: 5, tone: 'warn', status: 'In operation; battery replaced 11 Oct', days: 101, slots: 6196, rate: 81.6 },
]

// kind: field | data | model | fault | fix
export const HISTORY = [
  { date: '2026-06-29', kind: 'field', title: 'Five nodes and a hub go into the ground',
    text: 'Installed at five points within 500 m near Zaježová (Pliešovce). All sensors shift on day one while they settle into the soil, so analysis starts on 1 July.' },
  { date: '2026-07-15', kind: 'data', title: 'The first big storm',
    text: '24.7 mm at the local station. The four nodes reacted completely differently, from almost nothing to fully saturated, the first sign that every spot on the land needs water differently.' },
  { date: '2026-07-24', kind: 'data', title: '24 days without rain',
    text: 'Until 16 August not a drop fell at the station, which gave the cleanest drying curves of the season.' },
  { date: '2026-07-28', kind: 'fault', title: 'Node 3’s clock starts failing',
    text: 'Its DS3231 real-time clock stopped answering around midday, most likely from heat, and from 6 August it was almost dead. The readings kept coming, but without a timestamp.' },
  { date: '2026-08-08', kind: 'fault', title: 'Node 2 goes silent',
    text: 'A bad solder joint from the build kept its ESP32 from entering deep sleep, so it drained the battery. The repair attempt later destroyed the board for good.' },
  { date: '2026-09-03', kind: 'model', title: 'First model loses to “stays the same”',
    text: 'A single FAO-56 soil-water bucket model with nine parameters and gridded weather couldn’t beat the simplest forecast on any node. Finding out why led to the current model.' },
  { date: '2026-09-10', kind: 'fault', title: 'Node 3 stops transmitting',
    text: 'Poor sealing of the antenna chamber let water droplets in, and the contamination cut the radio link. The board itself survived.' },
  { date: '2026-09-25', kind: 'model', title: 'The drying model works',
    text: 'Rebuilt around the local weather station, raw sensor values and separate drying and wetting models, it beats both baselines at 7 days ahead on nodes 1, 4 and 5.' },
  { date: '2026-09-27', kind: 'model', title: 'Drought forecast goes live',
    text: 'The dashboard now runs both models in the browser on a 16-day weather forecast and shows when each spot reaches plant stress if no rain falls.' },
  { date: '2026-10-05', kind: 'fault', title: 'Node 5’s battery runs out',
    text: 'Six days without data until the battery was swapped.' },
  { date: '2026-10-11', kind: 'fix', title: 'Recovery and rebuild',
    text: 'Node 3’s full flash log (10,075 readings) was read out over USB, and 505 readings the radio had missed were backfilled. Its board was then reprogrammed and fitted into node 2’s body, and the new node 2 started reporting the same evening. Node 5 got a new battery.' },
]
