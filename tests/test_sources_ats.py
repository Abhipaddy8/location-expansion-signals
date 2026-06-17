"""M4: GreenhouseSource parses real board JSON → expansion Observations.
Remote/other-metro jobs are dropped; expansion roles are counted."""

from datetime import datetime
from pathlib import Path

import httpx
import respx

from signal_connector.http.cache import ResponseCache
from signal_connector.http.client import HttpClient
from signal_connector.http.ratelimit import PerHostRateLimiter
from signal_connector.models import Location, SourceType
from signal_connector.processing.locations import is_remote, parse_location
from signal_connector.processing.roles import infer_expansion_type, is_expansion_role
from signal_connector.sources.ats import GreenhouseSource
from signal_connector.sources.base import CompanyConfig, RunContext

FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_intercom.json"


def _ctx(tmp_path):
    http = HttpClient(
        cache=ResponseCache(tmp_path / "c", 3600), limiter=PerHostRateLimiter(0.0)
    )
    company = CompanyConfig(
        name="Intercom", slug="intercom", greenhouse="intercom",
        hq=Location(city="San Francisco", country="US"),
        watch_metros=["Berlin, Germany"],
    )
    return RunContext(http=http, companies=[company], discovered_at=datetime(2026, 6, 17))


@respx.mock
def test_greenhouse_emits_berlin_observation(tmp_path):
    body = FIXTURE.read_text()
    respx.get("https://boards-api.greenhouse.io/v1/boards/intercom/jobs").mock(
        return_value=httpx.Response(200, text=body)
    )
    obs = list(GreenhouseSource().discover(_ctx(tmp_path)))
    assert len(obs) == 1  # one (company, metro) cluster
    o = obs[0]
    assert o.source_type == SourceType.GREENHOUSE
    assert o.location.city == "Berlin"
    # 3 Berlin jobs matched; remote + Dublin dropped
    assert o.evidence["jobPostingsInLocation"] == 3
    # AI Infrastructure Engineer + ML Scientist count as expansion roles
    assert len(o.evidence["expansionRoles"]) >= 2


def test_location_parsing_and_remote():
    assert is_remote("Remote - US") is True
    assert parse_location("Remote - US") is None
    berlin = parse_location("Berlin, Germany")
    assert berlin and berlin.city == "Berlin" and berlin.country == "DE"
    austin = parse_location("Austin, TX")
    assert austin and austin.region == "TX" and austin.country == "US"


def test_role_and_type_inference():
    assert is_expansion_role("AI Infrastructure Engineer")
    assert is_expansion_role("Construction Manager (Electrical)")
    assert not is_expansion_role("Brand Copywriter")
    from signal_connector.models import ExpansionType
    assert infer_expansion_type(["Civil Engineer", "Construction Manager", "Data Center Tech"]) == (
        ExpansionType.DATACENTER
    )
    assert infer_expansion_type(["Senior Machine Learning Scientist"]) == ExpansionType.RD
