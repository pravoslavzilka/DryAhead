#!/usr/bin/env python3
"""PostToolUse hook: fires after any Edit/Write. If the touched file is
contracts/telemetry.md, reminds that the firmware encoder, backend
decoder, and golden fixture must all change together, bumping
packet_version. Exit 2 surfaces this back to Claude immediately."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REMINDER = (
    "contracts/telemetry.md was just touched.\n"
    "Reminder (contracts-first rule): a packet layout change must update, "
    "together, in one change:\n"
    "  1. the firmware encoder\n"
    "  2. the backend decoder\n"
    "  3. the golden fixture (contracts/fixtures/golden_packet_v1.json once "
    "it exists)\n"
    "Bump packet_version; never reorder/resize an existing version's "
    "fields. See CLAUDE.md."
)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    normalized = file_path.replace("\\", "/")

    if normalized.endswith("contracts/telemetry.md"):
        print(REMINDER, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
