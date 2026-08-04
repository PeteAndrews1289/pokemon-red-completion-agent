import pytest

from pokemon_red_completion import bruno as bruno_module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bruno import (
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
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState


def test_bruno_source_contract_is_exact() -> None:
    assert BRUNO_CHECKPOINT_COUNT == 3
    assert BRUNO_RNG_DELAY_FRAMES == 185
    assert BRUNO_HITMONLEE_SAFE_HP == 120
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
    assert not _turns_valid((BrunoTurn(0x22, 53, 1, 0, 0, (1, 1, 1, 1), 4),))


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

    executor = Executor()
    reader = Reader(executor)
    monkeypatch.setattr(bruno_module, "_event", lambda *_args: True)

    assert _settle_bruno_victory(executor, reader) == raw  # type: ignore[arg-type]
    assert [action.kind for action in executor.actions].count(MacroActionKind.CONFIRM) == 1
