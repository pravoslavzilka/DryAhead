import { useCallback, useEffect, useState } from 'react'
import { supabase, fetchAllRows } from '../lib/supabase'
import { rawToHumidity, thresholds, sensorStatus } from '../lib/calibration'
import { parseGps } from '../lib/gps'
import { readingTime } from '../lib/format'

const OVERVIEW_HOURS = 48
const REFRESH_MS = 5 * 60 * 1000

function toPoint(r, cal) {
  const t = readingTime(r)
  return {
    t,
    humidity: rawToHumidity(r.raw, cal),
    raw: r.raw,
    temperature: r.temperature,
    rssi: r.rssi,
    snr: r.snr,
  }
}

/**
 * Loads calibration for every node plus the last 48 h of readings (for the map,
 * cards and sparklines). For nodes silent longer than that, fetches their single
 * latest reading so "last seen" is still accurate. Refreshes every 5 minutes.
 */
export function useSensorData() {
  const [sensors, setSensors] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const { data: cals, error: calErr } = await supabase
        .from('sensor_calibration')
        .select('*')
        .order('node_id')
      if (calErr) throw calErr

      // Filter/order on received_at (server clock) — node clocks drift, so
      // recorded_at can hold bogus future timestamps.
      const cutoffIso = new Date(Date.now() - OVERVIEW_HOURS * 3600 * 1000).toISOString()
      const recent = await fetchAllRows(() =>
        supabase
          .from('readings')
          .select('node_id, raw, temperature, recorded_at, received_at, rssi, snr')
          .gte('received_at', cutoffIso)
          .order('received_at', { ascending: true }),
      )

      const byNode = new Map()
      for (const r of recent) {
        if (!byNode.has(r.node_id)) byNode.set(r.node_id, [])
        byNode.get(r.node_id).push(r)
      }

      // Latest single reading for nodes with nothing in the overview window
      const silent = (cals ?? []).filter((c) => !byNode.has(c.node_id))
      const latestSilent = await Promise.all(
        silent.map((c) =>
          supabase
            .from('readings')
            .select('node_id, raw, temperature, recorded_at, received_at, rssi, snr')
            .eq('node_id', c.node_id)
            .order('received_at', { ascending: false })
            .limit(1)
            .then(({ data, error: e }) => (e || !data?.length ? null : data[0])),
        ),
      )
      for (const r of latestSilent) {
        if (r) byNode.set(r.node_id, [r])
      }

      const result = (cals ?? []).map((cal) => {
        const rows = byNode.get(cal.node_id) ?? []
        const history = rows
          .map((r) => toPoint(r, cal))
          .filter((p) => p.t != null)
          .sort((a, b) => a.t - b.t)
        const latest = history.at(-1) ?? null
        const th = thresholds(cal)
        return {
          nodeId: cal.node_id,
          cal,
          gps: parseGps(cal.GPS),
          history,
          latest,
          ...th,
          status: sensorStatus(latest?.humidity ?? null, th, latest?.t ?? null),
        }
      })

      setSensors(result)
      setLastUpdated(Date.now())
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  return { sensors, loading, error, lastUpdated, refresh: load }
}

/** Full history for one node over `rangeHours`, for the detail modal. */
export async function fetchNodeHistory(nodeId, rangeHours, cal) {
  const cutoffIso = new Date(Date.now() - rangeHours * 3600 * 1000).toISOString()
  const rows = await fetchAllRows(() =>
    supabase
      .from('readings')
      .select('raw, temperature, recorded_at, received_at, rssi, snr')
      .eq('node_id', nodeId)
      .gte('received_at', cutoffIso)
      .order('received_at', { ascending: true }),
  )
  return rows
    .map((r) => toPoint(r, cal))
    .filter((p) => p.t != null)
    .sort((a, b) => a.t - b.t)
}
