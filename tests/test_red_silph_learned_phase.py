from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_story_battle import actor, contract

from pokemon_red_completion import red_silph_learned_phase as phase
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.red_story_battle import FrozenStoryBattleController


@pytest.mark.parametrize("fault", [None, "lost", "unresolved", "scope", "card_key", "cash", "bag"])
def test_phase_runs_one_learned_boundary_and_never_falls_back(monkeypatch, tmp_path, fault):
    raw = RawGameState(
        True,
        int(MapId.SAFFRON_POKECENTER),
        3,
        3,
        2,
        0,
        party_hp=(50, 40),
        party_max_hp=(50, 40),
        party_status=(0, 0),
        party_species_ids=(28, 64),
        party_pp=((25, 0, 0, 0),) * 2,
        player_money=13420,
        bag_items=((4, 1),),
        event_flags=bytes(4),
    )
    state = [raw]
    calls = []
    records = []
    reader = NS(
        read=lambda: state[0],
        read_input_readiness=lambda: NS(ready=True),
        read_pokedex_state=lambda: NS(owned_species={7, 8, 9}),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    emulator = NS(frame_count=0, pressed_buttons=frozenset())
    c = contract(210)
    controller = FrozenStoryBattleController(actor(tmp_path), (c,))
    monkeypatch.setattr(phase, "silph_card_key_battle_contract", lambda *a: c)
    monkeypatch.setattr(phase, "_raw_party_fully_restored", lambda _: True)

    def approach(*a):
        calls.append("navigation")
        state[0] = replace(raw, map_id=210, battle_state=2)

    monkeypatch.setattr(phase, "_approach_first_silph_battle", approach)

    def run(*a, **kw):
        calls.append("model")
        state[0] = replace(
            state[0], battle_state=0, player_money=13900, event_flags=bytes((0, 1, 0, 0))
        )
        outcome = fault if fault in {"lost", "unresolved"} else "won"
        return NS(
            outcome=outcome,
            field_ready=outcome != "unresolved",
            final_state=state[0],
            public_dict=lambda: {"outcome": outcome},
            episode=NS(decisions=({},)),
        )

    controller.run = run

    def collect(*a):
        calls.append("pickup")
        state[0] = replace(state[0], bag_items=raw.bag_items + ((int(ItemId.CARD_KEY), 1),))
        if fault == "card_key":
            state[0] = replace(state[0], bag_items=raw.bag_items)
        if fault == "cash":
            state[0] = replace(state[0], player_money=0)
        if fault == "bag":
            state[0] = replace(state[0], bag_items=((int(ItemId.CARD_KEY), 1),))

    monkeypatch.setattr(phase, "_collect_silph_card_key", collect)
    if fault == "scope":
        controller.contracts = (replace(c, victory_money=1),)

    def execute():
        return phase.run_learned_silph_card_key_phase(
            emulator,
            reader,
            NS(execute=lambda _: None),
            rom=b"rom",
            controller=controller,
            record=lambda *a: records.append(a),
        )

    if fault in {"scope", "card_key", "cash", "bag"}:
        with pytest.raises((ValueError, RuntimeError)):
            execute()
        if fault == "scope":
            assert not calls
    else:
        result = execute()
        assert result["status"] == (fault or "complete")
        assert calls == (["navigation", "model"] if fault else ["navigation", "model", "pickup"])
        assert records[1][0] == "story-battle-completion"
