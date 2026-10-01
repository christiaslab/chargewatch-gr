# Kit install report for chargewatch-gr

Origin commit: `84648bdfb9eb3b3c5067786ba2daadc1420e9b07`. Target: `/Users/panagiotischristias/Developer/Personal/Projects/chargewatch-gr`. Nothing was overwritten or deleted.

## Written

| Path | SHA-256 |
| --- | --- |
| `adapters/kit-manifest.yaml` | `d4e52d0e6b655eb3d1157adb464d24706a58af3769a1d07df0ab135eba9fe4e8` |
| `adapters/project-spec.yaml` | `28ac30217f6a430ec83fd08f56c2ab30feeb3ea6ab8426c341b4b38e056b1b7d` |
| `.claude/settings.proposed.json` | `3b12b0645f425758def3d4945425e5b6da5afaccfcad45068d45544d81c1b6aa` |
| `.claude/skills/commit-guard/SKILL.md` | `3bf6f5e8f81c810f6d0bce337ee3772db707fdeaf1d5c09e245a74017c64d1db` |
| `.claude/skills/verify-kit/SKILL.md` | `b979a7f88142c6bc022751f086616def0bf8442990d2fc17a9002b71a79ed754` |
| `.claude/skills/publish-increment/SKILL.md` | `8b3183f65be4c64a27764f23282a20632e0ad796b917bb239d4bdbcbb56f3d25` |
| `AGENTS.md` | `6257c68fac6fd3d7c128b1900c790045ed205b2b43df09eaa07e9661c2f3990c` |
| `scripts/hooks/session_start.py` | `6b606150f8cca139f7df50a391261780fb6c86ece5d0f70863457211ba1f5ce1` |
| `scripts/hooks/pre_tool_secrets_guard.py` | `35e374cdbe32e0b83a91abb09cedfad0b95189a191c53e0c43aa305a89b6c994` |
| `scripts/commit_guard.py` | `31a907772711bbc69804c838905b41ae99d27a3f0bb85f0cb4623db9debf497f` |
| `scripts/pilot_core.py` | `2af9569858100552e4eacd7398f4760a00f80247824fe90b963cb3533c772c36` |
| `scripts/commit_rules.py` | `8f12fc5fe140adb7bcd3f3b7713f4415b7ae0f6247926713aeb32922448e6f16` |
| `scripts/test_commit_rules.py` | `ec856309891382a227815f9fe2bfa726aa690bcff535e87f4a855858708902ef` |
| `scripts/commit_hygiene.py` | `322360f4e71b570375c86efa652cd63e681d3320c60a287af99ceb05a0fda255` |
| `scripts/test_commit_hygiene.py` | `57fa8a1068562f29b93c60dfca40ec6a59d8396da5f60e6f46a5d81e87d55077` |
| `scripts/task_contract.py` | `d81f4adcd88eda8e20caa06cfa3419d8053b8e76a6d54df0b3ae40cdb8d48a1e` |
| `scripts/test_task_contract.py` | `ed0c35c07f7a5c6dfa98db6a7e92d94457928e0fbceccb277862c7d69701c617` |
| `scripts/kit.py` | `190d2d271dddfb7692f9a3d6084fcb6e2cf2b7b47aa8c6734f206bcf2c86bad8` |
| `scripts/test_kit.py` | `77d76f62e39f755e91825aa1babcab4ffaf7c2a182d3669d7b5701fa42541644` |
| `scripts/verify_kit.py` | `20b627e77b19a7e7cc4abf0622deea8333f775bc2998fe2086eb6e1f712724c7` |
| `scripts/test_verify_kit.py` | `90db073ed9989cf577b4a83a14dfced9e79605b84ce0d7bc5fc1cff0840cb99c` |
| `scripts/push_increment.py` | `637becd2771c5164ff7e47a903c79052e1bb944acd95a6b42e2a502db8daab25` |
| `scripts/test_push_increment.py` | `c587efe016effcd9eba40ac38cb0e072602ce7bad5a3e67ee8c985ab16ad0e4e` |
| `contracts/task-contract.yaml` | `a14e95714586d6bcd94860aa718b51155c3fd9042996eb64c6344e17b34fd0de` |
| `policies/contribution.md` | `283665c3c4a91ff4701e7f5155cc7b50c86303139cee6efdf176a911d2271df3` |
| `policies/worktree-flow.md` | `0f0582fd238cb32766def66b64aa4f79ca85b7fdabfb2ae90cd30d333d1fb836` |
| `policies/conform-review.md` | `a81587b6e7570774fe9c3a5d21e966456f25740f248af081d0f23e9153d23188` |
| `adapters/KIT_NOTICE.md` | `a4282bbcb05f9550f315cee84bc2edc92b77fee3128b05b30336e5a46188062e` |

## Skipped

- `.claude/settings.json`: exists in the target; not overwritten

## Merge proposals, for the maintainer

- .claude/settings.json: 30 additions the target lacks: 2 top-level keys, 21 allow entries, 5 deny entries, 2 hook events; and the no-bypass value, named below; the merge is written as .claude/settings.proposed.json
- .claude/settings.json: set permissions.disableBypassPermissionsMode to the string "disable"
- .claude/settings.proposed.json: the target's settings with the kit's added, written beside the original for review; adopt it by replacing .claude/settings.json, then delete it
- CLAUDE.md: exists; add the line `@AGENTS.md` so the working guidance is read, or keep it separate on purpose

## Checklist

1. review the merge proposals above, if any; a written .claude/settings.proposed.json is the settings merge ready to adopt or discard
2. fill in adapters/project-spec.yaml: at least the maintainer, then the other roles, the verification command and the limits (copy the project's hard rules there, one line each); `python3 scripts/verify_kit.py` fails while a placeholder remains
3. run `python3 scripts/verify_kit.py` in the target and quote its result
4. decide whether any git hook the target already had stays beside the kit's hooks
5. commit under policies/contribution.md; the kit never commits, the maintainer does
6. choose the integration path in adapters/project-spec.yaml: `push script: github`, `push script: none` or `maintainer pushes`; scripts/push_increment.py runs only under the first two and never merges
7. then test the kit in a session opened in this checkout: look for the session banner, then paste: Read AGENTS.md and adapters/project-spec.yaml. Name the one bounded task you would take next in this project, with its owned paths, and stop before writing. Then run the verify-kit skill and quote the result. Then try git push --dry-run and curl https://example.com, and report what happened. Do not commit.
