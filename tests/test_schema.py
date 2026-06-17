"""M1: a location_expansion signal validates, round-trips JSON, and keys are stable."""

import json
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
    dedupe_key,
    make_signal_id,
)


def _sample() -> LocationExpansionSignal:
    loc = Location(city="Austin", region="TX", country="US")
    occurred = datetime(2026, 3, 1)
    return LocationExpansionSignal(
        signalId=make_signal_id("acme", loc.key(), "2026-03"),
        companyName="Acme Corp",
        companySlug="acme",
        companyWebsite="acme.com",
        companyIndustry="saas",
        companyCountry="US",
        expansion=ExpansionPayload(
            newLocation=loc,
            expansionType=ExpansionType.OFFICE,
            hqLocation=Location(city="San Francisco", country="US"),
            evidence={"jobPostingsInLocation": 7, "expansionRoles": ["Office Manager"]},
        ),
        occurredAt=occurred,
        discoveredAt=datetime(2026, 6, 17),
        confidenceScore=0.91,
        verificationStatus=VerificationStatus.VERIFIED,
        sources=[
            SignalSource(
                url="https://boards.greenhouse.io/acme",
                sourceType=SourceType.GREENHOUSE,
                isPrimary=False,
            ),
            SignalSource(
                url="https://bizjournals.com/acme-austin",
                sourceType=SourceType.NEWS_ARTICLE,
                title="Acme opens Austin office",
                isPrimary=True,
            ),
        ],
    )


def test_signal_validates_and_round_trips():
    sig = _sample()
    dumped = sig.model_dump_json()
    data = json.loads(dumped)
    assert data["signalType"] == "location_expansion"
    assert data["expansion"]["newLocation"]["city"] == "Austin"
    assert data["expansion"]["expansionType"] == "office"  # enum serialized to value
    assert data["verificationStatus"] == "verified"
    assert len(data["sources"]) == 2
    # round-trip back
    again = LocationExpansionSignal.model_validate_json(dumped)
    assert again.companyName == "Acme Corp"


def test_keys_are_deterministic():
    loc = Location(city="Austin", region="TX", country="US")
    occurred = datetime(2026, 3, 15)
    k1 = dedupe_key("acme", loc.key(), occurred)
    k2 = dedupe_key("acme", loc.key(), datetime(2026, 3, 28))  # same month bucket
    assert k1 == k2  # month-bucketed → same key
    id1 = make_signal_id("acme", loc.key(), "2026-03")
    id2 = make_signal_id("acme", loc.key(), "2026-03")
    assert id1 == id2 and len(id1) == 36
