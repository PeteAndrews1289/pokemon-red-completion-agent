"""Title-neutral team-development capability at the current encounter source.

The goal manager must be able to choose a real non-acquisition action after a
capture without receiving a map route or title identity.  This module defines
that reusable boundary.  Game adapters supply a source-local executor and a
fresh semantic observer; the verifier accepts progress only when team
readiness improves and living-collection state does not regress.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)

_SAFE_SOURCE_REF = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")


class EncounterSourceDevelopmentError(ValueError):
    """Raised when an encounter-development binding weakens its contract."""


@dataclass(frozen=True, slots=True)
class EncounterSourceDevelopmentSnapshot:
    """Game-neutral facts required to offer and verify local development."""

    source_ref: str
    team_readiness: float
    living_specimens: int
    required_specimens_remaining: int
    fainted_party_members: int
    input_ready: bool
    in_battle: bool
    local_encounters_available: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_ref, str) or _SAFE_SOURCE_REF.fullmatch(
            self.source_ref
        ) is None:
            raise EncounterSourceDevelopmentError("encounter source identity is invalid")
        if (
            isinstance(self.team_readiness, bool)
            or not isinstance(self.team_readiness, (int, float))
            or not 0.0 <= float(self.team_readiness) <= 1.0
        ):
            raise EncounterSourceDevelopmentError(
                "team readiness must be between zero and one"
            )
        object.__setattr__(self, "team_readiness", float(self.team_readiness))
        for name in (
            "living_specimens",
            "required_specimens_remaining",
            "fainted_party_members",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise EncounterSourceDevelopmentError(
                    f"{name} must be a non-negative integer"
                )
        for name in ("input_ready", "in_battle", "local_encounters_available"):
            if type(getattr(self, name)) is not bool:  # noqa: E721
                raise EncounterSourceDevelopmentError(f"{name} must be a boolean")

    def public_dict(self) -> dict[str, object]:
        """Project only portable evidence; source identity remains adapter-private."""

        return {
            "schema": "pokemon.core.encounter-source-development-snapshot.v1",
            "team_readiness": self.team_readiness,
            "living_specimens": self.living_specimens,
            "required_specimens_remaining": self.required_specimens_remaining,
            "fainted_party_members": self.fainted_party_members,
            "input_ready": self.input_ready,
            "in_battle": self.in_battle,
            "local_encounters_available": self.local_encounters_available,
            "title_identity_included": False,
            "source_identity_included": False,
        }


@dataclass(frozen=True, slots=True)
class EncounterSourceDevelopmentOffer:
    """Either one executable portable binding or one portable block reason."""

    binding: ExecutableGoalBinding | None
    unavailable_reason: GoalUnavailableReason | None

    def __post_init__(self) -> None:
        if self.binding is None:
            if not isinstance(self.unavailable_reason, GoalUnavailableReason):
                raise EncounterSourceDevelopmentError(
                    "blocked development offer requires a portable reason"
                )
        elif self.unavailable_reason is not None:
            raise EncounterSourceDevelopmentError(
                "executable development offer cannot include a block reason"
            )


EncounterDevelopmentExecutor = Callable[[], GoalExecutionReport]
EncounterDevelopmentObserver = Callable[[], EncounterSourceDevelopmentSnapshot]


@dataclass(frozen=True, slots=True)
class EncounterSourceDevelopmentProvider:
    """Offer one bounded local training quantum without encoding a route."""

    binding_ref: str
    observer: EncounterDevelopmentObserver
    executor: EncounterDevelopmentExecutor
    estimated_effort: float = 0.30
    estimated_risk: float = 0.15

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise EncounterSourceDevelopmentError("development binding identity is absent")
        if not callable(self.observer) or not callable(self.executor):
            raise EncounterSourceDevelopmentError(
                "development provider requires observer and executor callables"
            )
        # ExecutableGoalBinding performs the canonical normalized-metric checks.
        _ = ExecutableGoalBinding(
            binding_ref=self.binding_ref,
            kind=GoalKind.DEVELOP_TEAM,
            estimated_effort=self.estimated_effort,
            estimated_risk=self.estimated_risk,
            execute=self.executor,
            verify=lambda _report: GoalVerification.succeeded(),
        )

    def offer(
        self,
        before: EncounterSourceDevelopmentSnapshot,
    ) -> EncounterSourceDevelopmentOffer:
        """Build a binding from one action-free snapshot and a fresh verifier."""

        if not isinstance(before, EncounterSourceDevelopmentSnapshot):
            raise TypeError("before must be an EncounterSourceDevelopmentSnapshot")
        reason = _unavailable_reason(before)
        if reason is not None:
            return EncounterSourceDevelopmentOffer(None, reason)

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.observer()
            if (
                after.source_ref != before.source_ref
                or not after.local_encounters_available
            ):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if (
                after.living_specimens < before.living_specimens
                or after.required_specimens_remaining
                > before.required_specimens_remaining
                or after.fainted_party_members > before.fainted_party_members
            ):
                return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            if (
                report.actions_executed <= 0
                or report.frames_executed <= 0
                or not after.input_ready
                or after.in_battle
                or after.team_readiness <= before.team_readiness
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return EncounterSourceDevelopmentOffer(
            ExecutableGoalBinding(
                binding_ref=self.binding_ref,
                kind=GoalKind.DEVELOP_TEAM,
                estimated_effort=self.estimated_effort,
                estimated_risk=self.estimated_risk,
                execute=self.executor,
                verify=verify,
            ),
            None,
        )


def encounter_source_development_qualification() -> dict[str, object]:
    """Return the public engineering boundary for later title adapters."""

    return {
        "schema": "pokemon.core.encounter-source-development-qualification.v1",
        "goal_kind": GoalKind.DEVELOP_TEAM.value,
        "title_identity_in_policy_input": False,
        "source_identity_in_policy_input": False,
        "route_or_coordinate_input": False,
        "teacher_choice": False,
        "executor_scope": "one_source_local_training_quantum",
        "independent_verification": [
            "team_readiness_increased",
            "living_specimen_count_nonregressed",
            "required_specimens_remaining_nonincreased",
            "fainted_party_members_nonincreased",
            "same_encounter_source",
            "settled_input_ready_state",
        ],
        "execution_integrated": False,
        "gameplay_authorized": False,
        "claim_boundary": (
            "ROM-free capability and adapter contract only; not an executed skill, learned "
            "replan, Red completion, living-Pokedex completion, or cross-title transfer"
        ),
    }


def _unavailable_reason(
    snapshot: EncounterSourceDevelopmentSnapshot,
) -> GoalUnavailableReason | None:
    if snapshot.in_battle or not snapshot.input_ready:
        return GoalUnavailableReason.TEMPORARILY_BLOCKED
    if not snapshot.local_encounters_available:
        return GoalUnavailableReason.MISSING_CAPABILITY
    if snapshot.team_readiness >= 1.0:
        return GoalUnavailableReason.NO_LEGAL_TARGET
    if snapshot.fainted_party_members:
        return GoalUnavailableReason.MISSING_RESOURCE
    return None


__all__ = (
    "EncounterSourceDevelopmentError",
    "EncounterSourceDevelopmentOffer",
    "EncounterSourceDevelopmentProvider",
    "EncounterSourceDevelopmentSnapshot",
    "encounter_source_development_qualification",
)
