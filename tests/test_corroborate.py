"""M5/M6/M7: corroboration math, verification, emit threshold, evidence extraction."""

from datetime import datetime

from signal_connector.models import Location, Observation, SourceType, VerificationStatus
from signal_connector.processing.corroborate import CorroborationEngine
from signal_connector.processing.evidence import extract_evidence
from signal_connector.sources.base import CompanyConfig

NOW = datetime(2026, 6, 17)
BERLIN = Location(city="Berlin", country="DE")


def _company():
    return CompanyConfig(
        name="Intercom", slug="intercom", domain="intercom.com", industry="saas",
        country="US", hq=Location(city="San Francisco", country="US"),
    )


def _gh_obs(roles=2):
    return Observation(
        source_type=SourceType.GREENHOUSE, company_slug="intercom", location=BERLIN,
        url="https://boards.greenhouse.io/intercom", title="3 jobs in Berlin",
        discovered_at=NOW,
        evidence={
            "jobPostingsInLocation": 3,
            "expansionRoles": ["AI Infrastructure Engineer", "ML Scientist"][:roles],
            "allTitles": ["AI Infrastructure Engineer", "Senior Machine Learning Scientist"],
        },
    )


def _news_obs(when=datetime(2026, 5, 1)):
    return Observation(
        source_type=SourceType.NEWS_ARTICLE, company_slug="intercom", location=BERLIN,
        url="https://tech.eu/intercom-berlin", title="Intercom opens Berlin hub, 100 hires",
        published_at=when, occurred_at=when, discovered_at=NOW, is_primary=True,
        evidence={"snippet": "Intercom will scale to 200 staff by July 2026."},
    )


def test_two_independent_sources_verify_and_emit():
    eng = CorroborationEngine([_company()])
    sigs = eng.run([_gh_obs(), _news_obs()], NOW)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.verificationStatus == VerificationStatus.VERIFIED  # greenhouse + news = 2 independent
    assert s.confidenceScore >= 0.6
    assert {str(x.sourceType) for x in s.sources} == {"greenhouse", "news_article"}
    # evidence enriched from the news text
    assert s.expansion.evidence.get("headcountTarget") == 200
    assert "2026" in s.expansion.evidence.get("timeline", "")


def test_single_ats_source_not_emitted_when_below_threshold():
    eng = CorroborationEngine([_company()])
    # greenhouse only: weight 0.45 + evidence(2 roles=0.10) = 0.55 < 0.60 → unverified, not emitted
    sigs = eng.run([_gh_obs(roles=2)], NOW)
    assert sigs == []


def test_stale_signal_decays_confidence():
    eng = CorroborationEngine([_company()])
    older = datetime(2026, 2, 15)  # ~4 months before NOW → decayed but still emits
    fresh = eng.run([_gh_obs(), _news_obs(when=datetime(2026, 6, 1))], NOW)[0]
    stale = eng.run([_gh_obs(), _news_obs(when=older)], NOW)[0]
    assert stale.confidenceScore < fresh.confidenceScore


def test_evidence_extractor():
    ev = extract_evidence(
        ["Anduril opens Ohio factory", "A $1 billion Arsenal-1 plant, 4000 jobs, by July 2026"]
    )
    assert ev["headcountTarget"] == 4000
    assert "billion" in ev["investment"].lower()
    assert "2026" in ev["timeline"]
