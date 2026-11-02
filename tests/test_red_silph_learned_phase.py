from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_story_battle import actor, contract

from pokemon_red_completion import red_silph_learned_phase as phase
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.red_story_battle import FrozenStoryBattleController


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "lost",
        "unresolved",
        "scope",
        "card_key",
        "cash",
        "bag",
        "poison_tick",
        "poison_faint",
        "poison_unchanged",
        "healthy_hp_loss",
        "healthy_heal",
        "poison_heal",
        "poison_cure",
        "poison_status_change",
        "poison_other_member_damage",
        "poison_faint_status_retained",
        "new_poison",
        "pp",
        "levels",
        "moves",
        "max_hp",
        "party_count",
        "species",
        "pokedex",
        "trainer_flag",
        "held_button",
        "not_ready",
    ],
)
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
        party_levels=(30, 29),
        party_moves=((33, 0, 0, 0),) * 2,
        party_pp=((25, 0, 0, 0),) * 2,
        player_money=13420,
        bag_items=((4, 1),),
        event_flags=bytes(4),
    )
    state = [raw]
    calls = []
    records = []
    owned = [{7, 8, 9}]
    ready = [True]
    reader = NS(
        read=lambda: state[0],
        read_input_readiness=lambda: NS(ready=ready[0]),
        read_pokedex_state=lambda: NS(owned_species=owned[0]),
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
            state[0],
            battle_state=0,
            player_money=13900,
            event_flags=bytes((0, 1, 0, 0)),
            party_hp=(48, 40),
            party_status=(8 if str(fault).startswith("poison_") else 0, 0),
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
        changes = {
            "poison_tick": dict(party_hp=(46, 40)),
            "poison_faint": dict(party_hp=(0, 40), party_status=(0, 0)),
            "healthy_hp_loss": dict(party_hp=(47, 40)),
            "healthy_heal": dict(party_hp=(49, 40)),
            "poison_heal": dict(party_hp=(49, 40)),
            "poison_cure": dict(party_hp=(47, 40), party_status=(0, 0)),
            "poison_status_change": dict(party_hp=(47, 40), party_status=(16, 0)),
            "poison_other_member_damage": dict(party_hp=(47, 39)),
            "poison_faint_status_retained": dict(party_hp=(0, 40)),
            "new_poison": dict(party_hp=(47, 40), party_status=(8, 0)),
            "pp": dict(party_pp=((24, 0, 0, 0), raw.party_pp[1])),
            "levels": dict(party_levels=(31, 29)),
            "moves": dict(party_moves=((45, 0, 0, 0), raw.party_moves[1])),
            "max_hp": dict(party_max_hp=(51, 40)),
            "party_count": dict(party_count=1),
            "species": dict(party_species_ids=(29, 64)),
            "trainer_flag": dict(event_flags=bytes(4)),
        }
        state[0] = replace(state[0], **changes.get(fault, {}))
        if fault == "pokedex":
            owned[0].add(10)
        if fault == "held_button":
            emulator.pressed_buttons = frozenset({"a"})
        if fault == "not_ready":
            ready[0] = False

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

    complete = {None, "poison_tick", "poison_faint", "poison_unchanged"}
    if fault not in complete | {"lost", "unresolved"}:
        with pytest.raises((ValueError, RuntimeError)):
            execute()
        if fault == "scope":
            assert not calls
    else:
        result = execute()
        assert result["status"] == ("complete" if fault in complete else fault)
        assert calls == (
            ["navigation", "model", "pickup"] if fault in complete else ["navigation", "model"]
        )
        assert records[1][0] == "story-battle-completion"
        if fault in complete:
            assert result["field_poison_hp_lost"] == {"poison_tick": 2, "poison_faint": 48}.get(
                fault, 0
            )
            assert not result["chapter_complete"]
