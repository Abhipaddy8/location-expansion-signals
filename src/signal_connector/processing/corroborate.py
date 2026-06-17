"""Corroboration engine: cluster observations → score → verify → emit signals.

This is the judgment layer. Independence = distinct source_types (syndication already
collapsed per source). Confidence + verification follow the locked formula (decisions.md).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from signal_connector.models import (
    NEWS_LIKE,
    Observation,
    SignalSource,
    SourceType,
    VerificationStatus,
)
from signal_connector.processing.evidence import extract_evidence
from signal_connector.processing.roles import infer_expansion_type
from signal_connector.schema import (
    ExpansionPayload,
    LocationExpansionSignal,
    make_signal_id,
)
from signal_connector.settings import settings
from signal_connector.sources.base import CompanyConfig

_ATS = {SourceType.GREENHOUSE, SourceType.LEVER}


def _source_weight(st: SourceType) -> float:
    if st == SourceType.PRESS_RELEASE:
        return settings.weight_press
    if st in (SourceType.NEWS_ARTICLE, SourceType.BLOG_POST):
        return settings.weight_news
    if st in _ATS:
        return settings.weight_greenhouse
    if st == SourceType.SOCIAL_MEDIA:
        return settings.weight_social
    return 0.40


def _recency_factor(occurred: datetime, now: datetime) -> float:
    age_days = max(0.0, (now - occurred).total_seconds() / 86400)
    full, floor_d, floor = (
        settings.recency_full_days,
        settings.recency_floor_days,
        settings.recency_floor,
    )
    if age_days <= full:
        return 1.0
    if age_days >= floor_d:
        return floor
    # linear interp between full→1.0 and floor_d→floor
    span = floor_d - full
    return 1.0 - (1.0 - floor) * (age_days - full) / span


class CorroborationEngine:
    def __init__(self, companies: list[CompanyConfig]):
        self.by_slug = {c.slug: c for c in companies}
        self.dropped = 0  # clusters that didn't clear threshold/verification (kept as raw obs)

    def run(self, observations: list[Observation], now: datetime) -> list[LocationExpansionSignal]:
        clusters: dict[tuple[str, str], list[Observation]] = defaultdict(list)
        for o in observations:
            clusters[(o.company_slug, o.location.key())].append(o)

        self.dropped = 0
        signals: list[LocationExpansionSignal] = []
        for (slug, _loc_key), obs in clusters.items():
            company = self.by_slug.get(slug)
            if company is None:
                continue
            sig = self._build(company, obs, now)
            if sig is not None:
                signals.append(sig)
            else:
                self.dropped += 1
        return signals

    def _build(
        self, company: CompanyConfig, obs: list[Observation], now: datetime
    ) -> LocationExpansionSignal | None:
        source_types = {o.source_type for o in obs}
        independent = len(source_types)

        # evidence from ATS clusters
        ats_obs = [o for o in obs if o.source_type in _ATS]
        roles = max((len(o.evidence.get("expansionRoles", [])) for o in ats_obs), default=0)
        jobs_in_loc = max((o.evidence.get("jobPostingsInLocation", 0) for o in ats_obs), default=0)
        all_titles = [t for o in ats_obs for t in o.evidence.get("allTitles", [])]

        # occurred_at = earliest known event time (news), else discovered
        occ_times = [o.occurred_at for o in obs if o.occurred_at]
        occurred = min(occ_times) if occ_times else obs[0].discovered_at

        # --- confidence (locked formula) ---
        base = max(_source_weight(st) for st in source_types)
        indep_bonus = settings.independence_bonus if independent >= 2 else 0.0
        evid_bonus = min(settings.evidence_cap, settings.evidence_per_role * roles)
        recency = _recency_factor(occurred, now)
        confidence = round(max(0.0, min(1.0, (base + indep_bonus + evid_bonus) * recency)), 3)

        # --- verification ---
        has_primary_press = any(
            o.source_type == SourceType.PRESS_RELEASE for o in obs
        )
        strong_single = has_primary_press or roles >= 2
        if independent >= 2:
            verification = VerificationStatus.VERIFIED
        elif strong_single:
            verification = VerificationStatus.UNVERIFIED
        else:
            verification = VerificationStatus.PENDING

        if confidence < settings.emit_threshold or verification == VerificationStatus.PENDING:
            return None  # kept as raw observations, not emitted to the feed

        # --- evidence payload ---
        texts = [o.title or "" for o in obs] + [
            o.evidence.get("snippet", "") for o in obs if o.evidence.get("snippet")
        ]
        evidence = {"jobPostingsInLocation": jobs_in_loc} if jobs_in_loc else {}
        if roles:
            evidence["expansionRoles"] = next(
                (o.evidence["expansionRoles"] for o in ats_obs if o.evidence.get("expansionRoles")),
                [],
            )
        evidence.update(extract_evidence(texts))

        loc = obs[0].location
        sources = _dedupe_sources(obs)
        return LocationExpansionSignal(
            signalId=make_signal_id(company.slug, loc.key(), occurred.strftime("%Y-%m")),
            companyName=company.name,
            companySlug=company.slug,
            companyWebsite=company.domain,
            companyIndustry=company.industry,
            companyCountry=company.country,
            expansion=ExpansionPayload(
                newLocation=loc,
                expansionType=infer_expansion_type(all_titles),
                hqLocation=company.hq,
                evidence=evidence,
            ),
            occurredAt=occurred,
            discoveredAt=obs[0].discovered_at,
            confidenceScore=confidence,
            verificationStatus=verification,
            sources=sources,
        )


def _dedupe_sources(obs: list[Observation]) -> list[SignalSource]:
    seen: set[str] = set()
    out: list[SignalSource] = []
    # primary first so isPrimary wins on dedupe
    for o in sorted(obs, key=lambda x: (not x.is_primary, x.source_type not in NEWS_LIKE)):
        if o.url in seen:
            continue
        seen.add(o.url)
        out.append(
            SignalSource(
                url=o.url,
                sourceType=o.source_type,
                title=o.title,
                publishedAt=o.published_at,
                isPrimary=o.is_primary,
            )
        )
    return out
