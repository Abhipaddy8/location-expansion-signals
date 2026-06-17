"""Build the active source list + company config from config/sources.yaml.

Adding a new source type to the demo = register its class here; adding a company = a
YAML entry. No other code changes.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from signal_connector.sources.ats import AshbySource, GreenhouseSource, LeverSource
from signal_connector.sources.base import BaseSource, CompanyConfig
from signal_connector.sources.feeds import EconDevSource, NewsSource, PressSource

_SOURCE_CLASSES: dict[str, type[BaseSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "ashby": AshbySource,
    "news": NewsSource,
    "press": PressSource,
    "econdev": EconDevSource,
}


def load_config(path: Path | str) -> tuple[list[BaseSource], list[CompanyConfig]]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    sources_cfg = raw.get("sources", {})
    sources: list[BaseSource] = []
    for name, cls in _SOURCE_CLASSES.items():
        entry = sources_cfg.get(name)
        # enabled by default if the source name appears with enabled != false
        if entry is None:
            continue
        if isinstance(entry, dict) and entry.get("enabled") is False:
            continue
        sources.append(cls())

    companies = [CompanyConfig.model_validate(c) for c in (raw.get("companies") or [])]
    return sources, companies
