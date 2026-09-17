from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_battle_practice_factory as red
from pokemon_red_completion.battle_practice_factory import (
    BattlePracticeError,
    BattlePracticeSpec,
)
from pokemon_red_completion.observation import (
    PARTY_MOVES_OFFSET,
    PARTY_PP_OFFSET,
    PARTY_STRUCT_STRIDE,
    BattleMenuPhase,
    RamAddress,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _spec(**changes):
    value = {
        "source_state_sha256": "a" * 64,
        "root_lineage_id": "red-goal-root-practice-test",
        "partition": "train",
        "actor_moves": [
            {"move_ref": pokemon_red_move_ref(33), "pp": 20},
            {"move_ref": pokemon_red_move_ref(70), "pp": 15},
        ],
        "opponent_hp": 50,
    }
    value.update(changes)
    return BattlePracticeSpec.from_dict(value)


def test_title_neutral_spec_rejects_unsupported_or_non_train_conditions():
    spec = _spec()
    assert spec.partition is ScenarioPartition.TRAIN
    assert len(spec.configuration_sha256) == 64
    with pytest.raises(BattlePracticeError, match="unsupported or missing"):
        _spec(opponent_species="arbitrary")
    with pytest.raises(BattlePracticeError, match="train-only"):
        _spec(partition="development")
    with pytest.raises(BattlePracticeError, match="PP"):
        _spec(actor_moves=[{"move_ref": pokemon_red_move_ref(33), "pp": 0}] * 2)
    with pytest.raises(BattlePracticeError, match="distinct alternatives"):
        _spec(actor_moves=[{"move_ref": pokemon_red_move_ref(33), "pp": 20}] * 2)


class FakeReader:
    def __init__(self, memory):
        self.memory = memory
        self.phase = BattleMenuPhase.MAIN
        self.transformed = False
        self.enemy_max_hp = 80

    def read(self):
        base = int(RamAddress.PARTY_MON_1) + PARTY_STRUCT_STRIDE
        moves = tuple(self.memory.get(base + PARTY_MOVES_OFFSET + index, 0) for index in range(4))
        pp = tuple(self.memory.get(base + PARTY_PP_OFFSET + index, 0) for index in range(4))
        enemy_hp = 256 * self.memory.get(int(RamAddress.ENEMY_HP), 0) + self.memory.get(
            int(RamAddress.ENEMY_HP) + 1, 80
        )
        return SimpleNamespace(
            battle_state=1,
            map_id=165,
            active_party_index=1,
            active_party_species_id=28,
            active_party_level=30,
            active_party_hp=90,
            active_party_max_hp=90,
            active_party_moves=moves,
            active_party_pp=pp,
            battler_moves=moves,
            battler_pp=pp,
            enemy_species_id=55,
            enemy_level=30,
            enemy_hp=enemy_hp,
            enemy_max_hp=self.enemy_max_hp,
        )

    def read_battle_menu_state(self, _raw):
        return SimpleNamespace(phase=self.phase)

    def read_wild_capture_identity(self):
        return SimpleNamespace(
            transformed=self.transformed,
            original_species_id=55,
            displayed_species_id=55,
        )


def _reader():
    memory = {}
    base = int(RamAddress.PARTY_MON_1) + PARTY_STRUCT_STRIDE
    for index, (move, pp) in enumerate(((56, 5), (70, 15), (58, 10), (57, 15))):
        memory[base + PARTY_MOVES_OFFSET + index] = move
        memory[base + PARTY_PP_OFFSET + index] = pp
    return FakeReader(memory)


def test_red_factory_writes_battle_and_party_mirrors_then_verifies(monkeypatch):
    reader = _reader()
    monkeypatch.setattr(
        red.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda _reader: object(),
    )
    monkeypatch.setattr(
        red,
        "prepare_red_battle_scenario",
        lambda _encoder, _raw: SimpleNamespace(
            supported_candidate_mask=(True, True, False, False),
            initial_observation_sha256="b" * 64,
        ),
    )
    receipt = red.materialize_red_train_practice(reader, reader.memory, _spec())
    assert receipt.actor_move_ids == (33, 70, 0, 0)
    assert receipt.actor_pp == (20, 15, 0, 0)
    assert receipt.opponent_hp == 50
    assert receipt.legal_move_count == 2
    assert receipt.public_dict()["new_independent_upstream_roots"] == 0
    base = int(RamAddress.PARTY_MON_1) + PARTY_STRUCT_STRIDE
    for index in range(4):
        assert reader.memory[0xD01C + index] == receipt.actor_move_ids[index]
        assert reader.memory[0xD02D + index] == receipt.actor_pp[index]
        assert reader.memory[base + PARTY_MOVES_OFFSET + index] == receipt.actor_move_ids[index]
        assert reader.memory[base + PARTY_PP_OFFSET + index] == receipt.actor_pp[index]


def test_red_factory_rejects_unsafe_source_before_writes():
    reader = _reader()
    reader.phase = BattleMenuPhase.UNKNOWN
    before = dict(reader.memory)
    with pytest.raises(BattlePracticeError, match="MAIN boundary"):
        red.materialize_red_train_practice(reader, reader.memory, _spec())
    assert reader.memory == before


def test_red_factory_rejects_hp_above_max_before_writes():
    reader = _reader()
    before = dict(reader.memory)
    with pytest.raises(BattlePracticeError, match="MAIN boundary"):
        red.materialize_red_train_practice(reader, reader.memory, _spec(opponent_hp=81))
    assert reader.memory == before
