"""End-to-end tests of the service with no network and no GCP: the upstream is an
`httpx.MockTransport`, the bucket is a fake recording every upload."""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import GoogleAPIError, PreconditionFailed

import chargewatch.logger.app as app_module
from chargewatch.logger.app import app, get_settings, get_transport
from chargewatch.logger.settings import Settings

PAYLOAD = b"PK\x03\x04not-really-a-zip"
DYNAMIC_URL = "https://feed.test/dynamic.json.zip"
STATIC_URL = "https://feed.test/static.json.zip"
SLOT_HEADER = {"X-CloudScheduler-ScheduleTime": "2026-09-22T10:47:12Z"}
EXPECTED_NAME = "raw/dynamic/dt=2026-09-22/20260922T1040Z.json.zip"


class FakeBlob:
    def __init__(self, bucket: "FakeBucket", name: str) -> None:
        self.bucket = bucket
        self.name = name
        self.metadata: dict[str, str] | None = None

    def upload_from_string(self, data: bytes, content_type: str, if_generation_match: int) -> None:
        self.bucket.uploads.append(
            {
                "name": self.name,
                "data": data,
                "content_type": content_type,
                "if_generation_match": if_generation_match,
                "metadata": self.metadata,
            }
        )
        if self.bucket.raises is not None:
            raise self.bucket.raises


class FakeBucket:
    def __init__(self, raises: Exception | None = None) -> None:
        self.uploads: list[dict] = []
        self.raises = raises

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)


def upstream(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def raising(exc: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


def ok_upstream(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        content=PAYLOAD,
        headers={"ETag": '"abc123"', "Last-Modified": "Tue, 22 Sep 2026 10:41:00 GMT"},
    )


@pytest.fixture
def bucket() -> FakeBucket:
    return FakeBucket()


@pytest.fixture
def client(bucket: FakeBucket, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(
        gcs_bucket="test-bucket",
        feed_url_dynamic=DYNAMIC_URL,
        feed_url_static=STATIC_URL,
        fetch_timeout_s=1,
    )
    app.dependency_overrides[get_transport] = lambda: upstream(ok_upstream)
    monkeypatch.setattr(app_module, "get_bucket", lambda: bucket)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def set_upstream(handler) -> None:
    app.dependency_overrides[get_transport] = lambda: upstream(handler)


def log_lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]


def test_healthz(client: TestClient):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stores_object_with_name_content_type_and_metadata(client, bucket, capsys):
    response = client.post("/run?feed=dynamic", headers=SLOT_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["feed"] == "dynamic"
    assert body["object"] == EXPECTED_NAME
    assert body["bytes"] == len(PAYLOAD)
    assert body["created"] is True
    assert isinstance(body["duration_ms"], int)

    assert len(bucket.uploads) == 1
    upload = bucket.uploads[0]
    assert upload["name"] == EXPECTED_NAME
    assert upload["data"] == PAYLOAD
    assert upload["content_type"] == "application/zip"
    assert upload["if_generation_match"] == 0
    metadata = upload["metadata"]
    assert metadata["source-url"] == DYNAMIC_URL
    assert metadata["schedule-time"] == SLOT_HEADER["X-CloudScheduler-ScheduleTime"]
    assert metadata["upstream-etag"] == '"abc123"'
    assert metadata["upstream-last-modified"] == "Tue, 22 Sep 2026 10:41:00 GMT"
    assert metadata["fetched-at"].endswith("+00:00")

    lines = log_lines(capsys)
    assert lines == [{**body, "event": "snapshot"}]


def test_static_feed_uses_its_own_url_and_prefix(client, bucket):
    response = client.post("/run?feed=static", headers=SLOT_HEADER)

    assert response.status_code == 200
    assert response.json()["object"] == "raw/static/dt=2026-09-22/20260922T1040Z.json.zip"
    assert bucket.uploads[0]["metadata"]["source-url"] == STATIC_URL


def test_missing_upstream_headers_become_empty_strings(client, bucket):
    set_upstream(lambda request: httpx.Response(200, content=PAYLOAD))

    response = client.post("/run?feed=dynamic")

    assert response.status_code == 200
    metadata = bucket.uploads[0]["metadata"]
    assert metadata["upstream-etag"] == ""
    assert metadata["upstream-last-modified"] == ""
    assert metadata["schedule-time"] == ""


def test_existing_object_is_not_overwritten(client, bucket, capsys):
    bucket.raises = PreconditionFailed("object exists")

    response = client.post("/run?feed=dynamic", headers=SLOT_HEADER)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert response.json()["object"] == EXPECTED_NAME
    assert len(bucket.uploads) == 1
    assert log_lines(capsys)[0]["event"] == "snapshot"


@pytest.mark.parametrize(
    ("handler", "error_fragment"),
    [
        (lambda request: httpx.Response(500, content=b"boom"), "upstream status 500"),
        (lambda request: httpx.Response(200, content=b""), "0 bytes"),
        (raising(httpx.ReadTimeout("read timed out")), "ReadTimeout"),
        (raising(httpx.ConnectError("refused")), "ConnectError"),
    ],
    ids=["upstream-500", "empty-body", "timeout", "connection-error"],
)
def test_fetch_failures_are_502_and_never_upload(client, bucket, capsys, handler, error_fragment):
    set_upstream(handler)

    response = client.post("/run?feed=dynamic", headers=SLOT_HEADER)

    assert response.status_code == 502
    body = response.json()
    assert body["feed"] == "dynamic"
    assert body["stage"] == "fetch"
    assert error_fragment in body["error"]
    assert bucket.uploads == []
    assert log_lines(capsys) == [{**body, "event": "snapshot_failed"}]


def test_gcs_error_is_500(client, bucket, capsys):
    bucket.raises = GoogleAPIError("gcs down")

    response = client.post("/run?feed=dynamic", headers=SLOT_HEADER)

    assert response.status_code == 500
    body = response.json()
    assert body["feed"] == "dynamic"
    assert body["stage"] == "store"
    assert "gcs down" in body["error"]
    assert log_lines(capsys) == [{**body, "event": "snapshot_failed"}]


@pytest.mark.parametrize("query", ["?feed=other", ""], ids=["unknown-feed", "missing-feed"])
def test_bad_feed_is_400(client, bucket, query):
    response = client.post(f"/run{query}")

    assert response.status_code == 400
    assert bucket.uploads == []


def test_no_payload_bytes_are_logged(client, capsys):
    client.post("/run?feed=dynamic", headers=SLOT_HEADER)

    assert "not-really-a-zip" not in capsys.readouterr().out
