from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_crystal_completion.goal_state import (
    CrystalCampaignSnapshot,
    CrystalCapability,
    CrystalCapabilityState,
    CrystalGoalManagerConfig,
    CrystalGoalStateError,
    PokemonCrystalGoalStateAdapter,
    project_crystal_goal_state,
)
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)


def _party(*, species_start: int = 152, level: int = 40) -> PartyObservation:
    return PartyObservation(
        tuple(
            PartyMemberObservation(
                slot=slot,
                species_id=species_start + slot - 1,
                level=level,
                hp=80,
                max_hp=80,
                moves=(MoveObservation(move_id=slot + 20, current_pp=15, max_pp=20),),
            )
            for slot in range(1, 7)
        )
    )


def _snapshot(*, party: PartyObservation | None = None) -> CrystalCampaignSnapshot:
    return CrystalCampaignSnapshot(
        story=CompletionProgress(8, 16),
        registered_collection=CompletionProgress(200, 250),
        living_collection=CompletionProgress(180, 250),
        level_collection=CompletionProgress(20, 250),
        evolution=CompletionProgress(50, 100),
        world_knowledge=CompletionProgress(125, 250),
        party=party or _party(),
        game_started=True,
        input_ready=True,
        capture_item_count=5,
        recovery_item_count=8,
        free_storage_slots=40,
        immediate_capture_slots=4,
        capabilities=CrystalCapabilityState(
            available=frozenset(
                {
                    CrystalCapability.BATTLE,
                    CrystalCapability.CAPTURE,
                    CrystalCapability.PC_STORAGE,
                }
            ),
            unknown=frozenset(
                set(CrystalCapability)
                - {
                    CrystalCapability.BATTLE,
                    CrystalCapability.CAPTURE,
                    CrystalCapability.PC_STORAGE,
                }
            ),
        ),
    )


def test_crystal_snapshot_projects_to_the_shared_nine_pressures() -> None:
    observation = project_crystal_goal_state(_snapshot())
    pressures = observation.policy_dict()["need_pressures"]

    assert pressures == pytest.approx(
        {
            "story_progress": 0.5,
            "collection_progress": 0.28,
            "team_readiness": 0.2,
            "evolution_progress": 0.5,
            "safety": 0.0,
            "resources": 0.5,
            "storage_capacity": 0.5,
            "control_recovery": 0.0,
            "world_knowledge": 0.5,
        }
    )


def test_projection_is_invariant_to_title_private_species_and_move_ids() -> None:
    first = project_crystal_goal_state(_snapshot(party=_party(species_start=1)))
    second = project_crystal_goal_state(_snapshot(party=_party(species_start=200)))

    assert first.policy_dict() == second.policy_dict()
    assert first.public_dict() == second.public_dict()
    encoded = json.dumps(second.public_dict(), sort_keys=True)
    for forbidden in (
        "pokemon.crystal",
        "breeding",
        "species_id",
        "move_id",
        "map_id",
        "/Users/",
        "/Volumes/",
        "0xdc",
    ):
        assert forbidden not in encoded.lower()
    assert second.public_dict()["capability_identity_in_model_input"] is False


def test_control_pressure_requires_started_and_input_ready_together() -> None:
    ready = _snapshot()
    not_started = replace(ready, game_started=False)
    blocked = replace(ready, input_ready=False)

    assert project_crystal_goal_state(ready).situation.recovery_pressure == 0.0
    assert project_crystal_goal_state(not_started).situation.recovery_pressure == 1.0
    assert project_crystal_goal_state(blocked).situation.recovery_pressure == 1.0


def test_reader_boundary_accepts_only_a_semantic_snapshot() -> None:
    expected = _snapshot()

    class Reader:
        def read_goal_state(self, raw: object) -> CrystalCampaignSnapshot:
            assert raw == "opaque-emulator-state"
            return expected

    adapter = PokemonCrystalGoalStateAdapter(reader=Reader())
    observation = adapter.observe("opaque-emulator-state")
    assert observation.snapshot is expected

    class BadReader:
        def read_goal_state(self, raw: object) -> object:
            del raw
            return {"wPartyCount": 6}

    with pytest.raises(CrystalGoalStateError, match="invalid campaign"):
        PokemonCrystalGoalStateAdapter(reader=BadReader()).observe(object())  # type: ignore[arg-type]


def test_snapshot_rejects_impossible_collection_or_capture_counts() -> None:
    base = _snapshot()
    with pytest.raises(CrystalGoalStateError, match="living collection"):
        replace(base, living_collection=CompletionProgress(201, 250))
    with pytest.raises(CrystalGoalStateError, match="level-cap collection"):
        replace(base, level_collection=CompletionProgress(181, 250))
    with pytest.raises(CrystalGoalStateError, match="capture slots"):
        replace(base, immediate_capture_slots=41)
    with pytest.raises(CrystalGoalStateError, match="boolean"):
        replace(base, input_ready=1)  # type: ignore[arg-type]


def test_normalization_targets_are_declared_not_crystal_magic_numbers() -> None:
    snapshot = _snapshot(party=_party(level=40))
    easier = project_crystal_goal_state(
        snapshot,
        config=CrystalGoalManagerConfig(required_team_level=40),
    )
    harder = project_crystal_goal_state(
        snapshot,
        config=CrystalGoalManagerConfig(required_team_level=80),
    )

    assert easier.situation.team_pressure == 0.0
    assert harder.situation.team_pressure == 0.5
