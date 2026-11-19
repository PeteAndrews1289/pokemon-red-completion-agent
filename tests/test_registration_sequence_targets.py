from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import pytest
from pokemon_red_completion.player_sequence_targets import *
from pokemon_red_completion.player_short_sequence import MeasuredSequenceStep, SequenceEnd, measure_sequence
from pokemon_red_completion.red_sequence_state_audit import NativeRegistrationSequenceStateReader


def test_recorded_resource_targets_keep_unverified_cost_and_labels_unknown():
    m = measure_sequence((MeasuredSequenceStep(*[c*64 for c in "abcd"], 10, 60, 100, 0),),
        horizon=4, end=SequenceEnd.TASK_TERMINAL)
    raw = unverified_sequence_targets(m, target_contract=RESOURCE_TASK_TARGET_CONTRACT)
    assert raw.raw == (0, 0, 10, 60, None, 0, 0)
    assert not any(raw.known)
    with pytest.raises(ValueError, match="independently verified"):
        sequence_targets(m, target_contract=RESOURCE_TASK_TARGET_CONTRACT)
    assert unverified_sequence_targets(m, target_contract=TASK_TERMINAL_TARGET_CONTRACT) == sequence_targets(m, target_contract=TASK_TERMINAL_TARGET_CONTRACT)


class Emulator:
    frame_count=0
    def load_state_bytes(self, state): self.state=state
    def save_state_bytes(self): return self.state


def test_native_reader_binds_dex_stock_and_rejects_unread_or_changed_boundaries(tmp_path, monkeypatch):
    import pokemon_red_completion.red_sequence_state_audit as module
    em=Emulator()
    def raw():
        return SimpleNamespace(battle_state=0, player_money=100, bag_items=((20,2 if em.state==b"a" else 1),))
    class Reader:
        def __init__(self, emulator): pass
        def read(self):return raw()
        def read_pokedex_state(self): return SimpleNamespace(owned_species=frozenset({1} if em.state==b"a" else {1,2}))
    monkeypatch.setattr(module,"PokemonRedStateReader",Reader)
    reader=NativeRegistrationSequenceStateReader(em,rom=b"rom",expected_rom_sha256=sha256(b"rom").hexdigest())
    rows=[]
    for state in (b"a",b"b"):
        p=tmp_path/state.decode();p.write_bytes(state);rows.append(reader.read(p,sha256(state).hexdigest()))
    assert reader.task_completed(rows[0].progress,rows[1].progress)
    assert reader.priced_medicine_depletion(rows[0].state_sha256,rows[1].state_sha256)==300
    with pytest.raises(ValueError,match="independently read"):
        reader.priced_medicine_depletion("f"*64,rows[1].state_sha256)
    with pytest.raises(ValueError,match="state bytes"):
        reader.read(p,"f"*64)
