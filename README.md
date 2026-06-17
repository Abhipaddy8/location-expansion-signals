# Location-Expansion Signals

A Python connector that detects **company location-expansion** events for a configured set of companies,
corroborates them across independent public sources, and **idempotently builds a signal database**.
Each result is emitted as a structured `location_expansion` signal in a GTM-signal envelope
(modelled on the [Signalbase](https://docs.trysignalbase.com/) API shape).

> Pipeline: `discover → normalize → resolve → corroborate → emit → persist`.
> Deterministic core (no LLM in the hot path) · idempotent single-run · structured run summary.
> **No API keys required** — it scrapes public job boards + news feeds.
> **Scope:** verifies/structures expansions for companies listed in `config/sources.yaml` — not an
> open-web crawler. See [Scope](#scope-this-is-a-connector-not-open-world-discovery) and
> [Running it across many companies](#running-it-across-many-companies-scaling-off-greenhouse).

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

## Scope: this is a connector, not open-world discovery

**Read this before assuming more than it does.** This tool is pointed at a **curated set of companies**
in `config/sources.yaml`, each with the metro to watch. For each one it scrapes *that* company's board
+ news, corroborates, and structures the result. The detection and corroboration are **real and run
live** — but the *selection of which companies* is configured. It does **not** crawl all job boards to
discover unknown expanders on its own.

That's deliberate: it isolates and proves the two hard, reusable parts — **conforming to the signal
schema** and **the corroboration/quality logic on real data**. Turning it into open-world discovery is
a well-defined extension, described below.

Other honest limits:
- **Config-anchored entity resolution.** Companies carry their canonical identity in config; a
  production system would resolve against a company graph.
- **Heuristic confidence.** A transparent, tunable formula (`settings.py`), not calibrated to ground truth.
- **Unverified is intentional.** Kaseya stays `unverified` because news names its expansion "Silicon
  Valley" while the job board says "Sunnyvale" and no source independently confirmed it — the system
  discriminates rather than rubber-stamps.

## Adding a company

If you know a company uses Greenhouse and has a new metro, add an entry to `config/sources.yaml`:

```yaml
- name: Acme
  slug: acme
  domain: acme.com
  industry: saas
  country: US
  hq: {city: San Francisco, region: CA, country: US}
  greenhouse: acme              # the boards.greenhouse.io/<slug> board slug
  watch_metros: ["Austin, TX"]
  metro_aliases: ["Central Texas"]   # alt names news may use for the same place
```

Re-run — it's idempotent, so it just adds Acme without disturbing the rest. (Lever/Ashby slugs work the
same via `lever:` / `ashby:`.)

## Running it across many companies (scaling off Greenhouse)

The engine already scales — pluggable sources, idempotent store, safe to run on any schedule. Going from
"verify known expansions" to "**discover** unknown ones" is two additions:

**1. Get a universe of board slugs.** Greenhouse's public API is per-board
(`https://boards-api.greenhouse.io/v1/boards/{slug}/jobs` — no auth, returns every posting with
`location.name`). There is **no global "list all boards" endpoint**, so you assemble a slug list from:
company-name → slug guessing (lowercase, no spaces — works surprisingly often), public Greenhouse-customer
lists, job aggregators, or an existing company database. One slug per company is all the connector needs.

**2. Scan all metros + detect "new".** Today each company has a `watch_metros` allow-list. To discover,
drop the allow-list and instead, per board:
- cluster **every** posting by metro, dropping HQ and remote (the `processing/` layer already normalizes
  locations, strips remote, and classifies roles);
- flag a metro as a **candidate expansion** when it has a cluster of *expansion-indicating* roles —
  Site Lead, Office Manager, GM, facilities, construction, on-site engineering (`processing/roles.py`).
  Those role types signal *standing up a physical location*, which is the cold-start heuristic when you
  have no history;
- for higher precision, add a **baseline diff**: the `observations` table already timestamps every
  observation, so a metro that appears this run but wasn't there N weeks ago = genuinely *new*.

Everything downstream — corroboration, confidence, idempotent persistence, the run summary — stays
unchanged. Point that at a large slug universe on a schedule and it continuously surfaces *newly
appearing* metros, corroborated by news, in the same envelope.

## License

MIT — see [LICENSE](LICENSE).
