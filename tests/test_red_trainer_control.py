from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_trainer_control as control
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_trainer_control import (
    RedTrainerControlError,
    RedTrainerPartyController,
)


def raw(*, active=0, enemy=22, hp=(160, 190), pp=(10, 15)):
    moves = ((87, 0, 0, 0), (57, 58, 0, 0))
    pps = ((pp[0], 0, 0, 0), (pp[1], 10, 0, 0))
    return RawGameState(
        game_started=True, map_id=245, player_y=3, player_x=5, battle_state=2,
        party_count=2, party_species_ids=(104, 28), party_levels=(55, 55),
        party_hp=hp, party_max_hp=(160, 190), party_status=(0, 0),
        party_moves=moves, party_pp=pps, bag_items=((16, 4),),
        active_party_index=active, active_party_species_id=(104, 28)[active],
        active_party_hp=hp[active], active_party_max_hp=(160, 190)[active],
        active_party_moves=moves[active], active_party_pp=pps[active],
        enemy_species_id=enemy, enemy_level=55,
    )


def controller(state):
    reader = SimpleNamespace(state=state)
    reader.read = lambda: reader.state
    reader.read_trainer_entry_moves = lambda _: (33, 0, 0, 0)
    return RedTrainerPartyController(reader, object())


def test_good_active_matchup_uses_existing_move_policy():
    subject = controller(raw())
    calls = []
    assert subject.choose(raw(), lambda state: calls.append(state) or 1) == 1
    assert calls == [raw()] and subject.moves_selected == 1
    assert not subject.switches


@pytest.mark.parametrize("state", [raw(enemy=34), raw(hp=(79, 190)), raw(pp=(0, 15))])
def test_immunity_low_hp_or_exhaustion_requests_a_living_reserve(state):
    subject = controller(state)
    with pytest.raises(control._SwitchRequest) as requested:
        subject.choose(state, lambda _: pytest.fail("unfit member attacked"))
    assert requested.value.action.party_slot == 2
    assert subject.moves_selected == 0


def test_exhausted_switch_budget_and_no_move_between_switches_stop():
    state = raw(enemy=34)
    subject = controller(state)
    subject.switches[:] = [2] * 6
    with pytest.raises(RedTrainerControlError, match="budget"):
        subject.choose(state, lambda _: pytest.fail("unsafe attack"))
    subject.switches.clear()
    subject._move_since_switch = False
    with pytest.raises(RedTrainerControlError, match="unfit active"):
        subject.choose(state, lambda _: pytest.fail("unsafe attack"))


@pytest.mark.parametrize("state", [raw(hp=(0, 190)), raw(hp=(79, 94)),
                                    replace(raw(), battle_state=1),
                                    replace(raw(), enemy_species_id=None)])
def test_unsupported_or_unsafe_state_does_not_issue_input(state):
    with pytest.raises(RedTrainerControlError):
        controller(state).choose(state, lambda _: pytest.fail("unsafe attack"))


def run(subject, executor, guard=lambda _: None):
    return subject.run(subject.reader, executor, lambda _: 1, expected_map=245,
                       intent=BattleIntent("defeat_lorelei", "cartridge-trainer-story"),
                       timing=BattleRuntimeTiming(), label="test story",
                       consume_battle_start_schedule=False, move_decision_guard=guard)


def test_switch_is_acknowledged_then_combat_resumes_without_restarting_intro(monkeypatch):
    subject = controller(raw(enemy=34))
    seen = []
    executor = object()
    def battle(reader, actions, policy, **kwargs):
        assert actions is executor
        kwargs["move_decision_guard"](reader.read())
        try:
            slot = policy(reader.read())
        except control._SwitchRequest as error:
            raise BattleRuntimeError("switch boundary") from error
        assert slot == 1
        return replace(reader.read(), battle_state=0)
    def switch(actions, reader, emulator, index, **_):
        assert actions is executor and index == 1
        seen.append(index)
        reader.state = raw(active=1, enemy=34)
    monkeypatch.setattr(control, "run_adaptive_trainer_battle", battle)
    monkeypatch.setattr(control, "switch_active_battler", switch)
    assert run(subject, executor).battle_state == 0
    assert seen == [1] and subject.switches == [2] and subject.moves_selected == 1
    with pytest.raises(RedTrainerControlError, match="consumed"):
        run(subject, executor)
    assert seen == [1]


def test_unrelated_runtime_failure_never_becomes_a_switch_or_retry(monkeypatch):
    subject = controller(raw())
    calls = []
    def failure(*_, **__):
        calls.append(1)
        raise BattleRuntimeError("wrong battle identity")
    monkeypatch.setattr(control, "run_adaptive_trainer_battle", failure)
    monkeypatch.setattr(control, "switch_active_battler", lambda *_a, **_k: pytest.fail("switch"))
    with pytest.raises(BattleRuntimeError, match="wrong battle"):
        run(subject, object())
    assert calls == [1]


def test_shadow_model_cannot_silently_gain_battle_authority(monkeypatch):
    subject = controller(raw())
    monkeypatch.setattr(control, "battle_policy_override_active", lambda: True)
    monkeypatch.setattr(control, "run_adaptive_trainer_battle",
                        lambda *_a, **_k: pytest.fail("learned execution"))
    with pytest.raises(RedTrainerControlError, match="authority"):
        run(subject, object())


def test_resource_change_is_caught_before_next_move(monkeypatch):
    subject = controller(raw())
    def battle(reader, _actions, _policy, **kwargs):
        reader.state = replace(reader.state, bag_items=())
        kwargs["move_decision_guard"](reader.read())
    monkeypatch.setattr(control, "run_adaptive_trainer_battle", battle)
    with pytest.raises(RedTrainerControlError, match="bag resources"):
        run(subject, object())


def test_coverage_move_rejects_otherwise_preferred_reserve():
    state = raw(hp=(79, 190))
    subject = controller(state)
    # The water reserve's attacker need not be electric to know Thunderbolt.
    subject.reader.read_trainer_entry_moves = lambda _: (85, 0, 0, 0)
    with pytest.raises(RedTrainerControlError, match="entry screen"):
        subject.choose(state, lambda _: pytest.fail("unsafe active attack"))
    assert not subject.switches and subject.moves_selected == 0


def test_missing_incoming_moves_never_authorize_a_switch():
    state = raw(enemy=34)
    subject = controller(state)
    subject.reader.read_trainer_entry_moves = lambda _: None
    with pytest.raises(RedTrainerControlError, match="moves are unavailable"):
        subject.choose(state, lambda _: pytest.fail("unsafe attack"))


def test_good_active_does_not_require_privileged_reserve_observation():
    subject = controller(raw())
    subject.reader.read_trainer_entry_moves = lambda _: pytest.fail("unneeded entry read")
    assert subject.choose(raw(), lambda _: 1) == 1


def test_changed_coverage_before_switch_blocks_all_input(monkeypatch):
    subject = controller(raw(enemy=34))
    inventories = iter(((33, 0, 0, 0), (85, 0, 0, 0)))
    subject.reader.read_trainer_entry_moves = lambda _: next(inventories)
    def battle(reader, _actions, policy, **_):
        try:
            policy(reader.read())
        except control._SwitchRequest as error:
            raise BattleRuntimeError("switch boundary") from error
    monkeypatch.setattr(control, "run_adaptive_trainer_battle", battle)
    monkeypatch.setattr(control, "switch_active_battler", lambda *_a, **_k: pytest.fail("input"))
    with pytest.raises(RedTrainerControlError, match="entry screen"):
        run(subject, object())
    assert not subject.switches and subject.moves_selected == 0


@pytest.mark.parametrize("move,damage", [(49, 20), (82, 40), (101, 55)])
def test_fixed_damage_switch_executes_and_resumes_move_policy(monkeypatch, move, damage):
    state = raw(enemy=34, hp=(79, 190))
    subject = controller(state)
    subject.reader.read_trainer_entry_moves = lambda _: (move, 0, 0, 0)
    seen = []
    executor = object()

    def battle(reader, actions, policy, **kwargs):
        assert actions is executor
        kwargs["move_decision_guard"](reader.read())
        try:
            assert policy(reader.read()) == 1
        except control._SwitchRequest as error:
            raise BattleRuntimeError("switch boundary") from error
        return replace(reader.read(), battle_state=0)

    def switch(actions, reader, _emulator, index, **_):
        assert actions is executor and index == 1
        seen.append(index)
        # Simulate the incoming hit, not just the selected party cursor.
        reader.state = replace(state, active_party_index=1, active_party_species_id=28,
            party_hp=(79, 190 - damage), active_party_hp=190 - damage, active_party_max_hp=190,
            active_party_moves=state.party_moves[1], active_party_pp=state.party_pp[1])

    monkeypatch.setattr(control, "run_adaptive_trainer_battle", battle)
    monkeypatch.setattr(control, "switch_active_battler", switch)
    assert run(subject, executor).battle_state == 0
    assert seen == [1] and subject.switches == [2] and subject.moves_selected == 1


def test_surviving_entry_at_one_hp_does_not_authorize_another_attack(monkeypatch):
    state = replace(raw(enemy=34, hp=(79, 41)), party_max_hp=(160, 80))
    subject = controller(state)
    subject.reader.read_trainer_entry_moves = lambda _: (82, 0, 0, 0)
    seen = []

    def battle(reader, _actions, policy, **_):
        try:
            policy(reader.read())
        except control._SwitchRequest as error:
            raise BattleRuntimeError("switch boundary") from error
        pytest.fail("near-fainted battler attacked")

    def switch(_actions, reader, _emulator, index, **_):
        assert index == 1
        seen.append(index)
        reader.state = replace(state, active_party_index=1, active_party_species_id=28,
            party_hp=(79, 1), active_party_hp=1, active_party_max_hp=80,
            active_party_moves=state.party_moves[1], active_party_pp=state.party_pp[1])

    monkeypatch.setattr(control, "run_adaptive_trainer_battle", battle)
    monkeypatch.setattr(control, "switch_active_battler", switch)
    with pytest.raises(RedTrainerControlError, match="no healthy offensive matchup"):
        run(subject, object())
    assert seen == [1] and subject.switches == [2] and subject.moves_selected == 0


@pytest.mark.parametrize("change", ["hp", "enemy_level"])
def test_fresh_night_shade_bound_blocks_newly_lethal_switch_without_input(monkeypatch, change):
    state = replace(raw(enemy=34, hp=(79, 56)), party_max_hp=(160, 110))
    subject = controller(state)
    subject.reader.read_trainer_entry_moves = lambda _: (101, 0, 0, 0)

    def battle(reader, _actions, policy, **_):
        try:
            policy(reader.read())
        except control._SwitchRequest as error:
            reader.state = replace(state, **(
                {"party_hp": (79, 55)} if change == "hp" else {"enemy_level": 56}
            ))
            raise BattleRuntimeError("switch boundary") from error
        pytest.fail("initial safe reserve was not selected")

    monkeypatch.setattr(control, "run_adaptive_trainer_battle", battle)
    monkeypatch.setattr(control, "switch_active_battler",
                        lambda *_a, **_k: pytest.fail("unsafe input"))
    with pytest.raises(RedTrainerControlError, match="entry screen"):
        run(subject, object())
    assert not subject.switches and subject.moves_selected == 0
