"""ROM-free prospective Red curriculum for living-Pokedex option learning.

The shared capture contract defines what a useful lesson must prove.  This
module supplies Red's first concrete fifteen-slot schedule and audits whether
the existing semantic skills can actually instantiate it.  It deliberately
does not open a ROM, name a private state, plan a route, press a button, issue
a behavior draw, or manufacture a learner target.

The audit keeps three layers separate:

* the generic routed-goal composition seam is now implemented and published;
* the durable setup-binding contract and whole-slot runner are implemented;
* the calibration pilot still needs concrete private Red route/terminal
  bindings materialized against that runner;
* the full living-Pokedex mission additionally needs a repeatable semantic
  trade executor, even though trade is not required to satisfy the first
  four-kind pilot gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
    LivingDexCaptureSetupBoundary,
    LivingDexProspectiveCapturePlan,
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic
from pokemon_red_completion.red_goal_manager import RedStoryGoalBindingProvider
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedEncounterSourceDevelopmentGoalProvider,
    RedMartResupplyGoalProvider,
    RedObservedGoalSkillProvider,
    RedProgressGoalProvider,
    RedRouteGoalProvider,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    RedFreshGoalDestinationBinder,
    RedSemanticTransportRoute,
    build_red_routed_semantic_goal_composer,
)
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticGoalComposer,
)

RED_LIVING_DEX_CAPTURE_PLAN_SCHEMA = "pokemon.red.living-dex-prospective-capture-plan.v1"
RED_LIVING_DEX_CAPTURE_FEASIBILITY_SCHEMA = (
    "pokemon.red.living-dex-prospective-capture-feasibility.v2"
)
RED_LIVING_DEX_SETUP_REQUEST_SCHEMA = "pokemon.red.private-living-dex-semantic-setup-request.v1"
RED_LIVING_DEX_TERMINAL_PREDICATE_SCHEMA = (
    "pokemon.red.private-living-dex-semantic-terminal-predicate.v1"
)
RED_LIVING_DEX_OBSERVER_CONTRACT_SHA256 = canonical_sha256(
    {
        "capture_before_behavior_draw": True,
        "complete_menu_required": True,
        "fresh_collection_observation_required": True,
        "learner_effects": 0,
        "schema": "pokemon.red.private-living-dex-capture-observer-contract.v1",
    }
)
RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS = 100_000
RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES = 60_000_000
RED_ROUTED_SEMANTIC_GOAL_CAPABILITY = "routed-semantic-goal-composition"
RED_ACTION_FREE_SETUP_BINDING_MATERIALIZER_CAPABILITY = "action-free-red-setup-binding-materializer"
RED_PRIVATE_SETUP_SOURCE_ADAPTER_CAPABILITY = "private-red-setup-source-adapter"
RED_CONCRETE_ROUTED_SETUP_BINDINGS_CAPABILITY = "concrete-red-routed-setup-bindings"
RED_DURABLE_SETUP_RUNNER_CAPABILITY = "durable-red-setup-runner"
RED_SAME_ROOT_SETUP_RECIPE_CAPABILITY = "same-root-red-setup-recipe-validation"
RED_DURABLE_SETUP_RECIPE_CAMPAIGN_CAPABILITY = "durable-red-setup-recipe-campaign"
RED_PURPOSE_BUILT_SETUP_RECIPES_CAPABILITY = "purpose-built-red-setup-recipes"

RED_ROUTED_SEMANTIC_COMPONENTS = (
    RoutedSemanticGoalComposer,
    RedSemanticTransportRoute,
    RedFreshGoalDestinationBinder,
    build_red_routed_semantic_goal_composer,
)

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


class RedLivingDexCapturePlanError(ValueError):
    """A Red prospective plan overstates its semantic feasibility."""


class RedLivingDexExecutorStatus(StrEnum):
    """Whether Red implements a local provider contract for one portable kind."""

    IMPLEMENTED_LOCAL_CONTRACT = "implemented_local_contract"
    MISSING = "missing"


_OPTION_TO_GOAL_KIND = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}

_OPTION_TO_EXECUTOR_TYPES: dict[
    LivingDexOptionKind,
    tuple[type[object], ...],
] = {
    LivingDexOptionKind.ACQUIRE: (RedAreaSurveyGoalProvider,),
    # The profile-bound Diglett evolution seam builds an independently
    # observed skill provider.  ``RedProgressGoalProvider`` is used for the
    # ordinary development quantum, not for the evolution offer.
    LivingDexOptionKind.EVOLVE: (RedObservedGoalSkillProvider,),
    LivingDexOptionKind.DEVELOP: (
        RedEncounterSourceDevelopmentGoalProvider,
        RedProgressGoalProvider,
        RedObservedGoalSkillProvider,
    ),
    LivingDexOptionKind.MANAGE_STORAGE: (RedBoxSwitchGoalProvider,),
    LivingDexOptionKind.RESUPPLY: (RedMartResupplyGoalProvider,),
    LivingDexOptionKind.UNLOCK_ACCESS: (RedStoryGoalBindingProvider,),
    LivingDexOptionKind.EXPLORE: (
        RedEncounterDiscoveryGoalProvider,
        RedRouteGoalProvider,
    ),
}


def _executor_contract_id(executor_type: type[object]) -> str:
    return f"{executor_type.__module__}.{executor_type.__qualname__}"


def _runtime_contract_id(component: object) -> str:
    module = getattr(component, "__module__", None)
    qualname = getattr(component, "__qualname__", None)
    if (
        not callable(component)
        or not isinstance(module, str)
        or not module
        or not isinstance(qualname, str)
        or not qualname
    ):
        raise RedLivingDexCapturePlanError("Red routed semantic component provenance differs")
    return f"{module}.{qualname}"


def red_living_dex_setup_runtime_contract_ids() -> tuple[str, ...]:
    """Return published setup contracts without creating an import cycle.

    The setup campaign imports this module's frozen plan and capabilities.  A
    lazy import lets the feasibility audit credit the now-published runner only
    after both modules are fully initialized.
    """

    from pokemon_red_completion.red_living_dex_setup_campaign import (
        RedLivingDexSetupBindingPlan,
        RedLivingDexSetupOptionBinding,
        RedLivingDexSetupSlotBinding,
        build_red_living_dex_setup_binding_plan,
        run_red_living_dex_setup_campaign,
    )

    return tuple(
        _runtime_contract_id(item)
        for item in (
            RedLivingDexSetupOptionBinding,
            RedLivingDexSetupSlotBinding,
            RedLivingDexSetupBindingPlan,
            build_red_living_dex_setup_binding_plan,
            run_red_living_dex_setup_campaign,
        )
    )


def red_living_dex_setup_materialization_runtime_contract_ids() -> tuple[str, ...]:
    """Return published action-free materialization contracts lazily."""

    from pokemon_red_completion.red_living_dex_setup_materialization import (
        RedLivingDexSetupBindingMaterialization,
        RedLivingDexSetupPrivateSourceAttestation,
        materialize_red_living_dex_setup_bindings,
    )

    return tuple(
        _runtime_contract_id(item)
        for item in (
            RedLivingDexSetupPrivateSourceAttestation,
            RedLivingDexSetupBindingMaterialization,
            materialize_red_living_dex_setup_bindings,
        )
    )


def red_living_dex_setup_source_runtime_contract_ids() -> tuple[str, ...]:
    """Return the concrete action-free private source contract lazily."""

    from pokemon_red_completion.red_living_dex_setup_source import (
        RedLivingDexSetupCatalogSource,
        RedLivingDexSetupProviderWitness,
        RedLivingDexSetupRouteWitness,
        RedLivingDexSetupSlotWitness,
        build_red_living_dex_setup_source_payload,
    )

    return tuple(
        _runtime_contract_id(item)
        for item in (
            RedLivingDexSetupSlotWitness,
            RedLivingDexSetupRouteWitness,
            RedLivingDexSetupProviderWitness,
            build_red_living_dex_setup_source_payload,
            RedLivingDexSetupCatalogSource,
        )
    )


def red_living_dex_setup_recipe_runtime_contract_ids() -> tuple[str, ...]:
    """Return the successor same-root recipe and durability contracts lazily."""

    from pokemon_red_completion.red_living_dex_setup_recipe import (
        RedLivingDexSetupProviderRecipe,
        RedLivingDexSetupRecipePlan,
        RedLivingDexSetupRouteRecipe,
        RedLivingDexSetupSlotRecipe,
        RedLivingDexValidatedSetupCapture,
        build_red_living_dex_setup_recipe_plan,
        validate_red_living_dex_setup_recipe,
    )
    from pokemon_red_completion.red_living_dex_setup_recipe_campaign import (
        RedLivingDexSetupRecipeRun,
        run_red_living_dex_setup_recipe_campaign,
    )

    return tuple(
        _runtime_contract_id(item)
        for item in (
            RedLivingDexSetupRouteRecipe,
            RedLivingDexSetupProviderRecipe,
            RedLivingDexSetupSlotRecipe,
            RedLivingDexSetupRecipePlan,
            RedLivingDexValidatedSetupCapture,
            build_red_living_dex_setup_recipe_plan,
            validate_red_living_dex_setup_recipe,
            RedLivingDexSetupRecipeRun,
            run_red_living_dex_setup_recipe_campaign,
        )
    )


@dataclass(frozen=True, slots=True)
class RedLivingDexExecutorCapability:
    """ROM-free evidence for one existing or missing Red semantic skill."""

    option_kind: LivingDexOptionKind
    status: RedLivingDexExecutorStatus
    goal_kind: GoalKind | None
    mechanics: tuple[RedGoalMechanic, ...]
    boundary_scopes: tuple[str, ...]
    executor_types: tuple[type[object], ...]
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.option_kind, LivingDexOptionKind) or not isinstance(
            self.status, RedLivingDexExecutorStatus
        ):
            raise RedLivingDexCapturePlanError("Red capture executor capability identity differs")
        if self.status is RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT:
            expected_goal = _OPTION_TO_GOAL_KIND.get(self.option_kind)
            if self.goal_kind is not expected_goal or expected_goal is None:
                raise RedLivingDexCapturePlanError("Red capture executor goal mapping differs")
            if (
                not self.mechanics
                or len(self.mechanics) != len(set(self.mechanics))
                or any(not isinstance(item, RedGoalMechanic) for item in self.mechanics)
            ):
                raise RedLivingDexCapturePlanError("Red capture executor mechanics differ")
            if (
                not self.boundary_scopes
                or len(self.boundary_scopes) != len(set(self.boundary_scopes))
                or any(_SAFE_ID.fullmatch(item) is None for item in self.boundary_scopes)
            ):
                raise RedLivingDexCapturePlanError("Red capture executor boundary scopes differ")
            expected_types = _OPTION_TO_EXECUTOR_TYPES.get(self.option_kind)
            if (
                self.executor_types != expected_types
                or not self.executor_types
                or len(self.executor_types) != len(set(self.executor_types))
                or any(
                    not isinstance(item, type) or not callable(getattr(item, "offer", None))
                    for item in self.executor_types
                )
                or self.missing_reason is not None
            ):
                raise RedLivingDexCapturePlanError("Red capture executor provenance differs")
        elif not (
            self.option_kind is LivingDexOptionKind.TRADE
            and self.goal_kind is None
            and not self.mechanics
            and not self.boundary_scopes
            and not self.executor_types
            and self.missing_reason == "missing-repeatable-semantic-trade-executor"
        ):
            raise RedLivingDexCapturePlanError("Red missing executor record differs")

    @property
    def capability_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "boundary_scope_count": len(self.boundary_scopes),
            "executor_contract_ids": [_executor_contract_id(item) for item in self.executor_types],
            "goal_kind": None if self.goal_kind is None else self.goal_kind.value,
            "mechanics": [item.value for item in self.mechanics],
            "missing_reason": self.missing_reason,
            "option_kind": self.option_kind.value,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "raw_controller_sequence": False,
            "status": self.status.value,
            "teacher_route": False,
        }


RED_LIVING_DEX_EXECUTOR_CAPABILITIES = (
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.ACQUIRE,
        RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
        GoalKind.ACQUIRE_SPECIES,
        (RedGoalMechanic.WILD_CORRIDOR_CAPTURE,),
        ("wild-corridor",),
        (RedAreaSurveyGoalProvider,),
    ),
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.EVOLVE,
        RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
        GoalKind.EVOLVE_SPECIES,
        (
            RedGoalMechanic.DIGLETT_EVOLUTION,
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        ),
        ("pokemon-center",),
        (RedObservedGoalSkillProvider,),
    ),
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.TRADE,
        RedLivingDexExecutorStatus.MISSING,
        None,
        (),
        (),
        (),
        "missing-repeatable-semantic-trade-executor",
    ),
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.DEVELOP,
        RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
        GoalKind.DEVELOP_TEAM,
        (
            RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
            RedGoalMechanic.BALANCED_TEAM,
            RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
        ),
        ("pokemon-center", "wild-corridor"),
        (
            RedEncounterSourceDevelopmentGoalProvider,
            RedProgressGoalProvider,
            RedObservedGoalSkillProvider,
        ),
    ),
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.MANAGE_STORAGE,
        RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
        GoalKind.MANAGE_STORAGE,
        (RedGoalMechanic.BOX_SWITCH,),
        ("storage-pc",),
        (RedBoxSwitchGoalProvider,),
    ),
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.RESUPPLY,
        RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
        GoalKind.RESUPPLY,
        (RedGoalMechanic.MART_RESUPPLY,),
        ("mart-clerk",),
        (RedMartResupplyGoalProvider,),
    ),
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.UNLOCK_ACCESS,
        RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
        GoalKind.ADVANCE_STORY,
        (RedGoalMechanic.MIDGAME_STORY,),
        ("story-objective",),
        (RedStoryGoalBindingProvider,),
    ),
    RedLivingDexExecutorCapability(
        LivingDexOptionKind.EXPLORE,
        RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
        GoalKind.EXPLORE,
        (RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,),
        ("route-start", "wild-corridor"),
        (RedEncounterDiscoveryGoalProvider, RedRouteGoalProvider),
    ),
)


@dataclass(frozen=True, slots=True)
class _RedCaptureSlotTemplate:
    purpose_id: str
    partition: LivingDexCapturePartition
    kinds: tuple[LivingDexOptionKind, ...]
    family_scope_id: str
    location_scope_id: str

    def __post_init__(self) -> None:
        for value in (
            self.purpose_id,
            self.family_scope_id,
            self.location_scope_id,
        ):
            if _SAFE_ID.fullmatch(value) is None:
                raise RedLivingDexCapturePlanError("Red capture slot template identity differs")
        if not isinstance(self.partition, LivingDexCapturePartition):
            raise RedLivingDexCapturePlanError("Red capture slot template partition differs")
        if (
            not isinstance(self.kinds, tuple)
            or len(self.kinds) < 3
            or len(self.kinds) != len(set(self.kinds))
            or any(not isinstance(item, LivingDexOptionKind) for item in self.kinds)
        ):
            raise RedLivingDexCapturePlanError("Red capture slot template menu differs")


_TRAIN_MENUS = (
    (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.EXPLORE,
    ),
    (
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.MANAGE_STORAGE,
    ),
    (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.UNLOCK_ACCESS,
    ),
    (
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.UNLOCK_ACCESS,
    ),
    (
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.EXPLORE,
    ),
    (
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.UNLOCK_ACCESS,
        LivingDexOptionKind.EXPLORE,
    ),
    (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.EXPLORE,
    ),
    (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY,
    ),
    (
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.UNLOCK_ACCESS,
    ),
    (
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.EXPLORE,
    ),
)

_DEVELOPMENT_MENUS = (
    (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY,
    ),
    (
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.UNLOCK_ACCESS,
    ),
    (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.UNLOCK_ACCESS,
        LivingDexOptionKind.EXPLORE,
    ),
    (
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.RESUPPLY,
    ),
    (
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.EXPLORE,
    ),
)


def _templates() -> tuple[_RedCaptureSlotTemplate, ...]:
    train = tuple(
        _RedCaptureSlotTemplate(
            purpose_id=f"train-semantic-menu-{index:02d}",
            partition=LivingDexCapturePartition.TRAIN,
            kinds=kinds,
            family_scope_id=(
                "train-family-scope-a"
                if index < 4
                else "train-family-scope-b"
                if index < 7
                else "train-family-scope-c"
            ),
            location_scope_id=f"train-location-scope-{index // 2}",
        )
        for index, kinds in enumerate(_TRAIN_MENUS)
    )
    development = tuple(
        _RedCaptureSlotTemplate(
            purpose_id=f"development-semantic-menu-{index:02d}",
            partition=LivingDexCapturePartition.DEVELOPMENT,
            kinds=kinds,
            family_scope_id=f"development-family-scope-{index}",
            location_scope_id=f"development-location-scope-{index}",
        )
        for index, kinds in enumerate(_DEVELOPMENT_MENUS)
    )
    return (*train, *development)


def _setup_boundary(template: _RedCaptureSlotTemplate) -> LivingDexCaptureSetupBoundary:
    setup_document = {
        "capture_before_behavior_draw": True,
        "deterministic_setup": True,
        "family_scope_id": template.family_scope_id,
        "learner_labels": 0,
        "location_scope_id": template.location_scope_id,
        "maximum_controller_actions": RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS,
        "maximum_emulator_frames": RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES,
        "planned_option_kinds": [item.value for item in template.kinds],
        "purpose_id": template.purpose_id,
        "schema": RED_LIVING_DEX_SETUP_REQUEST_SCHEMA,
    }
    terminal_document = {
        "all_available_executors_authenticated": True,
        "behavior_draws": 0,
        "complete_distinct_kind_menu": [item.value for item in template.kinds],
        "input_ready": True,
        "learner_labels": 0,
        "schema": RED_LIVING_DEX_TERMINAL_PREDICATE_SCHEMA,
    }
    return LivingDexCaptureSetupBoundary(
        setup_plan_sha256=canonical_sha256(setup_document),
        terminal_predicate_sha256=canonical_sha256(terminal_document),
        observer_contract_sha256=RED_LIVING_DEX_OBSERVER_CONTRACT_SHA256,
        maximum_controller_actions=RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS,
        maximum_emulator_frames=RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES,
    )


def build_red_living_dex_prospective_capture_plan() -> LivingDexProspectiveCapturePlan:
    """Freeze the exact abstract 10+5 Red schedule without opening title input."""

    slots = tuple(
        LivingDexProspectiveCaptureSlot(
            slot_id=f"red-capture-{template.purpose_id}",
            partition=template.partition,
            available_option_kinds=template.kinds,
            family_scope_id=template.family_scope_id,
            location_scope_id=template.location_scope_id,
            root_slot_id=f"red-root-{template.purpose_id}",
            setup=_setup_boundary(template),
        )
        for template in _templates()
    )
    return LivingDexProspectiveCapturePlan(slots)


@dataclass(frozen=True, slots=True)
class RedLivingDexCapturePlanFeasibility:
    """Honest distinction between a valid schedule and runnable Red setup."""

    plan: LivingDexProspectiveCapturePlan
    capabilities: tuple[RedLivingDexExecutorCapability, ...]
    implemented_runtime_capabilities: tuple[str, ...]
    unresolved_runtime_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, LivingDexProspectiveCapturePlan):
            raise TypeError("Red capture feasibility needs a prospective plan")
        self.plan.__post_init__()
        if (
            not isinstance(self.capabilities, tuple)
            or tuple(item.option_kind for item in self.capabilities) != tuple(LivingDexOptionKind)
            or len({item.capability_sha256 for item in self.capabilities}) != len(self.capabilities)
        ):
            raise RedLivingDexCapturePlanError("Red capture capability audit is incomplete")
        for item in self.capabilities:
            item.__post_init__()
        for name in (
            "implemented_runtime_capabilities",
            "unresolved_runtime_capabilities",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, tuple)
                or len(value) != len(set(value))
                or any(_SAFE_ID.fullmatch(item) is None for item in value)
            ):
                raise RedLivingDexCapturePlanError(f"Red capture {name.replace('_', ' ')} differ")
        if set(self.implemented_runtime_capabilities).intersection(
            self.unresolved_runtime_capabilities
        ):
            raise RedLivingDexCapturePlanError("Red capture runtime capability status overlaps")
        capability_by_kind = {item.option_kind: item for item in self.capabilities}
        unavailable_scheduled = {
            kind
            for kind in self.scheduled_option_kinds
            if capability_by_kind[kind].status
            is not RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT
        }
        if unavailable_scheduled:
            raise RedLivingDexCapturePlanError(
                "Red capture plan schedules a missing local executor"
            )
        routed_slots = self.routed_slot_count
        expected_implemented = (
            RED_ROUTED_SEMANTIC_GOAL_CAPABILITY,
            RED_DURABLE_SETUP_RUNNER_CAPABILITY,
            RED_ACTION_FREE_SETUP_BINDING_MATERIALIZER_CAPABILITY,
            RED_PRIVATE_SETUP_SOURCE_ADAPTER_CAPABILITY,
            RED_SAME_ROOT_SETUP_RECIPE_CAPABILITY,
            RED_DURABLE_SETUP_RECIPE_CAMPAIGN_CAPABILITY,
        )
        if routed_slots and self.implemented_runtime_capabilities != expected_implemented:
            raise RedLivingDexCapturePlanError(
                "Red capture plan hides a published runtime capability"
            )
        if not routed_slots and self.implemented_runtime_capabilities != (
            RED_DURABLE_SETUP_RUNNER_CAPABILITY,
            RED_ACTION_FREE_SETUP_BINDING_MATERIALIZER_CAPABILITY,
            RED_PRIVATE_SETUP_SOURCE_ADAPTER_CAPABILITY,
            RED_SAME_ROOT_SETUP_RECIPE_CAPABILITY,
            RED_DURABLE_SETUP_RECIPE_CAMPAIGN_CAPABILITY,
        ):
            raise RedLivingDexCapturePlanError("Red capture plan runtime capability census differs")
        if self.unresolved_runtime_capabilities != (RED_PURPOSE_BUILT_SETUP_RECIPES_CAPABILITY,):
            raise RedLivingDexCapturePlanError(
                "Red capture plan hides concrete setup execution blockers"
            )
        tuple(_runtime_contract_id(item) for item in RED_ROUTED_SEMANTIC_COMPONENTS)
        red_living_dex_setup_runtime_contract_ids()
        red_living_dex_setup_materialization_runtime_contract_ids()
        red_living_dex_setup_source_runtime_contract_ids()
        red_living_dex_setup_recipe_runtime_contract_ids()

    @property
    def scheduled_option_kinds(self) -> tuple[LivingDexOptionKind, ...]:
        present = {kind for slot in self.plan.slots for kind in slot.available_option_kinds}
        return tuple(kind for kind in LivingDexOptionKind if kind in present)

    @property
    def mission_missing_option_kinds(self) -> tuple[LivingDexOptionKind, ...]:
        return tuple(
            item.option_kind
            for item in self.capabilities
            if item.status is RedLivingDexExecutorStatus.MISSING
        )

    @property
    def locally_composable_slot_count(self) -> int:
        capabilities = {item.option_kind: item for item in self.capabilities}
        result = 0
        for slot in self.plan.slots:
            common: set[str] | None = None
            for kind in slot.available_option_kinds:
                scopes = set(capabilities[kind].boundary_scopes)
                common = scopes if common is None else common & scopes
            if common:
                result += 1
        return result

    @property
    def routed_slot_count(self) -> int:
        return len(self.plan.slots) - self.locally_composable_slot_count

    @property
    def pilot_plan_contract_satisfied(self) -> bool:
        return True

    @property
    def pilot_execution_ready(self) -> bool:
        return not self.unresolved_runtime_capabilities

    @property
    def full_mission_ready(self) -> bool:
        return self.pilot_execution_ready and not self.mission_missing_option_kinds

    @property
    def qualification_sha256(self) -> str:
        return canonical_sha256(self._public_document())

    def _public_document(self) -> dict[str, object]:
        return {
            "capabilities": [item.public_dict() for item in self.capabilities],
            "full_mission_ready": self.full_mission_ready,
            "learner_effects": 0,
            "locally_composable_slot_count": self.locally_composable_slot_count,
            "implemented_runtime_capabilities": list(self.implemented_runtime_capabilities),
            "implemented_runtime_contract_ids": [
                *(_runtime_contract_id(item) for item in RED_ROUTED_SEMANTIC_COMPONENTS),
                *red_living_dex_setup_runtime_contract_ids(),
                *red_living_dex_setup_materialization_runtime_contract_ids(),
                *red_living_dex_setup_source_runtime_contract_ids(),
                *red_living_dex_setup_recipe_runtime_contract_ids(),
            ],
            "mission_missing_option_kinds": [
                item.value for item in self.mission_missing_option_kinds
            ],
            "pilot_execution_ready": self.pilot_execution_ready,
            "pilot_plan_contract_satisfied": self.pilot_plan_contract_satisfied,
            "plan": self.plan.public_dict(),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "rom_accesses": 0,
            "routed_slot_count": self.routed_slot_count,
            "scheduled_option_kinds": [item.value for item in self.scheduled_option_kinds],
            "schema": RED_LIVING_DEX_CAPTURE_FEASIBILITY_SCHEMA,
            "setup_controller_actions": 0,
            "setup_emulator_frames": 0,
            "unresolved_runtime_capabilities": list(self.unresolved_runtime_capabilities),
        }

    def public_dict(self) -> dict[str, object]:
        document = self._public_document()
        document["qualification_sha256"] = self.qualification_sha256
        return document


def qualify_red_living_dex_prospective_capture_plan() -> RedLivingDexCapturePlanFeasibility:
    """Return the frozen schedule and its current, deliberately non-green audit."""

    return RedLivingDexCapturePlanFeasibility(
        plan=build_red_living_dex_prospective_capture_plan(),
        capabilities=RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
        implemented_runtime_capabilities=(
            RED_ROUTED_SEMANTIC_GOAL_CAPABILITY,
            RED_DURABLE_SETUP_RUNNER_CAPABILITY,
            RED_ACTION_FREE_SETUP_BINDING_MATERIALIZER_CAPABILITY,
            RED_PRIVATE_SETUP_SOURCE_ADAPTER_CAPABILITY,
            RED_SAME_ROOT_SETUP_RECIPE_CAPABILITY,
            RED_DURABLE_SETUP_RECIPE_CAMPAIGN_CAPABILITY,
        ),
        unresolved_runtime_capabilities=(RED_PURPOSE_BUILT_SETUP_RECIPES_CAPABILITY,),
    )


__all__ = [
    "RED_LIVING_DEX_CAPTURE_FEASIBILITY_SCHEMA",
    "RED_LIVING_DEX_CAPTURE_PLAN_SCHEMA",
    "RED_ACTION_FREE_SETUP_BINDING_MATERIALIZER_CAPABILITY",
    "RED_CONCRETE_ROUTED_SETUP_BINDINGS_CAPABILITY",
    "RED_DURABLE_SETUP_RUNNER_CAPABILITY",
    "RED_DURABLE_SETUP_RECIPE_CAMPAIGN_CAPABILITY",
    "RED_LIVING_DEX_EXECUTOR_CAPABILITIES",
    "RED_LIVING_DEX_OBSERVER_CONTRACT_SHA256",
    "RED_PRIVATE_SETUP_SOURCE_ADAPTER_CAPABILITY",
    "RED_PURPOSE_BUILT_SETUP_RECIPES_CAPABILITY",
    "RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS",
    "RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES",
    "RED_ROUTED_SEMANTIC_GOAL_CAPABILITY",
    "RED_ROUTED_SEMANTIC_COMPONENTS",
    "RED_SAME_ROOT_SETUP_RECIPE_CAPABILITY",
    "RedLivingDexCapturePlanError",
    "RedLivingDexCapturePlanFeasibility",
    "RedLivingDexExecutorCapability",
    "RedLivingDexExecutorStatus",
    "build_red_living_dex_prospective_capture_plan",
    "qualify_red_living_dex_prospective_capture_plan",
    "red_living_dex_setup_materialization_runtime_contract_ids",
    "red_living_dex_setup_runtime_contract_ids",
    "red_living_dex_setup_recipe_runtime_contract_ids",
    "red_living_dex_setup_source_runtime_contract_ids",
]
