# PAES kit notice

origin: paes
origin_commit: ecf63cd21d5f4e4d3ac73cbdc3af9a99d331db5d
exported: 2026-10-10
licence: MIT (the exported kit, Decision 0018; full text in the section below)
copyright: Copyright (c) 2026 Panagiotis Christias

The exported kit is granted under the MIT licence; inside the origin repository the same files are AGPL-3.0-only, and the MIT grant attaches to exactly the files the manifest lists at the origin commit, byte-identical copies and rendered templates alike.

Files below marked with a digest are byte-identical copies of the origin; templates are filled at install time and are not digest-checked; a line marked `skipped` names a file the target already had, which the installer left alone and does not digest-check; a line marked `modified` names a copy the kit wrote and the target changed since, which the maintainer took as the target's own with `install --upgrade --own <path>` and which is not digest-checked until it is back at a kit digest.

## Digests

8b6b2add78c35a2463cb3df1c797d8496d8aeb9c106762e81a8d7a28c1c5d51c  adapters/kit-manifest.yaml
template  adapters/project-spec.yaml
template  .claude/settings.json
3bf6f5e8f81c810f6d0bce337ee3772db707fdeaf1d5c09e245a74017c64d1db  .claude/skills/commit-guard/SKILL.md
template  .claude/skills/verify-kit/SKILL.md
template  .claude/skills/publish-increment/SKILL.md
template  AGENTS.md
6b606150f8cca139f7df50a391261780fb6c86ece5d0f70863457211ba1f5ce1  scripts/hooks/session_start.py
ff01e4eb1927897ec3427e37e3be89dd11eb4a8792031f639ea36309cefc0d0c  scripts/hooks/pre_tool_secrets_guard.py
dc2fee25ecefc0434726697c0b297f9e0b6aa386c8073d2131d86de06d94fe13  scripts/test_hooks.py
31a907772711bbc69804c838905b41ae99d27a3f0bb85f0cb4623db9debf497f  scripts/commit_guard.py
2af9569858100552e4eacd7398f4760a00f80247824fe90b963cb3533c772c36  scripts/pilot_core.py
71a0f85e373f5e8123638f66b09aa89c7932470f859d172d2b79c57df70bea9a  scripts/commit_rules.py
ec856309891382a227815f9fe2bfa726aa690bcff535e87f4a855858708902ef  scripts/test_commit_rules.py
a955dcf377459e1671bf14678a431f540be2bdf9aa1c12223d7399c778aa5674  scripts/commit_hygiene.py
473afcdbbb28650687873c93330a4db6b4c1c5cca9a04a370a870847390d8bf6  scripts/test_commit_hygiene.py
d81f4adcd88eda8e20caa06cfa3419d8053b8e76a6d54df0b3ae40cdb8d48a1e  scripts/task_contract.py
ed0c35c07f7a5c6dfa98db6a7e92d94457928e0fbceccb277862c7d69701c617  scripts/test_task_contract.py
47d319c04cdc6fb198c7a39c2901f5cc970913d37356297023126323af8cac2e  scripts/kit.py
6c728147819690964cf7d62970f004495dec6996fdc738a6fdc6753b6aa003ec  scripts/verify_kit.py
4c8b0044a33f59949650ae26c83ba428c3b585286b9b63d62a3e6754bf39f5fe  scripts/push_increment.py
ab2393dbed2dd28006700ebb7e6b379d1ec46221719c3abbfac682504e8a68e1  scripts/test_push_increment.py
optional  .github/workflows/verify.yml  (written only when the installer is asked)
a14e95714586d6bcd94860aa718b51155c3fd9042996eb64c6344e17b34fd0de  contracts/task-contract.yaml
ee0de367401604763a75db92b44ee541b6bf85dbdab57143af24fe39076c0f51  policies/contribution.md
540bc7ea87779c4086b261eb11208b2fd888336d4ef2aa7c491d06e492c75a73  policies/worktree-flow.md
dcdbd608b95064455d4152ca387f89fa06601f9013b1846097ffe6ad36399474  policies/conform-review.md

## Retiring an increment branch

The push script, scripts/push_increment.py, creates an increment branch in this repository and opens its pull request; it never merges and never deletes. After the maintainer merges, and only once the forge shows the merge (`git ls-remote --heads origin` no longer lists the branch), retire it from the primary checkout, in order, as policies/worktree-flow.md rule 6 says: `git fetch --prune origin`, `git merge --ff-only origin/main`, `git worktree remove <worktree>` when a worktree holds the branch, then `git branch -D <branch>`.

## Upgrades

- 2026-10-08: from origin commit 6d72ca87020e (kit version 12) to cebe25e6c4a5 (kit version 17); files written: 9; owned: none; refused: none
- 2026-10-08: from origin commit cebe25e6c4a5 (kit version 17) to 7e6629a8222a (kit version 18); files written: 4; owned: none; refused: none
- 2026-10-10: from origin commit 7e6629a8222a (kit version 18) to e5bc4d7a8888 (kit version 19); files written: 2; owned: none; refused: none
- 2026-10-10: from origin commit e5bc4d7a8888 (kit version 19) to ecf63cd21d5f (kit version 22); files written: 5; owned: none; refused: none

## Licence

MIT License

Copyright (c) 2026 Panagiotis Christias

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
