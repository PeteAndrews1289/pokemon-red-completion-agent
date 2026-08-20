from __future__ import annotations

import numpy as np
import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_control import (
    TRAINING_CONTROL_FEATURE_NAMES,
    TrainingControlAction,
    TrainingControlDecision,
    TrainingControlError,
    TrainingControlPhase,
    project_training_control_observation,
)


def _member(
    slot: int,
    *,
    level: int,
    hp: int = 80,
    status: StatusCondition = StatusCondition.HEALTHY,
) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=1000 + slot,
        level=level,
        hp=hp,
        max_hp=100,
        status=status,
        moves=(MoveObservation(2000 + slot, 12, 20),),
    )


def test_training_projection_is_normalized_and_identity_free() -> None:
    party = PartyObservation(tuple(_member(slot, level=35 + slot) for slot in range(1, 7)))
    policy = BalancedTeamPolicy(
        minimum_level=55,
        maximum_level_spread=5,
        required_size=6,
        max_battles=2000,
        max_steps=100_000,
        max_healing_trips=1000,
    )
    progress = TeamTrainingProgress(battles_completed=50, steps_taken=500, healing_trips=3)
    venue = GrindingArea("portable_venue", 28, 34, measured_samples=100)

    observation = project_training_control_observation(
        party,
        policy,
        progress,
        phase=TrainingControlPhase.OVERWORLD,
        trainee=party.lead,
        attack_pp=12,
        attack_pp_reserve=3,
        safety_reserve=party.members[1],
        safety_reserve_attack_pp=9,
        safety_reserve_attack_pp_reserve=2,
        venue=venue,
        consecutive_flees=2,
        max_consecutive_flees=10,
    )

    assert observation.candidate_actions == (
        TrainingControlAction.SEEK,
        TrainingControlAction.HEAL,
        TrainingControlAction.STOP,
    )
    assert observation.vector().shape == (len(TRAINING_CONTROL_FEATURE_NAMES),)
    assert np.all(np.isfinite(observation.vector()))
    assert np.all(observation.vector() >= -1.0)
    assert np.all(observation.vector() <= 1.0)
    public = observation.public_dict()
    rendered = repr(public)
    assert "portable_venue" not in rendered
    assert "1001" not in rendered
    assert "2001" not in rendered
    features = public["features"]
    assert isinstance(features, dict)
    assert features["reserve.hp_ratio"] == pytest.approx(0.8)
    assert features["reserve.status_healthy"] == 1.0
    assert features["reserve.attack_pp_margin"] == pytest.approx(7 / 64)


def test_battle_projection_exposes_relative_matchup_without_species_identity() -> None:
    trainee = _member(1, level=30, hp=44, status=StatusCondition.POISON)
    party = PartyObservation((trainee, _member(2, level=50)))
    policy = BalancedTeamPolicy(minimum_level=55, required_size=2)

    observation = project_training_control_observation(
        party,
        policy,
        TeamTrainingProgress(),
        phase=TrainingControlPhase.BATTLE,
        trainee=trainee,
        attack_pp=2,
        attack_pp_reserve=2,
        enemy_level=34,
    )

    features = dict(zip(TRAINING_CONTROL_FEATURE_NAMES, observation.features, strict=True))
    assert observation.candidate_actions == (
        TrainingControlAction.FIGHT,
        TrainingControlAction.FLEE,
    )
    assert features["enemy.observed"] == 1.0
    assert features["enemy.level_delta"] == pytest.approx(-0.04)
    assert features["trainee.status_healthy"] == 0.0
    assert features["trainee.attack_pp_margin"] == 0.0


def test_battle_projection_removes_fight_when_runtime_affordance_is_unavailable() -> None:
    trainee = _member(1, level=30)
    party = PartyObservation((trainee,))

    observation = project_training_control_observation(
        party,
        BalancedTeamPolicy(minimum_level=55, required_size=1),
        TeamTrainingProgress(),
        phase=TrainingControlPhase.BATTLE,
        trainee=trainee,
        attack_pp=0,
        attack_pp_reserve=0,
        enemy_level=30,
        fight_allowed=False,
    )

    assert observation.candidate_actions == (TrainingControlAction.FLEE,)


def test_projection_accepts_a_canonical_runtime_candidate_subset() -> None:
    trainee = _member(1, level=30)
    observation = project_training_control_observation(
        PartyObservation((trainee,)),
        BalancedTeamPolicy(minimum_level=55, required_size=1),
        TeamTrainingProgress(),
        phase=TrainingControlPhase.OVERWORLD,
        trainee=trainee,
        candidate_actions=(TrainingControlAction.SEEK,),
    )

    assert observation.candidate_actions == (TrainingControlAction.SEEK,)


def test_projection_rejects_fight_at_an_unsafe_runtime_boundary() -> None:
    trainee = _member(1, level=30)
    with pytest.raises(TrainingControlError, match="fight cannot be a candidate"):
        project_training_control_observation(
            PartyObservation((trainee,)),
            BalancedTeamPolicy(minimum_level=55, required_size=1),
            TeamTrainingProgress(),
            phase=TrainingControlPhase.BATTLE,
            trainee=trainee,
            enemy_level=30,
            fight_allowed=False,
            candidate_actions=(TrainingControlAction.FIGHT, TrainingControlAction.FLEE),
        )


def test_training_decision_rejects_an_action_illegal_for_its_phase() -> None:
    party = PartyObservation((_member(1, level=30),))
    observation = project_training_control_observation(
        party,
        BalancedTeamPolicy(minimum_level=55, required_size=1),
        TeamTrainingProgress(),
        phase=TrainingControlPhase.BATTLE,
        trainee=party.lead,
        enemy_level=30,
    )

    with pytest.raises(TrainingControlError, match="illegal"):
        TrainingControlDecision(0, TrainingControlAction.HEAL, observation, "heal in battle")


def test_public_teacher_decision_keeps_reason_and_schema() -> None:
    party = PartyObservation((_member(1, level=55),))
    observation = project_training_control_observation(
        party,
        BalancedTeamPolicy(minimum_level=55, required_size=1),
        TeamTrainingProgress(),
        phase=TrainingControlPhase.OVERWORLD,
        trainee=party.lead,
    )
    decision = TrainingControlDecision(
        7,
        TrainingControlAction.STOP,
        observation,
        "party meets the contract",
    )

    assert decision.public_dict()["schema"] == "pokemon-training-control-decision-v1"
    assert decision.public_dict()["action"] == "stop"
    assert decision.public_dict()["decision_index"] == 7
