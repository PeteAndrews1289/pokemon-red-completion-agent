"""Prospective recovery authority, never a relabel of old unsupported choices."""

import copy
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_goal_policy import _model, _question
from test_living_dex_option_value import _example, _menu, _settled, _utility
from test_red_player_training import _episode
from test_red_player_training_fit import _fit

from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalOpportunity
from pokemon_red_completion.living_dex_goal_policy import LivingDexGoalDecisionMode
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    fit_living_dex_option_value,
    option_feature_names,
    upgrade_option_value_model_for_optional_recovery,
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.living_dex_player_exploration import (
    DETERMINISTIC_POLICY_ID,
    RECOVERY_EXPLORATION_POLICY_ID,
    ExploringLivingDexGoalPolicy,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
from pokemon_red_completion.red_player_training_fit import bootstrap_red_player_optional_recovery


def _recovery_question():
    return replace(
        _question(),
        opportunities=(
            GoalOpportunity(
                "private-evolve", GoalKind.EVOLVE_SPECIES, GoalAvailability.AVAILABLE, 0.4, 0.1
            ),
            GoalOpportunity(
                "private-restore", GoalKind.RESTORE_TEAM, GoalAvailability.AVAILABLE, 0.2, 0.0
            ),
        ),
    )


def test_legacy_layout_is_frozen_and_recovery_is_append_only():
    assert option_feature_names(1)[:8] == (
        "kind.acquire",
        "kind.evolve",
        "kind.trade",
        "kind.develop",
        "kind.manage_storage",
        "kind.resupply",
        "kind.unlock_access",
        "kind.explore",
    )
    assert len(option_feature_names(1)) == 24
    assert len(option_feature_names(2)) == 29
    assert option_feature_names(3) == (
        *option_feature_names(2),
        "kind.restore",
        "party_pressure_x_restore",
    )
    menu = _menu()
    prior = upgrade_option_value_model_for_search_history(_model())
    original = copy.deepcopy(prior.to_dict())
    upgraded = upgrade_option_value_model_for_optional_recovery(prior)
    assert prior.to_dict() == original
    assert upgraded.feature_version == 3 and upgraded.settled_examples == prior.settled_examples
    assert upgraded.train_dataset_sha256 == prior.train_dataset_sha256
    np.testing.assert_array_equal(upgraded.coefficients[:-2], prior.coefficients)
    np.testing.assert_array_equal(upgraded.coefficients[-2:], 0)
    assert upgraded.feature_mean[-1] == 0 and upgraded.feature_scale[-1] == 1
    assert LivingDexOptionValueModel.from_dict(original).to_dict() == original
    assert (
        LivingDexOptionValueModel.from_dict(upgraded.to_dict()).model_sha256
        == upgraded.model_sha256
    )
    for candidate in menu.candidates:
        assert candidate.vector(menu.context, feature_version=3) == (
            *candidate.vector(menu.context, feature_version=2),
            0.0,
            0.0,
        )
        assert upgraded.predict_candidate(menu.context, candidate).vector() == pytest.approx(
            prior.predict_candidate(menu.context, candidate).vector(), abs=1e-14
        )
    assert upgrade_option_value_model_for_search_history(upgraded) is upgraded
    assert upgrade_option_value_model_for_optional_recovery(upgraded) is upgraded


def test_legacy_vector_matches_independent_nonuniform_golden_not_the_new_encoder():
    context = LivingDexOptionContext(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
    features = LivingDexOptionFeatures(
        LivingDexOptionKind.EVOLVE,
        completion_gain=0.11,
        dependency_unlock_gain=0.22,
        travel_effort=0.33,
        execution_effort=0.44,
        resource_cost=0.55,
        storage_cost=0.66,
        party_risk=0.77,
        irreversibility_risk=0.88,
        uncertainty=0.99,
    )
    expected = (
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0.11,
        0.22,
        0.33,
        0.44,
        0.55,
        0.66,
        0.77,
        0.88,
        0.99,
        0.011,
        0.044,
        0.099,
        0.22,
        0.33,
        0.462,
        0.693,
    )
    candidate = replace(_menu().candidates[0], features=features, search_history=None)
    assert candidate.vector(context, feature_version=1) == pytest.approx(expected)
    assert candidate.vector(context, feature_version=2) == pytest.approx((*expected, 0, 0, 0, 0, 0))
    assert candidate.vector(context, feature_version=3) == pytest.approx(
        (*expected, 0, 0, 0, 0, 0, 0, 0)
    )


@pytest.mark.parametrize("version", [1, 2])
def test_old_actor_stays_unsupported_and_old_scorer_rejects_recovery(version):
    model = _model()
    if version == 2:
        model = upgrade_option_value_model_for_search_history(model)
    old = ExploringLivingDexGoalPolicy(model, seed=17)
    old.select(_recovery_question())
    assert old.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_UNSUPPORTED
    assert not old.training_eligible and old.last_decision.scores == ()
    candidate = replace(
        _menu().candidates[0],
        features=replace(_menu().candidates[0].features, kind=LivingDexOptionKind.RESTORE),
    )
    with pytest.raises(LivingDexOptionValueError, match="recovery"):
        model.predict_candidate(_menu().context, candidate)


def test_optional_recovery_has_real_scores_full_support_and_exact_codec_replay():
    model = upgrade_option_value_model_for_optional_recovery(_model())
    policy = ExploringLivingDexGoalPolicy(model, seed=17)
    replay = ExploringLivingDexGoalPolicy(model, seed=17)
    choices = set()
    for _ in range(40):
        choice = policy.select(_recovery_question())
        choices.add(choice.kind)
        assert replay.select(_recovery_question()) == choice
        assert replay.selection_metadata() == policy.selection_metadata()
        assert policy.training_eligible and len(policy.last_decision.scores) == 2
        assert all(value >= 0.125 for value in policy.option_probabilities)
        assert sum(policy.option_probabilities) == pytest.approx(1)
        assert policy.selection_metadata()["behavior_policy_id"] == RECOVERY_EXPLORATION_POLICY_ID
    assert choices == {GoalKind.RESTORE_TEAM, GoalKind.EVOLVE_SPECIES}
    menu = policy.last_menu
    assert menu.feature_version == 3
    assert menu.candidate_vector(0)[-2:] == (0, 0)
    assert menu.candidate_vector(1)[-2:] == (1, menu.context.party_pressure)
    injured = replace(menu.context, party_pressure=0.8)
    well = replace(menu.context, party_pressure=0.1)
    assert menu.candidates[1].vector(injured, feature_version=3)[-2:] == (1, 0.8)
    assert menu.candidates[1].vector(well, feature_version=3)[-2:] == (1, 0.1)
    document = menu.policy_dict()
    assert restore_living_dex_policy_menu(document).policy_dict() == document
    assert "private-" not in str(document)
    for mutation in ("old_menu", "old_features", "nonzero_kind", "private"):
        bad = copy.deepcopy(document)
        if mutation == "old_menu":
            bad["schema"] = "pokemon.core.living-dex-option-menu.v2"
        elif mutation == "old_features":
            bad["candidates"][1]["features"]["schema"] = (
                "pokemon.core.living-dex-option-features.v1"
            )
        elif mutation == "nonzero_kind":
            bad["candidates"][1]["features"]["values"][0] = 1
        else:
            bad["candidates"][1]["map_id"] = 22
        with pytest.raises(ValueError):
            restore_living_dex_policy_menu(bad)


def test_mandatory_recovery_never_samples_or_changes_the_next_rng_choice():
    model = upgrade_option_value_model_for_optional_recovery(_model())
    policy = ExploringLivingDexGoalPolicy(model, seed=42)
    untouched = ExploringLivingDexGoalPolicy(model, seed=42)
    question = _recovery_question()
    emergency = replace(question, situation=replace(question.situation, safety_pressure=0.99))
    assert policy.select(emergency).kind is GoalKind.RESTORE_TEAM
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY
    assert not policy.training_eligible and policy.last_decision.scores == ()
    assert policy.selection_metadata()["behavior_policy_id"] == DETERMINISTIC_POLICY_ID
    assert policy.select(question) == untouched.select(question)


def test_old_nonexploratory_episode_is_still_excluded(tmp_path):
    dataset = _episode(tmp_path, acquire_only=True, plan_profile_sha="7" * 64)
    assert not dataset.examples and dataset.excluded_nonexploratory == 1


def test_controlled_outcomes_can_teach_pressure_sensitive_recovery_not_a_fixed_rule():
    # Synthetic falsifier, not cartridge evidence or a training artifact.
    base = _menu()
    candidate = replace(
        base.candidates[0],
        features=replace(
            base.candidates[0].features,
            completion_gain=0,
            dependency_unlock_gain=0,
            party_risk=0,
        ),
    )
    recovery = replace(
        candidate,
        binding_ref="recovery",
        features=replace(
            candidate.features,
            kind=LivingDexOptionKind.RESTORE,
        ),
    )

    def menu(pressure):
        return replace(
            base,
            context=replace(base.context, party_pressure=pressure),
            candidates=(candidate, recovery),
        )

    models = []
    for reverse in (False, True):
        rows = []
        for index in range(24):
            high = bool((index // 2) % 2)
            selected = index % 2
            success = (bool(selected) == high) != reverse
            row = _example(
                index,
                selected=selected,
                outcome=_settled(
                    success=success,
                    completion=0,
                    unlock=0,
                    action_cost=0.2,
                ),
            )
            rows.append(
                replace(row, menu=menu(0.9 if high else 0.1), behavior_probabilities=(0.5, 0.5))
            )
        models.append(fit_living_dex_option_value(rows, feature_version=3).model)
    assert models[0].select(menu(0.8), _utility()) == 1
    assert models[0].select(menu(0.2), _utility()) == 0
    assert models[1].select(menu(0.8), _utility()) == 0
    assert models[1].select(menu(0.2), _utility()) == 1
    flipped = replace(menu(0.8), candidates=tuple(reversed(menu(0.8).candidates)))
    assert models[0].select(flipped, _utility()) == 0


@pytest.mark.parametrize("history", [False, True])
def test_recovery_bootstrap_preserves_authenticated_corpus_without_fitting(
    tmp_path, monkeypatch, history
):
    store, _, _, _, result = _fit(tmp_path, monkeypatch, history=history)
    digest = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rp-model-{digest}", expected_kind="red_player_model")
    prior = load_player_goal_model_record_bytes(record.read_bytes(), expected_model_sha256=digest)
    before = record.read_bytes()
    report = bootstrap_red_player_optional_recovery(
        store, prior=prior, source_commit="e" * 40, source_bundle_sha256="f" * 64
    )
    assert report["fits"] == report["new_examples"] == report["controller_actions"] == 0
    assert report["recovery_effect_learned"] is False
    assert report["retained_examples"] == 3 and record.read_bytes() == before
    new_digest = report["model"]["model_sha256"]
    new_record = store.find_sealed_record(
        f"rp-model-{new_digest}", expected_kind="red_player_model"
    )
    upgraded = load_player_goal_model_record_bytes(
        new_record.read_bytes(), expected_model_sha256=new_digest
    )
    assert upgraded.model.feature_version == 3
    assert upgraded.corpus_sha256 == prior.corpus_sha256
    assert upgraded.retained_example_sha256 == prior.retained_example_sha256
    with pytest.raises(ValueError, match="legacy"):
        bootstrap_red_player_optional_recovery(
            store, prior=upgraded, source_commit="e" * 40, source_bundle_sha256="f" * 64
        )
