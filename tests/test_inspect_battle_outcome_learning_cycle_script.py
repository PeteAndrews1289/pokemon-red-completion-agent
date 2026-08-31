from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_experiment import (
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentPlan,
)
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, FEATURE_SCHEMA_ID
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/inspect_battle_outcome_learning_cycle.py")


def _model() -> MaskedMLPMoveRanker:
    weights = np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64)
    weights[0, 0] = 1.0
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.ones(2, dtype=np.float64),
        output_bias=0.0,
    )


class Reader:
    def __init__(
        self,
        streams: dict[str, tuple[dict[str, object], ...]],
        *,
        status: str = "complete",
        reason_code: str | None = None,
    ) -> None:
        self.streams = streams
        self.reason_code = reason_code
        self.summary = SimpleNamespace(
            status=status,
            manifest_sha256="d" * 64,
            stream_records=tuple((name, len(records)) for name, records in sorted(streams.items())),
            public_dict=lambda: {
                "schema": "private-json-artifact-summary-v1",
                "artifact_id": "bo-cycle-plan",
                "kind": "battle_outcome_cycle",
                "status": status,
            },
        )

    @property
    def stream_names(self) -> tuple[str, ...]:
        return tuple(self.streams)

    def iter_stream(
        self,
        stream: str,
        *,
        max_records: int | None = None,
    ):  # type: ignore[no-untyped-def]
        records = self.streams[stream]
        assert max_records is None or len(records) <= max_records
        return iter(records)


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        plan_sha256="1" * 64,
        experiment_id="battle-cycle-test",
        base_model_sha256="2" * 64,
        epochs=100,
        learning_rate=0.01,
        prior_l2=0.1,
        train=SimpleNamespace(
            supported_candidate_count=2,
            root_lineage_id="red-goal-root-" + "3" * 64,
            state_sha256="4" * 64,
        ),
        development=SimpleNamespace(
            supported_candidate_count=2,
            root_lineage_id="red-goal-root-" + "5" * 64,
            capture_id="development-capture",
            manifest_sha256="6" * 64,
            initial_observation_sha256="7" * 64,
        ),
    )


def _outcome(opponent_damage_fraction: float) -> dict[str, object]:
    return {
        "schema": "pokemon.core.battle.selected-turn-outcome.v2",
        "move_executed": True,
        "opponent_damage_fraction": opponent_damage_fraction,
        "player_damage_fraction": 0.0,
        "opponent_fainted": False,
        "player_fainted": False,
        "battle_exited": False,
        "actions_executed": 2,
        "frames_executed": 100,
        "pre_attack_frames": 50,
        "utility": opponent_damage_fraction,
    }


def _retained_binding(
    partition: ScenarioPartition,
    marker: str,
) -> BattleOutcomeCaptureBinding:
    def digest(label: str) -> str:
        return hashlib.sha256(f"{marker}:{label}".encode()).hexdigest()

    source_state = digest("source-state")
    source_envelope = digest("source-envelope")
    assignment = digest("assignment")
    return BattleOutcomeCaptureBinding(
        partition=partition,
        capture_id=f"retained-{partition.value}-{marker}",
        manifest_sha256=digest("manifest"),
        state_sha256=digest("state"),
        initial_observation_sha256=digest("observation"),
        source_commit="a" * 40,
        source_state_sha256=source_state,
        source_slot_id=f"retained-{partition.value}-{marker}",
        source_assignment_id=assignment,
        source_context_id=digest("context"),
        source_envelope_sha256=source_envelope,
        root_lineage_id=f"red-goal-root-{assignment}",
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=source_state,
            envelope_sha256=source_envelope,
        ),
        menu_sha256=digest("menu"),
        supported_candidate_count=2,
        distinct_candidate_vector_count=2,
        hidden_embedding_sha256=digest("hidden"),
        distinct_hidden_embedding_count=2,
        expected_map=165,
        expected_battle_state=1,
    )


def _retained_plan() -> BattleOutcomeExperimentPlan:
    return BattleOutcomeExperimentPlan(
        experiment_id="retained-battle-cycle-test",
        source_commit="a" * 40,
        source_bundle_sha256="1" * 64,
        runner_sha256="2" * 64,
        materializer_sha256="3" * 64,
        registry_source_commit="b" * 40,
        registry_source_bundle_sha256="4" * 64,
        registry_sha256="5" * 64,
        context_catalog_sha256="6" * 64,
        rom_sha256="7" * 64,
        runtime_identity_sha256="8" * 64,
        numpy_runtime_sha256="9" * 64,
        base_model_sha256="a" * 64,
        controller_timing_sha256="b" * 64,
        captures=(
            _retained_binding(ScenarioPartition.TRAIN, "train"),
            _retained_binding(ScenarioPartition.DEVELOPMENT, "development"),
        ),
    )


def _retained_record(plan: BattleOutcomeExperimentPlan) -> dict[str, object]:
    return {
        "record_type": "battle_outcome_collection",
        "split": "train",
        "collection": {
            "schema": "pokemon.red.battle.outcome-collection.v1",
            "capture_id": plan.train.capture_id,
            "manifest_sha256": plan.train.manifest_sha256,
            "root_lineage_id": plan.train.root_lineage_id,
            "partition": "train",
            "initial_state_sha256": plan.train.state_sha256,
            "initial_observation_sha256": plan.train.initial_observation_sha256,
            "candidate_count": 2,
            "measured_candidate_count": 2,
            "outcomes": [_outcome(0.25), _outcome(0.75)],
            "best_candidate_indices": [1],
            "learner_update_eligible": True,
            "counterfactual_pre_attack_frames": 50,
            "teacher_queries": 0,
            "teacher_choice_targets": 0,
            "full_game_replays": 0,
            "private_path_fields": 0,
        },
        "unexecuted_counterfactual_targets": 0,
        "unmeasured_action_targets": 0,
    }


def _complete_reader() -> Reader:
    plan = _plan()
    model = _model()
    model_sha256 = hashlib.sha256(model.to_json().encode("ascii")).hexdigest()
    update_report = {
        "schema": "pokemon.core.battle.outcome-update.v1",
        "base_model_sha256": plan.base_model_sha256,
        "updated_model_sha256": model_sha256,
        "training_example_count": 1,
        "training_root_lineage_ids": [plan.train.root_lineage_id],
        "training_state_sha256": [plan.train.state_sha256],
        "loss_before": 1.0,
        "loss_after": 0.5,
        "epochs": plan.epochs,
        "learning_rate": plan.learning_rate,
        "prior_l2": plan.prior_l2,
        "authority_promoted": False,
        "teacher_choice_targets": 0,
    }
    base_development = {
        "schema": "pokemon.core.battle.outcome-evaluation.v1",
        "model_sha256": plan.base_model_sha256,
        "partition": "development",
        "example_count": 1,
        "correct_preferences": 0,
        "preference_accuracy": 0.0,
        "mean_selected_utility": 0.0,
        "root_lineage_ids": [plan.development.root_lineage_id],
        "learner_updates": 0,
        "authority_promoted": False,
    }
    updated_development = {
        **base_development,
        "model_sha256": model_sha256,
        "correct_preferences": 1,
        "preference_accuracy": 1.0,
        "mean_selected_utility": 1.0,
    }
    cycle = {
        "schema": "pokemon.core.battle.outcome-learning-cycle.v1",
        "update": update_report,
        "base_development": base_development,
        "updated_development": updated_development,
        "lineage_partition_overlap": 0,
        "initial_state_partition_overlap": 0,
        "sealed_test_cases_opened": 0,
        "authority_promoted": False,
    }
    paired = {
        "schema": "pokemon.core.battle.outcome-paired-evaluation.v1",
        "partition": "development",
        "base_model_sha256": plan.base_model_sha256,
        "updated_model_sha256": model_sha256,
        "example_count": 1,
        "updated_wins": 1,
        "base_wins": 0,
        "equivalent_choices": 0,
        "discordant_examples": 1,
        "updated_better_one_sided_exact_p": 0.5,
        "base_correct_preferences": 0,
        "updated_correct_preferences": 1,
        "root_lineage_ids": [plan.development.root_lineage_id],
        "inferential_claim": False,
        "learner_updates": 0,
        "authority_promoted": False,
    }
    terminal = {
        "record_type": "battle_outcome_cycle_terminal",
        "status": "candidate_advantage_observed",
        "experiment_id": plan.experiment_id,
        "plan_sha256": plan.plan_sha256,
        "cycle": cycle,
        "paired_development": paired,
        "base_model_sha256": plan.base_model_sha256,
        "model_sha256": model_sha256,
        "claim": "bounded_descriptive_advantage_only",
        "candidate_advantage_observed": True,
        "historically_untouched_claimed": False,
        "root_claims_created": 2,
        "candidate_claims_created": 4,
        "measured_candidate_outcomes": 4,
        "activated_candidate_targets": 4,
        "deferred_unactivated_development_candidates": 0,
        "unexecuted_counterfactual_targets": 0,
        "unmeasured_action_targets": 0,
        "development_capture_metadata_opened": True,
        "development_outcomes_opened": 2,
        "development_influenced_fit": False,
        "development_predictions_committed_before_outcomes": True,
        "model_fits": 1,
        "development_comparisons": 1,
        "unseen_comparisons": 0,
        "authority_promoted": False,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "full_game_replays": 0,
        "materializer_derivation_claimed": False,
        "private_path_fields": 0,
    }
    claims = tuple(
        {
            "split": split,
            "capture_id": ("train-capture" if split == "train" else plan.development.capture_id),
            "candidate_index": index,
        }
        for split in ("train", "development")
        for index in range(2)
    )
    outcomes = tuple(
        {
            **record,
            "record_type": "battle_candidate_outcome",
            "plan_sha256": plan.plan_sha256,
            "root_pair_claim_sha256": ("8" * 64 if record["split"] == "train" else "9" * 64),
            "outcome": _outcome(float(record["candidate_index"])),
            "teacher_queries": 0,
            "teacher_choice_targets": 0,
        }
        for record in claims
    )
    return Reader(
        {
            "assignment": (
                {
                    "record_type": "battle_outcome_experiment_assignment",
                    "plan_sha256": plan.plan_sha256,
                },
            ),
            "root_claims": ({"split": "train"}, {"split": "development"}),
            "candidate_claims": claims,
            "candidate_outcomes": outcomes,
            "outcomes": ({"split": "train"}, {"split": "development"}),
            "model": (
                {
                    "model": model.to_dict(),
                    "model_sha256": model_sha256,
                    "base_model_sha256": plan.base_model_sha256,
                    "update_report": update_report,
                },
            ),
            "prediction_commitment": (
                {
                    "record_type": "battle_development_prediction_commitment",
                    "plan_sha256": plan.plan_sha256,
                    "root_pair_claim_sha256": "9" * 64,
                    "capture_id": plan.development.capture_id,
                    "manifest_sha256": plan.development.manifest_sha256,
                    "initial_observation_sha256": (plan.development.initial_observation_sha256),
                    "base_model_sha256": plan.base_model_sha256,
                    "base_candidate_index": 0,
                    "updated_model_sha256": model_sha256,
                    "updated_candidate_index": 1,
                    "development_outcomes_opened": 0,
                },
            ),
            "evaluation": (
                {
                    "record_type": "battle_outcome_learning_cycle",
                    "status": terminal["status"],
                    "cycle": cycle,
                    "paired_development": paired,
                    "claim": terminal["claim"],
                    "candidate_advantage_observed": True,
                    "historically_untouched_claimed": False,
                    "promotion_gate_passed": False,
                    "reason_promotion_false": "independent_sealed_gate_not_run",
                },
            ),
            "terminal": (terminal,),
        }
    )


def test_complete_inspection_reconstructs_the_original_public_terminal() -> None:
    receipt = SCRIPT["_project_complete"](_complete_reader(), _plan())

    assert receipt["schema"] == "pokemon-red-battle-outcome-cycle-receipt-v4"
    assert receipt["status"] == "candidate_advantage_observed"
    assert receipt["candidate_claims_created"] == 4
    assert receipt["measured_candidate_outcomes"] == 4
    assert receipt["model_fits"] == 1
    assert receipt["unseen_comparisons"] == 0


def test_complete_inspection_projects_one_exact_path_free_retained_prefix() -> None:
    plan = _retained_plan()
    reader = Reader({"outcomes": (_retained_record(plan),)})

    receipt = SCRIPT["_project_retained_batch_prefix"](reader, plan)

    assert receipt["status"] == "verified_no_replay"
    assert receipt["plan_sha256"] == plan.plan_sha256
    assert receipt["artifact_manifest_sha256"] == "d" * 64
    assert receipt["train_supported_candidate_indices"] == [0, 1]
    assert "/private/" not in str(receipt)


def test_retained_prefix_projection_rejects_failed_evidence() -> None:
    plan = _retained_plan()
    reader = Reader(
        {"outcomes": (_retained_record(plan),)},
        status="failed",
        reason_code="process_interrupted",
    )

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleInspectionError"],
        match="failed battle evidence",
    ):
        SCRIPT["_project_retained_batch_prefix"](reader, plan)


def test_retained_prefix_projection_rejects_a_private_path_field() -> None:
    plan = _retained_plan()
    record = _retained_record(plan)
    record["private_path"] = "/private/capture.state"
    reader = Reader({"outcomes": (record,)})

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleInspectionError"],
        match="retained V1 train collection differs",
    ):
        SCRIPT["_project_retained_batch_prefix"](reader, plan)


def test_run_never_projects_a_prefix_before_full_terminal_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _retained_plan()
    reader = Reader({"outcomes": (_retained_record(plan),)})

    class Store:
        def reconcile_interrupted_artifact(
            self,
            artifact_id: str,
            *,
            expected_kind: str,
        ) -> SimpleNamespace:
            assert artifact_id == f"bo-cycle-{plan.plan_sha256}"
            assert expected_kind == "battle_outcome_cycle"
            return SimpleNamespace(summary=SimpleNamespace(status="complete"))

        def open_artifact(
            self,
            artifact_id: str,
            *,
            expected_kind: str,
        ) -> Reader:
            assert artifact_id == f"bo-cycle-{plan.plan_sha256}"
            assert expected_kind == "battle_outcome_cycle"
            return reader

    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "_read_plan", lambda path, digest: plan)
    monkeypatch.setitem(globals_, "open_private_root", lambda *args, **kwargs: Store())
    prefix_called = False

    def reject_tampered_terminal(
        observed_reader: Reader,
        observed_plan: BattleOutcomeExperimentPlan,
    ) -> dict[str, object]:
        assert observed_reader is reader
        assert observed_plan is plan
        raise SCRIPT["BattleOutcomeCycleInspectionError"]("tampered terminal")

    def forbidden_prefix(*args: object) -> dict[str, object]:
        nonlocal prefix_called
        prefix_called = True
        return {}

    monkeypatch.setitem(globals_, "_project_complete", reject_tampered_terminal)
    monkeypatch.setitem(globals_, "_project_retained_batch_prefix", forbidden_prefix)
    args = SimpleNamespace(
        private_root=Path("/private/artifacts"),
        plan=Path("/private/plan.json"),
        expected_plan_sha256=plan.plan_sha256,
        project_retained_batch_prefix=True,
    )

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleInspectionError"],
        match="tampered terminal",
    ):
        SCRIPT["_run"](args)

    assert prefix_called is False


def test_retained_prefix_projection_writer_is_private_exclusive_and_durable(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "retained-prefix.json"
    payload = b'{"schema":"test"}\n'

    resolved = SCRIPT["_private_new_projection"](destination)
    SCRIPT["_write_exclusive_projection"](resolved, payload)

    assert destination.read_bytes() == payload
    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(
        SCRIPT["BattleOutcomeCycleInspectionError"],
        match="already exists",
    ):
        SCRIPT["_private_new_projection"](destination)


def test_retained_prefix_projection_refuses_a_tracked_destination() -> None:
    destination = Path("docs") / "retained-prefix.json"

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleInspectionError"],
        match="must remain private",
    ):
        SCRIPT["_private_new_projection"](destination)


def test_complete_inspection_reconstructs_a_flat_train_terminal() -> None:
    reader = _complete_reader()
    terminal = dict(reader.streams["terminal"][0])
    terminal.update(
        {
            "status": "no_update",
            "cycle": None,
            "paired_development": None,
            "model_sha256": None,
            "claim": "insufficient_train_preference_signal",
            "candidate_advantage_observed": False,
            "root_claims_created": 1,
            "candidate_claims_created": 2,
            "measured_candidate_outcomes": 2,
            "activated_candidate_targets": 2,
            "deferred_unactivated_development_candidates": 2,
            "development_outcomes_opened": 0,
            "development_predictions_committed_before_outcomes": False,
            "model_fits": 0,
            "development_comparisons": 0,
        }
    )
    reader.streams = {
        "assignment": reader.streams["assignment"],
        "root_claims": (reader.streams["root_claims"][0],),
        "candidate_claims": reader.streams["candidate_claims"][:2],
        "candidate_outcomes": reader.streams["candidate_outcomes"][:2],
        "outcomes": (reader.streams["outcomes"][0],),
        "evaluation": (
            {
                "record_type": "battle_outcome_no_update",
                "status": terminal["status"],
                "claim": terminal["claim"],
                "train_learner_update_eligible": False,
                "development_root_claimed": False,
                "development_capture_metadata_opened": True,
                "development_outcomes_opened": 0,
                "activated_candidate_targets": 2,
                "deferred_unactivated_development_candidates": 2,
                "promotion_gate_passed": False,
                "model_written": False,
            },
        ),
        "terminal": (terminal,),
    }
    reader.summary.stream_records = tuple(  # type: ignore[misc]
        (name, len(records)) for name, records in sorted(reader.streams.items())
    )

    receipt = SCRIPT["_project_complete"](reader, _plan())

    assert receipt["status"] == "no_update"
    assert receipt["model_fits"] == 0
    assert receipt["development_outcomes_opened"] == 0
    assert receipt["deferred_unactivated_development_candidates"] == 2


def test_complete_inspection_rejects_a_missing_candidate_outcome() -> None:
    reader = _complete_reader()
    reader.streams["candidate_outcomes"] = reader.streams["candidate_outcomes"][:-1]
    reader.summary.stream_records = tuple(  # type: ignore[misc]
        (name, len(records)) for name, records in sorted(reader.streams.items())
    )

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleInspectionError"],
        match="terminal census",
    ):
        SCRIPT["_project_complete"](reader, _plan())


def test_complete_inspection_rejects_a_terminal_that_reverses_the_measured_winner() -> None:
    reader = _complete_reader()
    terminal = dict(reader.streams["terminal"][0])
    paired = dict(terminal["paired_development"])
    paired.update({"updated_wins": 0, "base_wins": 1})
    terminal["paired_development"] = paired
    reader.streams["terminal"] = (terminal,)

    with pytest.raises(
        SCRIPT["BattleOutcomeCycleInspectionError"],
        match="measured utilities",
    ):
        SCRIPT["_project_complete"](reader, _plan())


def test_failed_inspection_never_authorizes_a_counter_projection() -> None:
    reader = Reader(
        {
            "assignment": ({"plan_sha256": _plan().plan_sha256},),
            "candidate_claims": ({"candidate_index": 0},),
        },
        status="failed",
        reason_code="process_interrupted",
    )

    receipt = SCRIPT["_project_failure"](reader, _plan())

    assert receipt["status"] == "failed"
    assert receipt["reason_code"] == "process_interrupted"
    assert receipt["candidate_claims_retained"] == 1
    assert receipt["counter_projection_authorized"] is False
    assert receipt["model_fits"] == 0
