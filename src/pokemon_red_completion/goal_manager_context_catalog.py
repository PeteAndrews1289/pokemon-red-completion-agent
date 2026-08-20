"""Frozen path-free mapping from goal-manager slots to private Red contexts.

The public registry fixes the curriculum shape before private state access.
This second, private catalog fixes the exact captured state for every slot
before any counted action runs.  It contains only content digests and semantic
preflight facts, never filesystem locations, ROM bytes, outcomes, or labels
derived from execution.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from pathlib import Path

from pokemon_red_completion.captured_progress import (
    CapturedProgressEnvelope,
    parse_captured_progress,
)
from pokemon_red_completion.collection_protocol import collection_document_sha256
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerAssignment,
    GoalManagerCollectionRegistry,
)
from pokemon_red_completion.provenance import canonical_sha256

GOAL_MANAGER_CONTEXT_CATALOG_SCHEMA = "pokemon-red-goal-manager-context-catalog-v2"
GOAL_MANAGER_CONTEXT_ENTRY_SCHEMA = "pokemon-red-goal-manager-context-entry-v2"
_MINIMUM_MULTIWAY_TRAIN_CONTEXTS = 24
_MINIMUM_CONTEXT_DEPENDENT_TRAIN_MENUS = 3
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_MAX_CATALOG_BYTES = 4 * 1024 * 1024
_CAPTURE_VALIDATION_TOKEN = object()


class GoalManagerContextCatalogError(RuntimeError):
    """Raised when a context mapping is incomplete, mutable, or path-bearing."""


@dataclass(frozen=True, slots=True)
class GoalManagerContextCapture:
    """One exact private capture, constructible only by the verified opener."""

    capture_id: str
    state_sha256: str
    envelope_sha256: str
    envelope: CapturedProgressEnvelope
    state_bytes: bytes = field(repr=False)
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _CAPTURE_VALIDATION_TOKEN:
            raise GoalManagerContextCatalogError(
                "goal-manager captures must come from the verified opener"
            )


def open_goal_manager_context_capture(
    state_path: str | Path,
    envelope_path: str | Path,
) -> GoalManagerContextCapture:
    """Read and authenticate one capture exactly once, returning no path fields."""

    try:
        state_bytes = Path(state_path).read_bytes()
        envelope_bytes = Path(envelope_path).read_bytes()
    except OSError:
        raise GoalManagerContextCatalogError(
            "goal-manager context capture is unavailable"
        ) from None
    return parse_goal_manager_context_capture(state_bytes, envelope_bytes)


def parse_goal_manager_context_capture(
    state_bytes: bytes,
    envelope_bytes: bytes,
) -> GoalManagerContextCapture:
    """Authenticate retained bytes so execution and frozen digests share one read."""

    if not isinstance(state_bytes, bytes) or not isinstance(envelope_bytes, bytes):
        raise TypeError("goal-manager context capture inputs must be bytes")
    envelope = parse_captured_progress(envelope_bytes, state_bytes=state_bytes)
    return GoalManagerContextCapture(
        capture_id=envelope.checkpoint_id,
        state_sha256=envelope.state_sha256,
        envelope_sha256=hashlib.sha256(envelope_bytes).hexdigest(),
        envelope=envelope,
        state_bytes=state_bytes,
        _validation_token=_CAPTURE_VALIDATION_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class GoalManagerContextCatalogEntry:
    slot_id: str
    assignment_id: str
    capture_id: str
    state_sha256: str
    envelope_sha256: str
    question_sha256: str
    policy_context_sha256: str
    available_menu_sha256: str
    selected_candidate_index: int
    candidate_goal_kinds: tuple[GoalKind, ...]
    binding_manifest_sha256: str
    focus_pressure: float
    selected_kind: GoalKind
    available_goal_kinds: tuple[GoalKind, ...]
    context_id: str

    @property
    def root_lineage_id(self) -> str:
        """Return the canonical lineage frozen by the historical assignment."""

        return f"red-goal-root-{self.assignment_id}"

    def authenticated_root_lineage_id(
        self,
        *,
        slot_id: str,
        capture_id: str,
        state_sha256: str,
        envelope_sha256: str,
    ) -> str:
        """Resolve lineage only for the exact capture bytes represented here."""

        if (
            self.slot_id != slot_id
            or self.capture_id != capture_id
            or self.state_sha256 != state_sha256
            or self.envelope_sha256 != envelope_sha256
        ):
            raise GoalManagerContextCatalogError(
                "context catalog entry differs from the requested capture identity"
            )
        return self.root_lineage_id

    def __post_init__(self) -> None:
        for value, subject in (
            (self.slot_id, "slot identity"),
            (self.capture_id, "capture identity"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise GoalManagerContextCatalogError(f"{subject} is invalid")
        for value, subject in (
            (self.assignment_id, "assignment digest"),
            (self.state_sha256, "state digest"),
            (self.envelope_sha256, "envelope digest"),
            (self.question_sha256, "question digest"),
            (self.policy_context_sha256, "policy context digest"),
            (self.available_menu_sha256, "available menu digest"),
            (self.binding_manifest_sha256, "binding manifest digest"),
            (self.context_id, "context digest"),
        ):
            _digest(value, subject)
        if isinstance(self.focus_pressure, bool) or not isinstance(
            self.focus_pressure, (int, float)
        ):
            raise GoalManagerContextCatalogError("focus pressure must be numeric")
        if not 0.5 <= float(self.focus_pressure) <= 1.0:
            raise GoalManagerContextCatalogError(
                "focus pressure must meet the preregistered active threshold"
            )
        if not isinstance(self.selected_kind, GoalKind):
            raise GoalManagerContextCatalogError("selected goal kind is invalid")
        if (
            not isinstance(self.available_goal_kinds, tuple)
            or not self.available_goal_kinds
            or any(not isinstance(kind, GoalKind) for kind in self.available_goal_kinds)
            or len(set(self.available_goal_kinds)) != len(self.available_goal_kinds)
        ):
            raise GoalManagerContextCatalogError(
                "a context needs at least one unique available goal kind"
            )
        expected_order = tuple(
            kind for kind in GoalKind if kind in set(self.available_goal_kinds)
        )
        if self.available_goal_kinds != expected_order:
            raise GoalManagerContextCatalogError(
                "available goal kinds must use canonical semantic order"
            )
        if self.selected_kind not in self.available_goal_kinds:
            raise GoalManagerContextCatalogError(
                "selected goal kind must be available in its context"
            )
        if (
            type(self.selected_candidate_index) is not int  # noqa: E721
            or not 0 <= self.selected_candidate_index < len(self.candidate_goal_kinds)
        ):
            raise GoalManagerContextCatalogError(
                "selected candidate index is invalid"
            )
        if (
            not isinstance(self.candidate_goal_kinds, tuple)
            or len(self.candidate_goal_kinds) != len(GoalKind)
            or set(self.candidate_goal_kinds) != set(GoalKind)
            or self.candidate_goal_kinds[self.selected_candidate_index]
            is not self.selected_kind
        ):
            raise GoalManagerContextCatalogError("candidate goal order is invalid")
        if self.available_menu_sha256 != _available_menu_sha256(
            self.available_goal_kinds
        ):
            raise GoalManagerContextCatalogError(
                "available menu digest differs from its goal kinds"
            )
        if self.context_id != _context_id(
            slot_id=self.slot_id,
            assignment_id=self.assignment_id,
            capture_id=self.capture_id,
            state_sha256=self.state_sha256,
            envelope_sha256=self.envelope_sha256,
            question_sha256=self.question_sha256,
            policy_context_sha256=self.policy_context_sha256,
            available_menu_sha256=self.available_menu_sha256,
            selected_candidate_index=self.selected_candidate_index,
            candidate_goal_kinds=self.candidate_goal_kinds,
            binding_manifest_sha256=self.binding_manifest_sha256,
            focus_pressure=float(self.focus_pressure),
            selected_kind=self.selected_kind,
            available_goal_kinds=self.available_goal_kinds,
        ):
            raise GoalManagerContextCatalogError("context digest differs")

    @classmethod
    def build(
        cls,
        *,
        assignment: GoalManagerAssignment,
        capture_id: str,
        state_sha256: str,
        envelope_sha256: str,
        question_sha256: str,
        binding_manifest_sha256: str,
        focus_pressure: float,
        selected_kind: GoalKind,
        available_goal_kinds: tuple[GoalKind, ...],
        policy_context_sha256: str,
        available_menu_sha256: str,
        selected_candidate_index: int,
        candidate_goal_kinds: tuple[GoalKind, ...],
    ) -> GoalManagerContextCatalogEntry:
        ordered = tuple(kind for kind in GoalKind if kind in set(available_goal_kinds))
        context_id = _context_id(
            slot_id=assignment.slot_id,
            assignment_id=assignment.assignment_id,
            capture_id=capture_id,
            state_sha256=state_sha256,
            envelope_sha256=envelope_sha256,
            question_sha256=question_sha256,
            policy_context_sha256=policy_context_sha256,
            available_menu_sha256=available_menu_sha256,
            selected_candidate_index=selected_candidate_index,
            candidate_goal_kinds=candidate_goal_kinds,
            binding_manifest_sha256=binding_manifest_sha256,
            focus_pressure=focus_pressure,
            selected_kind=selected_kind,
            available_goal_kinds=ordered,
        )
        return cls(
            slot_id=assignment.slot_id,
            assignment_id=assignment.assignment_id,
            capture_id=capture_id,
            state_sha256=state_sha256,
            envelope_sha256=envelope_sha256,
            question_sha256=question_sha256,
            policy_context_sha256=policy_context_sha256,
            available_menu_sha256=available_menu_sha256,
            selected_candidate_index=selected_candidate_index,
            candidate_goal_kinds=candidate_goal_kinds,
            binding_manifest_sha256=binding_manifest_sha256,
            focus_pressure=focus_pressure,
            selected_kind=selected_kind,
            available_goal_kinds=ordered,
            context_id=context_id,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": GOAL_MANAGER_CONTEXT_ENTRY_SCHEMA,
            "slot_id": self.slot_id,
            "assignment_id": self.assignment_id,
            "capture_id": self.capture_id,
            "state_sha256": self.state_sha256,
            "envelope_sha256": self.envelope_sha256,
            "question_sha256": self.question_sha256,
            "policy_context_sha256": self.policy_context_sha256,
            "available_menu_sha256": self.available_menu_sha256,
            "selected_candidate_index": self.selected_candidate_index,
            "candidate_goal_kinds": [kind.value for kind in self.candidate_goal_kinds],
            "binding_manifest_sha256": self.binding_manifest_sha256,
            "focus_pressure": self.focus_pressure,
            "selected_kind": self.selected_kind.value,
            "available_goal_kinds": [kind.value for kind in self.available_goal_kinds],
            "context_id": self.context_id,
        }


@dataclass(frozen=True, slots=True)
class GoalManagerContextCatalog:
    catalog_sha256: str
    collection_id: str
    registry_sha256: str
    source_bundle_sha256: str
    source_commit: str
    entries: tuple[GoalManagerContextCatalogEntry, ...]

    def entry(self, slot_id: str) -> GoalManagerContextCatalogEntry:
        try:
            return next(item for item in self.entries if item.slot_id == slot_id)
        except StopIteration as error:
            raise GoalManagerContextCatalogError("context catalog has no requested slot") from error

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-goal-manager-context-catalog-summary-v2",
            "catalog_sha256": self.catalog_sha256,
            "collection_id": self.collection_id,
            "registry_sha256": self.registry_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "context_count": len(self.entries),
            "unique_state_count": len({entry.state_sha256 for entry in self.entries}),
            "unique_question_count": len({entry.question_sha256 for entry in self.entries}),
            "unique_policy_context_count": len(
                {entry.policy_context_sha256 for entry in self.entries}
            ),
            "multiway_train_contexts": sum(
                len(entry.available_goal_kinds) >= 3
                for entry in self.entries
                if entry.slot_id and "-train-" in entry.slot_id
            ),
            "context_dependent_train_menus": _context_dependent_train_menu_count(
                self.entries
            ),
            "private_path_fields": 0,
        }


def build_goal_manager_context_catalog_payload(
    registry: GoalManagerCollectionRegistry,
    entries: tuple[GoalManagerContextCatalogEntry, ...],
) -> bytes:
    """Build canonical bytes only after all prospective contexts are present."""

    _validate_entries(registry, entries)
    source_commit = registry.execution.source_commit
    if source_commit is None:
        raise GoalManagerContextCatalogError("context catalog requires committed source")
    return _canonical_line(
        {
            "schema": GOAL_MANAGER_CONTEXT_CATALOG_SCHEMA,
            "collection_id": entries and registry.assignment(entries[0].slot_id).collection_id,
            "registry_sha256": registry.registry_sha256,
            "source_bundle_sha256": registry.execution.source_bundle_sha256,
            "source_commit": source_commit,
            "entries": [entry.public_dict() for entry in entries],
        }
    )


def parse_goal_manager_context_catalog(
    payload: bytes,
    registry: GoalManagerCollectionRegistry,
) -> GoalManagerContextCatalog:
    """Authenticate canonical catalog bytes against the exact committed registry."""

    if not isinstance(payload, bytes):
        raise TypeError("goal-manager context catalog must be bytes")
    if not payload or len(payload) > _MAX_CATALOG_BYTES:
        raise GoalManagerContextCatalogError("goal-manager context catalog size is invalid")
    try:
        document = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise GoalManagerContextCatalogError(
            "goal-manager context catalog is not canonical ASCII JSON"
        ) from None
    if not isinstance(document, dict) or _canonical_line(document) != payload:
        raise GoalManagerContextCatalogError(
            "goal-manager context catalog is not canonical ASCII JSON"
        )
    _exact_keys(
        document,
        {
            "schema",
            "collection_id",
            "registry_sha256",
            "source_bundle_sha256",
            "source_commit",
            "entries",
        },
        "context catalog",
    )
    source_commit = registry.execution.source_commit
    if source_commit is None:
        raise GoalManagerContextCatalogError("context catalog requires committed source")
    first_assignment = registry.assignment(registry.slots[0].slot_id)
    expected = {
        "schema": GOAL_MANAGER_CONTEXT_CATALOG_SCHEMA,
        "collection_id": first_assignment.collection_id,
        "registry_sha256": registry.registry_sha256,
        "source_bundle_sha256": registry.execution.source_bundle_sha256,
        "source_commit": source_commit,
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise GoalManagerContextCatalogError("context catalog source identity differs")
    rows = document.get("entries")
    if not isinstance(rows, list):
        raise GoalManagerContextCatalogError("context catalog entries must be a list")
    entries = tuple(_parse_entry(row) for row in rows)
    _validate_entries(registry, entries)
    return GoalManagerContextCatalog(
        catalog_sha256=hashlib.sha256(payload).hexdigest(),
        collection_id=first_assignment.collection_id,
        registry_sha256=registry.registry_sha256,
        source_bundle_sha256=registry.execution.source_bundle_sha256,
        source_commit=source_commit,
        entries=entries,
    )


def goal_manager_catalog_episode_metadata(
    assignment: GoalManagerAssignment,
    catalog: GoalManagerContextCatalog,
) -> dict[str, object]:
    """Bind the frozen context catalog and entry into an episode header."""

    if assignment.source_commit != catalog.source_commit:
        raise GoalManagerContextCatalogError("assignment and context catalog commits differ")
    entry = catalog.entry(assignment.slot_id)
    if entry.assignment_id != assignment.assignment_id:
        raise GoalManagerContextCatalogError("assignment and context entry differ")
    metadata = assignment.episode_metadata()
    raw_goal = metadata.get("goal_manager")
    if not isinstance(raw_goal, Mapping):  # pragma: no cover - assignment constructs it
        raise GoalManagerContextCatalogError("assignment goal metadata is invalid")
    goal = dict(raw_goal)
    goal.update(
        {
            "binding_manifest_sha256": entry.binding_manifest_sha256,
            "context_catalog_sha256": catalog.catalog_sha256,
            "context_id": entry.context_id,
            "state_sha256": entry.state_sha256,
            "envelope_sha256": entry.envelope_sha256,
        }
    )
    metadata["goal_manager"] = goal
    return metadata


def _parse_entry(value: object) -> GoalManagerContextCatalogEntry:
    if not isinstance(value, dict):
        raise GoalManagerContextCatalogError("context catalog entry must be an object")
    _exact_keys(
        value,
        {
            "schema",
            "slot_id",
            "assignment_id",
            "capture_id",
            "state_sha256",
            "envelope_sha256",
            "question_sha256",
            "policy_context_sha256",
            "available_menu_sha256",
            "selected_candidate_index",
            "candidate_goal_kinds",
            "binding_manifest_sha256",
            "focus_pressure",
            "selected_kind",
            "available_goal_kinds",
            "context_id",
        },
        "context catalog entry",
    )
    if value.get("schema") != GOAL_MANAGER_CONTEXT_ENTRY_SCHEMA:
        raise GoalManagerContextCatalogError("context catalog entry schema differs")
    try:
        selected = GoalKind(value["selected_kind"])
        raw_available = value["available_goal_kinds"]
        raw_candidates = value["candidate_goal_kinds"]
        if not isinstance(raw_available, list) or not isinstance(raw_candidates, list):
            raise TypeError
        available = tuple(GoalKind(item) for item in raw_available)
        candidates = tuple(GoalKind(item) for item in raw_candidates)
    except (KeyError, TypeError, ValueError):
        raise GoalManagerContextCatalogError("context catalog goal kinds are invalid") from None
    return GoalManagerContextCatalogEntry(
        slot_id=_string(value.get("slot_id"), "slot identity"),
        assignment_id=_string(value.get("assignment_id"), "assignment digest"),
        capture_id=_string(value.get("capture_id"), "capture identity"),
        state_sha256=_string(value.get("state_sha256"), "state digest"),
        envelope_sha256=_string(value.get("envelope_sha256"), "envelope digest"),
        question_sha256=_string(value.get("question_sha256"), "question digest"),
        policy_context_sha256=_string(
            value.get("policy_context_sha256"),
            "policy context digest",
        ),
        available_menu_sha256=_string(
            value.get("available_menu_sha256"),
            "available menu digest",
        ),
        selected_candidate_index=_integer(
            value.get("selected_candidate_index"),
            "selected candidate index",
        ),
        candidate_goal_kinds=candidates,
        binding_manifest_sha256=_string(
            value.get("binding_manifest_sha256"),
            "binding manifest digest",
        ),
        focus_pressure=_number(value.get("focus_pressure"), "focus pressure"),
        selected_kind=selected,
        available_goal_kinds=available,
        context_id=_string(value.get("context_id"), "context digest"),
    )


def _validate_entries(
    registry: GoalManagerCollectionRegistry,
    entries: tuple[GoalManagerContextCatalogEntry, ...],
) -> None:
    if not isinstance(registry, GoalManagerCollectionRegistry):
        raise TypeError("registry must be a GoalManagerCollectionRegistry")
    if not isinstance(entries, tuple) or any(
        not isinstance(entry, GoalManagerContextCatalogEntry) for entry in entries
    ):
        raise GoalManagerContextCatalogError("context catalog entries must be immutable")
    expected_slots = tuple(slot.slot_id for slot in registry.slots)
    if tuple(entry.slot_id for entry in entries) != expected_slots:
        raise GoalManagerContextCatalogError(
            "context catalog must cover every registry slot in exact order"
        )
    for entry in entries:
        assignment = registry.assignment(entry.slot_id)
        if (
            entry.assignment_id != assignment.assignment_id
            or entry.selected_kind is not assignment.focus_kind
        ):
            raise GoalManagerContextCatalogError(
                "context entry differs from its prospective assignment"
            )
    for values, subject in (
        ((entry.capture_id for entry in entries), "capture identity"),
        ((entry.state_sha256 for entry in entries), "captured state"),
        ((entry.envelope_sha256 for entry in entries), "capture envelope"),
        ((entry.question_sha256 for entry in entries), "policy question"),
        ((entry.policy_context_sha256 for entry in entries), "policy context"),
        ((entry.context_id for entry in entries), "context identity"),
    ):
        materialized = tuple(values)
        if len(materialized) != len(set(materialized)):
            raise GoalManagerContextCatalogError(
                f"context catalog repeats a {subject}"
            )
    train_entries = tuple(
        entry
        for entry in entries
        if registry.assignment(entry.slot_id).partition == "train"
    )
    multiway = sum(len(entry.available_goal_kinds) >= 3 for entry in train_entries)
    if multiway < _MINIMUM_MULTIWAY_TRAIN_CONTEXTS:
        raise GoalManagerContextCatalogError(
            "context catalog has insufficient multiway training contexts"
        )
    if (
        _context_dependent_train_menu_count(train_entries)
        < _MINIMUM_CONTEXT_DEPENDENT_TRAIN_MENUS
    ):
        raise GoalManagerContextCatalogError(
            "context catalog has insufficient context-dependent training menus"
        )
    if len({entry.selected_candidate_index for entry in train_entries}) < 2:
        raise GoalManagerContextCatalogError(
            "context catalog lacks selected candidate position diversity"
        )


def _context_id(
    *,
    slot_id: str,
    assignment_id: str,
    capture_id: str,
    state_sha256: str,
    envelope_sha256: str,
    question_sha256: str,
    policy_context_sha256: str,
    available_menu_sha256: str,
    selected_candidate_index: int,
    candidate_goal_kinds: tuple[GoalKind, ...],
    binding_manifest_sha256: str,
    focus_pressure: float,
    selected_kind: GoalKind,
    available_goal_kinds: tuple[GoalKind, ...],
) -> str:
    return collection_document_sha256(
        {
            "schema": GOAL_MANAGER_CONTEXT_ENTRY_SCHEMA,
            "slot_id": slot_id,
            "assignment_id": assignment_id,
            "capture_id": capture_id,
            "state_sha256": state_sha256,
            "envelope_sha256": envelope_sha256,
            "question_sha256": question_sha256,
            "policy_context_sha256": policy_context_sha256,
            "available_menu_sha256": available_menu_sha256,
            "selected_candidate_index": selected_candidate_index,
            "candidate_goal_kinds": [kind.value for kind in candidate_goal_kinds],
            "binding_manifest_sha256": binding_manifest_sha256,
            "focus_pressure": focus_pressure,
            "selected_kind": selected_kind.value,
            "available_goal_kinds": [kind.value for kind in available_goal_kinds],
        }
    )


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _exact_keys(value: dict[str, object], expected: set[str], subject: str) -> None:
    if set(value) != expected:
        raise GoalManagerContextCatalogError(f"{subject} fields differ")


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str):
        raise GoalManagerContextCatalogError(f"{subject} must be a string")
    return value


def _number(value: object, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoalManagerContextCatalogError(f"{subject} must be numeric")
    return float(value)


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise GoalManagerContextCatalogError(f"{subject} must be a non-negative integer")
    return value


def _available_menu_sha256(kinds: tuple[GoalKind, ...]) -> str:
    return canonical_sha256(
        {
            "available_goal_kinds": sorted(kind.value for kind in kinds),
            "schema": "pokemon.core.available-goal-menu.v1",
        }
    )


def _context_dependent_train_menu_count(
    entries: tuple[GoalManagerContextCatalogEntry, ...],
) -> int:
    targets: dict[str, set[GoalKind]] = {}
    for entry in entries:
        if "-train-" not in entry.slot_id:
            continue
        targets.setdefault(entry.available_menu_sha256, set()).add(entry.selected_kind)
    return sum(len(kinds) >= 2 for kinds in targets.values())


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise GoalManagerContextCatalogError(f"{subject} must be a SHA-256 digest")
    return value
