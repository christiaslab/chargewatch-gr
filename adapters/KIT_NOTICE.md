# PAES kit notice

origin: paes
origin_commit: 84648bdfb9eb3b3c5067786ba2daadc1420e9b07
exported: 2026-10-01
licence: MIT (the exported kit, Decision 0018; full text in the section below)
copyright: Copyright (c) 2026 Panagiotis Christias

The exported kit is granted under the MIT licence; inside the origin repository the same files are AGPL-3.0-only, and the MIT grant attaches to exactly the files the manifest lists at the origin commit, byte-identical copies and rendered templates alike.

Files below marked with a digest are byte-identical copies of the origin; templates are filled at install time and are not digest-checked; a line marked `skipped` names a file the target already had, which the installer left alone and does not digest-check.

## Digests

d4e52d0e6b655eb3d1157adb464d24706a58af3769a1d07df0ab135eba9fe4e8  adapters/kit-manifest.yaml
template  adapters/project-spec.yaml
template  .claude/settings.json
3bf6f5e8f81c810f6d0bce337ee3772db707fdeaf1d5c09e245a74017c64d1db  .claude/skills/commit-guard/SKILL.md
template  .claude/skills/verify-kit/SKILL.md
template  .claude/skills/publish-increment/SKILL.md
template  AGENTS.md
6b606150f8cca139f7df50a391261780fb6c86ece5d0f70863457211ba1f5ce1  scripts/hooks/session_start.py
35e374cdbe32e0b83a91abb09cedfad0b95189a191c53e0c43aa305a89b6c994  scripts/hooks/pre_tool_secrets_guard.py
31a907772711bbc69804c838905b41ae99d27a3f0bb85f0cb4623db9debf497f  scripts/commit_guard.py
2af9569858100552e4eacd7398f4760a00f80247824fe90b963cb3533c772c36  scripts/pilot_core.py
8f12fc5fe140adb7bcd3f3b7713f4415b7ae0f6247926713aeb32922448e6f16  scripts/commit_rules.py
ec856309891382a227815f9fe2bfa726aa690bcff535e87f4a855858708902ef  scripts/test_commit_rules.py
322360f4e71b570375c86efa652cd63e681d3320c60a287af99ceb05a0fda255  scripts/commit_hygiene.py
57fa8a1068562f29b93c60dfca40ec6a59d8396da5f60e6f46a5d81e87d55077  scripts/test_commit_hygiene.py
d81f4adcd88eda8e20caa06cfa3419d8053b8e76a6d54df0b3ae40cdb8d48a1e  scripts/task_contract.py
ed0c35c07f7a5c6dfa98db6a7e92d94457928e0fbceccb277862c7d69701c617  scripts/test_task_contract.py
190d2d271dddfb7692f9a3d6084fcb6e2cf2b7b47aa8c6734f206bcf2c86bad8  scripts/kit.py
77d76f62e39f755e91825aa1babcab4ffaf7c2a182d3669d7b5701fa42541644  scripts/test_kit.py
20b627e77b19a7e7cc4abf0622deea8333f775bc2998fe2086eb6e1f712724c7  scripts/verify_kit.py
90db073ed9989cf577b4a83a14dfced9e79605b84ce0d7bc5fc1cff0840cb99c  scripts/test_verify_kit.py
637becd2771c5164ff7e47a903c79052e1bb944acd95a6b42e2a502db8daab25  scripts/push_increment.py
c587efe016effcd9eba40ac38cb0e072602ce7bad5a3e67ee8c985ab16ad0e4e  scripts/test_push_increment.py
optional  .github/workflows/verify.yml  (written only when the installer is asked)
a14e95714586d6bcd94860aa718b51155c3fd9042996eb64c6344e17b34fd0de  contracts/task-contract.yaml
283665c3c4a91ff4701e7f5155cc7b50c86303139cee6efdf176a911d2271df3  policies/contribution.md
0f0582fd238cb32766def66b64aa4f79ca85b7fdabfb2ae90cd30d333d1fb836  policies/worktree-flow.md
a81587b6e7570774fe9c3a5d21e966456f25740f248af081d0f23e9153d23188  policies/conform-review.md

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
