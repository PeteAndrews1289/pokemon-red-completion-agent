"""Outcome-blind source and party-slot freeze for seven Red battle captures.

The capacity census proves that enough authenticated roots exist.  This module
turns that aggregate fact into one immutable private assignment before any
controller input.  Selection may use source provenance, venue, party state,
move availability, and the declared level-pressure contract.  It cannot use a
wild encounter, battle menu, outcome, model prediction, or teacher choice.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from pokemon_red_completion.battle_outcome_batch import MAXIMUM_LEVEL_GAP
from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition

BATTLE_SCENARIO_MATERIALIZATION_PLAN_SCHEMA = (
    "pokemon.red.private-battle-scenario-materialization-plan.v1"
)
BATTLE_SCENARIO_MATERIALIZATION_SELECTION_POLICY_SCHEMA = (
    "pokemon.red.battle-scenario-materialization-selection-policy.v1"
)

MANSION_VENUE_ID = "pokemon_mansion_1f"
ROUTE_11_VENUE_ID = "route_11"
REQUIRED_MANSION_CAPTURES = 5
REQUIRED_ROUTE_11_CAPTURES = 2
REQUIRED_CAPTURE_COUNT = REQUIRED_MANSION_CAPTURES + REQUIRED_ROUTE_11_CAPTURES
MINIMUM_USABLE_MOVES = 2

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SAFE_FILENAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_MAXIMUM_PLAN_BYTES = 8 * 1024 * 1024

_VENUE_QUOTAS = {
    MANSION_VENUE_ID: REQUIRED_MANSION_CAPTURES,
    ROUTE_11_VENUE_ID: REQUIRED_ROUTE_11_CAPTURES,
}
_SELECTION_POLICY = {
    "schema": BATTLE_SCENARIO_MATERIALIZATION_SELECTION_POLICY_SCHEMA,
    "capture_count": REQUIRED_CAPTURE_COUNT,
    "venue_quotas": dict(sorted(_VENUE_QUOTAS.items())),
    "maximum_level_gap": MAXIMUM_LEVEL_GAP,
    "encounter_level_guard": (
        "party_level_within_maximum_gap_of_every_measured_level_including_rare_ceiling"
    ),
    "minimum_usable_moves": MINIMUM_USABLE_MOVES,
    "inventory_order": ["candidate_identity_sha256_asc"],
    "selection_venue_order": [ROUTE_11_VENUE_ID, MANSION_VENUE_ID],
    "selection_order": [
        "selected_species_count_asc",
        "selected_party_slot_count_asc",
        "selected_status_count_asc",
        "selected_level_count_asc",
        "usable_move_count_desc",
        "hp_ratio_desc",
        "candidate_identity_sha256_asc",
        "party_slot_asc",
    ],
    "source_reuse": False,
    "replacement_slots": 0,
    "controller_actions": 0,
    "outcome_fields": 0,
    "prediction_fields": 0,
    "teacher_choice_fields": 0,
}


class BattleScenarioMaterializationPlanError(ValueError):
    """Raised before a private materialization assignment can drift."""


@dataclass(frozen=True, slots=True)
class BattleScenarioPartySlot:
    """One prospectively usable party member observed without acting."""

    party_slot: int
    species_id: int
    level: int
    current_hp: int
    maximum_hp: int
    status_id: int
    usable_move_count: int

    def __post_init__(self) -> None:
        if (
            type(self.party_slot) is not int  # noqa: E721
            or not 1 <= self.party_slot <= 6
            or type(self.species_id) is not int  # noqa: E721
            or not 1 <= self.species_id <= 255
            or type(self.level) is not int  # noqa: E721
            or not 1 <= self.level <= 100
            or type(self.current_hp) is not int  # noqa: E721
            or type(self.maximum_hp) is not int  # noqa: E721
            or not 1 <= self.current_hp <= self.maximum_hp <= 999
            or type(self.status_id) is not int  # noqa: E721
            or not 0 <= self.status_id <= 255
            or type(self.usable_move_count) is not int  # noqa: E721
            or not MINIMUM_USABLE_MOVES <= self.usable_move_count <= 4
        ):
            raise BattleScenarioMaterializationPlanError(
                "battle materialization party slot differs"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "current_hp": self.current_hp,
            "level": self.level,
            "maximum_hp": self.maximum_hp,
            "party_slot": self.party_slot,
            "species_id": self.species_id,
            "status_id": self.status_id,
            "usable_move_count": self.usable_move_count,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationCandidate:
    """One authenticated source root and its action-free eligible party slots."""

    source: BattleScenarioSourceBinding
    venue_id: str
    source_location: str
    minimum_encounter_level: int
    maximum_encounter_level: int
    rare_maximum_encounter_level: int
    party_slots: tuple[BattleScenarioPartySlot, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source, BattleScenarioSourceBinding)
            or self.source.partition is not ScenarioPartition.TRAIN
            or self.venue_id not in _VENUE_QUOTAS
            or _SAFE_ID.fullmatch(self.source_location) is None
            or type(self.minimum_encounter_level) is not int  # noqa: E721
            or type(self.maximum_encounter_level) is not int  # noqa: E721
            or type(self.rare_maximum_encounter_level) is not int  # noqa: E721
            or not 1
            <= self.minimum_encounter_level
            <= self.maximum_encounter_level
            <= self.rare_maximum_encounter_level
            <= 100
            or not isinstance(self.party_slots, tuple)
            or not self.party_slots
            or any(not isinstance(slot, BattleScenarioPartySlot) for slot in self.party_slots)
            or tuple(sorted(self.party_slots, key=lambda item: item.party_slot))
            != self.party_slots
            or len({slot.party_slot for slot in self.party_slots}) != len(self.party_slots)
        ):
            raise BattleScenarioMaterializationPlanError(
                "battle materialization candidate differs"
            )
        minimum_safe_level = self.rare_maximum_encounter_level - MAXIMUM_LEVEL_GAP
        maximum_safe_level = self.minimum_encounter_level + MAXIMUM_LEVEL_GAP
        if any(
            not minimum_safe_level <= slot.level <= maximum_safe_level
            for slot in self.party_slots
        ):
            raise BattleScenarioMaterializationPlanError(
                "battle materialization candidate exceeds the frozen level gap"
            )

    @property
    def candidate_identity_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "maximum_encounter_level": self.maximum_encounter_level,
            "minimum_encounter_level": self.minimum_encounter_level,
            "party_slots": [slot.private_dict() for slot in self.party_slots],
            "rare_maximum_encounter_level": self.rare_maximum_encounter_level,
            "source": self.source.public_dict(),
            "source_location": self.source_location,
            "venue_id": self.venue_id,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationAssignment:
    """One frozen call to the battle-boundary materializer."""

    ordinal: int
    capture_id: str
    candidate: BattleScenarioMaterializationCandidate
    party_slot: BattleScenarioPartySlot
    state_filename: str
    manifest_filename: str

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int  # noqa: E721
            or not 0 <= self.ordinal < REQUIRED_CAPTURE_COUNT
            or _SAFE_ID.fullmatch(self.capture_id) is None
            or not isinstance(self.candidate, BattleScenarioMaterializationCandidate)
            or not isinstance(self.party_slot, BattleScenarioPartySlot)
            or self.party_slot not in self.candidate.party_slots
            or _SAFE_FILENAME.fullmatch(self.state_filename) is None
            or _SAFE_FILENAME.fullmatch(self.manifest_filename) is None
            or self.state_filename == self.manifest_filename
            or not self.state_filename.endswith(".state")
            or not self.manifest_filename.endswith(".state.json")
        ):
            raise BattleScenarioMaterializationPlanError(
                "battle materialization assignment differs"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "candidate_identity_sha256": self.candidate.candidate_identity_sha256,
            "capture_id": self.capture_id,
            "manifest_filename": self.manifest_filename,
            "ordinal": self.ordinal,
            "party_slot": self.party_slot.party_slot,
            "state_filename": self.state_filename,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationPlan:
    """Canonical private inventory and its derived seven-capture assignment."""

    plan_id: str
    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str
    capture_directory_sha256: str
    inventory: tuple[BattleScenarioMaterializationCandidate, ...]
    assignments: tuple[BattleScenarioMaterializationAssignment, ...]

    def __post_init__(self) -> None:
        if (
            _SAFE_ID.fullmatch(self.plan_id) is None
            or _GIT_COMMIT.fullmatch(self.source_commit) is None
            or _SHA256.fullmatch(self.source_bundle_sha256) is None
            or _SHA256.fullmatch(self.rom_sha256) is None
            or _SHA256.fullmatch(self.capture_directory_sha256) is None
            or not isinstance(self.inventory, tuple)
            or not self.inventory
            or any(
                not isinstance(item, BattleScenarioMaterializationCandidate)
                for item in self.inventory
            )
            or tuple(
                sorted(self.inventory, key=lambda item: item.candidate_identity_sha256)
            )
            != self.inventory
            or len({item.candidate_identity_sha256 for item in self.inventory})
            != len(self.inventory)
            or len({item.source.source_state_sha256 for item in self.inventory})
            != len(self.inventory)
        ):
            raise BattleScenarioMaterializationPlanError(
                "battle materialization plan inventory differs"
            )
        provenances = {
            (
                item.source.catalog_sha256,
                item.source.registry_sha256,
                item.source.registry_source_commit,
            )
            for item in self.inventory
        }
        if len(provenances) != 1:
            raise BattleScenarioMaterializationPlanError(
                "battle materialization source provenance differs"
            )
        expected = _select_assignments(self.plan_id, self.inventory)
        if self.assignments != expected:
            raise BattleScenarioMaterializationPlanError(
                "battle materialization assignment is not canonical"
            )

    @property
    def selection_policy_sha256(self) -> str:
        return battle_scenario_materialization_selection_policy_sha256()

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def private_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "capture_directory_sha256": self.capture_directory_sha256,
            "effects": {
                "authority_promoted": False,
                "battle_captures_created": 0,
                "controller_actions": 0,
                "crystal_contexts_opened": 0,
                "emulator_frames": 0,
                "full_game_replays": 0,
                "model_fits": 0,
                "model_predictions": 0,
                "outcomes_opened": 0,
                "root_claims_created": 0,
                "sealed_red_cases_opened": 0,
                "teacher_queries": 0,
            },
            "inventory": [item.private_dict() for item in self.inventory],
            "plan_id": self.plan_id,
            "retry_after_controller_input": False,
            "rom_sha256": self.rom_sha256,
            "schema": BATTLE_SCENARIO_MATERIALIZATION_PLAN_SCHEMA,
            "selection_policy_sha256": self.selection_policy_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "status": "prospective_unexecuted",
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.private_dict())


def battle_scenario_materialization_selection_policy_sha256() -> str:
    """Return the exact outcome-blind selection policy identity."""

    return canonical_sha256(_SELECTION_POLICY)


def build_battle_scenario_materialization_plan(
    *,
    plan_id: str,
    source_commit: str,
    source_bundle_sha256: str,
    rom_sha256: str,
    capture_directory_sha256: str,
    candidates: Sequence[BattleScenarioMaterializationCandidate],
) -> BattleScenarioMaterializationPlan:
    """Freeze the complete eligible inventory and its canonical assignments."""

    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise TypeError("battle materialization candidates must be a sequence")
    inventory = tuple(
        sorted(candidates, key=lambda item: item.candidate_identity_sha256)
    )
    return BattleScenarioMaterializationPlan(
        plan_id=plan_id,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        rom_sha256=rom_sha256,
        capture_directory_sha256=capture_directory_sha256,
        inventory=inventory,
        assignments=_select_assignments(plan_id, inventory),
    )


def parse_battle_scenario_materialization_plan(
    payload: bytes,
) -> BattleScenarioMaterializationPlan:
    """Strictly reopen one canonical private materialization plan."""

    if not isinstance(payload, bytes):
        raise TypeError("battle materialization plan must be bytes")
    if not payload or len(payload) > _MAXIMUM_PLAN_BYTES:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization plan size differs"
        )
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleScenarioMaterializationPlanError(
            "battle materialization plan is not canonical JSON"
        ) from None
    plan = _parse_plan(value)
    if plan.canonical_bytes() != payload:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization plan is not canonical JSON"
        )
    return plan


def _select_assignments(
    plan_id: str,
    inventory: tuple[BattleScenarioMaterializationCandidate, ...],
) -> tuple[BattleScenarioMaterializationAssignment, ...]:
    if _SAFE_ID.fullmatch(plan_id) is None:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization plan identity differs"
        )
    available = Counter(item.venue_id for item in inventory)
    if any(available[venue] < count for venue, count in _VENUE_QUOTAS.items()):
        raise BattleScenarioMaterializationPlanError(
            "battle materialization inventory lacks frozen venue capacity"
        )
    used_candidates: set[str] = set()
    species_counts: Counter[int] = Counter()
    party_slot_counts: Counter[int] = Counter()
    status_counts: Counter[int] = Counter()
    level_counts: Counter[int] = Counter()
    selected: list[tuple[BattleScenarioMaterializationCandidate, BattleScenarioPartySlot]] = []

    for venue_id in (ROUTE_11_VENUE_ID, MANSION_VENUE_ID):
        for _ in range(_VENUE_QUOTAS[venue_id]):
            choices = tuple(
                (candidate, slot)
                for candidate in inventory
                if candidate.venue_id == venue_id
                and candidate.candidate_identity_sha256 not in used_candidates
                for slot in candidate.party_slots
            )
            if not choices:
                raise BattleScenarioMaterializationPlanError(
                    "battle materialization inventory exhausted during selection"
                )
            candidate, slot = min(
                choices,
                key=lambda item: (
                    species_counts[item[1].species_id],
                    party_slot_counts[item[1].party_slot],
                    status_counts[item[1].status_id],
                    level_counts[item[1].level],
                    -item[1].usable_move_count,
                    -Fraction(item[1].current_hp, item[1].maximum_hp),
                    item[0].candidate_identity_sha256,
                    item[1].party_slot,
                ),
            )
            used_candidates.add(candidate.candidate_identity_sha256)
            species_counts[slot.species_id] += 1
            party_slot_counts[slot.party_slot] += 1
            status_counts[slot.status_id] += 1
            level_counts[slot.level] += 1
            selected.append((candidate, slot))

    assignments = tuple(
        BattleScenarioMaterializationAssignment(
            ordinal=ordinal,
            capture_id=f"{plan_id}-{ordinal + 1:02d}",
            candidate=candidate,
            party_slot=slot,
            state_filename=f"{plan_id}-{ordinal + 1:02d}.state",
            manifest_filename=f"{plan_id}-{ordinal + 1:02d}.state.json",
        )
        for ordinal, (candidate, slot) in enumerate(selected)
    )
    if (
        len(assignments) != REQUIRED_CAPTURE_COUNT
        or len({item.capture_id for item in assignments}) != len(assignments)
        or len({item.candidate.source.source_state_sha256 for item in assignments})
        != len(assignments)
        or Counter(item.candidate.venue_id for item in assignments) != _VENUE_QUOTAS
    ):
        raise BattleScenarioMaterializationPlanError(
            "battle materialization assignment denominator differs"
        )
    return assignments


def _parse_plan(value: object) -> BattleScenarioMaterializationPlan:
    expected = {
        "assignments",
        "capture_directory_sha256",
        "effects",
        "inventory",
        "plan_id",
        "retry_after_controller_input",
        "rom_sha256",
        "schema",
        "selection_policy_sha256",
        "source_bundle_sha256",
        "source_commit",
        "status",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("schema") != BATTLE_SCENARIO_MATERIALIZATION_PLAN_SCHEMA
        or value.get("status") != "prospective_unexecuted"
        or value.get("retry_after_controller_input") is not False
        or value.get("selection_policy_sha256")
        != battle_scenario_materialization_selection_policy_sha256()
        or value.get("effects")
        != {
            "authority_promoted": False,
            "battle_captures_created": 0,
            "controller_actions": 0,
            "crystal_contexts_opened": 0,
            "emulator_frames": 0,
            "full_game_replays": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "root_claims_created": 0,
            "sealed_red_cases_opened": 0,
            "teacher_queries": 0,
        }
    ):
        raise BattleScenarioMaterializationPlanError(
            "battle materialization plan fields differ"
        )
    inventory_value = value.get("inventory")
    assignments_value = value.get("assignments")
    if not isinstance(inventory_value, list) or not isinstance(assignments_value, list):
        raise BattleScenarioMaterializationPlanError(
            "battle materialization plan collections differ"
        )
    inventory = tuple(_parse_candidate(item) for item in inventory_value)
    by_identity = {item.candidate_identity_sha256: item for item in inventory}
    assignments = tuple(
        _parse_assignment(item, by_identity=by_identity) for item in assignments_value
    )
    return BattleScenarioMaterializationPlan(
        plan_id=_text(value.get("plan_id"), "plan id"),
        source_commit=_text(value.get("source_commit"), "source commit"),
        source_bundle_sha256=_text(
            value.get("source_bundle_sha256"), "source bundle"
        ),
        rom_sha256=_text(value.get("rom_sha256"), "ROM"),
        capture_directory_sha256=_text(
            value.get("capture_directory_sha256"), "capture directory"
        ),
        inventory=inventory,
        assignments=assignments,
    )


def _parse_candidate(value: object) -> BattleScenarioMaterializationCandidate:
    expected = {
        "maximum_encounter_level",
        "minimum_encounter_level",
        "party_slots",
        "rare_maximum_encounter_level",
        "source",
        "source_location",
        "venue_id",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization candidate fields differ"
        )
    slots = value.get("party_slots")
    if not isinstance(slots, list):
        raise BattleScenarioMaterializationPlanError(
            "battle materialization party slots differ"
        )
    return BattleScenarioMaterializationCandidate(
        source=_parse_source_binding(value.get("source")),
        venue_id=_text(value.get("venue_id"), "venue"),
        source_location=_text(value.get("source_location"), "source location"),
        minimum_encounter_level=_integer(
            value.get("minimum_encounter_level"), "minimum encounter level"
        ),
        maximum_encounter_level=_integer(
            value.get("maximum_encounter_level"), "maximum encounter level"
        ),
        rare_maximum_encounter_level=_integer(
            value.get("rare_maximum_encounter_level"), "rare encounter level"
        ),
        party_slots=tuple(_parse_party_slot(item) for item in slots),
    )


def _parse_party_slot(value: object) -> BattleScenarioPartySlot:
    expected = {
        "current_hp",
        "level",
        "maximum_hp",
        "party_slot",
        "species_id",
        "status_id",
        "usable_move_count",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization party slot fields differ"
        )
    return BattleScenarioPartySlot(
        party_slot=_integer(value.get("party_slot"), "party slot"),
        species_id=_integer(value.get("species_id"), "species"),
        level=_integer(value.get("level"), "level"),
        current_hp=_integer(value.get("current_hp"), "current HP"),
        maximum_hp=_integer(value.get("maximum_hp"), "maximum HP"),
        status_id=_integer(value.get("status_id"), "status"),
        usable_move_count=_integer(value.get("usable_move_count"), "usable moves"),
    )


def _parse_assignment(
    value: object,
    *,
    by_identity: Mapping[str, BattleScenarioMaterializationCandidate],
) -> BattleScenarioMaterializationAssignment:
    expected = {
        "candidate_identity_sha256",
        "capture_id",
        "manifest_filename",
        "ordinal",
        "party_slot",
        "state_filename",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization assignment fields differ"
        )
    identity = _text(value.get("candidate_identity_sha256"), "candidate identity")
    try:
        candidate = by_identity[identity]
    except KeyError:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization assignment candidate differs"
        ) from None
    party_slot = _integer(value.get("party_slot"), "party slot")
    matching = tuple(item for item in candidate.party_slots if item.party_slot == party_slot)
    if len(matching) != 1:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization assignment party slot differs"
        )
    return BattleScenarioMaterializationAssignment(
        ordinal=_integer(value.get("ordinal"), "ordinal"),
        capture_id=_text(value.get("capture_id"), "capture id"),
        candidate=candidate,
        party_slot=matching[0],
        state_filename=_text(value.get("state_filename"), "state filename"),
        manifest_filename=_text(value.get("manifest_filename"), "manifest filename"),
    )


def _parse_source_binding(value: object) -> BattleScenarioSourceBinding:
    expected = {
        "caller_supplied_lineage",
        "caller_supplied_partition",
        "catalog_sha256",
        "partition",
        "private_path_fields",
        "registry_sha256",
        "registry_source_commit",
        "root_consumption_sha256",
        "root_lineage_id",
        "schema",
        "source_assignment_id",
        "source_context_id",
        "source_envelope_sha256",
        "source_slot_id",
        "source_state_sha256",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("schema") != "pokemon.red.battle-scenario-source-binding.v1"
        or value.get("caller_supplied_lineage") is not False
        or value.get("caller_supplied_partition") is not False
        or value.get("private_path_fields") != 0
    ):
        raise BattleScenarioMaterializationPlanError(
            "battle materialization source binding fields differ"
        )
    try:
        partition = ScenarioPartition(_text(value.get("partition"), "partition"))
    except ValueError:
        raise BattleScenarioMaterializationPlanError(
            "battle materialization source partition differs"
        ) from None
    return BattleScenarioSourceBinding(
        partition=partition,
        source_state_sha256=_text(value.get("source_state_sha256"), "source state"),
        source_slot_id=_text(value.get("source_slot_id"), "source slot"),
        source_assignment_id=_text(
            value.get("source_assignment_id"), "source assignment"
        ),
        source_context_id=_text(value.get("source_context_id"), "source context"),
        source_envelope_sha256=_text(
            value.get("source_envelope_sha256"), "source envelope"
        ),
        root_lineage_id=_text(value.get("root_lineage_id"), "root lineage"),
        root_consumption_sha256=_text(
            value.get("root_consumption_sha256"), "root consumption"
        ),
        catalog_sha256=_text(value.get("catalog_sha256"), "catalog"),
        registry_sha256=_text(value.get("registry_sha256"), "registry"),
        registry_source_commit=_text(
            value.get("registry_source_commit"), "registry source commit"
        ),
    )


def _canonical_payload(value: Mapping[str, object]) -> bytes:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{encoded}\n".encode("ascii")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise BattleScenarioMaterializationPlanError(
            f"battle materialization {subject} differs"
        )
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int:  # noqa: E721
        raise BattleScenarioMaterializationPlanError(
            f"battle materialization {subject} differs"
        )
    return value
