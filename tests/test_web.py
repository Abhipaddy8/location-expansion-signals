"""M10: the read-only feed renders signals from the DB and serves raw JSON."""

from datetime import datetime

from fastapi.testclient import TestClient

import signal_connector.settings as settings_mod
from signal_connector.models import (
    ExpansionType,
    Location,
    SignalSource,
    SourceType,
    VerificationStatus,
)
from signal_connector.schema import ExpansionPayload, LocationExpansionSignal, make_signal_id
from signal_connector.storage.sqlite_store import SqliteStore


def _seed(db_path):
    store = SqliteStore(db_path)
    store.init_schema()
    loc = Location(city="Berlin", country="DE")
    store.upsert_signal(
        LocationExpansionSignal(
            signalId=make_signal_id("intercom", loc.key(), "2025-10"),
            companyName="Intercom", companySlug="intercom",
            expansion=ExpansionPayload(newLocation=loc, expansionType=ExpansionType.RD),
            occurredAt=datetime(2025, 10, 29), discoveredAt=datetime(2026, 6, 17),
            confidenceScore=0.68, verificationStatus=VerificationStatus.VERIFIED,
            sources=[
                SignalSource(
                    url="https://boards.greenhouse.io/intercom",
                    sourceType=SourceType.GREENHOUSE,
                ),
                SignalSource(
                    url="https://tech.eu/intercom-berlin",
                    sourceType=SourceType.NEWS_ARTICLE,
                    isPrimary=True,
                ),
            ],
        )
    )


def test_feed_and_json(tmp_path, monkeypatch):
    db = tmp_path / "signals.db"
    _seed(db)
    monkeypatch.setattr(settings_mod.settings, "db_path", db)

    import web.app as webapp
    client = TestClient(webapp.app)

    html = client.get("/")
    assert html.status_code == 200
    assert "Intercom" in html.text
    assert "Berlin" in html.text
    assert "verified" in html.text
    assert "independent sources" in html.text  # corroboration row rendered

    data = client.get("/signals.json")
    assert data.status_code == 200
    body = data.json()
    assert len(body) == 1 and body[0]["companyName"] == "Intercom"
