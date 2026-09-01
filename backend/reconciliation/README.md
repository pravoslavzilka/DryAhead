# reconciliation

A standalone script that finds gaps in the sensor-readings time series and
queues backfill instructions in Supabase for the hub to carry out. It shares
the Supabase project with `backend/`'s FastAPI service but is deliberately
independent of it (own `requirements.txt`, no shared code) so it can run
anywhere with just Python and network access to Supabase -- a cron box, a
systemd timer, a scheduled serverless function.

## Why this design: "since", not ranges

The node firmware (`firmware/nodes/`) only understands one backfill command:

```
GETDATA:<since_epoch>
```

On receiving it, the node resends **every** locally-stored record newer than
`since_epoch` -- there is no way to ask it to stop at an end bound. Given that
constraint, this script:

- **Never emits one instruction per gap.** If node 3 is missing 40 separate
  20-minute slots spread across 10 days, that is still recoverable with a
  single `GETDATA:<earliest_missing>` -- the node will stream everything after
  that point, filling all 40 gaps (and re-sending data that already exists,
  which the hub's upsert-on-`(node_id, recorded_at)` makes harmless).
- **Never splits into ranged chunks.** A "chunk 1: hours 0-6, chunk 2: hours
  6-12" scheme would require the node to honor `range_end`, which the current
  firmware does not do. See "Future option" below.
- **Emits at most one instruction per node per run**, pointing at that node's
  single earliest recoverable gap.

If you need bounded, chunked backfills (e.g. to avoid one huge resend flooding
LoRa airtime), that requires a **node firmware change** to support an end
bound in `GETDATA`, plus a corresponding change here to emit ranged
instructions instead of a single open-ended one. Out of scope for this
script as it stands.

## Idempotency: the central guarantee

Re-running this script must never create redundant instructions, whether it's
run twice in a row, weekly, or after a long gap. Before creating an
instruction for a node, the script:

1. **Checks for an in-flight instruction.** If the node already has an
   instruction in state `Posted` or `Received` whose `range_start` is
   less-than-or-equal to the one this run would create, it skips -- that
   existing instruction already asks the node for everything from an
   equal-or-earlier point, so it already covers the newly-found gaps too.
2. **Checks the dead-node cap.** If the node already has `--failure-cap`
   (default 3) instructions in state `Failed to resolve` whose `range_start`
   is at or before the candidate one, the script stops retrying and logs the
   node as unrecoverable for this run. This exists to stop a genuinely
   offline/dead node from generating a fresh instruction every single run
   forever.

Both checks use `range_start` comparisons rather than exact matches, because
"an earlier since" always subsumes "a later since" under this node's resend
semantics.

## Node storage horizon

Nodes buffer unsent readings to local flash (LittleFS) and the buffer is
finite. `NODE_RETENTION_DAYS` (default 14, configurable via `--retention-days`)
is a conservative estimate of how long the node can hold data before old
entries are overwritten. Requesting data older than that is presumed
pointless. Concretely:

- If a node's earliest missing timestamp is **within** the horizon, the
  instruction requests that timestamp directly.
- If it's **older** than the horizon, the script requests the horizon cutoff
  instead (recovering everything still on the node) and logs that the older
  data is presumed permanently lost.
- If *even the horizon cutoff* has no missing readings after it (every gap
  predates the horizon), the script creates nothing for that node and logs it
  as permanently lost -- there's nothing left to recover.

**This constant must be tuned to the node's real LittleFS capacity**, and the
reconciliation schedule (see below) must run more often than that horizon,
or gaps can age out of the recoverable window before anyone asks for them.

## Setup

```bash
cd backend/reconciliation
python -m venv .venv
. .venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on Linux/macOS
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Supabase project URL and anon key
```

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | yes | e.g. `https://xxxx.supabase.co` |
| `SUPABASE_KEY` | yes | **anon key**, not `service_role`. See below. |

Both are read from the environment (via `.env`, loaded with `python-dotenv`,
or already-exported shell vars). The script validates both are present at
startup and exits with a non-zero code and a clear message if either is
missing -- it will not run with partial credentials.

### Least privilege: anon key + RLS, not service_role

This script assumes it is running with the Supabase **anon** key, scoped by
Row Level Security policies to exactly what it needs:

- `select` on `readings`
- `select` and `insert` on `instructions`

It never needs (and must never be given) the `service_role` key, which
bypasses RLS entirely. Example minimal policies (adjust to your project's
auth model -- these assume anon/public access is acceptable for this
low-sensitivity data, which is typical for a public-repo hobby/research
deployment; tighten as needed):

```sql
create policy "reconciliation can read readings"
  on readings for select
  to anon
  using (true);

create policy "reconciliation can read instructions"
  on instructions for select
  to anon
  using (true);

create policy "reconciliation can create instructions"
  on instructions for insert
  to anon
  with check (command = 'GETDATA');
```

If `SUPABASE_KEY` is not scoped correctly, the script's startup connectivity
check will surface a `401`/`403` and exit non-zero rather than silently doing
nothing.

## Configuration reference

All of these are CLI flags with sensible defaults; none require editing the
script.

| Flag | Default | Meaning | When to tune |
|---|---|---|---|
| `--nodes` | `1,2,3,4,5` | Node IDs to check | Network grows/shrinks |
| `--cadence-minutes` | `20` | Expected minutes between readings | Firmware sleep interval changes |
| `--lookback-days` | `35` | How far back to scan for gaps | Wider to catch older gaps; narrower to cut query cost |
| `--retention-days` | `14` | Node local-storage horizon (see above) | Match the node's real LittleFS capacity |
| `--failure-cap` | `3` | Failed-to-resolve instructions before giving up on a node | Lower to stop retrying sooner; raise to be more persistent |
| `--http-timeout` | `15` | Seconds per Supabase HTTP call | Slow/flaky network |
| `--dry-run` | off | Compute and log, write nothing | Every time you're not sure |
| `--log-level` | `INFO` | Logging verbosity | `DEBUG` to see per-node detail while troubleshooting |

Two more constants live at the top of `reconcile.py` (not exposed as flags,
since they're about matching tolerance rather than policy):

- `TOLERANCE_FRACTION_OF_CADENCE` (default `0.5`, i.e. ±10 min at the default
  20-minute cadence) -- how close an actual reading must be to an expected
  slot to count as "present." Absorbs node clock jitter.
- `GRACE_PERIODS_OF_CADENCE` (default `1`) -- the most recent full cadence
  interval is never flagged as missing, since the node may simply not have
  reported yet.

## Running

```bash
# Dry run: see what it would do, no writes
python reconcile.py --dry-run

# Real run
python reconcile.py

# Custom window / horizon for a one-off investigation
python reconcile.py --lookback-days 60 --retention-days 10 --dry-run
```

Exit codes: `0` on a completed run (even if every node was skipped), `2` for
missing/invalid configuration, `1` for a hard failure (can't reach Supabase,
auth rejected, an unexpected API error mid-run).

Every decision is logged, one line per node, with a machine-greppable reason:
`no_gaps`, `already_in_flight`, `capped_unrecoverable`,
`trimmed_to_horizon_no_recoverable`, or `created` (`would_create` in
`--dry-run`). A final summary line totals created/skipped/no-action counts
across the run.

## Scheduling

Designed to run unattended on a recurring schedule -- weekly is the
target cadence -- via cron, a systemd timer, or a scheduled serverless
function (e.g. a scheduled Lambda/Cloud Function/Supabase Edge Function
invocation). It does not manage its own schedule; wire it up with whichever
of those fits your deployment.

```cron
# crontab -e -- every Monday at 03:00
0 3 * * 1 cd /path/to/backend/reconciliation && /path/to/.venv/bin/python reconcile.py >> /var/log/reconcile.log 2>&1
```

Whatever the interval, it must stay **shorter than `--retention-days`** (see
"Node storage horizon" above), or a node can overwrite gap data before a run
ever asks for it.

## Safety notes

- No secrets are hardcoded anywhere in this script; `.env` is git-ignored
  (see `.gitignore`) and `.env.example` only carries placeholders.
- All timestamps are UTC epoch seconds end-to-end -- no local time is ever
  computed or compared.
- Every Supabase call goes through the parameterized `requests` API (query
  params / JSON body), never hand-built query strings, so there's no
  injection surface into PostgREST's filter syntax.
