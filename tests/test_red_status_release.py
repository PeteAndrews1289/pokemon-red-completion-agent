from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_battle_mechanics_boundary import fixture, prepare
from test_red_development_story_scope import actor
from test_red_trainer_practice_outcome_policy import _IndexedHead

from pokemon_red_completion.battle_actions import BattleActionKind
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)


def setup(*, release=True, control=1):
    obs, catalog = fixture((55,), reserve_move=55)
    party = obs["features"]["party"]
    party["lead"]["status"] = "paralysis"
    for member in party["members"][1:]:
        member["status"] = None
    head = _IndexedHead(control)
    head.schema_id = "unit-control"
    model = SimpleNamespace(move=_IndexedHead(0), switch=_IndexedHead(0), control=head)
    policy = RedTrainerPracticeOutcomePolicy(
        "status-test",
        "battle",
        model,
        catalog=catalog,
        mechanics_aware_choices=True,
        diagnostic_stay_when_productive=True,
        diagnostic_status_release=release,
    )
    return obs, catalog, policy


@pytest.mark.parametrize("status,confusion", [("paralysis", False), (None, True)])
def test_release_preserves_model_switch_and_next_attack_mask(status, confusion):
    obs, catalog, policy = setup()
    obs["features"]["party"]["lead"]["status"] = status
    obs["features"]["battle"]["status_context"] = {"player_confused": confusion}
    action = policy.choose_main(obs, prepare(obs, catalog)[0])
    assert action.kind is BattleActionKind.SWITCH and action.party_slot == 2
    assert policy.last_decision_diagnostics["diagnostic_control"]["released_learned_switch"]
    after = deepcopy(obs)
    party = after["features"]["party"]
    party["active_index"] = 1
    party["lead"] = party["members"][1]
    # Even another impairment cannot bypass the consecutive-switch guard.
    party["lead"]["status"] = "paralysis"
    assert (
        policy.choose_main(after, prepare(after, catalog)[0]).kind is BattleActionKind.SELECT_MOVE
    )
    assert policy.last_decision_diagnostics["switch_masked_until_attack"]


@pytest.mark.parametrize(
    "condition", ["default", "healthy", "fainted", "depleted", "immune", "status", "attack"]
)
def test_release_does_not_force_or_invent_a_viable_switch(condition):
    obs, catalog, policy = setup(
        release=condition != "default", control=0 if condition == "attack" else 1
    )
    party = obs["features"]["party"]
    if condition == "healthy":
        party["lead"]["status"] = None
    for member in party["members"][1:]:
        if condition == "fainted":
            member["hp"] = 0
        if condition == "depleted":
            member["moves"][0]["pp"] = 0
        if condition == "immune":
            member["moves"][0]["move_ref"] = "pokemon.red.gb.us.rev0:move:033"
        if condition == "status":
            member["status"] = "paralysis"
    assert policy.choose_main(obs, prepare(obs, catalog)[0]).kind is BattleActionKind.SELECT_MOVE
    assert not policy.last_decision_diagnostics["diagnostic_control"].get(
        "released_learned_switch", False
    )


@pytest.mark.parametrize("value,stay", [(1, True), (True, False)])
def test_release_is_explicit(value, stay):
    with pytest.raises(ValueError, match="status release"):
        RedTrainerPracticeOutcomePolicy(
            "test",
            "battle",
            None,
            mechanics_aware_choices=True,
            diagnostic_stay_when_productive=stay,
            diagnostic_status_release=value,
        )


def test_scope_preserves_old_identity_and_binds_new_variant(tmp_path):
    scope = actor(tmp_path).development_story_scope
    old = replace(scope, diagnostic_stay_when_productive=True)
    assert "diagnostic_status_release" not in old.document()
    assert type(old).from_document(old.document()) == old
    new = replace(old, diagnostic_status_release=True)
    assert new.identity != old.identity
    assert type(new).from_document(new.document()) == new
    with pytest.raises(ValueError, match="status release"):
        replace(scope, diagnostic_status_release=True)
