import copy
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_option_value import _example, _settled
from test_party_preparation import team
from test_player_decision_probe import question
from test_post_battle_strategy import menu
from test_red_player_lesson import player_records

from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionMenu,
    LivingDexOptionValueModel,
    curriculum_features,
    fit_living_dex_option_value,
    living_dex_option_context_from_goal_situation,
    option_feature_names,
    upgrade_option_value_model_for_readiness,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.player_decision_probe import (
    compare_player_decision_pair,
    probe_player_decision,
)
from pokemon_red_completion.player_readiness import PlayerReadiness
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_curriculum import (
    READINESS_CONTRACT,
    READINESS_OUTCOME_SCHEMA,
    READINESS_PLAN_SCHEMA,
    reconstruct_native_curriculum,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def test_no_history_keeps_current_facts_without_inventing_a_battle():
    from pokemon_red_completion.player_readiness import CONTEXT_NAMES, NO_HISTORY_SCHEMA

    r = PlayerReadiness.without_battle_history(team(5, 9), (1.0,) * 5)
    values = dict(zip(CONTEXT_NAMES, r.values, strict=False))
    assert all(value == 0 for name, value in values.items() if name.startswith("recent."))
    assert values["current.hp_fraction"] == 1
    assert values["current.combat_level_spread"] == 0.04
    assert values["current.median_combat_level_gap"] == 0
    assert r.public_dict()["schema"] == NO_HISTORY_SCHEMA
    assert PlayerReadiness.from_public(r.public_dict()) == r
    doc = r.public_dict()
    doc["values"][0] = 1
    with pytest.raises(ValueError):
        PlayerReadiness.from_public(doc)
    with pytest.raises(ValueError):
        PlayerReadiness(r.values)


def test_no_history_flows_through_real_policy_projection_without_dimension_change():
    r = PlayerReadiness.without_battle_history(team(5), (1.0,) * 5)
    q = question()
    candidate = project_living_dex_goal_candidate(
        q, 0, feature_version=5, binding_ref="private", readiness=r,
    )
    context = living_dex_option_context_from_goal_situation(
        q.situation, economy_snapshot=EconomySnapshot(1000, ()), target_cash=3000,
    )
    assert len(candidate.vector(context, feature_version=5)) == len(option_feature_names(5))


def readiness(*, level=40, budget=1.0):
    m = menu()
    context = replace(m.context, current_combat_levels=(level, level))
    return PlayerReadiness.from_context(context, (budget,) * 5)


def records(path, *, level=40, success=True):
    plan, result = player_records(path)
    plan.update(
        schema=READINESS_PLAN_SCHEMA,
        contract=READINESS_CONTRACT,
        readiness=readiness(level=level).public_dict(),
    )
    result.update(schema=READINESS_OUTCOME_SCHEMA, declaration_sha256=canonical_sha256(plan))
    if not success:
        result.update(
            succeeded=False,
            after=copy.deepcopy(plan["before"]),
            player_lesson=copy.deepcopy(plan["player_lesson"]["before"]),
        )
    return plan, result


def test_existing_context_values_and_unknown_history_are_distinct():
    m = menu()
    r = PlayerReadiness.from_context(m.context, m.remaining_budget)
    assert r.values == (*m.context.features().values(), *m.remaining_budget)
    assert PlayerReadiness.from_public(r.public_dict()) == r
    q = question()
    context = living_dex_option_context_from_goal_situation(q.situation)
    old = project_living_dex_goal_candidate(q, 0, feature_version=3, binding_ref="private")
    new = replace(old, readiness=r)
    assert old.vector(context, feature_version=5)[: len(option_feature_names(3))] == old.vector(
        context, feature_version=3
    )
    assert any(new.vector(context, feature_version=5)[len(option_feature_names(4)) :])
    assert not any(old.vector(context, feature_version=5)[len(option_feature_names(4)) :])
    with pytest.raises(ValueError, match="readiness"):
        new.vector(context, feature_version=4)


def test_actual_inference_now_distinguishes_readiness_and_budget_contrasts():
    def probe(r, identity="red"):
        return probe_player_decision(
            question(identity=identity),
            economy_snapshot=EconomySnapshot(1000, ()),
            target_cash=3000,
            feature_version=5,
            readiness=r,
        )

    a, b = probe(readiness(level=30)), probe(readiness(level=60))
    result = compare_player_decision_pair(a, b, before_pair=(0, 1), after_pair=(0, 1))
    assert not result["identical_linear_contrast"]
    assert not result["learned_advantage_demonstrated"]
    assert probe(readiness(), "crystal").vectors == probe(readiness(), "red").vectors
    c = compare_player_decision_pair(
        probe(readiness()), probe(readiness(budget=0.2)), before_pair=(0, 1), after_pair=(0, 1)
    )
    assert not c["identical_linear_contrast"]


def test_mixed_legacy_and_new_rows_fit_reload_without_rewriting_legacy(tmp_path):
    old_plan, old_result = player_records(tmp_path / "old")
    old = reconstruct_native_curriculum(old_plan, old_result)
    frozen = old.public_dict()
    rows = [old]
    for i, (level, success) in enumerate(((25, False), (60, True), (30, False), (65, True))):
        rows.append(
            reconstruct_native_curriculum(*records(tmp_path / str(i), level=level, success=success))
        )
    base = (
        _example(
            77,
            selected=0,
            outcome=_settled(success=True, completion=0.1, unlock=0, action_cost=0.2),
        ),
    )
    fit = fit_living_dex_option_value(base, feature_version=5, curriculum_examples=rows)
    loaded = LivingDexOptionValueModel.from_dict(fit.model.to_dict())
    assert loaded.model_sha256 == fit.model.model_sha256
    assert fit.report.weighted_mse_after < fit.report.weighted_mse_before
    assert old.public_dict() == frozen
    assert curriculum_features(old, 5)[: len(old.features)] == old.features
    assert not any(curriculum_features(old, 5)[len(old.features) :])
    q = question()
    context = living_dex_option_context_from_goal_situation(
        q.situation, economy_snapshot=EconomySnapshot(1000, ()), target_cash=3000
    )
    candidates = tuple(
        project_living_dex_goal_candidate(
            q, i, feature_version=5, binding_ref=f"private-{i}", readiness=readiness()
        )
        for i in (0, 1)
    )
    m = LivingDexOptionMenu(context, candidates)
    restored = restore_living_dex_policy_menu(m.policy_dict())
    assert restored.policy_dict() == m.policy_dict()
    assert loaded.predict_candidate(context, candidates[0]) == fit.model.predict_candidate(
        context, restored.candidates[0]
    )


def test_zero_extension_keeps_frozen_model_predictions(tmp_path):
    rows = [reconstruct_native_curriculum(*player_records(tmp_path / "a"))]
    rows.append(replace(rows[0], decision_sha256="9" * 64))
    base = (
        _example(
            77,
            selected=0,
            outcome=_settled(success=True, completion=0.1, unlock=0, action_cost=0.2),
        ),
    )
    old = fit_living_dex_option_value(base, feature_version=4, curriculum_examples=rows).model
    frozen = copy.deepcopy(old.to_dict())
    new = upgrade_option_value_model_for_readiness(old)
    assert old.to_dict() == frozen
    np.testing.assert_array_equal(new.coefficients[: len(old.coefficients)], old.coefficients)
    assert not np.any(new.coefficients[len(old.coefficients) :])
    q = question()
    context = living_dex_option_context_from_goal_situation(
        q.situation, economy_snapshot=EconomySnapshot(1000, ()), target_cash=3000
    )
    candidate = project_living_dex_goal_candidate(q, 0, feature_version=4, binding_ref="ignored")
    assert old.predict_candidate(context, candidate) == new.predict_candidate(
        context, replace(candidate, readiness=readiness())
    )


@pytest.mark.parametrize("mutation", ["nan", "bool", "unknown", "order", "extra"])
def test_invalid_readiness_fails_closed(mutation):
    doc = readiness().public_dict()
    if mutation == "nan":
        doc["values"][0] = float("nan")
    if mutation == "bool":
        doc["values"][0] = True
    if mutation == "unknown":
        doc["values"][20:22] = [0, 0.9]
    if mutation == "order":
        doc["names"].reverse()
    if mutation == "extra":
        doc["private_binding"] = "ignored"
    with pytest.raises(ValueError):
        PlayerReadiness.from_public(doc)


def test_registered_fitter_retains_v4_and_new_v5_lessons(tmp_path, monkeypatch):
    import test_red_native_curriculum as original

    def factory(path):
        plan, result = records(path)
        return plan, result, None

    monkeypatch.setattr(original, "records", factory)
    original.test_player_updates_authenticate_and_retain_native_lessons(tmp_path, monkeypatch)


def test_live_option_menu_uses_the_same_readiness_projection():
    from test_post_battle_strategy import bindings

    from pokemon_red_completion.red_live_option_menu import build_red_live_option_set

    bound = bindings()
    q = bound.question(question().situation)
    r = readiness()
    options = build_red_live_option_set(
        situation=q.situation, binding_set=bound, supplements=(), model_feature_version=5,
        ordering_seed_sha256='a' * 64, economy_snapshot=EconomySnapshot(1000, ()),
        target_cash=3000, readiness=r,
    )
    assert options.menu.feature_version == 5
    for candidate in options.menu.candidates:
        index = next(i for i, o in enumerate(q.opportunities)
                     if o.binding_ref == candidate.binding_ref)
        projected = project_living_dex_goal_candidate(
            q, index, feature_version=5, binding_ref=candidate.binding_ref, readiness=r)
        assert candidate.vector(options.menu.context, feature_version=5) == projected.vector(
            options.menu.context, feature_version=5)
    with pytest.raises(ValueError, match='readiness'):
        build_red_live_option_set(
            situation=q.situation, binding_set=bound, supplements=(), model_feature_version=4,
            ordering_seed_sha256='a' * 64, economy_snapshot=EconomySnapshot(1000, ()),
            target_cash=3000, readiness=r,
        )
