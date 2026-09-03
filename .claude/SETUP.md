# Claude Code setup — 2026-09

This configuration pass was scoped to **Claude Code configuration only**:
no application source, build config, credentials, or git-remote changes.
Everything outside that scope is written up in `.claude/SUGGESTIONS.md`
instead of applied. This file records what was actually built, what was
deliberately skipped, and what's left for you to do by hand.

## What was created

**CLAUDE.md files**
- Root `CLAUDE.md` — repo map, the contracts-first rule, and the
  never-break rules (firmware is live-deployed, 11–12µA sleep budget,
  never hand-edit `hardware/`, never commit secrets).
- Per-package: `firmware/CLAUDE.md`, `backend/CLAUDE.md`,
  `frontend/CLAUDE.md`, `ml/CLAUDE.md`, `hardware/CLAUDE.md` — each states
  facts not inferable from the code (sleep-path fixes, the CSV-vs-packed
  protocol gap, `ml/option_one/`'s real state, etc.).

**`.claude/settings.json`**
- Permissions: an allow list (read-only git, `npm run build/dev`, the
  existing `just` recipes) and a deny list (force-push variants,
  `git reset --hard`, `rm -rf`, `supabase db reset`).
- 6 hooks wired in (all tested — see below).

**`.claude/hooks/`** (all Python, all UTF-8-safe on Windows console output)
| Hook | Event | Status |
|---|---|---|
| `contract_touch_reminder.py` | `PostToolUse` on `contracts/telemetry.md` | Real E2E confirmed |
| `destructive_bash_blocker.py` | `PreToolUse` on `Bash` | Real E2E confirmed (blocked a live `DROP TABLE`-containing command) |
| `source_edit_guard.py` | `PreToolUse` on `Edit\|Write` under `firmware/backend/frontend/ml/hardware/contracts` | Real E2E confirmed (blocked a live Write into `backend/`) |
| `format_on_write.py` | `PostToolUse` on `Edit\|Write` | Simulated only — currently an inert no-op, no formatter configured anywhere yet |
| `session_start.py` | `SessionStart` | Simulated only — prints branch/dirty-file count/reminder, can't be manually re-triggered mid-session |
| `stop_reminder.py` | `Stop` | Simulated only — prints a file-count delta since session start, no enforcement |

Two real bugs were found and fixed while testing these: a hardcoded
`/tmp/...` path doesn't resolve correctly under this Windows Python (fixed
via `tempfile.gettempdir()`), and em dashes in hook output were getting
mangled on this Windows console (fixed by forcing UTF-8 on stdout/stderr in
every hook).

**`.claude/skills/telemetry-contract/SKILL.md`**
The 8-step mandatory procedure for any packet-layout change, with an
explicit note that steps 4–6 (firmware encoder / backend decoder / golden
fixture) target code that doesn't exist yet.

**`.claude/agents/firmware-reviewer.md`**
Read-only subagent (Read/Grep/Glob/Bash — no Edit/Write) reviewing
proposed firmware changes for sleep-current-budget impact, ISR safety,
buffer/parsing handling, and node-variant scope sanity.

**`.gitignore`**
Changed from ignoring all of `.claude/` to ignoring only
`.claude/settings.local.json` — so cloud/unattended sessions now actually
see the committed config (they didn't before this pass).

**`.claude/SUGGESTIONS.md`**
8 written-not-applied items: the golden packet fixture, a `platformio.ini`
for firmware, removing hardcoded credentials from two test sketches,
removing the stale `fe` git remote, wiring CI to real checks, proposed
per-package `check.sh` contents, the two deferred skills, and the
`ml/option_one/` commit decision.

## Deliberately skipped, and why

- **`node-triage` skill** — needs backend ingestion, which doesn't exist.
- **`ml-experiment` skill** — `ml/option_one/` is one manual pipeline run
  so far, not yet a repeated loop with a tracked baseline.
- **`db-migration` / `firmware-release` skills** — moved to
  `SUGGESTIONS.md`; nothing real to document a procedure against yet.
- **`.mcp.json` / ESP-IDF Tools MCP / docs MCP** — not created. The
  official ESP-IDF Tools MCP targets `idf.py`-based projects; this
  firmware is Arduino-sketch-based (proposed to migrate to PlatformIO, not
  ESP-IDF). A generic docs MCP wasn't judged worth its context cost for a
  solo dev who knows the codebase.
- **`pytest`/`pio` permissions** — not added to the allow list; nothing to
  run yet since neither tool is wired up in this pass.
- **Everything in `SUGGESTIONS.md`** — out of scope by your explicit
  instruction (no source/build/credential/git-remote changes this pass).

## Definition of done — actual status

The original definition of done assumed the full original Phase 3 scope
(including the golden fixture and `check.sh`). Given the scope was
narrowed mid-implementation, here's what's actually true:

- ❌ `make check` / `just check` per package — **not built**, moved to
  `SUGGESTIONS.md` item 6 (would require tooling not yet installed).
- ❌ Golden fixture test passing on both sides — **not built**, moved to
  `SUGGESTIONS.md` item 1 (would require firmware/backend source changes).
- ✅ Hooks 1–3 (the ones with real blocking/reminder consequences)
  confirmed firing through Claude Code's actual pipeline, live, this
  session. Hooks 4–6 verified only by feeding them simulated payloads
  directly — 4 is a no-op regardless, 5/6 fire automatically at session
  boundaries and weren't independently re-observed after being wired in.
- ✅ `.claude/SETUP.md` exists (this file).
- ✅ No file outside `.claude/**` and `CLAUDE.md` files was modified,
  except `.gitignore` (needed to make `.claude/` committable at all —
  flagging this as the one deliberate exception to that constraint).

## What you still need to do by hand

1. **Review `.claude/SUGGESTIONS.md`** and greenlight items individually —
   nothing in it expires or gets auto-applied.
2. **Rotate the exposed Supabase API key** from the two hardcoded-credential
   test sketches — this is a Supabase dashboard action, can't be done from
   here regardless of scope.
3. **Commit `.claude/` and the `CLAUDE.md` files** — they're written and
   `.gitignore`-visible now (confirmed via `git ls-files --others
   --exclude-standard .claude`), but nothing has been `git add`ed or
   committed. I didn't do this unprompted per your commit-only-when-asked
   preference.
4. **Decide when to lift the source-edit guard**
   (`.claude/hooks/source_edit_guard.py`) — it's deliberately stricter than
   a permanent rule, built for this configuration-only pass. Once you're
   ready for normal firmware/backend/frontend/ml development again, either
   remove its `PreToolUse` entry from `.claude/settings.json` or narrow
   `PROTECTED_DIRS` in the script.
5. **Decide when to commit `ml/option_one/`** — left untracked on purpose.
6. **Decide on the `fe` git remote** — confirmed stale, not removed this
   pass (`SUGGESTIONS.md` item 4).
