"""Feed-based sources: third-party news, company primary press, and econ-dev/local-gov
announcements. All parse RSS/Atom via feedparser and match entries to the known company
set + a watch-metro, then emit Observations.

These give the *independent* corroboration that turns a job-cluster into a verified signal.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import feedparser

from signal_connector.models import Observation, SourceType
from signal_connector.processing.locations import parse_location
from signal_connector.sources.base import BaseSource, CompanyConfig, RunContext


def _published(entry) -> datetime | None:
    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not st:
        return None
    return datetime.fromtimestamp(time.mktime(st))


def _canonical(url: str) -> str:
    s = urlsplit(url)
    return f"{s.netloc.lower()}{s.path.rstrip('/')}"


def _entry_mentions_any(entry, terms: list[str]) -> bool:
    text = f"{getattr(entry, 'title', '')} {getattr(entry, 'summary', '')}".lower()
    return any(t.lower() in text for t in terms if t)


class NewsSource(BaseSource):
    """Third-party coverage via Google News RSS. Query is broad (company + expansion
    keywords); entries are then filtered to the watch-metro OR one of its aliases —
    because news often names a metro differently than the job board (Sunnyvale vs
    'Silicon Valley')."""

    source_type = SourceType.NEWS_ARTICLE
    name = "news"

    def _query_url(self, company: str) -> str:
        q = f'"{company}" ("opens" OR "expands" OR "new office" OR "hub" OR "expansion" OR "R&D")'
        return f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"

    def discover(self, ctx: RunContext) -> Iterator[Observation]:
        for c in ctx.companies:
            for metro in c.watch_metros:
                target = parse_location(metro)
                if target is None:
                    continue
                terms = [target.city, *c.metro_aliases]
                feed = feedparser.parse(ctx.http.get(self._query_url(c.name)))
                seen: set[str] = set()
                for entry in feed.entries[:12]:
                    link = getattr(entry, "link", "")
                    if not link or not _entry_mentions_any(entry, terms):
                        continue
                    canon = _canonical(link)
                    if canon in seen:  # collapse syndication
                        continue
                    seen.add(canon)
                    pub = _published(entry)
                    yield Observation(
                        source_type=self.source_type,
                        company_slug=c.slug,
                        location=target,
                        url=link,
                        title=getattr(entry, "title", None),
                        published_at=pub,
                        occurred_at=pub,
                        discovered_at=ctx.discovered_at,
                        evidence={"snippet": getattr(entry, "summary", "")[:400]},
                    )


class _ConfiguredFeedSource(BaseSource):
    """Base for sources reading explicit per-company feed URLs (press / econ-dev)."""

    def _feed_urls(self, c: CompanyConfig) -> list[str]:  # pragma: no cover - overridden
        raise NotImplementedError

    def discover(self, ctx: RunContext) -> Iterator[Observation]:
        for c in ctx.companies:
            for feed_url in self._feed_urls(c):
                feed = feedparser.parse(ctx.http.get(feed_url))
                for metro in c.watch_metros:
                    target = parse_location(metro)
                    if target is None:
                        continue
                    terms = [target.city, *c.metro_aliases]
                    for entry in feed.entries[:20]:
                        link = getattr(entry, "link", "")
                        if not link or not _entry_mentions_any(entry, terms):
                            continue
                        pub = _published(entry)
                        yield Observation(
                            source_type=self.source_type,
                            company_slug=c.slug,
                            location=target,
                            url=link,
                            title=getattr(entry, "title", None),
                            published_at=pub,
                            occurred_at=pub,
                            discovered_at=ctx.discovered_at,
                            is_primary=self.source_type == SourceType.PRESS_RELEASE,
                            evidence={"snippet": getattr(entry, "summary", "")[:400]},
                        )


class PressSource(_ConfiguredFeedSource):
    """Company's own newsroom/blog feed → press_release (isPrimary)."""

    source_type = SourceType.PRESS_RELEASE
    name = "press"

    def _feed_urls(self, c: CompanyConfig) -> list[str]:
        return [c.newsroom_rss] if c.newsroom_rss else []


class EconDevSource(_ConfiguredFeedSource):
    """Local-gov / economic-development announcements (mapped to news_article enum)."""

    source_type = SourceType.NEWS_ARTICLE
    name = "econdev"

    def _feed_urls(self, c: CompanyConfig) -> list[str]:
        return list(c.econdev_urls)
