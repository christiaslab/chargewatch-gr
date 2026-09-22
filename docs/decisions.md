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
as served (`.json.zip`); a lifecycle rule moves objects to Coldline after 30 days.

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

---

*#13-15 added 2026-09-21 (CareerOS update). They change the order of work and the shape
of the agent layer; #1-12 above are untouched.*

### 13. Semantic layer: lightweight, no new service
The NL→SQL agent should answer against *metrics*, not tables. "Uptime by operator" has
one correct definition — AC/DC normalised, on the `(location_id, evse_uid)` grain,
`publish == false` excluded — and that definition belongs in one place, versioned, not
re-derived by a model on every question.

Metric and dimension definitions live **in the repo**, over the existing gold schema in
Neon. Permissions stay exactly where #7 put them: the read-only `agent_ro` role. No new
database, no new deployment, no new surface to secure.

Two candidate implementations, to be decided at M4 on evidence:
- **Boring Semantic Layer** — Ibis-based, compiles metrics to SQL, already speaks MCP,
  which makes #14 close to free.
- **Plain YAML definitions + Postgres views** — fewer moving parts, no dependency, but
  MCP exposure is then hand-rolled.

*Rejected:* Cube and similar server-shaped semantic layers. They mean a second
long-running service, its own container, its own cost and its own failure mode, for a
project whose whole cost argument is one Cloud Run service inside the free tier.

*Consequence, and the reason this lands at M4 rather than after the agent:* the NL→SQL
agent (M5) targets metrics, and the golden set of 50 is written **against metric
definitions**. Building the agent first would mean rewriting every eval once the
semantic layer arrived — and evals that get rewritten to match the system stop being
evals (see #10).

*Reverses if:* the metric surface outgrows what a repo of definitions can express —
realistically, multiple consumers needing caching and pre-aggregation. Not before there
are paying consumers.

### 14. MCP server over the semantic layer, in place of the anomaly investigator
The M6 slot previously held a multi-step anomaly-investigation agent. It now holds an
MCP server that exposes the semantic layer to *any* agent.

Reasons:
- **It is near-free once #13 exists.** The semantic layer already resolves a metric
  request to safe SQL under `agent_ro`. MCP is a protocol wrapper over that, not new
  capability — and if the Boring Semantic Layer option wins, it is largely built in.
- **It is the natural shape of Phase 3.** The monetisation ladder's paid-API rung
  assumed a REST API and a dashboard nobody asked for. The realistic version is that
  the customer brings their own agent and points it at this archive. An MCP endpoint
  is that product, and it is also the most legible demonstration of the archive's
  value: the data is the moat, the interface is thin.
- The anomaly investigator needs *months of transitions* before there are anomalies
  worth investigating. It was scheduled before the data to feed it would exist.

The anomaly investigator moves to "later" in the roadmap. Its `anomaly_investigator`
role stays pinned in `models.yaml` — unused, but pinned, so that reviving it does not
start with a model-selection argument.

*Note on #9's open item:* that entry ties the "confirm Claude availability in
`europe-west1`" check to building the anomaly agent. With the anomaly agent deferred,
the first Claude consumer is the **report agent**, so the check must happen before that
instead. #9 itself is left as written.

*Reverses if:* MCP loses adoption as an integration standard, in which case the same
semantic layer gets a thin HTTP API instead — the layer is the asset, the protocol is
not.

### 15. Ingestion isolation and observability belong to M1
Observability was previously one line item late in the plan, bundled with Langfuse. That
conflated two unrelated things: *is the archive still being written* and *what did an
agent cost*. The first is existential and must exist on day one; the second is a nicety
that matters only once agents run.

M1 therefore owns ingestion isolation and ingestion observability:

- **A dead-man's switch.** Cloud Monitoring alerts when no new object has landed in the
  raw prefix for ~30 minutes. The failure mode of a logger is *silence*, not an error —
  a crashed container raises nothing, and nothing is exactly what an error-based alert
  reports. The alert must fire on absence, and must be verified once by pausing the
  Scheduler job and waiting for the email.
- **GCS is the only dependency in the write path.** No Neon, no DuckLake, no validation
  before the write. The logger fetches bytes and stores bytes. This is why contracts sit
  at M3, downstream of raw: when the feed's schema changes — and it will — validation
  fails in a batch job that can be re-run over retained raw data, while ingestion keeps
  capturing. A validator in the write path converts a schema change into permanent data
  loss.
- **Scheduler retries, with idempotent object names** derived from the fetch timestamp,
  so a retried run is a no-op for its slot (create-if-absent) rather than producing a
  duplicate snapshot.
- **A ~5 €/month budget alert on gross spend.** Alert only, never a spend cap: GCP's cap
  enforcement *pauses services*, and a paused logger is permanently lost snapshots. Gross
  rather than net, or trial credits mask all spend until they run out.
- **ENTSO-E is out of scope for M1.** Wholesale prices are backfillable from the
  Transparency Platform at any time. Only the Μ.Υ.Φ.Α.Η. dynamic feed is perishable, and
  M1 should contain nothing that is not perishable.

**M7 keeps only agent tracing and cost** — Langfuse, cost per agent run, eval-accuracy
history. Nothing in M7 watches the logger.

*Reverses if:* nothing. This is the direct application of the project's first rule — when
in doubt, favour keeping the logger running.
