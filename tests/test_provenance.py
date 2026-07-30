from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    SourceIdentity,
    build_evaluation_identity,
    canonical_sha256,
    detect_source_identity,
    file_sha256,
    require_clean_source,
    require_published_source,
)


def _committed_repository(tmp_path: Path, name: str, content: str) -> tuple[Path, str]:
    repository = tmp_path / name
    repository.mkdir()
    (repository / "tracked.txt").write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Provenance Test",
            "-c",
            "user.email=provenance@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=repository,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository, commit


def test_canonical_digest_is_independent_of_mapping_order() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})
    assert canonical_sha256({"a": [1, 2]}) != canonical_sha256({"a": [2, 1]})


def test_official_identity_requires_known_clean_source() -> None:
    with pytest.raises(EvaluationIdentityError, match="unavailable"):
        require_clean_source(SourceIdentity(None, None))
    with pytest.raises(EvaluationIdentityError, match="clean worktree"):
        require_clean_source(SourceIdentity("a" * 40, True))


def test_scheduled_collection_requires_the_exact_commit_on_a_remote_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pokemon_red_completion import provenance

    source = SourceIdentity("a" * 40, False)
    observed: list[tuple[str, ...]] = []

    def remote_refs(_root: Path, *arguments: str) -> str:
        observed.append(arguments)
        return "refs/remotes/origin/protocol\n"

    monkeypatch.setattr(provenance, "_git_output", remote_refs)
    require_published_source(Path("/repository"), source)

    assert observed == [
        (
            "for-each-ref",
            f"--contains={source.git_commit}",
            "--format=%(refname)",
            "refs/remotes",
        )
    ]


@pytest.mark.parametrize(
    "refs",
    (
        "",
        "refs/remotes/origin/HEAD\n",
    ),
)
def test_scheduled_collection_rejects_an_unpublished_commit(
    monkeypatch: pytest.MonkeyPatch,
    refs: str,
) -> None:
    from pokemon_red_completion import provenance

    monkeypatch.setattr(provenance, "_git_output", lambda _root, *_arguments: refs)

    with pytest.raises(EvaluationIdentityError, match="exact source commit"):
        require_published_source(
            Path("/repository"),
            SourceIdentity("a" * 40, False),
        )


def test_published_source_probe_failure_is_path_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pokemon_red_completion import provenance

    private_root = Path("/private/repository")
    monkeypatch.setattr(provenance, "_git_output", lambda _root, *_arguments: None)

    with pytest.raises(EvaluationIdentityError) as error:
        require_published_source(
            private_root,
            SourceIdentity("a" * 40, False),
        )

    assert str(private_root) not in str(error.value)
    assert str(error.value) == "Published source identity is unavailable."


def test_source_identity_ignores_git_repository_and_config_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pokemon_red_completion import provenance

    trusted, trusted_commit = _committed_repository(tmp_path, "trusted", "trusted\n")
    other, _other_commit = _committed_repository(tmp_path, "other", "other\n")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    monkeypatch.setenv("GIT_NO_REPLACE_OBJECTS", "0")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(other))

    identity = detect_source_identity(trusted)
    environment = provenance._sanitized_git_environment()

    assert identity == SourceIdentity(trusted_commit, False)
    assert "GIT_DIR" not in environment
    assert "GIT_WORK_TREE" not in environment
    assert "GIT_INDEX_FILE" not in environment
    assert "GIT_CONFIG_COUNT" not in environment
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"


def test_git_output_limit_fails_closed(tmp_path: Path) -> None:
    from pokemon_red_completion import provenance

    repository, _commit = _committed_repository(tmp_path, "bounded", "tracked\n")
    (repository / ("x" * 100)).write_text("untracked\n", encoding="utf-8")

    output = provenance._git_output(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=all",
        maximum_output_bytes=8,
    )

    assert output is None


def test_git_timeout_fails_closed_without_exposing_process_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pokemon_red_completion import provenance

    executable_directory = tmp_path / "bin"
    executable_directory.mkdir()
    fake_git = executable_directory / "git"
    fake_git.write_text(
        f"#!{sys.executable}\nimport time\ntime.sleep(5)\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(executable_directory))
    monkeypatch.setattr(provenance, "_GIT_TIMEOUT_SECONDS", 0.05)

    started = time.monotonic()
    output = provenance._git_output(tmp_path, "status")
    elapsed = time.monotonic() - started

    assert output is None
    assert elapsed < 1


def test_build_evaluation_identity_hashes_all_influencing_inputs(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"weights")

    identity = build_evaluation_identity(
        source=SourceIdentity("a" * 40, False),
        rom_sha1="b" * 40,
        rom_sha256="c" * 64,
        objective_graph={"route": ["start", "hall-of-fame"]},
        configuration={"seed": 7},
        model_paths=(model,),
    )

    assert identity.source.git_commit == "a" * 40
    assert identity.model_sha256 == (file_sha256(model),)
    assert identity.public_dict()["source"]["worktree_dirty"] is False
    assert str(tmp_path) not in str(identity.public_dict())
