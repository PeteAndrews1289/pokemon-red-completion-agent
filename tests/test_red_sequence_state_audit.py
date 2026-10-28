"""Native-reader seam tests; fake bytes are never claimed as cartridge evidence."""

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_red_sequence_native_audit import collect, read

import pokemon_red_completion.red_sequence_state_audit as module
from pokemon_red_completion.observation import EVENT_FLAG_BYTES, Badge, EventFlag
from pokemon_red_completion.player_short_sequence import SequenceEnd, measure_sequence
from pokemon_red_completion.provenance import canonical_sha256


class Emulator:
    frame_count = 0
    state = b""

    def load_state_bytes(self, state):
        self.state = state

    def save_state_bytes(self):
        return self.state


def events(*flags):
    result = bytearray(EVENT_FLAG_BYTES)
    for flag in flags:
        byte, bit = divmod(int(flag), 8)
        result[byte] |= 1 << bit
    return bytes(result)


def reader(monkeypatch, raw=None):
    em = Emulator()
    monkeypatch.setattr(module, "trainer_headers", lambda *a, **kw: (NS(event_flag=10),))

    def observe():
        return raw if raw is not None else NS(
            battle_state=0, player_money=3000, badge_bits=0,
            event_flags=events(10, *([EventFlag.MET_BILL] if int(em.state) > 0 else [])),
        )

    monkeypatch.setattr(module, "PokemonRedStateReader", lambda _: NS(read=observe))
    return module.CeruleanSequenceStateReader(
        em, rom=b"rom", expected_rom_sha256=sha256(b"rom").hexdigest(), maps=(1, 2),
    )


def arguments(root, audit_reader, source):
    return dict(reader=audit_reader, source_sha256=source,
                expected_plan_sha256=canonical_sha256(read(root / "plan.json")),
                expected_result_sha256=canonical_sha256(read(root / "result.json")),
                expected_catalog_sha256=audit_reader.catalog_sha256)


def test_native_channels_do_not_count_travel_or_repeated_events(tmp_path, monkeypatch):
    native, kwargs, executed = collect(tmp_path, monkeypatch)
    root = native / "episode"
    audit_reader = reader(monkeypatch)
    audit = module.audit_sequence_state_channels(
        root, **arguments(root, audit_reader, kwargs["source_sha256"]),
    )
    measured = measure_sequence(audit.steps, horizon=3, end=SequenceEnd.HORIZON,
                                initial_progress=audit.initial_progress,
                                initial_quests=audit.initial_quests)
    assert measured.new_progress == 1  # initial event10 and repeat visits earn nothing
    assert measured.completed_quests == 0  # meeting Bill is not completing his quest
    assert (measured.actions, measured.frames, measured.cash_debits) == (3, 6, 0)
    assert not audit.training_eligible and not audit.battle_losses_verified
    assert audit_reader.emulator.frame_count == 0 and executed == [2, 4, 6]


@pytest.mark.parametrize("field,value", [
    ("cash", 2999), ("quests", ("defeat_misty",)),
    ("state_sha256", "f" * 64),
])
def test_native_disagreement_rejects_without_editing_records(
    tmp_path, monkeypatch, field, value,
):
    native, kwargs, _ = collect(tmp_path, monkeypatch)
    root = native / "episode"
    audit_reader = reader(monkeypatch)
    original = audit_reader.read
    monkeypatch.setattr(audit_reader, "read", lambda *a: replace(original(*a), **{field: value}))
    before = (root / "result.json").read_bytes()
    with pytest.raises(ValueError, match="differs"):
        module.audit_sequence_state_channels(
            root, **arguments(root, audit_reader, kwargs["source_sha256"]),
        )
    assert (root / "result.json").read_bytes() == before


def test_lost_native_progress_is_not_silently_reintroduced(tmp_path, monkeypatch):
    native, kwargs, _ = collect(tmp_path, monkeypatch)
    root = native / "episode"
    audit_reader = reader(monkeypatch)
    original = audit_reader.read

    def observed(path, digest):
        result = original(path, digest)
        return replace(result, progress=()) if path.parent.name == "step-001" else result

    monkeypatch.setattr(audit_reader, "read", observed)
    with pytest.raises(ValueError, match="progress differs"):
        module.audit_sequence_state_channels(
            root, **arguments(root, audit_reader, kwargs["source_sha256"]),
        )


@pytest.mark.parametrize("flag,badge,quests", [
    (EventFlag.BEAT_MISTY, 0, ()),
    (EventFlag.BEAT_MISTY, int(Badge.CASCADE), ("defeat_misty",)),
    (EventFlag.MET_BILL, 0, ()),
    (EventFlag.GOT_SS_TICKET, 0, ("help_bill",)),
])
def test_native_quest_predicates_separate_intermediate_progress(
    tmp_path, monkeypatch, flag, badge, quests,
):
    state = tmp_path / "state"
    state.write_bytes(b"state")
    audit_reader = reader(monkeypatch, NS(battle_state=0, player_money=427,
                         event_flags=events(flag), badge_bits=badge))
    result = audit_reader.read(state, sha256(b"state").hexdigest())
    assert result.quests == quests and result.cash == 427


@pytest.mark.parametrize("fault", ["state", "frame", "cash", "battle", "badge", "catalog"])
def test_unstable_or_wrong_native_boundary_rejected(tmp_path, monkeypatch, fault):
    raw = NS(battle_state=0, player_money=427, event_flags=events(), badge_bits=0)
    if fault == "cash":
        raw.player_money = True
    if fault == "battle":
        raw.battle_state = 1
    if fault == "badge":
        raw.badge_bits = int(Badge.CASCADE)
    audit_reader = reader(monkeypatch, raw)
    if fault == "frame":
        original = audit_reader.emulator.load_state_bytes

        def load(state):
            original(state)
            audit_reader.emulator.frame_count += 1

        monkeypatch.setattr(audit_reader.emulator, "load_state_bytes", load)
    state = tmp_path / "state"
    state.write_bytes(b"state")
    with pytest.raises(ValueError):
        if fault == "catalog":
            module.CeruleanSequenceStateReader(
                Emulator(), rom=b"rom", expected_rom_sha256="a" * 64, maps=(1, 2),
            )
        else:
            audit_reader.read(state, "f" * 64 if fault == "state" else sha256(b"state").hexdigest())
