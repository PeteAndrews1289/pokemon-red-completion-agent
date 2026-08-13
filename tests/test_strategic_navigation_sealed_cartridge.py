from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.rom import RomFingerprint
from pokemon_red_completion.runtime_identity import RuntimeFileIdentity, RuntimeIdentity
from pokemon_red_completion.strategic_navigation_binding import (
    DestinationRouteBinding,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_ADAPTER_ID,
    STRATEGIC_NAVIGATION_GAME_ID,
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    STRATEGIC_SCENARIO_ORIGIN_MAPS,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_sealed_adapter import (
    StrategicSealedAdapterError,
)
from pokemon_red_completion.strategic_navigation_sealed_cartridge import (
    StrategicSealedPyBoySessionFactory,
    _sealed_episode_metadata,
    _sealed_scenario_assignment,
    qualify_strategic_sealed_adapter_on_non_test_capture,
)
from pokemon_red_completion.strategic_navigation_sealed_catalog import (
    STRATEGIC_SEALED_CASE_CATALOG_ENTRY_SCHEMA,
    STRATEGIC_SEALED_CASE_CATALOG_SCHEMA,
    STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256,
    parse_strategic_sealed_case_catalog,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    StrategicSealedEvaluationPlan,
    build_strategic_sealed_authorization,
    build_strategic_sealed_external_audit_receipt,
    build_strategic_sealed_non_test_qualification_receipt,
    load_strategic_sealed_evaluation_plan,
    parse_strategic_sealed_authorization,
    parse_strategic_sealed_external_audit_receipt,
    parse_strategic_sealed_non_test_qualification_receipt,
    require_strategic_sealed_runtime_preflight,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_AUDIT_EVIDENCE_SHA256 = "3" * 64
NON_TEST_ADAPTER_QUALIFICATION_EVIDENCE_SHA256 = "4" * 64


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


def _receipts(plan: StrategicSealedEvaluationPlan, *, source_commit: str):
    audit = parse_strategic_sealed_external_audit_receipt(
        build_strategic_sealed_external_audit_receipt(
            plan,
            receipt_id="sealed-cartridge-external-audit",
            issued_by="independent-auditor",
            issued_on="2026-08-13",
            source_commit=source_commit,
            evidence_sha256=EXTERNAL_AUDIT_EVIDENCE_SHA256,
            verdict="approved_for_authorization",
        ),
        plan=plan,
        source_commit=source_commit,
    )
    qualification = parse_strategic_sealed_non_test_qualification_receipt(
        build_strategic_sealed_non_test_qualification_receipt(
            plan,
            receipt_id="sealed-cartridge-non-test-qualification",
            issued_by="qualification-runner",
            issued_on="2026-08-13",
            source_commit=source_commit,
            evidence_sha256=NON_TEST_ADAPTER_QUALIFICATION_EVIDENCE_SHA256,
            verdict="passed",
        ),
        plan=plan,
        source_commit=source_commit,
    )
    return audit, qualification


def _runtime(*, suffix: str = "1") -> RuntimeIdentity:
    return RuntimeIdentity(
        python_implementation="CPython",
        python_version="3.14.3",
        python_executable_sha256=suffix * 64,
        pyboy_distribution_name="pyboy",
        pyboy_distribution_version="2.6.0",
        pyboy_files=(
            RuntimeFileIdentity(
                name="pyboy/__init__.py",
                size=1,
                sha256="2" * 64,
            ),
        ),
        pyboy_inventory_sha256="3" * 64,
    )


def _catalog_document(runtime: RuntimeIdentity) -> dict[str, object]:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    return {
        "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
        "cases": [
            {
                "capture": {
                    "checkpoint_id": f"sealed-cartridge-fixture-{case.ordinal:02d}",
                    "envelope_sha256": f"{case.ordinal + 100:064x}",
                    "state_bytes": 100_000 + case.ordinal,
                    "state_sha256": f"{case.ordinal:064x}",
                },
                "case_id": case.case_id,
                "case_sha256": case.case_sha256,
                "ordinal": case.ordinal,
                "schema": STRATEGIC_SEALED_CASE_CATALOG_ENTRY_SCHEMA,
                "source_scenario_id": case.source_scenario_id,
                "source_scenario_sha256": case.source_scenario_sha256,
            }
            for case in plan.cases
        ],
        "evaluation_id": plan.evaluation_id,
        "execution_configuration_sha256": (STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256),
        "game_id": STRATEGIC_NAVIGATION_GAME_ID,
        "plan_sha256": plan.plan_sha256,
        "rom_identity": {
            "sha1": POKEMON_RED_US_REV_0.sha1,
            "sha256": POKEMON_RED_US_REV_0.sha256,
            "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
            "title": POKEMON_RED_US_REV_0.title,
        },
        "runtime_sha256": runtime.sha256,
        "schema": STRATEGIC_SEALED_CASE_CATALOG_SCHEMA,
        "source_scenario_registry_sha256": plan.source_scenario_registry_sha256,
        "teacher_execution_sha256": plan.teacher_execution_sha256,
    }


def _protocol(runtime: RuntimeIdentity):
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    scenarios = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    catalog = parse_strategic_sealed_case_catalog(
        _canonical(_catalog_document(runtime)),
        plan=plan,
        scenario_registry=scenarios,
    )
    audit, qualification = _receipts(plan, source_commit="a" * 40)
    authorization = parse_strategic_sealed_authorization(
        build_strategic_sealed_authorization(
            plan,
            authorization_id="sealed-cartridge-fixture",
            authorized_by="test-owner",
            authorized_on="2026-08-13",
            source_commit="a" * 40,
            case_catalog_sha256=catalog.catalog_sha256,
            external_audit_receipt=audit,
            non_test_adapter_qualification_receipt=qualification,
        ),
        plan=plan,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    grant = require_strategic_sealed_runtime_preflight(
        plan,
        authorization,
        source_commit=authorization.source_commit,
        source_bundle_sha256=plan.execution_source_bundle_sha256,
        source_clean=True,
        source_published=True,
        model_canonical_sha256=plan.model_canonical_sha256,
        model_file_sha256=plan.model_file_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        case_catalog_sha256=catalog.catalog_sha256,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    execution = replace(
        parse_strategic_navigation_registry(
            (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
        ).execution,
        source_commit=authorization.source_commit,
    )
    return plan, scenarios, catalog, authorization, grant, execution


def test_factory_constructor_authenticates_public_inputs_without_opening_a_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    plan, scenarios, catalog, authorization, grant, execution = _protocol(runtime)
    private_path = tmp_path / "private"
    private_path.mkdir()
    private_root = initialize_private_root(
        private_path,
        repository_root=PROJECT_ROOT,
        allow_same_device=True,
    )
    rom_path = tmp_path / "private-red.gb"
    rom_path.write_bytes(b"ROM-free constructor fixture")
    opened: list[str] = []

    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.verify_rom_bytes",
        lambda payload, filename: RomFingerprint(
            filename=filename,
            title=POKEMON_RED_US_REV_0.title,
            size_bytes=POKEMON_RED_US_REV_0.size_bytes,
            sha1=POKEMON_RED_US_REV_0.sha1,
            sha256=POKEMON_RED_US_REV_0.sha256,
        ),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge."
        "StrategicScenarioRouteWorld.from_rom",
        lambda payload: object(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.rom_adjacent_artifacts",
        lambda path: (),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge."
        "open_strategic_sealed_case_input",
        lambda *args, **kwargs: opened.append("opened"),
    )

    factory = StrategicSealedPyBoySessionFactory(
        capture_root=tmp_path / "captures-not-opened",
        private_root=private_root,
        rom_path=rom_path,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        catalog=catalog,
        scenario_registry=scenarios,
        execution=execution,
        runtime=runtime,
    )

    assert opened == []
    assert factory.plan_sha256 == plan.plan_sha256
    assert factory.authorization_sha256 == authorization.authorization_sha256
    assert factory.case_catalog_sha256 == catalog.catalog_sha256
    assert factory.runtime_sha256 == runtime.sha256


def test_non_test_qualification_uses_shared_path_without_teacher_or_test_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    scenarios = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = scenarios.scenario("red-strategic-scenario-v2-015-validation")
    state_path = tmp_path / "qualification.state"
    state_path.write_bytes(b"authenticated non-test state")
    state_sha256 = hashlib.sha256(state_path.read_bytes()).hexdigest()
    envelope_path = tmp_path / "qualification.state.json"
    envelope_path.write_text(
        json.dumps(
            {
                "checkpoint_id": "non-test-qualification-fixture",
                "checkpoint_label": "Non-test qualification fixture",
                "checkpoints_completed": 1,
                "checkpoints_total": 1,
                "schema": "pokemon-private-captured-progress-v1",
                "state_sha256": state_sha256,
                "verified_objective_ids": list(scenario.completed_objective_ids),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )
    rom_path = tmp_path / "qualification.gb"
    rom_path.write_bytes(b"ROM-free qualification fixture")
    calls: list[object] = []
    bindings = tuple(SimpleNamespace(plan=object()) for _ in scenario.candidate_objective_ids)

    class FakeEmulator:
        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.verify_rom_bytes",
        lambda payload, filename: RomFingerprint(
            filename=filename,
            title=POKEMON_RED_US_REV_0.title,
            size_bytes=POKEMON_RED_US_REV_0.size_bytes,
            sha1=POKEMON_RED_US_REV_0.sha1,
            sha256=POKEMON_RED_US_REV_0.sha256,
        ),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge."
        "StrategicScenarioRouteWorld.from_rom",
        lambda payload: "route-world",
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.rom_adjacent_artifacts",
        lambda path: (),
    )

    def shared_path(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(emulator=FakeEmulator(), bindings=bindings)

    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge."
        "_open_strategic_cartridge_context",
        shared_path,
    )

    observation = qualify_strategic_sealed_adapter_on_non_test_capture(
        rom_path=rom_path,
        state_path=state_path,
        envelope_path=envelope_path,
        plan=plan,
        scenario_registry=scenarios,
        scenario_id=scenario.scenario_id,
        challenged_non_teacher_objective_id="liberate_silph",
        source_commit="a" * 40,
    )

    invocation = cast(dict[str, object], calls[0])
    assert invocation["declared_origin_region"] == "saffron"
    assert invocation["scenario"] is scenario
    assert calls[-1] == "close"
    assert observation.public_dict()["challenge"] == {
        "declared_origin_region": "saffron",
        "non_teacher_objective_id": "liberate_silph",
        "region_authenticated_by_completed_objective": True,
        "relocation_exercised": True,
        "source_origin_region": "celadon",
    }
    assert observation.public_dict()["result"] == {
        "available_candidate_count": len(scenario.candidate_objective_ids),
        "candidate_count": len(scenario.candidate_objective_ids),
        "capture_unchanged": True,
        "rom_adjacent_artifacts_unchanged": True,
        "sealed_test_cases_opened": 0,
        "status": "passed",
        "teacher_executed": False,
    }
    assert hashlib.sha256(observation.canonical_payload()).hexdigest() == (
        observation.evidence_sha256
    )
    assert str(tmp_path) not in json.dumps(observation.public_dict())


def test_non_test_qualification_requires_an_authenticated_challenge_region(
    tmp_path: Path,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    scenarios = load_strategic_navigation_scenario_registry(PROJECT_ROOT)

    with pytest.raises(
        StrategicSealedAdapterError,
        match="challenge region is not authenticated",
    ):
        qualify_strategic_sealed_adapter_on_non_test_capture(
            rom_path=tmp_path / "not-opened.gb",
            state_path=tmp_path / "not-opened.state",
            envelope_path=tmp_path / "not-opened.state.json",
            plan=plan,
            scenario_registry=scenarios,
            scenario_id="red-strategic-scenario-v2-007-validation",
            challenged_non_teacher_objective_id="reach_saffron",
            source_commit="a" * 40,
        )


def test_non_test_qualification_refuses_the_sealed_test_partition(
    tmp_path: Path,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    scenarios = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    sealed_scenario_id = next(
        scenario.scenario_id for scenario in scenarios.scenarios if scenario.partition == "test"
    )

    with pytest.raises(
        StrategicScenarioProtocolError,
        match="test scenario must remain unopened",
    ):
        qualify_strategic_sealed_adapter_on_non_test_capture(
            rom_path=tmp_path / "not-opened.gb",
            state_path=tmp_path / "not-opened.state",
            envelope_path=tmp_path / "not-opened.state.json",
            plan=plan,
            scenario_registry=scenarios,
            scenario_id=sealed_scenario_id,
            challenged_non_teacher_objective_id="not-used",
            source_commit="a" * 40,
        )


def test_factory_rejects_runtime_drift_before_reading_the_rom_or_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    plan, scenarios, catalog, authorization, grant, execution = _protocol(runtime)
    private_path = tmp_path / "private"
    private_path.mkdir()
    private_root = initialize_private_root(
        private_path,
        repository_root=PROJECT_ROOT,
        allow_same_device=True,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.verify_rom_bytes",
        lambda payload, filename: calls.append("rom"),
    )

    with pytest.raises(StrategicSealedAdapterError, match="identity differs"):
        StrategicSealedPyBoySessionFactory(
            capture_root=tmp_path / "captures",
            private_root=private_root,
            rom_path=tmp_path / "absent.gb",
            plan=plan,
            authorization=authorization,
            runtime_grant=grant,
            catalog=catalog,
            scenario_registry=scenarios,
            execution=execution,
            runtime=_runtime(suffix="4"),
        )

    assert calls == []


def test_sealed_assignment_and_episode_metadata_bind_case_without_a_path() -> None:
    runtime = _runtime()
    plan, scenarios, catalog, authorization, _, execution = _protocol(runtime)
    case = plan.cases[0]
    scenario = next(
        item for item in scenarios.scenarios if item.scenario_id == case.source_scenario_id
    )
    entry = catalog.cases[0]
    assignment = _sealed_scenario_assignment(
        scenario=scenario,
        entry=entry,
        registry_sha256=scenarios.registry_sha256,
        execution=execution,
    )

    metadata = _sealed_episode_metadata(
        assignment=assignment,
        case=case,
        plan=plan,
        authorization=authorization,
        catalog=catalog,
        execution=execution,
        runtime=runtime,
    )
    encoded = json.dumps(metadata, sort_keys=True)

    assert assignment.scenario_partition == "test"
    assert assignment.partition == "unassigned"
    assert metadata["sealed_evaluation"] == {
        "authorization_sha256": authorization.authorization_sha256,
        "case_catalog_sha256": catalog.catalog_sha256,
        "case_id": case.case_id,
        "case_sha256": case.case_sha256,
        "ordinal": case.ordinal,
        "origin_region": case.origin_region,
        "plan_sha256": plan.plan_sha256,
        "schema": "strategic-sealed-scenario-episode-binding-v1",
    }
    assert all(
        forbidden not in encoded
        for forbidden in (
            "capture_root",
            "envelope_path",
            "rom_path",
            "state_path",
        )
    )


@pytest.mark.parametrize("relocation_changes_frontier", [False, True])
def test_factory_relocates_a_claimed_challenge_before_planning_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relocation_changes_frontier: bool,
) -> None:
    runtime = _runtime()
    plan, scenarios, catalog, authorization, grant, execution = _protocol(runtime)
    case = plan.cases[1]
    scenario = next(
        item for item in scenarios.scenarios if item.scenario_id == case.source_scenario_id
    )
    assert case.origin_region != scenario.origin_region
    entry = catalog.cases[1]
    private_path = tmp_path / "private"
    private_path.mkdir()
    private_root = initialize_private_root(
        private_path,
        repository_root=PROJECT_ROOT,
        allow_same_device=True,
    )
    rom_path = tmp_path / "private-red.gb"
    rom_path.write_bytes(b"ROM-free relocation fixture")
    source_map = next(iter(STRATEGIC_SCENARIO_ORIGIN_MAPS[scenario.origin_region])).value
    target_maps = frozenset(
        item.value for item in STRATEGIC_SCENARIO_ORIGIN_MAPS[case.origin_region]
    )
    reader = SimpleNamespace()
    reader.raw = SimpleNamespace(
        game_started=True,
        map_id=source_map,
        player_y=1,
        player_x=1,
        battle_state=0,
    )
    reader.read = lambda: reader.raw
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    events: list[str] = []
    bindings = tuple(
        cast(DestinationRouteBinding, object()) for _ in scenario.candidate_objective_ids
    )

    class FakeEmulator:
        def start(self) -> None:
            events.append("emulator-start")

        def load_state_bytes(self, payload: bytes) -> None:
            assert payload == b"verified-state"
            events.append("state-load")

        def close(self) -> None:
            events.append("emulator-close")

    emulator = FakeEmulator()

    class FakeSemanticObserver:
        observations = 0

        def observe(self) -> frozenset[str]:
            self.observations += 1
            events.append("frontier-observe")
            if relocation_changes_frontier and self.observations == 2:
                return frozenset((*scenario.completed_objective_ids, "unexpected"))
            return frozenset(scenario.completed_objective_ids)

    class FakeTraversalObserver:
        def observe(self) -> object:
            events.append("traversal-observe")
            return object()

    class FakeRouteWorld:
        def plan_to_any_map(
            self,
            start: object,
            goals: frozenset[int],
        ) -> str:
            assert goals == target_maps
            events.append("relocation-plan")
            return "relocation"

        def plan_bindings(
            self,
            specs: object,
            start: object,
        ) -> tuple[DestinationRouteBinding, ...]:
            assert reader.raw.map_id in target_maps
            events.append("candidate-plan")
            return bindings

        def replanner(self) -> object:
            return object()

    route_world = FakeRouteWorld()

    def fake_execute_route(plan_value: object, *args: object, **kwargs: object) -> None:
        assert plan_value == "relocation"
        events.append("relocation-execute")
        reader.raw = SimpleNamespace(**{**vars(reader.raw), "map_id": min(target_maps)})

    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.verify_rom_bytes",
        lambda payload, filename: RomFingerprint(
            filename=filename,
            title=POKEMON_RED_US_REV_0.title,
            size_bytes=POKEMON_RED_US_REV_0.size_bytes,
            sha1=POKEMON_RED_US_REV_0.sha1,
            sha256=POKEMON_RED_US_REV_0.sha256,
        ),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge."
        "StrategicScenarioRouteWorld.from_rom",
        lambda payload: route_world,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.rom_adjacent_artifacts",
        lambda path: (),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge."
        "open_strategic_sealed_case_input",
        lambda *args, **kwargs: SimpleNamespace(
            state_bytes=b"verified-state",
            envelope=object(),
        ),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.PyBoyAdapter",
        lambda *args, **kwargs: emulator,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.PokemonRedStateReader",
        lambda value: reader,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.CapturedPokemonRedObserver",
        lambda *args, **kwargs: FakeSemanticObserver(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.COMPLETION_QUEST",
        SimpleNamespace(completed_ids=lambda value: value),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.Gen1TrainerSightProjector",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.Gen1TraversalObserver",
        lambda *args, **kwargs: FakeTraversalObserver(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.FrameSafeExecutor",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.CountingExecutor",
        lambda value: object(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.traversal_rules",
        lambda *args: SimpleNamespace(cut_block_swaps=()),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.map_graph",
        lambda value: object(),
    )
    field_actions = object()
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.Gen1FieldMovePort",
        lambda *args, **kwargs: field_actions,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge._sealed_interruption_handler",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_cartridge.execute_route",
        fake_execute_route,
    )

    factory = StrategicSealedPyBoySessionFactory(
        capture_root=tmp_path / "captures",
        private_root=private_root,
        rom_path=rom_path,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        catalog=catalog,
        scenario_registry=scenarios,
        execution=execution,
        runtime=runtime,
    )
    if relocation_changes_frontier:
        with pytest.raises(StrategicSealedAdapterError, match="changed"):
            factory.open_case(case, entry, scenario)
        assert "candidate-plan" not in events
        assert events[-1] == "emulator-close"
        return

    session = factory.open_case(case, entry, scenario)
    assert session.bindings is bindings
    assert events.index("relocation-execute") < events.index("candidate-plan")
    assert events.count("frontier-observe") == 2
    session.close()
