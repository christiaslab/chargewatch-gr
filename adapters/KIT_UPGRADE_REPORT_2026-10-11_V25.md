# Kit install report for chargewatch-gr

Origin commit: `84e3dd371825dbdec864fcb9e8f9e789c515a246`. Target: `/Users/panagiotischristias/Developer/Personal/Projects/chargewatch-gr/.claude/worktrees/vigilant-roentgen-24f697`. Kit copies still at the installed notice's digest and the notice were overwritten; nothing was deleted.

## Written

| Path | SHA-256 |
| --- | --- |
| `adapters/kit-manifest.yaml` | `6b7273682cff4e6df3aa78e01b497ddf946ce4b838f073f90606ca0ab74375b2` |
| `scripts/test_hooks.py` | `31c53c6c17e92f0cb658fa8a19dad9b2abe3acce144cfedb20c502960fe46b31` |
| `scripts/kit.py` | `a0a5dcbad13772e6366d7799a52711bae56686f8aacba9b8fe0315610756cce9` |
| `adapters/KIT_NOTICE.md` | `09657976cc7183e2ad5c42f5d0f37d935215753968ae70fb54f4c581607ebe40` |

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
- `scripts/commit_hygiene.py`: unchanged, already at the export's digest
- `scripts/test_commit_hygiene.py`: unchanged, already at the export's digest
- `scripts/task_contract.py`: unchanged, already at the export's digest
- `scripts/test_task_contract.py`: unchanged, already at the export's digest
- `scripts/verify_kit.py`: unchanged, already at the export's digest
- `scripts/push_increment.py`: unchanged, already at the export's digest
- `scripts/test_push_increment.py`: unchanged, already at the export's digest
- `.github/workflows/verify.yml`: exists in the target; not overwritten
- `contracts/task-contract.yaml`: unchanged, already at the export's digest
- `policies/contribution.md`: unchanged, already at the export's digest
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
