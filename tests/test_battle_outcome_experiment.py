from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_experiment import (
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentError,
    BattleOutcomeExperimentPlan,
    battle_outcome_distinct_hidden_embedding_count,
    battle_outcome_supported_hidden_embeddings,
    build_battle_outcome_experiment_plan_payload,
    parse_battle_outcome_experiment_plan,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _capture(
    partition: ScenarioPartition,
    marker: str,
) -> BattleOutcomeCaptureBinding:
    def digest(label: str) -> str:
        return hashlib.sha256(f"{marker}:{label}".encode()).hexdigest()

    assignment = digest("assignment")
    state = digest("source-state")
    envelope = digest("source-envelope")
    return BattleOutcomeCaptureBinding(
        partition=partition,
        capture_id=f"battle-{partition.value}-{marker}",
        manifest_sha256=digest("manifest"),
        state_sha256=digest("capture-state"),
        initial_observation_sha256=digest("observation"),
        source_commit="a" * 40,
        source_state_sha256=state,
        source_slot_id=f"red-goal-v1-{partition.value}-{marker}",
        source_assignment_id=assignment,
        source_context_id=digest("context"),
        source_envelope_sha256=envelope,
        root_lineage_id=f"red-goal-root-{assignment}",
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=state,
            envelope_sha256=envelope,
        ),
        menu_sha256=digest("menu"),
        supported_candidate_count=2,
        distinct_candidate_vector_count=2,
        hidden_embedding_sha256=digest("hidden-menu"),
        distinct_hidden_embedding_count=2,
        expected_map=11 if partition is ScenarioPartition.TRAIN else 197,
        expected_battle_state=1,
    )


def _plan() -> BattleOutcomeExperimentPlan:
    return BattleOutcomeExperimentPlan(
        experiment_id="red-battle-update-001",
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        runner_sha256="c" * 64,
        materializer_sha256="4" * 64,
        registry_source_commit="d" * 40,
        registry_source_bundle_sha256="5" * 64,
        registry_sha256="d" * 64,
        context_catalog_sha256="e" * 64,
        rom_sha256="f" * 64,
        runtime_identity_sha256="0" * 64,
        numpy_runtime_sha256="7" * 64,
        base_model_sha256="1" * 64,
        controller_timing_sha256="2" * 64,
        captures=(
            _capture(ScenarioPartition.TRAIN, "3"),
            _capture(ScenarioPartition.DEVELOPMENT, "6"),
        ),
    )


def _features() -> BattleFeatureBatch:
    low = [0.0] * len(FEATURE_NAMES)
    high = [0.0] * len(FEATURE_NAMES)
    low[0] = -0.5
    high[0] = 0.5
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=(tuple(low), tuple(high)),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
        slot_indices=(0, 1),
        schema_id=FEATURE_SCHEMA_ID,
    )


def _model(*, distinct: bool = True) -> MaskedMLPMoveRanker:
    weights = np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64)
    if distinct:
        weights[0, 0] = 1.0
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.ones(2, dtype=np.float64),
        output_bias=0.0,
    )


def test_battle_outcome_experiment_plan_round_trips_canonical_bytes() -> None:
    plan = _plan()
    payload = build_battle_outcome_experiment_plan_payload(plan)

    restored = parse_battle_outcome_experiment_plan(payload)

    assert restored == plan
    assert restored.plan_sha256 == plan.plan_sha256
    assert restored.train.partition is ScenarioPartition.TRAIN
    assert restored.development.partition is ScenarioPartition.DEVELOPMENT
    assert restored.numpy_runtime_sha256 == "7" * 64
    assert restored.plan_consumption_sha256 == plan.plan_consumption_sha256
    assert restored.train.logical_root_sha256 == restored.train.root_consumption_sha256
    assert restored.train.physical_root_sha256 == restored.train.state_sha256
    assert restored.public_dict()["private_path_fields"] == 0
    assert restored.public_dict()["protections"] == {
        "authority_promoted": False,
        "crystal_contexts_opened": 0,
        "development_influences_fit": False,
        "development_predictions_before_outcomes": True,
        "full_game_replays": 0,
        "materializer_derivation_claimed": False,
        "red_sealed_test_cases_opened": 0,
        "teacher_choice_targets": 0,
        "teacher_queries": 0,
    }


def test_hidden_menu_requires_the_exact_frozen_model_feature_schema() -> None:
    features = _features()
    model = MaskedMLPMoveRanker(
        feature_names=tuple(f"renamed-{index}" for index in range(len(FEATURE_NAMES))),
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64),
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.ones(2, dtype=np.float64),
        output_bias=0.0,
    )

    with pytest.raises(BattleOutcomeExperimentError, match="feature schema differs"):
        battle_outcome_supported_hidden_embeddings(model, features)


def test_hidden_menu_requires_two_numerically_distinct_representations() -> None:
    features = _features()

    assert battle_outcome_distinct_hidden_embedding_count(_model(), features) == 2
    assert (
        battle_outcome_distinct_hidden_embedding_count(
            _model(distinct=False),
            features,
        )
        == 1
    )


def test_battle_outcome_capture_rejects_a_forged_catalog_lineage() -> None:
    capture = _capture(ScenarioPartition.TRAIN, "3")

    with pytest.raises(BattleOutcomeExperimentError, match="catalog assignment"):
        replace(capture, root_lineage_id="red-goal-root-forged")


def test_battle_outcome_capture_rejects_a_forged_physical_root() -> None:
    capture = _capture(ScenarioPartition.TRAIN, "3")

    with pytest.raises(BattleOutcomeExperimentError, match="upstream bytes"):
        replace(capture, root_consumption_sha256="9" * 64)


def test_battle_outcome_capture_rejects_a_collapsed_root_pair() -> None:
    capture = _capture(ScenarioPartition.TRAIN, "3")

    with pytest.raises(BattleOutcomeExperimentError, match="identities collapse"):
        replace(capture, state_sha256=capture.root_consumption_sha256)


@pytest.mark.parametrize(
    ("attribute", "value", "error"),
    (
        ("supported_candidate_count", 1, "two to four supported"),
        ("supported_candidate_count", 5, "two to four supported"),
        ("distinct_candidate_vector_count", 1, "two distinct candidate"),
        ("distinct_hidden_embedding_count", 1, "two distinct hidden"),
    ),
)
def test_battle_outcome_capture_rejects_an_unlearnable_menu(
    attribute: str,
    value: int,
    error: str,
) -> None:
    capture = _capture(ScenarioPartition.TRAIN, "3")

    with pytest.raises(BattleOutcomeExperimentError, match=error):
        replace(capture, **{attribute: value})


@pytest.mark.parametrize(
    "attribute",
    (
        "capture_id",
        "manifest_sha256",
        "state_sha256",
        "initial_observation_sha256",
        "source_slot_id",
        "source_context_id",
    ),
)
def test_battle_outcome_plan_rejects_train_development_identity_overlap(
    attribute: str,
) -> None:
    plan = _plan()
    development = replace(
        plan.development,
        **{attribute: getattr(plan.train, attribute)},
    )

    with pytest.raises(BattleOutcomeExperimentError, match="repeat"):
        replace(plan, captures=(plan.train, development))


def test_battle_outcome_plan_rejects_partition_reordering() -> None:
    plan = _plan()

    with pytest.raises(BattleOutcomeExperimentError, match="ordered"):
        replace(plan, captures=(plan.development, plan.train))


def test_battle_outcome_plan_rejects_noncanonical_encoding() -> None:
    document = _plan().public_dict()
    payload = json.dumps(document, indent=2, sort_keys=True).encode("ascii")

    with pytest.raises(BattleOutcomeExperimentError, match="canonical"):
        parse_battle_outcome_experiment_plan(payload)


def test_battle_outcome_plan_rejects_mutated_protections() -> None:
    document = _plan().public_dict()
    protections = document["protections"]
    assert isinstance(protections, dict)
    protections["development_influences_fit"] = True
    payload = (
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )

    with pytest.raises(BattleOutcomeExperimentError, match="fields differ"):
        parse_battle_outcome_experiment_plan(payload)


def test_battle_outcome_plan_requires_the_numpy_runtime_identity() -> None:
    document = _plan().public_dict()
    del document["numpy_runtime_sha256"]
    payload = (
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )

    with pytest.raises(BattleOutcomeExperimentError, match="fields differ"):
        parse_battle_outcome_experiment_plan(payload)


def test_battle_outcome_plan_rejects_duplicate_json_keys() -> None:
    payload = build_battle_outcome_experiment_plan_payload(_plan())
    duplicated = payload.replace(
        b'"status":"prospective_unexecuted"',
        b'"status":"prospective_unexecuted","status":"prospective_unexecuted"',
        1,
    )

    with pytest.raises(BattleOutcomeExperimentError, match="canonical"):
        parse_battle_outcome_experiment_plan(duplicated)
