from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from pokemon_red_completion import private_artifacts as private_artifacts_module
from pokemon_red_completion.private_artifacts import (
    PRIVATE_JSON_ARTIFACT_FORMAT,
    PRIVATE_JSON_ARTIFACT_IDENTITY_FORMAT,
    PrivateArtifactError,
    PrivateArtifactWriter,
    initialize_private_root,
)


def _make_store(tmp_path: Path):
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda path: False,
    )
    return root, store


def _orphan(writer: PrivateArtifactWriter) -> None:
    writer._close_streams()
    writer._release_lock()


def test_begin_durably_binds_typed_identity_before_return(tmp_path: Path) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-identity", kind="battle_outcome_cycle")

    identity_path = (
        root
        / "bo-cycle-identity.partial"
        / private_artifacts_module._TYPED_ARTIFACT_IDENTITY
    )
    identity = json.loads(identity_path.read_text(encoding="ascii"))
    assert identity == {
        "artifact_id": "bo-cycle-identity",
        "format": PRIVATE_JSON_ARTIFACT_IDENTITY_FORMAT,
        "kind": "battle_outcome_cycle",
        "schema_version": 1,
    }
    assert stat.S_IMODE(identity_path.stat().st_mode) == 0o600
    writer.abort("test_cleanup")
    assert not (
        root
        / "bo-cycle-identity.failed.partial"
        / private_artifacts_module._TYPED_ARTIFACT_IDENTITY
    ).exists()


def test_reconciliation_seals_durable_streams_and_is_idempotent(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-plan", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "candidate-0"}, durable=True)
    writer.append("outcomes", {"utility": 1.0}, durable=True)
    partial = root / "bo-cycle-plan.partial"
    before = {
        path.name: path.read_bytes()
        for path in partial.iterdir()
        if path.suffix == ".jsonl"
    }
    _orphan(writer)

    recovered = store.reconcile_interrupted_artifact(
        "bo-cycle-plan",
        expected_kind="battle_outcome_cycle",
    )

    failed = root / "bo-cycle-plan.failed.partial"
    assert recovered.disposition == "sealed_interrupted"
    assert recovered.reason_code == "process_interrupted"
    assert recovered.summary.status == "failed"
    assert recovered.summary.stream_records == (("claims", 1), ("outcomes", 1))
    assert not partial.exists()
    assert {
        path.name: path.read_bytes()
        for path in failed.iterdir()
        if path.suffix == ".jsonl"
    } == before
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["format"] == PRIVATE_JSON_ARTIFACT_FORMAT
    assert manifest["reason_code"] == "process_interrupted"

    repeated = store.reconcile_interrupted_artifact(
        "bo-cycle-plan",
        expected_kind="battle_outcome_cycle",
    )
    assert repeated.disposition == "already_failed"
    assert repeated.reason_code == "process_interrupted"
    assert repeated.summary == recovered.summary
    reader = store.open_failed_artifact(
        "bo-cycle-plan",
        expected_kind="battle_outcome_cycle",
    )
    assert reader.summary == recovered.summary
    assert reader.reason_code == "process_interrupted"
    assert tuple(reader.iter_stream("claims", max_records=1)) == (
        {"claim_id": "candidate-0"},
    )
    assert tuple(reader.iter_stream("outcomes", max_records=1)) == ({"utility": 1.0},)


def test_reconciliation_retains_only_verified_prefix_before_a_torn_tail(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-torn", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "durable"}, durable=True)
    _orphan(writer)
    stream = root / "bo-cycle-torn.partial" / "claims.jsonl"
    durable_prefix = stream.read_bytes()
    with stream.open("ab", buffering=0) as handle:
        handle.write(b'{"claim_id":"torn')
        os.fsync(handle.fileno())

    recovered = store.reconcile_interrupted_artifact(
        "bo-cycle-torn",
        expected_kind="battle_outcome_cycle",
    )

    retained = root / "bo-cycle-torn.failed.partial" / "claims.jsonl"
    assert recovered.disposition == "sealed_interrupted"
    assert recovered.summary.stream_records == (("claims", 1),)
    assert retained.read_bytes() == durable_prefix
    assert b"torn" not in retained.read_bytes()
    reader = store.open_failed_artifact(
        "bo-cycle-torn",
        expected_kind="battle_outcome_cycle",
    )
    assert tuple(reader.iter_stream("claims", max_records=1)) == (
        {"claim_id": "durable"},
    )


def test_process_exit_releases_claim_and_retains_only_durable_prefix(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    root.mkdir()
    project_root = Path(__file__).resolve().parents[1]
    initialize_private_root(
        root,
        repository_root=project_root,
        allow_same_device=True,
        git_worktree_probe=lambda path: False,
    )
    program = """
import os
from pathlib import Path
from pokemon_red_completion.private_artifacts import open_private_root
root = Path(os.environ["RECOVERY_TEST_ROOT"])
project = Path(os.environ["RECOVERY_TEST_PROJECT"])
store = open_private_root(root, repository_root=project, allow_same_device=True)
writer = store.begin_artifact("bo-cycle-process", kind="battle_outcome_cycle")
writer.append("claims", {"claim_id": "durable"}, durable=True)
os.write(writer._streams["claims"].handle.fileno(), b'{"claim_id":"torn')
os._exit(23)
"""
    environment = dict(os.environ)
    environment["RECOVERY_TEST_ROOT"] = str(root)
    environment["RECOVERY_TEST_PROJECT"] = str(project_root)
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=project_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 23
    store = private_artifacts_module.open_private_root(
        root,
        repository_root=project_root,
        allow_same_device=True,
    )

    recovered = store.reconcile_interrupted_artifact(
        "bo-cycle-process",
        expected_kind="battle_outcome_cycle",
    )

    assert recovered.disposition == "sealed_interrupted"
    reader = store.open_failed_artifact(
        "bo-cycle-process",
        expected_kind="battle_outcome_cycle",
    )
    assert tuple(reader.iter_stream("claims", max_records=1)) == (
        {"claim_id": "durable"},
    )


def test_reconciliation_itself_resumes_after_recovery_seal_publish_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-recovery-crash", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "candidate-0"}, durable=True)
    _orphan(writer)
    real_rename = private_artifacts_module._rename_no_replace

    def interrupt_recovery_seal(source: Path, destination: Path) -> None:
        if destination.name == "manifest.json":
            raise OSError("simulated recovery interruption")
        real_rename(source, destination)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        interrupt_recovery_seal,
    )
    with pytest.raises(PrivateArtifactError, match="recovery seal"):
        store.reconcile_interrupted_artifact(
            "bo-cycle-recovery-crash",
            expected_kind="battle_outcome_cycle",
        )
    partial = root / "bo-cycle-recovery-crash.partial"
    assert (partial / private_artifacts_module._TYPED_RECOVERY_MANIFEST).is_file()
    assert not (partial / "manifest.json").exists()

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        real_rename,
    )
    recovered = store.reconcile_interrupted_artifact(
        "bo-cycle-recovery-crash",
        expected_kind="battle_outcome_cycle",
    )
    assert recovered.disposition == "sealed_interrupted"
    assert (root / "bo-cycle-recovery-crash.failed.partial").is_dir()


def test_reconciliation_finishes_interrupted_publication_failure_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-publish-cut", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "candidate-0"}, durable=True)
    real_rename = private_artifacts_module._rename_no_replace
    real_write = private_artifacts_module._write_exclusive_file
    completed_destination = root / "bo-cycle-publish-cut"

    def collide_at_complete_publish(source: Path, destination: Path) -> None:
        if destination == completed_destination:
            destination.mkdir()
            raise OSError("simulated completed publication collision")
        real_rename(source, destination)

    def interrupt_failed_manifest(path: Path, payload: bytes, *, mode: int) -> None:
        if path.name == "manifest.json" and (
            path.parent / "manifest.unpublished.json"
        ).exists():
            raise PrivateArtifactError("simulated publication conversion interruption")
        real_write(path, payload, mode=mode)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        collide_at_complete_publish,
    )
    monkeypatch.setattr(
        private_artifacts_module,
        "_write_exclusive_file",
        interrupt_failed_manifest,
    )
    with pytest.raises(PrivateArtifactError):
        writer.complete()

    partial = root / "bo-cycle-publish-cut.partial"
    assert (partial / "manifest.unpublished.json").is_file()
    assert (
        partial / private_artifacts_module._TYPED_ARTIFACT_IDENTITY
    ).is_file()
    assert not (partial / "manifest.json").exists()

    monkeypatch.setattr(private_artifacts_module, "_rename_no_replace", real_rename)
    monkeypatch.setattr(private_artifacts_module, "_write_exclusive_file", real_write)
    recovered = store.reconcile_interrupted_artifact(
        "bo-cycle-publish-cut",
        expected_kind="battle_outcome_cycle",
    )

    assert recovered.disposition == "published_failed"
    assert recovered.reason_code == "publication_failed"
    failed = root / "bo-cycle-publish-cut.failed.partial"
    assert failed.is_dir()
    assert (failed / "manifest.unpublished.json").is_file()
    assert not (failed / private_artifacts_module._TYPED_ARTIFACT_IDENTITY).exists()
    repeated = store.reconcile_interrupted_artifact(
        "bo-cycle-publish-cut",
        expected_kind="battle_outcome_cycle",
    )
    assert repeated.disposition == "already_failed"
    reader = store.open_failed_artifact(
        "bo-cycle-publish-cut",
        expected_kind="battle_outcome_cycle",
    )
    assert tuple(reader.iter_stream("claims", max_records=1)) == (
        {"claim_id": "candidate-0"},
    )


def test_reconciliation_refuses_an_artifact_with_an_active_writer(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-active", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "candidate-0"}, durable=True)

    with pytest.raises(PrivateArtifactError, match="still active") as raised:
        store.reconcile_interrupted_artifact(
            "bo-cycle-active",
            expected_kind="battle_outcome_cycle",
        )

    assert str(tmp_path) not in str(raised.value)
    assert (root / "bo-cycle-active.partial").is_dir()
    assert not (root / "bo-cycle-active.failed.partial").exists()
    writer.abort("test_cleanup")


def test_reconciliation_cannot_relabel_an_orphaned_artifact(tmp_path: Path) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-kind", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "candidate-0"}, durable=True)
    _orphan(writer)

    with pytest.raises(PrivateArtifactError, match="identity seal does not match"):
        store.reconcile_interrupted_artifact(
            "bo-cycle-kind",
            expected_kind="unrelated_kind",
        )

    partial = root / "bo-cycle-kind.partial"
    assert partial.is_dir()
    assert not (partial / "manifest.json").exists()
    recovered = store.reconcile_interrupted_artifact(
        "bo-cycle-kind",
        expected_kind="battle_outcome_cycle",
    )
    assert recovered.summary.kind == "battle_outcome_cycle"


def test_reconciliation_publishes_a_valid_complete_manifest_left_under_partial(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-sealed", kind="battle_outcome_cycle")
    writer.append("receipt", {"status": "complete"}, durable=True)
    expected = writer._finalize(status="complete", reason_code=None)
    writer._release_lock()

    recovered = store.reconcile_interrupted_artifact(
        "bo-cycle-sealed",
        expected_kind="battle_outcome_cycle",
    )

    assert recovered.disposition == "published_complete"
    assert recovered.reason_code is None
    assert recovered.summary == expected
    assert (root / "bo-cycle-sealed").is_dir()
    assert not (root / "bo-cycle-sealed.partial").exists()
    reader = store.open_artifact(
        "bo-cycle-sealed",
        expected_kind="battle_outcome_cycle",
    )
    assert tuple(reader.iter_stream("receipt", max_records=1)) == (
        {"status": "complete"},
    )


@pytest.mark.parametrize("unsafe", ["symlink", "permissions", "path_record"])
def test_reconciliation_rejects_unsafe_partial_streams_without_sealing(
    tmp_path: Path,
    unsafe: str,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-unsafe", kind="battle_outcome_cycle")
    _orphan(writer)
    partial = root / "bo-cycle-unsafe.partial"
    stream = partial / "claims.jsonl"
    if unsafe == "symlink":
        target = tmp_path / "target"
        target.write_text('{"claim_id":"outside"}\n', encoding="ascii")
        stream.symlink_to(target)
    else:
        stream.write_text(
            (
                '{"claim_id":"candidate-0"}\n'
                if unsafe == "permissions"
                else '{"source":"/private/claim.json"}\n'
            ),
            encoding="ascii",
        )
        stream.chmod(0o644 if unsafe == "permissions" else 0o600)

    with pytest.raises(PrivateArtifactError) as raised:
        store.reconcile_interrupted_artifact(
            "bo-cycle-unsafe",
            expected_kind="battle_outcome_cycle",
        )

    assert str(tmp_path) not in str(raised.value)
    assert partial.is_dir()
    assert not (partial / "manifest.json").exists()
    assert not (root / "bo-cycle-unsafe.failed.partial").exists()


def test_reconciliation_enforces_stream_count_bound(tmp_path: Path) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-wide", kind="battle_outcome_cycle")
    _orphan(writer)
    partial = root / "bo-cycle-wide.partial"
    for index in range(65):
        stream = partial / f"s{index:02d}.jsonl"
        stream.write_bytes(b"")
        stream.chmod(0o600)

    with pytest.raises(PrivateArtifactError, match="stream bound"):
        store.reconcile_interrupted_artifact(
            "bo-cycle-wide",
            expected_kind="battle_outcome_cycle",
        )

    assert not (partial / "manifest.json").exists()


def test_reconciliation_requires_current_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-owner", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "candidate-0"}, durable=True)
    _orphan(writer)
    real_uid = os.getuid()
    monkeypatch.setattr(private_artifacts_module.os, "getuid", lambda: real_uid + 1)

    with pytest.raises(PrivateArtifactError, match="owner is unsafe") as raised:
        store.reconcile_interrupted_artifact(
            "bo-cycle-owner",
            expected_kind="battle_outcome_cycle",
        )

    assert str(tmp_path) not in str(raised.value)
    assert stat.S_IMODE((root / "bo-cycle-owner.partial").stat().st_mode) == 0o700


def test_reconciliation_fails_closed_on_identity_and_namespace_collisions(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("bo-cycle-collision", kind="battle_outcome_cycle")
    writer.append("claims", {"claim_id": "candidate-0"}, durable=True)
    _orphan(writer)
    (root / "bo-cycle-collision.failed.partial").mkdir(mode=0o700)

    with pytest.raises(PrivateArtifactError, match="ambiguous"):
        store.reconcile_interrupted_artifact(
            "bo-cycle-collision",
            expected_kind="battle_outcome_cycle",
        )

    assert not (root / "bo-cycle-collision.partial" / "manifest.json").exists()


def test_valid_sealed_record_collision_never_becomes_a_readable_typed_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    real_rename = private_artifacts_module._rename_no_replace
    interleaved = False

    def interleave_supported_publications(source: Path, destination: Path) -> None:
        nonlocal interleaved
        if destination == root / "same-id" and ".sealed-" in source.name:
            interleaved = True
            writer = store.begin_artifact("same-id", kind="battle_outcome_cycle")
            writer.append("claims", {"claim_id": "candidate-0"}, durable=True)
            writer.abort("publication_interleaving")
        real_rename(source, destination)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        interleave_supported_publications,
    )
    sealed = store.publish_sealed_record(
        "same-id",
        kind="summary",
        record={"status": "complete"},
    )

    assert interleaved is True
    assert sealed.read() == {"status": "complete"}
    assert store.find_sealed_record("same-id", expected_kind="summary") is not None
    with pytest.raises(PrivateArtifactError, match="ambiguous"):
        store.reconcile_interrupted_artifact(
            "same-id",
            expected_kind="battle_outcome_cycle",
        )
    with pytest.raises(PrivateArtifactError, match="ambiguous"):
        store.open_failed_artifact(
            "same-id",
            expected_kind="battle_outcome_cycle",
        )
