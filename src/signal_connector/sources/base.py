"""Source plugin contract. Adding the next scraper = one BaseSource subclass, nothing else.

The pipeline wraps every discover() in try/except → one source failing logs and the run
continues (per-source isolation).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field

from signal_connector.http.client import HttpClient
from signal_connector.models import Location, Observation, SourceType


class CompanyConfig(BaseModel):
    """One curated company (config-anchored entity resolution)."""

    name: str
    slug: str
    domain: str | None = None
    industry: str | None = None
    country: str | None = None
    hq: Location | None = None

    # ATS board slugs (whichever the company uses)
    greenhouse: str | None = None
    lever: str | None = None
    ashby: str | None = None

    # candidate new metros to detect (full strings, e.g. "Berlin, Germany")
    watch_metros: list[str] = Field(default_factory=list)
    # alternate place-names the news/press may use for the same expansion
    # (e.g. Sunnyvale ↔ "Silicon Valley", Ashville OH ↔ "Columbus" / "Ohio")
    metro_aliases: list[str] = Field(default_factory=list)

    # feed-source inputs
    newsroom_rss: str | None = None
    econdev_urls: list[str] = Field(default_factory=list)


@dataclass
class RunContext:
    http: HttpClient
    companies: list[CompanyConfig]
    discovered_at: datetime


class BaseSource(ABC):
    source_type: SourceType
    name: str

    @abstractmethod
    def discover(self, ctx: RunContext) -> Iterator[Observation]: ...
