import { useCallback, useEffect, useState } from 'react'
import { supabase, fetchAllRows } from '../lib/supabase'

const HISTORY_HOURS = 168 // 7 d of hourly heartbeats
const REFRESH_MS = 5 * 60 * 1000

/**
 * Loads current hub status from `hub_health` (a view that flags staleness
 * server-side — a hung hub still has active=true in its last hub_status row,
 * so freshness must be judged by heartbeat age, not that flag alone) plus
 * `hub_status` heartbeat history for the activity chart.
 */
export function useHubStatus() {
  const [health, setHealth] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const { data: healthRows, error: healthErr } = await supabase
        .from('hub_health')
        .select('*')
        .limit(1)
      if (healthErr) throw healthErr

      const cutoffIso = new Date(Date.now() - HISTORY_HOURS * 3600 * 1000).toISOString()
      const rows = await fetchAllRows(() =>
        supabase
          .from('hub_status')
          .select('reported_at, active, pending_count, last_error, uptime_seconds, wifi_rssi, free_heap')
          .gte('reported_at', cutoffIso)
          .order('reported_at', { ascending: true }),
      )

      setHealth(healthRows?.[0] ?? null)
      setHistory(rows.map((r) => ({ ...r, t: Date.parse(r.reported_at) })))
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

  return { health, history, loading, error, refresh: load }
}
