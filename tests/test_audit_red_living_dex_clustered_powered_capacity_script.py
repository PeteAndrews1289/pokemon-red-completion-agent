# ruff: noqa: E402 -- standalone runner is loaded after script-local imports.

from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_setup_identity import _runtime

from pokemon_red_completion.living_dex_clustered_powered_design import (
    LivingDexClusteredPoweredDesign,
)
from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/audit_red_living_dex_clustered_powered_capacity.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="audit_red_living_dex_clustered_powered_capacity_test",
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _args(*, design_sha256: str | None = None) -> list[str]:
    return [
        "--expected-design-sha256",
        design_sha256 or LivingDexClusteredPoweredDesign().design_sha256,
        "--expected-source-commit",
        "a" * 40,
        "--expected-source-bundle-sha256",
        _sha("source"),
        "--registry-source-commit",
        "b" * 40,
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
        "--rom",
        "/private/red.gb",
    ]


def test_parser_binds_the_design_and_has_no_execution_or_publication_target() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_design_sha256 == LivingDexClusteredPoweredDesign().design_sha256
    for field in (
        "watch",
        "speed",
        "retry",
        "seed",
        "fit",
        "execute",
        "output",
        "allocation_plan",
    ):
        assert not hasattr(parsed, field)


def test_runner_has_no_action_claim_teacher_outcome_or_fit_authority() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "CountingExecutor",
        "write_root_claim",
        "publish_sealed_record",
        "CompletionFirstGoalTeacher",
        "issue_red_living_dex_behavior_commitment",
        "fit_living_dex_option_value",
        ".press(",
        ".tick(",
        ".execute(",
    ):
        assert forbidden not in source


def test_main_emits_the_decisive_path_free_shortfall(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    runtime = _runtime()
    roots = (object(), object())
    integrity_checks = 0

    def support(name: str):  # type: ignore[no-untyped-def]
        if name == "_authenticate_source":
            return lambda _args: ("a" * 40, _sha("source"))
        if name == "_authenticate_inputs":
            return lambda *_args: (
                Path("/private/red.gb"),
                "1" * 64,
                b"rom",
                (1, 2),
                _sha("catalog"),
                _sha("context-plan"),
            )
        if name == "_authenticate_supplemental_roots":
            return lambda *_args: ()
        if name == "_observe_candidates":
            return lambda *_args, **_kwargs: roots
        if name == "_observe_supplemental_candidates":
            return lambda *_args, **_kwargs: ()
        if name == "_require_integrity":

            def integrity(*_args: object, **_kwargs: object) -> None:
                nonlocal integrity_checks
                integrity_checks += 1

            return integrity
        raise AssertionError(name)

    @contextmanager
    def lease(_registry: Path, *, exclusive: bool) -> Iterator[None]:
        assert exclusive is False
        yield

    audit = SimpleNamespace(
        capacity_proven=False,
        reasons=("insufficient_total_lineages",),
        public_dict=lambda: {
            "capacity_proven": False,
            "total_lineage_deficit": 137,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "outcomes": 0,
            "root_claims": 0,
        },
    )
    monkeypatch.setitem(globals_, "_support", support)
    monkeypatch.setitem(globals_, "build_runtime_identity", lambda: runtime)
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _runtime: None)
    monkeypatch.setitem(
        globals_,
        "load_strategic_navigation_scenario_registry",
        lambda _root: SimpleNamespace(registry_sha256=_sha("routes")),
    )
    monkeypatch.setitem(
        globals_,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda _rom: object()),
    )
    monkeypatch.setitem(
        globals_,
        "derive_red_living_dex_provider_corridors",
        lambda _world: (),
    )
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(globals_, "fixed_account_claim_registry_lease", lease)
    monkeypatch.setitem(
        globals_,
        "enumerate_red_living_dex_causal_capabilities",
        lambda *_args, **_kwargs: (object(),),
    )
    monkeypatch.setitem(
        globals_,
        "adapt_red_living_dex_clustered_powered_capacity",
        lambda *_args, **_kwargs: (object(), object()),
    )
    monkeypatch.setitem(
        globals_,
        "build_living_dex_clustered_powered_allocation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setitem(
        globals_,
        "audit_living_dex_clustered_powered_capacity",
        lambda *_args, **_kwargs: audit,
    )

    assert SCRIPT["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert integrity_checks == 1
    assert result["status"] == ("authenticated_action_free_capacity_falsified_before_gameplay")
    assert result["hard_capacity_reasons"] == ["insufficient_total_lineages"]
    assert result["total_lineage_deficit"] == 137
    assert result["capacity_proven"] is False
    assert result["controller_actions"] == 0
    assert result["emulator_frames"] == 0
    assert result["outcomes"] == 0
    assert result["root_claims"] == 0
    assert "/private" not in str(result)


def test_wrong_design_digest_fails_before_private_authentication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    support_calls = 0

    def support(_name: str):  # type: ignore[no-untyped-def]
        nonlocal support_calls
        support_calls += 1
        raise AssertionError("private support must remain closed")

    monkeypatch.setitem(globals_, "_support", support)

    assert SCRIPT["main"](_args(design_sha256="0" * 64)) == 1
    result = json.loads(capsys.readouterr().out)
    assert support_calls == 0
    assert result["stage"] == "design_authentication"
    assert result["status"] == "failed_closed"
    assert result["controller_actions"] == 0
    assert result["emulator_frames"] == 0
    assert result["root_claims"] == 0
