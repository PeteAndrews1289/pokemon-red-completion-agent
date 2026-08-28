"""Project a validated Red setup menu into the title-neutral learner contract.

Setup validation already obtains one coherent origin observation and one genuine
``ExecutableGoalBinding`` for every candidate fork.  This module turns only
those prospective facts into a ``LivingDexOptionMenu``.  It never executes a
provider, uses a teacher choice, reads an outcome, or encodes a map/species/root
identity in a learner feature.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.living_dex_policy_codec import (
    living_dex_private_menu_dict,
    restore_living_dex_private_menu,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_manager import RedGoalObservation

RED_LIVING_DEX_SETUP_POLICY_PROJECTION_SCHEMA = (
    "pokemon.red.private-living-dex-setup-policy-projection.v2"
)

_OPTION_BY_GOAL = {
    GoalKind.ADVANCE_STORY: LivingDexOptionKind.UNLOCK_ACCESS,
    GoalKind.ACQUIRE_SPECIES: LivingDexOptionKind.ACQUIRE,
    GoalKind.DEVELOP_TEAM: LivingDexOptionKind.DEVELOP,
    GoalKind.EVOLVE_SPECIES: LivingDexOptionKind.EVOLVE,
    GoalKind.RESUPPLY: LivingDexOptionKind.RESUPPLY,
    GoalKind.MANAGE_STORAGE: LivingDexOptionKind.MANAGE_STORAGE,
    GoalKind.EXPLORE: LivingDexOptionKind.EXPLORE,
}
_COMPLETION_PRIOR = {
    LivingDexOptionKind.ACQUIRE: 1.0,
    LivingDexOptionKind.EVOLVE: 1.0,
    LivingDexOptionKind.TRADE: 1.0,
}
_DEPENDENCY_PRIOR = {
    LivingDexOptionKind.UNLOCK_ACCESS: 1.0,
    LivingDexOptionKind.EXPLORE: 0.5,
    LivingDexOptionKind.DEVELOP: 0.25,
    LivingDexOptionKind.MANAGE_STORAGE: 0.25,
    LivingDexOptionKind.RESUPPLY: 0.25,
}


class RedLivingDexSetupPolicyError(ValueError):
    """Validated Red setup evidence cannot produce one honest policy menu."""


def red_living_dex_setup_candidate_features(
    kind: LivingDexOptionKind,
    *,
    route_controller_actions: int,
    maximum_controller_actions: int,
    estimated_effort: float,
    estimated_risk: float,
    storage_unit: float,
) -> LivingDexOptionFeatures:
    """Return the exact first-title feature projection for one setup offer."""

    if not isinstance(kind, LivingDexOptionKind):
        raise RedLivingDexSetupPolicyError("Red setup feature kind differs")
    if (
        type(route_controller_actions) is not int  # noqa: E721
        or type(maximum_controller_actions) is not int  # noqa: E721
        or maximum_controller_actions <= 0
        or not 0 <= route_controller_actions <= maximum_controller_actions
    ):
        raise RedLivingDexSetupPolicyError("Red setup feature action budget differs")
    return LivingDexOptionFeatures(
        kind=kind,
        completion_gain=_COMPLETION_PRIOR.get(kind, 0.0),
        dependency_unlock_gain=_DEPENDENCY_PRIOR.get(kind, 0.0),
        travel_effort=route_controller_actions / maximum_controller_actions,
        execution_effort=estimated_effort,
        resource_cost=0.0,
        storage_cost=(storage_unit if kind is LivingDexOptionKind.ACQUIRE else 0.0),
        party_risk=estimated_risk,
        irreversibility_risk=(1.0 if kind is LivingDexOptionKind.TRADE else 0.0),
        uncertainty=0.0,
    )


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupPolicyProjection:
    """Exact private provenance beside one identity-free learner menu."""

    menu: LivingDexOptionMenu
    origin_policy_observation: dict[str, object]
    route_controller_actions: tuple[int, ...]
    maximum_controller_actions: int
    maximum_emulator_frames: int

    def __post_init__(self) -> None:
        if not isinstance(self.menu, LivingDexOptionMenu):
            raise TypeError("Red setup policy projection needs a living-Dex menu")
        self.menu.__post_init__()
        if not isinstance(self.origin_policy_observation, dict):
            raise RedLivingDexSetupPolicyError("Red setup origin policy evidence differs")
        canonical_sha256(self.origin_policy_observation)
        if (
            not isinstance(self.route_controller_actions, tuple)
            or len(self.route_controller_actions) != len(self.menu.candidates)
            or any(type(value) is not int or value < 0 for value in self.route_controller_actions)  # noqa: E721
        ):
            raise RedLivingDexSetupPolicyError("Red setup route-action census differs")
        if (
            type(self.maximum_controller_actions) is not int  # noqa: E721
            or self.maximum_controller_actions <= 0
            or any(
                value > self.maximum_controller_actions for value in self.route_controller_actions
            )
        ):
            raise RedLivingDexSetupPolicyError("Red setup policy action budget differs")
        if type(self.maximum_emulator_frames) is not int or self.maximum_emulator_frames <= 0:  # noqa: E721
            raise RedLivingDexSetupPolicyError("Red setup policy frame budget differs")

    @property
    def projection_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "maximum_controller_actions": self.maximum_controller_actions,
            "maximum_emulator_frames": self.maximum_emulator_frames,
            "menu": living_dex_private_menu_dict(self.menu),
            "origin_policy_observation": self.origin_policy_observation,
            "route_controller_actions": list(self.route_controller_actions),
            "schema": RED_LIVING_DEX_SETUP_POLICY_PROJECTION_SCHEMA,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_count": len(self.menu.candidates),
            "identity_fields_public": 0,
            "menu": self.menu.policy_dict(),
            "menu_sha256": self.menu.policy_sha256,
            "private_path_fields": 0,
            "provider_executions": 0,
            "schema": RED_LIVING_DEX_SETUP_POLICY_PROJECTION_SCHEMA,
            "teacher_queries": 0,
        }


def project_red_living_dex_setup_policy(
    observation: RedGoalObservation,
    bindings: Sequence[ExecutableGoalBinding],
    *,
    option_kinds: Sequence[LivingDexOptionKind],
    route_controller_actions: Sequence[int],
    maximum_controller_actions: int,
    maximum_emulator_frames: int,
) -> RedLivingDexSetupPolicyProjection:
    """Build the canonical policy at the validated origin without acting."""

    if not isinstance(observation, RedGoalObservation):
        raise TypeError("Red setup policy needs a RedGoalObservation")
    typed_bindings = tuple(bindings)
    typed_kinds = tuple(option_kinds)
    route_actions = tuple(route_controller_actions)
    if (
        len(typed_bindings) < 2
        or len(typed_bindings) != len(typed_kinds)
        or len(route_actions) != len(typed_bindings)
        or any(not isinstance(item, ExecutableGoalBinding) for item in typed_bindings)
        or any(not isinstance(item, LivingDexOptionKind) for item in typed_kinds)
    ):
        raise RedLivingDexSetupPolicyError("Red setup policy candidate census differs")
    expected_kinds = tuple(_OPTION_BY_GOAL.get(binding.kind) for binding in typed_bindings)
    if expected_kinds != typed_kinds or any(item is None for item in expected_kinds):
        raise RedLivingDexSetupPolicyError("Red setup policy goal mapping differs")
    if len({binding.binding_ref for binding in typed_bindings}) != len(typed_bindings):
        raise RedLivingDexSetupPolicyError("Red setup policy bindings are duplicated")
    if type(maximum_controller_actions) is not int or maximum_controller_actions <= 0:  # noqa: E721
        raise RedLivingDexSetupPolicyError("Red setup policy action budget differs")
    if type(maximum_emulator_frames) is not int or maximum_emulator_frames <= 0:  # noqa: E721
        raise RedLivingDexSetupPolicyError("Red setup policy frame budget differs")
    if any(
        type(value) is not int or not 0 <= value <= maximum_controller_actions  # noqa: E721
        for value in route_actions
    ):
        raise RedLivingDexSetupPolicyError("Red setup policy route actions differ")

    situation = observation.situation
    context = living_dex_option_context_from_goal_situation(situation)
    storage_unit = min(1.0, 1.0 / max(1, observation.free_storage_slots))
    candidates = tuple(
        LivingDexOptionCandidate(
            binding.binding_ref,
            red_living_dex_setup_candidate_features(
                kind,
                route_controller_actions=route_actions[index],
                maximum_controller_actions=maximum_controller_actions,
                estimated_effort=binding.estimated_effort,
                estimated_risk=binding.estimated_risk,
                storage_unit=storage_unit,
            ),
            LivingDexOptionAvailability.AVAILABLE,
        )
        for index, (kind, binding) in enumerate(zip(typed_kinds, typed_bindings, strict=True))
    )
    try:
        menu = LivingDexOptionMenu(context, candidates)
    except (TypeError, ValueError) as error:
        raise RedLivingDexSetupPolicyError(str(error)) from None
    if len({menu.candidate_vector(index) for index in menu.available_indices}) != len(
        menu.available_indices
    ):
        raise RedLivingDexSetupPolicyError("Red setup policy candidates are not distinguishable")
    return RedLivingDexSetupPolicyProjection(
        menu,
        observation.public_dict(),
        route_actions,
        maximum_controller_actions,
        maximum_emulator_frames,
    )


def restore_red_living_dex_setup_policy_projection(
    document: Mapping[str, object],
) -> RedLivingDexSetupPolicyProjection:
    """Restore one exact private projection after artifact authentication."""

    expected = {
        "maximum_controller_actions",
        "maximum_emulator_frames",
        "menu",
        "origin_policy_observation",
        "route_controller_actions",
        "schema",
    }
    if not isinstance(document, Mapping) or set(document) != expected:
        raise RedLivingDexSetupPolicyError("stored Red setup policy fields differ")
    if document["schema"] != RED_LIVING_DEX_SETUP_POLICY_PROJECTION_SCHEMA:
        raise RedLivingDexSetupPolicyError("stored Red setup policy schema differs")
    menu_document = document["menu"]
    origin_document = document["origin_policy_observation"]
    route_values = document["route_controller_actions"]
    maximum = document["maximum_controller_actions"]
    maximum_frames = document["maximum_emulator_frames"]
    if not isinstance(menu_document, Mapping):
        raise RedLivingDexSetupPolicyError("stored Red setup policy menu differs")
    if not isinstance(origin_document, dict):
        raise RedLivingDexSetupPolicyError("stored Red setup policy origin differs")
    if not isinstance(route_values, list) or any(
        type(item) is not int
        for item in route_values  # noqa: E721
    ):
        raise RedLivingDexSetupPolicyError("stored Red setup route census differs")
    if type(maximum) is not int:  # noqa: E721
        raise RedLivingDexSetupPolicyError("stored Red setup action budget differs")
    if type(maximum_frames) is not int:  # noqa: E721
        raise RedLivingDexSetupPolicyError("stored Red setup frame budget differs")
    try:
        projection = RedLivingDexSetupPolicyProjection(
            restore_living_dex_private_menu(menu_document),
            origin_document,
            tuple(route_values),
            maximum,
            maximum_frames,
        )
    except (TypeError, ValueError) as error:
        raise RedLivingDexSetupPolicyError(str(error)) from None
    if projection.private_dict() != dict(document):
        raise RedLivingDexSetupPolicyError("stored Red setup policy does not replay")
    return projection


__all__ = [
    "RED_LIVING_DEX_SETUP_POLICY_PROJECTION_SCHEMA",
    "RedLivingDexSetupPolicyError",
    "RedLivingDexSetupPolicyProjection",
    "project_red_living_dex_setup_policy",
    "red_living_dex_setup_candidate_features",
    "restore_red_living_dex_setup_policy_projection",
]
