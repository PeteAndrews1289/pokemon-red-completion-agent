from __future__ import annotations

import json

import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingCandidateDecision,
    TrainingCandidateRankError,
    project_trainee_candidates,
    project_venue_candidates,
)

POLICY = BalancedTeamPolicy(
    minimum_level=55,
    maximum_level_spread=10,
    required_size=3,
)
CAVE = GrindingArea("diglett_cave", 15, 21, measured_samples=100)
MANSION = GrindingArea("pokemon_mansion", 28, 34, measured_samples=100)


def member(slot: int, species: int, level: int, *, hp: int = 100) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=species,
        level=level,
        hp=hp,
        max_hp=100,
        moves=(MoveObservation(species + 10, 20, 25),),
    )


def test_trainee_projection_labels_the_unique_weakest_without_identity() -> None:
    party = PartyObservation(
        members=(member(1, 9, 45), member(2, 3, 30), member(3, 26, 40))
    )

    projected = project_trainee_candidates(party, POLICY, (CAVE, MANSION))

    assert projected is not None
    selected, selected_index, observation = projected
    assert selected.species_id == 3
    assert selected_index == 1
    assert len(observation.candidates) == 3
    public = json.dumps(observation.public_dict(), sort_keys=True)
    assert "diglett_cave" not in public
    assert "pokemon_mansion" not in public
    assert "species" not in public
    assert "move" not in public
    assert "slot" not in public
    public_features = observation.candidates[0].public_dict()["features"]
    assert isinstance(public_features, dict)
    assert tuple(public_features) == TRAINING_CANDIDATE_FEATURE_NAMES


def test_trainee_projection_excludes_an_unobservable_nonlead_tie() -> None:
    party = PartyObservation(
        members=(member(1, 9, 45), member(2, 3, 30), member(3, 26, 30))
    )

    assert project_trainee_candidates(party, POLICY, (CAVE, MANSION)) is None


def test_venue_projection_is_equivariant_to_candidate_order() -> None:
    party = PartyObservation(
        members=(member(1, 9, 35), member(2, 3, 50), member(3, 26, 50))
    )
    trainee = party.members[0]

    forward = project_venue_candidates(party, POLICY, trainee, (CAVE, MANSION))
    reverse = project_venue_candidates(party, POLICY, trainee, (MANSION, CAVE))

    assert forward is not None and reverse is not None
    forward_area, forward_index, forward_observation = forward
    reverse_area, reverse_index, reverse_observation = reverse
    assert forward_area == reverse_area == MANSION
    assert forward_index == 1
    assert reverse_index == 0
    assert tuple(
        candidate.features for candidate in reversed(forward_observation.candidates)
    ) == tuple(candidate.features for candidate in reverse_observation.candidates)


def test_title_identities_do_not_change_candidate_features() -> None:
    red = PartyObservation(
        members=(member(1, 9, 35), member(2, 3, 50), member(3, 26, 50))
    )
    crystal = PartyObservation(
        members=(member(1, 160, 35), member(2, 154, 50), member(3, 181, 50))
    )
    red_areas = (
        GrindingArea("diglett_cave", 15, 21, measured_samples=100),
        GrindingArea("pokemon_mansion", 28, 34, measured_samples=100),
    )
    crystal_areas = (
        GrindingArea("union_cave", 15, 21, measured_samples=100),
        GrindingArea("mount_silver", 28, 34, measured_samples=100),
    )

    red_projection = project_venue_candidates(red, POLICY, red.members[0], red_areas)
    crystal_projection = project_venue_candidates(
        crystal, POLICY, crystal.members[0], crystal_areas
    )

    assert red_projection is not None and crystal_projection is not None
    assert red_projection[1:] == crystal_projection[1:]


def test_decision_rejects_a_candidate_outside_the_choice_set() -> None:
    party = PartyObservation(
        members=(member(1, 9, 35), member(2, 3, 50), member(3, 26, 50))
    )
    projected = project_venue_candidates(party, POLICY, party.members[0], (CAVE, MANSION))
    assert projected is not None
    _, _, observation = projected

    with pytest.raises(TrainingCandidateRankError, match="selected candidate"):
        TrainingCandidateDecision(0, 2, observation, "synthetic")
