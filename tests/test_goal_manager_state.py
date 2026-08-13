from __future__ import annotations

import pytest

from pokemon_red_completion.collection import CollectionReport
from pokemon_red_completion.goal_manager import GoalNeed
from pokemon_red_completion.goal_manager_state import (
    CompletionProgress,
    goal_state_evidence,
    party_readiness_satisfaction,
    party_safety_satisfaction,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)


def _member(
    slot: int,
    *,
    species_id: int,
    level: int,
    hp: int = 100,
    status: StatusCondition = StatusCondition.HEALTHY,
    pp: int = 10,
) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=species_id,
        level=level,
        hp=hp,
        max_hp=100,
        status=status,
        moves=(MoveObservation(move_id=1, current_pp=pp, max_pp=10),),
    )


def _report(*, target: int, owned: int, living_target: int, living: int) -> CollectionReport:
    return CollectionReport(
        target_count=target,
        living_target_count=living_target,
        pokedex_owned_count=owned,
        living_count=living,
        level_cap_count=0,
        missing_owned=tuple(f"missing-owned-{index}" for index in range(target - owned)),
        missing_living=tuple(f"missing-living-{index}" for index in range(living_target - living)),
        underleveled=(),
    )


def test_equal_semantic_progress_is_invariant_to_title_scale() -> None:
    red_party = PartyObservation(
        (
            _member(1, species_id=9, level=30),
            _member(2, species_id=25, level=30),
            _member(3, species_id=143, level=30),
        )
    )
    crystal_party = PartyObservation(
        (
            _member(1, species_id=160, level=30),
            _member(2, species_id=181, level=30),
            _member(3, species_id=248, level=30),
        )
    )

    red = goal_state_evidence(
        story=CompletionProgress(4, 8),
        collection=_report(target=150, owned=75, living_target=120, living=60),
        party=red_party,
        required_party_size=3,
        required_team_level=40,
        evolution=CompletionProgress(10, 20),
        available_resources=10,
        desired_resources=20,
        free_storage_slots=5,
        desired_storage_headroom=10,
        control_stable=True,
        world_knowledge=CompletionProgress(50, 100),
    ).situation()
    crystal = goal_state_evidence(
        story=CompletionProgress(8, 16),
        collection=_report(target=250, owned=125, living_target=200, living=100),
        party=crystal_party,
        required_party_size=3,
        required_team_level=40,
        evolution=CompletionProgress(20, 40),
        available_resources=25,
        desired_resources=50,
        free_storage_slots=10,
        desired_storage_headroom=20,
        control_stable=True,
        world_knowledge=CompletionProgress(125, 250),
    ).situation()

    assert red == crystal


def test_living_collection_prevents_registration_from_claiming_completion() -> None:
    evidence = goal_state_evidence(
        story=CompletionProgress(8, 8),
        collection=_report(target=10, owned=10, living_target=8, living=4),
        party=PartyObservation((_member(1, species_id=9, level=50),)),
        required_party_size=1,
        required_team_level=50,
        evolution=CompletionProgress(1, 1),
        available_resources=1,
        desired_resources=1,
        free_storage_slots=1,
        desired_storage_headroom=1,
        control_stable=True,
        world_knowledge=CompletionProgress(1, 1),
    )

    assert evidence.situation().pressure(GoalNeed.COLLECTION_PROGRESS) == 0.5


def test_party_readiness_counts_missing_members_and_relative_levels() -> None:
    party = PartyObservation(
        (
            _member(1, species_id=9, level=40),
            _member(2, species_id=25, level=20),
        )
    )

    assert party_readiness_satisfaction(
        party,
        required_size=4,
        required_level=40,
    ) == pytest.approx((1.0 + 0.5 + 0.0 + 0.0) / 4)


def test_party_safety_combines_hp_status_and_usable_actions() -> None:
    party = PartyObservation(
        (
            _member(1, species_id=9, level=40, hp=100),
            _member(
                2,
                species_id=25,
                level=40,
                hp=50,
                status=StatusCondition.PARALYSIS,
                pp=0,
            ),
        )
    )

    assert party_safety_satisfaction(party) == 0.5
    assert party_safety_satisfaction(PartyObservation()) == 1.0
