"""Core domain models. Two layers:

- Observation: a raw scraped atom (one source saw one company in one location).
- Signal: the emitted, corroborated, Signalbase-shaped output (see schema.py for the envelope).

Kept separate so corroboration can be replayed without re-scraping (auditability).
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class SourceType(enum.StrEnum):
    """Mirrors the Signalbase sources[].sourceType enum (+ greenhouse for ATS)."""

    PRESS_RELEASE = "press_release"
    NEWS_ARTICLE = "news_article"
    SOCIAL_MEDIA = "social_media"
    BLOG_POST = "blog_post"
    SEC_FILING = "sec_filing"
    CRUNCHBASE = "crunchbase"
    PITCHBOOK = "pitchbook"
    GREENHOUSE = "greenhouse"  # ATS job board (our addition)
    LEVER = "lever"


# Source types that count as "news-like" — collapsed by canonical URL for independence.
NEWS_LIKE = {SourceType.PRESS_RELEASE, SourceType.NEWS_ARTICLE, SourceType.BLOG_POST}


class ExpansionType(enum.StrEnum):
    OFFICE = "office"
    RD = "rd"
    WAREHOUSE = "warehouse"
    RETAIL = "retail"
    MANUFACTURING = "manufacturing"
    DATACENTER = "datacenter"


class VerificationStatus(enum.StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    PENDING = "pending"


class Location(BaseModel):
    city: str
    region: str | None = None
    country: str | None = None

    def key(self) -> str:
        return "|".join(
            p.strip().lower() for p in (self.city, self.region or "", self.country or "")
        )


class Company(BaseModel):
    """Canonical entity (config-anchored for the demo)."""

    name: str
    slug: str
    domain: str | None = None
    industry: str | None = None
    country: str | None = None
    hq: Location | None = None
    linkedin: str | None = None
    employee_count: int | None = None


class Observation(BaseModel):
    """A raw atom emitted by one Source.discover()."""

    source_type: SourceType
    company_slug: str
    location: Location
    url: str
    title: str | None = None
    published_at: datetime | None = None
    occurred_at: datetime | None = None
    discovered_at: datetime
    is_primary: bool = False
    # source-specific evidence (e.g. greenhouse: matched job titles / count)
    evidence: dict = Field(default_factory=dict)


class SignalSource(BaseModel):
    """Normalized sources[] entry — exact Signalbase shape."""

    url: HttpUrl
    sourceType: SourceType
    title: str | None = None
    publishedAt: datetime | None = None
    isPrimary: bool = False
