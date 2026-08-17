from __future__ import annotations

import runpy
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeDose,
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.party_development_rank import PartyDevelopmentGoal
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_repeatable_party_outcome_successor.py")
)


def _assignment(*, binding: str, candidate_index: int = 1):
    return PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=2,
        scenario_id="repeatable-party-train-001",
        root_lineage_id="red-goal-root-example",
        initial_state_sha256="1" * 64,
        partition=ScenarioPartition.TRAIN,
        kind=TrainingChoiceKind.TRAINEE,
        goal=PartyDevelopmentGoal.COLLECTION,
        binding_sha256=binding,
        candidate_index=candidate_index,
        candidate_sha256="2" * 64,
        candidate_feature_sha256="3" * 64,
    )


def test_successor_recovers_the_exact_frozen_candidate_permutation() -> None:
    expected = (2, 0, 1)

    recovered = SCRIPT["_recover_candidate_order"](
        3,
        canonical_sha256(list(expected)),
    )

    assert recovered == expected
    with pytest.raises(RuntimeError, match="not uniquely recoverable"):
        SCRIPT["_recover_candidate_order"](3, "f" * 64)


def test_successor_question_comparison_ignores_only_source_bound_option_identity() -> None:
    base = {
        "scenario_id": "repeatable-party-train-001",
        "root_lineage_id": "red-goal-root-example",
        "initial_state_sha256": "1" * 64,
        "partition": "train",
        "kind": "trainee",
        "goal": "collection",
        "candidate_count": 3,
        "candidate_order_sha256": "2" * 64,
        "timing_offset_frames": 17,
        "candidate_feature_values_public": False,
        "private_path_fields": 0,
        "option_sha256": "3" * 64,
    }
    new_source = {**base, "option_sha256": "4" * 64}

    assert SCRIPT["_assignment_semantics"](base) == SCRIPT[
        "_assignment_semantics"
    ](new_source)
    changed_timing = {**new_source, "timing_offset_frames": 18}
    assert SCRIPT["_assignment_semantics"](base) != SCRIPT[
        "_assignment_semantics"
    ](changed_timing)


def test_successor_plan_claims_only_the_predecessor_failure() -> None:
    old = _assignment(binding="a" * 64)
    current = _assignment(binding="b" * 64)
    dose = PartyDevelopmentOutcomeDose(
        completed_battles=1,
        maximum_encounter_steps=1_200,
        maximum_controller_actions=50_000,
        maximum_frames=750_000,
        maximum_healing_trips=3,
        maximum_rotations=8,
        maximum_faints=0,
    )
    key = (old.scenario_id, old.candidate_index)
    predecessor = SimpleNamespace(
        pilot=SimpleNamespace(manifest_sha256="c" * 64),
        dose=dose,
        old_assignments={key: old},
        current_assignments={key: current},
        claim_keys=(key,),
        semantic_reconstruction_sha256="d" * 64,
    )
    reconstruction = SimpleNamespace(
        plan=SimpleNamespace(plan_sha256="e" * 64)
    )
    args = Namespace(
        expected_predecessor_plan_sha256="f" * 64,
        expected_predecessor_source="1" * 40,
        expected_predecessor_measured_trials=78,
        expected_predecessor_invalid_trials=1,
        battle_credit_protocol="direct-safe-else-switch-assisted-fixed-dose-v1",
    )

    plan = SCRIPT["_successor_plan_core"](args, reconstruction, predecessor)

    assert plan["predecessor_candidate_denominator"] == 79
    assert plan["claimed_trial_count"] == 1
    assert plan["claims"] == [
        {
            "predecessor_assignment_sha256": old.assignment_sha256,
            "predecessor_trial_id": old.trial_id,
            "successor_assignment": current.private_dict(),
        }
    ]
    assert plan["dose"]["maximum_healing_trips"] == 3
    assert plan["retry_after_controller_input"] is False
    assert plan["teacher_queries"] == plan["sealed_red_cases_opened"] == 0


def test_successor_execution_cannot_start_without_its_frozen_plan() -> None:
    args = Namespace(
        out_plan=None,
        frozen_plan=None,
        execute=True,
        private_artifact_root=Path("/external/private"),
    )

    with pytest.raises(RuntimeError, match="needs a frozen plan"):
        SCRIPT["_run"](args)
