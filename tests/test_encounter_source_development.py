from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.encounter_source_development import (
    EncounterSourceDevelopmentError,
    EncounterSourceDevelopmentProvider,
    EncounterSourceDevelopmentSnapshot,
    encounter_source_development_qualification,
)
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport


def _snapshot(**changes: object) -> EncounterSourceDevelopmentSnapshot:
    values: dict[str, object] = {
        "source_ref": "encounter-source-001",
        "team_readiness": 0.40,
        "living_specimens": 12,
        "required_specimens_remaining": 100,
        "fainted_party_members": 0,
        "input_ready": True,
        "in_battle": False,
        "local_encounters_available": True,
    }
    values.update(changes)
    return EncounterSourceDevelopmentSnapshot(**values)  # type: ignore[arg-type]


def test_snapshot_projection_is_title_and_source_identity_free() -> None:
    snapshot = _snapshot()

    public = snapshot.public_dict()

    assert public["title_identity_included"] is False
    assert public["source_identity_included"] is False
    assert "encounter-source-001" not in str(public)
    with pytest.raises(EncounterSourceDevelopmentError, match="source identity"):
        _snapshot(source_ref="Route 1 / private")


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"input_ready": False}, GoalUnavailableReason.TEMPORARILY_BLOCKED),
        ({"in_battle": True}, GoalUnavailableReason.TEMPORARILY_BLOCKED),
        ({"local_encounters_available": False}, GoalUnavailableReason.MISSING_CAPABILITY),
        ({"team_readiness": 1.0}, GoalUnavailableReason.NO_LEGAL_TARGET),
        ({"fainted_party_members": 1}, GoalUnavailableReason.MISSING_RESOURCE),
    ),
)
def test_offer_masks_unexecutable_local_training(
    changes: dict[str, object],
    reason: GoalUnavailableReason,
) -> None:
    provider = EncounterSourceDevelopmentProvider(
        binding_ref="pokemon.core:development:encounter-source",
        observer=_snapshot,
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )

    offer = provider.offer(_snapshot(**changes))

    assert offer.binding is None
    assert offer.unavailable_reason is reason


def test_offer_is_action_free_and_verifies_real_progress() -> None:
    before = _snapshot()
    state = {"snapshot": before, "executions": 0}

    def execute() -> GoalExecutionReport:
        state["executions"] = int(state["executions"]) + 1
        state["snapshot"] = replace(before, team_readiness=0.45)
        return GoalExecutionReport(7, 120, {"bounded": True, "completed_battles": 1})

    provider = EncounterSourceDevelopmentProvider(
        binding_ref="pokemon.core:development:encounter-source",
        observer=lambda: state["snapshot"],  # type: ignore[return-value]
        executor=execute,
    )

    offer = provider.offer(before)

    assert state["executions"] == 0
    assert offer.unavailable_reason is None
    assert offer.binding is not None
    assert offer.binding.kind is GoalKind.DEVELOP_TEAM
    report = offer.binding.execute()
    verdict = offer.binding.verify(report)
    assert state["executions"] == 1
    assert verdict.status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    ("after", "reason"),
    (
        (
            _snapshot(source_ref="encounter-source-002", team_readiness=0.45),
            GoalFailureReason.WORLD_STATE_DIVERGED,
        ),
        (_snapshot(living_specimens=11, team_readiness=0.45), GoalFailureReason.RESOURCE_LOST),
        (
            _snapshot(required_specimens_remaining=101, team_readiness=0.45),
            GoalFailureReason.RESOURCE_LOST,
        ),
        (_snapshot(fainted_party_members=1, team_readiness=0.45), GoalFailureReason.RESOURCE_LOST),
        (_snapshot(team_readiness=0.40), GoalFailureReason.OUTCOME_NOT_VERIFIED),
        (
            _snapshot(team_readiness=0.45, local_encounters_available=False),
            GoalFailureReason.WORLD_STATE_DIVERGED,
        ),
        (_snapshot(team_readiness=0.45, input_ready=False), GoalFailureReason.OUTCOME_NOT_VERIFIED),
        (_snapshot(team_readiness=0.45, in_battle=True), GoalFailureReason.OUTCOME_NOT_VERIFIED),
    ),
)
def test_verifier_rejects_drift_loss_or_unsettled_progress(
    after: EncounterSourceDevelopmentSnapshot,
    reason: GoalFailureReason,
) -> None:
    provider = EncounterSourceDevelopmentProvider(
        binding_ref="pokemon.core:development:encounter-source",
        observer=lambda: after,
        executor=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
    )
    offer = provider.offer(_snapshot())
    assert offer.binding is not None

    verdict = offer.binding.verify(offer.binding.execute())

    assert verdict.status is GoalDecisionOutcome.FAILED
    assert verdict.failure_reason is reason


def test_qualification_explicitly_stops_before_gameplay_integration() -> None:
    qualification = encounter_source_development_qualification()

    assert qualification["goal_kind"] == "develop_team"
    assert qualification["route_or_coordinate_input"] is False
    assert qualification["teacher_choice"] is False
    assert qualification["execution_integrated"] is False
    assert qualification["gameplay_authorized"] is False
