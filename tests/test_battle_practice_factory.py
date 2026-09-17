from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_battle_practice_factory as red
from pokemon_red_completion.battle_practice_factory import (
    BattlePracticeError,
    BattlePracticeSpec,
    PracticeStats,
)
from pokemon_red_completion.observation import (
    PARTY_MOVES_OFFSET,
    PARTY_PP_OFFSET,
    PARTY_SPECIES_OFFSET,
    PARTY_STRUCT_STRIDE,
    BattleMenuPhase,
    RamAddress,
)
from pokemon_red_completion.red_battle_catalog import (
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
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

        def word(address, default):
            return 256 * self.memory.get(address, default >> 8) + self.memory.get(
                address + 1, default & 255
            )

        party_bases = tuple(int(RamAddress.PARTY_MON_1) + i * PARTY_STRUCT_STRIDE for i in range(6))
        party_species = tuple(self.memory.get(b, 28) for b in party_bases)

        return SimpleNamespace(
            battle_state=1,
            party_count=6,
            party_species_ids=party_species,
            party_hp=tuple(word(b + 1, 90) for b in party_bases),
            party_max_hp=tuple(word(b + 34, 90) for b in party_bases),
            party_levels=tuple(self.memory.get(b + 33, 30) for b in party_bases),
            party_status=tuple(self.memory.get(b + 4, 0) for b in party_bases),
            party_moves=tuple(
                tuple(self.memory.get(b + 8 + i, 0) for i in range(4)) for b in party_bases
            ),
            party_pp=tuple(
                tuple(self.memory.get(b + 29 + i, 0) for i in range(4)) for b in party_bases
            ),
            map_id=165,
            active_party_index=1,
            active_party_species_id=self.memory.get(base + PARTY_SPECIES_OFFSET, 28),
            active_party_level=self.memory.get(base + 33, 30),
            active_party_hp=word(base + 1, 90),
            active_party_max_hp=word(base + 34, 90),
            active_party_moves=moves,
            active_party_pp=pp,
            battler_moves=moves,
            battler_pp=pp,
            enemy_species_id=self.memory.get(int(RamAddress.ENEMY_SPECIES), 55),
            enemy_level=self.memory.get(int(RamAddress.ENEMY_LEVEL), 30),
            enemy_hp=enemy_hp,
            enemy_max_hp=word(int(RamAddress.ENEMY_MAX_HP), self.enemy_max_hp),
        )

    def read_battle_menu_state(self, _raw):
        return SimpleNamespace(phase=self.phase)

    def read_wild_capture_identity(self):
        enemy = self.memory.get(int(RamAddress.ENEMY_SPECIES), 55)
        return SimpleNamespace(
            transformed=self.transformed,
            original_species_id=enemy,
            displayed_species_id=enemy,
            type_ids=(
                self.memory.get(int(RamAddress.ENEMY_TYPE_1), 21),
                self.memory.get(int(RamAddress.ENEMY_TYPE_2), 21),
            ),
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
    with pytest.raises(BattlePracticeError, match="opponent HP exceeds maximum"):
        red.materialize_red_train_practice(reader, reader.memory, _spec(opponent_hp=81))
    assert reader.memory == before


def test_practice_level_and_stats_validation_and_legacy_hash():
    baseline = _spec()
    assert baseline.configuration_sha256 == _spec().configuration_sha256
    previous = _spec(
        source_state_sha256="d629f64d9800ecd7dda6cb6b47f4c12f1e0f81a5124422fde8e1a28b11ad902f",
        root_lineage_id=(
            "red-goal-root-c1d575483e311b3a9854b0e85237f725c3da1412ed62ab142dcd82050c666435"
        ),
        actor_moves=[
            {"move_ref": pokemon_red_move_ref(33), "pp": 20},
            {"move_ref": pokemon_red_move_ref(70), "pp": 15},
            {"move_ref": pokemon_red_move_ref(58), "pp": 10},
            {"move_ref": pokemon_red_move_ref(12), "pp": 5},
        ],
        opponent_hp=77,
    )
    assert previous.configuration_sha256 == (
        "b7dc83e42f5b7ab910b52b0dd10ee951b243998a3ce4f8c7989d96b8ef23e876"
    )
    with pytest.raises(BattlePracticeError, match="actor_level"):
        _spec(actor_level=101)
    with pytest.raises(BattlePracticeError, match="five declared fields"):
        _spec(actor_stats={"attack": 50})
    with pytest.raises(BattlePracticeError, match="opponent HP exceeds"):
        _spec(
            opponent_stats={"max_hp": 30, "attack": 50, "defense": 50, "speed": 50, "special": 50}
        )
    extended = _spec(actor_level=20, opponent_level=25)
    assert extended.configuration_sha256 != baseline.configuration_sha256


def test_red_factory_mirrors_levels_hp_and_all_stats(monkeypatch):
    reader = _reader()
    memory = reader.memory
    base = int(RamAddress.PARTY_MON_1) + PARTY_STRUCT_STRIDE
    memory[0xD022] = 30
    memory[0xCD0F] = 30
    memory[0xCD23] = 30
    memory[0xD015] = 0
    memory[0xD016] = 90
    memory[0xD023] = 0
    memory[0xD024] = 90
    monkeypatch.setattr(red.PokemonRedObservationEncoder, "from_state_reader", lambda _r: object())
    monkeypatch.setattr(
        red,
        "prepare_red_battle_scenario",
        lambda _e, _r: SimpleNamespace(
            supported_candidate_mask=(True, True, False, False),
            initial_observation_sha256="b" * 64,
        ),
    )
    actor = {"max_hp": 120, "attack": 75, "defense": 50, "speed": 65, "special": 80}
    opponent = {"max_hp": 85, "attack": 65, "defense": 72, "speed": 55, "special": 69}
    receipt = red.materialize_red_train_practice(
        reader,
        memory,
        _spec(
            actor_level=24,
            opponent_level=28,
            actor_stats=actor,
            opponent_stats=opponent,
            actor_hp=100,
            opponent_hp=55,
        ),
    )
    assert receipt.actor_level == 24
    assert receipt.opponent_level == 28
    assert receipt.actor_hp == 100
    assert receipt.opponent_hp == 55
    assert receipt.actor_stats.public_dict() == actor
    assert receipt.opponent_stats.public_dict() == opponent
    for address in (base + 3, base + 33, 0xD017, 0xD022, 0xCD0F):
        assert memory[address] == 24
    for address in (0xCFE8, int(RamAddress.ENEMY_LEVEL), 0xCD23):
        assert memory[address] == 28
    for block in (base + 34, 0xD023, 0xCD10):
        assert [red._u16(memory, block + 2 * index) for index in range(5)] == list(actor.values())
    for block in (int(RamAddress.ENEMY_MAX_HP), 0xCD24):
        assert [red._u16(memory, block + 2 * index) for index in range(5)] == list(
            opponent.values()
        )
    assert red._u16(memory, base + 1) == red._u16(memory, 0xD015) == 100


def test_red_factory_rejects_incoherent_source_mirror_before_writes():
    reader = _reader()
    reader.memory[0xD022] = 29
    before = dict(reader.memory)
    with pytest.raises(BattlePracticeError, match="source battle and party mirrors"):
        red.materialize_red_train_practice(reader, reader.memory, _spec(actor_level=24))
    assert reader.memory == before


def test_reserve_spec_validation_and_hash():
    reserve = {
        "party_slot": 1,
        "species_ref": pokemon_red_species_ref(84),
        "level": 35,
        "moves": [{"move_ref": pokemon_red_move_ref(85), "pp": 15}],
    }
    assert _spec(party_reserves=[reserve]).configuration_sha256 != _spec().configuration_sha256
    with pytest.raises(BattlePracticeError, match="distinct slots"):
        _spec(party_reserves=[reserve, reserve])
    with pytest.raises(BattlePracticeError, match="1..100"):
        _spec(party_reserves=[{**reserve, "level": 101}])
    with pytest.raises(BattlePracticeError, match="reserve record differs"):
        _spec(party_reserves=[{**reserve, "unknown": 1}])


def test_red_factory_materializes_reserve_party_member(monkeypatch):
    reader = _reader()
    memory = reader.memory
    base = int(RamAddress.PARTY_MON_1)
    memory[base] = 28
    memory[int(RamAddress.PARTY_SPECIES)] = 28
    monkeypatch.setattr(red.PokemonRedObservationEncoder, "from_state_reader", lambda _r: object())
    monkeypatch.setattr(
        red,
        "prepare_red_battle_scenario",
        lambda _e, _r: SimpleNamespace(
            supported_candidate_mask=(True, True, False, False),
            initial_observation_sha256="b" * 64,
        ),
    )
    species = SimpleNamespace(
        types=(23, 23),
        catch_rate=190,
        nickname_bytes=b"PIKACHU\x50\x50\x50\x50",
        neutral_stats=lambda _level: PracticeStats(70, 55, 40, 80, 45),
        experience_at_level=lambda _level: 12345,
    )
    reserve = {
        "party_slot": 1,
        "species_ref": pokemon_red_species_ref(84),
        "level": 35,
        "moves": [
            {"move_ref": pokemon_red_move_ref(85), "pp": 15},
            {"move_ref": pokemon_red_move_ref(98), "pp": 30},
        ],
        "hp": 50,
    }
    receipt = red.materialize_red_train_practice(
        reader,
        memory,
        _spec(party_reserves=[reserve]),
        cartridge=SimpleNamespace(species=lambda _id: species),
    )
    assert receipt.party_reserves is not None
    assert receipt.party_reserves[0]["species_id"] == 84
    assert reader.read().party_species_ids[0] == 84
    assert reader.read().party_hp[0] == 50
    assert reader.read().party_moves[0] == (85, 98, 0, 0)
    assert memory[base + 3] == memory[base + 33] == 35
    assert bytes(memory[red.PARTY_NICKNAMES_BASE + i] for i in range(11)) == species.nickname_bytes


def test_red_factory_changes_both_species_and_opponent_moves(monkeypatch):
    reader = _reader()
    memory = reader.memory
    base = int(RamAddress.PARTY_MON_1) + PARTY_STRUCT_STRIDE
    memory[base + PARTY_SPECIES_OFFSET] = 28
    memory[int(RamAddress.PARTY_SPECIES) + 1] = 28
    memory[red._BATTLE_SPECIES] = 28
    memory[red._BATTLE_SPECIES_2] = 28
    memory[int(RamAddress.ENEMY_SPECIES)] = 55
    memory[int(RamAddress.ENEMY_SPECIES_2)] = 55
    memory[red._BATTLE_LEVEL] = 30
    memory[red._PLAYER_UNMODIFIED_LEVEL] = 30
    memory[red._ENEMY_UNMODIFIED_LEVEL] = 30
    red._put_u16(memory, red._BATTLE_HP, 90)
    red._put_u16(memory, red._BATTLE_MAX_HP, 90)
    monkeypatch.setattr(red.PokemonRedObservationEncoder, "from_state_reader", lambda _r: object())
    monkeypatch.setattr(
        red,
        "prepare_red_battle_scenario",
        lambda _e, _r: SimpleNamespace(
            supported_candidate_mask=(True, True, False, False),
            initial_observation_sha256="b" * 64,
        ),
    )
    actor = SimpleNamespace(
        types=(23, 23),
        catch_rate=190,
        base_stats=(35, 55, 30, 90, 50),
        base_experience=82,
        neutral_stats=lambda _level: PracticeStats(70, 55, 40, 80, 45),
        experience_at_level=lambda _level: 12345,
    )
    opponent = SimpleNamespace(
        types=(21, 21),
        catch_rate=45,
        base_stats=(44, 48, 65, 43, 50),
        base_experience=66,
        neutral_stats=lambda _level: PracticeStats(65, 45, 60, 40, 48),
        experience_at_level=lambda _level: 10000,
    )
    cartridge = SimpleNamespace(species=lambda number: {84: actor, 177: opponent}[number])
    receipt = red.materialize_red_train_practice(
        reader,
        memory,
        _spec(
            actor_species_ref=pokemon_red_species_ref(84),
            opponent_species_ref=pokemon_red_species_ref(177),
            actor_level=35,
            opponent_level=33,
            actor_moves=[
                {"move_ref": pokemon_red_move_ref(85), "pp": 15},
                {"move_ref": pokemon_red_move_ref(98), "pp": 30},
            ],
            opponent_moves=[
                {"move_ref": pokemon_red_move_ref(55), "pp": 25},
                {"move_ref": pokemon_red_move_ref(33), "pp": 35},
            ],
            opponent_hp=40,
        ),
        cartridge=cartridge,
    )
    assert (receipt.actor_species_id, receipt.opponent_species_id) == (84, 177)
    assert receipt.actor_experience == 12345
    assert receipt.actor_stats == actor.neutral_stats(35)
    assert receipt.opponent_stats == opponent.neutral_stats(33)
    assert receipt.opponent_move_ids == (55, 33, 0, 0)
    assert receipt.opponent_pp == (25, 35, 0, 0)
    assert tuple(memory[red._ENEMY_BASE_STATS + i] for i in range(5)) == opponent.base_stats
    assert tuple(memory[base + red._PARTY_EXPERIENCE_OFFSET + i] for i in range(3)) == tuple(
        (12345).to_bytes(3, "big")
    )
