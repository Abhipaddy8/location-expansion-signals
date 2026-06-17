"""Runtime settings, env-driven. Defaults are demo-safe."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SC_", env_file=".env", extra="ignore")

    # storage
    db_path: Path = REPO_ROOT / "output" / "signals.db"

    # http
    http_cache_dir: Path = REPO_ROOT / ".cache" / "http"
    http_cache_ttl_s: int = 60 * 60 * 6  # 6h — reproducible Looms/tests
    http_timeout_s: float = 15.0
    http_max_retries: int = 4
    http_rate_limit_per_host_s: float = 1.0  # min seconds between requests per host

    # sources config
    sources_file: Path = REPO_ROOT / "config" / "sources.yaml"

    # corroboration / scoring (formula lives in processing/corroborate.py; weights here)
    weight_press: float = 0.50
    weight_news: float = 0.50
    weight_greenhouse: float = 0.45
    weight_social: float = 0.30
    independence_bonus: float = 0.25
    evidence_per_role: float = 0.05
    evidence_cap: float = 0.15
    # expansion signals have a long half-life (a new hub stays a live GTM trigger for
    # 6-12 months), so decay is gentler than for transactional signals.
    recency_floor: float = 0.80
    recency_full_days: int = 60
    recency_floor_days: int = 180
    emit_threshold: float = 0.60

    # logging
    log_level: str = "INFO"
    log_json: bool = False


settings = Settings()
