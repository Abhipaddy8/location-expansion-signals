"""The emitted Signal — Signalbase `FundingSignal` envelope, verbatim field names,
with a typed `location_expansion` payload (proposed catalog extension).

camelCase field names are intentional: they match the Signalbase API exactly so the
JSON reads native to them.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from signal_connector.models import (
    ExpansionType,
    Location,
    SignalSource,
    VerificationStatus,
)


class ExpansionPayload(BaseModel):
    """Typed payload for signalType == 'location_expansion'."""

    model_config = ConfigDict(use_enum_values=True)

    newLocation: Location
    expansionType: ExpansionType
    hqLocation: Location | None = None
    evidence: dict = Field(default_factory=dict)


class LocationExpansionSignal(BaseModel):
    """Mirrors Signalbase FundingSignal envelope. `expansion` replaces the funding block."""

    model_config = ConfigDict(use_enum_values=True)

    # identifiers
    signalId: str
    signalType: str = "location_expansion"
    companyId: str | None = None
    companyName: str  # primary key in Signalbase
    companySlug: str | None = None

    # company context
    companyWebsite: str | None = None
    companyLinkedin: str | None = None
    companyIndustry: str | None = None
    companyCountry: str | None = None
    companyEmployeeCount: int | None = None

    # typed payload (this signal type's "funding block")
    expansion: ExpansionPayload

    # timestamps (ISO 8601)
    occurredAt: datetime
    discoveredAt: datetime

    # quality & attribution
    confidenceScore: float | None = None
    verificationStatus: VerificationStatus = VerificationStatus.PENDING
    sources: list[SignalSource] = Field(default_factory=list)


def make_signal_id(company_slug: str, location_key: str, occurred_bucket: str) -> str:
    """Deterministic UUID-shaped id from the dedupe inputs (stable across runs)."""
    raw = f"location_expansion|{company_slug}|{location_key}|{occurred_bucket}"
    h = hashlib.sha1(raw.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def dedupe_key(company_slug: str, location_key: str, occurred_at: datetime) -> str:
    """Idempotency key: company + canonical location + month bucket + signal type."""
    bucket = occurred_at.strftime("%Y-%m")
    raw = f"location_expansion|{company_slug}|{location_key}|{bucket}"
    return hashlib.sha1(raw.encode()).hexdigest()
