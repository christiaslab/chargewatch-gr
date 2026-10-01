#!/usr/bin/env python3
"""SessionStart hook: a read-only banner. Wiring only; fails open.

Prints the checkout's HEAD, branch and cleanliness, the hand-off pointer from
AGENTS.md when that row exists, and the first fenced command under the
"## Verification" heading of AGENTS.md when it exists. It names no rule of its
own: AGENTS.md is the rule. It stores nothing and derives no status:
verification is run, not remembered. On any error it prints one line to stderr
and exits 0. Standard library only; part of the portable kit (Decision 0012).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

POINTER = re.compile(r"\| Latest session hand-off and open items \| \[([^\]]+)\]")
VERIFICATION = re.compile(r"^## Verification\n.*?```[a-z]*\n([^\n]+)\n", re.MULTILINE | re.DOTALL)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def banner(root: Path) -> str:
    head = git(root, "rev-parse", "--short", "HEAD")
    branch = git(root, "branch", "--show-current") or "(detached)"
    dirty = bool(git(root, "status", "--porcelain"))
    agents = (root / "AGENTS.md").read_text(encoding="utf-8") if (root / "AGENTS.md").is_file() else ""
    match = POINTER.search(agents)
    handoff = match.group(1) if match else "(no hand-off pointer in AGENTS.md)"
    command = VERIFICATION.search(agents)
    verification = command.group(1).strip() if command else "(no fenced command under ## Verification in AGENTS.md)"
    return "\n".join((
        "PAES session banner (read-only)",
        f"checkout: {root.name} at {head} on {branch}, working tree {'has uncommitted changes' if dirty else 'clean'}",
        f"hand-off: {handoff}",
        f"verification: not run at session start; run {verification} and quote the result before reporting completion",
        "rules: AGENTS.md",
    ))


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
    try:
        print(banner(root))
    except Exception as error:  # fail open: one line, exit 0
        print(f"session banner unavailable: {type(error).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
