from __future__ import annotations

import hashlib
import json
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
