#!/usr/bin/env python3
"""PostToolUse hook on Edit|Write: dispatches to a formatter by file
extension. Currently a documented no-op — no formatter (ruff format,
prettier, clang-format, etc.) is configured anywhere in this repo yet.
Wire a real command into DISPATCH once one is added; until then this
always exits 0 and does nothing observable."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# extension -> formatter command, populated once a formatter exists.
DISPATCH: dict[str, list[str]] = {}


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""

    formatter = DISPATCH.get(ext)
    if formatter is None:
        sys.exit(0)

    # Not reachable today (DISPATCH is empty) — left here so adding a
    # formatter later is a one-line DISPATCH entry, not a new hook.
    import subprocess

    result = subprocess.run(
        formatter + [file_path], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
