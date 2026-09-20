# Data notes

Findings from analysing real snapshots of both feeds, 2026-09-19. Every claim here was
measured, not assumed. These findings are the reason for the data rules in `CLAUDE.md`
and for much of the product thesis.

## Sources

| Feed | URL | Cadence |
|---|---|---|
| Dynamic | `https://electrokinisi.yme.gov.gr/public/static_files/GR.IDRO.dynamic.data.latest.json.zip` | every 10 min |
| Static | `https://electrokinisi.yme.gov.gr/public/static_files/GR.IDRO.static.data.latest.json.zip` | daily |

Docs: `https://electrokinisi.yme.gov.gr/public/HelpMyfah/PublicData/`
No stated licence or rate limit. Contact: `dteo@yme.gov.gr`.

Both files are UTF-8 **with BOM** — parse with `utf-8-sig`.

## Format

The payload is **OCPI** (Open Charge Point Interface), the EU standard: `country_code`,
`party_id`, `evses[]`, `evse_id`, `status`, `connectors[]`. This matters strategically —
the parser generalises to any AFIR-compliant National Access Point in the EU, not just
Greece.

Top level: `{"Locations": [...], "status": "ok", "statusDesc": "success"}`

## Scale (2026-09-19 snapshot)

| | Dynamic | Static |
|---|---|---|
| Locations | 4,252 | 4,251 |
| EVSEs | 9,940 (9,662 distinct uid) | 9,939 |
| Connectors | 10,198 | 10,197 |
| Operators (`party_id`) | 35 | — |
| Size | 26 MB raw / 644 KB gzip | 38 MB raw |

Projected raw volume: **3.75 GB/day, 1.37 TB/year** uncompressed; ~93 MB/day,
~34 GB/year gzipped.

## Finding 1 — status is widely stale

`last_updated` spans **2024-02-27 → 2026-09-19 (935 days)** in a feed advertised as
real-time.

| Age of record | Share of EVSEs |
|---|---|
| < 1 hour | 28.2% |
| 1-6 hours | 25.8% |
| 6-24 hours | 10.2% |
| 1-7 days | 17.9% |
| 7-30 days | 11.4% |
| > 30 days | 6.6% |

**Over a third of the national network reports a status older than one day.** Any app
showing this as "available now" is misleading drivers without knowing it.

Per operator (EVSE count, median age, p90 age):

| Operator | EVSEs | Median | p90 |
|---|---|---|---|
| PPC | 3,539 | 1.0 h | 2.1 h |
| EMU | 293 | 9.6 h | 143 h |
| JLT | 573 | 24.7 h | 247 h |
| HEC | 705 | 31.8 h | 514 h |
| NRG | 2,161 | 51.3 h | **647 h (27 d)** |
| WAV | 982 | 57.2 h | 395 h |
| BLK | 501 | 77.4 h | **8,793 h (366 d)** |
| FRZ | 136 | 178.7 h | 6,866 h |

PPC runs a genuine real-time feed. NRG — the second largest — has a two-day median.

## Finding 2 — some operators bulk-stamp `last_updated`

Distinct timestamp values per operator:

| Operator | EVSEs | Distinct ts | Reading |
|---|---|---|---|
| NRG | 2,161 | 2,160 | genuine per-EVSE |
| BLK | 501 | 498 | genuine |
| PPC | 3,539 | 797 | partly batched |
| **LDL** | **235** | **2** | 226 share one timestamp |
| 7X3 | 50 | 10 | bulk-stamped |

LDL writes `last_updated` = *when I pushed the file*, not *when the status changed*.

**Consequence:** `last_updated` cannot be used as a change signal. Transitions must be
detected by diffing consecutive snapshots — which is precisely why an independently
captured archive is more valuable than the feed itself.

## Finding 3 — tariffs are present, coverage is bimodal

`connectors[].\_openapiTariffs` carries full OCPI pricing with component types
`ENERGY`, `TIME`, `FLAT`, `PARKING_TIME`.

```json
{"currency":"EUR","type":"DEFAULT","elements":[
  {"price_components":[{"type":"ENERGY","price":"0.4","step_size":1}]}]}
```

Observed energy prices: 0.41 / 0.42 / 0.43 / 0.45 / 0.50 / 0.54 / 0.56 €/kWh.

| ~96-100% coverage | ~0% coverage |
|---|---|
| NRG, WAV, HEC, EMU, EVR, EVZ, FYS, 7X3 | PPC (0.3%), JLT (0.2%), BLK, LDL, ELE, OPM |

Roughly half the market by connector count yields a national retail charging price
series. Combined with ENTSO-E wholesale prices this gives a retail-vs-wholesale margin
index that nobody currently publishes.

## Finding 4 — duplicate EVSEs with conflicting status

**256 uids appear in two locations; 69 of those disagree on status.** 259 locations
affected.

```
GR-PPC-E0000002033-2
  loc Scs32624-L | G304 AB Perissos | CHARGING  | ts 2026-02-19   <- zombie, frozen 7 months
  loc Scs42741-L | G304 AB Perissos | AVAILABLE | ts 2026-09-19   <- live
```

Same charger, same name, two location ids — one was migrated and the old record was
never removed. This is an entity-resolution problem the upstream registry has not solved.

## Finding 5 — the static file adds the physical picture

| Power band | Connectors | Share |
|---|---|---|
| ≤ 7.4 kW | 137 | 1.3% |
| **7.4-22 kW** | **7,389** | **72.5%** |
| 22-50 kW | 1,041 | 10.2% |
| 50-150 kW | 1,094 | 10.7% |
| > 150 kW | 480 | 4.7% |

Median 22 kW, max 500 kW. Standards: T2 75%, CCS 22%, CHAdeMO 2.6%.
Power types: AC_3_PHASE 6,926 · DC 2,528 · AC_1_PHASE 743 → **only 24.8% DC**.

DC share by operator, which is why uptime comparisons must be normalised:

| Operator | Connectors | DC % |
|---|---|---|
| ELE | 232 | 70.3% |
| LDL | 235 | 68.5% |
| HEC | 756 | 64.8% |
| JLT | 575 | 26.3% |
| NRG | 2,167 | 25.0% |
| PPC | 3,576 | 21.8% |
| BLK | 629 | 1.3% |
| OPM / 7X3 / FYS | 172 | 0% |

DC hardware fails materially more often than AC. Without this dimension, BLK looks
unfairly good and HEC unfairly bad.

## Finding 6 — assorted defects the validator must catch

- **The two feeds disagree on membership.** One location exists only in dynamic:
  `GR-EMU-S3939835635845136110736419-L`. Use an outer join with a quarantine table.
- `publish: false` on **41 locations** — must be filtered.
- `parking_type` missing on **32%**.
- `state` contains junk such as `"Good state"` instead of a region.
- City names are inconsistent across two alphabets: `Athens` 99, `Αθήνα` 42,
  `Athina` 33; `Thessaloniki` 61, `ΘΕΣΣΑΛΟΝΙΚΗ` 28. Needs Greek→Latin normalisation
  and a crosswalk to ELSTAT regions.
- `energy_mix` present on **1,617 locations** — renewable share per site. Keep it; it
  is a future "green charging" angle.
- The static file also carries `status`, but at daily freshness. **Ignore it entirely.**
- All 4,251 static coordinates parse and fall inside Greece. No cleaning needed there.

## Join key

`(location_id, evse_uid)` — covers 9,939 of 9,940. Never `evse_uid` alone, per Finding 4.

## Second source: ENTSO-E

Greek bidding zone EIC `10YGR-HTSO-----Y`. Free token by email
(`transparency@entsoe.eu`, subject "RESTful API access"). Document types: A44 day-ahead
prices, A65 load, A75 generation.

Two traps, both documented and both worth writing about:

1. **The day-ahead auction moved to 15-minute products during 2025.** Granularity must
   be detected per chunk, not assumed.
2. **Run-length compression:** when consecutive intervals clear at the same price, only
   the first is sent. Without forward-filling, a reported daily average was **11% too
   high**.

Also note: errors arrive as HTTP 200 with an `Acknowledgement_MarketDocument` body.
