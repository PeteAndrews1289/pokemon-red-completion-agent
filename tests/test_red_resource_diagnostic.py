import pytest

from pokemon_red_completion.observation import RamAddress
from pokemon_red_completion.red_party import (
    HP_OFFSET,
    MAX_HP_OFFSET,
    MOVES_OFFSET,
    PP_OFFSET,
    STATUS_OFFSET,
)
from pokemon_red_completion.red_party import (
    member_field_address as addr,
)
from pokemon_red_completion.red_resource_diagnostic import (
    condition_development_resources,
    restored_resource_writes,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def memory():
    data = bytearray(65536)
    data[int(RamAddress.PARTY_COUNT)] = 2
    for i in range(2):
        data[addr(i, MAX_HP_OFFSET)] = 1
        data[addr(i, MAX_HP_OFFSET + 1)] = 44
        data[addr(i, MOVES_OFFSET)] = 45  # Growl, base40, maximum61 with3PP Ups
        data[addr(i, PP_OFFSET)] = 0xC1
    return data


def test_restore_only_hp_and_pp_preserving_pp_ups_and_empty_slots():
    data = memory()
    before = bytes(data)
    planned = restored_resource_writes(data, partition=ScenarioPartition.DEVELOPMENT)
    assert bytes(data) == before
    result = condition_development_resources(data, partition=ScenarioPartition.DEVELOPMENT)
    assert result["writes"] == planned and result["setup_memory_writes"] == 6
    assert result["actor_memory_writes"] == 0 and result["assisted"]
    assert {i for i, (a, b) in enumerate(zip(before, data, strict=True)) if a != b} == {
        r["address"] for r in planned
    }
    for i in range(2):
        assert data[addr(i, HP_OFFSET) : addr(i, HP_OFFSET) + 2] == bytes((1, 44))
        assert data[addr(i, PP_OFFSET) : addr(i, PP_OFFSET) + 4] == bytes((0xFD, 0, 0, 0))
    assert restored_resource_writes(data, partition=ScenarioPartition.DEVELOPMENT) == []


@pytest.mark.parametrize(
    "partition", [p for p in ScenarioPartition if p is not ScenarioPartition.DEVELOPMENT]
)
def test_reject_other_partitions_without_writes(partition):
    data = memory()
    before = bytes(data)
    with pytest.raises(ValueError):
        condition_development_resources(data, partition=partition)
    assert bytes(data) == before


@pytest.mark.parametrize(
    "address,value",
    [
        (int(RamAddress.IS_IN_BATTLE), 2),
        (int(RamAddress.PARTY_COUNT), 0),
        (int(RamAddress.PARTY_COUNT), 7),
        (addr(1, STATUS_OFFSET), 8),
        (addr(1, HP_OFFSET), 2),
        (addr(1, PP_OFFSET + 1), 1),
        (addr(1, PP_OFFSET), 0xFF),
    ],
)
def test_bad_last_member_or_field_rejects_before_any_write(address, value):
    data = memory()
    data[address] = value
    before = bytes(data)
    with pytest.raises(ValueError):
        condition_development_resources(data, partition=ScenarioPartition.DEVELOPMENT)
    assert bytes(data) == before


def test_unexpected_write_side_effect_is_detected():
    class BadMemory:
        def __init__(self):
            self.data = memory()

        def __getitem__(self, a):
            return self.data[a]

        def __setitem__(self, a, v):
            self.data[a] = v
            self.data[0xC000] = 99

    with pytest.raises(ValueError, match="unexpected memory"):
        condition_development_resources(BadMemory(), partition=ScenarioPartition.DEVELOPMENT)
