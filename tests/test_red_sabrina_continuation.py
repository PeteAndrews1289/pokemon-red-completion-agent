from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_story_battle import actor

from pokemon_red_completion import red_sabrina_continuation as gym
from pokemon_red_completion.observation import Badge, EventFlag, ItemId, RawGameState
from pokemon_red_completion.red_story_battle import FrozenStoryBattleController


@pytest.mark.parametrize("fault", [None, "identity", "consumed"])
def test_cartridge_leader_contract(monkeypatch, fault):
    monkeypatch.setattr(gym, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(gym, "map_object_events", lambda *a: (
        NS(object_index=1, trainer_class=239 if fault == "identity" else 240, trainer_set=1),))
    monkeypatch.setattr(gym, "trainer_party_quote", lambda *a: NS(expected_victory_money=4257))
    raw = NS(event_flags=bytes(256), badge_bits=int(Badge.MARSH) if fault == "consumed" else 0)
    if fault:
        with pytest.raises(ValueError):
            gym.sabrina_contract(b"rom", raw)
    else:
        assert gym.sabrina_contract(b"rom", raw).trainer_identity == (240, 40, 1)


@pytest.mark.parametrize("fault", [None, "unhealed", "lost", "resource", "reward"])
@pytest.mark.parametrize("resume", [False, True])
def test_learned_gym_guards_and_rewards(monkeypatch, tmp_path, fault, resume):
    events = bytearray(256)
    events[int(EventFlag.BEAT_SILPH_CO_GIOVANNI) // 8] |= (
        1 << (int(EventFlag.BEAT_SILPH_CO_GIOVANNI) % 8))
    state = [RawGameState(True, 178 if resume else 182, 3, 3, 2, 0, event_flags=bytes(events),
                          player_money=1000, bag_items=((4, 1),), badge_bits=15)]
    contract = gym.StoryTrainerContract("defeat_sabrina", "sabrina", 178,
                                        (240, 40, 1), int(EventFlag.BEAT_SABRINA), 4257)
    controller = FrozenStoryBattleController(actor(tmp_path), (contract,))
    monkeypatch.setattr(gym, "sabrina_contract", lambda *a: contract)
    monkeypatch.setattr(gym, "_raw_party_fully_restored", lambda _: fault != "unhealed")
    calls = []

    def approach(*a, **kw):
        calls.append("approach")
        state[0] = replace(state[0], map_id=178,
                           player_money=999 if fault == "resource" else 1000)
        return {}

    monkeypatch.setattr(gym, "approach_npc", approach)
    monkeypatch.setattr(gym.silph, "_interact", lambda *a: None)
    monkeypatch.setattr(gym.silph, "_await_trainer_battle", lambda *a: None)

    def run(*a, **kw):
        calls.append("battle")
        if fault not in {"lost", "reward"}:
            updated = bytearray(state[0].event_flags)
            for event in (EventFlag.BEAT_SABRINA, EventFlag.GOT_TM46):
                updated[int(event) // 8] |= 1 << (int(event) % 8)
            state[0] = replace(state[0], event_flags=bytes(updated),
                               badge_bits=15 | int(Badge.MARSH), player_money=5257,
                               bag_items=((4, 1), (int(ItemId.TM46_PSYWAVE), 1)))
        return NS(outcome="lost" if fault == "lost" else "won", field_ready=True,
                  public_dict=lambda: {})

    monkeypatch.setattr(FrozenStoryBattleController, "run", run)
    reader = NS(read=lambda: state[0], read_input_readiness=lambda: NS(ready=True),
                read_bottom_dialogue_box_visible=lambda: False)
    kwargs = dict(rom=b"rom", controller=controller, record=lambda *a: None,
                  resume_approach=resume)
    if fault in {"unhealed", "resource", "reward"}:
        with pytest.raises((ValueError, RuntimeError)):
            gym.run_learned_sabrina(NS(pressed_buttons=()), reader, NS(), **kwargs)
        if fault in {"unhealed", "resource"}:
            assert "battle" not in calls
    else:
        result = gym.run_learned_sabrina(NS(pressed_buttons=()), reader, NS(), **kwargs)
        assert result["status"] == ("lost" if fault == "lost" else "complete")
