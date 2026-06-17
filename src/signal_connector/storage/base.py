"""Storage interface. SQLite impl today; the ABC keeps Postgres a drop-in later."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod

from signal_connector.models import Company, Observation
from signal_connector.schema import LocationExpansionSignal


class UpsertResult(enum.StrEnum):
    """Outcome of persisting one signal — drives the run summary + the 'DB grows' story."""

    NEW = "new"  # first time we've seen this company+location+month
    ENRICHED = "enriched"  # already known, but a new corroborating source arrived
    DEDUPED = "deduped"  # already known, nothing new — no-op


class Store(ABC):
    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def upsert_company(self, company: Company) -> None: ...

    @abstractmethod
    def add_observation(self, obs: Observation, run_id: str) -> None: ...

    @abstractmethod
    def upsert_signal(self, signal: LocationExpansionSignal) -> UpsertResult: ...

    @abstractmethod
    def signal_count(self) -> int: ...

    @abstractmethod
    def all_signals(self) -> list[LocationExpansionSignal]: ...

    @abstractmethod
    def record_run(self, run: dict) -> None: ...
