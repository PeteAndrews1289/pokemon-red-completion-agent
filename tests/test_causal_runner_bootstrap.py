from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "causal_runner_bootstrap.py"


def test_bootstrap_has_no_eager_project_import() -> None:
    tree = ast.parse(SCRIPT.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )

    assert not any(name.startswith("pokemon_red_completion") for name in imported)


def test_isolated_bootstrap_imports_development_before_every_project_helper() -> None:
    code = f"""
import json
import sys
sys.path.insert(0, {str(PROJECT_ROOT / "scripts")!r})
import causal_runner_bootstrap as bootstrap
modules = bootstrap.load_causal_runner_modules()
modules.development._require_project_import_origins()
print(json.dumps({{
    'preloaded': list(modules.development._PRELOADED_PROJECT_MODULES),
    'development': modules.development.__name__,
    'paired': modules.paired.__name__,
    'multiroot': modules.multiroot.__name__,
    'public_manifest': modules.public_manifest.__name__,
    'manifest_freezer': modules.manifest_freezer.__name__,
}}))
"""
    completed = subprocess.run(
        (sys.executable, "-I", "-c", code),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "preloaded": [],
        "development": "run_repeatable_goal_manager_development",
        "paired": "run_paired_goal_manager_outcome_screen",
        "multiroot": "run_resettable_goal_manager_multiroot_campaign",
        "public_manifest": "public_execution_manifest",
        "manifest_freezer": "freeze_causal_execution_manifest",
    }


@pytest.mark.parametrize(
    ("error_type", "raw", "expected"),
    (
        (
            "RepeatableGoalManagerRunError",
            "source_authentication",
            "readiness_source_authentication",
        ),
        (
            "RepeatableGoalManagerRunError",
            "external_context_plan_attestation",
            "readiness_context_plan_authentication",
        ),
        (
            "PairedScreenRunError",
            "shadow_candidate_contract",
            "readiness_candidate_authentication",
        ),
        (
            "PairedScreenRunError",
            "prior_campaign_attestation",
            "readiness_prior_campaign_authentication",
        ),
        (
            "ResettableMultirootRunError",
            "import_origin_attestation",
            "readiness_executable_authentication",
        ),
    ),
)
def test_readiness_substages_are_allowlisted_and_path_free(
    error_type: str,
    raw: str,
    expected: str,
) -> None:
    module = _load_without_project_imports()
    error_class = type(error_type, (RuntimeError,), {})
    error = error_class(raw)

    assert module["sanitized_readiness_substage"](error) == expected


def test_unknown_or_private_error_text_collapses_without_echo() -> None:
    module = _load_without_project_imports()
    error_class = type("PairedScreenRunError", (RuntimeError,), {})

    assert (
        module["sanitized_readiness_substage"](error_class("/private/secret"))
        == "readiness_internal"
    )
    assert (
        module["sanitized_readiness_substage"](RuntimeError("source_authentication"))
        == "readiness_internal"
    )


def _load_without_project_imports() -> dict[str, object]:
    name = "causal_runner_bootstrap_mapping_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("bootstrap test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return vars(module)
