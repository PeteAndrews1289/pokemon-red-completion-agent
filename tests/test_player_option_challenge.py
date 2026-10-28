from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_option_value import _menu
from test_red_live_option_menu import _fishing_candidate, _model

from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionValueModel,
    option_feature_names,
    upgrade_option_value_model_for_challenge,
    upgrade_option_value_model_for_readiness,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.player_option_challenge import OptionChallenge


def preview(levels=(18, 21), own=(17,)):
    return OptionChallenge.from_levels(combat_levels=own, opponent_levels=levels)


def test_challenge_is_portable_normalized_and_not_an_outcome_label():
    p = preview()
    assert p.opponent_fraction == 2 / 6
    assert p.maximum_level_deficit == 0.04
    assert p.median_level_deficit == 0.025
    assert OptionChallenge.from_public(p.public_dict()) == p
    assert set(p.public_dict()) == {
        "schema",
        "combat_required",
        "opposition_known",
        "opponent_fraction",
        "maximum_level_deficit",
        "median_level_deficit",
    }


@pytest.mark.parametrize("levels", [(), (0,), (101,), (True,), [18], (18,) * 7])
def test_invalid_preview_cannot_enter_features(levels):
    with pytest.raises(ValueError):
        preview(levels)


def test_preview_and_noncombat_and_unknown_are_distinct():
    menu = _menu("private")
    row = menu.candidates[0]
    versions = [
        row,
        replace(row, challenge=OptionChallenge(False, False, 0.0, 0.0, 0.0)),
        replace(row, challenge=preview()),
    ]
    assert len({r.vector(menu.context, feature_version=6) for r in versions}) == 3
    for r in versions[1:]:
        with pytest.raises(ValueError, match="ignore challenge"):
            r.vector(menu.context, feature_version=5)


def test_equal_generic_costs_no_longer_alias_distinct_opposition():
    menu = _menu("private")
    a = replace(menu.candidates[0], challenge=preview())
    b = replace(a, challenge=preview((18, 15, 15, 17)))
    assert a.vector(menu.context, feature_version=6) != b.vector(menu.context, feature_version=6)
    assert (
        a.vector(menu.context, feature_version=6)[: len(option_feature_names(5))]
        == (b.vector(menu.context, feature_version=6)[: len(option_feature_names(5))])
    )


def test_v6_codec_preserves_challenge_but_never_private_identity():
    menu = _menu("private-gym-or-region")
    menu = replace(menu, candidates=tuple(replace(r, challenge=preview()) for r in menu.candidates))
    public = menu.policy_dict()
    assert menu.feature_version == 6
    assert "private-gym-or-region" not in str(public)
    assert restore_living_dex_policy_menu(public).policy_dict() == public
    public["candidates"][0]["challenge"]["winner"] = True
    with pytest.raises(ValueError):
        restore_living_dex_policy_menu(public)


def test_zero_bridge_preserves_predictions_and_does_not_claim_training():
    old = upgrade_option_value_model_for_readiness(_model())
    new = upgrade_option_value_model_for_challenge(old)
    assert new.feature_version == 6 and new.settled_examples == old.settled_examples
    assert new.train_dataset_sha256 == old.train_dataset_sha256
    assert not np.any(new.coefficients[len(option_feature_names(5)) :])
    menu = _menu("legacy")
    row = _fishing_candidate("legacy-row", travel=0.2)
    assert old.predict_candidate(menu.context, row) == new.predict_candidate(
        menu.context, replace(row, challenge=preview())
    )
    assert LivingDexOptionValueModel.from_dict(new.to_dict()).model_sha256 == new.model_sha256


def test_native_challenge_lesson_reconstructs_without_rewriting_legacy(tmp_path):
    from test_player_readiness import records

    from pokemon_red_completion.living_dex_option_value import curriculum_features
    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_native_curriculum import (
        CHALLENGE_CONTRACT,
        CHALLENGE_OUTCOME_SCHEMA,
        CHALLENGE_PLAN_SCHEMA,
        reconstruct_native_curriculum,
    )

    plan, result = records(tmp_path)
    old = reconstruct_native_curriculum(plan, result)
    plan.update(
        schema=CHALLENGE_PLAN_SCHEMA, contract=CHALLENGE_CONTRACT, challenge=preview().public_dict()
    )
    result.update(schema=CHALLENGE_OUTCOME_SCHEMA, declaration_sha256=canonical_sha256(plan))
    new = reconstruct_native_curriculum(plan, result)
    assert new.feature_version == 6
    assert new.features[: len(old.features)] == old.features
    assert any(new.features[len(old.features) :])
    assert new.outcome == old.outcome
    assert not any(curriculum_features(old, 6)[len(old.features) :])
    plan["challenge"]["winner"] = True
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError):
        reconstruct_native_curriculum(plan, result)


def test_registered_fitter_accepts_v6_lessons_with_compatible_prior(tmp_path, monkeypatch):
    import test_red_native_curriculum as original
    from test_player_readiness import records

    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_native_curriculum import (
        CHALLENGE_CONTRACT,
        CHALLENGE_OUTCOME_SCHEMA,
        CHALLENGE_PLAN_SCHEMA,
    )

    def factory(path):
        plan, result = records(path)
        plan.update(schema=CHALLENGE_PLAN_SCHEMA, contract=CHALLENGE_CONTRACT,
                    challenge=preview().public_dict())
        result.update(schema=CHALLENGE_OUTCOME_SCHEMA, declaration_sha256=canonical_sha256(plan))
        return plan, result, None

    monkeypatch.setattr(original, "records", factory)
    original.test_player_updates_authenticate_and_retain_native_lessons(tmp_path, monkeypatch)
