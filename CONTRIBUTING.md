# Contributing

Thanks for helping. Read this once before your first pull request.

## Ground rules

- **The archive comes first.** The logger in `src/` feeds an archive that cannot be
  rebuilt: a snapshot the feed published and nobody captured is lost. A change that puts
  ingestion at risk is not merged, however useful it is elsewhere.
- **Nothing but GCS in the ingestion write path.** No database, no validation, no agent
  before the write. Contracts and checks live downstream of `raw/`.
- **Raw is immutable.** Nothing ever mutates or deletes objects in the raw bucket.
- **No secrets in the repository.** Credentials live in Secret Manager. Push protection
  rejects pushes that contain known secret formats; do not work around it.
- **Locked choices stay locked.** The stack in `CLAUDE.md` changes only with a new entry
  in `docs/decisions.md` that records the reason.
- **Data rules are tested.** Every rule in `CLAUDE.md` under *Data rules* comes from a
  defect in the live feed (`docs/data-notes.md`) and gets a test with a real fixture.

## Setup

Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
```

No cloud access is needed to develop or run the tests.

## Before you open a pull request

Run the same checks CI runs, plus the kit verification:

```sh
uv run ruff check
uv run ruff format --check
uv run pytest
python3 scripts/verify_kit.py
```

The last command must print `"result": "PASS"`. Do not weaken a check to make it pass;
say in the pull request what conflicts instead.

## Branches and commits

- One change, one branch, named `<type>/<slug>`: `feat/`, `fix/`, `docs/` or `chore/`.
- Commit subjects follow conventional commits, at most 72 characters. A body is optional:
  up to three lines, only the why.
- No attribution trailers (`Co-Authored-By`, `Signed-off-by`) and no generated-by lines.
  CI rejects them. Details: `policies/contribution.md`.
- Everything in the repository is in English: code, comments, docs and commit messages.

## Review and merge

- `main` accepts changes only through a pull request with one approving review and a
  green `test` check. History stays linear; merges are rebase merges.
- `CODEOWNERS` requests a review from the maintainers automatically.
- The maintainer merges. Do not merge your own pull request.

## Reporting a vulnerability

Do not open a public issue. See `SECURITY.md`.
