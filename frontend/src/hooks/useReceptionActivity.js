import { useCallback, useEffect, useState } from 'react'
import { supabase, fetchAllRows } from '../lib/supabase'
import { READINGS_PER_DAY } from '../lib/calibration'

const DAY_MS = 86400000

export const GRANULARITIES = [
  { key: 'day', label: 'Days', daysPerBucket: 1 },
  { key: 'week', label: 'Weeks', daysPerBucket: 7 },
  { key: 'month', label: 'Months', daysPerBucket: 30 },
]

export const BUCKET_COUNT_OPTIONS = [5, 10, 20, 40]
export const DEFAULT_BUCKET_COUNT = 10

function startOfDay(ms) {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/**
 * `bucketCount` contiguous buckets ending "today", oldest first. `expected` is
 * the reading count a fully-reporting node should produce in the bucket,
 * scaled down for the still-open latest bucket so it isn't judged against a
 * full period it hasn't finished yet.
 */
function buildBuckets(daysPerBucket, bucketCount) {
  const now = Date.now()
  const todayEnd = startOfDay(now) + DAY_MS
  const spanMs = daysPerBucket * DAY_MS
  const buckets = []
  for (let i = bucketCount - 1; i >= 0; i--) {
    const idealEnd = todayEnd - i * spanMs
    const idealStart = idealEnd - spanMs
    const coverageMs = Math.max(0, Math.min(idealEnd, now) - idealStart)
    buckets.push({ start: idealStart, end: idealEnd, expected: (coverageMs / DAY_MS) * READINGS_PER_DAY })
  }
  return buckets
}

/**
 * Per-node reading-reception history bucketed into day/week/month periods
 * (`bucketCount` back) — a GitHub-contributions-style activity grid showing
 * how much data each node actually delivered versus its ~20 min cadence.
 */
export function useReceptionActivity(granularityKey, bucketCount = DEFAULT_BUCKET_COUNT) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const granularity = GRANULARITIES.find((g) => g.key === granularityKey) ?? GRANULARITIES[0]
      const buckets = buildBuckets(granularity.daysPerBucket, bucketCount)
      const cutoffIso = new Date(buckets[0].start).toISOString()

      const { data: cals, error: calErr } = await supabase
        .from('sensor_calibration')
        .select('node_id')
        .order('node_id')
      if (calErr) throw calErr

      const readings = await fetchAllRows(() =>
        supabase
          .from('readings')
          .select('node_id, received_at')
          .gte('received_at', cutoffIso)
          .order('received_at', { ascending: true }),
      )

      const byNode = new Map(
        (cals ?? []).map((c) => [c.node_id, buckets.map((b) => ({ ...b, count: 0 }))]),
      )
      for (const r of readings) {
        const nodeBuckets = byNode.get(r.node_id)
        if (!nodeBuckets) continue
        const t = Date.parse(r.received_at)
        const bucket = nodeBuckets.find((b) => t >= b.start && t < b.end)
        if (bucket) bucket.count += 1
      }

      setRows(
        [...byNode.entries()].map(([nodeId, nodeBuckets]) => ({
          nodeId,
          buckets: nodeBuckets.map((b) => ({
            ...b,
            ratio: b.expected > 0 ? b.count / b.expected : 0,
          })),
        })),
      )
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }, [granularityKey, bucketCount])

  useEffect(() => {
    load()
  }, [load])

  return { rows, loading, error, refresh: load }
}
