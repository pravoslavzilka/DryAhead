#!/usr/bin/env python3
"""Stop hook: informational only, no enforcement. Compares current
`git status --short` against the snapshot session_start.py took at the
start of this session and prints how many files changed. Does not run
check.sh (none exist yet) and always exits 0, so it never blocks
handing control back - the hard ~3s-per-hook budget rules out running
real checks here; that belongs in CI / manual `just check` instead."""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=os.environ.get("CLAUDE_PROJECT_DIR")
        ).stdout.strip()
    except Exception:
        return ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    session_id = data.get("session_id", "unknown")
    snapshot_path = os.path.join(
        tempfile.gettempdir(), f"dryahead-session-{session_id}.snapshot"
    )

    baseline = ""
    if os.path.exists(snapshot_path):
        with open(snapshot_path, "r", encoding="utf-8") as f:
            baseline = f.read()

    current = run(["git", "status", "--short"])
    current_count = len([l for l in current.splitlines() if l.strip()])
    baseline_count = len([l for l in baseline.splitlines() if l.strip()])

    delta = current_count - baseline_count
    print(
        f"{current_count} file(s) currently dirty "
        f"({'+' if delta >= 0 else ''}{delta} since session start). "
        f"No check.sh exists yet this pass - see .claude/SUGGESTIONS.md."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
