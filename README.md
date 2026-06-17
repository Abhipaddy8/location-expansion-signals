# Location-Expansion Signals

A Python connector that detects **company location-expansion** events from public sources,
corroborates them across independent source types, and **idempotently builds a signal database**.
Each result is emitted as a structured `location_expansion` signal in a GTM-signal envelope
(modelled on the [Signalbase](https://docs.trysignalbase.com/) API shape).

> Pipeline: `discover → normalize → resolve → corroborate → emit → persist`.
> Deterministic core (no LLM in the hot path) · idempotent single-run · structured run summary.
> **No API keys required** — it scrapes public job boards + news feeds.

---

## What it produces (live, real data)

```
run · scraped 22 · new 6 · enriched 0 · deduped 0 · emitted 6 · errors 0 · 5.7s
```

| Company | New metro | Type | Conf | Status | Sources |
|---------|-----------|------|------|--------|---------|
| Cato Networks | London | rd | 0.90 | verified | greenhouse + news |
| Anduril Industries | Ashville, OH | manufacturing | 0.90 | verified | greenhouse + news |
| xAI | Memphis | datacenter | 0.74 | verified | greenhouse + news |
| StarRez | Hyderabad | rd | 0.72 | verified | greenhouse + news |
| Intercom | Berlin | rd | 0.68 | verified | greenhouse + news |
| Kaseya | Sunnyvale | rd | 0.60 | unverified | greenhouse only |

Each signal carries the envelope (`signalId · companyName · occurredAt/discoveredAt ·
confidenceScore · verificationStatus · sources[]`) plus a typed `expansion` payload with extracted
evidence (`jobPostingsInLocation`, `headcountTarget`, `investment`, `timeline`).

## The property that matters: it *accumulates*

```
RUN 1 (fresh)        new 6 · deduped 0     → DB has 6
RUN 2 (same inputs)  new 0 · deduped 6     → DB still 6   (idempotent)
```

Re-runs never duplicate. When a **new corroborating source** appears for a known signal, the row is
**enriched** in place (source appended, confidence raised, `unverified → verified`) rather than twinned.

## Quickstart

```bash
git clone <this repo> && cd location-expansion-signals
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                       # 23 tests, incl. the idempotency gate
signal-connector run         # scrape → corroborate → persist; prints the run summary + table
signal-connector export      # dump signals as JSON
signal-connector serve       # read-only feed at http://127.0.0.1:8000
```

(Or use the `Makefile`: `make install`, `make test`, `make run`, `make serve`, `make demo`.)

## Architecture

- **Pluggable sources** behind one `BaseSource` ABC. Live: Greenhouse (ATS) + News (RSS) + Press +
  Econ-dev. Built + fixture-tested for extension: Lever, Ashby, EDGAR.
  *Adding the next source is a subclass — see `tests/test_extensibility.py`.*
- **Resilient HTTP** — httpx + tenacity (retry/backoff/jitter), per-host rate limiting, on-disk cache.
- **Corroboration** — independence = distinct `source_type`s (news syndication collapsed by canonical
  URL); `verified` at ≥2 independent sources; transparent confidence
  (`source weight + independence + role-evidence × recency`).
- **Idempotent SQLite store** — `dedupe_key` UNIQUE with enrich-on-conflict. `Store` ABC → Postgres drop-in.
- **Observability** — structlog + a `runs` row per execution.

Full design notes in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Scope & honest limitations

- **Curated company set.** The pipeline is demonstrated on a fixed set in `config/sources.yaml`,
  working from known expansions to exercise the output shape and quality logic on real data. Scaling
  discovery to an open universe is a separate (larger) problem.
- **Config-anchored entity resolution.** Companies carry their canonical identity in config; a
  production system would resolve against a company graph.
- **Heuristic confidence.** The score is a transparent, tunable formula (`settings.py`), not calibrated
  against ground truth.
- **Unverified is intentional.** Kaseya stays `unverified` because news names its expansion "Silicon
  Valley" while the job board says "Sunnyvale" and no source independently confirmed it — the system
  discriminates rather than rubber-stamps. (Metro aliasing resolves Anduril/Cato; Kaseya does not clear.)

## License

MIT — see [LICENSE](LICENSE).
