from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_trainer_practice_features import _six_party_observation
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


@pytest.mark.parametrize("hp", [None, True, -1, "50"])
def test_forced_choice_rejects_untyped_or_invalid_lead_hp(hp):
    target = _target()
    model = fit_trainer_practice_three_heads([target], seed=1, require_corpus_floor=False, epochs=1)
    policy = RedTrainerPracticeOutcomePolicy(policy_id="unit", battle_plan_id="unit", model=model)
    observation = deepcopy(target["observation"])
    observation["features"]["party"]["lead"]["hp"] = hp
    with pytest.raises(TrainerOutcomePolicyError, match="lead HP"):
        policy.observe_forced_choice(observation, BattleAction.switch(2))


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


class _IndexedHead:
    schema_id = "pokemon.core.battle.move-ranker.observable-stats.v1"
    def __init__(self, selected_index):
        self.selected_index = selected_index

    def predict_index(self, rows):
        assert rows
        assert 0 <= self.selected_index < len(rows)
        return self.selected_index

    def probabilities(self, rows):
        values = [0.0] * len(rows)
        values[self.selected_index] = 1.0
        return SimpleNamespace(tolist=lambda: values)


def _immune_recovery_fixture(*, enabled, control_choice=1):
    observation = _target()["observation"]
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    vectors = []
    for original in batch.candidate_vectors:
        row = list(original)
        for name, value in (
            ("move.power_fraction", 0.3),
            ("move.type_effectiveness_fraction", 0.0),
            ("move.effective_power_fraction", 0.0),
            ("move.category.status", 0.0),
            ("move.effect.fixed_damage", 0.0),
        ):
            row[batch.feature_names.index(name)] = value
        vectors.append(tuple(row))
    batch = replace(batch, candidate_vectors=tuple(vectors))
    control = _IndexedHead(control_choice)
    control.schema_id = "unit-legacy-control"
    model = SimpleNamespace(control=control, move=_IndexedHead(0), switch=_IndexedHead(0))
    policy = RedTrainerPracticeOutcomePolicy(
        "unit", "unit", model, allow_immune_switch_recovery=enabled
    )
    policy._unanswered_voluntary_switch_opponent = 0
    return (
        policy,
        observation,
        SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask),
    )


def test_immune_recovery_is_opt_in_and_preserves_default_attack_guard():
    policy, observation, prepared = _immune_recovery_fixture(enabled=False)
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SELECT_MOVE
    assert policy.last_decision_diagnostics["switch_masked_until_attack"]


def test_immune_recovery_exposes_one_model_switch_then_stops_a_repeat():
    policy, observation, prepared = _immune_recovery_fixture(enabled=True)
    action = policy.choose_main(observation, prepared)
    assert action.kind is BattleActionKind.SWITCH
    assert action.party_slot == 2
    assert policy.last_decision_diagnostics["immune_switch_recovery_offered"]
    with pytest.raises(TrainerOutcomePolicyError, match="recovery budget exhausted"):
        policy.choose_main(observation, prepared)


def test_immune_recovery_does_not_override_a_model_selected_attack():
    policy, observation, prepared = _immune_recovery_fixture(enabled=True, control_choice=0)
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SELECT_MOVE
    assert policy._immune_switch_escape_opponent is None


def test_new_opponent_has_a_separate_immune_recovery_budget():
    policy, observation, prepared = _immune_recovery_fixture(enabled=True)
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SWITCH
    policy.history.note_opponent_replacement()
    # First switch against a new opponent is ordinary, then one escape is available.
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SWITCH
    assert not policy.last_decision_diagnostics["immune_switch_recovery_offered"]
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SWITCH
    assert policy.last_decision_diagnostics["immune_switch_recovery_offered"]
    with pytest.raises(TrainerOutcomePolicyError, match="recovery budget exhausted"):
        policy.choose_main(observation, prepared)


def test_no_living_reserve_does_not_offer_an_impossible_escape():
    policy, observation, prepared = _immune_recovery_fixture(enabled=True)
    observation = deepcopy(observation)
    for member in observation["features"]["party"]["members"][1:]:
        member["hp"] = 0
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SELECT_MOVE
    assert not policy.last_decision_diagnostics["immune_switch_recovery_offered"]


@pytest.mark.parametrize(
    "feature,value",
    [
        ("move.type_effectiveness_fraction", 0.25),
        ("move.effect.fixed_damage", 1.0),
        ("move.category.status", 1.0),
        ("move.power_fraction", 0.0),
    ],
)
def test_possible_or_uncertain_attack_keeps_the_ordinary_guard(feature, value):
    policy, observation, prepared = _immune_recovery_fixture(enabled=True)
    rows = list(prepared.features.candidate_vectors)
    row = list(rows[0])
    row[prepared.features.feature_names.index(feature)] = value
    rows[0] = tuple(row)
    prepared.features = replace(prepared.features, candidate_vectors=tuple(rows))
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SELECT_MOVE
    assert not policy.last_decision_diagnostics["immune_switch_recovery_offered"]


def test_depleted_effective_move_does_not_prevent_immune_recovery():
    policy, observation, prepared = _immune_recovery_fixture(enabled=True)
    rows = list(prepared.features.candidate_vectors)
    row = list(rows[1])
    row[prepared.features.feature_names.index("move.type_effectiveness_fraction")] = 0.25
    rows[1] = tuple(row)
    prepared.features = replace(prepared.features, candidate_vectors=tuple(rows))
    prepared.supported_candidate_mask = (True, False)
    assert policy.choose_main(observation, prepared).kind is BattleActionKind.SWITCH


@pytest.mark.parametrize("enabled", [1, None, "true"])
def test_immune_recovery_rejects_untyped_opt_in(enabled):
    with pytest.raises(TrainerOutcomePolicyError, match="explicit boolean"):
        _immune_recovery_fixture(enabled=enabled)


@pytest.mark.parametrize("target_slot", (4, 5, 6))
def test_stub_scoring_maps_distinct_winning_rows_back_to_late_slots(target_slot):
    observation = _six_party_observation(active_slot=1)
    candidate_slots = (2, 3, 4, 5, 6)
    model = SimpleNamespace(
        switch=_IndexedHead(candidate_slots.index(target_slot)),
        control=SimpleNamespace(schema_id="unused"),
        move=SimpleNamespace(),
    )
    policy = RedTrainerPracticeOutcomePolicy("six-slot", "six-slot", model)

    selected = policy.choose_switch(
        observation,
        candidate_slots,
        forced=True,
        may_decline=False,
    )

    assert selected == target_slot
    assert policy.last_decision_diagnostics["switch_candidate_slots"] == list(candidate_slots)
    assert policy.last_decision_diagnostics["switch_probabilities"][target_slot - 2] == 1.0


@pytest.mark.parametrize("target_slot", (4, 5, 6))
def test_forced_policy_reaches_the_only_living_late_reserve(target_slot):
    observation = _six_party_observation(active_slot=1, living_slots={1, target_slot})
    policy = RedTrainerPracticeOutcomePolicy(
        "six-slot",
        "six-slot",
        SimpleNamespace(
            switch=_IndexedHead(0),
            control=SimpleNamespace(schema_id="unused"),
            move=SimpleNamespace(),
        ),
    )
    assert (
        policy.choose_switch(
            observation,
            (target_slot,),
            forced=True,
            may_decline=False,
        )
        == target_slot
    )


def test_policy_cannot_select_active_fainted_or_absent_late_slots():
    observation = _six_party_observation(active_slot=4, living_slots={4, 6})
    policy = RedTrainerPracticeOutcomePolicy(
        "six-slot",
        "six-slot",
        SimpleNamespace(
            switch=_IndexedHead(0),
            control=SimpleNamespace(schema_id="unused"),
            move=SimpleNamespace(),
        ),
    )
    assert policy.choose_switch(observation, (4, 5, 6), forced=True, may_decline=False) == 6
    with pytest.raises(TrainerOutcomePolicyError, match="no legal switch candidate"):
        policy.choose_switch(observation, (4, 5), forced=True, may_decline=False)
