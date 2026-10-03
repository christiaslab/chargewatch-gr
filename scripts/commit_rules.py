#!/usr/bin/env python3
"""Staged-content rules beside the pilot commit guard, and the vendor-term matcher.

`scripts/commit_guard.py` and `scripts/pilot_core.py` are pinned by the accepted
baseline's implementation digest and are not changed. This module adds the two
rules from the contribution policy that the pilot guard does not cover:

* a staged local-instruction or local-secret file fails (``CLAUDE.local.md``,
  ``AGENTS.local.md``, any ``*.local.md`` or ``settings.local.json``, ``.env`` and
  ``.env.*`` except ``.env.example``), as does any staged path that the
  repository's ignore rules would ignore;
* a vendor or assistant name in staged text is reported as an advisory for a
  human ruling; it does not fail the scan.

The vendor-term matcher is also used by the repository verifier's
``model-neutral-core`` check. A term counts only as a word: a match preceded by
a dot or followed by a dot or slash is a path or host name (``.claude/``,
``CLAUDE.local.md``, ``openai.com``) and is not reported. Findings name the path
and the rule, never the matched text. Standard library only.

Usage: python3 scripts/commit_rules.py [--root DIR] [PATH ...]
Exit 0 when no finding, 1 when a finding exists, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

DEFAULT_VENDOR_TERMS = (
    "anthropic", "claude", "openai", "chatgpt", "codex", "gemini", "copilot", "mistral", "llama",
)
LOCAL_INSTRUCTION_BASENAMES = {"claude.local.md", "agents.local.md", "settings.local.json"}
LOCAL_INSTRUCTION_SUFFIXES = (".local.md", ".local.json")
SECRET_FILE_ALLOWED = {".env.example"}


def vendor_term_pattern(terms: Iterable[str] = DEFAULT_VENDOR_TERMS) -> re.Pattern[str]:
    """Whole-word, case-insensitive; a dot before or a dot or slash after marks a path or host."""
    alternatives = "|".join(re.escape(term) for term in terms if term)
    return re.compile(rf"(?<![\w.])(?:{alternatives})(?![\w./])", re.IGNORECASE)


def vendor_hits(text: str, terms: Iterable[str] = DEFAULT_VENDOR_TERMS) -> list[str]:
    """Return the sorted lowercase terms that occur as words in ``text``; never the surrounding text."""
    pattern = vendor_term_pattern(terms)
    return sorted({match.group(0).casefold() for match in pattern.finditer(text)})


def local_file_rule(relative_path: str) -> str | None:
    name = Path(relative_path).name
    lowered = name.casefold()
    if lowered in LOCAL_INSTRUCTION_BASENAMES or lowered.endswith(LOCAL_INSTRUCTION_SUFFIXES):
        return "local-instruction-file-staged"
    if (lowered == ".env" or lowered.startswith(".env.")) and lowered not in SECRET_FILE_ALLOWED:
        return "local-secret-file-staged"
    return None


def staged_relative_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"], cwd=root, check=True, capture_output=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def ignored_paths(root: Path, relative_paths: Iterable[str]) -> set[str]:
    """Paths the repository's ignore rules would ignore, tracked or not."""
    candidates = [path for path in relative_paths if path]
    if not candidates:
        return set()
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=root, input="\0".join(candidates).encode("utf-8") + b"\0", capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("git check-ignore failed")
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


def scan_staged(root: Path, relative_paths: Iterable[str] | None = None,
                vendor_terms: Iterable[str] = DEFAULT_VENDOR_TERMS) -> dict[str, object]:
    root = root.resolve()
    paths = list(relative_paths) if relative_paths is not None else staged_relative_paths(root)
    findings: list[dict[str, str]] = []
    advisories: list[dict[str, str]] = []
    for path in paths:
        rule = local_file_rule(path)
        if rule:
            findings.append({"path": path, "rule": rule})
    for path in sorted(ignored_paths(root, paths)):
        findings.append({"path": path, "rule": "gitignored-path-staged"})
    for path in paths:
        full = root / path
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for term in vendor_hits(text, vendor_terms):
            advisories.append({"path": path, "rule": "vendor-name-in-content", "term": term})
    findings.sort(key=lambda item: (item["path"], item["rule"]))
    return {
        "evidence_id": "commit-rules",
        "artifact_count": len(paths),
        "checks": ["local-instruction-file-staged", "local-secret-file-staged", "gitignored-path-staged", "vendor-name-in-content"],
        "result": "FAIL" if findings else "PASS",
        "findings": findings,
        "advisories": advisories,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the staged-content rules of policies/contribution.md.")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--vendor-term", action="append", default=[])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / ".git").exists():
        print(f"usage: not a git checkout: {root}", file=sys.stderr)
        return 2
    terms = tuple(args.vendor_term) or DEFAULT_VENDOR_TERMS
    report = scan_staged(root, args.paths or None, terms)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
