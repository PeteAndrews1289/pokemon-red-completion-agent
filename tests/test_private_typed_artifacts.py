from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from pokemon_red_completion import private_artifacts as private_artifacts_module
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, FEATURE_SCHEMA_ID
from pokemon_red_completion.learned_battle_policy import load_battle_model_artifact
from pokemon_red_completion.private_artifacts import (
    EPISODE_FORMAT,
    PRIVATE_JSON_ARTIFACT_FORMAT,
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


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_typed_artifact_is_canonical_private_and_distinct_from_an_episode(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("battle-ranker-001", kind="battle_model")
    partial = root / "battle-ranker-001.partial"
    assert partial.is_dir()
    assert not (partial / "manifest.json").exists()
    assert str(tmp_path) not in repr(writer)

    with writer:
        writer.append(
            "model",
            {
                "model_id": "pokemon.core.battle.masked-linear-ranker.v1",
                "weights": [0.25, -0.5],
            },
        )
        writer.append("evidence", {"accuracy": 0.75, "promotion_eligible": False})

    final = root / "battle-ranker-001"
    assert final.is_dir()
    assert not partial.exists()
    assert _mode(final) == 0o700
    assert all(_mode(path) == 0o600 for path in final.iterdir() if path.is_file())
    assert (final / "model.jsonl").read_bytes() == (
        b'{"model_id":"pokemon.core.battle.masked-linear-ranker.v1","weights":[0.25,-0.5]}\n'
    )

    manifest_bytes = (final / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert set(manifest) == {
        "artifact_id",
        "files",
        "format",
        "kind",
        "schema_version",
        "status",
        "totals",
    }
    assert manifest["artifact_id"] == "battle-ranker-001"
    assert manifest["kind"] == "battle_model"
    assert manifest["format"] == PRIVATE_JSON_ARTIFACT_FORMAT
    assert manifest["format"] != EPISODE_FORMAT
    assert "episode_id" not in manifest
    assert manifest["status"] == "complete"
    assert manifest["totals"] == {
        "bytes": sum((final / entry["filename"]).stat().st_size for entry in manifest["files"]),
        "files": 2,
        "records": 2,
    }

    summary = writer.summary
    assert summary.artifact_id == "battle-ranker-001"
    assert summary.kind == "battle_model"
    assert summary.status == "complete"
    assert summary.stream_records == (("evidence", 1), ("model", 1))
    assert summary.manifest_sha256 == hashlib.sha256(manifest_bytes).hexdigest()
    public_text = json.dumps(summary.public_dict(), sort_keys=True)
    assert str(tmp_path) not in public_text
    assert all(
        forbidden not in public_text.casefold() for forbidden in ("path", "filename", "directory")
    )

    with pytest.raises(PrivateArtifactError, match="unsupported or missing"):
        store.open_episode("battle-ranker-001")


def test_battle_model_candidate_round_trips_through_real_private_writer(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    model = MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64),
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.asarray((0.25, -0.5), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )
    model_sha256 = hashlib.sha256(model.to_json().encode("utf-8")).hexdigest()

    with store.begin_artifact(
        "battle-outcome-round-trip",
        kind="battle_outcome_cycle",
    ) as writer:
        writer.append(
            "model",
            {
                "record_type": "battle_model_candidate",
                "model": model.to_dict(),
                "model_sha256": model_sha256,
                "authority": "shadow_only",
            },
        )

    loaded = load_battle_model_artifact(
        root / "battle-outcome-round-trip" / "model.jsonl"
    )

    assert isinstance(loaded, MaskedMLPMoveRanker)
    assert loaded.to_json() == model.to_json()
    assert hashlib.sha256(loaded.to_json().encode("utf-8")).hexdigest() == model_sha256


@pytest.mark.parametrize(
    ("artifact_id", "kind", "message"),
    [
        ("../model", "battle_model", "artifact id"),
        ("UPPERCASE", "battle_model", "artifact id"),
        ("model.partial", "battle_model", "reserved suffix"),
        ("model", "../battle", "artifact kind"),
        ("model", "BattleModel", "artifact kind"),
        ("model", "battle.model", "artifact kind"),
    ],
)
def test_typed_artifact_requires_safe_identity_and_kind(
    tmp_path: Path,
    artifact_id: str,
    kind: str,
    message: str,
) -> None:
    _, store = _make_store(tmp_path)

    with pytest.raises(PrivateArtifactError, match=message) as raised:
        store.begin_artifact(artifact_id, kind=kind)
    assert str(tmp_path) not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    ("stream", "record", "message"),
    [
        ("../model", {"value": 1}, "stream name"),
        ("manifest", {"value": 1}, "reserved stream"),
        ("model", {"model_path": "private-model.json"}, "path fields"),
        ("model", {"source": "/private/model.json"}, "filesystem paths"),
        ("model", {"weight": float("nan")}, "finite numeric"),
        ("model", cast(dict[str, object], ["not", "an", "object"]), "JSON objects"),
    ],
)
def test_typed_artifact_rejects_unsafe_streams_and_records(
    tmp_path: Path,
    stream: str,
    record: dict[str, object],
    message: str,
) -> None:
    root, store = _make_store(tmp_path)

    with (
        pytest.raises(PrivateArtifactError, match=message),
        store.begin_artifact("rejected-model", kind="battle_model") as writer,
    ):
        writer.append(stream, record)

    failed = root / "rejected-model.failed.partial"
    assert failed.is_dir()
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["format"] == PRIVATE_JSON_ARTIFACT_FORMAT
    assert manifest["artifact_id"] == "rejected-model"
    assert manifest["kind"] == "battle_model"
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "unhandled_exception"


def test_typed_and_episode_artifacts_share_a_no_overwrite_namespace(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    with store.begin_episode("shared-id") as episode:
        episode.append("episode", {"record_type": "episode"})

    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_artifact("shared-id", kind="battle_model")

    with store.begin_artifact("model-id", kind="battle_model") as artifact:
        artifact.append("model", {"weight": 1.0})
    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_episode("model-id")

    pending = store.begin_artifact("pending-model", kind="battle_model")
    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_artifact("pending-model", kind="evaluation")
    pending.abort("test_cleanup")

    assert (root / "shared-id").is_dir()
    assert (root / "model-id").is_dir()
    assert (root / "pending-model.failed.partial").is_dir()


def test_typed_existing_final_is_detected_before_complete_manifest_sealing(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("late-model-collision", kind="battle_model")
    writer.append("model", {"weight": 1.0})
    destination = root / "late-model-collision"
    destination.mkdir()
    (destination / "marker").write_text("untouched", encoding="ascii")

    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        writer.complete()

    assert (destination / "marker").read_text(encoding="ascii") == "untouched"
    assert not (root / "late-model-collision.partial" / "manifest.json").exists()
    writer.abort("test_cleanup")


def test_typed_atomic_publish_race_preserves_destination_and_retains_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("model-publish-race", kind="battle_model")
    writer.append("model", {"weight": 1.0})
    real_rename = private_artifacts_module._rename_no_replace
    destination = root / "model-publish-race"

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
    assert not (root / "model-publish-race.partial").exists()
    failed = root / "model-publish-race.failed.partial"
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    unpublished = json.loads((failed / "manifest.unpublished.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "publication_failed"
    assert unpublished["status"] == "complete"


def test_typed_atomic_publish_race_preserves_an_empty_destination_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("empty-model-publish-race", kind="battle_model")
    writer.append("model", {"weight": 1.0})
    real_rename = private_artifacts_module._rename_no_replace
    destination = root / "empty-model-publish-race"
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
    assert not (root / "empty-model-publish-race.partial").exists()
    failed = root / "empty-model-publish-race.failed.partial"
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "publication_failed"


def test_typed_atomic_failed_publish_race_preserves_destination_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("model-failed-race", kind="battle_model")
    writer.append("model", {"weight": 1.0})
    real_rename = private_artifacts_module._rename_no_replace
    destination = root / "model-failed-race.failed.partial"

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
    partial = root / "model-failed-race.partial"
    manifest = json.loads((partial / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "test_failure"
    assert writer.summary.status == "failed"


def test_typed_artifact_explicit_abort_is_sanitized_and_finalizes_once(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("aborted-model", kind="battle_model")
    writer.append("model", {"weight": 1.0})

    with pytest.raises(PrivateArtifactError, match="sanitized"):
        writer.abort("../private/reason")
    summary = writer.abort("training_failed")

    assert summary.status == "failed"
    assert summary.kind == "battle_model"
    failed = root / "aborted-model.failed.partial"
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["reason_code"] == "training_failed"
    assert "artifact_id" in manifest
    assert "episode_id" not in manifest
    with pytest.raises(PrivateArtifactError, match="already finalized"):
        writer.append("model", {"weight": 2.0})
    with pytest.raises(PrivateArtifactError, match="already finalized"):
        writer.complete()


def test_typed_artifact_context_failure_retains_no_exception_text(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    sensitive = f"could not save {tmp_path}/private/model.json"

    with (
        pytest.raises(RuntimeError, match="could not save"),
        store.begin_artifact("failed-model", kind="battle_model") as writer,
    ):
        writer.append("model", {"weight": 1.0})
        raise RuntimeError(sensitive)

    failed = root / "failed-model.failed.partial"
    serialized = b"".join(path.read_bytes() for path in failed.iterdir() if path.is_file()).decode(
        "ascii"
    )
    assert sensitive not in serialized
    assert str(tmp_path) not in serialized
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    assert manifest["reason_code"] == "unhandled_exception"
    assert all(_mode(path) == 0o600 for path in failed.iterdir() if path.is_file())


def test_typed_artifact_publish_failure_becomes_explicitly_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    writer = store.begin_artifact("publish-failure", kind="battle_model")
    writer.append("model", {"weight": 1.0})
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
            match="unable to publish the completed private artifact",
        ) as raised,
        writer,
    ):
        pass

    assert str(tmp_path) not in str(raised.value)
    assert raised.value.__cause__ is None
    assert not (root / "publish-failure").exists()
    assert not (root / "publish-failure.partial").exists()
    failed = root / "publish-failure.failed.partial"
    assert failed.is_dir()
    manifest = json.loads((failed / "manifest.json").read_text(encoding="ascii"))
    unpublished = json.loads((failed / "manifest.unpublished.json").read_text(encoding="ascii"))
    assert manifest["status"] == "failed"
    assert manifest["reason_code"] == "publication_failed"
    assert unpublished["status"] == "complete"
    assert writer.summary.status == "failed"


def test_typed_artifact_revalidates_root_and_syncs_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    synchronized: list[Path] = []
    monkeypatch.setattr(
        private_artifacts_module,
        "_fsync_directory",
        lambda path: synchronized.append(path),
    )

    with store.begin_artifact("synced-model", kind="battle_model") as writer:
        writer.append("model", {"weight": 1.0})
    assert synchronized[-2:] == [root / "synced-model.partial", root]

    (root / PRIVATE_ROOT_SENTINEL).write_text("tampered", encoding="ascii")
    with pytest.raises(PrivateArtifactError, match="sentinel failed validation") as raised:
        store.begin_artifact("must-not-start", kind="battle_model")
    assert raised.value.__cause__ is None
    assert str(tmp_path) not in str(raised.value)
    assert not (root / "must-not-start.partial").exists()


def test_begin_typed_artifact_durably_claims_the_partial_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    synchronized: list[Path] = []
    monkeypatch.setattr(
        private_artifacts_module,
        "_fsync_directory",
        lambda path: synchronized.append(path),
    )

    writer = store.begin_artifact("durable-model-claim", kind="battle_model")

    partial = root / "durable-model-claim.partial"
    assert partial.is_dir()
    assert synchronized == [partial, root]
    writer.abort("test_cleanup")


def test_begin_typed_artifact_sync_failure_retains_path_free_consumed_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, store = _make_store(tmp_path)
    partial = root / "failed-durable-model-claim.partial"
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
        match="unable to durably claim the private artifact",
    ) as raised:
        store.begin_artifact("failed-durable-model-claim", kind="battle_model")

    assert synchronized == [partial, root]
    assert partial.is_dir()
    assert str(tmp_path) not in str(raised.value)
    assert raised.value.__cause__ is None
    with pytest.raises(PrivateArtifactError, match="refusing to overwrite"):
        store.begin_artifact("failed-durable-model-claim", kind="battle_model")


def test_typed_artifact_summary_requires_finalization_and_repr_is_path_free(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    writer = store.begin_artifact("pending-summary", kind="battle_model")

    assert repr(writer) == (
        "PrivateArtifactWriter(artifact_id='pending-summary', kind='battle_model', state='active')"
    )
    assert str(tmp_path) not in repr(writer)
    with pytest.raises(PrivateArtifactError, match="not been finalized"):
        _ = writer.summary
    writer.abort("test_cleanup")


def test_typed_artifact_writer_cannot_be_constructed_directly(tmp_path: Path) -> None:
    with pytest.raises(PrivateArtifactError, match="validated private root"):
        private_artifacts_module.PrivateArtifactWriter(
            _validation_token=object(),
            artifact_id="model",
            kind="battle_model",
            partial=tmp_path / "model.partial",
            final=tmp_path / "model",
            failed=tmp_path / "model.failed.partial",
        )
