"""SQLite store with idempotent upsert + enrich-on-conflict.

The dedupe_key UNIQUE constraint is the spine: re-runs never duplicate; when a *new*
corroborating source arrives for a known signal, we ENRICH it (append source, raise
confidence, possibly upgrade verification) instead of inserting a twin.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from signal_connector.models import (
    Company,
    Observation,
    SignalSource,
    VerificationStatus,
)
from signal_connector.schema import (
    ExpansionPayload,
    LocationExpansionSignal,
    dedupe_key,
)
from signal_connector.storage.base import Store, UpsertResult

_VERIFICATION_RANK = {
    VerificationStatus.PENDING: 0,
    VerificationStatus.UNVERIFIED: 1,
    VerificationStatus.VERIFIED: 2,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    slug TEXT PRIMARY KEY, name TEXT, domain TEXT, industry TEXT,
    country TEXT, hq_json TEXT, linkedin TEXT, employee_count INTEGER
);
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    dedupe_key TEXT UNIQUE NOT NULL,
    signal_type TEXT NOT NULL,
    company_slug TEXT,
    company_name TEXT,
    payload_json TEXT NOT NULL,
    confidence_score REAL,
    verification_status TEXT,
    occurred_at TEXT,
    discovered_at TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS signal_sources (
    signal_id TEXT, url TEXT, source_type TEXT, title TEXT,
    published_at TEXT, is_primary INTEGER,
    PRIMARY KEY (signal_id, url)
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, source_type TEXT, company_slug TEXT, raw_location TEXT,
    city TEXT, region TEXT, country TEXT, url TEXT,
    occurred_at TEXT, discovered_at TEXT, evidence_json TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT,
    scraped INTEGER, new INTEGER, enriched INTEGER, deduped INTEGER,
    dropped_json TEXT, errors_json TEXT, duration_s REAL
);
"""


class SqliteStore(Store):
    def __init__(self, db_path: Path | str = ":memory:"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_company(self, company: Company) -> None:
        self.conn.execute(
            """INSERT INTO companies
               (slug,name,domain,industry,country,hq_json,linkedin,employee_count)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET name=excluded.name, domain=excluded.domain,
                 industry=excluded.industry, country=excluded.country, hq_json=excluded.hq_json""",
            (
                company.slug, company.name, company.domain, company.industry, company.country,
                company.hq.model_dump_json() if company.hq else None,
                company.linkedin, company.employee_count,
            ),
        )
        self.conn.commit()

    def add_observation(self, obs: Observation, run_id: str) -> None:
        self.conn.execute(
            """INSERT INTO observations
               (run_id,source_type,company_slug,raw_location,city,region,country,url,
                occurred_at,discovered_at,evidence_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, str(obs.source_type), obs.company_slug, obs.location.city,
                obs.location.city, obs.location.region, obs.location.country, obs.url,
                _iso(obs.occurred_at), _iso(obs.discovered_at), json.dumps(obs.evidence),
            ),
        )
        self.conn.commit()

    def upsert_signal(self, signal: LocationExpansionSignal) -> UpsertResult:
        key = dedupe_key(
            signal.companySlug or signal.companyName,
            _payload(signal).newLocation.key(),
            signal.occurredAt,
        )
        row = self.conn.execute(
            "SELECT signal_id FROM signals WHERE dedupe_key=?", (key,)
        ).fetchone()

        if row is None:
            self._insert_signal(signal, key)
            return UpsertResult.NEW

        signal_id = row["signal_id"]
        existing_urls = {
            r["url"]
            for r in self.conn.execute(
                "SELECT url FROM signal_sources WHERE signal_id=?", (signal_id,)
            )
        }
        new_sources = [s for s in signal.sources if str(s.url) not in existing_urls]
        if not new_sources:
            return UpsertResult.DEDUPED

        self._enrich_signal(signal_id, signal, new_sources)
        return UpsertResult.ENRICHED

    # ---- internals ----

    def _insert_signal(self, signal: LocationExpansionSignal, key: str) -> None:
        now = _iso(signal.discoveredAt)
        self.conn.execute(
            """INSERT INTO signals
               (signal_id,dedupe_key,signal_type,company_slug,company_name,payload_json,
                confidence_score,verification_status,occurred_at,discovered_at,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                signal.signalId, key, signal.signalType, signal.companySlug, signal.companyName,
                signal.model_dump_json(), signal.confidenceScore, str(signal.verificationStatus),
                _iso(signal.occurredAt), _iso(signal.discoveredAt), now, now,
            ),
        )
        self._write_sources(signal.signalId, signal.sources)
        self.conn.commit()

    def _enrich_signal(
        self, signal_id: str, signal: LocationExpansionSignal, new_sources: list[SignalSource]
    ) -> None:
        self._write_sources(signal_id, new_sources)
        # merge into payload: load stored, append new sources, raise confidence/verification
        stored = LocationExpansionSignal.model_validate_json(
            self.conn.execute(
                "SELECT payload_json FROM signals WHERE signal_id=?", (signal_id,)
            ).fetchone()["payload_json"]
        )
        merged_sources = stored.sources + new_sources
        new_conf = max(
            signal.confidenceScore or 0.0, stored.confidenceScore or 0.0
        )
        new_verif = max(
            signal.verificationStatus,
            stored.verificationStatus,
            key=lambda v: _VERIFICATION_RANK.get(VerificationStatus(v), 0),
        )
        stored.sources = merged_sources
        stored.confidenceScore = new_conf
        stored.verificationStatus = new_verif
        self.conn.execute(
            """UPDATE signals SET payload_json=?, confidence_score=?, verification_status=?,
               updated_at=? WHERE signal_id=?""",
            (
                stored.model_dump_json(), new_conf, str(new_verif),
                _iso(datetime.now()), signal_id,
            ),
        )
        self.conn.commit()

    def _write_sources(self, signal_id: str, sources: list[SignalSource]) -> None:
        for s in sources:
            self.conn.execute(
                """INSERT OR IGNORE INTO signal_sources
                   (signal_id,url,source_type,title,published_at,is_primary)
                   VALUES (?,?,?,?,?,?)""",
                (signal_id, str(s.url), str(s.sourceType), s.title, _iso(s.publishedAt),
                 int(s.isPrimary)),
            )

    def signal_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM signals").fetchone()["c"]

    def all_signals(self) -> list[LocationExpansionSignal]:
        rows = self.conn.execute(
            "SELECT payload_json FROM signals ORDER BY confidence_score DESC"
        ).fetchall()
        return [LocationExpansionSignal.model_validate_json(r["payload_json"]) for r in rows]

    def record_run(self, run: dict) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id,started_at,finished_at,scraped,new,enriched,deduped,
                dropped_json,errors_json,duration_s)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                run["run_id"], run.get("started_at"), run.get("finished_at"),
                run.get("scraped", 0), run.get("new", 0), run.get("enriched", 0),
                run.get("deduped", 0), json.dumps(run.get("dropped", {})),
                json.dumps(run.get("errors", [])), run.get("duration_s"),
            ),
        )
        self.conn.commit()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _payload(signal: LocationExpansionSignal) -> ExpansionPayload:
    return signal.expansion
