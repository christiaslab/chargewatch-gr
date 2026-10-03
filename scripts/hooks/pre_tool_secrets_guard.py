#!/usr/bin/env python3
"""PreToolUse hook: block a write or shell command that carries a secret-like value,
and a read or search that names a secret-bearing file.

Wiring only. Reads the hook payload from stdin (tool_name, tool_input).

Write side: takes the text a Write, Edit, MultiEdit or Bash call would introduce and
applies the secret patterns of the pilot guard (scripts/pilot_core.py).

Read side: takes the path a Read, Grep or Glob call would open or search (Read
file_path; Grep path and glob; Glob pattern and path) and blocks when any path
component names a secret-bearing file, such as .env and its dotted variants, a
private key file or a credential file. A search path and a search glob are guarded
like a read, since a search prints the matching lines of the file it reaches.

A positive finding exits 2 with the rule name on stderr and never the matched value
or path. Any other outcome, including a malformed payload, a missing field or an
import error, prints at most one line to stderr and exits 0. On the write side the
core gates (scripts/commit_guard.py, the evaluations) remain the rule; the read side
has no core gate behind it, so a skipped hook leaves that one read unguarded. Known
gap: a Grep whose path is a directory and that carries no glob is not a path finding;
the shell read (cat .env) is covered by the value scan only. Standard library only.

Provenance of the read side: reimplemented from the hook doctrine summarised in
reference/technical-patterns-2026-10/TECHNICAL_KNOWLEDGE.md line 446 (per-tool field
map, a search path and glob guarded like a read, path-component match for the secret
file and its dotted variants, exit 2 blocks, fail open on parse error); no text
copied. Roadmap refinement 2026-10-01 rulings 4 and 9; no decision.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

TEXT_FIELDS = {
    "Write": ("content",),
    "Edit": ("new_string",),
    "MultiEdit": ("new_string",),
    "Bash": ("command",),
}

PATH_FIELDS = {
    "Read": ("file_path",),
    "Grep": ("path", "glob"),
    "Glob": ("pattern", "path"),
}

PATH_RULE = "secret-bearing-path"

# Each pattern is matched in full against one path component, case-insensitively
# (a case-insensitive file system opens .ENV as .env).
SECRET_COMPONENTS = {
    "env-file": re.compile(r"\.env(?:\..*)?|\.envrc"),
    "private-key-file": re.compile(r"id_(?:rsa|dsa|ecdsa|ed25519)(?:_sk)?|.*\.(?:pem|key|p12|pfx)"),
    "credential-file": re.compile(r"[._]netrc|\.npmrc|\.pypirc|\.git-credentials|\.htpasswd|credentials(?:\.json)?"),
    "secrets-file": re.compile(r"secrets\..*"),
}

# Allowed although a pattern above matches: a component whose last suffix marks it as an
# example, sample, template or distribution copy (.env.example, .env.sample, .env.template,
# .env.dist, and the kit's own *.template files). By convention these carry placeholders that
# document the keys a project expects, not values; reading them is how an agent learns the
# configuration shape without touching the real file. A real value placed in one of them is
# a write-side finding for the value scan and the commit guard, not a read-side one.
PLACEHOLDER_COMPONENT = re.compile(r".+\.(?:example|sample|template|dist)", re.IGNORECASE)

GLOB_WILDCARDS = re.compile(r"[*?]")
COMPONENT_SEPARATORS = re.compile(r"[/\\]")
BRACE_GROUP = re.compile(r"\{([^{}]*)\}")
MAX_EXPANSIONS = 64


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


def paths_from(payload: dict) -> list[str]:
    tool_input = payload.get("tool_input") or {}
    values = (tool_input.get(field) for field in PATH_FIELDS.get(payload.get("tool_name"), ()))
    return [value for value in values if isinstance(value, str) and value]


def expand_braces(value: str) -> list[str]:
    """Expand glob alternation such as *.{pem,key} into its alternatives, innermost group first."""
    pending, done = [value], []
    while pending and len(pending) + len(done) <= MAX_EXPANSIONS:
        current = pending.pop()
        group = BRACE_GROUP.search(current)
        if group is None:
            done.append(current)
            continue
        head, tail = current[:group.start()], current[group.end():]
        pending.extend(head + option + tail for option in group.group(1).split(","))
    return done + pending


def is_secret_component(component: str) -> bool:
    # Drop the wildcards so that *.pem reads as .pem and id_rsa* as id_rsa: a glob that can
    # reach a secret-bearing name is guarded like the name itself.
    name = GLOB_WILDCARDS.sub("", component).strip()
    if not name or PLACEHOLDER_COMPONENT.fullmatch(name):
        return False
    return any(pattern.fullmatch(name.lower()) for pattern in SECRET_COMPONENTS.values())


def names_secret_path(value: str) -> bool:
    return any(is_secret_component(component)
               for candidate in expand_braces(value)
               for component in COMPONENT_SEPARATORS.split(candidate))


def blocked(rules: list[str], tool: object) -> int:
    print(f"blocked by the secrets guard: {', '.join(rules)} in {tool} input; remove it and retry", file=sys.stderr)
    return 2


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
        path_hit = any(names_secret_path(value) for value in paths_from(payload))
    except Exception as error:  # fail open
        print(f"secrets guard skipped: {type(error).__name__}", file=sys.stderr)
        return 0
    if path_hit:
        return blocked([PATH_RULE], payload.get("tool_name"))
    texts = texts_from(payload)
    if not texts:
        return 0
    try:
        sys.path.insert(0, str(root / "scripts"))
        from pilot_core import scan_text  # the pinned pilot guard's patterns
        rules = sorted({rule for text in texts for rule in scan_text(text)})
    except Exception as error:  # fail open
        print(f"secrets guard skipped: {type(error).__name__}", file=sys.stderr)
        return 0
    if rules:
        return blocked(rules, payload.get("tool_name"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
