"""Typed, outcome-blind catalog for one terminal development capture campaign.

The V2 development materialization plan is frozen before controller input.  A
terminal run journal proves which assignments were consumed, while this
catalog independently reopens the eight successful outputs and turns them
into one canonical producer contract for the batch freezer.  It contains no
paths, outcomes, predictions, teacher choices, or preferred actions.
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

BATTLE_SCENARIO_DEVELOPMENT_CAPTURE_CATALOG_SCHEMA = (
    "pokemon.red.private-battle-scenario-development-capture-catalog.v1"
)
REQUIRED_DEVELOPMENT_CAPTURE_COUNT = 8
REQUIRED_DEVELOPMENT_VENUE_COUNTS = {"digletts_cave": 4, "route_11": 4}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SAFE_FILENAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_MAXIMUM_CATALOG_BYTES = 4 * 1024 * 1024
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


class BattleScenarioDevelopmentCaptureCatalogError(ValueError):
    """Raised when a development producer or output can be substituted."""


@dataclass(frozen=True, slots=True)
class BattleScenarioDevelopmentCaptureProducer:
    """The immutable plan, terminal journal, and execution identity."""

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

    def __post_init__(self) -> None:
        _require_safe_id(self.plan_id, "development plan identity")
        for value, subject in (
            (self.plan_sha256, "development plan"),
            (self.run_journal_sha256, "development journal"),
            (self.source_bundle_sha256, "development source bundle"),
            (self.materializer_sha256, "development materializer"),
            (self.runtime_identity_sha256, "development runtime"),
            (self.rom_sha256, "development ROM"),
            (self.capture_directory_sha256, "development capture directory"),
            (self.context_catalog_sha256, "development context catalog"),
            (self.registry_sha256, "development registry"),
        ):
            _require_sha256(value, subject)
        for value, subject in (
            (self.source_commit, "development source"),
            (self.registry_source_commit, "development registry source"),
        ):
            _require_commit(value, subject)
        for integer_value, subject in (
            (self.exact_ci_run, "development CI run"),
            (self.exact_ci_attempt, "development CI attempt"),
        ):
            if type(integer_value) is not int or integer_value <= 0:  # noqa: E721
                raise BattleScenarioDevelopmentCaptureCatalogError(f"{subject} differs")

    def private_dict(self) -> dict[str, object]:
        return {
            "capture_directory_sha256": self.capture_directory_sha256,
            "context_catalog_sha256": self.context_catalog_sha256,
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "materializer_sha256": self.materializer_sha256,
            "plan_id": self.plan_id,
            "plan_sha256": self.plan_sha256,
            "registry_sha256": self.registry_sha256,
            "registry_source_commit": self.registry_source_commit,
            "rom_sha256": self.rom_sha256,
            "run_journal_sha256": self.run_journal_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioDevelopmentCaptureEntry:
    """One successful assignment independently joined to its output bytes."""

    ordinal: int
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
        if type(self.ordinal) is not int or not (  # noqa: E721
            0 <= self.ordinal < REQUIRED_DEVELOPMENT_CAPTURE_COUNT
        ):
            raise BattleScenarioDevelopmentCaptureCatalogError(
                "development capture ordinal differs"
            )
        for value, subject in (
            (self.capture_id, "development capture identity"),
            (self.root_lineage_id, "development capture lineage"),
            (self.venue_id, "development capture venue"),
        ):
            _require_safe_id(value, subject)
        for value, subject in (
            (self.assignment_sha256, "development assignment"),
            (self.source_state_sha256, "development source state"),
            (self.state_sha256, "development state"),
            (self.manifest_sha256, "development manifest"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.party_slot, BattleScenarioPartySlot):
            raise BattleScenarioDevelopmentCaptureCatalogError("development party slot differs")
        for value, suffix, subject in (
            (self.state_filename, ".state", "development state filename"),
            (
                self.manifest_filename,
                ".state.json",
                "development manifest filename",
            ),
        ):
            if _SAFE_FILENAME.fullmatch(value) is None or not value.endswith(suffix):
                raise BattleScenarioDevelopmentCaptureCatalogError(f"{subject} differs")
        if self.state_filename == self.manifest_filename:
            raise BattleScenarioDevelopmentCaptureCatalogError(
                "development capture filenames collide"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "assignment_sha256": self.assignment_sha256,
            "capture_id": self.capture_id,
            "manifest_filename": self.manifest_filename,
            "manifest_sha256": self.manifest_sha256,
            "ordinal": self.ordinal,
            "party_slot": self.party_slot.private_dict(),
            "root_lineage_id": self.root_lineage_id,
            "source_state_sha256": self.source_state_sha256,
            "state_filename": self.state_filename,
            "state_sha256": self.state_sha256,
            "venue_id": self.venue_id,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioDevelopmentCaptureCatalog:
    """Exactly eight authenticated, partition-development capture outputs."""

    catalog_id: str
    builder_source_commit: str
    builder_source_bundle_sha256: str
    producer: BattleScenarioDevelopmentCaptureProducer
    captures: tuple[BattleScenarioDevelopmentCaptureEntry, ...]

    def __post_init__(self) -> None:
        _require_safe_id(self.catalog_id, "development catalog identity")
        _require_commit(self.builder_source_commit, "development catalog builder")
        _require_sha256(
            self.builder_source_bundle_sha256,
            "development catalog builder bundle",
        )
        if not isinstance(self.producer, BattleScenarioDevelopmentCaptureProducer):
            raise BattleScenarioDevelopmentCaptureCatalogError("development producer differs")
        if (
            not isinstance(self.captures, tuple)
            or len(self.captures) != REQUIRED_DEVELOPMENT_CAPTURE_COUNT
            or any(
                not isinstance(item, BattleScenarioDevelopmentCaptureEntry)
                for item in self.captures
            )
            or tuple(item.ordinal for item in self.captures)
            != tuple(range(REQUIRED_DEVELOPMENT_CAPTURE_COUNT))
        ):
            raise BattleScenarioDevelopmentCaptureCatalogError(
                "development catalog denominator differs"
            )
        identity_sets = (
            {item.capture_id for item in self.captures},
            {item.assignment_sha256 for item in self.captures},
            {item.source_state_sha256 for item in self.captures},
            {item.root_lineage_id for item in self.captures},
            {item.state_filename for item in self.captures},
            {item.manifest_filename for item in self.captures},
            {item.state_sha256 for item in self.captures},
            {item.manifest_sha256 for item in self.captures},
        )
        if any(len(values) != REQUIRED_DEVELOPMENT_CAPTURE_COUNT for values in identity_sets):
            raise BattleScenarioDevelopmentCaptureCatalogError(
                "development catalog identity repeats"
            )
        if Counter(item.venue_id for item in self.captures) != Counter(
            REQUIRED_DEVELOPMENT_VENUE_COUNTS
        ):
            raise BattleScenarioDevelopmentCaptureCatalogError(
                "development venue distribution differs"
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
            "partition": "development",
            "producer": self.producer.private_dict(),
            "schema": BATTLE_SCENARIO_DEVELOPMENT_CAPTURE_CATALOG_SCHEMA,
            "status": "authenticated_action_free",
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.private_dict())


def build_battle_scenario_development_capture_catalog(
    *,
    catalog_id: str,
    builder_source_commit: str,
    builder_source_bundle_sha256: str,
    producer: BattleScenarioDevelopmentCaptureProducer,
    captures: Sequence[BattleScenarioDevelopmentCaptureEntry],
) -> BattleScenarioDevelopmentCaptureCatalog:
    """Normalize one terminal V2 development producer into ordinal order."""

    if isinstance(captures, (str, bytes)) or not isinstance(captures, Sequence):
        raise TypeError("development capture entries must be a sequence")
    if any(not isinstance(item, BattleScenarioDevelopmentCaptureEntry) for item in captures):
        raise BattleScenarioDevelopmentCaptureCatalogError("development capture entries differ")
    ordered = tuple(sorted(captures, key=lambda item: item.ordinal))
    return BattleScenarioDevelopmentCaptureCatalog(
        catalog_id=catalog_id,
        builder_source_commit=builder_source_commit,
        builder_source_bundle_sha256=builder_source_bundle_sha256,
        producer=producer,
        captures=ordered,
    )


def parse_battle_scenario_development_capture_catalog(
    payload: bytes,
) -> BattleScenarioDevelopmentCaptureCatalog:
    """Strictly reopen one canonical path-free development catalog."""

    if not isinstance(payload, bytes):
        raise TypeError("development capture catalog must be bytes")
    if not payload or len(payload) > _MAXIMUM_CATALOG_BYTES:
        raise BattleScenarioDevelopmentCaptureCatalogError("development catalog size differs")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleScenarioDevelopmentCaptureCatalogError(
            "development catalog is not canonical JSON"
        ) from None
    catalog = _parse_catalog(value)
    if catalog.canonical_bytes() != payload:
        raise BattleScenarioDevelopmentCaptureCatalogError(
            "development catalog is not canonical JSON"
        )
    return catalog


def _parse_catalog(value: object) -> BattleScenarioDevelopmentCaptureCatalog:
    fields = {
        "builder_source_bundle_sha256",
        "builder_source_commit",
        "captures",
        "catalog_id",
        "effects",
        "partition",
        "producer",
        "schema",
        "status",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("schema") != BATTLE_SCENARIO_DEVELOPMENT_CAPTURE_CATALOG_SCHEMA
        or value.get("status") != "authenticated_action_free"
        or value.get("partition") != "development"
        or value.get("effects") != _ZERO_EFFECTS
        or not isinstance(value.get("captures"), list)
    ):
        raise BattleScenarioDevelopmentCaptureCatalogError("development catalog fields differ")
    producer_value = value.get("producer")
    if not isinstance(producer_value, Mapping) or set(producer_value) != set(
        BattleScenarioDevelopmentCaptureProducer.__dataclass_fields__
    ):
        raise BattleScenarioDevelopmentCaptureCatalogError("development producer fields differ")
    return BattleScenarioDevelopmentCaptureCatalog(
        catalog_id=_text(value.get("catalog_id"), "development catalog identity"),
        builder_source_commit=_text(
            value.get("builder_source_commit"), "development catalog builder"
        ),
        builder_source_bundle_sha256=_text(
            value.get("builder_source_bundle_sha256"),
            "development catalog builder bundle",
        ),
        producer=BattleScenarioDevelopmentCaptureProducer(**dict(producer_value)),  # type: ignore[arg-type]
        captures=tuple(_parse_entry(item) for item in value["captures"]),
    )


def _parse_entry(value: object) -> BattleScenarioDevelopmentCaptureEntry:
    fields = {
        "assignment_sha256",
        "capture_id",
        "manifest_filename",
        "manifest_sha256",
        "ordinal",
        "party_slot",
        "root_lineage_id",
        "source_state_sha256",
        "state_filename",
        "state_sha256",
        "venue_id",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioDevelopmentCaptureCatalogError("development capture fields differ")
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
        raise BattleScenarioDevelopmentCaptureCatalogError("development party slot differs")
    try:
        slot = BattleScenarioPartySlot(**dict(party))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise BattleScenarioDevelopmentCaptureCatalogError(
            "development party slot differs"
        ) from None
    return BattleScenarioDevelopmentCaptureEntry(
        ordinal=value.get("ordinal"),  # type: ignore[arg-type]
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
        raise BattleScenarioDevelopmentCaptureCatalogError(f"{subject} differs")


def _require_sha256(value: object, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleScenarioDevelopmentCaptureCatalogError(f"{subject} differs")


def _require_commit(value: object, subject: str) -> None:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleScenarioDevelopmentCaptureCatalogError(f"{subject} differs")


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str):
        raise BattleScenarioDevelopmentCaptureCatalogError(f"{subject} differs")
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
        ).encode("ascii")
        + b"\n"
    )


__all__ = [
    "BATTLE_SCENARIO_DEVELOPMENT_CAPTURE_CATALOG_SCHEMA",
    "REQUIRED_DEVELOPMENT_CAPTURE_COUNT",
    "BattleScenarioDevelopmentCaptureCatalog",
    "BattleScenarioDevelopmentCaptureCatalogError",
    "BattleScenarioDevelopmentCaptureEntry",
    "BattleScenarioDevelopmentCaptureProducer",
    "build_battle_scenario_development_capture_catalog",
    "parse_battle_scenario_development_capture_catalog",
]
