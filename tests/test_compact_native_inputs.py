"""Lossless native-input representation; not new training or cartridge evidence."""

import json
import os
import stat
from hashlib import sha256
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import private_artifacts as private
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.red_player_lesson_runtime import (
    _RecordedActions,
    native_action_record_id,
)


def store_at(tmp_path, name, *, flat=True):
    root = tmp_path / name
    root.mkdir(mode=0o700)
    options = dict(
        repository_root=tmp_path / "repository",
        device_id=lambda p: 2,
        git_worktree_probe=lambda p: False,
        allow_same_device=True,
    )
    options["repository_root"].mkdir(exist_ok=True)
    store = private.initialize_private_root(
        root, **options, **({"native_input_storage": "flat_sealed_v1"} if flat else {})
    )
    return root, store, options


def sample(ordinal=0):
    return dict(ordinal=ordinal, before_frame=0, action="wait", value=None, repeat=1)


def publish(store, ordinal=0):
    identifier = native_action_record_id("action", "a" * 64, ordinal)
    return identifier, store.publish_sealed_record(
        identifier, kind="red_native_lesson_action", record=sample(ordinal)
    )


def test_flat_and_legacy_preserve_exact_payload_manifest_identity_and_reopen(tmp_path):
    old_root, old, _ = store_at(tmp_path, "old", flat=False)
    root, store, options = store_at(tmp_path, "flat")
    identifier, original = publish(old)
    _, compact = publish(store)
    assert original.read_bytes() == compact.read_bytes()
    assert original.summary == compact.summary
    assert (old_root / identifier / "record.json").read_bytes() == compact.read_bytes()
    assert (root / (identifier + ".sealed.jsonl")).read_bytes() == (
        (old_root / identifier / "manifest.json").read_bytes() + original.read_bytes()
    )
    assert not (root / identifier).exists()
    reopened = private.open_private_root(root, **options)
    assert reopened.find_sealed_record(identifier).read_bytes() == original.read_bytes()
    assert (
        reopened.inspect_sealed_record_metadata(identifier).declared_record_sha256
        == original.summary.record_sha256
    )


def test_non_input_evidence_keeps_original_directory_representation(tmp_path):
    root, store, _ = store_at(tmp_path, "flat")
    store.publish_sealed_record(
        "native-claim", kind="red_native_player_execution", record={"version": 1}
    )
    assert {p.name for p in (root / "native-claim").iterdir()} == {"manifest.json", "record.json"}


def test_native_diagnostics_use_same_lossless_flat_record_and_api(tmp_path):
    old_root, old, _ = store_at(tmp_path, "old", flat=False)
    root, store, _ = store_at(tmp_path, "flat")
    identifier = "rnp-diagnostic-" + "d" * 64
    event = dict(
        kind="battle_failure",
        diagnostic_only=True,
        automatic_fit=False,
        payload=dict(reason="ordinary loss", actions=37, frames=1234),
    )
    a = old.publish_sealed_record(identifier, kind="red_native_player_diagnostic", record=event)
    b = store.publish_sealed_record(identifier, kind="red_native_player_diagnostic", record=event)
    assert a.summary == b.summary and a.read_bytes() == b.read_bytes()
    assert not (root / identifier).exists() and (old_root / identifier).is_dir()
    assert (
        store.inventory_sealed_record_metadata(
            record_id_prefix="rnp-diagnostic-",
            expected_kind="red_native_player_diagnostic",
            maximum_records=1,
        )[0].declared_record_sha256
        == a.summary.record_sha256
    )


@pytest.mark.parametrize(
    "fault",
    ["payload", "truncated", "identity", "kind", "digest", "size", "schema", "status", "unsafe"],
)
def test_flat_reader_rejects_corrupt_noncanonical_or_unrelated_bytes(tmp_path, fault):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    path = root / (identifier + ".sealed.jsonl")
    header, payload = path.read_bytes().split(b"\n", 1)
    manifest = json.loads(header)
    if fault == "payload":
        payload = payload.replace(b'"ordinal":0', b'"ordinal":1')
    elif fault == "truncated":
        payload = payload[:-2]
    elif fault == "identity":
        manifest["record_id"] = "other"
    elif fault == "kind":
        manifest["kind"] = "red_native_lesson_trace"
    elif fault == "digest":
        manifest["record_sha256"] = "b" * 64
    elif fault == "size":
        manifest["bytes"] += 1
    elif fault == "schema":
        manifest["schema_version"] = True
    elif fault == "status":
        manifest["status"] = "partial"
    else:
        payload = b'{"path":"/private/data"}\n'
        manifest.update(bytes=len(payload), record_sha256=sha256(payload).hexdigest())
    path.write_bytes(private._canonical_json_line(manifest) + payload)
    with pytest.raises(private.PrivateArtifactError):
        store.find_sealed_record(identifier)


@pytest.mark.parametrize("fault", ["permissions", "hardlink", "symlink", "directory", "ambiguous"])
def test_flat_reader_and_metadata_keep_filesystem_safety(tmp_path, fault):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    path = root / (identifier + ".sealed.jsonl")
    if fault == "permissions":
        path.chmod(0o644)
    elif fault == "hardlink":
        os.link(path, root / "alias")
    elif fault == "symlink":
        target = root / "target"
        path.rename(target)
        path.symlink_to(target)
    elif fault == "directory":
        path.unlink()
        path.mkdir(mode=0o700)
    else:
        (root / identifier).mkdir(mode=0o700)
    for call in (store.find_sealed_record, store.inspect_sealed_record_metadata):
        with pytest.raises(private.PrivateArtifactError):
            call(identifier)


def test_metadata_reads_only_manifest_even_for_damaged_same_length_payload(tmp_path, monkeypatch):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    path = root / (identifier + ".sealed.jsonl")
    header, payload = path.read_bytes().split(b"\n", 1)
    path.write_bytes(header + b"\n" + payload.replace(b'"ordinal":0', b'"ordinal":1'))
    inode = path.stat().st_ino
    real_read, observed = os.read, bytearray()

    def tracked(fd, amount):
        value = real_read(fd, amount)
        if os.fstat(fd).st_ino == inode:
            observed.extend(value)
        return value

    monkeypatch.setattr(os, "read", tracked)
    metadata = store.inspect_sealed_record_metadata(identifier)
    assert bytes(observed) == header + b"\n"
    assert metadata.public_dict()["payload_opened"] is False
    with pytest.raises(private.PrivateArtifactError, match="integrity"):
        store.find_sealed_record(identifier)


def test_idempotence_conflict_and_manifest_inventory_are_unchanged(tmp_path):
    _, store, _ = store_at(tmp_path, "flat")
    identifier = "rnl-action-" + "f" * 64
    original = store.publish_sealed_record(
        identifier, kind="red_native_lesson_action", record=sample()
    )
    assert (
        store.publish_sealed_record(
            identifier, kind="red_native_lesson_action", record=sample()
        ).read_bytes()
        == original.read_bytes()
    )
    with pytest.raises(private.PrivateArtifactError, match="different content"):
        store.publish_sealed_record(identifier, kind="red_native_lesson_action", record=sample(1))
    rows = store.inventory_sealed_record_metadata(
        record_id_prefix="rnl-action-", expected_kind="red_native_lesson_action", maximum_records=1
    )
    assert len(rows) == 1 and rows[0].declared_record_sha256 == original.summary.record_sha256


@pytest.mark.parametrize("fault", ["missing", "changed", "symlink", "permissions"])
def test_storage_marker_cannot_be_removed_swapped_or_relaxed(tmp_path, fault):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    marker = root / ".native-input-storage.json"
    if fault == "missing":
        marker.unlink()
    elif fault == "changed":
        marker.write_bytes(b"{}\n")
    elif fault == "symlink":
        target = root / "marker-copy"
        marker.rename(target)
        marker.symlink_to(target)
    else:
        marker.chmod(0o644)
    with pytest.raises(private.PrivateArtifactError):
        store.find_sealed_record(identifier)


def test_old_journal_is_not_converted_in_place(tmp_path):
    root, store, options = store_at(tmp_path, "old", flat=False)
    identifier, before = publish(store)
    with pytest.raises(private.PrivateArtifactError, match="new empty journal"):
        private.initialize_private_root(root, **options, native_input_storage="flat_sealed_v1")
    assert store.find_sealed_record(identifier).read_bytes() == before.read_bytes()


@pytest.mark.parametrize("interrupted", [False, True])
@pytest.mark.parametrize("ordinal", [0, 9999, 10000])
def test_durable_intent_precedes_input_and_partial_failure_trace_reopens(
    tmp_path, interrupted, ordinal
):
    root, store, options = store_at(tmp_path, "flat")
    from test_red_player_lesson_runtime import Emulator

    from pokemon_red_completion.executor import NativeLessonController

    emulator = Emulator()
    controller = NativeLessonController(emulator, maximum_frames=1000)
    actions = _RecordedActions(controller, store, "a" * 64, ordinal + 1)
    actions.enabled = True
    actions.trace = [None] * ordinal
    intent_id = native_action_record_id("action", "a" * 64, ordinal)
    trace_id = native_action_record_id("trace", "a" * 64, ordinal)

    def execute(action):
        # Reopen from a new reader, not the recorder's in-memory return value.
        reopened = private.open_private_root(root, **options)
        assert reopened.find_sealed_record(intent_id).read()["ordinal"] == ordinal
        assert reopened.find_sealed_record(trace_id) is None
        emulator.frame_count += 2 if interrupted else 8
        if interrupted:
            raise RuntimeError("interrupted native input")
        return N(frames=8)

    actions.delegate.execute = execute
    if interrupted:
        with pytest.raises(RuntimeError, match="interrupted native input"):
            actions.execute(MacroAction(MacroActionKind.WAIT))
    else:
        actions.execute(MacroAction(MacroActionKind.WAIT))
    saved = private.open_private_root(root, **options).find_sealed_record(trace_id).read()
    assert saved["succeeded"] is (not interrupted)
    assert saved["after_frame"] == (2 if interrupted else 8)
    assert not controller.input_enabled


def test_existing_training_loader_reauthenticates_flat_actions_and_traces(tmp_path):
    from test_red_collection_teacher_learning import sealed

    from pokemon_red_completion import red_collection_teacher_learning as learning

    fake, plan, result, identity, _ = sealed(tmp_path)
    _, store, options = store_at(tmp_path, "flat")
    for name, (kind, record) in fake.records.items():
        store.publish_sealed_record(name, kind=kind, record=record)
    item = learning.publish_collection_teacher_outcome(
        store, plan, result, native_execution_claim_id=identity.claim_id
    )
    row = learning.load_collection_teacher_lesson(store, item)
    reopened = private.open_private_root(store._root, **options)
    assert learning.load_collection_teacher_lesson(reopened, item) == row
    assert learning.retained_collection_teacher_lessons(
        reopened, {"collection_teacher_lessons": [item.public_dict()]}
    )[1] == (row,)


def test_flat_publication_syncs_payload_then_directory_before_return(tmp_path, monkeypatch):
    _, store, _ = store_at(tmp_path, "flat")
    real_sync = os.fsync
    synchronized = []

    def sync(fd):
        synchronized.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        real_sync(fd)

    monkeypatch.setattr(os, "fsync", sync)
    publish(store)
    assert synchronized == [False, True]


def test_failed_publication_retains_partial_bytes_and_sends_no_controller_input(
    tmp_path, monkeypatch
):
    from test_red_player_lesson_runtime import Emulator

    from pokemon_red_completion.executor import NativeLessonController

    root, store, _ = store_at(tmp_path, "flat")
    emulator = Emulator()
    controller = NativeLessonController(emulator, maximum_frames=100)
    actions = _RecordedActions(controller, store, "a" * 64, 1)
    actions.enabled = True

    def fail_rename(*args):
        raise OSError("injected storage failure before intent publication")

    monkeypatch.setattr(private, "_rename_no_replace", fail_rename)
    with pytest.raises(private.PrivateArtifactError, match="publish"):
        actions.execute(MacroAction(MacroActionKind.WAIT))
    assert emulator.frame_count == 0 and not actions.trace and not controller.input_enabled
    partials = tuple(root.glob("*.partial"))
    assert len(partials) == 1 and partials[0].is_file()
    assert json.loads(partials[0].read_bytes().split(b"\n", 1)[0])["status"] == "complete"
    assert store.find_sealed_record(native_action_record_id("action", "a" * 64, 0)) is None


@pytest.mark.parametrize("error_type", [private.PrivateArtifactError, OSError])
def test_failed_directory_sync_never_returns_a_successful_input_publication(
    tmp_path, monkeypatch, error_type
):
    from test_red_player_lesson_runtime import Emulator

    from pokemon_red_completion.executor import NativeLessonController

    _, store, _ = store_at(tmp_path, "flat")
    emulator = Emulator()
    controller = NativeLessonController(emulator, maximum_frames=100)
    actions = _RecordedActions(controller, store, "a" * 64, 1)
    actions.enabled = True

    def fail_directory_sync(*args):
        raise error_type("injected directory synchronization failure")

    monkeypatch.setattr(private, "_fsync_directory", fail_directory_sync)
    with pytest.raises(private.PrivateArtifactError):
        actions.execute(MacroAction(MacroActionKind.WAIT))
    assert emulator.frame_count == 0 and not actions.trace and not controller.input_enabled



def test_full_reader_batches_header_io_and_keeps_exact_authenticated_payload(tmp_path, monkeypatch):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, original = publish(store)
    inode = (root / (identifier + ".sealed.jsonl")).stat().st_ino
    real_read, nonempty_reads = os.read, []

    def tracked(fd, amount):
        value = real_read(fd, amount)
        if os.fstat(fd).st_ino == inode and value:
            nonempty_reads.append((amount, value))
        return value

    monkeypatch.setattr(os, "read", tracked)
    reopened = store.find_sealed_record(identifier)
    assert reopened.read_bytes() == original.read_bytes()
    assert reopened.summary == original.summary
    assert len(nonempty_reads) == 2  # Bounded header scan plus existing complete revalidation.
    assert all(amount > 1 for amount, _ in nonempty_reads)


@pytest.mark.parametrize("maximum_read", [1, 7, 64])
def test_full_reader_handles_short_regular_file_reads(tmp_path, monkeypatch, maximum_read):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, original = publish(store)
    inode = (root / (identifier + ".sealed.jsonl")).stat().st_ino
    real_read = os.read

    def short_read(fd, amount):
        return real_read(fd, min(amount, maximum_read) if os.fstat(fd).st_ino == inode else amount)

    monkeypatch.setattr(os, "read", short_read)
    reopened = store.find_sealed_record(identifier)
    assert reopened.read_bytes() == original.read_bytes()
    assert reopened.summary == original.summary


@pytest.mark.parametrize("metadata_only", [False, True])
@pytest.mark.parametrize("contents,reason", [(b"{", "truncated"), (b"x" * 4096, "bound")])
def test_both_header_modes_reject_unterminated_or_oversized_manifests(
    tmp_path, metadata_only, contents, reason
):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    (root / (identifier + ".sealed.jsonl")).write_bytes(contents)
    reader = store.inspect_sealed_record_metadata if metadata_only else store.find_sealed_record
    with pytest.raises(private.PrivateArtifactError, match=reason):
        reader(identifier)


def test_full_reader_still_rejects_metadata_change_after_payload_validation(tmp_path, monkeypatch):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    path = root / (identifier + ".sealed.jsonl")
    original_read = private._read_private_entry

    def read_then_change(directory, name, **kwargs):
        data = original_read(directory, name, **kwargs)
        if name == path.name:
            info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
        return data

    monkeypatch.setattr(private, "_read_private_entry", read_then_change)
    with pytest.raises(private.PrivateArtifactError, match="changed during validation"):
        store.find_sealed_record(identifier)
