# Architecture

## Spine
`discover → normalize → resolve → corroborate → emit → persist`
Deterministic (no LLM in the hot path). Idempotent single-run. Structured run summary as the sensor.

```
   SOURCES                PROCESSING                    PERSIST
 Greenhouse ─obs─▶  normalize→resolve→corroborate→emit ─upsert─▶  SQLite (grows, idempotent)
 News(RSS)  ─obs─▶              │                                      │
 Press      ─obs─▶         run metrics                            read-only
 Econ-dev   ─obs─▶     (scraped/new/enriched/                     FastAPI feed
      ▲                 deduped/dropped/errors)
 resilient HTTP
 (retry/backoff/ratelimit/cache)
```

## Module map
```
src/signal_connector/
  cli.py            run | export | serve
  pipeline.py       orchestrate the 6 stages, per-source try/except isolation
  models.py         pydantic: Observation, Company, enums
  schema.py         the signal envelope + location_expansion payload + dedupe/id
  http/             client.py (httpx+tenacity) · ratelimit.py · cache.py
  sources/          base.py (BaseSource ABC) · ats.py (greenhouse/lever/ashby)
                    · feeds.py (news/press/econdev) · registry.py
  processing/       locations.py · roles.py · evidence.py · corroborate.py
  storage/          base.py (Store ABC) · sqlite_store.py
  observability/    logging.py (structlog)
web/app.py          read-only FastAPI feed over the DB
config/sources.yaml curated companies (config-anchored entity resolution)
```

## Key contracts

**Source plugin** — adding a scraper is one subclass:
```python
class BaseSource(ABC):
    source_type: SourceType
    name: str
    def discover(self, ctx: RunContext) -> Iterator[Observation]: ...
```
The pipeline wraps every `discover()` in try/except → one source failing logs and the run continues.

**Idempotent store** — `dedupe_key = hash(company + canonical_location + occurred_month + signal_type)`
UNIQUE. On conflict: a new corroborating source → enrich (append `sources[]`, raise confidence,
possibly upgrade verification); otherwise no-op.

**Run summary (the sensor):**
`{run_id, scraped, new, enriched, deduped, dropped, errors, duration_s}`

## Data model (SQLite)
- `companies` — canonical entity
- `observations` — raw scraped atoms (kept separate so corroboration can be replayed without re-scraping)
- `signals` — emitted signals (`payload_json`, confidence, verification, `dedupe_key` UNIQUE)
- `signal_sources` — normalized `sources[]`
- `runs` — per-run metrics

## Corroboration math
independence = distinct `source_type`s (news syndication collapsed by canonical URL).
- `verified` ≥ 2 independent source types
- `unverified` = a single strong source (primary press, or an ATS cluster of ≥2 expansion roles)
- `pending` = below minimum (kept as raw observations, not emitted)

`confidence = (base_source_weight + independence_bonus + role_evidence_bonus) × recency`, clamped [0,1],
emitted when ≥ 0.60. Recency decays gently (expansion signals have a long half-life). All weights live
in `settings.py`.

## Determinism & idempotency
No LLM in the hot path — normalization, role classification, and corroboration are rules/heuristics, so
runs are reproducible and testable (`tests/test_dedupe_idempotency.py` runs the pipeline twice and
asserts the signal count is stable). The single-run entrypoint is idempotent, so it is safe to schedule.
