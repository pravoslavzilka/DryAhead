#!/usr/bin/env python3
"""PreToolUse hook on Edit|Write: blocks edits under firmware/, backend/,
frontend/, ml/, hardware/ by default, EXCEPT files named CLAUDE.md (which
is exactly what this configuration pass is meant to create/update).

This is deliberately stricter than a permanent rule: it exists for the
current "Claude configuration only, no application source changes" pass.
Meant to be relaxed or removed once that constraint is lifted — see
.claude/SETUP.md."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROTECTED_DIRS = (
    "firmware/",
    "backend/",
    "frontend/",
    "ml/",
    "hardware/",
    "contracts/",
)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    normalized = file_path.replace("\\", "/")
    basename = os.path.basename(normalized)

    if basename == "CLAUDE.md":
        sys.exit(0)

    for prefix in PROTECTED_DIRS:
        if f"/{prefix}" in normalized or normalized.startswith(prefix):
            print(
                f"Blocked: source-edit guard is active this session. "
                f"'{file_path}' is under {prefix.rstrip('/')}/, which is "
                f"live/deployed or otherwise off-limits without your "
                f"explicit go-ahead this round. See .claude/SUGGESTIONS.md "
                f"for the proposed change instead.",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
