from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_ADAPTER_ID,
    STRATEGIC_NAVIGATION_GAME_ID,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_sealed_catalog import (
    STRATEGIC_SEALED_CASE_CATALOG_ENTRY_SCHEMA,
    STRATEGIC_SEALED_CASE_CATALOG_SCHEMA,
    STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256,
    StrategicSealedCaseCatalog,
    StrategicSealedCaseCatalogError,
    open_strategic_sealed_case_input,
    parse_strategic_sealed_case_catalog,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    load_strategic_sealed_evaluation_plan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def _catalog_document() -> dict[str, object]:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    return {
        "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
        "cases": [
            {
                "capture": {
                    "checkpoint_id": f"sealed-fixture-{case.ordinal:02d}",
                    "envelope_sha256": f"{case.ordinal + 100:064x}",
                    "state_bytes": 131_072 + case.ordinal,
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
        "execution_configuration_sha256": (
            STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256
        ),
        "game_id": STRATEGIC_NAVIGATION_GAME_ID,
        "plan_sha256": plan.plan_sha256,
        "rom_identity": {
            "sha1": POKEMON_RED_US_REV_0.sha1,
            "sha256": POKEMON_RED_US_REV_0.sha256,
            "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
            "title": POKEMON_RED_US_REV_0.title,
        },
        "runtime_sha256": "a" * 64,
        "schema": STRATEGIC_SEALED_CASE_CATALOG_SCHEMA,
        "source_scenario_registry_sha256": plan.source_scenario_registry_sha256,
        "teacher_execution_sha256": plan.teacher_execution_sha256,
    }


def _parse(document: dict[str, object]) -> StrategicSealedCaseCatalog:
    return parse_strategic_sealed_case_catalog(
        _canonical(document),
        plan=load_strategic_sealed_evaluation_plan(PROJECT_ROOT),
        scenario_registry=load_strategic_navigation_scenario_registry(PROJECT_ROOT),
    )


def test_catalog_binds_every_case_without_paths_or_results() -> None:
    document = _catalog_document()
    payload = _canonical(document)
    catalog = _parse(document)

    assert catalog.catalog_sha256 == hashlib.sha256(payload).hexdigest()
    assert catalog.payload_bytes == len(payload)
    assert tuple(case.ordinal for case in catalog.cases) == tuple(range(1, 13))
    assert catalog.case(catalog.cases[4].case_id) is catalog.cases[4]
    encoded = payload.decode("ascii")
    assert "path" not in encoded
    assert "teacher_objective" not in encoded
    assert "route_cost" not in encoded
    assert "prediction" not in encoded
    assert "outcome" not in encoded


def test_catalog_objects_cannot_be_forged_directly() -> None:
    catalog = _parse(_catalog_document())

    with pytest.raises(StrategicSealedCaseCatalogError, match="canonical parser"):
        StrategicSealedCaseCatalog(
            catalog_sha256=catalog.catalog_sha256,
            payload_bytes=catalog.payload_bytes,
            evaluation_id=catalog.evaluation_id,
            plan_sha256=catalog.plan_sha256,
            source_scenario_registry_sha256=(
                catalog.source_scenario_registry_sha256
            ),
            teacher_execution_sha256=catalog.teacher_execution_sha256,
            runtime_sha256=catalog.runtime_sha256,
            execution_configuration_sha256=(
                catalog.execution_configuration_sha256
            ),
            rom_title=catalog.rom_title,
            rom_size_bytes=catalog.rom_size_bytes,
            rom_sha1=catalog.rom_sha1,
            rom_sha256=catalog.rom_sha256,
            cases=catalog.cases,
            _validation_token=object(),
        )
    with pytest.raises(TypeError, match="InitVar"):
        replace(catalog, runtime_sha256="b" * 64)
    with pytest.raises(TypeError, match="InitVar"):
        replace(catalog.cases[0], capture_state_sha256="c" * 64)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda value: value.update(plan_sha256="f" * 64),
            "public identity differs",
        ),
        (
            lambda value: value.update(runtime_sha256="not-a-digest"),
            "runtime is invalid",
        ),
        (
            lambda value: value["rom_identity"].update(title="POKEMON BLUE"),
            "ROM identity differs",
        ),
        (
            lambda value: value["cases"].reverse(),
            "order or identity differs",
        ),
        (
            lambda value: value["cases"][0].update(teacher_objective_id="hidden"),
            "fields differ",
        ),
        (
            lambda value: value["cases"][0]["capture"].update(path="private"),
            "fields differ",
        ),
        (
            lambda value: value["cases"][1]["capture"].update(
                state_sha256=value["cases"][0]["capture"]["state_sha256"]
            ),
            "state digest is duplicated",
        ),
        (
            lambda value: value["cases"][0]["capture"].update(state_bytes=True),
            "state size is invalid",
        ),
    ),
)
def test_catalog_rejects_semantic_mutations(
    mutate: object,
    message: str,
) -> None:
    document = deepcopy(_catalog_document())
    mutate(document)

    with pytest.raises(StrategicSealedCaseCatalogError, match=message):
        _parse(document)


def test_catalog_requires_canonical_unique_key_json() -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    noncanonical = json.dumps(_catalog_document(), indent=2).encode("ascii")

    with pytest.raises(StrategicSealedCaseCatalogError, match="not canonical"):
        parse_strategic_sealed_case_catalog(
            noncanonical,
            plan=plan,
            scenario_registry=registry,
        )

    duplicate = _canonical(_catalog_document()).replace(
        b'{"adapter_id":',
        b'{"adapter_id":"duplicate","adapter_id":',
        1,
    )
    with pytest.raises(StrategicSealedCaseCatalogError, match="duplicated"):
        parse_strategic_sealed_case_catalog(
            duplicate,
            plan=plan,
            scenario_registry=registry,
        )


def test_catalog_rejects_a_registry_not_bound_to_the_plan() -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)

    with pytest.raises(StrategicSealedCaseCatalogError, match="registry differs"):
        parse_strategic_sealed_case_catalog(
            _canonical(_catalog_document()),
            plan=plan,
            scenario_registry=replace(registry, registry_sha256="b" * 64),
        )


def _write_synthetic_case_input(
    root: Path,
    *,
    document: dict[str, object],
    objective_ids: tuple[str, ...],
) -> bytes:
    state = b"synthetic ROM-free PyBoy state fixture"
    state_sha256 = hashlib.sha256(state).hexdigest()
    capture = document["cases"][0]["capture"]
    capture.update(
        {
            "checkpoint_id": "sealed-synthetic-01",
            "state_bytes": len(state),
            "state_sha256": state_sha256,
        }
    )
    envelope = {
        "checkpoint_id": "sealed-synthetic-01",
        "checkpoint_label": "ROM-free synthetic sealed fixture",
        "checkpoints_completed": len(objective_ids),
        "checkpoints_total": len(objective_ids) + 1,
        "schema": "pokemon-private-captured-progress-v1",
        "state_sha256": state_sha256,
        "verified_objective_ids": list(objective_ids),
    }
    capture["envelope_sha256"] = canonical_sha256(envelope)
    case_directory = root / document["cases"][0]["case_id"]
    case_directory.mkdir(parents=True)
    (case_directory / "capture.state").write_bytes(state)
    (case_directory / "capture.state.json").write_text(
        json.dumps(envelope, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="ascii",
    )
    return state


def test_case_input_opener_reads_only_the_digest_bound_synthetic_layout(
    tmp_path: Path,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = next(
        item
        for item in registry.scenarios
        if item.scenario_id == plan.cases[0].source_scenario_id
    )
    document = _catalog_document()
    state = _write_synthetic_case_input(
        tmp_path,
        document=document,
        objective_ids=scenario.completed_objective_ids,
    )
    catalog = _parse(document)

    opened = open_strategic_sealed_case_input(
        tmp_path,
        entry=catalog.cases[0],
        scenario=scenario,
    )

    assert opened.state_bytes == state
    assert opened.envelope.checkpoint_id == "sealed-synthetic-01"
    assert opened.entry is catalog.cases[0]
    with pytest.raises(TypeError, match="InitVar"):
        replace(opened, state_bytes=b"replacement")


def test_case_input_opener_rejects_symlinks_without_disclosing_the_root(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "do-not-disclose-private-root"
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = next(
        item
        for item in registry.scenarios
        if item.scenario_id == plan.cases[0].source_scenario_id
    )
    document = _catalog_document()
    _write_synthetic_case_input(
        private_root,
        document=document,
        objective_ids=scenario.completed_objective_ids,
    )
    catalog = _parse(document)
    state_path = private_root / catalog.cases[0].case_id / "capture.state"
    external = tmp_path / "external.state"
    external.write_bytes(state_path.read_bytes())
    state_path.unlink()
    state_path.symlink_to(external)

    with pytest.raises(StrategicSealedCaseCatalogError) as caught:
        open_strategic_sealed_case_input(
            private_root,
            entry=catalog.cases[0],
            scenario=scenario,
        )

    assert "do-not-disclose" not in str(caught.value)
    assert str(private_root) not in str(caught.value)


def test_case_input_opener_rejects_a_symlinked_root_component(
    tmp_path: Path,
) -> None:
    actual_root = tmp_path / "actual-private-root"
    alias_root = tmp_path / "private-root-alias"
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = next(
        item
        for item in registry.scenarios
        if item.scenario_id == plan.cases[0].source_scenario_id
    )
    document = _catalog_document()
    _write_synthetic_case_input(
        actual_root,
        document=document,
        objective_ids=scenario.completed_objective_ids,
    )
    alias_root.symlink_to(actual_root, target_is_directory=True)
    catalog = _parse(document)

    with pytest.raises(StrategicSealedCaseCatalogError) as caught:
        open_strategic_sealed_case_input(
            alias_root,
            entry=catalog.cases[0],
            scenario=scenario,
        )

    assert "actual-private-root" not in str(caught.value)
    assert "private-root-alias" not in str(caught.value)


def test_case_input_opener_refuses_a_relative_private_root() -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = next(
        item
        for item in registry.scenarios
        if item.scenario_id == plan.cases[0].source_scenario_id
    )
    catalog = _parse(_catalog_document())

    with pytest.raises(StrategicSealedCaseCatalogError, match="must be absolute"):
        open_strategic_sealed_case_input(
            Path("relative-private-root"),
            entry=catalog.cases[0],
            scenario=scenario,
        )


def test_case_input_opener_rejects_capture_mutation_and_frontier_drift(
    tmp_path: Path,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = next(
        item
        for item in registry.scenarios
        if item.scenario_id == plan.cases[0].source_scenario_id
    )
    document = _catalog_document()
    _write_synthetic_case_input(
        tmp_path,
        document=document,
        objective_ids=scenario.completed_objective_ids,
    )
    catalog = _parse(document)
    state_path = tmp_path / catalog.cases[0].case_id / "capture.state"
    state_path.write_bytes(b"same length is not needed for this refusal")

    with pytest.raises(StrategicSealedCaseCatalogError, match="size differs"):
        open_strategic_sealed_case_input(
            tmp_path,
            entry=catalog.cases[0],
            scenario=scenario,
        )

    state_path.write_bytes(b"synthetic ROM-free PyBoy state fixture")
    envelope_path = state_path.with_suffix(".state.json")
    envelope = json.loads(envelope_path.read_text(encoding="ascii"))
    envelope["verified_objective_ids"] = ["power_on"]
    envelope_path.write_text(
        json.dumps(envelope, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="ascii",
    )
    with pytest.raises(StrategicSealedCaseCatalogError, match="envelope differs"):
        open_strategic_sealed_case_input(
            tmp_path,
            entry=catalog.cases[0],
            scenario=scenario,
        )
