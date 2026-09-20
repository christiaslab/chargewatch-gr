# Decision record

Every locked choice, with the reason and what would reverse it. Add an entry rather than
silently changing a line above.

*Locked 2026-09-19/20.*

---

### 1. GCP, not AWS
Since July 2025 the AWS Free Plan **closes the account after 6 months** and deletes
resources. GCP's Always Free tier does not expire and the account survives credit
expiry. For a portfolio project that must stay live indefinitely, this is decisive.

*Reverses if:* nothing foreseeable.

### 2. Cloud Run **Service**, not Job
The always-free allowance is request-based and applies to Services. Jobs bill
differently and do not benefit. Estimated load: 144 runs/day × ~15s × 1 vCPU ≈ 65,000
vCPU-sec/month against 180,000 free.

*Reverses if:* a single run exceeds ~60s, at which point revisit.

### 3. DuckLake v1.0 as the lake format
DuckDB alone is single-writer and file-based, which breaks in a stateless runtime — a
problem already hit on another project. DuckLake puts the catalog in Postgres and data
in object storage, giving ACID, snapshots/time travel, schema evolution and safe
concurrent access. Reached v1.0 April 2026.

Supersedes an earlier plan to add Apache Iceberg later — DuckLake provides the same
lakehouse properties with far less machinery.

*Reverses if:* Spark/Trino interop becomes necessary → Iceberg.

*Known caveats:* deletion vectors are still experimental; smaller ecosystem than Iceberg.

### 4. Catalog in Neon Postgres
DuckLake requires a catalog database. Neon is free, scales to zero, and the same
instance also serves the gold schema.

### 5. Raw in GCS, never deleted
Single source of truth. Every model is recomputable from raw. Volume is ~35 GB/year
gzipped; a lifecycle rule moves objects to Coldline after 30 days.

### 6. Only transitions in the lake, not every snapshot
Raw volume is 3.75 GB/day (26 MB × 144 snapshots). Storing every snapshot as rows
would be ~525M rows/year for data that barely changes. Storing state transitions is
50-100× smaller and is the correct model for uptime analytics, which needs durations
rather than samples.

This is SCD Type 2 applied to a streaming snapshot feed.

### 7. Gold served from plain Postgres
The NL→SQL agent needs a small, stable, well-named schema and a hard read-only
boundary. A Postgres role gives that cleanly. Pointing an LLM at the whole lake is both
unsafe and bad for accuracy.

### 8. Polars for diffing, SQLMesh for models
The diff is a ~10,000-row set comparison every 10 minutes — Polars is ideal.
SQLMesh's `incremental_by_time_range` is built for time-partitioned feeds; in dbt the
same behaviour is hand-rolled. SQLMesh also brings column-level lineage and virtual
data environments, which pair well with Neon branches.

### 9. All models via Vertex AI
Vertex Model Garden serves both Gemini and Claude, so one auth, one billing, one SDK.

*Open item:* confirm Claude model availability in `europe-west1` before building the
anomaly agent. Gemini is available there, so setup was not blocked.

### 10. Flash-Lite for NL→SQL, Sonnet for the rest
The frequently-run agent is the cheap one; the expensive agents run rarely (the report
writer ~4×/month). Cost optimisation therefore only matters for NL→SQL.

*Reverses if:* eval accuracy on the golden set falls below ~85% → step up a tier, and
keep the chart that shows why.

### 11. No Kafka, Kubernetes, vector DB, or fine-tuning
A 10-minute feed needs a cron, not a streaming platform. One container needs Cloud Run,
not an orchestrator. The data is tabular, so RAG adds nothing. Over-engineering is a
negative signal in senior review.

*Reverses if:* AFIR regulatory texts are added as a corpus → then RAG earns its place.

### 12. Shell scripts now, OpenTofu later
IaC is the right end state and a good CV line, but costs roughly a week for zero benefit
while there is one environment.

*Reverses if:* a second environment (staging) is needed. That is the trigger — at which
point it solves a real problem and makes a better story.
