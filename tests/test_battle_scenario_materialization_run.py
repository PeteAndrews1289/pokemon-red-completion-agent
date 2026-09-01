from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (
    MANSION_VENUE_ID,
    ROUTE_11_VENUE_ID,
    BattleScenarioMaterializationCandidate,
    BattleScenarioPartySlot,
    build_battle_scenario_materialization_plan,
)
from pokemon_red_completion.battle_scenario_materialization_run import (
    FAILED,
    PENDING,
    STARTED,
    SUCCEEDED,
    BattleScenarioMaterializationRunError,
    BattleScenarioMaterializationRunIdentity,
    fail_battle_scenario_materialization_assignment,
    initialize_battle_scenario_materialization_run,
    parse_battle_scenario_materialization_run,
    require_battle_scenario_materialization_run_matches_plan,
    start_battle_scenario_materialization_assignment,
    succeed_battle_scenario_materialization_assignment,
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


def _candidate(index: int, venue_id: str) -> BattleScenarioMaterializationCandidate:
    route_11 = venue_id == ROUTE_11_VENUE_ID
    return BattleScenarioMaterializationCandidate(
        source=_source(index),
        venue_id=venue_id,
        source_location="lavender_center_route_11" if route_11 else "cinnabar_center",
        minimum_encounter_level=9 if route_11 else 28,
        maximum_encounter_level=15 if route_11 else 34,
        rare_maximum_encounter_level=17 if route_11 else 39,
        party_slots=(
            BattleScenarioPartySlot(
                party_slot=1,
                species_id=10 + index,
                level=20 if route_11 else 30,
                current_hp=40,
                maximum_hp=50,
                status_id=0,
                usable_move_count=3,
            ),
        ),
    )


def _plan():  # type: ignore[no-untyped-def]
    return build_battle_scenario_materialization_plan(
        plan_id="red-battle-v2-materialization",
        source_commit="b" * 40,
        source_bundle_sha256=_sha("freezer-bundle"),
        rom_sha256=_sha("rom"),
        capture_directory_sha256=_sha("capture-directory"),
        candidates=(
            *(_candidate(index, MANSION_VENUE_ID) for index in range(7)),
            _candidate(20, ROUTE_11_VENUE_ID),
            _candidate(21, ROUTE_11_VENUE_ID),
        ),
    )


def _identity(plan=None):  # type: ignore[no-untyped-def]
    plan = plan or _plan()
    return BattleScenarioMaterializationRunIdentity(
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


def test_journal_starts_with_exact_seven_item_pending_denominator() -> None:
    plan = _plan()
    journal = initialize_battle_scenario_materialization_run(plan, _identity(plan))

    assert len(journal.entries) == 7
    assert {item.status for item in journal.entries} == {PENDING}
    assert {item.attempt_count for item in journal.entries} == {0}
    assert parse_battle_scenario_materialization_run(journal.canonical_bytes()) == journal
    require_battle_scenario_materialization_run_matches_plan(
        journal,
        plan,
        _identity(plan),
    )


def test_started_assignment_can_only_move_once_to_one_terminal_state() -> None:
    plan = _plan()
    initial = initialize_battle_scenario_materialization_run(plan, _identity(plan))
    started = start_battle_scenario_materialization_assignment(initial, 0)

    assert started.entries[0].status == STARTED
    assert started.entries[0].attempt_count == 1
    with pytest.raises(BattleScenarioMaterializationRunError, match="only a pending"):
        start_battle_scenario_materialization_assignment(started, 0)

    succeeded = succeed_battle_scenario_materialization_assignment(
        started,
        0,
        state_sha256=_sha("state-output"),
        manifest_sha256=_sha("manifest-output"),
    )
    assert succeeded.entries[0].status == SUCCEEDED
    with pytest.raises(BattleScenarioMaterializationRunError, match="only a started"):
        fail_battle_scenario_materialization_assignment(
            succeeded,
            0,
            reason_code="late_failure",
        )


def test_failed_assignment_is_terminal_and_stays_in_denominator() -> None:
    plan = _plan()
    journal = initialize_battle_scenario_materialization_run(plan, _identity(plan))
    journal = start_battle_scenario_materialization_assignment(journal, 3)
    journal = fail_battle_scenario_materialization_assignment(
        journal,
        3,
        reason_code="materializer_process_failed",
    )

    assert journal.entries[3].status == FAILED
    assert journal.entries[3].attempt_count == 1
    assert len(journal.entries) == 7
    assert journal.public_receipt()["counts"] == {
        "pending": 6,
        "started": 0,
        "succeeded": 0,
        "failed": 1,
    }
    with pytest.raises(BattleScenarioMaterializationRunError, match="only a pending"):
        start_battle_scenario_materialization_assignment(journal, 3)


def test_journal_rejects_changed_plan_execution_or_assignment_identity() -> None:
    plan = _plan()
    identity = _identity(plan)
    journal = initialize_battle_scenario_materialization_run(plan, identity)

    with pytest.raises(BattleScenarioMaterializationRunError, match="identity differs"):
        require_battle_scenario_materialization_run_matches_plan(
            journal,
            plan,
            replace(identity, source_commit="d" * 40),
        )
    value = json.loads(journal.canonical_bytes())
    value["entries"][0]["capture_id"] = "substituted"
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )
    changed = parse_battle_scenario_materialization_run(payload)
    with pytest.raises(BattleScenarioMaterializationRunError, match="assignment differs"):
        require_battle_scenario_materialization_run_matches_plan(
            changed,
            plan,
            identity,
        )


def test_parser_rejects_noncanonical_duplicate_and_rewound_states() -> None:
    plan = _plan()
    journal = initialize_battle_scenario_materialization_run(plan, _identity(plan))

    with pytest.raises(BattleScenarioMaterializationRunError, match="not canonical"):
        parse_battle_scenario_materialization_run(
            json.dumps(json.loads(journal.canonical_bytes()), indent=2).encode("ascii")
        )
    with pytest.raises(BattleScenarioMaterializationRunError, match="not canonical"):
        parse_battle_scenario_materialization_run(b'{"schema":"x","schema":"y"}\n')

    value = json.loads(journal.canonical_bytes())
    value["entries"][0]["status"] = STARTED
    value["entries"][0]["attempt_count"] = 0
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )
    with pytest.raises(BattleScenarioMaterializationRunError, match="entry state"):
        parse_battle_scenario_materialization_run(payload)


def test_public_receipt_is_aggregate_path_free_and_declares_zero_learning() -> None:
    plan = _plan()
    journal = initialize_battle_scenario_materialization_run(plan, _identity(plan))
    journal = start_battle_scenario_materialization_assignment(journal, 0)
    receipt = journal.public_receipt()
    encoded = json.dumps(receipt, sort_keys=True)

    assert receipt["status"] == "interrupted_nonretryable"
    assert receipt["retry_after_started"] is False
    assert receipt["move_choices_executed"] == 0
    assert receipt["teacher_queries"] == 0
    assert receipt["outcomes_opened"] == 0
    assert receipt["model_fits"] == 0
    assert receipt["authority_promoted"] is False
    assert receipt["private_path_fields"] == 0
    assert "/private/" not in encoded
    assert "state_filename" not in encoded
    assert "capture_id" not in encoded
