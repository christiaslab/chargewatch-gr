# Contribution policy

Status: added 2026-09-19 under Decision 0006; the commit-history rule is enforced, the rest is guidance; 2026-10-07: enforcement named through the project specification, bot exemption for `Signed-off-by` and squash-merge guidance added (brief tasks/kit-v14-sandbox-spec-and-bots.json)

## Commit history

Commit messages and pull-request descriptions carry no attribution: no `Co-Authored-By` or `Signed-off-by` trailer, the one exception being the bot rule below, no assistant credit, and no generated-with or generated-by signature. Technical provenance (source commits, digests, verification results) belongs in the body.

Enforcement: the project's verification command, named by `verification_command` in `adapters/project-spec.yaml`, runs a check (`commit-message-hygiene` in PAES, `kit-commit-history` in a kit target) that runs `scripts/commit_hygiene.py` over every commit reachable from `HEAD` and fails on any such line. Findings name the commit and the rule, never the rejected text. The project tooling default that keeps trailers out of new commits is separate, in `.claude/settings.json`, and is not read by the check.

Bots: a `Signed-off-by` line is accepted only when the commit's author email is listed under `bot_authors` in `adapters/project-spec.yaml`, for example a dependency-update bot that signs its commits. Nothing else is exempt: a `Co-Authored-By` line or a generated-by signature still fails for a listed bot. The author email is not authenticated, so the list is a rule of history hygiene, not access control.

Squash merges: GitHub adds `Co-authored-by` lines to the squash commit of a pull request with more than one author, and that commit then fails the check. The maintainer merges such a pull request with a rebase merge (Decision 0013) or a merge commit, or removes the lines from the squash message before merging. There is no code exemption.

Commit authors: a session that commits sets `user.name` and `user.email` to the person responsible for the change; the check does not forbid an anonymous or assistant author, but the maintainer treats one as a finding.

## Staged content

Before a commit, the staged snapshot passes two guards. The pilot guard, `scripts/commit_guard.py` (pinned by the accepted baseline and unchanged), rejects secret-like assignments, configured private identifiers and unexpected binaries. The staged-content rules in `scripts/commit_rules.py` (added 2026-09-24, increment 4) add:

| Rule | Effect | Examples |
| --- | --- | --- |
| `local-instruction-file-staged` | fail | `CLAUDE.local.md`, `AGENTS.local.md`, any `*.local.md` or `settings.local.json` |
| `local-secret-file-staged` | fail | `.env`, `.env.*` except `.env.example` |
| `gitignored-path-staged` | fail | any staged path the repository's ignore rules would ignore |
| `vendor-name-in-content` | advisory, reported for a human ruling | a vendor or assistant name used as a word in staged text |

Findings name the path and the rule, never the matched text. Run `python3 scripts/commit_rules.py` from the checkout; it exits 1 on a finding. The `commit-rules` check in `scripts/verify_repository.py` runs the rules' mutation tests.

## Model-neutral core

The `model-neutral-core` check scans `contracts/`, `agents/`, `skills/`, `workflows/`, `evals/`, `policies/`, `scripts/`, `plan/` and `pilot-manifest.yaml` for the default vendor and assistant terms of `scripts/commit_rules.py` used as words. A path or host name (`.claude/`, `openai.com`) is not a word. The frozen EXP-003 scorer and the rules module itself are exempt, with the reason printed in the check's detail. Decisions, hand-offs, adapters and the cockpit may name the development environment; the core may not. The `--forbidden-term` option still adds terms over the wider scan.

## Guidance, not checked

Subject lines follow the existing `type(scope): subject` shape, with the scope optional. Whether a closed type set or subject-shape check is adopted is a later decision; it is not enforced now.
