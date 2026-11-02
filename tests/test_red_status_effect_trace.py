from collections import defaultdict
from copy import deepcopy
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_status_effect_trace as trace
from pokemon_red_completion.rom import RomValidationError
from pokemon_red_completion.scenario_lab import ScenarioPartition


class Backend:
    def __init__(self):
        self.memory = defaultdict(int)
        for i, byte in enumerate(trace.DISPATCH):
            self.memory[trace.BANK, trace.ENTRY+i] = byte
        self.register_file = SimpleNamespace(SP=0xDFF0)
        self.frame_count = 0
        self.hooks = {}
        self.memory.update({0xCFD2: 105, 0xCFD3: 0x38, 0xD015: 0, 0xD016: 50,
                            0xD023: 0, 0xD024: 100, 0xD057: 2})

    def hook_register(self, bank, address, callback, context):
        assert (bank, address) not in self.hooks
        self.hooks[bank, address] = (callback, context)

    def hook_deregister(self, bank, address):
        del self.hooks[bank, address]


def recorder(monkeypatch, backend):
    monkeypatch.setattr(trace, "verify_rom_bytes", lambda *args: None)
    rom = bytearray(0x40000)
    start = trace.BANK*0x4000 + trace.ENTRY - 0x4000
    rom[start:start+len(trace.DISPATCH)] = trace.DISPATCH
    return trace.RedStatusEffectTrace(backend, bytes(rom), partition=ScenarioPartition.TRAIN)


def invoke(rec, mutate=lambda: None):
    rec.enter(None)
    mutate()
    rec.leave(None)
    return rec.records[-1]["label"]


def test_healing_observed_before_opposing_damage_and_no_ram_writes(monkeypatch):
    b = Backend()
    rec = recorder(monkeypatch, b)
    with rec.installed():
        label = invoke(rec, lambda: b.memory.update({0xD016: 100}))
        b.memory[0xD016] = 40  # opposing damage after the selected effect
    assert label["application_success"] == 1 and label["hp_gained_inside_effect"] == 50
    assert b.memory[0xD016] == 40 and not b.hooks
    before = deepcopy(b.memory)
    assert invoke(rec)["application_success"] == 0
    assert b.memory == before


@pytest.mark.parametrize("move,effect,initial,mutation,expected", [
    (156, 0x38, {0xD018: 16}, {0xD018: 2, 0xD016: 100}, 1),
    (156, 0x38, {0xD016: 100}, {}, 0),
    (109, 0x31, {}, {0xD067: 128, 0xD070: 3}, 1),
    (109, 0x31, {0xD067: 128, 0xD070: 3}, {}, 0),
    (50, 0x56, {}, {0xD072: 0x13}, 1),
    (50, 0x56, {0xD072: 0x13}, {}, 0),
])
def test_precise_effect_labels(monkeypatch, move, effect, initial, mutation, expected):
    b = Backend()
    b.memory.update({0xCFD2: move, 0xCFD3: effect, **initial})
    rec = recorder(monkeypatch, b)
    assert invoke(rec, lambda: b.memory.update(mutation))["application_success"] == expected


def test_mismatches_missing_entry_and_partial_trace_fail_closed(monkeypatch):
    b = Backend()
    rec = recorder(monkeypatch, b)
    with pytest.raises(ValueError, match="without entry"):
        rec.leave(None)
    with pytest.raises(ValueError, match="unclosed"), rec.installed():
        rec.enter(None)
    assert not b.hooks
    rec.pending = None
    assert invoke(rec, lambda: b.memory.update({0xCC2F: 1}))["kind"] == "unknown"
    with pytest.raises(ValueError, match="single-use"), rec.installed():
        pass


def test_cleanup_on_registration_failure_and_callback_failure(monkeypatch):
    b = Backend()
    original = b.hook_register
    def fail_second(bank, address, callback, context):
        if address == trace.RETURN:
            raise RuntimeError("registration")
        original(bank, address, callback, context)
    b.hook_register = fail_second
    rec = recorder(monkeypatch, b)
    with pytest.raises(RuntimeError), rec.installed():
        pass
    assert not b.hooks
    b.hook_register = original
    rec = recorder(monkeypatch, b)
    with pytest.raises(ValueError, match="nested"), rec.installed():
        rec.enter(None)
        rec.enter(None)
    assert not b.hooks


def test_non_train_and_wrong_cartridge_cannot_install_hooks():
    b = Backend()
    for partition in (ScenarioPartition.DEVELOPMENT, ScenarioPartition.TEST):
        with pytest.raises(ValueError, match="TRAIN-only"):
            trace.RedStatusEffectTrace(b, b"", partition=partition)
    with pytest.raises(RomValidationError):
        trace.RedStatusEffectTrace(b, b"", partition=ScenarioPartition.TRAIN)
    assert not b.hooks


def test_effect_setup_is_train_only_and_updates_volatile_mirrors():
    from pokemon_red_completion.observation import BattleMenuPhase
    from pokemon_red_completion.red_status_practice import condition_train_effect_state
    b = Backend()
    b.memory[0xCFED] = 33

    class Reader:
        def read(self):
            return SimpleNamespace(battle_state=2, party_count=1, enemy_party_count=1,
                active_party_index=0, enemy_party_position=0,
                enemy_confused=bool(b.memory[0xD067] & 128))

        def read_battle_menu_state(self, _):
            return SimpleNamespace(phase=BattleMenuPhase.MAIN)

    with pytest.raises(ValueError, match="TRAIN-only"):
        condition_train_effect_state(None, None, partition=ScenarioPartition.TEST)
    with pytest.raises(ValueError, match="has no move"):
        condition_train_effect_state(Reader(), b.memory, partition=ScenarioPartition.TRAIN,
                                     opponent_disabled_slot=4)
    result = condition_train_effect_state(Reader(), b.memory, partition=ScenarioPartition.TRAIN,
                                         opponent_confusion_turns=3, opponent_disabled_slot=1)
    assert result["actor_memory_writes"] == 0
    assert b.memory[0xD067] == 128 and b.memory[0xD070] == 3
    assert b.memory[0xD072] == 0x13 and b.memory[0xCCEF] == 33
    with pytest.raises(ValueError, match="clean single-member"):
        condition_train_effect_state(Reader(), b.memory, partition=ScenarioPartition.TRAIN)


def test_explicit_root_rejected_before_creating_files(tmp_path):
    import run_red_status_curriculum as lab
    args = SimpleNamespace(output=tmp_path)
    row = {"source_index": 1, "root": "first", "id": "unstarted"}
    with pytest.raises(ValueError, match="root assignment"):
        lab.materialize(args, row, 0, [(None, {"source_id": "first"})], None, "commit")
    assert not list(tmp_path.iterdir())
