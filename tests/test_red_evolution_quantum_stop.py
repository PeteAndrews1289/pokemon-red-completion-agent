"""Finite evolution work is a failed attempt, never an evolution success."""

from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import ordinary_player_setback


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"quantum_limit_reached": False},
        {"quantum_limit_reached": 1},
        {"completed_training_quanta": None},
        {"completed_training_quanta": True},
        {"completed_training_quanta": 63},
        {"completed_training_quanta": 65},
        {"maximum_training_quanta": None},
        {"maximum_training_quanta": 64.0},
        {"maximum_training_quanta": 0, "completed_training_quanta": 0},
        {"maximum_training_quanta": 513, "completed_training_quanta": 513},
        {"completed_training_battles": 0},
        {"completed_training_battles": True},
    ],
)
def test_quantum_stop_requires_exact_positive_configured_limit(patch):
    facts = dict(
        actions=0,
        completed_actions=0,
        frames=0,
        cash=100,
        owned_species=["source"],
        completed_objectives=["story"],
        specimen_counts={"source": 1},
        battle_state=0,
        input_ready=True,
        buttons_released=True,
    )
    evidence = dict(
        schema="pokemon.red.native-evolution-partial.v1",
        bounded=True,
        source_species_ref="pokemon:national:017",
        target_species_ref="pokemon:national:018",
        evolution_partial=True,
        retained_active_roster_restored=True,
        settlement_reserve_reached=False,
        wall_limit_reached=False,
        quantum_limit_reached=True,
        completed_training_quanta=64,
        maximum_training_quanta=64,
        completed_training_battles=256,
    )
    evidence.update(patch)
    verdict = GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    assert ordinary_player_setback(
        SimpleNamespace(kind=GoalKind.EVOLVE_SPECIES),
        AutonomousSnapshot(b"before", facts, True),
        AutonomousSnapshot(b"after", dict(facts, actions=2, completed_actions=2, frames=20), True),
        GoalExecutionReport(2, 20, evidence),
        verdict,
        None,
    ) is (not patch)
    assert verdict.status.value == "failed"
