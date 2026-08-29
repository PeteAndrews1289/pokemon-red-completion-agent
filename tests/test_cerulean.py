from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import FrozenInstanceError, fields, replace
from typing import Any

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleSwitchCapability,
    bind_battle_decision_observer,
)
from pokemon_red_completion.cerulean import (
    CENTER_HEAL_TO_PC_DIRECTIONS,
    CENTER_PC_TO_HEAL_DIRECTIONS,
    CENTER_TO_ROUTE_3_DIRECTIONS,
    CERULEAN_CHECKPOINT_COUNT,
    CERULEAN_QUALIFICATION_BOUNDARIES,
    DEFAULT_CERULEAN_TIMING,
    GYM_EXIT_APPROACH_DIRECTIONS,
    MT_MOON_1F_DIRECTIONS,
    MT_MOON_1F_POST_TM_SEED_WAITS,
    MT_MOON_1F_PRE_TM_SEED_WAITS,
    MT_MOON_1F_ZUBAT_LEVELS,
    MT_MOON_B1F_DIRECTIONS,
    MT_MOON_B1F_EXIT_DIRECTIONS,
    MT_MOON_B1F_EXIT_SEED_WAIT,
    MT_MOON_B1F_SEED_WAITS,
    MT_MOON_B2F_EXIT_DIRECTIONS,
    MT_MOON_B2F_EXIT_SEED_WAIT,
    MT_MOON_B2F_SEED_WAITS,
    MT_MOON_B2F_TO_ROCKET_DIRECTIONS,
    MT_MOON_BATTLE_POTION_FLOOR,
    MT_MOON_MAX_WILD_FLEES,
    MT_MOON_PICKUP_ENCOUNTER_WAIT_FRAMES,
    MT_MOON_POTION_APPROACH_DIRECTIONS,
    MT_MOON_POTION_DETOUR_ORIGIN,
    MT_MOON_POTION_PICKUP_POSITION,
    MT_MOON_POTION_RETURN_DIRECTIONS,
    MT_MOON_POTION_STARTING_QUANTITIES,
    MT_MOON_POTION_TOGGLE_INDEX,
    MT_MOON_RARE_CANDY_APPROACH_DIRECTIONS,
    MT_MOON_RARE_CANDY_PICKUP_POSITION,
    MT_MOON_RARE_CANDY_RETURN_DIRECTIONS,
    MT_MOON_RARE_CANDY_TOGGLE_INDEX,
    MT_MOON_TM12_APPROACH_DIRECTIONS,
    MT_MOON_TM12_PICKUP_POSITION,
    MT_MOON_TM12_RETURN_DIRECTIONS,
    MT_MOON_TM12_TOGGLE_INDEX,
    MT_MOON_ZUBAT_ENCOUNTER_WAIT_FRAMES,
    MT_MOON_ZUBAT_MAX_CAPTURE_ATTEMPTS,
    MT_MOON_ZUBAT_MAX_WEAKENING_ATTEMPTS,
    MT_MOON_ZUBAT_PRE_THROW_WAIT,
    MT_MOON_ZUBAT_SEED_WAIT,
    MT_MOON_ZUBAT_TARGET_WEAKENING_HITS,
    PEWTER_TO_CENTER_DIRECTIONS,
    ROCKET_TO_SUPER_NERD_DIRECTIONS,
    ROUTE_3_BATTLE_POTION_FLOOR,
    ROUTE_3_BATTLE_RECOVERY_HP,
    ROUTE_3_BUBBLE_TRAINER_INDEXES,
    ROUTE_3_RECOVERY_TRAINER_INDEXES,
    ROUTE_3_REJOIN_SEED_WAIT,
    ROUTE_3_REMAINDER_DIRECTIONS,
    ROUTE_3_REQUIRED_TRAINER_INDEXES,
    ROUTE_3_TRAINER_SEGMENTS,
    ROUTE_4_FINAL_APPROACH_DIRECTIONS,
    ROUTE_4_FIRST_LEDGE_APPROACH_DIRECTIONS,
    ROUTE_4_MIDDLE_DIRECTIONS,
    CeruleanChapterError,
    CeruleanChapterReport,
    CeruleanProgress,
    CeruleanTiming,
    _approach_pewter_mart_clerk,
    _capture_mt_moon_zubat,
    _capture_weakened_mt_moon_zubat,
    _collect_mt_moon_rare_candy_funding,
    _collect_mt_moon_recovery_potion,
    _collect_mt_moon_tm12,
    _CountingChapterExecutor,
    _cure_field_poison_if_needed,
    _face_mt_moon_pickup_after_encounter_settle,
    _finish_battle,
    _is_persistent_capture_hp,
    _leave_pewter_mart,
    _maximum_bubble_damage,
    _move_with_seed_waits,
    _move_without_battles_with_retries,
    _MtMoonTraversalLedger,
    _normalize_cerulean_antidotes,
    _obtain_helix_fossil,
    _open_pewter_ball_quantity_menu,
    _poison_return_potions_required,
    _pp_at,
    _reverse_directions,
    _route_3_victory_sequence,
    _seek_mt_moon_zubat,
    _select_battle_move,
    _select_pewter_shop_quantity,
    _sell_pewter_funding_tm34,
    _settle_super_nerd_field_control,
    _trigger_trainer_through_wild_encounters,
    _use_battle_potion,
    _weaken_mt_moon_zubat,
)
from pokemon_red_completion.economy import (
    PEWTER_NET_SUPPLY_COST,
    PEWTER_POKE_BALL_PURCHASE_QUANTITY,
    PEWTER_SUPPLY_COST,
    PEWTER_TM34_SALE_PROCEEDS,
)
from pokemon_red_completion.observation import (
    MT_MOON_SUPER_NERD_OPPONENT_ID,
    MT_MOON_SUPER_NERD_TRAINER_NUMBER,
    ROCKET_OPPONENT_ID,
    ROCKET_TRAINER_CLASS_ID,
    ROUTE_3_REQUIRED_TRAINER_SPECS,
    SQUIRTLE_SPECIES_ID,
    SUPER_NERD_TRAINER_CLASS_ID,
    WARTORTLE_SPECIES_ID,
    ZUBAT_SPECIES_ID,
    BattleMenuPhase,
    BattleMenuState,
    CeruleanBoundary,
    CeruleanChapterState,
    CeruleanPhase,
    InputReadiness,
    ItemId,
    MapId,
    NorthboundPhase,
    PewterChapterState,
    RamAddress,
    RawGameState,
    TravelBoundary,
)

READY = InputReadiness(0, 0, 0, 0, 0, 0)
ROUTE_3_EVENT_FIELDS = (
    "beat_route_3_trainer_0",
    "beat_route_3_trainer_1",
    "beat_route_3_trainer_3",
    "beat_route_3_trainer_6",
)


def test_pewter_shop_opener_stops_in_ball_quantity_menu() -> None:
    class Emulator:
        selected = 0
        quantity = 0

        def read_u8(self, address: int) -> int:
            if address == RamAddress.SHOP_SELECTED_ITEM:
                return self.selected
            if address == RamAddress.SHOP_QUANTITY:
                return self.quantity
            return 0

    emulator = Emulator()

    class Executor:
        confirmations = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.WAIT:
                return object()
            assert action.kind is MacroActionKind.CONFIRM
            self.confirmations += 1
            if self.confirmations == 3:
                emulator.selected = int(ItemId.POKE_BALL)
                emulator.quantity = 1
            elif self.confirmations > 3:
                raise AssertionError("quantity was accepted instead of left open")
            return object()

    executor = _CountingChapterExecutor(Executor())  # type: ignore[arg-type]
    _open_pewter_ball_quantity_menu(executor, emulator)  # type: ignore[arg-type]

    assert executor.actions_executed == 6
    assert emulator.selected == ItemId.POKE_BALL
    assert emulator.quantity == 1


def test_pewter_mart_exit_accepts_a_warp_on_the_final_bounded_pulse() -> None:
    class Reader:
        state = _raw(MapId.PEWTER_MART, 3, 5)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        down_pulses = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE and action.value == "down":
                self.down_pulses += 1
                if self.down_pulses == 1:
                    reader.state = replace(reader.state, player_y=6)
                elif self.down_pulses == 12:
                    reader.state = _raw(MapId.PEWTER_CITY, 23, 18)
            return object()

    executor = Executor()
    _leave_pewter_mart(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        replace(DEFAULT_CERULEAN_TIMING, transition_wait_frames=1),
    )

    assert executor.down_pulses == 12
    assert reader.state.map_id == MapId.PEWTER_CITY


def test_pewter_mart_exit_accepts_the_column_on_the_final_bounded_pulse() -> None:
    class Reader:
        state = _raw(MapId.PEWTER_MART, 2, 5)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        right_pulses = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE and action.value == "right":
                self.right_pulses += 1
                if self.right_pulses == 12:
                    reader.state = replace(reader.state, player_x=3)
            elif action.kind is MacroActionKind.MOVE and action.value == "down":
                reader.state = _raw(MapId.PEWTER_CITY, 23, 18)
            return object()

    executor = Executor()
    _leave_pewter_mart(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        replace(DEFAULT_CERULEAN_TIMING, transition_wait_frames=1),
    )

    assert executor.right_pulses == 12
    assert reader.state.map_id == MapId.PEWTER_CITY


def test_pewter_mart_exit_rejects_no_warp_after_the_bounded_allowance() -> None:
    class Reader:
        state = _raw(MapId.PEWTER_MART, 3, 5)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        down_pulses = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE and action.value == "down":
                self.down_pulses += 1
                reader.state = replace(reader.state, player_y=6)
            return object()

    executor = Executor()
    with pytest.raises(CeruleanChapterError, match="door did not return"):
        _leave_pewter_mart(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            reader,  # type: ignore[arg-type]
            replace(DEFAULT_CERULEAN_TIMING, transition_wait_frames=1),
        )

    assert executor.down_pulses == 12


def test_pewter_shop_quantity_tolerates_swallowed_menu_inputs() -> None:
    class Emulator:
        quantity = 1

        def read_u8(self, address: int) -> int:
            if address == RamAddress.SHOP_SELECTED_ITEM:
                return int(ItemId.POKE_BALL)
            if address == RamAddress.SHOP_QUANTITY:
                return self.quantity
            return 0

    emulator = Emulator()

    class Executor:
        up_requests = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE:
                assert action.value == "up"
                self.up_requests += 1
                if self.up_requests >= 3:
                    emulator.quantity += 1
            return object()

    executor = _CountingChapterExecutor(Executor())  # type: ignore[arg-type]
    _select_pewter_shop_quantity(
        executor,
        emulator,  # type: ignore[arg-type]
        item=ItemId.POKE_BALL,
        quantity=PEWTER_POKE_BALL_PURCHASE_QUANTITY,
        label="unit Ball reserve",
    )

    assert emulator.quantity == PEWTER_POKE_BALL_PURCHASE_QUANTITY
    assert executor.actions_executed == 2 * (PEWTER_POKE_BALL_PURCHASE_QUANTITY + 1)


def test_pewter_tm34_sale_is_exact_bounded_and_restores_control() -> None:
    class Emulator:
        items = [ItemId.POTION, ItemId.ANTIDOTE, ItemId.TM34_BIDE]
        quantities = [1, 1, 1]
        money = 4_476
        current_menu_item = 0
        list_scroll_offset = 0

        def read_u8(self, address: int) -> int:
            if address == RamAddress.NUM_BAG_ITEMS:
                return len(self.items)
            if int(RamAddress.BAG_ITEMS) <= address < int(RamAddress.BAG_ITEMS) + 40:
                offset = address - int(RamAddress.BAG_ITEMS)
                index, field = divmod(offset, 2)
                if index >= len(self.items):
                    return 0
                return int(self.items[index]) if field == 0 else self.quantities[index]
            if int(RamAddress.PLAYER_MONEY) <= address < int(RamAddress.PLAYER_MONEY) + 3:
                digits = f"{self.money:06d}"
                offset = address - int(RamAddress.PLAYER_MONEY)
                return int(digits[offset * 2]) * 16 + int(digits[offset * 2 + 1])
            if address == RamAddress.CURRENT_MENU_ITEM:
                return self.current_menu_item
            if address == RamAddress.LIST_SCROLL_OFFSET:
                return self.list_scroll_offset
            return 0

    emulator = Emulator()

    class Executor:
        phase = "field"
        cancel_count = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.WAIT:
                return object()
            if action.kind is MacroActionKind.INTERACT:
                assert self.phase == "field"
                self.phase = "shop_menu"
            elif action.kind is MacroActionKind.MOVE:
                assert action.value == "down"
                if self.phase == "shop_menu":
                    emulator.current_menu_item = 1
                elif self.phase == "sell_list":
                    emulator.current_menu_item += 1
                else:
                    raise AssertionError(f"unexpected sale movement phase {self.phase!r}")
            elif action.kind is MacroActionKind.CONFIRM:
                if self.phase == "shop_menu":
                    assert emulator.current_menu_item == 1
                    emulator.current_menu_item = 0
                    self.phase = "sell_list"
                elif self.phase == "sell_list":
                    assert emulator.items[emulator.current_menu_item] == ItemId.TM34_BIDE
                    self.phase = "sale_confirmation"
                elif self.phase == "sale_confirmation":
                    tm_index = emulator.items.index(ItemId.TM34_BIDE)
                    emulator.items.pop(tm_index)
                    emulator.quantities.pop(tm_index)
                    emulator.money += PEWTER_TM34_SALE_PROCEEDS
                    self.phase = "sale_complete"
                else:
                    raise AssertionError(f"unexpected sale confirmation phase {self.phase!r}")
            elif action.kind is MacroActionKind.CANCEL:
                assert self.phase in {"sale_complete", "field"}
                self.phase = "field"
                self.cancel_count += 1
            else:
                raise AssertionError(f"unexpected sale action {action!r}")
            return object()

    executor = Executor()

    class Reader:
        def read(self) -> RawGameState:
            return _raw(MapId.PEWTER_MART, 2, 5)

        def read_input_readiness(self) -> InputReadiness:
            return READY if executor.phase == "field" else InputReadiness(1, 0, 0, 0, 0)

    counted = _CountingChapterExecutor(executor)  # type: ignore[arg-type]
    proceeds = _sell_pewter_funding_tm34(
        counted,
        Reader(),  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
    )

    assert proceeds == PEWTER_TM34_SALE_PROCEEDS
    assert emulator.money == 5_476
    assert ItemId.TM34_BIDE not in emulator.items
    assert executor.cancel_count == 4


def _raw(
    map_id: MapId,
    x: int,
    y: int,
    *,
    battle_state: int = 0,
    level: int = 17,
    hp: int = 23,
    max_hp: int = 49,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=x,
        player_y=y,
        party_count=1,
        battle_state=battle_state,
        badge_bits=1,
        bag_item_ids=(ItemId.TM34_BIDE, ItemId.HELIX_FOSSIL),
        event_flags=b"",
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_level=level,
        first_party_hp=hp,
        first_party_max_hp=max_hp,
        first_party_status=0,
        battle_result=0,
        first_party_moves=(0x21, 0x27, 0x91, 0x37),
        first_party_pp=(34, 30, 20, 11),
    )


@pytest.mark.parametrize("expected_map", (MapId.ROUTE_3, MapId.MT_MOON_B2F))
def test_field_antidote_policy_is_a_noop_when_healthy(expected_map: MapId) -> None:
    state = _raw(expected_map, 31, 9)

    class Reader:
        def read(self) -> RawGameState:
            return state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    class Emulator:
        def read_u8(self, address: int) -> int:
            assert address == RamAddress.NUM_BAG_ITEMS
            return 0

    class Executor:
        def execute(self, action: MacroAction) -> object:
            raise AssertionError(f"healthy party unexpectedly used {action!r}")

    _cure_field_poison_if_needed(
        _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        Emulator(),  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        expected_map=expected_map,
        label="unit field traversal",
    )


def test_route_3_antidote_policy_fails_closed_when_poisoned_without_a_reserve() -> None:
    state = replace(_raw(MapId.ROUTE_3, 31, 9), first_party_status=0x08)

    class Reader:
        def read(self) -> RawGameState:
            return state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    class Emulator:
        def read_u8(self, address: int) -> int:
            assert address == RamAddress.NUM_BAG_ITEMS
            return 0

    with pytest.raises(CeruleanChapterError, match="exhausted the free Antidote reserve"):
        _cure_field_poison_if_needed(
            _CountingChapterExecutor(object()),  # type: ignore[arg-type]
            Reader(),  # type: ignore[arg-type]
            Emulator(),  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
            expected_map=MapId.ROUTE_3,
            label="unit Route 3",
        )


@pytest.mark.parametrize(
    ("hp", "max_hp", "route_steps", "expected"),
    (
        (17, 41, 61, 0),
        (12, 41, 61, 1),
        (1, 41, 61, 1),
        (1, 41, 124, 2),
    ),
)
def test_poison_return_plans_the_minimum_survival_potions(
    hp: int,
    max_hp: int,
    route_steps: int,
    expected: int,
) -> None:
    assert (
        _poison_return_potions_required(
            hp=hp,
            max_hp=max_hp,
            route_steps=route_steps,
        )
        == expected
    )


def test_poison_return_rejects_a_route_beyond_maximum_hp() -> None:
    with pytest.raises(CeruleanChapterError, match="maximum survivable HP"):
        _poison_return_potions_required(hp=20, max_hp=41, route_steps=164)


def test_cerulean_antidote_normalization_accepts_an_already_clean_boundary() -> None:
    state = _raw(MapId.CERULEAN_CITY, 0, 18)

    class Reader:
        def read(self) -> RawGameState:
            return state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    class Emulator:
        def read_u8(self, address: int) -> int:
            assert address == RamAddress.NUM_BAG_ITEMS
            return 0

    class Executor:
        def execute(self, action: MacroAction) -> object:
            raise AssertionError(f"clean boundary unexpectedly used {action!r}")

    _normalize_cerulean_antidotes(
        _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        Emulator(),  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
    )


def test_cerulean_antidote_normalization_rejects_poison_without_a_reserve() -> None:
    state = replace(_raw(MapId.CERULEAN_CITY, 0, 18), first_party_status=0x08)

    class Reader:
        def read(self) -> RawGameState:
            return state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    class Emulator:
        def read_u8(self, address: int) -> int:
            assert address == RamAddress.NUM_BAG_ITEMS
            return 0

    with pytest.raises(CeruleanChapterError, match="exhausted the free Antidote reserve"):
        _normalize_cerulean_antidotes(
            _CountingChapterExecutor(object()),  # type: ignore[arg-type]
            Reader(),  # type: ignore[arg-type]
            Emulator(),  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
        )


@pytest.mark.parametrize("enemy_level", sorted(MT_MOON_1F_ZUBAT_LEVELS))
def test_mt_moon_zubat_search_observes_every_valid_level_on_the_return_step(
    enemy_level: int,
) -> None:
    origin = _raw(MapId.MT_MOON_1F, 14, 32)
    upper = replace(origin, player_y=31)
    target = replace(
        origin,
        battle_state=1,
        enemy_species_id=ZUBAT_SPECIES_ID,
        enemy_level=enemy_level,
        enemy_hp=23,
        enemy_max_hp=23,
    )

    class _Reader:
        state = origin

        def read(self) -> RawGameState:
            return self.state

    reader = _Reader()

    class _Executor:
        returning = False
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> object:
            self.actions.append(action)
            if action.kind is MacroActionKind.MOVE and action.value == "up":
                reader.state = upper
            elif action.kind is MacroActionKind.MOVE and action.value == "down":
                reader.state = origin
                self.returning = True
            elif action.kind is MacroActionKind.WAIT and self.returning:
                reader.state = target
            return object()

    executor = _Executor()
    observed, flees, retries, attempts = _seek_mt_moon_zubat(  # type: ignore[arg-type]
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
    )

    assert observed is target
    assert flees == ()
    assert retries == 0
    assert attempts == 1
    assert [action.value for action in executor.actions if action.kind is MacroActionKind.MOVE] == [
        "up",
        "down",
    ]
    assert executor.actions[-1] == MacroAction(
        MacroActionKind.WAIT,
        repeat=MT_MOON_ZUBAT_ENCOUNTER_WAIT_FRAMES,
    )


def _capture_retry_harness(
    *,
    success_attempt: int | None,
    pre_throw_enemy_hp: int | None = None,
) -> tuple[RawGameState, Any, Any, Any]:
    weakened = replace(
        _raw(MapId.MT_MOON_1F, 14, 32, battle_state=1, level=15, hp=35, max_hp=40),
        party_species_ids=(SQUIRTLE_SPECIES_ID,),
        enemy_species_id=ZUBAT_SPECIES_ID,
        enemy_level=7,
        enemy_hp=13,
        enemy_max_hp=23,
    )

    class Emulator:
        frame_count = 0
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POKE_BALL),
            int(RamAddress.BAG_ITEMS) + 1: PEWTER_POKE_BALL_PURCHASE_QUANTITY,
            int(RamAddress.CURRENT_MENU_ITEM): 0,
            int(RamAddress.LIST_SCROLL_OFFSET): 0,
        }

        @property
        def pressed_buttons(self) -> frozenset[str]:
            return frozenset()

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = weakened
        menu_phase = BattleMenuPhase.MAIN

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(self.menu_phase, selected_main_command=1)

        def read_input_readiness(self) -> InputReadiness:
            return READY

    reader = Reader()

    class Executor:
        confirm_count = 0
        throw_count = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.CONFIRM:
                self.confirm_count += 1
                if self.confirm_count % 2 == 1 and pre_throw_enemy_hp is not None:
                    reader.state = replace(reader.state, enemy_hp=pre_throw_enemy_hp)
                if self.confirm_count % 2 == 0:
                    self.throw_count += 1
                    emulator.memory[int(RamAddress.BAG_ITEMS) + 1] -= 1
                    if self.throw_count == success_attempt:
                        reader.state = replace(
                            weakened,
                            player_y=31,
                            battle_state=0,
                            party_count=2,
                            party_species_ids=(SQUIRTLE_SPECIES_ID, ZUBAT_SPECIES_ID),
                        )
                    else:
                        reader.state = replace(reader.state, enemy_hp=14)
                        reader.menu_phase = BattleMenuPhase.UNKNOWN
            elif action.kind is MacroActionKind.CANCEL:
                reader.menu_phase = BattleMenuPhase.MAIN
            return object()

    return weakened, emulator, reader, Executor()


def test_mt_moon_capture_retries_the_same_encounter_after_one_failed_ball() -> None:
    weakened, emulator, reader, executor = _capture_retry_harness(success_attempt=2)

    settled, attempts, balls_used, balls_remaining, captured_enemy_hp = (
        _capture_weakened_mt_moon_zubat(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            reader,  # type: ignore[arg-type]
            emulator,  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
            weakened,
        )
    )

    assert settled.party_species_ids == (SQUIRTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
    assert (attempts, balls_used, balls_remaining) == (
        2,
        2,
        PEWTER_POKE_BALL_PURCHASE_QUANTITY - 2,
    )
    assert captured_enemy_hp == 14
    assert executor.throw_count == 2


def test_mt_moon_capture_binds_persistence_to_the_armed_throw_state() -> None:
    weakened, emulator, reader, executor = _capture_retry_harness(
        success_attempt=1,
        pre_throw_enemy_hp=2,
    )

    settled, attempts, balls_used, balls_remaining, captured_enemy_hp = (
        _capture_weakened_mt_moon_zubat(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            reader,  # type: ignore[arg-type]
            emulator,  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
            weakened,
        )
    )

    assert settled.party_species_ids == (SQUIRTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
    assert (attempts, balls_used, balls_remaining) == (
        1,
        1,
        PEWTER_POKE_BALL_PURCHASE_QUANTITY - 1,
    )
    assert weakened.enemy_hp == 13
    assert captured_enemy_hp == 2
    assert executor.throw_count == 1


def test_mt_moon_capture_persistent_gate_accepts_a_full_health_low_level_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encounter = replace(
        _raw(MapId.MT_MOON_1F, 14, 32, battle_state=1, level=15, hp=42, max_hp=42),
        party_species_ids=(SQUIRTLE_SPECIES_ID,),
        enemy_species_id=ZUBAT_SPECIES_ID,
        enemy_level=6,
        enemy_hp=21,
        enemy_max_hp=21,
    )
    settled = replace(
        encounter,
        player_y=31,
        battle_state=0,
        party_count=2,
        party_species_ids=(SQUIRTLE_SPECIES_ID, ZUBAT_SPECIES_ID),
    )

    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POKE_BALL),
            int(RamAddress.BAG_ITEMS) + 1: PEWTER_POKE_BALL_PURCHASE_QUANTITY,
            int(RamAddress.PARTY_MON_2_LEVEL): 6,
            int(RamAddress.PARTY_MON_2_HP): 0,
            int(RamAddress.PARTY_MON_2_HP) + 1: 21,
            int(RamAddress.PARTY_MON_2_MAX_HP): 0,
            int(RamAddress.PARTY_MON_2_MAX_HP) + 1: 21,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    class Reader:
        def read(self) -> RawGameState:
            return settled

        def read_input_readiness(self) -> InputReadiness:
            raise AssertionError("the capture helper already authenticated field readiness")

    monkeypatch.setattr(
        "pokemon_red_completion.cerulean._move_mt_moon",
        lambda *args, **kwargs: encounter,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.cerulean._seek_mt_moon_zubat",
        lambda *args, **kwargs: (encounter, (), 0, 1),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.cerulean._weaken_mt_moon_zubat",
        lambda *args, **kwargs: encounter,
    )
    emulator = Emulator()

    def capture(*args: object, **kwargs: object) -> tuple[RawGameState, int, int, int, int]:
        del args, kwargs
        emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = 3
        return settled, 1, 1, 3, 21

    monkeypatch.setattr(
        "pokemon_red_completion.cerulean._capture_weakened_mt_moon_zubat",
        capture,
    )
    monkeypatch.setattr("pokemon_red_completion.cerulean._wait", lambda *args: None)

    result = _capture_mt_moon_zubat(
        _CountingChapterExecutor(object()),  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        _MtMoonTraversalLedger(),
    )

    assert result == ((), 1, 0, 1, 1, 3)


def test_mt_moon_capture_fails_closed_after_the_fixed_ball_reserve() -> None:
    weakened, emulator, reader, executor = _capture_retry_harness(success_attempt=None)

    with pytest.raises(CeruleanChapterError, match="bounded same-encounter Ball reserve"):
        _capture_weakened_mt_moon_zubat(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            reader,  # type: ignore[arg-type]
            emulator,  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
            weakened,
        )

    assert executor.throw_count == MT_MOON_ZUBAT_MAX_CAPTURE_ATTEMPTS
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == 0


def test_mt_moon_zubat_weakening_retries_a_miss_and_lands_two_safe_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encounter = replace(
        _raw(MapId.MT_MOON_1F, 14, 32, battle_state=1, level=15, hp=41, max_hp=43),
        party_species_ids=(SQUIRTLE_SPECIES_ID,),
        enemy_species_id=ZUBAT_SPECIES_ID,
        enemy_level=11,
        enemy_hp=33,
        enemy_max_hp=33,
    )

    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POKE_BALL),
            int(RamAddress.BAG_ITEMS) + 1: PEWTER_POKE_BALL_PURCHASE_QUANTITY,
            int(RamAddress.BATTLE_MON_SPECIAL): 0,
            int(RamAddress.BATTLE_MON_SPECIAL) + 1: 32,
            int(RamAddress.PARTY_MON_1_SPECIAL): 0,
            int(RamAddress.PARTY_MON_1_SPECIAL) + 1: 31,
            int(RamAddress.ENEMY_SPECIAL): 0,
            int(RamAddress.ENEMY_SPECIAL) + 1: 14,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = encounter

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()
    observed_hps = iter((33, 25, 17))
    selections = 0

    def select(*args: object, **kwargs: object) -> bool:
        nonlocal selections
        del args
        assert kwargs["allow_resolved_turn_without_pp"] is True
        selections += 1
        reader.state = replace(reader.state, enemy_hp=next(observed_hps))
        return True

    monkeypatch.setattr("pokemon_red_completion.cerulean._select_battle_move", select)
    weakened = _weaken_mt_moon_zubat(
        _CountingChapterExecutor(object()),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        encounter,
    )

    assert _maximum_bubble_damage(emulator, encounter) == 21  # type: ignore[arg-type]
    assert selections == 3
    assert weakened.enemy_hp == 17
    assert MT_MOON_ZUBAT_MAX_WEAKENING_ATTEMPTS == 4
    assert MT_MOON_ZUBAT_TARGET_WEAKENING_HITS == 2


@pytest.mark.parametrize("enemy_level", (6, 7, 8))
def test_mt_moon_zubat_weakening_uses_full_health_throw_when_hit_may_be_lethal(
    monkeypatch: pytest.MonkeyPatch,
    enemy_level: int,
) -> None:
    encounter = replace(
        _raw(MapId.MT_MOON_1F, 14, 32, battle_state=1, level=15, hp=41, max_hp=43),
        party_species_ids=(SQUIRTLE_SPECIES_ID,),
        enemy_species_id=ZUBAT_SPECIES_ID,
        enemy_level=enemy_level,
        enemy_hp=21,
        enemy_max_hp=27,
    )

    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POKE_BALL),
            int(RamAddress.BAG_ITEMS) + 1: PEWTER_POKE_BALL_PURCHASE_QUANTITY,
            int(RamAddress.BATTLE_MON_SPECIAL): 0,
            int(RamAddress.BATTLE_MON_SPECIAL) + 1: 32,
            int(RamAddress.PARTY_MON_1_SPECIAL): 0,
            int(RamAddress.PARTY_MON_1_SPECIAL) + 1: 31,
            int(RamAddress.ENEMY_SPECIAL): 0,
            int(RamAddress.ENEMY_SPECIAL) + 1: 14,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    def should_not_select(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        raise AssertionError("unsafe Bubble was selected")

    monkeypatch.setattr(
        "pokemon_red_completion.cerulean._select_battle_move",
        should_not_select,
    )
    prepared = _weaken_mt_moon_zubat(
        _CountingChapterExecutor(object()),  # type: ignore[arg-type]
        type("Reader", (), {"read": lambda self: encounter})(),  # type: ignore[arg-type]
        Emulator(),  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        encounter,
    )

    assert prepared is encounter


def _brock_victory() -> PewterChapterState:
    return PewterChapterState(
        phase=NorthboundPhase.BROCK_DEFEATED,
        boundary=TravelBoundary.UNKNOWN,
        controls=READY,
        local_script=0,
        current_map_script=0,
        oak_lab_script=18,
        got_oaks_parcel=True,
        oak_got_parcel=True,
        got_pokedex=True,
        parcel_in_bag=False,
        beat_brock=True,
        got_tm34=True,
        tm34_in_bag=True,
        boulder_badge=True,
        boulder_badge_mirror=True,
        current_opponent=0,
        trainer_class=0,
        engaged_trainer_class=0,
        gym_leader_number=1,
        map_id=MapId.PEWTER_GYM,
        player_x=4,
        player_y=3,
        party_count=1,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_hp=27,
        first_party_max_hp=33,
        first_party_level=12,
        battle_state=0,
        battle_result=0,
        first_party_status=0,
        first_party_moves=(0x21, 0x27, 0x91, 0),
        first_party_pp=(3, 30, 23, 0),
    )


def _chapter(**changes: object) -> CeruleanChapterState:
    defaults: dict[str, object] = {
        "phase": CeruleanPhase.UNKNOWN,
        "boundary": CeruleanBoundary.UNKNOWN,
        "controls": READY,
        "local_script": 0,
        "current_map_script": 0,
        "beat_brock": True,
        "got_tm34": True,
        "boulder_badge": True,
        "boulder_badge_mirror": True,
        "beat_route_3_trainer_0": True,
        "beat_route_3_trainer_1": True,
        "beat_route_3_trainer_3": True,
        "beat_route_3_trainer_6": True,
        "beat_required_rocket": True,
        "beat_super_nerd": True,
        "got_dome_fossil": False,
        "got_helix_fossil": False,
        "dome_fossil_in_bag": False,
        "helix_fossil_in_bag": False,
        "current_opponent": 0,
        "trainer_class": 0,
        "trainer_number": 0,
        "engaged_trainer_class": 0,
        "engaged_trainer_set": 0,
        "map_id": MapId.MT_MOON_B2F,
        "player_x": 13,
        "player_y": 7,
        "party_count": 1,
        "party_species_ids": (WARTORTLE_SPECIES_ID,),
        "first_party_hp": 23,
        "first_party_max_hp": 49,
        "first_party_status": 0,
        "battle_state": 0,
        "battle_result": 0,
    }
    defaults.update(changes)
    return CeruleanChapterState(**defaults)  # type: ignore[arg-type]


def test_helix_fossil_rearms_one_dropped_ready_field_interaction() -> None:
    class Reader:
        obtained = False

        def read(self) -> RawGameState:
            return _raw(MapId.MT_MOON_B2F, 13, 7)

        def read_input_readiness(self) -> InputReadiness:
            return READY

        def read_cerulean_chapter_state(self, raw: RawGameState) -> CeruleanChapterState:
            del raw
            if not self.obtained:
                return _chapter()
            return _chapter(
                phase=CeruleanPhase.FOSSIL_OBTAINED,
                got_helix_fossil=True,
                helix_fossil_in_bag=True,
            )

    reader = Reader()

    class Executor:
        interactions = 0
        facing_pulses = 0

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.MOVE:
                assert action.value == "up"
                self.facing_pulses += 1
            elif action.kind is MacroActionKind.INTERACT:
                self.interactions += 1
                if self.interactions == 2:
                    reader.obtained = True

    class Tracker:
        def observe(self, evidence: CeruleanChapterState) -> CeruleanPhase:
            assert evidence.fossil_snapshot
            return CeruleanPhase.FOSSIL_OBTAINED

    executor = Executor()
    raw, evidence = _obtain_helix_fossil(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        Tracker(),  # type: ignore[arg-type]
        replace(DEFAULT_CERULEAN_TIMING, fossil_dialogue_pulses=3),
    )

    assert raw.map_id == MapId.MT_MOON_B2F
    assert evidence.fossil_snapshot
    assert executor.interactions == 2
    assert executor.facing_pulses == 2


def test_helix_fossil_does_not_rearm_inside_an_active_script() -> None:
    class Reader:
        obtained = False

        def read(self) -> RawGameState:
            return _raw(MapId.MT_MOON_B2F, 13, 7)

        def read_cerulean_chapter_state(self, raw: RawGameState) -> CeruleanChapterState:
            del raw
            if not self.obtained:
                return _chapter(local_script=1, current_map_script=1)
            return _chapter(
                phase=CeruleanPhase.FOSSIL_OBTAINED,
                got_helix_fossil=True,
                helix_fossil_in_bag=True,
            )

    reader = Reader()

    class Executor:
        confirmations = 0
        interactions = 0

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.CONFIRM:
                self.confirmations += 1
                reader.obtained = True
            elif action.kind is MacroActionKind.INTERACT:
                self.interactions += 1

    class Tracker:
        def observe(self, evidence: CeruleanChapterState) -> CeruleanPhase:
            assert evidence.fossil_snapshot
            return CeruleanPhase.FOSSIL_OBTAINED

    executor = Executor()
    _, evidence = _obtain_helix_fossil(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        Tracker(),  # type: ignore[arg-type]
        replace(DEFAULT_CERULEAN_TIMING, fossil_dialogue_pulses=2),
    )

    assert evidence.fossil_snapshot
    assert executor.confirmations == 1
    assert executor.interactions == 0


def test_mt_moon_pickup_faces_only_after_delayed_wild_is_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = _raw(MapId.MT_MOON_B2F, 28, 5)

        def read(self) -> RawGameState:
            return self.state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    reader = Reader()

    class Executor:
        exposed_transition = False
        directions: list[str] = []

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.WAIT and not self.exposed_transition:
                self.exposed_transition = True
                reader.state = replace(reader.state, battle_state=1)
            elif action.kind is MacroActionKind.MOVE:
                self.directions.append(str(action.value))

    def flee_wild(*args: object, **kwargs: object) -> object:
        del args, kwargs
        assert reader.state.battle_state == 1
        reader.state = replace(reader.state, battle_state=0, battle_result=2)
        return object()

    monkeypatch.setattr("pokemon_red_completion.cerulean.flee_wild", flee_wild)
    executor = Executor()
    ledger = _MtMoonTraversalLedger()
    faced = _face_mt_moon_pickup_after_encounter_settle(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        direction="right",
        expected_map_id=MapId.MT_MOON_B2F,
        expected_position=(28, 5),
        label="unit delayed pickup",
        ledger=ledger,
    )

    assert MT_MOON_PICKUP_ENCOUNTER_WAIT_FRAMES == 1
    assert executor.exposed_transition
    assert executor.directions == ["right"]
    assert (faced.player_x, faced.player_y, faced.battle_state) == (28, 5, 0)
    assert len(ledger.flees) == 1


@pytest.mark.parametrize(
    "delayed_state",
    (
        _raw(MapId.MT_MOON_B2F, 28, 5, battle_state=2),
        _raw(MapId.MT_MOON_1F, 28, 5, battle_state=1),
    ),
)
def test_mt_moon_pickup_rejects_an_unexpected_delayed_battle(
    delayed_state: RawGameState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        def read(self) -> RawGameState:
            return delayed_state

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)

    def forbidden_flee(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("unexpected battle must fail before attempting to flee")

    monkeypatch.setattr("pokemon_red_completion.cerulean.flee_wild", forbidden_flee)
    executor = Executor()
    with pytest.raises(CeruleanChapterError, match="unexpected delayed battle"):
        _face_mt_moon_pickup_after_encounter_settle(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            Reader(),  # type: ignore[arg-type]
            direction="right",
            expected_map_id=MapId.MT_MOON_B2F,
            expected_position=(28, 5),
            label="unit delayed pickup",
            ledger=_MtMoonTraversalLedger(),
        )

    assert [action.kind for action in executor.actions] == [MacroActionKind.WAIT]


def test_mt_moon_pickup_rejects_a_delayed_wild_after_the_flee_budget() -> None:
    state = _raw(MapId.MT_MOON_B2F, 28, 5, battle_state=1)

    class Reader:
        def read(self) -> RawGameState:
            return state

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)

    ledger = _MtMoonTraversalLedger()
    ledger.flees.extend(  # type: ignore[arg-type]
        [object()] * MT_MOON_MAX_WILD_FLEES
    )
    executor = Executor()
    with pytest.raises(CeruleanChapterError, match="exhausted.*flee budget"):
        _face_mt_moon_pickup_after_encounter_settle(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            Reader(),  # type: ignore[arg-type]
            direction="right",
            expected_map_id=MapId.MT_MOON_B2F,
            expected_position=(28, 5),
            label="unit delayed pickup",
            ledger=ledger,
        )

    assert ledger.remaining_flees == 0
    assert [action.kind for action in executor.actions] == [MacroActionKind.WAIT]


def test_mt_moon_pickup_rejects_a_lost_party_safe_stance() -> None:
    state = _raw(MapId.MT_MOON_B2F, 28, 5, hp=0)

    class Reader:
        def read(self) -> RawGameState:
            return state

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)

    executor = Executor()
    with pytest.raises(CeruleanChapterError, match="lost.*pickup stance"):
        _face_mt_moon_pickup_after_encounter_settle(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            Reader(),  # type: ignore[arg-type]
            direction="right",
            expected_map_id=MapId.MT_MOON_B2F,
            expected_position=(28, 5),
            label="unit delayed pickup",
            ledger=_MtMoonTraversalLedger(),
        )

    assert [action.kind for action in executor.actions] == [MacroActionKind.WAIT]


def test_mt_moon_pickup_rejects_a_facing_pulse_that_moves() -> None:
    class Reader:
        state = _raw(MapId.MT_MOON_B2F, 28, 5)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        directions: list[str] = []

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.MOVE:
                self.directions.append(str(action.value))
                reader.state = replace(reader.state, player_x=29)

    executor = Executor()
    with pytest.raises(CeruleanChapterError, match="did not collide"):
        _face_mt_moon_pickup_after_encounter_settle(
            _CountingChapterExecutor(executor),  # type: ignore[arg-type]
            reader,  # type: ignore[arg-type]
            direction="right",
            expected_map_id=MapId.MT_MOON_B2F,
            expected_position=(28, 5),
            label="unit delayed pickup",
            ledger=_MtMoonTraversalLedger(),
        )

    assert executor.directions == ["right"]


def _route_3_evidence() -> tuple[
    tuple[CeruleanChapterState, ...],
    tuple[CeruleanChapterState, ...],
]:
    battles = []
    victories = []
    defeated = [False, False, False, False]
    for position, (_, opponent, trainer_class, trainer_number) in enumerate(
        ROUTE_3_REQUIRED_TRAINER_SPECS
    ):
        event_values = dict(zip(ROUTE_3_EVENT_FIELDS, defeated, strict=True))
        battles.append(
            _chapter(
                phase=CeruleanPhase.ROUTE_3_TRAINER_BATTLE,
                map_id=MapId.ROUTE_3,
                player_x=10 + position,
                player_y=6,
                battle_state=2,
                local_script=2,
                current_map_script=2,
                current_opponent=opponent,
                trainer_class=trainer_class,
                trainer_number=trainer_number,
                engaged_trainer_class=opponent,
                engaged_trainer_set=trainer_number,
                beat_required_rocket=False,
                beat_super_nerd=False,
                **event_values,
            )
        )
        defeated[position] = True
        victories.append(
            _chapter(
                phase=CeruleanPhase.UNKNOWN,
                map_id=MapId.ROUTE_3,
                player_x=10 + position,
                player_y=6,
                beat_required_rocket=False,
                beat_super_nerd=False,
                **dict(zip(ROUTE_3_EVENT_FIELDS, defeated, strict=True)),
            )
        )
    return tuple(battles), tuple(victories)


def _report() -> CeruleanChapterReport:
    route_3_battle_evidence, route_3_victory_evidence = _route_3_evidence()
    rocket_battle_evidence = _chapter(
        phase=CeruleanPhase.REQUIRED_ROCKET_BATTLE,
        beat_required_rocket=False,
        beat_super_nerd=False,
        battle_state=2,
        local_script=2,
        current_map_script=2,
        player_x=11,
        player_y=19,
        current_opponent=ROCKET_OPPONENT_ID,
        trainer_class=ROCKET_TRAINER_CLASS_ID,
        trainer_number=1,
        engaged_trainer_class=ROCKET_OPPONENT_ID,
        engaged_trainer_set=1,
    )
    rocket_victory_evidence = _chapter(
        phase=CeruleanPhase.REQUIRED_ROCKET_DEFEATED,
        beat_super_nerd=False,
    )
    nerd_battle_evidence = _chapter(
        phase=CeruleanPhase.SUPER_NERD_BATTLE,
        beat_super_nerd=False,
        battle_state=2,
        local_script=3,
        current_map_script=3,
        player_x=13,
        player_y=8,
        current_opponent=MT_MOON_SUPER_NERD_OPPONENT_ID,
        trainer_class=SUPER_NERD_TRAINER_CLASS_ID,
        trainer_number=MT_MOON_SUPER_NERD_TRAINER_NUMBER,
        engaged_trainer_class=MT_MOON_SUPER_NERD_OPPONENT_ID,
        engaged_trainer_set=MT_MOON_SUPER_NERD_TRAINER_NUMBER,
    )
    nerd_victory_evidence = _chapter(phase=CeruleanPhase.SUPER_NERD_DEFEATED)
    fossil_evidence = _chapter(
        phase=CeruleanPhase.FOSSIL_OBTAINED,
        got_helix_fossil=True,
        helix_fossil_in_bag=True,
    )
    cerulean_evidence = replace(
        fossil_evidence,
        phase=CeruleanPhase.CERULEAN_REACHED,
        boundary=CeruleanBoundary.CERULEAN_WEST_ENTRY,
        map_id=MapId.CERULEAN_CITY,
        player_x=0,
        player_y=18,
    )
    return CeruleanChapterReport(
        starting_brock_evidence=_brock_victory(),
        pewter_tm34_sale_proceeds=PEWTER_TM34_SALE_PROCEEDS,
        mt_moon_tm12_in_bag=True,
        mt_moon_rare_candy_in_bag=True,
        route_3_reached=_raw(MapId.ROUTE_3, 0, 10, level=12, hp=33, max_hp=33),
        route_3_battles=tuple(
            _raw(MapId.ROUTE_3, 10 + position, 6, battle_state=2) for position in range(4)
        ),
        route_3_victories=tuple(_raw(MapId.ROUTE_3, 10 + position, 6) for position in range(4)),
        route_4_reached=_raw(MapId.ROUTE_4, 9, 17),
        mt_moon_entered=_raw(MapId.MT_MOON_1F, 14, 35),
        mt_moon_b1f_reached=_raw(MapId.MT_MOON_B1F, 5, 5),
        mt_moon_b2f_reached=_raw(MapId.MT_MOON_B2F, 21, 17),
        rocket_battle=replace(
            _raw(MapId.MT_MOON_B2F, 11, 19, battle_state=2),
            first_party_moves=(0x21, 0x27, 0x05, 0x37),
        ),
        rocket_defeated=_raw(MapId.MT_MOON_B2F, 11, 19),
        super_nerd_battle=_raw(MapId.MT_MOON_B2F, 13, 8, battle_state=2),
        super_nerd_defeated=_raw(MapId.MT_MOON_B2F, 13, 8),
        fossil_obtained=_raw(MapId.MT_MOON_B2F, 13, 7),
        mt_moon_b1f_ascent=_raw(MapId.MT_MOON_B1F, 23, 3),
        mt_moon_exited=_raw(MapId.ROUTE_4, 24, 6),
        cerulean_reached=_raw(MapId.CERULEAN_CITY, 0, 18, hp=26),
        route_3_battle_evidence=route_3_battle_evidence,
        route_3_victory_evidence=route_3_victory_evidence,
        route_3_wild_flees=(),
        route_3_movement_retries=0,
        mt_moon_zubat_search_flees=(),
        mt_moon_zubat_search_attempts=1,
        mt_moon_zubat_movement_retries=0,
        mt_moon_zubat_capture_attempts=1,
        mt_moon_zubat_balls_used=1,
        mt_moon_zubat_balls_remaining=PEWTER_POKE_BALL_PURCHASE_QUANTITY - 1,
        mt_moon_wild_flees=(),
        mt_moon_movement_retries=0,
        rocket_battle_evidence=rocket_battle_evidence,
        rocket_victory_evidence=rocket_victory_evidence,
        super_nerd_battle_evidence=nerd_battle_evidence,
        super_nerd_victory_evidence=nerd_victory_evidence,
        fossil_evidence=fossil_evidence,
        cerulean_evidence=cerulean_evidence,
        reached_boundaries=CERULEAN_QUALIFICATION_BOUNDARIES,
        observed_route_3_trainers=ROUTE_3_REQUIRED_TRAINER_INDEXES,
        saw_required_rocket_battle=True,
        saw_super_nerd_battle=True,
        frames_executed=129_990,
        actions_executed=2_031,
        controller_released=True,
    )


def test_npc_sensitive_mart_corridor_retries_a_blocked_step() -> None:
    origin = _raw(MapId.PEWTER_MART, 3, 7)

    class Reader:
        state = origin

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        movement_requests = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.WAIT:
                return object()
            assert action.kind is MacroActionKind.MOVE
            self.movement_requests += 1
            if self.movement_requests > 1:
                reader.state = replace(
                    reader.state,
                    player_y=(reader.state.player_y or 0) - 1,
                )
            return object()

    executor = Executor()
    final, retries = _move_without_battles_with_retries(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        ("up", "up"),
        "unit Pewter Mart customer",
        expected_map_id=MapId.PEWTER_MART,
        maximum_step_attempts=3,
        step_retry_wait_frames=1,
    )

    assert (final.player_x, final.player_y) == (3, 5)
    assert retries == 1
    assert executor.movement_requests == 3


class _ScriptedBattleReader:
    def __init__(
        self,
        menu_states: tuple[BattleMenuState, ...],
        *,
        pp: int = 10,
        hp: int = 30,
        battle_state: int = 2,
        pp_slot: int = 4,
    ) -> None:
        self._menu_states = list(menu_states)
        self.pp = pp
        self.hp = hp
        self.battle_state = battle_state
        self.pp_slot = pp_slot

    def read(self) -> RawGameState:
        pp = [34, 30, 20, 10]
        pp[self.pp_slot - 1] = self.pp
        return replace(
            _raw(MapId.ROUTE_3, 11, 6, battle_state=self.battle_state),
            first_party_hp=self.hp,
            first_party_pp=tuple(pp),
        )

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        assert raw.battle_state == self.battle_state
        if not self._menu_states:
            raise AssertionError("selector read beyond the scripted semantic menus")
        return self._menu_states.pop(0)


class _RecordingBattleExecutor:
    def __init__(
        self,
        reader: _ScriptedBattleReader | None = None,
        *,
        decrement_on_confirm: int | None = None,
        damage_on_confirm: int | None = None,
    ) -> None:
        self.actions: list[MacroAction] = []
        self.reader = reader
        self.decrement_on_confirm = decrement_on_confirm
        self.damage_on_confirm = damage_on_confirm
        self.confirm_count = 0

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.CONFIRM:
            self.confirm_count += 1
            if self.reader is not None and self.confirm_count == self.decrement_on_confirm:
                self.reader.pp -= 1
            if self.reader is not None and self.confirm_count == self.damage_on_confirm:
                self.reader.hp -= 7


class _StableRouteReader:
    def read(self) -> RawGameState:
        return _raw(MapId.MT_MOON_1F, 14, 35)


@pytest.mark.parametrize(
    ("main_commands", "expected_navigation"),
    (
        ((1, 0), ("up",)),
        ((2, 0), ("left",)),
        ((3, 2, 0), ("up", "left")),
    ),
)
def test_battle_selector_navigates_non_fight_commands_before_confirming(
    main_commands: tuple[int, ...],
    expected_navigation: tuple[str, ...],
) -> None:
    menus = tuple(
        BattleMenuState(
            BattleMenuPhase.MAIN,
            selected_main_command=command,
        )
        for command in main_commands
    ) + (BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=4),)
    reader = _ScriptedBattleReader(menus)
    recording = _RecordingBattleExecutor(reader, decrement_on_confirm=2)

    _select_battle_move(
        _CountingChapterExecutor(recording),
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        slot=4,
        label="semantic selector test",
    )

    non_wait_actions = tuple(
        action for action in recording.actions if action.kind is not MacroActionKind.WAIT
    )
    assert (
        tuple(action.value for action in non_wait_actions if action.kind is MacroActionKind.MOVE)
        == expected_navigation
    )
    first_confirm = next(
        index
        for index, action in enumerate(non_wait_actions)
        if action.kind is MacroActionKind.CONFIRM
    )
    assert first_confirm == len(expected_navigation)
    assert recording.confirm_count == 2
    assert reader.pp == 9


def test_battle_selector_supports_a_semantic_wild_battle_move() -> None:
    reader = _ScriptedBattleReader(
        (
            BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0),
            BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=3),
        ),
        battle_state=1,
        pp_slot=3,
    )
    recording = _RecordingBattleExecutor(reader, decrement_on_confirm=2)

    _select_battle_move(
        _CountingChapterExecutor(recording),
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        slot=3,
        label="wild Bubble selector test",
        expected_battle_state=1,
    )

    assert reader.pp == 9
    assert recording.confirm_count == 2


def test_battle_selector_does_not_treat_unknown_menu_as_active() -> None:
    reader = _ScriptedBattleReader(
        (
            BattleMenuState(BattleMenuPhase.UNKNOWN),
            BattleMenuState(BattleMenuPhase.UNKNOWN),
        )
    )
    recording = _RecordingBattleExecutor()
    timing = replace(DEFAULT_CERULEAN_TIMING, max_main_menu_pulses=2)

    with pytest.raises(
        CeruleanChapterError,
        match="never reached the semantic battle menu",
    ):
        _select_battle_move(
            _CountingChapterExecutor(recording),
            reader,  # type: ignore[arg-type]
            timing,
            slot=4,
            label="stale menu test",
        )

    assert [action.kind for action in recording.actions] == [
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
    ]


def test_battle_selector_rejects_stale_move_menu_before_attacking() -> None:
    reader = _ScriptedBattleReader(
        (
            BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0),
            BattleMenuState(BattleMenuPhase.UNKNOWN),
        )
    )
    recording = _RecordingBattleExecutor()

    with pytest.raises(
        CeruleanChapterError,
        match="left the semantic move menu",
    ):
        _select_battle_move(
            _CountingChapterExecutor(recording),
            reader,  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
            slot=4,
            label="stale move menu test",
        )

    assert recording.confirm_count == 1


def test_battle_selector_requires_a_persistent_pp_decrement() -> None:
    reader = _ScriptedBattleReader(
        (
            BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0),
            BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=4),
        )
    )
    recording = _RecordingBattleExecutor()
    timing = replace(DEFAULT_CERULEAN_TIMING, max_attack_start_pulses=3)

    with pytest.raises(
        CeruleanChapterError,
        match="persistent PP-decrement gate",
    ):
        _select_battle_move(
            _CountingChapterExecutor(recording),
            reader,  # type: ignore[arg-type]
            timing,
            slot=4,
            label="PP gate test",
        )

    assert recording.confirm_count == 4
    assert reader.pp == 10


def test_battle_selector_accepts_an_observed_confusion_turn_when_enabled() -> None:
    reader = _ScriptedBattleReader(
        (
            BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0),
            BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=4),
            BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0),
        )
    )
    recording = _RecordingBattleExecutor(reader, damage_on_confirm=2)

    pp_spent = _select_battle_move(
        _CountingChapterExecutor(recording),
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        slot=4,
        label="confusion turn test",
        allow_resolved_turn_without_pp=True,
    )

    assert not pp_spent
    assert reader.hp == 23
    assert reader.pp == 10
    assert recording.confirm_count == 2


def test_deterministic_seed_wait_is_placed_before_its_exact_move() -> None:
    recording = _RecordingBattleExecutor()

    _move_with_seed_waits(
        _CountingChapterExecutor(recording),
        _StableRouteReader(),  # type: ignore[arg-type]
        ("up", "right", "down"),
        ((2, 7),),
        "seed wait test",
    )

    assert recording.actions == [
        MacroAction(MacroActionKind.MOVE, "up"),
        MacroAction(MacroActionKind.WAIT, repeat=7),
        MacroAction(MacroActionKind.MOVE, "right"),
        MacroAction(MacroActionKind.MOVE, "down"),
    ]


def test_deterministic_seed_wait_rejects_duplicate_step_entries() -> None:
    recording = _RecordingBattleExecutor()

    with pytest.raises(CeruleanChapterError, match="invalid deterministic wait"):
        _move_with_seed_waits(
            _CountingChapterExecutor(recording),
            _StableRouteReader(),  # type: ignore[arg-type]
            ("up", "right"),
            ((1, 2), (1, 3)),
            "duplicate seed wait test",
        )

    assert recording.actions == []


def test_cerulean_route_is_pinned_at_critical_segments() -> None:
    assert _reverse_directions(CENTER_HEAL_TO_PC_DIRECTIONS) == (CENTER_PC_TO_HEAL_DIRECTIONS)
    assert len(GYM_EXIT_APPROACH_DIRECTIONS) == 16
    assert len(PEWTER_TO_CENTER_DIRECTIONS) == 40
    assert len(CENTER_TO_ROUTE_3_DIRECTIONS) == 35
    assert tuple(map(len, ROUTE_3_TRAINER_SEGMENTS)) == (15, 3, 7, 8)
    assert len(ROUTE_3_REMAINDER_DIRECTIONS) == 60
    assert len(MT_MOON_1F_DIRECTIONS) == 103
    assert MT_MOON_1F_PRE_TM_SEED_WAITS == (
        (1, 220),
        (10, 2),
        (30, 1),
        (31, 1),
    )
    assert MT_MOON_1F_POST_TM_SEED_WAITS == ((6, 2), (28, 2))
    assert len(MT_MOON_B1F_DIRECTIONS) == 28
    assert MT_MOON_B1F_SEED_WAITS == ((1, 2), (14, 1))
    assert len(MT_MOON_B2F_TO_ROCKET_DIRECTIONS) == 75
    assert MT_MOON_B2F_SEED_WAITS == (
        (1, 9),
        (19, 1),
        (29, 2),
        (65, 2),
    )
    assert len(ROCKET_TO_SUPER_NERD_DIRECTIONS) == 15
    assert len(MT_MOON_B2F_EXIT_DIRECTIONS) == 18
    assert MT_MOON_B2F_EXIT_SEED_WAIT == 1
    assert len(MT_MOON_B1F_EXIT_DIRECTIONS) == 4
    assert MT_MOON_B1F_EXIT_SEED_WAIT == 1
    assert MT_MOON_ZUBAT_SEED_WAIT == 155
    assert MT_MOON_ZUBAT_PRE_THROW_WAIT == 3
    assert MT_MOON_BATTLE_POTION_FLOOR == 9
    assert ROUTE_3_BATTLE_POTION_FLOOR + 1 == MT_MOON_BATTLE_POTION_FLOOR
    assert ROUTE_3_REQUIRED_TRAINER_INDEXES == (0, 1, 3, 6)
    assert frozenset(ROUTE_3_REQUIRED_TRAINER_INDEXES) == ROUTE_3_BUBBLE_TRAINER_INDEXES
    assert frozenset(ROUTE_3_REQUIRED_TRAINER_INDEXES) == ROUTE_3_RECOVERY_TRAINER_INDEXES
    assert ROUTE_3_REJOIN_SEED_WAIT == 8
    assert len(ROUTE_4_FIRST_LEDGE_APPROACH_DIRECTIONS) == 20
    assert len(ROUTE_4_MIDDLE_DIRECTIONS) == 39
    assert len(ROUTE_4_FINAL_APPROACH_DIRECTIONS) == 10


@pytest.mark.parametrize(
    ("initial_quantity", "expected_quantity"),
    ((13, 12), (14, 13)),
)
def test_route_3_battle_recovery_consumes_one_potion_above_the_floor(
    initial_quantity: int,
    expected_quantity: int,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: initial_quantity,
            int(RamAddress.CURRENT_MENU_ITEM): 0,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = replace(
            _raw(MapId.ROUTE_3, 14, 6, battle_state=2, level=13, hp=13, max_hp=35),
            enemy_hp=30,
            enemy_max_hp=30,
        )
        selected_main_command = 0

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=self.selected_main_command,
            )

    reader = Reader()

    class Executor:
        confirms = 0

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.MOVE and action.value == "down":
                reader.selected_main_command = 1
            elif action.kind is MacroActionKind.MOVE and action.value == "up":
                reader.selected_main_command = 0
            if action.kind is not MacroActionKind.CONFIRM:
                return
            self.confirms += 1
            if self.confirms == 3:
                reader.state = replace(reader.state, first_party_hp=33)
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = expected_quantity

    _use_battle_potion(
        _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        quantity_floor=12,
        label="Route 3 trainer 1",
    )

    assert reader.state.first_party_hp == 33
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == expected_quantity
    assert reader.selected_main_command == 0


def test_mt_moon_free_potion_detour_is_exactly_reversible() -> None:
    def endpoint(start: tuple[int, int], directions: tuple[str, ...]) -> tuple[int, int]:
        x, y = start
        for direction in directions:
            if direction == "left":
                x -= 1
            elif direction == "right":
                x += 1
            elif direction == "up":
                y -= 1
            else:
                y += 1
        return x, y

    assert (
        endpoint(
            MT_MOON_POTION_DETOUR_ORIGIN,
            MT_MOON_POTION_APPROACH_DIRECTIONS,
        )
        == MT_MOON_POTION_PICKUP_POSITION
    )
    assert (
        endpoint(
            MT_MOON_POTION_PICKUP_POSITION,
            MT_MOON_POTION_RETURN_DIRECTIONS,
        )
        == MT_MOON_POTION_DETOUR_ORIGIN
    )
    assert (
        _reverse_directions(MT_MOON_POTION_APPROACH_DIRECTIONS) == MT_MOON_POTION_RETURN_DIRECTIONS
    )
    assert MT_MOON_POTION_TOGGLE_INDEX == 0x6B


def test_mt_moon_tm12_funding_detour_is_exactly_reversible() -> None:
    origin = (14, 35)

    def endpoint(start: tuple[int, int], directions: tuple[str, ...]) -> tuple[int, int]:
        x, y = start
        for direction in directions:
            dx, dy = {
                "left": (-1, 0),
                "right": (1, 0),
                "up": (0, -1),
                "down": (0, 1),
            }[direction]
            x += dx
            y += dy
        return x, y

    assert endpoint(origin, MT_MOON_TM12_APPROACH_DIRECTIONS) == MT_MOON_TM12_PICKUP_POSITION
    assert endpoint(MT_MOON_TM12_PICKUP_POSITION, MT_MOON_TM12_RETURN_DIRECTIONS) == origin
    assert _reverse_directions(MT_MOON_TM12_APPROACH_DIRECTIONS) == (MT_MOON_TM12_RETURN_DIRECTIONS)
    assert MT_MOON_TM12_TOGGLE_INDEX == 0x6C
    assert ItemId.TM12_WATER_GUN == 0xD4


def test_mt_moon_rare_candy_funding_detour_is_exactly_reversible() -> None:
    def endpoint(start: tuple[int, int], directions: tuple[str, ...]) -> tuple[int, int]:
        x, y = start
        for direction in directions:
            dx, dy = {
                "left": (-1, 0),
                "right": (1, 0),
                "up": (0, -1),
                "down": (0, 1),
            }[direction]
            x += dx
            y += dy
        return x, y

    assert (
        endpoint(MT_MOON_POTION_PICKUP_POSITION, MT_MOON_RARE_CANDY_APPROACH_DIRECTIONS)
        == MT_MOON_RARE_CANDY_PICKUP_POSITION
    )
    assert (
        endpoint(MT_MOON_RARE_CANDY_PICKUP_POSITION, MT_MOON_RARE_CANDY_RETURN_DIRECTIONS)
        == MT_MOON_POTION_PICKUP_POSITION
    )
    assert _reverse_directions(MT_MOON_RARE_CANDY_APPROACH_DIRECTIONS) == (
        MT_MOON_RARE_CANDY_RETURN_DIRECTIONS
    )
    assert MT_MOON_RARE_CANDY_TOGGLE_INDEX == 0x69
    assert ItemId.RARE_CANDY == 0x28


def test_mt_moon_rare_candy_funding_asset_is_collected_and_route_rejoined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 0,
            int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + MT_MOON_RARE_CANDY_TOGGLE_INDEX // 8: 0,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = _raw(MapId.MT_MOON_1F, *MT_MOON_POTION_PICKUP_POSITION)

        def read(self) -> RawGameState:
            return self.state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    reader = Reader()

    class Executor:
        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.INTERACT:
                emulator.memory[int(RamAddress.NUM_BAG_ITEMS)] = 1
                emulator.memory[int(RamAddress.BAG_ITEMS)] = int(ItemId.RARE_CANDY)
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = 1
                flag_address = (
                    int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + MT_MOON_RARE_CANDY_TOGGLE_INDEX // 8
                )
                emulator.memory[flag_address] |= 1 << (MT_MOON_RARE_CANDY_TOGGLE_INDEX % 8)

    def move_mt_moon(
        *args: object,
        directions: tuple[str, ...] | None = None,
        **kwargs: object,
    ) -> RawGameState:
        active_directions = args[2] if len(args) > 2 else directions
        del kwargs
        target = {
            MT_MOON_RARE_CANDY_APPROACH_DIRECTIONS: MT_MOON_RARE_CANDY_PICKUP_POSITION,
            ("right",): (35, 31),
            ("left",): MT_MOON_RARE_CANDY_PICKUP_POSITION,
            MT_MOON_RARE_CANDY_RETURN_DIRECTIONS: MT_MOON_POTION_PICKUP_POSITION,
        }[active_directions]
        reader.state = replace(reader.state, player_x=target[0], player_y=target[1])
        return reader.state

    monkeypatch.setattr("pokemon_red_completion.cerulean._move_mt_moon", move_mt_moon)
    _collect_mt_moon_rare_candy_funding(
        _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        _MtMoonTraversalLedger(),
    )

    assert emulator.read_u8(int(RamAddress.BAG_ITEMS)) == ItemId.RARE_CANDY
    assert (reader.state.player_x, reader.state.player_y) == MT_MOON_POTION_PICKUP_POSITION


def test_mt_moon_tm12_funding_asset_is_collected_and_route_rejoined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 0,
            int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + MT_MOON_TM12_TOGGLE_INDEX // 8: 0,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = _raw(MapId.MT_MOON_1F, 14, 35)

        def read(self) -> RawGameState:
            return self.state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    reader = Reader()

    class Executor:
        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.INTERACT:
                emulator.memory[int(RamAddress.NUM_BAG_ITEMS)] = 1
                emulator.memory[int(RamAddress.BAG_ITEMS)] = int(ItemId.TM12_WATER_GUN)
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = 1
                flag_address = (
                    int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + MT_MOON_TM12_TOGGLE_INDEX // 8
                )
                emulator.memory[flag_address] |= 1 << (MT_MOON_TM12_TOGGLE_INDEX % 8)

    def move_mt_moon(
        *args: object,
        directions: tuple[str, ...] | None = None,
        **kwargs: object,
    ) -> RawGameState:
        active_directions = args[2] if len(args) > 2 else directions
        del kwargs
        target = {
            MT_MOON_TM12_APPROACH_DIRECTIONS: MT_MOON_TM12_PICKUP_POSITION,
            ("left",): (5, 32),
            ("right",): MT_MOON_TM12_PICKUP_POSITION,
            MT_MOON_TM12_RETURN_DIRECTIONS: (14, 35),
        }[active_directions]
        reader.state = replace(reader.state, player_x=target[0], player_y=target[1])
        return reader.state

    monkeypatch.setattr("pokemon_red_completion.cerulean._move_mt_moon", move_mt_moon)
    _collect_mt_moon_tm12(
        _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        _MtMoonTraversalLedger(),
    )

    assert emulator.read_u8(int(RamAddress.BAG_ITEMS)) == ItemId.TM12_WATER_GUN
    assert (reader.state.player_x, reader.state.player_y) == (14, 35)


@pytest.mark.parametrize(
    ("starting_quantity", "expected_quantity"),
    ((ROUTE_3_BATTLE_POTION_FLOOR, MT_MOON_BATTLE_POTION_FLOOR), (13, 14)),
)
def test_mt_moon_free_potion_bridges_route_3_and_accepts_unspent_reserve(
    monkeypatch: pytest.MonkeyPatch,
    starting_quantity: int,
    expected_quantity: int,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: starting_quantity,
            int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + MT_MOON_POTION_TOGGLE_INDEX // 8: 0,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = _raw(MapId.MT_MOON_1F, *MT_MOON_POTION_DETOUR_ORIGIN)

        def read(self) -> RawGameState:
            return self.state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    reader = Reader()

    class Executor:
        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.INTERACT:
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = expected_quantity
                flag_address = (
                    int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + MT_MOON_POTION_TOGGLE_INDEX // 8
                )
                emulator.memory[flag_address] |= 1 << (MT_MOON_POTION_TOGGLE_INDEX % 8)

    def move_mt_moon(
        *args: object,
        directions: tuple[str, ...] | None = None,
        **kwargs: object,
    ) -> RawGameState:
        active_directions = args[2] if len(args) > 2 else directions
        del kwargs
        if active_directions == MT_MOON_POTION_APPROACH_DIRECTIONS:
            reader.state = replace(
                reader.state,
                player_x=MT_MOON_POTION_PICKUP_POSITION[0],
                player_y=MT_MOON_POTION_PICKUP_POSITION[1],
            )
        else:
            reader.state = replace(
                reader.state,
                player_x=MT_MOON_POTION_DETOUR_ORIGIN[0],
                player_y=MT_MOON_POTION_DETOUR_ORIGIN[1],
            )
        return reader.state

    monkeypatch.setattr("pokemon_red_completion.cerulean._move_mt_moon", move_mt_moon)
    monkeypatch.setattr(
        "pokemon_red_completion.cerulean._collect_mt_moon_rare_candy_funding",
        lambda *args, **kwargs: None,
    )
    _collect_mt_moon_recovery_potion(
        _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        _MtMoonTraversalLedger(),
    )

    assert frozenset(range(8, 14)) == MT_MOON_POTION_STARTING_QUANTITIES
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == expected_quantity
    assert (reader.state.player_x, reader.state.player_y) == MT_MOON_POTION_DETOUR_ORIGIN


def test_pewter_mart_clerk_approach_uses_the_open_aisle_around_a_customer() -> None:
    class Reader:
        state = _raw(MapId.PEWTER_MART, 3, 7)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        blocked_left_once = False

        def execute(self, action: MacroAction) -> None:
            if action.kind is not MacroActionKind.MOVE:
                return
            position = (reader.state.player_x, reader.state.player_y)
            if position == (3, 6) and action.value == "left" and not self.blocked_left_once:
                self.blocked_left_once = True
                return
            deltas = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
            dx, dy = deltas[str(action.value)]
            reader.state = replace(
                reader.state,
                player_x=(reader.state.player_x or 0) + dx,
                player_y=(reader.state.player_y or 0) + dy,
            )

    executor = Executor()
    reached = _approach_pewter_mart_clerk(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
    )

    assert executor.blocked_left_once
    assert (reached.player_x, reached.player_y) == (2, 5)


def test_super_nerd_sight_line_retries_after_a_consumed_wild_encounter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = _raw(MapId.MT_MOON_B2F, 13, 9)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        upward_attempts = 0
        moves: list[str] = []

        def execute(self, action: MacroAction) -> None:
            if action.kind is not MacroActionKind.MOVE:
                return
            self.moves.append(str(action.value))
            if action.value == "up":
                self.upward_attempts += 1
                reader.state = replace(
                    reader.state,
                    player_y=8,
                    battle_state=1 if self.upward_attempts == 1 else 2,
                )
            elif action.value == "down":
                reader.state = replace(reader.state, player_y=9, battle_state=0)

    executor = Executor()

    def flee(*args: object, **kwargs: object) -> object:
        del args, kwargs
        reader.state = replace(reader.state, battle_state=0)
        return object()

    monkeypatch.setattr("pokemon_red_completion.cerulean.flee_wild", flee)

    reached = _trigger_trainer_through_wild_encounters(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        direction="up",
        origin=(13, 9),
        destination=(13, 8),
        expected_map=MapId.MT_MOON_B2F,
        label="Mt. Moon Super Nerd",
    )

    assert reached.battle_state == 2
    assert (reached.player_x, reached.player_y) == (13, 8)
    assert executor.moves == ["up", "down", "up"]


def test_super_nerd_sight_line_accepts_an_authenticated_direct_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = _raw(MapId.MT_MOON_B2F, 13, 9)

        def read(self) -> RawGameState:
            return self.state

        def read_cerulean_chapter_state(self, raw: RawGameState) -> object:
            class Evidence:
                super_nerd_battle_snapshot = raw.battle_state == 2 and raw.enemy_species_id == 38

            return Evidence()

    reader = Reader()

    class Executor:
        moves: list[str] = []

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.MOVE:
                self.moves.append(str(action.value))
                reader.state = replace(
                    reader.state,
                    player_y=8,
                    battle_state=1,
                    enemy_species_id=109,
                    enemy_level=10,
                )

    executor = Executor()

    def flee(*args: object, **kwargs: object) -> None:
        del args
        predicate = kwargs["trainer_handoff"]
        assert callable(predicate)
        reader.state = replace(reader.state, battle_state=2, enemy_species_id=38)
        assert predicate(reader.state)

    monkeypatch.setattr("pokemon_red_completion.cerulean.flee_wild", flee)
    reached = _trigger_trainer_through_wild_encounters(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        direction="up",
        origin=(13, 9),
        destination=(13, 8),
        expected_map=MapId.MT_MOON_B2F,
        label="Mt. Moon Super Nerd",
    )

    assert reached.battle_state == 2
    assert reached.enemy_species_id == 38
    assert executor.moves == ["up"]


def test_cerulean_qualification_stops_at_city_entry_not_the_gym() -> None:
    assert CERULEAN_QUALIFICATION_BOUNDARIES[-1] is CeruleanBoundary.CERULEAN_WEST_ENTRY
    assert len(CERULEAN_QUALIFICATION_BOUNDARIES) == 8


def test_cerulean_timing_defaults_are_positive_bounded_integers() -> None:
    assert CeruleanTiming() == DEFAULT_CERULEAN_TIMING
    assert DEFAULT_CERULEAN_TIMING.super_nerd_preselect_wait_frames == 1
    assert DEFAULT_CERULEAN_TIMING.super_nerd_cleanup_pulses == 4
    assert DEFAULT_CERULEAN_TIMING.b1f_exit_seed_wait_frames == 2
    assert all(
        isinstance(getattr(DEFAULT_CERULEAN_TIMING, field.name), int)
        and not isinstance(getattr(DEFAULT_CERULEAN_TIMING, field.name), bool)
        and getattr(DEFAULT_CERULEAN_TIMING, field.name) > 0
        for field in fields(CeruleanTiming)
    )


def test_super_nerd_cleanup_uses_a_bounded_cancel_settle() -> None:
    state = _raw(MapId.MT_MOON_B2F, 13, 8)

    class Reader:
        def read(self) -> RawGameState:
            return state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    class Executor:
        cancels = 0

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.CANCEL:
                self.cancels += 1

    executor = Executor()
    final = _settle_super_nerd_field_control(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
    )

    assert final == state
    assert executor.cancels == DEFAULT_CERULEAN_TIMING.super_nerd_cleanup_pulses


def test_super_nerd_cleanup_rejects_an_active_battle() -> None:
    state = _raw(MapId.MT_MOON_B2F, 13, 8, battle_state=2)

    class Reader:
        def read(self) -> RawGameState:
            return state

        def read_input_readiness(self) -> InputReadiness:
            return READY

    class Executor:
        def execute(self, action: MacroAction) -> None:
            del action

    with pytest.raises(CeruleanChapterError, match="safe field control"):
        _settle_super_nerd_field_control(
            _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
            Reader(),  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
        )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_cerulean_timing_rejects_unbounded_values(invalid: object) -> None:
    for field in fields(CeruleanTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_CERULEAN_TIMING, **{field.name: invalid})


def test_cerulean_helpers_use_one_based_pp_and_exact_reverse_routes() -> None:
    raw = _raw(MapId.ROUTE_3, 0, 10)
    assert _pp_at(raw, 1) == 34
    assert _pp_at(raw, 4) == 11
    assert _pp_at(raw, 0) == 0
    route = ("up", "right", "right", "down", "left")
    assert _reverse_directions(route) == (
        "right",
        "up",
        "left",
        "left",
        "down",
    )
    assert _is_persistent_capture_hp(13, 23, 13, 23)
    assert _is_persistent_capture_hp(14, 23, 13, 23)
    assert _is_persistent_capture_hp(21, 21, 21, 21)
    assert not _is_persistent_capture_hp(0, 23, 1, 23)
    assert not _is_persistent_capture_hp(23, 23, 22, 23)
    assert not _is_persistent_capture_hp(20, 21, 21, 21)
    assert not _is_persistent_capture_hp(15, 23, 13, 23)


def test_battle_completion_uses_a_semantic_fallback_after_switch_and_disable() -> None:
    class Reader:
        switch_prompt = True
        menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        state = replace(
            _raw(MapId.MT_MOON_B2F, 13, 8),
            battle_state=2,
            enemy_hp=26,
            enemy_species_id=13,
            party_count=2,
            party_species_ids=(WARTORTLE_SPECIES_ID, ZUBAT_SPECIES_ID),
            player_disabled_move_slot=4,
            player_disable_turns=3,
        )

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return self.menu

        def read_input_readiness(self) -> InputReadiness:
            return READY

        def trainer_switch_prompt_visible(self, raw: RawGameState) -> bool:
            del raw
            return self.switch_prompt

    reader = Reader()
    selected_slots: list[int] = []

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            if action.kind is MacroActionKind.CANCEL and reader.switch_prompt:
                reader.switch_prompt = False
                reader.menu = BattleMenuState(
                    BattleMenuPhase.MAIN,
                    selected_main_command=0,
                )
            elif action.kind is MacroActionKind.MOVE and reader.menu.phase is BattleMenuPhase.MOVE:
                selected = reader.menu.selected_move_slot or 1
                reader.menu = BattleMenuState(
                    BattleMenuPhase.MOVE,
                    selected_move_slot=(selected + 1 if action.value == "down" else selected - 1),
                )
            elif action.kind is MacroActionKind.CONFIRM:
                if reader.menu.phase is BattleMenuPhase.MAIN:
                    reader.menu = BattleMenuState(
                        BattleMenuPhase.MOVE,
                        selected_move_slot=1,
                    )
                elif reader.menu.phase is BattleMenuPhase.MOVE:
                    selected_slot = reader.menu.selected_move_slot
                    assert selected_slot is not None and selected_slot != 4
                    selected_slots.append(selected_slot)
                    final_pp = [34, 30, 20, 11]
                    final_pp[selected_slot - 1] -= 1
                    reader.state = replace(
                        reader.state,
                        battle_state=0,
                        enemy_hp=0,
                        first_party_pp=tuple(final_pp),
                    )
                    reader.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)

    executor = Executor()

    class Observer:
        started: list[BattleIntent] = []
        decisions: list[BattleIntent] = []
        finished = 0
        failures = 0

        def battle_started(self, *, intent: BattleIntent | None) -> None:
            assert intent is not None
            self.started.append(intent)

        def battle_finished(self) -> None:
            self.finished += 1

        def decision_scope(self, **kwargs: object) -> object:
            intent = kwargs["intent"]
            assert isinstance(intent, BattleIntent)
            self.decisions.append(intent)
            return nullcontext()

        def note_instrumentation_failure(self) -> None:
            self.failures += 1

    observer = Observer()
    with bind_battle_decision_observer(observer):  # type: ignore[arg-type]
        final = _finish_battle(
            executor,  # type: ignore[arg-type]
            reader,  # type: ignore[arg-type]
            DEFAULT_CERULEAN_TIMING,
            MapId.MT_MOON_B2F,
            "Mt. Moon Super Nerd",
            move_slot=4,
            battle_plan_id="unit-super-nerd",
        )

    assert selected_slots and selected_slots[0] != 4
    assert [intent.battle_plan_id for intent in observer.started] == ["unit-super-nerd"]
    assert [intent.objective_id for intent in observer.decisions] == ["reach_cerulean"]
    assert observer.finished == 1
    assert observer.failures == 0
    assert (
        next(action.kind for action in executor.actions if action.kind is not MacroActionKind.WAIT)
        is MacroActionKind.CANCEL
    )
    assert final.battle_state == 0


def test_battle_completion_declines_switch_without_cancelling_evolution() -> None:
    class Reader:
        switch_prompt_visible = False
        state = replace(
            _raw(MapId.MT_MOON_B2F, 21, 17),
            battle_state=2,
            enemy_hp=0,
            party_count=2,
            party_species_ids=(SQUIRTLE_SPECIES_ID, 0x6B),
            first_party_level=16,
        )

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(BattleMenuPhase.UNKNOWN)

        def read_input_readiness(self) -> InputReadiness:
            return READY

        def trainer_switch_prompt_visible(self, raw: RawGameState) -> bool:
            del raw
            return self.switch_prompt_visible

    reader = Reader()

    class Executor:
        actions: list[MacroAction] = []
        confirms = 0

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            if action.kind is MacroActionKind.CANCEL:
                assert reader.switch_prompt_visible
                reader.switch_prompt_visible = False
                reader.state = replace(
                    reader.state,
                    enemy_hp=0,
                    first_party_level=16,
                )
                return
            if action.kind is not MacroActionKind.CONFIRM:
                return
            self.confirms += 1
            if self.confirms == 1:
                reader.switch_prompt_visible = True
                reader.state = replace(reader.state, enemy_hp=35)
            elif self.confirms == 2:
                reader.state = replace(
                    reader.state,
                    party_species_ids=(WARTORTLE_SPECIES_ID, 0x6B),
                )
            elif self.confirms == 3:
                reader.state = replace(reader.state, battle_state=0)

    executor = Executor()
    final = _finish_battle(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        MapId.MT_MOON_B2F,
        "evolution regression",
    )

    inputs = [action.kind for action in executor.actions if action.kind is not MacroActionKind.WAIT]
    assert inputs.count(MacroActionKind.CANCEL) == 1
    assert inputs[:4] == [
        MacroActionKind.CONFIRM,
        MacroActionKind.CANCEL,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
    ]
    assert final.party_species_ids == (WARTORTLE_SPECIES_ID, 0x6B)


def test_battle_completion_uses_one_surplus_potion_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: 13,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = replace(
            _raw(MapId.MT_MOON_B2F, 13, 8),
            battle_state=2,
            enemy_hp=43,
            party_count=2,
            party_species_ids=(WARTORTLE_SPECIES_ID, 0x6B),
            first_party_hp=21,
            first_party_max_hp=46,
        )

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)

        def read_input_readiness(self) -> InputReadiness:
            return READY

        def trainer_switch_prompt_visible(self, raw: RawGameState) -> bool:
            del raw
            return False

    reader = Reader()
    recovery_calls: list[tuple[int, str]] = []

    def recover(*args: object, quantity_floor: int, label: str, **kwargs: object) -> None:
        del args, kwargs
        recovery_calls.append((quantity_floor, label))
        reader.state = replace(reader.state, first_party_hp=41)
        emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = 12

    monkeypatch.setattr("pokemon_red_completion.cerulean._use_battle_potion", recover)

    runtime_calls = 0

    def run_adaptive(
        runtime_reader: object,
        runtime_executor: object,
        policy: object,
        **kwargs: object,
    ) -> RawGameState:
        nonlocal runtime_calls
        del runtime_reader, runtime_executor
        runtime_calls += 1
        guard = kwargs["move_decision_guard"]
        assert callable(guard)
        if runtime_calls == 1:
            try:
                guard(reader.state)
            except Exception as cause:
                raise BattleRuntimeError("unit recovery request") from cause
            raise AssertionError("the low-HP guard did not request recovery")
        assert callable(policy)
        ranked_state = replace(
            reader.state,
            active_party_index=0,
            active_party_species_id=WARTORTLE_SPECIES_ID,
            active_party_moves=(0x21, 0x27, 0x91, 0),
            active_party_pp=(34, 30, 20, 0),
            enemy_species_id=0x6C,
        )
        assert policy(ranked_state) == 1
        assert kwargs["consume_battle_start_schedule"] is False
        assert kwargs["unknown_cancel_interval"] == 10_000
        intent = kwargs["intent"]
        assert isinstance(intent, BattleIntent)
        assert intent.objective_id == "reach_cerulean"
        assert intent.battle_plan_id == "unit-super-nerd-recovery"
        assert intent.resource_policy is BattleResourcePolicy.BOUNDED_RECOVERY
        assert intent.recovery_capabilities == frozenset({BattleRecoveryCapability.RESTORE_HP})
        reader.state = replace(reader.state, battle_state=0)
        return reader.state

    monkeypatch.setattr(
        "pokemon_red_completion.cerulean.run_adaptive_trainer_battle",
        run_adaptive,
    )

    class Executor:
        def execute(self, action: MacroAction) -> None:
            del action

    final = _finish_battle(
        Executor(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        MapId.MT_MOON_B2F,
        "Mt. Moon Super Nerd",
        move_slot=4,
        battle_plan_id="unit-super-nerd-recovery",
        emulator=emulator,  # type: ignore[arg-type]
        recovery_hp_threshold=25,
        recovery_potion_floor=12,
    )

    assert recovery_calls == [(12, "Mt. Moon Super Nerd")]
    assert runtime_calls == 2
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == 12
    assert final.first_party_hp == 41


def test_route_3_adaptive_battle_can_spend_fourth_surplus_before_cave_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: 12,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = replace(
            _raw(MapId.ROUTE_3, 14, 6),
            battle_state=2,
            enemy_hp=6,
            first_party_hp=20,
            first_party_max_hp=36,
        )

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()
    recovery_calls: list[int] = []

    def recover(*args: object, quantity_floor: int, **kwargs: object) -> None:
        del args, kwargs
        recovery_calls.append(quantity_floor)
        remaining = emulator.memory[int(RamAddress.BAG_ITEMS) + 1] - 1
        emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = remaining
        reader.state = replace(
            reader.state,
            first_party_hp=20 if remaining > quantity_floor else 36,
        )

    def run_adaptive(*args: object, **kwargs: object) -> RawGameState:
        del args
        guard = kwargs["move_decision_guard"]
        assert callable(guard)
        try:
            guard(reader.state)
        except Exception as cause:
            raise BattleRuntimeError("unit recovery request") from cause
        reader.state = replace(reader.state, battle_state=0, enemy_hp=0)
        return reader.state

    monkeypatch.setattr("pokemon_red_completion.cerulean._use_battle_potion", recover)
    monkeypatch.setattr(
        "pokemon_red_completion.cerulean.run_adaptive_trainer_battle",
        run_adaptive,
    )

    class Executor:
        def execute(self, action: MacroAction) -> None:
            del action

    final = _finish_battle(
        Executor(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        MapId.ROUTE_3,
        "Route 3 trainer 1",
        move_slot=3,
        battle_plan_id="cerulean-route-3-trainer-1",
        emulator=emulator,  # type: ignore[arg-type]
        recovery_hp_threshold=ROUTE_3_BATTLE_RECOVERY_HP,
        recovery_potion_floor=ROUTE_3_BATTLE_POTION_FLOOR,
    )

    assert recovery_calls == [ROUTE_3_BATTLE_POTION_FLOOR] * 4
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == 8
    assert final.battle_state == 0


def test_battle_completion_continues_with_the_sole_living_forced_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: 12,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = replace(
            _raw(MapId.MT_MOON_B2F, 13, 8),
            battle_state=2,
            enemy_species_id=0x37,
            enemy_hp=3,
            enemy_max_hp=33,
            party_count=2,
            party_species_ids=(WARTORTLE_SPECIES_ID, 0x6B),
            party_hp=(0, 17),
            party_max_hp=(50, 27),
            party_status=(0, 0),
            party_moves=((0x21, 0x27, 0x05, 0x37), (0x8D, 0, 0, 0)),
            party_pp=((35, 30, 6, 24), (15, 0, 0, 0)),
            first_party_hp=0,
            first_party_max_hp=50,
            active_party_index=0,
            active_party_species_id=WARTORTLE_SPECIES_ID,
            active_party_hp=0,
            active_party_max_hp=50,
            active_party_moves=(0x21, 0x27, 0x05, 0x37),
            active_party_pp=(35, 30, 6, 24),
        )

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()
    runtime_calls = 0

    def run_adaptive(
        runtime_reader: object,
        runtime_executor: object,
        policy: object,
        **kwargs: object,
    ) -> RawGameState:
        nonlocal runtime_calls
        del runtime_reader, runtime_executor
        runtime_calls += 1
        intent = kwargs["intent"]
        assert isinstance(intent, BattleIntent)
        assert intent.switch_capabilities == frozenset({BattleSwitchCapability.DIRECT})
        assert intent.switch_limit == 1
        if runtime_calls == 1:
            raise BattleRuntimeError("unit forced switch")
        assert callable(policy)
        assert policy(reader.state) == 1
        reader.state = replace(reader.state, battle_state=0, enemy_hp=0)
        return reader.state

    def switch(
        _executor: object,
        _reader: object,
        _emulator: object,
        target: int,
        **kwargs: object,
    ) -> None:
        assert target == 1
        assert kwargs["label"] == "Mt. Moon Super Nerd sole living forced switch"
        reader.state = replace(
            reader.state,
            active_party_index=1,
            active_party_species_id=0x6B,
            active_party_hp=17,
            active_party_max_hp=27,
            active_party_moves=(0x8D, 0, 0, 0),
            active_party_pp=(15, 0, 0, 0),
        )

    monkeypatch.setattr(
        "pokemon_red_completion.cerulean.run_adaptive_trainer_battle",
        run_adaptive,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.cerulean.switch_active_battler",
        switch,
    )

    class Executor:
        def execute(self, action: MacroAction) -> None:
            del action

    final = _finish_battle(
        Executor(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        MapId.MT_MOON_B2F,
        "Mt. Moon Super Nerd",
        move_slot=4,
        battle_plan_id="unit-super-nerd-switch",
        emulator=emulator,  # type: ignore[arg-type]
        recovery_hp_threshold=25,
        recovery_potion_floor=12,
    )

    assert runtime_calls == 2
    assert final.battle_state == 0
    assert final.active_party_index == 1
    assert final.active_party_hp == 17


def test_battle_completion_uses_each_surplus_potion_above_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: 14,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = replace(
            _raw(MapId.ROUTE_3, 14, 6),
            battle_state=2,
            enemy_hp=30,
            first_party_hp=13,
            first_party_max_hp=35,
        )

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)

        def read_input_readiness(self) -> InputReadiness:
            return READY

        def trainer_switch_prompt_visible(self, raw: RawGameState) -> bool:
            del raw
            return False

    reader = Reader()
    recovery_calls: list[tuple[int, str]] = []

    def recover(*args: object, quantity_floor: int, label: str, **kwargs: object) -> None:
        del args, kwargs
        recovery_calls.append((quantity_floor, label))
        remaining = emulator.memory[int(RamAddress.BAG_ITEMS) + 1] - 1
        emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = remaining
        reader.state = replace(
            reader.state,
            first_party_hp=13 if remaining > quantity_floor else 33,
        )

    monkeypatch.setattr("pokemon_red_completion.cerulean._use_battle_potion", recover)

    class Executor:
        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.CONFIRM:
                reader.state = replace(reader.state, battle_state=0)

    final = _finish_battle(
        Executor(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        MapId.ROUTE_3,
        "Route 3 trainer 1",
        emulator=emulator,  # type: ignore[arg-type]
        recovery_hp_threshold=13,
        recovery_potion_floor=12,
    )

    assert recovery_calls == [
        (12, "Route 3 trainer 1"),
        (12, "Route 3 trainer 1"),
    ]
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == 12
    assert final.first_party_hp == 33


def test_battle_completion_does_not_decline_a_nonexistent_single_party_switch() -> None:
    class Reader:
        state = replace(
            _raw(MapId.ROUTE_3, 12, 6),
            battle_state=2,
            enemy_hp=0,
            party_count=1,
            party_species_ids=(SQUIRTLE_SPECIES_ID,),
        )

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(BattleMenuPhase.UNKNOWN)

        def read_input_readiness(self) -> InputReadiness:
            return READY

        def trainer_switch_prompt_visible(self, raw: RawGameState) -> bool:
            del raw
            return False

    reader = Reader()

    class Executor:
        actions: list[MacroAction] = []
        confirms = 0

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            if action.kind is MacroActionKind.CONFIRM:
                self.confirms += 1
                if self.confirms == 1:
                    reader.state = replace(reader.state, battle_state=0)

    executor = Executor()
    _finish_battle(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        MapId.ROUTE_3,
        "single-party regression",
    )

    assert MacroActionKind.CANCEL not in {action.kind for action in executor.actions}


def test_route_3_victory_sequence_rejects_skips() -> None:
    _, victories = _route_3_evidence()
    assert _route_3_victory_sequence(victories)
    assert not _route_3_victory_sequence(victories[:-1])
    assert not _route_3_victory_sequence(
        (replace(victories[0], beat_route_3_trainer_0=False), *victories[1:])
    )


def test_cerulean_progress_and_report_are_immutable() -> None:
    progress = CeruleanProgress(
        checkpoint_id="cerulean_reached",
        label="Reached Cerulean City",
        completed=CERULEAN_CHECKPOINT_COUNT,
        total=CERULEAN_CHECKPOINT_COUNT,
        frames_executed=252_989,
    )
    report = _report()
    with pytest.raises(FrozenInstanceError):
        progress.completed = 14  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.controller_released = False  # type: ignore[misc]


def test_cerulean_report_is_complete_honest_and_privacy_safe() -> None:
    report = _report()
    public = report.public_dict()
    serialized = json.dumps(public, sort_keys=True)

    assert report.passed
    assert len(report.checkpoints()) == CERULEAN_CHECKPOINT_COUNT
    assert public["status"] == "ok"
    assert public["route"] == {
        "ordered_boundaries_verified": 8,
        "ordered_boundaries_total": 8,
        "required_route_3_trainers": [0, 1, 3, 6],
        "route_3_wild_flees": [],
        "route_3_movement_retries": 0,
    }
    assert public["economy"] == {
        "pewter_tm34_sale_proceeds": PEWTER_TM34_SALE_PROCEEDS,
        "mt_moon_tm12_funding_asset_collected": True,
        "mt_moon_rare_candy_funding_asset_collected": True,
        "pewter_supply_gross_cost": PEWTER_SUPPLY_COST,
        "pewter_supply_net_cost": PEWTER_NET_SUPPLY_COST,
    }
    assert public["mt_moon"] == {
        "required_rocket_battle_observed": True,
        "mega_punch_taught_before_rocket": True,
        "super_nerd_battle_observed": True,
        "helix_fossil_verified": True,
        "zubat_search_attempts": 1,
        "zubat_movement_retries": 0,
        "zubat_capture_attempts": 1,
        "zubat_balls_used": 1,
        "zubat_balls_remaining": PEWTER_POKE_BALL_PURCHASE_QUANTITY - 1,
        "zubat_search_flees": [],
        "wild_flees": [],
        "movement_retries": 0,
    }
    assert public["cerulean"] == {
        "arrival_verified": True,
        "wartortle_level": 17,
        "wartortle_hp": 26,
        "wartortle_max_hp": 49,
        "wartortle_status": 0,
    }
    for private_key in (
        "event_flags",
        "bag_item_ids",
        "party_species_ids",
        "first_party_moves",
        "first_party_pp",
        "joy_ignore",
        "current_opponent",
        "trainer_class",
        "trainer_number",
        "engaged_trainer_class",
        "engaged_trainer_set",
    ):
        assert private_key not in serialized


@pytest.mark.parametrize(
    "changes",
    (
        {"controller_released": False},
        {"mt_moon_rare_candy_in_bag": False},
        {"reached_boundaries": CERULEAN_QUALIFICATION_BOUNDARIES[:-1]},
        {"observed_route_3_trainers": (0, 1, 3)},
        {"saw_required_rocket_battle": False},
        {"saw_super_nerd_battle": False},
        {
            "rocket_battle_evidence": replace(
                _report().rocket_battle_evidence,
                current_opponent=0,
            )
        },
        {
            "super_nerd_battle_evidence": replace(
                _report().super_nerd_battle_evidence,
                trainer_number=0,
            )
        },
        {"fossil_evidence": replace(_report().fossil_evidence, got_helix_fossil=False)},
        {"cerulean_evidence": replace(_report().cerulean_evidence, player_y=11)},
        {"cerulean_reached": replace(_report().cerulean_reached, first_party_status=4)},
    ),
)
def test_cerulean_report_rejects_each_evidence_near_miss(
    changes: dict[str, object],
) -> None:
    assert not replace(_report(), **changes).passed
