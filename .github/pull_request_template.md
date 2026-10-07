## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` pass
- [ ] `python3 scripts/verify_kit.py` prints `"result": "PASS"`
- [ ] Nothing in the ingestion write path besides GCS; nothing under `raw/` is mutated
- [ ] No secrets, `.env` files or service-account keys
- [ ] A new data rule has a test with a real fixture
- [ ] A change to a locked choice has a new entry in `docs/decisions.md`
