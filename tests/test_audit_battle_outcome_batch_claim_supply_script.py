from __future__ import annotations

import runpy
from types import SimpleNamespace

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAvailabilitySnapshot,
    ClaimFirstPairAvailability,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/audit_battle_outcome_batch_claim_supply.py")


def _candidate(partition: ScenarioPartition, logical: str, physical: str):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        partition=partition,
        binding=SimpleNamespace(
            logical_root_sha256=logical,
            physical_root_sha256=physical,
        ),
    )


def test_claim_supply_counts_each_partition_without_creating_claims() -> None:
    pairs = (
        ("1" * 64, "2" * 64, True),
        ("3" * 64, "4" * 64, False),
        ("5" * 64, "6" * 64, False),
    )
    candidates = (
        _candidate(ScenarioPartition.TRAIN, pairs[0][0], pairs[0][1]),
        _candidate(ScenarioPartition.TRAIN, pairs[1][0], pairs[1][1]),
        _candidate(ScenarioPartition.DEVELOPMENT, pairs[2][0], pairs[2][1]),
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

    assert SCRIPT["_availability_counts"](candidates, snapshot) == {
        "fresh_train_total": 2,
        "fresh_train_available": 1,
        "fresh_train_claimed": 1,
        "development_total": 1,
        "development_available": 0,
        "development_claimed": 1,
    }
