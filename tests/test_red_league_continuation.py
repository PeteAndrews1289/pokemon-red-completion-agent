from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_league_continuation as continuation
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState
from pokemon_red_completion.red_learned_league import FrozenLeagueController


@pytest.mark.parametrize("failure", [None, "identity", "faint", "bag", "payout", "not_active"])
def test_exact_league_continuation_preserves_guards_and_does_not_reenter(monkeypatch, failure):
    before = RawGameState(
        game_started=True,
        map_id=MapId.LORELEIS_ROOM,
        player_y=3,
        player_x=5,
        party_count=1,
        party_species_ids=(28,),
        party_hp=(50,),
        bag_items=(),
        player_money=573,
        badge_bits=255,
        battle_state=0 if failure == "not_active" else 2,
        event_flags=bytes(320),
    )
    state = [before]
    calls = []
    reader = SimpleNamespace(
        read=lambda: state[0],
        read_active_trainer_identity=lambda: (244, 44, 2 if failure == "identity" else 1),
        read_input_readiness=lambda: SimpleNamespace(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    adapter = SimpleNamespace(
        observe=lambda: SimpleNamespace(raw=state[0], collection_observation="ledger")
    )
    runtime = SimpleNamespace(
        reader=reader, adapter=adapter, emulator=SimpleNamespace(frame_count=0)
    )
    actions = SimpleNamespace(
        actions_executed=0, execute=lambda action: pytest.fail("unexpected input")
    )
    quote = SimpleNamespace(opponent_id=244, trainer_set=1, expected_victory_money=100)
    monkeypatch.setattr(continuation, "_room_quote", lambda *args: quote)
    monkeypatch.setattr(continuation, "dependency_specimen_ledger", lambda obs: obs)

    def play(_reader, _actions, **kwargs):
        calls.append("model")
        assert kwargs["resume"] and kwargs["require_win"] and type(kwargs["expected_map"]) is int
        assert kwargs["maximum_decisions"] == 59
        kwargs["decision_guard"](state[0])
        if failure == "faint":
            state[0] = replace(before, party_hp=(0,))
            kwargs["decision_guard"](state[0])
        if failure == "bag":
            state[0] = replace(before, bag_items=((1, 1),))
            kwargs["decision_guard"](state[0])
        events = bytearray(before.event_flags)
        event = int(EventFlag.BEAT_LORELEI)
        events[event // 8] |= 1 << (event % 8)
        state[0] = replace(
            before,
            battle_state=0,
            battle_result=0,
            event_flags=bytes(events),
            player_money=573 if failure == "payout" else 673,
        )
        actions.actions_executed = 3
        runtime.emulator.frame_count = 40

    monkeypatch.setattr(
        continuation,
        "learned_league_controller",
        lambda rt: FrozenLeagueController(SimpleNamespace(_play=play)),
    )
    if failure:
        with pytest.raises(ValueError):
            continuation.continue_league_room_battle(
                runtime,
                actions,
                SimpleNamespace(rom=b"rom"),
                "defeat_lorelei",
                maximum_decisions=59,
            )
        assert bool(calls) is (failure not in {"identity", "not_active"})
    else:
        result = continuation.continue_league_room_battle(
            runtime, actions, SimpleNamespace(rom=b"rom"), "defeat_lorelei", maximum_decisions=59
        )
        assert (
            result.money_after - result.money_before == 100
            and result.actions == 3
            and result.frames == 40
        )
