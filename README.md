# ChargeWatch GR

Agentic analytics over Greek EV-charging open data — uptime, reliability and pricing
across ~4,250 charging locations and ~9,900 charge points, built from a feed that
publishes only a live snapshot and keeps no history.

*Work in progress. Started September 2026.*

## Why

The Μ.Υ.Φ.Α.Η. registry publishes charge-point status every 10 minutes and a static
inventory daily, both as open OCPI data. Neither is archived by anyone. This project
captures that stream and turns it into the history that does not otherwise exist, then
uses it to answer questions the feed alone cannot: how reliable is each operator's
network, how much of it is actually reporting, and what does charging cost relative to
wholesale power.

Analysis of a single live snapshot already shows why the raw feed is not enough — **over
a third of the national network reports a status more than a day old**, and some
operators stamp every record with the same timestamp. See `docs/data-notes.md`.

## Architecture

```
Cloud Scheduler ──(every 10 min)──→ Cloud Run Service
                                          │
                        fetch → validate → raw to GCS (immutable)
                                          │
                        DuckDB ATTACH DuckLake (catalog: Neon Postgres)
                                          │
                              Polars: diff vs current state
                                          │
                                  write transitions
                                          ↓
                        SQLMesh: silver → gold ──→ Neon (gold schema)
                                                        ↑
                                       dashboard + NL→SQL agent (read-only)
```

## Docs

| File | Contents |
|---|---|
| `CLAUDE.md` | Working context and hard rules |
| `docs/decisions.md` | Every locked technical choice with its reason |
| `docs/data-notes.md` | Measured findings from both feeds |
| `docs/roadmap.md` | 10-week plan and the business thesis |

## Setup

Manual prerequisites and the full script are in `scripts/setup-gcp.sh`.

## Data source

Ministry of Infrastructure & Transport, Μ.Υ.Φ.Α.Η. registry —
[public open data](https://electrokinisi.yme.gov.gr/public/HelpMyfah/PublicData/).
Wholesale electricity prices from the ENTSO-E Transparency Platform.
