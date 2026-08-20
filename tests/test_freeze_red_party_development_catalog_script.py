from __future__ import annotations

import ast
import hashlib
import json
import runpy
import stat
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "freeze_red_party_development_catalog.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def _canonical(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _artifact(root: Path, artifact_id: str) -> tuple[Path, str]:
    directory = root / artifact_id
    directory.mkdir()
    stream_counts = {
        "output_claim.jsonl": 1,
        "plan.jsonl": 1,
        "progress.jsonl": 27,
        "terminal.jsonl": 1,
    }
    files = []
    total_bytes = 0
    total_records = 0
    for filename, count in stream_counts.items():
        payload = b"".join(_canonical({"index": index}) for index in range(count))
        (directory / filename).write_bytes(payload)
        files.append(
            {
                "bytes": len(payload),
                "filename": filename,
                "records": count,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        total_bytes += len(payload)
        total_records += count
    manifest = {
        "artifact_id": artifact_id,
        "files": sorted(files, key=lambda item: item["filename"]),
        "format": "pokemon-red-completion-private-artifact-jsonl",
        "kind": "party_development_pp_materialization",
        "schema_version": 1,
        "status": "complete",
        "totals": {
            "bytes": total_bytes,
            "files": 4,
            "records": total_records,
        },
    }
    payload = _canonical(manifest)
    (directory / "manifest.json").write_bytes(payload)
    return directory, hashlib.sha256(payload).hexdigest()


def test_artifact_reader_authenticates_every_manifest_stream(tmp_path: Path) -> None:
    artifact_id = "red-party-pp-materialization-v1-train"
    directory, manifest_sha256 = _artifact(tmp_path, artifact_id)

    manifest, streams = SCRIPT["_artifact_streams"](
        directory,
        artifact_id=artifact_id,
        expected_manifest_sha256=manifest_sha256,
    )

    assert manifest["status"] == "complete"
    assert len(streams["progress"]) == 27
    progress = directory / "progress.jsonl"
    progress.write_bytes(progress.read_bytes() + _canonical({"index": 28}))
    with pytest.raises(RuntimeError, match="digest or count differs"):
        SCRIPT["_artifact_streams"](
            directory,
            artifact_id=artifact_id,
            expected_manifest_sha256=manifest_sha256,
        )


def test_catalog_writer_is_exclusive_durable_and_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "catalog.json"
    payload = _canonical({"schema": "private-test-v1"})

    digest = SCRIPT["_write_exclusive"](target, payload)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert target.read_bytes() == payload
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        SCRIPT["_write_exclusive"](target, payload)


def test_catalog_freezer_has_no_actor_answer_or_learning_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not any(
        token in module
        for module in imported_modules
        for token in ("executor", "outcome_learning", "teacher")
    )
    assert called_names.isdisjoint(
        {"CountingExecutor", "FrameSafeExecutor", "run_red_team_balancing"}
    )
    assert called_attributes.isdisjoint(
        {"execute", "hold", "press", "release", "send_input", "tick"}
    )
    assert "PartyDevelopmentFrozenCatalog.freeze" in source
    assert "PartyDevelopmentQuestionPreflight" in source
    assert "exact prior inventory plus two PP states" in source
    assert "--execute" not in source
    assert "candidate_decision_authority" not in source
