# Worktree flow policy

Status: added 2026-09-24 under Decision 0008 point 8 (increment 2); rules 5, 6 and 11 brought level with Decision 0013 on 2026-10-03 with the fetch-and-fast-forward step of the retirement routine (brief `tasks/worktree-retire-prune.json`); the local rules are in force as documented guidance; the remote rules are in force from Decision 0010, accepted 2026-09-26, from the first push onward

Provenance: reimplemented from the documented behaviour of the agent-skills worktree-flow doctrine at `adb5af6` and from section 3 of the Nebula scope-fit review of 2026-09-20; no text was copied from either source.

## Local rules, in force

1. **One increment, one worktree, one branch.** Every bounded increment runs in its own linked worktree with its own branch. A worktree is never shared between two increments, and two increments never share a branch.
2. **The main checkout stays on `main` and stays clean.** Work is never done directly in the primary checkout. It exists to hold `main`, to run verification against `main`, and to receive fast-forward merges.
3. **Naming.** The worktree is a sibling directory `../<repository>-<slug>`; the branch is `<type>/<slug>` where `<type>` is the commit type the increment will use (`feat`, `fix`, `docs`, `chore`) and `<slug>` is a short lowercase hyphenated name. Create it from `main`:

   ```sh
   git worktree add ../<repository>-<slug> -b <type>/<slug> main
   ```

4. **Verification before integration.** `python3 scripts/verify_repository.py` must print `"result": "PASS"` in the worktree before the branch is merged. The check `declared-remote-only` accepts a linked worktree.
5. **Integration is the pull request, merged by the maintainer.** Since Decision 0013 the maintainer merges the increment's pull request on the forge with a rebase merge once the CI job is green: the increment's commits are replayed onto `main` one by one with new hashes, so the commits remain the record and `main` gains no merge commit and no squash. `main`'s own history is never rewritten. The primary checkout receives `main` only by fast-forward from `origin` (rule 6) and is then verified. Before the first push (2026-09-24 to 2026-09-26) the maintainer fast-forwarded the branch locally instead; that path is closed by rule 9.
6. **Retire immediately, in order.** After the maintainer merges the pull request, bring the primary checkout level with the remote, then remove the worktree and delete the branch, in the same step and from the primary checkout:

   ```sh
   git fetch --prune origin
   git merge --ff-only origin/main
   git worktree remove ../<repository>-<slug>
   git branch -D <type>/<slug>
   ```

   `--ff-only` refuses when local `main` has diverged, which is a finding, not a case for a merge commit. `-D` is deliberate: the rebase merge gave the commits new hashes and the prune removed the remote-tracking branch, so `git branch -d` would judge the branch against `HEAD`, find none of its commits there and refuse as not fully merged. `-D` is run only after the forge reports the pull request merged, which the prune has shown by dropping `origin/<type>/<slug>`. A hand-off written before the merge quotes the branch hash, not the hash that reaches `main`. An abandoned increment is removed the same way, explicitly, and the session hand-off records that it was abandoned and why. Nothing is left to be found later.
7. **Evidence is never removed with a worktree.** A worktree that holds an unrecorded run, a new evidence file or a new hand-off is not removed until that record is committed on its branch or explicitly abandoned in a hand-off. Automatic removal of worktrees is not permitted.
8. **Automatic hooks come only from a PAES-owned record.** No hook that runs on worktree creation or removal is configured through git configuration alone; if one is ever wanted it is declared in `adapters/` under Decision 0008 and recorded with provenance.

## Remote rules, in force from Decision 0010 (accepted 2026-09-26)

9. `main` accepts no direct push; every change reaches it through a pull request from an increment branch, with the verification job green.
10. The maintainer merges. No agent merges its own or another agent's branch.
11. The remote branch is deleted with the local one when the increment is retired. The maintainer deletes it at the merge (Decision 0013 point 3); `git fetch --prune origin` in rule 6 then drops the remote-tracking branch, so no `git push --delete` is needed and none is allowed.
12. **Who pushes (Decision 0013, 2026-09-27).** The increment branch is pushed and its pull request opened by `python3 scripts/push_increment.py`, run in the worktree once verification passes; the script refuses `main`, a dirty tree, a second remote or a failing verification, and never merges. A raw `git push` stays denied. In a target of the portable kit the maintainer decides the push path.

## Relationship to other records

- Task boundaries come from a brief that satisfies [contracts/task-contract.yaml](../contracts/task-contract.yaml); the worktree is where that brief's owned paths are written and nowhere else.
- Commit messages follow [policies/contribution.md](contribution.md).
- Parallel worktrees with concurrent agents remain excluded by Decision 0004; this policy governs one serial increment at a time.
