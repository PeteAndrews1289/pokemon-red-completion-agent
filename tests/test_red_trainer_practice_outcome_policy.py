from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_trainer_practice_fit import _target

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import project_trainer_control_features
from pokemon_red_completion.red_trainer_practice_fit import (
    control_action_candidates,
    fit_trainer_practice_three_heads,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
    TrainerOutcomePolicyError,
)


def test_trained_policy_owns_main_and_forced_switch_choices():
    target = _target()
    model = fit_trainer_practice_three_heads(
        [target],
        seed=31,
        require_corpus_floor=False,
        epochs=50,
    )
    observation = target["observation"]
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    policy = RedTrainerPracticeOutcomePolicy(
        policy_id="unit-outcome",
        battle_plan_id="unit-battle",
        model=model,
    )
    action = policy.choose_main(
        observation, SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)
    )
    assert action.kind in {BattleActionKind.SELECT_MOVE, BattleActionKind.SWITCH}
    assert policy.last_decision_diagnostics
    expected = control_action_candidates(
        tuple(
            project_trainer_control_features(
                observation, catalog=policy.catalog, move_batch=batch
            ).tolist()
        )
    )
    assert policy.last_decision_diagnostics["control_candidate_vectors"] == [
        list(row) for row in expected
    ]
    exhausted = replace(batch, legal_mask=(False, False), current_pp=(0.0, 0.0))
    forced_policy = RedTrainerPracticeOutcomePolicy(
        policy_id="unit-outcome",
        battle_plan_id="unit-battle",
        model=model,
    )
    forced_action = forced_policy.choose_main(
        observation, SimpleNamespace(features=exhausted, supported_candidate_mask=(False, False))
    )
    assert forced_action.kind is BattleActionKind.SWITCH
    assert forced_action.party_slot in {2, 3}
    assert forced_policy.last_decision_diagnostics["forced_by_legality"] is True
    replacement = forced_policy.choose_switch(
        observation,
        (2, 3),
        forced=True,
        may_decline=False,
    )
    assert replacement in {2, 3}


def test_optional_prompt_without_living_reserve_declines_without_projection(monkeypatch):
    target = _target()
    model = fit_trainer_practice_three_heads(
        [target], seed=31, require_corpus_floor=False, epochs=10
    )
    policy = RedTrainerPracticeOutcomePolicy(
        policy_id="unit-outcome", battle_plan_id="unit-battle", model=model
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_trainer_practice_outcome_policy."
        "project_trainer_switch_features",
        lambda *_args: pytest.fail("empty optional prompt must not project targets"),
    )
    assert policy.choose_switch(target["observation"], (), forced=False, may_decline=True) is None
    assert policy.last_decision_diagnostics == {
        "decision_mode": "prompt",
        "control_choice": "decline",
        "reason": "no_legal_target",
    }
    with pytest.raises(TrainerOutcomePolicyError, match="no legal target"):
        policy.choose_switch(target["observation"], (), forced=True, may_decline=False)


def test_voluntary_switch_requires_an_attack_before_another_same_opponent_switch():
    target = _target()
    model = fit_trainer_practice_three_heads(
        [target], seed=31, require_corpus_floor=False, epochs=10
    )
    observation = target["observation"]
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    policy = RedTrainerPracticeOutcomePolicy(
        policy_id="unit-outcome", battle_plan_id="unit-battle", model=model
    )
    policy._unanswered_voluntary_switch_opponent = 0
    action = policy.choose_main(
        observation, SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)
    )
    assert action.kind is BattleActionKind.SELECT_MOVE
    assert policy.last_decision_diagnostics["switch_masked_until_attack"] is True
    assert policy._unanswered_voluntary_switch_opponent is None

    exhausted = replace(batch, legal_mask=(False, False), current_pp=(0.0, 0.0))
    policy._unanswered_voluntary_switch_opponent = 0
    forced_action = policy.choose_main(
        observation, SimpleNamespace(features=exhausted, supported_candidate_mask=(False, False))
    )
    assert forced_action.kind is BattleActionKind.SWITCH


def test_counterfactual_opening_switch_updates_the_same_guard_as_live_switch():
    target = _target()
    model = fit_trainer_practice_three_heads(
        [target], seed=31, require_corpus_floor=False, epochs=10
    )
    policy = RedTrainerPracticeOutcomePolicy("test", "test", model)
    observation = target["observation"]
    policy.observe_forced_choice(observation, BattleAction.switch(2))
    assert policy._unanswered_voluntary_switch_opponent == 0
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    action = policy.choose_main(
        observation, SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)
    )
    assert action.kind is BattleActionKind.SELECT_MOVE
    assert policy.last_decision_diagnostics["switch_masked_until_attack"] is True
    policy.observe_forced_choice(observation, BattleAction.move(1))
    assert policy._unanswered_voluntary_switch_opponent is None
    from copy import deepcopy

    fainted = deepcopy(observation)
    fainted["features"]["party"]["lead"]["hp"] = 0
    policy.observe_forced_choice(fainted, BattleAction.switch(2))
    assert policy._unanswered_voluntary_switch_opponent is None
