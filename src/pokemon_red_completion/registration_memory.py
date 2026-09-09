"""Durable registration memory, independent of living stock and model weights.

Only an authenticated observation adapter should call ``record``. Digests bind
records to caller-verified evidence; they do NOT authenticate a ROM or prove that
an arbitrary caller actually played. No public receipt or model prediction is an
import source. Evaluation callers must freeze ``snapshot()`` before their run.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .collection import CollectionObservation

SCHEMA = "pokemon.shared-registration.v1"
_ID = re.compile(r"[a-z0-9][a-z0-9:._-]{0,159}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _species(values: object) -> frozenset[int]:
    if not isinstance(values, (tuple, list, frozenset, set)):
        raise ValueError("species must be a collection of National identifiers")
    if any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("National identifiers must be positive integers")
    if len(values) != len(set(values)):
        raise ValueError("duplicate species identifier")
    return frozenset(values)


def _encode(document: dict) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class RegistrationObservation:
    """One complete adapter observation, not a guessed acquisition method.

    ``sequence`` is a caller-assigned monotonic observation number within a run.
    Reimport order cannot replace the latest local state with an older state.
    A restored earlier save may have fewer local flags; global history persists.
    """

    run_id: str
    game_id: str
    adapter_id: str
    cartridge_sha256: str
    snapshot_sha256: str
    sequence: int
    seen: frozenset[int]
    owned: frozenset[int]
    physical_counts: Mapping[int, int]

    def __post_init__(self) -> None:
        for value in (self.run_id, self.game_id, self.adapter_id):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError("identities must be path-free identifiers")
        for value in (self.cartridge_sha256, self.snapshot_sha256):
            if not isinstance(value, str) or not _SHA.fullmatch(value):
                raise ValueError("evidence identities must be SHA-256 digests")
        if type(self.sequence) is not int or not 0 <= self.sequence < 2**63:
            raise ValueError("sequence must be a nonnegative signed-64-bit integer")
        object.__setattr__(self, "seen", _species(self.seen))
        object.__setattr__(self, "owned", _species(self.owned))
        if not self.owned <= self.seen:
            raise ValueError("owned registration must also be seen")
        if not isinstance(self.physical_counts, Mapping):
            raise ValueError("physical counts must be a mapping")
        _species(tuple(self.physical_counts))
        counts = dict(self.physical_counts)
        if any(type(count) is not int or count <= 0 for count in counts.values()):
            raise ValueError("physical counts must be positive integers")
        if not counts.keys() <= self.owned:
            raise ValueError("physical stock requires actual local registration")
        object.__setattr__(self, "physical_counts", MappingProxyType(counts))

    def document(self) -> dict:
        return {
            "schema": SCHEMA, "run_id": self.run_id, "game_id": self.game_id,
            "adapter_id": self.adapter_id, "cartridge_sha256": self.cartridge_sha256,
            "snapshot_sha256": self.snapshot_sha256, "sequence": self.sequence,
            "seen": sorted(self.seen), "owned": sorted(self.owned),
            "physical_counts": [[s, n] for s, n in sorted(self.physical_counts.items())],
        }

    @property
    def sha256(self) -> str:
        return _digest(_encode(self.document()))


def observation_from_collection(
    collection: CollectionObservation,
    *,
    seen_species: frozenset[str],
    national_ids: Mapping[str, int],
    run_id: str,
    game_id: str,
    adapter_id: str,
    cartridge_sha256: str,
    snapshot_sha256: str,
    sequence: int,
) -> RegistrationObservation:
    """Bridge existing semantic inventory without inferring global/local flags.

    The adapter supplies an explicit, bijective namespace mapping. In particular,
    cartridge-internal indices must never be mistaken for National Dex numbers.
    """
    national_ids = dict(national_ids)
    if any(not isinstance(key, str) or not key for key in national_ids):
        raise ValueError("adapter species references must be nonempty strings")
    _species(tuple(national_ids.values()))
    counts = Counter(specimen.species_ref for specimen in collection.specimens)
    required = set(seen_species) | set(collection.owned_species) | counts.keys()
    if not required <= national_ids.keys():
        raise ValueError("adapter mapping is missing an observed species")
    return RegistrationObservation(
        run_id, game_id, adapter_id, cartridge_sha256, snapshot_sha256, sequence,
        frozenset(national_ids[s] for s in seen_species),
        frozenset(national_ids[s] for s in collection.owned_species),
        {national_ids[s]: n for s, n in counts.items()},
    )


def _decode(payload: str, expected: str) -> RegistrationObservation:
    if _digest(payload) != expected:
        raise ValueError("registration evidence digest mismatch")
    data = json.loads(payload)
    if not isinstance(data, dict) or data.pop("schema", None) != SCHEMA:
        raise ValueError("unsupported registration evidence schema")
    pairs = data.pop("physical_counts", None)
    if (not isinstance(pairs, list)
            or any(not isinstance(p, list) or len(p) != 2 for p in pairs)):
        raise ValueError("invalid physical stock record")
    _species([p[0] for p in pairs])
    try:
        observation = RegistrationObservation(**data, physical_counts=dict(pairs))
    except TypeError as exc:
        raise ValueError("invalid registration evidence fields") from exc
    if _encode(observation.document()) != payload:
        raise ValueError("registration evidence must be canonical")
    return observation


@dataclass(frozen=True, slots=True)
class RegistrationSnapshot:
    """Frozen memory for reproducible planning/evaluation; no live DB handle."""

    observations: tuple[RegistrationObservation, ...]

    def __post_init__(self) -> None:
        rows = tuple(self.observations)
        if any(not isinstance(row, RegistrationObservation) for row in rows):
            raise ValueError("snapshot requires typed registration observations")
        if len({(row.run_id, row.sequence) for row in rows}) != len(rows):
            raise ValueError("snapshot repeats a run sequence")
        bindings: dict[str, tuple[str, str, str]] = {}
        for row in rows:
            binding = row.game_id, row.adapter_id, row.cartridge_sha256
            if row.run_id in bindings and bindings[row.run_id] != binding:
                raise ValueError("run identity changed cartridge or adapter")
            bindings[row.run_id] = binding
        object.__setattr__(self, "observations", tuple(sorted(
            rows, key=lambda row: (row.run_id, row.sequence),
        )))

    @property
    def registered(self) -> frozenset[int]:
        return frozenset(s for row in self.observations for s in row.owned)

    def latest(self, run_id: str) -> RegistrationObservation | None:
        return max((row for row in self.observations if row.run_id == run_id),
                   key=lambda row: row.sequence, default=None)

    def export_json(self) -> str:
        """Readable, path-free export; callers publish atomically if writing a file."""
        return json.dumps({
            "schema": SCHEMA, "registered": sorted(self.registered),
            "observations": [row.document() for row in self.observations],
        }, sort_keys=True, indent=2) + "\n"

    @property
    def sha256(self) -> str:
        return _digest(self.export_json())


@dataclass(frozen=True, slots=True)
class RegistrationImport:
    inserted: bool
    new_global_species: frozenset[int]


class RegistrationMemory:
    """Append-only SQLite store. Each operation owns and closes its connection.

    Immediate transactions serialize import/novelty attribution across workers.
    SQLite rollback journaling and FULL synchronization protect interrupted writes.
    The caller owns file permissions and backup of this private database.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if tables and (tables != {"registrations"} or version != 1):
                raise ValueError("not a supported registration database")
            if not tables:
                if version != 0:
                    raise ValueError("unsupported registration database version")
                connection.execute(
                    "CREATE TABLE registrations (run_id TEXT NOT NULL, "
                    "sequence INTEGER NOT NULL, digest TEXT NOT NULL UNIQUE, "
                    "payload TEXT NOT NULL, PRIMARY KEY (run_id, sequence))"
                )
                connection.execute("PRAGMA user_version=1")
        self.snapshot()  # Reject damaged existing evidence before accepting more.

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # sqlite3's connection context manager commits/rolls back but does not close.
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _snapshot(connection: sqlite3.Connection) -> RegistrationSnapshot:
        observations = []
        for run_id, sequence, digest, payload in connection.execute(
            "SELECT run_id, sequence, digest, payload FROM registrations "
            "ORDER BY run_id, sequence"
        ):
            row = _decode(payload, digest)
            if (row.run_id, row.sequence) != (run_id, sequence):
                raise ValueError("registration index differs from evidence")
            observations.append(row)
        return RegistrationSnapshot(tuple(observations))

    def snapshot(self) -> RegistrationSnapshot:
        with self._connection() as connection:
            return self._snapshot(connection)

    def record(self, observation: RegistrationObservation) -> RegistrationImport:
        if not isinstance(observation, RegistrationObservation):
            raise TypeError("record requires an adapter registration observation")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = self._snapshot(connection)
            for row in previous.observations:
                if row.run_id != observation.run_id:
                    continue
                if ((row.game_id, row.adapter_id, row.cartridge_sha256)
                        != (observation.game_id, observation.adapter_id,
                            observation.cartridge_sha256)):
                    raise ValueError("run identity changed cartridge or adapter")
                if row.sequence == observation.sequence:
                    if row.sha256 != observation.sha256:
                        raise ValueError("conflicting observation at the same run sequence")
                    return RegistrationImport(False, frozenset())
            connection.execute("INSERT INTO registrations VALUES (?, ?, ?, ?)", (
                observation.run_id, observation.sequence, observation.sha256,
                _encode(observation.document()),
            ))
            return RegistrationImport(True, observation.owned - previous.registered)
