"""M8: end-to-end pipeline on mocked sources → signals in DB + run summary;
twice-run is idempotent at the pipeline level (the Loom moment)."""

from datetime import datetime

import httpx
import respx

from signal_connector.http.cache import ResponseCache
from signal_connector.http.client import HttpClient
from signal_connector.http.ratelimit import PerHostRateLimiter
from signal_connector.models import Location
from signal_connector.pipeline import Pipeline
from signal_connector.sources.ats import GreenhouseSource
from signal_connector.sources.base import CompanyConfig
from signal_connector.sources.feeds import NewsSource
from signal_connector.storage.sqlite_store import SqliteStore
from tests.conftest_data import GREENHOUSE_BODY, NEWS_BODY


def _company():
    return CompanyConfig(
        name="Intercom", slug="intercom", greenhouse="intercom", domain="intercom.com",
        industry="saas", country="US", hq=Location(city="San Francisco", country="US"),
        watch_metros=["Berlin, Germany"],
    )


def _pipeline(tmp_path):
    http = HttpClient(cache=ResponseCache(tmp_path / "c", 3600), limiter=PerHostRateLimiter(0.0))
    store = SqliteStore(":memory:")
    return Pipeline([GreenhouseSource(), NewsSource()], [_company()], store, http=http), store


@respx.mock
def test_end_to_end_and_idempotent(tmp_path):
    respx.get("https://boards-api.greenhouse.io/v1/boards/intercom/jobs").mock(
        return_value=httpx.Response(200, text=GREENHOUSE_BODY)
    )
    respx.get(url__regex=r"https://news\.google\.com/rss/search.*").mock(
        return_value=httpx.Response(200, text=NEWS_BODY)
    )
    pipeline, store = _pipeline(tmp_path)

    s1 = pipeline.run(now=datetime(2026, 6, 17))
    assert s1["emitted_signals"] == 1
    assert s1["new"] == 1
    assert store.signal_count() == 1
    sig = store.all_signals()[0]
    assert sig.companyName == "Intercom"
    assert sig.verificationStatus == "verified"  # greenhouse + news

    # run 2: same inputs → deduped, DB does NOT grow
    s2 = pipeline.run(now=datetime(2026, 6, 17))
    assert s2["new"] == 0
    assert s2["deduped"] == 1
    assert store.signal_count() == 1  # the idempotency guarantee, end-to-end
