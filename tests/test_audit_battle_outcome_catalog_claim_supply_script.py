from __future__ import annotations

import runpy

import pytest

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAvailabilitySnapshot,
    ClaimFirstPairAvailability,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/audit_battle_outcome_catalog_claim_supply.py")


def _root(partition: ScenarioPartition, logical: str, physical: str):  # type: ignore[no-untyped-def]
    return SCRIPT["CatalogRoot"](
        partition=partition,
        logical_root_sha256=logical,
        physical_root_sha256=physical,
    )


def test_cli_has_no_state_rom_manifest_model_or_gameplay_input() -> None:
    destinations = {
        action.dest for action in SCRIPT["_parser"]()._actions  # noqa: SLF001
    }

    assert {"train_capture_catalog", "development_capture_catalog"} <= destinations
    assert not destinations.intersection(
        {
            "state",
            "capture_manifest",
            "rom",
            "base_model",
            "controller",
            "teacher",
        }
    )


def test_availability_counts_authenticated_catalog_roots_by_partition() -> None:
    pairs = (
        ("1" * 64, "2" * 64, True),
        ("3" * 64, "4" * 64, False),
        ("5" * 64, "6" * 64, False),
    )
    roots = (
        _root(ScenarioPartition.TRAIN, pairs[0][0], pairs[0][1]),
        _root(ScenarioPartition.TRAIN, pairs[1][0], pairs[1][1]),
        _root(ScenarioPartition.DEVELOPMENT, pairs[2][0], pairs[2][1]),
    )
    snapshot = ClaimFirstAvailabilitySnapshot(
        registry_state_sha256="7" * 64,
        observations=tuple(
            ClaimFirstPairAvailability(
                logical_root_sha256=logical,
                physical_root_sha256=physical,
                available=available,
            )
            for logical, physical, available in pairs
        ),
    )

    assert SCRIPT["_availability_counts"](roots, snapshot) == {
        "train_total": 2,
        "train_available": 1,
        "train_claimed": 1,
        "development_total": 1,
        "development_available": 0,
        "development_claimed": 1,
    }


def test_catalog_root_derives_logical_identity_and_rejects_lineage_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_catalog_root"].__globals__
    binding = type(
        "Binding",
        (),
        {"root_lineage_id": "expected-lineage", "root_consumption_sha256": "1" * 64},
    )()
    observed: list[object] = []

    def authenticate(source: str, **kwargs: object):  # type: ignore[no-untyped-def]
        observed.extend((source, kwargs["expected_partition"]))
        return binding

    monkeypatch.setitem(
        globals_,
        "authenticate_battle_scenario_source_binding",
        authenticate,
    )

    result = SCRIPT["_catalog_root"](
        partition=ScenarioPartition.TRAIN,
        source_state_sha256="2" * 64,
        state_sha256="3" * 64,
        root_lineage_id="expected-lineage",
        context_catalog=object(),
        registry=object(),
    )

    assert result.logical_root_sha256 == "1" * 64
    assert result.physical_root_sha256 == "3" * 64
    assert observed == ["2" * 64, ScenarioPartition.TRAIN]

    with pytest.raises(
        SCRIPT["BattleOutcomeCatalogClaimSupplyAuditError"],
        match="lineage differs",
    ):
        SCRIPT["_catalog_root"](
            partition=ScenarioPartition.TRAIN,
            source_state_sha256="2" * 64,
            state_sha256="3" * 64,
            root_lineage_id="substituted-lineage",
            context_catalog=object(),
            registry=object(),
        )
