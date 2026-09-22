# ChargeWatch GR

Agentic analytics platform over Greek EV-charging open data. Portfolio project with a
commercial path. Solo developer, ~5-8 hours/week.

**The core asset is the time-series archive.** The Μ.Υ.Φ.Α.Η. dynamic feed is a snapshot,
not a history — whatever is not captured is lost permanently. Nothing may compromise the
continuity of ingestion. When in doubt, favour keeping the logger running over any other
concern.

**Current milestone: M1 — the logger, running unattended.** Order and definition of done:
`docs/roadmap.md`. After M1 the project has a pause point: everything downstream reads
from `raw/` and is recomputable, so it can stop for a quarter with zero data loss. Only
the logger must never stop.

## Locked stack

| Layer | Choice |
|---|---|
| Runtime | Cloud Run **Service** + Cloud Scheduler, `europe-west1` |
| Raw storage | GCS `gs://chargewatch-raw-gr`, `.json.zip` as served, immutable |
| Lake | DuckLake v1.0 — catalog in Neon Postgres, Parquet in GCS |
| Query engine | DuckDB over DuckLake |
| Transform | Polars (diff) + SQLMesh (models) |
| Serving | Neon Postgres `chargewatch_gold`, read-only role `agent_ro` |
| Semantic layer | Metric/dimension definitions in-repo over gold — no new service (#13) |
| Agent interface | MCP server over the semantic layer (#14) |
| Agents | Pydantic AI |
| Models | Vertex AI — see `models.yaml` |
| Observability | Cloud Monitoring for ingestion (M1, #15); Langfuse for agent tracing and cost (M7) |
| Tooling | uv, Ruff, pytest |

Rationale for every line: `docs/decisions.md`. Do not change a locked choice without
recording a new decision entry with its reason.

## Hard rules

- **Never write secrets to files in the repo.** Connection strings and API keys live in
  Secret Manager. No `.env` with real values committed, no service-account JSON keys.
- **Raw is immutable.** Never mutate or delete anything under `raw/`. All models are
  recomputable from it.
- **The NL→SQL agent only ever sees the gold schema in Postgres, through `agent_ro`.**
  It must never be pointed at the lake or given write access. The same boundary binds
  the semantic layer and the MCP server — `agent_ro` is the only path out to a model,
  including for callers bringing their own agent (#13, #14).
- **Nothing but GCS in the ingestion write path.** No Neon, no DuckLake, and *no
  validation* before the write — the logger fetches bytes and stores bytes. Contracts
  live at M3, downstream of raw, so a feed schema change breaks a re-runnable batch job
  and never the archive (#15).
- **No agent in the ingestion path.** Ingestion and diffing are deterministic.
- **Pin exact model versions** in `models.yaml`. Never use `-latest` aliases — evals
  become meaningless if the model changes underneath them.
- **Evals decide the model, not intuition.** Write the golden set before tuning.
- Do not add Kafka, Kubernetes, a vector DB, or fine-tuning. See `docs/decisions.md` #11.

## Data rules

These come from analysing real feed snapshots (`docs/data-notes.md`). They are not
theoretical — each one corresponds to a defect present in the live data.

- Filter `publish == false` (41 locations).
- Grain is `(location_id, evse_uid)` — **not** `evse_uid` alone. 256 uids appear in two
  locations, 69 with conflicting status.
- Outer join static↔dynamic; orphans go to a quarantine table. The feeds disagree.
- Ignore `status` in the static file. Only the dynamic feed's status counts.
- `state` is a garbage field (contains values like `"Good state"`). Never map it to region.
- Normalise city names Greek→Latin before any grouping. `Athens` / `Αθήνα` / `Athina`
  are the same city.
- **Never compare uptime across operators without normalising for AC/DC.** DC share ranges
  from 0% to 70% by operator and DC hardware fails more often.
- `last_updated` is not a reliable change signal — some operators bulk-stamp it. Detect
  transitions by diffing snapshots.

From M4 these rules stop being conventions and become code: the AC/DC normalisation, the
`(location_id, evse_uid)` grain and the `publish` filter are encoded once in the semantic
layer's metric definitions, and every agent answers through those rather than re-deriving
them (#13).

## Conventions

- Python 3.12+, managed with `uv`. Ruff for lint and format.
- Type hints everywhere. Pydantic models for anything crossing a boundary.
- Tests with pytest. Every data rule above gets a test with a real fixture.
- **Commits:** conventional subject, ≤72 chars. Body optional, max 3 lines, only the
  why. No trailers.
- **Language:** chat with me in Greek. Everything in the repo — code, comments, docs,
  commit messages — stays in English.
- Keep this file lean. Detail belongs in `docs/`.
