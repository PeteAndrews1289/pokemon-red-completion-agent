from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    BROCK_GYM_LEADER_NUMBER,
    BROCK_OPPONENT_ID,
    BROCK_TRAINER_CLASS_ID,
    BUBBLE_MOVE_ID,
    SQUIRTLE_SPECIES_ID,
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    ItemId,
    MapId,
    NorthboundPhase,
    OaksErrandPhase,
    OaksErrandState,
    PewterChapterState,
    RawGameState,
    TravelBoundary,
)
from pokemon_red_completion.pewter import (
    DEFAULT_PEWTER_TIMING,
    FOREST_ROUTE_DIRECTIONS,
    GYM_TO_BROCK_DIRECTIONS,
    LAB_TO_PALLET_DIRECTIONS,
    PALLET_TO_ROUTE_1_DIRECTIONS,
    PEWTER_CENTER_TO_GYM_DIRECTIONS,
    PEWTER_CHECKPOINT_COUNT,
    PEWTER_TO_CENTER_DIRECTIONS,
    PEWTER_TO_GYM_DIRECTIONS,
    ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
    ROUTE_1_TRAINING_TO_VIRIDIAN_DIRECTIONS,
    ROUTE_2_TO_FOREST_GATE_DIRECTIONS,
    VIRIDIAN_CENTER_RETURN_DIRECTIONS,
    VIRIDIAN_TO_CENTER_DIRECTIONS,
    VIRIDIAN_TO_ROUTE_1_TRAINING_DIRECTIONS,
    VIRIDIAN_TO_ROUTE_2_DIRECTIONS,
    PewterChapterError,
    PewterChapterReport,
    PewterProgress,
    PewterTiming,
    _bug_catcher_continuation_move,
    _expect_brock_transit_ready,
    _finish_battle,
    _is_healed_route_1_capability_party,
    _move_without_battles_with_retries,
    _seek_route_1_training_battle,
    _training_search_jitter_frames,
    _wild_training_continuation_move,
)


def _raw(
    map_id: MapId,
    x: int,
    y: int,
    *,
    level: int = 9,
    hp: int = 21,
    max_hp: int = 27,
    battle_state: int = 0,
    badge_bits: int = 0,
    bag: tuple[int, ...] = (),
    bubble_pp: int = 26,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=x,
        player_y=y,
        party_count=1,
        battle_state=battle_state,
        badge_bits=badge_bits,
        bag_item_ids=bag,
        event_flags=b"",
        party_species_ids=(SQUIRTLE_SPECIES_ID,),
        first_party_level=level,
        first_party_hp=hp,
        first_party_max_hp=max_hp,
        first_party_status=0,
        battle_result=0,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(4, 30, bubble_pp, 0),
    )


def _pokedex() -> OaksErrandState:
    return OaksErrandState(
        phase=OaksErrandPhase.POKEDEX_OBTAINED,
        joy_ignore=0,
        lab_script=18,
        mart_script=2,
        battled_rival=True,
        got_oaks_parcel=True,
        oak_got_parcel=True,
        got_pokedex=True,
        parcel_in_bag=False,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_level=6,
        first_party_hp=21,
        first_party_max_hp=21,
        battle_result=2,
        map_id=MapId.OAKS_LAB,
        battle_state=0,
    )


def test_bug_catcher_continuation_prefers_bubble_then_falls_back_to_tackle() -> None:
    battle = _raw(
        MapId.VIRIDIAN_FOREST,
        1,
        18,
        level=8,
        battle_state=2,
    )

    assert (
        _bug_catcher_continuation_move(replace(battle, first_party_pp=(1, 30, 29, 0)))
        == BUBBLE_MOVE_ID
    )
    assert _bug_catcher_continuation_move(replace(battle, first_party_pp=(1, 30, 0, 0))) == 0x21
    with pytest.raises(PewterChapterError, match="no usable Tackle or Bubble"):
        _bug_catcher_continuation_move(replace(battle, first_party_pp=(0, 30, 0, 0)))
    with pytest.raises(PewterChapterError, match="ended before continuation"):
        _bug_catcher_continuation_move(replace(battle, battle_state=0))


def test_wild_training_uses_bubble_after_learning_it_to_bypass_harden() -> None:
    battle = _raw(
        MapId.VIRIDIAN_FOREST,
        8,
        7,
        level=8,
        battle_state=1,
    )

    assert (
        _wild_training_continuation_move(replace(battle, first_party_pp=(20, 30, 29, 0)))
        == BUBBLE_MOVE_ID
    )
    assert _wild_training_continuation_move(replace(battle, first_party_pp=(20, 30, 0, 0))) == 0x21
    with pytest.raises(PewterChapterError, match="no usable Tackle or Bubble"):
        _wild_training_continuation_move(replace(battle, first_party_pp=(0, 30, 0, 0)))
    with pytest.raises(PewterChapterError, match="ended before continuation"):
        _wild_training_continuation_move(replace(battle, battle_state=0))


def test_npc_safe_corridor_retries_a_blocked_step_without_skipping_it() -> None:
    origin = _raw(MapId.VIRIDIAN_CITY, 21, 35, level=6, max_hp=21)

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
            assert action.value == "up"
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
        "unit moving-NPC corridor",
        expected_map_id=MapId.VIRIDIAN_CITY,
        maximum_step_attempts=3,
        step_retry_wait_frames=1,
    )

    assert (final.player_x, final.player_y) == (21, 33)
    assert retries == 1
    assert executor.movement_requests == 3


def test_npc_safe_corridor_fails_closed_after_its_retry_bound() -> None:
    class Reader:
        state = _raw(MapId.VIRIDIAN_CITY, 21, 35, level=6, max_hp=21)

        def read(self) -> RawGameState:
            return self.state

    class Executor:
        def execute(self, _action: MacroAction) -> object:
            return object()

    with pytest.raises(PewterChapterError, match="bounded 2-attempt"):
        _move_without_battles_with_retries(
            Executor(),  # type: ignore[arg-type]
            Reader(),  # type: ignore[arg-type]
            ("up",),
            "unit permanently blocked corridor",
            expected_map_id=MapId.VIRIDIAN_CITY,
            maximum_step_attempts=2,
            step_retry_wait_frames=1,
        )


def test_training_search_jitter_sweeps_distinct_bounded_rng_phases() -> None:
    values = tuple(_training_search_jitter_frames(index) for index in range(1, 32))

    assert set(values) == set(range(1, 32))
    assert _training_search_jitter_frames(32) == 1
    for invalid in (0, -1, True, 1.5):
        with pytest.raises(PewterChapterError, match="attempt is invalid"):
            _training_search_jitter_frames(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("phase", "expected_continuations"),
    ((BattleMenuPhase.MOVE, 1), (BattleMenuPhase.UNKNOWN, 0)),
)
def test_battle_continuation_runs_only_at_an_actionable_menu(
    phase: BattleMenuPhase,
    expected_continuations: int,
) -> None:
    class Reader:
        state = _raw(MapId.VIRIDIAN_FOREST, 1, 18, battle_state=2)

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(phase, selected_move_slot=1)

        def read_input_readiness(self) -> InputReadiness:
            return InputReadiness(0, 0, 0, 0, 0, 0)

    reader = Reader()

    class Executor:
        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.CONFIRM and reader.state.battle_state == 2:
                reader.state = replace(reader.state, battle_state=0)
            return object()

    calls = 0

    def continuation(*args: object) -> None:
        nonlocal calls
        del args
        calls += 1
        reader.state = replace(reader.state, battle_state=0)

    final = _finish_battle(
        Executor(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        expected_battle_state=2,
        max_pulses=4,
        timing=DEFAULT_PEWTER_TIMING,
        label="unit adaptive battle",
        continuation=continuation,  # type: ignore[arg-type]
    )

    assert final.battle_state == 0
    assert calls == expected_continuations


def _gym_ready() -> PewterChapterState:
    return PewterChapterState(
        phase=NorthboundPhase.PEWTER_GYM_ENTERED,
        boundary=TravelBoundary.PEWTER_GYM_ENTRANCE,
        controls=InputReadiness(0, 0, 0, 0, 0, 0),
        local_script=0,
        current_map_script=0,
        oak_lab_script=18,
        got_oaks_parcel=True,
        oak_got_parcel=True,
        got_pokedex=True,
        parcel_in_bag=False,
        beat_brock=False,
        got_tm34=False,
        tm34_in_bag=False,
        boulder_badge=False,
        boulder_badge_mirror=False,
        current_opponent=0,
        trainer_class=0,
        engaged_trainer_class=0,
        gym_leader_number=0,
        map_id=MapId.PEWTER_GYM,
        player_x=4,
        player_y=13,
        party_count=1,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_hp=21,
        first_party_max_hp=27,
        first_party_level=9,
        battle_state=0,
        battle_result=2,
        first_party_status=0,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(4, 30, 26, 0),
    )


def _brock_battle() -> PewterChapterState:
    return replace(
        _gym_ready(),
        phase=NorthboundPhase.BROCK_BATTLE,
        boundary=TravelBoundary.UNKNOWN,
        local_script=3,
        current_map_script=3,
        current_opponent=BROCK_OPPONENT_ID,
        trainer_class=BROCK_TRAINER_CLASS_ID,
        engaged_trainer_class=BROCK_OPPONENT_ID,
        gym_leader_number=BROCK_GYM_LEADER_NUMBER,
        player_y=2,
        battle_state=2,
    )


def _brock_victory() -> PewterChapterState:
    return replace(
        _gym_ready(),
        phase=NorthboundPhase.BROCK_DEFEATED,
        boundary=TravelBoundary.UNKNOWN,
        beat_brock=True,
        got_tm34=True,
        tm34_in_bag=True,
        boulder_badge=True,
        boulder_badge_mirror=True,
        player_y=2,
        first_party_hp=27,
        first_party_max_hp=33,
        first_party_level=12,
        battle_result=0,
        first_party_pp=(4, 30, 23, 0),
    )


def _report() -> PewterChapterReport:
    gym_ready = _gym_ready()
    brock_battle = _brock_battle()
    brock_victory = _brock_victory()
    initial_viridian_heal = replace(
        _raw(
            MapId.VIRIDIAN_POKECENTER,
            3,
            3,
            level=6,
            hp=21,
            max_hp=21,
        ),
        first_party_moves=(0x21, 0x27, 0, 0),
        first_party_pp=(35, 30, 0, 0),
    )
    level_seven_heal = replace(
        initial_viridian_heal,
        first_party_level=7,
        first_party_max_hp=23,
        first_party_hp=23,
    )
    level_eight_heal = replace(
        initial_viridian_heal,
        first_party_level=8,
        first_party_hp=25,
        first_party_max_hp=25,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(35, 30, 30, 0),
    )
    viridian_healed = replace(
        level_eight_heal,
        first_party_level=9,
        first_party_hp=27,
        first_party_max_hp=27,
    )
    return PewterChapterReport(
        pokedex_evidence=_pokedex(),
        lab_exited=_raw(MapId.PALLET_TOWN, 12, 12, level=6, max_hp=21),
        viridian_reached=_raw(MapId.VIRIDIAN_CITY, 21, 35, level=6, max_hp=21),
        route_2_reached=_raw(MapId.ROUTE_2, 8, 71),
        forest_gate_reached=_raw(
            MapId.VIRIDIAN_FOREST_SOUTH_GATE,
            4,
            7,
            level=9,
            max_hp=27,
        ),
        forest_entered=_raw(MapId.VIRIDIAN_FOREST, 17, 47),
        forest_cleared=_raw(MapId.VIRIDIAN_FOREST_NORTH_GATE, 4, 7),
        pewter_reached=_raw(MapId.PEWTER_CITY, 18, 35),
        pewter_center_healed=_raw(MapId.PEWTER_POKECENTER, 3, 3, hp=27),
        gym_entered=_raw(MapId.PEWTER_GYM, 4, 13),
        brock_battle=_raw(MapId.PEWTER_GYM, 4, 2, battle_state=2),
        brock_defeated=_raw(
            MapId.PEWTER_GYM,
            4,
            2,
            level=12,
            hp=27,
            max_hp=33,
            badge_bits=1,
            bag=(ItemId.TM34_BIDE,),
            bubble_pp=23,
        ),
        gym_entry_evidence=gym_ready,
        brock_battle_evidence=brock_battle,
        brock_victory_evidence=brock_victory,
        reached_boundaries=tuple(TravelBoundary)[1:],
        saw_brock_battle=True,
        route_1_wild_flees=(),
        route_1_movement_retries=0,
        route_2_wild_flees=(),
        route_2_movement_retries=0,
        forest_wild_flees=(),
        forest_movement_retries=0,
        viridian_pre_forest_healed=viridian_healed,
        lab_rival_loss_recovery_required=False,
        route_1_capability_search_attempts=(1, 1, 1),
        route_1_capability_species_ids=(0x24, 0xA5, 0x24),
        route_1_capability_level=9,
        route_1_capability_heals=(
            initial_viridian_heal,
            level_seven_heal,
            level_eight_heal,
            viridian_healed,
        ),
        overworld_control_verified=True,
        frames_executed=70_043,
        actions_executed=954,
        controller_released=True,
    )


def test_pewter_route_is_source_stable_at_critical_segments() -> None:
    assert LAB_TO_PALLET_DIRECTIONS == ("down",) * 9
    assert len(PALLET_TO_ROUTE_1_DIRECTIONS) == 17
    assert len(ROUTE_1_TO_VIRIDIAN_DIRECTIONS) == 53
    assert len(VIRIDIAN_TO_ROUTE_1_TRAINING_DIRECTIONS) == 11
    assert len(ROUTE_1_TRAINING_TO_VIRIDIAN_DIRECTIONS) == 12
    assert len(VIRIDIAN_TO_CENTER_DIRECTIONS) == 16
    assert len(VIRIDIAN_CENTER_RETURN_DIRECTIONS) == 15
    assert len(VIRIDIAN_TO_ROUTE_2_DIRECTIONS) == 39
    assert len(ROUTE_2_TO_FOREST_GATE_DIRECTIONS) == 43
    assert len(FOREST_ROUTE_DIRECTIONS) == 135
    assert FOREST_ROUTE_DIRECTIONS[97:117] == (
        *(("down",) * 9),
        *(("left",) * 6),
        *(("up",) * 3),
        "left",
        "up",
    )
    assert len(PEWTER_TO_GYM_DIRECTIONS) == 44
    assert len(PEWTER_TO_CENTER_DIRECTIONS) == 15
    assert len(PEWTER_CENTER_TO_GYM_DIRECTIONS) == 40
    assert len(GYM_TO_BROCK_DIRECTIONS) == 17


def test_pewter_timing_defaults_are_positive_bounded_integers() -> None:
    assert PewterTiming() == DEFAULT_PEWTER_TIMING
    assert fields(PewterTiming)
    assert all(
        isinstance(getattr(DEFAULT_PEWTER_TIMING, field.name), int)
        and not isinstance(getattr(DEFAULT_PEWTER_TIMING, field.name), bool)
        and getattr(DEFAULT_PEWTER_TIMING, field.name) > 0
        for field in fields(PewterTiming)
    )


@pytest.mark.parametrize(("hp", "status"), ((1, 0), (19, 0x08)))
def test_brock_transit_accepts_living_healthy_or_resourced_poisoned_party(
    hp: int,
    status: int,
) -> None:
    _expect_brock_transit_ready(
        replace(_raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=hp), first_party_status=status),
        "unit Forest exit",
    )


@pytest.mark.parametrize(
    "raw",
    (
        _raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=0),
        replace(_raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=18), first_party_status=0x08),
        replace(_raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=19), first_party_status=0x40),
        _raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=19, bubble_pp=3),
    ),
)
def test_brock_transit_rejects_unsafe_resource_or_status_boundary(raw: RawGameState) -> None:
    with pytest.raises(PewterChapterError, match="Brock-transit"):
        _expect_brock_transit_ready(raw, "unit Forest exit")


def test_brock_transit_accepts_living_status_free_authenticated_loss_recovery() -> None:
    _expect_brock_transit_ready(
        _raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=1),
        "unit Forest exit",
        authenticated_loss_recovery=True,
    )


@pytest.mark.parametrize(
    "raw",
    (
        _raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=0),
        replace(_raw(MapId.VIRIDIAN_FOREST, 1, 18, hp=19), first_party_status=0x08),
    ),
)
def test_brock_transit_rejects_unsafe_authenticated_loss_recovery(
    raw: RawGameState,
) -> None:
    with pytest.raises(PewterChapterError, match="Brock-transit"):
        _expect_brock_transit_ready(
            raw,
            "unit Forest exit",
            authenticated_loss_recovery=True,
        )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_pewter_timing_rejects_unbounded_values(invalid: object) -> None:
    for field in fields(PewterTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_PEWTER_TIMING, **{field.name: invalid})


def test_route_1_capability_training_search_accepts_only_low_level_local_prey() -> None:
    origin = _raw(MapId.ROUTE_1, 14, 8, level=5, hp=19, max_hp=19)
    rattata = replace(
        _raw(MapId.ROUTE_1, 14, 7, level=5, hp=19, max_hp=19),
        battle_state=1,
        enemy_species_id=0xA5,
        enemy_level=3,
    )

    class _Reader:
        state = origin

        def read(self) -> RawGameState:
            return self.state

    reader = _Reader()

    class _Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> object:
            self.actions.append(action)
            if action.kind is MacroActionKind.MOVE and action.value == "up":
                reader.state = rattata
            return object()

    executor = _Executor()
    encounter, flees, retries, attempts, return_steps = _seek_route_1_training_battle(  # type: ignore[arg-type]
        executor,
        reader,  # type: ignore[arg-type]
        "up",
        1,
        DEFAULT_PEWTER_TIMING,
        "unit Route 1 lesson",
        used_flees=0,
    )

    assert encounter is rattata
    assert not flees
    assert retries == 0
    assert attempts == 1
    assert return_steps == 1


def test_route_1_capability_heal_requires_full_hp_status_and_move_pp() -> None:
    healed = replace(
        _raw(MapId.VIRIDIAN_POKECENTER, 3, 3, level=6, hp=21, max_hp=21),
        first_party_moves=(0x21, 0x27, 0, 0),
        first_party_pp=(35, 30, 0, 0),
    )

    assert _is_healed_route_1_capability_party(healed)
    assert _is_healed_route_1_capability_party(replace(healed, first_party_level=5))
    assert _is_healed_route_1_capability_party(
        replace(
            healed,
            first_party_level=8,
            first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
            first_party_pp=(35, 30, 30, 0),
        )
    )
    assert not _is_healed_route_1_capability_party(None)
    assert not _is_healed_route_1_capability_party(replace(healed, first_party_hp=20))
    assert not _is_healed_route_1_capability_party(replace(healed, first_party_status=0x08))
    assert not _is_healed_route_1_capability_party(replace(healed, first_party_pp=(34, 30, 0, 0)))


def test_pewter_progress_is_sanitized_and_immutable() -> None:
    progress = PewterProgress(
        checkpoint_id="brock_defeated",
        label="Defeated Brock and received TM34",
        completed=PEWTER_CHECKPOINT_COUNT,
        total=PEWTER_CHECKPOINT_COUNT,
        frames_executed=122_999,
    )

    assert progress.completed == progress.total == 10
    with pytest.raises(FrozenInstanceError):
        progress.completed = 9  # type: ignore[misc]


def test_pewter_report_is_complete_honest_and_privacy_safe() -> None:
    report = _report()

    public = report.public_dict()
    serialized = json.dumps(public, sort_keys=True)

    assert report.passed
    assert public["status"] == "ok"
    assert len(public["checkpoints"]) == PEWTER_CHECKPOINT_COUNT
    assert public["route"] == {
        "ordered_boundaries_verified": 9,
        "ordered_boundaries_total": 9,
        "brock_battle_observed": True,
        "route_1_wild_flees": [],
        "route_1_movement_retries": 0,
        "route_2_wild_flees": [],
        "route_2_movement_retries": 0,
        "forest_wild_flees": [],
        "forest_movement_retries": 0,
        "viridian_pre_forest_heal": {
            "state": {
                "battle_state": 0,
                "hp": 27,
                "level": 9,
                "map_id": int(MapId.VIRIDIAN_POKECENTER),
                "max_hp": 27,
                "party_count": 1,
                "player_x": 3,
                "player_y": 3,
                "status": 0,
            },
            "verified": True,
        },
        "lab_rival_loss_recovery_required": False,
        "route_1_capability_search_attempts": [1, 1, 1],
        "route_1_capability_species_ids": [0x24, 0xA5, 0x24],
        "route_1_capability_level": 9,
        "route_1_capability_heals": [
            {
                "state": {
                    "battle_state": 0,
                    "hp": 21,
                    "level": 6,
                    "map_id": int(MapId.VIRIDIAN_POKECENTER),
                    "max_hp": 21,
                    "party_count": 1,
                    "player_x": 3,
                    "player_y": 3,
                    "status": 0,
                },
                "tackle_pp": 35,
                "tail_whip_pp": 30,
                "verified": True,
            },
            {
                "state": {
                    "battle_state": 0,
                    "hp": 23,
                    "level": 7,
                    "map_id": int(MapId.VIRIDIAN_POKECENTER),
                    "max_hp": 23,
                    "party_count": 1,
                    "player_x": 3,
                    "player_y": 3,
                    "status": 0,
                },
                "tackle_pp": 35,
                "tail_whip_pp": 30,
                "verified": True,
            },
            {
                "state": {
                    "battle_state": 0,
                    "hp": 25,
                    "level": 8,
                    "map_id": int(MapId.VIRIDIAN_POKECENTER),
                    "max_hp": 25,
                    "party_count": 1,
                    "player_x": 3,
                    "player_y": 3,
                    "status": 0,
                },
                "tackle_pp": 35,
                "tail_whip_pp": 30,
                "verified": True,
            },
            {
                "state": {
                    "battle_state": 0,
                    "hp": 27,
                    "level": 9,
                    "map_id": int(MapId.VIRIDIAN_POKECENTER),
                    "max_hp": 27,
                    "party_count": 1,
                    "player_x": 3,
                    "player_y": 3,
                    "status": 0,
                },
                "tackle_pp": 35,
                "tail_whip_pp": 30,
                "verified": True,
            },
        ],
    }
    assert public["brock"] == {
        "pre_battle_healing_verified": True,
        "victory_verified": True,
        "boulder_badge_verified": True,
        "tm34_verified": True,
        "overworld_control_verified": True,
        "squirtle_level": 12,
        "squirtle_hp": 27,
        "squirtle_max_hp": 33,
        "squirtle_status": 0,
        "bubble_pp": 23,
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
    ):
        assert private_key not in serialized


def test_pewter_report_requires_the_authenticated_route_1_capability_lesson() -> None:
    healed = replace(
        _raw(MapId.VIRIDIAN_POKECENTER, 3, 3, level=6, hp=21, max_hp=21),
        first_party_moves=(0x21, 0x27, 0, 0),
        first_party_pp=(35, 30, 0, 0),
    )
    healed_with_bubble = replace(
        healed,
        first_party_level=9,
        first_party_hp=27,
        first_party_max_hp=27,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(35, 30, 30, 0),
    )
    recovered = replace(
        _report(),
        lab_rival_loss_recovery_required=True,
        route_1_capability_search_attempts=(3, 2),
        route_1_capability_species_ids=(0x24, 0xA5),
        route_1_capability_level=9,
        route_1_capability_heals=(
            replace(healed, first_party_level=5),
            healed,
            healed_with_bubble,
        ),
        viridian_pre_forest_healed=healed_with_bubble,
    )

    assert recovered.passed
    assert recovered.public_dict()["route"]["route_1_capability_search_attempts"] == [3, 2]
    assert not replace(recovered, route_1_capability_search_attempts=()).passed
    assert not replace(recovered, route_1_capability_species_ids=(0x7B,)).passed
    assert not replace(recovered, route_1_capability_level=7).passed
    assert not replace(recovered, route_1_capability_heals=(healed,)).passed


@pytest.mark.parametrize(
    "changes",
    (
        {"saw_brock_battle": False},
        {"overworld_control_verified": False},
        {"controller_released": False},
        {"reached_boundaries": tuple(TravelBoundary)[1:-1]},
        {"lab_rival_loss_recovery_required": True},
        {"route_1_capability_search_attempts": (1,)},
        {"route_1_capability_species_ids": (0x71,)},
        {"route_1_capability_level": 6},
        {
            "pewter_center_healed": replace(
                _report().pewter_center_healed,
                first_party_hp=26,
            )
        },
        {"gym_entry_evidence": replace(_gym_ready(), first_party_hp=18)},
        {
            "brock_battle_evidence": replace(
                _brock_battle(),
                current_opponent=0,
            )
        },
        {"brock_victory_evidence": replace(_brock_victory(), got_tm34=False)},
        {
            "brock_defeated": replace(
                _report().brock_defeated,
                bag_item_ids=(),
            )
        },
    ),
)
def test_pewter_report_rejects_each_evidence_near_miss(
    changes: dict[str, object],
) -> None:
    assert not replace(_report(), **changes).passed
