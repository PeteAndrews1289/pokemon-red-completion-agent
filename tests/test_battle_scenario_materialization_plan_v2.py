from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (
    BattleScenarioPartySlot,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (
    BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_PLAN_SCHEMA,
    BATTLE_SCENARIO_MATERIALIZATION_PLAN_V2_SCHEMA,
    BattleScenarioMaterializationCandidateV2,
    BattleScenarioMaterializationPlanV2Error,
    BattleScenarioReachableVenue,
    RetainedBattleScenarioMaterializationCapture,
    build_battle_scenario_materialization_completion_plan,
    build_battle_scenario_materialization_plan_v2,
    parse_battle_scenario_materialization_completion_plan,
    parse_battle_scenario_materialization_plan_v2,
)
from pokemon_red_completion.battle_scenario_materialization_run import (
    BattleScenarioMaterializationRunIdentity,
    initialize_battle_scenario_materialization_run,
    require_battle_scenario_materialization_run_matches_plan,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256
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


def _slot(index: int, *, level: int, species: int | None = None) -> BattleScenarioPartySlot:
    return BattleScenarioPartySlot(
        party_slot=index,
        species_id=species if species is not None else index,
        level=level,
        current_hp=40,
        maximum_hp=50,
        status_id=0,
        usable_move_count=3,
    )


def _venue(venue_id: str, *, index: int) -> BattleScenarioReachableVenue:
    if venue_id == "route_11":
        minimum, maximum, rare, level = 9, 15, 17, 20
        source_location = "vermilion_transition_route_11"
    else:
        minimum, maximum, rare, level = 18, 22, 31, 25
        source_location = "vermilion_transition_digletts_cave"
    return BattleScenarioReachableVenue(
        venue_id=venue_id,
        source_location=source_location,
        minimum_encounter_level=minimum,
        maximum_encounter_level=maximum,
        rare_maximum_encounter_level=rare,
        party_slots=(
            _slot(1, level=level, species=10 + index),
            _slot(2, level=level, species=100 + index),
        ),
    )


def _candidate(index: int, venues: tuple[str, ...] = ("digletts_cave", "route_11")):
    return BattleScenarioMaterializationCandidateV2(
        source=_source(index),
        reachable_venues=tuple(_venue(venue_id, index=index) for venue_id in venues),
    )


def _build(
    candidates: tuple[BattleScenarioMaterializationCandidateV2, ...] | None = None,
):
    if candidates is None:
        candidates = tuple(_candidate(index) for index in range(10))
    return build_battle_scenario_materialization_plan_v2(
        plan_id="red-battle-v2-multivenue",
        source_commit="b" * 40,
        source_bundle_sha256=_sha("bundle"),
        rom_sha256=_sha("rom"),
        capture_directory_sha256=_sha("captures"),
        excluded_plan_sha256=_sha("old-plan"),
        excluded_run_journal_sha256=_sha("old-journal"),
        candidates=candidates,
    )


def _retained_successes():
    predecessor = _build()
    retained = tuple(
        RetainedBattleScenarioMaterializationCapture(
            ordinal=assignment.ordinal,
            capture_id=assignment.capture_id,
            assignment_sha256=canonical_sha256(assignment.private_dict()),
            source_commit=predecessor.source_commit,
            source_state_sha256=assignment.candidate.source.source_state_sha256,
            root_lineage_id=assignment.candidate.source.root_lineage_id,
            venue_id=assignment.selected_venue.venue_id,
            party_slot=assignment.party_slot,
            state_filename=assignment.state_filename,
            manifest_filename=assignment.manifest_filename,
            state_sha256=_sha(f"retained-state-{assignment.ordinal}"),
            manifest_sha256=_sha(f"retained-manifest-{assignment.ordinal}"),
        )
        for assignment in (
            predecessor.assignments[0],
            predecessor.assignments[2],
            predecessor.assignments[4],
            predecessor.assignments[5],
            predecessor.assignments[6],
        )
    )
    return predecessor, retained


def _build_completion(
    candidates: tuple[BattleScenarioMaterializationCandidateV2, ...] | None = None,
):
    predecessor, retained = _retained_successes()
    if candidates is None:
        candidates = tuple(_candidate(index) for index in range(20, 23))
    return build_battle_scenario_materialization_completion_plan(
        plan_id="red-battle-v2-additive-completion",
        source_commit="c" * 40,
        source_bundle_sha256=_sha("completion-bundle"),
        rom_sha256=predecessor.rom_sha256,
        capture_directory_sha256=_sha("completion-captures"),
        earliest_excluded_plan_sha256=predecessor.excluded_plan_sha256,
        earliest_excluded_run_journal_sha256=(
            predecessor.excluded_run_journal_sha256
        ),
        predecessor_plan_sha256=predecessor.plan_sha256,
        predecessor_run_journal_sha256=_sha("predecessor-journal"),
        predecessor_capture_directory_sha256=(
            predecessor.capture_directory_sha256
        ),
        predecessor_failure_count=2,
        retained_successes=retained,
        candidates=candidates,
    )


def test_v2_plan_freezes_exact_capped_allocation_and_round_trips() -> None:
    plan = _build()
    counts: dict[str, int] = {}
    for assignment in plan.assignments:
        venue_id = assignment.selected_venue.venue_id
        counts[venue_id] = counts.get(venue_id, 0) + 1

    assert len(plan.inventory) == 10
    assert len(plan.assignments) == 7
    assert counts == {"digletts_cave": 4, "route_11": 3}
    assert len({item.candidate.source.source_state_sha256 for item in plan.assignments}) == 7
    assert parse_battle_scenario_materialization_plan_v2(plan.canonical_bytes()) == plan
    assert plan.private_dict()["schema"] == BATTLE_SCENARIO_MATERIALIZATION_PLAN_V2_SCHEMA


def test_v2_selection_is_independent_of_inventory_order() -> None:
    candidates = tuple(_candidate(index) for index in range(10))

    assert _build(candidates) == _build(tuple(reversed(candidates)))


def test_v2_exact_allocator_does_not_greedily_consume_scarce_venue_roots() -> None:
    candidates = (
        *(_candidate(index) for index in range(6)),
        _candidate(6, ("route_11",)),
    )
    plan = _build(candidates)

    assert {item.selected_venue.venue_id for item in plan.assignments} == {
        "digletts_cave",
        "route_11",
    }


def test_v2_rejects_single_venue_inventory_even_with_seven_roots() -> None:
    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="venue capacity"):
        _build(tuple(_candidate(index, ("route_11",)) for index in range(8)))


def test_v2_rederives_edge_and_party_slot_instead_of_trusting_json() -> None:
    plan = _build()
    value = json.loads(plan.canonical_bytes())
    value["assignments"][0]["party_slot"] = 2
    forged = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="not canonical"):
        parse_battle_scenario_materialization_plan_v2(forged)


def test_v2_candidate_rejects_duplicate_venue_and_duplicate_root() -> None:
    venue = _venue("route_11", index=1)
    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="candidate differs"):
        BattleScenarioMaterializationCandidateV2(
            source=_source(1),
            reachable_venues=(venue, venue),
        )

    candidates = list(_candidate(index) for index in range(10))
    candidates[1] = replace(candidates[1], source=candidates[0].source)
    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="inventory differs"):
        _build(tuple(candidates))


def test_v2_reachable_venue_rejects_party_slot_outside_full_measured_band() -> None:
    route = _venue("route_11", index=1)

    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="level gap"):
        replace(
            route,
            party_slots=(_slot(1, level=25),),
        )


def test_v2_plan_declares_zero_effects_and_no_retry() -> None:
    encoded = _build().canonical_bytes().decode("ascii")

    assert '"retry_after_controller_input":false' in encoded
    assert '"controller_actions":0' in encoded
    assert '"outcomes_opened":0' in encoded
    assert '"model_predictions":0' in encoded
    assert '"teacher_queries":0' in encoded


def test_v2_plan_uses_the_same_started_before_input_journal_contract() -> None:
    plan = _build()
    identity = BattleScenarioMaterializationRunIdentity(
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        source_commit="c" * 40,
        source_bundle_sha256=_sha("runner-bundle"),
        materializer_sha256=_sha("materializer"),
        runtime_identity_sha256=_sha("runtime"),
        rom_sha256=plan.rom_sha256,
        capture_directory_sha256=plan.capture_directory_sha256,
        context_catalog_sha256=_sha("catalog"),
        registry_sha256=_sha("registry"),
        registry_source_commit="a" * 40,
        exact_ci_run=123,
        exact_ci_attempt=1,
    )

    journal = initialize_battle_scenario_materialization_run(plan, identity)

    assert len(journal.entries) == 7
    require_battle_scenario_materialization_run_matches_plan(
        journal,
        plan,
        identity,
    )


def test_completion_plan_retains_five_and_selects_only_two_new_roots() -> None:
    plan = _build_completion()

    assert len(plan.retained_successes) == 5
    assert plan.predecessor_failure_count == 2
    assert len(plan.assignments) == 2
    assert len(
        {
            *(item.source_state_sha256 for item in plan.retained_successes),
            *(
                item.candidate.source.source_state_sha256
                for item in plan.assignments
            ),
        }
    ) == 7
    assert plan.private_dict()["schema"] == (
        BATTLE_SCENARIO_MATERIALIZATION_COMPLETION_PLAN_SCHEMA
    )
    assert (
        parse_battle_scenario_materialization_completion_plan(
            plan.canonical_bytes()
        )
        == plan
    )


def test_completion_plan_selection_is_independent_of_new_inventory_order() -> None:
    candidates = tuple(_candidate(index) for index in range(20, 23))

    assert _build_completion(candidates) == _build_completion(tuple(reversed(candidates)))


def test_completion_plan_rejects_a_retained_source_in_new_inventory() -> None:
    predecessor, _retained = _retained_successes()
    reused = predecessor.assignments[0].candidate

    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="plan differs"):
        _build_completion((reused, _candidate(20), _candidate(21)))


def test_completion_plan_rejects_duplicate_retained_ordinal() -> None:
    plan = _build_completion()
    duplicated = replace(
        plan.retained_successes[1],
        ordinal=plan.retained_successes[0].ordinal,
    )

    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="plan differs"):
        replace(
            plan,
            retained_successes=(
                plan.retained_successes[0],
                duplicated,
                *plan.retained_successes[2:],
            ),
        )


def test_completion_plan_rejects_capture_identity_reused_across_producers() -> None:
    plan = _build_completion()

    with pytest.raises(
        BattleScenarioMaterializationPlanV2Error,
        match="capture identity differs",
    ):
        replace(
            plan,
            retained_successes=(
                replace(
                    plan.retained_successes[0],
                    capture_id=plan.assignments[0].capture_id,
                ),
                *plan.retained_successes[1:],
            ),
        )


def test_completion_plan_rederives_new_assignments_after_reopen() -> None:
    plan = _build_completion()
    value = json.loads(plan.canonical_bytes())
    value["assignments"][0]["selected_venue_id"] = "route_11"
    forged = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

    with pytest.raises(BattleScenarioMaterializationPlanV2Error, match="not canonical"):
        parse_battle_scenario_materialization_completion_plan(forged)


def test_completion_plan_uses_a_two_item_started_before_input_journal() -> None:
    plan = _build_completion()
    identity = BattleScenarioMaterializationRunIdentity(
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        source_commit=plan.source_commit,
        source_bundle_sha256=plan.source_bundle_sha256,
        materializer_sha256=_sha("completion-materializer"),
        runtime_identity_sha256=_sha("completion-runtime"),
        rom_sha256=plan.rom_sha256,
        capture_directory_sha256=plan.capture_directory_sha256,
        context_catalog_sha256=_sha("catalog"),
        registry_sha256=_sha("registry"),
        registry_source_commit="a" * 40,
        exact_ci_run=124,
        exact_ci_attempt=1,
    )

    journal = initialize_battle_scenario_materialization_run(plan, identity)

    assert len(journal.entries) == 2
    require_battle_scenario_materialization_run_matches_plan(
        journal,
        plan,
        identity,
    )
