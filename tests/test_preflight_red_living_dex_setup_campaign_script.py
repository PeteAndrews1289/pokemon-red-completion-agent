# ruff: noqa: E402 -- standalone bridge is loaded after its script-local imports.

from __future__ import annotations

import copy
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import venv
from contextlib import contextmanager
from pathlib import Path
from types import FunctionType, SimpleNamespace
from typing import cast

import pytest
from test_red_living_dex_provider_plan import _root

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.private_artifacts import SealedRecordSummary
from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/preflight_red_living_dex_setup_campaign.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="preflight_red_living_dex_setup_campaign_test",
)


def _bind_test_host_git(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use the test host's root-owned Git without weakening production constants."""

    raw_git = shutil.which("git")
    assert raw_git is not None
    git = Path(raw_git).resolve(strict=True)
    globals_ = SCRIPT["_bootstrap_git_bytes"].__globals__
    monkeypatch.setitem(globals_, "_BOOTSTRAP_GIT_EXECUTABLE", git)
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_GIT_EXECUTABLE_SHA256",
        hashlib.sha256(git.read_bytes()).hexdigest(),
    )
    return git


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _args() -> list[str]:
    return [
        "--expected-bridge-source-commit",
        "b" * 40,
        "--exact-ci-run",
        "1234",
        "--exact-ci-attempt",
        "1",
        "--expected-source-commit",
        "a" * 40,
        "--expected-source-bundle-sha256",
        _sha("source"),
        "--registry-source-commit",
        "c" * 40,
        "--expected-registry-sha256",
        _sha("registry"),
        "--context-catalog",
        "/private/catalog.json",
        "--expected-context-catalog-sha256",
        _sha("catalog"),
        "--context-plan",
        "/private/plan.json",
        "--expected-context-plan-sha256",
        _sha("context-plan"),
        "--private-root",
        "/private/artifacts",
        "--expected-private-plan-sha256",
        _sha("private-plan"),
        "--expected-plan-manifest-sha256",
        _sha("manifest"),
        "--expected-recipe-plan-sha256",
        _sha("recipe-plan"),
        "--expected-execution-identity-sha256",
        _sha("execution"),
        "--rom",
        "/private/red.gb",
    ]


def _plan_and_freeze() -> tuple[dict[str, object], dict[str, object], tuple[str, ...]]:
    execution: dict[str, object] = {
        "schema": "synthetic-execution-v1",
        "source_commit": "a" * 40,
    }
    execution_sha256 = canonical_sha256(execution)
    recipes: list[dict[str, object]] = []
    family_documents: list[dict[str, object]] = []
    for family_index in range(33):
        family_documents.append(
            {
                "goal_kind": f"goal-{family_index % 3}",
                "mechanic": "synthetic",
                "option_kind": f"option-{family_index % 3}",
                "schema": "pokemon.core.living-dex-transformation-family.v1",
                "semantic_parameters": {"family_index": family_index},
            }
        )
    provider_index = 0
    for recipe_index in range(15):
        option_kinds = ["option-0", "option-1", "option-2"]
        providers: list[dict[str, object]] = []
        for option_index, option_kind in enumerate(option_kinds):
            family = copy.deepcopy(family_documents[provider_index % 33])
            family["option_kind"] = option_kind
            family["goal_kind"] = f"goal-{option_index}"
            providers.append(
                {
                    "expected_family_sha256": canonical_sha256(family),
                    "family": family,
                    "goal_kind": f"goal-{option_index}",
                    "option_kind": option_kind,
                    "profile_sha256": _sha(f"profile-{provider_index}"),
                    "provider_configuration_sha256": _sha(
                        f"configuration-{provider_index}"
                    ),
                    "provider_contract_id": f"provider-{option_index}",
                    "route_recipe_sha256": (
                        None if provider_index % 2 == 0 else _sha(f"route-{provider_index}")
                    ),
                    "schema": "pokemon.red.private-living-dex-setup-provider-recipe.v2",
                }
            )
            provider_index += 1
        recipes.append(
            {
                "available_option_kinds": option_kinds,
                "base_boundary_sha256": _sha(f"base-{recipe_index}"),
                "construction_route_sha256": None,
                "origin_boundary_sha256": _sha(f"origin-{recipe_index % 10}"),
                "partition": "train" if recipe_index < 10 else "development",
                "providers": providers,
                "root_consumption_sha256": _sha(f"root-{recipe_index}"),
                "root_envelope_sha256": _sha(f"envelope-{recipe_index}"),
                "root_state_sha256": _sha(f"state-{recipe_index}"),
                "schema": "pokemon.red.private-living-dex-setup-slot-recipe.v2",
                "slot_sha256": _sha(f"slot-{recipe_index}"),
            }
        )
    recipe_plan: dict[str, object] = {
        "claim_before_controller_input": True,
        "execution_identity": execution,
        "execution_identity_sha256": execution_sha256,
        "learner_effects": 0,
        "prospective_plan_sha256": _sha("prospective"),
        "recipes": recipes,
        "retry_after_controller_input": False,
        "same_origin_fork_required": True,
        "schema": "pokemon.red.private-living-dex-setup-recipe-plan.v2",
    }
    recipe_plan_sha256 = canonical_sha256(recipe_plan)
    corridor_binding_sha256s = (_sha("corridor-0"), _sha("corridor-1"))
    effects = {
        "behavior_draws": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "learner_labels": 0,
        "learner_outcomes": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "provider_executions": 0,
        "root_claims": 0,
        "schema": "pokemon.core.red-living-dex-setup-protected-effects.v1",
        "teacher_queries": 0,
    }
    freeze: dict[str, object] = {
        "corridor_binding_sha256s": list(corridor_binding_sha256s),
        "effects_after": copy.deepcopy(effects),
        "effects_before": copy.deepcopy(effects),
        "recipe_plan_sha256": recipe_plan_sha256,
        "schema": "pokemon.red.private-living-dex-provider-plan-freeze.v1",
    }
    return recipe_plan, freeze, corridor_binding_sha256s


def _record() -> tuple[dict[str, object], SimpleNamespace]:
    recipe_plan, freeze, _corridors = _plan_and_freeze()
    execution = copy.deepcopy(recipe_plan["execution_identity"])
    assert isinstance(execution, dict)
    execution_sha256 = canonical_sha256(execution)
    recipe_plan_sha256 = canonical_sha256(recipe_plan)
    payload: dict[str, object] = {
        "context_catalog_sha256": _sha("catalog"),
        "context_plan_sha256": _sha("context-plan"),
        "controller_actions": 0,
        "emulator_frames": 0,
        "execution_identity": execution,
        "execution_identity_sha256": execution_sha256,
        "freeze": freeze,
        "freeze_sha256": canonical_sha256(freeze),
        "goal_registry_sha256": _sha("registry"),
        "model_fits": 0,
        "model_predictions": 0,
        "outcomes": 0,
        "provider_executions": 0,
        "recipe_plan": recipe_plan,
        "recipe_plan_sha256": recipe_plan_sha256,
        "root_claims": 0,
        "route_registry_sha256": _sha("routes"),
        "rom_sha256": POKEMON_RED_US_REV_0.sha256,
        "runtime_identity_sha256": _sha("runtime"),
        "schema": "pokemon.red.private-living-dex-provider-plan.v1",
        "source_catalog_partition_reused_as_prospective_label": False,
        "source_bundle_sha256": _sha("source"),
        "source_commit": "a" * 40,
        "status": "frozen_before_claim_controller_input_outcome_or_fit",
        "teacher_queries": 0,
    }
    private_plan_sha256 = canonical_sha256(payload)
    document = {**payload, "private_plan_sha256": private_plan_sha256}
    args = SimpleNamespace(
        expected_private_plan_sha256=private_plan_sha256,
        expected_plan_manifest_sha256=_sha("manifest"),
        expected_source_commit="a" * 40,
        expected_source_bundle_sha256=_sha("source"),
        expected_recipe_plan_sha256=recipe_plan_sha256,
        expected_execution_identity_sha256=execution_sha256,
    )
    return document, args


class _Sealed:
    def __init__(self, document: dict[str, object], manifest_sha256: str) -> None:
        self._document = document
        self.summary = SealedRecordSummary(
            record_id="red-living-dex-provider-plan-v1",
            kind="red-living-dex-provider-plan-v1",
            record_sha256=_sha("record"),
            manifest_sha256=manifest_sha256,
            total_bytes=100,
        )

    def read(self) -> dict[str, object]:
        return copy.deepcopy(self._document)


class _Store:
    def __init__(self, sealed: _Sealed | None) -> None:
        self.sealed = sealed

    def find_sealed_record(self, record_id: str, *, expected_kind: str):
        assert record_id == "red-living-dex-provider-plan-v1"
        assert expected_kind == "red-living-dex-provider-plan-v1"
        return self.sealed


def test_parser_exposes_precontroller_authentication_only() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_bridge_source_commit == "b" * 40
    assert parsed.expected_source_commit == "a" * 40
    assert parsed.exact_ci_run == 1234
    assert parsed.private_root == Path("/private/artifacts")
    for field in (
        "execute",
        "retry",
        "watch",
        "speed",
        "teacher",
        "fit",
        "predict",
    ):
        assert not hasattr(parsed, field)


def test_bridge_source_has_no_setup_or_learning_authority() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "CountingExecutor",
        "write_root_claim",
        "run_red_living_dex_setup_recipe_campaign",
        "CompletionFirstGoalTeacher",
        "issue_red_living_dex_behavior_commitment",
        "fit_red_living_dex",
        "_observe_candidates(",
        "_observe_supplemental_candidates(",
        "PyBoyAdapter(",
        "build_runtime_identity(",
        "require_pyboy_import_origins(",
        "site.addsitedir(",
        "import pyboy",
        ".press(",
        ".tick(",
        ".execute(",
    ):
        assert forbidden not in source
    assert SCRIPT["_FREEZER"] is None


def test_no_site_non_main_load_fails_before_project_import() -> None:
    code = f"""
import runpy
runpy.run_path({str(SCRIPT_PATH)!r}, run_name='isolated_setup_bridge')
"""
    completed = subprocess.run(
        (sys.executable, "-I", "-S", "-B", "-c", code),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "_BootstrapAuthenticationError" in completed.stderr
    assert "pokemon_red_completion" not in completed.stderr


def test_cli_bootstrap_fails_before_any_project_import() -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(SCRIPT_PATH),
            "--expected-bridge-source-commit",
            "b" * 40,
            "--expected-source-commit",
            "a" * 40,
            "--expected-source-bundle-sha256",
            "c" * 64,
        ),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    receipt = json.loads(completed.stdout)
    assert receipt["stage"] == "bootstrap_source_authentication"
    assert receipt["controller_actions"] == 0
    assert receipt["root_claims"] == 0
    assert "pokemon_red_completion" not in completed.stderr


@pytest.mark.parametrize(
    "mutation",
    (
        None,
        "head",
        "dirty",
        "remote",
        "source_byte",
        "workflow_byte",
        "script_inventory",
        "bridge_byte",
    ),
)
def test_bootstrap_cli_identity_crosses_the_authenticated_success_half(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str | None,
) -> None:
    project = tmp_path / "project"
    src = project / "src"
    scripts = project / "scripts"
    workflow_path = project / ".github/workflows/ci.yml"
    src.mkdir(parents=True)
    scripts.mkdir()
    workflow_path.parent.mkdir(parents=True)
    files = {
        "pyproject.toml": b"[project]\nname = 'fixture'\n",
        "src/package.py": b"VALUE = 1\n",
        "scripts/preflight_red_living_dex_setup_campaign.py": b"bridge\n",
        "scripts/helper.py": b"helper\n",
        ".github/workflows/ci.yml": b"name: CI\n",
    }
    for relative, payload in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    evidence_path = project / "canonical.json"
    plan_commit = "a" * 40
    bridge_commit = "b" * 40
    source_bundle = "c" * 64
    evidence_payload = json.dumps(
        {
            "publication": {
                "merged_main_commit": plan_commit,
                "source_bundle_sha256": source_bundle,
            }
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    evidence_path.write_bytes(evidence_payload)
    source_inventory = {"pyproject.toml", "src/package.py"}
    script_inventory = {
        "scripts/preflight_red_living_dex_setup_campaign.py",
        "scripts/helper.py",
    }
    queries: list[tuple[str, ...]] = []
    bridge_show_calls = 0

    def git_bytes(
        arguments: tuple[str, ...],
        *,
        maximum_bytes: int = 128 * 1024 * 1024,
    ) -> bytes:
        nonlocal bridge_show_calls
        del maximum_bytes
        queries.append(arguments)
        command = arguments[0]
        if command == "rev-parse":
            return (("d" * 40) if mutation == "head" else bridge_commit).encode() + b"\n"
        if command == "status":
            return b" M src/package.py\n" if mutation == "dirty" else b""
        if command == "for-each-ref":
            return b"" if mutation == "remote" else b"refs/remotes/origin/main\n"
        if command == "diff":
            return (
                b"A\tscripts/preflight_red_living_dex_setup_campaign.py\n"
                if arguments[-1] == "scripts"
                else b""
            )
        if command == "ls-tree":
            inventory = script_inventory if arguments[-1] == "scripts" else source_inventory
            return b"\0".join(
                relative.encode("ascii") for relative in sorted(inventory)
            ) + b"\0"
        assert command == "show"
        revision, relative = arguments[1].split(":", 1)
        assert revision in {plan_commit, bridge_commit}
        payload = files[relative]
        if mutation == "source_byte" and relative == "src/package.py":
            return b"VALUE = 2\n"
        if mutation == "workflow_byte" and relative == ".github/workflows/ci.yml":
            return b"name: Other\n"
        if relative == "scripts/preflight_red_living_dex_setup_campaign.py":
            bridge_show_calls += 1
            if mutation == "bridge_byte" and bridge_show_calls == 2:
                return b"changed bridge\n"
        return payload

    globals_ = SCRIPT["_bootstrap_cli_identity"].__globals__
    attribute_boundaries: list[str] = []
    monkeypatch.setitem(
        globals_,
        "sys",
        SimpleNamespace(
            flags=SimpleNamespace(
                dont_write_bytecode=1,
                isolated=1,
                no_site=1,
            )
        ),
    )
    monkeypatch.setitem(globals_, "PROJECT_ROOT", project)
    monkeypatch.setitem(globals_, "SRC_ROOT", src)
    monkeypatch.setitem(globals_, "SCRIPTS_ROOT", scripts)
    monkeypatch.setitem(
        globals_,
        "SCRIPT_PATH",
        project / "scripts/preflight_red_living_dex_setup_campaign.py",
    )
    monkeypatch.setitem(globals_, "_CANONICAL_EVIDENCE_PATH", evidence_path)
    monkeypatch.setitem(
        globals_,
        "_CANONICAL_EVIDENCE_SHA256",
        hashlib.sha256(evidence_payload).hexdigest(),
    )
    monkeypatch.setitem(globals_, "_BOOTSTRAP_ALLOWED_LOCAL_METADATA_SHA256", {})
    monkeypatch.setitem(
        globals_,
        "_authenticate_git_attribute_boundary",
        lambda: attribute_boundaries.append("attributes"),
    )
    monkeypatch.setitem(globals_, "_bootstrap_git_bytes", git_bytes)
    monkeypatch.setitem(
        globals_,
        "_bootstrap_filesystem_src_root_inventory",
        lambda *_args, **_kwargs: set(source_inventory),
    )
    monkeypatch.setitem(
        globals_,
        "_bootstrap_filesystem_script_inventory",
        lambda *_args, **_kwargs: (
            {"scripts/preflight_red_living_dex_setup_campaign.py"}
            if mutation == "script_inventory"
            else set(script_inventory)
        ),
    )
    argv = [
        "--expected-bridge-source-commit",
        bridge_commit,
        "--expected-source-commit",
        plan_commit,
        "--expected-source-bundle-sha256",
        source_bundle,
    ]

    if mutation is None:
        assert SCRIPT["_bootstrap_cli_identity"](argv) == (
            bridge_commit,
            plan_commit,
            source_bundle,
        )
        assert {query[0] for query in queries} == {
            "diff",
            "for-each-ref",
            "ls-tree",
            "rev-parse",
            "show",
            "status",
        }
        assert bridge_show_calls == 2
        assert attribute_boundaries == ["attributes"]
        status_queries = [query for query in queries if query[0] == "status"]
        assert status_queries == [
            (
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--ignore-submodules=all",
            )
        ]
    else:
        with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
            SCRIPT["_bootstrap_cli_identity"](argv)


def test_cli_bootstrap_requires_isolated_no_site_before_project_import() -> None:
    for invocation in (
        (sys.executable, str(SCRIPT_PATH), "--help"),
        (sys.executable, "-I", str(SCRIPT_PATH), "--help"),
        (sys.executable, "-S", str(SCRIPT_PATH), "--help"),
        (sys.executable, "-I", "-S", str(SCRIPT_PATH), "--help"),
    ):
        completed = subprocess.run(
            invocation,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        assert completed.returncode == 1
        assert (
            json.loads(completed.stdout)["stage"]
            == "bootstrap_source_authentication"
        )
        assert "pokemon_red_completion" not in completed.stderr


def test_isolated_help_exits_or_fails_closed_before_project_import() -> None:
    profile = subprocess.run(
        (
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import sys; print(sys.flags.int_max_str_digits)",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    completed = subprocess.run(
        (
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(SCRIPT_PATH),
            "--help",
        ),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    if profile.stdout.strip() == "4300":
        assert completed.returncode == 0
        assert completed.stdout == f"{SCRIPT['_BOOTSTRAP_USAGE']}\n"
    else:
        # Python 3.11 reports -1 here.  That foreign flag profile must fail
        # closed rather than weakening the pinned Python 3.14 production gate.
        assert profile.stdout.strip() == "-1"
        assert completed.returncode == 1
        assert (
            json.loads(completed.stdout)["stage"]
            == "bootstrap_source_authentication"
        )
    assert "pokemon_red_completion" not in completed.stderr


@pytest.mark.parametrize(
    "extra_flags",
    (
        ("-O",),
        ("-W", "error"),
        ("-X", "dev"),
        ("-X", "importtime"),
        ("-X", "pycache_prefix=/tmp/untrusted-bridge-cache"),
    ),
)
def test_cli_rejects_extra_semantic_or_cache_flags_before_project_import(
    extra_flags: tuple[str, ...],
) -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-I",
            "-S",
            "-B",
            *extra_flags,
            str(SCRIPT_PATH),
            "--help",
        ),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["stage"] == "bootstrap_source_authentication"
    assert "pokemon_red_completion" not in completed.stderr


def test_post_bootstrap_import_failure_is_one_path_free_receipt() -> None:
    code = f"""
import runpy
namespace = runpy.run_path({str(SCRIPT_PATH)!r}, run_name='bridge_import_failure_test')
namespace['_install_post_bootstrap_failure_boundary']()
raise RuntimeError('/private/should-never-appear')
"""
    completed = subprocess.run(
        (sys.executable, "-c", code),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stderr == ""
    assert completed.stdout.count("\n") == 1
    receipt = json.loads(completed.stdout)
    assert receipt["stage"] == "project_import_authentication"
    assert receipt["controller_actions"] == 0
    assert receipt["root_claims"] == 0
    assert "/private/should-never-appear" not in completed.stdout
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    install_at = source.index("        _install_post_bootstrap_failure_boundary()")
    first_project_import_at = source.index(
        "from pokemon_red_completion.constants import POKEMON_RED_US_REV_0"
    )
    release_at = source.rindex("    _release_post_bootstrap_failure_boundary()")
    assert install_at < first_project_import_at < release_at


def test_dependency_metadata_bootstrap_requires_a_direct_base_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    metadata_root = project / ".venv/lib/python3.14/site-packages"
    metadata_root.mkdir(parents=True)
    prefix = tmp_path / "base"
    executable = prefix / "bin/python3.14"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture-base-python\n")
    executable.chmod(0o755)
    stdlib = prefix / "lib/python3.14"
    stdlib.mkdir(parents=True)
    fake_sys = SimpleNamespace(
        _base_executable=str(executable),
        base_exec_prefix=str(prefix),
        base_prefix=str(prefix),
        exec_prefix=str(prefix),
        executable=str(executable),
        flags=SimpleNamespace(
            dont_write_bytecode=1,
            isolated=1,
            no_site=1,
        ),
        modules={},
        path=[str(stdlib)],
        prefix=str(prefix),
    )
    globals_ = SCRIPT["_bootstrap_dependency_metadata_roots"].__globals__
    monkeypatch.setitem(globals_, "sys", fake_sys)
    monkeypatch.setitem(globals_, "PROJECT_ROOT", project)
    monkeypatch.setitem(globals_, "_BOOTSTRAP_BASE_PREFIX", prefix)
    monkeypatch.setitem(globals_, "_BOOTSTRAP_PYTHON_EXECUTABLE", executable)
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_PYTHON_EXECUTABLE_SHA256",
        hashlib.sha256(executable.read_bytes()).hexdigest(),
    )
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_DEPENDENCY_METADATA_ROOT",
        metadata_root,
    )

    assert SCRIPT["_bootstrap_dependency_metadata_roots"]() == (metadata_root,)
    fake_sys.prefix = str(project / ".venv")
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_bootstrap_dependency_metadata_roots"]()


def test_disposable_venv_proves_no_site_blocks_pth_startup_hooks(
    tmp_path: Path,
) -> None:
    environment = tmp_path / "hook-environment"
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / "bin/python"
    purelib = Path(
        subprocess.run(
            (
                str(python),
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    sentinel = tmp_path / "pth-hook-ran"
    hook = purelib / "pre_bridge_hook.pth"
    hook.write_text(
        "import pathlib; pathlib.Path("
        f"{str(sentinel)!r}"
        ").write_text('ran', encoding='ascii')\n",
        encoding="ascii",
    )

    subprocess.run((str(python), "-c", "pass"), check=True)
    assert sentinel.read_text(encoding="ascii") == "ran"
    sentinel.unlink()
    # Whether -I alone re-enters a venv site directory differs between the
    # supported Python 3.14 runtime and CI's Python 3.11.  The cross-version
    # security invariant is that -S prevents the startup hook.
    subprocess.run((str(python), "-I", "-S", "-B", "-c", "pass"), check=True)
    assert not sentinel.exists()


def test_cli_rejects_openssl_loader_environment_before_project_import(
    tmp_path: Path,
) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("OPENSSL_") and key not in {"CTLOG_FILE", "RANDFILE"}
    }
    environment["OPENSSL_MODULES"] = str(tmp_path / "untrusted-modules")
    completed = subprocess.run(
        (sys.executable, "-I", "-S", "-B", str(SCRIPT_PATH), "--help"),
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["stage"] == "bootstrap_source_authentication"
    assert "pokemon_red_completion" not in completed.stderr


def test_git_children_use_one_minimal_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_bootstrap_git_bytes"].__globals__
    observed: list[dict[str, object]] = []

    def run(*args: object, **kwargs: object) -> SimpleNamespace:
        observed.append({"args": args, **kwargs})
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setitem(
        globals_,
        "_bootstrap_require_executable",
        lambda _path, *, expected_sha256, require_root_owned_path: Path("/usr/bin/git"),
    )
    monkeypatch.setitem(globals_, "_bootstrap_git_directory", lambda: Path("/git-dir"))
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED",
        True,
    )
    monkeypatch.setitem(globals_, "subprocess", SimpleNamespace(run=run, SubprocessError=OSError))
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "/untrusted/dylib")
    monkeypatch.setenv("LD_PRELOAD", "/untrusted/preload")
    monkeypatch.setenv("BASH_ENV", "/untrusted/shell-hook")
    monkeypatch.setenv("DEVELOPER_DIR", "/untrusted/developer-tools")

    assert SCRIPT["_bootstrap_git_bytes"](("status", "--porcelain")) == b""
    assert SCRIPT["_run_git_bytes"](("show", "HEAD:file")) == b""

    expected = SCRIPT["_minimal_git_environment"]()
    assert expected["GIT_NO_LAZY_FETCH"] == "1"
    assert (
        "core.attributesFile=/dev/null"
        in globals_["_BOOTSTRAP_GIT_CONFIG_OVERRIDES"]
    )
    assert len(observed) == 2
    assert all(call["env"] == expected for call in observed)
    environments = [cast(dict[str, str], call["env"]) for call in observed]
    assert all("DYLD_INSERT_LIBRARIES" not in environment for environment in environments)
    assert all("LD_PRELOAD" not in environment for environment in environments)
    assert all("BASH_ENV" not in environment for environment in environments)
    assert all("DEVELOPER_DIR" not in environment for environment in environments)


@pytest.mark.skipif(
    sys.platform != "darwin"
    or not Path("/Library/Developer/CommandLineTools/usr/bin/git").exists(),
    reason="exact local Mac Git qualification",
)
def test_exact_local_mac_git_binds_the_implementation_not_the_selector() -> None:
    executable = SCRIPT["_BOOTSTRAP_GIT_EXECUTABLE"]

    assert executable == Path("/Library/Developer/CommandLineTools/usr/bin/git")
    assert executable != Path("/usr/bin/git")
    assert (
        SCRIPT["_bootstrap_require_executable"](
            executable,
            expected_sha256=SCRIPT["_BOOTSTRAP_GIT_EXECUTABLE_SHA256"],
            require_root_owned_path=True,
        )
        == executable
    )


def test_hardened_git_ignores_fsmonitor_and_core_worktree_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_executable = _bind_test_host_git(monkeypatch)
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            (str(git_executable), *arguments),
            cwd=repository,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    tracked = repository / "tracked.txt"
    tracked.write_text("frozen\n", encoding="ascii")
    git("add", "tracked.txt")
    git(
        "-c",
        "user.name=Bridge Test",
        "-c",
        "user.email=bridge@example.invalid",
        "commit",
        "-qm",
        "freeze",
    )
    sentinel = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor-hook"
    hook.write_text(
        "#!/bin/sh\n"
        f"printf ran > {str(sentinel)!r}\n"
        "printf 'token\\n'\n",
        encoding="ascii",
    )
    hook.chmod(0o700)
    git("config", "core.fsmonitor", str(hook))
    git("status", "--porcelain")
    assert sentinel.read_text(encoding="ascii") == "ran"
    sentinel.unlink()
    git("config", "--unset", "core.fsmonitor")

    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "tracked.txt").write_text("frozen\n", encoding="ascii")
    git("config", "core.worktree", str(decoy))
    tracked.write_text("changed\n", encoding="ascii")
    assert git("status", "--porcelain").stdout == b""

    globals_ = SCRIPT["_bootstrap_git_bytes"].__globals__
    monkeypatch.setitem(globals_, "PROJECT_ROOT", repository)
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_PROJECT_GIT_CONFIG_OVERRIDES",
        (
            "-c",
            "core.bare=false",
            *globals_["_BOOTSTRAP_GIT_CONFIG_OVERRIDES"],
            "-c",
            f"core.worktree={repository}",
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_bootstrap_git_directory",
        lambda: repository / ".git",
    )
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED",
        True,
    )
    status = SCRIPT["_bootstrap_git_bytes"](
        ("status", "--porcelain", "--untracked-files=all")
    )

    assert b"tracked.txt" in status
    assert not sentinel.exists()


def test_git_attribute_filters_and_info_attributes_fail_before_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_executable = _bind_test_host_git(monkeypatch)
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            (str(git_executable), *arguments),
            cwd=repository,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    tracked = repository / "tracked.py"
    tracked.write_text("VALUE = 1\n", encoding="ascii")
    git("add", "tracked.py")
    git(
        "-c",
        "user.name=Bridge Test",
        "-c",
        "user.email=bridge@example.invalid",
        "commit",
        "-qm",
        "freeze",
    )
    sentinel = tmp_path / "filter-ran"
    filter_program = tmp_path / "clean-filter"
    filter_program.write_text(
        "#!/bin/sh\n"
        f"touch {str(sentinel)!r}\n"
        "cat\n",
        encoding="ascii",
    )
    filter_program.chmod(0o700)
    (repository / ".gitattributes").write_text(
        "*.py filter=probe\n",
        encoding="ascii",
    )
    git("config", "filter.probe.clean", str(filter_program))
    tracked.write_text("VALUE = 2\n", encoding="ascii")
    git("status", "--porcelain")
    assert sentinel.read_text(encoding="ascii") == ""
    sentinel.unlink()

    globals_ = SCRIPT["_bootstrap_git_bytes"].__globals__
    monkeypatch.setitem(globals_, "PROJECT_ROOT", repository)
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_PROJECT_GIT_CONFIG_OVERRIDES",
        (
            "-c",
            "core.bare=false",
            *globals_["_BOOTSTRAP_GIT_CONFIG_OVERRIDES"],
            "-c",
            f"core.worktree={repository}",
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_bootstrap_git_directory",
        lambda: repository / ".git",
    )
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_authenticate_git_attribute_boundary"]()
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_bootstrap_git_bytes"](("status", "--porcelain"))
    assert not sentinel.exists()

    (repository / ".gitattributes").unlink()
    mixed_case_attributes = repository / ".GITATTRIBUTES"
    mixed_case_attributes.write_text("*.py filter=probe\n", encoding="ascii")
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_authenticate_git_attribute_boundary"]()
    mixed_case_attributes.unlink()

    attribute_blob = subprocess.run(
        (str(git_executable), "hash-object", "-w", "--stdin"),
        cwd=repository,
        input=b"*.py filter=probe\n",
        check=True,
        capture_output=True,
    ).stdout.decode("ascii").strip()
    git(
        "update-index",
        "--add",
        "--cacheinfo",
        f"100644,{attribute_blob},.gitattributes",
    )
    assert not (repository / ".gitattributes").exists()
    git("status", "--porcelain")
    assert sentinel.exists()
    sentinel.unlink()
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_authenticate_git_attribute_boundary"]()
    assert not sentinel.exists()
    git("update-index", "--force-remove", ".gitattributes")

    info_attributes = repository / ".git/info/attributes"
    info_attributes.write_text("*.py filter=probe\n", encoding="ascii")
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_authenticate_git_attribute_boundary"]()
    assert not sentinel.exists()

    info_attributes.unlink()
    linked_git_directory = repository / ".git/worktrees/linked"
    linked_git_directory.mkdir(parents=True)
    (linked_git_directory / "commondir").write_text("../..\n", encoding="ascii")
    monkeypatch.setitem(
        globals_,
        "_bootstrap_git_directory",
        lambda: linked_git_directory,
    )
    assert (
        SCRIPT["_bootstrap_git_common_directory"](linked_git_directory)
        == repository / ".git"
    )
    info_attributes.write_text("*.py filter=probe\n", encoding="ascii")
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_authenticate_git_attribute_boundary"]()
    assert not sentinel.exists()


def test_private_root_probe_is_hardened_and_detects_other_worktrees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_executable = _bind_test_host_git(monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    assert SCRIPT["_hardened_git_worktree_probe"](outside) is False

    repository = tmp_path / "other-repository"
    repository.mkdir()
    subprocess.run(
        (str(git_executable), "init", "-q"),
        cwd=repository,
        check=True,
    )
    nested = repository / "private-looking-subdirectory"
    nested.mkdir()
    assert SCRIPT["_hardened_git_worktree_probe"](nested) is True
    (repository / ".git/config").write_text("[malformed\n", encoding="ascii")
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="private_namespace_authentication",
    ):
        SCRIPT["_hardened_git_worktree_probe"](nested)


def test_runtime_identity_uses_only_one_exact_fixture_metadata_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_build_stdlib_runtime_identity"].__globals__
    dependency_root = tmp_path / "site-packages"
    metadata_root = dependency_root / "pyboy-2.7.0.dist-info"
    package_root = dependency_root / "pyboy"
    (metadata_root / "licenses").mkdir(parents=True)
    package_root.mkdir()
    package_file = package_root / "__init__.py"
    package_file.write_bytes(b"class PyBoy: pass\n")
    metadata_payloads = {
        "INSTALLER": b"fixture\n",
        "METADATA": b"Metadata-Version: 2.1\nName: pyboy\nVersion: 2.7.0\n\n",
        "WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: fixture\n"
            b"Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        "entry_points.txt": b"",
        "licenses/LICENSE.md": b"fixture license\n",
        "top_level.txt": b"pyboy\n",
    }
    record_names = [
        "pyboy/__init__.py",
        *(
            f"pyboy-2.7.0.dist-info/{relative}"
            for relative in (*metadata_payloads, "RECORD")
        ),
    ]
    metadata_payloads["RECORD"] = "".join(
        f"{name},,\n" for name in record_names
    ).encode("ascii")
    for relative, payload in metadata_payloads.items():
        path = metadata_root / relative
        path.write_bytes(payload)
    executable = tmp_path / "python"
    executable.write_bytes(b"fixture-python-executable\n")
    executable.chmod(0o755)

    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_DEPENDENCY_METADATA_ROOTS",
        (dependency_root,),
    )
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_PYBOY_METADATA_SHA256",
        {
            relative: hashlib.sha256(payload).hexdigest()
            for relative, payload in metadata_payloads.items()
        },
    )
    monkeypatch.setitem(
        globals_,
        "sys",
        SimpleNamespace(executable=str(executable), modules=sys.modules),
    )
    monkeypatch.setitem(
        globals_,
        "platform",
        SimpleNamespace(
            python_implementation=lambda: "CPython",
            python_version=lambda: "3.14.3",
        ),
    )
    monkeypatch.setitem(globals_, "_require_no_third_party_execution", lambda: None)
    monkeypatch.setattr(
        globals_["importlib_metadata"],
        "distributions",
        lambda **_kwargs: pytest.fail("global distribution scan is forbidden"),
    )
    before = {
        name
        for name in sys.modules
        if name.split(".")[0] in {"pyboy", "PIL", "sdl2", "sdl2dll"}
    }

    first = SCRIPT["_build_stdlib_runtime_identity"]()
    second = SCRIPT["_build_stdlib_runtime_identity"]()

    after = {
        name
        for name in sys.modules
        if name.split(".")[0] in {"pyboy", "PIL", "sdl2", "sdl2dll"}
    }
    assert first == second
    assert len(first.sha256) == 64
    assert len(first.pyboy_files) == len(record_names)
    assert first.pyboy_distribution_version == "2.7.0"
    assert after == before


@pytest.mark.skipif(
    sys.platform != "darwin"
    or not Path(
        "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
        "Python.framework/Versions/3.14/bin/python3.14"
    ).exists(),
    reason="exact local Mac runtime qualification",
)
def test_exact_local_mac_runtime_identity_qualification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_build_stdlib_runtime_identity"].__globals__
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_DEPENDENCY_METADATA_ROOTS",
        (PROJECT_ROOT / ".venv/lib/python3.14/site-packages",),
    )
    monkeypatch.setitem(globals_, "_require_no_third_party_execution", lambda: None)

    identity = SCRIPT["_build_stdlib_runtime_identity"]()

    assert identity.sha256 == (
        "028fc1935cdaa31f2a749ff85a3ba43d24a805c8219aa6c45b843ee0637147f4"
    )
    assert len(identity.pyboy_files) == 170


def test_pyboy_metadata_authentication_never_opens_unrelated_distributions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_root = tmp_path / "pyboy-2.7.0.dist-info"
    (metadata_root / "licenses").mkdir(parents=True)
    payloads = {
        "INSTALLER": b"test\n",
        "METADATA": b"Metadata-Version: 2.1\nName: pyboy\nVersion: 2.7.0\n\n",
        "RECORD": b"",
        "WHEEL": b"Wheel-Version: 1.0\n",
        "entry_points.txt": b"",
        "licenses/LICENSE.md": b"license\n",
        "top_level.txt": b"pyboy\n",
    }
    for relative, payload in payloads.items():
        path = metadata_root / relative
        path.write_bytes(payload)
    unrelated = tmp_path / "unrelated-1.0.dist-info"
    unrelated.mkdir()
    fifo = unrelated / "METADATA"
    os.mkfifo(fifo)

    globals_ = SCRIPT["_stdlib_pyboy_distribution"].__globals__
    monkeypatch.setitem(globals_, "_BOOTSTRAP_DEPENDENCY_METADATA_ROOTS", (tmp_path,))
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_PYBOY_METADATA_SHA256",
        {relative: hashlib.sha256(payload).hexdigest() for relative, payload in payloads.items()},
    )
    monkeypatch.setitem(globals_, "_require_no_third_party_execution", lambda: None)

    distribution = SCRIPT["_stdlib_pyboy_distribution"]()

    assert distribution.metadata["Name"] == "pyboy"
    assert fifo.exists()
    (tmp_path / "PyBoy-shadow.dist-info").mkdir()
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="runtime_identity_authentication",
    ):
        SCRIPT["_stdlib_pyboy_distribution"]()


def test_hardened_registry_loader_matches_the_canonical_public_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bind_test_host_git(monkeypatch)
    monkeypatch.setitem(
        SCRIPT["_run_git_bytes"].__globals__,
        "_BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED",
        True,
    )
    commit = "69a0c707006c78ae8473544f40e2bdd0a0b23f91"
    expected_bundle = (
        "56789cd96fcad437c25b9706eb390a929fcc04db0ad2b99c2180cb2e5821f5df"
    )

    assert SCRIPT["_committed_source_bundle_sha256"](commit) == expected_bundle
    hardened = SCRIPT["_load_committed_goal_manager_registry_at_revision"](
        PROJECT_ROOT,
        commit,
    )
    original = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        commit,
    )

    assert hardened == original
    assert hardened.registry_sha256 == (
        "a6845e154974e3a0520403520ae0921b799f627ba5ee6620d2b0035592a17322"
    )
    assert hardened.execution.source_bundle_sha256 == expected_bundle


def test_hardened_source_bundle_distinguishes_listing_and_blob_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_committed_source_bundle_sha256"].__globals__
    commit = "a" * 40
    pyproject_oid = "1" * 40
    source_oid = "2" * 40
    payloads = {
        pyproject_oid: b"[project]\n",
        source_oid: b"VALUE = 1\n",
    }
    listing = (
        f"100644 blob {pyproject_oid}\tpyproject.toml\0"
        f"100644 blob {source_oid}\tsrc/pokemon_red_completion/example.py\0"
    ).encode("ascii")

    def git_bytes(
        arguments: tuple[str, ...],
        *,
        maximum_bytes: int = 4_000_000,
    ) -> bytes:
        del maximum_bytes
        if arguments[0] == "rev-parse":
            return f"{commit}\n".encode("ascii")
        if arguments[0] == "ls-tree":
            return listing
        oid = arguments[-1]
        if arguments[:2] == ("cat-file", "-s"):
            return f"{len(payloads[oid])}\n".encode("ascii")
        assert arguments[:2] == ("cat-file", "blob")
        return payloads[oid]

    monkeypatch.setitem(globals_, "_run_git_bytes", git_bytes)
    baseline = SCRIPT["_committed_source_bundle_sha256"](commit)
    payloads[source_oid] = b"VALUE = 2\n"
    assert SCRIPT["_committed_source_bundle_sha256"](commit) != baseline
    payloads[source_oid] = b"VALUE = 1\n"
    duplicate_listing = listing + (
        f"100644 blob {source_oid}\tsrc/pokemon_red_completion/example.py\0"
    ).encode("ascii")
    listing = duplicate_listing
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="private_input_authentication",
    ):
        SCRIPT["_committed_source_bundle_sha256"](commit)


def test_bootstrap_rejects_a_preseeded_cache_prefix_without_creating_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_fresh_unused_pycache_prefix"].__globals__
    nonce = b"\x8a" * 32
    candidate = PROJECT_ROOT / f".bridge-pycache-{nonce.hex()}"
    monkeypatch.setattr(globals_["os"], "urandom", lambda _size: nonce)

    assert not candidate.exists()
    assert SCRIPT["_fresh_unused_pycache_prefix"]() == candidate
    assert not candidate.exists()
    candidate.mkdir()
    try:
        (candidate / "malicious.pyc").write_bytes(b"preseeded")
        with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
            SCRIPT["_fresh_unused_pycache_prefix"]()
    finally:
        (candidate / "malicious.pyc").unlink()
        candidate.rmdir()


def test_bootstrap_rejects_every_top_level_src_shadow(
    tmp_path: Path,
) -> None:
    expected = {"src/pokemon_red_completion/constants.py"}
    metadata_payload = b"authenticated-project-metadata"
    allowed_metadata = {
        "src/pokemon_red_completion_agent.egg-info/PKG-INFO": hashlib.sha256(
            metadata_payload
        ).hexdigest()
    }

    def source_root(case: str) -> tuple[Path, Path, Path]:
        root = tmp_path / case
        src = root / "src"
        package = src / "pokemon_red_completion"
        package.mkdir(parents=True)
        (package / "constants.py").write_text("VALUE = 1\n", encoding="ascii")
        cache = package / "__pycache__"
        cache.mkdir()
        (cache / "constants.cpython-314.pyc").write_bytes(b"ordinary-cache")
        metadata = src / "pokemon_red_completion_agent.egg-info"
        metadata.mkdir()
        (metadata / "PKG-INFO").write_bytes(metadata_payload)
        (src / ".DS_Store").write_bytes(b"non-importable-metadata")
        return root, src, package

    root, src, _package = source_root("baseline")
    assert SCRIPT["_bootstrap_filesystem_src_root_inventory"](
        root,
        src,
        expected,
        allowed_local_metadata_sha256=allowed_metadata,
    ) == expected

    (src / "pokemon_red_completion_agent.egg-info/PKG-INFO").write_bytes(
        b"mutated-project-metadata"
    )
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_bootstrap_filesystem_src_root_inventory"](
            root,
            src,
            expected,
            allowed_local_metadata_sha256=allowed_metadata,
        )

    for case, relative in (
        ("direct-pyc", Path("pyboy.pyc")),
        ("package-pyc", Path("pyboy/__init__.pyc")),
        ("metadata-shadow", Path("pyboy.egg-info/PKG-INFO")),
        ("tracked-name-package", Path("pokemon_red_completion/constants/__init__.pyc")),
    ):
        root, src, _package = source_root(case)
        shadow = src / relative
        shadow.parent.mkdir(parents=True, exist_ok=True)
        shadow.write_bytes(b"sourceless-shadow")
        with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
            SCRIPT["_bootstrap_filesystem_src_root_inventory"](
                root,
                src,
                expected,
                allowed_local_metadata_sha256=allowed_metadata,
            )


def test_bootstrap_rejects_sourceless_script_module_shadows(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "helper.py").write_text("VALUE = 1\n", encoding="ascii")
    (scripts / ".DS_Store").write_bytes(b"non-importable-metadata")
    cache = scripts / "__pycache__"
    cache.mkdir()
    (cache / "helper.cpython-314.pyc").write_bytes(b"ordinary-cache")

    assert SCRIPT["_bootstrap_filesystem_script_inventory"](
        tmp_path,
        scripts,
    ) == {"scripts/helper.py"}

    shadow = scripts / "helper"
    shadow.mkdir()
    (shadow / "__init__.pyc").write_bytes(b"sourceless-shadow")
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_bootstrap_filesystem_script_inventory"](tmp_path, scripts)


def test_exact_green_ci_requires_one_successful_push_for_the_bridge_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_require_exact_green_ci_run"].__globals__
    document = {
        "conclusion": "success",
        "event": "push",
        "head_sha": "b" * 40,
        "html_url": (
            "https://github.com/PeteAndrews1289/"
            "pokemon-red-completion-agent/actions/runs/1234"
        ),
        "id": 1234,
        "name": "CI",
        "path": ".github/workflows/ci.yml",
        "repository": {
            "full_name": "PeteAndrews1289/pokemon-red-completion-agent"
        },
        "run_attempt": 1,
        "status": "completed",
    }
    monkeypatch.setitem(
        globals_,
        "_fetch_github_json",
        lambda _url: document,
    )

    authenticated = SCRIPT["_require_exact_green_ci_run"](
        1234,
        1,
        source_commit="b" * 40,
    )

    assert authenticated["headSha"] == "b" * 40
    document["event"] = "pull_request"
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="bridge_ci_authentication",
    ):
        SCRIPT["_require_exact_green_ci_run"](
            1234,
            1,
            source_commit="b" * 40,
        )
    document["event"] = "push"
    document["path"] = ".github/workflows/other.yml"
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="bridge_ci_authentication",
    ):
        SCRIPT["_require_exact_green_ci_run"](
            1234,
            1,
            source_commit="b" * 40,
        )


def test_github_transport_supports_two_identity_pinned_fetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_fetch_github_json"].__globals__
    ca_bytes = b"pinned-ca"
    url = (
        "https://api.github.com/repos/PeteAndrews1289/"
        "pokemon-red-completion-agent/actions/runs/1234/attempts/1"
    )
    opens = 0

    class Context:
        check_hostname = False
        verify_mode = 0

        def load_verify_locations(self, *, cadata: str) -> None:
            assert cadata == ca_bytes.decode("ascii")

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def getcode(self) -> int:
            return 200

        def geturl(self) -> str:
            return url

        def read(self, _maximum: int) -> bytes:
            return b'{"id":1234}'

    class Opener:
        def open(self, _request: object, *, timeout: int) -> Response:
            nonlocal opens
            assert timeout == 30
            opens += 1
            return Response()

    class RedirectHandler:
        pass

    request_module = SimpleNamespace(
        HTTPRedirectHandler=RedirectHandler,
        HTTPSHandler=lambda **_kwargs: object(),
        ProxyHandler=lambda value: ("proxy", value),
        Request=lambda *args, **kwargs: (args, kwargs),
        build_opener=lambda *_handlers: Opener(),
    )
    ssl_module = SimpleNamespace(
        CERT_REQUIRED=2,
        PROTOCOL_TLS_CLIENT=16,
        SSLContext=lambda _protocol: Context(),
    )
    monkeypatch.setitem(globals_, "_secure_https_modules", lambda: (ssl_module, request_module))
    monkeypatch.setitem(globals_, "_bootstrap_read_regular", lambda *_a, **_k: ca_bytes)
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_CA_BUNDLE_SHA256",
        hashlib.sha256(ca_bytes).hexdigest(),
    )

    assert SCRIPT["_fetch_github_json"](url)["id"] == 1234
    assert SCRIPT["_fetch_github_json"](url)["id"] == 1234
    assert opens == 2


def test_external_executables_are_exact_byte_bound(tmp_path: Path) -> None:
    executable = tmp_path / "tool"
    executable.write_bytes(b"exact-tool-bytes")
    executable.chmod(0o755)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()

    assert (
        SCRIPT["_bootstrap_require_executable"](
            executable,
            expected_sha256=digest,
        )
        == executable
    )
    executable.write_bytes(b"replacement-tool")
    with pytest.raises(SCRIPT["_BootstrapAuthenticationError"]):
        SCRIPT["_bootstrap_require_executable"](
            executable,
            expected_sha256=digest,
        )


def test_canonical_evidence_anchors_private_plan_and_freeze_source() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())
    parsed.expected_private_plan_sha256 = (
        "b555dfb61fb90f7741cca9e93bf60a4f98b94ee485e8832ff419359fdb3a2bcc"
    )
    parsed.expected_plan_manifest_sha256 = (
        "3bb930568edbf47899e362f1904237967837d18fc167e1d95285a46ca06b4816"
    )
    parsed.expected_source_commit = "69a0c707006c78ae8473544f40e2bdd0a0b23f91"
    parsed.expected_source_bundle_sha256 = (
        "56789cd96fcad437c25b9706eb390a929fcc04db0ad2b99c2180cb2e5821f5df"
    )

    evidence = SCRIPT["_authenticate_canonical_evidence"](parsed)

    assert evidence["slot_count"] == 15
    parsed.expected_private_plan_sha256 = _sha("replacement")
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="canonical_evidence_authentication",
    ):
        SCRIPT["_authenticate_canonical_evidence"](parsed)


def test_bridge_source_keeps_frozen_bundle_while_binding_new_published_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())
    globals_ = SCRIPT["_authenticate_bridge_source"].__globals__
    events: list[str] = []
    monkeypatch.setitem(
        globals_,
        "_require_project_import_origins",
        lambda: events.append("origins"),
    )
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_IDENTITY",
        ("b" * 40, "a" * 40, _sha("source")),
    )
    def bootstrap(_argv: object) -> tuple[str, str, str]:
        events.append("bootstrap")
        return "b" * 40, "a" * 40, _sha("source")

    monkeypatch.setitem(globals_, "_bootstrap_cli_identity", bootstrap)
    monkeypatch.setitem(
        globals_,
        "_authenticate_frozen_script_closure",
        lambda **_kwargs: (_sha("freezer"), _sha("authentication-support")),
    )

    binding = SCRIPT["_authenticate_bridge_source"](parsed)

    assert binding.bridge_source_commit == "b" * 40
    assert len(binding.bridge_script_sha256) == 64
    assert binding.freezer_script_sha256 == _sha("freezer")
    assert events == ["origins", "bootstrap"]
    monkeypatch.setitem(
        globals_,
        "_bootstrap_cli_identity",
        lambda _argv: ("b" * 40, "a" * 40, _sha("drift")),
    )
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="bridge_source_authentication",
    ):
        SCRIPT["_authenticate_bridge_source"](parsed)


def test_project_import_origin_gate_rejects_preloaded_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_require_project_import_origins"].__globals__
    monkeypatch.setitem(globals_, "_PRELOADED_PROJECT_MODULES", ())
    SCRIPT["_require_project_import_origins"]()
    monkeypatch.setitem(
        globals_,
        "_PRELOADED_PROJECT_MODULES",
        ("pokemon_red_completion.injected",),
    )
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="project_import_authentication",
    ):
        SCRIPT["_require_project_import_origins"]()


def test_frozen_script_closure_binds_exact_original_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_authenticate_frozen_script_closure"].__globals__
    freezer = globals_["_FREEZER_SCRIPT_PATH"].read_bytes()
    authentication = globals_["_AUTHENTICATION_SUPPORT_SCRIPT_PATH"].read_bytes()

    def git_bytes(arguments: tuple[str, ...]) -> bytes:
        if arguments[0] == "diff":
            return globals_["_EXPECTED_SCRIPT_DELTA"].encode("utf-8")
        assert arguments[0] == "show"
        return authentication if "multifamily" in arguments[1] else freezer

    monkeypatch.setitem(globals_, "_run_git_bytes", git_bytes)
    digests = SCRIPT["_authenticate_frozen_script_closure"](
        plan_commit="a" * 40,
        bridge_commit="b" * 40,
    )
    assert digests == (
        hashlib.sha256(freezer).hexdigest(),
        hashlib.sha256(authentication).hexdigest(),
    )
    monkeypatch.setitem(
        globals_,
        "_run_git_bytes",
        lambda arguments: (
            globals_["_EXPECTED_SCRIPT_DELTA"].encode("utf-8")
            if arguments[0] == "diff"
            else b"changed"
        ),
    )
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="frozen_script_support_authentication",
    ):
        SCRIPT["_authenticate_frozen_script_closure"](
            plan_commit="a" * 40,
            bridge_commit="b" * 40,
        )


def test_frozen_support_loads_only_after_digest_and_origin_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_load_freezer_support"].__globals__
    binding = SCRIPT["_BridgeSourceBinding"](
        "b" * 40,
        _sha("bridge"),
        _sha("freezer"),
        _sha("authentication"),
    )
    events: list[str] = []
    monkeypatch.setitem(globals_, "_FREEZER", None)
    monkeypatch.setitem(globals_, "_FREEZER_BINDING", None)

    def digests() -> tuple[str, str]:
        events.append("digests")
        return binding.freezer_script_sha256, binding.authentication_support_script_sha256

    loaded = {
        "PLAN_RECORD_ID": "red-living-dex-provider-plan-v1",
        "PLAN_RECORD_KIND": "red-living-dex-provider-plan-v1",
        "_authenticate_inputs": lambda *_a, **_k: None,
        "_authenticate_supplemental_roots": lambda *_a, **_k: None,
    }
    monkeypatch.setitem(globals_, "_current_frozen_script_digests", digests)
    def load_support(*_args: object, **_kwargs: object) -> dict[str, object]:
        events.append("runpy")
        return loaded

    monkeypatch.setitem(
        globals_,
        "runpy",
        SimpleNamespace(run_path=load_support),
    )
    monkeypatch.setitem(
        globals_,
        "_require_project_import_origins",
        lambda: events.append("project-origins"),
    )
    monkeypatch.setitem(
        globals_,
        "_require_script_import_origins",
        lambda: events.append("script-origins"),
    )

    SCRIPT["_load_freezer_support"](binding)

    assert events == [
        "digests",
        "runpy",
        "digests",
        "project-origins",
        "script-origins",
    ]
    monkeypatch.setitem(globals_, "_FREEZER", None)
    monkeypatch.setitem(globals_, "_FREEZER_BINDING", None)
    events.clear()
    monkeypatch.setitem(
        globals_,
        "_current_frozen_script_digests",
        lambda: (_sha("changed"), binding.authentication_support_script_sha256),
    )
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="frozen_script_support_authentication",
    ):
        SCRIPT["_load_freezer_support"](binding)
    assert "runpy" not in events


def test_immutable_record_binds_every_nested_plan_identity() -> None:
    document, args = _record()
    store = _Store(_Sealed(document, args.expected_plan_manifest_sha256))

    restored, summary = SCRIPT["_authenticate_plan_record"](store, args)

    assert restored == document
    assert summary.manifest_sha256 == args.expected_plan_manifest_sha256


@pytest.mark.parametrize(
    "mutate",
    (
        lambda document: document.__setitem__("root_claims", 1),
        lambda document: document.__setitem__("status", "executed"),
        lambda document: document.__setitem__("unexpected", 0),
        lambda document: document.__setitem__("source_commit", "b" * 40),
    ),
)
def test_immutable_record_rejects_outer_replacement(
    mutate: object,
) -> None:
    document, args = _record()
    assert callable(mutate)
    mutate(document)
    store = _Store(_Sealed(document, args.expected_plan_manifest_sha256))

    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="immutable_plan_authentication",
    ):
        SCRIPT["_authenticate_plan_record"](store, args)


def test_immutable_record_rejects_cross_join_even_when_rehashed() -> None:
    document, args = _record()
    recipe = copy.deepcopy(document["recipe_plan"])
    assert isinstance(recipe, dict)
    recipe["execution_identity_sha256"] = _sha("cross-joined-execution")
    document["recipe_plan"] = recipe
    document["recipe_plan_sha256"] = canonical_sha256(recipe)
    freeze = copy.deepcopy(document["freeze"])
    assert isinstance(freeze, dict)
    freeze["recipe_plan_sha256"] = document["recipe_plan_sha256"]
    document["freeze"] = freeze
    document["freeze_sha256"] = canonical_sha256(freeze)
    payload = dict(document)
    payload.pop("private_plan_sha256")
    document["private_plan_sha256"] = canonical_sha256(payload)
    args.expected_private_plan_sha256 = document["private_plan_sha256"]
    args.expected_recipe_plan_sha256 = document["recipe_plan_sha256"]
    store = _Store(_Sealed(document, args.expected_plan_manifest_sha256))

    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="immutable_plan_authentication",
    ):
        SCRIPT["_authenticate_plan_record"](store, args)


def test_static_plan_join_validates_real_lossless_boundary_without_runtime() -> None:
    document, _args_namespace = _record()
    plan = document["recipe_plan"]
    freeze = document["freeze"]
    execution = document["execution_identity"]
    assert isinstance(plan, dict)
    assert isinstance(freeze, dict)
    assert isinstance(execution, dict)
    corridors = tuple(freeze["corridor_binding_sha256s"])

    inventory = SCRIPT["_inspect_recipe_plan"](plan)
    assert len(inventory.root_bindings) == 15
    assert inventory.option_count == 45
    assert inventory.semantic_family_count == 33
    SCRIPT["_require_static_plan_join"](
        document,
        execution_identity=execution,
        execution_identity_sha256=document["execution_identity_sha256"],
        plan_document=plan,
        freeze_document=freeze,
        corridor_binding_sha256s=corridors,
        catalog_sha256=document["context_catalog_sha256"],
        context_plan_sha256=document["context_plan_sha256"],
        runtime_sha256=document["runtime_identity_sha256"],
        route_registry_sha256=document["route_registry_sha256"],
    )
    changed = copy.deepcopy(freeze)
    changed["corridor_binding_sha256s"] = [_sha("replacement-corridor")]
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="reconstructed_plan_join",
    ):
        SCRIPT["_require_static_plan_join"](
            document,
            execution_identity=execution,
            execution_identity_sha256=document["execution_identity_sha256"],
            plan_document=plan,
            freeze_document=changed,
            corridor_binding_sha256s=corridors,
            catalog_sha256=document["context_catalog_sha256"],
            context_plan_sha256=document["context_plan_sha256"],
            runtime_sha256=document["runtime_identity_sha256"],
            route_registry_sha256=document["route_registry_sha256"],
        )


def test_top_level_rehearsal_crosses_every_authentication_guard_without_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())
    record, _record_args = _record()
    summary = SealedRecordSummary(
        record_id="red-living-dex-provider-plan-v1",
        kind="red-living-dex-provider-plan-v1",
        record_sha256=_sha("record"),
        manifest_sha256=_sha("manifest"),
        total_bytes=100,
    )
    binding = SCRIPT["_BridgeSourceBinding"](
        "b" * 40,
        _sha("bridge"),
        _sha("freezer"),
        _sha("authentication"),
    )
    runtime = SimpleNamespace(sha256=record["runtime_identity_sha256"])
    route_registry = SimpleNamespace(
        registry_sha256=record["route_registry_sha256"]
    )
    freeze = record["freeze"]
    assert isinstance(freeze, dict)
    corridors = tuple(
        SimpleNamespace(binding_sha256=value)
        for value in freeze["corridor_binding_sha256s"]
    )
    execution = SimpleNamespace(
        identity_sha256=record["execution_identity_sha256"],
        private_dict=lambda: record["execution_identity"],
    )
    inventory = SCRIPT["_inspect_recipe_plan"](record["recipe_plan"])
    roots = tuple(object() for _ in inventory.root_bindings)
    events: list[str] = []
    globals_ = SCRIPT["prepare_red_living_dex_setup_bridge"].__globals__

    def event(name: str, result: object = None):
        def called(*_args: object, **_kwargs: object) -> object:
            events.append(name)
            return result

        return called

    monkeypatch.setitem(globals_, "_authenticate_bridge_source", event("source", binding))
    monkeypatch.setitem(globals_, "_require_exact_green_ci_run", event("ci"))
    monkeypatch.setitem(
        globals_,
        "_authenticate_canonical_evidence",
        event("canonical-evidence"),
    )
    monkeypatch.setitem(globals_, "_load_freezer_support", event("support"))
    store = object()
    monkeypatch.setitem(globals_, "_open_store", event("store", store))
    monkeypatch.setitem(
        globals_,
        "_authenticate_plan_record",
        event("record", (record, summary)),
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        event(
            "inputs",
            (
                Path("red.gb"),
                POKEMON_RED_US_REV_0.sha256,
                b"rom",
                (),
                record["context_catalog_sha256"],
                record["context_plan_sha256"],
            ),
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_supplemental_roots",
        event("supplements", ()),
    )
    monkeypatch.setitem(
        globals_,
        "_build_stdlib_runtime_identity",
        event("runtime-id", runtime),
    )
    monkeypatch.setitem(
        globals_,
        "_require_runtime_identity_without_imports",
        event("no-third-party"),
    )
    monkeypatch.setitem(
        globals_,
        "load_strategic_navigation_scenario_registry",
        event("routes", route_registry),
    )
    monkeypatch.setitem(
        globals_,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=event("cartridge-world", object())),
    )
    monkeypatch.setitem(
        globals_,
        "derive_red_living_dex_provider_corridors",
        event("corridors", corridors),
    )
    monkeypatch.setitem(
        globals_,
        "compose_red_living_dex_setup_execution_identity",
        event("execution-id", execution),
    )
    original_inspect = SCRIPT["_inspect_recipe_plan"]

    def inspect_plan(plan: object):
        events.append("plan")
        return original_inspect(plan)

    monkeypatch.setitem(globals_, "_inspect_recipe_plan", inspect_plan)
    monkeypatch.setitem(globals_, "_require_static_plan_join", event("static-join"))
    monkeypatch.setitem(globals_, "_join_authenticated_root_bytes", event("root-bytes", roots))
    monkeypatch.setitem(
        globals_,
        "open_fixed_account_claim_registry",
        event("claim-registry", Path("claims")),
    )

    @contextmanager
    def lease(*_args: object, **_kwargs: object):
        events.append("lease-enter")
        yield
        events.append("lease-exit")

    monkeypatch.setitem(globals_, "_existing_claim_registry_read_lease", lease)
    monkeypatch.setitem(
        globals_,
        "_require_root_inventory",
        event("root-claims", len(roots)),
    )
    monkeypatch.setitem(globals_, "_require_protected_integrity", event("final-integrity"))
    monkeypatch.setitem(
        globals_,
        "_require_campaign_namespace_pristine",
        event("namespace"),
    )

    class Prepared:
        def __init__(self, **_kwargs: object) -> None:
            events.append("prepared")

        def __post_init__(self) -> None:
            events.append("prepared-validated")

    monkeypatch.setitem(globals_, "PreparedRedLivingDexSetupBridge", Prepared)
    monkeypatch.setitem(
        globals_,
        "_BOOTSTRAP_IDENTITY",
        ("b" * 40, "a" * 40, _sha("source")),
    )

    SCRIPT["prepare_red_living_dex_setup_bridge"](parsed)

    assert events == [
        "source",
        "ci",
        "canonical-evidence",
        "support",
        "store",
        "record",
        "inputs",
        "supplements",
        "runtime-id",
        "no-third-party",
        "routes",
        "cartridge-world",
        "corridors",
        "execution-id",
        "plan",
        "static-join",
        "root-bytes",
        "claim-registry",
        "lease-enter",
        "root-claims",
        "final-integrity",
        "lease-exit",
        "namespace",
        "prepared",
        "prepared-validated",
    ]


def test_root_inventory_checks_logical_and_physical_claims_under_one_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(0).root
    binding = SCRIPT["_FrozenRootBinding"](
        root_consumption_sha256=root.root_consumption_sha256,
        root_state_sha256=root.state_sha256,
        root_envelope_sha256=root.envelope_sha256,
        recipe_sha256=_sha("recipe"),
    )
    seen: list[str] = []
    globals_ = SCRIPT["_require_root_inventory"].__globals__

    def available(_registry: Path, digest: str) -> bool:
        seen.append(digest)
        return True

    monkeypatch.setitem(globals_, "root_claim_is_available", available)
    diagnostics = SCRIPT["_DiagnosticState"]()

    assert (
        SCRIPT["_require_root_inventory"](
            (binding,),
            (root,),
            claim_registry=Path("claims"),
            diagnostics=diagnostics,
        )
        == 1
    )
    assert seen == [root.root_consumption_sha256, root.physical_root_sha256]
    assert diagnostics.logical_claims_available == 1
    assert diagnostics.physical_claims_available == 1

    monkeypatch.setitem(
        globals_,
        "root_claim_is_available",
        lambda _registry, digest: digest != root.physical_root_sha256,
    )
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="root_claim_availability",
    ):
        SCRIPT["_require_root_inventory"](
            (binding,),
            (root,),
            claim_registry=Path("claims"),
            diagnostics=SCRIPT["_DiagnosticState"](),
        )


def test_claim_registry_read_lease_never_creates_coordination_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / ".coordination.lock"
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="root_claim_availability",
    ), SCRIPT["_existing_claim_registry_read_lease"](tmp_path):
        pass
    assert not marker.exists()

    marker.write_bytes(b"")
    marker.chmod(0o600)
    original_open = SCRIPT["_existing_claim_registry_read_lease"].__globals__["os"].open
    seen_flags: list[int] = []

    def observed_open(path: object, flags: int, *args: object) -> int:
        seen_flags.append(flags)
        return original_open(path, flags, *args)

    monkeypatch.setattr(
        SCRIPT["_existing_claim_registry_read_lease"].__globals__["os"],
        "open",
        observed_open,
    )
    inode = marker.stat().st_ino
    with SCRIPT["_existing_claim_registry_read_lease"](tmp_path):
        assert marker.stat().st_ino == inode
    assert seen_flags and all(flags & os.O_CREAT == 0 for flags in seen_flags)


def test_private_store_reuses_the_hardened_worktree_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_open_store"].__globals__
    observed: dict[str, object] = {}

    def open_root(*args: object, **kwargs: object) -> object:
        observed["args"] = args
        observed["kwargs"] = kwargs
        return object()

    monkeypatch.setitem(globals_, "open_private_root", open_root)
    result = SCRIPT["_open_store"](SimpleNamespace(private_root=Path("/private/root")))

    assert result is not None
    kwargs = observed["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["git_worktree_probe"] is SCRIPT["_hardened_git_worktree_probe"]


def test_exact_input_helper_is_bound_to_the_no_create_read_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_bind_read_only_input_authenticator"].__globals__
    events: list[str] = []

    expected = (Path("red.gb"), "d" * 64, b"rom", (), "e" * 64, "f" * 64)

    def probe(_args: object, _source_commit: str, _source_bundle: str) -> object:
        load_committed_goal_manager_registry_at_revision(Path("repository"), "revision")
        with fixed_account_claim_registry_lease(Path("claims"), exclusive=False):
            return (Path("red.gb"), "d" * 64, b"rom", (), "e" * 64, "f" * 64)

    probe_namespace = {
        "Path": Path,
        "fixed_account_claim_registry_lease": globals_[
            "fixed_account_claim_registry_lease"
        ],
        "load_committed_goal_manager_registry_at_revision": globals_[
            "_unsafe_registry_loader"
        ],
    }
    exact_probe = FunctionType(probe.__code__, probe_namespace, name="probe")

    @contextmanager
    def read_only_lease(_registry: Path):
        events.append("read-only-existing-marker")
        yield

    monkeypatch.setitem(
        globals_,
        "_existing_claim_registry_read_lease",
        read_only_lease,
    )
    monkeypatch.setitem(
        globals_,
        "_load_committed_goal_manager_registry_at_revision",
        lambda *_args: events.append("hardened-registry-loader"),
    )
    monkeypatch.setitem(
        globals_,
        "_freezer_support",
        lambda: {"_AUTHENTICATION_SUPPORT": {"_authenticate_inputs": exact_probe}},
    )

    assert SCRIPT["_authenticate_inputs"](object(), "a" * 40, "b" * 64) == expected
    assert events == ["hardened-registry-loader", "read-only-existing-marker"]
    assert exact_probe.__globals__["fixed_account_claim_registry_lease"] is globals_[
        "fixed_account_claim_registry_lease"
    ]


def test_campaign_namespace_preflight_rejects_any_partial_recovery_state() -> None:
    recipe_sha256s = ("a" * 64,)

    class Store:
        partial = False

        def find_sealed_record(self, record_id: str, *, expected_kind: str):
            del record_id, expected_kind
            return None

        def inspect_episode_state(self, episode_id: str):
            assert episode_id == "red-living-dex-recipe-00-" + "a" * 20
            return SimpleNamespace(status="partial" if self.partial else "absent")

    store = Store()
    SCRIPT["_require_campaign_namespace_pristine"](store, recipe_sha256s)
    store.partial = True
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="campaign_namespace_not_pristine",
    ):
        SCRIPT["_require_campaign_namespace_pristine"](store, recipe_sha256s)


def test_protected_integrity_rejects_runtime_route_or_corridor_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = SimpleNamespace(
        exact_ci_attempt=1,
        exact_ci_run=1234,
        expected_source_bundle_sha256=_sha("source"),
        expected_source_commit="a" * 40,
    )
    rom_bytes = b"red-rom"
    rom_sha256 = hashlib.sha256(rom_bytes).hexdigest()
    record, _record_args = _record()
    plan = record["recipe_plan"]
    freeze = record["freeze"]
    assert isinstance(plan, dict)
    assert isinstance(freeze, dict)
    corridors = tuple(freeze["corridor_binding_sha256s"])
    summary = SealedRecordSummary(
        record_id="red-living-dex-provider-plan-v1",
        kind="red-living-dex-provider-plan-v1",
        record_sha256=_sha("record"),
        manifest_sha256=_sha("manifest"),
        total_bytes=100,
    )
    globals_ = SCRIPT["_require_protected_integrity"].__globals__
    monkeypatch.setitem(
        globals_,
        "verify_rom",
        lambda _path: SimpleNamespace(sha256=rom_sha256),
    )
    monkeypatch.setitem(
        globals_,
        "POKEMON_RED_US_REV_0",
        SimpleNamespace(sha256=rom_sha256),
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_bridge_source",
        lambda _args: SCRIPT["_BridgeSourceBinding"](
            "b" * 40,
            _sha("bridge-script"),
            _sha("freezer-script"),
            _sha("authentication-support"),
        ),
    )
    canonical_calls: list[object] = []

    def canonical_evidence(args: object) -> dict[str, object]:
        canonical_calls.append(args)
        return {}

    monkeypatch.setitem(globals_, "_authenticate_canonical_evidence", canonical_evidence)
    monkeypatch.setitem(
        globals_,
        "_authenticate_plan_record",
        lambda _store, _args: (dict(record), summary),
    )
    monkeypatch.setitem(
        globals_,
        "_build_stdlib_runtime_identity",
        lambda: SimpleNamespace(sha256=_sha("runtime")),
    )
    monkeypatch.setitem(
        globals_,
        "_require_runtime_identity_without_imports",
        lambda _runtime: None,
    )
    monkeypatch.setitem(
        globals_,
        "load_strategic_navigation_scenario_registry",
        lambda _root: SimpleNamespace(registry_sha256=_sha("routes")),
    )
    monkeypatch.setitem(
        globals_,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda _bytes: object()),
    )
    monkeypatch.setitem(
        globals_,
        "derive_red_living_dex_provider_corridors",
        lambda _world: tuple(
            SimpleNamespace(binding_sha256=value) for value in corridors
        ),
    )
    monkeypatch.setitem(
        globals_,
        "compose_red_living_dex_setup_execution_identity",
        lambda **_kwargs: SimpleNamespace(
            identity_sha256=record["execution_identity_sha256"],
            private_dict=lambda: record["execution_identity"],
        ),
    )
    monkeypatch.setitem(globals_, "_require_static_plan_join", lambda *_a, **_k: None)
    bridge_binding = SCRIPT["_BridgeSourceBinding"](
        "b" * 40,
        _sha("bridge-script"),
        _sha("freezer-script"),
        _sha("authentication-support"),
    )
    ci_document = {"attempt": 1, "databaseId": 1234}
    current_ci = dict(ci_document)
    monkeypatch.setitem(
        globals_,
        "_require_exact_green_ci_run",
        lambda *_args, **_kwargs: dict(current_ci),
    )
    arguments = {
        "store": object(),
        "record": record,
        "record_summary": summary,
        "bridge_source_binding": bridge_binding,
        "rom_path": Path("red.gb"),
        "rom_sha256": rom_sha256,
        "rom_bytes": rom_bytes,
        "runtime_sha256": _sha("runtime"),
        "route_registry_sha256": _sha("routes"),
        "plan_document": plan,
        "freeze_document": freeze,
        "corridor_binding_sha256s": corridors,
        "catalog_sha256": record["context_catalog_sha256"],
        "context_plan_sha256": record["context_plan_sha256"],
        "ci_document": ci_document,
    }

    SCRIPT["_require_protected_integrity"](parsed, **arguments)
    assert canonical_calls == [parsed]
    for field, value in (
        ("runtime_sha256", _sha("runtime-drift")),
        ("route_registry_sha256", _sha("route-drift")),
    ):
        changed = {**arguments, field: value}
        with pytest.raises(
            SCRIPT["SetupBridgePreflightError"],
            match="protected_input_integrity",
        ):
            SCRIPT["_require_protected_integrity"](parsed, **changed)
    changed = {**arguments, "corridor_binding_sha256s": (_sha("drift"),)}
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="protected_input_integrity",
    ):
        SCRIPT["_require_protected_integrity"](parsed, **changed)
    current_ci["attempt"] = 2
    with pytest.raises(
        SCRIPT["SetupBridgePreflightError"],
        match="protected_input_integrity",
    ):
        SCRIPT["_require_protected_integrity"](parsed, **arguments)


def test_main_failure_is_path_free_and_never_claims_or_runs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "prepare_red_living_dex_setup_bridge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SCRIPT["SetupBridgePreflightError"]("immutable_plan_authentication")
        ),
    )

    assert SCRIPT["main"](_args()) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "failed_closed"
    assert receipt["stage"] == "immutable_plan_authentication"
    assert receipt["setup_runtime_factory_calls"] == 0
    assert receipt["setup_campaign_calls"] == 0
    assert receipt["root_claims"] == 0
    assert "/private" not in json.dumps(receipt)
