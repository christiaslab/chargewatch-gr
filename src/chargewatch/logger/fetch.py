"""Fetch one feed file. Bytes in, bytes out — nothing is inspected."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class FetchResult:
    body: bytes
    etag: str
    last_modified: str
    status: int

    @property
    def ok(self) -> bool:
        return self.status == 200 and len(self.body) > 0


def fetch(url: str, timeout: float, *, transport: httpx.BaseTransport | None = None) -> FetchResult:
    """GET `url` with a single timeout applied to every phase. Follows redirects,
    sends no conditional headers (a 304 would be a gap in the archive).

    Transport errors (timeout, connection refused, ...) propagate as `httpx.HTTPError`;
    a non-200 status is returned, not raised.
    """
    with httpx.Client(timeout=timeout, follow_redirects=True, transport=transport) as client:
        response = client.get(url)
    return FetchResult(
        body=response.content,
        etag=response.headers.get("etag", ""),
        last_modified=response.headers.get("last-modified", ""),
        status=response.status_code,
    )
