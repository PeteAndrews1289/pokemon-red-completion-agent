from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from pokemon_red_completion import private_artifacts as private_artifacts_module
from pokemon_red_completion.private_artifacts import (
    PRIVATE_ROOT_SENTINEL,
    PrivateArtifactError,
    initialize_private_root,
    open_private_root,
)
from pokemon_red_completion.runtime_identity import (
    PYBOY_INVENTORY_SCHEMA,
    RUNTIME_IDENTITY_SCHEMA,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    parse_strategic_navigation_registry,
)


def _separate_devices(root: Path, repository: Path):
    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return {
        "repository_root": repository,
        "device_id": device_id,
        "git_worktree_probe": lambda path: False,
    }


def _make_store(tmp_path: Path):
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()
    store = initialize_private_root(root, **_separate_devices(root, repository))
    return root, repository, store


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_episode_writer_can_sync_a_record_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, store = _make_store(tmp_path)
    writer = store.begin_episode("durable-record-before-action")
    synchronized: list[int] = []
    monkeypatch.setattr(
        private_artifacts_module.os,
        "fsync",
        lambda descriptor: synchronized.append(descriptor),
    )

    writer.append("decisions", {"kind": "goal"}, durable=True)

    assert len(synchronized) == 2
    writer.abort("identity_probe")


def test_strategic_assignments_fit_the_private_episode_namespace(tmp_path: Path) -> None:
    _, _, store = _make_store(tmp_path)
    project_root = Path(__file__).resolve().parents[1]
    registry = parse_strategic_navigation_registry(
        (project_root / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    assignments = (
        registry.assignment("red-strategic-v1-01-train"),
        registry.rehearsal_assignment(),
    )

    for assignment in assignments:
        writer = store.begin_episode(assignment.episode_id)
        summary = writer.abort("identity_probe")
        assert summary.status == "failed"


def _episode_header_with_runtime_name(name: str) -> dict[str, object]:
    files = [
        {
            "name": name,
            "bytes": 7,
            "sha256": "a" * 64,
        }
    ]
    inventory = {
        "schema": PYBOY_INVENTORY_SCHEMA,
        "distribution_name": "pyboy",
        "distribution_version": "2.7.0",
        "files": files,
    }
    inventory_sha256 = hashlib.sha256(
        (
            json.dumps(
                inventory,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
    ).hexdigest()
    return {
        "record_type": "episode",
        "trajectory_schema": "pokemon.trajectory.v1",
        "episode_id": "episode-runtime",
        "game_id": "pokemon.mainline:red",
        "metadata": {
            "runtime": {
                "schema": RUNTIME_IDENTITY_SCHEMA,
                "python": {
                    "implementation": "CPython",
                    "version": "3.14.3",
                    "executable_sha256": "b" * 64,
                },
                "pyboy": {
                    "distribution_name": "pyboy",
                    "distribution_version": "2.7.0",
                    "files": files,
                    "inventory_sha256": inventory_sha256,
                },
            }
        },
    }


def test_initialization_requires_an_explicit_existing_root(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    missing = tmp_path / "missing"

    with pytest.raises(PrivateArtifactError, match="already exist"):
        initialize_private_root(
            missing,
            repository_root=repository,
            device_id=lambda path: 2,
            git_worktree_probe=lambda path: False,
        )

    assert not missing.exists()
    with pytest.raises(PrivateArtifactError, match="explicit absolute"):
        initialize_private_root(
            Path("relative-private-root"),
            repository_root=repository,
            device_id=lambda path: 2,
            git_worktree_probe=lambda path: False,
        )


def test_initialization_rejects_repository_and_git_worktree_locations(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    nested = repository / "private"
    nested.mkdir()

    with pytest.raises(PrivateArtifactError, match="outside the repository"):
        initialize_private_root(
            nested,
            repository_root=repository,
            allow_same_device=True,
            git_worktree_probe=lambda path: False,
        )

    other = tmp_path / "worktree"
    other.mkdir()
    with pytest.raises(PrivateArtifactError, match="Git worktree"):
        initialize_private_root(
            other,
            repository_root=repository,
            allow_same_device=True,
            git_worktree_probe=lambda path: True,
        )


def test_initialization_defaults_to_a_separate_storage_device(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()
    seen: list[Path] = []

    def same_device(path: Path) -> int:
        seen.append(path)
        return 7

    with pytest.raises(PrivateArtifactError, match="different storage device"):
        initialize_private_root(
            root,
            repository_root=repository,
            device_id=same_device,
            git_worktree_probe=lambda path: False,
        )

    assert set(seen) == {root.resolve(), repository.resolve()}
    store = initialize_private_root(
        root,
        repository_root=repository,
        allow_same_device=True,
        device_id=lambda path: 7,
        git_worktree_probe=lambda path: False,
    )
    assert repr(store) == "PrivateArtifactRoot(validated=True)"


def test_initialization_rejects_symlink_components(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    actual = tmp_path / "actual"
    repository.mkdir()
    actual.mkdir()
    link = tmp_path / "linked-private"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(PrivateArtifactError, match="symbolic-link"):
        initialize_private_root(
            link,
            repository_root=repository,
            allow_same_device=True,
            git_worktree_probe=lambda path: False,
        )


def test_open_fails_closed_for_an_absent_or_tampered_sentinel(tmp_path: Path) -> None:
    root, repository, _ = _make_store(tmp_path)
    arguments = _separate_devices(root, repository)
    sentinel = root / PRIVATE_ROOT_SENTINEL
    expected = sentinel.read_bytes()

    sentinel.unlink()
    with pytest.raises(PrivateArtifactError, match="sentinel is absent"):
        open_private_root(root, **arguments)

    sentinel.write_bytes(expected + b"tampered")
    with pytest.raises(PrivateArtifactError, match="failed validation"):
        open_private_root(root, **arguments)
    with pytest.raises(PrivateArtifactError, match="failed validation"):
        initialize_private_root(root, **arguments)
    assert sentinel.read_bytes() == expected + b"tampered"


def test_episode_is_canonical_private_and_manifest_verified(tmp_path: Path) -> None:
    root, _, store = _make_store(tmp_path)
    writer = store.begin_episode("episode-001")
    with writer:
        writer.append(
            "observations",
            {"step": 0, "state": {"map": "bedroom", "position": [3, 5]}},
        )
        writer.append("observations", {"state": {"map": "hall_of_fame"}, "step": 1})
        writer.append("actions", {"action": "interact", "step": 0})

    final = root / "episode-001"
    assert final.is_dir()
    assert not (root / "episode-001.partial").exists()
    assert _mode(final) == 0o700
    for filename in ("observations.jsonl", "actions.jsonl", "manifest.json"):
        assert _mode(final / filename) == 0o600

    observations = (final / "observations.jsonl").read_bytes()
    assert observations == (
        b'{"state":{"map":"bedroom","position":[3,5]},"step":0}\n'
        b'{"state":{"map":"hall_of_fame"},"step":1}\n'
    )
    manifest = json.loads((final / "manifest.json").read_text(encoding="ascii"))
    files = {item["filename"]: item for item in manifest["files"]}
    assert manifest["status"] == "complete"
    assert manifest["totals"]["records"] == 3
    assert set(files) == {"actions.jsonl", "observations.jsonl"}
    assert files["observations.jsonl"]["sha256"] == hashlib.sha256(observations).hexdigest()
    assert all(
        "/" not in item["filename"] and "\\" not in item["filename"] for item in files.values()
    )

    summary = writer.summary.public_dict()
    assert summary["status"] == "complete"
    assert summary["stream_records"] == {"actions": 1, "observations": 2}
    assert summary["total_records"] == 3
    assert str(tmp_path) not in json.dumps(summary)
    assert all(
        forbidden not in json.dumps(summary).casefold()
        for forbidden in ("path", "filename", "directory")
    )


def test_episode_never_overwrites_a_final_or_partial_artifact(tmp_path: Path) -> None:
    root, _, store = _make_store(tmp_path)
    with store.begin_episode("fixed-id") as writer:
        writer.append("actions", {"step": 1})
    original = (root / "fixed-id" / "actions.jsonl").read_bytes()

    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_episode("fixed-id")
    assert (root / "fixed-id" / "actions.jsonl").read_bytes() == original

    (root / "occupied.partial").mkdir()
    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_episode("occupied")


def test_begin_episode_durably_claims_the_partial_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    synchronized: list[Path] = []
    monkeypatch.setattr(
        private_artifacts_module,
        "_fsync_directory",
        lambda path: synchronized.append(path),
    )

    writer = store.begin_episode("durable-claim")

    partial = root / "durable-claim.partial"
    assert partial.is_dir()
    assert synchronized == [partial, root]
    writer.abort("test_cleanup")


def test_begin_episode_sync_failure_retains_a_path_free_consumed_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    partial = root / "failed-durable-claim.partial"
    synchronized: list[Path] = []

    def fail_parent_sync(path: Path) -> None:
        synchronized.append(path)
        if path == root:
            raise PrivateArtifactError(f"cannot synchronize private location {path}")

    monkeypatch.setattr(
        private_artifacts_module,
        "_fsync_directory",
        fail_parent_sync,
    )

    with pytest.raises(
        PrivateArtifactError,
        match="unable to durably claim the private episode",
    ) as raised:
        store.begin_episode("failed-durable-claim")

    assert synchronized == [partial, root]
    assert str(tmp_path) not in str(raised.value)
    assert store.inspect_episode_state("failed-durable-claim").status == "partial"
    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_episode("failed-durable-claim")


def test_atomic_no_replace_rename_preserves_an_existing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "source-marker").write_text("source", encoding="ascii")
    (destination / "destination-marker").write_text("destination", encoding="ascii")

    with pytest.raises(OSError):
        private_artifacts_module._rename_no_replace(source, destination)

    assert (source / "source-marker").read_text(encoding="ascii") == "source"
    assert (destination / "destination-marker").read_text(encoding="ascii") == "destination"


def test_atomic_no_replace_rename_preserves_an_empty_destination_inode(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    (source / "source-marker").write_text("source", encoding="ascii")
    source_inode = source.stat().st_ino
    destination_inode = destination.stat().st_ino

    with pytest.raises(OSError):
        private_artifacts_module._rename_no_replace(source, destination)

    assert source.stat().st_ino == source_inode
    assert (source / "source-marker").read_text(encoding="ascii") == "source"
    assert destination.stat().st_ino == destination_inode
    assert list(destination.iterdir()) == []


def test_atomic_no_replace_rename_fails_closed_on_an_unsupported_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    monkeypatch.setattr(private_artifacts_module.sys, "platform", "unsupported")

    with pytest.raises(OSError, match="unsupported"):
        private_artifacts_module._rename_no_replace(source, destination)

    assert source.is_dir()
    assert not destination.exists()


def test_episode_existing_final_is_detected_before_complete_manifest_sealing(
    tmp_path: Path,
) -> None:
    root, _, store = _make_store(tmp_path)
    writer = store.begin_episode("late-collision")
    writer.append("actions", {"step": 0})
    destination = root / "late-collision"
    destination.mkdir()
    (destination / "marker").write_text("untouched", encoding="ascii")

    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        writer.complete()

    assert (destination / "marker").read_text(encoding="ascii") == "untouched"
    assert not (root / "late-collision.partial" / "manifest.json").exists()
    writer.abort("test_cleanup")


def test_episode_atomic_publish_race_preserves_destination_and_retains_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    writer = store.begin_episode("publish-race")
    writer.append("actions", {"step": 0})
    real_rename = private_artifacts_module._rename_no_replace
    destination = root / "publish-race"

    def collide_at_publication(source: Path, target: Path) -> None:
        if target == destination:
            target.mkdir()
            (target / "marker").write_text("untouched", encoding="ascii")
        real_rename(source, target)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        collide_at_publication,
    )
    with pytest.raises(PrivateArtifactError, match="unable to publish"):
        writer.complete()

    assert (destination / "marker").read_text(encoding="ascii") == "untouched"
    assert not (root / "publish-race.partial").exists()
    failed = root / "publish-race.failed.partial"
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    unpublished = json.loads((failed / "manifest.unpublished.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "publication_failed"
    assert unpublished["status"] == "complete"


def test_episode_atomic_publish_race_preserves_an_empty_destination_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    writer = store.begin_episode("empty-publish-race")
    writer.append("actions", {"step": 0})
    real_rename = private_artifacts_module._rename_no_replace
    destination = root / "empty-publish-race"
    destination_inodes: list[int] = []

    def collide_with_empty_destination(source: Path, target: Path) -> None:
        if target == destination:
            target.mkdir()
            destination_inodes.append(target.stat().st_ino)
        real_rename(source, target)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        collide_with_empty_destination,
    )
    with pytest.raises(PrivateArtifactError, match="unable to publish"):
        writer.complete()

    assert len(destination_inodes) == 1
    assert destination.stat().st_ino == destination_inodes[0]
    assert list(destination.iterdir()) == []
    assert not (root / "empty-publish-race.partial").exists()
    failed = root / "empty-publish-race.failed.partial"
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "publication_failed"


def test_episode_atomic_failed_publish_race_preserves_destination_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    writer = store.begin_episode("failed-race")
    writer.append("actions", {"step": 0})
    real_rename = private_artifacts_module._rename_no_replace
    destination = root / "failed-race.failed.partial"

    def collide_at_failed_publication(source: Path, target: Path) -> None:
        if target == destination:
            target.mkdir()
            (target / "marker").write_text("untouched", encoding="ascii")
        real_rename(source, target)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        collide_at_failed_publication,
    )
    with pytest.raises(PrivateArtifactError, match="unable to retain"):
        writer.abort("test_failure")

    assert (destination / "marker").read_text(encoding="ascii") == "untouched"
    partial = root / "failed-race.partial"
    manifest = json.loads((partial / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "test_failure"
    assert writer.summary.status == "failed"


@pytest.mark.parametrize(
    "record",
    [
        {"path": "checkpoint.state"},
        {"value": Path("checkpoint.state")},
        {"value": "nested/checkpoint.state"},
        {"value": "C:\\private\\checkpoint.state"},
        {"value": float("nan")},
        {"value": b"not-json"},
    ],
)
def test_episode_records_reject_paths_and_non_json_values(
    tmp_path: Path,
    record: dict[str, object],
) -> None:
    root, _, store = _make_store(tmp_path)

    with pytest.raises(PrivateArtifactError), store.begin_episode("rejected") as writer:
        writer.append("observations", record)

    failed = root / "rejected.failed.partial"
    assert failed.is_dir()
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "unhandled_exception"


def test_failure_retains_sanitized_explicit_partial_artifact(tmp_path: Path) -> None:
    root, _, store = _make_store(tmp_path)
    sensitive_exception = "could not read /Users/example/private/game.state"

    with (
        pytest.raises(RuntimeError, match="could not read"),
        store.begin_episode("failed-run") as writer,
    ):
        writer.append("actions", {"action": "start", "step": 0})
        raise RuntimeError(sensitive_exception)

    assert not (root / "failed-run").exists()
    assert not (root / "failed-run.partial").exists()
    failed = root / "failed-run.failed.partial"
    assert failed.is_dir()
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "unhandled_exception"
    artifact_text = b"".join(
        path.read_bytes() for path in failed.iterdir() if path.is_file()
    ).decode("ascii")
    assert sensitive_exception not in artifact_text
    assert "/Users/" not in artifact_text
    assert _mode(failed) == 0o700
    assert all(_mode(path) == 0o600 for path in failed.iterdir() if path.is_file())


def test_existing_store_rechecks_its_sentinel_before_each_episode(tmp_path: Path) -> None:
    root, _, store = _make_store(tmp_path)
    (root / PRIVATE_ROOT_SENTINEL).write_text("not the sentinel", encoding="ascii")

    with pytest.raises(PrivateArtifactError, match="failed validation"):
        store.begin_episode("must-not-start")
    assert not (root / "must-not-start.partial").exists()


def test_stream_stat_failure_is_wrapped_without_disclosing_its_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    writer = store.begin_episode("stat-failure")
    writer.append("actions", {"action": "start", "step": 0})
    real_stat = Path.stat

    def fail_stream_stat(path: Path, *args, **kwargs):
        if path.name == "actions.jsonl":
            raise OSError(f"cannot inspect sensitive location {path}")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_stream_stat)
    with pytest.raises(
        PrivateArtifactError,
        match="unable to inspect a private episode stream",
    ) as raised:
        writer.complete()

    assert str(tmp_path) not in str(raised.value)
    assert (root / "stat-failure.partial").is_dir()
    assert not (root / "stat-failure.partial" / "manifest.json").exists()


def test_publish_rename_failure_becomes_an_explicit_failed_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    writer = store.begin_episode("publish-failure")
    writer.append("actions", {"action": "start", "step": 0})
    real_rename = private_artifacts_module._rename_no_replace

    def fail_completed_publish(source, destination, *args, **kwargs):
        if (
            Path(source).name == "publish-failure.partial"
            and Path(destination).name == "publish-failure"
        ):
            raise OSError(f"cannot rename private location {source}")
        return real_rename(source, destination, *args, **kwargs)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        fail_completed_publish,
    )
    with (
        pytest.raises(
            PrivateArtifactError,
            match="unable to publish the completed private episode",
        ) as raised,
        writer,
    ):
        pass

    assert str(tmp_path) not in str(raised.value)
    assert not (root / "publish-failure").exists()
    assert not (root / "publish-failure.partial").exists()
    failed = root / "publish-failure.failed.partial"
    assert failed.is_dir()
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "publication_failed"
    unpublished = json.loads((failed / "manifest.unpublished.json").read_text(encoding="ascii"))
    assert unpublished["status"] == "complete"
    assert writer.summary.status == "failed"


def test_episode_directory_renames_are_synchronized_at_the_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    synchronized: list[Path] = []
    monkeypatch.setattr(
        private_artifacts_module,
        "_fsync_directory",
        lambda path: synchronized.append(path),
    )

    with store.begin_episode("complete-sync") as writer:
        writer.append("actions", {"step": 0})
    assert synchronized[-1] == root

    synchronized.clear()
    writer = store.begin_episode("failed-sync")
    writer.append("actions", {"step": 0})
    writer.abort("test_failure")
    assert synchronized[-1] == root


def test_collection_session_is_exclusive_and_releases_without_storing_a_path(
    tmp_path: Path,
) -> None:
    root, _, store = _make_store(tmp_path)
    first = store.collection_session("red-battle-heldout-v1")
    second = store.collection_session("red-battle-heldout-v1")

    with first:
        assert first.active
        assert str(root) not in repr(first)
        with pytest.raises(PrivateArtifactError, match="already active"), second:
            pass

    assert not first.active
    with store.collection_session("red-battle-heldout-v1") as reopened:
        assert reopened.active


def test_episode_runtime_inventory_exception_requires_exact_header_envelope(
    tmp_path: Path,
) -> None:
    _, _, store = _make_store(tmp_path)
    valid = _episode_header_with_runtime_name("pyboy/runtime.py")
    cases = (
        ("events", valid),
        (
            "episode",
            {
                **valid,
                "trajectory_schema": "unexpected.trajectory.v1",
            },
        ),
        (
            "episode",
            {
                **valid,
                "unexpected": True,
            },
        ),
        (
            "episode",
            {
                **valid,
                "metadata": {
                    "runtime.pyboy.files[0].name": "pyboy/runtime.py",
                },
            },
        ),
    )

    for index, (stream, record) in enumerate(cases):
        writer = store.begin_episode(f"episode-envelope-{index}")
        with pytest.raises(PrivateArtifactError, match="filesystem path"):
            writer.append(stream, record)
        writer.abort("expected_failure")


def test_sealed_record_is_canonical_private_idempotent_and_immutable(
    tmp_path: Path,
) -> None:
    root, _, store = _make_store(tmp_path)
    record = {
        "schema": "collection-seal-test-v1",
        "collection_id": "red-battle-heldout-v1",
        "registry_sha256": "a" * 64,
    }

    first = store.publish_sealed_record(
        "seal-" + "b" * 64,
        kind="collection_seal",
        record=record,
    )
    repeated = store.publish_sealed_record(
        "seal-" + "b" * 64,
        kind="collection_seal",
        record=record,
    )

    assert first.read() == record
    changed = first.read()
    changed["collection_id"] = "changed"
    assert first.read() == record
    assert repeated.summary == first.summary
    directory = root / ("seal-" + "b" * 64)
    assert _mode(directory) == 0o700
    assert _mode(directory / "manifest.json") == 0o600
    assert _mode(directory / "record.json") == 0o600
    assert (directory / "record.json").read_bytes() == (
        json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )
    assert str(root) not in json.dumps(first.summary.public_dict())

    with pytest.raises(PrivateArtifactError, match="different content"):
        store.publish_sealed_record(
            "seal-" + "b" * 64,
            kind="collection_seal",
            record={**record, "registry_sha256": "c" * 64},
        )
    assert (
        store.find_sealed_record(
            "seal-" + "b" * 64,
            expected_kind="collection_seal",
        ).read()
        == record
    )


def test_sealed_record_metadata_inspection_never_opens_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    record_id = "metadata-only-" + "a" * 64
    published = store.publish_sealed_record(
        record_id,
        kind="collection_seal",
        record={"schema": "metadata-only-test-v1", "commitment": "b" * 64},
    )
    read_entry = private_artifacts_module._read_private_entry
    open_file = private_artifacts_module.os.open
    opened_entries: list[str] = []

    def reject_payload_open(
        directory_descriptor: int,
        filename: str,
        *,
        subject: str,
        maximum_bytes: int,
        expected_bytes: int | None = None,
    ) -> bytes:
        opened_entries.append(filename)
        if filename == "record.json":
            raise AssertionError("metadata inspection opened the sealed payload")
        return read_entry(
            directory_descriptor,
            filename,
            subject=subject,
            maximum_bytes=maximum_bytes,
            expected_bytes=expected_bytes,
        )

    monkeypatch.setattr(private_artifacts_module, "_read_private_entry", reject_payload_open)

    def reject_payload_descriptor(path, flags, *arguments, **keywords):
        if str(path) == "record.json":
            raise AssertionError("metadata inspection opened a payload descriptor")
        return open_file(path, flags, *arguments, **keywords)

    monkeypatch.setattr(private_artifacts_module.os, "open", reject_payload_descriptor)

    metadata = store.inspect_sealed_record_metadata(
        record_id,
        expected_kind="collection_seal",
    )

    assert metadata is not None
    assert opened_entries == ["manifest.json"]
    assert metadata.declared_record_sha256 == published.summary.record_sha256
    assert metadata.manifest_sha256 == published.summary.manifest_sha256
    assert metadata.declared_total_bytes == published.summary.total_bytes
    assert metadata.public_dict()["payload_integrity_verified"] is False
    assert metadata.public_dict()["payload_opened"] is False
    assert str(root) not in json.dumps(metadata.public_dict())


def test_sealed_record_inventory_is_stable_bounded_and_manifest_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    first_id = "family-" + "a" * 64
    second_id = "family-" + "b" * 64
    for record_id in (second_id, first_id):
        store.publish_sealed_record(
            record_id,
            kind="collection_seal",
            record={"schema": "inventory-test-v1", "record_id": record_id},
        )
    store.publish_sealed_record(
        "other-" + "c" * 64,
        kind="collection_seal",
        record={"schema": "inventory-test-v1", "record_id": "other"},
    )
    read_entry = private_artifacts_module._read_private_entry

    def reject_payload_open(
        directory_descriptor: int,
        filename: str,
        *,
        subject: str,
        maximum_bytes: int,
        expected_bytes: int | None = None,
    ) -> bytes:
        if filename == "record.json":
            raise AssertionError("inventory opened a sealed payload")
        return read_entry(
            directory_descriptor,
            filename,
            subject=subject,
            maximum_bytes=maximum_bytes,
            expected_bytes=expected_bytes,
        )

    monkeypatch.setattr(private_artifacts_module, "_read_private_entry", reject_payload_open)

    inventory = store.inventory_sealed_record_metadata(
        record_id_prefix="family-",
        expected_kind="collection_seal",
        maximum_records=2,
    )

    assert tuple(row.record_id for row in inventory) == (first_id, second_id)
    assert all(row.kind == "collection_seal" for row in inventory)
    assert str(root) not in json.dumps([row.public_dict() for row in inventory])
    with pytest.raises(PrivateArtifactError, match="exceeds"):
        store.inventory_sealed_record_metadata(
            record_id_prefix="family-",
            expected_kind="collection_seal",
            maximum_records=1,
        )


def test_sealed_record_inventory_rejects_malformed_family_and_census_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    record_id = "family-" + "d" * 64
    store.publish_sealed_record(
        record_id,
        kind="collection_seal",
        record={"schema": "inventory-race-test-v1"},
    )
    malformed = root / "family-not-a-digest"
    malformed.mkdir(mode=0o700)
    with pytest.raises(PrivateArtifactError, match="family is malformed"):
        store.inventory_sealed_record_metadata(
            record_id_prefix="family-",
            expected_kind="collection_seal",
            maximum_records=2,
        )
    malformed.rmdir()

    inventory = private_artifacts_module._inventory_digest_record_ids
    calls = 0

    def changed(root_path: Path, prefix: str) -> tuple[str, ...]:
        nonlocal calls
        calls += 1
        original = inventory(root_path, prefix)
        if calls == 2:
            return (*original, "family-" + "e" * 64)
        return original

    monkeypatch.setattr(
        private_artifacts_module,
        "_inventory_digest_record_ids",
        changed,
    )
    with pytest.raises(PrivateArtifactError, match="changed during inspection"):
        store.inventory_sealed_record_metadata(
            record_id_prefix="family-",
            expected_kind="collection_seal",
            maximum_records=2,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "symlink",
        "hardlink",
        "mode",
        "size",
        "payload_swap",
        "directory_swap",
        "manifest",
    ),
)
def test_sealed_record_metadata_inspection_rejects_unsafe_or_changed_payload_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root, _, store = _make_store(tmp_path)
    record_id = "metadata-mutation-" + "c" * 60
    store.publish_sealed_record(
        record_id,
        kind="collection_seal",
        record={"schema": "metadata-mutation-test-v1", "commitment": "d" * 64},
    )
    record_directory = root / record_id
    payload_path = record_directory / "record.json"
    payload = payload_path.read_bytes()
    if mutation == "symlink":
        payload_path.unlink()
        payload_path.symlink_to(record_directory / "manifest.json")
    elif mutation == "hardlink":
        os.link(payload_path, root / "metadata-payload-hardlink")
    elif mutation == "mode":
        payload_path.chmod(0o640)
    elif mutation == "size":
        payload_path.write_bytes(payload + b"x")
        payload_path.chmod(0o600)
    elif mutation == "manifest":
        manifest_path = record_directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        manifest["schema_version"] = True
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="ascii",
        )
        manifest_path.chmod(0o600)
    elif mutation == "payload_swap":
        entry_metadata = private_artifacts_module._entry_metadata
        payload_checks = 0

        def swap_before_second_check(
            directory_descriptor: int,
            filename: str,
        ) -> os.stat_result | None:
            nonlocal payload_checks
            if filename == "record.json":
                payload_checks += 1
                if payload_checks == 2:
                    replacement = record_directory / "replacement.tmp"
                    replacement.write_bytes(payload)
                    replacement.chmod(0o600)
                    os.replace(replacement, payload_path)
            return entry_metadata(directory_descriptor, filename)

        monkeypatch.setattr(
            private_artifacts_module,
            "_entry_metadata",
            swap_before_second_check,
        )
    else:
        entry_metadata = private_artifacts_module._entry_metadata
        directory_checks = 0

        def swap_directory_before_final_check(
            directory_descriptor: int,
            filename: str,
        ) -> os.stat_result | None:
            nonlocal directory_checks
            if filename == record_id:
                directory_checks += 1
                if directory_checks == 2:
                    record_directory.rename(root / "metadata-directory-swapped-away")
                    record_directory.mkdir(mode=0o700)
            return entry_metadata(directory_descriptor, filename)

        monkeypatch.setattr(
            private_artifacts_module,
            "_entry_metadata",
            swap_directory_before_final_check,
        )

    with pytest.raises(PrivateArtifactError):
        store.inspect_sealed_record_metadata(
            record_id,
            expected_kind="collection_seal",
        )


def test_sealed_record_rejects_path_content_and_recovers_after_a_stale_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, store = _make_store(tmp_path)
    record_id = "outcome-" + "d" * 64
    with pytest.raises(PrivateArtifactError, match="filesystem path"):
        store.publish_sealed_record(
            record_id,
            kind="collection_outcome",
            record={"private_path": str(root)},
        )
    with pytest.raises(PrivateArtifactError, match="filesystem path"):
        store.publish_sealed_record(
            record_id,
            kind="collection_outcome",
            record={"logical_name": "pyboy/runtime.py"},
        )

    real_rename = private_artifacts_module._rename_no_replace

    def interrupt_publish(source: Path, destination: Path) -> None:
        if destination.name == record_id:
            raise OSError("simulated power loss")
        real_rename(source, destination)

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        interrupt_publish,
    )
    with pytest.raises(PrivateArtifactError, match="unable to publish"):
        store.publish_sealed_record(
            record_id,
            kind="collection_outcome",
            record={"schema": "outcome-test-v1", "status": "failed"},
        )
    assert store.find_sealed_record(record_id) is None
    assert any(entry.name.startswith(f".{record_id}.sealed-") for entry in root.iterdir())

    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        real_rename,
    )
    published = store.publish_sealed_record(
        record_id,
        kind="collection_outcome",
        record={"schema": "outcome-test-v1", "status": "failed"},
    )
    assert published.read()["status"] == "failed"


def test_orphan_partial_is_permanently_classified_as_interrupted(
    tmp_path: Path,
) -> None:
    root, _, store = _make_store(tmp_path)
    store.begin_episode("planned-power-loss")

    assert store.inspect_episode_state("planned-power-loss").status == "partial"
    with store.collection_session("red-battle-heldout-v1") as session:
        recovered = session.recover_interrupted_episode("planned-power-loss")

    assert recovered.status == "interrupted"
    assert recovered.reason_code == "process_interrupted"
    assert not (root / "planned-power-loss.partial").exists()
    assert (root / "planned-power-loss.interrupted.partial").is_dir()
    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_episode("planned-power-loss")
    with pytest.raises(PrivateArtifactError, match="interrupted"):
        store.open_episode("planned-power-loss")


def test_recovery_promotes_sealed_complete_and_failed_partial_directories(
    tmp_path: Path,
) -> None:
    root, _, store = _make_store(tmp_path)
    with store.begin_episode("sealed-complete") as writer:
        writer.append("events", {"kind": "terminal"})
    (root / "sealed-complete").rename(root / "sealed-complete.partial")

    failed_writer = store.begin_episode("sealed-failed")
    failed_writer.append("events", {"kind": "start"})
    failed_writer.abort("qualified_play_error")
    (root / "sealed-failed.failed.partial").rename(root / "sealed-failed.partial")

    with store.collection_session("red-battle-heldout-v1") as session:
        complete = session.recover_interrupted_episode("sealed-complete")
        failed = session.recover_interrupted_episode("sealed-failed")

    assert complete.status == "complete"
    assert complete.manifest_sha256 is not None
    assert (root / "sealed-complete").is_dir()
    assert store.open_episode("sealed-complete").summary.status == "complete"
    assert failed.status == "failed"
    assert failed.reason_code == "qualified_play_error"
    assert failed.manifest_sha256 is not None
    assert (root / "sealed-failed.failed.partial").is_dir()


@pytest.mark.parametrize(
    ("status", "reason_code"),
    (
        ("complete", None),
        ("failed", "test_failure"),
        ("interrupted", "process_interrupted"),
    ),
)
def test_recovery_reinspects_a_terminal_rename_after_parent_sync_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    reason_code: str | None,
) -> None:
    root, _, store = _make_store(tmp_path)
    episode_id = f"recovery-sync-{status}"
    if status == "complete":
        with store.begin_episode(episode_id) as writer:
            writer.append("events", {"kind": "terminal"})
        (root / episode_id).rename(root / f"{episode_id}.partial")
    elif status == "failed":
        writer = store.begin_episode(episode_id)
        writer.append("events", {"kind": "start"})
        writer.abort("test_failure")
        (root / f"{episode_id}.failed.partial").rename(root / f"{episode_id}.partial")
    else:
        store.begin_episode(episode_id)

    real_sync = private_artifacts_module._fsync_directory
    synchronized: list[Path] = []

    def fail_recovery_sync(path: Path) -> None:
        synchronized.append(path)
        if path == root:
            raise PrivateArtifactError("simulated parent synchronization failure")
        real_sync(path)

    monkeypatch.setattr(
        private_artifacts_module,
        "_fsync_directory",
        fail_recovery_sync,
    )

    with store.collection_session("red-battle-heldout-v1") as session:
        recovered = session.recover_interrupted_episode(episode_id)

    assert synchronized == [root]
    assert recovered.status == status
    assert recovered.reason_code == reason_code
    assert store.inspect_episode_state(episode_id) == recovered


def test_recovery_leaves_a_retryable_partial_unclassified_after_rename_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, store = _make_store(tmp_path)
    episode_id = "retryable-recovery"
    store.begin_episode(episode_id)
    monkeypatch.setattr(
        private_artifacts_module,
        "_rename_no_replace",
        lambda source, destination: (_ for _ in ()).throw(OSError("simulated pre-rename failure")),
    )

    with (
        store.collection_session("red-battle-heldout-v1") as session,
        pytest.raises(
            PrivateArtifactError,
            match="unable to establish a stable recovered episode state",
        ),
    ):
        session.recover_interrupted_episode(episode_id)

    assert store.inspect_episode_state(episode_id).status == "partial"
