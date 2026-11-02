from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_option_value import _menu
from test_red_live_option_menu import _fishing_candidate, _model

from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind,
    LivingDexOptionValueModel,
    option_feature_names,
    upgrade_option_value_model_for_challenge,
    upgrade_option_value_model_for_preparation,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.player_option_preparation import OptionPreparation


def facts(**changes):
    return replace(OptionPreparation(17, 20, 3000, 1.0, 0.8, False, True, 20), **changes)


def candidate():
    row = _fishing_candidate("private-member", travel=0.2)
    return replace(row, features=replace(row.features, kind=LivingDexOptionKind.DEVELOP))


def test_portable_facts_distinguish_cost_evolution_and_member_intent():
    first = facts()
    assert OptionPreparation.from_public(first.public_dict()) == first
    assert len(first.vector()) == len(option_feature_names(7)) - len(option_feature_names(6))
    assert first.vector() != facts(evolution_level=None).vector()
    assert first.vector() != facts(remaining_xp=100).vector()
    assert first.vector() != facts(existing_combat_intent=True, undecided_intent=False).vector()
    assert all(0 <= value <= 1 for value in first.vector())


@pytest.mark.parametrize(
    "changes",
    [
        {"target_level": 17},
        {"current_level": True},
        {"remaining_xp": 0},
        {"hp_fraction": float("nan")},
        {"pp_fraction": 1.1},
        {"evolution_level": True},
        {"existing_combat_intent": True},
        {"undecided_intent": False},
    ],
)
def test_bad_facts_fail_closed(changes):
    with pytest.raises(ValueError):
        facts(**changes)


def test_preparation_requires_development_and_v7():
    with pytest.raises(ValueError):
        replace(_fishing_candidate("private", travel=0.2), preparation=facts())
    row = replace(candidate(), preparation=facts())
    with pytest.raises(ValueError, match="preparation"):
        row.vector(_menu("private").context, feature_version=6)


def test_codec_retains_semantics_not_member_identity():
    original = _menu("private")
    menu = replace(
        original, candidates=(replace(candidate(), preparation=facts()), original.candidates[1])
    )
    public = menu.policy_dict()
    assert menu.feature_version == 7
    assert "private" not in str(public)
    assert restore_living_dex_policy_menu(public).policy_dict() == public
    public["candidates"][0]["preparation"]["species"] = "answer-leak"
    with pytest.raises(ValueError):
        restore_living_dex_policy_menu(public)


def test_zero_bridge_preserves_predictions_without_claiming_learning():
    old = upgrade_option_value_model_for_challenge(_model())
    new = upgrade_option_value_model_for_preparation(old)
    assert new.feature_version == 7
    assert new.settled_examples == old.settled_examples
    assert new.train_dataset_sha256 == old.train_dataset_sha256
    assert not np.any(new.coefficients[len(option_feature_names(6)) :])
    row = candidate()
    context = _menu("private").context
    assert old.predict_candidate(context, row) == new.predict_candidate(
        context, replace(row, preparation=facts())
    )
    assert LivingDexOptionValueModel.from_dict(new.to_dict()).model_sha256 == new.model_sha256
