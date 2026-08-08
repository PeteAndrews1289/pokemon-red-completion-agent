"""Falsification tests for the game-neutrality claim.

``party.py``, ``pokedex.py`` and ``team_training.py`` all *claim* to be reusable
across mainline titles.  Until a second generation exercised them, that claim
was untested — and an untested claim about transferability is exactly the kind
of thing this project has learned not to trust.

These tests express Generation II quantities through the same contracts, with no
change to any of them.  They are cheap, and they fail loudly the moment someone
bakes a Red-specific assumption into the neutral layer.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.pokedex import (
    ExclusionReason,
    LivingDex,
    PokedexObservation,
    declare_target,
    plan_next_run,
    summarize,
)
from pokemon_red_completion.red_pokedex import RED_POKEDEX_TARGET
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    LevelParityContract,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_control import (
    TrainingControlAction,
    TrainingControlPhase,
    project_training_control_observation,
)

#: Generation II's species count. The point is that this is a *parameter*.
CRYSTAL_TOTAL_SPECIES = 251
#: Celebi was event-only, exactly as Mew was in Generation I.
CRYSTAL_EXCLUSIONS = {251: ExclusionReason.EVENT_DISTRIBUTION}


def crystal_target():
    return declare_target(CRYSTAL_TOTAL_SPECIES, CRYSTAL_EXCLUSIONS)


def test_the_dex_contract_expresses_a_second_generation_unchanged() -> None:
    """251 species and a different event exclusion, with no code change."""

    target = crystal_target()
    assert target.total_species == 251
    assert target.obtainable_count == 250
    assert target.excluded_for(ExclusionReason.EVENT_DISTRIBUTION) == frozenset({251})
    # The Generation I target is unaffected by the Generation II one existing.
    assert RED_POKEDEX_TARGET.total_species == 151


def test_a_living_dex_accumulates_across_generations() -> None:
    """The whole point of the living dex: one collection, many cartridges."""

    crystal = crystal_target()
    living = LivingDex().with_run(
        PokedexObservation(
            seen=RED_POKEDEX_TARGET.obtainable,
            owned=RED_POKEDEX_TARGET.obtainable,
        )
    )
    # A complete Red run closes its own target entirely...
    assert living.remaining(RED_POKEDEX_TARGET) == frozenset()
    # ...and still leaves most of Generation II open.
    remaining = living.remaining(crystal)
    assert len(remaining) == 125
    # Everything Red could reach counts toward Crystal too; ordinals are shared.
    assert not remaining & RED_POKEDEX_TARGET.obtainable


def test_coverage_planning_prefers_the_generation_that_adds_more() -> None:
    crystal = crystal_target()
    living = LivingDex()
    plan = plan_next_run(living, {"red": RED_POKEDEX_TARGET, "crystal": crystal})
    assert plan
    # Greedy coverage: the larger generation first, then whatever it leaves.
    first_name, first_gain = plan[0]
    assert first_name == "crystal"
    assert len(first_gain) == 250
    # Red adds nothing once Crystal's obtainable set is registered.
    assert all(name != "red" for name, _ in plan[1:])


def test_the_party_contract_accepts_a_second_generation_party() -> None:
    """Species identifiers outside Generation I's range must simply work."""

    party = PartyObservation(
        members=(
            PartyMemberObservation(
                slot=1,
                species_id=155,  # Cyndaquil: beyond Generation I entirely
                level=30,
                hp=60,
                max_hp=60,
                moves=(MoveObservation(52, 25, 25),),
            ),
        )
    )
    assert party.size == 1
    assert party.minimum_level == 30
    assert party.has_species(155)


def test_level_parity_transfers_to_a_different_league() -> None:
    """The reason parity replaced an absolute floor: 50 means nothing here."""

    contract = LevelParityContract(max_levels_behind=10)
    # Generation II's champion sits lower than Generation I's.
    assert contract.required_level(50) == 40
    assert contract.required_level(65) == 55
    # The same contract, unchanged, answers both.
    assert contract.required_level(50) != contract.required_level(65)


def test_progress_reports_against_whichever_target_it_is_given() -> None:
    crystal = crystal_target()
    observed = PokedexObservation(seen={1, 155, 251}, owned={1, 155})
    progress = summarize(crystal, observed)
    assert progress.registered == frozenset({1, 155})
    assert progress.completion == pytest.approx(2 / 250)
    # Celebi is excluded, so seeing it never inflates the denominator.
    assert 251 not in crystal.obtainable


def test_training_control_projection_is_invariant_to_title_identity() -> None:
    """Species, move, and venue identity must not become model shortcuts."""

    red_party = PartyObservation(
        members=(
            PartyMemberObservation(
                slot=1,
                species_id=9,
                level=35,
                hp=70,
                max_hp=100,
                moves=(MoveObservation(55, 12, 25),),
            ),
            PartyMemberObservation(
                slot=2,
                species_id=3,
                level=50,
                hp=90,
                max_hp=100,
                moves=(MoveObservation(75, 9, 15),),
            ),
        )
    )
    crystal_party = PartyObservation(
        members=(
            PartyMemberObservation(
                slot=1,
                species_id=160,
                level=35,
                hp=70,
                max_hp=100,
                moves=(MoveObservation(57, 12, 25),),
            ),
            PartyMemberObservation(
                slot=2,
                species_id=154,
                level=50,
                hp=90,
                max_hp=100,
                moves=(MoveObservation(22, 9, 15),),
            ),
        )
    )
    policy = BalancedTeamPolicy(
        minimum_level=55,
        maximum_level_spread=5,
        required_size=2,
        max_battles=2_000,
        max_steps=100_000,
        max_healing_trips=1_000,
    )
    progress = TeamTrainingProgress(
        battles_completed=500,
        steps_taken=10_000,
        healing_trips=40,
    )

    def project(party: PartyObservation, venue_name: str):
        return project_training_control_observation(
            party,
            policy,
            progress,
            phase=TrainingControlPhase.OVERWORLD,
            trainee=party.members[0],
            attack_pp=12,
            attack_pp_reserve=3,
            safety_reserve=party.members[1],
            safety_reserve_attack_pp=9,
            safety_reserve_attack_pp_reserve=2,
            venue=GrindingArea(venue_name, 30, 34, measured_samples=100),
            candidate_actions=(TrainingControlAction.SEEK, TrainingControlAction.HEAL),
        )

    assert project(red_party, "pokemon_mansion") == project(
        crystal_party,
        "mount_silver",
    )
