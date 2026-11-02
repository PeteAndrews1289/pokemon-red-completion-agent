"""Capped stat effects are supplied mechanics, not a blanket status ban."""

from types import SimpleNamespace

import pytest
from test_red_battle_mechanics_boundary import fixture, prepare
from test_red_trainer_practice_outcome_policy import _IndexedHead

from pokemon_red_completion.red_battle_mechanics_boundary import capped_stat_choices
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)


def observed(moves, *, player=None, foe=None):
    obs, catalog = fixture(moves, foe_type="normal")
    obs["features"]["battle"]["status_context"] = dict(
        schema="pokemon.core.battle.status-context.v1",
        player_confused=False,
        opponent_confused=False,
        player_stages=player or [0] * 6,
        opponent_stages=foe or [0] * 6,
    )
    return obs, catalog


@pytest.mark.parametrize("move,index", [(39, 1), (28, 4), (45, 0), (81, 2), (43, 1)])
def test_only_capped_stat_drop_removed(move, index):
    stages = [0] * 6
    stages[index] = -6
    obs, catalog = observed((move, 55, 79), foe=stages)
    assert capped_stat_choices(obs, catalog, (1, 2, 3)) == ((2, 3), (1,))
    stages[index] = -5
    assert capped_stat_choices(obs, catalog, (1, 2, 3)) == ((1, 2, 3), ())


def test_capped_self_buff_and_uncapped_sleep_kept_separate():
    obs, catalog = observed((104, 55, 79), player=[0, 0, 0, 0, 0, 6])
    assert capped_stat_choices(obs, catalog, (1, 2, 3)) == ((2, 3), (1,))


def test_all_noop_inventory_not_emptied_or_replaced():
    obs, catalog = observed((39,), foe=[0, -6, 0, 0, 0, 0])
    assert capped_stat_choices(obs, catalog, (1,)) == ((1,), ())


@pytest.mark.parametrize("value", [None, [0, 0], [0, True, 0, 0, 0, 0], [0, -7, 0, 0, 0, 0]])
def test_unknown_stage_context_refused(value):
    obs, catalog = observed((39, 55))
    obs["features"]["battle"]["status_context"]["opponent_stages"] = value
    with pytest.raises(ValueError, match="six observed"):
        capped_stat_choices(obs, catalog, (1, 2))


def test_policy_opt_in_preserves_baseline_and_damage_ranking():
    obs, catalog = observed((39, 55, 79), foe=[0, -6, 0, 0, 0, 0])
    prepared, _ = prepare(obs, catalog)
    control = _IndexedHead(0)
    control.schema_id = "unit-control"
    model = SimpleNamespace(move=_IndexedHead(0), switch=_IndexedHead(0), control=control)
    baseline = RedTrainerPracticeOutcomePolicy("old", "battle", model, mechanics_aware_choices=True)
    candidate = RedTrainerPracticeOutcomePolicy(
        "new", "battle", model, mechanics_aware_choices=True, screen_capped_status_moves=True
    )
    assert baseline.choose_main(obs, prepared).move_slot == 1
    assert candidate.choose_main(obs, prepared).move_slot == 2
    assert candidate.model is model
    assert candidate.last_decision_diagnostics["capped_status_screen"] == dict(
        schema="pokemon.red.capped-stat-screen.v1",
        removed_move_slots=[1],
        supplied_rules_not_learned=True,
    )
    assert "capped_status_screen" not in baseline.last_decision_diagnostics


@pytest.mark.parametrize("flag,mechanics", [(1, True), (True, False)])
def test_implicit_or_unscoped_enablement_refused(flag, mechanics):
    with pytest.raises(ValueError, match="Capped status screen"):
        RedTrainerPracticeOutcomePolicy(
            "bad",
            "battle",
            object(),
            mechanics_aware_choices=mechanics,
            screen_capped_status_moves=flag,
        )
