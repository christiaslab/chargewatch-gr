---
name: commit-guard
description: Scan the staged snapshot or declared candidate paths for secret-like assignments, private identifiers, unexpected binaries, staged local-instruction or gitignored files, and vendor names, without echoing matched values. Triggers - before any commit, "run the commit guard", "scan staged files", "is it safe to commit".
---

# Commit guard (adapter wrapper)

This wrapper adds nothing to the rule. It says how to run the core guard from this environment.

- Doctrine: `policies/contribution.md`
- Script: `scripts/commit_guard.py`
- Also run: `scripts/commit_rules.py` (staged-content rules of `policies/contribution.md`)

## How to run

```sh
python3 scripts/commit_guard.py --root . --evidence runs/local-pilot-output/guard-evidence.json
python3 scripts/commit_rules.py --root .
```

Each must print `"result": "PASS"`; both exit 1 on a finding. Findings name the path and the rule only. Advisories from the second command (a vendor name used as a word) are for the maintainer to rule on; they do not block.

## Boundary

Read-only over declared candidate paths inside the workspace. Never widen the scan outside the repository and never print a matched value.
