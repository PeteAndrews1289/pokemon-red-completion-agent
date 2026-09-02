#!/usr/bin/env python3
"""Recover one path-free Red battle-cycle terminal without replay or refit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import (  # noqa: E402
    MaskedMLPMoveRanker,
)
from pokemon_red_completion.battle_outcome_batch import (  # noqa: E402
    build_retained_battle_outcome_prefix,
)
from pokemon_red_completion.battle_outcome_experiment import (  # noqa: E402
    BattleOutcomeExperimentPlan,
    parse_battle_outcome_experiment_plan,
)
from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    BattleOutcomePairedEvaluation,
    BattleTurnOutcome,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactReader,
    open_private_root,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAXIMUM_PLAN_BYTES = 128 * 1024
_COMPLETE_STATUSES = {
    "candidate_advantage_observed",
    "no_update",
    "rejected_no_development_advantage",
    "rejected_no_development_discordance",
}
_TERMINAL_FIELDS = {
    "record_type",
    "status",
    "experiment_id",
    "plan_sha256",
    "cycle",
    "paired_development",
    "base_model_sha256",
    "model_sha256",
    "claim",
    "candidate_advantage_observed",
    "historically_untouched_claimed",
    "root_claims_created",
    "candidate_claims_created",
    "measured_candidate_outcomes",
    "activated_candidate_targets",
    "deferred_unactivated_development_candidates",
    "unexecuted_counterfactual_targets",
    "unmeasured_action_targets",
    "development_capture_metadata_opened",
    "development_outcomes_opened",
    "development_influenced_fit",
    "development_predictions_committed_before_outcomes",
    "model_fits",
    "development_comparisons",
    "unseen_comparisons",
    "authority_promoted",
    "red_sealed_test_cases_opened",
    "crystal_contexts_opened",
    "teacher_queries",
    "teacher_choice_targets",
    "full_game_replays",
    "materializer_derivation_claimed",
    "private_path_fields",
}


class BattleOutcomeCycleInspectionError(RuntimeError):
    """Raised when retained cycle evidence cannot support a public terminal."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument(
        "--project-retained-batch-prefix",
        action="store_true",
        help="project the verified V1 train prefix without replaying it",
    )
    parser.add_argument(
        "--out-retained-batch-prefix",
        type=Path,
        default=None,
        help="exclusive private canonical retained-prefix output",
    )
    parser.add_argument(
        "--out-retained-train-record",
        type=Path,
        default=None,
        help="exclusive private canonical retained train-record output",
    )
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    projection_outputs = (
        getattr(args, "out_retained_batch_prefix", None),
        getattr(args, "out_retained_train_record", None),
    )
    if any(item is not None for item in projection_outputs) and not getattr(
        args, "project_retained_batch_prefix", False
    ):
        raise BattleOutcomeCycleInspectionError(
            "retained output requires retained-prefix projection"
        )
    expected_plan_sha256 = _sha256(args.expected_plan_sha256, "experiment plan")
    plan = _read_plan(args.plan, expected_plan_sha256)
    artifact_id = f"bo-cycle-{plan.plan_sha256}"
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    recovery = store.reconcile_interrupted_artifact(
        artifact_id,
        expected_kind="battle_outcome_cycle",
    )
    if recovery.summary.status == "complete":
        reader = store.open_artifact(
            artifact_id,
            expected_kind="battle_outcome_cycle",
        )
        receipt = _project_complete(reader, plan)
        if getattr(args, "project_retained_batch_prefix", False):
            prefix = _project_retained_batch_prefix(reader, plan)
            record_destination = getattr(args, "out_retained_train_record", None)
            if record_destination is not None:
                record_sha256 = _project_retained_train_record(
                    reader,
                    plan,
                    record_destination,
                )
                if record_sha256 != prefix["train_record_sha256"]:
                    raise BattleOutcomeCycleInspectionError(
                        "retained train-record projection differs from prefix"
                    )
            return prefix
        return receipt
    if getattr(args, "project_retained_batch_prefix", False):
        raise BattleOutcomeCycleInspectionError(
            "failed battle evidence cannot become a retained train prefix"
        )
    reader = store.open_failed_artifact(
        artifact_id,
        expected_kind="battle_outcome_cycle",
    )
    return _project_failure(reader, plan)


def _project_complete(
    reader: PrivateArtifactReader,
    plan: BattleOutcomeExperimentPlan,
) -> dict[str, object]:
    terminal = _single_record(reader, "terminal")
    assignment = _single_record(reader, "assignment")
    evaluation = _single_record(reader, "evaluation")
    status = terminal.get("status")
    if (
        set(terminal) != _TERMINAL_FIELDS
        or terminal.get("record_type") != "battle_outcome_cycle_terminal"
        or status not in _COMPLETE_STATUSES
        or terminal.get("plan_sha256") != plan.plan_sha256
        or terminal.get("experiment_id") != plan.experiment_id
        or terminal.get("base_model_sha256") != plan.base_model_sha256
        or assignment.get("record_type") != "battle_outcome_experiment_assignment"
        or assignment.get("plan_sha256") != plan.plan_sha256
        or evaluation.get("status") != status
        or evaluation.get("claim") != terminal.get("claim")
    ):
        raise BattleOutcomeCycleInspectionError(
            "retained cycle terminal differs from its prospective plan"
        )

    stream_counts = dict(reader.summary.stream_records)
    root_claims = _records(reader, "root_claims")
    candidate_claims = _records(reader, "candidate_claims")
    candidate_outcomes = _records(reader, "candidate_outcomes")
    root_count = _integer(terminal, "root_claims_created")
    candidate_count = _integer(terminal, "candidate_claims_created")
    measured_count = _integer(terminal, "measured_candidate_outcomes")
    activated_count = _integer(terminal, "activated_candidate_targets")
    development_outcomes = _integer(terminal, "development_outcomes_opened")
    model_fits = _integer(terminal, "model_fits")
    development_comparisons = _integer(terminal, "development_comparisons")
    if (
        stream_counts.get("terminal") != 1
        or len(root_claims) != root_count
        or len(candidate_claims) != candidate_count
        or len(candidate_outcomes) != measured_count
        or candidate_count != measured_count
        or candidate_count != activated_count
        or len(_records(reader, "model", optional=True)) != model_fits
        or len(_records(reader, "prediction_commitment", optional=True)) != development_comparisons
        or sum(record.get("split") == "development" for record in candidate_outcomes)
        != development_outcomes
        or sum(record.get("split") == "train" for record in root_claims) != 1
        or sum(record.get("split") == "development" for record in root_claims)
        != int(root_count == 2)
        or sum(record.get("split") == "train" for record in candidate_claims)
        != plan.train.supported_candidate_count
        or sum(record.get("split") == "development" for record in candidate_claims)
        != development_outcomes
    ):
        raise BattleOutcomeCycleInspectionError(
            "retained cycle streams differ from the terminal census"
        )
    _require_candidate_join(candidate_claims, candidate_outcomes)
    _require_terminal_policy(terminal, plan)
    _require_model_record(reader, terminal, plan)
    _require_retained_result(reader, terminal, evaluation, plan)

    public_terminal = dict(terminal)
    del public_terminal["record_type"]
    return {
        "schema": "pokemon-red-battle-outcome-cycle-receipt-v4",
        "artifact": reader.summary.public_dict(),
        **public_terminal,
    }


def _project_retained_batch_prefix(
    reader: PrivateArtifactReader,
    plan: BattleOutcomeExperimentPlan,
) -> dict[str, object]:
    if reader.summary.status != "complete":
        raise BattleOutcomeCycleInspectionError(
            "failed battle evidence cannot become a retained train prefix"
        )
    train_record = _retained_train_record(reader)
    try:
        retained = build_retained_battle_outcome_prefix(
            plan,
            artifact_manifest_sha256=reader.summary.manifest_sha256,
            train_collection_record=train_record,
        )
    except (TypeError, ValueError):
        raise BattleOutcomeCycleInspectionError(
            "retained V1 train collection differs from its inspected artifact"
        ) from None
    return retained.public_dict()


def _retained_train_record(reader: PrivateArtifactReader) -> dict[str, object]:
    train_records = tuple(
        record
        for record in _records(reader, "outcomes")
        if record.get("split") == ScenarioPartition.TRAIN.value
    )
    if len(train_records) != 1:
        raise BattleOutcomeCycleInspectionError(
            "retained V1 train collection is not singular"
        )
    return train_records[0]


def _project_retained_train_record(
    reader: PrivateArtifactReader,
    plan: BattleOutcomeExperimentPlan,
    destination: Path,
) -> str:
    train_record = _retained_train_record(reader)
    try:
        retained = build_retained_battle_outcome_prefix(
            plan,
            artifact_manifest_sha256=reader.summary.manifest_sha256,
            train_collection_record=train_record,
        )
    except (TypeError, ValueError):
        raise BattleOutcomeCycleInspectionError(
            "retained V1 train collection differs from its inspected artifact"
        ) from None
    _write_exclusive_projection(
        _private_new_projection(destination),
        _canonical_payload(train_record),
    )
    return retained.train_record_sha256


def _project_failure(
    reader: PrivateArtifactReader,
    plan: BattleOutcomeExperimentPlan,
) -> dict[str, object]:
    stream_counts = dict(reader.summary.stream_records)
    return {
        "schema": "pokemon-red-battle-outcome-cycle-recovery-receipt-v1",
        "status": "failed",
        "reason_code": reader.reason_code,
        "artifact": reader.summary.public_dict(),
        "experiment_id": plan.experiment_id,
        "plan_sha256": plan.plan_sha256,
        "root_claims_retained": stream_counts.get("root_claims", 0),
        "candidate_claims_retained": stream_counts.get("candidate_claims", 0),
        "candidate_outcomes_retained": stream_counts.get("candidate_outcomes", 0),
        "model_records_retained": stream_counts.get("model", 0),
        "terminal_records_retained": stream_counts.get("terminal", 0),
        "counter_projection_authorized": False,
        "root_retries": 0,
        "emulator_inputs": 0,
        "outcome_reads": 0,
        "predictions": 0,
        "model_fits": 0,
        "private_path_fields": 0,
    }


def _require_candidate_join(
    claims: tuple[dict[str, object], ...],
    outcomes: tuple[dict[str, object], ...],
) -> None:
    claim_keys = {
        (record.get("split"), record.get("capture_id"), record.get("candidate_index"))
        for record in claims
    }
    outcome_keys = {
        (record.get("split"), record.get("capture_id"), record.get("candidate_index"))
        for record in outcomes
    }
    if (
        len(claim_keys) != len(claims)
        or len(outcome_keys) != len(outcomes)
        or claim_keys != outcome_keys
    ):
        raise BattleOutcomeCycleInspectionError(
            "candidate claims and outcomes do not form one retained census"
        )


def _require_terminal_policy(
    terminal: Mapping[str, object],
    plan: BattleOutcomeExperimentPlan,
) -> None:
    status = terminal.get("status")
    train_count = plan.train.supported_candidate_count
    development_count = plan.development.supported_candidate_count
    zeros = (
        "authority_promoted",
        "historically_untouched_claimed",
        "materializer_derivation_claimed",
    )
    if any(terminal.get(key) is not False for key in zeros) or any(
        _integer(terminal, key) != 0
        for key in (
            "crystal_contexts_opened",
            "full_game_replays",
            "red_sealed_test_cases_opened",
            "teacher_choice_targets",
            "teacher_queries",
            "unexecuted_counterfactual_targets",
            "unmeasured_action_targets",
            "unseen_comparisons",
            "private_path_fields",
        )
    ):
        raise BattleOutcomeCycleInspectionError("retained terminal crosses a protected boundary")
    if status == "no_update":
        expected = (1, train_count, development_count, 0, 0)
        if (
            terminal.get("cycle") is not None
            or terminal.get("paired_development") is not None
            or terminal.get("model_sha256") is not None
            or terminal.get("candidate_advantage_observed") is not False
            or terminal.get("development_predictions_committed_before_outcomes") is not False
            or _integer(terminal, "development_comparisons") != 0
        ):
            raise BattleOutcomeCycleInspectionError(
                "no-update terminal contains a development or model result"
            )
    else:
        expected = (2, train_count + development_count, 0, development_count, 1)
        if (
            not isinstance(terminal.get("cycle"), Mapping)
            or not isinstance(terminal.get("paired_development"), Mapping)
            or not isinstance(terminal.get("model_sha256"), str)
            or terminal.get("development_predictions_committed_before_outcomes") is not True
            or _integer(terminal, "development_comparisons") != 1
            or terminal.get("candidate_advantage_observed")
            is not (status == "candidate_advantage_observed")
        ):
            raise BattleOutcomeCycleInspectionError(
                "updated terminal lacks its development or model result"
            )
    if (
        terminal.get("development_capture_metadata_opened") is not True
        or terminal.get("development_influenced_fit") is not False
    ):
        raise BattleOutcomeCycleInspectionError("retained terminal misstates development isolation")
    observed = (
        _integer(terminal, "root_claims_created"),
        _integer(terminal, "activated_candidate_targets"),
        _integer(terminal, "deferred_unactivated_development_candidates"),
        _integer(terminal, "development_outcomes_opened"),
        _integer(terminal, "model_fits"),
    )
    if observed != expected:
        raise BattleOutcomeCycleInspectionError("retained terminal violates cycle policy")


def _require_retained_result(
    reader: PrivateArtifactReader,
    terminal: Mapping[str, object],
    evaluation: Mapping[str, object],
    plan: BattleOutcomeExperimentPlan,
) -> None:
    """Re-derive every public result from the durable pre-outcome commitment.

    Stream integrity alone cannot establish that a terminal describes the
    retained outcomes.  This join deliberately reconstructs the one-context
    development comparison instead of trusting either redundant result record.
    """

    status = terminal.get("status")
    if status == "no_update":
        expected_evaluation = {
            "record_type": "battle_outcome_no_update",
            "status": "no_update",
            "claim": "insufficient_train_preference_signal",
            "train_learner_update_eligible": False,
            "development_root_claimed": False,
            "development_capture_metadata_opened": True,
            "development_outcomes_opened": 0,
            "activated_candidate_targets": plan.train.supported_candidate_count,
            "deferred_unactivated_development_candidates": (
                plan.development.supported_candidate_count
            ),
            "promotion_gate_passed": False,
            "model_written": False,
        }
        expected_streams = {
            "assignment",
            "candidate_claims",
            "candidate_outcomes",
            "evaluation",
            "outcomes",
            "root_claims",
            "terminal",
        }
        if dict(evaluation) != expected_evaluation or set(reader.stream_names) != expected_streams:
            raise BattleOutcomeCycleInspectionError(
                "retained no-update result differs from its frozen policy"
            )
        return

    expected_streams = {
        "assignment",
        "candidate_claims",
        "candidate_outcomes",
        "evaluation",
        "model",
        "outcomes",
        "prediction_commitment",
        "root_claims",
        "terminal",
    }
    if set(reader.stream_names) != expected_streams:
        raise BattleOutcomeCycleInspectionError(
            "retained updated result has an unexpected evidence stream"
        )

    commitment = _single_record(reader, "prediction_commitment")
    model_record = _single_record(reader, "model")
    updated_model_sha256 = terminal.get("model_sha256")
    base_choice = commitment.get("base_candidate_index")
    updated_choice = commitment.get("updated_candidate_index")
    if (
        commitment.get("record_type") != "battle_development_prediction_commitment"
        or commitment.get("plan_sha256") != plan.plan_sha256
        or commitment.get("capture_id") != plan.development.capture_id
        or commitment.get("manifest_sha256") != plan.development.manifest_sha256
        or commitment.get("initial_observation_sha256")
        != plan.development.initial_observation_sha256
        or commitment.get("base_model_sha256") != plan.base_model_sha256
        or commitment.get("updated_model_sha256") != updated_model_sha256
        or commitment.get("development_outcomes_opened") != 0
        or type(base_choice) is not int  # noqa: E721
        or type(updated_choice) is not int  # noqa: E721
    ):
        raise BattleOutcomeCycleInspectionError(
            "retained development commitment differs from the frozen comparison"
        )

    development_records = tuple(
        record
        for record in _records(reader, "candidate_outcomes")
        if record.get("split") == "development"
    )
    utilities: dict[int, float] = {}
    claim_sha256 = commitment.get("root_pair_claim_sha256")
    for record in development_records:
        candidate_index = record.get("candidate_index")
        if (
            record.get("record_type") != "battle_candidate_outcome"
            or record.get("plan_sha256") != plan.plan_sha256
            or record.get("root_pair_claim_sha256") != claim_sha256
            or record.get("capture_id") != plan.development.capture_id
            or type(candidate_index) is not int  # noqa: E721
            or candidate_index in utilities
            or record.get("teacher_queries") != 0
            or record.get("teacher_choice_targets") != 0
        ):
            raise BattleOutcomeCycleInspectionError("retained development outcome identity differs")
        utilities[candidate_index] = _outcome_utility(record.get("outcome"))
    if (
        len(utilities) != plan.development.supported_candidate_count
        or base_choice not in utilities
        or updated_choice not in utilities
    ):
        raise BattleOutcomeCycleInspectionError(
            "retained development commitment does not select measured outcomes"
        )

    best_utility = max(utilities.values())
    difference = utilities[updated_choice] - utilities[base_choice]
    equivalent = math.isclose(difference, 0.0, abs_tol=1e-9)
    expected_paired = BattleOutcomePairedEvaluation(
        base_model_sha256=plan.base_model_sha256,
        updated_model_sha256=str(updated_model_sha256),
        example_count=1,
        updated_wins=int(difference > 0.0 and not equivalent),
        base_wins=int(difference < 0.0 and not equivalent),
        equivalent_choices=int(equivalent),
        base_correct_preferences=int(
            math.isclose(utilities[base_choice], best_utility, abs_tol=1e-9)
        ),
        updated_correct_preferences=int(
            math.isclose(utilities[updated_choice], best_utility, abs_tol=1e-9)
        ),
        root_lineage_ids=(plan.development.root_lineage_id,),
    ).public_dict()
    if expected_paired["discordant_examples"] == 0:
        expected_status = "rejected_no_development_discordance"
        expected_claim = "no_discordant_development_choice"
    elif _integer(expected_paired, "updated_wins") <= _integer(
        expected_paired,
        "base_wins",
    ):
        expected_status = "rejected_no_development_advantage"
        expected_claim = "candidate_did_not_beat_frozen_prior"
    else:
        expected_status = "candidate_advantage_observed"
        expected_claim = "bounded_descriptive_advantage_only"

    update_report = model_record.get("update_report")
    if not isinstance(update_report, Mapping):
        raise BattleOutcomeCycleInspectionError("retained model update report is invalid")
    _require_update_report(update_report, plan, str(updated_model_sha256))
    base_correct = int(math.isclose(utilities[base_choice], best_utility, abs_tol=1e-9))
    updated_correct = int(math.isclose(utilities[updated_choice], best_utility, abs_tol=1e-9))
    expected_cycle = {
        "schema": "pokemon.core.battle.outcome-learning-cycle.v1",
        "update": dict(update_report),
        "base_development": _development_evaluation(
            model_sha256=plan.base_model_sha256,
            correct=base_correct,
            selected_utility=utilities[base_choice],
            root_lineage_id=plan.development.root_lineage_id,
        ),
        "updated_development": _development_evaluation(
            model_sha256=str(updated_model_sha256),
            correct=updated_correct,
            selected_utility=utilities[updated_choice],
            root_lineage_id=plan.development.root_lineage_id,
        ),
        "lineage_partition_overlap": 0,
        "initial_state_partition_overlap": 0,
        "sealed_test_cases_opened": 0,
        "authority_promoted": False,
    }
    expected_evaluation = {
        "record_type": "battle_outcome_learning_cycle",
        "status": expected_status,
        "cycle": expected_cycle,
        "paired_development": expected_paired,
        "claim": expected_claim,
        "candidate_advantage_observed": (expected_status == "candidate_advantage_observed"),
        "historically_untouched_claimed": False,
        "promotion_gate_passed": False,
        "reason_promotion_false": "independent_sealed_gate_not_run",
    }
    if (
        status != expected_status
        or terminal.get("claim") != expected_claim
        or terminal.get("paired_development") != expected_paired
        or terminal.get("cycle") != expected_cycle
        or dict(evaluation) != expected_evaluation
    ):
        raise BattleOutcomeCycleInspectionError(
            "retained development result differs from measured utilities"
        )


def _outcome_utility(value: object) -> float:
    if not isinstance(value, Mapping):
        raise BattleOutcomeCycleInspectionError("retained candidate outcome is invalid")
    expected_fields = {
        "schema",
        "move_executed",
        "opponent_damage_fraction",
        "player_damage_fraction",
        "opponent_fainted",
        "player_fainted",
        "battle_exited",
        "actions_executed",
        "frames_executed",
        "pre_attack_frames",
        "utility",
    }
    if set(value) != expected_fields or value.get("schema") != (
        "pokemon.core.battle.selected-turn-outcome.v2"
    ):
        raise BattleOutcomeCycleInspectionError("retained candidate outcome is invalid")
    try:
        outcome = BattleTurnOutcome(
            move_executed=value["move_executed"],
            opponent_damage_fraction=value["opponent_damage_fraction"],
            player_damage_fraction=value["player_damage_fraction"],
            opponent_fainted=value["opponent_fainted"],
            player_fainted=value["player_fainted"],
            battle_exited=value["battle_exited"],
            actions_executed=value["actions_executed"],
            frames_executed=value["frames_executed"],
            pre_attack_frames=value["pre_attack_frames"],
        )
    except (TypeError, ValueError):
        raise BattleOutcomeCycleInspectionError("retained candidate outcome is invalid") from None
    if outcome.public_dict() != dict(value):
        raise BattleOutcomeCycleInspectionError(
            "retained candidate outcome utility is not canonical"
        )
    return outcome.utility


def _require_update_report(
    report: Mapping[str, object],
    plan: BattleOutcomeExperimentPlan,
    updated_model_sha256: str,
) -> None:
    expected_fields = {
        "schema",
        "base_model_sha256",
        "updated_model_sha256",
        "training_example_count",
        "training_root_lineage_ids",
        "training_state_sha256",
        "loss_before",
        "loss_after",
        "epochs",
        "learning_rate",
        "prior_l2",
        "authority_promoted",
        "teacher_choice_targets",
    }
    losses = (report.get("loss_before"), report.get("loss_after"))
    if (
        set(report) != expected_fields
        or report.get("schema") != "pokemon.core.battle.outcome-update.v1"
        or report.get("base_model_sha256") != plan.base_model_sha256
        or report.get("updated_model_sha256") != updated_model_sha256
        or report.get("training_example_count") != 1
        or report.get("training_root_lineage_ids") != [plan.train.root_lineage_id]
        or report.get("training_state_sha256") != [plan.train.state_sha256]
        or report.get("epochs") != plan.epochs
        or report.get("learning_rate") != plan.learning_rate
        or report.get("prior_l2") != plan.prior_l2
        or report.get("authority_promoted") is not False
        or report.get("teacher_choice_targets") != 0
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in losses
        )
    ):
        raise BattleOutcomeCycleInspectionError("retained model update report is invalid")


def _development_evaluation(
    *,
    model_sha256: str,
    correct: int,
    selected_utility: float,
    root_lineage_id: str,
) -> dict[str, object]:
    return {
        "schema": "pokemon.core.battle.outcome-evaluation.v1",
        "model_sha256": model_sha256,
        "partition": "development",
        "example_count": 1,
        "correct_preferences": correct,
        "preference_accuracy": float(correct),
        "mean_selected_utility": selected_utility,
        "root_lineage_ids": [root_lineage_id],
        "learner_updates": 0,
        "authority_promoted": False,
    }


def _require_model_record(
    reader: PrivateArtifactReader,
    terminal: Mapping[str, object],
    plan: BattleOutcomeExperimentPlan,
) -> None:
    models = _records(reader, "model", optional=True)
    if not models:
        if terminal.get("model_sha256") is not None:
            raise BattleOutcomeCycleInspectionError("no-update terminal names a model")
        return
    record = models[0]
    model_payload = record.get("model")
    if not isinstance(model_payload, Mapping):
        raise BattleOutcomeCycleInspectionError("retained model payload is invalid")
    try:
        model = MaskedMLPMoveRanker.from_dict(model_payload)
    except (TypeError, ValueError):
        raise BattleOutcomeCycleInspectionError("retained model payload is invalid") from None
    digest = hashlib.sha256(model.to_json().encode("ascii")).hexdigest()
    if (
        record.get("model_sha256") != digest
        or terminal.get("model_sha256") != digest
        or record.get("base_model_sha256") != plan.base_model_sha256
    ):
        raise BattleOutcomeCycleInspectionError("retained model identity differs")


def _single_record(
    reader: PrivateArtifactReader,
    stream: str,
) -> dict[str, object]:
    records = _records(reader, stream)
    if len(records) != 1:
        raise BattleOutcomeCycleInspectionError(f"retained {stream} stream is not singular")
    return records[0]


def _records(
    reader: PrivateArtifactReader,
    stream: str,
    *,
    optional: bool = False,
) -> tuple[dict[str, object], ...]:
    if stream not in reader.stream_names:
        if optional:
            return ()
        raise BattleOutcomeCycleInspectionError(f"retained {stream} stream is absent")
    return tuple(reader.iter_stream(stream, max_records=8))


def _integer(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise BattleOutcomeCycleInspectionError(f"retained {key} is invalid")
    return value


def _read_plan(path: Path, expected_sha256: str) -> BattleOutcomeExperimentPlan:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or not 1 <= opened.st_size <= _MAXIMUM_PLAN_BYTES
        ):
            raise OSError("unsafe plan")
        payload = os.read(descriptor, opened.st_size + 1)
        if len(payload) != opened.st_size:
            raise OSError("plan changed")
    except OSError:
        raise BattleOutcomeCycleInspectionError("experiment plan cannot be authenticated") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise BattleOutcomeCycleInspectionError("experiment plan digest differs")
    try:
        return parse_battle_outcome_experiment_plan(payload)
    except ValueError:
        raise BattleOutcomeCycleInspectionError("experiment plan cannot be authenticated") from None


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleOutcomeCycleInspectionError(f"{subject} digest is invalid")
    return value


def _private_new_projection(destination: Path) -> Path:
    if not isinstance(destination, Path):
        raise TypeError("retained-prefix destination must be a Path")
    resolved = destination.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise BattleOutcomeCycleInspectionError(
            "retained-prefix projection must remain private"
        )
    if (
        not resolved.parent.is_dir()
        or resolved.exists()
        or destination.is_symlink()
    ):
        raise BattleOutcomeCycleInspectionError(
            "retained-prefix output is unavailable or already exists"
        )
    return resolved


def _write_exclusive_projection(destination: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    directory_descriptor = -1
    created = False
    try:
        descriptor = os.open(destination, flags, 0o600)
        created = True
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("retained-prefix write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        directory_descriptor = os.open(
            destination.parent,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
        os.fsync(directory_descriptor)
    except OSError:
        if created:
            with suppress(OSError):
                destination.unlink()
        raise BattleOutcomeCycleInspectionError(
            "retained-prefix projection could not be retained"
        ) from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if directory_descriptor >= 0:
            with suppress(OSError):
                os.close(directory_descriptor)


def _canonical_payload(value: object) -> bytes:
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = _run(args)
    encoded = _canonical_payload(receipt)
    destination = getattr(args, "out_retained_batch_prefix", None)
    if destination is not None:
        _write_exclusive_projection(_private_new_projection(destination), encoded)
    print(json.dumps(receipt, allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
