import { useCallback, useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

const REFRESH_MS = 5 * 60 * 1000
const FETCH_LIMIT = 200

export const ACTIVE_STATES = ['Posted', 'Received']
export const FAILED_STATE = 'Failed to resolve'

/**
 * Loads the most recent rows from `instructions` (the hub's backfill command
 * queue — see backend/reconciliation) so the UI can show how the current
 * queue is being handled: how many commands are in flight vs. failed.
 */
export function useInstructions() {
  const [instructions, setInstructions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const { data, error: err } = await supabase
        .from('instructions')
        .select('id, node_id, command, range_start, range_end, state, message, created_at, updated_at')
        .order('created_at', { ascending: false })
        .limit(FETCH_LIMIT)
      if (err) throw err
      setInstructions(data ?? [])
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

  const activeCount = instructions.filter((i) => ACTIVE_STATES.includes(i.state)).length
  const failedCount = instructions.filter((i) => i.state === FAILED_STATE).length

  return { instructions, activeCount, failedCount, loading, error, refresh: load }
}
