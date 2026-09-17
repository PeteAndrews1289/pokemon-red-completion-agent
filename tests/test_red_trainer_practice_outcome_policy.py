from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from test_red_trainer_practice_fit import _target

from pokemon_red_completion.battle_actions import BattleActionKind
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
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
