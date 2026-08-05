from dataclasses import fields, replace
from inspect import getsource
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import Badge, EventFlag, ItemId, MapId, RawGameState
from pokemon_red_completion.silph import (
    BATTLE_ITEM_SETTLE_PULSES,
    DEFAULT_SILPH_TIMING,
    MART_2F_ASCENT_CUSTOMER_BLOCK_POSITION,
    MART_2F_ASCENT_CUSTOMER_CLEAR_ATTEMPTS,
    MART_2F_ASCENT_CUSTOMER_CLEAR_POSITION,
    MART_2F_ASCENT_CUSTOMER_YIELD_POSITION,
    MART_2F_GIRL_X,
    MART_2F_GIRL_Y,
    MART_5F_GENTLEMAN_BLOCK_POSITION,
    MART_5F_GENTLEMAN_CLEAR_ATTEMPTS,
    MART_5F_GENTLEMAN_CLEAR_POSITION,
    MART_5F_GENTLEMAN_YIELD_POSITION,
    ROOF_GIRL_X,
    ROOF_GIRL_Y,
    ROOF_NERD_X,
    ROOF_NERD_Y,
    ROUTE_7_CONNECTION_TO_GATE,
    SAFFRON_CENTER_APPROACH,
    SAFFRON_WARP_COORDINATES,
    SILPH_1F_TO_ELEVATOR,
    SILPH_CHECKPOINT_COUNT,
    SILPH_ENTRANCE_APPROACH,
    SILPH_PC_DEPOSIT_ITEMS,
    THIRD_FLOOR_GUARD,
    X_SPECIAL_PURCHASE_QUANTITY,
    SilphChapterReport,
    SilphCheckpoint,
    SilphTiming,
    _battle_healing_item,
    _battle_healing_item_verified_terminal_exit,
    _enter_silph_elevator,
    _enter_silph_from_city,
    _interact_with_roof_girl,
    _mart_2f_girl_coordinate,
    _move_verified,
    _plan_saffron_center_approach,
    _plan_saffron_route,
    _return_center_to_seventh,
    _silph_capacity_deposit_items,
    _silph_capacity_ready,
    _silph_fixed_move_slot,
    _silph_rival_move_slot,
    run_silph_chapter,
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


def test_mart_5f_customer_yield_is_source_pinned_and_bounded() -> None:
    assert MART_5F_GENTLEMAN_BLOCK_POSITION == (15, 2)
    assert MART_5F_GENTLEMAN_YIELD_POSITION == (15, 3)
    assert MART_5F_GENTLEMAN_CLEAR_POSITION == (14, 2)
    assert MART_5F_GENTLEMAN_CLEAR_ATTEMPTS == 16


def test_mart_2f_ascent_customer_yield_is_source_pinned_and_bounded() -> None:
    assert MART_2F_ASCENT_CUSTOMER_BLOCK_POSITION == (14, 5)
    assert MART_2F_ASCENT_CUSTOMER_YIELD_POSITION == (13, 5)
    assert MART_2F_ASCENT_CUSTOMER_CLEAR_POSITION == (14, 4)
    assert MART_2F_ASCENT_CUSTOMER_CLEAR_ATTEMPTS == 32


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
        money_after=28_796,
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
    assert X_SPECIAL_PURCHASE_QUANTITY == 3
    assert BATTLE_ITEM_SETTLE_PULSES == 720
    for field in fields(SilphTiming):
        assert getattr(DEFAULT_SILPH_TIMING, field.name) > 0
        with pytest.raises(ValueError, match=field.name):
            replace(DEFAULT_SILPH_TIMING, **{field.name: 0})


def test_battle_healing_uses_the_shared_long_settle_bound() -> None:
    source = getsource(_battle_healing_item)
    assert "for _ in range(BATTLE_ITEM_SETTLE_PULSES):" in source


def test_battle_healing_accepts_verified_enemy_recoil_knockout() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.BRUNOS_ROOM,
        player_x=5,
        player_y=3,
        party_count=6,
        battle_state=0,
        enemy_hp=0,
    )

    assert _battle_healing_item_verified_terminal_exit(raw, 7, 6)
    assert not _battle_healing_item_verified_terminal_exit(raw, 7, 7)
    assert not _battle_healing_item_verified_terminal_exit(
        replace(raw, battle_state=2),
        7,
        6,
    )
    assert not _battle_healing_item_verified_terminal_exit(
        replace(raw, enemy_hp=1),
        7,
        6,
    )


def test_silph_capacity_accepts_a_consumed_recovery_stack() -> None:
    route_items = {item: 1 for item in SILPH_PC_DEPOSIT_ITEMS}

    nineteen_slots = {
        **route_items,
        ItemId.X_ACCURACY: 1,
        **{1000 + index: 1 for index in range(15)},
    }
    assert _silph_capacity_deposit_items(nineteen_slots) == SILPH_PC_DEPOSIT_ITEMS
    assert _silph_capacity_ready(nineteen_slots)
    replacement_pending = {**route_items, **{1000 + index: 1 for index in range(13)}}
    assert len(replacement_pending) == 16
    assert _silph_capacity_deposit_items(replacement_pending) == (ItemId.SS_TICKET,)
    already_safe = {
        ItemId.SS_TICKET: 1,
        ItemId.LIFT_KEY: 1,
        **{1000 + index: 1 for index in range(12)},
    }
    assert len(already_safe) == 14
    assert _silph_capacity_deposit_items(already_safe) == ()
    assert _silph_capacity_ready(already_safe)
    twenty_slots_without_enough_cleanup = {
        ItemId.SS_TICKET: 1,
        ItemId.LIFT_KEY: 1,
        **{1000 + index: 1 for index in range(18)},
    }
    assert _silph_capacity_deposit_items(twenty_slots_without_enough_cleanup) is None
    assert not _silph_capacity_ready(twenty_slots_without_enough_cleanup)


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


def test_silph_verified_movement_yields_on_mart_2f_before_3f_stairs() -> None:
    blocked = replace(
        _terminal(),
        map_id=MapId.CELADON_MART_2F,
        player_x=14,
        player_y=5,
    )
    yielded = replace(blocked, player_x=13)
    crossed = replace(blocked, player_y=4)
    states = iter(
        (
            blocked,
            *(blocked for _ in range(DEFAULT_SILPH_TIMING.movement_retries * 2)),
            blocked,
            yielded,
            blocked,
            crossed,
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
        ("up",),
        replace(DEFAULT_SILPH_TIMING, movement_frames=1),
        "X Special Mart 3F",
    )

    assert (final.map_id, final.player_x, final.player_y) == (
        MapId.CELADON_MART_2F,
        14,
        4,
    )


def test_silph_elevator_entry_retries_a_swallowed_doorway_input() -> None:
    hallway = replace(_terminal(), map_id=MapId.SILPH_CO_3F, player_x=20, player_y=1)
    elevator = replace(
        hallway,
        map_id=MapId.SILPH_CO_ELEVATOR,
        player_x=1,
        player_y=3,
    )
    states = iter((hallway, hallway, hallway, hallway, elevator))

    class Reader:
        def read(self) -> RawGameState:
            return next(states)

    class Executor:
        def execute(self, _action: object) -> None:
            return None

    final = _enter_silph_elevator(
        Executor(),  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        replace(DEFAULT_SILPH_TIMING, movement_frames=1),
        "test elevator",
    )

    assert final.map_id == MapId.SILPH_CO_ELEVATOR


def test_silph_clerk_approach_uses_verified_steps() -> None:
    source = getsource(run_silph_chapter)

    assert (
        '_move_verified(actions, reader, MART_TO_CLERK, timing, "Saffron clerk approach")'
        in source
    )


def test_silph_first_floor_routes_delegate_the_doorway_step() -> None:
    assert SILPH_1F_TO_ELEVATOR[-1] == "right"
    assert getsource(run_silph_chapter).count("_enter_silph_elevator(") >= 3
    assert "Silph 1F elevator corridor" in getsource(run_silph_chapter)
    assert "return Silph 1F elevator corridor" in getsource(_return_center_to_seventh)


def test_silph_city_entry_uses_collision_aware_navigation() -> None:
    assert SILPH_ENTRANCE_APPROACH == (18, 22)
    source = getsource(_enter_silph_from_city)
    assert "_navigate_saffron_coordinate" in source
    assert "MapId.SILPH_CO_1F" in source


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

    healthy_reserve = replace(
        surf_disabled,
        active_party_index=3,
        active_party_pp=(0, 12, 8, 5),
    )
    assert _silph_rival_move_slot(healthy_reserve) == 2


def test_silph_fixed_policy_falls_back_from_live_disable() -> None:
    disabled = replace(
        _terminal(),
        battle_state=2,
        first_party_moves=(44, 39, 58, 57),
        first_party_pp=(15, 0, 10, 15),
        player_disabled_move_slot=4,
        player_disable_turns=3,
    )

    assert _silph_fixed_move_slot(disabled, preferred=4) == 1


def test_silph_fixed_policy_preserves_usable_preference() -> None:
    raw = replace(
        _terminal(),
        battle_state=2,
        first_party_moves=(44, 39, 58, 57),
        first_party_pp=(15, 0, 10, 15),
    )

    assert _silph_fixed_move_slot(raw, preferred=4) == 4


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
        getattr(action, "kind", None) is MacroActionKind.INTERACT for action in executor.actions
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
        money_after=28_996,
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
