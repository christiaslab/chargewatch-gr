# M1 — Logger spec

Decisions taken 2026-09-22. Implements the M1 definition of done in `docs/roadmap.md`
and decision #15. The builder implements exactly this; anything not written here is out
of scope. Read `CLAUDE.md` first — its hard rules bind every line below.

## 1. Goal

A Cloud Run Service that, when invoked by Cloud Scheduler, fetches one feed file and
stores the bytes unchanged in GCS under an idempotent, timestamp-derived name. Nothing
else. It runs every 10 minutes for the dynamic feed and once a day for the static feed,
and an alert fires when it goes silent.

## 2. Scope

**In:** the service, its tests, the Dockerfile, `scripts/deploy.sh`, amendments to
`scripts/setup-gcp.sh`, the alert policy, and the doc corrections in §9.

**Out:** unzipping, parsing, validating or inspecting the payload; Neon, DuckLake,
Secret Manager; ENTSO-E; in-process retries; error-rate alerts; any model.

## 3. Behaviour

### 3.1 Endpoints

| Route | Caller | Behaviour |
|---|---|---|
| `POST /run?feed=dynamic\|static` | Cloud Scheduler (OIDC) | fetch → store → respond. `feed` is required; unknown value → 400. |
| `GET /healthz` | Cloud Run / humans | `200 {"status":"ok"}`. No I/O. |

### 3.2 Slot and object name

- Slot time = `X-CloudScheduler-ScheduleTime` header (RFC 3339) if present, else
  `now(UTC)`. Convert to UTC, floor to the 10-minute boundary.
- Object name: `raw/<feed>/dt=YYYY-MM-DD/YYYYMMDDTHHMMZ.json.zip`, e.g.
  `raw/dynamic/dt=2026-09-22/20260922T1040Z.json.zip`. Same rule for both feeds.
- The name depends only on the slot, so a Scheduler retry targets the same object.

### 3.3 Fetch

- `httpx.Client`, total timeout 45 s (`FETCH_TIMEOUT_S`), follow redirects, no
  conditional headers (a 304 would be a gap).
- Success = HTTP 200 **and** `len(body) > 0`. Nothing else is checked — not the zip
  magic, not the content type. Bytes in, bytes out.

### 3.4 Store

- `google-cloud-storage`, `blob.upload_from_string(body, content_type="application/zip",
  if_generation_match=0)`.
- `PreconditionFailed` (412) means the slot already has an object: treat as success with
  `created=false`. Raw is never overwritten.
- Object metadata: `source-url`, `fetched-at` (ISO 8601 UTC), `schedule-time` (the raw
  header value or `""`), `upstream-etag`, `upstream-last-modified` (empty string when the
  upstream header is absent).

### 3.5 Responses

| Outcome | Status | Body |
|---|---|---|
| stored, or already present | 200 | `{"feed","object","bytes","created","duration_ms"}` |
| upstream non-200, empty body, timeout, connection error | 502 | `{"feed","stage":"fetch","error"}` |
| GCS error other than 412 | 500 | `{"feed","stage":"store","error"}` |

Any non-2xx makes Scheduler retry. There is no in-process retry.

### 3.6 Logging

One JSON line per run on stdout (Cloud Run ingests it): on success the 200 body plus
`"event":"snapshot"`; on failure the error body plus `"event":"snapshot_failed"`. Nothing
else is logged at INFO. No payload contents, ever.

### 3.7 Configuration (env, via `pydantic-settings`)

| Var | Default | Notes |
|---|---|---|
| `GCS_BUCKET` | — | required |
| `RAW_PREFIX` | `raw` | |
| `FEED_URL_DYNAMIC` | `https://electrokinisi.yme.gov.gr/public/static_files/GR.IDRO.dynamic.data.latest.json.zip` | |
| `FEED_URL_STATIC` | `https://electrokinisi.yme.gov.gr/public/static_files/GR.IDRO.static.data.latest.json.zip` | |
| `FETCH_TIMEOUT_S` | `45` | |
| `PORT` | `8080` | set by Cloud Run |

No secrets. No `.env` needed for the deployed service.

## 4. Layout

```
pyproject.toml                # name chargewatch; requires-python >=3.12; ruff + pytest config
uv.lock
Dockerfile                    # python:3.12-slim + uv; uv sync --frozen --no-dev; non-root; uvicorn
.dockerignore
src/chargewatch/__init__.py
src/chargewatch/logger/__init__.py
src/chargewatch/logger/app.py         # FastAPI app: /run, /healthz, JSON logging
src/chargewatch/logger/fetch.py       # fetch(url, timeout) -> FetchResult(body, etag, last_modified, status)
src/chargewatch/logger/store.py       # store(bucket, name, body, metadata) -> created: bool
src/chargewatch/logger/slot.py        # slot_time(header) -> datetime; object_name(feed, slot) -> str
src/chargewatch/logger/settings.py    # Settings(BaseSettings)
tests/test_slot.py
tests/test_run.py
scripts/setup-gcp.sh                  # amended, see §6
scripts/deploy.sh                     # new, see §7
scripts/monitoring/dead-man.json      # alert policy, see §8
```

Runtime dependencies, exactly: `fastapi`, `uvicorn`, `httpx`, `google-cloud-storage`,
`pydantic-settings`. Dev: `pytest`, `ruff`. Nothing else — `grep -i "neon\|duckdb\|psycopg\|polars"
pyproject.toml` must be empty.

## 5. Tests (no network, no GCP)

- `test_slot.py`: header parsed and floored (`10:47:12Z → 10:40`); non-UTC offset
  converted; missing header falls back to now; object name format for both feeds.
- `test_run.py` (FastAPI `TestClient`, `httpx.MockTransport`, a fake bucket object):
  200 upstream → object stored with the right name, content type and metadata, response
  `created=true`; fake raising `PreconditionFailed` → 200 with `created=false` and no
  second upload; upstream 500, empty body, timeout → 502 and no upload attempted; GCS
  `GoogleAPIError` → 500; `feed=other` → 400; `/healthz` → 200.

## 6. `scripts/setup-gcp.sh` amendments (one-off infra, idempotent)

- Enable `monitoring.googleapis.com` in addition to the existing list.
- Runtime SA `chargewatch-run`: bind `roles/storage.objectCreator` on the bucket;
  **remove** `roles/storage.objectAdmin` on the bucket and `roles/aiplatform.user` on the
  project (tolerate "binding not found"). The logger can create objects and nothing else.
- New SA `chargewatch-scheduler`, no project roles. Its `roles/run.invoker` binding is
  service-scoped and lives in `deploy.sh` because the service must exist first.
- Smoke test writes to `gs://${BUCKET}/smoke/`, not under `raw/`. Whatever already sits
  in `raw/smoke/` stays; M2 reads `raw/dynamic/**` and `raw/static/**` only.
- Notification channel: email from `ALERT_EMAIL` env var (required, never hardcoded);
  create if no channel with that address exists. Alert policy from
  `scripts/monitoring/dead-man.json` (§8), created or updated by display name.

## 7. `scripts/deploy.sh` (repeatable; build + service + jobs)

```
gcloud run deploy chargewatch-logger --source . --region europe-west1 \
  --service-account chargewatch-run@… --no-allow-unauthenticated \
  --min-instances 0 --max-instances 1 --concurrency 1 --cpu 1 --memory 256Mi \
  --timeout 120 --set-env-vars GCS_BUCKET=chargewatch-raw-gr
gcloud run services add-iam-policy-binding chargewatch-logger \
  --member serviceAccount:chargewatch-scheduler@… --role roles/run.invoker
```

Two Scheduler jobs, `describe || create` then `update`, both with `--time-zone Etc/UTC
--http-method POST --oidc-service-account-email chargewatch-scheduler@…
--attempt-deadline 120s --max-retry-attempts 3 --min-backoff 30s --max-backoff 120s`:

| Job | Schedule | URI |
|---|---|---|
| `chargewatch-logger-dynamic` | `*/10 * * * *` | `${SERVICE_URL}/run?feed=dynamic` |
| `chargewatch-logger-static` | `5 3 * * *` | `${SERVICE_URL}/run?feed=static` |

The static job is deliberately off the 10-minute grid. Feed phase is unknown; revisit
the dynamic schedule at M2 by comparing max `last_updated` against fetch time.

## 8. Dead-man's switch

Cloud Monitoring alert policy, condition **metric absence**, duration 1800 s, on
`storage.googleapis.com/api/request_count` filtered to
`resource.label.bucket_name="chargewatch-raw-gr"`, `metric.label.method="WriteObject"`,
`metric.label.response_code="OK"`, aligned `ALIGN_SUM` over 600 s. Notification: the email
channel from §6. Zero code in the logger; it measures the write that actually landed.

The `method` label value must be confirmed in Metrics Explorer after the first real
writes before the policy is trusted. Fallback if the GCS metric proves laggy or the label
differs: a log-based counter on `event="snapshot"` with the same absence condition.

## 9. Doc corrections (same change)

- `CLAUDE.md` locked-stack row and `docs/roadmap.md` DoD: "gzip" → "`.json.zip` as
  served". The feed is already zipped; the logger does not re-compress.
- `docs/decisions.md` #15: "a retried run overwrites its own slot" → "a retried run is a
  no-op for its slot (create-if-absent)".
- `README.md` Setup section: mention `scripts/deploy.sh`.

## 10. Order of work and commits

1. `feat(logger): fetch-and-store service with tests` — §3-5, green locally
   (`uv run pytest`, `uv run ruff check`, `uv run ruff format --check`).
2. `chore(gcp): least-privilege SAs, scheduler identity, monitoring` — §6, run it.
3. `chore(gcp): deploy script and scheduler jobs` — §7, run it.
4. `docs: align wording with the M1 logger spec` — §9.
5. Verification (§11), then 48 h hands off.

## 11. Definition of done — verification checklist

Each line maps to the M1 DoD in `docs/roadmap.md`.

- [ ] **Service-account write path proved end to end:** `gcloud scheduler jobs run
      chargewatch-logger-dynamic` → `gcloud storage ls -l gs://chargewatch-raw-gr/raw/dynamic/`
      shows the object. The container holds no other credential.
- [ ] **Idempotency:** `jobs run` twice inside one slot → one object, second run logs
      `created=false`. A retention check: `raw/` object count never decreases.
- [ ] **Retries:** temporarily set `FEED_URL_DYNAMIC` to an unreachable host → Cloud Run
      logs show 502 and Scheduler shows three attempts; restore.
- [ ] **Dead-man's switch, both halves:** pause `chargewatch-logger-dynamic` → email
      within 35 min → resume → incident resolves. The `method` label confirmed (§8).
- [ ] **Write path is GCS only:** dependency grep in §4 empty; no Neon/DuckLake/ENTSO-E
      /model references anywhere under `src/`.
- [ ] **Run time:** Cloud Run request latency p50 < 60 s on day one (decision #2 trigger).
- [ ] **Least privilege:** `chargewatch-run` holds only `objectCreator` on the bucket;
      `chargewatch-scheduler` holds only `run.invoker` on the service.
- [ ] **Budget alert** exists at ~5 €/month gross (already created).
- [ ] **48 h unattended:** `gcloud storage ls gs://chargewatch-raw-gr/raw/dynamic/dt=<day>/ | wc -l`
      = 144 for two consecutive full UTC days; one object per day under `raw/static/`.
