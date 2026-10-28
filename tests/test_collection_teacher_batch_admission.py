"""Complete native teacher admission through both immutable storage formats."""
from types import SimpleNamespace as N
import pytest
from test_compact_native_inputs import store_at
from test_red_collection_teacher_learning import sealed
from pokemon_red_completion import red_collection_teacher_learning as learning
from pokemon_red_completion import private_artifacts as private
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_lesson_runtime import native_action_record_id


def materialized_lesson(tmp_path, *, flat):
    memory, plan, result, identity, native = sealed(tmp_path)
    # More than two batches: every record of the tail must still be verified.
    trace = [dict(ordinal=i, before_frame=i * 20, after_frame=(i + 1) * 20,
                  succeeded=True) for i in range(40)]
    result.update(trace=trace, actions=40, frames=800)
    for i, row in enumerate(trace):
        for phase, value in (("trace", row), ("action", dict(ordinal=i, before_frame=i * 20))):
            memory.publish_sealed_record(native_action_record_id(phase, canonical_sha256(native), i),
                                         kind="red_native_lesson_" + phase, record=value)
    item = learning.publish_collection_teacher_outcome(
        memory, plan, result, native_execution_claim_id=identity.claim_id)
    expected = learning.load_collection_teacher_lesson(memory, item)
    root, store, _ = store_at(tmp_path, "materialized", flat=flat)
    for identifier, (kind, value) in memory.records.items():
        store.publish_sealed_record(identifier, kind=kind, record=value)
    return root, store, item, native, expected


@pytest.mark.parametrize("flat", [False, True])
def test_full_batched_lesson_has_exact_original_fingerprint_and_no_format_conversion(tmp_path, flat):
    root, store, item, native, expected = materialized_lesson(tmp_path, flat=flat)
    actual = learning.load_collection_teacher_lesson(store, item)
    assert canonical_sha256(actual.public_dict()) == canonical_sha256(expected.public_dict())
    identifier = native_action_record_id("trace", canonical_sha256(native), 39)
    assert (root / identifier).is_dir() is (not flat)


@pytest.mark.parametrize("flat", [False, True])
@pytest.mark.parametrize("fault", ["missing", "payload", "mode", "ambiguous", "symlink"])
def test_batched_lesson_rejects_unsafe_or_missing_tail_in_every_format(tmp_path, flat, fault):
    root, store, item, native, _ = materialized_lesson(tmp_path, flat=flat)
    identifier = native_action_record_id("trace", canonical_sha256(native), 39)
    payload = root / (identifier + ".sealed.jsonl") if flat else root / identifier / "record.json"
    if fault == "missing":
        payload.unlink()
    elif fault == "payload":
        payload.write_bytes(payload.read_bytes().replace(b'"ordinal":39', b'"ordinal":38'))
    elif fault == "mode":
        payload.chmod(0o644)
    elif fault == "ambiguous":
        if flat:
            (root / identifier).mkdir(mode=0o700)
        else:
            (root / (identifier + ".sealed.jsonl")).write_bytes(b"{}\n{}\n")
    else:
        target = root / "tail-payload"
        payload.rename(target)
        payload.symlink_to(target)
    with pytest.raises((private.PrivateArtifactError, ValueError)):
        learning.load_collection_teacher_lesson(store, item)


@pytest.mark.parametrize("fault", ["short", "reordered", "kind"])
def test_batch_adapter_cannot_drop_reorder_or_substitute_record_identity(tmp_path, fault):
    _, store, item, _, _ = materialized_lesson(tmp_path, flat=True)
    read = store.read_native_record_batch
    class WrongBatch:
        find_sealed_record = store.find_sealed_record
        def read_native_record_batch(self, identifiers, *, expected_kind):
            batch = read(identifiers, expected_kind=expected_kind)
            if fault == "short":
                return batch[:-1]
            if fault == "reordered":
                return tuple(reversed(batch))
            return tuple(N(read=r.read, summary=N(record_id=r.summary.record_id,
                         kind="wrong")) for r in batch)
    with pytest.raises(ValueError, match="batch"):
        learning.load_collection_teacher_lesson(WrongBatch(), item)
