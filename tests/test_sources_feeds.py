"""M4b: NewsSource matches the watch-metro, collapses syndication, drops off-metro;
registry builds the right sources + companies from YAML."""

from datetime import datetime
from pathlib import Path

import httpx
import respx

from signal_connector.http.cache import ResponseCache
from signal_connector.http.client import HttpClient
from signal_connector.http.ratelimit import PerHostRateLimiter
from signal_connector.models import Location, SourceType
from signal_connector.sources.base import CompanyConfig, RunContext
from signal_connector.sources.feeds import NewsSource
from signal_connector.sources.registry import load_config

FIXTURE = Path(__file__).parent / "fixtures" / "news_intercom_berlin.xml"


def _ctx(tmp_path):
    http = HttpClient(cache=ResponseCache(tmp_path / "c", 3600), limiter=PerHostRateLimiter(0.0))
    company = CompanyConfig(
        name="Intercom", slug="intercom",
        hq=Location(city="San Francisco", country="US"),
        watch_metros=["Berlin, Germany"],
    )
    return RunContext(http=http, companies=[company], discovered_at=datetime(2026, 6, 17))


@respx.mock
def test_news_matches_metro_and_collapses_syndication(tmp_path):
    respx.get(url__regex=r"https://news\.google\.com/rss/search.*").mock(
        return_value=httpx.Response(200, text=FIXTURE.read_text())
    )
    obs = list(NewsSource().discover(_ctx(tmp_path)))
    # 4 entries: 2 Berlin (1 collapsed) + 1 Dublin (off-metro) → 2 distinct Berlin observations
    assert len(obs) == 2
    assert all(o.source_type == SourceType.NEWS_ARTICLE for o in obs)
    assert all(o.location.city == "Berlin" for o in obs)
    urls = {o.url for o in obs}
    assert "https://tech.eu/2025/10/29/intercom-berlin" in urls
    assert "https://eu-startups.com/intercom-berlin-hub" in urls
    assert "https://example.com/intercom-dublin" not in urls  # off-metro dropped
    assert all(o.occurred_at and o.occurred_at.year == 2025 for o in obs)


def test_registry_loads_sources_and_companies(tmp_path):
    yaml_text = """
sources:
  greenhouse:
    enabled: true
  news:
    enabled: true
  lever:
    enabled: false
companies:
  - name: Intercom
    slug: intercom
    greenhouse: intercom
    industry: saas
    country: US
    hq: {city: San Francisco, country: US}
    watch_metros: ["Berlin, Germany"]
"""
    p = tmp_path / "sources.yaml"
    p.write_text(yaml_text)
    sources, companies = load_config(p)
    names = {s.name for s in sources}
    assert "greenhouse" in names and "news" in names
    assert "lever" not in names  # disabled
    assert len(companies) == 1 and companies[0].greenhouse == "intercom"
    assert companies[0].watch_metros == ["Berlin, Germany"]
