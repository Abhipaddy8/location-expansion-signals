"""M12: adding a source = one BaseSource subclass. Lever (a different ATS JSON shape)
works through the exact same ATS pipeline — the 'keep building out your DB' story."""

import json
from datetime import datetime

import httpx
import respx

from signal_connector.http.cache import ResponseCache
from signal_connector.http.client import HttpClient
from signal_connector.http.ratelimit import PerHostRateLimiter
from signal_connector.models import Location, SourceType
from signal_connector.sources.ats import LeverSource
from signal_connector.sources.base import CompanyConfig, RunContext

# Lever's posting shape: list of {text, categories: {location}}
LEVER_BODY = json.dumps([
    {"text": "Site Reliability Engineer", "categories": {"location": "Toronto, Canada"}},
    {"text": "Office Manager", "categories": {"location": "Toronto, ON"}},
    {"text": "Remote Sales Rep", "categories": {"location": "Remote - Canada"}},
])


@respx.mock
def test_lever_source_one_subclass(tmp_path):
    respx.get("https://api.lever.co/v0/postings/acme?mode=json").mock(
        return_value=httpx.Response(200, text=LEVER_BODY)
    )
    http = HttpClient(cache=ResponseCache(tmp_path / "c", 3600), limiter=PerHostRateLimiter(0.0))
    company = CompanyConfig(
        name="Acme", slug="acme", lever="acme",
        hq=Location(city="San Francisco", country="US"),
        watch_metros=["Toronto, Canada"],
    )
    ctx = RunContext(http=http, companies=[company], discovered_at=datetime(2026, 6, 17))

    obs = list(LeverSource().discover(ctx))
    assert len(obs) == 1
    assert obs[0].source_type == SourceType.LEVER
    assert obs[0].location.city == "Toronto"
    assert obs[0].evidence["jobPostingsInLocation"] == 2  # remote dropped
