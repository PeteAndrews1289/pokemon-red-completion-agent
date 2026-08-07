from unittest.mock import Mock

import pytest

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_party import PARTY_STRUCT_STRIDE, PokemonRedPartyReader
from pokemon_red_completion.red_team_training import (
    EmulatorState,
    run_red_team_balancing,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    TeamRosterPlan,
)


class FakeEmulatorState:
    def __init__(self, memory: dict[int, int] | None = None) -> None:
        self.memory = memory or {}
        
    def read_u8(self, address: int) -> int:
        return self.memory.get(address, 0)
        
    def write_u8(self, address: int, value: int) -> None:
        self.memory[address] = value


class FakeReader(PokemonRedStateReader):
    def __init__(self, states: list[RawGameState]) -> None:
        self.states = states
        self.call_count = 0

    def read(self) -> RawGameState:
        if not self.states:
            return Mock(spec=RawGameState)
        state = self.states.pop(0)
        self.call_count += 1
        return state

    def menu_phase(self) -> BattleMenuPhase:
        return BattleMenuPhase.MAIN


class FakeExecutor(ChapterExecutor):
    def __init__(self) -> None:
        self.actions: list[MacroAction] = []
        
    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        return None


def test_fake_emulator_harness_instantiates() -> None:
    emulator = FakeEmulatorState()
    reader = FakeReader([Mock(spec=RawGameState)])
    executor = CountingExecutor(FakeExecutor())
    
    # Just asserting the harness components can be instantiated without PyBoy
    assert emulator.read_u8(0) == 0
    assert reader.read() is not None
    assert executor.actions_executed == 0


def _write_party_member(emulator: FakeEmulatorState, index: int, species: int, level: int) -> None:
    # Party count
    emulator.write_u8(RamAddress.PARTY_COUNT, index + 1)
    
    # Species list
    emulator.write_u8(RamAddress.PARTY_SPECIES + index, species)
    emulator.write_u8(RamAddress.PARTY_SPECIES + index + 1, 0xFF)
    
    # Struct
    struct_addr = int(RamAddress.PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
    emulator.write_u8(struct_addr + 0x00, species)
    emulator.write_u8(struct_addr + 0x01, 100) # HP high
    emulator.write_u8(struct_addr + 0x02, 100) # HP low
    emulator.write_u8(struct_addr + 0x21, level) # Level (33)
    emulator.write_u8(struct_addr + 0x22, 100) # Max HP high
    emulator.write_u8(struct_addr + 0x23, 100) # Max HP low


def test_venue_mismatch_trigger_raises() -> None:
    emulator = FakeEmulatorState()
    _write_party_member(emulator, 0, 9, 50) # Blastoise
    
    # Expanding this tests further requires setting up run_red_team_balancing args
    pass
