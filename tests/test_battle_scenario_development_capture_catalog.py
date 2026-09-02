from __future__ import annotations

import json
import runpy
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_scenario_development_capture_catalog import (
    BATTLE_SCENARIO_DEVELOPMENT_CAPTURE_CATALOG_SCHEMA,
    BattleScenarioDevelopmentCaptureCatalogError,
    BattleScenarioDevelopmentCaptureCatalogV2,
    BattleScenarioDevelopmentCaptureEntry,
    BattleScenarioDevelopmentCaptureEntryV2,
    BattleScenarioDevelopmentCaptureProducer,
    BattleScenarioDevelopmentCaptureProducerV2,
    build_battle_scenario_development_capture_catalog,
    build_battle_scenario_development_capture_catalog_v2,
    parse_battle_scenario_development_capture_catalog,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

HELPERS = runpy.run_path("tests/test_battle_scenario_materialization_plan_v2.py")


def _sha(marker: str) -> str:
    return HELPERS["_sha"](marker)


def _catalog():  # type: ignore[no-untyped-def]
    candidates = tuple(
        HELPERS["_candidate"](index, partition=ScenarioPartition.DEVELOPMENT) for index in range(20)
    )
    plan = HELPERS["_build"](candidates)
    producer = BattleScenarioDevelopmentCaptureProducer(
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        run_journal_sha256=_sha("terminal-journal"),
        source_commit=plan.source_commit,
        source_bundle_sha256=_sha("source-bundle"),
        materializer_sha256=_sha("materializer"),
        runtime_identity_sha256=_sha("runtime"),
        rom_sha256=plan.rom_sha256,
        capture_directory_sha256=plan.capture_directory_sha256,
        context_catalog_sha256=plan.inventory[0].source.catalog_sha256,
        registry_sha256=plan.inventory[0].source.registry_sha256,
        registry_source_commit=plan.inventory[0].source.registry_source_commit,
        exact_ci_run=123,
        exact_ci_attempt=1,
    )
    entries = tuple(
        BattleScenarioDevelopmentCaptureEntry(
            ordinal=assignment.ordinal,
            capture_id=assignment.capture_id,
            assignment_sha256=_sha(f"assignment-{assignment.ordinal}"),
            source_state_sha256=assignment.candidate.source.source_state_sha256,
            root_lineage_id=assignment.candidate.source.root_lineage_id,
            venue_id=assignment.selected_venue.venue_id,
            party_slot=assignment.party_slot,
            state_filename=assignment.state_filename,
            manifest_filename=assignment.manifest_filename,
            state_sha256=_sha(f"state-{assignment.ordinal}"),
            manifest_sha256=_sha(f"manifest-{assignment.ordinal}"),
        )
        for assignment in plan.assignments
    )
    return build_battle_scenario_development_capture_catalog(
        catalog_id="red-battle-v2-development-catalog",
        builder_source_commit="f" * 40,
        builder_source_bundle_sha256=_sha("builder-bundle"),
        producer=producer,
        captures=tuple(reversed(entries)),
    )


def _catalog_v2() -> BattleScenarioDevelopmentCaptureCatalogV2:
    original = _catalog()

    def producer(role: str) -> BattleScenarioDevelopmentCaptureProducerV2:
        return BattleScenarioDevelopmentCaptureProducerV2(
            producer_id=role,
            role=role,
            plan_id=f"development-{role}",
            plan_sha256=_sha(f"{role}-plan"),
            run_journal_sha256=_sha(f"{role}-journal"),
            source_commit=("e" if role == "predecessor" else "d") * 40,
            source_bundle_sha256=_sha(f"{role}-bundle"),
            materializer_sha256=_sha(f"{role}-materializer"),
            runtime_identity_sha256=_sha("runtime"),
            rom_sha256=_sha("rom"),
            capture_directory_sha256=_sha(f"{role}-directory"),
            context_catalog_sha256=_sha("context"),
            registry_sha256=_sha("registry"),
            registry_source_commit="c" * 40,
            exact_ci_run=123,
            exact_ci_attempt=1,
            successful_capture_count=7 if role == "predecessor" else 1,
            failed_assignment_count=1 if role == "predecessor" else 0,
        )

    captures = tuple(
        BattleScenarioDevelopmentCaptureEntryV2(
            ordinal=item.ordinal,
            capture_id=item.capture_id,
            assignment_sha256=item.assignment_sha256,
            source_state_sha256=item.source_state_sha256,
            root_lineage_id=item.root_lineage_id,
            venue_id=item.venue_id,
            party_slot=item.party_slot,
            state_filename=item.state_filename,
            manifest_filename=item.manifest_filename,
            state_sha256=item.state_sha256,
            manifest_sha256=item.manifest_sha256,
            producer_id="predecessor" if item.ordinal < 7 else "completion",
            producer_ordinal=item.ordinal if item.ordinal < 7 else 0,
        )
        for item in original.captures
    )
    return build_battle_scenario_development_capture_catalog_v2(
        catalog_id="red-battle-v2-development-catalog-v2",
        builder_source_commit="f" * 40,
        builder_source_bundle_sha256=_sha("builder-bundle"),
        rom_sha256=_sha("rom"),
        producers=(producer("completion"), producer("predecessor")),
        captures=tuple(reversed(captures)),
    )


def test_development_capture_catalog_round_trips_canonically() -> None:
    catalog = _catalog()
    reopened = parse_battle_scenario_development_capture_catalog(catalog.canonical_bytes())

    assert reopened == catalog
    assert reopened.private_dict()["schema"] == (BATTLE_SCENARIO_DEVELOPMENT_CAPTURE_CATALOG_SCHEMA)
    assert tuple(item.ordinal for item in reopened.captures) == tuple(range(8))
    assert reopened.private_dict()["partition"] == "development"
    assert set(reopened.private_dict()["effects"].values()) == {0}


def test_development_capture_catalog_rejects_duplicate_root_or_output() -> None:
    catalog = _catalog()
    duplicate_root = replace(
        catalog.captures[1],
        source_state_sha256=catalog.captures[0].source_state_sha256,
    )
    with pytest.raises(
        BattleScenarioDevelopmentCaptureCatalogError,
        match="identity repeats",
    ):
        replace(
            catalog,
            captures=(catalog.captures[0], duplicate_root, *catalog.captures[2:]),
        )


def test_development_capture_catalog_rejects_venue_drift() -> None:
    catalog = _catalog()
    changed = replace(catalog.captures[0], venue_id="route_11")

    with pytest.raises(
        BattleScenarioDevelopmentCaptureCatalogError,
        match="venue distribution differs",
    ):
        replace(catalog, captures=(changed, *catalog.captures[1:]))


def test_development_capture_catalog_rejects_noncanonical_or_extra_fields() -> None:
    catalog = _catalog()
    document = json.loads(catalog.canonical_bytes())
    document["unexpected"] = True
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()

    with pytest.raises(
        BattleScenarioDevelopmentCaptureCatalogError,
        match="fields differ",
    ):
        parse_battle_scenario_development_capture_catalog(payload + b"\n")
    with pytest.raises(
        BattleScenarioDevelopmentCaptureCatalogError,
        match="not canonical JSON",
    ):
        parse_battle_scenario_development_capture_catalog(
            catalog.canonical_bytes().replace(b'"catalog_id":', b'"catalog_id" :')
        )


def test_development_capture_catalog_contains_no_paths_or_learning_results() -> None:
    payload = _catalog().canonical_bytes()

    for forbidden in (
        b"/Volumes/",
        b'"prediction":',
        b'"preferred_action":',
        b'"teacher_choice":',
        b'"outcome":',
    ):
        assert forbidden not in payload


def test_development_capture_catalog_v2_preserves_seven_plus_one_provenance() -> None:
    catalog = _catalog_v2()
    reopened = parse_battle_scenario_development_capture_catalog(catalog.canonical_bytes())

    assert reopened == catalog
    assert isinstance(reopened, BattleScenarioDevelopmentCaptureCatalogV2)
    assert tuple(item.role for item in reopened.producers) == (
        "predecessor",
        "completion",
    )
    assert [item.producer_id for item in reopened.captures].count("predecessor") == 7
    assert [item.producer_id for item in reopened.captures].count("completion") == 1
    assert reopened.private_dict()["historical_failed_assignments"] == 1


def test_development_capture_catalog_v2_rejects_flattened_provenance() -> None:
    catalog = _catalog_v2()
    flattened = replace(catalog.captures[-1], producer_id="predecessor")

    with pytest.raises(
        BattleScenarioDevelopmentCaptureCatalogError,
        match="producer membership differs",
    ):
        replace(catalog, captures=(*catalog.captures[:-1], flattened))
