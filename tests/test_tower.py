from __future__ import annotations

from dataclasses import fields, replace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _normalized_run_actions,
    _unknown_flee_action,
)
from pokemon_red_completion.observation import EventFlag, MapId, RamAddress, RawGameState
from pokemon_red_completion.tower import (
    DEFAULT_TOWER_TIMING,
    OPTIONAL_EVENTS,
    REQUIRED_EVENTS,
    ROUTE_8_EAST_GOAL,
    ROUTE_8_SAFE_ROW_MASKS,
    TOWER_5F_MIN_SUPER_POTION_RESERVE,
    TOWER_6F_PAIR_FIELD_RECOVERY_HP_THRESHOLD,
    TOWER_CHECKPOINT_COUNT,
    TOWER_FINAL_PARTY,
    TOWER_LAVENDER_TIMING,
    TOWER_RIVAL_FIELD_RECOVERY_HP_THRESHOLD,
    TOWER_RIVAL_IVYSAUR,
    TOWER_ROCKET_FIELD_RECOVERY_HP_THRESHOLD,
    TowerBattleEvidence,
    TowerChapterReport,
    TowerCheckpoint,
    TowerTiming,
    _observe_protected_party,
    _plan_route_8_east,
    _route_8_coordinate_is_safe,
    _RunState,
    _scripted_trainer_identity,
    _tower_rival_needs_accuracy_reset,
    party_core_intact,
)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.LAVENDER_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        party_species_ids=(0x1C, 0x40, 0x3B),
        first_party_hp=111,
        first_party_max_hp=111,
        first_party_status=0,
    )


def _report() -> TowerChapterReport:
    raw = _raw()
    sets = (5, 10, 14, 19, 21, 20, None, 19, 20, 21)
    spent = (13, 3, 2, 4, 2, 2, 1, 7, 5, 6)
    events = tuple(int(item) for item in REQUIRED_EVENTS[:10])
    return TowerChapterReport(
        records=tuple(
            TowerCheckpoint(f"gate_{index}", f"Gate {index}", raw)
            for index in range(TOWER_CHECKPOINT_COUNT)
        ),
        battles=tuple(
            TowerBattleEvidence(
                f"battle {index}",
                0x91
                if trainer_set is None
                else 0xF2
                if index == 0
                else 0xF5
                if index < 6
                else 0xE6,
                None
                if trainer_set is None
                else 0x2A
                if index == 0
                else 0x2D
                if index < 6
                else 0x1E,
                trainer_set,
                events[index],
                0x3D if 1 <= index <= 6 else 0x2C,
                spent[index],
                30 if trainer_set is None else None,
            )
            for index, trainer_set in enumerate(sets)
        ),
        final_raw=raw,
        optional_events=(False,) * len(OPTIONAL_EVENTS),
        required_events=(True,) * len(REQUIRED_EVENTS),
        x_accuracy_carried=True,
        rare_candy_used_for_evolution=True,
        elixir_carried=True,
        poke_flute_carried=True,
        evolution_before=(0xB3, 0x40, 0x3B),
        evolution_after=(0x1C, 0x40, 0x3B),
        evolution_moves_preserved=True,
        purified_zone_event=True,
        purified_heals=3,
        super_potions_used=3,
        super_potions_remaining=3,
        super_potion_inventory_path=(6, 5, 4, 3),
        party_hp=(111, 52, 37),
        party_max_hp=(111, 52, 37),
        party_status=(0, 0, 0),
        money_before=10_814,
        money_remaining=18_139,
        frames_executed=100,
        actions_executed=50,
        controller_released=True,
    )


def test_tower_timing_is_positive_and_bounded() -> None:
    assert TowerTiming() == DEFAULT_TOWER_TIMING
    assert all(
        isinstance(getattr(DEFAULT_TOWER_TIMING, field.name), int)
        and getattr(DEFAULT_TOWER_TIMING, field.name) > 0
        for field in fields(TowerTiming)
    )
    assert DEFAULT_LAVENDER_TIMING.flee_pulses == 20
    assert TOWER_LAVENDER_TIMING.flee_pulses == 64
    assert TOWER_RIVAL_FIELD_RECOVERY_HP_THRESHOLD == 55
    assert TOWER_5F_MIN_SUPER_POTION_RESERVE == 1
    assert TOWER_6F_PAIR_FIELD_RECOVERY_HP_THRESHOLD == 40
    assert TOWER_ROCKET_FIELD_RECOVERY_HP_THRESHOLD == 30
    assert _unknown_flee_action(cancel_for_safety=True) is MacroActionKind.CANCEL
    assert _normalized_run_actions(TOWER_LAVENDER_TIMING) == (
        (MacroActionKind.CANCEL, None, TOWER_LAVENDER_TIMING.wait_frames),
        (MacroActionKind.MOVE, "down", TOWER_LAVENDER_TIMING.wait_frames),
        (MacroActionKind.MOVE, "right", TOWER_LAVENDER_TIMING.wait_frames),
        (MacroActionKind.CONFIRM, None, 240),
    )


def test_tower_rival_resets_inherited_accuracy_loss_against_ivysaur_once() -> None:
    rival = replace(
        _raw(),
        battle_state=2,
        active_party_index=0,
        enemy_species_id=TOWER_RIVAL_IVYSAUR,
        player_accuracy_stage=6,
    )

    assert _tower_rival_needs_accuracy_reset(
        rival,
        battle_plan_id=RedBattlePlanId.TOWER_RIVAL,
        reset_complete=False,
    )
    assert not _tower_rival_needs_accuracy_reset(
        replace(rival, player_accuracy_stage=7),
        battle_plan_id=RedBattlePlanId.TOWER_RIVAL,
        reset_complete=False,
    )
    assert not _tower_rival_needs_accuracy_reset(
        rival,
        battle_plan_id=RedBattlePlanId.TOWER_RIVAL,
        reset_complete=True,
    )


def test_route_8_planner_uses_the_source_derived_trainer_safe_map() -> None:
    assert len(ROUTE_8_SAFE_ROW_MASKS) == 18
    route = _plan_route_8_east((13, 5))
    assert "".join(direction[0].upper() for direction in route) == (
        "RRRDDDDDDDRRRRRRRRRRRRUUUUURURRRRRRRRRRRR"
        "DRRRRRDDDDDRRRRDRRRRRUUUUURRRR"
    )
    coordinate = (13, 5)
    deltas = {"up": (0, -1), "left": (-1, 0), "right": (1, 0), "down": (0, 1)}
    for direction in route:
        dx, dy = deltas[direction]
        coordinate = (coordinate[0] + dx, coordinate[1] + dy)
        assert _route_8_coordinate_is_safe(coordinate)
    assert coordinate == ROUTE_8_EAST_GOAL
    assert not _route_8_coordinate_is_safe((51, 12))


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_tower_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(TowerTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_TOWER_TIMING, **{field.name: invalid})


def test_tower_report_requires_every_terminal_gate() -> None:
    report = _report()
    assert report.passed
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, battles=report.battles[:-1]),
        replace(report, optional_events=(True,) + report.optional_events[1:]),
        replace(report, required_events=(False,) + report.required_events[1:]),
        replace(report, x_accuracy_carried=False),
        replace(report, elixir_carried=False),
        replace(report, poke_flute_carried=False),
        replace(report, evolution_after=(0xB3, 0x40, 0x3B)),
        replace(report, evolution_moves_preserved=False),
        replace(report, purified_zone_event=False),
        replace(report, purified_heals=2),
        replace(report, super_potions_remaining=1),
        replace(report, party_hp=(110, 52, 37)),
        replace(report, money_before=-1),
        replace(report, money_remaining=23_338),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_tower_report_accepts_natural_evolution_without_spending_rare_candy() -> None:
    report = replace(_report(), rare_candy_used_for_evolution=False)

    assert report.passed


def test_tower_report_accepts_blastoise_that_evolved_before_tower() -> None:
    report = replace(
        _report(),
        rare_candy_used_for_evolution=False,
        evolution_before=TOWER_FINAL_PARTY,
    )

    assert report.passed


def test_tower_guard_learns_a_natural_mid_chapter_evolution() -> None:
    run = _RunState()
    evolved = replace(_raw(), party_species_ids=TOWER_FINAL_PARTY, first_party_hp=78)

    assert _observe_protected_party(run, evolved)
    assert run.evolved


def test_tower_report_accepts_a_conserved_surplus_inventory_path() -> None:
    report = replace(
        _report(),
        super_potions_used=3,
        super_potions_remaining=4,
        super_potion_inventory_path=(7, 6, 5, 4),
    )

    assert report.passed


def test_tower_report_requires_selected_move_evidence_and_marowak_level() -> None:
    report = _report()
    wrong_count = replace(
        report,
        battles=(
            replace(report.battles[0], selected_pp_spent=0),
            *report.battles[1:],
        ),
    )
    wrong_marowak = replace(
        report,
        battles=(
            *report.battles[:6],
            replace(report.battles[6], enemy_level=29),
            *report.battles[7:],
        ),
    )
    assert not wrong_count.passed
    assert not wrong_marowak.passed


def test_tower_public_report_discloses_route_assistance() -> None:
    public = _report().public_dict()
    assert public["status"] == "ok"
    assert public["objective"] == "rescue_fuji"
    assert public["optional_trainers_bypassed"] == 8
    assert public["purified_zone"] == {"event_set": True, "full_party_heals": 3}
    assert public["required_pickups"] == {
        "x_accuracy": True,
        "rare_candy": True,
        "elixir": True,
        "poke_flute": True,
    }


def test_tower_event_addresses_match_pinned_source_symbols() -> None:
    assert EventFlag.BEAT_POKEMON_TOWER_RIVAL == 0x0EF
    assert EventFlag.BEAT_GHOST_MAROWAK == 0x10F
    assert EventFlag.RESCUED_MR_FUJI == 0x117
    assert EventFlag.GOT_POKE_FLUTE == 0x128
    assert EventFlag.RESCUED_MR_FUJI_WORLD == 0x4CF


def test_scripted_rival_identity_ignores_stale_engaged_set() -> None:
    class Memory:
        values = {
            RamAddress.CURRENT_OPPONENT: 0xF2,
            RamAddress.TRAINER_CLASS: 0x2A,
            RamAddress.TRAINER_NUMBER: 5,
            RamAddress.ENGAGED_TRAINER_SET: 7,
        }

        def read_u8(self, address: int) -> int:
            return self.values[address]

    assert _scripted_trainer_identity(Memory()) == (0xF2, 0x2A, 5)


def test_party_core_intact_detects_loss_reorder_and_substitution() -> None:
    """The guard must still catch every failure exact equality caught."""

    assert party_core_intact(TOWER_FINAL_PARTY)
    assert not party_core_intact(None)
    assert not party_core_intact(())
    # a lost member
    assert not party_core_intact(TOWER_FINAL_PARTY[:2])
    # a reordered core
    assert not party_core_intact((TOWER_FINAL_PARTY[1], TOWER_FINAL_PARTY[0], TOWER_FINAL_PARTY[2]))
    # a substituted member
    assert not party_core_intact((TOWER_FINAL_PARTY[0], 0x99, TOWER_FINAL_PARTY[2]))
    # an unevolved lead
    assert not party_core_intact((0xB3, TOWER_FINAL_PARTY[1], TOWER_FINAL_PARTY[2]))


def test_party_core_intact_allows_the_balanced_roster_to_recruit() -> None:
    """Appending members must not trip a guard that exists to catch losses."""

    assert party_core_intact((*TOWER_FINAL_PARTY, 0x84))
    assert party_core_intact((*TOWER_FINAL_PARTY, 0x84, 0x68, 0x2B))
    assert party_core_intact((TOWER_FINAL_PARTY[0], TOWER_FINAL_PARTY[1], 0x76))
    # growth still cannot hide damage to the core
    assert not party_core_intact((TOWER_FINAL_PARTY[0], 0x84, TOWER_FINAL_PARTY[2]))


def test_party_core_intact_accepts_an_explicit_core() -> None:
    assert party_core_intact((0x1C, 0x84), core=(0x1C,))
    assert not party_core_intact((0x84, 0x1C), core=(0x1C,))
