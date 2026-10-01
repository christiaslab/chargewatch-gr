#!/usr/bin/env python3
"""PreToolUse hook: block a write or shell command that carries a secret-like value.

Wiring only. Reads the hook payload from stdin (tool_name, tool_input), takes the
text a Write, Edit, MultiEdit or Bash call would introduce, and applies the
secret patterns of the pilot guard (scripts/pilot_core.py). A positive finding
exits 2 with the rule name on stderr and never the matched value. Any other
outcome, including a malformed payload or an import error, prints at most one
line to stderr and exits 0: the core gates remain the rule. Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TEXT_FIELDS = {
    "Write": ("content",),
    "Edit": ("new_string",),
    "MultiEdit": ("new_string",),
    "Bash": ("command",),
}


def texts_from(payload: dict) -> list[str]:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    fields = TEXT_FIELDS.get(tool, ())
    found: list[str] = []
    for field in fields:
        value = tool_input.get(field)
        if isinstance(value, str):
            found.append(value)
    for edit in tool_input.get("edits", []) if tool == "MultiEdit" else []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            found.append(edit["new_string"])
    return found


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
    try:
        sys.path.insert(0, str(root / "scripts"))
        from pilot_core import scan_text  # the pinned pilot guard's patterns
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
        rules = sorted({rule for text in texts_from(payload) for rule in scan_text(text)})
    except Exception as error:  # fail open
        print(f"secrets guard skipped: {type(error).__name__}", file=sys.stderr)
        return 0
    if rules:
        print(f"blocked by the secrets guard: {', '.join(rules)} in {payload.get('tool_name')} input; remove the value and retry", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
