from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_red_completion.artifacts import (
    PRIVATE_DIRECTORY_NAMES,
    PRIVATE_SUFFIXES,
    inspect_public_tree,
    inspect_tracked_tree,
    sensitive_text_reasons,
)


def test_sensitive_text_detects_secrets_and_private_home_paths() -> None:
    private_path = "/" + "Users" + "/alice/private/run.json"
    token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz123456"

    assert sensitive_text_reasons(private_path) == ("private home-directory path",)
    assert sensitive_text_reasons(f"token={token}") == ("GitHub token",)
    assert sensitive_text_reasons("/Users/example/project") == ()


def test_secret_token_boundary_does_not_match_risk_identifiers() -> None:
    key = "sk" + "-" + "x" * 30
    for prefix in ("", "token=", '"', "Bearer ", "/", "-", "\n"):
        assert sensitive_text_reasons(prefix + key) == ("OpenAI-style key",)
    assert sensitive_text_reasons("risk-cost-" + "x" * 30) == ()


def test_public_tree_rejects_private_suffixes_and_symlinks(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("safe", encoding="utf-8")
    (tmp_path / "accidental.state").write_bytes(b"private")
    (tmp_path / "link.md").symlink_to(tmp_path / "README.md")

    violations = inspect_public_tree(tmp_path)
    reasons = {(violation.path, violation.reason) for violation in violations}

    assert ("accidental.state", "private artifact suffix") in reasons
    assert ("link.md", "symbolic links are not publishable") in reasons


def test_training_trajectory_formats_and_directory_are_always_private() -> None:
    assert {"trajectories", "datasets", "models", "recordings"}.issubset(
        PRIVATE_DIRECTORY_NAMES
    )
    assert {".jsonl", ".parquet", ".arrow", ".npy", ".npz", ".pkl"}.issubset(PRIVATE_SUFFIXES)


def test_ignored_runtime_directories_are_not_scanned_as_public_content(tmp_path: Path) -> None:
    runtime = tmp_path / "runs"
    runtime.mkdir()
    (runtime / "private.state").write_bytes(b"private")

    assert inspect_public_tree(tmp_path) == ()


def test_git_tracked_private_file_is_scanned_even_under_runtime_directory(
    tmp_path: Path,
) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    runtime = tmp_path / "runs"
    runtime.mkdir()
    private = runtime / "forced.state"
    private.write_bytes(b"private")
    subprocess.run(["git", "add", "-f", str(private)], cwd=tmp_path, check=True)

    assert inspect_tracked_tree(tmp_path)[0].reason == "private artifact suffix"


@pytest.mark.parametrize("mount,drive,users,username", [
    ("mnt", "c", "Users", "alice"),
    ("MNT", "C", "USERS", "Alice"),
    ("mnt", "d", "users", "alice.smith-2"),
    ("mNt", "Z", "uSeRs", "test_person"),
])
def test_mounted_windows_home_paths_are_private_in_all_case_variants(
    mount: str, drive: str, users: str, username: str,
) -> None:
    path = "/".join(("", mount, drive, users, username, "Documents", "review.json"))
    assert sensitive_text_reasons(path) == ("private home-directory path",)


@pytest.mark.parametrize("username", ["example", "runner", "user", "username", "EXAMPLE"])
def test_mounted_windows_placeholder_homes_remain_publishable(username: str) -> None:
    path = "/".join(("", "MNT", "C", "USERS", username, "project"))
    assert sensitive_text_reasons(path) == ()


def test_mounted_windows_home_is_rejected_inside_public_json(tmp_path: Path) -> None:
    import json

    path = "/".join(("", "mnt", "c", "Users", "alice", "Documents", "review.json"))
    document = tmp_path / "evidence.json"
    document.write_text(json.dumps({"source": path}), encoding="utf-8")
    reasons = {(item.path, item.reason) for item in inspect_public_tree(tmp_path)}
    assert reasons == {("evidence.json", "private home-directory path")}


def test_mount_prefix_must_name_one_drive_and_an_actual_home_component() -> None:
    for parts in (("", "mnt", "cc", "Users", "alice", "project"),
                  ("", "mnt", "c", "SomeUsers", "alice", "project")):
        assert sensitive_text_reasons("/".join(parts)) == ()
