"""Runtime configuration, read from the environment. No secrets live here."""

from pydantic_settings import BaseSettings, SettingsConfigDict

_FEED_BASE = "https://electrokinisi.yme.gov.gr/public/static_files"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    gcs_bucket: str
    raw_prefix: str = "raw"
    feed_url_dynamic: str = f"{_FEED_BASE}/GR.IDRO.dynamic.data.latest.json.zip"
    feed_url_static: str = f"{_FEED_BASE}/GR.IDRO.static.data.latest.json.zip"
    fetch_timeout_s: float = 45
    port: int = 8080

    def feed_url(self, feed: str) -> str:
        return {"dynamic": self.feed_url_dynamic, "static": self.feed_url_static}[feed]
