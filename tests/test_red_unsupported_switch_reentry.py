"""Observed unsupported-move exits cannot become voluntary reentry loops."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from test_red_trainer_practice_features import _six_party_observation
from test_red_trainer_practice_outcome_policy import _IndexedHead

from pokemon_red_completion.battle_actions import BattleActionKind
from pokemon_red_completion.battle_semantics import BattleFeatureError, BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_battle_scenario import (
    PreparedRedBattleScenario,
    red_battle_move_unsupported_reason,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)


class _LastHead(_IndexedHead):
    def predict_index(self, rows):
        assert rows
        return len(rows) - 1

    def probabilities(self, rows):
        assert rows
        values = np.zeros(len(rows))
        values[-1] = 1.0
        return values


def fixture(*, active=5, enabled=True, living=frozenset({1, 4, 5})):
    obs = _six_party_observation(active_slot=active, living_slots=set(living))
    party = obs["features"]["party"]
    for member in party["members"]:
        member["moves"] = [
            dict(slot_index=0, move_ref="pokemon.red.gb.us.rev0:move:033", pp=30)
        ]
    party["members"][4]["moves"] = [
        dict(slot_index=0, move_ref="pokemon.red.gb.us.rev0:move:106", pp=30)
    ]
    party["lead"] = deepcopy(party["members"][active - 1])
    control = _IndexedHead(1)
    control.schema_id = "unit-control"
    control.probabilities = lambda rows: np.array([0.0, 1.0])
    model = SimpleNamespace(move=_IndexedHead(0), switch=_LastHead(1), control=control)
    return obs, RedTrainerPracticeOutcomePolicy(
        "unit", "battle", model, pp_depleted_switch_screen=enabled
    )


def prepared(obs, *, status_supported=False, reason_override=None):
    catalog = PokemonRedBattleCatalog()
    batch = BattleFeatureProjector(catalog).project(obs)
    reasons = []
    for item in obs["features"]["party"]["lead"]["moves"]:
        move_id = int(item["move_ref"].rsplit(":", 1)[1])
        reason = red_battle_move_unsupported_reason(move_id, item["pp"], catalog=catalog)
        if status_supported and reason == "status_or_non_damaging_outside_segment":
            reason = None
        if item["slot_index"] + 1 == obs["features"]["battle"].get("player_disabled_move_slot"):
            reason = "disabled_move"
        reasons.append(reason_override if reason_override is not None else reason)
    mask = tuple(reason is None for reason in reasons)
    return PreparedRedBattleScenario(
        "a" * 64, replace(batch, legal_mask=mask), allow_no_attack=True,
        unsupported_candidate_reasons=tuple(reasons),
    )


def leave_unsupported(policy, obs):
    action = policy.choose_main(obs, prepared(obs))
    assert action.kind is BattleActionKind.SWITCH and action.party_slot == 4
    assert policy.last_decision_diagnostics["forced_by_legality"]


def attack_after_exit(policy):
    obs, _ = fixture(active=4)
    assert policy.choose_main(obs, prepared(obs)).kind is BattleActionKind.SELECT_MOVE
    return obs


def test_status_only_reentry_loop_removes_only_observed_unexecutable_target():
    obs, policy = fixture()
    original = deepcopy(obs)
    model = policy.model
    leave_unsupported(policy, obs)
    productive = attack_after_exit(policy)
    action = policy.choose_main(productive, prepared(productive))
    assert action.kind is BattleActionKind.SWITCH and action.party_slot == 1
    assert policy.model is model and obs == original
    assert policy.last_decision_diagnostics["switch_candidate_slots"] == [1]
    assert policy.last_decision_diagnostics["unsupported_move_reentry_screen"] == {
        "schema": "pokemon.red.unsupported-move-reentry.v1",
        "removed_party_slots": [5], "observed_unsupported_members": [5],
        "supplied_rules_not_learned": True,
    }
    assert policy.last_decision_diagnostics["pp_depleted_switch_screen"][
        "observed_depleted_members"
    ] == []


def test_unobserved_status_only_reserve_remains_a_learned_choice():
    obs, policy = fixture(active=4)
    assert policy.choose_main(obs, prepared(obs)).party_slot == 5
    assert "unsupported_move_reentry_screen" not in policy.last_decision_diagnostics


@pytest.mark.parametrize("move", [106, 120])
def test_only_adapter_declared_scope_exclusions_are_remembered(move):
    obs, policy = fixture()
    party = obs["features"]["party"]
    item = party["members"][4]["moves"][0]
    item.update(move_ref=f"pokemon.red.gb.us.rev0:move:{move:03d}", pp=5)
    party["lead"] = deepcopy(party["members"][4])
    leave_unsupported(policy, obs)
    assert policy.last_decision_diagnostics["unsupported_move_reentry_screen"][
        "observed_unsupported_members"
    ] == [5]


def test_counter_without_received_damage_still_rejects_before_policy():
    obs, policy = fixture()
    party = obs["features"]["party"]
    party["members"][4]["moves"][0].update(
        move_ref="pokemon.red.gb.us.rev0:move:068", pp=5
    )
    party["lead"] = deepcopy(party["members"][4])
    with pytest.raises(BattleFeatureError, match="Counter requires prior-turn"):
        prepared(obs)
    assert not policy.last_decision_diagnostics


def test_historical_opt_out_preserves_original_reentry():
    obs, policy = fixture(enabled=False)
    leave_unsupported(policy, obs)
    productive = attack_after_exit(policy)
    assert policy.choose_main(productive, prepared(productive)).party_slot == 5
    assert "unsupported_move_reentry_screen" not in policy.last_decision_diagnostics


@pytest.mark.parametrize("forced", [False, True])
def test_only_optional_prompt_is_screened_for_an_observed_unsupported_member(forced):
    obs, policy = fixture()
    leave_unsupported(policy, obs)
    productive, _ = fixture(active=4)
    assert policy.choose_switch(productive, (5,), forced=forced, may_decline=not forced) == (
        5 if forced else None
    )


@pytest.mark.parametrize("change,expected", [("pp", 1), ("move", 5)])
def test_reentry_tracks_supported_move_capability_not_health_or_pp_alone(change, expected):
    obs, policy = fixture()
    leave_unsupported(policy, obs)
    productive = attack_after_exit(policy)
    item = productive["features"]["party"]["members"][4]["moves"][0]
    if change == "pp":
        item["pp"] = 1  # Harden still cannot execute in this actor's scope.
    else:
        item["move_ref"] = "pokemon.red.gb.us.rev0:move:033"
    assert policy.choose_main(productive, prepared(productive)).party_slot == expected


def test_status_capable_actor_is_not_misclassified_as_attack_only():
    obs, policy = fixture()
    action = policy.choose_main(obs, prepared(obs, status_supported=True))
    assert action.kind is BattleActionKind.SWITCH and action.party_slot == 4
    assert "unsupported_move_reentry_screen" not in policy.last_decision_diagnostics
    productive = attack_after_exit(policy)
    assert policy.choose_main(productive, prepared(productive)).party_slot == 5


@pytest.mark.parametrize("reason", ["disabled_move", "unknown_future_reason", "no_pp"])
def test_transient_unknown_or_depleted_reasons_are_not_permanent_support_exclusions(reason):
    obs, policy = fixture()
    party = obs["features"]["party"]
    party["members"][4]["moves"][0]["move_ref"] = "pokemon.red.gb.us.rev0:move:033"
    party["lead"] = deepcopy(party["members"][4])
    assert policy.choose_main(obs, prepared(obs, reason_override=reason)).party_slot == 4
    assert "unsupported_move_reentry_screen" not in policy.last_decision_diagnostics


def test_all_unsupported_party_keeps_last_escape_and_does_not_invent_a_move():
    obs, policy = fixture(living=frozenset({4, 5}))
    party = obs["features"]["party"]
    party["members"][3]["moves"] = deepcopy(party["members"][4]["moves"])
    leave_unsupported(policy, obs)
    party["active_index"] = 3
    party["lead"] = deepcopy(party["members"][3])
    action = policy.choose_main(obs, prepared(obs))
    assert action.kind is BattleActionKind.SWITCH and action.party_slot == 5
    assert policy.last_decision_diagnostics["unsupported_move_reentry_screen"][
        "removed_party_slots"
    ] == []


@pytest.mark.parametrize("unsupported,productive", [(1, 2), (2, 6), (6, 3)])
def test_observed_support_screen_is_not_tied_to_route_species_or_party_slot(
    unsupported, productive,
):
    obs, policy = fixture(active=unsupported, living=frozenset({unsupported, productive}))
    party = obs["features"]["party"]
    for member in party["members"]:
        member["moves"] = [dict(slot_index=0, move_ref="pokemon.red.gb.us.rev0:move:033", pp=30)]
    party["members"][unsupported - 1]["moves"][0]["move_ref"] = "pokemon.red.gb.us.rev0:move:106"
    party["lead"] = deepcopy(party["members"][unsupported - 1])
    assert policy.choose_main(obs, prepared(obs)).party_slot == productive
    party["active_index"] = productive - 1
    party["lead"] = deepcopy(party["members"][productive - 1])
    assert policy.choose_main(obs, prepared(obs)).kind is BattleActionKind.SELECT_MOVE
    assert policy.choose_main(obs, prepared(obs)).kind is BattleActionKind.SELECT_MOVE
    assert policy.last_decision_diagnostics["unsupported_move_reentry_screen"][
        "removed_party_slots"
    ] == [unsupported]
