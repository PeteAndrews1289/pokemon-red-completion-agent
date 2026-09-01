from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (
    BATTLE_SCENARIO_MATERIALIZATION_PLAN_SCHEMA,
    MANSION_VENUE_ID,
    REQUIRED_CAPTURE_COUNT,
    ROUTE_11_VENUE_ID,
    BattleScenarioMaterializationCandidate,
    BattleScenarioMaterializationPlan,
    BattleScenarioMaterializationPlanError,
    BattleScenarioPartySlot,
    battle_scenario_materialization_selection_policy_sha256,
    build_battle_scenario_materialization_plan,
    parse_battle_scenario_materialization_plan,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _source(index: int) -> BattleScenarioSourceBinding:
    state = _sha(f"state-{index}")
    envelope = _sha(f"envelope-{index}")
    assignment = _sha(f"assignment-{index}")
    return BattleScenarioSourceBinding(
        partition=ScenarioPartition.TRAIN,
        source_state_sha256=state,
        source_slot_id=f"slot-{index}",
        source_assignment_id=assignment,
        source_context_id=_sha(f"context-{index}"),
        source_envelope_sha256=envelope,
        root_lineage_id=f"red-goal-root-{assignment}",
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=state,
            envelope_sha256=envelope,
        ),
        catalog_sha256=_sha("catalog"),
        registry_sha256=_sha("registry"),
        registry_source_commit="a" * 40,
    )


def _slot(
    party_slot: int,
    *,
    species_id: int,
    level: int,
    status_id: int = 0,
    usable_move_count: int = 3,
) -> BattleScenarioPartySlot:
    return BattleScenarioPartySlot(
        party_slot=party_slot,
        species_id=species_id,
        level=level,
        current_hp=40,
        maximum_hp=50,
        status_id=status_id,
        usable_move_count=usable_move_count,
    )


def _candidate(
    index: int,
    venue_id: str,
    *,
    species_id: int | None = None,
) -> BattleScenarioMaterializationCandidate:
    if venue_id == ROUTE_11_VENUE_ID:
        minimum, maximum, rare, level = 9, 15, 17, 20
        source_location = "lavender_center_route_11"
    else:
        minimum, maximum, rare, level = 28, 34, 39, 30
        source_location = "cinnabar_center"
    species = species_id if species_id is not None else 10 + index
    return BattleScenarioMaterializationCandidate(
        source=_source(index),
        venue_id=venue_id,
        source_location=source_location,
        minimum_encounter_level=minimum,
        maximum_encounter_level=maximum,
        rare_maximum_encounter_level=rare,
        party_slots=(
            _slot(1, species_id=species, level=level),
            _slot(2, species_id=100 + index, level=level),
        ),
    )


def _inventory() -> tuple[BattleScenarioMaterializationCandidate, ...]:
    return (
        *(_candidate(index, MANSION_VENUE_ID) for index in range(8)),
        _candidate(20, ROUTE_11_VENUE_ID),
        _candidate(21, ROUTE_11_VENUE_ID),
    )


def _plan() -> BattleScenarioMaterializationPlan:
    return build_battle_scenario_materialization_plan(
        plan_id="red-battle-v2-materialization",
        source_commit="b" * 40,
        source_bundle_sha256=_sha("bundle"),
        rom_sha256=_sha("rom"),
        capture_directory_sha256=_sha("capture-directory"),
        candidates=_inventory(),
    )


def test_plan_freezes_exact_two_venue_denominator_and_round_trips() -> None:
    plan = _plan()

    assert len(plan.assignments) == REQUIRED_CAPTURE_COUNT
    assert [item.candidate.venue_id for item in plan.assignments].count(
        ROUTE_11_VENUE_ID
    ) == 2
    assert [item.candidate.venue_id for item in plan.assignments].count(
        MANSION_VENUE_ID
    ) == 5
    assert len({item.candidate.source.source_state_sha256 for item in plan.assignments}) == 7
    assert parse_battle_scenario_materialization_plan(plan.canonical_bytes()) == plan
    assert plan.private_dict()["schema"] == BATTLE_SCENARIO_MATERIALIZATION_PLAN_SCHEMA


def test_plan_selection_is_canonical_independent_of_caller_order() -> None:
    forward = _plan()
    reverse = build_battle_scenario_materialization_plan(
        plan_id=forward.plan_id,
        source_commit=forward.source_commit,
        source_bundle_sha256=forward.source_bundle_sha256,
        rom_sha256=forward.rom_sha256,
        capture_directory_sha256=forward.capture_directory_sha256,
        candidates=tuple(reversed(_inventory())),
    )

    assert reverse == forward
    assert reverse.plan_sha256 == forward.plan_sha256


def test_plan_rejects_missing_second_venue_without_shrinking() -> None:
    with pytest.raises(
        BattleScenarioMaterializationPlanError,
        match="venue capacity",
    ):
        build_battle_scenario_materialization_plan(
            plan_id="red-battle-v2-materialization",
            source_commit="b" * 40,
            source_bundle_sha256=_sha("bundle"),
            rom_sha256=_sha("rom"),
            capture_directory_sha256=_sha("capture-directory"),
            candidates=tuple(_candidate(index, MANSION_VENUE_ID) for index in range(9)),
        )


def test_candidate_rejects_a_slot_that_can_break_the_level_gap() -> None:
    with pytest.raises(
        BattleScenarioMaterializationPlanError,
        match="level gap",
    ):
        replace(
            _candidate(20, ROUTE_11_VENUE_ID),
            party_slots=(_slot(1, species_id=25, level=22),),
        )


def test_plan_rejects_duplicate_source_roots() -> None:
    inventory = list(_inventory())
    inventory[1] = replace(inventory[1], source=inventory[0].source)

    with pytest.raises(
        BattleScenarioMaterializationPlanError,
        match="inventory differs",
    ):
        build_battle_scenario_materialization_plan(
            plan_id="red-battle-v2-materialization",
            source_commit="b" * 40,
            source_bundle_sha256=_sha("bundle"),
            rom_sha256=_sha("rom"),
            capture_directory_sha256=_sha("capture-directory"),
            candidates=inventory,
        )


def test_plan_rederives_assignments_instead_of_trusting_serialized_selection() -> None:
    plan = _plan()
    assignments = list(plan.assignments)
    assignments[0] = replace(assignments[0], party_slot=assignments[0].candidate.party_slots[1])

    with pytest.raises(
        BattleScenarioMaterializationPlanError,
        match="not canonical",
    ):
        replace(plan, assignments=tuple(assignments))


def test_selection_prefers_new_species_before_repeating_one() -> None:
    inventory = list(_inventory())
    inventory[0] = replace(
        inventory[0],
        party_slots=(
            _slot(1, species_id=30, level=30),
            _slot(2, species_id=200, level=30),
        ),
    )
    inventory[1] = replace(
        inventory[1],
        party_slots=(
            _slot(1, species_id=30, level=30),
            _slot(2, species_id=201, level=30),
        ),
    )
    plan = build_battle_scenario_materialization_plan(
        plan_id="red-battle-v2-materialization",
        source_commit="b" * 40,
        source_bundle_sha256=_sha("bundle"),
        rom_sha256=_sha("rom"),
        capture_directory_sha256=_sha("capture-directory"),
        candidates=inventory,
    )

    selected_species = [item.party_slot.species_id for item in plan.assignments]
    assert len(set(selected_species)) == len(selected_species)


def test_policy_and_private_plan_declare_zero_learning_effects() -> None:
    plan = _plan()
    encoded = plan.canonical_bytes().decode("ascii")
    policy = battle_scenario_materialization_selection_policy_sha256()

    assert plan.selection_policy_sha256 == policy
    assert plan.private_dict()["effects"] == {
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
    assert '"retry_after_controller_input":false' in encoded


def test_parser_rejects_noncanonical_and_duplicate_json() -> None:
    plan = _plan()
    value = json.loads(plan.canonical_bytes())
    noncanonical = json.dumps(value, indent=2).encode("ascii")

    with pytest.raises(
        BattleScenarioMaterializationPlanError,
        match="not canonical",
    ):
        parse_battle_scenario_materialization_plan(noncanonical)
    with pytest.raises(
        BattleScenarioMaterializationPlanError,
        match="not canonical",
    ):
        parse_battle_scenario_materialization_plan(
            b'{"schema":"x","schema":"y"}\n'
        )
