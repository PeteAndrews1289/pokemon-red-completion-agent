from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from typing import cast

import pytest

import pokemon_red_completion.cascade as cascade_module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
)
from pokemon_red_completion.cascade import (
    BILL_EXIT_DIRECTIONS,
    BILL_PC_TO_HUMAN_DIRECTIONS,
    BILL_RETURN_WAIT_SEGMENTS,
    BILL_TO_CENTER_SEGMENTS,
    CASCADE_CHECKPOINT_COUNT,
    CENTER_HEAL_TO_PC_DIRECTIONS,
    CENTER_PC_TO_HEAL_DIRECTIONS,
    CENTER_TO_RIVAL_STAGING_DIRECTIONS,
    CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS,
    CERULEAN_ANTIDOTE_RESERVE,
    CERULEAN_GYM_POTION_RESERVE,
    CERULEAN_GYM_START_POTION_RESERVE,
    CERULEAN_GYM_TRAINER_MOVE_SLOT,
    CERULEAN_GYM_TRAINER_RECOVERY_HP,
    CERULEAN_RIVAL_MAX_POTION_RESERVE,
    CERULEAN_RIVAL_RECOVERY_HP_THRESHOLDS,
    DEFAULT_CASCADE_TIMING,
    FIELD_ITEM_MENU_CLOSE_PULSES,
    GYM_TRAINER_DIRECTIONS,
    GYM_TRAINER_TO_MISTY_DIRECTIONS,
    MART_REPEAT_CLERK_DIRECTIONS,
    MART_REPEAT_CUSTOMER_CLEAR_ATTEMPTS,
    MART_REPEAT_TO_CENTER_STAGING_DIRECTIONS,
    MISTY_RECOVERY_HP,
    RIVAL_CENTER_NPC_CORRECTION_DIRECTIONS,
    RIVAL_TRIGGER_DIRECTIONS,
    ROCKET_THIEF_POTION_RESERVE,
    ROUTE_24_ACCURACY_RECOVERY_HP,
    ROUTE_24_ACCURACY_RECOVERY_POSITION,
    ROUTE_24_AFTER_NPC_DIRECTIONS,
    ROUTE_24_CENTER_RECOVERY_POSITION,
    ROUTE_24_RECOVERY_POTION_RESERVE,
    ROUTE_24_REQUIRED_TRAINER_INDEXES,
    ROUTE_24_TRAINER_SEGMENTS,
    ROUTE_25_NON_HIKER_MOVE_SLOT,
    ROUTE_25_RECOVERY_POTION_RESERVE,
    ROUTE_25_REQUIRED_TRAINER_INDEXES,
    ROUTE_25_TRAINER_SEGMENTS,
    TM01_FIELD_MENU_CLOSE_PULSES,
    CascadeChapterError,
    CascadeChapterReport,
    CascadeCheckpoint,
    CascadeProgress,
    CascadeTiming,
    _cerulean_return_blocked_detour,
    _cerulean_return_direction,
    _choose_preferred_usable_move_slot,
    _cross_route_24_npc,
    _cross_route_24_recovery_npc,
    _move_verified,
    _reverse_directions,
    _run_cerulean_gym_trainer_with_potion,
    _run_cerulean_rival_with_potion,
    _run_misty_with_potion,
    _run_route_24_accuracy_battle_with_potion,
    _should_use_cerulean_rival_potion,
    _use_cerulean_rival_potion,
    _use_route_24_antidote_if_needed,
    _use_route_24_recovery_potion,
)
from pokemon_red_completion.economy import CERULEAN_RIVAL_POTION_RESERVE
from pokemon_red_completion.observation import (
    ABRA_SPECIES_ID,
    PIDGEOTTO_SPECIES_ID,
    WARTORTLE_SPECIES_ID,
    BattleMenuPhase,
    BattleMenuState,
    CascadeState,
    CeruleanChapterState,
    ItemId,
    MapId,
    RamAddress,
    RawGameState,
)


class _StartingEvidence:
    cerulean_snapshot = True


class _FinalEvidence:
    misty_victory_snapshot = True
    cascade_badge = True
    cascade_badge_mirror = True
    got_tm11 = True
    tm11_in_bag = True
    got_ss_ticket = True
    ss_ticket_in_bag = True


def test_cerulean_poison_reserve_covers_route_and_tunnel_contingencies() -> None:
    assert CERULEAN_ANTIDOTE_RESERVE == 3


def test_verified_cerulean_route_retries_a_swallowed_pedestrian_step() -> None:
    class Reader:
        state = RawGameState(True, MapId.CERULEAN_CITY, 0, 0, 1, 0, first_party_hp=10)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        actions = 0

        def execute(self, action: MacroAction) -> MacroAction:
            self.actions += 1
            if self.actions > 1:
                reader.state = replace(reader.state, player_x=(reader.state.player_x or 0) + 1)
            return action

    executor = Executor()
    final = _move_verified(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        ("right", "right"),
        "Cerulean rival staging",
    )

    assert (final.player_x, final.player_y) == (2, 0)
    assert executor.actions == 3


class _MemoryEmulator:
    frame_count = 0
    pressed_buttons = frozenset()

    def __init__(self, potion_quantity: int) -> None:
        self.memory = {
            int(RamAddress.NUM_BAG_ITEMS): int(potion_quantity > 0),
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: potion_quantity,
        }

    def read_u8(self, address: int) -> int:
        return self.memory.get(int(address), 0)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CERULEAN_GYM,
        player_x=5,
        player_y=2,
        party_count=1,
        battle_state=0,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
    first_party_level=24,
    first_party_hp=18,
    first_party_max_hp=66,
    first_party_status=0,
    battle_result=0,
    )


def _report() -> CascadeChapterReport:
    raw = _raw()
    evidence = cast(CascadeState, _FinalEvidence())
    records = tuple(
        CascadeCheckpoint(
            checkpoint_id=f"cascade_{index:02d}",
            label=f"Cascade checkpoint {index}",
            raw=raw,
            evidence=evidence,
        )
        for index in range(1, CASCADE_CHECKPOINT_COUNT + 1)
    )
    return CascadeChapterReport(
        starting_cerulean_evidence=cast(
            CeruleanChapterState,
            _StartingEvidence(),
        ),
        records=records,
        final_raw=raw,
        final_evidence=evidence,
        observed_route_24_trainers=ROUTE_24_REQUIRED_TRAINER_INDEXES,
        observed_route_25_trainers=ROUTE_25_REQUIRED_TRAINER_INDEXES,
        saw_rival_battle=True,
        rival_defeated=True,
        saw_nugget_rocket_battle=True,
        nugget_rocket_defeated=True,
        bills_house_left=True,
        saw_cerulean_gym_trainer_battle=True,
        cerulean_gym_trainer_defeated=True,
        saw_misty_battle=True,
        misty_defeated=True,
        frames_executed=141_000,
        actions_executed=2_100,
        controller_released=True,
    )


def test_route_constants_capture_the_collision_qualified_teacher() -> None:
    assert ROUTE_24_REQUIRED_TRAINER_INDEXES == (5, 4, 3, 2, 1)
    assert tuple(len(segment) for segment in ROUTE_24_TRAINER_SEGMENTS) == (
        4,
        4,
        4,
        4,
        4,
    )
    assert ROUTE_25_REQUIRED_TRAINER_INDEXES == (8, 3, 2, 5)
    assert tuple(len(segment) for segment in ROUTE_25_TRAINER_SEGMENTS) == (
        20,
        12,
        6,
        14,
    )
    assert len(CENTER_TO_RIVAL_STAGING_DIRECTIONS) == 34
    assert MART_REPEAT_CLERK_DIRECTIONS == ("right", "up", "up", "left", "left")
    assert MART_REPEAT_TO_CENTER_STAGING_DIRECTIONS[:4] == (
        "down",
        "down",
        "right",
        "down",
    )
    assert MART_REPEAT_CUSTOMER_CLEAR_ATTEMPTS == 32
    assert _reverse_directions(
        CENTER_HEAL_TO_PC_DIRECTIONS
    ) == CENTER_PC_TO_HEAL_DIRECTIONS
    assert CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS == ("left",)
    assert (
        *("up" for _ in range(4)),
        *("right" for _ in range(12)),
        *("up" for _ in range(13)),
    ) == ROUTE_24_AFTER_NPC_DIRECTIONS
    assert RIVAL_TRIGGER_DIRECTIONS == ("up",)
    assert TM01_FIELD_MENU_CLOSE_PULSES == 2
    assert CERULEAN_RIVAL_MAX_POTION_RESERVE == CERULEAN_RIVAL_POTION_RESERVE + 4
    assert ROUTE_24_RECOVERY_POTION_RESERVE == 6
    assert cascade_module.ROUTE_24_FINAL_RECOVERY_POSITION == 4
    assert ROUTE_25_RECOVERY_POTION_RESERVE == 5
    assert CERULEAN_GYM_POTION_RESERVE == 8
    assert CERULEAN_GYM_START_POTION_RESERVE == 7
    assert ROCKET_THIEF_POTION_RESERVE == 4
    assert ROUTE_24_CENTER_RECOVERY_POSITION == 2
    assert ROUTE_24_REQUIRED_TRAINER_INDEXES[ROUTE_24_CENTER_RECOVERY_POSITION] == 3
    assert CERULEAN_GYM_TRAINER_MOVE_SLOT == 3
    assert CERULEAN_GYM_TRAINER_RECOVERY_HP == 30
    assert ROUTE_25_NON_HIKER_MOVE_SLOT == 3
    assert RIVAL_CENTER_NPC_CORRECTION_DIRECTIONS == (
        "down",
        "right",
        "right",
        "right",
        "up",
    )
    assert _cerulean_return_direction((11, 3)) == "left"
    assert _cerulean_return_direction((3, 4)) == "up"


def test_route_25_policy_falls_back_when_preferred_pp_is_exhausted() -> None:
    raw = replace(
        _raw(),
        battle_state=2,
        first_party_moves=(0x21, 0x27, 0x05, 0x37),
        first_party_pp=(35, 30, 0, 24),
    )

    assert _choose_preferred_usable_move_slot(raw, preferred_slot=3) == 4
    assert (
        _choose_preferred_usable_move_slot(
            replace(raw, first_party_pp=(35, 30, 1, 24)),
            preferred_slot=3,
        )
        == 3
    )
    assert _cerulean_return_blocked_detour((5, 3), "left") == "down"
    assert BILL_PC_TO_HUMAN_DIRECTIONS == (
        "right",
        "right",
        "right",
        "up",
    )
    assert BILL_EXIT_DIRECTIONS == ("down", "left", "down", "down")
    assert tuple(len(segment) for segment in BILL_TO_CENTER_SEGMENTS) == (
        9,
        14,
        6,
        12,
        20,
        17,
        4,
        4,
        4,
        4,
        4,
        4,
        1,
        42,
    )
    assert frozenset({6, 13, 14}) == BILL_RETURN_WAIT_SEGMENTS
    assert len(GYM_TRAINER_DIRECTIONS) == 19
    assert GYM_TRAINER_TO_MISTY_DIRECTIONS == ("up", "left")


def test_repeat_mart_clerk_waits_for_customer_to_vacate() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.x = 4
            self.left_pulses = 0

        def execute(self, action: MacroAction) -> None:
            if action.kind is MacroActionKind.MOVE and action.value == "left":
                self.left_pulses += 1
                if self.left_pulses >= 4:
                    self.x -= 1

        def read(self) -> RawGameState:
            return replace(
                _raw(),
                map_id=MapId.CERULEAN_MART,
                player_x=self.x,
                player_y=5,
            )

    runtime = Runtime()
    final = cascade_module._settle_mart_repeat_clerk_stance(
        runtime,  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
        replace(DEFAULT_CASCADE_TIMING, dialogue_wait_frames=1),
    )

    assert (final.player_x, final.player_y) == (2, 5)
    assert runtime.left_pulses == 5


def test_repeat_mart_clerk_return_retries_blocked_exit_customer() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.map_id = MapId.CERULEAN_MART
            self.x = 2
            self.y = 5
            self.right_attempts = 0

        def execute(self, action: MacroAction) -> None:
            if action.kind is not MacroActionKind.MOVE:
                return
            if self.map_id is not MapId.CERULEAN_MART:
                return
            if action.value == "down" and self.x == 2 and self.y < 7:
                self.y += 1
            elif action.value == "right" and (self.x, self.y) == (2, 7):
                self.right_attempts += 1
                if self.right_attempts >= 3:
                    self.x = 3
            elif action.value == "down" and (self.x, self.y) == (3, 7):
                self.map_id = MapId.CERULEAN_CITY
                self.x, self.y = (19, 18)

        def read(self) -> RawGameState:
            return replace(
                _raw(),
                map_id=self.map_id,
                player_x=self.x,
                player_y=self.y,
            )

    runtime = Runtime()
    cascade_module._return_from_cerulean_repeat_clerk(
        runtime,  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
        replace(DEFAULT_CASCADE_TIMING, dialogue_wait_frames=1),
    )

    assert (runtime.map_id, runtime.x, runtime.y) == (MapId.CERULEAN_CITY, 19, 18)
    assert runtime.right_attempts == 3


def test_reverse_directions_is_exact_and_involutive() -> None:
    route = ("up", "right", "right", "down", "left")
    reversed_route = _reverse_directions(route)

    assert reversed_route == ("right", "up", "left", "left", "down")
    assert _reverse_directions(reversed_route) == route


class _Route24CrossingReader:
    def __init__(self, *, blocked_pulses: int) -> None:
        self.x = 16
        self.y = 16
        self.blocked_pulses = blocked_pulses

    def read(self) -> RawGameState:
        return replace(
            _raw(),
            map_id=MapId.CERULEAN_CITY,
            player_x=self.x,
            player_y=self.y,
            first_party_hp=51,
        )


class _Route24CrossingExecutor:
    def __init__(self, reader: _Route24CrossingReader) -> None:
        self.reader = reader
        self.left_pulses = 0

    def execute(self, action: MacroAction) -> None:
        if action.kind is not MacroActionKind.MOVE or action.value != "left":
            return
        self.left_pulses += 1
        if self.reader.blocked_pulses:
            self.reader.blocked_pulses -= 1
        else:
            self.reader.x -= 1


def test_route_24_npc_crossing_retries_blocked_inputs_until_live_progress() -> None:
    reader = _Route24CrossingReader(blocked_pulses=5)
    executor = _Route24CrossingExecutor(reader)

    _cross_route_24_npc(executor, reader, DEFAULT_CASCADE_TIMING)

    assert (reader.x, reader.y) == (8, 16)
    assert executor.left_pulses == 13


def test_route_24_npc_crossing_tolerates_qualified_long_npc_blockage() -> None:
    reader = _Route24CrossingReader(blocked_pulses=39)
    executor = _Route24CrossingExecutor(reader)

    _cross_route_24_npc(executor, reader, DEFAULT_CASCADE_TIMING)

    assert (reader.x, reader.y) == (8, 16)
    assert executor.left_pulses == 47


def test_route_24_npc_crossing_fails_closed_when_progress_never_occurs() -> None:
    reader = _Route24CrossingReader(blocked_pulses=10_000)
    executor = _Route24CrossingExecutor(reader)

    with pytest.raises(CascadeChapterError, match="exhausted its bounded progress retries"):
        _cross_route_24_npc(executor, reader, DEFAULT_CASCADE_TIMING)

    assert (reader.x, reader.y) == (16, 16)
    assert executor.left_pulses == 72


def test_route_24_recovery_npc_crossing_retries_blocked_east_inputs() -> None:
    class Reader:
        x = 8

        def read(self) -> RawGameState:
            return replace(
                _raw(),
                map_id=MapId.CERULEAN_CITY,
                player_x=self.x,
                player_y=16,
                first_party_hp=51,
            )

    reader = Reader()

    class Executor:
        blocked = 3
        right_pulses = 0

        def execute(self, action: MacroAction) -> None:
            if action.kind is not MacroActionKind.MOVE or action.value != "right":
                return
            self.right_pulses += 1
            if self.blocked:
                self.blocked -= 1
            else:
                reader.x += 1

    executor = Executor()

    _cross_route_24_recovery_npc(executor, reader, DEFAULT_CASCADE_TIMING)

    assert reader.x == 17
    assert executor.right_pulses == 12


def test_cascade_timing_defaults_are_positive_and_pin_qualified_delays() -> None:
    assert CascadeTiming() == DEFAULT_CASCADE_TIMING
    assert DEFAULT_CASCADE_TIMING.rival_seed_wait_frames == 41
    assert DEFAULT_CASCADE_TIMING.misty_seed_wait_frames == 2
    assert DEFAULT_CASCADE_TIMING.post_battle_cleanup_pulses == 1
    assert DEFAULT_CASCADE_TIMING.gym_trainer_cleanup_pulses == 3
    assert DEFAULT_CASCADE_TIMING.bill_ticket_cleanup_pulses == 9
    assert DEFAULT_CASCADE_TIMING.misty_reward_pulses == 9
    assert DEFAULT_CASCADE_TIMING.max_route_24_npc_attempts == 8
    for field in fields(CascadeTiming):
        if field.name == "battle_runtime":
            continue
        value = getattr(DEFAULT_CASCADE_TIMING, field.name)
        assert isinstance(value, int)
        assert not isinstance(value, bool)
        assert value > 0


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_cascade_timing_rejects_unbounded_scalar_values(invalid: object) -> None:
    for field in fields(CascadeTiming):
        if field.name == "battle_runtime":
            continue
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_CASCADE_TIMING, **{field.name: invalid})


def test_cascade_timing_rejects_a_non_runtime_battle_controller() -> None:
    with pytest.raises(ValueError, match="battle_runtime"):
        replace(DEFAULT_CASCADE_TIMING, battle_runtime=object())


def test_cerulean_rival_recovery_waits_for_a_semantic_risk_gate() -> None:
    pidgeotto_threshold = CERULEAN_RIVAL_RECOVERY_HP_THRESHOLDS[
        PIDGEOTTO_SPECIES_ID
    ]
    pidgeotto = replace(
        _raw(),
        battle_state=2,
        enemy_species_id=PIDGEOTTO_SPECIES_ID,
        first_party_hp=pidgeotto_threshold + 1,
        first_party_max_hp=49,
    )

    assert not _should_use_cerulean_rival_potion(pidgeotto)
    assert _should_use_cerulean_rival_potion(
        replace(pidgeotto, first_party_hp=pidgeotto_threshold)
    )
    assert not _should_use_cerulean_rival_potion(
        replace(
            pidgeotto,
            enemy_species_id=ABRA_SPECIES_ID,
            first_party_hp=48,
        )
    )
    assert _should_use_cerulean_rival_potion(
        replace(
            pidgeotto,
            enemy_species_id=ABRA_SPECIES_ID,
            first_party_hp=CERULEAN_RIVAL_RECOVERY_HP_THRESHOLDS[
                ABRA_SPECIES_ID
            ],
        )
    )


@pytest.mark.parametrize(
    "change",
    (
        {"first_party_hp": 0},
        {"first_party_hp": None},
        {"first_party_hp": 50},
        {"first_party_max_hp": None},
        {"enemy_species_id": None},
    ),
)
def test_cerulean_rival_recovery_rejects_ambiguous_live_evidence(
    change: dict[str, object],
) -> None:
    base = replace(
        _raw(),
        battle_state=2,
        enemy_species_id=PIDGEOTTO_SPECIES_ID,
        first_party_hp=22,
        first_party_max_hp=49,
    )
    raw = replace(base, **change)

    with pytest.raises(ValueError, match="valid live HP/species"):
        _should_use_cerulean_rival_potion(raw)


def test_cerulean_rival_living_reserve_selects_a_legal_attack() -> None:
    reserve = replace(
        _raw(),
        battle_state=2,
        active_party_index=1,
        active_party_moves=(0, 0x2C, 0x10, 0),
        active_party_pp=(0, 5, 10, 0),
    )

    assert cascade_module._cerulean_rival_reserve_move_slot(reserve) == 2
    with pytest.raises(CascadeChapterError, match="no legal attack"):
        cascade_module._cerulean_rival_reserve_move_slot(
            replace(reserve, active_party_pp=(0, 0, 0, 0))
        )


def test_cerulean_rival_recovery_reuses_one_bounded_intent_across_consecutive_heals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emulator = _MemoryEmulator(potion_quantity=8)
    final = replace(_raw(), first_party_hp=19, first_party_max_hp=51)
    intents = []
    calls = 0

    def fake_runtime(*args: object, **kwargs: object) -> RawGameState:
        nonlocal calls
        del args
        calls += 1
        intents.append(kwargs["intent"])
        if calls <= 2:
            try:
                raise cascade_module._PauseForCeruleanRivalPotion
            except cascade_module._PauseForCeruleanRivalPotion as pause:
                raise BattleRuntimeError("paused for recovery") from pause
        return final

    def fake_use(*args: object) -> None:
        del args
        quantity_address = int(RamAddress.BAG_ITEMS) + 1
        emulator.memory[quantity_address] -= 1

    monkeypatch.setattr(cascade_module, "run_adaptive_trainer_battle", fake_runtime)
    monkeypatch.setattr(cascade_module, "_use_cerulean_rival_potion", fake_use)

    observed = _run_cerulean_rival_with_potion(
        cast(object, object()),
        cast(object, object()),
        emulator,
        DEFAULT_CASCADE_TIMING,
    )

    assert observed is final
    assert calls == 3
    assert intents[0] is intents[1] is intents[2]
    assert intents[0].resource_policy is BattleResourcePolicy.BOUNDED_RECOVERY
    assert (
        emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1)
        == ROUTE_24_RECOVERY_POTION_RESERVE
    )


def test_misty_spends_only_two_surplus_potions_and_reuses_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emulator = _MemoryEmulator(potion_quantity=ROCKET_THIEF_POTION_RESERVE + 2)
    low = replace(
        _raw(),
        map_id=MapId.CERULEAN_GYM,
        battle_state=2,
        active_party_hp=MISTY_RECOVERY_HP,
        active_party_max_hp=64,
    )
    final = replace(low, battle_state=0, active_party_hp=43)
    intent = BattleIntent("defeat_misty", battle_plan_id="misty-test")
    intents: list[BattleIntent] = []
    calls = 0

    def fake_runtime(*args: object, **kwargs: object) -> RawGameState:
        nonlocal calls
        calls += 1
        intents.append(cast(BattleIntent, kwargs["intent"]))
        if calls <= 2:
            policy = cast(object, args[2])
            try:
                cast(object, policy)(low)  # type: ignore[operator]
            except cascade_module._PauseForMistyPotion as pause:
                raise BattleRuntimeError("paused for Misty recovery") from pause
        return final

    def fake_use(*args: object) -> None:
        del args
        emulator.memory[int(RamAddress.BAG_ITEMS) + 1] -= 1

    monkeypatch.setattr(cascade_module, "run_adaptive_trainer_battle", fake_runtime)
    monkeypatch.setattr(cascade_module, "_use_cerulean_rival_potion", fake_use)

    observed = _run_misty_with_potion(
        cast(object, object()),
        cast(object, object()),
        emulator,
        lambda _raw: 3,
        DEFAULT_CASCADE_TIMING,
        intent,
    )

    assert observed is final
    assert calls == 3
    assert intents == [intent, intent, intent]
    assert _bag_quantity_for_test(emulator) == ROCKET_THIEF_POTION_RESERVE


def test_cerulean_rival_recovery_latches_the_transient_exact_heal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emulator = _MemoryEmulator(potion_quantity=3)

    class Reader:
        state = replace(
            _raw(),
            battle_state=2,
            enemy_species_id=PIDGEOTTO_SPECIES_ID,
            first_party_hp=10,
            first_party_max_hp=50,
        )
        phase = BattleMenuPhase.MAIN

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(
                self.phase,
                selected_main_command=1
                if self.phase is BattleMenuPhase.MAIN
                else None,
            )

    reader = Reader()

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            if len(self.actions) == 1:
                reader.state = replace(reader.state, first_party_hp=30)
                reader.phase = BattleMenuPhase.UNKNOWN
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = 2

    executor = Executor()
    waits = 0

    def fake_wait(*args: object) -> None:
        nonlocal waits
        del args
        waits += 1
        if waits == 1:
            reader.state = replace(reader.state, first_party_hp=22)
        elif executor.actions[-1].kind is MacroActionKind.CANCEL:
            reader.phase = BattleMenuPhase.MAIN

    monkeypatch.setattr(cascade_module, "_battle_pulse", lambda *args: None)
    monkeypatch.setattr(cascade_module, "_select_bag_item", lambda *args: None)
    monkeypatch.setattr(cascade_module, "_wait", fake_wait)

    _use_cerulean_rival_potion(
        cast(object, reader),
        cast(object, executor),
        emulator,
        DEFAULT_CASCADE_TIMING,
    )

    assert tuple(action.kind for action in executor.actions) == (
        MacroActionKind.CONFIRM,
        MacroActionKind.CANCEL,
    )
    assert reader.state.first_party_hp == 22
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == 2


def test_route_24_recovery_consumes_the_retained_field_potion() -> None:
    emulator = _MemoryEmulator(potion_quantity=ROUTE_24_RECOVERY_POTION_RESERVE)
    emulator.memory[int(RamAddress.CURRENT_MENU_ITEM)] = 2

    class Reader:
        state = replace(
            _raw(),
            map_id=MapId.ROUTE_24,
            first_party_hp=7,
            first_party_max_hp=59,
            first_party_status=8,
        )

        def read(self) -> RawGameState:
            return self.state

        def read_input_readiness(self) -> object:
            return type("Ready", (), {"ready": True})()

    reader = Reader()

    class Executor:
        actions: list[MacroAction] = []
        confirms = 0

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            if action.kind is not MacroActionKind.CONFIRM:
                return
            self.confirms += 1
            if self.confirms == 1:
                emulator.memory[int(RamAddress.CURRENT_MENU_ITEM)] = 0
            elif self.confirms == 3:
                reader.state = replace(reader.state, first_party_hp=27)
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = (
                    ROUTE_25_RECOVERY_POTION_RESERVE
                )

    executor = Executor()
    _use_route_24_recovery_potion(
        reader,  # type: ignore[arg-type]
        executor,  # type: ignore[arg-type]
        emulator,
    )

    assert reader.state.first_party_hp == 27
    assert (
        emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1)
        == ROUTE_25_RECOVERY_POTION_RESERVE
    )
    assert sum(
        action.kind is MacroActionKind.CANCEL for action in executor.actions
    ) == FIELD_ITEM_MENU_CLOSE_PULSES


@pytest.mark.parametrize(
    "potion_quantity",
    (CERULEAN_GYM_START_POTION_RESERVE, CERULEAN_GYM_POTION_RESERVE),
)
def test_cerulean_gym_preserves_unused_potion_after_full_hp_victory(
    monkeypatch: pytest.MonkeyPatch,
    potion_quantity: int,
) -> None:
    emulator = _MemoryEmulator(potion_quantity=potion_quantity)
    starting = replace(
        _raw(),
        first_party_hp=61,
        first_party_max_hp=61,
        first_party_pp=(25, 30, 20, 25),
    )
    terminal = replace(starting, first_party_pp=(25, 30, 19, 25))

    class Reader:
        reads = 0

        def read(self) -> RawGameState:
            self.reads += 1
            return starting if self.reads == 1 else terminal

        def read_input_readiness(self) -> object:
            return type("Ready", (), {"ready": True})()

    monkeypatch.setattr(cascade_module, "_select_battle_move", lambda *_a, **_k: None)
    monkeypatch.setattr(cascade_module, "_wait", lambda *_a, **_k: None)

    observed = _run_cerulean_gym_trainer_with_potion(
        Reader(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        emulator,
        DEFAULT_CASCADE_TIMING,
        "Cerulean Gym trainer",
    )

    assert observed is terminal
    assert _bag_quantity_for_test(emulator) == potion_quantity


@pytest.mark.parametrize(
    "potion_quantity",
    (CERULEAN_GYM_START_POTION_RESERVE, CERULEAN_GYM_POTION_RESERVE),
)
def test_cerulean_gym_spends_exactly_one_potion_after_damaged_victory(
    monkeypatch: pytest.MonkeyPatch,
    potion_quantity: int,
) -> None:
    emulator = _MemoryEmulator(potion_quantity=potion_quantity)
    starting = replace(
        _raw(),
        first_party_hp=61,
        first_party_max_hp=61,
        first_party_pp=(25, 30, 20, 25),
    )
    terminal = replace(
        starting,
        first_party_hp=41,
        first_party_pp=(25, 30, 19, 25),
    )

    class Reader:
        reads = 0

        def read(self) -> RawGameState:
            self.reads += 1
            return starting if self.reads == 1 else terminal

        def read_input_readiness(self) -> object:
            return type("Ready", (), {"ready": True})()

    def fake_recovery(*_args: object, **kwargs: object) -> None:
        assert kwargs["starting_quantity"] == potion_quantity
        assert kwargs["ending_quantity"] == potion_quantity - 1
        emulator.memory[int(RamAddress.BAG_ITEMS) + 1] -= 1

    monkeypatch.setattr(cascade_module, "_select_battle_move", lambda *_a, **_k: None)
    monkeypatch.setattr(cascade_module, "_use_field_recovery_potion", fake_recovery)
    monkeypatch.setattr(cascade_module, "_wait", lambda *_a, **_k: None)

    observed = _run_cerulean_gym_trainer_with_potion(
        Reader(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        emulator,
        DEFAULT_CASCADE_TIMING,
        "Cerulean Gym trainer",
    )

    assert observed is terminal
    assert _bag_quantity_for_test(emulator) == potion_quantity - 1


def _bag_quantity_for_test(emulator: _MemoryEmulator) -> int:
    return emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1)


def test_route_24_accuracy_battle_spends_one_potion_at_low_hp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emulator = _MemoryEmulator(potion_quantity=ROUTE_24_RECOVERY_POTION_RESERVE)

    class Reader:
        state = replace(
            _raw(),
            map_id=MapId.ROUTE_24,
            battle_state=2,
            first_party_hp=ROUTE_24_ACCURACY_RECOVERY_HP,
            first_party_max_hp=56,
        )

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(BattleMenuPhase.MAIN, 0, None)

        def read_input_readiness(self) -> object:
            return type("Ready", (), {"ready": self.state.battle_state == 0})()

    reader = Reader()

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            reader.state = replace(reader.state, battle_state=0)

    executor = Executor()
    recoveries = 0
    selections = 0

    def fake_recovery(*args: object) -> None:
        nonlocal recoveries
        del args
        recoveries += 1
        reader.state = replace(reader.state, first_party_hp=56)
        emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = ROUTE_25_RECOVERY_POTION_RESERVE

    def fake_select(*args: object, **kwargs: object) -> None:
        nonlocal selections
        del args, kwargs
        selections += 1
        if selections == 2:
            reader.state = replace(reader.state, battle_state=0)

    monkeypatch.setattr(cascade_module, "_select_battle_move", fake_select)
    monkeypatch.setattr(cascade_module, "_use_cerulean_rival_potion", fake_recovery)
    monkeypatch.setattr(cascade_module, "_wait", lambda *args: None)

    result = _run_route_24_accuracy_battle_with_potion(
        cast(object, reader),
        cast(object, executor),
        emulator,
        DEFAULT_CASCADE_TIMING,
        "Route 24 trainer 2",
    )

    assert result.battle_state == 0
    assert recoveries == 1
    assert selections == 2
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == ROUTE_25_RECOVERY_POTION_RESERVE
    assert ROUTE_24_ACCURACY_RECOVERY_POSITION > ROUTE_24_CENTER_RECOVERY_POSITION


def test_route_24_antidote_uses_the_immediate_field_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_field_cure(*args: object, **kwargs: object) -> None:
        del args
        observed.update(kwargs)

    monkeypatch.setattr(cascade_module, "_use_field_antidote_if_needed", fake_field_cure)

    _use_route_24_antidote_if_needed(
        cast(object, object()),
        cast(object, object()),
        cast(object, object()),
    )

    assert observed == {"expected_map": MapId.ROUTE_24, "label": "Route 24"}


@pytest.mark.parametrize(
    "quantity",
    (0, CERULEAN_RIVAL_MAX_POTION_RESERVE + 1),
)
def test_cerulean_rival_recovery_rejects_an_invalid_fixed_reserve(
    quantity: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emulator = _MemoryEmulator(potion_quantity=quantity)
    called = False

    def fake_runtime(*args: object, **kwargs: object) -> RawGameState:
        nonlocal called
        del args, kwargs
        called = True
        return _raw()

    monkeypatch.setattr(cascade_module, "run_adaptive_trainer_battle", fake_runtime)

    with pytest.raises(CascadeChapterError, match="outside its fixed bound"):
        _run_cerulean_rival_with_potion(
            cast(object, object()),
            cast(object, object()),
            emulator,
            DEFAULT_CASCADE_TIMING,
        )

    assert not called


def test_progress_and_checkpoint_records_are_immutable() -> None:
    progress = CascadeProgress(
        checkpoint_id="misty_defeated",
        label="Defeated Misty",
        completed=CASCADE_CHECKPOINT_COUNT,
        total=CASCADE_CHECKPOINT_COUNT,
        frames_executed=141_000,
    )
    record = _report().records[-1]

    with pytest.raises(FrozenInstanceError):
        progress.completed = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.label = "changed"  # type: ignore[misc]


def test_report_is_complete_honest_and_json_safe() -> None:
    report = _report()

    assert report.passed
    assert len(report.checkpoints()) == CASCADE_CHECKPOINT_COUNT
    assert report.checkpoints()[-1][2] is report.final_raw
    payload = report.public_dict()
    assert payload["status"] == "ok"
    assert payload["route"] == {
        "route_24_trainers": [5, 4, 3, 2, 1],
        "route_25_trainers": [8, 3, 2, 5],
        "rival_battle_observed": True,
        "nugget_rocket_battle_observed": True,
        "bill_help_verified": True,
        "gym_trainer_battle_observed": True,
        "misty_battle_observed": True,
    }
    assert payload["cascade"] == {
        "victory_verified": True,
        "badge_verified": True,
        "tm11_verified": True,
        "ss_ticket_verified": True,
        "wartortle_level": 24,
        "wartortle_hp": 18,
        "wartortle_max_hp": 66,
        "wartortle_status": 0,
    }
    assert "/Users/" not in json.dumps(payload)


@pytest.mark.parametrize(
    "change",
    (
        {"records": ()},
        {"observed_route_24_trainers": (5, 4, 3, 2)},
        {"observed_route_25_trainers": (8, 3, 2)},
        {"saw_cerulean_gym_trainer_battle": False},
        {"cerulean_gym_trainer_defeated": False},
        {"misty_defeated": False},
        {"controller_released": False},
    ),
)
def test_report_rejects_missing_or_skipped_evidence(
    change: dict[str, object],
) -> None:
    assert not replace(_report(), **change).passed
