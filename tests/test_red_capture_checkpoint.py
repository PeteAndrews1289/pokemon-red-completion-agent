import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_capture_checkpoint import (
    capture_allocation_sha256,
    create_capture_journal,
    load_capture_checkpoint,
    write_capture_checkpoint,
)
from pokemon_red_completion.red_one_off_capture import OneOffCaptureBudget, OneOffCaptureRequest
from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget

TARGET = RedStaticCaptureTarget(145, 75, 50, 83, 9, 9, (9, 4), 1129)
ORIGIN = "a" * 64


def packet(tmp_path, phase="paused"):
    b = OneOffCaptureBudget(OneOffCaptureRequest(75, 50, ItemId.GREAT_BALL), 20, 20, 14)
    allocation = capture_allocation_sha256(
        ORIGIN, TARGET, b, maximum_status_attempts=3, preserve_viable_active=True
    )
    path = tmp_path / "receipt"
    digest = write_capture_checkpoint(
        path,
        state=b"exact retained save",
        origin_state_sha256=ORIGIN,
        target=TARGET,
        budget=b,
        status_attempts=1,
        preserve_viable_active=True,
        phase=phase,
    )
    args = dict(
        expected_receipt_sha256=digest,
        expected_origin_sha256=ORIGIN,
        expected_target=TARGET,
        expected_allocation_sha256=allocation,
    )
    return path, args, b


def reader():
    raw = NS(battle_state=1, map_id=83, enemy_level=50, bag_items=((3, 6),))
    return NS(read=lambda: raw, read_wild_capture_identity=lambda: NS(original_species_id=75))


def emulator():
    return NS(save_state_bytes=lambda: b"exact retained save")


def test_exact_state_original_allocation_and_status_counter_restored(tmp_path):
    path, args, b = packet(tmp_path)
    restored = load_capture_checkpoint(path, **args)
    assert restored.state == b"exact retained save" and restored.budget == b
    restored.require_live_resume(reader(), TARGET, emulator=emulator())
    prepare = restored.status_preparer(emulator(), None, None)
    assert prepare.attempts == 1 and prepare.maximum_attempts == 3
    assert prepare.preserve_viable_active and prepare.latched_original_species_id == 75
    assert restored.minimum_prepared_helper_level is None


def test_prepared_helper_floor_is_bound_to_allocation_and_survives_resume(tmp_path):
    budget=OneOffCaptureBudget(OneOffCaptureRequest(75,50,ItemId.GREAT_BALL),20,20,14)
    path=tmp_path/'prepared'
    digest=write_capture_checkpoint(path,state=b'exact retained save',origin_state_sha256=ORIGIN,
        target=TARGET,budget=budget,status_attempts=2,preserve_viable_active=True,
        minimum_prepared_helper_level=55)
    allocation=capture_allocation_sha256(ORIGIN,TARGET,budget,maximum_status_attempts=3,
        preserve_viable_active=True,minimum_prepared_helper_level=55)
    args=dict(expected_receipt_sha256=digest,expected_origin_sha256=ORIGIN,expected_target=TARGET,
        expected_allocation_sha256=allocation)
    restored=load_capture_checkpoint(path,**args)
    prepare=restored.status_preparer(emulator(),None,None)
    assert restored.minimum_prepared_helper_level==prepare.minimum_prepared_helper_level==55
    assert restored.status_attempts==prepare.attempts==2 and restored.budget.throws_committed==14
    old=capture_allocation_sha256(ORIGIN,TARGET,budget,maximum_status_attempts=3,preserve_viable_active=True)
    with pytest.raises(ValueError,match='allocation differs'):
        load_capture_checkpoint(path,**{**args,'expected_allocation_sha256':old})


@pytest.mark.parametrize(
    "field", ["expected_receipt_sha256", "expected_origin_sha256", "expected_allocation_sha256"]
)
def test_foreign_external_reference_rejected(tmp_path, field):
    path, args, _ = packet(tmp_path)
    args[field] = "b" * 64
    with pytest.raises(ValueError):
        load_capture_checkpoint(path, **args)


@pytest.mark.parametrize("file", ["state.bin", "receipt.json"])
def test_modified_bytes_rejected(tmp_path, file):
    path, args, _ = packet(tmp_path)
    (path / file).write_bytes((path / file).read_bytes() + b" ")
    with pytest.raises(ValueError):
        load_capture_checkpoint(path, **args)


def test_target_drift_rejected(tmp_path):
    path, args, _ = packet(tmp_path)
    args["expected_target"] = replace(TARGET, at=(8, 4))
    with pytest.raises(ValueError):
        load_capture_checkpoint(path, **args)


@pytest.mark.parametrize("phase", ["admitted", "throw_intent", "settled"])
def test_unsettled_or_completed_receipt_not_resumable(tmp_path, phase):
    path, args, _ = packet(tmp_path, phase)
    restored = load_capture_checkpoint(path, **args)
    with pytest.raises(ValueError):
        restored.require_live_resume(reader(), TARGET, emulator=emulator())
    with pytest.raises(ValueError):
        restored.status_preparer(None, None, None)


@pytest.mark.parametrize("fault", ["balls", "target", "map", "level", "battle"])
def test_observed_continuation_drift_refused(tmp_path, fault):
    path, args, _ = packet(tmp_path)
    restored = load_capture_checkpoint(path, **args)
    r = reader()
    raw = r.read()
    if fault == "balls":
        raw.bag_items = ((3, 7),)
    if fault == "target":
        r.read_wild_capture_identity = lambda: NS(original_species_id=74)
    if fault == "map":
        raw.map_id = 162
    if fault == "level":
        raw.enemy_level = 49
    if fault == "battle":
        raw.battle_state = 0
    with pytest.raises(ValueError):
        restored.require_live_resume(r, TARGET, emulator=emulator())


def test_semantically_similar_but_different_emulator_save_is_not_resumable(tmp_path):
    path, args, _ = packet(tmp_path)
    restored = load_capture_checkpoint(path, **args)
    other = NS(save_state_bytes=lambda: b"same target and balls but different history")
    with pytest.raises(ValueError, match="authenticated state"):
        restored.require_live_resume(reader(), TARGET, emulator=other)
    with pytest.raises(ValueError, match="authenticated state"):
        restored.status_preparer(other, None, None)


def test_existing_packet_never_overwritten(tmp_path):
    path, args, b = packet(tmp_path)
    with pytest.raises(FileExistsError):
        write_capture_checkpoint(
            path,
            state=b"other",
            origin_state_sha256=ORIGIN,
            target=TARGET,
            budget=b,
            status_attempts=1,
            preserve_viable_active=True,
        )
    assert load_capture_checkpoint(path, **args).state == b"exact retained save"


@pytest.mark.parametrize(
    "field,value", [("status_attempts", True), ("status_attempts", 4), ("phase", "unknown")]
)
def test_even_externally_referenced_malformed_counter_refused(tmp_path, field, value):
    path, args, _ = packet(tmp_path)
    data = json.loads((path / "receipt.json").read_bytes())
    data[field] = value
    blob = json.dumps(data).encode()
    (path / "receipt.json").write_bytes(blob)
    args["expected_receipt_sha256"] = hashlib.sha256(blob).hexdigest()
    with pytest.raises(ValueError):
        load_capture_checkpoint(path, **args)


def test_allocation_hash_does_not_change_when_spent_counter_advances(tmp_path):
    path, args, b = packet(tmp_path)
    b.throws_committed = 20
    assert (
        capture_allocation_sha256(
            ORIGIN, TARGET, b, maximum_status_attempts=3, preserve_viable_active=True
        )
        == args["expected_allocation_sha256"]
    )


def test_checkpoint_syncs_both_directory_entries_after_file_contents(monkeypatch, tmp_path):
    import os
    import stat

    synced = []
    native = os.fsync

    def fsync(fd):
        synced.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        native(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    packet(tmp_path)
    assert synced == [False, False, True, True]
    create_capture_journal(tmp_path / "journal")
    assert synced[-1] is True
    with pytest.raises(FileExistsError):
        create_capture_journal(tmp_path / "journal")


def test_directory_sync_failure_is_not_reported_as_a_committed_receipt(monkeypatch, tmp_path):
    import pokemon_red_completion.red_capture_checkpoint as m

    def fail(_):
        raise OSError("directory sync failed")

    monkeypatch.setattr(m, "_sync_directory", fail)
    with pytest.raises(OSError, match="sync failed"):
        packet(tmp_path)
    assert (tmp_path / "receipt/state.bin").exists()
    assert (tmp_path / "receipt/receipt.json").exists()
    # Partial packets remain preserved and cannot be retried in place.
    with pytest.raises(FileExistsError):
        packet(tmp_path)
