# Observations (not acted on -- out of scope for this task)

- `ml/option_one/README.md` records that as of its last live run
  (2026-09-03), nodes 1/4/5 had ~56 usable days each (2026-06-29 to
  2026-09-02), node 3 had 28, and node 2 had 8 ("effectively dead"). That's
  *daily* coverage for option_one's purposes, not directly the same thing
  as "how many independent >=5-day drying windows exist," but it's a
  useful sanity bound: with only ~56 days of record per node, getting
  three non-overlapping windows of 5+ days each (this task's minimum to
  calibrate at all) is plausible but not generous, especially if rain is
  frequent enough that few drying stretches run that long uninterrupted.
  Worth knowing going in, not a reason to change the approach -- the task
  spec already anticipates and handles the <3-windows case explicitly.
- No other issues noticed in `ml/option_one/` or the read-only paths
  touched for schema knowledge. `ml/option_one/data_supabase.py` and its
  README are internally consistent and already self-aware of their own
  limitations (documented under "Known simplifications / next steps").
  Nothing there looked broken or worth flagging.
- Did not open `ml/option_two/` beyond confirming it's present but
  untracked on this branch (per instructions, another night's unmerged
  work, read-only, not touched).
