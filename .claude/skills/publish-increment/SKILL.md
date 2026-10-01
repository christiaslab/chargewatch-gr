---
name: publish-increment
description: Push the current increment branch and open its review through the backend the project specification names, then report the result; never merge. Triggers - "publish the increment", "push the branch", "open the pull request", after verification passes at the end of an increment.
---

# Publish increment (adapter wrapper)

This wrapper adds nothing to the rule. It says how to run the one allowed push path in chargewatch-gr.

- Doctrine: `policies/worktree-flow.md`
- Script: `scripts/push_increment.py`

## How to run

```sh
python3 scripts/push_increment.py
```

It must print `"result": "PASS"` with the review URL, or with the branch name when the backend is `none` and the maintainer opens the review by hand. The backend comes from the `integration` field of `adapters/project-spec.yaml`: `push script: github` or `push script: none`; under `maintainer pushes` the script refuses to run and the maintainer pushes. The script refuses `main`, a branch not shaped `type/slug`, a dirty tree, a second remote and a failing verification, strips attribution from the body, and never merges: the maintainer merges.
