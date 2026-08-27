"""Same-root construction and fork validation for Red living-Pokedex lessons.

The retired setup-source design expected a destination observation and provider
offer to exist *before* a route had been executed.  Historical captures cannot
truthfully provide those counterfactual endpoint observations.  This module
freezes only facts that can be known prospectively -- an authenticated root,
an optional construction route, one origin, candidate transport routes, and
finite provider profiles -- then validates every candidate from an exact fork
of the newly captured origin.

Setup and transport movement are deliberately outside the learner boundary.
The validator never draws a behavior choice, executes a provider, asks a
teacher, emits a target, observes an outcome, or fits a model.  It derives the
physical location from the freshly observed origin and derives transformation
families from actual profile-bound executable offers; neither value may be
supplied by a catalog author.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pokemon_red_completion.captured_progress import (
    CapturedProgressEnvelope,
    parse_captured_progress,
)
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureAttestation,
    LivingDexCapturePartition,
    LivingDexProspectiveCapturePlan,
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import (
    RedGoalContextProviderOffer,
    RedGoalContextRuntime,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
)
from pokemon_red_completion.red_goal_manager import (
    RedStoryGoalBindingProvider,
)
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedEncounterSourceDevelopmentGoalProvider,
    RedMartResupplyGoalProvider,
    RedObservedGoalSkillProvider,
    RedProgressGoalProvider,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_setup_campaign import (
    RedLivingDexSetupOptionBinding,
    RedLivingDexSetupSlotBinding,
    RedLivingDexSetupTransportKind,
)
from pokemon_red_completion.red_living_dex_setup_source import (
    RED_LIVING_DEX_SETUP_PROVIDER_OFFER_WITNESS_SCHEMA,
    red_living_dex_setup_executable_binding_sha256,
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupExecutionIdentity,
    RedLivingDexSetupProtectedEffectCheckpoint,
    RedLivingDexTransformationFamily,
    red_living_dex_binding_matches_family,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedRoutedSemanticBoundary,
    RedSemanticTransportRoute,
)
from pokemon_red_completion.route_executor import RouteExecutionReport
from pokemon_red_completion.route_plan import RoutePlan

RED_LIVING_DEX_SETUP_RECIPE_ROUTE_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-route.v1"
RED_LIVING_DEX_SETUP_PROVIDER_RECIPE_SCHEMA = (
    "pokemon.red.private-living-dex-setup-provider-recipe.v2"
)
RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA = "pokemon.red.private-living-dex-setup-slot-recipe.v2"
RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-plan.v2"
RED_LIVING_DEX_SETUP_ORIGIN_SCHEMA = "pokemon.red.private-living-dex-constructed-origin.v2"
RED_LIVING_DEX_SETUP_FORK_PROOF_SCHEMA = "pokemon.red.private-living-dex-setup-fork-proof.v2"
RED_LIVING_DEX_SETUP_VALIDATED_CAPTURE_SCHEMA = (
    "pokemon.red.private-living-dex-validated-setup-capture.v2"
)
RED_LIVING_DEX_SETUP_MENU_SCHEMA = "pokemon.red.private-living-dex-same-root-menu.v1"
RED_LIVING_DEX_SETUP_OBSERVER_BINDING_SCHEMA = (
    "pokemon.red.private-living-dex-same-root-observer-binding.v1"
)
RED_LIVING_DEX_SETUP_RECIPE_COUNT = 15
RED_LIVING_DEX_SETUP_OFFER_COUNT = 45
RED_LIVING_DEX_SETUP_MINIMUM_SEMANTIC_FAMILIES = 33
RED_LIVING_DEX_SETUP_PHYSICAL_ORIGIN_COUNT = 10

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

_GOAL_KIND_BY_OPTION = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}

_PROVIDER_TYPE_BY_MECHANIC = {
    RedGoalMechanic.MIDGAME_STORY: RedStoryGoalBindingProvider,
    RedGoalMechanic.WILD_CORRIDOR_CAPTURE: RedAreaSurveyGoalProvider,
    RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT: (RedEncounterSourceDevelopmentGoalProvider),
    RedGoalMechanic.BALANCED_TEAM: RedProgressGoalProvider,
    RedGoalMechanic.DIGLETT_EVOLUTION: RedObservedGoalSkillProvider,
    RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT: RedObservedGoalSkillProvider,
    RedGoalMechanic.TARGETED_LEVEL_EVOLUTION: RedObservedGoalSkillProvider,
    RedGoalMechanic.MART_RESUPPLY: RedMartResupplyGoalProvider,
    RedGoalMechanic.BOX_SWITCH: RedBoxSwitchGoalProvider,
    RedGoalMechanic.WILD_CORRIDOR_DISCOVERY: (RedEncounterDiscoveryGoalProvider),
}

_CAPABILITY_BY_KIND = {item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES}


class RedLivingDexSetupRecipeError(RuntimeError):
    """A prospective recipe or same-root validation crossed its contract."""


def _contract_id(value: type[object]) -> str:
    return f"{value.__module__}.{value.__qualname__}"


def _route_plan_execution_document(plan: RoutePlan) -> dict[str, object]:
    """Bind exactly the flattened acknowledgement contract the executor uses."""

    if not isinstance(plan, RoutePlan):
        raise TypeError("Red setup recipe route needs a RoutePlan")
    plan.__post_init__()
    return {
        "cost": plan.cost,
        "maps": list(plan.macro_path.maps),
        "schema": "pokemon.red.private-route-execution-contract.v1",
        "start_at": list(plan.start_at),
        "start_mode": plan.start_mode,
        "steps": [
            {
                "action": step.action,
                "action_kind": step.action_kind.value,
                "expected_at": list(step.expected_at),
                "expected_map": step.expected_map,
                "expected_mode": step.expected_mode,
                "kind": step.kind,
                "source_at": list(step.source_at),
                "source_map": step.source_map,
                "source_mode": step.source_mode,
                "transient_at": (None if step.transient_at is None else list(step.transient_at)),
            }
            for step in plan.steps
        ],
        "terminal_at": list(plan.terminal_at),
        "terminal_map": plan.terminal_map,
        "terminal_mode": plan.terminal_mode,
    }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRouteRecipe:
    """One frozen semantic-router candidate, never a teacher direction list."""

    plan: RoutePlan
    planner_binding_sha256: str
    route_source: str = field(default="semantic-router-v1", init=False)
    raw_controller_sequence_steps: int = field(default=0, init=False)
    teacher_route: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RoutePlan):
            raise TypeError("Red setup recipe route needs a RoutePlan")
        self.plan.__post_init__()
        if not self.plan.steps:
            raise RedLivingDexSetupRecipeError("Red setup recipe route must cross a real boundary")
        _require_sha256(self.planner_binding_sha256, "recipe planner binding")
        if (
            self.route_source != "semantic-router-v1"
            or self.raw_controller_sequence_steps != 0
            or self.teacher_route
        ):
            raise RedLivingDexSetupRecipeError("Red setup recipe route provenance differs")

    @property
    def origin_boundary(self) -> RedRoutedSemanticBoundary:
        return RedRoutedSemanticBoundary(
            self.plan.macro_path.maps[0],
            self.plan.start_at,
            self.plan.start_mode,
        )

    @property
    def terminal_boundary(self) -> RedRoutedSemanticBoundary:
        return RedRoutedSemanticBoundary.from_plan(self.plan)

    @property
    def route_plan_sha256(self) -> str:
        return canonical_sha256(_route_plan_execution_document(self.plan))

    @property
    def recipe_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "origin_boundary_sha256": self.origin_boundary.sha256,
            "planner_binding_sha256": self.planner_binding_sha256,
            "raw_controller_sequence_steps": self.raw_controller_sequence_steps,
            "route_plan_sha256": self.route_plan_sha256,
            "route_source": self.route_source,
            "schema": RED_LIVING_DEX_SETUP_RECIPE_ROUTE_SCHEMA,
            "teacher_route": self.teacher_route,
            "terminal_boundary_sha256": self.terminal_boundary.sha256,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupProviderRecipe:
    """One finite provider profile to offer after a candidate transport."""

    option_kind: LivingDexOptionKind
    provider_type: type[object]
    profile: RedGoalContextProfile
    family: RedLivingDexTransformationFamily
    route: RedLivingDexSetupRouteRecipe | None

    def __post_init__(self) -> None:
        if not isinstance(self.option_kind, LivingDexOptionKind):
            raise RedLivingDexSetupRecipeError("provider recipe option kind differs")
        if not isinstance(self.provider_type, type):
            raise TypeError("provider recipe needs a provider type")
        if not isinstance(self.profile, RedGoalContextProfile):
            raise TypeError("provider recipe needs a Red context profile")
        self.profile.__post_init__()
        if not isinstance(self.family, RedLivingDexTransformationFamily):
            raise TypeError("provider recipe needs a typed transformation family")
        self.family.__post_init__()
        goal_kind = _GOAL_KIND_BY_OPTION.get(self.option_kind)
        specs = tuple(item for item in self.profile.providers if item.kind is goal_kind)
        if goal_kind is None or len(specs) != 1:
            raise RedLivingDexSetupRecipeError(
                "provider recipe lacks one profile mechanic for its kind"
            )
        spec = specs[0]
        if (
            self.family.option_kind is not self.option_kind
            or self.family.goal_kind is not goal_kind
            or self.family.mechanic is not spec.mechanic
        ):
            raise RedLivingDexSetupRecipeError(
                "provider recipe family differs from its real profile mechanic"
            )
        expected_type = _PROVIDER_TYPE_BY_MECHANIC.get(spec.mechanic)
        capability = _CAPABILITY_BY_KIND.get(self.option_kind)
        if (
            expected_type is not self.provider_type
            or capability is None
            or self.provider_type not in capability.executor_types
        ):
            raise RedLivingDexSetupRecipeError(
                "provider recipe type differs from its real profile mechanic"
            )
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT and spec.parameters.get(
            "map_id"
        ) != int(MapId.POKEMON_MANSION_1F):
            raise RedLivingDexSetupRecipeError(
                "encounter-source development recipe lacks its measured venue"
            )
        if self.route is not None:
            if not isinstance(self.route, RedLivingDexSetupRouteRecipe):
                raise TypeError("provider recipe route differs")
            self.route.__post_init__()

    @property
    def goal_kind(self) -> GoalKind:
        return _GOAL_KIND_BY_OPTION[self.option_kind]

    @property
    def provider_spec(self) -> object:
        return next(item for item in self.profile.providers if item.kind is self.goal_kind)

    @property
    def provider_contract_id(self) -> str:
        return _contract_id(self.provider_type)

    @property
    def expected_family_sha256(self) -> str:
        return self.family.family_sha256

    @property
    def recipe_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        spec = next(item for item in self.profile.providers if item.kind is self.goal_kind)
        return {
            "goal_kind": self.goal_kind.value,
            "option_kind": self.option_kind.value,
            "expected_family_sha256": self.expected_family_sha256,
            "family": self.family.private_dict(),
            "profile_sha256": self.profile.profile_sha256,
            "provider_configuration_sha256": spec.configuration_sha256,
            "provider_contract_id": self.provider_contract_id,
            "route_recipe_sha256": (None if self.route is None else self.route.recipe_sha256),
            "schema": RED_LIVING_DEX_SETUP_PROVIDER_RECIPE_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupSlotRecipe:
    """One root-to-origin construction plus all same-origin candidate forks."""

    slot_sha256: str
    partition: LivingDexCapturePartition
    available_option_kinds: tuple[LivingDexOptionKind, ...]
    root_consumption_sha256: str
    root_state_sha256: str
    root_envelope_sha256: str
    base_boundary: RedRoutedSemanticBoundary
    origin_boundary: RedRoutedSemanticBoundary
    construction_route: RedLivingDexSetupRouteRecipe | None
    providers: tuple[RedLivingDexSetupProviderRecipe, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.slot_sha256, "recipe slot"),
            (self.root_consumption_sha256, "recipe root consumption"),
            (self.root_state_sha256, "recipe root state"),
            (self.root_envelope_sha256, "recipe root envelope"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.partition, LivingDexCapturePartition):
            raise RedLivingDexSetupRecipeError("recipe partition differs")
        _require_option_kinds(self.available_option_kinds)
        for boundary, subject in (
            (self.base_boundary, "recipe base boundary"),
            (self.origin_boundary, "recipe origin boundary"),
        ):
            if not isinstance(boundary, RedRoutedSemanticBoundary):
                raise TypeError(subject)
            boundary.__post_init__()
        if self.construction_route is None:
            if self.base_boundary != self.origin_boundary:
                raise RedLivingDexSetupRecipeError("route-free recipe does not start at its origin")
        else:
            if not isinstance(self.construction_route, RedLivingDexSetupRouteRecipe):
                raise TypeError("recipe construction route differs")
            self.construction_route.__post_init__()
            if (
                self.construction_route.origin_boundary != self.base_boundary
                or self.construction_route.terminal_boundary != self.origin_boundary
            ):
                raise RedLivingDexSetupRecipeError(
                    "recipe construction route crosses another boundary"
                )
        if (
            not isinstance(self.providers, tuple)
            or len(self.providers) != len(self.available_option_kinds)
            or any(not isinstance(item, RedLivingDexSetupProviderRecipe) for item in self.providers)
        ):
            raise RedLivingDexSetupRecipeError("recipe needs one provider for every option")
        for provider in self.providers:
            provider.__post_init__()
        if tuple(item.option_kind for item in self.providers) != self.available_option_kinds:
            raise RedLivingDexSetupRecipeError("recipe provider order differs")
        for provider in self.providers:
            if (
                provider.route is not None
                and provider.route.origin_boundary != self.origin_boundary
            ):
                raise RedLivingDexSetupRecipeError(
                    "recipe candidate route does not fork from the shared origin"
                )
            actual_terminal = (
                self.origin_boundary if provider.route is None else provider.route.terminal_boundary
            )
            if not _profile_terminal_matches(
                provider.profile,
                provider.goal_kind,
                actual_terminal,
            ):
                raise RedLivingDexSetupRecipeError(
                    "recipe candidate terminal differs from its provider profile"
                )
        _require_unique(
            (item.recipe_sha256 for item in self.providers),
            "recipe providers",
        )

    @property
    def recipe_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    @property
    def location_sha256(self) -> str:
        """Derive the physical scope from the planned origin map, never a label."""

        return _location_sha256(self.origin_boundary)

    def private_dict(self) -> dict[str, object]:
        return {
            "available_option_kinds": [item.value for item in self.available_option_kinds],
            "base_boundary_sha256": self.base_boundary.sha256,
            "construction_route_sha256": (
                None if self.construction_route is None else self.construction_route.recipe_sha256
            ),
            "origin_boundary_sha256": self.origin_boundary.sha256,
            "partition": self.partition.value,
            "providers": [item.private_dict() for item in self.providers],
            "root_consumption_sha256": self.root_consumption_sha256,
            "root_envelope_sha256": self.root_envelope_sha256,
            "root_state_sha256": self.root_state_sha256,
            "schema": RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA,
            "slot_sha256": self.slot_sha256,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRecipePlan:
    """The complete purpose-built Red schedule frozen before controller input."""

    prospective_plan: LivingDexProspectiveCapturePlan
    recipes: tuple[RedLivingDexSetupSlotRecipe, ...]
    execution_identity: RedLivingDexSetupExecutionIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.prospective_plan, LivingDexProspectiveCapturePlan):
            raise TypeError("recipe plan needs the prospective plan")
        if not isinstance(self.execution_identity, RedLivingDexSetupExecutionIdentity):
            raise TypeError("recipe plan needs an execution identity")
        self.execution_identity.__post_init__()
        self.prospective_plan.__post_init__()
        canonical = build_red_living_dex_prospective_capture_plan()
        if self.prospective_plan.plan_sha256 != canonical.plan_sha256:
            raise RedLivingDexSetupRecipeError("recipe plan prospective schedule differs")
        if (
            not isinstance(self.recipes, tuple)
            or len(self.recipes) != len(self.prospective_plan.slots)
            or any(not isinstance(item, RedLivingDexSetupSlotRecipe) for item in self.recipes)
        ):
            raise RedLivingDexSetupRecipeError("recipe plan must cover every prospective slot")
        for slot, recipe in zip(
            self.prospective_plan.slots,
            self.recipes,
            strict=True,
        ):
            recipe.__post_init__()
            _require_recipe_join(slot, recipe)
        for values, subject in (
            ((item.recipe_sha256 for item in self.recipes), "slot recipes"),
            ((item.root_consumption_sha256 for item in self.recipes), "recipe roots"),
            ((item.root_state_sha256 for item in self.recipes), "recipe root states"),
            ((item.root_envelope_sha256 for item in self.recipes), "recipe root envelopes"),
        ):
            _require_unique(values, subject)
        _require_location_scope_join(self.prospective_plan.slots, self.recipes)
        _require_family_scope_join(self.prospective_plan.slots, self.recipes)
        offer_count = sum(len(item.providers) for item in self.recipes)
        semantic_family_count = len(
            {
                provider.expected_family_sha256
                for recipe in self.recipes
                for provider in recipe.providers
            }
        )
        physical_origin_count = len({item.location_sha256 for item in self.recipes})
        if (
            len(self.recipes) != RED_LIVING_DEX_SETUP_RECIPE_COUNT
            or offer_count != RED_LIVING_DEX_SETUP_OFFER_COUNT
            or semantic_family_count < RED_LIVING_DEX_SETUP_MINIMUM_SEMANTIC_FAMILIES
            or physical_origin_count != RED_LIVING_DEX_SETUP_PHYSICAL_ORIGIN_COUNT
        ):
            raise RedLivingDexSetupRecipeError(
                "recipe plan does not meet the frozen causal-capacity contract"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "claim_before_controller_input": True,
            "execution_identity": self.execution_identity.private_dict(),
            "execution_identity_sha256": self.execution_identity.identity_sha256,
            "learner_effects": 0,
            "prospective_plan_sha256": self.prospective_plan.plan_sha256,
            "recipes": [item.private_dict() for item in self.recipes],
            "retry_after_controller_input": False,
            "same_origin_fork_required": True,
            "schema": RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA,
        }

    def public_dict(self) -> dict[str, object]:
        partitions = Counter(item.partition.value for item in self.recipes)
        routed = sum(
            provider.route is not None for item in self.recipes for provider in item.providers
        )
        semantic_family_count = len(
            {
                provider.expected_family_sha256
                for recipe in self.recipes
                for provider in recipe.providers
            }
        )
        return {
            "claim_before_controller_input": True,
            "development_slots": partitions[LivingDexCapturePartition.DEVELOPMENT.value],
            "learner_effects": 0,
            "option_count": sum(len(item.providers) for item in self.recipes),
            "physical_origin_count": len({item.location_sha256 for item in self.recipes}),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "execution_identity_bound": True,
            "retry_after_controller_input": False,
            "routed_option_count": routed,
            "same_origin_fork_required": True,
            "schema": RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA,
            "semantic_family_count": semantic_family_count,
            "semantic_family_minimum": RED_LIVING_DEX_SETUP_MINIMUM_SEMANTIC_FAMILIES,
            "slot_count": len(self.recipes),
            "train_slots": partitions[LivingDexCapturePartition.TRAIN.value],
        }


def build_red_living_dex_setup_recipe_plan(
    recipes: tuple[RedLivingDexSetupSlotRecipe, ...],
    *,
    execution_identity: RedLivingDexSetupExecutionIdentity,
    prospective_plan: LivingDexProspectiveCapturePlan | None = None,
) -> RedLivingDexSetupRecipePlan:
    """Freeze a purpose-built plan without inventing endpoint observations."""

    return RedLivingDexSetupRecipePlan(
        prospective_plan=(
            build_red_living_dex_prospective_capture_plan()
            if prospective_plan is None
            else prospective_plan
        ),
        recipes=recipes,
        execution_identity=execution_identity,
    )


@dataclass(frozen=True, slots=True)
class RedLivingDexAuthenticatedSetupRoot:
    """Exact pre-validated private root supplied independently of the runtime."""

    root_consumption_sha256: str
    state_bytes: bytes = field(repr=False)
    envelope_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _require_sha256(self.root_consumption_sha256, "authenticated setup root")
        if not isinstance(self.state_bytes, bytes) or not self.state_bytes:
            raise RedLivingDexSetupRecipeError("authenticated setup root state is absent")
        if not isinstance(self.envelope_bytes, bytes) or not self.envelope_bytes:
            raise RedLivingDexSetupRecipeError("authenticated setup root envelope is absent")
        envelope = parse_captured_progress(
            self.envelope_bytes,
            state_bytes=self.state_bytes,
        )
        canonical = (
            json.dumps(envelope.to_dict(), ensure_ascii=True, sort_keys=True).encode("ascii")
            + b"\n"
        )
        if canonical != self.envelope_bytes:
            raise RedLivingDexSetupRecipeError("authenticated setup root envelope is not canonical")

    @property
    def state_sha256(self) -> str:
        return hashlib.sha256(self.state_bytes).hexdigest()

    @property
    def envelope_sha256(self) -> str:
        return hashlib.sha256(self.envelope_bytes).hexdigest()

    @property
    def physical_root_sha256(self) -> str:
        """Identity of the actual bytes, independent of a catalog label."""

        return canonical_sha256(
            {
                "envelope_sha256": self.envelope_sha256,
                "schema": "pokemon.red.private-physical-setup-root.v1",
                "state_sha256": self.state_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class RedLivingDexConstructedOrigin:
    """Exact repeatable origin bytes produced from one authenticated root."""

    state_bytes: bytes = field(repr=False)
    envelope_bytes: bytes = field(repr=False)
    consumed_root_state_bytes: bytes = field(repr=False)
    consumed_root_envelope_bytes: bytes = field(repr=False)
    fresh: FreshRedGoalObservation
    root_consumption_sha256: str
    consumed_root_state_sha256: str
    consumed_root_envelope_sha256: str
    construction_runtime_sha256: str
    construction_route_recipe_sha256: str | None
    construction_route_plan_sha256: str | None
    construction_route_planner_binding_sha256: str | None
    construction_route_terminal_boundary_sha256: str | None
    construction_route_report_sha256: str | None
    construction_route_controller_actions: int
    construction_route_emulator_frames: int

    def __post_init__(self) -> None:
        if not isinstance(self.state_bytes, bytes) or not self.state_bytes:
            raise RedLivingDexSetupRecipeError("constructed origin state is absent")
        if not isinstance(self.envelope_bytes, bytes) or not self.envelope_bytes:
            raise RedLivingDexSetupRecipeError("constructed origin envelope is absent")
        if (
            not isinstance(self.consumed_root_state_bytes, bytes)
            or not self.consumed_root_state_bytes
        ):
            raise RedLivingDexSetupRecipeError("constructed origin source state is absent")
        if (
            not isinstance(self.consumed_root_envelope_bytes, bytes)
            or not self.consumed_root_envelope_bytes
        ):
            raise RedLivingDexSetupRecipeError("constructed origin source envelope is absent")
        for value, subject in (
            (self.root_consumption_sha256, "constructed origin root"),
            (self.consumed_root_state_sha256, "constructed origin source state"),
            (self.consumed_root_envelope_sha256, "constructed origin source envelope"),
            (self.construction_runtime_sha256, "construction runtime"),
        ):
            _require_sha256(value, subject)
        route_values = (
            self.construction_route_recipe_sha256,
            self.construction_route_plan_sha256,
            self.construction_route_planner_binding_sha256,
            self.construction_route_terminal_boundary_sha256,
            self.construction_route_report_sha256,
        )
        if any(item is None for item in route_values) != all(
            item is None for item in route_values
        ):
            raise RedLivingDexSetupRecipeError("construction route proof is partially bound")
        for route_value in route_values:
            if route_value is not None:
                _require_sha256(route_value, "construction route proof")
        for counter_value, subject in (
            (self.construction_route_controller_actions, "construction route actions"),
            (self.construction_route_emulator_frames, "construction route frames"),
        ):
            if type(counter_value) is not int or counter_value < 0:  # noqa: E721
                raise RedLivingDexSetupRecipeError(f"{subject} differ")
        if self.construction_route_recipe_sha256 is None:
            if (
                self.construction_route_controller_actions
                or self.construction_route_emulator_frames
            ):
                raise RedLivingDexSetupRecipeError("route-free construction reports effects")
        elif (
            self.construction_route_controller_actions <= 0
            or self.construction_route_emulator_frames <= 0
        ):
            raise RedLivingDexSetupRecipeError("routed construction lacks measured effects")
        if (
            hashlib.sha256(self.consumed_root_state_bytes).hexdigest()
            != self.consumed_root_state_sha256
        ):
            raise RedLivingDexSetupRecipeError("constructed origin source state digest differs")
        if (
            hashlib.sha256(self.consumed_root_envelope_bytes).hexdigest()
            != self.consumed_root_envelope_sha256
        ):
            raise RedLivingDexSetupRecipeError("constructed origin source envelope digest differs")
        root_envelope = parse_captured_progress(
            self.consumed_root_envelope_bytes,
            state_bytes=self.consumed_root_state_bytes,
        )
        root_canonical = (
            json.dumps(
                root_envelope.to_dict(),
                ensure_ascii=True,
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        if root_canonical != self.consumed_root_envelope_bytes:
            raise RedLivingDexSetupRecipeError(
                "constructed origin source envelope is not canonical"
            )
        _require_fresh(self.fresh)
        envelope = parse_captured_progress(
            self.envelope_bytes,
            state_bytes=self.state_bytes,
        )
        canonical = (
            json.dumps(
                envelope.to_dict(),
                ensure_ascii=True,
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        if canonical != self.envelope_bytes:
            raise RedLivingDexSetupRecipeError("constructed origin envelope is not canonical")

    @property
    def state_sha256(self) -> str:
        return hashlib.sha256(self.state_bytes).hexdigest()

    @property
    def envelope_sha256(self) -> str:
        return hashlib.sha256(self.envelope_bytes).hexdigest()

    def private_dict(self) -> dict[str, object]:
        return {
            "construction_route_controller_actions": (
                self.construction_route_controller_actions
            ),
            "construction_route_emulator_frames": self.construction_route_emulator_frames,
            "construction_route_plan_sha256": self.construction_route_plan_sha256,
            "construction_route_planner_binding_sha256": (
                self.construction_route_planner_binding_sha256
            ),
            "construction_route_recipe_sha256": self.construction_route_recipe_sha256,
            "construction_route_report_sha256": self.construction_route_report_sha256,
            "construction_route_terminal_boundary_sha256": (
                self.construction_route_terminal_boundary_sha256
            ),
            "construction_runtime_sha256": self.construction_runtime_sha256,
            "consumed_root_envelope_sha256": self.consumed_root_envelope_sha256,
            "consumed_root_state_sha256": self.consumed_root_state_sha256,
            "envelope_sha256": self.envelope_sha256,
            "fresh_observation_sha256": self.fresh.observation_sha256,
            "root_consumption_sha256": self.root_consumption_sha256,
            "schema": RED_LIVING_DEX_SETUP_ORIGIN_SCHEMA,
            "state_sha256": self.state_sha256,
        }


@dataclass(frozen=True, slots=True)
class _ProvisionalFork:
    provider_recipe: RedLivingDexSetupProviderRecipe
    executable_binding: ExecutableGoalBinding
    fork_runtime_sha256: str
    fresh_sha256: str
    executable_sha256: str
    offer_sha256: str
    family_sha256: str
    route_report_sha256: str | None
    route_actions: int
    route_frames: int


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupForkProof:
    """One candidate validated after restoring the exact captured origin."""

    provider_recipe_sha256: str
    option_binding_sha256: str
    execution_identity_sha256: str
    fork_runtime_sha256: str
    origin_state_sha256: str
    fresh_observation_sha256: str
    provider_offer_sha256: str
    executable_binding_sha256: str
    family_sha256: str
    route_recipe_sha256: str | None
    route_plan_sha256: str | None
    route_planner_binding_sha256: str | None
    route_terminal_boundary_sha256: str
    route_report_sha256: str | None
    route_controller_actions: int
    route_emulator_frames: int
    restore_effects: int = field(default=0, init=False)
    provider_offer_effects: int = field(default=0, init=False)
    provider_executions: int = field(default=0, init=False)
    learner_effects: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for digest_value, subject in (
            (self.provider_recipe_sha256, "fork provider recipe"),
            (self.option_binding_sha256, "fork option binding"),
            (self.execution_identity_sha256, "fork execution identity"),
            (self.fork_runtime_sha256, "fork runtime"),
            (self.origin_state_sha256, "fork origin state"),
            (self.fresh_observation_sha256, "fork fresh observation"),
            (self.provider_offer_sha256, "fork provider offer"),
            (self.executable_binding_sha256, "fork executable binding"),
            (self.family_sha256, "fork family"),
            (self.route_terminal_boundary_sha256, "fork route terminal"),
        ):
            _require_sha256(digest_value, subject)
        route_values = (
            self.route_recipe_sha256,
            self.route_plan_sha256,
            self.route_planner_binding_sha256,
            self.route_report_sha256,
        )
        if any(item is None for item in route_values) != all(item is None for item in route_values):
            raise RedLivingDexSetupRecipeError("fork route proof is partially bound")
        for value in route_values:
            if value is not None:
                _require_sha256(value, "fork route proof")
        if self.route_recipe_sha256 is None and (
            self.route_controller_actions or self.route_emulator_frames
        ):
            raise RedLivingDexSetupRecipeError("local fork reports route effects")
        for numeric_value, subject in (
            (self.route_controller_actions, "fork route actions"),
            (self.route_emulator_frames, "fork route frames"),
        ):
            if type(numeric_value) is not int or numeric_value < 0:  # noqa: E721
                raise RedLivingDexSetupRecipeError(f"{subject} differ")
        if any(
            value != 0
            for value in (
                self.restore_effects,
                self.provider_offer_effects,
                self.provider_executions,
                self.learner_effects,
            )
        ):
            raise RedLivingDexSetupRecipeError("fork proof crossed a validation-only boundary")

    def private_dict(self) -> dict[str, object]:
        return {
            "executable_binding_sha256": self.executable_binding_sha256,
            "family_sha256": self.family_sha256,
            "execution_identity_sha256": self.execution_identity_sha256,
            "fork_runtime_sha256": self.fork_runtime_sha256,
            "fresh_observation_sha256": self.fresh_observation_sha256,
            "learner_effects": self.learner_effects,
            "option_binding_sha256": self.option_binding_sha256,
            "origin_state_sha256": self.origin_state_sha256,
            "provider_executions": self.provider_executions,
            "provider_offer_effects": self.provider_offer_effects,
            "provider_offer_sha256": self.provider_offer_sha256,
            "provider_recipe_sha256": self.provider_recipe_sha256,
            "restore_effects": self.restore_effects,
            "route_controller_actions": self.route_controller_actions,
            "route_emulator_frames": self.route_emulator_frames,
            "route_plan_sha256": self.route_plan_sha256,
            "route_planner_binding_sha256": self.route_planner_binding_sha256,
            "route_recipe_sha256": self.route_recipe_sha256,
            "route_report_sha256": self.route_report_sha256,
            "route_terminal_boundary_sha256": self.route_terminal_boundary_sha256,
            "schema": RED_LIVING_DEX_SETUP_FORK_PROOF_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexValidatedSetupCapture:
    """Post-validation repeatable capture; still not a learner example."""

    recipe_sha256: str
    execution_identity_sha256: str
    binding: RedLivingDexSetupSlotBinding
    attestation: LivingDexCaptureAttestation
    fork_proofs: tuple[RedLivingDexSetupForkProof, ...]
    origin_observation_sha256: str
    final_origin_observation_sha256: str
    construction_runtime_sha256: str
    construction_route_recipe_sha256: str | None
    construction_route_plan_sha256: str | None
    construction_route_planner_binding_sha256: str | None
    construction_route_terminal_boundary_sha256: str | None
    construction_route_report_sha256: str | None
    construction_route_controller_actions: int
    construction_route_emulator_frames: int
    state_bytes: bytes = field(repr=False)
    envelope_bytes: bytes = field(repr=False)
    origin_restore_count: int = 0
    behavior_draws: int = field(default=0, init=False)
    learner_labels: int = field(default=0, init=False)
    learner_outcomes: int = field(default=0, init=False)
    model_predictions: int = field(default=0, init=False)
    provider_executions: int = field(default=0, init=False)
    teacher_queries: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.recipe_sha256, "validated recipe")
        _require_sha256(self.execution_identity_sha256, "validated execution identity")
        if not isinstance(self.binding, RedLivingDexSetupSlotBinding):
            raise TypeError("validated capture needs a setup binding")
        self.binding.__post_init__()
        if not isinstance(self.attestation, LivingDexCaptureAttestation):
            raise TypeError("validated capture needs an attestation")
        self.attestation.__post_init__()
        if (
            self.binding.execution_identity_sha256 != self.execution_identity_sha256
            or self.attestation.slot_sha256 != self.binding.slot_sha256
            or self.attestation.setup_plan_sha256 != self.binding.setup_plan_sha256
            or self.attestation.terminal_predicate_sha256 != self.binding.terminal_predicate_sha256
            or self.attestation.observer_contract_sha256 != self.binding.observer_contract_sha256
            or self.attestation.root_consumption_sha256 != self.binding.root_consumption_sha256
            or self.attestation.state_sha256 != self.binding.state_sha256
            or self.attestation.envelope_sha256 != self.binding.envelope_sha256
            or self.attestation.menu_sha256 != self.binding.menu_sha256
            or self.attestation.observer_binding_sha256 != self.binding.observer_binding_sha256
            or self.attestation.available_option_kinds != self.binding.available_option_kinds
            or self.attestation.available_family_sha256s != self.binding.available_family_sha256s
            or self.attestation.location_sha256 != self.binding.location_sha256
        ):
            raise RedLivingDexSetupRecipeError(
                "validated capture attestation differs from its binding"
            )
        if (
            not isinstance(self.fork_proofs, tuple)
            or len(self.fork_proofs) != len(self.binding.option_bindings)
            or any(not isinstance(item, RedLivingDexSetupForkProof) for item in self.fork_proofs)
        ):
            raise RedLivingDexSetupRecipeError("validated capture fork census differs")
        for item in self.fork_proofs:
            item.__post_init__()
        for value, subject in (
            (self.origin_observation_sha256, "origin observation"),
            (self.final_origin_observation_sha256, "final origin observation"),
        ):
            _require_sha256(value, subject)
        if self.final_origin_observation_sha256 != self.origin_observation_sha256:
            raise RedLivingDexSetupRecipeError(
                "final restored origin differs from the captured observation"
            )
        _require_sha256(self.construction_runtime_sha256, "construction runtime")
        if self.construction_runtime_sha256 in {
            item.fork_runtime_sha256 for item in self.fork_proofs
        }:
            raise RedLivingDexSetupRecipeError(
                "construction runtime was reused for a candidate fork"
            )
        construction_values = (
            self.construction_route_recipe_sha256,
            self.construction_route_plan_sha256,
            self.construction_route_planner_binding_sha256,
            self.construction_route_terminal_boundary_sha256,
            self.construction_route_report_sha256,
        )
        if any(item is None for item in construction_values) != all(
            item is None for item in construction_values
        ):
            raise RedLivingDexSetupRecipeError(
                "validated construction route proof is partially bound"
            )
        for construction_value in construction_values:
            if construction_value is not None:
                _require_sha256(construction_value, "validated construction route proof")
        for counter_value, subject in (
            (self.construction_route_controller_actions, "construction route actions"),
            (self.construction_route_emulator_frames, "construction route frames"),
        ):
            if type(counter_value) is not int or counter_value < 0:  # noqa: E721
                raise RedLivingDexSetupRecipeError(f"validated {subject} differ")
        if self.construction_route_recipe_sha256 is None:
            if (
                self.construction_route_controller_actions
                or self.construction_route_emulator_frames
            ):
                raise RedLivingDexSetupRecipeError(
                    "route-free validated construction reports effects"
                )
        elif (
            self.construction_route_controller_actions <= 0
            or self.construction_route_emulator_frames <= 0
        ):
            raise RedLivingDexSetupRecipeError(
                "routed validated construction lacks measured effects"
            )
        if tuple(item.option_binding_sha256 for item in self.fork_proofs) != tuple(
            item.binding_sha256 for item in self.binding.option_bindings
        ):
            raise RedLivingDexSetupRecipeError("validated capture fork order differs")
        expected_observer_binding_sha256 = canonical_sha256(
            {
                "construction_route_report_sha256": (
                    self.construction_route_report_sha256
                ),
                "construction_runtime_sha256": self.construction_runtime_sha256,
                "execution_identity_sha256": self.execution_identity_sha256,
                "final_origin_observation_sha256": (
                    self.final_origin_observation_sha256
                ),
                "fork_observation_sha256s": [
                    item.fresh_observation_sha256 for item in self.fork_proofs
                ],
                "fork_proof_sha256s": [
                    canonical_sha256(item.private_dict()) for item in self.fork_proofs
                ],
                "origin_observation_sha256": self.origin_observation_sha256,
                "schema": RED_LIVING_DEX_SETUP_OBSERVER_BINDING_SCHEMA,
                "slot_recipe_sha256": self.recipe_sha256,
            }
        )
        if self.binding.observer_binding_sha256 != expected_observer_binding_sha256:
            raise RedLivingDexSetupRecipeError(
                "validated capture observer proof tree differs"
            )
        for option, proof in zip(
            self.binding.option_bindings,
            self.fork_proofs,
            strict=True,
        ):
            if (
                proof.provider_recipe_sha256 != option.provider_recipe_sha256
                or proof.execution_identity_sha256 != option.execution_identity_sha256
                or proof.execution_identity_sha256 != self.execution_identity_sha256
                or proof.origin_state_sha256 != option.origin_state_sha256
                or proof.fresh_observation_sha256 != option.expected_fresh_observation_sha256
                or proof.provider_offer_sha256 != option.expected_provider_offer_sha256
                or proof.executable_binding_sha256 != option.expected_executable_binding_sha256
                or proof.family_sha256 != option.expected_family_sha256
                or proof.route_plan_sha256 != option.route_plan_sha256
                or proof.route_planner_binding_sha256 != option.route_planner_binding_sha256
                or proof.route_terminal_boundary_sha256
                != option.destination_terminal_boundary_sha256
                or (
                    option.transport_kind is RedLivingDexSetupTransportKind.LOCAL
                    and (
                        proof.route_recipe_sha256 is not None
                        or proof.route_report_sha256 is not None
                    )
                )
                or (
                    option.transport_kind is RedLivingDexSetupTransportKind.ROUTED
                    and (proof.route_recipe_sha256 is None or proof.route_report_sha256 is None)
                )
            ):
                raise RedLivingDexSetupRecipeError(
                    "validated capture fork proof differs from its complete binding"
                )
        if not isinstance(self.state_bytes, bytes) or not self.state_bytes:
            raise RedLivingDexSetupRecipeError("validated capture state is absent")
        if not isinstance(self.envelope_bytes, bytes) or not self.envelope_bytes:
            raise RedLivingDexSetupRecipeError("validated capture envelope is absent")
        if hashlib.sha256(self.state_bytes).hexdigest() != self.binding.state_sha256:
            raise RedLivingDexSetupRecipeError("validated capture state digest differs")
        if hashlib.sha256(self.envelope_bytes).hexdigest() != self.binding.envelope_sha256:
            raise RedLivingDexSetupRecipeError("validated capture envelope digest differs")
        parse_captured_progress(self.envelope_bytes, state_bytes=self.state_bytes)
        if type(self.origin_restore_count) is not int or self.origin_restore_count != (
            len(self.fork_proofs) + 2
        ):  # noqa: E721
            raise RedLivingDexSetupRecipeError("validated capture restore census differs")
        if any(
            value != 0
            for value in (
                self.behavior_draws,
                self.learner_labels,
                self.learner_outcomes,
                self.model_predictions,
                self.provider_executions,
                self.teacher_queries,
            )
        ):
            raise RedLivingDexSetupRecipeError("validated capture crossed the learner boundary")

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_draws": 0,
            "candidate_forks_validated": len(self.fork_proofs),
            "complete_menu_observed": True,
            "construction_route_executed": (
                self.construction_route_recipe_sha256 is not None
            ),
            "execution_identity_bound": True,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "model_predictions": 0,
            "origin_restore_count": self.origin_restore_count,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "schema": RED_LIVING_DEX_SETUP_VALIDATED_CAPTURE_SCHEMA,
            "setup_controller_actions": self.attestation.setup_controller_actions,
            "setup_emulator_frames": self.attestation.setup_emulator_frames,
            "teacher_queries": 0,
        }

    def private_dict(self) -> dict[str, object]:
        """Encode private bytes without retaining a filesystem location."""

        return {
            "attestation_sha256": self.attestation.attestation_sha256,
            "behavior_draws": self.behavior_draws,
            "binding": self.binding.private_dict(),
            "construction_route_controller_actions": (
                self.construction_route_controller_actions
            ),
            "construction_route_emulator_frames": self.construction_route_emulator_frames,
            "construction_route_plan_sha256": self.construction_route_plan_sha256,
            "construction_route_planner_binding_sha256": (
                self.construction_route_planner_binding_sha256
            ),
            "construction_route_recipe_sha256": self.construction_route_recipe_sha256,
            "construction_route_report_sha256": self.construction_route_report_sha256,
            "construction_route_terminal_boundary_sha256": (
                self.construction_route_terminal_boundary_sha256
            ),
            "construction_runtime_sha256": self.construction_runtime_sha256,
            "envelope_payload_base64": _encode_private_bytes(self.envelope_bytes),
            "execution_identity_sha256": self.execution_identity_sha256,
            "fork_proofs": [item.private_dict() for item in self.fork_proofs],
            "final_origin_observation_sha256": self.final_origin_observation_sha256,
            "learner_labels": self.learner_labels,
            "learner_outcomes": self.learner_outcomes,
            "model_predictions": self.model_predictions,
            "origin_restore_count": self.origin_restore_count,
            "origin_observation_sha256": self.origin_observation_sha256,
            "provider_executions": self.provider_executions,
            "recipe_sha256": self.recipe_sha256,
            "schema": RED_LIVING_DEX_SETUP_VALIDATED_CAPTURE_SCHEMA,
            "setup_controller_actions": self.attestation.setup_controller_actions,
            "setup_emulator_frames": self.attestation.setup_emulator_frames,
            "state_payload_base64": _encode_private_bytes(self.state_bytes),
            "teacher_queries": self.teacher_queries,
        }


def restore_red_living_dex_validated_setup_capture(
    document: Mapping[str, object],
) -> RedLivingDexValidatedSetupCapture:
    """Restore one exact private capture after the artifact layer verifies JSON."""

    _exact_keys(
        document,
        {
            "attestation_sha256",
            "behavior_draws",
            "binding",
            "construction_route_controller_actions",
            "construction_route_emulator_frames",
            "construction_route_plan_sha256",
            "construction_route_planner_binding_sha256",
            "construction_route_recipe_sha256",
            "construction_route_report_sha256",
            "construction_route_terminal_boundary_sha256",
            "construction_runtime_sha256",
            "envelope_payload_base64",
            "execution_identity_sha256",
            "final_origin_observation_sha256",
            "fork_proofs",
            "learner_labels",
            "learner_outcomes",
            "model_predictions",
            "origin_restore_count",
            "origin_observation_sha256",
            "provider_executions",
            "recipe_sha256",
            "schema",
            "setup_controller_actions",
            "setup_emulator_frames",
            "state_payload_base64",
            "teacher_queries",
        },
        "validated setup capture",
    )
    if document["schema"] != RED_LIVING_DEX_SETUP_VALIDATED_CAPTURE_SCHEMA:
        raise RedLivingDexSetupRecipeError("validated setup capture schema differs")
    for key in (
        "behavior_draws",
        "learner_labels",
        "learner_outcomes",
        "model_predictions",
        "provider_executions",
        "teacher_queries",
    ):
        if _integer(document[key], f"validated setup capture {key}") != 0:
            raise RedLivingDexSetupRecipeError("stored setup capture crossed the learner boundary")
    binding = _restore_slot_binding(_mapping(document["binding"], "setup binding"))
    setup_actions = _integer(
        document["setup_controller_actions"],
        "validated setup actions",
    )
    setup_frames = _integer(
        document["setup_emulator_frames"],
        "validated setup frames",
    )
    attestation = LivingDexCaptureAttestation(
        slot_sha256=binding.slot_sha256,
        setup_plan_sha256=binding.setup_plan_sha256,
        terminal_predicate_sha256=binding.terminal_predicate_sha256,
        observer_contract_sha256=binding.observer_contract_sha256,
        root_consumption_sha256=binding.root_consumption_sha256,
        state_sha256=binding.state_sha256,
        envelope_sha256=binding.envelope_sha256,
        menu_sha256=binding.menu_sha256,
        observer_binding_sha256=binding.observer_binding_sha256,
        available_option_kinds=binding.available_option_kinds,
        available_family_sha256s=binding.available_family_sha256s,
        location_sha256=binding.location_sha256,
        setup_controller_actions=setup_actions,
        setup_emulator_frames=setup_frames,
    )
    if attestation.attestation_sha256 != _string(
        document["attestation_sha256"],
        "validated setup attestation",
    ):
        raise RedLivingDexSetupRecipeError("stored setup capture attestation digest differs")
    raw_proofs = _sequence(document["fork_proofs"], "setup fork proofs")
    proofs = tuple(_restore_fork_proof(_mapping(item, "setup fork proof")) for item in raw_proofs)
    return RedLivingDexValidatedSetupCapture(
        recipe_sha256=_string(document["recipe_sha256"], "validated recipe"),
        execution_identity_sha256=_string(
            document["execution_identity_sha256"],
            "validated execution identity",
        ),
        binding=binding,
        attestation=attestation,
        fork_proofs=proofs,
        origin_observation_sha256=_string(
            document["origin_observation_sha256"],
            "validated origin observation",
        ),
        final_origin_observation_sha256=_string(
            document["final_origin_observation_sha256"],
            "validated final origin observation",
        ),
        construction_runtime_sha256=_string(
            document["construction_runtime_sha256"],
            "validated construction runtime",
        ),
        construction_route_recipe_sha256=_optional_string(
            document["construction_route_recipe_sha256"],
            "validated construction route recipe",
        ),
        construction_route_plan_sha256=_optional_string(
            document["construction_route_plan_sha256"],
            "validated construction route plan",
        ),
        construction_route_planner_binding_sha256=_optional_string(
            document["construction_route_planner_binding_sha256"],
            "validated construction route planner",
        ),
        construction_route_terminal_boundary_sha256=_optional_string(
            document["construction_route_terminal_boundary_sha256"],
            "validated construction route terminal",
        ),
        construction_route_report_sha256=_optional_string(
            document["construction_route_report_sha256"],
            "validated construction route report",
        ),
        construction_route_controller_actions=_integer(
            document["construction_route_controller_actions"],
            "validated construction route actions",
        ),
        construction_route_emulator_frames=_integer(
            document["construction_route_emulator_frames"],
            "validated construction route frames",
        ),
        state_bytes=_decode_private_bytes(
            document["state_payload_base64"],
            subject="validated state payload",
            maximum_bytes=8 * 1024 * 1024,
        ),
        envelope_bytes=_decode_private_bytes(
            document["envelope_payload_base64"],
            subject="validated envelope payload",
            maximum_bytes=256 * 1024,
        ),
        origin_restore_count=_integer(
            document["origin_restore_count"],
            "validated restore count",
        ),
    )


def _restore_slot_binding(
    document: Mapping[str, object],
) -> RedLivingDexSetupSlotBinding:
    _exact_keys(
        document,
        {
            "available_family_sha256s",
            "available_option_kinds",
            "envelope_sha256",
            "execution_identity_sha256",
            "location_sha256",
            "menu_sha256",
            "observer_binding_sha256",
            "observer_contract_sha256",
            "option_bindings",
            "origin_boundary_sha256",
            "partition",
            "root_consumption_sha256",
            "schema",
            "setup_plan_sha256",
            "slot_sha256",
            "state_sha256",
            "terminal_predicate_sha256",
        },
        "setup binding",
    )
    from pokemon_red_completion.red_living_dex_setup_campaign import (
        RED_LIVING_DEX_SETUP_SLOT_BINDING_SCHEMA,
    )

    if document["schema"] != RED_LIVING_DEX_SETUP_SLOT_BINDING_SCHEMA:
        raise RedLivingDexSetupRecipeError("stored setup binding schema differs")
    raw_kinds = _sequence(document["available_option_kinds"], "setup option kinds")
    try:
        kinds = tuple(LivingDexOptionKind(_string(item, "setup option kind")) for item in raw_kinds)
        partition = LivingDexCapturePartition(_string(document["partition"], "setup partition"))
    except ValueError:
        raise RedLivingDexSetupRecipeError("stored setup enum differs") from None
    return RedLivingDexSetupSlotBinding(
        slot_sha256=_string(document["slot_sha256"], "setup slot"),
        setup_plan_sha256=_string(document["setup_plan_sha256"], "setup plan"),
        terminal_predicate_sha256=_string(
            document["terminal_predicate_sha256"],
            "setup terminal predicate",
        ),
        observer_contract_sha256=_string(
            document["observer_contract_sha256"],
            "setup observer contract",
        ),
        execution_identity_sha256=_string(
            document["execution_identity_sha256"],
            "setup execution identity",
        ),
        partition=partition,
        available_option_kinds=kinds,
        root_consumption_sha256=_string(
            document["root_consumption_sha256"],
            "setup root",
        ),
        state_sha256=_string(document["state_sha256"], "setup state"),
        origin_boundary_sha256=_string(
            document["origin_boundary_sha256"],
            "setup origin",
        ),
        envelope_sha256=_string(document["envelope_sha256"], "setup envelope"),
        menu_sha256=_string(document["menu_sha256"], "setup menu"),
        observer_binding_sha256=_string(
            document["observer_binding_sha256"],
            "setup observer binding",
        ),
        available_family_sha256s=tuple(
            _string(item, "setup family")
            for item in _sequence(
                document["available_family_sha256s"],
                "setup families",
            )
        ),
        location_sha256=_string(document["location_sha256"], "setup location"),
        option_bindings=tuple(
            _restore_option_binding(_mapping(item, "setup option binding"))
            for item in _sequence(document["option_bindings"], "setup option bindings")
        ),
    )


def _restore_option_binding(
    document: Mapping[str, object],
) -> RedLivingDexSetupOptionBinding:
    _exact_keys(
        document,
        {
            "destination_terminal_boundary_sha256",
            "expected_executable_binding_sha256",
            "expected_family_sha256",
            "expected_fresh_observation_sha256",
            "expected_provider_offer_sha256",
            "goal_kind",
            "execution_identity_sha256",
            "option_kind",
            "origin_boundary_sha256",
            "origin_state_sha256",
            "provider_capability_sha256",
            "provider_contract_id",
            "provider_recipe_sha256",
            "raw_controller_sequence_steps",
            "route_plan_sha256",
            "route_planner_binding_sha256",
            "route_source",
            "route_terminal_predicate_sha256",
            "schema",
            "teacher_route",
            "transport_kind",
        },
        "setup option binding",
    )
    from pokemon_red_completion.red_living_dex_setup_campaign import (
        RED_LIVING_DEX_SETUP_OPTION_BINDING_SCHEMA,
    )

    if document["schema"] != RED_LIVING_DEX_SETUP_OPTION_BINDING_SCHEMA:
        raise RedLivingDexSetupRecipeError("stored setup option schema differs")
    if _integer(
        document["raw_controller_sequence_steps"],
        "setup raw controller sequence",
    ) != 0 or _boolean(document["teacher_route"], "setup teacher route"):
        raise RedLivingDexSetupRecipeError("stored setup option contains a teacher route")
    try:
        kind = LivingDexOptionKind(_string(document["option_kind"], "setup option kind"))
        goal_kind = GoalKind(_string(document["goal_kind"], "setup goal kind"))
        transport = RedLivingDexSetupTransportKind(
            _string(document["transport_kind"], "setup transport kind")
        )
    except ValueError:
        raise RedLivingDexSetupRecipeError("stored setup option enum differs") from None
    route_plan = _optional_string(document["route_plan_sha256"], "setup route plan")
    route_terminal = _optional_string(
        document["route_terminal_predicate_sha256"],
        "setup route terminal",
    )
    route_planner = _optional_string(
        document["route_planner_binding_sha256"],
        "setup route planner",
    )
    route_source = document["route_source"]
    if (transport is RedLivingDexSetupTransportKind.LOCAL and route_source is not None) or (
        transport is RedLivingDexSetupTransportKind.ROUTED and route_source != "semantic-router-v1"
    ):
        raise RedLivingDexSetupRecipeError("stored setup route source differs")
    return RedLivingDexSetupOptionBinding(
        option_kind=kind,
        goal_kind=goal_kind,
        transport_kind=transport,
        provider_contract_id=_string(
            document["provider_contract_id"],
            "setup provider contract",
        ),
        provider_capability_sha256=_string(
            document["provider_capability_sha256"],
            "setup provider capability",
        ),
        provider_recipe_sha256=_string(
            document["provider_recipe_sha256"],
            "setup provider recipe",
        ),
        expected_family_sha256=_string(
            document["expected_family_sha256"],
            "setup family",
        ),
        execution_identity_sha256=_string(
            document["execution_identity_sha256"],
            "setup execution identity",
        ),
        origin_state_sha256=_string(
            document["origin_state_sha256"],
            "setup origin state",
        ),
        origin_boundary_sha256=_string(
            document["origin_boundary_sha256"],
            "setup origin boundary",
        ),
        destination_terminal_boundary_sha256=_string(
            document["destination_terminal_boundary_sha256"],
            "setup destination terminal",
        ),
        expected_fresh_observation_sha256=_string(
            document["expected_fresh_observation_sha256"],
            "setup fresh observation",
        ),
        expected_provider_offer_sha256=_string(
            document["expected_provider_offer_sha256"],
            "setup provider offer",
        ),
        expected_executable_binding_sha256=_string(
            document["expected_executable_binding_sha256"],
            "setup executable binding",
        ),
        route_plan_sha256=route_plan,
        route_terminal_predicate_sha256=route_terminal,
        route_planner_binding_sha256=route_planner,
    )


def _restore_fork_proof(
    document: Mapping[str, object],
) -> RedLivingDexSetupForkProof:
    _exact_keys(
        document,
        {
            "executable_binding_sha256",
            "execution_identity_sha256",
            "family_sha256",
            "fork_runtime_sha256",
            "fresh_observation_sha256",
            "learner_effects",
            "option_binding_sha256",
            "origin_state_sha256",
            "provider_executions",
            "provider_offer_effects",
            "provider_offer_sha256",
            "provider_recipe_sha256",
            "restore_effects",
            "route_controller_actions",
            "route_emulator_frames",
            "route_plan_sha256",
            "route_planner_binding_sha256",
            "route_recipe_sha256",
            "route_report_sha256",
            "route_terminal_boundary_sha256",
            "schema",
        },
        "setup fork proof",
    )
    if document["schema"] != RED_LIVING_DEX_SETUP_FORK_PROOF_SCHEMA:
        raise RedLivingDexSetupRecipeError("setup fork proof schema differs")
    for key in (
        "learner_effects",
        "provider_executions",
        "provider_offer_effects",
        "restore_effects",
    ):
        if _integer(document[key], f"setup fork proof {key}") != 0:
            raise RedLivingDexSetupRecipeError("stored setup fork crossed the learner boundary")
    return RedLivingDexSetupForkProof(
        provider_recipe_sha256=_string(
            document["provider_recipe_sha256"],
            "fork provider recipe",
        ),
        option_binding_sha256=_string(
            document["option_binding_sha256"],
            "fork option binding",
        ),
        execution_identity_sha256=_string(
            document["execution_identity_sha256"],
            "fork execution identity",
        ),
        fork_runtime_sha256=_string(
            document["fork_runtime_sha256"],
            "fork runtime",
        ),
        origin_state_sha256=_string(
            document["origin_state_sha256"],
            "fork origin state",
        ),
        fresh_observation_sha256=_string(
            document["fresh_observation_sha256"],
            "fork fresh observation",
        ),
        provider_offer_sha256=_string(
            document["provider_offer_sha256"],
            "fork provider offer",
        ),
        executable_binding_sha256=_string(
            document["executable_binding_sha256"],
            "fork executable binding",
        ),
        family_sha256=_string(document["family_sha256"], "fork family"),
        route_recipe_sha256=_optional_string(
            document["route_recipe_sha256"],
            "fork route recipe",
        ),
        route_plan_sha256=_optional_string(
            document["route_plan_sha256"],
            "fork route plan",
        ),
        route_planner_binding_sha256=_optional_string(
            document["route_planner_binding_sha256"],
            "fork route planner",
        ),
        route_terminal_boundary_sha256=_string(
            document["route_terminal_boundary_sha256"],
            "fork route terminal",
        ),
        route_report_sha256=_optional_string(
            document["route_report_sha256"],
            "fork route report",
        ),
        route_controller_actions=_integer(
            document["route_controller_actions"],
            "fork route actions",
        ),
        route_emulator_frames=_integer(
            document["route_emulator_frames"],
            "fork route frames",
        ),
    )


@runtime_checkable
class RedLivingDexSetupStatePort(Protocol):
    """Exact in-memory save-state authority shared by one isolated arm."""

    @property
    def frame_count(self) -> int: ...

    def load_state_bytes(self, payload: bytes) -> None: ...

    def save_state_bytes(self) -> bytes: ...


@runtime_checkable
class RedLivingDexSetupForkRuntime(Protocol):
    """One fresh emulator arm; it cannot attest its own route or provider offer."""

    @property
    def arm_identity_sha256(self) -> str: ...

    @property
    def execution_identity_sha256(self) -> str: ...

    @property
    def emulator(self) -> RedLivingDexSetupStatePort: ...

    @property
    def actions(self) -> CountingExecutor: ...

    @property
    def effect_meter(self) -> RedLivingDexSetupEffectMeter: ...

    def observe_fresh(self) -> FreshRedGoalObservation: ...

    def build_route(
        self,
        recipe: RedLivingDexSetupRouteRecipe,
        *,
        origin_observation_sha256: str,
    ) -> RedSemanticTransportRoute: ...

    def build_goal_context(
        self,
        profile: RedGoalContextProfile,
        capture: GoalManagerContextCapture,
    ) -> RedGoalContextRuntime: ...


RedLivingDexSetupForkRuntimeFactory = Callable[
    [RedLivingDexSetupSlotRecipe, str, int],
    RedLivingDexSetupForkRuntime,
]


def validate_red_living_dex_setup_recipe(
    slot: LivingDexProspectiveCaptureSlot,
    recipe: RedLivingDexSetupSlotRecipe,
    *,
    execution_identity: RedLivingDexSetupExecutionIdentity,
    root: RedLivingDexAuthenticatedSetupRoot,
    arm_factory: RedLivingDexSetupForkRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexValidatedSetupCapture:
    """Build one origin and validate every candidate through isolated real seams."""

    if not isinstance(slot, LivingDexProspectiveCaptureSlot):
        raise TypeError("same-root validation needs a prospective slot")
    slot.__post_init__()
    if not isinstance(recipe, RedLivingDexSetupSlotRecipe):
        raise TypeError("same-root validation needs a setup recipe")
    recipe.__post_init__()
    _require_recipe_join(slot, recipe)
    if not isinstance(execution_identity, RedLivingDexSetupExecutionIdentity):
        raise TypeError("same-root validation needs an execution identity")
    execution_identity.__post_init__()
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("same-root validation needs an authenticated root")
    root.__post_init__()
    _require_root_join(recipe, root)
    if not callable(arm_factory):
        raise TypeError("same-root validation needs an isolated-arm factory")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("same-root validation needs a comprehensive effect meter")

    setup_before = _checkpoint(meter)
    used_arm_identities: set[str] = set()
    construction_arm = _open_arm(
        arm_factory,
        recipe,
        purpose="construction",
        ordinal=0,
        execution_identity=execution_identity,
        meter=meter,
        used_arm_identities=used_arm_identities,
    )
    _load_and_read_back(
        construction_arm,
        root.state_bytes,
        meter=meter,
        subject="construction root",
    )
    base_fresh = _observe_arm(
        construction_arm,
        meter=meter,
        subject="construction root",
    )
    _require_fresh_at(base_fresh, recipe.base_boundary, "construction root")
    if recipe.construction_route is None:
        origin_fresh = base_fresh
        construction_report_sha256 = None
        construction_actions = 0
        construction_frames = 0
    else:
        (
            origin_fresh,
            construction_report_sha256,
            construction_actions,
            construction_frames,
        ) = _execute_authenticated_route(
            construction_arm,
            recipe.construction_route,
            base_fresh,
            meter=meter,
        )
    _require_fresh_at(origin_fresh, recipe.origin_boundary, "constructed origin")
    origin_state_bytes = _save_state_bytes(
        construction_arm.emulator,
        meter=meter,
        subject="constructed origin",
    )
    origin_envelope_bytes = _derived_envelope_bytes(
        root.envelope_bytes,
        source_state_bytes=root.state_bytes,
        state_bytes=origin_state_bytes,
    )
    origin = RedLivingDexConstructedOrigin(
        state_bytes=origin_state_bytes,
        envelope_bytes=origin_envelope_bytes,
        consumed_root_state_bytes=root.state_bytes,
        consumed_root_envelope_bytes=root.envelope_bytes,
        fresh=origin_fresh,
        root_consumption_sha256=root.root_consumption_sha256,
        consumed_root_state_sha256=root.state_sha256,
        consumed_root_envelope_sha256=root.envelope_sha256,
        construction_runtime_sha256=construction_arm.arm_identity_sha256,
        construction_route_recipe_sha256=(
            None
            if recipe.construction_route is None
            else recipe.construction_route.recipe_sha256
        ),
        construction_route_plan_sha256=(
            None
            if recipe.construction_route is None
            else recipe.construction_route.route_plan_sha256
        ),
        construction_route_planner_binding_sha256=(
            None
            if recipe.construction_route is None
            else recipe.construction_route.planner_binding_sha256
        ),
        construction_route_terminal_boundary_sha256=(
            None
            if recipe.construction_route is None
            else recipe.construction_route.terminal_boundary.sha256
        ),
        construction_route_report_sha256=construction_report_sha256,
        construction_route_controller_actions=construction_actions,
        construction_route_emulator_frames=construction_frames,
    )
    _validate_constructed_origin(recipe, origin)
    if recipe.construction_route is None:
        if construction_report_sha256 is not None:
            raise RedLivingDexSetupRecipeError("route-free construction retained a route report")
        construction_delta = _delta(setup_before, _checkpoint(meter))
        if construction_delta != (0, 0):
            raise RedLivingDexSetupRecipeError(
                "route-free origin construction changed setup effects"
            )
    elif (
        construction_report_sha256 is None or construction_actions <= 0 or construction_frames <= 0
    ):
        raise RedLivingDexSetupRecipeError(
            "routed origin construction lacks authenticated execution"
        )

    option_bindings: list[RedLivingDexSetupOptionBinding] = []
    provisional_proofs: list[_ProvisionalFork] = []
    for option_ordinal, provider_recipe in enumerate(recipe.providers):
        arm = _open_arm(
            arm_factory,
            recipe,
            purpose="candidate",
            ordinal=option_ordinal,
            execution_identity=execution_identity,
            meter=meter,
            used_arm_identities=used_arm_identities,
        )
        _load_and_read_back(
            arm,
            origin.state_bytes,
            meter=meter,
            subject="candidate origin",
        )
        restored = _observe_arm(arm, meter=meter, subject="candidate origin")
        _require_fresh_at(restored, recipe.origin_boundary, "restored origin")
        if restored.observation_sha256 != origin.fresh.observation_sha256:
            raise RedLivingDexSetupRecipeError(
                "restored origin differs from the captured decision state"
            )

        if provider_recipe.route is None:
            fresh = restored
            route_report_sha256 = None
            route_actions = 0
            route_frames = 0
            terminal = recipe.origin_boundary
        else:
            (
                fresh,
                route_report_sha256,
                route_actions,
                route_frames,
            ) = _execute_authenticated_route(
                arm,
                provider_recipe.route,
                restored,
                meter=meter,
            )
            terminal = provider_recipe.route.terminal_boundary
        _require_fresh_at(fresh, terminal, "candidate terminal")

        destination_state_bytes = _save_state_bytes(
            arm.emulator,
            meter=meter,
            subject="candidate terminal",
        )
        destination_envelope_bytes = _derived_envelope_bytes(
            origin.envelope_bytes,
            source_state_bytes=origin.state_bytes,
            state_bytes=destination_state_bytes,
        )
        context_capture = parse_goal_manager_context_capture(
            destination_state_bytes,
            destination_envelope_bytes,
        )
        context_before = _checkpoint(meter)
        context = arm.build_goal_context(provider_recipe.profile, context_capture)
        context_after = _checkpoint(meter)
        if context_after != context_before:
            raise RedLivingDexSetupRecipeError(
                "provider registry construction changed protected effects"
            )
        if (
            type(context) is not RedGoalContextRuntime
            or context.profile.profile_sha256 != provider_recipe.profile.profile_sha256
            or context.capture is not context_capture
            or context.capture.state_sha256 != hashlib.sha256(destination_state_bytes).hexdigest()
            or context.emulator is not arm.emulator
        ):
            raise RedLivingDexSetupRecipeError(
                "provider registry differs from the isolated candidate state"
            )
        context_observation_before = _checkpoint(meter)
        context_observation = context.adapter.observe()
        if _checkpoint(meter) != context_observation_before:
            raise RedLivingDexSetupRecipeError(
                "provider registry observation changed protected effects"
            )
        context_fresh = FreshRedGoalObservation(
            red_living_dex_setup_fresh_observation_sha256(
                FreshRedGoalObservation(
                    "0" * 64,
                    context_observation,
                    fresh.traversal,
                )
            ),
            context_observation,
            fresh.traversal,
        )
        _require_fresh_at(context_fresh, terminal, "provider registry observation")
        if context_fresh.observation_sha256 != fresh.observation_sha256:
            raise RedLivingDexSetupRecipeError("provider registry observed another candidate state")

        offer_before = _checkpoint(meter)
        observed = context.offer_for(
            provider_recipe.goal_kind,
            context_observation,
            arm.actions,
        )
        offer_after = _checkpoint(meter)
        if offer_after != offer_before:
            raise RedLivingDexSetupRecipeError("provider offer changed protected setup effects")
        (
            executable_binding,
            fresh_sha256,
            executable_sha256,
            offer_sha256,
            family_sha256,
        ) = _validate_registry_offer(provider_recipe, context_fresh, observed)
        option_binding = RedLivingDexSetupOptionBinding(
            option_kind=provider_recipe.option_kind,
            goal_kind=provider_recipe.goal_kind,
            transport_kind=(
                RedLivingDexSetupTransportKind.LOCAL
                if provider_recipe.route is None
                else RedLivingDexSetupTransportKind.ROUTED
            ),
            provider_contract_id=provider_recipe.provider_contract_id,
            provider_capability_sha256=(
                _CAPABILITY_BY_KIND[provider_recipe.option_kind].capability_sha256
            ),
            provider_recipe_sha256=provider_recipe.recipe_sha256,
            expected_family_sha256=family_sha256,
            execution_identity_sha256=execution_identity.identity_sha256,
            origin_state_sha256=origin.state_sha256,
            origin_boundary_sha256=recipe.origin_boundary.sha256,
            destination_terminal_boundary_sha256=terminal.sha256,
            expected_fresh_observation_sha256=fresh_sha256,
            expected_provider_offer_sha256=offer_sha256,
            expected_executable_binding_sha256=executable_sha256,
            route_plan_sha256=(
                None if provider_recipe.route is None else provider_recipe.route.route_plan_sha256
            ),
            route_terminal_predicate_sha256=(
                None if provider_recipe.route is None else terminal.sha256
            ),
            route_planner_binding_sha256=(
                None
                if provider_recipe.route is None
                else provider_recipe.route.planner_binding_sha256
            ),
        )
        option_bindings.append(option_binding)
        provisional_proofs.append(
            _ProvisionalFork(
                provider_recipe=provider_recipe,
                executable_binding=executable_binding,
                fork_runtime_sha256=arm.arm_identity_sha256,
                fresh_sha256=fresh_sha256,
                executable_sha256=executable_sha256,
                offer_sha256=offer_sha256,
                family_sha256=family_sha256,
                route_report_sha256=route_report_sha256,
                route_actions=route_actions,
                route_frames=route_frames,
            )
        )

    final_arm = _open_arm(
        arm_factory,
        recipe,
        purpose="final_restore",
        ordinal=len(recipe.providers),
        execution_identity=execution_identity,
        meter=meter,
        used_arm_identities=used_arm_identities,
    )
    _load_and_read_back(
        final_arm,
        origin.state_bytes,
        meter=meter,
        subject="final origin",
    )
    final_fresh = _observe_arm(final_arm, meter=meter, subject="final origin")
    _require_fresh_at(final_fresh, recipe.origin_boundary, "final restored origin")
    if final_fresh.observation_sha256 != origin.fresh.observation_sha256:
        raise RedLivingDexSetupRecipeError(
            "final restored origin differs from the captured decision state"
        )

    setup_after = _checkpoint(meter)
    setup_actions, setup_frames = _delta(setup_before, setup_after)
    _require_within_slot_budget(slot, setup_actions, setup_frames)
    families = tuple(item.family_sha256 for item in provisional_proofs)
    location_sha256 = _location_sha256(recipe.origin_boundary)
    menu_sha256 = canonical_sha256(
        {
            "execution_identity_sha256": execution_identity.identity_sha256,
            "option_bindings": [item.binding_sha256 for item in option_bindings],
            "option_kinds": [item.value for item in recipe.available_option_kinds],
            "origin_state_sha256": origin.state_sha256,
            "schema": RED_LIVING_DEX_SETUP_MENU_SCHEMA,
            "slot_sha256": recipe.slot_sha256,
        }
    )
    fork_proofs = tuple(
        RedLivingDexSetupForkProof(
            provider_recipe_sha256=item.provider_recipe.recipe_sha256,
            option_binding_sha256=option.binding_sha256,
            execution_identity_sha256=execution_identity.identity_sha256,
            fork_runtime_sha256=item.fork_runtime_sha256,
            origin_state_sha256=origin.state_sha256,
            fresh_observation_sha256=item.fresh_sha256,
            provider_offer_sha256=item.offer_sha256,
            executable_binding_sha256=item.executable_sha256,
            family_sha256=item.family_sha256,
            route_recipe_sha256=(
                None
                if item.provider_recipe.route is None
                else item.provider_recipe.route.recipe_sha256
            ),
            route_plan_sha256=option.route_plan_sha256,
            route_planner_binding_sha256=option.route_planner_binding_sha256,
            route_terminal_boundary_sha256=(option.destination_terminal_boundary_sha256),
            route_report_sha256=item.route_report_sha256,
            route_controller_actions=item.route_actions,
            route_emulator_frames=item.route_frames,
        )
        for option, item in zip(option_bindings, provisional_proofs, strict=True)
    )
    observer_binding_sha256 = canonical_sha256(
        {
            "construction_route_report_sha256": origin.construction_route_report_sha256,
            "construction_runtime_sha256": origin.construction_runtime_sha256,
            "execution_identity_sha256": execution_identity.identity_sha256,
            "final_origin_observation_sha256": final_fresh.observation_sha256,
            "fork_observation_sha256s": [item.fresh_sha256 for item in provisional_proofs],
            "fork_proof_sha256s": [
                canonical_sha256(item.private_dict()) for item in fork_proofs
            ],
            "origin_observation_sha256": origin.fresh.observation_sha256,
            "schema": RED_LIVING_DEX_SETUP_OBSERVER_BINDING_SCHEMA,
            "slot_recipe_sha256": recipe.recipe_sha256,
        }
    )
    slot_binding = RedLivingDexSetupSlotBinding(
        slot_sha256=slot.slot_sha256,
        setup_plan_sha256=slot.setup.setup_plan_sha256,
        terminal_predicate_sha256=slot.setup.terminal_predicate_sha256,
        observer_contract_sha256=slot.setup.observer_contract_sha256,
        execution_identity_sha256=execution_identity.identity_sha256,
        partition=slot.partition,
        available_option_kinds=slot.available_option_kinds,
        root_consumption_sha256=recipe.root_consumption_sha256,
        state_sha256=origin.state_sha256,
        origin_boundary_sha256=recipe.origin_boundary.sha256,
        envelope_sha256=origin.envelope_sha256,
        menu_sha256=menu_sha256,
        observer_binding_sha256=observer_binding_sha256,
        available_family_sha256s=families,
        location_sha256=location_sha256,
        option_bindings=tuple(option_bindings),
    )
    attestation = LivingDexCaptureAttestation(
        slot_sha256=slot.slot_sha256,
        setup_plan_sha256=slot.setup.setup_plan_sha256,
        terminal_predicate_sha256=slot.setup.terminal_predicate_sha256,
        observer_contract_sha256=slot.setup.observer_contract_sha256,
        root_consumption_sha256=recipe.root_consumption_sha256,
        state_sha256=origin.state_sha256,
        envelope_sha256=origin.envelope_sha256,
        menu_sha256=menu_sha256,
        observer_binding_sha256=observer_binding_sha256,
        available_option_kinds=slot.available_option_kinds,
        available_family_sha256s=families,
        location_sha256=location_sha256,
        setup_controller_actions=setup_actions,
        setup_emulator_frames=setup_frames,
    )
    return RedLivingDexValidatedSetupCapture(
        recipe_sha256=recipe.recipe_sha256,
        execution_identity_sha256=execution_identity.identity_sha256,
        binding=slot_binding,
        attestation=attestation,
        fork_proofs=fork_proofs,
        origin_observation_sha256=origin.fresh.observation_sha256,
        final_origin_observation_sha256=final_fresh.observation_sha256,
        construction_runtime_sha256=origin.construction_runtime_sha256,
        construction_route_recipe_sha256=origin.construction_route_recipe_sha256,
        construction_route_plan_sha256=origin.construction_route_plan_sha256,
        construction_route_planner_binding_sha256=(
            origin.construction_route_planner_binding_sha256
        ),
        construction_route_terminal_boundary_sha256=(
            origin.construction_route_terminal_boundary_sha256
        ),
        construction_route_report_sha256=origin.construction_route_report_sha256,
        construction_route_controller_actions=origin.construction_route_controller_actions,
        construction_route_emulator_frames=origin.construction_route_emulator_frames,
        state_bytes=origin.state_bytes,
        envelope_bytes=origin.envelope_bytes,
        origin_restore_count=len(recipe.providers) + 2,
    )


def _open_arm(
    factory: RedLivingDexSetupForkRuntimeFactory,
    recipe: RedLivingDexSetupSlotRecipe,
    *,
    purpose: str,
    ordinal: int,
    execution_identity: RedLivingDexSetupExecutionIdentity,
    meter: RedLivingDexSetupEffectMeter,
    used_arm_identities: set[str],
) -> RedLivingDexSetupForkRuntime:
    if purpose not in {"construction", "candidate", "final_restore"}:
        raise RedLivingDexSetupRecipeError("setup fork purpose differs")
    before = _checkpoint(meter)
    arm = factory(recipe, purpose, ordinal)
    if not isinstance(arm, RedLivingDexSetupForkRuntime):
        raise RedLivingDexSetupRecipeError("setup factory returned an invalid isolated arm")
    _require_sha256(arm.arm_identity_sha256, "setup fork runtime")
    if arm.arm_identity_sha256 in used_arm_identities:
        raise RedLivingDexSetupRecipeError("setup factory reused an isolated arm identity")
    if arm.execution_identity_sha256 != execution_identity.identity_sha256:
        raise RedLivingDexSetupRecipeError("setup fork execution identity differs")
    if arm.effect_meter is not meter:
        raise RedLivingDexSetupRecipeError("setup fork does not share the protected meter")
    if not isinstance(arm.emulator, RedLivingDexSetupStatePort):
        raise RedLivingDexSetupRecipeError("setup fork lacks an exact state port")
    if not isinstance(arm.actions, CountingExecutor):
        raise RedLivingDexSetupRecipeError("setup fork lacks a counted action port")
    if _checkpoint(meter) != before:
        raise RedLivingDexSetupRecipeError("setup fork construction changed protected effects")
    used_arm_identities.add(arm.arm_identity_sha256)
    return arm


def _load_and_read_back(
    arm: RedLivingDexSetupForkRuntime,
    payload: bytes,
    *,
    meter: RedLivingDexSetupEffectMeter,
    subject: str,
) -> None:
    if not isinstance(payload, bytes) or not payload:
        raise RedLivingDexSetupRecipeError(f"{subject} state is absent")
    before = _checkpoint(meter)
    arm.emulator.load_state_bytes(payload)
    readback = arm.emulator.save_state_bytes()
    after = _checkpoint(meter)
    if after != before:
        raise RedLivingDexSetupRecipeError(f"{subject} restore changed protected effects")
    if (
        not isinstance(readback, bytes)
        or hashlib.sha256(readback).digest() != hashlib.sha256(payload).digest()
    ):
        raise RedLivingDexSetupRecipeError(f"{subject} restore readback differs")


def _save_state_bytes(
    emulator: RedLivingDexSetupStatePort,
    *,
    meter: RedLivingDexSetupEffectMeter,
    subject: str,
) -> bytes:
    before = _checkpoint(meter)
    payload = emulator.save_state_bytes()
    after = _checkpoint(meter)
    if after != before:
        raise RedLivingDexSetupRecipeError(f"{subject} state readback changed protected effects")
    if not isinstance(payload, bytes) or not payload:
        raise RedLivingDexSetupRecipeError(f"{subject} state readback is absent")
    return payload


def _observe_arm(
    arm: RedLivingDexSetupForkRuntime,
    *,
    meter: RedLivingDexSetupEffectMeter,
    subject: str,
) -> FreshRedGoalObservation:
    before = _checkpoint(meter)
    fresh = arm.observe_fresh()
    after = _checkpoint(meter)
    if after != before:
        raise RedLivingDexSetupRecipeError(f"{subject} observation changed protected effects")
    _require_fresh(fresh)
    return fresh


def _execute_authenticated_route(
    arm: RedLivingDexSetupForkRuntime,
    recipe: RedLivingDexSetupRouteRecipe,
    origin: FreshRedGoalObservation,
    *,
    meter: RedLivingDexSetupEffectMeter,
) -> tuple[FreshRedGoalObservation, str, int, int]:
    before = _checkpoint(meter)
    origin_state_bytes = _save_state_bytes(
        arm.emulator,
        meter=meter,
        subject="semantic route origin",
    )
    route = arm.build_route(
        recipe,
        origin_observation_sha256=origin.observation_sha256,
    )
    built = _checkpoint(meter)
    if built != before:
        raise RedLivingDexSetupRecipeError("semantic route construction changed protected effects")
    if (
        type(route) is not RedSemanticTransportRoute
        or route.plan is not recipe.plan
        or route.planner_binding_sha256 != recipe.planner_binding_sha256
        or route.origin_observation_sha256 != origin.observation_sha256
        or route.actions is not arm.actions
        or route.emulator is not arm.emulator
        or route.route_source != "authenticated_semantic_router"
        or route.profile_direction_steps != 0
        or route.curriculum_direction_steps != 0
    ):
        raise RedLivingDexSetupRecipeError("isolated arm constructed a different semantic route")
    binding = route.route_binding()
    report = binding.execute()
    verification = binding.verify(report)
    if verification.status is not GoalDecisionOutcome.SUCCEEDED:
        raise RedLivingDexSetupRecipeError("semantic route did not verify")
    route_report = route.authenticated_report()
    if (
        not isinstance(route_report, RouteExecutionReport)
        or route_report.initial_plan is not recipe.plan
        or not route_report.passed
        or not recipe.terminal_boundary.matches_traversal(route_report.terminal)
    ):
        raise RedLivingDexSetupRecipeError("semantic route report differs")
    after = _checkpoint(meter)
    actions, frames = _delta(before, after)
    if (
        actions <= 0
        or frames <= 0
        or report.actions_executed != actions
        or report.frames_executed != frames
    ):
        raise RedLivingDexSetupRecipeError("semantic route accounting differs")
    terminal_state_bytes = _save_state_bytes(
        arm.emulator,
        meter=meter,
        subject="semantic route terminal",
    )
    if hashlib.sha256(terminal_state_bytes).digest() == hashlib.sha256(
        origin_state_bytes
    ).digest():
        raise RedLivingDexSetupRecipeError(
            "semantic route reported arrival without changing emulator state"
        )
    fresh = _observe_arm(arm, meter=meter, subject="semantic route terminal")
    _require_fresh_at(fresh, recipe.terminal_boundary, "semantic route terminal")
    return fresh, _route_report_sha256(route_report, recipe), actions, frames


def _route_report_sha256(
    report: RouteExecutionReport,
    recipe: RedLivingDexSetupRouteRecipe,
) -> str:
    return canonical_sha256(
        {
            "acknowledged_steps": [
                {
                    "action": item.step.action,
                    "action_kind": item.step.action_kind.value,
                    "expected_at": list(item.step.expected_at),
                    "expected_map": item.step.expected_map,
                    "expected_mode": item.step.expected_mode,
                    "interruption_count": item.interruption_count,
                    "movement_requests": item.movement_requests,
                    "source_at": list(item.step.source_at),
                    "source_map": item.step.source_map,
                    "source_mode": item.step.source_mode,
                }
                for item in report.executed_steps
            ],
            "initial_route_plan_sha256": recipe.route_plan_sha256,
            "interruptions": len(report.interruptions),
            "movement_requests": report.movement_requests,
            "planner_binding_sha256": recipe.planner_binding_sha256,
            "replans": len(report.replans),
            "resource_renewals": len(report.resource_renewals),
            "schema": "pokemon.red.private-living-dex-authenticated-route-report.v2",
            "terminal_boundary_sha256": recipe.terminal_boundary.sha256,
            "wait_actions": report.wait_actions,
        }
    )


def _derived_envelope_bytes(
    source: bytes,
    *,
    source_state_bytes: bytes,
    state_bytes: bytes,
) -> bytes:
    source_envelope = parse_captured_progress(
        source,
        state_bytes=source_state_bytes,
    )
    envelope = CapturedProgressEnvelope(
        state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        checkpoint_id=source_envelope.checkpoint_id,
        checkpoint_label=source_envelope.checkpoint_label,
        checkpoints_completed=source_envelope.checkpoints_completed,
        checkpoints_total=source_envelope.checkpoints_total,
        verified_objective_ids=source_envelope.verified_objective_ids,
    )
    return json.dumps(envelope.to_dict(), ensure_ascii=True, sort_keys=True).encode("ascii") + b"\n"


def qualify_red_living_dex_validated_recipe_captures(
    plan: RedLivingDexSetupRecipePlan,
    captures: tuple[RedLivingDexValidatedSetupCapture, ...],
) -> tuple[LivingDexCaptureAttestation, ...]:
    """Join all validated captures and enforce actual family/location scopes."""

    if not isinstance(plan, RedLivingDexSetupRecipePlan):
        raise TypeError("validated capture qualification needs a recipe plan")
    plan.__post_init__()
    if (
        not isinstance(captures, tuple)
        or len(captures) != len(plan.recipes)
        or any(not isinstance(item, RedLivingDexValidatedSetupCapture) for item in captures)
    ):
        raise RedLivingDexSetupRecipeError("validated capture qualification census differs")
    for recipe, capture in zip(plan.recipes, captures, strict=True):
        capture.__post_init__()
        if (
            capture.recipe_sha256 != recipe.recipe_sha256
            or capture.execution_identity_sha256 != plan.execution_identity.identity_sha256
        ):
            raise RedLivingDexSetupRecipeError("validated capture is joined to another recipe")
    attestations = tuple(item.attestation for item in captures)
    for values, subject in (
        ((item.state_sha256 for item in attestations), "validated states"),
        ((item.envelope_sha256 for item in attestations), "validated envelopes"),
        ((item.observer_binding_sha256 for item in attestations), "validated observers"),
    ):
        _require_unique(values, subject)

    families_by_scope: dict[str, set[str]] = {}
    locations_by_scope: dict[str, str] = {}
    scopes_by_location: dict[str, str] = {}
    for slot, attestation in zip(
        plan.prospective_plan.slots,
        attestations,
        strict=True,
    ):
        families_by_scope.setdefault(slot.family_scope_id, set()).update(
            attestation.available_family_sha256s
        )
        prior_location = locations_by_scope.setdefault(
            slot.location_scope_id,
            attestation.location_sha256,
        )
        if prior_location != attestation.location_sha256:
            raise RedLivingDexSetupRecipeError(
                "validated location scope maps to multiple physical locations"
            )
        prior_scope = scopes_by_location.setdefault(
            attestation.location_sha256,
            slot.location_scope_id,
        )
        if prior_scope != slot.location_scope_id:
            raise RedLivingDexSetupRecipeError(
                "validated physical location is reused across logical scopes"
            )
    family_rows = tuple(families_by_scope.items())
    for index, (left_scope, left) in enumerate(family_rows):
        for right_scope, right in family_rows[index + 1 :]:
            if left_scope != right_scope and left & right:
                raise RedLivingDexSetupRecipeError(
                    "validated transformation families overlap logical scopes"
                )
    return attestations


def _validate_constructed_origin(
    recipe: RedLivingDexSetupSlotRecipe,
    origin: RedLivingDexConstructedOrigin,
) -> None:
    route = recipe.construction_route
    if (
        origin.root_consumption_sha256 != recipe.root_consumption_sha256
        or origin.consumed_root_state_sha256 != recipe.root_state_sha256
        or origin.consumed_root_envelope_sha256 != recipe.root_envelope_sha256
        or origin.construction_route_recipe_sha256
        != (None if route is None else route.recipe_sha256)
        or origin.construction_route_plan_sha256
        != (None if route is None else route.route_plan_sha256)
        or origin.construction_route_planner_binding_sha256
        != (None if route is None else route.planner_binding_sha256)
        or origin.construction_route_terminal_boundary_sha256
        != (None if route is None else route.terminal_boundary.sha256)
    ):
        raise RedLivingDexSetupRecipeError(
            "constructed origin differs from its authenticated root recipe"
        )
    _require_fresh_at(origin.fresh, recipe.origin_boundary, "constructed origin")


def _validate_registry_offer(
    recipe: RedLivingDexSetupProviderRecipe,
    fresh: FreshRedGoalObservation,
    observed: RedGoalContextProviderOffer,
) -> tuple[ExecutableGoalBinding, str, str, str, str]:
    if type(observed) is not RedGoalContextProviderOffer:
        raise RedLivingDexSetupRecipeError("registry returned an invalid provider offer")
    observed.__post_init__()
    spec = next(item for item in recipe.profile.providers if item.kind is recipe.goal_kind)
    if (
        observed.provider_type is not recipe.provider_type
        or observed.profile_sha256 != recipe.profile.profile_sha256
        or observed.provider_configuration_sha256 != spec.configuration_sha256
    ):
        raise RedLivingDexSetupRecipeError("registry provider differs from its frozen recipe")
    offer = observed.offer
    if (
        offer.kind is not recipe.goal_kind
        or offer.binding is None
        or offer.unavailable_reason is not None
    ):
        raise RedLivingDexSetupRecipeError("candidate provider did not return an available offer")
    binding = offer.binding
    binding.__post_init__()
    if not red_living_dex_binding_matches_family(
        binding.binding_ref,
        recipe.family,
        recipe.profile,
    ):
        raise RedLivingDexSetupRecipeError(
            "candidate provider family differs from its frozen recipe"
        )
    family_sha256 = recipe.family.family_sha256
    fresh_sha256 = red_living_dex_setup_fresh_observation_sha256(fresh)
    if fresh.observation_sha256 != fresh_sha256:
        raise RedLivingDexSetupRecipeError("candidate fresh observation digest differs")
    executable_sha256 = red_living_dex_setup_executable_binding_sha256(binding)
    offer_sha256 = canonical_sha256(
        {
            "executable_binding_sha256": executable_sha256,
            "fresh_observation_sha256": fresh_sha256,
            "goal_kind": offer.kind.value,
            "provider_contract_id": recipe.provider_contract_id,
            "provider_recipe_sha256": recipe.recipe_sha256,
            "schema": RED_LIVING_DEX_SETUP_PROVIDER_OFFER_WITNESS_SCHEMA,
        }
    )
    return binding, fresh_sha256, executable_sha256, offer_sha256, family_sha256


def _require_root_join(
    recipe: RedLivingDexSetupSlotRecipe,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    if (
        root.root_consumption_sha256 != recipe.root_consumption_sha256
        or root.state_sha256 != recipe.root_state_sha256
        or root.envelope_sha256 != recipe.root_envelope_sha256
    ):
        raise RedLivingDexSetupRecipeError(
            "authenticated setup root differs from its frozen recipe"
        )


def _require_recipe_join(
    slot: LivingDexProspectiveCaptureSlot,
    recipe: RedLivingDexSetupSlotRecipe,
) -> None:
    if (
        recipe.slot_sha256 != slot.slot_sha256
        or recipe.partition is not slot.partition
        or recipe.available_option_kinds != slot.available_option_kinds
    ):
        raise RedLivingDexSetupRecipeError("setup recipe differs from its prospective slot")


def _require_location_scope_join(
    slots: tuple[LivingDexProspectiveCaptureSlot, ...],
    recipes: tuple[RedLivingDexSetupSlotRecipe, ...],
) -> None:
    scope_to_location: dict[str, str] = {}
    location_to_scope: dict[str, str] = {}
    for slot, recipe in zip(slots, recipes, strict=True):
        location = recipe.location_sha256
        previous = scope_to_location.setdefault(slot.location_scope_id, location)
        if previous != location:
            raise RedLivingDexSetupRecipeError("recipe location scope maps to multiple origin maps")
        previous_scope = location_to_scope.setdefault(location, slot.location_scope_id)
        if previous_scope != slot.location_scope_id:
            raise RedLivingDexSetupRecipeError(
                "recipe origin map is reused across logical location scopes"
            )


def _require_family_scope_join(
    slots: tuple[LivingDexProspectiveCaptureSlot, ...],
    recipes: tuple[RedLivingDexSetupSlotRecipe, ...],
) -> None:
    families_by_scope: dict[str, set[str]] = {}
    for slot, recipe in zip(slots, recipes, strict=True):
        families_by_scope.setdefault(slot.family_scope_id, set()).update(
            provider.expected_family_sha256 for provider in recipe.providers
        )
    scope_rows = tuple(families_by_scope.items())
    for index, (left_scope, left_families) in enumerate(scope_rows):
        for right_scope, right_families in scope_rows[index + 1 :]:
            if left_scope != right_scope and left_families & right_families:
                raise RedLivingDexSetupRecipeError(
                    "recipe transformation families overlap logical scopes"
                )


def _location_sha256(boundary: RedRoutedSemanticBoundary) -> str:
    return canonical_sha256(
        {
            "location_ref": f"red.start-map.{boundary.map_id}",
            "schema": "pokemon.red.private-option-location-join.v1",
        }
    )


def _profile_terminal_matches(
    profile: RedGoalContextProfile,
    goal_kind: GoalKind,
    actual: RedRoutedSemanticBoundary,
) -> bool:
    spec = next(item for item in profile.providers if item.kind is goal_kind)
    parameters = spec.parameters
    if spec.mechanic in {
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
        RedGoalMechanic.MART_RESUPPLY,
        RedGoalMechanic.BOX_SWITCH,
    }:
        map_id = parameters.get("map_id")
        player_x = parameters.get("player_x")
        player_y = parameters.get("player_y")
        if any(type(item) is not int for item in (map_id, player_x, player_y)):  # noqa: E721
            raise RedLivingDexSetupRecipeError("provider profile terminal parameters differ")
        assert isinstance(map_id, int)
        assert isinstance(player_x, int)
        assert isinstance(player_y, int)
        # Profiles bind the physical stance.  The authenticated route retains
        # Red's explicit ``land`` mode, while historical synthetic fixtures
        # used ``None``; movement mode is not part of any of these provider
        # boundaries and must not make a real terminal impossible to encode.
        return actual.map_id == map_id and actual.at == (player_y, player_x)
    if spec.mechanic in {
        RedGoalMechanic.BALANCED_TEAM,
        RedGoalMechanic.DIGLETT_EVOLUTION,
        RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
        RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
    }:
        # The concrete profile runtime admits these mechanics only at the same
        # two tested Pokemon Center terminals.
        return actual.at == (3, 3) and actual.map_id in {
            int(MapId.CINNABAR_POKECENTER),
            int(MapId.VERMILION_POKECENTER),
        }
    # Story boundaries are determined by the live objective registry rather
    # than by a coordinate-bearing profile.  Availability is still proved by
    # the fresh offer during fork validation.
    return True


def _require_fresh(value: FreshRedGoalObservation) -> None:
    if not isinstance(value, FreshRedGoalObservation):
        raise TypeError("recipe validation needs a fresh Red observation")
    value.__post_init__()
    expected = red_living_dex_setup_fresh_observation_sha256(value)
    if value.observation_sha256 != expected:
        raise RedLivingDexSetupRecipeError("fresh Red observation digest differs")


def _require_fresh_at(
    value: FreshRedGoalObservation,
    boundary: RedRoutedSemanticBoundary,
    subject: str,
) -> None:
    _require_fresh(value)
    if not boundary.matches_traversal(value.traversal) or not (
        boundary.matches_goal_observation(value.observation)
    ):
        raise RedLivingDexSetupRecipeError(f"{subject} boundary differs")


def _checkpoint(
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexSetupProtectedEffectCheckpoint:
    value = meter.checkpoint()
    if not isinstance(value, RedLivingDexSetupProtectedEffectCheckpoint):
        raise RedLivingDexSetupRecipeError("setup effect checkpoint differs")
    return value


def _delta(
    before: RedLivingDexSetupProtectedEffectCheckpoint,
    after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> tuple[int, int]:
    try:
        return before.action_frame_delta(after)
    except RuntimeError as error:
        raise RedLivingDexSetupRecipeError(str(error)) from None


def _require_within_slot_budget(
    slot: LivingDexProspectiveCaptureSlot,
    actions: int,
    frames: int,
) -> None:
    if (
        actions > slot.setup.maximum_controller_actions
        or frames > slot.setup.maximum_emulator_frames
    ):
        raise RedLivingDexSetupRecipeError("same-root validation exceeded setup budget")


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexSetupRecipeError(f"{subject} digest differs")
    return value


def _require_option_kinds(value: object) -> None:
    if (
        not isinstance(value, tuple)
        or len(value) < 3
        or len(value) != len(set(value))
        or any(not isinstance(item, LivingDexOptionKind) for item in value)
    ):
        raise RedLivingDexSetupRecipeError("recipe option menu differs")


def _require_unique(values: Iterable[Hashable], subject: str) -> None:
    frozen = tuple(values)
    if len(frozen) != len(set(frozen)):
        raise RedLivingDexSetupRecipeError(f"{subject} are not unique")


def _encode_private_bytes(payload: bytes) -> str:
    if not isinstance(payload, bytes) or not payload:
        raise RedLivingDexSetupRecipeError("private setup payload is absent")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii")
    if "/" in encoded or "\\" in encoded:
        raise RedLivingDexSetupRecipeError("private setup payload encoding differs")
    return encoded


def _decode_private_bytes(
    value: object,
    *,
    subject: str,
    maximum_bytes: int,
) -> bytes:
    encoded = _string(value, subject)
    if len(encoded) > ((maximum_bytes + 2) // 3) * 4:
        raise RedLivingDexSetupRecipeError(f"{subject} exceeds its bound")
    try:
        payload = base64.b64decode(
            encoded.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeEncodeError):
        raise RedLivingDexSetupRecipeError(f"{subject} encoding differs") from None
    if not payload or len(payload) > maximum_bytes or _encode_private_bytes(payload) != encoded:
        raise RedLivingDexSetupRecipeError(f"{subject} encoding differs")
    return payload


def _exact_keys(
    document: Mapping[str, object],
    expected: set[str],
    subject: str,
) -> None:
    if set(document) != expected:
        raise RedLivingDexSetupRecipeError(f"{subject} fields differ")


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RedLivingDexSetupRecipeError(f"{subject} differs")
    return value


def _sequence(value: object, subject: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise RedLivingDexSetupRecipeError(f"{subject} differ")
    return tuple(value)


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexSetupRecipeError(f"{subject} differs")
    return value


def _optional_string(value: object, subject: str) -> str | None:
    if value is None:
        return None
    return _string(value, subject)


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexSetupRecipeError(f"{subject} differs")
    return value


def _boolean(value: object, subject: str) -> bool:
    if type(value) is not bool:  # noqa: E721
        raise RedLivingDexSetupRecipeError(f"{subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_SETUP_FORK_PROOF_SCHEMA",
    "RED_LIVING_DEX_SETUP_MINIMUM_SEMANTIC_FAMILIES",
    "RED_LIVING_DEX_SETUP_OFFER_COUNT",
    "RED_LIVING_DEX_SETUP_PHYSICAL_ORIGIN_COUNT",
    "RED_LIVING_DEX_SETUP_PROVIDER_RECIPE_SCHEMA",
    "RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA",
    "RED_LIVING_DEX_SETUP_RECIPE_ROUTE_SCHEMA",
    "RED_LIVING_DEX_SETUP_RECIPE_COUNT",
    "RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA",
    "RED_LIVING_DEX_SETUP_VALIDATED_CAPTURE_SCHEMA",
    "RedLivingDexAuthenticatedSetupRoot",
    "RedLivingDexConstructedOrigin",
    "RedLivingDexSetupEffectMeter",
    "RedLivingDexSetupForkRuntime",
    "RedLivingDexSetupForkRuntimeFactory",
    "RedLivingDexSetupForkProof",
    "RedLivingDexSetupProviderRecipe",
    "RedLivingDexSetupRecipeError",
    "RedLivingDexSetupRecipePlan",
    "RedLivingDexSetupStatePort",
    "RedLivingDexSetupRouteRecipe",
    "RedLivingDexSetupSlotRecipe",
    "RedLivingDexValidatedSetupCapture",
    "build_red_living_dex_setup_recipe_plan",
    "qualify_red_living_dex_validated_recipe_captures",
    "restore_red_living_dex_validated_setup_capture",
    "validate_red_living_dex_setup_recipe",
]
