"""CLI entrypoint: run | export | serve. Single-run is the idempotent loop primitive."""

from __future__ import annotations

import argparse
import json
import sys

from signal_connector.observability.logging import get_logger
from signal_connector.pipeline import Pipeline
from signal_connector.settings import settings
from signal_connector.sources.registry import load_config
from signal_connector.storage.sqlite_store import SqliteStore

log = get_logger("cli")


def _build_pipeline() -> tuple[Pipeline, SqliteStore]:
    sources, companies = load_config(settings.sources_file)
    store = SqliteStore(settings.db_path)
    return Pipeline(sources, companies, store), store


def cmd_run(_args) -> int:
    pipeline, store = _build_pipeline()
    summary = pipeline.run()
    _print_signals(store)
    _print_summary(summary)
    return 0


def _print_signals(store) -> None:
    sigs = sorted(store.all_signals(), key=lambda s: -(s.confidenceScore or 0))
    if not sigs:
        return
    print("\n  signals in database:")
    for s in sigs:
        e = s.expansion
        city = e.newLocation.city
        srcs = "+".join(sorted({str(x.sourceType) for x in s.sources}))
        mark = "✓" if str(s.verificationStatus) == "verified" else "·"
        print(
            f"  {mark} {s.companyName:<20} → {city:<11} "
            f"{s.confidenceScore:.2f} {str(s.verificationStatus):<10} [{srcs}]"
        )


def cmd_export(args) -> int:
    store = SqliteStore(settings.db_path)
    store.init_schema()
    signals = [s.model_dump(mode="json") for s in store.all_signals()]
    out = json.dumps(signals, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
        print(f"wrote {len(signals)} signals → {args.out}")
    else:
        print(out)
    return 0


def cmd_serve(args) -> int:
    import os
    import sys

    sys.path.insert(0, os.getcwd())  # make the repo-root `web` package importable
    import uvicorn

    from web.app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def _print_summary(s: dict) -> None:
    line = (
        f"run {s['run_id']} · scraped {s['scraped']} · "
        f"new {s['new']} · enriched {s['enriched']} · deduped {s['deduped']} · "
        f"dropped {s['dropped']['below_threshold_or_pending']} · "
        f"emitted {s['emitted_signals']} · errors {len(s['errors'])} · {s['duration_s']}s"
    )
    print("\n" + line + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signal-connector")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run", help="scrape → corroborate → persist (idempotent)")

    p_export = sub.add_parser("export", help="dump signals as JSON")
    p_export.add_argument("--out", default=None)

    p_serve = sub.add_parser("serve", help="read-only feed")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    return {"run": cmd_run, "export": cmd_export, "serve": cmd_serve}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
