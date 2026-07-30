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
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()
    store = initialize_private_root(root, **_separate_devices(root, repository))
    return root, store


def _canonical(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _write_manifest(directory: Path, manifest: dict[str, object]) -> None:
    target = directory / "manifest.json"
    target.write_bytes(_canonical(manifest))
    target.chmod(0o600)


def _sealed_episode(tmp_path: Path, episode_id: str = "episode-001"):
    root, store = _make_store(tmp_path)
    with store.begin_episode(episode_id) as writer:
        writer.append(
            "episode",
            {
                "episode_id": episode_id,
                "game_id": "pokemon-red",
                "metadata": {"policy": {"policy_id": "teacher-v1"}},
                "record_type": "episode",
            },
        )
        writer.append("actions", {"action": "up", "step": 0})
        writer.append("actions", {"action": "interact", "step": 1})
    return root, store, root / episode_id


def _replace_stream(
    directory: Path,
    filename: str,
    payload: bytes,
    *,
    records: int,
) -> None:
    target = directory / filename
    target.write_bytes(payload)
    target.chmod(0o600)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    for entry in manifest["files"]:
        if entry["filename"] == filename:
            entry["bytes"] = len(payload)
            entry["records"] = records
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            break
    else:
        raise AssertionError(f"missing fixture stream: {filename}")
    manifest["totals"]["bytes"] = sum(entry["bytes"] for entry in manifest["files"])
    manifest["totals"]["records"] = sum(entry["records"] for entry in manifest["files"])
    _write_manifest(directory, manifest)


def _assert_path_free(error: pytest.ExceptionInfo[PrivateArtifactError], tmp_path: Path) -> None:
    assert str(tmp_path) not in str(error.value)
    assert str(tmp_path) not in repr(error.value)
    assert error.value.__cause__ is None


def test_reader_exposes_only_verified_path_free_data_and_bounds(tmp_path: Path) -> None:
    root, store, directory = _sealed_episode(tmp_path)
    manifest_bytes = (directory / "manifest.json").read_bytes()

    reader = store.open_episode("episode-001")

    assert reader.stream_names == ("actions", "episode")
    assert reader.manifest_sha256 == hashlib.sha256(manifest_bytes).hexdigest()
    assert reader.summary.manifest_sha256 == reader.manifest_sha256
    assert reader.summary.stream_records == (("actions", 2), ("episode", 1))
    assert reader.summary.total_records == 3
    assert reader.read_header()["episode_id"] == "episode-001"
    assert list(reader.iter_stream("actions")) == [
        {"action": "up", "step": 0},
        {"action": "interact", "step": 1},
    ]

    header = reader.read_header()
    header["metadata"] = {"changed": True}
    assert reader.read_header()["metadata"] == {"policy": {"policy_id": "teacher-v1"}}

    with pytest.raises(PrivateArtifactError, match="record limit"):
        reader.iter_stream("actions", max_records=1)
    with pytest.raises(PrivateArtifactError, match="non-negative"):
        reader.iter_stream("actions", max_records=-1)
    with pytest.raises(PrivateArtifactError, match="absent"):
        reader.iter_stream("events")
    with pytest.raises(PrivateArtifactError, match="safe lowercase"):
        reader.iter_stream("../actions")

    public_text = json.dumps(reader.public_summary(), sort_keys=True)
    assert str(tmp_path) not in public_text
    assert str(root) not in repr(reader)
    assert "validated=True" in repr(reader)


def test_reader_uses_an_immutable_snapshot_after_whole_episode_validation(
    tmp_path: Path,
) -> None:
    _, store, directory = _sealed_episode(tmp_path)
    reader = store.open_episode("episode-001")

    (directory / "actions.jsonl").write_bytes(b'{"action":"corrupted","step":999}\n')

    assert list(reader.iter_stream("actions")) == [
        {"action": "up", "step": 0},
        {"action": "interact", "step": 1},
    ]


def test_open_episode_revalidates_root_and_rejects_unsafe_ids(tmp_path: Path) -> None:
    root, store, _ = _sealed_episode(tmp_path)

    with pytest.raises(PrivateArtifactError, match="safe lowercase"):
        store.open_episode("../episode-001")

    (root / PRIVATE_ROOT_SENTINEL).write_text("tampered", encoding="ascii")
    with pytest.raises(PrivateArtifactError, match="sentinel failed validation") as raised:
        store.open_episode("episode-001")
    _assert_path_free(raised, tmp_path)


def test_reader_rejects_missing_partial_and_failed_episodes(tmp_path: Path) -> None:
    _, store = _make_store(tmp_path)

    with pytest.raises(PrivateArtifactError, match="absent") as missing:
        store.open_episode("missing")
    _assert_path_free(missing, tmp_path)

    writer = store.begin_episode("pending")
    writer.append("episode", {"record_type": "episode"})
    with pytest.raises(PrivateArtifactError, match="still partial") as partial:
        store.open_episode("pending")
    _assert_path_free(partial, tmp_path)
    writer.abort("test_abort")

    with pytest.raises(PrivateArtifactError, match="failed") as failed:
        store.open_episode("pending")
    _assert_path_free(failed, tmp_path)


def test_reader_rejects_symlinked_episode_and_stream_targets(tmp_path: Path) -> None:
    root, store, directory = _sealed_episode(tmp_path, "real-episode")
    linked_episode = root / "linked-episode"
    try:
        linked_episode.symlink_to(directory, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(PrivateArtifactError, match="regular private directory") as episode_error:
        store.open_episode("linked-episode")
    _assert_path_free(episode_error, tmp_path)

    original = directory / "actions.jsonl"
    external = tmp_path / "external-actions.jsonl"
    external.write_bytes(original.read_bytes())
    external.chmod(0o600)
    original.unlink()
    original.symlink_to(external)
    with pytest.raises(PrivateArtifactError, match="regular file") as stream_error:
        store.open_episode("real-episode")
    _assert_path_free(stream_error, tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_field",
        "extra_field",
        "wrong_format",
        "wrong_schema",
        "float_schema",
        "wrong_status",
        "wrong_identity",
        "files_not_list",
        "wrong_totals",
        "file_extra_field",
    ],
)
def test_reader_rejects_unsupported_manifest_schema(
    tmp_path: Path,
    mutation: str,
) -> None:
    _, store, directory = _sealed_episode(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))

    if mutation == "missing_field":
        manifest.pop("format")
    elif mutation == "extra_field":
        manifest["unsupported"] = True
    elif mutation == "wrong_format":
        manifest["format"] = "other-format"
    elif mutation == "wrong_schema":
        manifest["schema_version"] = True
    elif mutation == "float_schema":
        manifest["schema_version"] = 1.0
    elif mutation == "wrong_status":
        manifest["status"] = "failed"
    elif mutation == "wrong_identity":
        manifest["episode_id"] = "different-episode"
    elif mutation == "files_not_list":
        manifest["files"] = {}
    elif mutation == "wrong_totals":
        manifest["totals"]["records"] += 1
    elif mutation == "file_extra_field":
        manifest["files"][0]["unsupported"] = 1
    else:
        raise AssertionError(mutation)
    _write_manifest(directory, manifest)

    with pytest.raises(PrivateArtifactError) as raised:
        store.open_episode("episode-001")
    _assert_path_free(raised, tmp_path)


@pytest.mark.parametrize("mutation", ["noncanonical", "duplicate_key", "non_object"])
def test_reader_requires_a_canonical_unique_object_manifest(
    tmp_path: Path,
    mutation: str,
) -> None:
    _, store, directory = _sealed_episode(tmp_path)
    target = directory / "manifest.json"
    original = target.read_bytes()
    if mutation == "noncanonical":
        payload = b" " + original
    elif mutation == "duplicate_key":
        payload = original.replace(
            b'{"episode_id":',
            b'{"episode_id":"duplicate","episode_id":',
            1,
        )
    elif mutation == "non_object":
        payload = b"[]\n"
    else:
        raise AssertionError(mutation)
    target.write_bytes(payload)
    target.chmod(0o600)

    with pytest.raises(PrivateArtifactError) as raised:
        store.open_episode("episode-001")
    _assert_path_free(raised, tmp_path)


def test_reader_rejects_duplicate_declarations_and_unknown_directory_entries(
    tmp_path: Path,
) -> None:
    _, store, directory = _sealed_episode(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    manifest["files"].insert(1, dict(manifest["files"][0]))
    manifest["totals"]["files"] += 1
    manifest["totals"]["bytes"] += manifest["files"][0]["bytes"]
    manifest["totals"]["records"] += manifest["files"][0]["records"]
    _write_manifest(directory, manifest)

    with pytest.raises(PrivateArtifactError, match="duplicate") as duplicate:
        store.open_episode("episode-001")
    _assert_path_free(duplicate, tmp_path)

    _, second_store, second_directory = _sealed_episode(
        tmp_path / "second",
        "episode-002",
    )
    extra = second_directory / "undeclared.jsonl"
    extra.write_bytes(b'{"record_type":"extra"}\n')
    extra.chmod(0o600)
    with pytest.raises(PrivateArtifactError, match="exactly match") as unknown:
        second_store.open_episode("episode-002")
    _assert_path_free(unknown, tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"action":"up"\n',
        b"[]\n",
        b'{"action": "up"}\n',
        b'{"action":"up","action":"down"}\n',
        b'{"value":NaN}\n',
    ],
)
def test_reader_rejects_malformed_nonobject_or_noncanonical_stream_records(
    tmp_path: Path,
    payload: bytes,
) -> None:
    _, store, directory = _sealed_episode(tmp_path)
    _replace_stream(directory, "actions.jsonl", payload, records=1)

    with pytest.raises(PrivateArtifactError) as raised:
        store.open_episode("episode-001")
    _assert_path_free(raised, tmp_path)


def test_reader_recomputes_stream_hash_bytes_and_record_counts(tmp_path: Path) -> None:
    _, store, directory = _sealed_episode(tmp_path)
    actions = directory / "actions.jsonl"
    original = actions.read_bytes()
    actions.write_bytes(original.replace(b'"up"', b'"do"', 1))
    with pytest.raises(PrivateArtifactError, match="integrity") as digest_error:
        store.open_episode("episode-001")
    _assert_path_free(digest_error, tmp_path)

    _, second_store, second_directory = _sealed_episode(
        tmp_path / "second",
        "episode-002",
    )
    payload = b'{"action":"up","step":0}\n{"action":"down","step":1}\n'
    _replace_stream(second_directory, "actions.jsonl", payload, records=1)
    with pytest.raises(PrivateArtifactError, match="record count") as count_error:
        second_store.open_episode("episode-002")
    _assert_path_free(count_error, tmp_path)

    _, third_store, third_directory = _sealed_episode(
        tmp_path / "third",
        "episode-003",
    )
    manifest = json.loads((third_directory / "manifest.json").read_text(encoding="ascii"))
    manifest["files"][0]["bytes"] += 1
    manifest["totals"]["bytes"] += 1
    _write_manifest(third_directory, manifest)
    with pytest.raises(PrivateArtifactError, match="byte count") as byte_error:
        third_store.open_episode("episode-003")
    _assert_path_free(byte_error, tmp_path)


def test_reader_rejects_oversized_lines_and_unsafe_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, store, directory = _sealed_episode(tmp_path)
    payload = _canonical({"value": "x" * 64})
    _replace_stream(directory, "actions.jsonl", payload, records=1)
    monkeypatch.setattr(private_artifacts_module, "_MAX_JSONL_LINE_BYTES", 32)
    with pytest.raises(PrivateArtifactError, match="maximum line size") as oversized:
        store.open_episode("episode-001")
    _assert_path_free(oversized, tmp_path)

    monkeypatch.setattr(
        private_artifacts_module,
        "_MAX_JSONL_LINE_BYTES",
        16 * 1024 * 1024,
    )
    (directory / "actions.jsonl").chmod(0o644)
    with pytest.raises(PrivateArtifactError, match="permissions") as file_mode:
        store.open_episode("episode-001")
    _assert_path_free(file_mode, tmp_path)

    (directory / "actions.jsonl").chmod(0o600)
    directory.chmod(0o755)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o755
    with pytest.raises(PrivateArtifactError, match="directory permissions") as directory_mode:
        store.open_episode("episode-001")
    _assert_path_free(directory_mode, tmp_path)


def test_reader_rejects_direct_construction(tmp_path: Path) -> None:
    del tmp_path
    with pytest.raises(PrivateArtifactError, match="validated private root"):
        private_artifacts_module.PrivateEpisodeReader(
            _validation_token=object(),
            episode_id="episode-001",
            files=(),
            payloads={},
            summary=private_artifacts_module.EpisodeSummary(
                episode_id="episode-001",
                status="complete",
                stream_records=(),
                total_records=0,
                total_bytes=0,
                manifest_sha256="0" * 64,
            ),
        )
