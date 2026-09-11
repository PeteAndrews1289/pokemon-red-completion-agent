from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_red_fresh_celadon_join.py"


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


def test_runner_authenticates_both_captures_and_published_source() -> None:
    calls = _call_names()

    for required in (
        "require_clean_source",
        "require_published_source",
        "load_captured_progress",
        "run_first_badge_to_celadon_conductor",
        "save_state",
        "write_captured_progress",
    ):
        assert required in calls

    source = SCRIPT.read_text(encoding="utf-8")
    assert "source_state_sha256" in source
    assert "fresh Celadon join changed its authenticated source state" in source
    assert "speed=args.speed if args.watch else None" in source


def test_runner_requires_distinct_source_and_output_paths() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "if len(distinct) != 4" in source
    assert "source and output state/envelope paths must all differ" in source
    assert "_require_new_private_output(parser, args.out_state)" in source
    assert "_require_new_private_output(parser, args.out_envelope)" in source
