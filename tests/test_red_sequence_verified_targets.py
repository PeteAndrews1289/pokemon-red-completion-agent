"""Complete prospective collector -> native channel joins, no dataset admission."""

import pytest
from test_red_sequence_native_audit import collect, read
from test_red_sequence_state_audit import reader

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_sequence_verified_targets import verify_sequence_target_channels


def setup(tmp_path, monkeypatch):
    root, args, executed = collect(tmp_path, monkeypatch)
    audit_reader = reader(monkeypatch)
    args.update(
        reader=audit_reader, partition=read(root / "native-plan.json")["source"]["partition"],
        expected_actor_plan_sha256=canonical_sha256(read(root / "episode/plan.json")),
        expected_declaration_sha256=canonical_sha256(
            read(root / "episode/sequence/declaration.json")),
        expected_catalog_sha256=audit_reader.catalog_sha256,
    )
    return root, args, executed


def test_verified_native_values_join_prospective_windows_without_train_admission(
    tmp_path, monkeypatch,
):
    root, args, executed = setup(tmp_path, monkeypatch)
    original = (root / "episode/sequence/window-000.json").read_bytes()
    complete, censored = verify_sequence_target_channels(root, **args)
    assert complete.measurement.new_progress == 1
    assert complete.original.measurement.new_progress == 0  # unverified original retained
    assert complete.targets.known == (True, True, True, True, True, True, False)
    assert complete.targets.values[:2] == (0.5, 0.0)
    assert not any(censored.targets.known) and censored.measurement.frames == 2
    assert complete.native_channel_audit_sha256 == censored.native_channel_audit_sha256
    assert not complete.training_eligible and not censored.training_eligible
    assert (root / "episode/sequence/window-000.json").read_bytes() == original
    assert executed == [2, 4, 6] and args["reader"].emulator.frame_count == 0


@pytest.mark.parametrize("field", [
    "expected_native_plan_sha256", "expected_actor_plan_sha256", "expected_actor_result_sha256",
    "expected_declaration_sha256", "expected_catalog_sha256", "source_sha256", "partition",
])
def test_every_join_identity_remains_required(tmp_path, monkeypatch, field):
    root, args, _ = setup(tmp_path, monkeypatch)
    args[field] = "development" if field == "partition" else "f" * 64
    if field == "partition":
        current = read(root / "native-plan.json")["source"]["partition"]
        args[field] = "train" if current == "development" else "development"
    with pytest.raises(ValueError):
        verify_sequence_target_channels(root, **args)
