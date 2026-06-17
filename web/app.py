"""Read-only feed over the signal DB — the shareable hook. Renders the signals table
as cards (with the corroboration story front-and-center) + serves raw /signals.json."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Template

from signal_connector.settings import settings
from signal_connector.storage.sqlite_store import SqliteStore

app = FastAPI(title="Location Expansion Signals")
_TEMPLATE = Template((Path(__file__).parent / "templates" / "feed.html").read_text())


def _load() -> list[dict]:
    store = SqliteStore(settings.db_path)
    store.init_schema()
    return [s.model_dump(mode="json") for s in store.all_signals()]


@app.get("/", response_class=HTMLResponse)
def feed():
    signals = _load()
    for s in signals:
        s["_json"] = json.dumps(s, indent=2, default=str)
        s["_indep"] = len({src["sourceType"] for src in s["sources"]})
    verified = sum(1 for s in signals if s["verificationStatus"] == "verified")
    html = _TEMPLATE.render(signals=signals, count=len(signals), verified=verified)
    return HTMLResponse(html)


@app.get("/signals.json")
def signals_json():
    return JSONResponse(_load())
