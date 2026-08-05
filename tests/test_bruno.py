from inspect import getsource

import pytest

from pokemon_red_completion import bruno as bruno_module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bruno import (
    BRUNO_AFTER_BATTLE_TEXT_PULSES,
    BRUNO_APPROACH,
    BRUNO_CHECKPOINT_COUNT,
    BRUNO_HITMONLEE_SAFE_HP,
    BRUNO_PARTY,
    BRUNO_RNG_DELAY_FRAMES,
    BrunoTurn,
    _bruno_recovery_threshold,
    _encounter_party,
    _settle_bruno_victory,
    _turns_valid,
    run_bruno_chapter,
)
from pokemon_red_completion.observation import EventFlag, MapId, RamAddress, RawGameState


def test_bruno_source_contract_is_exact() -> None:
    assert BRUNO_CHECKPOINT_COUNT == 3
    assert BRUNO_RNG_DELAY_FRAMES == 185
    assert BRUNO_HITMONLEE_SAFE_HP == 120
    assert BRUNO_AFTER_BATTLE_TEXT_PULSES == 2
    assert BRUNO_APPROACH == ("right", "up", "up")
    assert MapId.BRUNOS_ROOM == 0xF6
    assert MapId.AGATHAS_ROOM == 0xF7
    assert EventFlag.BEAT_BRUNO == 0x8E9
    assert BRUNO_PARTY == (
        (0x22, 53),
        (0x2C, 55),
        (0x2B, 55),
        (0x22, 56),
        (0x7E, 58),
    )


def test_bruno_receipt_reconstructs_party_and_policy() -> None:
    turns = tuple(
        BrunoTurn(
            species,
            level,
            1,
            70,
            0,
            (1, 1, 1, 1),
            4 if species == 0x22 else 1,
        )
        for species, level in BRUNO_PARTY
    )
    assert _encounter_party(turns) == BRUNO_PARTY
    assert _turns_valid(turns)
    assert _turns_valid((BrunoTurn(0x2C, 55, 63, 193, 0x20, (19, 10, 10, 14), 1),))
    assert not _turns_valid((BrunoTurn(0x22, 53, 1, 0, 0, (1, 1, 1, 1), 4),))
    assert not _turns_valid((BrunoTurn(0x22, 53, 1, 70, 0x80, (1, 1, 1, 1), 4),))


def test_bruno_recovery_threshold_accounts_for_hitmonlee_damage() -> None:
    def raw(species: int) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.BRUNOS_ROOM,
            player_x=4,
            player_y=5,
            party_count=3,
            battle_state=2,
            enemy_species_id=species,
            first_party_max_hp=163,
        )

    assert _bruno_recovery_threshold(raw(0x2B)) == BRUNO_HITMONLEE_SAFE_HP
    assert _bruno_recovery_threshold(raw(0x2C)) == 163
    assert _bruno_recovery_threshold(raw(0x7E)) == 163
    assert _bruno_recovery_threshold(raw(0x22)) == 90


def test_bruno_victory_settle_stops_before_reinteracting(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.BRUNOS_ROOM,
        player_x=5,
        player_y=3,
        party_count=6,
        battle_state=0,
    )

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)

    class Reader:
        def __init__(self, executor: Executor) -> None:
            self.executor = executor

        def read(self) -> RawGameState:
            return raw

        def read_input_readiness(self):
            ready = any(
                action.kind is MacroActionKind.CONFIRM for action in self.executor.actions
            )
            return type("Readiness", (), {"ready": ready})()

    class Emulator:
        def __init__(self, executor: Executor) -> None:
            self.executor = executor

        def read_u8(self, address: int) -> int:
            assert address == RamAddress.CURRENT_MAP_SCRIPT
            return 0 if any(
                action.kind is MacroActionKind.CONFIRM for action in self.executor.actions
            ) else 2

    executor = Executor()
    reader = Reader(executor)
    emulator = Emulator(executor)
    monkeypatch.setattr(bruno_module, "_event", lambda *_args: True)

    assert _settle_bruno_victory(  # type: ignore[arg-type]
        executor,
        reader,
        emulator,
    ) == raw
    assert [action.kind for action in executor.actions].count(MacroActionKind.CONFIRM) == 3


def test_post_bruno_field_heal_occurs_after_agatha_room_entry() -> None:
    source = getsource(run_bruno_chapter)

    assert source.index('"Agatha room entry"') < source.index("_use_bag_item(")


def test_bruno_closes_collection_schedule_when_recoil_ends_healing_turn() -> None:
    source = getsource(run_bruno_chapter)

    assert "terminal_exit = _battle_healing_item(" in source
    assert "note_observed_trainer_battle_exit(battle_intent)" in source
