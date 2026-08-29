# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
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
EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-causal-capacity-census-v1-2026-08-28.json"
)
MACHINE_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-causal-capacity-census-machine-result-v1-2026-08-28.json"
)
CLUSTERED_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-clustered-curriculum-census-v1-2026-08-29.json"
)
CLUSTERED_MACHINE_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-clustered-curriculum-census-machine-result-v1-2026-08-29.json"
)
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
    roots = tuple(
        replace(
            root,
            cluster_partition="train" if index < 10 else "development",
        )
        for index, root in enumerate(_roots())
    )
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
    clustered = SimpleNamespace(
        public_dict=lambda: {
            "train_scenarios": 8,
            "development_scenarios": 4,
            "lineage_overlap": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "outcomes_observed": 0,
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
        "enumerate_red_living_dex_causal_capabilities",
        lambda *_args, **_kwargs: (object(),),
    )
    monkeypatch.setitem(
        globals_,
        "audit_red_living_dex_causal_inventory",
        lambda *_args, **_kwargs: audit,
    )
    monkeypatch.setitem(
        globals_,
        "schedule_red_living_dex_clustered_integration",
        lambda *_args, **_kwargs: clustered,
    )

    assert SCRIPT["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert integrity_checks == 1
    assert result["status"] == (
        "authenticated_action_free_clustered_inventory_censused"
    )
    assert result["inventory_sufficient"] is False
    assert result["combined_context_deficit"] == 180
    assert result["private_identity_fields"] == 0
    assert result["private_path_fields"] == 0
    assert result["root_claims"] == 0
    assert result["clustered_integration"] == clustered.public_dict()
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


def test_published_capacity_result_is_path_free_and_keeps_effects_zero() -> None:
    result = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    machine_bytes = MACHINE_RESULT_PATH.read_bytes()
    machine = json.loads(machine_bytes)

    assert result["status"] == (
        "authenticated_action_free_inventory_censused_capacity_insufficient"
    )
    assert result["source"]["commit"] == (
        "cb18a8b5ffcc256707ee3cafa94f419565f17ab6"
    )
    assert result["source"]["ci_run"] == 33140010028
    assert result["source"]["machine_result_sha256"] == hashlib.sha256(
        machine_bytes
    ).hexdigest()
    assert result["source"]["machine_result_schema"] == machine["schema"]
    assert result["source"]["machine_result_status"] == machine["status"]
    assert result["audit"]["train_maximum_matching"] == 54
    assert result["audit"]["development_maximum_matching"] == 63
    assert result["audit"]["combined_maximum_matching"] == 63
    assert result["audit"]["combined_context_deficit"] == 132
    assert result["audit"]["development_template_compatible_root_counts"] == [
        44,
        0,
        5,
        34,
        45,
    ]
    assert set(result["protected_effects"].values()) <= {0}
    direct_audit_fields = {
        "authenticated_contexts",
        "authenticated_supplemental_roots",
        "capacity_schedule_sha256",
        "combined_context_deficit",
        "combined_maximum_matching",
        "compatibility_edges",
        "consumed_contexts",
        "consumed_supplemental_roots",
        "development_context_deficit",
        "development_maximum_matching",
        "development_template_compatible_root_counts",
        "distinct_independence_lineages",
        "distinct_physical_roots",
        "eligible_root_pool",
        "eligible_supplemental_roots",
        "ineligible_control_contexts",
        "independence_qualified_roots",
        "inventory_sufficient",
        "reasons",
        "roots_observed",
        "roots_with_any_compatible_template",
        "roots_without_compatible_template",
        "source_catalog_partition_reused_as_prospective_label",
        "source_train_roots",
        "source_validation_roots",
        "train_context_deficit",
        "train_maximum_matching",
        "train_template_compatible_root_counts",
        "unqualified_lineage_roots",
    }
    for field in direct_audit_fields:
        assert result["audit"][field] == machine[field]
    for field in result["protected_effects"]:
        assert result["protected_effects"][field] == machine[field]
    pressure_axes = (
        "collection_pressure",
        "dependency_pressure",
        "access_pressure",
        "resource_pressure",
        "storage_pressure",
        "party_pressure",
        "knowledge_pressure",
    )
    assert result["audit"]["pressure_value_counts"] == dict(
        zip(pressure_axes, machine["pressure_value_counts"], strict=True)
    )
    assert result["design_sha256"] == machine["design_sha256"]
    assert (
        result["interpretation"]["combined_new_independent_root_lower_bound"]
        == machine["minimum_new_independent_roots_lower_bound"]
    )
    encoded = json.dumps(result, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_published_clustered_census_passes_without_learning_or_private_leak() -> None:
    result = json.loads(CLUSTERED_EVIDENCE_PATH.read_text(encoding="utf-8"))
    machine_bytes = CLUSTERED_MACHINE_RESULT_PATH.read_bytes()
    machine = json.loads(machine_bytes)

    assert result["status"] == (
        "clustered_integration_capacity_passed_private_schedule_freeze_pending"
    )
    assert result["source"]["commit"] == (
        "f26be2a10936784abaf95c9a441626948d3fc162"
    )
    assert result["source"]["ci_run"] == 33263228797
    assert result["source"]["machine_result_sha256"] == hashlib.sha256(
        machine_bytes
    ).hexdigest()
    clustered = result["clustered_gate"]
    assert clustered["gate_passed"] is True
    assert clustered["train_scenarios"] == clustered["train_lineages"] == 8
    assert clustered["development_scenarios"] == clustered["development_lineages"] == 4
    assert clustered["train_option_kinds"] == clustered["development_option_kinds"]
    assert len(clustered["train_option_kinds"]) == 7
    assert clustered["lineage_overlap"] == 0
    assert clustered["maximum_observed_scenarios_per_lineage"] == 1
    assert clustered["schedule_sha256"] == (
        machine["clustered_integration"]["schedule_sha256"]
    )
    assert clustered["policy_sha256"] == (
        machine["clustered_integration"]["policy_sha256"]
    )
    protected = result["protected_effects"]
    assert protected["collection_authorized"] is False
    assert set(protected) == {
        "behavior_commitments",
        "collection_authorized",
        "controller_actions",
        "emulator_frames",
        "model_fits",
        "model_predictions",
        "outcomes",
        "provider_executions",
        "root_claims",
        "teacher_queries",
    }
    assert all(value == 0 for key, value in protected.items() if key != "collection_authorized")
    encoded = json.dumps(result, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
