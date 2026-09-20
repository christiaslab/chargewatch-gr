# Roadmap

10 weeks at ~5-8 hours/week. Two items are deliberately placed.

| Week | Goal | Deliverable |
|---|---|---|
| **1** | **Logger live** | Cloud Run + Scheduler every 10 min, raw → GCS. *The archive starts here.* |
| 2 | Bronze + first public artifact | Daily Parquet batching; **operator data-quality scorecard** |
| 3 | Silver — transitions | CDC / SCD-2 model. The technical highlight. |
| 4 | Gold marts | dbt-equivalent in SQLMesh: uptime by EVSE / operator / region, AC-DC normalised |
| 5 | **First report, written by hand** | Validates the story before automating it. First LinkedIn post. |
| 6-7 | NL→SQL agent + evals | Agent, golden set of 50, CI regression |
| 8 | Anomaly investigator | Multi-step agent with Langfuse tracing |
| 9 | Report agent + observability | Automates week 5 |
| 10 | Public dashboard + launch | README with architecture, eval-accuracy chart, launch post |

**Week 1 is the logger, not the design.** Every week of delay is data that will never
exist. An imperfect logger writing plain JSON to a bucket beats a perfect design that
starts next month.

**Week 2 ships something publishable.** The operator data-quality scorecard is computable
from a *single* snapshot — no history required. It is regulatory-relevant (AFIR requires
accurate data) and nobody else publishes it. This exists so there is an external result
in week 2 rather than week 5.

**Week 5 is manual on purpose.** If you cannot write an interesting report from the data
yourself, the agent certainly cannot — and it is better to learn that in week 5 than in
week 9.

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
| 3 | Month 12+ | Paid API over the archive | Needs 12 months of history first |

Phase 1 is the engine: the same weekly report is simultaneously portfolio proof, content,
and lead generation.

## Open risks

| Risk | How it surfaces |
|---|---|
| Feed terms of use are unstated | Email `dteo@yme.gov.gr` before any commercial phase |
| Feed schema will change | Validator fails → DuckLake schema evolution earns its place |
| Claude model availability in `europe-west1` | Check before week 8 |
| Run time > 60s pushes out of free tier | First week in production |
| Losing interest midway | Mitigated by shipping publicly in week 2, not week 10 |
