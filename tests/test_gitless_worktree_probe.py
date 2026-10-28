from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pokemon_red_completion import private_artifacts as artifacts


@pytest.fixture(autouse=True)
def isolated_git_environment(monkeypatch):
    for name in tuple(artifacts.os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)


def fallback(monkeypatch, value=True):
    calls = []

    def probe(path):
        calls.append(path)
        return value

    monkeypatch.setattr(artifacts, "_default_git_worktree_probe", probe)
    return calls


def test_plain_directory_is_reobserved_without_subprocess(tmp_path, monkeypatch):
    calls = fallback(monkeypatch)
    for _ in range(20):
        assert artifacts.gitless_fast_path_worktree_probe(tmp_path) is False
    assert calls == []


@pytest.mark.parametrize("name", [".git", "HEAD"])
@pytest.mark.parametrize("level", ["self", "parent"])
@pytest.mark.parametrize("form", ["file", "directory", "dangling_symlink"])
def test_any_potential_marker_keeps_original_git_authority(
    tmp_path, monkeypatch, name, level, form,
):
    root = tmp_path / "private"
    root.mkdir()
    marker = (root if level == "self" else tmp_path) / name
    if form == "file":
        marker.write_text("ambiguous marker")
    elif form == "directory":
        marker.mkdir()
    else:
        marker.symlink_to(tmp_path / "missing")
    calls = fallback(monkeypatch, value=False)
    assert artifacts.gitless_fast_path_worktree_probe(root) is False
    assert calls == [root]


def test_later_added_and_removed_marker_is_not_cached(tmp_path, monkeypatch):
    calls = fallback(monkeypatch)
    assert artifacts.gitless_fast_path_worktree_probe(tmp_path) is False
    marker = tmp_path / ".git"
    marker.mkdir()
    assert artifacts.gitless_fast_path_worktree_probe(tmp_path) is True
    marker.rmdir()
    assert artifacts.gitless_fast_path_worktree_probe(tmp_path) is False
    assert calls == [tmp_path]


@pytest.mark.parametrize("name", [
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_CONFIG_COUNT",
    "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_UNKNOWN_FUTURE",
])
def test_git_environment_overrides_fall_back(tmp_path, monkeypatch, name):
    calls = fallback(monkeypatch)
    monkeypatch.setenv(name, "1")
    assert artifacts.gitless_fast_path_worktree_probe(tmp_path) is True
    assert calls == [tmp_path]


def test_display_only_pager_does_not_change_discovery(tmp_path, monkeypatch):
    calls = fallback(monkeypatch)
    monkeypatch.setenv("GIT_PAGER", "cat")
    assert artifacts.gitless_fast_path_worktree_probe(tmp_path) is False
    assert calls == []


@pytest.mark.parametrize("form", ["relative", "missing", "file", "symlink"])
def test_unproved_directory_falls_back(tmp_path, monkeypatch, form):
    path = tmp_path / "private"
    if form == "relative":
        path = Path("relative-private")
    elif form == "file":
        path.write_text("not a directory")
    elif form == "symlink":
        path.symlink_to(tmp_path, target_is_directory=True)
    calls = fallback(monkeypatch)
    assert artifacts.gitless_fast_path_worktree_probe(path) is True
    assert calls == [path]


def test_marker_read_error_falls_back(tmp_path, monkeypatch):
    original = Path.lstat

    def read(path):
        if path == tmp_path / ".git":
            raise PermissionError("unreadable Git marker")
        return original(path)

    monkeypatch.setattr(Path, "lstat", read)
    calls = fallback(monkeypatch)
    assert artifacts.gitless_fast_path_worktree_probe(tmp_path) is True
    assert calls == [tmp_path]


def test_fallback_error_is_not_swallowed(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()

    def broken(_path):
        raise artifacts.PrivateArtifactError("original Git failure")

    monkeypatch.setattr(artifacts, "_default_git_worktree_probe", broken)
    with pytest.raises(artifacts.PrivateArtifactError, match="original Git failure"):
        artifacts.gitless_fast_path_worktree_probe(tmp_path)


@pytest.mark.parametrize(
    "form", ["plain", "worktree", "nested", "git_directory", "bare", "gitfile"],
)
def test_real_git_parity(tmp_path, form):
    root = tmp_path / "private"
    if form == "plain":
        root.mkdir()
    else:
        command = ["git", "init", "-q"]
        if form == "bare":
            command.append("--bare")
        elif form == "gitfile":
            command.append(f"--separate-git-dir={tmp_path / 'separate'}")
        subprocess.run([*command, str(root)], check=True, capture_output=True)
        if form == "nested":
            root = root / "nested"
            root.mkdir()
        elif form == "git_directory":
            root = root / ".git" / "objects"
    assert (
        artifacts.gitless_fast_path_worktree_probe(root)
        == artifacts._default_git_worktree_probe(root)
    )


def test_real_store_preserves_records_and_durability(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    observed = []
    original_sync = artifacts.os.fsync
    synchronized = []

    def sync(descriptor):
        synchronized.append(descriptor)
        return original_sync(descriptor)

    monkeypatch.setattr(artifacts.os, "fsync", sync)
    record = dict(ordinal=0, before_frame=0, action="wait", repeat=1)
    for mode in ("ordinary", "fast"):
        root = tmp_path / mode
        root.mkdir()
        kwargs = {} if mode == "ordinary" else dict(
            git_worktree_probe=artifacts.gitless_fast_path_worktree_probe,
        )
        store = artifacts.initialize_private_root(
            root, repository_root=repository, allow_same_device=True, **kwargs,
        )
        synchronized.clear()
        published = store.publish_sealed_record("input-000", kind="input_probe", record=record)
        assert published.read() == record
        assert store.find_sealed_record("input-000").read() == record
        observed.append((published.summary.public_dict(), len(synchronized)))
    assert observed[0] == observed[1]
    assert observed[0][1] > 0


@pytest.mark.parametrize("tampering", ["git", "sentinel"])
def test_fast_store_rechecks_new_git_and_sentinel_before_publication(tmp_path, tampering):
    repository, root = tmp_path / "repository", tmp_path / "private"
    repository.mkdir()
    root.mkdir()
    store = artifacts.initialize_private_root(
        root, repository_root=repository, allow_same_device=True,
        git_worktree_probe=artifacts.gitless_fast_path_worktree_probe,
    )
    store.publish_sealed_record("before", kind="input_probe", record=dict(ordinal=0))
    if tampering == "git":
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    else:
        (root / artifacts.PRIVATE_ROOT_SENTINEL).write_text("tampered")
    with pytest.raises(artifacts.PrivateArtifactError):
        store.publish_sealed_record("after", kind="input_probe", record=dict(ordinal=1))
    assert not (root / "after").exists()
