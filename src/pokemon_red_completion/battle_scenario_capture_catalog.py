"""Canonical path-free catalog for battle captures from multiple producers.

The materialization campaign completed across two immutable generations.  This
contract preserves that fact instead of pretending that every capture came
from one source commit or directory.  It contains authenticated identities,
never filesystem paths, outcomes, predictions, or preferred actions.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pokemon_red_completion.battle_scenario_materialization_plan import (
    BattleScenarioPartySlot,
)

BATTLE_SCENARIO_CAPTURE_CATALOG_SCHEMA = "pokemon.red.private-battle-scenario-capture-catalog.v1"
BATTLE_SCENARIO_RETAINED_TRAIN_CAPTURE_CATALOG_SCHEMA = (
    "pokemon.red.private-battle-scenario-retained-train-capture-catalog.v1"
)
REQUIRED_CAPTURE_COUNT = 7
REQUIRED_RETAINED_TRAIN_CAPTURE_COUNT = 5
REQUIRED_PRODUCER_ROLES = ("predecessor", "completion")

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SAFE_FILENAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_MAXIMUM_CATALOG_BYTES = 2 * 1024 * 1024
_ZERO_EFFECTS = {
    "authority_promoted": False,
    "controller_actions": 0,
    "crystal_contexts_opened": 0,
    "emulator_frames": 0,
    "model_fits": 0,
    "move_choices_executed": 0,
    "outcomes_opened": 0,
    "predictions_computed": 0,
    "red_sealed_test_cases_opened": 0,
    "root_claims_created": 0,
    "teacher_choice_targets": 0,
    "teacher_queries": 0,
}


class BattleScenarioCaptureCatalogError(ValueError):
    """Raised when mixed-producer capture provenance can be flattened."""


@dataclass(frozen=True, slots=True)
class BattleScenarioCaptureProducer:
    """One immutable materialization plan and its terminal run identity."""

    producer_id: str
    role: str
    plan_id: str
    plan_sha256: str
    run_journal_sha256: str
    source_commit: str
    source_bundle_sha256: str
    materializer_sha256: str
    runtime_identity_sha256: str
    rom_sha256: str
    capture_directory_sha256: str
    context_catalog_sha256: str
    registry_sha256: str
    registry_source_commit: str
    exact_ci_run: int
    exact_ci_attempt: int
    successful_capture_count: int
    failed_assignment_count: int

    def __post_init__(self) -> None:
        for value, subject in (
            (self.producer_id, "producer identity"),
            (self.plan_id, "producer plan identity"),
        ):
            _require_safe_id(value, subject)
        if self.role not in REQUIRED_PRODUCER_ROLES:
            raise BattleScenarioCaptureCatalogError("producer role differs")
        for value, subject in (
            (self.plan_sha256, "producer plan"),
            (self.run_journal_sha256, "producer journal"),
            (self.source_bundle_sha256, "producer source bundle"),
            (self.materializer_sha256, "producer materializer"),
            (self.runtime_identity_sha256, "producer runtime"),
            (self.rom_sha256, "producer ROM"),
            (self.capture_directory_sha256, "producer capture directory"),
            (self.context_catalog_sha256, "producer context catalog"),
            (self.registry_sha256, "producer registry"),
        ):
            _require_sha256(value, subject)
        for value, subject in (
            (self.source_commit, "producer source"),
            (self.registry_source_commit, "producer registry source"),
        ):
            _require_commit(value, subject)
        for integer_value, subject in (
            (self.exact_ci_run, "producer CI run"),
            (self.exact_ci_attempt, "producer CI attempt"),
            (self.successful_capture_count, "producer success count"),
        ):
            if type(integer_value) is not int or integer_value <= 0:  # noqa: E721
                raise BattleScenarioCaptureCatalogError(f"{subject} differs")
        if type(self.failed_assignment_count) is not int or self.failed_assignment_count < 0:  # noqa: E721
            raise BattleScenarioCaptureCatalogError("producer failure count differs")
        expected = {
            "predecessor": (5, 2),
            "completion": (2, 0),
        }[self.role]
        if (self.successful_capture_count, self.failed_assignment_count) != expected:
            raise BattleScenarioCaptureCatalogError("producer terminal denominator differs")

    def private_dict(self) -> dict[str, object]:
        return {
            "capture_directory_sha256": self.capture_directory_sha256,
            "context_catalog_sha256": self.context_catalog_sha256,
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "failed_assignment_count": self.failed_assignment_count,
            "materializer_sha256": self.materializer_sha256,
            "plan_id": self.plan_id,
            "plan_sha256": self.plan_sha256,
            "producer_id": self.producer_id,
            "registry_sha256": self.registry_sha256,
            "registry_source_commit": self.registry_source_commit,
            "role": self.role,
            "rom_sha256": self.rom_sha256,
            "run_journal_sha256": self.run_journal_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "successful_capture_count": self.successful_capture_count,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioCaptureCatalogEntry:
    """One independently reopened successful output and its producer join."""

    ordinal: int
    producer_id: str
    producer_ordinal: int
    capture_id: str
    assignment_sha256: str
    source_state_sha256: str
    root_lineage_id: str
    venue_id: str
    party_slot: BattleScenarioPartySlot
    state_filename: str
    manifest_filename: str
    state_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or not 0 <= self.ordinal < REQUIRED_CAPTURE_COUNT:  # noqa: E721
            raise BattleScenarioCaptureCatalogError("capture catalog ordinal differs")
        if type(self.producer_ordinal) is not int or self.producer_ordinal < 0:  # noqa: E721
            raise BattleScenarioCaptureCatalogError("capture producer ordinal differs")
        for value, subject in (
            (self.producer_id, "capture producer"),
            (self.capture_id, "capture identity"),
            (self.root_lineage_id, "capture lineage"),
            (self.venue_id, "capture venue"),
        ):
            _require_safe_id(value, subject)
        for value, subject in (
            (self.assignment_sha256, "capture assignment"),
            (self.source_state_sha256, "capture source state"),
            (self.state_sha256, "capture state"),
            (self.manifest_sha256, "capture manifest"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.party_slot, BattleScenarioPartySlot):
            raise BattleScenarioCaptureCatalogError("capture party slot differs")
        for value, suffix, subject in (
            (self.state_filename, ".state", "capture state filename"),
            (self.manifest_filename, ".state.json", "capture manifest filename"),
        ):
            if _SAFE_FILENAME.fullmatch(value) is None or not value.endswith(suffix):
                raise BattleScenarioCaptureCatalogError(f"{subject} differs")
        if self.state_filename == self.manifest_filename:
            raise BattleScenarioCaptureCatalogError("capture filenames collide")

    def private_dict(self) -> dict[str, object]:
        return {
            "assignment_sha256": self.assignment_sha256,
            "capture_id": self.capture_id,
            "manifest_filename": self.manifest_filename,
            "manifest_sha256": self.manifest_sha256,
            "ordinal": self.ordinal,
            "party_slot": self.party_slot.private_dict(),
            "producer_id": self.producer_id,
            "producer_ordinal": self.producer_ordinal,
            "root_lineage_id": self.root_lineage_id,
            "source_state_sha256": self.source_state_sha256,
            "state_filename": self.state_filename,
            "state_sha256": self.state_sha256,
            "venue_id": self.venue_id,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioCaptureCatalog:
    """Exactly seven train inputs across the immutable five-plus-two history."""

    catalog_id: str
    builder_source_commit: str
    builder_source_bundle_sha256: str
    rom_sha256: str
    producers: tuple[BattleScenarioCaptureProducer, ...]
    captures: tuple[BattleScenarioCaptureCatalogEntry, ...]

    def __post_init__(self) -> None:
        _require_safe_id(self.catalog_id, "capture catalog identity")
        _require_commit(self.builder_source_commit, "catalog builder source")
        _require_sha256(self.builder_source_bundle_sha256, "catalog builder bundle")
        _require_sha256(self.rom_sha256, "catalog ROM")
        if (
            not isinstance(self.producers, tuple)
            or tuple(item.role for item in self.producers) != REQUIRED_PRODUCER_ROLES
            or any(not isinstance(item, BattleScenarioCaptureProducer) for item in self.producers)
            or len({item.producer_id for item in self.producers}) != 2
            or len({item.source_commit for item in self.producers}) != 2
            or len({item.capture_directory_sha256 for item in self.producers}) != 2
            or {item.rom_sha256 for item in self.producers} != {self.rom_sha256}
            or len({item.context_catalog_sha256 for item in self.producers}) != 1
            or len({item.registry_sha256 for item in self.producers}) != 1
            or len({item.registry_source_commit for item in self.producers}) != 1
        ):
            raise BattleScenarioCaptureCatalogError("capture producer catalog differs")
        if (
            not isinstance(self.captures, tuple)
            or len(self.captures) != REQUIRED_CAPTURE_COUNT
            or any(
                not isinstance(item, BattleScenarioCaptureCatalogEntry) for item in self.captures
            )
            or tuple(item.ordinal for item in self.captures) != tuple(range(REQUIRED_CAPTURE_COUNT))
        ):
            raise BattleScenarioCaptureCatalogError("capture catalog denominator differs")
        producer_counts = Counter(item.producer_id for item in self.captures)
        expected_counts = {
            item.producer_id: item.successful_capture_count for item in self.producers
        }
        if producer_counts != Counter(expected_counts):
            raise BattleScenarioCaptureCatalogError("capture producer membership differs")
        producer_ordinals = {
            producer.producer_id: tuple(
                item.producer_ordinal
                for item in self.captures
                if item.producer_id == producer.producer_id
            )
            for producer in self.producers
        }
        if any(
            len(ordinals) != len(set(ordinals))
            or any(
                not 0
                <= ordinal
                < producer.successful_capture_count + producer.failed_assignment_count
                for ordinal in ordinals
            )
            for producer in self.producers
            for ordinals in (producer_ordinals[producer.producer_id],)
        ):
            raise BattleScenarioCaptureCatalogError(
                "capture producer ordinal membership differs"
            )
        if any(
            len(values) != REQUIRED_CAPTURE_COUNT
            for values in (
                {item.capture_id for item in self.captures},
                {item.assignment_sha256 for item in self.captures},
                {item.source_state_sha256 for item in self.captures},
                {item.root_lineage_id for item in self.captures},
                {item.state_sha256 for item in self.captures},
                {item.manifest_sha256 for item in self.captures},
            )
        ):
            raise BattleScenarioCaptureCatalogError("capture catalog identity repeats")
        venue_counts = Counter(item.venue_id for item in self.captures)
        if venue_counts != Counter({"digletts_cave": 4, "route_11": 3}):
            raise BattleScenarioCaptureCatalogError("capture venue distribution differs")

    @property
    def catalog_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def private_dict(self) -> dict[str, object]:
        return {
            "builder_source_bundle_sha256": self.builder_source_bundle_sha256,
            "builder_source_commit": self.builder_source_commit,
            "captures": [item.private_dict() for item in self.captures],
            "catalog_id": self.catalog_id,
            "effects": _ZERO_EFFECTS,
            "historical_failed_assignments": 2,
            "producers": [item.private_dict() for item in self.producers],
            "rom_sha256": self.rom_sha256,
            "schema": BATTLE_SCENARIO_CAPTURE_CATALOG_SCHEMA,
            "status": "authenticated_action_free",
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.private_dict())


@dataclass(frozen=True, slots=True)
class BattleScenarioRetainedTrainCaptureCatalog:
    """The five authentic predecessor successes, without replacement inputs."""

    catalog_id: str
    builder_source_commit: str
    builder_source_bundle_sha256: str
    rom_sha256: str
    producer: BattleScenarioCaptureProducer
    captures: tuple[BattleScenarioCaptureCatalogEntry, ...]

    def __post_init__(self) -> None:
        _require_safe_id(self.catalog_id, "retained train catalog identity")
        _require_commit(self.builder_source_commit, "retained train catalog builder")
        _require_sha256(
            self.builder_source_bundle_sha256,
            "retained train catalog builder bundle",
        )
        _require_sha256(self.rom_sha256, "retained train catalog ROM")
        if (
            not isinstance(self.producer, BattleScenarioCaptureProducer)
            or self.producer.role != "predecessor"
            or self.producer.producer_id != "predecessor"
            or self.producer.successful_capture_count
            != REQUIRED_RETAINED_TRAIN_CAPTURE_COUNT
            or self.producer.failed_assignment_count != 2
            or self.producer.rom_sha256 != self.rom_sha256
        ):
            raise BattleScenarioCaptureCatalogError(
                "retained train producer differs"
            )
        if (
            not isinstance(self.captures, tuple)
            or len(self.captures) != REQUIRED_RETAINED_TRAIN_CAPTURE_COUNT
            or any(
                not isinstance(item, BattleScenarioCaptureCatalogEntry)
                or item.producer_id != self.producer.producer_id
                for item in self.captures
            )
            or tuple(item.ordinal for item in self.captures)
            != tuple(range(REQUIRED_RETAINED_TRAIN_CAPTURE_COUNT))
            or len({item.producer_ordinal for item in self.captures})
            != REQUIRED_RETAINED_TRAIN_CAPTURE_COUNT
            or any(not 0 <= item.producer_ordinal < 7 for item in self.captures)
        ):
            raise BattleScenarioCaptureCatalogError(
                "retained train catalog denominator differs"
            )
        identity_sets = (
            {item.capture_id for item in self.captures},
            {item.assignment_sha256 for item in self.captures},
            {item.source_state_sha256 for item in self.captures},
            {item.root_lineage_id for item in self.captures},
            {item.state_sha256 for item in self.captures},
            {item.manifest_sha256 for item in self.captures},
        )
        if any(
            len(values) != REQUIRED_RETAINED_TRAIN_CAPTURE_COUNT
            for values in identity_sets
        ):
            raise BattleScenarioCaptureCatalogError(
                "retained train catalog identity repeats"
            )
        if Counter(item.venue_id for item in self.captures) != Counter(
            {"digletts_cave": 4, "route_11": 1}
        ):
            raise BattleScenarioCaptureCatalogError(
                "retained train venue distribution differs"
            )

    @property
    def catalog_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def private_dict(self) -> dict[str, object]:
        return {
            "builder_source_bundle_sha256": self.builder_source_bundle_sha256,
            "builder_source_commit": self.builder_source_commit,
            "captures": [item.private_dict() for item in self.captures],
            "catalog_id": self.catalog_id,
            "effects": _ZERO_EFFECTS,
            "historical_failed_assignments": 2,
            "producer": self.producer.private_dict(),
            "rom_sha256": self.rom_sha256,
            "schema": BATTLE_SCENARIO_RETAINED_TRAIN_CAPTURE_CATALOG_SCHEMA,
            "status": "authenticated_action_free",
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.private_dict())


def build_battle_scenario_capture_catalog(
    *,
    catalog_id: str,
    builder_source_commit: str,
    builder_source_bundle_sha256: str,
    rom_sha256: str,
    producers: Sequence[BattleScenarioCaptureProducer],
    captures: Sequence[BattleScenarioCaptureCatalogEntry],
) -> BattleScenarioCaptureCatalog:
    """Build the canonical producer-then-producer seven-capture catalog."""

    if isinstance(producers, (str, bytes)) or not isinstance(producers, Sequence):
        raise TypeError("capture catalog producers must be a sequence")
    if isinstance(captures, (str, bytes)) or not isinstance(captures, Sequence):
        raise TypeError("capture catalog entries must be a sequence")
    if any(not isinstance(item, BattleScenarioCaptureCatalogEntry) for item in captures):
        raise BattleScenarioCaptureCatalogError("capture catalog entries differ")
    producer_tuple = tuple(producers)
    if (
        len(producer_tuple) != len(REQUIRED_PRODUCER_ROLES)
        or any(not isinstance(item, BattleScenarioCaptureProducer) for item in producer_tuple)
        or {item.role for item in producer_tuple} != set(REQUIRED_PRODUCER_ROLES)
        or len({item.producer_id for item in producer_tuple}) != len(REQUIRED_PRODUCER_ROLES)
    ):
        raise BattleScenarioCaptureCatalogError("capture producer catalog differs")
    by_role = {item.role: item for item in producer_tuple}
    ordered_producers = tuple(by_role[role] for role in REQUIRED_PRODUCER_ROLES)
    role_order = {item.producer_id: index for index, item in enumerate(ordered_producers)}
    ordered_entries = tuple(
        sorted(
            captures,
            key=lambda item: (
                role_order.get(item.producer_id, len(role_order)),
                item.producer_ordinal,
            ),
        )
    )
    normalized = tuple(
        BattleScenarioCaptureCatalogEntry(
            ordinal=index,
            producer_id=item.producer_id,
            producer_ordinal=item.producer_ordinal,
            capture_id=item.capture_id,
            assignment_sha256=item.assignment_sha256,
            source_state_sha256=item.source_state_sha256,
            root_lineage_id=item.root_lineage_id,
            venue_id=item.venue_id,
            party_slot=item.party_slot,
            state_filename=item.state_filename,
            manifest_filename=item.manifest_filename,
            state_sha256=item.state_sha256,
            manifest_sha256=item.manifest_sha256,
        )
        for index, item in enumerate(ordered_entries)
    )
    return BattleScenarioCaptureCatalog(
        catalog_id=catalog_id,
        builder_source_commit=builder_source_commit,
        builder_source_bundle_sha256=builder_source_bundle_sha256,
        rom_sha256=rom_sha256,
        producers=ordered_producers,
        captures=normalized,
    )


def build_battle_scenario_retained_train_capture_catalog(
    *,
    catalog_id: str,
    builder_source_commit: str,
    builder_source_bundle_sha256: str,
    rom_sha256: str,
    producer: BattleScenarioCaptureProducer,
    captures: Sequence[BattleScenarioCaptureCatalogEntry],
) -> BattleScenarioRetainedTrainCaptureCatalog:
    """Build one immutable catalog from all five predecessor successes."""

    if isinstance(captures, (str, bytes)) or not isinstance(captures, Sequence):
        raise TypeError("retained train catalog entries must be a sequence")
    if any(not isinstance(item, BattleScenarioCaptureCatalogEntry) for item in captures):
        raise BattleScenarioCaptureCatalogError(
            "retained train catalog entries differ"
        )
    ordered = tuple(sorted(captures, key=lambda item: item.producer_ordinal))
    normalized = tuple(
        BattleScenarioCaptureCatalogEntry(
            ordinal=index,
            producer_id=item.producer_id,
            producer_ordinal=item.producer_ordinal,
            capture_id=item.capture_id,
            assignment_sha256=item.assignment_sha256,
            source_state_sha256=item.source_state_sha256,
            root_lineage_id=item.root_lineage_id,
            venue_id=item.venue_id,
            party_slot=item.party_slot,
            state_filename=item.state_filename,
            manifest_filename=item.manifest_filename,
            state_sha256=item.state_sha256,
            manifest_sha256=item.manifest_sha256,
        )
        for index, item in enumerate(ordered)
    )
    return BattleScenarioRetainedTrainCaptureCatalog(
        catalog_id=catalog_id,
        builder_source_commit=builder_source_commit,
        builder_source_bundle_sha256=builder_source_bundle_sha256,
        rom_sha256=rom_sha256,
        producer=producer,
        captures=normalized,
    )


def parse_battle_scenario_capture_catalog(payload: bytes) -> BattleScenarioCaptureCatalog:
    """Strictly reopen one canonical path-free mixed-producer catalog."""

    if not isinstance(payload, bytes):
        raise TypeError("battle capture catalog must be bytes")
    if not payload or len(payload) > _MAXIMUM_CATALOG_BYTES:
        raise BattleScenarioCaptureCatalogError("capture catalog size differs")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleScenarioCaptureCatalogError("capture catalog is not canonical JSON") from None
    catalog = _parse_catalog(value)
    if catalog.canonical_bytes() != payload:
        raise BattleScenarioCaptureCatalogError("capture catalog is not canonical JSON")
    return catalog


def parse_battle_scenario_retained_train_capture_catalog(
    payload: bytes,
) -> BattleScenarioRetainedTrainCaptureCatalog:
    """Strictly reopen the five-success predecessor catalog."""

    if not isinstance(payload, bytes):
        raise TypeError("retained train capture catalog must be bytes")
    if not payload or len(payload) > _MAXIMUM_CATALOG_BYTES:
        raise BattleScenarioCaptureCatalogError(
            "retained train catalog size differs"
        )
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleScenarioCaptureCatalogError(
            "retained train catalog is not canonical JSON"
        ) from None
    fields = {
        "builder_source_bundle_sha256",
        "builder_source_commit",
        "captures",
        "catalog_id",
        "effects",
        "historical_failed_assignments",
        "producer",
        "rom_sha256",
        "schema",
        "status",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("schema")
        != BATTLE_SCENARIO_RETAINED_TRAIN_CAPTURE_CATALOG_SCHEMA
        or value.get("status") != "authenticated_action_free"
        or value.get("historical_failed_assignments") != 2
        or value.get("effects") != _ZERO_EFFECTS
        or not isinstance(value.get("captures"), list)
    ):
        raise BattleScenarioCaptureCatalogError(
            "retained train catalog fields differ"
        )
    catalog = BattleScenarioRetainedTrainCaptureCatalog(
        catalog_id=_text(value.get("catalog_id"), "retained train catalog identity"),
        builder_source_commit=_text(
            value.get("builder_source_commit"), "retained train builder source"
        ),
        builder_source_bundle_sha256=_text(
            value.get("builder_source_bundle_sha256"),
            "retained train builder bundle",
        ),
        rom_sha256=_text(value.get("rom_sha256"), "retained train ROM"),
        producer=_parse_producer(value.get("producer")),
        captures=tuple(_parse_entry(item) for item in value["captures"]),
    )
    if catalog.canonical_bytes() != payload:
        raise BattleScenarioCaptureCatalogError(
            "retained train catalog is not canonical JSON"
        )
    return catalog


def _parse_catalog(value: object) -> BattleScenarioCaptureCatalog:
    fields = {
        "builder_source_bundle_sha256",
        "builder_source_commit",
        "captures",
        "catalog_id",
        "effects",
        "historical_failed_assignments",
        "producers",
        "rom_sha256",
        "schema",
        "status",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("schema") != BATTLE_SCENARIO_CAPTURE_CATALOG_SCHEMA
        or value.get("status") != "authenticated_action_free"
        or value.get("historical_failed_assignments") != 2
        or value.get("effects") != _ZERO_EFFECTS
    ):
        raise BattleScenarioCaptureCatalogError("capture catalog fields differ")
    producers = value.get("producers")
    captures = value.get("captures")
    if not isinstance(producers, list) or not isinstance(captures, list):
        raise BattleScenarioCaptureCatalogError("capture catalog fields differ")
    return BattleScenarioCaptureCatalog(
        catalog_id=_text(value.get("catalog_id"), "capture catalog identity"),
        builder_source_commit=_text(value.get("builder_source_commit"), "builder source"),
        builder_source_bundle_sha256=_text(
            value.get("builder_source_bundle_sha256"), "builder source bundle"
        ),
        rom_sha256=_text(value.get("rom_sha256"), "catalog ROM"),
        producers=tuple(_parse_producer(item) for item in producers),
        captures=tuple(_parse_entry(item) for item in captures),
    )


def _parse_producer(value: object) -> BattleScenarioCaptureProducer:
    fields = set(BattleScenarioCaptureProducer.__dataclass_fields__)
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioCaptureCatalogError("capture producer fields differ")
    return BattleScenarioCaptureProducer(**dict(value))  # type: ignore[arg-type]


def _parse_entry(value: object) -> BattleScenarioCaptureCatalogEntry:
    fields = {
        "assignment_sha256",
        "capture_id",
        "manifest_filename",
        "manifest_sha256",
        "ordinal",
        "party_slot",
        "producer_id",
        "producer_ordinal",
        "root_lineage_id",
        "source_state_sha256",
        "state_filename",
        "state_sha256",
        "venue_id",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioCaptureCatalogError("capture catalog entry fields differ")
    party = value.get("party_slot")
    if not isinstance(party, Mapping) or set(party) != {
        "current_hp",
        "level",
        "maximum_hp",
        "party_slot",
        "species_id",
        "status_id",
        "usable_move_count",
    }:
        raise BattleScenarioCaptureCatalogError("capture party slot differs")
    try:
        slot = BattleScenarioPartySlot(
            party_slot=party["party_slot"],
            species_id=party["species_id"],
            level=party["level"],
            status_id=party["status_id"],
            current_hp=party["current_hp"],
            maximum_hp=party["maximum_hp"],
            usable_move_count=party["usable_move_count"],
        )
    except (KeyError, TypeError, ValueError):
        raise BattleScenarioCaptureCatalogError("capture party slot differs") from None
    return BattleScenarioCaptureCatalogEntry(
        ordinal=value.get("ordinal"),  # type: ignore[arg-type]
        producer_id=value.get("producer_id"),  # type: ignore[arg-type]
        producer_ordinal=value.get("producer_ordinal"),  # type: ignore[arg-type]
        capture_id=value.get("capture_id"),  # type: ignore[arg-type]
        assignment_sha256=value.get("assignment_sha256"),  # type: ignore[arg-type]
        source_state_sha256=value.get("source_state_sha256"),  # type: ignore[arg-type]
        root_lineage_id=value.get("root_lineage_id"),  # type: ignore[arg-type]
        venue_id=value.get("venue_id"),  # type: ignore[arg-type]
        party_slot=slot,
        state_filename=value.get("state_filename"),  # type: ignore[arg-type]
        manifest_filename=value.get("manifest_filename"),  # type: ignore[arg-type]
        state_sha256=value.get("state_sha256"),  # type: ignore[arg-type]
        manifest_sha256=value.get("manifest_sha256"),  # type: ignore[arg-type]
    )


def _require_safe_id(value: object, subject: str) -> None:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise BattleScenarioCaptureCatalogError(f"{subject} differs")


def _require_sha256(value: object, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleScenarioCaptureCatalogError(f"{subject} differs")


def _require_commit(value: object, subject: str) -> None:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleScenarioCaptureCatalogError(f"{subject} differs")


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str):
        raise BattleScenarioCaptureCatalogError(f"{subject} differs")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_payload(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")


__all__ = [
    "BATTLE_SCENARIO_CAPTURE_CATALOG_SCHEMA",
    "BATTLE_SCENARIO_RETAINED_TRAIN_CAPTURE_CATALOG_SCHEMA",
    "BattleScenarioCaptureCatalog",
    "BattleScenarioCaptureCatalogEntry",
    "BattleScenarioCaptureCatalogError",
    "BattleScenarioCaptureProducer",
    "BattleScenarioRetainedTrainCaptureCatalog",
    "build_battle_scenario_capture_catalog",
    "build_battle_scenario_retained_train_capture_catalog",
    "parse_battle_scenario_capture_catalog",
    "parse_battle_scenario_retained_train_capture_catalog",
]
