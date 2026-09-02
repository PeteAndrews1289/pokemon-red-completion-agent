from __future__ import annotations

import json
import runpy
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_scenario_development_capture_catalog import (
    BATTLE_SCENARIO_DEVELOPMENT_CAPTURE_CATALOG_SCHEMA,
    BattleScenarioDevelopmentCaptureCatalogError,
    BattleScenarioDevelopmentCaptureEntry,
    BattleScenarioDevelopmentCaptureProducer,
    build_battle_scenario_development_capture_catalog,
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
