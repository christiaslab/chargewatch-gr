"""Slot time and object naming. The name depends only on the slot, so a retry
targets the same object."""

from datetime import UTC, datetime

SLOT_MINUTES = 10


def slot_time(header: str | None) -> datetime:
    """Return the run's slot: the Scheduler's schedule time if present, else now.

    Always UTC, floored to the 10-minute boundary. A missing or unparseable header
    falls back to now — capturing the snapshot beats rejecting the run.
    """
    parsed: datetime | None = None
    if header:
        try:
            parsed = datetime.fromisoformat(header.strip())
        except ValueError:
            parsed = None
    if parsed is None:
        parsed = datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    utc = parsed.astimezone(UTC)
    return utc.replace(minute=utc.minute - utc.minute % SLOT_MINUTES, second=0, microsecond=0)


def object_name(feed: str, slot: datetime, prefix: str = "raw") -> str:
    """`<prefix>/<feed>/dt=YYYY-MM-DD/YYYYMMDDTHHMMZ.json.zip`."""
    return f"{prefix}/{feed}/dt={slot:%Y-%m-%d}/{slot:%Y%m%dT%H%MZ}.json.zip"
