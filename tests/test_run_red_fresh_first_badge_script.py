from __future__ import annotations

import argparse
import ast
import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.route import COMPLETION_QUEST

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_red_fresh_first_badge.py"


def _call_names() -> tuple[str, ...]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    result: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            result.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.append(node.func.attr)
    return tuple(result)


def test_runner_authenticates_source_model_and_saved_capture() -> None:
    calls = _call_names()

    for required in (
        "require_clean_source",
        "require_published_source",
        "load_objective_model_artifact",
        "run_fresh_first_badge_conductor",
        "save_state",
        "write_captured_progress",
        "load_captured_progress",
    ):
        assert required in calls

    source = SCRIPT.read_text(encoding="utf-8")
    assert "speed=args.speed if args.watch else None" in source


def test_neutral_ranker_is_explicitly_unlearned_and_schema_compatible() -> None:
    module = runpy.run_path(str(SCRIPT))
    parser = argparse.ArgumentParser()

    model, identity = module["_load_ranker"](
        parser,
        artifact=None,
        integration_neutral=True,
    )

    assert model.feature_names == ObjectiveFeatureProjector(COMPLETION_QUEST).feature_names
    assert identity["artifact_authenticated"] is False
    assert identity["kind"] == "integration_only_zero_weight_ranker"
    assert identity["learned"] is False


def test_private_outputs_must_be_new_and_outside_repository(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    require_output = module["_require_new_private_output"]
    parser = argparse.ArgumentParser()
    outside = tmp_path / "first-badge.state"

    require_output(parser, outside)
    outside.write_bytes(b"existing")
    with pytest.raises(SystemExit):
        require_output(parser, outside)
    with pytest.raises(SystemExit):
        require_output(parser, PROJECT_ROOT / "private.state")
