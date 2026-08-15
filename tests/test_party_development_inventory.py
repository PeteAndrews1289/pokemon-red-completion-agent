from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.party_development_inventory import (
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
    PartyDevelopmentInventoryError,
    PartyDevelopmentInventoryMember,
    level_distance_bin,
    unit_bin,
)
from pokemon_red_completion.party_development_rank import (
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _member(
    *,
    level: int,
    hp_bin: str,
    route: EvolutionRouteKind = EvolutionRouteKind.NONE,
) -> PartyDevelopmentInventoryMember:
    return PartyDevelopmentInventoryMember(
        level=level,
        hp_bin=hp_bin,
        pp_bin="high",
        status_present=False,
        trainable=True,
        evolution_routes=(route,),
        level_evolution_distance_bin=(
            "near" if route is EvolutionRouteKind.LEVEL else "none"
        ),
        registration_target_needed=route is not EvolutionRouteKind.NONE,
        living_target_needed=route is not EvolutionRouteKind.NONE,
        role_complete=level >= 30,
    )


def _entry(
    *,
    checkpoint: str,
    partition: ScenarioPartition,
    digest: str,
    low_health: bool,
) -> PartyDevelopmentInventoryEntry:
    members = (
        _member(
            level=20,
            hp_bin="low" if low_health else "high",
            route=EvolutionRouteKind.LEVEL,
        ),
        _member(level=40, hp_bin="high"),
    )
    ordered = tuple(sorted(members, key=lambda item: item.semantic_tuple()))
    return PartyDevelopmentInventoryEntry(
        checkpoint_id=checkpoint,
        partition=partition,
        state_sha256=digest * 64,
        envelope_sha256=("c" if digest == "a" else "d") * 64,
        controls_ready=True,
        battle_active=False,
        members=ordered,
        registration_owned_count=20,
        registration_target_count=124,
        living_unique_count=18,
        living_target_count=120,
        specimen_count=22,
        role_coverage_count=1,
        role_target_count=6,
        storage_headroom=200,
        goal_hints=tuple(PartyDevelopmentGoal),
    )


def test_path_free_inventory_summary_is_diagnostic_and_partitioned() -> None:
    inventory = PartyDevelopmentCheckpointInventory(
        (
            _entry(
                checkpoint="party-development-development-01",
                partition=ScenarioPartition.DEVELOPMENT,
                digest="b",
                low_health=False,
            ),
            _entry(
                checkpoint="party-development-train-01",
                partition=ScenarioPartition.TRAIN,
                digest="a",
                low_health=True,
            ),
        )
    )

    summary = inventory.summary_dict()
    entry = inventory.private_dict()["entries"][0]

    assert summary["partition_counts"] == {"development": 1, "train": 1}
    assert summary["ready_multi_candidate_contexts"] == {
        "development": 1,
        "train": 1,
    }
    assert summary["prospective_catalog_frozen"] is False
    assert summary["outcomes_collected"] == 0
    assert summary["controller_actions"] == 0
    assert summary["authority_promoted"] is False
    assert isinstance(entry, dict)
    assert entry["schema"] == (
        "pokemon.core.party-development-checkpoint-inventory-entry.v1"
    )
    assert entry["semantics"]["schema"] == (  # type: ignore[index]
        "pokemon.core.party-development-checkpoint-semantics.v1"
    )
    encoded = json.dumps(summary, sort_keys=True)
    assert "party-development-train-01" not in encoded
    assert "species" not in encoded
    assert "/Users/" not in encoded


def test_inventory_rejects_reused_state_and_member_identity_order() -> None:
    first = _entry(
        checkpoint="party-development-train-01",
        partition=ScenarioPartition.TRAIN,
        digest="a",
        low_health=True,
    )
    duplicate_state = replace(
        first,
        checkpoint_id="party-development-train-02",
        envelope_sha256="d" * 64,
    )
    with pytest.raises(PartyDevelopmentInventoryError, match="repeats a state"):
        PartyDevelopmentCheckpointInventory((first, duplicate_state))

    with pytest.raises(PartyDevelopmentInventoryError, match="semantic order"):
        replace(first, members=tuple(reversed(first.members)))


def test_resource_and_evolution_bins_are_deterministic() -> None:
    assert tuple(unit_bin(value) for value in (0.0, 0.2, 0.5, 0.9)) == (
        "empty",
        "low",
        "middle",
        "high",
    )
    assert tuple(level_distance_bin(value) for value in (None, 0, 2, 8, 20)) == (
        "unknown",
        "ready",
        "near",
        "medium",
        "far",
    )
    with pytest.raises(PartyDevelopmentInventoryError, match="contradicts"):
        PartyDevelopmentInventoryMember(
            level=20,
            hp_bin="high",
            pp_bin="high",
            status_present=False,
            trainable=True,
            evolution_routes=(EvolutionRouteKind.LEVEL,),
            level_evolution_distance_bin="none",
            registration_target_needed=True,
            living_target_needed=True,
            role_complete=False,
        )
