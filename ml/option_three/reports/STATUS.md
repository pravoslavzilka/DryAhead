# Reports status

Superseded -- see `NIGHT_SUMMARY.md` for the real account. As of this
commit: `node_1_cleaning.png` exists (real cleaning before/after plot from
a live run). No `node_{id}.md` or `run_summary.json` yet -- the full
per-node validation (equifinality + hold-out for all three nodes) is still
running via `night.sh` given how compute-heavy it is (~4 hours for all
three nodes); check whether those files exist before assuming they don't.

Node 1's main calibration fit (one seed, no equifinality yet) succeeded:
KGE = 0.977. See `NIGHT_SUMMARY.md` for the full parameter values and what
still needs to run.
