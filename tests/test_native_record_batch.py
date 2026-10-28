"""Bounded native snapshot integrity; no emulator or fit."""
import os
import pytest
from pokemon_red_completion import private_artifacts as private
from test_compact_native_inputs import store_at, publish

KIND = "red_native_lesson_action"

def test_batch_matches_individual_bytes_and_returns_independent_values(tmp_path):
    root, store, _ = store_at(tmp_path, "flat")
    ids = [publish(store, i)[0] for i in range(4)]
    ordinary = [store.find_sealed_record(i) for i in ids]
    snapshot = store.read_native_record_batch(ids, expected_kind=KIND)
    assert tuple(r.summary for r in snapshot) == tuple(r.summary for r in ordinary)
    assert tuple(r.read_bytes() for r in snapshot) == tuple(r.read_bytes() for r in ordinary)
    snapshot[0].read()["ordinal"] = 999
    assert snapshot[0].read()["ordinal"] == 0

@pytest.mark.parametrize("fault", ["payload", "truncated", "permissions", "hardlink", "symlink", "directory", "ambiguous", "missing", "marker", "sentinel"])
def test_batch_rejects_corrupt_or_unsafe_record_and_root(tmp_path, fault):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    path = root / (identifier + ".sealed.jsonl")
    if fault == "payload":
        path.write_bytes(path.read_bytes().replace(b'"ordinal":0', b'"ordinal":1'))
    elif fault == "truncated":
        path.write_bytes(path.read_bytes()[:-1])
    elif fault == "permissions":
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
    elif fault == "ambiguous":
        (root / identifier).mkdir(mode=0o700)
    elif fault == "missing":
        path.unlink()
    elif fault == "marker":
        (root / ".native-input-storage.json").write_text("{}\n")
    else:
        (root / private.PRIVATE_ROOT_SENTINEL).write_text("{}\n")
    with pytest.raises(private.PrivateArtifactError):
        store.read_native_record_batch([identifier], expected_kind=KIND)

@pytest.mark.parametrize("fault", ["sentinel", "marker", "root"])
def test_batch_revalidates_root_after_read_before_return(tmp_path, monkeypatch, fault):
    root, store, _ = store_at(tmp_path, "flat")
    identifier, _ = publish(store)
    read = private._read_flat_native_record
    def changed(*args, **kwargs):
        record = read(*args, **kwargs)
        if fault == "root":
            root.rename(tmp_path / "replaced-root")
            root.mkdir(mode=0o700)
        else:
            name = private.PRIVATE_ROOT_SENTINEL if fault == "sentinel" else ".native-input-storage.json"
            (root / name).write_text("{}\n")
        return record
    monkeypatch.setattr(private, "_read_flat_native_record", changed)
    with pytest.raises(private.PrivateArtifactError):
        store.read_native_record_batch([identifier], expected_kind=KIND)

@pytest.mark.parametrize("ids,kind", [([], KIND), (["rnl-action-" + "a" * 64] * 1025, KIND), ("rnl-action-" + "a" * 64, KIND), (["other"], KIND), (["rnl-action-" + "a" * 64], "red_native_lesson_trace"), (["rnl-action-" + "a" * 64], "collection_seal")])
def test_batch_rejects_undeclared_kind_identity_or_unbounded_input(tmp_path, ids, kind):
    _, store, _ = store_at(tmp_path, "flat")
    with pytest.raises(private.PrivateArtifactError):
        store.read_native_record_batch(ids, expected_kind=kind)

def test_batch_does_not_convert_legacy_root(tmp_path):
    _, store, _ = store_at(tmp_path, "old", flat=False)
    identifier, _ = publish(store)
    before = store.find_sealed_record(identifier)
    batch, = store.read_native_record_batch([identifier], expected_kind=KIND)
    assert batch.summary == before.summary and batch.read_bytes() == before.read_bytes()
    assert (store._root / identifier).is_dir()
    assert not (store._root / (identifier + ".sealed.jsonl")).exists()
