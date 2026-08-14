from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.strategic_navigation import NavigationOutcomeStatus
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationExample,
    StrategicNavigationInferenceInput,
)
from pokemon_red_completion.strategic_navigation_model import (
    STRATEGIC_NAVIGATION_FEATURE_NAMES,
    StrategicNavigationLinear,
    StrategicNavigationMLP,
    StrategicNavigationModelError,
    _select_one_standard_error_feature_set,
    canonical_strategic_navigation_model_sha256,
    evaluate_strategic_navigation_model,
    load_strategic_navigation_model,
    select_strategic_navigation_linear_model,
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


def test_frozen_scorer_accepts_an_unlabeled_policy_question() -> None:
    training = tuple(_example(index, reverse=index % 2 == 1) for index in range(12))
    model = StrategicNavigationLinear.fit(
        training,
        enabled_feature_names=(
            "candidate.route_cost.relative_rank",
            "candidate.route_steps.relative_rank",
            "candidate.map_transitions.relative_rank",
            "candidate.field_actions.relative_rank",
            "candidate.mode_changes.relative_rank",
        ),
        feature_set_id="relative_route",
        epochs=300,
    )
    labeled = _example(20)
    unlabeled = StrategicNavigationInferenceInput(labeled.policy_input)

    assert not hasattr(unlabeled, "selected_candidate_index")
    assert not hasattr(unlabeled, "outcome_status")
    assert unlabeled.ordered_policy_input_sha256 == labeled.ordered_policy_input_sha256
    assert model.probabilities(unlabeled) == pytest.approx(
        model.probabilities(labeled)
    )
    assert model.predict(unlabeled) == model.predict(labeled)


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
    assert metrics.candidate_count_results == ((2, 6, 6),)
    assert metrics.public_dict()["candidate_count_results"] == {
        "2": {"correct": 6, "examples": 6, "accuracy": 1.0}
    }


def test_training_rejects_validation_examples() -> None:
    with pytest.raises(StrategicNavigationModelError, match="training-partition"):
        StrategicNavigationMLP.fit((_example(0, partition="validation"),))
    with pytest.raises(StrategicNavigationModelError, match="training-partition"):
        StrategicNavigationLinear.fit(
            (_example(0, partition="validation"),),
            enabled_feature_names=("candidate.route_cost.relative_rank",),
            feature_set_id="route_cost_rank",
        )


def test_linear_model_is_permutation_equivariant_and_round_trips() -> None:
    training = tuple(_example(index, reverse=index % 2 == 1) for index in range(12))
    enabled = tuple(
        f"candidate.{metric}.relative_rank"
        for metric in (
            "route_cost",
            "route_steps",
            "map_transitions",
            "field_actions",
            "mode_changes",
        )
    )
    model = StrategicNavigationLinear.fit(
        training,
        enabled_feature_names=enabled,
        feature_set_id="relative_route",
        epochs=300,
    )
    forward = _example(20)
    reversed_example = _example(20, reverse=True)

    assert model.predict(forward) == 1
    assert model.predict(reversed_example) == 0
    assert model.probabilities(forward) == pytest.approx(
        model.probabilities(reversed_example)[::-1]
    )
    restored = StrategicNavigationLinear.from_dict(model.to_dict())
    assert canonical_strategic_navigation_model_sha256(restored) == (
        canonical_strategic_navigation_model_sha256(model)
    )
    assert restored.parameter_count == 5
    assert not restored.weights.flags.writeable


@pytest.mark.parametrize("partition", ("validation", "test"))
def test_linear_selection_rejects_non_training_partitions(partition: str) -> None:
    non_training = tuple(_example(index, partition=partition) for index in range(4))

    with pytest.raises(StrategicNavigationModelError, match="training-partition"):
        select_strategic_navigation_linear_model(non_training, epochs=5)


def test_linear_selection_rejects_validation_before_any_fold_is_fitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validation = tuple(_example(index, partition="validation") for index in range(4))

    def forbidden_fit(*args: object, **kwargs: object) -> StrategicNavigationLinear:
        raise AssertionError("a non-training row reached linear fitting")

    monkeypatch.setattr(StrategicNavigationLinear, "fit", forbidden_fit)

    with pytest.raises(StrategicNavigationModelError, match="training-partition"):
        select_strategic_navigation_linear_model(validation, epochs=5)


def test_linear_selection_uses_training_only_one_standard_error_rule() -> None:
    training = tuple(_example(index, reverse=index % 2 == 1) for index in range(6))
    route_cost = ("candidate.route_cost.relative_rank",)
    relative_route = tuple(
        f"candidate.{metric}.relative_rank"
        for metric in (
            "route_cost",
            "route_steps",
            "map_transitions",
            "field_actions",
            "mode_changes",
        )
    )

    model, selection = select_strategic_navigation_linear_model(
        training,
        feature_sets=(
            ("route_cost_rank", route_cost),
            ("relative_route", relative_route),
        ),
        l2_values=(0.01,),
        epochs=100,
    )

    assert model.feature_set_id == "route_cost_rank"
    assert model.parameter_count == 1
    assert selection["selection_data"] == "train_only"
    assert selection["validation_used_for_selection"] is False
    assert selection["sealed_test_used_for_selection"] is False


def test_one_standard_error_rule_prefers_five_features_within_best_uncertainty() -> None:
    def trial(
        feature_set_id: str,
        *,
        parameters: int,
        correct: int,
        cross_entropy: float,
    ) -> dict[str, object]:
        return {
            "feature_set_id": feature_set_id,
            "feature_names": list(STRATEGIC_NAVIGATION_FEATURE_NAMES[:parameters]),
            "parameter_count": parameters,
            "l2": 0.1,
            "leave_one_out": {
                "examples": 24,
                "correct": correct,
                "accuracy": correct / 24,
                "cross_entropy": cross_entropy,
            },
        }

    small = trial("relative_route", parameters=5, correct=16, cross_entropy=0.85)
    large = trial("all_training_active", parameters=24, correct=17, cross_entropy=1.5)

    selected, eligible, best, error, threshold = (
        _select_one_standard_error_feature_set((small, large), example_count=24)
    )

    assert selected is small
    assert eligible == (small, large)
    assert best == pytest.approx(17 / 24)
    assert error == pytest.approx(0.092780476)
    assert threshold == pytest.approx(0.6155528527)


def test_linear_selection_really_leaves_each_training_example_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    training = tuple(_example(index, reverse=index % 2 == 1) for index in range(4))
    original_fit = StrategicNavigationLinear.fit
    fitted_decision_ids: list[tuple[str, ...]] = []

    def recording_fit(examples: object, **kwargs: object) -> StrategicNavigationLinear:
        rows = tuple(examples)  # type: ignore[arg-type]
        fitted_decision_ids.append(tuple(row.decision_id for row in rows))
        return original_fit(rows, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(StrategicNavigationLinear, "fit", staticmethod(recording_fit))

    select_strategic_navigation_linear_model(
        training,
        feature_sets=(("route_cost_rank", ("candidate.route_cost.relative_rank",)),),
        l2_values=(0.01,),
        epochs=5,
    )

    expected = {row.decision_id for row in training}
    assert len(fitted_decision_ids) == 5
    assert all(len(fold) == 3 for fold in fitted_decision_ids[:4])
    assert {
        next(iter(expected.difference(fold))) for fold in fitted_decision_ids[:4]
    } == expected
    assert set(fitted_decision_ids[-1]) == expected


def test_linear_record_rejects_nonzero_disabled_weight() -> None:
    model = StrategicNavigationLinear.fit(
        tuple(_example(index) for index in range(6)),
        enabled_feature_names=("candidate.route_cost.relative_rank",),
        feature_set_id="route_cost_rank",
        epochs=30,
    )
    payload = model.to_dict()
    weights = payload["weights"]
    assert isinstance(weights, list)
    disabled = STRATEGIC_NAVIGATION_FEATURE_NAMES.index(
        "candidate.route_steps.relative_rank"
    )
    weights[disabled] = 1.0

    with pytest.raises(StrategicNavigationModelError, match="disabled"):
        StrategicNavigationLinear.from_dict(payload)


def test_linear_model_file_round_trip_uses_authenticated_dispatch(
    tmp_path: Path,
) -> None:
    model = StrategicNavigationLinear.fit(
        tuple(_example(index) for index in range(6)),
        enabled_feature_names=("candidate.route_cost.relative_rank",),
        feature_set_id="route_cost_rank",
        epochs=30,
    )
    path = tmp_path / "strategic-linear-model.json"
    path.write_text(json.dumps(model.to_dict(), sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    loaded = load_strategic_navigation_model(path, expected_sha256=digest)

    assert isinstance(loaded, StrategicNavigationLinear)
    assert loaded.predict(_example(20)) == model.predict(_example(20))


def test_model_loader_rejects_unknown_authenticated_model_identity(
    tmp_path: Path,
) -> None:
    model = StrategicNavigationLinear.fit(
        tuple(_example(index) for index in range(6)),
        enabled_feature_names=("candidate.route_cost.relative_rank",),
        feature_set_id="route_cost_rank",
        epochs=30,
    )
    payload = model.to_dict()
    payload["model_id"] = "pokemon.core.strategic-navigation.unknown.v1"
    path = tmp_path / "unknown-strategic-model.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(StrategicNavigationModelError, match="identity"):
        load_strategic_navigation_model(path, expected_sha256=digest)


def test_linear_record_rejects_false_as_one_parameter() -> None:
    model = StrategicNavigationLinear.fit(
        tuple(_example(index) for index in range(6)),
        enabled_feature_names=("candidate.route_cost.relative_rank",),
        feature_set_id="route_cost_rank",
        epochs=30,
    )
    payload = model.to_dict()
    payload["parameter_count"] = True

    with pytest.raises(StrategicNavigationModelError, match="incompatible"):
        StrategicNavigationLinear.from_dict(payload)


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
