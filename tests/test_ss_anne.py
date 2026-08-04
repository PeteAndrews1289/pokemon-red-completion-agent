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
    assert policy.max_battles == 120
    raw = RawGameState(
        True,
        MapId.DIGLETTS_CAVE,
        37,
        30,
        1,
        1,
        first_party_moves=(0x2C, 0x27, 0x3D, 0x37),
        first_party_pp=(20, 30, 15, 20),
        enemy_species_id=0x3B,
        enemy_level=20,
        enemy_hp=40,
    )
    assert ss_anne._pre_ship_training_move_slot(raw) == 3
    assert ss_anne._pre_ship_training_move_slot(
        replace(raw, first_party_pp=(20, 30, 0, 20))
    ) == 4


def test_pre_ship_training_waits_through_linked_cave_warps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = [
        RawGameState(True, MapId.DIGLETTS_CAVE, 4, 4, 1, 0),
        RawGameState(True, MapId.DIGLETTS_CAVE, 37, 31, 1, 0),
        RawGameState(True, MapId.DIGLETTS_CAVE, 37, 31, 1, 0),
    ]

    class Reader:
        index = 0

        def read(self) -> RawGameState:
            state = states[min(self.index, len(states) - 1)]
            self.index += 1
            return state

        def read_input_readiness(self) -> object:
            return type("Ready", (), {"ready": True})()

    class Executor:
        actions = []

        def execute(self, action: object) -> None:
            self.actions.append(action)

    executor = Executor()
    monkeypatch.setattr(ss_anne, "_wait", lambda *_args: None)

    settled = ss_anne._settle_pre_ship_cave_entry(
        executor,  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
        ss_anne.DEFAULT_SS_ANNE_TIMING,
    )

    assert (settled.player_x, settled.player_y) == (37, 31)
    assert len(executor.actions) == 2


def test_pre_ship_training_leaves_the_arrival_warp_before_bouncing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = [
        RawGameState(True, MapId.DIGLETTS_CAVE, 37, 31, 1, 0),
        RawGameState(True, MapId.DIGLETTS_CAVE, 37, 30, 1, 0),
    ]

    class Reader:
        index = 0

        def read(self) -> RawGameState:
            state = states[min(self.index, len(states) - 1)]
            self.index += 1
            return state

    class Executor:
        actions = []

        def execute(self, action: object) -> None:
            self.actions.append(action)

    executor = Executor()
    monkeypatch.setattr(ss_anne, "_wait", lambda *_args: None)

    anchor = ss_anne._leave_pre_ship_entry_warp(
        executor,  # type: ignore[arg-type]
        Reader(),  # type: ignore[arg-type]
    )

    assert (anchor.player_x, anchor.player_y) == (37, 30)
    assert len(executor.actions) == 1
    assert executor.actions[0].kind is MacroActionKind.MOVE
    assert executor.actions[0].value == "up"


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


def test_ss_anne_rival_rejects_an_unconsumed_high_value_reserve(
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

    with pytest.raises(ss_anne.SSAnneChapterError, match="did not consume"):
        ss_anne._run_ss_anne_rival_with_potion(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            ss_anne.DEFAULT_SS_ANNE_TIMING,
        )
