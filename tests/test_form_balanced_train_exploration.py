"""TRAIN-only form-balanced exploration: exact propensities, unchanged defaults."""

from __future__ import annotations

import math
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _mixed, _model

import pokemon_red_completion.red_live_option_menu as menu_module
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.red_live_option_menu import (
    RED_LIVE_FORM_BALANCED_OPTION_POLICY,
    RedLiveOptionMenuError,
    RedLiveOptionSelectionMode,
    public_option_form,
    select_red_live_option,
)


def _features(kind):
    return LivingDexOptionFeatures(
        kind=kind,
        completion_gain=0.0,
        dependency_unlock_gain=0.5,
        travel_effort=0.0,
        execution_effort=0.1,
        resource_cost=0.0,
        storage_cost=0.0,
        party_risk=0.2,
        irreversibility_risk=0.0,
        uncertainty=0.0,
    )


def _candidate(kind, **extra):
    return LivingDexOptionCandidate(
        binding_ref="row",
        features=_features(kind),
        availability=LivingDexOptionAvailability.AVAILABLE,
        **extra,
    )


def test_public_form_uses_only_policy_visible_story_scope():
    movement = _candidate(
        LivingDexOptionKind.UNLOCK_ACCESS, story_unit=OptionStoryUnit("movement", True)
    )
    fight = _candidate(
        LivingDexOptionKind.UNLOCK_ACCESS,
        challenge=OptionChallenge(True, True, 1 / 6, -0.04, -0.04),
    )
    plain = _candidate(LivingDexOptionKind.UNLOCK_ACCESS)
    other = _candidate(LivingDexOptionKind.RESUPPLY)
    assert public_option_form(movement) == "story_unit_movement"
    assert public_option_form(fight) == "combat_obstruction"
    assert public_option_form(plain) == "other_access"
    assert public_option_form(other) is None


def _kind_balanced_expected(options, scores, mix):
    available = options.menu.available_indices
    kinds = [options.menu.candidates[i].features.kind for i in available]
    counts = {k: kinds.count(k) for k in set(kinds)}
    peak = max(scores[i] for i in available)
    weights = [math.exp(scores[i] - peak) / counts[k] for i, k in zip(available, kinds)]
    total = sum(weights)
    result = [0.0] * len(options.bindings)
    for (i, k), w in zip(zip(available, kinds), weights):
        result[i] = (1 - mix) * w / total + mix / (len(counts) * counts[k])
    return result


def test_default_sampler_is_byte_identical_to_the_kind_balanced_contract():
    options = _mixed([])
    choice = select_red_live_option(_model(), options, seed=5, allow_earning_exploration=True)
    assert choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    expected = _kind_balanced_expected(options, choice.scores, 0.25)
    assert choice.form_balanced_exploration is False
    assert choice.kind_balanced_exploration is True
    assert all(math.isclose(a, b, abs_tol=1e-15) for a, b in zip(choice.probabilities, expected))
    assert choice.public_dict()["policy_id"] == "red-live-kind-balanced-option-v1"


def test_form_balanced_splits_a_crowded_kind_into_visible_forms(monkeypatch):
    options = _mixed([])
    acquire = [
        i
        for i in options.menu.available_indices
        if options.menu.candidates[i].features.kind is LivingDexOptionKind.ACQUIRE
    ]
    assert len(acquire) == 2
    # Two same-kind variants with different public forms (a stand-in for many
    # movement steps beside one obstruction fight): each form is its own group.
    rare = options.menu.candidates[acquire[1]]
    monkeypatch.setattr(
        menu_module, "public_option_form", lambda c: "rare" if c is rare else "common"
    )
    common = dict(seed=5, exploration_mix=1.0, allow_earning_exploration=True)
    kind = select_red_live_option(_model(), options, **common)
    form = select_red_live_option(_model(), options, form_balanced_exploration=True, **common)
    groups_kind = len({options.menu.candidates[i].features.kind for i in options.menu.available_indices})
    assert math.isclose(kind.probabilities[acquire[1]], 1 / (groups_kind * 2))
    assert math.isclose(form.probabilities[acquire[1]], 1 / (groups_kind + 1))
    assert math.isclose(sum(form.probabilities), 1.0, abs_tol=1e-12)
    assert all(form.probabilities[i] > 0 for i in options.menu.available_indices)
    assert form.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert form.scores == kind.scores
    public = form.public_dict()
    assert public["policy_id"] == RED_LIVE_FORM_BALANCED_OPTION_POLICY
    assert public["sampling_rule"] == "mean_exponential_weight_per_public_option_form"


def test_form_balanced_without_story_variants_matches_kind_balanced():
    options = _mixed([])
    common = dict(seed=9, exploration_mix=0.6, allow_earning_exploration=True)
    a = select_red_live_option(_model(), options, **common)
    b = select_red_live_option(_model(), options, form_balanced_exploration=True, **common)
    assert a.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert a.probabilities == b.probabilities and a.selected_candidate_index == b.selected_candidate_index


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(greedy_selection=True),
        dict(kind_balanced_exploration=False),
    ],
)
def test_form_balanced_scope_is_exploration_only(kwargs):
    with pytest.raises(RedLiveOptionMenuError, match="form-balanced"):
        select_red_live_option(
            _model(), _mixed([]), seed=1, form_balanced_exploration=True, **kwargs
        )


@pytest.mark.parametrize("value", [None, 1, "yes"])
def test_form_balanced_requires_boolean(value):
    with pytest.raises(RedLiveOptionMenuError, match="form-balanced"):
        select_red_live_option(_model(), _mixed([]), seed=1, form_balanced_exploration=value)


@pytest.mark.parametrize("partition", ["development", "benchmark", None])
def test_runner_refuses_form_balanced_outside_train(tmp_path, partition):
    from pokemon_red_completion.red_autonomous_player import run_autonomous_options

    with pytest.raises(ValueError, match="TRAIN-only"):
        run_autonomous_options(
            model=N(feature_version=16),
            output=tmp_path / "x",
            snapshot=lambda: None,
            observe=lambda: None,
            seed=1,
            provenance=dict(source={} if partition is None else dict(partition=partition)),
            continuous_player=True,
            exploration_mix=0.75,
            train_form_balanced_exploration=True,
        )


def test_runner_refuses_form_balanced_without_continuous_scope(tmp_path):
    from pokemon_red_completion.red_autonomous_player import run_autonomous_options

    with pytest.raises(ValueError, match="TRAIN-only"):
        run_autonomous_options(
            model=N(feature_version=16),
            output=tmp_path / "x",
            snapshot=lambda: None,
            observe=lambda: None,
            seed=1,
            provenance=dict(source=dict(partition="train")),
            train_form_balanced_exploration=True,
        )


def test_custom_mix_still_needs_development_without_the_train_opt_in(tmp_path):
    from pokemon_red_completion.red_autonomous_player import run_autonomous_options

    with pytest.raises(ValueError, match="custom exploration"):
        run_autonomous_options(
            model=N(feature_version=16),
            output=tmp_path / "x",
            snapshot=lambda: None,
            observe=lambda: None,
            seed=1,
            provenance=dict(source=dict(partition="train")),
            continuous_player=True,
            exploration_mix=0.75,
        )
