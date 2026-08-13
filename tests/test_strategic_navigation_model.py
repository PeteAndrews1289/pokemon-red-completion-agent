from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.strategic_navigation import NavigationOutcomeStatus
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationExample,
)
from pokemon_red_completion.strategic_navigation_model import (
    STRATEGIC_NAVIGATION_FEATURE_NAMES,
    StrategicNavigationMLP,
    StrategicNavigationModelError,
    canonical_strategic_navigation_model_sha256,
    evaluate_strategic_navigation_model,
    load_strategic_navigation_model,
    select_strategic_navigation_model,
    strategic_navigation_feature_matrix,
)


def _example(
    index: int,
    *,
    partition: str = "train",
    reverse: bool = False,
    target_remove_blocker: bool = True,
) -> StrategicNavigationExample:
    challenge = {
        "binding_index": 0,
        "semantic_tags": ["challenge", "story_progress"],
        "availability": "available",
        "route_cost": 10 + index,
        "route_steps": 9 + index,
        "map_transitions": 1,
        "field_actions": 0,
        "mode_changes": 0,
        "unavailability_reason": None,
    }
    blocker = {
        "binding_index": 1,
        "semantic_tags": ["remove_blocker", "story_progress"],
        "availability": "available",
        "route_cost": 80 + index,
        "route_steps": 75 + index,
        "map_transitions": 3,
        "field_actions": 1,
        "mode_changes": 0,
        "unavailability_reason": None,
    }
    candidates = [challenge, blocker]
    selected = int(target_remove_blocker)
    if reverse:
        candidates.reverse()
        candidates = [dict(row, binding_index=slot) for slot, row in enumerate(candidates)]
        selected = 1 - selected
    return StrategicNavigationExample(
        decision_id=f"decision-{partition}-{index}-{int(reverse)}",
        episode_id=f"episode-{partition}-{index}-{int(reverse)}",
        decision_index=0,
        root_lineage_id=f"root-{partition}-{index}-{int(reverse)}",
        partition=partition,
        actor="deterministic_teacher",
        policy_id="qualified-completion-order-v1",
        policy_input={
            "schema": "strategic-navigation-policy-input-v1",
            "semantic_need_tags": ["advance_story", "reach_next_challenge"],
            "origin_semantic_tags": ["overworld", "safe_hub"],
            "candidates": candidates,
        },
        selected_candidate_index=selected,
        outcome_status=NavigationOutcomeStatus.SUCCEEDED,
    )


def test_feature_schema_is_identity_free_and_candidate_relative() -> None:
    example = _example(0)
    features = strategic_navigation_feature_matrix(example)

    assert features.shape == (2, len(STRATEGIC_NAVIGATION_FEATURE_NAMES))
    assert np.all(np.isfinite(features))
    assert not any(
        token in name
        for name in STRATEGIC_NAVIGATION_FEATURE_NAMES
        for token in ("map_id", "coordinate", "destination_ref", "binding_index")
    )
    rank = STRATEGIC_NAVIGATION_FEATURE_NAMES.index(
        "candidate.route_cost.relative_rank"
    )
    assert tuple(features[:, rank]) == (0.0, 1.0)


def test_shared_scorer_is_permutation_equivariant_and_round_trips() -> None:
    training = tuple(_example(index, reverse=index % 2 == 1) for index in range(12))
    model = StrategicNavigationMLP.fit(training, hidden_units=4, epochs=300)
    forward = _example(20)
    reversed_example = _example(20, reverse=True)

    assert model.predict(forward) == 1
    assert model.predict(reversed_example) == 0
    assert model.probabilities(forward) == pytest.approx(
        model.probabilities(reversed_example)[::-1]
    )
    restored = StrategicNavigationMLP.from_dict(model.to_dict())
    assert canonical_strategic_navigation_model_sha256(restored) == (
        canonical_strategic_navigation_model_sha256(model)
    )
    assert not restored.weights1.flags.writeable


def test_model_beats_cheapest_route_on_synthetic_semantic_choices() -> None:
    training = tuple(_example(index, reverse=index % 2 == 1) for index in range(12))
    validation = tuple(
        _example(index + 100, partition="validation", reverse=index % 2 == 0)
        for index in range(6)
    )
    model = StrategicNavigationMLP.fit(training, hidden_units=4, epochs=300)
    metrics = evaluate_strategic_navigation_model(model, validation)

    assert metrics.accuracy == 1.0
    assert metrics.route_cost_baseline_accuracy == 0.0
    assert metrics.paired_wins_over_route_cost == 6
    assert metrics.paired_losses_to_route_cost == 0
    assert metrics.paired_two_sided_exact_p == 0.03125


def test_training_rejects_validation_examples() -> None:
    with pytest.raises(StrategicNavigationModelError, match="training-partition"):
        StrategicNavigationMLP.fit((_example(0, partition="validation"),))


def test_model_selection_rejects_test_partition_as_validation() -> None:
    training = tuple(_example(index) for index in range(4))
    sealed = (_example(10, partition="test"),)

    with pytest.raises(StrategicNavigationModelError, match="validation partition"):
        select_strategic_navigation_model(training, sealed)


def test_unobserved_portable_tags_have_zero_fitted_input_weights() -> None:
    model = StrategicNavigationMLP.fit(tuple(_example(index) for index in range(6)))
    unused = STRATEGIC_NAVIGATION_FEATURE_NAMES.index(
        "candidate.tag.complete_collection"
    )

    assert np.all(model.weights1[unused] == 0.0)


def test_model_file_authentication_rejects_tampering(tmp_path: Path) -> None:
    model = StrategicNavigationMLP.fit(tuple(_example(index) for index in range(6)))
    path = tmp_path / "strategic-model.json"
    path.write_text(json.dumps(model.to_dict(), sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    loaded = load_strategic_navigation_model(path, expected_sha256=digest)
    assert loaded.predict(_example(20)) == model.predict(_example(20))
    path.write_text(path.read_text() + " ")
    with pytest.raises(StrategicNavigationModelError, match="authentication"):
        load_strategic_navigation_model(path, expected_sha256=digest)


def test_model_record_rejects_feature_order_drift() -> None:
    model = StrategicNavigationMLP.fit(tuple(_example(index) for index in range(6)))
    payload = model.to_dict()
    names = payload["feature_names"]
    assert isinstance(names, list)
    names[0], names[1] = names[1], names[0]

    with pytest.raises(StrategicNavigationModelError, match="incompatible"):
        StrategicNavigationMLP.from_dict(payload)
