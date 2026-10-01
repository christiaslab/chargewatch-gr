---
name: verify-kit
description: Run the portable-kit verification and quote its result before reporting any task as complete. Triggers - "verify the kit", "run kit verification", "is the kit green", before every hand-off and before every merge.
---

# Kit verification (adapter wrapper)

This wrapper adds nothing to the rule. It says how to run the kit verifier in chargewatch-gr.

- Doctrine: `AGENTS.md`
- Script: `scripts/verify_kit.py`

## How to run

```sh
python3 scripts/verify_kit.py
```

It must print `"result": "PASS"`. Quote the result and the check count in the report. A failing check is reported as a conflict, never weakened to pass. Standard output is one JSON document; test progress goes to standard error.
