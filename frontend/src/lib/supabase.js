import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!url || !anonKey) {
  throw new Error('Missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY — check the .env file.')
}

export const supabase = createClient(url, anonKey)

const PAGE_SIZE = 1000

/**
 * Fetch every row matching a query, paging past PostgREST's per-request row cap.
 * `buildQuery` must return a fresh query (already filtered + ordered) each call.
 */
export async function fetchAllRows(buildQuery) {
  const rows = []
  for (let page = 0; ; page++) {
    const from = page * PAGE_SIZE
    const { data, error } = await buildQuery().range(from, from + PAGE_SIZE - 1)
    if (error) throw error
    rows.push(...data)
    if (data.length < PAGE_SIZE) return rows
  }
}
