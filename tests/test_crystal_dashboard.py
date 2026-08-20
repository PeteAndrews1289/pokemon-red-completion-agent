from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_crystal_completion.dashboard import crystal_dashboard_snapshot
from pokemon_crystal_completion.goal_state import (
    CrystalCampaignSnapshot,
    project_crystal_goal_state,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, PartyObservation
from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardModelState,
)


def _observation():  # type: ignore[no-untyped-def]
    party = PartyObservation(
        (
            PartyMemberObservation(
                slot=1,
                species_id=155,
                level=12,
                hp=30,
                max_hp=40,
                moves=(MoveObservation(33, 20, 35),),
            ),
        )
    )
    return project_crystal_goal_state(
        CrystalCampaignSnapshot(
            story=CompletionProgress(2, 16),
            registered_collection=CompletionProgress(3, 250),
            living_collection=CompletionProgress(2, 250),
            level_collection=CompletionProgress(0, 250),
            evolution=CompletionProgress(0, 100),
            world_knowledge=CompletionProgress(4, 250),
            party=party,
            game_started=True,
            input_ready=True,
            capture_item_count=5,
            recovery_item_count=2,
            free_storage_slots=278,
            immediate_capture_slots=5,
        )
    )


def _question(observation):  # type: ignore[no-untyped-def]
    return GoalManagerQuestion(
        situation=observation.situation,
        opportunities=(
            GoalOpportunity(
                binding_ref="private:story-binding",
                kind=GoalKind.ADVANCE_STORY,
                availability=GoalAvailability.AVAILABLE,
                estimated_effort=0.4,
                estimated_risk=0.2,
            ),
            GoalOpportunity(
                binding_ref="private:capture-binding",
                kind=GoalKind.ACQUIRE_SPECIES,
                availability=GoalAvailability.UNKNOWN,
                unavailable_reason=GoalUnavailableReason.WORLD_STATE_UNKNOWN,
            ),
        ),
    )


def test_crystal_dashboard_projects_human_details_without_binding_identity() -> None:
    observation = _observation()
    snapshot = crystal_dashboard_snapshot(
        observation,
        run_status="running",
        stage="Zero-shot probe",
        message="Ranking the frozen goal menu.",
        frame_count=100,
        actions=4,
        emulation_speed=2.0,
        stage_progress=0.25,
        experiment=DashboardExperimentState(phase="zero_shot"),
        model=DashboardModelState(
            mode="zero_shot",
            choice="advance_story",
            confidence=0.9,
            decisions=1,
        ),
        question=_question(observation),
        selected_goal=GoalKind.ADVANCE_STORY,
        location="New Bark Town",
    )
    document = snapshot.public_dict()

    assert document["party"][0]["label"] == "Species #155"  # type: ignore[index]
    assert document["collection"] == {  # type: ignore[index]
        "registered": 3,
        "living": 2,
        "level_cap": 0,
        "target": 250,
    }
    goals = {row["goal"]: row for row in document["goals"]}  # type: ignore[union-attr]
    assert goals["advance_story"]["available"] is True
    assert goals["advance_story"]["selected"] is True
    assert goals["acquire_species"]["available"] is False
    assert "private:story-binding" not in str(document)


def test_crystal_dashboard_rejects_unrelated_question_or_unavailable_selection() -> None:
    observation = _observation()
    common = {
        "run_status": "running",
        "stage": "test",
        "message": "test",
        "frame_count": 0,
        "actions": 0,
        "emulation_speed": 0.0,
        "stage_progress": 0.0,
        "experiment": DashboardExperimentState(),
        "model": DashboardModelState(),
    }
    wrong_question = replace(
        _question(observation),
        situation=GoalSituation(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    )
    with pytest.raises(ValueError, match="observed Crystal situation"):
        crystal_dashboard_snapshot(observation, question=wrong_question, **common)
    with pytest.raises(ValueError, match="available"):
        crystal_dashboard_snapshot(
            observation,
            question=_question(observation),
            selected_goal=GoalKind.ACQUIRE_SPECIES,
            **common,
        )
