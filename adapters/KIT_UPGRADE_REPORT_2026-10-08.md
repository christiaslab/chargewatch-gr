# Kit install report for chargewatch-gr

Origin commit: `cebe25e6c4a5cdf9c7acab07b4290ec921a7688b`. Target: `/Users/panagiotischristias/Developer/Personal/Projects/chargewatch-gr`. Kit copies still at the installed notice's digest and the notice were overwritten; nothing was deleted.

## Written

| Path | SHA-256 |
| --- | --- |
| `adapters/kit-manifest.yaml` | `ca8fa6308e028cc54cda64d4d56fbd0a6d4d12daa0bc4307dd689026724e16d3` |
| `scripts/test_hooks.py` | `d5972d79b8144e673153822e9fa3fa88be1a84ef8977ae334ae8a92fc100cf3a` |
| `scripts/test_commit_hygiene.py` | `473afcdbbb28650687873c93330a4db6b4c1c5cca9a04a370a870847390d8bf6` |
| `scripts/kit.py` | `4ba941e152c33610b2c4a73a9ee1dba633d40f72e37557beff906349485e0ae7` |
| `scripts/verify_kit.py` | `f527ce498a6c77e441925caeaa71e188821fb838f2ad20cae60b8193530370da` |
| `scripts/push_increment.py` | `783d7bb65dc5b68733110165a922b40472c4c3680f3130dacc83a39904f7301e` |
| `scripts/test_push_increment.py` | `4a12e935425c481fda026cffe630baf4e8c689fd49ea73f619d69e0da9129045` |
| `policies/worktree-flow.md` | `540bc7ea87779c4086b261eb11208b2fd888336d4ef2aa7c491d06e492c75a73` |
| `policies/conform-review.md` | `dcdbd608b95064455d4152ca387f89fa06601f9013b1846097ffe6ad36399474` |
| `adapters/KIT_NOTICE.md` | `7a46a4ab2124a544dde493b8ca92cbd03e569923124279eef5f2bd6e69392d90` |

## Skipped

- `adapters/project-spec.yaml`: exists in the target; not overwritten
- `.claude/settings.json`: exists in the target; not overwritten
- `.claude/skills/commit-guard/SKILL.md`: unchanged, already at the export's digest
- `.claude/skills/verify-kit/SKILL.md`: exists in the target; not overwritten
- `.claude/skills/publish-increment/SKILL.md`: exists in the target; not overwritten
- `AGENTS.md`: exists in the target; not overwritten
- `scripts/hooks/session_start.py`: unchanged, already at the export's digest
- `scripts/hooks/pre_tool_secrets_guard.py`: unchanged, already at the export's digest
- `scripts/commit_guard.py`: unchanged, already at the export's digest
- `scripts/pilot_core.py`: unchanged, already at the export's digest
- `scripts/commit_rules.py`: unchanged, already at the export's digest
- `scripts/test_commit_rules.py`: unchanged, already at the export's digest
- `scripts/commit_hygiene.py`: exists in the target; not overwritten
- `scripts/task_contract.py`: unchanged, already at the export's digest
- `scripts/test_task_contract.py`: unchanged, already at the export's digest
- `.github/workflows/verify.yml`: exists in the target; not overwritten
- `contracts/task-contract.yaml`: unchanged, already at the export's digest
- `policies/contribution.md`: exists in the target; not overwritten

## Merge proposals, for the maintainer

- (none)

## Checklist

1. review the merge proposals above, if any; a written .claude/settings.proposed.json is the settings merge ready to adopt or discard
2. fill in adapters/project-spec.yaml: at least the maintainer, then the other roles, the verification command and the limits (copy the project's hard rules there, one line each); `python3 scripts/verify_kit.py` fails while a placeholder remains
3. run `python3 scripts/verify_kit.py` in the target and quote its result
4. decide whether any git hook the target already had stays beside the kit's hooks
5. commit under policies/contribution.md; the kit never commits, the maintainer does
6. choose the integration path in adapters/project-spec.yaml: `push script: github`, `push script: none` or `maintainer pushes`; scripts/push_increment.py runs only under the first two and never merges
7. then test the kit in a session opened in this checkout: look for the session banner, then paste: Read AGENTS.md and adapters/project-spec.yaml. Name the one bounded task you would take next in this project, with its owned paths, and stop before writing. Then run the verify-kit skill and quote the result. Then try git push --dry-run and curl https://example.com, and report what happened. Do not commit.
8. to upgrade later, run the kit.py of the newer export (`python3 <export>/scripts/kit.py install ...`): a newer export is installed with the kit.py it ships, not with the installed one
9. after each merged pull request, retire its branch as adapters/KIT_NOTICE.md says under `Retiring an increment branch`
