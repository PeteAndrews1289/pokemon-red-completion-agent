"""Packed native journal: the same sealed records in far fewer files, plus press observations."""

import json
import os
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import private_artifacts as private
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import RamAddress
from pokemon_red_completion.red_player_lesson_runtime import (
    _RecordedActions,
    native_action_record_id,
)
from pokemon_red_completion.red_press_observation import (
    PRESS_OBSERVATION_KIND,
    VIEW_FIELDS,
    decode_screen,
    decode_view,
    read_screen,
    read_view,
)

PACKED = "packed_sealed_v1"


def store_at(tmp_path, name, storage=PACKED):
    root = tmp_path / name
    root.mkdir(mode=0o700)
    options = dict(
        repository_root=tmp_path / "repository",
        device_id=lambda p: 2,
        git_worktree_probe=lambda p: False,
        allow_same_device=True,
    )
    options["repository_root"].mkdir(exist_ok=True)
    extra = {} if storage is None else {"native_input_storage": storage}
    return root, private.initialize_private_root(root, **options, **extra), options


def sample(ordinal=0):
    return dict(ordinal=ordinal, before_frame=ordinal * 8, action="move", value="down", repeat=1)


def publish(store, ordinal=0, kind="action"):
    identifier = native_action_record_id(kind, "a" * 64, ordinal)
    record = (
        sample(ordinal)
        if kind == "action"
        else dict(ordinal=ordinal, before_frame=0, after_frame=8, succeeded=True)
    )
    return identifier, store.publish_sealed_record(
        identifier, kind=f"red_native_lesson_{kind}", record=record
    )


def segments(root):
    return sorted(p for p in root.iterdir() if p.name.startswith("native-journal-"))


def test_packed_records_are_byte_identical_to_flat_and_directory_records(tmp_path):
    _, legacy, _ = store_at(tmp_path, "legacy", storage=None)
    _, flat, _ = store_at(tmp_path, "flat", storage="flat_sealed_v1")
    root, packed, options = store_at(tmp_path, "packed")
    for ordinal in (0, 1, 10000):
        for kind in ("action", "trace"):
            identifier, a = publish(legacy, ordinal, kind)
            _, b = publish(flat, ordinal, kind)
            _, c = publish(packed, ordinal, kind)
            assert a.read_bytes() == b.read_bytes() == c.read_bytes()
            assert a.summary == b.summary == c.summary
            reopened = private.open_private_root(root, **options)
            assert reopened.find_sealed_record(identifier).read_bytes() == a.read_bytes()
            meta = reopened.inspect_sealed_record_metadata(identifier)
            assert meta == flat.inspect_sealed_record_metadata(identifier)
    names = {p.name for p in root.iterdir()}
    assert names == {
        private.PRIVATE_ROOT_SENTINEL,
        ".native-input-storage.json",
        segments(root)[0].name,
    }


def test_many_presses_stay_in_one_file(tmp_path):
    root, store, options = store_at(tmp_path, "packed")
    for ordinal in range(300):
        publish(store, ordinal, "action")
        publish(store, ordinal, "trace")
    assert len(list(root.iterdir())) == 3
    reopened = private.open_private_root(root, **options)
    ids = [native_action_record_id("trace", "a" * 64, i) for i in range(300)]
    batch = reopened.read_native_record_batch(ids, expected_kind="red_native_lesson_trace")
    assert [r.read()["ordinal"] for r in batch] == list(range(300))


def test_publication_is_idempotent_only_for_identical_bytes(tmp_path):
    _, store, _ = store_at(tmp_path, "packed")
    identifier, first = publish(store)
    assert publish(store)[1].read_bytes() == first.read_bytes()
    with pytest.raises(private.PrivateArtifactError, match="different"):
        store.publish_sealed_record(
            identifier, kind="red_native_lesson_action", record=sample(7)
        )


def test_diagnostics_and_inventory_use_the_packed_journal(tmp_path):
    _, store, _ = store_at(tmp_path, "packed")
    identifier = "rnp-diagnostic-" + "d" * 64
    event = dict(kind="battle_failure", diagnostic_only=True, payload=dict(actions=3))
    record = store.publish_sealed_record(identifier, kind="red_native_player_diagnostic", record=event)
    rows = store.inventory_sealed_record_metadata(
        record_id_prefix="rnp-diagnostic-",
        expected_kind="red_native_player_diagnostic",
        maximum_records=1,
    )
    assert rows[0].declared_record_sha256 == record.summary.record_sha256


def test_non_input_evidence_keeps_the_directory_representation(tmp_path):
    root, store, _ = store_at(tmp_path, "packed")
    store.publish_sealed_record("native-claim", kind="red_native_player_execution", record={"v": 1})
    assert {p.name for p in (root / "native-claim").iterdir()} == {"manifest.json", "record.json"}
    assert store.find_sealed_record("native-claim").read() == {"v": 1}


def test_unacknowledged_torn_tail_is_ignored_and_writing_moves_on(tmp_path):
    root, store, options = store_at(tmp_path, "packed")
    publish(store, 0)
    publish(store, 1)
    segment = segments(root)[0]
    with open(segment, "ab") as handle:  # a writer that died mid-frame
        handle.write(b'{"format":"pokemon-red-completion-packed-native-frame","manifest')
    reopened = private.open_private_root(root, **options)
    assert reopened.find_sealed_record(native_action_record_id("action", "a" * 64, 1)) is not None
    publish(reopened, 2)
    assert len(segments(root)) == 2
    third = private.open_private_root(root, **options)
    assert all(
        third.find_sealed_record(native_action_record_id("action", "a" * 64, i)) for i in range(3)
    )


@pytest.mark.parametrize("fault", ["payload", "drop_first", "reorder", "header", "permissions"])
def test_changed_removed_or_reordered_frames_fail_closed(tmp_path, fault):
    root, store, options = store_at(tmp_path, "packed")
    for ordinal in range(3):
        publish(store, ordinal)
    segment = segments(root)[0]
    lines = segment.read_bytes().split(b"\n")
    frames = [b"\n".join(lines[i : i + 3]) + b"\n" for i in range(0, len(lines) - 1, 3)]
    if fault == "payload":
        frames[1] = frames[1].replace(b'"before_frame":8', b'"before_frame":9')
    elif fault == "drop_first":
        frames = frames[1:]
    elif fault == "reorder":
        frames[0], frames[1] = frames[1], frames[0]
    elif fault == "header":
        frames[2] = frames[2].replace(b'"sequence":2', b'"sequence":7')
    os.chmod(segment, 0o600)
    segment.write_bytes(b"".join(frames))
    if fault == "permissions":
        os.chmod(segment, 0o644)
    reopened = private.open_private_root(root, **options)
    with pytest.raises(private.PrivateArtifactError):
        reopened.find_sealed_record(native_action_record_id("action", "a" * 64, 2))


def test_segments_rotate_and_every_record_stays_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(private, "_MAX_PACKED_SEGMENT_BYTES", 4096)
    root, store, options = store_at(tmp_path, "packed")
    for ordinal in range(40):
        publish(store, ordinal)
    assert len(segments(root)) > 1
    reopened = private.open_private_root(root, **options)
    assert all(
        reopened.find_sealed_record(native_action_record_id("action", "a" * 64, i))
        for i in range(40)
    )


def test_storage_declaration_is_prospective_and_exact(tmp_path):
    root, store, options = store_at(tmp_path, "packed")
    marker = json.loads((root / ".native-input-storage.json").read_bytes())
    assert marker == {"native_input_storage": PACKED, "schema": "pokemon.native-input-storage.v1"}
    assert store.records_press_observations is True
    assert private.open_private_root(root, **options).records_press_observations is True
    with pytest.raises(private.PrivateArtifactError, match="different"):
        private.open_private_root(root, **options, native_input_storage="flat_sealed_v1")
    flat_root, flat, _ = store_at(tmp_path, "flat", storage="flat_sealed_v1")
    assert flat.records_press_observations is False
    publish(flat)
    with pytest.raises(private.PrivateArtifactError, match="different"):
        private.initialize_private_root(flat_root, **options, native_input_storage=PACKED)
    used = tmp_path / "used"
    used.mkdir(mode=0o700)
    private.initialize_private_root(used, **options)
    (used / "leftover").write_text("x")
    with pytest.raises(private.PrivateArtifactError, match="packed native input recording"):
        private.initialize_private_root(used, **options, native_input_storage=PACKED)
    with pytest.raises(private.PrivateArtifactError, match="unsupported"):
        store_at(tmp_path, "bad", storage="zip_v1")


class RamEmulator:
    """A frame counter plus Work RAM; ticking changes RAM like a game would."""

    pressed_buttons = frozenset()

    def __init__(self):
        self.frame_count = 0
        self.ram = bytearray(0x2000)
        self.set(RamAddress.CURRENT_MAP, 0x25)
        self.set(RamAddress.PLAYER_X, 5)
        self.set(RamAddress.PLAYER_Y, 7)
        self.set(RamAddress.PARTY_MON_1_HP, 0x01, 0x2C)
        self.set(RamAddress.PLAYER_MONEY, 0x00, 0x30, 0x00)
        for i in range(360):
            self.ram[RamAddress.TILE_MAP - 0xC000 + i] = i % 7

    def set(self, address, *values):
        for offset, value in enumerate(values):
            self.ram[address - 0xC000 + offset] = value

    def read_u8(self, address):
        if not 0xC000 <= address <= 0xDFFF:
            raise ValueError("outside Work RAM")
        return self.ram[address - 0xC000]

    def save_state_bytes(self):
        return bytes(self.ram) + self.frame_count.to_bytes(8, "big")


def record_presses(store, presses=3):
    from pokemon_red_completion.executor import NativeLessonController

    emulator = RamEmulator()
    controller = NativeLessonController(emulator, maximum_frames=1000)
    recorder = _RecordedActions(controller, store, "a" * 64, presses)
    recorder.enabled = True

    def execute(action):
        emulator.frame_count += 8
        emulator.set(RamAddress.PLAYER_Y, emulator.read_u8(RamAddress.PLAYER_Y) + 1)
        return N(frames=8)

    recorder.delegate.execute = execute
    for _ in range(presses):
        recorder.execute(MacroAction(MacroActionKind.MOVE, "down"))
    return recorder, emulator


def test_press_observations_add_data_without_changing_inputs_or_records(tmp_path):
    _, flat, _ = store_at(tmp_path, "flat", storage="flat_sealed_v1")
    root, packed, options = store_at(tmp_path, "packed")
    flat_recorder, flat_game = record_presses(flat)
    packed_recorder, packed_game = record_presses(packed)
    assert flat_recorder.trace == packed_recorder.trace
    assert flat_game.save_state_bytes() == packed_game.save_state_bytes()
    assert (flat_recorder.press_observations, packed_recorder.press_observations) == (0, 3)
    reopened = private.open_private_root(root, **options)
    for ordinal in range(3):
        for kind in ("action", "trace"):
            identifier = native_action_record_id(kind, "a" * 64, ordinal)
            assert (
                reopened.find_sealed_record(identifier).read_bytes()
                == flat.find_sealed_record(identifier).read_bytes()
            )
    from pokemon_red_completion.red_player_lesson_runtime import canonical_sha256

    first = reopened.find_sealed_record(
        "rno-" + canonical_sha256(dict(declaration="a" * 64, ordinal=0)),
        expected_kind=PRESS_OBSERVATION_KIND,
    ).read()
    before, after = decode_view(first["before"]), decode_view(first["after"])
    assert (before["y"], after["y"]) == (7, 8)
    assert before["map"] == 0x25 and before["lead_hp"] == 300
    assert before["money_bcd"] == "003000"
    assert first["view_layout"] == "pokemon.red.press-view.v1"
    assert len(packed.find_sealed_record(
        "rno-" + canonical_sha256(dict(declaration="a" * 64, ordinal=0))).read_bytes()) < 900
    assert first["action"] == "move" and first["value"] == "down"
    assert first["observation_only"] is True and first["automatic_fit"] is False
    assert decode_screen(first["screen_after"]) == bytes(i % 7 for i in range(360))
    assert len(list(root.iterdir())) == 3


def test_unreadable_ram_is_recorded_as_missing_not_a_crash():
    assert read_view(None) is None
    assert read_screen(None) is None
    assert {name for name, _, _ in VIEW_FIELDS} == set(decode_view(read_view(RamEmulator().read_u8)))
    with pytest.raises(ValueError):
        decode_view("00")


def test_only_press_observations_skip_their_own_fsync(tmp_path, monkeypatch):
    _, store, _ = store_at(tmp_path, "packed")
    publish(store, 0)  # opens the segment (directory fsync) before counting
    synced = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: synced.append(fd) or real(fd))
    publish(store, 1)
    store.publish_sealed_record("rno-" + "e" * 64, kind=PRESS_OBSERVATION_KIND, record=dict(ordinal=1))
    assert len(synced) == 1
    publish(store, 2)
    assert len(synced) == 2


def test_index_stays_compact_and_cache_is_released(tmp_path, monkeypatch):
    advised = []
    real = os.posix_fadvise
    monkeypatch.setattr(os, "posix_fadvise", lambda fd, o, n, a: advised.append(a) or real(fd, o, n, a))
    _, store, _ = store_at(tmp_path, "packed")
    for ordinal in range(50):
        publish(store, ordinal)
    journal = store._packed
    assert all(type(k) is bytes and len(k) == 16 and type(v) is int for k, v in journal._index.items())
    assert advised and set(advised) == {os.POSIX_FADV_DONTNEED}


def test_runner_accepts_only_declared_storage_modes():
    from run_configured_red_player import declared_input_recording

    base = dict(partition="development", input_recording=dict(
        git_worktree_probe="gitless_fast_path_v1", reason="M2 packed journal"))
    for mode in ("flat_sealed_v1", PACKED):
        base["input_recording"]["native_input_storage"] = mode
        assert declared_input_recording(base)["native_input_storage"] == mode
    base["input_recording"]["native_input_storage"] = "zip_v1"
    with pytest.raises(ValueError):
        declared_input_recording(base)
