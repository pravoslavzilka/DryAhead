#!/usr/bin/env python3
"""SessionStart hook: prints current branch, dirty files, and a one-line
reminder so a fresh session (especially an unattended cloud one) orients
immediately instead of discovering repo state by trial and error.
Also snapshots `git status --short` to a session-scoped temp file so the
Stop hook can report how many files changed during the session."""
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

    branch = run(["git", "branch", "--show-current"])
    status = run(["git", "status", "--short"])

    snapshot_path = os.path.join(
        tempfile.gettempdir(), f"dryahead-session-{session_id}.snapshot"
    )
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(status)
    except OSError:
        pass

    dirty_count = len([l for l in status.splitlines() if l.strip()])

    print(f"DryAhead repo: branch '{branch}', {dirty_count} dirty file(s).")
    print(
        "Reminder: contracts-first (see CLAUDE.md); this repo is currently "
        "in a Claude-configuration-only pass per .claude/SUGGESTIONS.md - "
        "check whether the source-edit guard is still meant to be active."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
