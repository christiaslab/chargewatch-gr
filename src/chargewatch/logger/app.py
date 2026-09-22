"""Cloud Run service: fetch one feed file and store the bytes unchanged in GCS.

Nothing but GCS in the write path. No retries here — any non-2xx makes Cloud
Scheduler retry, and the object name depends only on the slot, so a retry is a
no-op for a slot that already landed.
"""

import json
import sys
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from chargewatch.logger.fetch import fetch
from chargewatch.logger.settings import Settings
from chargewatch.logger.slot import object_name, slot_time
from chargewatch.logger.store import store

FEEDS = ("dynamic", "static")
SCHEDULE_TIME_HEADER = "X-CloudScheduler-ScheduleTime"

app = FastAPI(title="chargewatch-logger", docs_url=None, redoc_url=None)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_bucket() -> Any:
    """Built on first use, inside the store stage, so a credentials problem surfaces
    as a `stage: store` failure and never blocks the 400/fetch paths. Tests replace
    this function with one returning a fake bucket."""
    from google.cloud import storage

    return storage.Client().bucket(get_settings().gcs_bucket)


def get_transport() -> httpx.BaseTransport | None:
    """Override point for tests (`httpx.MockTransport`); None means the real network."""
    return None


def log_event(event: str, payload: dict[str, Any]) -> None:
    """One JSON line per run on stdout; Cloud Run ingests it as a structured entry."""
    sys.stdout.write(json.dumps({**payload, "event": event}) + "\n")
    sys.stdout.flush()


def _failed(feed: str, stage: str, error: str, status: int) -> JSONResponse:
    body = {"feed": feed, "stage": stage, "error": error}
    log_event("snapshot_failed", body)
    return JSONResponse(body, status_code=status)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
def run(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    transport: Annotated[httpx.BaseTransport | None, Depends(get_transport)],
    feed: str | None = None,
) -> JSONResponse:
    if feed not in FEEDS:
        return JSONResponse({"error": f"feed must be one of {', '.join(FEEDS)}"}, status_code=400)

    started = time.monotonic()
    schedule_time = request.headers.get(SCHEDULE_TIME_HEADER, "")
    name = object_name(feed, slot_time(schedule_time or None), prefix=settings.raw_prefix)
    url = settings.feed_url(feed)

    try:
        result = fetch(url, settings.fetch_timeout_s, transport=transport)
    except Exception as exc:  # every fetch failure must be a 502, whatever raised it
        return _failed(feed, "fetch", f"{type(exc).__name__}: {exc}", 502)
    if not result.ok:
        error = f"upstream status {result.status}, {len(result.body)} bytes"
        return _failed(feed, "fetch", error, 502)

    metadata = {
        "source-url": url,
        "fetched-at": datetime.now(UTC).isoformat(timespec="seconds"),
        "schedule-time": schedule_time,
        "upstream-etag": result.etag,
        "upstream-last-modified": result.last_modified,
    }
    try:
        created = store(get_bucket(), name, result.body, metadata)
    except Exception as exc:  # every store failure must be a 500, whatever raised it
        return _failed(feed, "store", f"{type(exc).__name__}: {exc}", 500)

    body = {
        "feed": feed,
        "object": name,
        "bytes": len(result.body),
        "created": created,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    log_event("snapshot", body)
    return JSONResponse(body, status_code=200)
