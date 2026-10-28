"""ROM-free boundaries for the classroom's disclosed native opponent AI axis."""

from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_practice_factory import BattlePracticeError
from pokemon_red_completion.observation import BattleMenuPhase, RamAddress
from pokemon_red_completion.red_status_practice import condition_train_trainer_class
from pokemon_red_completion.scenario_lab import ScenarioPartition


@dataclass(frozen=True)
class State:
    battle_state: int = 2
    party_count: int = 6
    enemy_party_count: int = 1
    active_party_index: int = 0
    enemy_party_position: int = 0
    party_hp: tuple[int, ...] = (100,) * 6
    battler_hp: int = 100
    enemy_hp: int = 169


class Memory(dict):
    def __init__(self, *, ignore=False):
        super().__init__({int(RamAddress.TRAINER_CLASS): 25, 1234: 77})
        self.writes = []
        self.ignore = ignore

    def __setitem__(self, address, value):
        self.writes.append((address, value))
        if not self.ignore:
            super().__setitem__(address, value)


def reader(state=None, phase=BattleMenuPhase.MAIN):
    state = State() if state is None else state
    return SimpleNamespace(read=lambda: state,
                           read_battle_menu_state=lambda _: SimpleNamespace(phase=phase))


def test_one_native_ai_byte_changes_without_party_or_actor_changes():
    memory = Memory()
    receipt = condition_train_trainer_class(reader(), memory,
        partition=ScenarioPartition.TRAIN, trainer_class_id=44)
    assert memory.writes == [(int(RamAddress.TRAINER_CLASS), 44)]
    assert memory[1234] == 77
    assert receipt["before"] == 25 and receipt["after"] == 44
    assert receipt["actor_memory_writes"] == 0
    assert receipt["semantic_battle_state_unchanged"]
    assert not receipt["campaign_identity_promoted"]


@pytest.mark.parametrize("partition", [ScenarioPartition.DEVELOPMENT, ScenarioPartition.TEST,
                                       "train", None])
def test_nontrain_rejected_before_memory_write(partition):
    memory = Memory()
    with pytest.raises(BattlePracticeError):
        condition_train_trainer_class(reader(), memory,
            partition=partition, trainer_class_id=44)
    assert memory.writes == []


@pytest.mark.parametrize("value", [0, 48, -1, True, 44.0, "44", None])
def test_invalid_native_class_rejected_before_write(value):
    memory = Memory()
    with pytest.raises(BattlePracticeError):
        condition_train_trainer_class(reader(), memory,
            partition=ScenarioPartition.TRAIN, trainer_class_id=value)
    assert memory.writes == []


@pytest.mark.parametrize("changes", [dict(battle_state=1), dict(party_count=0),
    dict(enemy_party_count=0), dict(active_party_index=1), dict(enemy_party_position=1),
    dict(party_hp=(0, 100)), dict(battler_hp=0), dict(enemy_hp=0)])
def test_invalid_materialized_boundary_rejected_before_write(changes):
    memory = Memory()
    with pytest.raises(BattlePracticeError):
        condition_train_trainer_class(reader(replace(State(), **changes)), memory,
            partition=ScenarioPartition.TRAIN, trainer_class_id=44)
    assert memory.writes == []


def test_failed_readback_is_not_a_success_receipt():
    with pytest.raises(BattlePracticeError, match="readback"):
        condition_train_trainer_class(reader(), Memory(ignore=True),
            partition=ScenarioPartition.TRAIN, trainer_class_id=44)
