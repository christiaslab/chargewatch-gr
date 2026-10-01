# Working guidance for chargewatch-gr

Status: installed from the PAES portable kit at origin commit `84648bdfb9eb`; edit freely, this file belongs to chargewatch-gr

## Read first

| Need | Canonical record |
| --- | --- |
| Commit-history and staged-content rules | [policies/contribution.md](policies/contribution.md) |
| One increment, one worktree, one branch | [policies/worktree-flow.md](policies/worktree-flow.md) |
| Review against the written rules | [policies/conform-review.md](policies/conform-review.md) |
| Task brief fields | [contracts/task-contract.yaml](contracts/task-contract.yaml) |
| Publishing an increment through the one allowed push path | [.claude/skills/publish-increment/SKILL.md](.claude/skills/publish-increment/SKILL.md) |
| Kit origin and digests | [adapters/KIT_NOTICE.md](adapters/KIT_NOTICE.md) |
| Project specification: roles, verification command, hand-off, integration path, limits | [adapters/project-spec.yaml](adapters/project-spec.yaml) |
| Latest session hand-off and open items | (none yet) |

## Verification

Run before reporting any task as complete:

```sh
python3 scripts/verify_kit.py
```

It must print `"result": "PASS"`. Do not weaken a check to make it pass; report the conflict instead.

## Working rules

- **Bounded tasks.** A task names its goal, the files it may write, what is out of scope, and the commands that prove it is done. Work that grows beyond that stops and reports.
- **Explicit write scope.** Write only inside the declared files and directories.
- **Verification before completion.** A claim that work was done is not evidence. Run the check above and quote the result.
- **Concise reports.** Lead with the outcome and the verification result, then what changed and what remains.
- **Commit history.** No attribution trailers or generated-by lines; technical provenance goes in the body.

## Enforcement

Mechanically enforced by `scripts/verify_kit.py`: the permission deny list and no-bypass setting, hook wiring, the project specification and its verification command, the shape of every skill, the commit-history rule over `HEAD`, the staged-content rules, task briefs under `tasks/`, and the kit digests. Documented guidance only: bounded tasks, write scope, report style.
