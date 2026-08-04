from __future__ import annotations

from dataclasses import replace

import pytest

import pokemon_red_completion.ss_anne as ss_anne
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import BattleResourcePolicy, BattleRuntimeError
from pokemon_red_completion.observation import ItemId, MapId, RawGameState


def test_pre_ship_training_is_bounded_and_prefers_water_moves() -> None:
    policy = ss_anne.PRE_SHIP_TRAINING_POLICY
    assert policy.target_level == 30
    assert policy.preferred_move_slots == (3, 4, 1)
    assert policy.retreat_hp_ratio == 0.65
    assert policy.reserve_total_pp == 8
    assert policy.max_battles == 120
    assert policy.max_healing_trips == 8
    assert ss_anne.PRE_SHIP_TRAINING_PATROL_DIRECTIONS == ("right", "left")
    assert ss_anne.PRE_SHIP_TRAINING_INTENT.battle_plan_id == (
        "red.route-11.pre-ship-leveling"
    )
    raw = RawGameState(
        True,
        MapId.ROUTE_11,
        12,
        6,
        1,
        1,
        first_party_moves=(0x2C, 0x27, 0x3D, 0x37),
        first_party_pp=(20, 30, 15, 20),
        enemy_species_id=0x3B,
        enemy_level=20,
        enemy_hp=40,
    )
    assert ss_anne._pre_ship_training_move_slot(raw) == 3
    assert ss_anne._pre_ship_training_move_slot(replace(raw, first_party_pp=(20, 30, 0, 20))) == 4
    assert (
        ss_anne._pre_ship_training_move_slot(
            replace(
                raw,
                first_party_pp=(20, 30, 0, 20),
                player_disabled_move_slot=4,
            )
        )
        == 1
    )


def test_ss_anne_waiter_yield_gate_is_source_pinned() -> None:
    assert ss_anne.SS_ANNE_WAITER_BLOCK_POSITION == (9, 6)
    assert ss_anne.SS_ANNE_WAITER_YIELD_POSITION == (9, 7)
    assert ss_anne.SS_ANNE_WAITER_CLEAR_POSITION == (8, 6)
    assert ss_anne.SS_ANNE_WAITER_CLEAR_ATTEMPTS == 10


def test_vermilion_sailor_yield_supports_both_observed_corridor_gates() -> None:
    assert frozenset({(21, 27), (22, 27)}) == ss_anne.VERMILION_SAILOR_BLOCK_POSITIONS
    assert ss_anne.VERMILION_SAILOR_CLEAR_ATTEMPTS == 10


def test_pre_ship_training_fights_lower_level_route_11_wilds() -> None:
    raw = RawGameState(
        True,
        MapId.ROUTE_11,
        12,
        6,
        1,
        1,
        first_party_level=26,
        first_party_hp=73,
        first_party_max_hp=73,
        first_party_pp=(25, 30, 16, 25),
        enemy_species_id=0x05,
        enemy_level=17,
        enemy_hp=44,
    )

    directive = ss_anne._pre_ship_training_directive(
        raw,
        ss_anne.TrainingObservation(
            level=raw.first_party_level or 0,
            hp=raw.first_party_hp or 0,
            max_hp=raw.first_party_max_hp or 0,
            pp=raw.first_party_pp or (),
            in_battle=True,
            enemy_level=raw.enemy_level,
        ),
    )

    assert directive is ss_anne.TrainingDirective.FIGHT


def test_pre_ship_training_preserves_return_direction_when_battle_preempts_step() -> None:
    moved, bounce = ss_anne._pre_ship_training_step_outcome(
        current=(36, 30),
        next_position=(36, 30),
        in_battle=True,
        direction="right",
        prior_bounce_direction="right",
        opposite={"right": "left"},
    )

    assert moved
    assert bounce == "right"


def test_pre_ship_training_does_not_treat_a_blocked_step_as_movement() -> None:
    moved, bounce = ss_anne._pre_ship_training_step_outcome(
        current=(37, 30),
        next_position=(37, 30),
        in_battle=False,
        direction="up",
        prior_bounce_direction=None,
        opposite={"up": "down"},
    )

    assert not moved
    assert bounce is None


def test_harbor_route_yields_to_the_vermilion_sailor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = RawGameState(
            True,
            MapId.VERMILION_CITY,
            21,
            27,
            1,
            0,
            first_party_hp=81,
        )

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        sailor_cleared = False

        def execute(self, action: object) -> object:
            assert isinstance(action, ss_anne.MacroAction)
            if action.kind is not MacroActionKind.MOVE:
                return action
            position = (reader.state.player_x, reader.state.player_y)
            if action.value == "up" and position == (21, 27):
                reader.state = replace(reader.state, player_y=26)
            elif action.value == "down" and position == (21, 26):
                if self.sailor_cleared:
                    reader.state = replace(reader.state, player_y=27)
                else:
                    self.sailor_cleared = True
            elif action.value == "left" and position == (21, 27) and self.sailor_cleared:
                reader.state = replace(reader.state, player_x=20)
            return action

    monkeypatch.setattr(ss_anne, "_wait", lambda *_args: None)

    final = ss_anne._move(
        Executor(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        ("left",),
        ss_anne.DEFAULT_SS_ANNE_TIMING,
        "Vermilion harbor",
    )

    assert (final.player_x, final.player_y) == (20, 27)


def test_rival_entry_waits_for_the_full_rival_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = [
        RawGameState(True, MapId.SS_ANNE_2F, 36, 8, 1, 2),
        RawGameState(True, MapId.SS_ANNE_2F, 36, 8, 1, 2),
    ]

    class Reader:
        index = 0

        def read(self) -> RawGameState:
            state = states[min(self.index, len(states) - 1)]
            self.index += 1
            return state

        def read_ss_anne_state(self, raw: RawGameState) -> object:
            return type(
                "RivalState",
                (),
                {"rival_battle_snapshot": raw is states[1]},
            )()

    monkeypatch.setattr(ss_anne, "_wait", lambda *_args: None)

    observed = ss_anne._enter_rival_battle(
        type("Executor", (), {})(),  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        ss_anne.DEFAULT_SS_ANNE_TIMING,
    )

    assert observed is states[1]


def test_ss_anne_rival_consumes_high_value_reserve_with_one_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quantities = {ItemId.POTION: 3, ItemId.SUPER_POTION: 3}
    calls = 0
    intents = []
    terminal = RawGameState(
        True,
        MapId.SS_ANNE_2F,
        2,
        4,
        1,
        0,
        first_party_hp=45,
        first_party_max_hp=71,
    )

    monkeypatch.setattr(ss_anne, "_bag_quantity", lambda _emulator, item: quantities[item])

    def fake_runtime(*args: object, **kwargs: object) -> RawGameState:
        nonlocal calls
        calls += 1
        intents.append(kwargs["intent"])
        if calls <= 3:
            policy = args[2]
            try:
                policy(
                    RawGameState(
                        True,
                        MapId.SS_ANNE_2F,
                        2,
                        4,
                        1,
                        2,
                        enemy_species_id=ss_anne.IVYSAUR_SPECIES_ID,
                        enemy_hp=38,
                        first_party_hp=55,
                        first_party_max_hp=71,
                    )
                )
            except ss_anne._PauseForSSAnneRivalPotion as pause:
                raise BattleRuntimeError("paused for S.S. Anne recovery") from pause
        return terminal

    def fake_use(*_args: object, **kwargs: object) -> None:
        quantities[kwargs["item"]] -= 1

    monkeypatch.setattr(ss_anne, "run_adaptive_trainer_battle", fake_runtime)
    monkeypatch.setattr(ss_anne, "_use_battle_recovery_item", fake_use)

    observed = ss_anne._run_ss_anne_rival_with_potion(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ss_anne.DEFAULT_SS_ANNE_TIMING,
    )

    assert observed is terminal
    assert quantities == {ItemId.POTION: 3, ItemId.SUPER_POTION: 0}
    assert calls == 4
    assert intents[0] is intents[1] is intents[2] is intents[3]
    assert intents[0].resource_policy is BattleResourcePolicy.BOUNDED_RECOVERY


def test_ss_anne_rival_preserves_an_unneeded_high_value_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = RawGameState(
        True,
        MapId.SS_ANNE_2F,
        2,
        4,
        1,
        0,
        first_party_hp=71,
        first_party_max_hp=71,
    )
    quantities = {ItemId.POTION: 7, ItemId.SUPER_POTION: 3}
    monkeypatch.setattr(ss_anne, "_bag_quantity", lambda _emulator, item: quantities[item])
    monkeypatch.setattr(
        ss_anne,
        "run_adaptive_trainer_battle",
        lambda *_args, **_kwargs: terminal,
    )

    observed = ss_anne._run_ss_anne_rival_with_potion(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ss_anne.DEFAULT_SS_ANNE_TIMING,
    )

    assert observed is terminal
    assert quantities[ItemId.SUPER_POTION] == 3
