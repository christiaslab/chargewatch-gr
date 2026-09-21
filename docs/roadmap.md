# Roadmap

Milestones, not weeks. Only M1 carries a date, because only M1 is perishable: the
dynamic feed keeps no history, so every day the logger is not running is data that will
never exist. Everything after M1 can pause and resume with zero data loss. Solo
developer at ~5-8 hours/week — the *order* is the plan; the calendar is not.

*Updated 2026-09-21 (CareerOS update). Supersedes the 10-week plan of 2026-09-19/20.
Decisions #13-15 in `docs/decisions.md` record why the order changed.*

## Order

| # | Milestone | Deliverable |
|---|---|---|
| **M1** | **Ingestion + alerting** | Cloud Run + Scheduler every 10 min, raw → GCS, dead-man's switch. **The only dated item — target date lives in CareerOS.** Definition of done below. |
| — | Operator data-quality scorecard | First public artifact. Computable from a *single* snapshot, no history needed. |
| M2 | Bronze / DuckLake | Daily Parquet batching from raw into DuckLake. |
| M3 | Contracts | Pydantic schemas for both feeds. Validation runs here, downstream of raw — a schema change breaks M3, never M1. |
| — | Transitions (SCD-2) + gold marts | Polars diff → transitions; SQLMesh silver → gold: uptime by EVSE / operator / region, AC-DC normalised. The technical highlight. |
| — | Manual report | First report, written by hand. First LinkedIn post. |
| M4 | Semantic layer | Metric and dimension definitions in the repo, over gold Postgres. Decision #13. |
| M5 | NL→SQL agent + evals | Agent targets metrics, not tables. Golden set of 50 written against metrics; CI regression. |
| M6 | MCP server | Exposes the semantic layer to any agent. Decision #14. |
| — | Report agent | Automates the manual report. |
| M7 | Langfuse / agent cost | Tracing and cost per agent run. Ingestion observability is *not* here — it is in M1. Decision #15. |
| — | Launch | Public dashboard, README with architecture, eval-accuracy chart, launch post. |

### Later

- **Anomaly investigator** — multi-step agent. Its slot went to the MCP server
  (decision #14). Revisit once there are enough months of transitions to contain
  anomalies worth investigating. The `anomaly_investigator` role in `models.yaml` stays
  pinned but unused until then.
- **OpenTofu** — decision #12; trigger is a second environment.

## Pause point

**After M1, everything is resumable with zero data loss.** The archive grows unattended;
every later milestone reads from `raw/` and is recomputable from it (decision #5). The
project can stop for a week or a quarter and pick up where it left off. The only thing
that must never stop is the logger.

## M1 — definition of done

M1 is done when the logger **runs unattended** — not when it runs once.

- **Cloud Run Service + Cloud Scheduler**, every 10 minutes. Each run writes one gzip
  object under `gs://chargewatch-raw-gr/raw/`.
- **Dead-man's switch.** Cloud Monitoring alert: no new object in the raw prefix for
  ~30 minutes → email. The failure mode of a logger is silence, not an error, so the
  alert fires on *absence*. Verify it once by pausing the Scheduler job and waiting for
  the email.
- **GCS is the only dependency in the write path.** No Neon, no DuckLake, no validation
  before the write. The logger fetches bytes and stores bytes. Schema changes break
  downstream (M3 contracts), never ingestion.
- **Scheduler retries** configured. **Object names are idempotent** — derived from the
  fetch timestamp — so a retried run cannot produce a second object for the same slot.
- **Budget alert ~5 €/month** on gross spend. Already created; see the header of
  `scripts/setup-gcp.sh` on why it must track gross.
- **ENTSO-E is out of M1.** Wholesale prices are backfillable from the Transparency
  Platform at any time. Only the Μ.Υ.Φ.Α.Η. dynamic feed is perishable.
- No agent, no model, no Neon anywhere in this milestone.

## Deliberate placements

**M1 is the logger, not the design.** An imperfect logger writing plain gzip to a bucket
beats a perfect design that starts next month. The design work (contracts, lake,
models) all happens *after* the archive has started.

**The scorecard ships right after M1.** The operator data-quality scorecard is
computable from a single snapshot — no history required. It is regulatory-relevant
(AFIR requires accurate data) and nobody else publishes it. It exists so there is an
external result early rather than at launch.

**The manual report comes before the report agent.** If you cannot write an interesting
report from the data yourself, the agent certainly cannot — and it is better to learn
that before building M4-M6 than after.

**The semantic layer comes before the agent.** The NL→SQL agent targets metric
definitions, not raw tables, and the golden set is written against those metrics.
Building the agent first would mean rewriting the evals later (decision #13).

## Business thesis in one paragraph

The asset is the archive, not the code: the dynamic feed is a snapshot, so history only
exists if someone captures it, and the gap widens daily at zero cost. Greece alone is too
small a market (301,297 alternative-fuel vehicles, 3.97% of the fleet) — but the feed
exists because **AFIR obliges every EU member state** to publish the same OCPI data to a
National Access Point, across 1,157,551 public charge points EU-wide. Greece is the
beachhead, not the market.

Monetisation ladder, honestly ranked:

| Phase | When | What | Realism |
|---|---|---|---|
| 1 | Month 3 | Free weekly report → audience, credibility, SEO | **Will happen** |
| 2 | Month 6+ | Consulting: siting / TCO studies for fleets | **Plausible** |
| 3 | Month 12+ | Paid API over the archive — the MCP server (M6) is its first shape | Needs 12 months of history first |

Phase 1 is the engine: the same weekly report is simultaneously portfolio proof, content,
and lead generation.

## Open risks

| Risk | How it surfaces |
|---|---|
| Feed terms of use are unstated | Email `dteo@yme.gov.gr` before any commercial phase |
| Feed schema will change | M3 contracts fail; the logger keeps writing (decision #15). DuckLake schema evolution earns its place |
| Dead-man's switch is itself misconfigured | Only caught by testing it: pause the Scheduler once and wait for the email |
| Claude model availability in `europe-west1` | Check before the report agent — now the first Claude consumer (decision #9) |
| Run time > 60s pushes out of free tier | First days of M1 in production |
| Losing interest midway | Mitigated by shipping publicly at the scorecard, not at launch; and by the pause point — stopping costs nothing after M1 |
