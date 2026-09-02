from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_scenario_capture_catalog import (
    BattleScenarioCaptureCatalogEntry,
    BattleScenarioCaptureCatalogError,
    BattleScenarioCaptureProducer,
    build_battle_scenario_capture_catalog,
    parse_battle_scenario_capture_catalog,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (
    BattleScenarioPartySlot,
)


def _sha(value: int) -> str:
    return f"{value:064x}"


def _producer(role: str) -> BattleScenarioCaptureProducer:
    predecessor = role == "predecessor"
    return BattleScenarioCaptureProducer(
        producer_id=role,
        role=role,
        plan_id=f"plan-{role}",
        plan_sha256=_sha(1 if predecessor else 2),
        run_journal_sha256=_sha(3 if predecessor else 4),
        source_commit=("a" if predecessor else "b") * 40,
        source_bundle_sha256=_sha(5 if predecessor else 6),
        materializer_sha256=_sha(7 if predecessor else 8),
        runtime_identity_sha256=_sha(9 if predecessor else 10),
        rom_sha256=_sha(11),
        capture_directory_sha256=_sha(12 if predecessor else 13),
        context_catalog_sha256=_sha(14),
        registry_sha256=_sha(15),
        registry_source_commit="c" * 40,
        exact_ci_run=100 if predecessor else 101,
        exact_ci_attempt=1,
        successful_capture_count=5 if predecessor else 2,
        failed_assignment_count=2 if predecessor else 0,
    )


def _slot(index: int) -> BattleScenarioPartySlot:
    return BattleScenarioPartySlot(
        party_slot=(index % 6) + 1,
        species_id=index + 1,
        level=20,
        current_hp=30,
        maximum_hp=30,
        status_id=0,
        usable_move_count=2,
    )


def _entry(index: int) -> BattleScenarioCaptureCatalogEntry:
    predecessor = index < 5
    local = (0, 2, 4, 5, 6)[index] if predecessor else index - 5
    return BattleScenarioCaptureCatalogEntry(
        ordinal=index,
        producer_id="predecessor" if predecessor else "completion",
        producer_ordinal=local,
        capture_id=f"capture-{index}",
        assignment_sha256=_sha(100 + index),
        source_state_sha256=_sha(200 + index),
        root_lineage_id=f"root-{index}",
        venue_id="digletts_cave" if index < 4 else "route_11",
        party_slot=_slot(index),
        state_filename=f"capture-{index}.state",
        manifest_filename=f"capture-{index}.state.json",
        state_sha256=_sha(300 + index),
        manifest_sha256=_sha(400 + index),
    )


def _catalog():  # type: ignore[no-untyped-def]
    return build_battle_scenario_capture_catalog(
        catalog_id="battle-v2-seven-inputs",
        builder_source_commit="d" * 40,
        builder_source_bundle_sha256=_sha(500),
        rom_sha256=_sha(11),
        producers=(_producer("completion"), _producer("predecessor")),
        captures=tuple(reversed(tuple(_entry(index) for index in range(7)))),
    )


def test_catalog_canonicalizes_two_producers_and_seven_captures() -> None:
    catalog = _catalog()

    assert tuple(item.role for item in catalog.producers) == (
        "predecessor",
        "completion",
    )
    assert tuple(item.ordinal for item in catalog.captures) == tuple(range(7))
    assert tuple(item.producer_id for item in catalog.captures) == (
        "predecessor",
        "predecessor",
        "predecessor",
        "predecessor",
        "predecessor",
        "completion",
        "completion",
    )
    assert parse_battle_scenario_capture_catalog(catalog.canonical_bytes()) == catalog
    assert catalog.private_dict()["effects"] == {
        "authority_promoted": False,
        "controller_actions": 0,
        "crystal_contexts_opened": 0,
        "emulator_frames": 0,
        "model_fits": 0,
        "move_choices_executed": 0,
        "outcomes_opened": 0,
        "predictions_computed": 0,
        "red_sealed_test_cases_opened": 0,
        "root_claims_created": 0,
        "teacher_choice_targets": 0,
        "teacher_queries": 0,
    }


def test_catalog_rejects_flattened_producer_commit() -> None:
    predecessor = _producer("predecessor")
    completion = replace(
        _producer("completion"),
        source_commit=predecessor.source_commit,
    )

    with pytest.raises(BattleScenarioCaptureCatalogError, match="producer catalog"):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(predecessor, completion),
            captures=tuple(_entry(index) for index in range(7)),
        )


def test_catalog_rejects_missing_or_duplicate_producer_role() -> None:
    predecessor = _producer("predecessor")

    with pytest.raises(BattleScenarioCaptureCatalogError, match="producer catalog"):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(predecessor,),
            captures=tuple(_entry(index) for index in range(7)),
        )
    with pytest.raises(BattleScenarioCaptureCatalogError, match="producer catalog"):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(predecessor, predecessor),
            captures=tuple(_entry(index) for index in range(7)),
        )


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("capture_id", "identity repeats"),
        ("source_state_sha256", "identity repeats"),
        ("root_lineage_id", "identity repeats"),
        ("state_sha256", "identity repeats"),
        ("manifest_sha256", "identity repeats"),
    ),
)
def test_catalog_rejects_repeated_capture_identity(field: str, message: str) -> None:
    entries = [_entry(index) for index in range(7)]
    entries[6] = replace(entries[6], **{field: getattr(entries[0], field)})

    with pytest.raises(BattleScenarioCaptureCatalogError, match=message):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(_producer("predecessor"), _producer("completion")),
            captures=entries,
        )


def test_catalog_rejects_single_venue_flattening() -> None:
    entries = [replace(_entry(index), venue_id="digletts_cave") for index in range(7)]

    with pytest.raises(BattleScenarioCaptureCatalogError, match="venue distribution"):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(_producer("predecessor"), _producer("completion")),
            captures=entries,
        )


def test_catalog_rejects_changed_two_venue_denominator() -> None:
    entries = [_entry(index) for index in range(7)]
    entries[3] = replace(entries[3], venue_id="route_11")

    with pytest.raises(BattleScenarioCaptureCatalogError, match="venue distribution"):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(_producer("predecessor"), _producer("completion")),
            captures=entries,
        )


def test_catalog_accepts_a_different_authenticated_predecessor_failure_pattern() -> None:
    entries = [_entry(index) for index in range(7)]
    for index, producer_ordinal in enumerate((1, 2, 3, 4, 6)):
        entries[index] = replace(entries[index], producer_ordinal=producer_ordinal)

    catalog = build_battle_scenario_capture_catalog(
        catalog_id="battle-v2-seven-inputs",
        builder_source_commit="d" * 40,
        builder_source_bundle_sha256=_sha(500),
        rom_sha256=_sha(11),
        producers=(_producer("predecessor"), _producer("completion")),
        captures=entries,
    )

    assert tuple(item.producer_ordinal for item in catalog.captures[:5]) == (
        1,
        2,
        3,
        4,
        6,
    )


@pytest.mark.parametrize("rewritten", (2, 7))
def test_catalog_rejects_duplicate_or_out_of_range_success_ordinal(
    rewritten: int,
) -> None:
    entries = [_entry(index) for index in range(7)]
    entries[0] = replace(entries[0], producer_ordinal=rewritten)

    with pytest.raises(BattleScenarioCaptureCatalogError, match="ordinal membership"):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(_producer("predecessor"), _producer("completion")),
            captures=entries,
        )


def test_catalog_rejects_failure_admitted_as_an_eighth_capture() -> None:
    with pytest.raises(BattleScenarioCaptureCatalogError, match="catalog ordinal"):
        build_battle_scenario_capture_catalog(
            catalog_id="battle-v2-seven-inputs",
            builder_source_commit="d" * 40,
            builder_source_bundle_sha256=_sha(500),
            rom_sha256=_sha(11),
            producers=(_producer("predecessor"), _producer("completion")),
            captures=tuple(_entry(index) for index in range(7)) + (_entry(7),),
        )


def test_catalog_rejects_noncanonical_and_duplicate_json() -> None:
    payload = _catalog().canonical_bytes()
    with pytest.raises(BattleScenarioCaptureCatalogError, match="not canonical"):
        parse_battle_scenario_capture_catalog(payload.replace(b'"status"', b' "status"', 1))
    with pytest.raises(BattleScenarioCaptureCatalogError, match="not canonical"):
        parse_battle_scenario_capture_catalog(b'{"schema":"x","schema":"y"}\n')


def test_catalog_rejects_effect_overclaim() -> None:
    value = json.loads(_catalog().canonical_bytes())
    value["effects"]["outcomes_opened"] = 1
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

    with pytest.raises(BattleScenarioCaptureCatalogError, match="fields differ"):
        parse_battle_scenario_capture_catalog(payload)
