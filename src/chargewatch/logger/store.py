"""Store bytes in GCS, create-if-absent. Raw is never overwritten."""

from typing import Any

from google.api_core.exceptions import PreconditionFailed

CONTENT_TYPE = "application/zip"


def store(bucket: Any, name: str, body: bytes, metadata: dict[str, str]) -> bool:
    """Upload `body` to `name` unless an object already exists there.

    Returns True when the object was created, False when the slot was already taken
    (GCS 412). Any other error propagates.
    """
    blob = bucket.blob(name)
    blob.metadata = metadata
    try:
        blob.upload_from_string(body, content_type=CONTENT_TYPE, if_generation_match=0)
    except PreconditionFailed:
        return False
    return True
