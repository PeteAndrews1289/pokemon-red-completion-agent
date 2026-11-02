"""ROM-free charge/release contracts; the native packet supplies actual game evidence."""

from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, _raw
from test_observation import RecordingMemory

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleRuntimeError,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    MapId,
    PokemonRedStateReader,
    RamAddress,
)


@pytest.mark.parametrize("player,enemy", [(0x50, 0), (0, 0x50), (0x10, 0x40), (0, 0)])
def test_charge_reader_is_semantic_and_read_only(player, enemy):
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.IS_IN_BATTLE: 2,
            RamAddress.PARTY_COUNT: 1,
            RamAddress.PLAYER_BATTLE_STATUS_1: player,
            RamAddress.ENEMY_BATTLE_STATUS_1: enemy,
        }
    )
    reader = PokemonRedStateReader(memory)
    raw = reader.read()
    result = reader.read_battle_charge_state(raw)
    assert result == {
        "active": True,
        "player_charging": bool(player & 0x10),
        "player_invulnerable": bool(player & 0x40),
        "opponent_charging": bool(enemy & 0x10),
        "opponent_invulnerable": bool(enemy & 0x40),
    }
    assert reader.read() == raw


def test_charge_reader_does_not_expose_stale_outside_battle_flags():
    reader = PokemonRedStateReader(RecordingMemory({RamAddress.PLAYER_BATTLE_STATUS_1: 0x50}))
    assert reader.read_battle_charge_state(reader.read()) == {"active": False}


@pytest.mark.parametrize("move", [19, 91])
@pytest.mark.parametrize("outcome", ["hit", "miss", "faint", "paralyzed", "double_spend"])
def test_charge_waits_for_release_or_truthful_interruption(move, outcome):
    runtime = MeasuredTurnRuntime(raw=_raw(moves=(move, 33, 0, 0), pp=(1, 10, 0, 0)))
    confirms = 0

    def advance(action):
        nonlocal confirms
        if action.kind is MacroActionKind.CONFIRM:
            confirms += 1
            if confirms == 1:
                runtime.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            elif confirms in (2, 3):
                # The initial charge does not spend PP or finish the selection.
                runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            elif confirms == 4:
                runtime.menu = (
                    BattleMenuState(BattleMenuPhase.UNKNOWN)
                    if outcome == "miss"
                    else BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
                )
                if outcome == "faint":
                    runtime.raw = replace(runtime.raw, first_party_hp=0)
                elif outcome == "paralyzed":
                    runtime.raw = replace(runtime.raw, first_party_status=64)
                else:
                    runtime.raw = replace(
                        runtime.raw,
                        enemy_hp=11 if outcome == "hit" else 20,
                        first_party_pp=(0, 9 if outcome == "double_spend" else 10, 0, 0),
                    )
            elif confirms == 5 and outcome == "miss":
                runtime.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)

    runtime.on_action = advance
    kwargs = dict(
        expected_map=MapId.CERULEAN_CITY,
        selected_slot=1,
        expected_battle_state=2,
        settle_to_next_decision=True,
    )
    if outcome == "double_spend":
        with pytest.raises(BattleRuntimeError, match="PP accounting"):
            execute_bounded_battle_move_turn(runtime, runtime, **kwargs)
    else:
        result = execute_bounded_battle_move_turn(runtime, runtime, **kwargs)
        assert result.move_executed == (outcome in {"hit", "miss"})
        assert result.final_state.battler_pp == (
            (0, 10, 0, 0) if result.move_executed else (1, 10, 0, 0)
        )
    assert confirms == (5 if outcome == "miss" else 4)


def test_audit_flags_a_policy_call_during_committed_charge():
    import audit_red_two_turn_compatibility as audit

    events = [
        {
            "event": "two_turn_observed",
            "frame": 1,
            "charge": {"player_charging": True},
            "player_hp": 10,
        },
        {"event": "choice_recorded", "decision_index": 0},
    ]
    counts = audit.trace_counts(events, {"player_charge": True}, {"decisions": []})
    assert counts["choices_during_charge"] == 1


def test_frame_cost_gate_detects_slow_two_turn_wins_without_demanding_perfection():
    import run_red_two_turn_compatibility as packet

    metrics = {
        "win": True,
        "loss": False,
        "censored": False,
        "pp_spent": 1,
        "actual_frames": 100,
        "decisions": 1,
        "actual_actions": 3,
        "own_faints": 1,
        "invalid_action_failures": 0,
    }
    pair = {"admitted": metrics, "candidate": {**metrics, "actual_frames": 126}}
    assert packet.summarize([pair])["behavior_failures"] == ["actual_frames_regression"]
    pair["candidate"]["actual_frames"] = 125
    assert packet.summarize([pair])["behavior_failures"] == []


def test_trace_opt_in_is_typed_before_any_output_or_native_actions():
    import run_red_status_curriculum as lab

    with pytest.raises(ValueError, match="boolean"):
        lab.play(None, None, None, None, None, trace_two_turn=1)


def test_post_battle_healing_does_not_erase_exact_move_spend():
    from pokemon_red_completion.red_trainer_practice_episode import _episode_metrics

    step = {
        "kind": "attack",
        "state_before": {"party_pp": [[2, 10]]},
        "state_after": {"party_pp": [[10, 10]]},
        "outcome": {"move_executed": True},
    }
    result = _episode_metrics((step,))
    assert result["party_pp_spent"] == 0  # historical net endpoint measure
    assert result["selected_move_pp_spends"] == 1
    step["outcome"]["move_executed"] = False
    assert _episode_metrics((step,))["selected_move_pp_spends"] == 0


def test_charge_audit_uses_live_proof_before_terminal_healing():
    import audit_red_two_turn_compatibility as audit

    decision = {
        "kind": "attack",
        "decision_index": 0,
        "move_slot": 1,
        "observation": {
            "features": {
                "party": {
                    "lead": {
                        "moves": [{"slot_index": 0, "move_ref": "pokemon.red.gb.us.rev0:move:091"}]
                    }
                }
            }
        },
        "state_before": {"active_party_slot": 1, "active_pp": [2, 10]},
        "state_after": {"active_party_slot": None, "active_pp": [10, 10]},
        "outcome": {"move_executed": True, "battle_exited": True},
        "opponent_hp_before": 10,
        "opponent_hp_after": 0,
    }
    events = [{"event": "choice_recorded", "decision_index": 0}]
    for frame, active, charging, pp in [
        (1, True, True, [2, 10]),
        (2, True, False, [1, 10]),
        (3, False, False, [10, 10]),
    ]:
        events.append(
            {
                "event": "two_turn_observed",
                "frame": frame,
                "charge": {"active": active, "player_charging": charging},
                "player_hp": 10,
                "player_slot": 0,
                "player_pp": pp,
            }
        )
    events.append({"event": "decision_completed"})
    counts = audit.trace_counts(events, {"player_charge": True}, {"decisions": [decision]})
    assert counts["charge_spent_pp"] == counts["observed_charge_release"] == 1
