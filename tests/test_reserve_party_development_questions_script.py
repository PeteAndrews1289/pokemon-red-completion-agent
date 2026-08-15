from __future__ import annotations

import argparse
import ast
import hashlib
import json
import runpy
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "reserve_party_development_questions.py"
)
SCRIPT = runpy.run_path(str(SCRIPT_PATH))
GLOBALS = SCRIPT["_run"].__globals__


def _write_json(path: Path, value: object) -> str:
    payload = (json.dumps(value, sort_keys=True) + "\n").encode("ascii")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _args(tmp_path: Path) -> argparse.Namespace:
    inventory = tmp_path / "inventory.json"
    model = tmp_path / "model.json"
    registry = tmp_path / "registry.json"
    return argparse.Namespace(
        inventory=inventory,
        inventory_file_sha256=_write_json(inventory, {"inventory": True}),
        initial_model=model,
        initial_model_file_sha256=_write_json(model, {"model": True}),
        venue_prior_registry=registry,
        venue_prior_registry_file_sha256=_write_json(
            registry, {"registry": True}
        ),
        out_plan=tmp_path / "private-plan.json",
    )


class _Loader:
    @classmethod
    def from_private_dict(cls, value: object) -> object:
        assert isinstance(value, dict)
        return value


class _ModelLoader:
    @classmethod
    def from_dict(cls, value: object) -> object:
        assert value == {"model": True}
        return SimpleNamespace(
            outcome_training_examples=0,
            teacher_prior="teacher-prior",
        )


class _Plan:
    def private_dict(self) -> dict[str, object]:
        return {
            "schema": "private-plan",
            "candidate_menus_frozen": 0,
            "outcomes_opened": 0,
        }

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": "public-summary",
            "reservation_count": 14,
            "controller_actions": 0,
        }


def test_script_authenticates_inputs_and_writes_one_exclusive_private_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(GLOBALS, "PartyDevelopmentCheckpointInventory", _Loader)
    monkeypatch.setitem(GLOBALS, "PartyDevelopmentOutcomeModel", _ModelLoader)
    monkeypatch.setitem(GLOBALS, "PartyDevelopmentVenuePriorRegistry", _Loader)
    monkeypatch.setitem(
        GLOBALS,
        "reserve_party_development_questions",
        lambda inventory, *, teacher_prior, venue_prior_registry: _Plan(),
    )
    args = _args(tmp_path)

    summary = SCRIPT["_run"](args)
    payload = args.out_plan.read_bytes()

    assert summary["reservation_count"] == 14
    assert summary["controller_actions"] == 0
    assert summary["private_plan_file_sha256"] == hashlib.sha256(payload).hexdigest()
    assert summary["private_plan_file_tracked"] is False
    assert stat.S_IMODE(args.out_plan.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        SCRIPT["_run"](args)


def test_script_rejects_changed_input_and_repository_private_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(GLOBALS, "PartyDevelopmentCheckpointInventory", _Loader)
    monkeypatch.setitem(GLOBALS, "PartyDevelopmentOutcomeModel", _ModelLoader)
    monkeypatch.setitem(GLOBALS, "PartyDevelopmentVenuePriorRegistry", _Loader)
    monkeypatch.setitem(
        GLOBALS,
        "reserve_party_development_questions",
        lambda inventory, *, teacher_prior, venue_prior_registry: _Plan(),
    )
    args = _args(tmp_path)
    args.inventory.write_text('{"changed":true}\n', encoding="ascii")

    with pytest.raises(RuntimeError, match="inventory file digest differs"):
        SCRIPT["_run"](args)

    args = _args(tmp_path)
    args.out_plan = PROJECT_ROOT / "private-question-plan-must-not-exist.json"
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_run"](args)
    assert not args.out_plan.exists()


def test_script_has_no_game_execution_prediction_or_teacher_surface() -> None:
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
        for token in ("emulator", "rom", "controller", "teacher")
    )
    assert called_names.isdisjoint(
        {"PyBoyAdapter", "resolve_rom_path", "verify_rom", "run_red_team_balancing"}
    )
    assert called_attributes.isdisjoint(
        {
            "execute",
            "fit",
            "hold",
            "load_state",
            "predict",
            "press",
            "release",
            "send_input",
            "tick",
        }
    )
