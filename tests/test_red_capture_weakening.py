from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.observation import (
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    SemanticStateError,
)
from pokemon_red_completion.red_capture_weakening import safe_special_capture_move


def raw(**changes):
    return replace(
        RawGameState(
            True,
            23,
            10,
            61,
            4,
            1,
            active_party_index=0,
            active_party_level=47,
            enemy_hp=140,
            active_party_moves=(44, 55, 58, 61),
            active_party_pp=(25, 25, 10, 20),
        ),
        **changes,
    )


def test_only_proven_nonlethal_pure_special_move():
    inputs = (110, 44, ("water",), ("normal",))
    slot, upper = safe_special_capture_move(raw(), inputs)
    assert slot == 2 and 0 < upper < 140
    assert safe_special_capture_move(raw(enemy_hp=upper), inputs) is None
    assert safe_special_capture_move(raw(active_party_pp=(25, 0, 10, 20)), inputs) is None
    assert (
        safe_special_capture_move(raw(player_disabled_move_slot=2, player_disable_turns=1), inputs)
        is None
    )
    assert safe_special_capture_move(raw(), (110, 44, ("water",), ("water",))) is not None


@pytest.mark.parametrize(
    "fault", [None, "stale", "trainer", "transform", "confusion", "zero", "converted"]
)
def test_adapter_uses_max_attack_min_defense_and_rejects_unsafe(monkeypatch, fault):
    state = raw(battle_state=2 if fault == "trainer" else 1)
    memory = {int(RamAddress.PARTY_MON_1) + 5: 21, int(RamAddress.PARTY_MON_1) + 6: 21}
    for i in (0, 1):
        memory[int(RamAddress.BATTLE_MON_ATTACK) - 12 + i] = 0 if fault == "converted" else 21
    if fault == "confusion":
        memory[int(RamAddress.PLAYER_BATTLE_STATUS_1)] = 128
    reader = PokemonRedStateReader(NS(read_u8=lambda address: memory.get(int(address), 0)))
    monkeypatch.setattr(
        reader, "read", lambda: replace(state, enemy_hp=139) if fault == "stale" else state
    )
    monkeypatch.setattr(
        reader,
        "read_wild_capture_identity",
        lambda: NS(transformed=fault == "transform", type_ids=(0, 0)),
    )
    values = {
        int(RamAddress.PARTY_MON_1) + 42: 100,
        int(RamAddress.BATTLE_MON_SPECIAL): 110,
        int(RamAddress.ENEMY_SPECIAL): 88,
        int(RamAddress.ENEMY_UNMODIFIED_SPECIAL): 0 if fault == "zero" else 44,
    }
    monkeypatch.setattr(reader, "_read_u16_be", lambda address: values[int(address)])
    if fault and fault != "converted":
        with pytest.raises(SemanticStateError):
            reader.read_wild_special_damage_inputs(state)
    else:
        own_type = "normal" if fault == "converted" else "water"
        assert reader.read_wild_special_damage_inputs(state) == (110, 44, (own_type,), ("normal",))


def test_capture_runtime_abstention_cancels_move_menu(monkeypatch):
    from pokemon_red_completion import fuchsia
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.observation import BattleMenuPhase

    state = raw(active_party_hp=100, active_party_max_hp=100)
    reader = NS(
        read=lambda: state,
        read_battle_menu_state=lambda _: NS(phase=BattleMenuPhase.MOVE, selected_move_slot=1),
    )
    monkeypatch.setattr(fuchsia, "_bag", lambda _: {3: 29})
    calls = []

    def pulse(actions, kind, **kwargs):
        calls.append(kind)
        raise StopIteration

    monkeypatch.setattr(fuchsia, "_pulse", pulse)
    monkeypatch.setattr(
        fuchsia, "_snorlax_move_slot", lambda _: pytest.fail("teacher attack fallback")
    )
    with pytest.raises(StopIteration):
        fuchsia._run_wild_capture(
            NS(),
            reader,
            NS(),
            23,
            fuchsia.DEFAULT_FUCHSIA_TIMING,
            (28,),
            weakening_selector=lambda _: None,
        )
    assert calls == [MacroActionKind.CANCEL]
