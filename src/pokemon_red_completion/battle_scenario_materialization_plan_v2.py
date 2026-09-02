"""Outcome-blind multi-venue freeze for partition-sized Red battle captures.

The historical V1 plan binds each retained root to the one venue implied by
its loaded map.  V2 instead freezes the exact root-to-reachable-venue edge
proved by the action-free V7 census.  It deliberately remains a private plan:
public receipts may report counts, never root identities or selected edges.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from pokemon_red_completion.battle_outcome_batch import (
    DEVELOPMENT_CONTEXTS,
    FRESH_TRAIN_CONTEXTS,
    MAXIMUM_LEVEL_GAP,
)
from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (
    BattleScenarioPartySlot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_venue_allocation import (
    ReachableVenueRoot,
    allocate_additive_reachable_venue_roots,
    allocate_reachable_venue_roots,
)

BATTLE_SCENARIO_MATERIALIZATION_PLAN_V2_SCHEMA = (
    "pokemon.red.private-battle-scenario-materialization-plan.v2"
)
BATTLE_SCENARIO_MATERIALIZATION_SELECTION_POLICY_V2_SCHEMA = (
    "pokemon.red.battle-scenario-materialization-selection-policy.v2"
)
BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_PLAN_SCHEMA = (
    "pokemon.red.private-battle-scenario-materialization-completion-plan.v1"
)
BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SUCCESSOR_PLAN_SCHEMA = (
    "pokemon.red.private-battle-scenario-materialization-completion-plan.v2"
)
BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SELECTION_POLICY_SCHEMA = (
    "pokemon.red.battle-scenario-materialization-completion-selection-policy.v1"
)

REQUIRED_CAPTURE_COUNT = FRESH_TRAIN_CONTEXTS
MAXIMUM_CAPTURE_COUNT = max(FRESH_TRAIN_CONTEXTS, DEVELOPMENT_CONTEXTS)
MINIMUM_DISTINCT_VENUES = 2
MAXIMUM_CAPTURES_PER_VENUE = 6

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SAFE_FILENAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_MAXIMUM_PLAN_BYTES = 8 * 1024 * 1024

_SELECTION_POLICY = {
    "schema": BATTLE_SCENARIO_MATERIALIZATION_SELECTION_POLICY_V2_SCHEMA,
    "capture_count": REQUIRED_CAPTURE_COUNT,
    "minimum_distinct_venues": MINIMUM_DISTINCT_VENUES,
    "maximum_captures_per_venue": MAXIMUM_CAPTURES_PER_VENUE,
    "maximum_level_gap": MAXIMUM_LEVEL_GAP,
    "encounter_level_guard": (
        "party_level_within_maximum_gap_of_every_measured_level_including_rare_ceiling"
    ),
    "root_venue_allocation": "exact_capacitated_title_neutral_v1",
    "allocation_order": ["candidate_identity_sha256_asc", "venue_id_asc"],
    "party_slot_selection_order": [
        "selected_species_count_asc",
        "selected_party_slot_count_asc",
        "selected_status_count_asc",
        "selected_level_count_asc",
        "usable_move_count_desc",
        "hp_ratio_desc",
        "party_slot_asc",
    ],
    "source_reuse": False,
    "replacement_slots": 0,
    "controller_actions": 0,
    "outcome_fields": 0,
    "prediction_fields": 0,
    "teacher_choice_fields": 0,
}
_COMPLETION_SELECTION_POLICY = {
    "schema": BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SELECTION_POLICY_SCHEMA,
    "required_total_capture_count": REQUIRED_CAPTURE_COUNT,
    "minimum_total_distinct_venues": MINIMUM_DISTINCT_VENUES,
    "maximum_total_captures_per_venue": MAXIMUM_CAPTURES_PER_VENUE,
    "retained_successes_are_fixed": True,
    "terminal_failures_are_retained": True,
    "new_assignment_count": "required_total_minus_retained_success_count",
    "root_venue_allocation": "exact_additive_capacitated_title_neutral_v1",
    "allocation_order": ["candidate_identity_sha256_asc", "venue_id_asc"],
    "party_slot_selection_order": _SELECTION_POLICY["party_slot_selection_order"],
    "source_reuse": False,
    "failed_assignment_reclassification": False,
    "replacement_slots_inside_prior_denominator": 0,
    "controller_actions": 0,
    "outcome_fields": 0,
    "prediction_fields": 0,
    "teacher_choice_fields": 0,
}


class BattleScenarioMaterializationPlanV2Error(ValueError):
    """Raised before a V2 private assignment can drift or leak."""


@dataclass(frozen=True, slots=True)
class BattleScenarioReachableVenue:
    """One executable venue edge and the party slots eligible at that edge."""

    venue_id: str
    source_location: str
    minimum_encounter_level: int
    maximum_encounter_level: int
    rare_maximum_encounter_level: int
    party_slots: tuple[BattleScenarioPartySlot, ...]

    def __post_init__(self) -> None:
        if (
            _SAFE_ID.fullmatch(self.venue_id) is None
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
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization reachable venue differs"
            )
        minimum_safe_level = self.rare_maximum_encounter_level - MAXIMUM_LEVEL_GAP
        maximum_safe_level = self.minimum_encounter_level + MAXIMUM_LEVEL_GAP
        if any(
            not minimum_safe_level <= slot.level <= maximum_safe_level
            for slot in self.party_slots
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization reachable venue exceeds the frozen level gap"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "maximum_encounter_level": self.maximum_encounter_level,
            "minimum_encounter_level": self.minimum_encounter_level,
            "party_slots": [slot.private_dict() for slot in self.party_slots],
            "rare_maximum_encounter_level": self.rare_maximum_encounter_level,
            "source_location": self.source_location,
            "venue_id": self.venue_id,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationCandidateV2:
    """One authenticated source root and all of its eligible venue edges."""

    source: BattleScenarioSourceBinding
    reachable_venues: tuple[BattleScenarioReachableVenue, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source, BattleScenarioSourceBinding)
            or self.source.partition
            not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}
            or not isinstance(self.reachable_venues, tuple)
            or not self.reachable_venues
            or any(
                not isinstance(venue, BattleScenarioReachableVenue)
                for venue in self.reachable_venues
            )
            or tuple(sorted(self.reachable_venues, key=lambda item: item.venue_id))
            != self.reachable_venues
            or len({venue.venue_id for venue in self.reachable_venues})
            != len(self.reachable_venues)
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization candidate differs"
            )

    @property
    def candidate_identity_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def venue(self, venue_id: str) -> BattleScenarioReachableVenue:
        matching = tuple(item for item in self.reachable_venues if item.venue_id == venue_id)
        if len(matching) != 1:
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization selected venue differs"
            )
        return matching[0]

    def private_dict(self) -> dict[str, object]:
        return {
            "reachable_venues": [item.private_dict() for item in self.reachable_venues],
            "source": self.source.public_dict(),
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationAssignmentV2:
    """One root, reachable venue, and mechanics-exact party slot frozen together."""

    ordinal: int
    capture_id: str
    candidate: BattleScenarioMaterializationCandidateV2
    selected_venue: BattleScenarioReachableVenue
    party_slot: BattleScenarioPartySlot
    state_filename: str
    manifest_filename: str

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int  # noqa: E721
            or not 0 <= self.ordinal < MAXIMUM_CAPTURE_COUNT
            or _SAFE_ID.fullmatch(self.capture_id) is None
            or not isinstance(self.candidate, BattleScenarioMaterializationCandidateV2)
            or self.selected_venue not in self.candidate.reachable_venues
            or self.party_slot not in self.selected_venue.party_slots
            or _SAFE_FILENAME.fullmatch(self.state_filename) is None
            or _SAFE_FILENAME.fullmatch(self.manifest_filename) is None
            or self.state_filename == self.manifest_filename
            or not self.state_filename.endswith(".state")
            or not self.manifest_filename.endswith(".state.json")
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization assignment differs"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "candidate_identity_sha256": self.candidate.candidate_identity_sha256,
            "capture_id": self.capture_id,
            "manifest_filename": self.manifest_filename,
            "ordinal": self.ordinal,
            "party_slot": self.party_slot.party_slot,
            "selected_venue_id": self.selected_venue.venue_id,
            "state_filename": self.state_filename,
        }


@dataclass(frozen=True, slots=True)
class RetainedBattleScenarioMaterializationCapture:
    """One immutable successful output from the terminal predecessor journal."""

    ordinal: int
    capture_id: str
    assignment_sha256: str
    source_commit: str
    source_state_sha256: str
    root_lineage_id: str
    venue_id: str
    party_slot: BattleScenarioPartySlot
    state_filename: str
    manifest_filename: str
    state_sha256: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int  # noqa: E721
            or not 0 <= self.ordinal < MAXIMUM_CAPTURE_COUNT
            or _SAFE_ID.fullmatch(self.capture_id) is None
            or _SHA256.fullmatch(self.assignment_sha256) is None
            or _GIT_COMMIT.fullmatch(self.source_commit) is None
            or _SHA256.fullmatch(self.source_state_sha256) is None
            or _SAFE_ID.fullmatch(self.root_lineage_id) is None
            or _SAFE_ID.fullmatch(self.venue_id) is None
            or not isinstance(self.party_slot, BattleScenarioPartySlot)
            or _SAFE_FILENAME.fullmatch(self.state_filename) is None
            or _SAFE_FILENAME.fullmatch(self.manifest_filename) is None
            or not self.state_filename.endswith(".state")
            or not self.manifest_filename.endswith(".state.json")
            or self.state_filename == self.manifest_filename
            or _SHA256.fullmatch(self.state_sha256) is None
            or _SHA256.fullmatch(self.manifest_sha256) is None
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "retained battle materialization capture differs"
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
            "source_commit": self.source_commit,
            "source_state_sha256": self.source_state_sha256,
            "state_filename": self.state_filename,
            "state_sha256": self.state_sha256,
            "venue_id": self.venue_id,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationSupplementalExclusion:
    """One later terminal tranche whose attempted roots remain unavailable."""

    plan_sha256: str
    run_journal_sha256: str

    def __post_init__(self) -> None:
        if (
            _SHA256.fullmatch(self.plan_sha256) is None
            or _SHA256.fullmatch(self.run_journal_sha256) is None
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization supplemental exclusion differs"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "plan_sha256": self.plan_sha256,
            "run_journal_sha256": self.run_journal_sha256,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationCompletionPlan:
    """Add only missing captures while preserving a terminal predecessor."""

    plan_id: str
    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str
    capture_directory_sha256: str
    earliest_excluded_plan_sha256: str
    earliest_excluded_run_journal_sha256: str
    predecessor_plan_sha256: str
    predecessor_run_journal_sha256: str
    predecessor_capture_directory_sha256: str
    predecessor_failure_count: int
    retained_successes: tuple[RetainedBattleScenarioMaterializationCapture, ...]
    inventory: tuple[BattleScenarioMaterializationCandidateV2, ...]
    assignments: tuple[BattleScenarioMaterializationAssignmentV2, ...]
    supplemental_exclusions: tuple[
        BattleScenarioMaterializationSupplementalExclusion, ...
    ] = ()

    def __post_init__(self) -> None:
        digests = (
            self.source_bundle_sha256,
            self.rom_sha256,
            self.capture_directory_sha256,
            self.earliest_excluded_plan_sha256,
            self.earliest_excluded_run_journal_sha256,
            self.predecessor_plan_sha256,
            self.predecessor_run_journal_sha256,
            self.predecessor_capture_directory_sha256,
        )
        if (
            _SAFE_ID.fullmatch(self.plan_id) is None
            or _GIT_COMMIT.fullmatch(self.source_commit) is None
            or any(_SHA256.fullmatch(value) is None for value in digests)
            or not isinstance(self.supplemental_exclusions, tuple)
            or any(
                not isinstance(
                    item,
                    BattleScenarioMaterializationSupplementalExclusion,
                )
                for item in self.supplemental_exclusions
            )
            or tuple(
                sorted(
                    self.supplemental_exclusions,
                    key=lambda item: (item.plan_sha256, item.run_journal_sha256),
                )
            )
            != self.supplemental_exclusions
            or len(
                {
                    (item.plan_sha256, item.run_journal_sha256)
                    for item in self.supplemental_exclusions
                }
            )
            != len(self.supplemental_exclusions)
            or type(self.predecessor_failure_count) is not int  # noqa: E721
            or self.predecessor_failure_count < 1
            or not isinstance(self.retained_successes, tuple)
            or not self.retained_successes
            or any(
                not isinstance(item, RetainedBattleScenarioMaterializationCapture)
                for item in self.retained_successes
            )
            or tuple(sorted(self.retained_successes, key=lambda item: item.ordinal))
            != self.retained_successes
            or len({item.ordinal for item in self.retained_successes})
            != len(self.retained_successes)
            or len({item.capture_id for item in self.retained_successes})
            != len(self.retained_successes)
            or len({item.source_state_sha256 for item in self.retained_successes})
            != len(self.retained_successes)
            or not isinstance(self.inventory, tuple)
            or not self.inventory
            or any(
                not isinstance(item, BattleScenarioMaterializationCandidateV2)
                for item in self.inventory
            )
            or len({item.source.partition for item in self.inventory}) != 1
            or tuple(
                sorted(self.inventory, key=lambda item: item.candidate_identity_sha256)
            )
            != self.inventory
            or len({item.candidate_identity_sha256 for item in self.inventory})
            != len(self.inventory)
            or len({item.source.source_state_sha256 for item in self.inventory})
            != len(self.inventory)
            or {
                item.source.source_state_sha256 for item in self.inventory
            }.intersection(
                item.source_state_sha256 for item in self.retained_successes
            )
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization completion plan differs"
            )
        required_capture_count = _required_capture_count(self.partition)
        if (
            len(self.retained_successes) + self.predecessor_failure_count
            != required_capture_count
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization completion plan differs"
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
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization completion source provenance differs"
            )
        if self.assignments != _select_completion_assignments(
            self.plan_id,
            self.inventory,
            self.retained_successes,
        ):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization completion assignment is not canonical"
            )
        if len(
            {
                *(item.capture_id for item in self.retained_successes),
                *(item.capture_id for item in self.assignments),
            }
        ) != required_capture_count:
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization completion capture identity differs"
            )

    @property
    def selection_policy_sha256(self) -> str:
        return canonical_sha256(_completion_selection_policy(self.partition))

    @property
    def partition(self) -> ScenarioPartition:
        """Return the immutable partition inherited from the predecessor."""

        partitions = {item.source.partition for item in self.inventory}
        if len(partitions) != 1:  # pragma: no cover - __post_init__ closes this
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization completion plan partition differs"
            )
        return next(iter(partitions))

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def private_dict(self) -> dict[str, object]:
        value = {
            "assignments": [item.private_dict() for item in self.assignments],
            "capture_directory_sha256": self.capture_directory_sha256,
            "earliest_excluded_plan_sha256": self.earliest_excluded_plan_sha256,
            "earliest_excluded_run_journal_sha256": (
                self.earliest_excluded_run_journal_sha256
            ),
            "effects": _zero_effects(),
            "inventory": [item.private_dict() for item in self.inventory],
            "plan_id": self.plan_id,
            "predecessor_capture_directory_sha256": (
                self.predecessor_capture_directory_sha256
            ),
            "predecessor_failure_count": self.predecessor_failure_count,
            "predecessor_plan_sha256": self.predecessor_plan_sha256,
            "predecessor_run_journal_sha256": self.predecessor_run_journal_sha256,
            "retained_successes": [
                item.private_dict() for item in self.retained_successes
            ],
            "retry_after_controller_input": False,
            "rom_sha256": self.rom_sha256,
            "schema": (
                BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SUCCESSOR_PLAN_SCHEMA
                if self.supplemental_exclusions
                else BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_PLAN_SCHEMA
            ),
            "selection_policy_sha256": self.selection_policy_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "status": "prospective_unexecuted_additive_completion",
        }
        if self.supplemental_exclusions:
            value["supplemental_exclusions"] = [
                item.private_dict() for item in self.supplemental_exclusions
            ]
        return value

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.private_dict())


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationPlanV2:
    """Canonical complete inventory and its partition-sized exact allocation."""

    plan_id: str
    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str
    capture_directory_sha256: str
    excluded_plan_sha256: str
    excluded_run_journal_sha256: str
    inventory: tuple[BattleScenarioMaterializationCandidateV2, ...]
    assignments: tuple[BattleScenarioMaterializationAssignmentV2, ...]

    def __post_init__(self) -> None:
        digests = (
            self.source_bundle_sha256,
            self.rom_sha256,
            self.capture_directory_sha256,
            self.excluded_plan_sha256,
            self.excluded_run_journal_sha256,
        )
        if (
            _SAFE_ID.fullmatch(self.plan_id) is None
            or _GIT_COMMIT.fullmatch(self.source_commit) is None
            or any(_SHA256.fullmatch(value) is None for value in digests)
            or not isinstance(self.inventory, tuple)
            or not self.inventory
            or any(
                not isinstance(item, BattleScenarioMaterializationCandidateV2)
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
            or len({item.source.partition for item in self.inventory}) != 1
        ):
            raise BattleScenarioMaterializationPlanV2Error(
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
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization source provenance differs"
            )
        if self.assignments != _select_assignments(self.plan_id, self.inventory):
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization assignment is not canonical"
            )

    @property
    def selection_policy_sha256(self) -> str:
        return canonical_sha256(_selection_policy(self.partition))

    @property
    def partition(self) -> ScenarioPartition:
        """Return the immutable catalog partition shared by the complete inventory."""

        partitions = {item.source.partition for item in self.inventory}
        if len(partitions) != 1:  # pragma: no cover - __post_init__ closes this
            raise BattleScenarioMaterializationPlanV2Error(
                "battle materialization plan partition differs"
            )
        return next(iter(partitions))

    @property
    def required_capture_count(self) -> int:
        return _required_capture_count(self.partition)

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def private_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "capture_directory_sha256": self.capture_directory_sha256,
            "effects": _zero_effects(),
            "excluded_plan_sha256": self.excluded_plan_sha256,
            "excluded_run_journal_sha256": self.excluded_run_journal_sha256,
            "inventory": [item.private_dict() for item in self.inventory],
            "plan_id": self.plan_id,
            "retry_after_controller_input": False,
            "rom_sha256": self.rom_sha256,
            "schema": BATTLE_SCENARIO_MATERIALIZATION_PLAN_V2_SCHEMA,
            "selection_policy_sha256": self.selection_policy_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "status": "prospective_unexecuted",
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.private_dict())


def build_battle_scenario_materialization_plan_v2(
    *,
    plan_id: str,
    source_commit: str,
    source_bundle_sha256: str,
    rom_sha256: str,
    capture_directory_sha256: str,
    excluded_plan_sha256: str,
    excluded_run_journal_sha256: str,
    candidates: Sequence[BattleScenarioMaterializationCandidateV2],
) -> BattleScenarioMaterializationPlanV2:
    """Freeze the complete eligible multi-venue inventory canonically."""

    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise TypeError("battle materialization candidates must be a sequence")
    inventory = tuple(
        sorted(candidates, key=lambda item: item.candidate_identity_sha256)
    )
    if (
        any(
            not isinstance(item, BattleScenarioMaterializationCandidateV2)
            for item in inventory
        )
        or len({item.candidate_identity_sha256 for item in inventory})
        != len(inventory)
        or len({item.source.source_state_sha256 for item in inventory})
        != len(inventory)
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan inventory differs"
        )
    return BattleScenarioMaterializationPlanV2(
        plan_id=plan_id,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        rom_sha256=rom_sha256,
        capture_directory_sha256=capture_directory_sha256,
        excluded_plan_sha256=excluded_plan_sha256,
        excluded_run_journal_sha256=excluded_run_journal_sha256,
        inventory=inventory,
        assignments=_select_assignments(plan_id, inventory),
    )


def build_battle_scenario_materialization_completion_plan(
    *,
    plan_id: str,
    source_commit: str,
    source_bundle_sha256: str,
    rom_sha256: str,
    capture_directory_sha256: str,
    earliest_excluded_plan_sha256: str,
    earliest_excluded_run_journal_sha256: str,
    predecessor_plan_sha256: str,
    predecessor_run_journal_sha256: str,
    predecessor_capture_directory_sha256: str,
    predecessor_failure_count: int,
    retained_successes: Sequence[RetainedBattleScenarioMaterializationCapture],
    candidates: Sequence[BattleScenarioMaterializationCandidateV2],
    supplemental_exclusions: Sequence[
        BattleScenarioMaterializationSupplementalExclusion
    ] = (),
) -> BattleScenarioMaterializationCompletionPlan:
    """Freeze one additive gap without reopening the predecessor denominator."""

    if (
        not isinstance(retained_successes, Sequence)
        or isinstance(retained_successes, (str, bytes))
        or not isinstance(candidates, Sequence)
        or isinstance(candidates, (str, bytes))
        or not isinstance(supplemental_exclusions, Sequence)
        or isinstance(supplemental_exclusions, (str, bytes))
    ):
        raise TypeError("battle materialization completion inputs must be sequences")
    retained = tuple(sorted(retained_successes, key=lambda item: item.ordinal))
    inventory = tuple(
        sorted(candidates, key=lambda item: item.candidate_identity_sha256)
    )
    exclusions = tuple(
        sorted(
            supplemental_exclusions,
            key=lambda item: (item.plan_sha256, item.run_journal_sha256),
        )
    )
    return BattleScenarioMaterializationCompletionPlan(
        plan_id=plan_id,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        rom_sha256=rom_sha256,
        capture_directory_sha256=capture_directory_sha256,
        earliest_excluded_plan_sha256=earliest_excluded_plan_sha256,
        earliest_excluded_run_journal_sha256=(
            earliest_excluded_run_journal_sha256
        ),
        predecessor_plan_sha256=predecessor_plan_sha256,
        predecessor_run_journal_sha256=predecessor_run_journal_sha256,
        predecessor_capture_directory_sha256=predecessor_capture_directory_sha256,
        predecessor_failure_count=predecessor_failure_count,
        retained_successes=retained,
        inventory=inventory,
        assignments=_select_completion_assignments(plan_id, inventory, retained),
        supplemental_exclusions=exclusions,
    )


def parse_battle_scenario_materialization_plan_v2(
    payload: bytes,
) -> BattleScenarioMaterializationPlanV2:
    """Strictly reopen one canonical private V2 plan."""

    if not isinstance(payload, bytes):
        raise TypeError("battle materialization plan must be bytes")
    if not payload or len(payload) > _MAXIMUM_PLAN_BYTES:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan size differs"
        )
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan is not canonical JSON"
        ) from None
    plan = _parse_plan(value)
    if plan.canonical_bytes() != payload:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan is not canonical JSON"
        )
    return plan


def parse_battle_scenario_materialization_completion_plan(
    payload: bytes,
) -> BattleScenarioMaterializationCompletionPlan:
    """Strictly reopen one canonical private additive completion plan."""

    if not isinstance(payload, bytes):
        raise TypeError("battle materialization completion plan must be bytes")
    if not payload or len(payload) > _MAXIMUM_PLAN_BYTES:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion plan size differs"
        )
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion plan is not canonical JSON"
        ) from None
    plan = _parse_completion_plan(value)
    if plan.canonical_bytes() != payload:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion plan is not canonical JSON"
        )
    return plan


def _select_assignments(
    plan_id: str,
    inventory: tuple[BattleScenarioMaterializationCandidateV2, ...],
) -> tuple[BattleScenarioMaterializationAssignmentV2, ...]:
    if _SAFE_ID.fullmatch(plan_id) is None:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan identity differs"
        )
    partitions = {item.source.partition for item in inventory}
    if len(partitions) != 1:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan partition differs"
        )
    required_capture_count = _required_capture_count(next(iter(partitions)))
    by_identity = {item.candidate_identity_sha256: item for item in inventory}
    allocation = allocate_reachable_venue_roots(
        tuple(
            ReachableVenueRoot(
                item.candidate_identity_sha256,
                tuple(venue.venue_id for venue in item.reachable_venues),
            )
            for item in inventory
        ),
        required_roots=required_capture_count,
        minimum_distinct_venues=MINIMUM_DISTINCT_VENUES,
        maximum_roots_per_venue=MAXIMUM_CAPTURES_PER_VENUE,
    )
    if not allocation.capacity_met:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization inventory lacks reachable venue capacity"
        )

    species_counts: Counter[int] = Counter()
    party_slot_counts: Counter[int] = Counter()
    status_counts: Counter[int] = Counter()
    level_counts: Counter[int] = Counter()
    selections = []
    for edge in allocation.assignments:
        candidate = by_identity[edge.root_id]
        venue = candidate.venue(edge.venue_id)
        slot = min(
            venue.party_slots,
            key=lambda item: (
                species_counts[item.species_id],
                party_slot_counts[item.party_slot],
                status_counts[item.status_id],
                level_counts[item.level],
                -item.usable_move_count,
                -Fraction(item.current_hp, item.maximum_hp),
                item.party_slot,
            ),
        )
        species_counts[slot.species_id] += 1
        party_slot_counts[slot.party_slot] += 1
        status_counts[slot.status_id] += 1
        level_counts[slot.level] += 1
        selections.append((candidate, venue, slot))

    assignments = tuple(
        BattleScenarioMaterializationAssignmentV2(
            ordinal=ordinal,
            capture_id=f"{plan_id}-{ordinal + 1:02d}",
            candidate=candidate,
            selected_venue=venue,
            party_slot=slot,
            state_filename=f"{plan_id}-{ordinal + 1:02d}.state",
            manifest_filename=f"{plan_id}-{ordinal + 1:02d}.state.json",
        )
        for ordinal, (candidate, venue, slot) in enumerate(selections)
    )
    counts = Counter(item.selected_venue.venue_id for item in assignments)
    if (
        len(assignments) != required_capture_count
        or len({item.candidate.source.source_state_sha256 for item in assignments})
        != required_capture_count
        or len(counts) < MINIMUM_DISTINCT_VENUES
        or max(counts.values(), default=0) > MAXIMUM_CAPTURES_PER_VENUE
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization assignment denominator differs"
        )
    return assignments


def _required_capture_count(partition: ScenarioPartition) -> int:
    if partition is ScenarioPartition.TRAIN:
        return FRESH_TRAIN_CONTEXTS
    if partition is ScenarioPartition.DEVELOPMENT:
        return DEVELOPMENT_CONTEXTS
    raise BattleScenarioMaterializationPlanV2Error(
        "battle materialization plan partition differs"
    )


def _selection_policy(partition: ScenarioPartition) -> Mapping[str, object]:
    if partition is ScenarioPartition.TRAIN:
        return _SELECTION_POLICY
    if partition is ScenarioPartition.DEVELOPMENT:
        return {
            **_SELECTION_POLICY,
            "capture_count": DEVELOPMENT_CONTEXTS,
            "partition": ScenarioPartition.DEVELOPMENT.value,
        }
    raise BattleScenarioMaterializationPlanV2Error(
        "battle materialization plan partition differs"
    )


def _select_completion_assignments(
    plan_id: str,
    inventory: tuple[BattleScenarioMaterializationCandidateV2, ...],
    retained_successes: tuple[RetainedBattleScenarioMaterializationCapture, ...],
) -> tuple[BattleScenarioMaterializationAssignmentV2, ...]:
    if _SAFE_ID.fullmatch(plan_id) is None:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion plan identity differs"
        )
    partitions = {item.source.partition for item in inventory}
    if len(partitions) != 1:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion plan partition differs"
        )
    required_capture_count = _required_capture_count(next(iter(partitions)))
    required_additional = required_capture_count - len(retained_successes)
    if required_additional < 1:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion gap differs"
        )
    retained_venue_counts = tuple(
        sorted(Counter(item.venue_id for item in retained_successes).items())
    )
    by_identity = {item.candidate_identity_sha256: item for item in inventory}
    allocation = allocate_additive_reachable_venue_roots(
        tuple(
            ReachableVenueRoot(
                item.candidate_identity_sha256,
                tuple(venue.venue_id for venue in item.reachable_venues),
            )
            for item in inventory
        ),
        retained_venue_counts=retained_venue_counts,
        required_additional_roots=required_additional,
        minimum_total_distinct_venues=MINIMUM_DISTINCT_VENUES,
        maximum_total_roots_per_venue=MAXIMUM_CAPTURES_PER_VENUE,
    )
    if not allocation.capacity_met:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion inventory lacks additive venue capacity"
        )

    species_counts = Counter(item.party_slot.species_id for item in retained_successes)
    party_slot_counts = Counter(item.party_slot.party_slot for item in retained_successes)
    status_counts = Counter(item.party_slot.status_id for item in retained_successes)
    level_counts = Counter(item.party_slot.level for item in retained_successes)
    selections = []
    for edge in allocation.assignments:
        candidate = by_identity[edge.root_id]
        venue = candidate.venue(edge.venue_id)
        slot = min(
            venue.party_slots,
            key=lambda item: (
                species_counts[item.species_id],
                party_slot_counts[item.party_slot],
                status_counts[item.status_id],
                level_counts[item.level],
                -item.usable_move_count,
                -Fraction(item.current_hp, item.maximum_hp),
                item.party_slot,
            ),
        )
        species_counts[slot.species_id] += 1
        party_slot_counts[slot.party_slot] += 1
        status_counts[slot.status_id] += 1
        level_counts[slot.level] += 1
        selections.append((candidate, venue, slot))

    assignments = tuple(
        BattleScenarioMaterializationAssignmentV2(
            ordinal=ordinal,
            capture_id=f"{plan_id}-{ordinal + 1:02d}",
            candidate=candidate,
            selected_venue=venue,
            party_slot=slot,
            state_filename=f"{plan_id}-{ordinal + 1:02d}.state",
            manifest_filename=f"{plan_id}-{ordinal + 1:02d}.state.json",
        )
        for ordinal, (candidate, venue, slot) in enumerate(selections)
    )
    total_counts = Counter(item.venue_id for item in retained_successes)
    total_counts.update(item.selected_venue.venue_id for item in assignments)
    if (
        len(assignments) != required_additional
        or len({item.candidate.source.source_state_sha256 for item in assignments})
        != required_additional
        or len(total_counts) < MINIMUM_DISTINCT_VENUES
        or max(total_counts.values(), default=0) > MAXIMUM_CAPTURES_PER_VENUE
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion denominator differs"
        )
    return assignments


def _completion_selection_policy(
    partition: ScenarioPartition,
) -> Mapping[str, object]:
    if partition is ScenarioPartition.TRAIN:
        return _COMPLETION_SELECTION_POLICY
    if partition is ScenarioPartition.DEVELOPMENT:
        return {
            **_COMPLETION_SELECTION_POLICY,
            "required_total_capture_count": DEVELOPMENT_CONTEXTS,
            "partition": ScenarioPartition.DEVELOPMENT.value,
        }
    raise BattleScenarioMaterializationPlanV2Error(
        "battle materialization completion plan partition differs"
    )


def _parse_completion_plan(
    value: object,
) -> BattleScenarioMaterializationCompletionPlan:
    base_fields = {
        "assignments",
        "capture_directory_sha256",
        "earliest_excluded_plan_sha256",
        "earliest_excluded_run_journal_sha256",
        "effects",
        "inventory",
        "plan_id",
        "predecessor_capture_directory_sha256",
        "predecessor_failure_count",
        "predecessor_plan_sha256",
        "predecessor_run_journal_sha256",
        "retained_successes",
        "retry_after_controller_input",
        "rom_sha256",
        "schema",
        "selection_policy_sha256",
        "source_bundle_sha256",
        "source_commit",
        "status",
    }
    schema = value.get("schema") if isinstance(value, Mapping) else None
    fields = (
        base_fields | {"supplemental_exclusions"}
        if schema == BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SUCCESSOR_PLAN_SCHEMA
        else base_fields
    )
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or schema
        not in {
            BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_PLAN_SCHEMA,
            BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SUCCESSOR_PLAN_SCHEMA,
        }
        or value.get("status") != "prospective_unexecuted_additive_completion"
        or value.get("retry_after_controller_input") is not False
        or value.get("effects") != _zero_effects()
        or not isinstance(value.get("inventory"), list)
        or not isinstance(value.get("retained_successes"), list)
        or not isinstance(value.get("assignments"), list)
        or (
            schema
            == BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SUCCESSOR_PLAN_SCHEMA
            and not isinstance(value.get("supplemental_exclusions"), list)
        )
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion plan fields differ"
        )
    inventory = tuple(_parse_candidate(item) for item in value["inventory"])
    partitions = {item.source.partition for item in inventory}
    if (
        len(partitions) != 1
        or value.get("selection_policy_sha256")
        != canonical_sha256(_completion_selection_policy(next(iter(partitions))))
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization completion plan fields differ"
        )
    retained = tuple(
        _parse_retained_capture(item) for item in value["retained_successes"]
    )
    by_identity = {item.candidate_identity_sha256: item for item in inventory}
    assignments = tuple(
        _parse_assignment(item, by_identity=by_identity)
        for item in value["assignments"]
    )
    supplemental_exclusions = tuple(
        _parse_supplemental_exclusion(item)
        for item in value.get("supplemental_exclusions", [])
    )
    return BattleScenarioMaterializationCompletionPlan(
        plan_id=_text(value.get("plan_id"), "plan id"),
        source_commit=_text(value.get("source_commit"), "source commit"),
        source_bundle_sha256=_text(value.get("source_bundle_sha256"), "source bundle"),
        rom_sha256=_text(value.get("rom_sha256"), "ROM"),
        capture_directory_sha256=_text(
            value.get("capture_directory_sha256"), "capture directory"
        ),
        earliest_excluded_plan_sha256=_text(
            value.get("earliest_excluded_plan_sha256"), "earliest excluded plan"
        ),
        earliest_excluded_run_journal_sha256=_text(
            value.get("earliest_excluded_run_journal_sha256"),
            "earliest excluded run journal",
        ),
        predecessor_plan_sha256=_text(
            value.get("predecessor_plan_sha256"), "predecessor plan"
        ),
        predecessor_run_journal_sha256=_text(
            value.get("predecessor_run_journal_sha256"),
            "predecessor run journal",
        ),
        predecessor_capture_directory_sha256=_text(
            value.get("predecessor_capture_directory_sha256"),
            "predecessor capture directory",
        ),
        predecessor_failure_count=_integer(
            value.get("predecessor_failure_count"), "predecessor failure count"
        ),
        retained_successes=retained,
        inventory=inventory,
        assignments=assignments,
        supplemental_exclusions=supplemental_exclusions,
    )


def _parse_supplemental_exclusion(
    value: object,
) -> BattleScenarioMaterializationSupplementalExclusion:
    if not isinstance(value, Mapping) or set(value) != {
        "plan_sha256",
        "run_journal_sha256",
    }:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization supplemental exclusion differs"
        )
    return BattleScenarioMaterializationSupplementalExclusion(
        plan_sha256=_text(value.get("plan_sha256"), "supplemental plan"),
        run_journal_sha256=_text(
            value.get("run_journal_sha256"),
            "supplemental run journal",
        ),
    )


def _parse_retained_capture(
    value: object,
) -> RetainedBattleScenarioMaterializationCapture:
    fields = {
        "assignment_sha256",
        "capture_id",
        "manifest_filename",
        "manifest_sha256",
        "ordinal",
        "party_slot",
        "root_lineage_id",
        "source_commit",
        "source_state_sha256",
        "state_filename",
        "state_sha256",
        "venue_id",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioMaterializationPlanV2Error(
            "retained battle materialization capture fields differ"
        )
    return RetainedBattleScenarioMaterializationCapture(
        ordinal=_integer(value.get("ordinal"), "retained ordinal"),
        capture_id=_text(value.get("capture_id"), "retained capture id"),
        assignment_sha256=_text(
            value.get("assignment_sha256"), "retained assignment"
        ),
        source_commit=_text(value.get("source_commit"), "retained source commit"),
        source_state_sha256=_text(
            value.get("source_state_sha256"), "retained source state"
        ),
        root_lineage_id=_text(
            value.get("root_lineage_id"), "retained root lineage"
        ),
        venue_id=_text(value.get("venue_id"), "retained venue"),
        party_slot=_parse_party_slot(value.get("party_slot")),
        state_filename=_text(value.get("state_filename"), "retained state filename"),
        manifest_filename=_text(
            value.get("manifest_filename"), "retained manifest filename"
        ),
        state_sha256=_text(value.get("state_sha256"), "retained state"),
        manifest_sha256=_text(value.get("manifest_sha256"), "retained manifest"),
    )


def _parse_plan(value: object) -> BattleScenarioMaterializationPlanV2:
    fields = {
        "assignments",
        "capture_directory_sha256",
        "effects",
        "excluded_plan_sha256",
        "excluded_run_journal_sha256",
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
        or set(value) != fields
        or value.get("schema") != BATTLE_SCENARIO_MATERIALIZATION_PLAN_V2_SCHEMA
        or value.get("status") != "prospective_unexecuted"
        or value.get("retry_after_controller_input") is not False
        or value.get("effects") != _zero_effects()
        or not isinstance(value.get("inventory"), list)
        or not isinstance(value.get("assignments"), list)
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan fields differ"
        )
    inventory = tuple(_parse_candidate(item) for item in value["inventory"])
    partitions = {item.source.partition for item in inventory}
    if (
        len(partitions) != 1
        or value.get("selection_policy_sha256")
        != canonical_sha256(_selection_policy(next(iter(partitions))))
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization plan fields differ"
        )
    by_identity = {item.candidate_identity_sha256: item for item in inventory}
    assignments = tuple(
        _parse_assignment(item, by_identity=by_identity)
        for item in value["assignments"]
    )
    return BattleScenarioMaterializationPlanV2(
        plan_id=_text(value.get("plan_id"), "plan id"),
        source_commit=_text(value.get("source_commit"), "source commit"),
        source_bundle_sha256=_text(value.get("source_bundle_sha256"), "source bundle"),
        rom_sha256=_text(value.get("rom_sha256"), "ROM"),
        capture_directory_sha256=_text(
            value.get("capture_directory_sha256"), "capture directory"
        ),
        excluded_plan_sha256=_text(value.get("excluded_plan_sha256"), "excluded plan"),
        excluded_run_journal_sha256=_text(
            value.get("excluded_run_journal_sha256"), "excluded run journal"
        ),
        inventory=inventory,
        assignments=assignments,
    )


def _parse_candidate(value: object) -> BattleScenarioMaterializationCandidateV2:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"reachable_venues", "source"}
        or not isinstance(value.get("reachable_venues"), list)
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization candidate fields differ"
        )
    return BattleScenarioMaterializationCandidateV2(
        source=_parse_source_binding(value.get("source")),
        reachable_venues=tuple(
            _parse_reachable_venue(item) for item in value["reachable_venues"]
        ),
    )


def _parse_reachable_venue(value: object) -> BattleScenarioReachableVenue:
    fields = {
        "maximum_encounter_level",
        "minimum_encounter_level",
        "party_slots",
        "rare_maximum_encounter_level",
        "source_location",
        "venue_id",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or not isinstance(value.get("party_slots"), list)
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization reachable venue fields differ"
        )
    return BattleScenarioReachableVenue(
        venue_id=_text(value.get("venue_id"), "venue"),
        source_location=_text(value.get("source_location"), "source location"),
        minimum_encounter_level=_integer(value.get("minimum_encounter_level"), "minimum"),
        maximum_encounter_level=_integer(value.get("maximum_encounter_level"), "maximum"),
        rare_maximum_encounter_level=_integer(
            value.get("rare_maximum_encounter_level"), "rare maximum"
        ),
        party_slots=tuple(_parse_party_slot(item) for item in value["party_slots"]),
    )


def _parse_party_slot(value: object) -> BattleScenarioPartySlot:
    fields = {
        "current_hp",
        "level",
        "maximum_hp",
        "party_slot",
        "species_id",
        "status_id",
        "usable_move_count",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioMaterializationPlanV2Error(
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
    by_identity: Mapping[str, BattleScenarioMaterializationCandidateV2],
) -> BattleScenarioMaterializationAssignmentV2:
    fields = {
        "candidate_identity_sha256",
        "capture_id",
        "manifest_filename",
        "ordinal",
        "party_slot",
        "selected_venue_id",
        "state_filename",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization assignment fields differ"
        )
    identity = _text(value.get("candidate_identity_sha256"), "candidate identity")
    try:
        candidate = by_identity[identity]
    except KeyError:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization assignment candidate differs"
        ) from None
    venue = candidate.venue(_text(value.get("selected_venue_id"), "selected venue"))
    party_slot = _integer(value.get("party_slot"), "party slot")
    matching = tuple(item for item in venue.party_slots if item.party_slot == party_slot)
    if len(matching) != 1:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization assignment party slot differs"
        )
    return BattleScenarioMaterializationAssignmentV2(
        ordinal=_integer(value.get("ordinal"), "ordinal"),
        capture_id=_text(value.get("capture_id"), "capture id"),
        candidate=candidate,
        selected_venue=venue,
        party_slot=matching[0],
        state_filename=_text(value.get("state_filename"), "state filename"),
        manifest_filename=_text(value.get("manifest_filename"), "manifest filename"),
    )


def _parse_source_binding(value: object) -> BattleScenarioSourceBinding:
    fields = {
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
        or set(value) != fields
        or value.get("schema") != "pokemon.red.battle-scenario-source-binding.v1"
        or value.get("caller_supplied_lineage") is not False
        or value.get("caller_supplied_partition") is not False
        or value.get("private_path_fields") != 0
    ):
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization source binding fields differ"
        )
    try:
        partition = ScenarioPartition(_text(value.get("partition"), "partition"))
    except ValueError:
        raise BattleScenarioMaterializationPlanV2Error(
            "battle materialization source partition differs"
        ) from None
    return BattleScenarioSourceBinding(
        partition=partition,
        source_state_sha256=_text(value.get("source_state_sha256"), "source state"),
        source_slot_id=_text(value.get("source_slot_id"), "source slot"),
        source_assignment_id=_text(value.get("source_assignment_id"), "source assignment"),
        source_context_id=_text(value.get("source_context_id"), "source context"),
        source_envelope_sha256=_text(value.get("source_envelope_sha256"), "source envelope"),
        root_lineage_id=_text(value.get("root_lineage_id"), "root lineage"),
        root_consumption_sha256=_text(value.get("root_consumption_sha256"), "root consumption"),
        catalog_sha256=_text(value.get("catalog_sha256"), "catalog"),
        registry_sha256=_text(value.get("registry_sha256"), "registry"),
        registry_source_commit=_text(value.get("registry_source_commit"), "registry source"),
    )


def _zero_effects() -> dict[str, object]:
    return {
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


def _canonical_payload(value: Mapping[str, object]) -> bytes:
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


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise BattleScenarioMaterializationPlanV2Error(
            f"battle materialization {subject} differs"
        )
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int:  # noqa: E721
        raise BattleScenarioMaterializationPlanV2Error(
            f"battle materialization {subject} differs"
        )
    return value


__all__ = [
    "BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_PLAN_SCHEMA",
    "BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_SUCCESSOR_PLAN_SCHEMA",
    "BATTLE_SCENARIO_MATERIALIZATION_PLAN_V2_SCHEMA",
    "MAXIMUM_CAPTURES_PER_VENUE",
    "MINIMUM_DISTINCT_VENUES",
    "REQUIRED_CAPTURE_COUNT",
    "BattleScenarioMaterializationAssignmentV2",
    "BattleScenarioMaterializationCandidateV2",
    "BattleScenarioMaterializationCompletionPlan",
    "BattleScenarioMaterializationSupplementalExclusion",
    "BattleScenarioMaterializationPlanV2",
    "BattleScenarioMaterializationPlanV2Error",
    "BattleScenarioReachableVenue",
    "RetainedBattleScenarioMaterializationCapture",
    "build_battle_scenario_materialization_completion_plan",
    "build_battle_scenario_materialization_plan_v2",
    "parse_battle_scenario_materialization_plan_v2",
    "parse_battle_scenario_materialization_completion_plan",
]
