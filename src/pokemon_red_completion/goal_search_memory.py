"""Observed search effort, separate from availability and learned predictions.

Private source/target keys never enter the policy projection. A legacy save has
unknown earlier history; zero tracked attempts must not mean a never-tried area.
This module neither selects an action nor declares an exhausted source impossible.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.collection_training_cost import CollectionTrainingCost

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

    _movement_visits: set[str] = field(default_factory=set, init=False, repr=False)

    _movement_returns: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    _costly_search_failures: dict[str, tuple[int, int]] = field(default_factory=dict, init=False, repr=False)

    _collection_training: dict[str, CollectionTrainingCost] = field(default_factory=dict, init=False, repr=False)

    def collection_training_cost(self, key: str) -> CollectionTrainingCost | None:
        if not isinstance(key, str) or _SHA.fullmatch(key) is None:
            raise ValueError("invalid collection training context")
        return self._collection_training.get(key)

    def record_collection_training_cost(self, key: str, observed: CollectionTrainingCost) -> None:
        previous = self.collection_training_cost(key)
        if type(observed) is not CollectionTrainingCost or observed.attempts != 1:
            raise ValueError("a collection training observation must close one attempt")
        if previous is None and len(self._collection_training) >= _MAX_ENTRIES:
            raise ValueError("collection training memory capacity exceeded")
        self._collection_training[key] = observed if previous is None else previous.plus(observed)

    def costly_search_seen(self, source: str, objective: str, progress: str, cash: int) -> bool:
        if type(cash) is not int or not 0 <= cash <= 999999:
            raise ValueError("costly search cash differs")
        value = self._costly_search_failures.get(_key(_key(source, objective), progress))
        return value is not None and value[0] >= 2 and cash <= value[1]

    def record_costly_search_failure(self, source: str, objective: str, progress: str, cash: int) -> None:
        if type(cash) is not int or not 0 <= cash <= 999999:
            raise ValueError("costly search cash differs")
        key = _key(_key(source, objective), progress)
        if key not in self._costly_search_failures and len(self._costly_search_failures) >= _MAX_ENTRIES:
            raise ValueError("costly search capacity exceeded")
        count, low = self._costly_search_failures.get(key, (0, cash))
        if count >= _MAX_COUNTER:
            raise ValueError("costly search counter exceeded")
        self._costly_search_failures[key] = (count + 1, min(low, cash))

    def record_movement_return(self, source_sha256: str, endpoint_sha256: str,
                               progress_sha256: str) -> int:
        """Count an actually executed unchanged return, never a quoted option."""
        key = _key(_key(source_sha256, endpoint_sha256), progress_sha256)
        if key not in self._movement_returns and len(self._movement_returns) >= _MAX_ENTRIES:
            raise ValueError("movement return memory capacity exceeded")
        count = self._movement_returns.get(key, 0) + 1
        if count > _MAX_COUNTER:
            raise ValueError("movement return counter exceeded")
        self._movement_returns[key] = count
        return count

    def movement_endpoint_seen(self, endpoint_sha256: str, progress_sha256: str) -> bool:
        return _key(endpoint_sha256, progress_sha256) in self._movement_visits

    def observe_movement_endpoint(self, endpoint_sha256: str, progress_sha256: str) -> None:
        key = _key(endpoint_sha256, progress_sha256)
        if key not in self._movement_visits and len(self._movement_visits) >= _MAX_ENTRIES:
            raise ValueError("movement observation memory capacity exceeded")
        self._movement_visits.add(key)

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
        }, **({"movement_visits": sorted(self._movement_visits)} if self._movement_visits else {}),
                **({"movement_returns": dict(sorted(self._movement_returns.items()))}
                   if self._movement_returns else {}),
                **({"costly_search_failures": {k: list(v) for k, v in sorted(self._costly_search_failures.items())}}
                   if self._costly_search_failures else {}),
                **({"collection_training": {k: asdict(v) for k, v in sorted(self._collection_training.items())}}
                   if self._collection_training else {})}

    def require_extension(self, previous: GoalSearchMemory) -> None:
        """A child save cannot quietly forget or reduce authenticated effort."""
        for key, old in previous._collection_training.items():
            current_cost = self._collection_training.get(key)
            if current_cost is None:
                raise ValueError("continued collection training memory lost an observation")
            current_cost.require_extension(old)
        if not previous._movement_visits <= self._movement_visits:
            raise ValueError("continued movement memory lost an observation")
        if any(self._movement_returns.get(key, 0) < count
               for key, count in previous._movement_returns.items()):
            raise ValueError("continued movement memory lost a return")
        for key, (count, low) in previous._costly_search_failures.items():
            current = self._costly_search_failures.get(key)
            if current is None or current[0] < count or current[1] > low or (
                    current[0] == count and current[1] != low):
                raise ValueError("continued costly search memory lost an observation")
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
        if not isinstance(value, Mapping) or not {"schema", "entries"} <= set(value) <= {"schema", "entries", "movement_visits", "movement_returns", "costly_search_failures", "collection_training"} or (
            value["schema"] != SEARCH_MEMORY_SCHEMA
        ):
            raise ValueError("search memory schema differs")
        entries = value["entries"]
        if not isinstance(entries, Mapping) or len(entries) > _MAX_ENTRIES:
            raise ValueError("search memory entries differ")
        result = cls()
        training = value.get("collection_training", {})
        if not isinstance(training, Mapping) or len(training) > _MAX_ENTRIES:
            raise ValueError("invalid collection training memory")
        for key, entry in training.items():
            if (not isinstance(key, str) or _SHA.fullmatch(key) is None or not isinstance(entry, dict)
                    or set(entry) != set(CollectionTrainingCost.__dataclass_fields__)):
                raise ValueError("invalid collection training entry")
            observed = CollectionTrainingCost(**entry)
            if observed.attempts == 0:
                raise ValueError("empty collection training entry")
            result._collection_training[key] = observed
        visits = value.get("movement_visits", [])
        if (type(visits) is not list or len(visits) > _MAX_ENTRIES
                or any(type(k) is not str or _SHA.fullmatch(k) is None for k in visits)
                or visits != sorted(set(visits))):
            raise ValueError("movement memory observations differ")
        result._movement_visits.update(visits)
        returns = value.get("movement_returns", {})
        if (not isinstance(returns, Mapping) or len(returns) > _MAX_ENTRIES
                or any(type(k) is not str or _SHA.fullmatch(k) is None
                       or type(v) is not int or not 1 <= v <= _MAX_COUNTER
                       for k, v in returns.items())):
            raise ValueError("movement return observations differ")
        result._movement_returns.update(returns)
        costly = value.get("costly_search_failures", {})
        if (not isinstance(costly, Mapping) or len(costly) > _MAX_ENTRIES
                or any(type(k) is not str or _SHA.fullmatch(k) is None
                       or type(v) is not list or len(v) != 2
                       or type(v[0]) is not int or not 1 <= v[0] <= _MAX_COUNTER
                       or type(v[1]) is not int or not 0 <= v[1] <= 999999
                       for k, v in costly.items())):
            raise ValueError("costly search observations differ")
        result._costly_search_failures.update({k: tuple(v) for k, v in costly.items()})
        for key, row in entries.items():
            if not isinstance(key, str) or _SHA.fullmatch(key) is None:
                raise ValueError("search memory key differs")
            history = GoalSearchHistory.from_public_dict(row)
            if history.attempts == 0:
                raise ValueError("search memory cannot store an unexecuted search")
            result._entries[key] = history
        return result
