"""Observed search effort, separate from availability and learned predictions.

Private source/target keys never enter the policy projection. A legacy save has
unknown earlier history; zero tracked attempts must not mean a never-tried area.
This module neither selects an action nor declares an exhausted source impossible.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.provenance import canonical_sha256

SEARCH_HISTORY_SCHEMA = "pokemon.core.search-history.v1"
SEARCH_MEMORY_SCHEMA = "pokemon.core.private-search-memory.v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_COUNTER = 2**53 - 1
_MAX_ENTRIES = 4096


@dataclass(frozen=True, slots=True)
class GoalSearchHistory:
    """Measured effort since tracking started, not a counterfactual outcome."""

    attempts: int = 0
    exhausted: int = 0
    actions: int = 0
    frames: int = 0

    def __post_init__(self) -> None:
        if any(type(x) is not int or not 0 <= x <= _MAX_COUNTER for x in (
            self.attempts, self.exhausted, self.actions, self.frames,
        )):
            raise ValueError("search history counters differ")
        if self.exhausted > self.attempts or (
            self.attempts == 0 and (self.actions or self.frames)
        ) or (self.attempts > 0 and self.actions < self.attempts):
            raise ValueError("search history accounting differs")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": SEARCH_HISTORY_SCHEMA,
            "coverage": "since_tracking_started",
            "earlier_history_known": False,
            "attempts": self.attempts, "exhausted": self.exhausted,
            "actions": self.actions, "frames": self.frames,
        }

    @classmethod
    def from_public_dict(cls, value: object) -> GoalSearchHistory:
        if not isinstance(value, Mapping) or set(value) != {
            "schema", "coverage", "earlier_history_known", "attempts", "exhausted",
            "actions", "frames",
        } or value["schema"] != SEARCH_HISTORY_SCHEMA or (
            value["coverage"] != "since_tracking_started"
            or value["earlier_history_known"] is not False
        ):
            raise ValueError("search history schema differs")
        return cls(**{name: value[name] for name in ("attempts", "exhausted", "actions", "frames")})


def _key(source_ref: str, objective_sha256: str) -> str:
    if not isinstance(source_ref, str) or not source_ref or (
        not isinstance(objective_sha256, str) or _SHA.fullmatch(objective_sha256) is None
    ):
        raise ValueError("search memory private context differs")
    return canonical_sha256({"source": source_ref, "objective": objective_sha256})


@dataclass(slots=True)
class GoalSearchMemory:
    """Bounded private lookup; persisted only with an authenticated checkpoint."""

    _entries: dict[str, GoalSearchHistory] = field(default_factory=dict, init=False, repr=False)

    def lookup(self, source_ref: str, objective_sha256: str) -> GoalSearchHistory:
        return self._entries.get(_key(source_ref, objective_sha256), GoalSearchHistory())

    def record(
        self, source_ref: str, objective_sha256: str, *, exhausted: bool,
        actions: int, frames: int,
    ) -> None:
        if type(exhausted) is not bool or type(actions) is not int or actions <= 0:
            raise ValueError("search memory needs an executed settled search")
        key = _key(source_ref, objective_sha256)
        if key not in self._entries and len(self._entries) >= _MAX_ENTRIES:
            raise ValueError("search memory capacity exceeded")
        prior = self.lookup(source_ref, objective_sha256)
        # Validate this increment independently: bool/negative frames must not
        # become an apparently valid cumulative total.
        GoalSearchHistory(1, int(exhausted), actions, frames)
        self._entries[key] = GoalSearchHistory(
            prior.attempts + 1, prior.exhausted + int(exhausted),
            prior.actions + actions, prior.frames + frames,
        )

    def private_dict(self) -> dict[str, object]:
        return {"schema": SEARCH_MEMORY_SCHEMA, "entries": {
            key: self._entries[key].public_dict() for key in sorted(self._entries)
        }}

    def require_extension(self, previous: GoalSearchMemory) -> None:
        """A child save cannot quietly forget or reduce authenticated effort."""
        for key, prior in previous._entries.items():
            current = self._entries.get(key)
            if current is None:
                raise ValueError("continued search memory lost a source")
            delta = (
                current.attempts - prior.attempts, current.exhausted - prior.exhausted,
                current.actions - prior.actions, current.frames - prior.frames,
            )
            GoalSearchHistory(*delta)

    @classmethod
    def from_private_dict(cls, value: object) -> GoalSearchMemory:
        if not isinstance(value, Mapping) or set(value) != {"schema", "entries"} or (
            value["schema"] != SEARCH_MEMORY_SCHEMA
        ):
            raise ValueError("search memory schema differs")
        entries = value["entries"]
        if not isinstance(entries, Mapping) or len(entries) > _MAX_ENTRIES:
            raise ValueError("search memory entries differ")
        result = cls()
        for key, row in entries.items():
            if not isinstance(key, str) or _SHA.fullmatch(key) is None:
                raise ValueError("search memory key differs")
            history = GoalSearchHistory.from_public_dict(row)
            if history.attempts == 0:
                raise ValueError("search memory cannot store an unexecuted search")
            result._entries[key] = history
        return result
