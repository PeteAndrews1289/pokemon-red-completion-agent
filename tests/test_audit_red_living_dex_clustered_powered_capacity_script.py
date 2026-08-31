# ruff: noqa: E402 -- standalone runner is loaded after script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_fresh_episode_runtime import _powered_plan
from test_red_living_dex_setup_identity import _runtime

from pokemon_red_completion.living_dex_clustered_powered_design import (
    LivingDexClusteredPoweredDesign,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    encode_red_living_dex_powered_supply_plan,
)

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
    assert parsed.powered_supply_plan is None
    assert parsed.powered_supply_private_root is None
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
    powered_roots = (object(), object(), object())
    powered_bundle = SimpleNamespace(
        roots=powered_roots,
        private_dict=lambda: {"schema": "powered-bundle"},
    )
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
        if name == "_observe_powered_supply_candidates":
            return lambda supplied, *_args, **_kwargs: supplied
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
    monkeypatch.setitem(
        globals_,
        "_authenticate_powered_supply",
        lambda *_args, **_kwargs: powered_bundle,
    )
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
    assert result["authenticated_powered_supply_roots"] == 3
    assert result["eligible_powered_supply_roots"] == 3
    assert result["consumed_powered_supply_roots"] == 0
    assert result["root_state_restores"] == 0
    assert "/private" not in str(result)


def test_powered_supply_admission_is_exactly_bound_before_recensus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _powered_plan()
    plan_path = tmp_path / "powered-plan.json"
    payload = encode_red_living_dex_powered_supply_plan(plan)
    plan_path.write_bytes(payload)
    record_sha256 = hashlib.sha256(b"admission-record").hexdigest()
    expected_private = {"schema": "private-powered-admission"}
    calls: list[bool] = []
    bundle = SimpleNamespace(
        roots=(object(), object()),
        admission=SimpleNamespace(qualification_passed=True),
        record_id=f"pwr-admit-{plan.plan_sha256}",
        private_dict=lambda: expected_private,
    )

    class _Record:
        summary = SimpleNamespace(record_sha256=record_sha256)

        def read(self) -> dict[str, object]:
            return expected_private

    class _Store:
        def find_sealed_record(self, *_args: object, **_kwargs: object) -> _Record:
            return _Record()

    globals_ = SCRIPT["_authenticate_powered_supply"].__globals__
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: _Store())
    monkeypatch.setitem(
        globals_,
        "open_fixed_account_claim_registry",
        lambda: Path("claims"),
    )

    def authenticate(
        observed_plan,  # type: ignore[no-untyped-def]
        *,
        private_store: object,
        claim_registry: Path,
        recover_interrupted: bool,
    ) -> object:
        assert observed_plan == plan
        assert isinstance(private_store, _Store)
        assert claim_registry == Path("claims")
        calls.append(recover_interrupted)
        return bundle

    monkeypatch.setitem(
        globals_,
        "authenticate_red_living_dex_powered_supply_private_tranche",
        authenticate,
    )
    args = SimpleNamespace(
        powered_supply_plan=plan_path,
        expected_powered_supply_plan_sha256=hashlib.sha256(payload).hexdigest(),
        powered_supply_private_root=Path("/private/store"),
        expected_powered_supply_admission_record_sha256=record_sha256,
    )

    observed = SCRIPT["_authenticate_powered_supply"](
        args,
        source_commit=plan.source_commit,
        source_bundle=plan.source_bundle_sha256,
    )

    assert observed is bundle
    assert calls == [False]


def test_powered_supply_recensus_rejects_partial_or_unsealed_admission(
    tmp_path: Path,
) -> None:
    args = SimpleNamespace(
        powered_supply_plan=tmp_path / "plan.json",
        expected_powered_supply_plan_sha256=None,
        powered_supply_private_root=None,
        expected_powered_supply_admission_record_sha256=None,
    )

    with pytest.raises(
        SCRIPT["PoweredCapacityCensusError"],
        match="powered_supply_admission_authentication",
    ):
        SCRIPT["_authenticate_powered_supply"](
            args,
            source_commit="a" * 40,
            source_bundle=_sha("source"),
        )


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
