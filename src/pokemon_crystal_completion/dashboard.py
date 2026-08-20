"""Crystal-to-dashboard projection kept outside the model-input boundary."""

from __future__ import annotations

from pokemon_crystal_completion.goal_state import CrystalGoalObservation
from pokemon_red_completion.goal_manager import (
    GOAL_KIND_NEEDS,
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
)
from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardGoalPressure,
    DashboardModelState,
    DashboardPartyMember,
    DashboardSnapshot,
)


def crystal_dashboard_snapshot(
    observation: CrystalGoalObservation,
    *,
    run_status: str,
    stage: str,
    message: str,
    frame_count: int,
    actions: int,
    emulation_speed: float,
    stage_progress: float,
    experiment: DashboardExperimentState,
    model: DashboardModelState,
    question: GoalManagerQuestion | None = None,
    selected_goal: GoalKind | None = None,
    location: str | None = None,
    events: tuple[str, ...] = (),
) -> DashboardSnapshot:
    """Render semantic evidence for a human without changing model features."""

    if not isinstance(observation, CrystalGoalObservation):
        raise TypeError("observation must be CrystalGoalObservation")
    if question is not None and question.situation != observation.situation:
        raise ValueError("dashboard question must use the observed Crystal situation")
    if selected_goal is not None and (
        question is None
        or not any(
            opportunity.kind is selected_goal
            and opportunity.availability is GoalAvailability.AVAILABLE
            for opportunity in question.opportunities
        )
    ):
        raise ValueError("dashboard selection must be available in the displayed question")

    available = (
        frozenset(
            opportunity.kind
            for opportunity in question.opportunities
            if opportunity.availability is GoalAvailability.AVAILABLE
        )
        if question is not None
        else frozenset()
    )
    situation = observation.situation
    goals = tuple(
        DashboardGoalPressure(
            goal=kind.value,
            pressure=max(situation.pressure(need) for need in GOAL_KIND_NEEDS[kind]),
            available=kind in available,
            selected=kind is selected_goal,
        )
        for kind in GoalKind
    )
    party = tuple(
        DashboardPartyMember(
            slot=member.slot,
            label=f"Species #{member.species_id:03d}",
            level=member.level,
            hp=member.hp,
            max_hp=member.max_hp,
            status=member.status.value,
        )
        for member in observation.snapshot.party.members
    )
    snapshot = observation.snapshot
    return DashboardSnapshot(
        game="Pokémon Crystal 1.1",
        run_status=run_status,
        stage=stage,
        message=message,
        frame_count=frame_count,
        actions=actions,
        emulation_speed=emulation_speed,
        stage_progress=stage_progress,
        location=location,
        registered_species=snapshot.registered_collection.completed,
        living_species=snapshot.living_collection.completed,
        level_cap_species=snapshot.level_collection.completed,
        collection_target=snapshot.registered_collection.target,
        capture_items=snapshot.capture_item_count,
        free_storage_slots=snapshot.free_storage_slots,
        party=party,
        goals=goals,
        model=model,
        experiment=experiment,
        events=events,
    )


__all__ = ["crystal_dashboard_snapshot"]
