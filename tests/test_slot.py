from datetime import UTC, datetime

from chargewatch.logger.slot import object_name, slot_time


def test_header_is_floored_to_ten_minutes():
    assert slot_time("2026-09-22T10:47:12Z") == datetime(2026, 9, 22, 10, 40, tzinfo=UTC)


def test_exact_boundary_is_unchanged():
    assert slot_time("2026-09-22T10:40:00Z") == datetime(2026, 9, 22, 10, 40, tzinfo=UTC)


def test_non_utc_offset_is_converted():
    # 12:47 at +02:00 is 10:47Z -> 10:40Z
    assert slot_time("2026-09-22T12:47:12+02:00") == datetime(2026, 9, 22, 10, 40, tzinfo=UTC)


def test_offset_crossing_midnight_changes_the_date():
    assert slot_time("2026-09-23T01:05:00+03:00") == datetime(2026, 9, 22, 22, 0, tzinfo=UTC)


def test_missing_header_falls_back_to_now():
    before = datetime.now(UTC)
    slot = slot_time(None)
    after = datetime.now(UTC)
    assert slot.tzinfo is UTC
    assert slot.minute % 10 == 0 and slot.second == 0 and slot.microsecond == 0
    floored_before = before.replace(
        minute=before.minute - before.minute % 10, second=0, microsecond=0
    )
    assert floored_before <= slot <= after


def test_empty_or_garbage_header_falls_back_to_now():
    for header in ("", "not-a-date"):
        slot = slot_time(header)
        assert slot.tzinfo is UTC
        assert (datetime.now(UTC) - slot).total_seconds() < 600


def test_object_name_dynamic():
    slot = datetime(2026, 9, 22, 10, 40, tzinfo=UTC)
    assert object_name("dynamic", slot) == "raw/dynamic/dt=2026-09-22/20260922T1040Z.json.zip"


def test_object_name_static():
    slot = datetime(2026, 9, 22, 3, 0, tzinfo=UTC)
    assert object_name("static", slot) == "raw/static/dt=2026-09-22/20260922T0300Z.json.zip"


def test_object_name_honours_prefix():
    slot = datetime(2026, 9, 22, 10, 40, tzinfo=UTC)
    assert object_name("dynamic", slot, prefix="smoke") == (
        "smoke/dynamic/dt=2026-09-22/20260922T1040Z.json.zip"
    )
