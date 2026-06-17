"""Pipeline orchestrator: discover (per-source isolated) → corroborate → persist.

Emits the structured run summary that is the loop's sensor. Idempotent: safe to call
repeatedly; the store dedupes/enriches.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from datetime import datetime

from signal_connector.http.client import HttpClient
from signal_connector.models import Observation
from signal_connector.observability.logging import get_logger
from signal_connector.processing.corroborate import CorroborationEngine
from signal_connector.sources.base import BaseSource, CompanyConfig, RunContext
from signal_connector.storage.base import Store, UpsertResult

log = get_logger("pipeline")


class Pipeline:
    def __init__(
        self,
        sources: Sequence[BaseSource],
        companies: list[CompanyConfig],
        store: Store,
        http: HttpClient | None = None,
    ):
        self.sources = list(sources)
        self.companies = companies
        self.store = store
        self.http = http or HttpClient()

    def run(self, *, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        run_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        self.store.init_schema()
        for c in self.companies:
            self.store.upsert_company(_to_company(c))

        ctx = RunContext(http=self.http, companies=self.companies, discovered_at=now)

        observations: list[Observation] = []
        errors: list[dict] = []
        for source in self.sources:
            try:
                found = list(source.discover(ctx))
                observations.extend(found)
                for o in found:
                    self.store.add_observation(o, run_id)
                log.info("source_done", source=source.name, observations=len(found))
            except Exception as exc:  # per-source isolation — one failure never kills the run
                errors.append({"source": source.name, "error": str(exc)})
                log.warning("source_failed", source=source.name, error=str(exc))

        engine = CorroborationEngine(self.companies)
        signals = engine.run(observations, now)

        counts = {"new": 0, "enriched": 0, "deduped": 0}
        for sig in signals:
            res = self.store.upsert_signal(sig)
            counts[res.value] += 1

        summary = {
            "run_id": run_id,
            "started_at": now.isoformat(),
            "finished_at": datetime.now().isoformat(),
            "scraped": len(observations),
            "new": counts[UpsertResult.NEW.value],
            "enriched": counts[UpsertResult.ENRICHED.value],
            "deduped": counts[UpsertResult.DEDUPED.value],
            "dropped": {"below_threshold_or_pending": engine.dropped},
            "emitted_signals": len(signals),
            "errors": errors,
            "duration_s": round(time.monotonic() - started, 2),
        }
        self.store.record_run(summary)
        log.info("run_summary", **{k: v for k, v in summary.items() if k != "started_at"})
        return summary


def _to_company(c: CompanyConfig):
    from signal_connector.models import Company

    return Company(
        name=c.name, slug=c.slug, domain=c.domain, industry=c.industry,
        country=c.country, hq=c.hq,
    )
