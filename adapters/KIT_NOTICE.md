# PAES kit notice

origin: paes
origin_commit: 6d72ca87020e979d80d644759ccb0c2140651ee9
exported: 2026-10-06
licence: MIT (the exported kit, Decision 0018; full text in the section below)
copyright: Copyright (c) 2026 Panagiotis Christias

The exported kit is granted under the MIT licence; inside the origin repository the same files are AGPL-3.0-only, and the MIT grant attaches to exactly the files the manifest lists at the origin commit, byte-identical copies and rendered templates alike.

Files below marked with a digest are byte-identical copies of the origin; templates are filled at install time and are not digest-checked; a line marked `skipped` names a file the target already had, which the installer left alone and does not digest-check.

## Digests

3767e506fe0c6d511d0206054188a610dcf20761bb7fdb2fe281103638989c22  adapters/kit-manifest.yaml
template  adapters/project-spec.yaml
template  .claude/settings.json
3bf6f5e8f81c810f6d0bce337ee3772db707fdeaf1d5c09e245a74017c64d1db  .claude/skills/commit-guard/SKILL.md
template  .claude/skills/verify-kit/SKILL.md
template  .claude/skills/publish-increment/SKILL.md
template  AGENTS.md
6b606150f8cca139f7df50a391261780fb6c86ece5d0f70863457211ba1f5ce1  scripts/hooks/session_start.py
ff01e4eb1927897ec3427e37e3be89dd11eb4a8792031f639ea36309cefc0d0c  scripts/hooks/pre_tool_secrets_guard.py
287615111a1cc67067caa57ab1f223ed3b69e9942e91274ba263988c4752d57c  scripts/test_hooks.py
31a907772711bbc69804c838905b41ae99d27a3f0bb85f0cb4623db9debf497f  scripts/commit_guard.py
2af9569858100552e4eacd7398f4760a00f80247824fe90b963cb3533c772c36  scripts/pilot_core.py
71a0f85e373f5e8123638f66b09aa89c7932470f859d172d2b79c57df70bea9a  scripts/commit_rules.py
ec856309891382a227815f9fe2bfa726aa690bcff535e87f4a855858708902ef  scripts/test_commit_rules.py
322360f4e71b570375c86efa652cd63e681d3320c60a287af99ceb05a0fda255  scripts/commit_hygiene.py
57fa8a1068562f29b93c60dfca40ec6a59d8396da5f60e6f46a5d81e87d55077  scripts/test_commit_hygiene.py
d81f4adcd88eda8e20caa06cfa3419d8053b8e76a6d54df0b3ae40cdb8d48a1e  scripts/task_contract.py
ed0c35c07f7a5c6dfa98db6a7e92d94457928e0fbceccb277862c7d69701c617  scripts/test_task_contract.py
99b22598cf449b5e8e9af030f51f2fd1070d4c70fb352f8056d9f25276782c9b  scripts/kit.py
20b627e77b19a7e7cc4abf0622deea8333f775bc2998fe2086eb6e1f712724c7  scripts/verify_kit.py
637becd2771c5164ff7e47a903c79052e1bb944acd95a6b42e2a502db8daab25  scripts/push_increment.py
c587efe016effcd9eba40ac38cb0e072602ce7bad5a3e67ee8c985ab16ad0e4e  scripts/test_push_increment.py
optional  .github/workflows/verify.yml  (written only when the installer is asked)
a14e95714586d6bcd94860aa718b51155c3fd9042996eb64c6344e17b34fd0de  contracts/task-contract.yaml
283665c3c4a91ff4701e7f5155cc7b50c86303139cee6efdf176a911d2271df3  policies/contribution.md
1d6e20ff914b4c09d61680a56cbbae002297ba5c4259eba99c5ebc8d3adc9a5c  policies/worktree-flow.md
34686667a0e66d5192ec089cc6709231096f31bce7e009377863758e42fd6395  policies/conform-review.md

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
