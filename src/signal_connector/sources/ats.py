"""ATS job-board sources. A shared base does the judgment (match jobs to a watch-metro,
strip remote, count expansion roles); per-provider subclasses only fetch + parse their JSON.

- Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
- Lever:      https://api.lever.co/v0/postings/{slug}?mode=json
- Ashby:      https://api.ashbyhq.com/posting-api/job-board/{slug}

Greenhouse fires live on the demo set; Lever/Ashby prove the one-subclass-to-add pattern.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from signal_connector.models import Observation, SourceType
from signal_connector.processing.locations import parse_location
from signal_connector.processing.roles import is_expansion_role
from signal_connector.sources.base import BaseSource, CompanyConfig, RunContext


@dataclass
class _Job:
    title: str
    location: str


class ATSSource(BaseSource):
    """Shared logic: for each company+watch_metro, find on-site jobs in that metro,
    drop remote, and emit one Observation carrying the expansion-role evidence."""

    def _board_slug(self, c: CompanyConfig) -> str | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _fetch_jobs(self, ctx: RunContext, slug: str) -> list[_Job]:  # pragma: no cover
        raise NotImplementedError

    def discover(self, ctx: RunContext) -> Iterator[Observation]:
        for c in ctx.companies:
            slug = self._board_slug(c)
            if not slug:
                continue
            jobs = self._fetch_jobs(ctx, slug)
            yield from self._observations_for_company(c, jobs, ctx)

    def _observations_for_company(
        self, c: CompanyConfig, jobs: list[_Job], ctx: RunContext
    ) -> Iterator[Observation]:
        for metro in c.watch_metros:
            target = parse_location(metro)
            if target is None:
                continue
            matched: list[_Job] = []
            for j in jobs:
                jl = parse_location(j.location)
                if jl and jl.city.lower() == target.city.lower():
                    matched.append(j)
            if not matched:
                continue
            roles = [j.title for j in matched if is_expansion_role(j.title)]
            yield Observation(
                source_type=self.source_type,
                company_slug=c.slug,
                location=target,
                url=self._board_url(slug=self._board_slug(c) or c.slug),
                title=f"{len(matched)} jobs in {target.city}",
                discovered_at=ctx.discovered_at,
                evidence={
                    "jobPostingsInLocation": len(matched),
                    "expansionRoles": roles[:8],
                    "allTitles": [j.title for j in matched][:12],
                },
            )

    def _board_url(self, slug: str) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


class GreenhouseSource(ATSSource):
    source_type = SourceType.GREENHOUSE
    name = "greenhouse"

    def _board_slug(self, c: CompanyConfig) -> str | None:
        return c.greenhouse

    def _board_url(self, slug: str) -> str:
        return f"https://boards.greenhouse.io/{slug}"

    def _fetch_jobs(self, ctx: RunContext, slug: str) -> list[_Job]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        body = ctx.http.get(url)
        data = json.loads(body)
        return [
            _Job(title=j.get("title", ""), location=(j.get("location") or {}).get("name", ""))
            for j in data.get("jobs", [])
        ]


class LeverSource(ATSSource):
    source_type = SourceType.LEVER
    name = "lever"

    def _board_slug(self, c: CompanyConfig) -> str | None:
        return c.lever

    def _board_url(self, slug: str) -> str:
        return f"https://jobs.lever.co/{slug}"

    def _fetch_jobs(self, ctx: RunContext, slug: str) -> list[_Job]:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        data = json.loads(ctx.http.get(url))
        return [
            _Job(title=p.get("text", ""), location=(p.get("categories") or {}).get("location", ""))
            for p in data
        ]


class AshbySource(ATSSource):
    source_type = SourceType.GREENHOUSE  # ATS class; reuse greenhouse enum bucket for scoring
    name = "ashby"

    def _board_slug(self, c: CompanyConfig) -> str | None:
        return c.ashby

    def _board_url(self, slug: str) -> str:
        return f"https://jobs.ashbyhq.com/{slug}"

    def _fetch_jobs(self, ctx: RunContext, slug: str) -> list[_Job]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        data = json.loads(ctx.http.get(url))
        return [
            _Job(title=j.get("title", ""), location=j.get("location", ""))
            for j in data.get("jobs", [])
        ]
