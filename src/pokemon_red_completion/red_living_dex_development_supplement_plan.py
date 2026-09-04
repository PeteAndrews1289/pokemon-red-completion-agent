"""Private Red binding for one title-neutral development supplement.

The shared planner selects identity-bearing but outcome-blind capabilities.
This adapter binds those selections back to exact Red roots, contexts, and
setup recipes.  It is a development-only plan: it cannot contain train rows,
model scores, behavior choices, outcomes, claims, or controller authority.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations, product

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementCapability,
    LivingDexDevelopmentSupplementError,
    LivingDexDevelopmentSupplementPlan,
    LivingDexDevelopmentSupplementPolicy,
    select_living_dex_development_supplement,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    RedLivingDexDevelopmentSupplyInventory,
    build_red_living_dex_development_supplement_capabilities,
)

RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA = (
    "pokemon.red.private-living-dex-development-supplement-plan.v1"
)
RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS = (
    "frozen_before_claim_controller_input_model_prediction_or_outcome"
)
RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID = (
    "red-living-dex-development-supplement-plan-v1"
)
RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND = (
    "red-living-dex-development-supplement-plan-v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedLivingDexDevelopmentSupplementPlanError(ValueError):
    """A Red supplement does not exactly bind its title-neutral selection."""


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementCapacity:
    """Aggregate-only feasibility census for the measured Red supplement."""

    eligible_capabilities: int
    eligible_lineages: int
    eligible_physical_roots: int
    eligible_families: int
    eligible_locations: int
    candidate_root_sets: int
    candidate_scenario_combinations: int
    feasible_supplements: int
    option_kind_root_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        counts = (
            self.eligible_capabilities,
            self.eligible_lineages,
            self.eligible_physical_roots,
            self.eligible_families,
            self.eligible_locations,
            self.candidate_root_sets,
            self.candidate_scenario_combinations,
            self.feasible_supplements,
        )
        if any(type(value) is not int or value < 0 for value in counts):  # noqa: E721
            raise RedLivingDexDevelopmentSupplementPlanError("supplement capacity counts differ")
        expected_kinds = tuple(item.value for item in RED_DIRECT_CAUSAL_OPTION_KINDS)
        if (
            not isinstance(self.option_kind_root_counts, tuple)
            or tuple(item[0] for item in self.option_kind_root_counts) != expected_kinds
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or type(item[1]) is not int  # noqa: E721
                or item[1] < 0
                for item in self.option_kind_root_counts
            )
        ):
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement capacity option counts differ"
            )
        if self.feasible_supplements > self.candidate_scenario_combinations:
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement capacity feasibility differs"
            )

    @property
    def selection_ready(self) -> bool:
        return self.feasible_supplements > 0

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_root_sets": self.candidate_root_sets,
            "candidate_scenario_combinations": self.candidate_scenario_combinations,
            "controller_actions": 0,
            "eligible_capabilities": self.eligible_capabilities,
            "eligible_families": self.eligible_families,
            "eligible_lineages": self.eligible_lineages,
            "eligible_locations": self.eligible_locations,
            "eligible_physical_roots": self.eligible_physical_roots,
            "feasible_supplements": self.feasible_supplements,
            "model_fits": 0,
            "model_predictions": 0,
            "option_kind_root_counts": dict(self.option_kind_root_counts),
            "outcomes_opened": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schema": "pokemon.red.living-dex-development-supplement-capacity.v1",
            "selection_ready": self.selection_ready,
            "status": (
                "supplement_capacity_ready"
                if self.selection_ready
                else "supplement_capacity_insufficient"
            ),
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementBindings:
    """Exact inputs to one action-free supplement freeze."""

    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str
    goal_registry_sha256: str
    route_registry_sha256: str
    context_catalog_sha256: str
    context_plan_sha256: str
    runtime_identity_sha256: str
    supply_audit_evidence_sha256: str
    model_sha256: str
    model_record_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _COMMIT.fullmatch(self.source_commit) is None:
            raise RedLivingDexDevelopmentSupplementPlanError("supplement source commit differs")
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.rom_sha256, "ROM"),
            (self.goal_registry_sha256, "goal registry"),
            (self.route_registry_sha256, "route registry"),
            (self.context_catalog_sha256, "context catalog"),
            (self.context_plan_sha256, "context plan"),
            (self.runtime_identity_sha256, "runtime identity"),
            (self.supply_audit_evidence_sha256, "supply audit evidence"),
            (self.model_sha256, "model"),
            (self.model_record_sha256, "model record"),
        ):
            _require_sha256(value, subject)

    def private_dict(self) -> dict[str, str]:
        return {
            "context_catalog_sha256": self.context_catalog_sha256,
            "context_plan_sha256": self.context_plan_sha256,
            "goal_registry_sha256": self.goal_registry_sha256,
            "model_record_sha256": self.model_record_sha256,
            "model_sha256": self.model_sha256,
            "rom_sha256": self.rom_sha256,
            "route_registry_sha256": self.route_registry_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "supply_audit_evidence_sha256": (self.supply_audit_evidence_sha256),
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementFrozenScenario:
    """One selected shared capability joined to one executable Red recipe."""

    ordinal: int
    assignment: LivingDexDevelopmentSupplementCapability
    capability: RedLivingDexCausalRootCapability
    context_identity_sha256: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:  # noqa: E721
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement assignment ordinal differs"
            )
        if not isinstance(
            self.assignment,
            LivingDexDevelopmentSupplementCapability,
        ):
            raise TypeError("supplement frozen scenario needs its assignment")
        if not isinstance(self.capability, RedLivingDexCausalRootCapability):
            raise TypeError("supplement frozen scenario needs its Red capability")
        self.assignment.__post_init__()
        self.capability.__post_init__()
        _require_sha256(self.context_identity_sha256, "context identity")
        projected = build_red_living_dex_development_supplement_capabilities((self.capability,))
        if len(projected) != 1 or projected[0] != self.assignment:
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement assignment does not join its Red capability"
            )

    def private_dict(self) -> dict[str, object]:
        root = self.capability.root.root
        recipe = self.capability.recipe
        return {
            **self.assignment.private_dict(),
            "context_identity_sha256": self.context_identity_sha256,
            "ordinal": self.ordinal,
            "partition": "development",
            "recipe": recipe.private_dict(),
            "recipe_sha256": recipe.recipe_sha256,
            "root_consumption_sha256": root.root_consumption_sha256,
            "root_envelope_sha256": root.envelope_sha256,
            "root_state_sha256": root.state_sha256,
            "template_ordinal": self.capability.template_ordinal,
            "template_sha256": self.capability.slot.slot_sha256,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementPrivatePlan:
    """One immutable three-root Red development supplement."""

    bindings: RedLivingDexDevelopmentSupplementBindings
    supplement: LivingDexDevelopmentSupplementPlan
    assignments: tuple[RedLivingDexDevelopmentSupplementFrozenScenario, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.bindings,
            RedLivingDexDevelopmentSupplementBindings,
        ):
            raise TypeError("supplement private plan needs its bindings")
        if not isinstance(self.supplement, LivingDexDevelopmentSupplementPlan):
            raise TypeError("supplement private plan needs its shared plan")
        self.bindings.__post_init__()
        self.supplement.__post_init__()
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != len(self.supplement.assignments)
            or any(
                not isinstance(
                    item,
                    RedLivingDexDevelopmentSupplementFrozenScenario,
                )
                for item in self.assignments
            )
        ):
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement private assignments differ"
            )
        for ordinal, (expected, frozen) in enumerate(
            zip(self.supplement.assignments, self.assignments, strict=True)
        ):
            frozen.__post_init__()
            if frozen.ordinal != ordinal or frozen.assignment != expected:
                raise RedLivingDexDevelopmentSupplementPlanError(
                    "supplement private assignment order differs"
                )

    @property
    def private_plan_sha256(self) -> str:
        return canonical_sha256(self.payload_dict())

    def payload_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "behavior_commitments": 0,
            **self.bindings.private_dict(),
            "collection_authorized": False,
            "controller_actions": 0,
            "development_outcomes_opened": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_observed": 0,
            "provider_executions": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA,
            "status": RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS,
            "supplement": self.supplement.private_dict(),
            "supplement_plan_sha256": self.supplement.plan_sha256,
            "supplement_policy_sha256": self.supplement.policy.policy_sha256,
            "teacher_queries": 0,
            "training_targets": 0,
            "unselected_action_targets": 0,
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self.payload_dict(),
            "private_plan_sha256": self.private_plan_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self.supplement.public_dict(),
            "collection_authorized": False,
            "model_sha256": self.bindings.model_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "schema": ("pokemon.red.living-dex-development-supplement-freeze-result.v1"),
            "status": "authenticated_action_free_development_supplement_frozen",
            "training_targets": 0,
        }


def freeze_red_living_dex_development_supplement_plan(
    capabilities: Sequence[RedLivingDexCausalRootCapability],
    *,
    supply: RedLivingDexDevelopmentSupplyInventory,
    context_identities: Mapping[str, str],
    bindings: RedLivingDexDevelopmentSupplementBindings,
) -> RedLivingDexDevelopmentSupplementPrivatePlan:
    """Select and bind only the measured, outcome-blind Red supply gap."""

    if isinstance(capabilities, (str, bytes)) or not isinstance(
        capabilities,
        Sequence,
    ):
        raise TypeError("supplement freeze needs a capability sequence")
    if not isinstance(supply, RedLivingDexDevelopmentSupplyInventory):
        raise TypeError("supplement freeze needs its authenticated supply")
    if not isinstance(context_identities, Mapping):
        raise TypeError("supplement freeze needs context identities")
    if not isinstance(bindings, RedLivingDexDevelopmentSupplementBindings):
        raise TypeError("supplement freeze needs its bindings")
    supply.__post_init__()
    bindings.__post_init__()
    result = supply.result
    if (
        result.supply_ready
        or result.minimum_new_roots_to_freeze != 3
        or result.available_development_roots != 2
        or result.development_root_shortfall != 2
        or result.setup_censor_allowance != 1
        or result.missing_option_kinds != ("manage_storage",)
        or result.model_sha256 != bindings.model_sha256
        or result.model_record_sha256 != bindings.model_record_sha256
    ):
        raise RedLivingDexDevelopmentSupplementPlanError(
            "supplement freeze does not match the exact measured gap"
        )
    policy = _supplement_policy(supply)
    eligible_red = _eligible_red_capabilities(capabilities, supply=supply)
    historical_lineages = {item.lineage_sha256 for item in supply.historical_roots}
    historical_physical = {item.physical_root_sha256 for item in supply.historical_roots}
    shared = build_red_living_dex_development_supplement_capabilities(tuple(eligible_red))
    supplement = select_living_dex_development_supplement(
        shared,
        policy=policy,
        excluded_lineages=frozenset(supply.train_lineages | historical_lineages),
        excluded_physical_roots=frozenset(historical_physical),
    )
    red_by_scenario: dict[str, RedLivingDexCausalRootCapability] = {}
    for capability in eligible_red:
        projected = build_red_living_dex_development_supplement_capabilities((capability,))[0]
        if projected.scenario_sha256 in red_by_scenario:
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement freeze repeats a Red scenario"
            )
        red_by_scenario[projected.scenario_sha256] = capability
    frozen: list[RedLivingDexDevelopmentSupplementFrozenScenario] = []
    used_contexts: set[str] = set()
    for ordinal, assignment in enumerate(supplement.assignments):
        try:
            capability = red_by_scenario[assignment.scenario_sha256]
            context_identity = context_identities[capability.root.root.root_consumption_sha256]
        except (KeyError, TypeError):
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement freeze cannot join its Red context"
            ) from None
        _require_sha256(context_identity, "context identity")
        if context_identity in used_contexts:
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement freeze repeats a Red context"
            )
        used_contexts.add(context_identity)
        frozen.append(
            RedLivingDexDevelopmentSupplementFrozenScenario(
                ordinal=ordinal,
                assignment=assignment,
                capability=capability,
                context_identity_sha256=context_identity,
            )
        )
    return RedLivingDexDevelopmentSupplementPrivatePlan(
        bindings=bindings,
        supplement=supplement,
        assignments=tuple(frozen),
    )


def audit_red_living_dex_development_supplement_capacity(
    capabilities: Sequence[RedLivingDexCausalRootCapability],
    *,
    supply: RedLivingDexDevelopmentSupplyInventory,
) -> RedLivingDexDevelopmentSupplementCapacity:
    """Measure why the fixed supplement can or cannot be selected."""

    if isinstance(capabilities, (str, bytes)) or not isinstance(capabilities, Sequence):
        raise TypeError("supplement capacity needs a capability sequence")
    if not isinstance(supply, RedLivingDexDevelopmentSupplyInventory):
        raise TypeError("supplement capacity needs its authenticated supply")
    supply.__post_init__()
    policy = _supplement_policy(supply)
    eligible_red = _eligible_red_capabilities(capabilities, supply=supply)
    shared = build_red_living_dex_development_supplement_capabilities(eligible_red)
    by_root: dict[str, list[LivingDexDevelopmentSupplementCapability]] = {}
    for item in shared:
        by_root.setdefault(item.physical_root_sha256, []).append(item)
    root_groups = tuple(
        tuple(sorted(by_root[root], key=lambda item: item.scenario_sha256))
        for root in sorted(by_root)
    )
    candidate_root_sets = 0
    candidate_scenario_combinations = 0
    feasible_supplements = 0
    for groups in combinations(root_groups, policy.new_roots):
        candidate_root_sets += 1
        for candidate_tuple in product(*groups):
            candidate_scenario_combinations += 1
            ordered = tuple(sorted(candidate_tuple, key=lambda item: item.scenario_sha256))
            try:
                LivingDexDevelopmentSupplementPlan(policy, ordered)
            except LivingDexDevelopmentSupplementError:
                continue
            feasible_supplements += 1
    return RedLivingDexDevelopmentSupplementCapacity(
        eligible_capabilities=len(shared),
        eligible_lineages=len({item.lineage_sha256 for item in shared}),
        eligible_physical_roots=len(by_root),
        eligible_families=len({item.family_scope_id for item in shared}),
        eligible_locations=len({item.location_scope_id for item in shared}),
        candidate_root_sets=candidate_root_sets,
        candidate_scenario_combinations=candidate_scenario_combinations,
        feasible_supplements=feasible_supplements,
        option_kind_root_counts=tuple(
            (
                kind.value,
                len(
                    {
                        item.physical_root_sha256
                        for item in shared
                        if kind in item.available_option_kinds
                    }
                ),
            )
            for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
        ),
    )


def _supplement_policy(
    supply: RedLivingDexDevelopmentSupplyInventory,
) -> LivingDexDevelopmentSupplementPolicy:
    result = supply.result
    if (
        result.supply_ready
        or result.minimum_new_roots_to_freeze != 3
        or result.available_development_roots != 2
        or result.development_root_shortfall != 2
        or result.setup_censor_allowance != 1
        or result.missing_option_kinds != ("manage_storage",)
    ):
        raise RedLivingDexDevelopmentSupplementPlanError(
            "supplement capacity does not match the exact measured gap"
        )
    held_kinds = tuple(
        kind
        for kind in RED_DIRECT_CAUSAL_OPTION_KINDS
        if kind.value in result.available_option_kinds
    )
    return LivingDexDevelopmentSupplementPolicy(
        new_roots=result.minimum_new_roots_to_freeze,
        minimum_surviving_roots=(
            result.minimum_new_roots_to_freeze - result.setup_censor_allowance
        ),
        minimum_new_families=result.minimum_new_roots_to_freeze,
        minimum_new_locations=result.minimum_new_roots_to_freeze,
        held_root_count=result.available_development_roots,
        required_total_roots=result.required_development_roots,
        held_option_kinds=held_kinds,
        required_option_kinds=RED_DIRECT_CAUSAL_OPTION_KINDS,
    )


def _eligible_red_capabilities(
    capabilities: Sequence[RedLivingDexCausalRootCapability],
    *,
    supply: RedLivingDexDevelopmentSupplyInventory,
) -> tuple[RedLivingDexCausalRootCapability, ...]:
    historical_lineages = {item.lineage_sha256 for item in supply.historical_roots}
    historical_physical = {item.physical_root_sha256 for item in supply.historical_roots}
    historical_states = {
        (item.state_sha256, item.envelope_sha256) for item in supply.historical_roots
    }
    eligible: list[RedLivingDexCausalRootCapability] = []
    for capability in capabilities:
        if not isinstance(capability, RedLivingDexCausalRootCapability):
            raise TypeError("supplement capacity capability differs")
        capability.__post_init__()
        root = capability.root
        lineage = root.independence_lineage_sha256
        state = (root.root.state_sha256, root.root.envelope_sha256)
        if (
            lineage is not None
            and lineage not in supply.train_lineages
            and lineage not in historical_lineages
            and root.root.physical_root_sha256 not in historical_physical
            and state not in supply.train_states
            and state not in historical_states
        ):
            eligible.append(capability)
    return tuple(eligible)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexDevelopmentSupplementPlanError(f"supplement {subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID",
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND",
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA",
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS",
    "RedLivingDexDevelopmentSupplementBindings",
    "RedLivingDexDevelopmentSupplementCapacity",
    "RedLivingDexDevelopmentSupplementFrozenScenario",
    "RedLivingDexDevelopmentSupplementPlanError",
    "RedLivingDexDevelopmentSupplementPrivatePlan",
    "audit_red_living_dex_development_supplement_capacity",
    "freeze_red_living_dex_development_supplement_plan",
]
