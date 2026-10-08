# Kit install report for chargewatch-gr

Origin commit: `7e6629a8222abaa3597681bc3ff791eeda7c897d`. Target: `/Users/panagiotischristias/Developer/Personal/Projects/chargewatch-gr`. Kit copies still at the installed notice's digest and the notice were overwritten; nothing was deleted.

## Written

| Path | SHA-256 |
| --- | --- |
| `adapters/kit-manifest.yaml` | `023b6d483cfea7b8196ea98e8549275b0f59d2bddb7bbcf75cab8a83b4d8109a` |
| `scripts/kit.py` | `d2c304dfd40b1c45b92a3cb0e04d4f4c9a361f49e95ae8b92eee312dc7e41c0f` |
| `scripts/push_increment.py` | `4c8b0044a33f59949650ae26c83ba428c3b585286b9b63d62a3e6754bf39f5fe` |
| `scripts/test_push_increment.py` | `ab2393dbed2dd28006700ebb7e6b379d1ec46221719c3abbfac682504e8a68e1` |
| `adapters/KIT_NOTICE.md` | `eecc1d64bfee9d19da30487dbb054771b236ede7a3d273c7afdb9a7a296d5977` |

## Skipped

- `adapters/project-spec.yaml`: exists in the target; not overwritten
- `.claude/settings.json`: exists in the target; not overwritten
- `.claude/skills/commit-guard/SKILL.md`: unchanged, already at the export's digest
- `.claude/skills/verify-kit/SKILL.md`: exists in the target; not overwritten
- `.claude/skills/publish-increment/SKILL.md`: exists in the target; not overwritten
- `AGENTS.md`: exists in the target; not overwritten
- `scripts/hooks/session_start.py`: unchanged, already at the export's digest
- `scripts/hooks/pre_tool_secrets_guard.py`: unchanged, already at the export's digest
- `scripts/test_hooks.py`: unchanged, already at the export's digest
- `scripts/commit_guard.py`: unchanged, already at the export's digest
- `scripts/pilot_core.py`: unchanged, already at the export's digest
- `scripts/commit_rules.py`: unchanged, already at the export's digest
- `scripts/test_commit_rules.py`: unchanged, already at the export's digest
- `scripts/commit_hygiene.py`: the target's own file, at the export's bytes; the notice now records its digest
- `scripts/test_commit_hygiene.py`: unchanged, already at the export's digest
- `scripts/task_contract.py`: unchanged, already at the export's digest
- `scripts/test_task_contract.py`: unchanged, already at the export's digest
- `scripts/verify_kit.py`: unchanged, already at the export's digest
- `.github/workflows/verify.yml`: exists in the target; not overwritten
- `contracts/task-contract.yaml`: unchanged, already at the export's digest
- `policies/contribution.md`: the target's own file, at the export's bytes; the notice now records its digest
- `policies/worktree-flow.md`: unchanged, already at the export's digest
- `policies/conform-review.md`: unchanged, already at the export's digest

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
