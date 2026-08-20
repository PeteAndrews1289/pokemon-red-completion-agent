from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind, GoalNeed
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH,
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
    load_committed_goal_manager_registry_at_revision,
    parse_goal_manager_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / GOAL_MANAGER_REGISTRY_RELATIVE_PATH
DIGEST_PATH = PROJECT_ROOT / GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH


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


def _slots(document: dict[str, object]) -> list[dict[str, object]]:
    slots = document["slots"]
    assert isinstance(slots, list)
    assert all(isinstance(item, dict) for item in slots)
    return slots


def test_registry_prospectively_balances_all_nine_goal_families() -> None:
    payload = REGISTRY_PATH.read_bytes()
    registry = parse_goal_manager_registry(payload)

    assert payload == _canonical(_document())
    assert registry.registry_sha256 == hashlib.sha256(payload).hexdigest()
    assert registry.partition_counts == {"train": 54, "validation": 27}
    assert len(registry.slots) == 81
    assert len({slot.slot_id for slot in registry.slots}) == 81
    assert len({slot.harness_seed for slot in registry.slots}) == 81
    assert Counter((slot.focus_kind, slot.partition) for slot in registry.slots) == Counter(
        {
            **{(kind, "train"): 6 for kind in GoalKind},
            **{(kind, "validation"): 3 for kind in GoalKind},
        }
    )
    assert {slot.focus_need for slot in registry.slots} == set(GoalNeed)


def test_registry_digest_and_assignment_are_path_free_and_source_bound() -> None:
    payload = REGISTRY_PATH.read_bytes()
    registry = parse_goal_manager_registry(payload)
    digest = json.loads(DIGEST_PATH.read_text(encoding="ascii"))

    assert digest == {
        "bytes": len(payload),
        "schema": "pokemon-red-goal-manager-registry-digest-v1",
        "sha256": registry.registry_sha256,
    }
    assignment = registry.assignment(registry.slots[0].slot_id)
    metadata = assignment.metadata_dict()
    assert assignment.partition == "train"
    assert assignment.collection_slot_ordinal == 1
    assert assignment.partition_slot_ordinal == 1
    assert assignment.declared_collection_slots == 81
    assert assignment.declared_partition_slots == 54
    assert metadata["curation_focus"] == {
        "excluded_from_policy_input": True,
        "kind": GoalKind.ADVANCE_STORY.value,
        "need": GoalNeed.STORY_PROGRESS.value,
        "not_a_teacher_label": True,
    }
    encoded = json.dumps(metadata, sort_keys=True)
    assert "/" not in encoded
    assert "Users" not in encoded
    with pytest.raises(GoalManagerProtocolError, match="committed assignment"):
        assignment.episode_metadata()


def test_parser_rejects_duplicate_keys_noncanonical_bytes_and_split_drift() -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        parse_goal_manager_registry("{}\n")  # type: ignore[arg-type]
    with pytest.raises(GoalManagerProtocolError, match="canonical ASCII"):
        parse_goal_manager_registry(b'{"schema":"one","schema":"two"}\n')
    with pytest.raises(GoalManagerProtocolError, match="canonical ASCII"):
        parse_goal_manager_registry(json.dumps(_document(), indent=2).encode("ascii"))

    drifted = _document()
    _slots(drifted)[0]["partition"] = "validation"
    with pytest.raises(GoalManagerProtocolError, match="order differs"):
        parse_goal_manager_registry(_canonical(drifted))

    relabeled = _document()
    _slots(relabeled)[0]["focus_kind"] = GoalKind.ACQUIRE_SPECIES.value
    with pytest.raises(GoalManagerProtocolError, match="focus kind differs"):
        parse_goal_manager_registry(_canonical(relabeled))


def test_generator_check_accepts_only_the_current_source_bound_registry() -> None:
    subprocess.run(
        [sys.executable, "scripts/regenerate_goal_manager_registry.py", "--check"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_committed_loader_binds_registry_to_exact_executable_source(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", repository / "pyproject.toml")
    shutil.copytree(
        PROJECT_ROOT / "src",
        repository / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    for relative in (
        GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
        GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH,
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
            "user.name=Goal Manager Test",
            "-c",
            "user.email=goal-manager@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "freeze goal-manager collection",
        ],
        cwd=repository,
        check=True,
    )

    loaded = load_committed_goal_manager_registry(repository)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    historical = load_committed_goal_manager_registry_at_revision(repository, commit)

    assert loaded.execution.source_commit is not None
    assert historical == loaded
    assignment = loaded.assignment(loaded.slots[-1].slot_id)
    assert assignment.source_commit == loaded.execution.source_commit
    assert assignment.episode_metadata()["source"] == {
        "git_commit": loaded.execution.source_commit
    }
    with pytest.raises(GoalManagerProtocolError, match="unavailable"):
        load_committed_goal_manager_registry_at_revision(repository, "f" * 40)
