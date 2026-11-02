from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from test_red_battle_mechanics_boundary import fixture
from test_red_development_story_scope import actor
from test_red_trainer_practice_outcome_policy import _IndexedHead

from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)


def setup(enabled=True):
    obs, catalog = fixture((55,), reserve_move=55)
    control = _IndexedHead(1)
    control.schema_id = "unit-control"
    control.probabilities = lambda rows: np.array([0.0, 1.0])
    policy = RedTrainerPracticeOutcomePolicy(
        "prompt-test", "battle",
        SimpleNamespace(move=_IndexedHead(0), switch=_IndexedHead(0), control=control),
        catalog=catalog, mechanics_aware_choices=True,
        diagnostic_stay_when_productive=True, diagnostic_prompt_stay=enabled,
    )
    return obs, policy


def test_prompt_stay_is_separate_opt_in_and_logs_the_model_choice():
    obs, old = setup(False)
    _, new = setup()
    assert old.choose_switch(obs, (2,), forced=False, may_decline=True) == 2
    assert new.choose_switch(obs, (2,), forced=False, may_decline=True) is None
    diagnostics = new.last_decision_diagnostics
    assert diagnostics["control_probabilities"] == [0.0, 1.0]
    assert diagnostics["diagnostic_control"]["overrode_learned_switch"] is True
    assert diagnostics["diagnostic_control"]["supplied_not_learned"] is True


@pytest.mark.parametrize("condition", ["forced", "fainted", "pp", "immune", "disabled", "status"])
def test_prompt_support_cannot_replace_forced_or_unproductive_choices(condition):
    obs, policy = setup()
    lead = obs["features"]["party"]["lead"]
    battle = obs["features"]["battle"]
    if condition == "fainted":
        lead["hp"] = 0
    if condition == "pp":
        lead["moves"][0]["pp"] = 0
    if condition == "immune":
        lead["moves"][0]["move_ref"] = "pokemon.red.gb.us.rev0:move:033"
    if condition == "disabled":
        battle["player_disabled_move_slot"] = 1
    if condition == "status":
        lead["status"] = "paralysis"
        policy.diagnostic_status_release = True
    forced = condition in {"forced", "fainted"}
    assert policy.choose_switch(obs, (2,), forced=forced, may_decline=not forced) == 2
    assert not policy.last_decision_diagnostics.get("diagnostic_control", {}).get(
        "overrode_learned_switch", False
    )


def test_scope_binds_new_support_without_changing_historical_identity(tmp_path):
    old = replace(actor(tmp_path).development_story_scope, diagnostic_stay_when_productive=True)
    assert "diagnostic_prompt_stay" not in old.document()
    assert type(old).from_document(old.document()) == old
    new = replace(old, diagnostic_prompt_stay=True)
    assert old.identity != new.identity
    assert type(new).from_document(new.document()) == new
    assert "diagnostic_status_entry" not in old.document()
    status = replace(new, diagnostic_status_entry=True)
    assert type(status).from_document(status.document()) == status
    assert status.identity != new.identity
    with pytest.raises(ValueError, match="status entry"):
        replace(status, diagnostic_status_entry=1)
    with pytest.raises(ValueError, match="prompt stay"):
        replace(new, diagnostic_stay_when_productive=False)


@pytest.mark.parametrize("value,stay", [(1, True), (True, False)])
def test_support_requires_explicit_development_stay(value, stay):
    with pytest.raises(ValueError, match="prompt stay"):
        RedTrainerPracticeOutcomePolicy(
            "test", "battle", object(), mechanics_aware_choices=True,
            diagnostic_stay_when_productive=stay, diagnostic_prompt_stay=value,
        )
