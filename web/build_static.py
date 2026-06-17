"""Render the feed to a static site (public/index.html + public/signals.json) for hosting.

Same template as the live server, but pre-rendered — no server/DB needed to host. Run after
`signal-connector run` so the DB has signals:  python -m web.build_static
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Template

from signal_connector.settings import settings
from signal_connector.storage.sqlite_store import SqliteStore

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "public"
TEMPLATE = Template((Path(__file__).parent / "templates" / "feed.html").read_text())


def build() -> int:
    store = SqliteStore(settings.db_path)
    store.init_schema()
    signals = [s.model_dump(mode="json") for s in store.all_signals()]
    for s in signals:
        s["_json"] = json.dumps(s, indent=2, default=str)
        s["_indep"] = len({src["sourceType"] for src in s["sources"]})
    verified = sum(1 for s in signals if s["verificationStatus"] == "verified")

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(
        TEMPLATE.render(signals=signals, count=len(signals), verified=verified)
    )
    clean = [{k: v for k, v in s.items() if not k.startswith("_")} for s in signals]
    (OUT / "signals.json").write_text(json.dumps(clean, indent=2))
    print(f"wrote {len(signals)} signals → {OUT}/index.html + signals.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
