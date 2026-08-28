# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_provider_plan import _roots
from test_red_living_dex_setup_identity import _runtime

from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/audit_red_living_dex_causal_inventory.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="audit_red_living_dex_causal_inventory_test",
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _args() -> list[str]:
    return [
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


def test_parser_is_read_only_and_has_no_private_publication_target() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_source_commit == "a" * 40
    assert not hasattr(parsed, "private_root")
    for field in (
        "watch",
        "speed",
        "retry",
        "seed",
        "fit",
        "execute",
        "output",
    ):
        assert not hasattr(parsed, field)


def test_runner_has_no_action_claim_teacher_outcome_fit_or_publication_authority() -> None:
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


def test_main_emits_only_the_path_free_aggregate_bound(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    roots = _roots()
    runtime = _runtime()
    integrity_checks = 0

    def support(name: str):  # type: ignore[no-untyped-def]
        if name == "_authenticate_source":
            return lambda _args: ("a" * 40, _sha("source"))
        if name == "_authenticate_inputs":
            return lambda *_args: (
                Path("/private/red.gb"),
                "1" * 64,
                b"rom",
                tuple(range(15)),
                _sha("catalog"),
                _sha("context-plan"),
            )
        if name == "_authenticate_supplemental_roots":
            return lambda *_args: ()
        if name in {"_observe_candidates", "_observe_supplemental_candidates"}:
            return lambda *_args, **_kwargs: roots if name == "_observe_candidates" else ()
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
        public_dict=lambda: {
            "inventory_sufficient": False,
            "combined_context_deficit": 180,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "outcomes": 0,
            "model_fits": 0,
        }
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
        globals_, "derive_red_living_dex_provider_corridors", lambda _world: ()
    )
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(globals_, "fixed_account_claim_registry_lease", lease)
    monkeypatch.setitem(
        globals_,
        "census_red_living_dex_causal_inventory",
        lambda *_args, **_kwargs: audit,
    )

    assert SCRIPT["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert integrity_checks == 1
    assert result["status"] == "authenticated_action_free_inventory_censused"
    assert result["inventory_sufficient"] is False
    assert result["combined_context_deficit"] == 180
    assert result["private_identity_fields"] == 0
    assert result["private_path_fields"] == 0
    assert result["root_claims"] == 0
    assert "/private" not in str(result)


def test_failure_receipt_sanitizes_an_exception_and_retains_zero_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__

    def support(_name: str):  # type: ignore[no-untyped-def]
        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("/private/secret/catalog.json")

        return fail

    monkeypatch.setitem(globals_, "_support", support)

    assert SCRIPT["main"](_args()) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "source_authentication"
    assert result["controller_actions"] == 0
    assert result["emulator_frames"] == 0
    assert result["root_claims"] == 0
    assert result["outcomes"] == 0
    assert "/private" not in str(result)
