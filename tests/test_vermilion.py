from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.vermilion as vermilion
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import BattleResourcePolicy, BattleRuntimeError
from pokemon_red_completion.observation import (
    CERULEAN_ROCKET_TRAINER_NUMBER,
    ROCKET_OPPONENT_ID,
    ROCKET_TRAINER_CLASS_ID,
    ROUTE_6_JR_TRAINER_F_CLASS_ID,
    ROUTE_6_JR_TRAINER_F_NUMBER,
    ROUTE_6_JR_TRAINER_F_OPPONENT_ID,
    ROUTE_6_JR_TRAINER_M_CLASS_ID,
    ROUTE_6_JR_TRAINER_M_NUMBER,
    ROUTE_6_JR_TRAINER_M_OPPONENT_ID,
    WARTORTLE_SPECIES_ID,
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    RawGameState,
    VermilionPhase,
    VermilionState,
)

READY = InputReadiness(0, 0, 0, 0, 0, 0)
NO_TRAINERS = (False, False, False, False, False, False)


def _evidence(**changes: object) -> VermilionState:
    base = VermilionState(
        phase=VermilionPhase.MISTY_READY,
        controls=READY,
        local_script=0,
        current_map_script=0,
        prior_chapter_complete=True,
        beat_rocket_thief=False,
        tm28_in_bag=False,
        route_6_trainer_events=NO_TRAINERS,
        current_opponent=0,
        trainer_class=0,
        trainer_number=0,
        engaged_trainer_class=0,
        engaged_trainer_set=0,
        map_id=MapId.CERULEAN_GYM,
        player_x=5,
        player_y=2,
        party_count=1,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=4,
        first_party_max_hp=66,
        first_party_status=0,
        battle_state=0,
        battle_result=0,
    )
    return replace(base, **changes)


def _ordered_evidence() -> tuple[VermilionState, ...]:
    persistent = {"beat_rocket_thief": True, "tm28_in_bag": True}
    return (
        _evidence(),
        _evidence(
            phase=VermilionPhase.TRASHED_HOUSE_ENTERED,
            map_id=MapId.CERULEAN_TRASHED_HOUSE,
            player_x=2,
            player_y=7,
        ),
        _evidence(
            phase=VermilionPhase.ROBBERY_REAR_EXIT,
            map_id=MapId.CERULEAN_CITY,
            player_x=27,
            player_y=9,
        ),
        _evidence(
            phase=VermilionPhase.ROCKET_THIEF_BATTLE,
            map_id=MapId.CERULEAN_CITY,
            player_x=30,
            player_y=9,
            local_script=4,
            battle_state=2,
            current_opponent=ROCKET_OPPONENT_ID,
            trainer_class=ROCKET_TRAINER_CLASS_ID,
            trainer_number=CERULEAN_ROCKET_TRAINER_NUMBER,
            engaged_trainer_class=ROCKET_OPPONENT_ID,
            engaged_trainer_set=CERULEAN_ROCKET_TRAINER_NUMBER,
        ),
        _evidence(
            phase=VermilionPhase.TM28_OBTAINED,
            map_id=MapId.CERULEAN_CITY,
            player_x=30,
            player_y=9,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.ROUTE_5_REACHED,
            map_id=MapId.ROUTE_5,
            player_x=3,
            player_y=0,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.UNDERGROUND_NORTH_ENTRANCE,
            map_id=MapId.UNDERGROUND_PATH_ROUTE_5,
            player_x=3,
            player_y=7,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.UNDERGROUND_TUNNEL,
            map_id=MapId.UNDERGROUND_PATH_NORTH_SOUTH,
            player_x=5,
            player_y=4,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.UNDERGROUND_SOUTH_ENTRANCE,
            map_id=MapId.UNDERGROUND_PATH_ROUTE_6,
            player_x=4,
            player_y=4,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.ROUTE_6_REACHED,
            map_id=MapId.ROUTE_6,
            player_x=17,
            player_y=14,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.ROUTE_6_TRAINER_F_BATTLE,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=30,
            local_script=2,
            current_map_script=2,
            battle_state=2,
            current_opponent=ROUTE_6_JR_TRAINER_F_OPPONENT_ID,
            trainer_class=ROUTE_6_JR_TRAINER_F_CLASS_ID,
            trainer_number=ROUTE_6_JR_TRAINER_F_NUMBER,
            engaged_trainer_class=ROUTE_6_JR_TRAINER_F_OPPONENT_ID,
            engaged_trainer_set=ROUTE_6_JR_TRAINER_F_NUMBER,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.ROUTE_6_TRAINER_F_DEFEATED,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=30,
            route_6_trainer_events=(False, False, False, False, True, False),
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.ROUTE_6_TRAINER_M_BATTLE,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=31,
            local_script=2,
            current_map_script=2,
            battle_state=2,
            route_6_trainer_events=(False, False, False, False, True, False),
            current_opponent=ROUTE_6_JR_TRAINER_M_OPPONENT_ID,
            trainer_class=ROUTE_6_JR_TRAINER_M_CLASS_ID,
            trainer_number=ROUTE_6_JR_TRAINER_M_NUMBER,
            engaged_trainer_class=ROUTE_6_JR_TRAINER_M_OPPONENT_ID,
            engaged_trainer_set=ROUTE_6_JR_TRAINER_M_NUMBER,
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.ROUTE_6_TRAINER_M_DEFEATED,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=31,
            route_6_trainer_events=(False, False, False, True, True, False),
            **persistent,
        ),
        _evidence(
            phase=VermilionPhase.VERMILION_REACHED,
            map_id=MapId.VERMILION_CITY,
            player_x=19,
            player_y=0,
            first_party_hp=14,
            route_6_trainer_events=(False, False, False, True, True, False),
            **persistent,
        ),
    )


def _raw(state: VermilionState) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=state.map_id,
        player_x=state.player_x,
        player_y=state.player_y,
        party_count=state.party_count,
        battle_state=state.battle_state,
        party_species_ids=state.party_species_ids,
        first_party_hp=state.first_party_hp,
        first_party_max_hp=state.first_party_max_hp,
        first_party_status=state.first_party_status,
        first_party_moves=vermilion.POST_ROCKET_WARTORTLE_MOVES,
        battle_result=state.battle_result,
    )


class ScriptedReader:
    def __init__(self, states: tuple[VermilionState, ...]) -> None:
        self.states = states
        self.index = 0

    def read(self) -> RawGameState:
        return _raw(self.states[min(self.index, len(self.states) - 1)])

    def read_cascade_state(self, raw: RawGameState) -> object:
        return SimpleNamespace(misty_victory_snapshot=True)

    def read_vermilion_state(self, raw: RawGameState) -> VermilionState:
        state = self.states[self.index]
        self.index += 1
        return state


class FakeEmulator:
    frame_count = 123
    pressed_buttons = frozenset()


class FakeExecutor:
    def execute(self, action: object) -> object:
        return action


def test_runner_records_all_fifteen_ordered_semantic_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = ScriptedReader(_ordered_evidence())
    progress: list[vermilion.VermilionProgress] = []
    monkeypatch.setattr(vermilion, "_move", lambda *args, **kwargs: reader.read())
    monkeypatch.setattr(
        vermilion,
        "_move_route_6_with_wild_flees",
        lambda *args, **kwargs: (),
    )
    monkeypatch.setattr(vermilion, "_wait", lambda *args, **kwargs: None)
    monkeypatch.setattr(vermilion, "_heal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        vermilion,
        "_enter_trainer_battle",
        lambda *args, **kwargs: reader.read(),
    )
    monkeypatch.setattr(vermilion, "_battle", lambda *args, **kwargs: reader.read())
    monkeypatch.setattr(
        vermilion,
        "_run_rocket_thief_with_potion",
        lambda *args, **kwargs: reader.read(),
    )
    monkeypatch.setattr(
        vermilion,
        "_run_route_6_trainer_f_with_potion",
        lambda *args, **kwargs: reader.read(),
    )
    monkeypatch.setattr(
        vermilion,
        "_backtrack_heal_and_replay",
        lambda *args, **kwargs: tuple(
            vermilion.Route6WildFleeEvidence(
                initial_battle_state=1,
                final_battle_state=0,
                map_id=MapId.ROUTE_6,
                player_x=x,
                player_y=y,
                enemy_species_id=species,
                initial_pp=(24, 30, 30, 22),
                final_pp=(24, 30, 30, 22),
                final_hp=66,
                final_status=0,
                trainer_events=(False, False, False, False, True, False),
                control_ready=True,
            )
            for x, y, species in vermilion.QUALIFIED_ROUTE_6_WILDS
        ),
    )
    monkeypatch.setattr(
        vermilion,
        "_confirm_pulses",
        lambda *args, **kwargs: None,
    )
    observed_events: list[tuple[bool, ...]] = []
    monkeypatch.setattr(
        vermilion,
        "_require_route_6_events",
        lambda _reader, expected, _label: observed_events.append(expected),
    )

    report = vermilion.run_vermilion_chapter(
        FakeEmulator(),
        reader,  # type: ignore[arg-type]
        FakeExecutor(),
        progress=progress.append,
    )

    assert report.passed
    assert replace(report, route_6_wild_flees=()).passed
    assert len(report.records) == vermilion.VERMILION_CHECKPOINT_COUNT == 15
    assert [record.evidence.phase for record in report.records] == [
        state.phase for state in _ordered_evidence()
    ]
    assert [item.completed for item in progress] == list(range(1, 16))
    assert observed_events == [
        (False, False, False, False, True, False),
        (False, False, False, True, True, False),
    ]
    assert report.final_raw.map_id == MapId.VERMILION_CITY
    assert (report.final_raw.player_x, report.final_raw.player_y) == (19, 0)


def test_live_route_constants_preserve_the_qualified_corridors() -> None:
    assert vermilion.ROUTE_6_JR_TRAINER_F_MOVE_SLOT == 3
    assert vermilion.ROUTE_6_JR_TRAINER_M_MOVE_SLOT == 3
    assert vermilion._directions(
        "R" * 3 + "D" * 9 + "R" * 3 + "D" * 13 + "L" * 23 + "D" * 5
    ) == vermilion.ROCKET_TO_ROUTE_5_DIRECTIONS


def test_trashed_house_replay_yields_to_the_cerulean_walker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = replace(
            _raw(_evidence()),
            map_id=MapId.CERULEAN_CITY,
            player_x=16,
            player_y=16,
            first_party_hp=66,
        )

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        left_attempts_from_block = 0

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is not MacroActionKind.MOVE:
                return action
            position = (reader.state.player_x, reader.state.player_y)
            if action.value == "right" and position == (16, 16):
                reader.state = replace(reader.state, player_x=17)
            elif action.value == "left" and position == (17, 16):
                reader.state = replace(reader.state, player_x=16)
            elif action.value == "left" and position == (16, 16):
                self.left_attempts_from_block += 1
                if self.left_attempts_from_block == 3:
                    reader.state = replace(reader.state, player_x=15)
            return action

    executor = Executor()
    monkeypatch.setattr(vermilion, "_wait", lambda *args: None)

    final = vermilion._move(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        ("left",),
        vermilion.DEFAULT_VERMILION_TIMING,
        "trashed house approach replay",
    )

    assert (final.player_x, final.player_y) == (15, 16)
    assert executor.left_attempts_from_block == 3


@pytest.mark.parametrize(
    ("learn_level_up_move", "expected_interval"),
    ((False, 3), (True, 10_000)),
)
def test_battle_only_suppresses_unknown_cancels_for_level_up_learning(
    monkeypatch: pytest.MonkeyPatch,
    learn_level_up_move: bool,
    expected_interval: int,
) -> None:
    observed: dict[str, object] = {}
    terminal = _raw(_evidence())

    def fake_runtime(*args: object, **kwargs: object) -> RawGameState:
        observed.update(kwargs)
        return terminal

    monkeypatch.setattr(vermilion, "run_adaptive_trainer_battle", fake_runtime)

    result = vermilion._battle(
        object(),  # type: ignore[arg-type]
        FakeExecutor(),
        lambda _: 1,
        MapId.CERULEAN_CITY,
        vermilion.DEFAULT_VERMILION_TIMING,
        "battle",
        "battle-plan",
        learn_level_up_move=learn_level_up_move,
    )

    assert result is terminal
    assert observed["unknown_cancel_interval"] == expected_interval
    assert vermilion._directions(
        "D" * 27 + "R" * 12 + "D" + "R" * 2 + "U"
    ) == vermilion.ROUTE_5_TO_UNDERGROUND_DIRECTIONS
    assert vermilion._directions(
        "D" * 37 + "L" * 3
    ) == vermilion.UNDERGROUND_TUNNEL_DIRECTIONS
    assert vermilion._directions(
        "L" * 2 + "D" * 15 + "L" * 7 + "R" + "D"
    ) == vermilion.ROUTE_6_TO_FIRST_TRAINER_DIRECTIONS
    assert (
        vermilion._directions("D" * 5)
        == vermilion.VERMILION_ENTRY_DIRECTIONS
    )


def test_rocket_policy_uses_exactly_one_bite_against_drowzee() -> None:
    machop = RawGameState(
        True,
        MapId.CERULEAN_CITY,
        30,
        9,
        1,
        2,
        enemy_species_id=0x6A,
        enemy_hp=53,
        first_party_moves=vermilion.POST_ROCKET_WARTORTLE_MOVES,
        first_party_pp=(25, 30, 20, 25),
    )
    drowzee = replace(machop, enemy_species_id=0x30, enemy_hp=50)

    assert vermilion._choose_rocket_move(machop) == 4
    assert vermilion._choose_rocket_move(drowzee) == 1
    assert (
        vermilion._choose_rocket_move(
            replace(drowzee, enemy_hp=24, first_party_pp=(24, 30, 20, 23))
        )
        == 3
    )

    assert (
        vermilion._choose_rocket_move(
            replace(
                drowzee,
                enemy_hp=24,
                first_party_pp=(24, 30, 20, 23),
                player_disabled_move_slot=3,
            )
        )
        == 1
    )


def test_rocket_recovery_consumes_the_extra_potion_and_reuses_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quantity = vermilion.ROCKET_THIEF_POTION_RESERVE
    calls = 0
    intents = []
    terminal = RawGameState(
        True,
        MapId.CERULEAN_CITY,
        30,
        9,
        1,
        0,
        first_party_hp=45,
        first_party_max_hp=66,
    )

    def fake_bag_quantity(*_args: object) -> int:
        return quantity

    def fake_runtime(*args: object, **kwargs: object) -> RawGameState:
        nonlocal calls
        calls += 1
        intents.append(kwargs["intent"])
        if calls == 1:
            policy = args[2]
            try:
                policy(
                    RawGameState(
                        True,
                        MapId.CERULEAN_CITY,
                        30,
                        9,
                        1,
                        2,
                        enemy_species_id=0x30,
                        enemy_hp=24,
                        first_party_hp=40,
                        first_party_max_hp=66,
                        first_party_moves=vermilion.POST_ROCKET_WARTORTLE_MOVES,
                        first_party_pp=(24, 30, 20, 23),
                    )
                )
            except vermilion._PauseForRocketThiefPotion as pause:
                raise BattleRuntimeError("paused for Rocket recovery") from pause
        return terminal

    def fake_use(*_args: object) -> None:
        nonlocal quantity
        quantity -= 1

    monkeypatch.setattr(vermilion, "_bag_quantity", fake_bag_quantity)
    monkeypatch.setattr(vermilion, "run_adaptive_trainer_battle", fake_runtime)
    monkeypatch.setattr(vermilion, "_use_cerulean_rival_potion", fake_use)

    observed = vermilion._run_rocket_thief_with_potion(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        vermilion.DEFAULT_VERMILION_TIMING,
    )

    assert observed is terminal
    assert quantity == vermilion.VERMILION_ROUTE_6_POTION_RESERVE
    assert calls == 2
    assert intents[0] is intents[1]
    assert intents[0].resource_policy is BattleResourcePolicy.BOUNDED_RECOVERY


@pytest.mark.parametrize("starting_reserve", [4, 5])
def test_rocket_victory_may_preserve_the_extra_potion_when_recovery_is_not_needed(
    monkeypatch: pytest.MonkeyPatch,
    starting_reserve: int,
) -> None:
    terminal = RawGameState(
        True,
        MapId.CERULEAN_CITY,
        30,
        9,
        1,
        0,
        first_party_hp=45,
        first_party_max_hp=66,
    )
    monkeypatch.setattr(
        vermilion,
        "_bag_quantity",
        lambda *_args: starting_reserve,
    )
    monkeypatch.setattr(
        vermilion,
        "run_adaptive_trainer_battle",
        lambda *_args, **_kwargs: terminal,
    )

    observed = vermilion._run_rocket_thief_with_potion(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        vermilion.DEFAULT_VERMILION_TIMING,
    )

    assert observed is terminal


@pytest.mark.parametrize("starting_reserve", [3, 5])
def test_route_6_victory_may_preserve_potion_when_recovery_is_not_needed(
    monkeypatch: pytest.MonkeyPatch,
    starting_reserve: int,
) -> None:
    terminal = RawGameState(
        True,
        MapId.ROUTE_6,
        10,
        25,
        1,
        0,
        first_party_hp=45,
        first_party_max_hp=66,
    )
    monkeypatch.setattr(
        vermilion,
        "_bag_quantity",
        lambda *_args: starting_reserve,
    )
    monkeypatch.setattr(
        vermilion,
        "run_adaptive_trainer_battle",
        lambda *_args, **_kwargs: terminal,
    )

    observed = vermilion._run_route_6_trainer_f_with_potion(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        vermilion.DEFAULT_VERMILION_TIMING,
        vermilion.RedBattlePlanId.VERMILION_ROUTE_6_JR_TRAINER_F,
    )

    assert observed is terminal


class WildFleeSimulation:
    def __init__(
        self,
        *,
        mutate_pp: bool = False,
        trainer_events: tuple[bool, ...] = (
            False,
            False,
            False,
            False,
            True,
            False,
        ),
    ) -> None:
        self.battle_state = 1
        self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        self.pp = (25, 30, 30, 25)
        self.mutate_pp = mutate_pp
        self.trainer_events = trainer_events
        self.actions: list[MacroAction] = []

    def read(self) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_6,
            player_x=15,
            player_y=19,
            party_count=1,
            battle_state=self.battle_state,
            first_party_hp=66,
            first_party_max_hp=66,
            first_party_status=0,
            first_party_pp=self.pp,
            enemy_species_id=0x24 if self.battle_state else None,
            enemy_hp=20 if self.battle_state else None,
        )

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        return self.menu

    def read_input_readiness(self) -> InputReadiness:
        return READY if self.battle_state == 0 else replace(READY, joy_ignore=1)

    def read_vermilion_state(self, raw: RawGameState) -> VermilionState:
        return _evidence(
            map_id=MapId.ROUTE_6,
            player_x=15,
            player_y=19,
            route_6_trainer_events=self.trainer_events,
        )

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        kind = action.kind
        value = action.value
        if kind is MacroActionKind.CONFIRM and self.menu.phase is BattleMenuPhase.UNKNOWN:
            self.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=0,
            )
        elif kind is MacroActionKind.MOVE and value == "right":
            self.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=2,
            )
        elif kind is MacroActionKind.MOVE and value == "down":
            self.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=3,
            )
        elif (
            kind is MacroActionKind.CONFIRM
            and self.menu.selected_main_command == 3
        ):
            self.battle_state = 0
            if self.mutate_pp:
                self.pp = (25, 29, 30, 25)
            self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        return action


def test_wild_flee_navigates_observed_run_menu_and_proves_resources() -> None:
    simulation = WildFleeSimulation()
    encounter = simulation.read()

    evidence = vermilion._flee_qualified_route_6_wild(
        vermilion._CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        vermilion.DEFAULT_VERMILION_TIMING,
        encounter,
    )

    moves = [
        action.value
        for action in simulation.actions
        if action.kind is MacroActionKind.MOVE
    ]
    assert moves == ["right", "down"]
    assert evidence.qualified_step_7_pidgey
    assert evidence.initial_pp == evidence.final_pp == (25, 30, 30, 25)
    assert evidence.control_ready


def test_wild_flee_accepts_pretrainer_route_6_event_state() -> None:
    simulation = WildFleeSimulation(trainer_events=(False,) * 6)

    evidence = vermilion._flee_qualified_route_6_wild(
        vermilion._CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        vermilion.DEFAULT_VERMILION_TIMING,
        simulation.read(),
        expected_trainer_events=(False,) * 6,
    )

    assert evidence.verified
    assert evidence.trainer_events == evidence.expected_trainer_events == (False,) * 6


def test_wild_flee_rejects_any_pp_change() -> None:
    simulation = WildFleeSimulation(mutate_pp=True)

    with pytest.raises(
        vermilion.VermilionChapterError,
        match="post-RUN semantic evidence",
    ):
        vermilion._flee_qualified_route_6_wild(
            vermilion._CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            vermilion.DEFAULT_VERMILION_TIMING,
            simulation.read(),
        )


def test_vermilion_timing_rejects_nonpositive_bounds() -> None:
    with pytest.raises(ValueError, match="movement_retries"):
        vermilion.VermilionTiming(movement_retries=0)
