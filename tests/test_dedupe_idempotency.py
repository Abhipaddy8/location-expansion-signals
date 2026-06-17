"""M3: the heart of the demo. Re-running must NOT duplicate; a new corroborating
source must ENRICH the existing signal (not create a twin)."""

from datetime import datetime

from signal_connector.models import (
    ExpansionType,
    Location,
    SignalSource,
    SourceType,
    VerificationStatus,
)
from signal_connector.schema import (
    ExpansionPayload,
    LocationExpansionSignal,
    make_signal_id,
)
from signal_connector.storage.base import UpsertResult
from signal_connector.storage.sqlite_store import SqliteStore


def _signal(*, sources, confidence, verification):
    loc = Location(city="Berlin", country="DE")
    return LocationExpansionSignal(
        signalId=make_signal_id("intercom", loc.key(), "2025-10"),
        companyName="Intercom",
        companySlug="intercom",
        expansion=ExpansionPayload(newLocation=loc, expansionType=ExpansionType.RD),
        occurredAt=datetime(2025, 10, 29),
        discoveredAt=datetime(2026, 6, 17),
        confidenceScore=confidence,
        verificationStatus=verification,
        sources=sources,
    )


GH = SignalSource(url="https://boards.greenhouse.io/intercom", sourceType=SourceType.GREENHOUSE)
NEWS = SignalSource(
    url="https://tech.eu/2025/10/29/intercom-berlin",
    sourceType=SourceType.NEWS_ARTICLE,
    isPrimary=True,
)


def _store() -> SqliteStore:
    s = SqliteStore(":memory:")
    s.init_schema()
    return s


def test_first_insert_is_new():
    s = _store()
    sig = _signal(sources=[GH], confidence=0.45, verification=VerificationStatus.UNVERIFIED)
    assert s.upsert_signal(sig) == UpsertResult.NEW
    assert s.signal_count() == 1


def test_identical_rerun_is_deduped_not_duplicated():
    s = _store()
    sig = _signal(sources=[GH], confidence=0.45, verification=VerificationStatus.UNVERIFIED)
    assert s.upsert_signal(sig) == UpsertResult.NEW
    # run again, same inputs
    assert s.upsert_signal(sig) == UpsertResult.DEDUPED
    assert s.upsert_signal(sig) == UpsertResult.DEDUPED
    assert s.signal_count() == 1  # still ONE — the whole point


def test_new_source_enriches_in_place():
    s = _store()
    # round 1: only greenhouse → unverified, low confidence
    s.upsert_signal(
        _signal(sources=[GH], confidence=0.45, verification=VerificationStatus.UNVERIFIED)
    )
    # round 2: news corroboration arrives → same signal, now verified, higher confidence
    res = s.upsert_signal(
        _signal(sources=[GH, NEWS], confidence=0.88, verification=VerificationStatus.VERIFIED)
    )
    assert res == UpsertResult.ENRICHED
    assert s.signal_count() == 1  # enriched, not duplicated

    sig = s.all_signals()[0]
    urls = {str(x.url) for x in sig.sources}
    assert "https://boards.greenhouse.io/intercom" in urls
    assert "https://tech.eu/2025/10/29/intercom-berlin" in urls
    assert sig.confidenceScore == 0.88
    assert sig.verificationStatus == VerificationStatus.VERIFIED
