#!/usr/bin/env python3
"""PreToolUse hook on Bash: blocks a short deny-list of destructive
command patterns, matched anywhere in the command text (not just as a
prefix) so e.g. `psql -c "DROP TABLE x"` is caught too, not just a bare
`DROP TABLE` invocation. Exit 2 blocks the command before it runs."""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PATTERNS = [
    (re.compile(r"git\s+push\s+.*(--force(-with-lease)?|-f\b)"), "force-push"),
    (re.compile(r"git\s+reset\s+--hard"), "git reset --hard"),
    (re.compile(r"rm\s+-rf"), "rm -rf"),
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "DROP TABLE"),
    (re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE), "DROP DATABASE"),
    (re.compile(r"\bTRUNCATE\b", re.IGNORECASE), "TRUNCATE"),
    (re.compile(r"supabase\s+db\s+reset"), "supabase db reset"),
]


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")

    for pattern, label in PATTERNS:
        if pattern.search(command):
            print(
                f"Blocked: command matches destructive pattern '{label}'.\n"
                f"If this is intentional, run it yourself outside Claude Code.",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
