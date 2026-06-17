"""On-disk response cache keyed by request URL. Makes runs/tests/Looms reproducible
and keeps us polite to public endpoints."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class ResponseCache:
    def __init__(self, cache_dir: Path, ttl_s: int):
        self.cache_dir = cache_dir
        self.ttl_s = ttl_s
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        h = hashlib.sha1(key.encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    def get(self, key: str, *, now: float | None = None) -> str | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        age = (now if now is not None else time.time()) - blob["stored_at"]
        if age > self.ttl_s:
            return None
        return blob["body"]

    def set(self, key: str, body: str, *, now: float | None = None) -> None:
        path = self._path(key)
        path.write_text(
            json.dumps({"stored_at": now if now is not None else time.time(), "body": body})
        )
