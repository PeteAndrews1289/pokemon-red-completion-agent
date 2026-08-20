from __future__ import annotations

import ast
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_goal_manager_context_batch.py"


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


def _registry() -> SimpleNamespace:
    return SimpleNamespace(
        registry_sha256="a" * 64,
        execution=SimpleNamespace(source_commit="b" * 40),
        slots=(SimpleNamespace(slot_id="red-goal-v1-001-advance_story-train-01"),),
    )


def _plan(tmp_path: Path) -> dict[str, object]:
    return {
        "schema": "pokemon-red-private-goal-manager-context-plan-v1",
        "registry_sha256": "a" * 64,
        "source_commit": "b" * 40,
        "entries": [
            {
                "slot_id": "red-goal-v1-001-advance_story-train-01",
                "state": str(tmp_path / "one.state"),
                "envelope": str(tmp_path / "one.state.json"),
                "profile": str(tmp_path / "one.profile.json"),
            }
        ],
    }


def test_batch_help_separates_read_only_preflight_from_counted_collection() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "preflight" in result.stdout
    assert "rehearse" in result.stdout
    assert "collect" in result.stdout
    assert "--context-catalog" in result.stdout
    assert "--private-root" in result.stdout


def test_batch_invokes_only_the_existing_guarded_stage_scripts() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "record_goal_manager_context" not in calls
    assert "preflight_goal_manager_context" not in calls
    assert '"preflight_goal_manager_context.py"' in source
    assert '"rehearse_goal_manager_context.py"' in source
    assert '"collect_goal_manager_context.py"' in source


def test_private_plan_requires_canonical_registry_order(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    destination = tmp_path / "plan.json"
    destination.write_bytes(_canonical(_plan(tmp_path)))

    entries = module["_load_plan"](destination, _registry())

    assert len(entries) == 1
    assert entries[0].slot_id == "red-goal-v1-001-advance_story-train-01"


def test_private_plan_rejects_duplicate_or_relative_context_paths(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    value = _plan(tmp_path)
    assert isinstance(value["entries"], list)
    value["entries"][0]["state"] = "relative.state"
    destination = tmp_path / "plan.json"
    destination.write_bytes(_canonical(value))

    with pytest.raises(
        module["GoalManagerContextBatchError"],
        match="absolute and unique",
    ):
        module["_load_plan"](destination, _registry())


def test_preflight_batch_root_must_be_empty_and_external(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    root = tmp_path / "receipts"
    root.mkdir()
    (root / "old.json").write_text("{}", encoding="ascii")

    with pytest.raises(
        module["GoalManagerContextBatchError"],
        match="must be empty",
    ):
        module["_external_directory"](root, empty=True)


def test_rehearsal_validates_every_frozen_capture_before_first_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(b"catalog")
    entries = tuple(
        module["_PlanEntry"](
            slot_id=f"slot-{ordinal}",
            state=tmp_path / f"{ordinal}.state",
            envelope=tmp_path / f"{ordinal}.state.json",
            profile=tmp_path / f"{ordinal}.profile.json",
        )
        for ordinal in (1, 2)
    )

    class _Catalog:
        @staticmethod
        def entry(slot_id: str) -> SimpleNamespace:
            return SimpleNamespace(
                capture_id=slot_id,
                state_sha256=f"state-{slot_id}",
                envelope_sha256=f"envelope-{slot_id}",
            )

    calls: list[list[str]] = []
    globals_dict = module["_rehearse"].__globals__
    monkeypatch.setitem(
        globals_dict,
        "parse_goal_manager_context_catalog",
        lambda *_args: _Catalog(),
    )
    monkeypatch.setitem(
        globals_dict,
        "open_goal_manager_context_capture",
        lambda state, _envelope: SimpleNamespace(
            capture_id=f"slot-{state.stem}",
            state_sha256=f"state-slot-{state.stem}",
            envelope_sha256=(
                f"envelope-slot-{state.stem}"
                if state.stem == "1"
                else "deliberate-mismatch"
            ),
        ),
    )
    monkeypatch.setitem(
        globals_dict,
        "_invoke",
        lambda command, **_kwargs: calls.append(command),
    )

    with pytest.raises(
        module["GoalManagerContextBatchError"],
        match="differs from the frozen catalog",
    ):
        module["_rehearse"](
            entries,
            object(),
            rom_path=tmp_path / "game.gb",
            context_catalog=catalog_path,
        )

    assert calls == []


def test_rehearsal_batch_aggregates_only_uncounted_successes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(b"catalog")
    entries = tuple(
        module["_PlanEntry"](
            slot_id=f"slot-{ordinal}",
            state=tmp_path / f"{ordinal}.state",
            envelope=tmp_path / f"{ordinal}.state.json",
            profile=tmp_path / f"{ordinal}.profile.json",
        )
        for ordinal in (1, 2)
    )

    class _Catalog:
        @staticmethod
        def entry(slot_id: str) -> SimpleNamespace:
            return SimpleNamespace(
                capture_id=slot_id,
                state_sha256=f"state-{slot_id}",
                envelope_sha256=f"envelope-{slot_id}",
            )

    globals_dict = module["_rehearse"].__globals__
    monkeypatch.setitem(
        globals_dict,
        "parse_goal_manager_context_catalog",
        lambda *_args: _Catalog(),
    )
    monkeypatch.setitem(
        globals_dict,
        "open_goal_manager_context_capture",
        lambda state, _envelope: SimpleNamespace(
            capture_id=f"slot-{state.stem}",
            state_sha256=f"state-slot-{state.stem}",
            envelope_sha256=f"envelope-slot-{state.stem}",
        ),
    )
    monkeypatch.setitem(
        globals_dict,
        "_invoke",
        lambda _command, **_kwargs: {
            "status": "passed_uncounted_rehearsal",
            "counted": False,
            "episode_created": False,
            "execution": {
                "status": "succeeded",
                "actions_executed": 7,
                "frames_executed": 90,
            },
        },
    )

    summary = module["_rehearse"](
        entries,
        object(),
        rom_path=tmp_path / "game.gb",
        context_catalog=catalog_path,
    )

    assert summary["passed_contexts"] == 2
    assert summary["actions_executed"] == 14
    assert summary["frames_executed"] == 180
    assert summary["episodes_created"] == 0
    assert summary["counted"] is False
