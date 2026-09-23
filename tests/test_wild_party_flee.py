from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import BattleMenuPhase, RawGameState
from pokemon_red_completion.route_1_wild import flee_wild
from pokemon_red_completion.wild_party_flee import validate_flee_party


def state():
    return RawGameState(
        True,
        17,
        14,
        10,
        4,
        1,
        first_party_hp=0,
        party_species_ids=(1, 2, 3, 4),
        party_levels=(24, 45, 25, 26),
        party_hp=(0, 140, 27, 63),
        party_max_hp=(40, 140, 66, 71),
        party_moves=((1, 2, 3, 4),) * 4,
        party_pp=((20, 20, 20, 20),) * 4,
        party_status=(0, 0, 0, 0),
        bag_items=(),
        player_money=4583,
        badge_bits=15,
        event_flags=bytes(320),
        active_party_index=0,
        active_party_hp=0,
        enemy_species_id=185,
        enemy_level=16,
        enemy_hp=41,
    )


@pytest.mark.parametrize("slot", [1, 2, 3])
@pytest.mark.parametrize("entry_delay", [0, 3])
def test_fainted_lead_dispatch_settles_entry_and_preserves_all_party(slot, entry_delay):
    initial = state()
    live = {"raw": initial, "waits": 0, "run": False}

    def execute(action):
        if action.kind is MacroActionKind.WAIT:
            live["waits"] += 1
            if live["waits"] >= entry_delay and not live["run"]:
                live["raw"] = replace(
                    initial, active_party_index=slot, active_party_hp=initial.party_hp[slot]
                )
        elif action.kind is MacroActionKind.CONFIRM:
            live["run"] = True
            live["raw"] = replace(live["raw"], battle_state=0, battle_result=2)
        else:
            assert action.kind is MacroActionKind.CANCEL

    if entry_delay == 0:
        live["raw"] = replace(
            initial, active_party_index=slot, active_party_hp=initial.party_hp[slot]
        )
    reader = NS(
        read=lambda: live["raw"],
        read_input_readiness=lambda: NS(ready=True),
        read_battle_menu_state=lambda raw: NS(
            phase=BattleMenuPhase.MAIN if raw.active_party_hp else BattleMenuPhase.UNKNOWN,
            selected_main_command=3,
        ),
    )
    result = flee_wild(
        NS(execute=execute),
        reader,
        initial,
        expected_map_id=17,
        route_name="test",
        stabilization_frames=24,
        error_type=RuntimeError,
    )
    assert result.verified and result.hp_scope == "whole_party" and result.run_attempts == 1
    assert result.final_hp == 230 and live["raw"].party_hp[0] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"party_hp": (0, 0, 0, 0)},
        {"party_hp": (0, 140, 0, 63)},
        {"party_hp": (1, 140, 27, 63)},
        {"party_hp": (0, 140, 28, 63)},
        {"party_pp": None},
        {"party_count": 3},
        {"party_status": (0, 0, 8, 0)},
        {"player_money": 4582},
        {"bag_items": ((1, 1),)},
        {"party_species_ids": (1, 2, 4, 3)},
        {"party_moves": ((2, 2, 3, 4),) * 4},
        {"event_flags": bytes(319) + b"x"},
    ],
)
def test_party_resource_changes_fail_closed(changes):
    with pytest.raises(ValueError):
        validate_flee_party(state(), replace(state(), **changes))


def test_all_fainted_origin_refused():
    raw = replace(state(), party_hp=(0, 0, 0, 0))
    with pytest.raises(ValueError):
        validate_flee_party(raw, raw)


def test_hp_damage_is_retained_without_allowing_new_faint():
    validate_flee_party(state(), replace(state(), party_hp=(0, 133, 27, 63)))
