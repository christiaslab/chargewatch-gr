#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from pilot_core import scan_staged_entries


def staged_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan declared candidate files without echoing matched values.")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--banned-term", action="append", default=[])
    parser.add_argument("--allowlisted-curated", action="append", default=[])
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    candidates = args.paths or staged_paths(root)
    resolved: list[Path] = []
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else root / candidate
        path = path.resolve()
        if root not in path.parents and path != root:
            raise SystemExit(f"candidate is outside workspace: {candidate}")
        if path.is_file():
            resolved.append(path)

    entries = {path.relative_to(root).as_posix(): path.read_bytes() for path in resolved}
    scan = scan_staged_entries(entries, args.allowlisted_curated, args.banned_term)
    findings = scan["findings"]
    evidence = {
        "evidence_id": "commit-guard",
        "artifact_count": len(resolved),
        "checks": ["secret-like-assignment", "configured-private-identifier", "unexpected-binary"],
        "result": "FAIL" if findings else "PASS",
        "findings": findings,
        "exemptions": scan["exemptions"],
    }
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
