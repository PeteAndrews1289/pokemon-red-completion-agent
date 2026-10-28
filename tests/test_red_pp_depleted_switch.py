from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from test_red_trainer_practice_features import _six_party_observation
from test_red_trainer_practice_outcome_policy import _IndexedHead

from pokemon_red_completion.battle_actions import BattleActionKind
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)


def fixture(active=4, *, enabled=True, pp=0):
    obs = _six_party_observation(active_slot=active, living_slots={4, 5})
    party = obs["features"]["party"]
    party["members"][3]["moves"] = [
        dict(slot_index=0, move_ref="pokemon.red.gb.us.rev0:move:071", pp=pp),
        dict(slot_index=1, move_ref="pokemon.red.gb.us.rev0:move:079", pp=15),
    ]
    party["lead"] = deepcopy(party["members"][active - 1])
    control = _IndexedHead(1)
    control.schema_id = "unit-control"
    control.probabilities = lambda rows: np.array([0.0, 1.0])
    model = SimpleNamespace(move=_IndexedHead(0), switch=_IndexedHead(0), control=control)
    return obs, RedTrainerPracticeOutcomePolicy(
        "unit", "battle", model, pp_depleted_switch_screen=enabled,
    )


def prepared(obs, *, supported=None):
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs)
    mask = tuple(m["pp"] > 0 and m["move_ref"].endswith(":033")
                 or m["pp"] > 0 and m["move_ref"].endswith(":071")
                 for m in obs["features"]["party"]["lead"]["moves"])
    if supported is not None:
        mask = supported
    return SimpleNamespace(features=replace(batch, legal_mask=mask), supported_candidate_mask=mask)


def leave_depleted(policy, obs):
    action = policy.choose_main(obs, prepared(obs))
    assert action.kind is BattleActionKind.SWITCH and action.party_slot == 5
    assert policy.last_decision_diagnostics["forced_by_legality"]


def test_observed_oddish_wartortle_loop_is_screened_without_a_new_move_choice():
    obs, policy = fixture()
    leave_depleted(policy, obs)
    productive, _ = fixture(active=5)
    assert policy.choose_main(productive, prepared(productive)).kind is BattleActionKind.SELECT_MOVE
    # The ordinary attack obligation clears after one attack. It must still
    # not reopen the exhausted Oddish target on the following boundary.
    action = policy.choose_main(productive, prepared(productive))
    assert action.kind is BattleActionKind.SELECT_MOVE and action.move_slot == 1
    assert policy.last_decision_diagnostics["pp_depleted_switch_screen"] == {
        "schema": "pokemon.red.pp-depleted-reentry.v1",
        "removed_party_slots": [4], "observed_depleted_members": [4],
        "supplied_rules_not_learned": True,
    }


def test_historical_default_still_reenters_and_has_no_new_diagnostics():
    obs, policy = fixture(enabled=False)
    leave_depleted(policy, obs)
    productive, _ = fixture(active=5)
    policy.choose_main(productive, prepared(productive))
    assert policy.choose_main(productive, prepared(productive)).party_slot == 4
    assert "pp_depleted_switch_screen" not in policy.last_decision_diagnostics


def test_pp_restoration_readmits_the_same_member():
    obs, policy = fixture()
    leave_depleted(policy, obs)
    restored, _ = fixture(active=5, pp=1)
    policy.choose_main(restored, prepared(restored))
    assert policy.choose_main(restored, prepared(restored)).party_slot == 4
    screen = policy.last_decision_diagnostics["pp_depleted_switch_screen"]
    assert not screen["observed_depleted_members"]


@pytest.mark.parametrize("forced", [False, True])
def test_forced_replacement_remains_legal_but_optional_prompt_declines(forced):
    obs, policy = fixture()
    leave_depleted(policy, obs)
    productive, _ = fixture(active=5)
    assert policy.choose_switch(productive, (4,), forced=forced, may_decline=not forced) == (
        4 if forced else None
    )


def test_status_capable_boundary_does_not_mark_a_usable_status_member():
    obs, policy = fixture()
    action = policy.choose_main(obs, prepared(obs, supported=(False, True)))
    assert action.kind is BattleActionKind.SWITCH
    screen = policy.last_decision_diagnostics["pp_depleted_switch_screen"]
    assert not screen["observed_depleted_members"]


def test_temporarily_disabled_positive_pp_attack_is_not_marked():
    obs, policy = fixture(pp=10)
    assert policy.choose_main(obs, prepared(obs, supported=(False, False))).party_slot == 5
    screen = policy.last_decision_diagnostics["pp_depleted_switch_screen"]
    assert not screen["observed_depleted_members"]


def test_all_party_depletion_does_not_remove_the_last_escape():
    obs, policy = fixture()
    leave_depleted(policy, obs)
    depleted, _ = fixture(active=5)
    depleted["features"]["party"]["members"][4]["moves"][0]["pp"] = 0
    depleted["features"]["party"]["lead"]["moves"][0]["pp"] = 0
    assert policy.choose_main(depleted, prepared(depleted)).party_slot == 4


@pytest.mark.parametrize("depleted_slot,productive_slot", [(1, 2), (2, 6), (6, 3)])
def test_screen_follows_the_observed_member_not_an_erika_party_position(
    depleted_slot, productive_slot,
):
    _, policy = fixture()
    obs = _six_party_observation(active_slot=depleted_slot,
        living_slots={depleted_slot, productive_slot})
    party = obs["features"]["party"]
    party["members"][depleted_slot - 1]["moves"][0]["pp"] = 0
    party["lead"] = deepcopy(party["members"][depleted_slot - 1])
    assert policy.choose_main(obs, prepared(obs)).party_slot == productive_slot
    party["active_index"] = productive_slot - 1
    party["lead"] = deepcopy(party["members"][productive_slot - 1])
    policy.choose_main(obs, prepared(obs))
    assert policy.choose_main(obs, prepared(obs)).kind is BattleActionKind.SELECT_MOVE
    assert policy.last_decision_diagnostics["pp_depleted_switch_screen"][
        "removed_party_slots"] == [depleted_slot]


@pytest.mark.parametrize("value", [1, None, "yes"])
def test_screen_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match="PP reentry"):
        RedTrainerPracticeOutcomePolicy("unit", "battle", object(), pp_depleted_switch_screen=value)


@pytest.mark.parametrize("changed", ["partition", "model", "receipt", "type"])
def test_native_opt_in_rejects_other_authority_before_input(tmp_path, changed):
    from pokemon_red_completion import red_learned_trainer as learned
    from pokemon_red_completion.battle_runtime import BattleRuntimeTiming

    actor = learned.FrozenTrainerBattler(
        None, None, tmp_path, "a" * 40, "root", "b" * 64, {},
        model_sha256=learned.FROZEN_K_SHA256,
        qualification_sha256=learned.K_QUALIFICATION_SHA256,
        pp_depleted_switch_screen=True,
    )
    if changed == "partition":
        actor.source_partition = learned.ScenarioPartition.TRAIN
    elif changed == "model":
        actor.model_sha256 = learned.FROZEN_J_SHA256
    elif changed == "receipt":
        actor.qualification_sha256 = "c" * 64
    else:
        actor.pp_depleted_switch_screen = 1
    with pytest.raises(ValueError, match="PP reentry"):
        actor._play(None, None, expected_map=134, timing=BattleRuntimeTiming(),
            label="test", decision_guard=lambda _: None, resume=True,
            require_win=False, authority="frozen-k-story-development")
    assert actor.calls == 0 and not tuple(tmp_path.iterdir())
