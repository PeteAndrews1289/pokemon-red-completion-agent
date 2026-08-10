from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
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
    MT_MOON_B1F_DIRECTIONS,
    MT_MOON_B1F_EXIT_DIRECTIONS,
    MT_MOON_B1F_EXIT_SEED_WAIT,
    MT_MOON_B1F_SEED_WAITS,
    MT_MOON_B2F_EXIT_DIRECTIONS,
    MT_MOON_B2F_EXIT_SEED_WAIT,
    MT_MOON_B2F_SEED_WAITS,
    MT_MOON_B2F_TO_ROCKET_DIRECTIONS,
    MT_MOON_ZUBAT_PRE_THROW_WAIT,
    MT_MOON_ZUBAT_SEED_WAIT,
    PEWTER_TO_CENTER_DIRECTIONS,
    POST_KO_SWITCH_DECLINE_PULSES,
    ROCKET_TO_SUPER_NERD_DIRECTIONS,
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
    _CountingChapterExecutor,
    _finish_battle,
    _move_with_seed_waits,
    _pp_at,
    _reverse_directions,
    _route_3_victory_sequence,
    _select_battle_move,
    _use_route_3_battle_potion,
    _use_route_3_recovery_potion,
)
from pokemon_red_completion.economy import (
    CERULEAN_RIVAL_POTION_RESERVE,
    PEWTER_POTION_PURCHASE_QUANTITY,
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
        route_3_reached=_raw(MapId.ROUTE_3, 0, 10, level=12, hp=33, max_hp=33),
        route_3_battles=tuple(
            _raw(MapId.ROUTE_3, 10 + position, 6, battle_state=2) for position in range(4)
        ),
        route_3_victories=tuple(_raw(MapId.ROUTE_3, 10 + position, 6) for position in range(4)),
        route_4_reached=_raw(MapId.ROUTE_4, 9, 17),
        mt_moon_entered=_raw(MapId.MT_MOON_1F, 14, 35),
        mt_moon_b1f_reached=_raw(MapId.MT_MOON_B1F, 5, 5),
        mt_moon_b2f_reached=_raw(MapId.MT_MOON_B2F, 21, 17),
        rocket_battle=_raw(MapId.MT_MOON_B2F, 11, 19, battle_state=2),
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


class _ScriptedBattleReader:
    def __init__(
        self,
        menu_states: tuple[BattleMenuState, ...],
        *,
        pp: int = 10,
        hp: int = 30,
    ) -> None:
        self._menu_states = list(menu_states)
        self.pp = pp
        self.hp = hp

    def read(self) -> RawGameState:
        return replace(
            _raw(MapId.ROUTE_3, 11, 6, battle_state=2),
            first_party_hp=self.hp,
            first_party_pp=(34, 30, 20, self.pp),
        )

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        assert raw.battle_state == 2
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
    assert _reverse_directions(CENTER_HEAL_TO_PC_DIRECTIONS) == (
        CENTER_PC_TO_HEAL_DIRECTIONS
    )
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
    assert ROUTE_3_REJOIN_SEED_WAIT == 8
    assert len(ROUTE_4_FIRST_LEDGE_APPROACH_DIRECTIONS) == 20
    assert len(ROUTE_4_MIDDLE_DIRECTIONS) == 39
    assert len(ROUTE_4_FINAL_APPROACH_DIRECTIONS) == 10


def test_route_3_recovery_consumes_only_the_guaranteed_pc_potion() -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: CERULEAN_RIVAL_POTION_RESERVE,
            int(RamAddress.CURRENT_MENU_ITEM): 2,
        }

        def read_u8(self, address: int) -> int:
            return self.memory.get(int(address), 0)

    emulator = Emulator()

    class Reader:
        state = replace(
            _raw(MapId.ROUTE_3, 11, 6, level=13, hp=10, max_hp=35),
            first_party_status=8,
        )

        def read(self) -> RawGameState:
            return self.state

        def read_input_readiness(self) -> InputReadiness:
            return READY

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
                reader.state = replace(reader.state, first_party_hp=30)
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = (
                    PEWTER_POTION_PURCHASE_QUANTITY
                )

    executor = Executor()
    _use_route_3_recovery_potion(
        _CountingChapterExecutor(executor),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
    )

    assert reader.state.first_party_hp == 30
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == 13
    assert sum(
        action.kind is MacroActionKind.CANCEL for action in executor.actions
    ) == 4


def test_route_3_battle_recovery_preserves_the_twelve_potion_floor() -> None:
    class Emulator:
        memory = {
            int(RamAddress.NUM_BAG_ITEMS): 1,
            int(RamAddress.BAG_ITEMS): int(ItemId.POTION),
            int(RamAddress.BAG_ITEMS) + 1: 13,
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
                emulator.memory[int(RamAddress.BAG_ITEMS) + 1] = 12

    _use_route_3_battle_potion(
        _CountingChapterExecutor(Executor()),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        quantity_floor=12,
        label="Route 3 trainer 1",
    )

    assert reader.state.first_party_hp == 33
    assert emulator.read_u8(int(RamAddress.BAG_ITEMS) + 1) == 12
    assert reader.selected_main_command == 0


def test_cerulean_qualification_stops_at_city_entry_not_the_gym() -> None:
    assert CERULEAN_QUALIFICATION_BOUNDARIES[-1] is CeruleanBoundary.CERULEAN_WEST_ENTRY
    assert len(CERULEAN_QUALIFICATION_BOUNDARIES) == 8


def test_cerulean_timing_defaults_are_positive_bounded_integers() -> None:
    assert CeruleanTiming() == DEFAULT_CERULEAN_TIMING
    assert DEFAULT_CERULEAN_TIMING.super_nerd_preselect_wait_frames == 1
    assert DEFAULT_CERULEAN_TIMING.b1f_exit_seed_wait_frames == 2
    assert all(
        isinstance(getattr(DEFAULT_CERULEAN_TIMING, field.name), int)
        and not isinstance(getattr(DEFAULT_CERULEAN_TIMING, field.name), bool)
        and getattr(DEFAULT_CERULEAN_TIMING, field.name) > 0
        for field in fields(CeruleanTiming)
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


def test_battle_completion_declines_switch_without_cancelling_evolution() -> None:
    class Reader:
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
                reader.state = replace(
                    reader.state,
                    party_species_ids=(WARTORTLE_SPECIES_ID, 0x6B),
                )
            elif self.confirms == 2:
                reader.state = replace(reader.state, battle_state=0)

    executor = Executor()
    final = _finish_battle(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        DEFAULT_CERULEAN_TIMING,
        MapId.MT_MOON_B2F,
        "evolution regression",
    )

    inputs = [
        action.kind
        for action in executor.actions
        if action.kind is not MacroActionKind.WAIT
    ]
    assert inputs[:POST_KO_SWITCH_DECLINE_PULSES] == [
        MacroActionKind.CANCEL
    ] * POST_KO_SWITCH_DECLINE_PULSES
    assert inputs[POST_KO_SWITCH_DECLINE_PULSES:] == [
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
    ]
    assert final.party_species_ids == (WARTORTLE_SPECIES_ID, 0x6B)


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

    assert MacroActionKind.CANCEL not in {
        action.kind for action in executor.actions
    }


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
    assert public["mt_moon"] == {
        "required_rocket_battle_observed": True,
        "super_nerd_battle_observed": True,
        "helix_fossil_verified": True,
        "zubat_search_attempts": 1,
        "zubat_movement_retries": 0,
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
