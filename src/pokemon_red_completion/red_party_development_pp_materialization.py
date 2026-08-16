"""Frozen Red contracts for two natural middle-PP curriculum contexts.

This boundary creates no learner question or answer.  It binds one untouched
train root and one untouched development root to a future, separately
authorized preparation that consumes PP only through ordinary wild battles.
Private execution identity stays in the plan; the public projection exposes
only provenance, counts, bounds and zero-access accounting.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from pokemon_red_completion.observation import (
    RawGameState,
    RedBoxCollectionState,
    RedPokedexState,
)
from pokemon_red_completion.party_development_question_reservations import (
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_party_pp import (
    RedPartyPpError,
    decode_red_party_pp,
    natural_pp_depletion_slots,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_SOURCE_SCHEMA = (
    "pokemon.red.party-development-pp-materialization-source.v1"
)
RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_PLAN_SCHEMA = (
    "pokemon.red.party-development-pp-materialization-plan.v1"
)
RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_SUMMARY_SCHEMA = (
    "pokemon.red.party-development-pp-materialization-summary.v1"
)

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedPartyDevelopmentPpMaterializationError(ValueError):
    """Raised before a PP preparation can lose its one-shot meaning."""


class RedPpStartAdapter(StrEnum):
    """Private, source-specific relocation into the shared safe venue."""

    CINNABAR_CENTER_PC_TO_ROUTE_11 = "cinnabar_center_pc_to_route_11"
    CINNABAR_MART_CLERK_TO_ROUTE_11 = "cinnabar_mart_clerk_to_route_11"


@dataclass(frozen=True, slots=True)
class RedPpMaterializationBounds:
    """Independent hard limits for one preparation attempt."""

    maximum_completed_battles: int = 27
    maximum_encounter_steps: int = 10_000
    maximum_controller_actions: int = 250_000
    maximum_frames: int = 5_000_000

    def __post_init__(self) -> None:
        if any(
            type(getattr(self, name)) is not int or getattr(self, name) <= 0  # noqa: E721
            for name in self.__dataclass_fields__
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization bounds must be positive integers"
            )

    def public_dict(self) -> dict[str, int]:
        return {
            name: cast(int, getattr(self, name))
            for name in self.__dataclass_fields__
        }


RED_PP_MATERIALIZATION_BOUNDS = RedPpMaterializationBounds()
RED_PP_MATERIALIZATION_EXECUTION_CONTRACT = {
    "schema": "pokemon.red.party-development-pp-materialization-execution.v1",
    "purpose": "naturally_create_one_middle_pp_context_per_open_partition",
    "source": "two_reserved_authenticated_non_sealed_red_checkpoints",
    "shared_venue": "one_cartridge_verified_low_risk_wild_encounter_area",
    "source_requirements": [
        "all_party_members_healthy_with_high_hp_and_high_pp",
        "experience_sharing_item_absent",
        "all_possible_wild_species_already_seen",
        "unique_highest_level_field_lead",
    ],
    "allowed_transient_execution_changes": [
        "bounded_noninteractive_overworld_navigation",
        "ordinary_wild_battle_dialogue",
        "ordinary_wild_encounter_rng",
    ],
    "allowed_durable_changes": [
        "target_member_battle_damage",
        "target_member_experience",
        "target_member_level",
        "target_member_level_derived_stats",
        "target_member_maximum_hp",
        "target_member_move_pp_consumption",
        "final_map_and_position",
    ],
    "forbidden_operations": [
        "bag_item_use",
        "capture",
        "direct_memory_edit",
        "healing",
        "learner_candidate_construction",
        "learner_outcome_measurement",
        "model_fit",
        "model_prediction",
        "party_reorder",
        "party_switch",
        "sealed_red_access",
        "storage_access",
        "teacher_query",
        "crystal_access",
    ],
    "protected_unchanged_state": [
        "badges",
        "bag",
        "boxed_collection",
        "money",
        "non_target_party_members",
        "party_membership",
        "party_moves",
        "pokedex_owned",
        "pokedex_seen",
        "story_event_flags",
    ],
    "deterministic_target": "unique_highest_level_healthy_lead_with_safe_pp_capacity",
    "deterministic_move_order": "ascending_safe_one_based_move_slot",
    "deterministic_stop": "first_completed_battle_with_target_total_pp_in_middle_bin",
    "abort_conditions": [
        "battle_loss_or_blackout",
        "faint",
        "hard_bound_exhausted",
        "input_not_released",
        "new_persistent_status",
        "protected_state_change",
        "target_move_or_species_change",
        "unexpected_battle_or_map",
        "unexpected_menu_or_story_progress",
        "saved_state_reload_authentication_failure",
    ],
    "durability": (
        "durable_private_plan_and_exclusive_output_claim_before_controller_then_"
        "saved_state_reload_authentication_and_envelope_commit_marker_after_all_"
        "terminal_and_isolation_checks"
    ),
    "authorization": "fresh_explicit_controller_authorization_per_unconsumed_entry",
    "retry_after_any_controller_input": False,
    "result_semantics": "context_preparation_only_not_a_question_label_or_outcome",
    "bounds": RED_PP_MATERIALIZATION_BOUNDS.public_dict(),
}
RED_PP_MATERIALIZATION_EXECUTION_CONTRACT_SHA256 = canonical_sha256(
    RED_PP_MATERIALIZATION_EXECUTION_CONTRACT
)


def red_pp_source_boundary_sha256(
    raw: RawGameState,
    *,
    input_ready: bool,
) -> str:
    """Digest the exact pre-controller map/control boundary."""

    if not isinstance(raw, RawGameState) or not isinstance(input_ready, bool):
        raise TypeError("PP materialization boundary inputs are invalid")
    return canonical_sha256(
        {
            "schema": "pokemon.red.party-development-pp-source-boundary.v1",
            "game_started": raw.game_started,
            "map_id": raw.map_id,
            "player_x": raw.player_x,
            "player_y": raw.player_y,
            "party_count": raw.party_count,
            "battle_state": raw.battle_state,
            "input_ready": input_ready,
        }
    )


def red_pp_protected_state_sha256(
    raw: RawGameState,
    pokedex: RedPokedexState,
    boxes: RedBoxCollectionState,
    party_experience: tuple[int, ...],
    *,
    target_party_slot: int,
) -> str:
    """Digest every durable field that the preparation must not change.

    Target HP, maximum HP, level, experience and PP are intentionally absent:
    they are the only party resources an ordinary battle may change. Target
    species, moves and status remain protected, as does every field of every
    non-target member.
    """

    if (
        not isinstance(raw, RawGameState)
        or not isinstance(pokedex, RedPokedexState)
        or not isinstance(boxes, RedBoxCollectionState)
        or not isinstance(party_experience, tuple)
        or type(target_party_slot) is not int  # noqa: E721
        or not 1 <= target_party_slot <= 6
    ):
        raise TypeError("PP materialization protected-state inputs are invalid")
    required = (
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
    )
    if any(value is None for value in required) or raw.party_count is None:
        raise RedPartyDevelopmentPpMaterializationError(
            "PP materialization party observation is incomplete"
        )
    species = cast(tuple[int, ...], raw.party_species_ids)
    levels = cast(tuple[int, ...], raw.party_levels)
    hp = cast(tuple[int, ...], raw.party_hp)
    maximum_hp = cast(tuple[int, ...], raw.party_max_hp)
    status = cast(tuple[int, ...], raw.party_status)
    moves = cast(tuple[tuple[int, ...], ...], raw.party_moves)
    pp = cast(tuple[tuple[int, ...], ...], raw.party_pp)
    vectors = (species, levels, hp, maximum_hp, status, moves, pp)
    if (
        any(len(value) != raw.party_count for value in vectors)
        or len(party_experience) != raw.party_count
        or any(
            type(value) is not int or value < 0  # noqa: E721
            for value in party_experience
        )
    ):
        raise RedPartyDevelopmentPpMaterializationError(
            "PP materialization party vectors disagree"
        )
    target_index = target_party_slot - 1
    non_target = [
        {
            "slot": index + 1,
            "species_id": species[index],
            "level": levels[index],
            "hp": hp[index],
            "maximum_hp": maximum_hp[index],
            "status": status[index],
            "moves": list(moves[index]),
            "packed_pp": list(pp[index]),
            "experience": party_experience[index],
        }
        for index in range(raw.party_count)
        if index != target_index
    ]
    return canonical_sha256(
        {
            "schema": "pokemon.red.party-development-pp-protected-state.v1",
            "badge_bits": raw.badge_bits,
            "bag_item_ids": list(raw.bag_item_ids or ()),
            "bag_items": [list(item) for item in (raw.bag_items or ())],
            "event_flags_hex": (
                raw.event_flags.hex() if raw.event_flags is not None else None
            ),
            "money": raw.player_money,
            "party_count": raw.party_count,
            "party_species_ids": list(species),
            "target": {
                "slot": target_party_slot,
                "species_id": species[target_index],
                "status": status[target_index],
                "moves": list(moves[target_index]),
            },
            "non_target_members": non_target,
            "pokedex_owned": sorted(pokedex.owned_species),
            "pokedex_seen": sorted(pokedex.seen_species),
            "boxes": [
                {
                    "box_index": box.box_index,
                    "species_ids": list(box.species_ids),
                    "levels": list(box.levels),
                }
                for box in boxes.boxes
            ],
            "current_box_index": boxes.current_box_index,
            "storage_initialized": boxes.storage_initialized,
        }
    )


@dataclass(frozen=True, slots=True)
class RedPpMaterializationSource:
    """One private, read-only-inspected source for later preparation."""

    scenario_id: str
    partition: ScenarioPartition
    source_checkpoint_id: str
    source_state_sha256: str
    source_envelope_sha256: str
    source_semantic_signature_sha256: str
    source_root_lineage_id: str
    source_boundary_sha256: str
    protected_state_sha256: str
    start_adapter: RedPpStartAdapter
    target_party_slot: int
    target_species_id: int
    target_level: int
    target_hp: int
    target_max_hp: int
    target_move_ids: tuple[int, int, int, int]
    target_initial_packed_pp: tuple[int, int, int, int]
    safe_move_slots: tuple[int, ...]
    current_total_pp: int
    maximum_total_pp: int
    middle_pp_ceiling: int
    minimum_pp_consumption: int
    safe_current_pp: int
    target_has_evolution_route: bool
    venue_map_id: int
    venue_binding_sha256: str
    venue_maximum_wild_level: int
    possible_wild_species_ids: tuple[int, ...]
    possible_wild_species_sha256: str
    all_possible_wild_species_seen: bool
    output_capture_id: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.scenario_id, "scenario"),
            (self.source_checkpoint_id, "source checkpoint"),
            (self.source_root_lineage_id, "source root"),
            (self.output_capture_id, "output capture"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise RedPartyDevelopmentPpMaterializationError(
                    f"PP materialization {subject} identity is invalid"
                )
        for value, subject in (
            (self.source_state_sha256, "source state"),
            (self.source_envelope_sha256, "source envelope"),
            (self.source_semantic_signature_sha256, "source semantics"),
            (self.source_boundary_sha256, "source boundary"),
            (self.protected_state_sha256, "protected state"),
            (self.venue_binding_sha256, "venue binding"),
            (self.possible_wild_species_sha256, "wild species"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise RedPartyDevelopmentPpMaterializationError(
                    f"PP materialization {subject} digest is invalid"
                )
        if not isinstance(self.partition, ScenarioPartition) or not isinstance(
            self.start_adapter, RedPpStartAdapter
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization source semantics are invalid"
            )
        for numeric_value, lower, upper, subject in (
            (self.target_party_slot, 1, 6, "target slot"),
            (self.target_species_id, 1, 0xFF, "target species"),
            (self.target_level, 1, 100, "target level"),
            (self.target_hp, 1, 999, "target HP"),
            (self.target_max_hp, 1, 999, "target maximum HP"),
            (self.current_total_pp, 1, 252, "current PP"),
            (self.maximum_total_pp, 1, 252, "maximum PP"),
            (self.middle_pp_ceiling, 0, 252, "middle-PP ceiling"),
            (self.minimum_pp_consumption, 1, 252, "minimum PP consumption"),
            (self.safe_current_pp, 1, 252, "safe current PP"),
            (self.venue_map_id, 0, 0xFF, "venue map"),
            (self.venue_maximum_wild_level, 1, 100, "wild level ceiling"),
        ):
            if (
                type(numeric_value) is not int  # noqa: E721
                or not lower <= numeric_value <= upper
            ):
                raise RedPartyDevelopmentPpMaterializationError(
                    f"PP materialization {subject} is invalid"
                )
        if self.target_hp > self.target_max_hp or self.target_hp * 20 < self.target_max_hp * 19:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization target must begin at or above 95% HP"
            )
        for values, subject in (
            (self.target_move_ids, "move"),
            (self.target_initial_packed_pp, "packed PP"),
        ):
            if (
                not isinstance(values, tuple)
                or len(values) != 4
                or any(type(value) is not int or not 0 <= value <= 0xFF for value in values)  # noqa: E721
            ):
                raise RedPartyDevelopmentPpMaterializationError(
                    f"PP materialization target {subject} vector is invalid"
                )
        try:
            decoded_pp = decode_red_party_pp(
                self.target_move_ids,
                self.target_initial_packed_pp,
            )
        except RedPartyPpError as error:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization target PP evidence is invalid"
            ) from error
        expected_safe_slots = natural_pp_depletion_slots(decoded_pp)
        expected_safe_pp = sum(
            decoded_pp.moves[slot - 1].current_pp
            for slot in expected_safe_slots
        )
        if (
            not isinstance(self.safe_move_slots, tuple)
            or not self.safe_move_slots
            or self.safe_move_slots != tuple(sorted(set(self.safe_move_slots)))
            or any(type(slot) is not int or not 1 <= slot <= 4 for slot in self.safe_move_slots)  # noqa: E721
            or self.safe_move_slots != expected_safe_slots
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization safe move slots are invalid"
            )
        expected_middle = (67 * self.maximum_total_pp - 1) // 100
        if (
            self.current_total_pp != decoded_pp.current_total
            or self.maximum_total_pp != decoded_pp.maximum_total
            or self.safe_current_pp != expected_safe_pp
            or self.current_total_pp > self.maximum_total_pp
            or self.current_total_pp * 100 < self.maximum_total_pp * 67
            or self.middle_pp_ceiling != expected_middle
            or self.minimum_pp_consumption
            != self.current_total_pp - self.middle_pp_ceiling
            or self.safe_current_pp < self.minimum_pp_consumption
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization depletion arithmetic is invalid"
            )
        if self.target_party_slot != 1:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization target must be the field lead"
            )
        if not isinstance(self.target_has_evolution_route, bool):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization evolution-route flag is invalid"
            )
        if self.target_has_evolution_route:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization target cannot cross an evolution route"
            )
        if self.target_level < self.venue_maximum_wild_level + 10:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization target lacks the frozen safety margin"
            )
        if (
            not isinstance(self.possible_wild_species_ids, tuple)
            or not self.possible_wild_species_ids
            or self.possible_wild_species_ids
            != tuple(sorted(set(self.possible_wild_species_ids)))
            or any(
                type(value) is not int or not 1 <= value <= 0xFF  # noqa: E721
                for value in self.possible_wild_species_ids
            )
            or canonical_sha256(list(self.possible_wild_species_ids))
            != self.possible_wild_species_sha256
            or self.all_possible_wild_species_seen is not True
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization wild-species protection is incomplete"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_SOURCE_SCHEMA,
            "scenario_id": self.scenario_id,
            "partition": self.partition.value,
            "source_checkpoint_id": self.source_checkpoint_id,
            "source_state_sha256": self.source_state_sha256,
            "source_envelope_sha256": self.source_envelope_sha256,
            "source_semantic_signature_sha256": (
                self.source_semantic_signature_sha256
            ),
            "source_root_lineage_id": self.source_root_lineage_id,
            "source_boundary_sha256": self.source_boundary_sha256,
            "protected_state_sha256": self.protected_state_sha256,
            "start_adapter": self.start_adapter.value,
            "target_party_slot": self.target_party_slot,
            "target_species_id": self.target_species_id,
            "target_level": self.target_level,
            "target_hp": self.target_hp,
            "target_max_hp": self.target_max_hp,
            "target_move_ids": list(self.target_move_ids),
            "target_initial_packed_pp": list(self.target_initial_packed_pp),
            "safe_move_slots": list(self.safe_move_slots),
            "current_total_pp": self.current_total_pp,
            "maximum_total_pp": self.maximum_total_pp,
            "middle_pp_ceiling": self.middle_pp_ceiling,
            "minimum_pp_consumption": self.minimum_pp_consumption,
            "safe_current_pp": self.safe_current_pp,
            "target_has_evolution_route": self.target_has_evolution_route,
            "venue_map_id": self.venue_map_id,
            "venue_binding_sha256": self.venue_binding_sha256,
            "venue_maximum_wild_level": self.venue_maximum_wild_level,
            "possible_wild_species_ids": list(self.possible_wild_species_ids),
            "possible_wild_species_sha256": self.possible_wild_species_sha256,
            "all_possible_wild_species_seen": (
                self.all_possible_wild_species_seen
            ),
            "output_capture_id": self.output_capture_id,
        }

    @classmethod
    def from_private_dict(cls, value: object) -> RedPpMaterializationSource:
        if not isinstance(value, Mapping):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization source document is invalid"
            )
        expected = set(cls._field_names()) | {"schema"}
        if (
            set(value) != expected
            or value.get("schema")
            != RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_SOURCE_SCHEMA
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization source document is invalid"
            )
        try:
            return cls(
                scenario_id=cast(str, value["scenario_id"]),
                partition=ScenarioPartition(cast(str, value["partition"])),
                source_checkpoint_id=cast(str, value["source_checkpoint_id"]),
                source_state_sha256=cast(str, value["source_state_sha256"]),
                source_envelope_sha256=cast(str, value["source_envelope_sha256"]),
                source_semantic_signature_sha256=cast(
                    str, value["source_semantic_signature_sha256"]
                ),
                source_root_lineage_id=cast(str, value["source_root_lineage_id"]),
                source_boundary_sha256=cast(str, value["source_boundary_sha256"]),
                protected_state_sha256=cast(str, value["protected_state_sha256"]),
                start_adapter=RedPpStartAdapter(cast(str, value["start_adapter"])),
                target_party_slot=cast(int, value["target_party_slot"]),
                target_species_id=cast(int, value["target_species_id"]),
                target_level=cast(int, value["target_level"]),
                target_hp=cast(int, value["target_hp"]),
                target_max_hp=cast(int, value["target_max_hp"]),
                target_move_ids=cast(
                    tuple[int, int, int, int], tuple(value["target_move_ids"])
                ),
                target_initial_packed_pp=cast(
                    tuple[int, int, int, int],
                    tuple(value["target_initial_packed_pp"]),
                ),
                safe_move_slots=tuple(cast(list[int], value["safe_move_slots"])),
                current_total_pp=cast(int, value["current_total_pp"]),
                maximum_total_pp=cast(int, value["maximum_total_pp"]),
                middle_pp_ceiling=cast(int, value["middle_pp_ceiling"]),
                minimum_pp_consumption=cast(int, value["minimum_pp_consumption"]),
                safe_current_pp=cast(int, value["safe_current_pp"]),
                target_has_evolution_route=cast(
                    bool, value["target_has_evolution_route"]
                ),
                venue_map_id=cast(int, value["venue_map_id"]),
                venue_binding_sha256=cast(str, value["venue_binding_sha256"]),
                venue_maximum_wild_level=cast(
                    int, value["venue_maximum_wild_level"]
                ),
                possible_wild_species_ids=tuple(
                    cast(list[int], value["possible_wild_species_ids"])
                ),
                possible_wild_species_sha256=cast(
                    str, value["possible_wild_species_sha256"]
                ),
                all_possible_wild_species_seen=cast(
                    bool, value["all_possible_wild_species_seen"]
                ),
                output_capture_id=cast(str, value["output_capture_id"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization source document is invalid"
            ) from error

    @staticmethod
    def _field_names() -> tuple[str, ...]:
        return (
            "scenario_id",
            "partition",
            "source_checkpoint_id",
            "source_state_sha256",
            "source_envelope_sha256",
            "source_semantic_signature_sha256",
            "source_root_lineage_id",
            "source_boundary_sha256",
            "protected_state_sha256",
            "start_adapter",
            "target_party_slot",
            "target_species_id",
            "target_level",
            "target_hp",
            "target_max_hp",
            "target_move_ids",
            "target_initial_packed_pp",
            "safe_move_slots",
            "current_total_pp",
            "maximum_total_pp",
            "middle_pp_ceiling",
            "minimum_pp_consumption",
            "safe_current_pp",
            "target_has_evolution_route",
            "venue_map_id",
            "venue_binding_sha256",
            "venue_maximum_wild_level",
            "possible_wild_species_ids",
            "possible_wild_species_sha256",
            "all_possible_wild_species_seen",
            "output_capture_id",
        )


@dataclass(frozen=True, slots=True)
class RedPartyDevelopmentPpMaterializationPlan:
    """Exact private two-entry plan, still closed to controller input."""

    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str
    inventory_sha256: str
    inventory_file_sha256: str
    reservation_plan_sha256: str
    reservation_plan_file_sha256: str
    venue_prior_registry_sha256: str
    venue_prior_registry_file_sha256: str
    venue_prior_count: int
    context_catalog_sha256: str
    context_catalog_file_sha256: str
    entries: tuple[RedPpMaterializationSource, ...]
    bounds: RedPpMaterializationBounds = RED_PP_MATERIALIZATION_BOUNDS
    execution_contract_sha256: str = (
        RED_PP_MATERIALIZATION_EXECUTION_CONTRACT_SHA256
    )

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization source commit is invalid"
            )
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.rom_sha256, "ROM"),
            (self.inventory_sha256, "inventory"),
            (self.inventory_file_sha256, "inventory file"),
            (self.reservation_plan_sha256, "reservation plan"),
            (self.reservation_plan_file_sha256, "reservation plan file"),
            (self.venue_prior_registry_sha256, "venue registry"),
            (self.venue_prior_registry_file_sha256, "venue registry file"),
            (self.context_catalog_sha256, "context catalog"),
            (self.context_catalog_file_sha256, "context catalog file"),
            (self.execution_contract_sha256, "execution contract"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise RedPartyDevelopmentPpMaterializationError(
                    f"PP materialization {subject} digest is invalid"
                )
        if (
            type(self.venue_prior_count) is not int  # noqa: E721
            or self.venue_prior_count != 2
            or not isinstance(self.bounds, RedPpMaterializationBounds)
            or self.bounds != RED_PP_MATERIALIZATION_BOUNDS
            or self.execution_contract_sha256
            != RED_PP_MATERIALIZATION_EXECUTION_CONTRACT_SHA256
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization plan contract is invalid"
            )
        if (
            not isinstance(self.entries, tuple)
            or len(self.entries) != 2
            or self.entries
            != tuple(sorted(self.entries, key=lambda item: item.scenario_id))
            or {item.partition for item in self.entries}
            != {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization plan needs one ordered source per partition"
            )
        for attribute, subject in (
            ("scenario_id", "scenario"),
            ("source_checkpoint_id", "source checkpoint"),
            ("source_root_lineage_id", "source root"),
            ("source_state_sha256", "source state"),
            ("output_capture_id", "output capture"),
        ):
            values = tuple(getattr(item, attribute) for item in self.entries)
            if len(values) != len(set(values)):
                raise RedPartyDevelopmentPpMaterializationError(
                    f"PP materialization plan repeats a {subject}"
                )
        if len({item.venue_binding_sha256 for item in self.entries}) != 1:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization sources do not share one frozen venue"
            )
        if (
            {item.start_adapter for item in self.entries} != set(RedPpStartAdapter)
            or len({item.venue_map_id for item in self.entries}) != 1
            or len({item.venue_maximum_wild_level for item in self.entries}) != 1
            or len({item.possible_wild_species_ids for item in self.entries}) != 1
            or any(
                item.minimum_pp_consumption
                > self.bounds.maximum_completed_battles
                for item in self.entries
            )
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization sources disagree with the frozen execution bounds"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self._document())

    def _document(self) -> dict[str, object]:
        return {
            "schema": RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_PLAN_SCHEMA,
            "status": "prospective_unexecuted_authorization_required",
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "rom_sha256": self.rom_sha256,
            "inventory_sha256": self.inventory_sha256,
            "inventory_file_sha256": self.inventory_file_sha256,
            "reservation_plan_sha256": self.reservation_plan_sha256,
            "reservation_plan_file_sha256": self.reservation_plan_file_sha256,
            "venue_prior_registry_sha256": self.venue_prior_registry_sha256,
            "venue_prior_registry_file_sha256": (
                self.venue_prior_registry_file_sha256
            ),
            "venue_prior_count": self.venue_prior_count,
            "context_catalog_sha256": self.context_catalog_sha256,
            "context_catalog_file_sha256": self.context_catalog_file_sha256,
            "execution_contract": RED_PP_MATERIALIZATION_EXECUTION_CONTRACT,
            "execution_contract_sha256": self.execution_contract_sha256,
            "bounds": self.bounds.public_dict(),
            "entries": [item.private_dict() for item in self.entries],
            "execution_authorized": False,
            "materializations_completed": 0,
            "candidate_menus_frozen": 0,
            "learner_outcomes_opened": 0,
            "controller_actions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }

    def private_dict(self) -> dict[str, object]:
        return {**self._document(), "plan_sha256": self.plan_sha256}

    def public_summary(self) -> dict[str, object]:
        partitions = Counter(item.partition.value for item in self.entries)
        return {
            "schema": RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_SUMMARY_SCHEMA,
            "status": "read_only_preflight_complete_controller_authorization_required",
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "rom_sha256": self.rom_sha256,
            "inventory_sha256": self.inventory_sha256,
            "reservation_plan_sha256": self.reservation_plan_sha256,
            "venue_prior_registry_sha256": self.venue_prior_registry_sha256,
            "venue_prior_count": self.venue_prior_count,
            "context_catalog_sha256": self.context_catalog_sha256,
            "private_plan_sha256": self.plan_sha256,
            "execution_contract_sha256": self.execution_contract_sha256,
            "bounds": self.bounds.public_dict(),
            "preparations_planned": len(self.entries),
            "partition_counts": dict(sorted(partitions.items())),
            "unique_authenticated_roots": len(
                {item.source_root_lineage_id for item in self.entries}
            ),
            "unique_source_states": len(
                {item.source_state_sha256 for item in self.entries}
            ),
            "source_pp_bin": "high",
            "target_pp_bin": "middle",
            "safe_move_capacity_sufficient": sum(
                item.safe_current_pp >= item.minimum_pp_consumption
                for item in self.entries
            ),
            "wild_species_seen_coverage_complete": sum(
                item.all_possible_wild_species_seen for item in self.entries
            ),
            "source_start_adapters_frozen": len(
                {item.start_adapter for item in self.entries}
            ),
            "execution_authorized": False,
            "materializations_completed": 0,
            "candidate_menus_frozen": 0,
            "learner_outcomes_opened": 0,
            "controller_actions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
            "authority_promoted": False,
            "source_checkpoint_identity_public": False,
            "party_species_identity_public": False,
            "party_slot_identity_public": False,
            "move_identity_public": False,
            "candidate_feature_values_public": False,
            "private_path_fields": 0,
        }

    @classmethod
    def from_private_dict(
        cls, value: object
    ) -> RedPartyDevelopmentPpMaterializationPlan:
        if not isinstance(value, Mapping):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization plan document is invalid"
            )
        expected = {
            "authority_promoted",
            "bounds",
            "candidate_menus_frozen",
            "context_catalog_file_sha256",
            "context_catalog_sha256",
            "controller_actions",
            "crystal_cases_opened",
            "entries",
            "execution_authorized",
            "execution_contract",
            "execution_contract_sha256",
            "full_game_replays",
            "inventory_file_sha256",
            "inventory_sha256",
            "learner_outcomes_opened",
            "materializations_completed",
            "model_predictions",
            "model_updates",
            "plan_sha256",
            "private_path_fields",
            "reservation_plan_file_sha256",
            "reservation_plan_sha256",
            "rom_sha256",
            "schema",
            "sealed_red_cases_opened",
            "source_bundle_sha256",
            "source_commit",
            "status",
            "teacher_queries",
            "venue_prior_count",
            "venue_prior_registry_file_sha256",
            "venue_prior_registry_sha256",
        }
        zero_fields = (
            "candidate_menus_frozen",
            "controller_actions",
            "crystal_cases_opened",
            "full_game_replays",
            "learner_outcomes_opened",
            "materializations_completed",
            "model_predictions",
            "model_updates",
            "sealed_red_cases_opened",
            "teacher_queries",
        )
        if (
            set(value) != expected
            or value.get("schema")
            != RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_PLAN_SCHEMA
            or value.get("status")
            != "prospective_unexecuted_authorization_required"
            or value.get("execution_contract")
            != RED_PP_MATERIALIZATION_EXECUTION_CONTRACT
            or value.get("execution_authorized") is not False
            or value.get("authority_promoted") is not False
            or value.get("private_path_fields") != 0
            or any(value.get(name) != 0 for name in zero_fields)
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization plan document is invalid"
            )
        bounds = value.get("bounds")
        rows = value.get("entries")
        if not isinstance(bounds, Mapping) or not isinstance(rows, list):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization plan rows are invalid"
            )
        try:
            result = cls(
                source_commit=cast(str, value["source_commit"]),
                source_bundle_sha256=cast(str, value["source_bundle_sha256"]),
                rom_sha256=cast(str, value["rom_sha256"]),
                inventory_sha256=cast(str, value["inventory_sha256"]),
                inventory_file_sha256=cast(str, value["inventory_file_sha256"]),
                reservation_plan_sha256=cast(
                    str, value["reservation_plan_sha256"]
                ),
                reservation_plan_file_sha256=cast(
                    str, value["reservation_plan_file_sha256"]
                ),
                venue_prior_registry_sha256=cast(
                    str, value["venue_prior_registry_sha256"]
                ),
                venue_prior_registry_file_sha256=cast(
                    str, value["venue_prior_registry_file_sha256"]
                ),
                venue_prior_count=cast(int, value["venue_prior_count"]),
                context_catalog_sha256=cast(
                    str, value["context_catalog_sha256"]
                ),
                context_catalog_file_sha256=cast(
                    str, value["context_catalog_file_sha256"]
                ),
                entries=tuple(
                    RedPpMaterializationSource.from_private_dict(item)
                    for item in rows
                ),
                bounds=RedPpMaterializationBounds(
                    maximum_completed_battles=cast(
                        int, bounds["maximum_completed_battles"]
                    ),
                    maximum_encounter_steps=cast(
                        int, bounds["maximum_encounter_steps"]
                    ),
                    maximum_controller_actions=cast(
                        int, bounds["maximum_controller_actions"]
                    ),
                    maximum_frames=cast(int, bounds["maximum_frames"]),
                ),
                execution_contract_sha256=cast(
                    str, value["execution_contract_sha256"]
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization plan document is invalid"
            ) from error
        if value.get("plan_sha256") != result.plan_sha256:
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization plan digest differs"
            )
        return result


def freeze_red_party_development_pp_materialization_plan(
    reservation_plan: PartyDevelopmentQuestionReservationPlan,
    *,
    sources: tuple[RedPpMaterializationSource, ...],
    source_commit: str,
    source_bundle_sha256: str,
    rom_sha256: str,
    inventory_file_sha256: str,
    reservation_plan_file_sha256: str,
    venue_prior_registry_file_sha256: str,
    context_catalog_sha256: str,
    context_catalog_file_sha256: str,
) -> RedPartyDevelopmentPpMaterializationPlan:
    """Bind two read-only observations to the exact refreshed reservations."""

    if not isinstance(reservation_plan, PartyDevelopmentQuestionReservationPlan):
        raise TypeError("reservation_plan must be a reservation plan")
    if not isinstance(sources, tuple) or any(
        not isinstance(item, RedPpMaterializationSource) for item in sources
    ):
        raise TypeError("sources must be PP materialization sources")
    reservations = tuple(
        item
        for item in reservation_plan.reservations
        if item.preparation
        is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
    )
    if len(reservations) != 2:
        raise RedPartyDevelopmentPpMaterializationError(
            "PP materialization requires exactly two reserved preparations"
        )
    reservations_by_scenario = {
        item.scenario_id: item for item in reservations
    }
    if set(reservations_by_scenario) != {item.scenario_id for item in sources}:
        raise RedPartyDevelopmentPpMaterializationError(
            "PP materialization sources differ from the reserved scenarios"
        )
    for source in sources:
        reservation = reservations_by_scenario[source.scenario_id]
        if (
            source.partition is not reservation.partition
            or source.source_checkpoint_id != reservation.source_checkpoint_id
            or source.source_state_sha256 != reservation.source_state_sha256
            or source.source_envelope_sha256
            != reservation.source_envelope_sha256
            or source.source_semantic_signature_sha256
            != reservation.source_semantic_signature_sha256
            or reservation.target_pp_bin != "middle"
        ):
            raise RedPartyDevelopmentPpMaterializationError(
                "PP materialization source differs from its reservation"
            )
    return RedPartyDevelopmentPpMaterializationPlan(
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        rom_sha256=rom_sha256,
        inventory_sha256=reservation_plan.inventory_sha256,
        inventory_file_sha256=inventory_file_sha256,
        reservation_plan_sha256=reservation_plan.plan_sha256,
        reservation_plan_file_sha256=reservation_plan_file_sha256,
        venue_prior_registry_sha256=reservation_plan.venue_prior_registry_sha256,
        venue_prior_registry_file_sha256=venue_prior_registry_file_sha256,
        venue_prior_count=reservation_plan.venue_prior_count,
        context_catalog_sha256=context_catalog_sha256,
        context_catalog_file_sha256=context_catalog_file_sha256,
        entries=tuple(sorted(sources, key=lambda item: item.scenario_id)),
    )


__all__ = [
    "RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_PLAN_SCHEMA",
    "RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_SOURCE_SCHEMA",
    "RED_PARTY_DEVELOPMENT_PP_MATERIALIZATION_SUMMARY_SCHEMA",
    "RED_PP_MATERIALIZATION_BOUNDS",
    "RED_PP_MATERIALIZATION_EXECUTION_CONTRACT",
    "RED_PP_MATERIALIZATION_EXECUTION_CONTRACT_SHA256",
    "RedPartyDevelopmentPpMaterializationError",
    "RedPartyDevelopmentPpMaterializationPlan",
    "RedPpMaterializationBounds",
    "RedPpMaterializationSource",
    "RedPpStartAdapter",
    "freeze_red_party_development_pp_materialization_plan",
    "red_pp_protected_state_sha256",
    "red_pp_source_boundary_sha256",
]
