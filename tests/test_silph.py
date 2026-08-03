from dataclasses import fields, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import Badge, EventFlag, ItemId, MapId, RawGameState
from pokemon_red_completion.silph import (
    BATTLE_ITEM_SETTLE_PULSES,
    DEFAULT_SILPH_TIMING,
    MART_2F_GIRL_X,
    MART_2F_GIRL_Y,
    ROOF_GIRL_X,
    ROOF_GIRL_Y,
    ROOF_NERD_X,
    ROOF_NERD_Y,
    ROUTE_7_CONNECTION_TO_GATE,
    SAFFRON_CENTER_APPROACH,
    SAFFRON_WARP_COORDINATES,
    SILPH_CHECKPOINT_COUNT,
    SILPH_PC_DEPOSIT_ITEMS,
    THIRD_FLOOR_GUARD,
    SilphChapterReport,
    SilphCheckpoint,
    SilphTiming,
    _interact_with_roof_girl,
    _mart_2f_girl_coordinate,
    _move_verified,
    _plan_saffron_center_approach,
    _plan_saffron_route,
    _silph_capacity_ready,
    _silph_rival_move_slot,
)
from pokemon_red_completion.tower import TOWER_FINAL_PARTY


def _terminal() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL),
        party_species_ids=TOWER_FINAL_PARTY,
        first_party_level=45,
        first_party_hp=139,
        first_party_max_hp=139,
        first_party_status=0,
        first_party_moves=(0x82, 0x46, 0x3A, 0x39),
        first_party_pp=(15, 15, 10, 15),
    )


def _report() -> SilphChapterReport:
    raw = _terminal()
    events = (
        EventFlag.BEAT_SILPH_CO_5F_TRAINER_0,
        EventFlag.BEAT_SILPH_CO_3F_TRAINER_0,
        EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2,
        EventFlag.BEAT_SILPH_CO_RIVAL,
        EventFlag.BEAT_SILPH_CO_11F_TRAINER_0,
        EventFlag.SILPH_CO_11_UNLOCKED_DOOR,
        EventFlag.BEAT_SILPH_CO_GIOVANNI,
        EventFlag.GOT_MASTER_BALL,
    )
    return SilphChapterReport(
        records=tuple(
            SilphCheckpoint(str(index), str(index), raw) for index in range(SILPH_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        money_before=32_047,
        money_after=30_096,
        tm13_event=True,
        tm13_preinstalled=False,
        tm13_transfer_before_event=True,
        other_roof_rewards_untouched=True,
        fresh_water_after_reward=0,
        tm13_after_teaching=0,
        upgraded_moves=(0x82, 0x46, 0x3A, 0x39),
        upgraded_pp=(15, 15, 10, 15),
        rival_potions_used=0,
        rival_x_special_used=1,
        hyper_potions_remaining=7,
        max_repel_remaining=0,
        route_items_archived=True,
        card_key_quantity=1,
        master_ball_quantity=1,
        required_events=tuple((int(event), True) for event in events),
        lapras_flag_before=0x0E,
        lapras_flag_after=0x0E,
        party_hp=(139, 52, 37),
        party_max_hp=(139, 52, 37),
        party_status=(0, 0, 0),
        controller_released=True,
        frames_executed=1,
        actions_executed=1,
    )


def test_silph_timing_is_positive_and_bounded() -> None:
    assert SILPH_PC_DEPOSIT_ITEMS == (ItemId.SS_TICKET, ItemId.LIFT_KEY, ItemId.HELIX_FOSSIL)
    assert BATTLE_ITEM_SETTLE_PULSES == 720
    for field in fields(SilphTiming):
        assert getattr(DEFAULT_SILPH_TIMING, field.name) > 0
        with pytest.raises(ValueError, match=field.name):
            replace(DEFAULT_SILPH_TIMING, **{field.name: 0})


def test_silph_capacity_accepts_a_consumed_recovery_stack() -> None:
    route_items = {item: 1 for item in SILPH_PC_DEPOSIT_ITEMS}

    assert _silph_capacity_ready({**route_items, **{1000 + index: 1 for index in range(15)}})
    assert _silph_capacity_ready({**route_items, **{1000 + index: 1 for index in range(16)}})
    assert not _silph_capacity_ready(
        {**route_items, **{1000 + index: 1 for index in range(17)}}
    )
    assert not _silph_capacity_ready(
        {item: quantity for item, quantity in route_items.items() if item is not ItemId.SS_TICKET}
    )


def test_mart_2f_customer_coordinate_uses_the_pinned_fourth_object_slot() -> None:
    class Emulator:
        def read_u8(self, address: int) -> int:
            return {MART_2F_GIRL_X: 18, MART_2F_GIRL_Y: 7}[address]

    assert _mart_2f_girl_coordinate(Emulator()) == (14, 3)  # type: ignore[arg-type]


def test_silph_verified_movement_retries_a_swallowed_input() -> None:
    states = iter(
        (
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=2, player_y=5),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=2, player_y=5),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=2, player_y=5),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=2, player_y=5),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=3, player_y=5),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=3, player_y=5),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=3, player_y=6),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=3, player_y=6),
            replace(_terminal(), map_id=MapId.SAFFRON_MART, player_x=3, player_y=7),
        )
    )

    class Reader:
        def read(self) -> RawGameState:
            return next(states)

    class Executor:
        def execute(self, _action: object) -> None:
            return None

    final = _move_verified(
        Executor(),  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        ("right", "down", "down"),
        replace(DEFAULT_SILPH_TIMING, movement_frames=1),
        "test route",
    )

    assert (final.map_id, final.player_x, final.player_y) == (MapId.SAFFRON_MART, 3, 7)


def test_silph_saffron_planner_detours_around_discovered_npc() -> None:
    direct = _plan_saffron_center_approach((25, 12))
    assert len(direct) == 34
    assert direct[0] == "left"

    blocked = frozenset({(20, 12)})
    detour = _plan_saffron_center_approach((25, 12), blocked)
    coordinate = (25, 12)
    deltas = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    visited = {coordinate}
    for direction in detour:
        dx, dy = deltas[direction]
        coordinate = (coordinate[0] + dx, coordinate[1] + dy)
        visited.add(coordinate)

    assert coordinate == SAFFRON_CENTER_APPROACH
    assert blocked.isdisjoint(visited)


def test_silph_saffron_planner_supports_gym_target() -> None:
    route = _plan_saffron_route((9, 30), (34, 4), frozenset({(18, 30)}))
    coordinate = (9, 30)
    deltas = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    visited = {coordinate}
    for direction in route:
        dx, dy = deltas[direction]
        coordinate = (coordinate[0] + dx, coordinate[1] + dy)
        visited.add(coordinate)

    assert coordinate == (34, 4)
    assert SAFFRON_WARP_COORDINATES.isdisjoint(visited)


def test_route_7_return_uses_reversible_lower_corridor() -> None:
    coordinate = (0, 3)
    deltas = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    visited = {coordinate}
    for direction in ROUTE_7_CONNECTION_TO_GATE:
        dx, dy = deltas[direction]
        coordinate = coordinate[0] + dx, coordinate[1] + dy
        visited.add(coordinate)

    assert coordinate == (11, 10)
    assert (9, 3) not in visited
    assert (4, 8) in visited


def test_silph_rival_policy_uses_live_disable_and_pp() -> None:
    surf_disabled = replace(
        _terminal(),
        enemy_species_id=0x10,
        first_party_pp=(15, 15, 10, 15),
        player_disabled_move_slot=4,
        player_disable_turns=3,
    )
    assert _silph_rival_move_slot(surf_disabled) == 2

    ice_beam_disabled = replace(
        surf_disabled,
        enemy_species_id=154,
        player_disabled_move_slot=3,
    )
    assert _silph_rival_move_slot(ice_beam_disabled) == 4

    surf_empty = replace(
        surf_disabled,
        player_disabled_move_slot=0,
        player_disable_turns=0,
        first_party_pp=(15, 15, 10, 0),
    )
    assert _silph_rival_move_slot(surf_empty) == 2

    transformed_water_flying_matchup = replace(
        surf_disabled,
        enemy_species_id=22,
        player_disabled_move_slot=0,
        player_disable_turns=0,
    )
    assert _silph_rival_move_slot(transformed_water_flying_matchup) == 3


def test_roof_girl_interaction_retries_until_dialogue_opens() -> None:
    raw = replace(
        _terminal(),
        map_id=MapId.CELADON_MART_ROOF,
        player_x=4,
        player_y=5,
    )

    class Reader:
        readiness_calls = 0

        def read(self) -> RawGameState:
            return raw

        def read_input_readiness(self) -> object:
            self.readiness_calls += 1
            return SimpleNamespace(ready=self.readiness_calls == 1)

    class Emulator:
        def read_u8(self, address: int) -> int:
            return {
                ROOF_GIRL_X: 9,
                ROOF_GIRL_Y: 9,
                ROOF_NERD_X: 14,
                ROOF_NERD_Y: 8,
            }[address]

    class Executor:
        def __init__(self) -> None:
            self.actions: list[object] = []

        def execute(self, action: object) -> None:
            self.actions.append(action)

    executor = Executor()
    _interact_with_roof_girl(
        executor,  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        Emulator(),  # type: ignore[arg-type]
        replace(DEFAULT_SILPH_TIMING, movement_frames=1, menu_frames=1),
        reward_started=lambda: False,
    )

    interactions = sum(
        getattr(action, "kind", None) is MacroActionKind.INTERACT
        for action in executor.actions
    )
    assert interactions == 2


def test_roof_girl_interaction_accepts_reward_evidence_when_readiness_stays_true() -> None:
    raw = replace(
        _terminal(),
        map_id=MapId.CELADON_MART_ROOF,
        player_x=4,
        player_y=5,
    )

    class Reader:
        def read(self) -> RawGameState:
            return raw

        def read_input_readiness(self) -> object:
            return SimpleNamespace(ready=True)

    class Emulator:
        def read_u8(self, address: int) -> int:
            return {
                ROOF_GIRL_X: 9,
                ROOF_GIRL_Y: 9,
                ROOF_NERD_X: 14,
                ROOF_NERD_Y: 8,
            }[address]

    class Executor:
        def __init__(self) -> None:
            self.actions: list[object] = []

        def execute(self, action: object) -> None:
            self.actions.append(action)

    executor = Executor()

    def reward_started() -> bool:
        return (
            sum(
                getattr(action, "kind", None) is MacroActionKind.INTERACT
                for action in executor.actions
            )
            >= 3
        )

    _interact_with_roof_girl(
        executor,  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        Emulator(),  # type: ignore[arg-type]
        replace(DEFAULT_SILPH_TIMING, movement_frames=1, menu_frames=1),
        reward_started=reward_started,
    )

    assert reward_started()


def test_silph_report_proves_required_story_and_terminal() -> None:
    report = _report()
    assert report.passed
    assert report.public_dict()["supply"] == {
        "hyper_potions_bought": 7,
        "used_by_rival_policy": 0,
        "x_special_used_by_rival_policy": 1,
        "remaining": 7,
        "max_repel_bought": 0,
        "max_repel_remaining": 0,
    }
    assert THIRD_FLOOR_GUARD == (
        "down",
        "down",
        "down",
        "down",
        "down",
        "left",
        "left",
        "down",
    )


def test_silph_report_accepts_the_pre_erika_ice_beam_upgrade() -> None:
    report = replace(
        _report(),
        money_after=30_296,
        tm13_preinstalled=True,
        tm13_transfer_before_event=False,
    )

    assert report.passed
    assert report.public_dict()["ice_beam_upgrade"]["preinstalled_before_silph"] is True


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("rival_potions_used", 2),
        ("hyper_potions_remaining", 4),
        ("max_repel_remaining", 1),
        ("route_items_archived", False),
        ("tm13_event", False),
        ("tm13_transfer_before_event", False),
        ("other_roof_rewards_untouched", False),
        ("fresh_water_after_reward", 1),
        ("tm13_after_teaching", 1),
        ("card_key_quantity", 0),
        ("master_ball_quantity", 0),
        ("lapras_flag_after", 0x0F),
        ("controller_released", False),
    ),
)
def test_silph_report_rejects_missing_evidence(
    field_name: str,
    value: object,
) -> None:
    assert not replace(_report(), **{field_name: value}).passed
