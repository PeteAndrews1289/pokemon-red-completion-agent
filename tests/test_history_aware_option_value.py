"""Controlled learner tests are not cartridge outcomes or training artifacts."""

import copy
import json
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_goal_policy import _model, _question
from test_living_dex_option_value import _example, _menu, _settled, _utility

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_search_memory import GoalSearchHistory
from pokemon_red_completion.living_dex_causal_journal import restore_living_dex_observed_arm_example
from pokemon_red_completion.living_dex_goal_policy import LivingDexGoalShadowPolicy
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    evaluate_living_dex_option_value,
    fit_living_dex_option_value,
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu


def _history_menu(history):
    menu = _menu()
    # Identical action semantics make history the only distinguishing input.
    first = replace(menu.candidates[0], search_history=history)
    second = replace(
        menu.candidates[0], binding_ref="another-source", search_history=GoalSearchHistory()
    )
    return replace(menu, candidates=(first, second))


def _rows(reverse=False):
    result = []
    for i in range(12):
        exhausted = i % 2 == 0
        history = GoalSearchHistory(3, 3, 900, 18000) if exhausted else GoalSearchHistory()
        # Deliberately reversing labels must reverse the learned effect: no rule penalty.
        success = exhausted if reverse else not exhausted
        row = _example(
            i,
            selected=0,
            outcome=_settled(
                success=success, completion=float(success), unlock=0, action_cost=float(not success)
            ),
        )
        result.append(replace(row, menu=_history_menu(history), behavior_probabilities=(0.5, 0.5)))
    return tuple(result)


def test_missing_tracked_zero_and_exhausted_are_three_distinct_inputs():
    unknown = _history_menu(None).candidate_vector(0)
    zero = _history_menu(GoalSearchHistory()).candidate_vector(0)
    exhausted = _history_menu(GoalSearchHistory(1, 1, 1000, 60000)).candidate_vector(0)
    assert unknown[-5:] == (0.0,) * 5
    assert zero[-5:] == (1.0, 0.0, 0.0, 0.0, 0.0)
    assert exhausted[-5:] == (1.0, 0.5, 0.5, 0.5, 0.5)
    assert unknown[:-5] == zero[:-5] == exhausted[:-5]


def test_v1_bytes_roundtrip_and_explicit_upgrade_preserves_predictions_not_fake_fits():
    prior = _model()
    serialized = copy.deepcopy(prior.to_dict())
    upgraded = upgrade_option_value_model_for_search_history(prior)
    assert LivingDexOptionValueModel.from_dict(serialized).to_dict() == serialized
    assert prior.to_dict() == serialized
    assert upgraded.settled_examples == prior.settled_examples
    assert upgraded.train_dataset_sha256 == prior.train_dataset_sha256
    assert upgraded.feature_version == 2 and upgraded.model_sha256 != prior.model_sha256
    assert np.count_nonzero(upgraded.coefficients[-5:]) == 0
    for candidate in _menu().candidates:
        expected = prior.predict_candidate(_menu().context, candidate).vector()
        for history in (None, GoalSearchHistory(), GoalSearchHistory(1, 1, 1000, 60000)):
            actual = upgraded.predict_candidate(
                _menu().context, replace(candidate, search_history=history)
            ).vector()
            assert actual == pytest.approx(expected, abs=1e-14)
    restored = LivingDexOptionValueModel.from_dict(upgraded.to_dict())
    assert restored.model_sha256 == upgraded.model_sha256


def test_history_effect_is_fitted_from_outcomes_and_reverses_with_evidence():
    menu = _history_menu(GoalSearchHistory(3, 3, 900, 18000))
    normal = fit_living_dex_option_value(_rows(), feature_version=2).model
    reversed_model = fit_living_dex_option_value(_rows(reverse=True), feature_version=2).model
    assert normal.select(menu, _utility()) == 1
    assert reversed_model.select(menu, _utility()) == 0
    assert normal.scores(menu, _utility())[1] - normal.scores(menu, _utility())[0] > 2
    # Unseen effort magnitude and private identities are not memorized row keys.
    changed = _history_menu(GoalSearchHistory(4, 4, 1200, 24000))
    changed = replace(
        changed,
        candidates=tuple(
            replace(c, binding_ref=f"renamed-{i}") for i, c in enumerate(changed.candidates)
        ),
    )
    assert normal.select(changed, _utility()) == 1
    assert (
        normal.select(replace(changed, candidates=tuple(reversed(changed.candidates))), _utility())
        == 0
    )


def test_mixed_corpus_keeps_legacy_rows_unchanged_and_retains_negative_outcomes():
    old = _example(
        500, selected=0, outcome=_settled(success=False, completion=0, unlock=0, action_cost=1)
    )
    original = old.public_dict()
    rows = (*_rows(), old)
    fitted = fit_living_dex_option_value(rows, feature_version=2)
    assert old.public_dict() == original
    assert "search_history" not in json.dumps(original)
    assert fitted.report.settled_examples == 13 and fitted.report.successful_examples == 6
    assert fitted.report.public_dict()["missing_history"] == "unknown_not_unattempted"
    assert (
        evaluate_living_dex_option_value(
            fitted.model, rows, expected_partition="train"
        ).settled_examples
        == 13
    )
    restored = restore_living_dex_observed_arm_example(rows[0].public_dict())
    assert restored.public_dict() == rows[0].public_dict()
    assert restored.menu.candidates[0].search_history == rows[0].menu.candidates[0].search_history


@pytest.mark.parametrize("version", [True, 0, 3, "2"])
def test_invalid_feature_versions_are_rejected(version):
    with pytest.raises(LivingDexOptionValueError):
        fit_living_dex_option_value(_rows(), feature_version=version)


def test_legacy_fit_and_prediction_cannot_silently_discard_history():
    with pytest.raises(LivingDexOptionValueError, match="ignore"):
        fit_living_dex_option_value(_rows())
    with pytest.raises(LivingDexOptionValueError, match="ignore"):
        _model().predict_candidate(_menu().context, _rows()[0].menu.candidates[0])
    with pytest.raises(LivingDexOptionValueError, match="partition"):
        fit_living_dex_option_value(
            (replace(_rows()[0], partition="development"), *_rows()[1:]), feature_version=2
        )


@pytest.mark.parametrize(
    "mutation", ["legacy_schema", "private_identity", "history_null", "feature_width"]
)
def test_codec_rejects_history_contract_mutations(mutation):
    value = _rows()[0].menu.policy_dict()
    if mutation == "legacy_schema":
        value["schema"] = "pokemon.core.living-dex-option-menu.v1"
    elif mutation == "private_identity":
        value["candidates"][0]["search_history"]["source_ref"] = "private"
    elif mutation == "history_null":
        value["candidates"][0]["search_history"] = None
    else:
        value["candidates"][0]["features"]["values"].append(0)
    with pytest.raises(ValueError):
        restore_living_dex_policy_menu(value)


def test_goal_policy_projects_history_without_forcing_a_different_action():
    model = upgrade_option_value_model_for_search_history(_model())
    question = _question()
    question = replace(
        question,
        opportunities=tuple(
            replace(row, search_history=GoalSearchHistory(10, 10, 5000, 50000))
            if row.kind is GoalKind.ACQUIRE_SPECIES
            else row
            for row in question.opportunities
        ),
    )
    policy = LivingDexGoalShadowPolicy(model)
    assert policy.select(question).kind is GoalKind.ACQUIRE_SPECIES
    assert policy.last_menu.feature_version == 2
    assert any(row.search_history is not None for row in policy.last_menu.candidates)
    assert all(
        row.search_history is None or row.search_history.exhausted == 10
        for row in policy.last_menu.candidates
    )
