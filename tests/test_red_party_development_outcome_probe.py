from __future__ import annotations

import json

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.red_party_development_outcome_probe import (
    RedPartyDevelopmentProbeError,
    build_bounded_evolution_venue_question,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_venue import TrainingVenue


def _member(slot: int, species_id: int, level: int) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=species_id,
        level=level,
        hp=80,
        max_hp=80,
        moves=(MoveObservation(1, 25, 35),),
        experience=level**3,
    )


def _party() -> PartyObservation:
    return PartyObservation(
        members=(
            _member(1, 9, 48),
            _member(2, 64, 20),
            _member(3, 59, 22),
            _member(4, 132, 30),
            _member(5, 104, 25),
            _member(6, 43, 30),
        )
    )


def _venue(name: str, minimum: int, maximum: int) -> TrainingVenue:
    return TrainingVenue(
        band=GrindingArea(name, minimum, maximum, measured_samples=50),
        map_id=minimum,
        walk_to_grass=lambda *_args: 1,
        heal_and_return=lambda *_args: None,
        is_in_center=lambda raw: isinstance(raw, RawGameState) and False,
        move_slot=lambda _raw: 1,
    )


def test_question_digest_orders_two_identity_free_venue_candidates() -> None:
    route = _venue("lower-band-private-name", 9, 15)
    cave = _venue("higher-band-private-name", 15, 21)
    policy = BalancedTeamPolicy(
        minimum_level=55,
        maximum_level_spread=40,
        required_size=6,
        minimum_direct_level_advantage=5,
    )

    natural = build_bounded_evolution_venue_question(
        _party(),
        policy,
        (route, cave),
        source_species_id=59,
        final_species_id=118,
        initial_state_sha256="0" * 64,
    )
    reversed_question = build_bounded_evolution_venue_question(
        _party(),
        policy,
        (route, cave),
        source_species_id=59,
        final_species_id=118,
        initial_state_sha256="f" * 64,
    )

    assert natural.venue_bindings == (route, cave)
    assert reversed_question.venue_bindings == (cave, route)
    assert [candidate.candidate_index for candidate in natural.candidate_set.candidates] == [0, 1]
    assert tuple(
        candidate.features for candidate in reversed(reversed_question.candidate_set.candidates)
    ) == tuple(candidate.features for candidate in natural.candidate_set.candidates)
    public = json.dumps(reversed_question.public_catalog(), sort_keys=True)
    assert "lower-band-private-name" not in public
    assert "higher-band-private-name" not in public
    assert "species" not in public
    assert "slot" not in public
    assert "map" not in public
    assert reversed_question.public_catalog()["teacher_choice_targets"] == 0
    assert reversed_question.public_catalog()["controller_action_labels"] == 0


def test_question_rejects_a_missing_or_single_venue_target() -> None:
    route = _venue("only-band", 9, 15)
    impossible = _venue("too-hard", 40, 45)
    policy = BalancedTeamPolicy(minimum_level=55, required_size=6)

    with pytest.raises(RedPartyDevelopmentProbeError, match="both frozen venues"):
        build_bounded_evolution_venue_question(
            _party(),
            policy,
            (route, impossible),
            source_species_id=59,
            final_species_id=118,
            initial_state_sha256="0" * 64,
        )
    with pytest.raises(RedPartyDevelopmentProbeError, match="source species is absent"):
        build_bounded_evolution_venue_question(
            _party(),
            policy,
            (route, impossible),
            source_species_id=25,
            final_species_id=26,
            initial_state_sha256="0" * 64,
        )
