from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_DIGEST_RELATIVE_PATH,
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    StrategicNavigationProtocolError,
    load_committed_strategic_navigation_registry,
    parse_strategic_navigation_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH
DIGEST_PATH = PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_DIGEST_RELATIVE_PATH


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _document() -> dict[str, object]:
    value = json.loads(REGISTRY_PATH.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def _runs(document: dict[str, object]) -> list[dict[str, object]]:
    rows = document["runs"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def test_registry_is_canonical_preassigned_and_seals_test_roots() -> None:
    payload = REGISTRY_PATH.read_bytes()
    registry = parse_strategic_navigation_registry(payload)

    assert payload == _canonical(_document())
    assert registry.registry_sha256 == hashlib.sha256(payload).hexdigest()
    assert registry.partition_counts == {"test": 5, "train": 5, "validation": 2}
    assert len(registry.runs) == 12
    assert len({run.harness_seed for run in registry.runs}) == 12
    assert len({run.schedule_sha256 for run in registry.runs}) == 12
    assert registry.rehearsal.harness_seed not in {
        run.harness_seed for run in registry.runs
    }
    assert registry.rehearsal.schedule_sha256 not in {
        run.schedule_sha256 for run in registry.runs
    }
    assert registry.learning_assignment("red-strategic-v1-01-train").partition == "train"
    assert (
        registry.learning_assignment("red-strategic-v1-06-validation").partition
        == "validation"
    )
    with pytest.raises(StrategicNavigationProtocolError, match="must remain unopened"):
        registry.learning_assignment("red-strategic-v1-08-test")


def test_registry_and_contract_have_stable_public_identities() -> None:
    payload = REGISTRY_PATH.read_bytes()
    registry = parse_strategic_navigation_registry(payload)
    digest = json.loads(DIGEST_PATH.read_text(encoding="ascii"))

    assert len(payload) == 6019
    assert (
        registry.registry_sha256
        == "b74a88907c5eb308fa7086a67cfecc19c2663e4184978080c15449719e54e91e"
    )
    assert (
        registry.execution.source_bundle_sha256
        == "2c2268156da6ee7918cbf25dd74e872c0bfac2df46e003b90ed066a660f222df"
    )
    assert (
        registry.execution.decision_contract_sha256
        == "d62f16a23ad54742c97a52ffaa50b0617042d5e35518af4ae61b623631e539a6"
    )
    assert (
        registry.execution.teacher_execution_sha256
        == "d544efb040f5c83da654df07db56b126867417180abea3ac314dc88151e24451"
    )
    assert digest == {
        "bytes": len(payload),
        "schema": "pokemon-strategic-navigation-collection-registry-digest-v1",
        "sha256": registry.registry_sha256,
    }


def test_assignment_identity_is_path_free_and_partition_bound() -> None:
    registry = parse_strategic_navigation_registry(REGISTRY_PATH.read_bytes())
    first = registry.assignment("red-strategic-v1-01-train")
    validation = registry.assignment("red-strategic-v1-06-validation")

    assert first == registry.assignment("red-strategic-v1-01-train")
    assert first.root_lineage_id == f"red-strategic-root-{first.assignment_id}"
    assert first.episode_id == f"red-strategic-teacher-{first.assignment_id}"
    assert first.collection_slot_ordinal == 1
    assert first.partition_slot_ordinal == 1
    assert first.declared_partition_slots == 5
    assert validation.collection_slot_ordinal == 6
    assert validation.partition_slot_ordinal == 1
    assert validation.declared_partition_slots == 2
    metadata = first.metadata_dict()
    assert metadata["attempt"] == {"attempts_per_slot": 1, "counted": True}
    assert metadata["split"] == {
        "partition": "train",
        "regime": "within_game_whole_root",
        "root_lineage_id": first.root_lineage_id,
    }
    assert "/" not in json.dumps(metadata, sort_keys=True)
    with pytest.raises(StrategicNavigationProtocolError, match="digest differs"):
        replace(first, assignment_id="0" * 64)
    with pytest.raises(StrategicNavigationProtocolError, match="committed assignment"):
        first.episode_metadata()
    committed = replace(first, source_commit="a" * 40)
    episode_metadata = committed.episode_metadata()
    assert episode_metadata["source"] == {"git_commit": "a" * 40}
    assert episode_metadata["split"] == metadata["split"]


def test_parser_rejects_noncanonical_duplicate_or_drifted_registry() -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        parse_strategic_navigation_registry("{}\n")  # type: ignore[arg-type]
    with pytest.raises(StrategicNavigationProtocolError, match="canonical ASCII"):
        parse_strategic_navigation_registry(b'{"schema":"one","schema":"two"}\n')

    document = _document()
    pretty = json.dumps(document, indent=2, sort_keys=True).encode("ascii")
    with pytest.raises(StrategicNavigationProtocolError, match="canonical ASCII"):
        parse_strategic_navigation_registry(pretty)

    drifted = _document()
    _runs(drifted)[0]["partition"] = "validation"
    with pytest.raises(StrategicNavigationProtocolError, match="order differs"):
        parse_strategic_navigation_registry(_canonical(drifted))

    repeated = _document()
    _runs(repeated)[1]["harness_seed"] = _runs(repeated)[0]["harness_seed"]
    _runs(repeated)[1]["schedule_sha256"] = _runs(repeated)[0]["schedule_sha256"]
    with pytest.raises(StrategicNavigationProtocolError, match="duplicated"):
        parse_strategic_navigation_registry(_canonical(repeated))


def test_committed_loader_binds_registry_to_exact_source(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", repository / "pyproject.toml")
    shutil.copytree(
        PROJECT_ROOT / "src",
        repository / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    for relative in (
        STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
        STRATEGIC_NAVIGATION_REGISTRY_DIGEST_RELATIVE_PATH,
    ):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative, target)
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Strategic Collection Test",
            "-c",
            "user.email=strategic@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "freeze strategic collection",
        ],
        cwd=repository,
        check=True,
    )

    loaded = load_committed_strategic_navigation_registry(repository)

    assert loaded.registry_sha256 == parse_strategic_navigation_registry(
        REGISTRY_PATH.read_bytes()
    ).registry_sha256
    assert loaded.execution.source_commit is not None
