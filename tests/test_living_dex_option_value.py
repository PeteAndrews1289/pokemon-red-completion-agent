from __future__ import annotations

import json

import numpy as np
import pytest

from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexCensorReason,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUnavailableReason,
    LivingDexOptionUtility,
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
    evaluate_living_dex_option_value,
    fit_living_dex_option_value,
    uniform_behavior_probabilities,
)


def _context(*, variant: float = 0.0) -> LivingDexOptionContext:
    return LivingDexOptionContext(
        collection_pressure=0.8,
        dependency_pressure=0.7,
        access_pressure=0.4 + variant,
        resource_pressure=0.3,
        storage_pressure=0.5,
        party_pressure=0.4,
        knowledge_pressure=0.2,
    )


def _features(
    kind: LivingDexOptionKind,
    *,
    completion: float,
    unlock: float,
    effort: float,
    resource: float = 0.1,
    storage: float = 0.1,
    risk: float = 0.1,
    uncertainty: float = 0.1,
) -> LivingDexOptionFeatures:
    return LivingDexOptionFeatures(
        kind=kind,
        completion_gain=completion,
        dependency_unlock_gain=unlock,
        travel_effort=effort,
        execution_effort=effort,
        resource_cost=resource,
        storage_cost=storage,
        party_risk=risk,
        irreversibility_risk=0.0,
        uncertainty=uncertainty,
    )


def _menu(prefix: str = "private.red", *, variant: float = 0.0) -> LivingDexOptionMenu:
    return LivingDexOptionMenu(
        context=_context(variant=variant),
        candidates=(
            LivingDexOptionCandidate(
                f"{prefix}.species-and-map-a",
                _features(
                    LivingDexOptionKind.ACQUIRE,
                    completion=0.9,
                    unlock=0.7,
                    effort=0.6,
                ),
                LivingDexOptionAvailability.AVAILABLE,
            ),
            LivingDexOptionCandidate(
                f"{prefix}.species-and-item-b",
                _features(
                    LivingDexOptionKind.EVOLVE,
                    completion=0.8,
                    unlock=0.6,
                    effort=0.3,
                ),
                LivingDexOptionAvailability.AVAILABLE,
            ),
            LivingDexOptionCandidate(
                f"{prefix}.storage-c",
                _features(
                    LivingDexOptionKind.MANAGE_STORAGE,
                    completion=0.2,
                    unlock=0.5,
                    effort=0.1,
                    storage=0.0,
                ),
                LivingDexOptionAvailability.AVAILABLE,
            ),
            LivingDexOptionCandidate(
                f"{prefix}.illegal-trade-d",
                _features(
                    LivingDexOptionKind.TRADE,
                    completion=1.0,
                    unlock=1.0,
                    effort=0.0,
                ),
                LivingDexOptionAvailability.UNAVAILABLE,
                LivingDexOptionUnavailableReason.MISSING_CAPABILITY,
            ),
        ),
    )


def _settled(
    *,
    success: bool,
    completion: float,
    unlock: float,
    action_cost: float,
) -> LivingDexObservedOutcome:
    return LivingDexObservedOutcome(
        status=LivingDexOutcomeStatus.SETTLED,
        verified_success=success,
        completion_gain=completion,
        dependency_unlock_gain=unlock,
        action_cost=action_cost,
        frame_cost=action_cost,
        resource_cost=0.2,
        party_cost=0.1,
        storage_cost=0.1,
        irreversible_loss=0.0,
    )


def _example(
    index: int,
    *,
    selected: int,
    outcome: LivingDexObservedOutcome,
    partition: str = "train",
    variant: float = 0.0,
    behavior_probabilities: tuple[float, ...] | None = None,
) -> LivingDexObservedArmExample:
    menu = _menu(variant=variant)
    return LivingDexObservedArmExample(
        decision_sha256=f"{index + 1:064x}",
        partition=partition,
        menu=menu,
        selected_candidate_index=selected,
        behavior_probabilities=(
            uniform_behavior_probabilities(menu)
            if behavior_probabilities is None
            else behavior_probabilities
        ),
        outcome=outcome,
    )


def _utility() -> LivingDexOptionUtility:
    return LivingDexOptionUtility(
        success_weight=1.0,
        completion_gain_weight=4.0,
        dependency_unlock_weight=2.0,
        action_cost_weight=0.5,
        frame_cost_weight=0.25,
        resource_cost_weight=0.5,
        party_cost_weight=1.0,
        storage_cost_weight=0.5,
        irreversible_loss_weight=10.0,
    )


def test_policy_projection_is_invariant_to_title_species_and_binding_identity() -> None:
    red = _menu("pokemon.red.secret-species-map")
    crystal = _menu("pokemon.crystal.other-species-map")

    assert red.policy_dict() == crystal.policy_dict()
    assert red.policy_sha256 == crystal.policy_sha256
    policy = red.policy_dict()
    assert set(policy) == {"candidates", "context", "schema"}
    assert set(policy["context"]) == {  # type: ignore[arg-type]
        "access_pressure",
        "collection_pressure",
        "dependency_pressure",
        "knowledge_pressure",
        "party_pressure",
        "resource_pressure",
        "schema",
        "storage_pressure",
    }
    for candidate in policy["candidates"]:  # type: ignore[union-attr]
        assert set(candidate) == {"availability", "features", "unavailable_reason"}
        assert set(candidate["features"]) == {  # type: ignore[index]
            "feature_names",
            "kind",
            "normalization",
            "schema",
            "values",
        }
    encoded = json.dumps(policy, sort_keys=True)
    assert not any(
        token in encoded
        for token in (
            "pokemon.red",
            "secret-species",
            "map_id",
            "species_id",
            "binding_ref",
            "candidate_index",
        )
    )


def test_variable_menu_preserves_masked_rows_but_never_gives_them_probability() -> None:
    menu = _menu()

    assert len(menu.candidates) == 4
    assert menu.available_indices == (0, 1, 2)
    assert uniform_behavior_probabilities(menu) == pytest.approx(
        (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0, 0.0)
    )
    assert menu.policy_dict()["candidates"][3]["availability"] == "unavailable"  # type: ignore[index]


def test_feature_projection_has_multiway_variation_and_context_interactions() -> None:
    menu = _menu()
    varied = _menu(variant=0.1)

    vectors = {menu.candidate_vector(index) for index in menu.available_indices}

    assert len(vectors) == 3
    assert menu.candidate_vector(0) != varied.candidate_vector(0)
    assert len(menu.candidate_vector(0)) == len(LIVING_DEX_OPTION_FEATURE_NAMES)


def test_every_portable_option_kind_has_a_distinct_title_neutral_projection() -> None:
    menu = LivingDexOptionMenu(
        context=_context(),
        candidates=tuple(
            LivingDexOptionCandidate(
                f"private.binding.{kind.value}",
                _features(
                    kind,
                    completion=0.5,
                    unlock=0.4,
                    effort=0.3,
                    resource=0.2,
                    storage=0.2,
                    risk=0.2,
                    uncertainty=0.2,
                ),
                LivingDexOptionAvailability.AVAILABLE,
            )
            for kind in LivingDexOptionKind
        ),
    )

    vectors = tuple(menu.candidate_vector(index) for index in menu.available_indices)

    assert len(menu.available_indices) == len(LivingDexOptionKind) == 8
    assert len(set(vectors)) == 8
    for vector in vectors:
        assert sum(vector[: len(LivingDexOptionKind)]) == pytest.approx(1.0)


def test_behavior_policy_requires_full_support_and_hard_masking() -> None:
    menu = _menu()
    outcome = _settled(success=True, completion=1.0, unlock=1.0, action_cost=0.2)

    with pytest.raises(LivingDexOptionValueError, match="full support"):
        LivingDexObservedArmExample(
            "1" * 64,
            "train",
            menu,
            0,
            (0.5, 0.5, 0.0, 0.0),
            outcome,
        )
    with pytest.raises(LivingDexOptionValueError, match="masked"):
        LivingDexObservedArmExample(
            "2" * 64,
            "train",
            menu,
            0,
            (0.3, 0.3, 0.3, 0.1),
            outcome,
        )
    with pytest.raises(LivingDexOptionValueError, match="unavailable"):
        LivingDexObservedArmExample(
            "3" * 64,
            "train",
            menu,
            3,
            uniform_behavior_probabilities(menu),
            outcome,
        )


def test_two_failed_arms_remain_two_failures_without_counterfactual_preferences() -> None:
    rows = (
        _example(
            0,
            selected=0,
            outcome=_settled(
                success=False,
                completion=0.0,
                unlock=0.0,
                action_cost=0.8,
            ),
        ),
        _example(
            1,
            selected=1,
            outcome=_settled(
                success=False,
                completion=0.0,
                unlock=0.0,
                action_cost=0.7,
            ),
            variant=0.1,
        ),
    )

    fit = fit_living_dex_option_value(rows)

    assert fit.report.successful_examples == 0
    assert fit.report.public_dict()["counterfactual_targets"] == 0
    assert fit.report.public_dict()["unselected_action_targets"] == 0
    assert fit.report.public_dict()["outcome_balance_required"] is False
    assert fit.model.predict_candidate(
        rows[0].menu.context,
        rows[0].menu.candidates[0],
    ).verified_success == pytest.approx(0.0, abs=1e-12)
    encoded = json.dumps([row.public_dict() for row in rows], sort_keys=True)
    assert "preferred_action" not in encoded
    assert "other_action" not in encoded


def test_fit_accepts_arbitrary_outcome_mix_and_excludes_censored_evidence() -> None:
    censored = LivingDexObservedOutcome(
        LivingDexOutcomeStatus.CENSORED,
        censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
    )
    rows = (
        _example(
            0,
            selected=0,
            outcome=_settled(success=True, completion=0.8, unlock=0.5, action_cost=0.4),
        ),
        _example(
            1,
            selected=1,
            outcome=_settled(success=True, completion=0.7, unlock=0.7, action_cost=0.3),
            variant=0.1,
        ),
        _example(
            2,
            selected=2,
            outcome=_settled(success=True, completion=0.2, unlock=0.6, action_cost=0.1),
            variant=0.2,
        ),
        _example(3, selected=0, outcome=censored, variant=0.15),
    )

    fit = fit_living_dex_option_value(rows)

    assert fit.report.total_examples == 4
    assert fit.report.settled_examples == 3
    assert fit.report.censored_examples == 1
    assert fit.report.successful_examples == 3
    assert fit.model.settled_examples == 3
    assert fit.model.censored_examples == 1
    assert fit.report.weighted_mse_after <= fit.report.weighted_mse_before


def test_nonuniform_propensities_and_cap_change_the_fitted_selected_arm_mean() -> None:
    rows = (
        _example(
            20,
            selected=0,
            outcome=_settled(success=True, completion=1.0, unlock=0.0, action_cost=0.0),
            behavior_probabilities=(0.1, 0.45, 0.45, 0.0),
        ),
        _example(
            21,
            selected=0,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=1.0),
            behavior_probabilities=(0.8, 0.1, 0.1, 0.0),
        ),
        _example(
            22,
            selected=0,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=1.0),
            behavior_probabilities=(0.8, 0.1, 0.1, 0.0),
        ),
    )

    fit = fit_living_dex_option_value(rows)

    assert rows[0].importance_weight() == pytest.approx(4.0)
    assert rows[0].importance_weight(20.0) == pytest.approx(10.0)
    assert rows[1].importance_weight() == pytest.approx(1.25)
    assert fit.model.intercept[0] == pytest.approx(4.0 / (4.0 + 1.25 + 1.25))
    assert fit.model.intercept[0] != pytest.approx(1.0 / 3.0)


def test_feature_standardization_uses_the_same_capped_propensity_weights() -> None:
    rows = (
        _example(
            23,
            selected=0,
            outcome=_settled(success=True, completion=1.0, unlock=0.4, action_cost=0.1),
            variant=0.0,
            behavior_probabilities=(0.1, 0.45, 0.45, 0.0),
        ),
        _example(
            24,
            selected=0,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.9),
            variant=0.1,
            behavior_probabilities=(0.8, 0.1, 0.1, 0.0),
        ),
        _example(
            25,
            selected=0,
            outcome=_settled(success=True, completion=0.7, unlock=0.2, action_cost=0.3),
            variant=0.2,
            behavior_probabilities=(0.5, 0.25, 0.25, 0.0),
        ),
    )
    weights = np.asarray([4.0, 1.25, 2.0], dtype=np.float64)
    features = np.asarray([row.selected_vector for row in rows], dtype=np.float64)
    expected_mean = np.average(features, axis=0, weights=weights)
    expected_scale = np.sqrt(
        np.average((features - expected_mean) ** 2, axis=0, weights=weights)
    )
    expected_scale[expected_scale == 0.0] = 1.0

    model = fit_living_dex_option_value(rows).model

    np.testing.assert_allclose(model.feature_mean, expected_mean)
    np.testing.assert_allclose(model.feature_scale, expected_scale)


def test_development_evaluation_uses_logged_nonuniform_propensities() -> None:
    train = (
        _example(
            30,
            selected=0,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.0),
        ),
        _example(
            31,
            selected=0,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.0),
        ),
    )
    model = fit_living_dex_option_value(train).model
    development = (
        _example(
            32,
            selected=0,
            outcome=_settled(success=True, completion=0.0, unlock=0.0, action_cost=0.0),
            partition="development",
            behavior_probabilities=(0.1, 0.45, 0.45, 0.0),
        ),
        _example(
            33,
            selected=0,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.0),
            partition="development",
            behavior_probabilities=(0.8, 0.1, 0.1, 0.0),
        ),
    )

    evaluation = evaluate_living_dex_option_value(model, development)

    assert evaluation.per_outcome_weighted_mse[0] == pytest.approx(4.0 / 5.25)
    assert evaluation.per_outcome_weighted_mse[0] != pytest.approx(0.5)


def test_failure_can_retain_observed_partial_progress_without_relabelling() -> None:
    outcome = _settled(success=False, completion=0.25, unlock=0.1, action_cost=1.0)

    assert outcome.target_vector == pytest.approx(
        (0.0, 0.25, 0.1, 1.0, 1.0, 0.2, 0.1, 0.1, 0.0)
    )


def test_model_hard_masks_an_unavailable_candidate_even_with_high_predicted_value() -> None:
    width = len(LIVING_DEX_OPTION_FEATURE_NAMES)
    targets = len(LIVING_DEX_OPTION_OUTCOME_NAMES)
    coefficients = np.zeros((width, targets), dtype=np.float64)
    coefficients[
        LIVING_DEX_OPTION_FEATURE_NAMES.index("completion_gain"),
        LIVING_DEX_OPTION_OUTCOME_NAMES.index("completion_gain"),
    ] = 1.0
    model = LivingDexOptionValueModel(
        coefficients=coefficients,
        intercept=np.zeros(targets),
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        train_dataset_sha256="a" * 64,
        settled_examples=2,
        censored_examples=0,
        ridge=0.25,
        maximum_importance_weight=4.0,
    )
    menu = _menu()

    scores = model.scores(menu, _utility())

    assert scores[3] is None
    assert model.select(menu, _utility()) == 0


def test_model_round_trip_preserves_predictions_and_schema() -> None:
    rows = (
        _example(
            0,
            selected=0,
            outcome=_settled(success=True, completion=0.8, unlock=0.6, action_cost=0.4),
        ),
        _example(
            1,
            selected=1,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.9),
            variant=0.1,
        ),
        _example(
            2,
            selected=2,
            outcome=_settled(success=True, completion=0.2, unlock=0.5, action_cost=0.1),
            variant=0.2,
        ),
    )
    model = fit_living_dex_option_value(rows).model

    restored = LivingDexOptionValueModel.from_dict(model.to_dict())

    assert restored.to_dict() == model.to_dict()
    assert restored.model_sha256 == model.model_sha256
    assert restored.scores(rows[0].menu, _utility()) == pytest.approx(
        model.scores(rows[0].menu, _utility())
    )


def test_fit_is_invariant_to_input_row_order() -> None:
    rows = (
        _example(
            0,
            selected=0,
            outcome=_settled(success=True, completion=0.8, unlock=0.6, action_cost=0.4),
        ),
        _example(
            1,
            selected=1,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.9),
            variant=0.1,
        ),
        _example(
            2,
            selected=2,
            outcome=_settled(success=True, completion=0.2, unlock=0.5, action_cost=0.1),
            variant=0.2,
        ),
    )

    forward = fit_living_dex_option_value(rows)
    reverse = fit_living_dex_option_value(tuple(reversed(rows)))

    assert forward.model.to_dict() == reverse.model.to_dict()
    assert forward.report.public_dict() == reverse.report.public_dict()


def test_development_evaluation_uses_only_settled_selected_arms() -> None:
    train = (
        _example(
            0,
            selected=0,
            outcome=_settled(success=True, completion=0.8, unlock=0.6, action_cost=0.4),
        ),
        _example(
            1,
            selected=1,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.9),
            variant=0.1,
        ),
    )
    model = fit_living_dex_option_value(train).model
    development = (
        _example(
            2,
            selected=2,
            outcome=_settled(success=True, completion=0.2, unlock=0.5, action_cost=0.1),
            partition="development",
            variant=0.2,
        ),
        _example(
            3,
            selected=0,
            outcome=LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
            ),
            partition="development",
            variant=0.15,
        ),
    )

    evaluation = evaluate_living_dex_option_value(model, development)

    assert evaluation.total_examples == 2
    assert evaluation.settled_examples == 1
    assert evaluation.censored_examples == 1
    assert evaluation.public_dict()["counterfactual_targets"] == 0
    assert evaluation.public_dict()["unselected_action_targets"] == 0


def test_censored_outcome_cannot_smuggle_a_target() -> None:
    with pytest.raises(LivingDexOptionValueError, match="cannot become a target"):
        LivingDexObservedOutcome(
            LivingDexOutcomeStatus.CENSORED,
            verified_success=False,
            completion_gain=0.0,
            dependency_unlock_gain=0.0,
            action_cost=1.0,
            frame_cost=1.0,
            resource_cost=0.0,
            party_cost=0.0,
            storage_cost=0.0,
            irreversible_loss=0.0,
            censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
        )


def test_model_document_rejects_feature_schema_drift() -> None:
    rows = (
        _example(
            0,
            selected=0,
            outcome=_settled(success=True, completion=0.8, unlock=0.6, action_cost=0.4),
        ),
        _example(
            1,
            selected=1,
            outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.9),
            variant=0.1,
        ),
    )
    document = fit_living_dex_option_value(rows).model.to_dict()
    document["feature_names"] = [*LIVING_DEX_OPTION_FEATURE_NAMES[:-1], "title_id"]

    with pytest.raises(LivingDexOptionValueError, match="schema"):
        LivingDexOptionValueModel.from_dict(document)


def test_fit_rejects_partition_leakage_and_duplicate_decisions() -> None:
    first = _example(
        0,
        selected=0,
        outcome=_settled(success=True, completion=0.8, unlock=0.6, action_cost=0.4),
    )
    development = _example(
        1,
        selected=1,
        outcome=_settled(success=False, completion=0.0, unlock=0.0, action_cost=0.9),
        partition="development",
        variant=0.1,
    )

    with pytest.raises(LivingDexOptionValueError, match="partition"):
        fit_living_dex_option_value((first, development))
    with pytest.raises(LivingDexOptionValueError, match="repeat"):
        fit_living_dex_option_value((first, first))
