"""Action-free inventory and deterministic freeze for authentic Red option menus.

The durable materializer accepts already-adapted scenarios but deliberately has no
authority to discover private captures.  This module is the read-only bridge: it
projects established Red goal bindings into the shared living-Pokedex menu,
requires byte-verified capture provenance, inventories every eligible scenario,
and deterministically selects the minimum 8-train/4-development plan without a
behavior draw, controller input, outcome, or model.

Selection uses only prospective menu, family, location, partition, and provenance
facts.  A coverage shortfall is terminal for the inventory; it is never repaired
by weakening the gate or looking at an outcome.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from math import ceil

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind,
    LivingDexOptionUnavailableReason,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfile
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedBoundLivingDexOption,
    RedLivingDexContextFacts,
    RedLivingDexOptionProspect,
    RedLivingDexOutcomeSnapshot,
    RedLivingDexScenarioBudgets,
    adapt_red_living_dex_options,
    bind_red_goal_option,
)
from pokemon_red_completion.red_living_dex_option_calibration import (
    MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES,
    MINIMUM_SETTLED_TRAIN_EXAMPLES,
)
from pokemon_red_completion.red_living_dex_option_materializer import (
    RedLivingDexMaterializationPlan,
    RedLivingDexMaterializationScenario,
    RedLivingDexMaterializationScenarioOrigin,
    bind_verified_red_living_dex_materialization_scenario,
    build_red_living_dex_materialization_plan,
)

RED_LIVING_DEX_ACTION_FREE_INVENTORY_SCHEMA = (
    "pokemon.red.living-dex-action-free-authentic-inventory.v1"
)

_GOAL_TO_OPTION_KIND: Mapping[GoalKind, LivingDexOptionKind] = {
    GoalKind.ADVANCE_STORY: LivingDexOptionKind.UNLOCK_ACCESS,
    GoalKind.ACQUIRE_SPECIES: LivingDexOptionKind.ACQUIRE,
    GoalKind.DEVELOP_TEAM: LivingDexOptionKind.DEVELOP,
    GoalKind.EVOLVE_SPECIES: LivingDexOptionKind.EVOLVE,
    GoalKind.RESUPPLY: LivingDexOptionKind.RESUPPLY,
    GoalKind.MANAGE_STORAGE: LivingDexOptionKind.MANAGE_STORAGE,
    GoalKind.EXPLORE: LivingDexOptionKind.EXPLORE,
}
_OPTION_TO_GOAL_KIND: Mapping[LivingDexOptionKind, GoalKind] = {
    option: goal for goal, option in _GOAL_TO_OPTION_KIND.items()
}
_UNAVAILABLE_REASON: Mapping[
    GoalUnavailableReason,
    LivingDexOptionUnavailableReason,
] = {
    GoalUnavailableReason.MISSING_CAPABILITY: (
        LivingDexOptionUnavailableReason.MISSING_CAPABILITY
    ),
    GoalUnavailableReason.NO_LEGAL_TARGET: (
        LivingDexOptionUnavailableReason.NO_LEGAL_TARGET
    ),
    GoalUnavailableReason.STORY_GATE_CLOSED: (
        LivingDexOptionUnavailableReason.STORY_GATE_CLOSED
    ),
    GoalUnavailableReason.TEMPORARILY_BLOCKED: (
        LivingDexOptionUnavailableReason.TEMPORARILY_BLOCKED
    ),
    GoalUnavailableReason.WORLD_STATE_UNKNOWN: (
        LivingDexOptionUnavailableReason.WORLD_STATE_UNKNOWN
    ),
}
_SATISFIED_FAMILY_TOKEN = "*"


class RedLivingDexActionFreeInventoryError(ValueError):
    """Authenticated Red captures cannot support the frozen calibration plan."""


@dataclass(frozen=True, slots=True)
class RedLivingDexInventoryObserverBinding:
    """Frozen observer descriptor that deliberately has no collection authority."""

    binding_sha256: str
    inventory_only: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.binding_sha256, str)
            or len(self.binding_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.binding_sha256)
        ):
            raise RedLivingDexActionFreeInventoryError(
                "inventory observer binding SHA-256 differs"
            )
        if self.inventory_only is not True:
            raise RedLivingDexActionFreeInventoryError(
                "inventory observer cannot receive execution authority"
            )

    def __call__(self) -> RedLivingDexOutcomeSnapshot:
        raise RedLivingDexActionFreeInventoryError(
            "inventory observer descriptor must be reconstructed before collection"
        )


@dataclass(frozen=True, slots=True)
class RedLivingDexActionFreeInventory:
    """All prospectively eligible verified scenarios from one bounded census."""

    scenarios: tuple[RedLivingDexMaterializationScenario, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenarios, tuple)
            or not self.scenarios
            or any(
                not isinstance(item, RedLivingDexMaterializationScenario)
                for item in self.scenarios
            )
        ):
            raise RedLivingDexActionFreeInventoryError(
                "action-free inventory needs verified Red scenarios"
            )
        identities = tuple(item.scenario_identity_sha256 for item in self.scenarios)
        if len(identities) != len(set(identities)):
            raise RedLivingDexActionFreeInventoryError(
                "action-free inventory repeats a scenario identity"
            )
        checkpoint_bindings = tuple(
            item.checkpoint_binding_sha256 for item in self.scenarios
        )
        if len(checkpoint_bindings) != len(set(checkpoint_bindings)):
            raise RedLivingDexActionFreeInventoryError(
                "action-free inventory repeats a physical capture"
            )
        for scenario in self.scenarios:
            if scenario.scenario_origin is not (
                RedLivingDexMaterializationScenarioOrigin.VERIFIED_REPEATABLE_CAPTURE
            ):
                raise RedLivingDexActionFreeInventoryError(
                    "action-free inventory contains synthetic provenance"
                )
            if not scenario.adapted.before.scenario_repeatable:
                raise RedLivingDexActionFreeInventoryError(
                    "action-free inventory contains a nonrepeatable scenario"
                )
            if any(option.consumed for option in scenario.adapted.ordered_options):
                raise RedLivingDexActionFreeInventoryError(
                    "action-free inventory contains a consumed option"
                )
            if not isinstance(
                scenario.observe_after,
                RedLivingDexInventoryObserverBinding,
            ):
                raise RedLivingDexActionFreeInventoryError(
                    "action-free inventory contains live observer authority"
                )

    def public_dict(self) -> dict[str, object]:
        partitions = Counter(item.partition for item in self.scenarios)
        return {
            "all_available_executors_authenticated": all(
                scenario.adapted.ordered_options[index].authenticated_executor
                for scenario in self.scenarios
                for index in scenario.adapted.menu.available_indices
            ),
            "available_width_counts": _integer_counter(
                Counter(
                    len(item.adapted.menu.available_indices)
                    for item in self.scenarios
                )
            ),
            "behavior_draws": 0,
            "complete_menu_count": len(self.scenarios),
            "controller_actions": 0,
            "emulator_frames_advanced": 0,
            "identity_fields_public": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "observer_descriptors_frozen": len(self.scenarios),
            "observer_execution_bindings": 0,
            "outcomes_observed": 0,
            "partition_counts": {
                "development": partitions["development"],
                "train": partitions["train"],
            },
            "root_claims": 0,
            "scenario_count": len(self.scenarios),
            "schema": RED_LIVING_DEX_ACTION_FREE_INVENTORY_SCHEMA,
            "verified_repeatable_capture_count": len(self.scenarios),
        }


def build_verified_red_living_dex_goal_scenario(
    capture: GoalManagerContextCapture,
    profile: RedGoalContextProfile,
    before: RedLivingDexOutcomeSnapshot,
    facts: RedLivingDexContextFacts,
    budgets: RedLivingDexScenarioBudgets,
    bindings: GoalBindingSet,
    *,
    partition: str,
    location_ref: str,
    checkpoint_attestation_sha256: str,
    observer_binding_sha256: str,
    observe_after: Callable[[], RedLivingDexOutcomeSnapshot],
) -> RedLivingDexMaterializationScenario:
    """Project one verified capture's complete goal menu without selecting an arm."""

    if not isinstance(capture, GoalManagerContextCapture):
        raise TypeError("authentic inventory needs a verified capture")
    if not isinstance(profile, RedGoalContextProfile):
        raise TypeError("authentic inventory needs a Red context profile")
    if not isinstance(before, RedLivingDexOutcomeSnapshot):
        raise TypeError("authentic inventory needs a Red before snapshot")
    if not isinstance(facts, RedLivingDexContextFacts):
        raise TypeError("authentic inventory needs Red context facts")
    if not isinstance(budgets, RedLivingDexScenarioBudgets):
        raise TypeError("authentic inventory needs frozen scenario budgets")
    if not isinstance(bindings, GoalBindingSet):
        raise TypeError("authentic inventory needs established Red goal bindings")
    if profile.profile_id != capture.capture_id:
        raise RedLivingDexActionFreeInventoryError(
            "capture and profile identities differ"
        )
    if not isinstance(location_ref, str) or not location_ref:
        raise RedLivingDexActionFreeInventoryError(
            "authentic inventory location reference differs"
        )

    options = tuple(
        _option_for_kind(
            kind,
            capture=capture,
            profile=profile,
            before=before,
            facts=facts,
            budgets=budgets,
            bindings=bindings,
            location_ref=location_ref,
        )
        for kind in LivingDexOptionKind
    )
    ordering_seed = canonical_sha256(
        {
            "capture_id": capture.capture_id,
            "envelope_sha256": capture.envelope_sha256,
            "profile_sha256": profile.profile_sha256,
            "purpose": "living-dex-action-free-menu-order",
            "schema": "pokemon.red.private-living-dex-menu-order.v1",
            "state_sha256": capture.state_sha256,
        }
    )
    adapted = adapt_red_living_dex_options(
        before,
        facts,
        budgets,
        options,
        ordering_seed_sha256=ordering_seed,
    )
    return bind_verified_red_living_dex_materialization_scenario(
        capture,
        adapted,
        partition=partition,
        observer_binding_sha256=observer_binding_sha256,
        checkpoint_attestation_sha256=checkpoint_attestation_sha256,
        observe_after=observe_after,
    )


def freeze_red_living_dex_action_free_inventory(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> tuple[RedLivingDexActionFreeInventory, RedLivingDexMaterializationPlan]:
    """Freeze the first deterministic exact 8+4 subset satisfying every gate."""

    if not isinstance(scenarios, Sequence):
        raise TypeError("action-free inventory scenarios must be a sequence")
    inventory = RedLivingDexActionFreeInventory(tuple(scenarios))
    train = tuple(
        sorted(
            (item for item in inventory.scenarios if item.partition == "train"),
            key=_scenario_key,
        )
    )
    development = tuple(
        sorted(
            (item for item in inventory.scenarios if item.partition == "development"),
            key=_scenario_key,
        )
    )
    if len(train) < MINIMUM_SETTLED_TRAIN_EXAMPLES:
        raise RedLivingDexActionFreeInventoryError(
            "action-free inventory lacks eight train scenarios"
        )
    if len(development) < MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES:
        raise RedLivingDexActionFreeInventoryError(
            "action-free inventory lacks four development scenarios"
        )

    for development_selection in combinations(
        development,
        MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES,
    ):
        development_families = _family_hashes(development_selection)
        development_locations = _location_hashes(development_selection)
        if len(development_families) < 4 or len(development_locations) < 4:
            continue
        eligible_train = tuple(
            item
            for item in train
            if not _family_hashes((item,)) & development_families
            and not _location_hashes((item,)) & development_locations
        )
        train_selection = _select_train(eligible_train)
        if train_selection is None:
            continue
        return inventory, build_red_living_dex_materialization_plan(
            (*train_selection, *development_selection)
        )
    raise RedLivingDexActionFreeInventoryError(
        "action-free inventory cannot satisfy the 8+4 kind, family, and location gate"
    )


def red_living_dex_goal_family_ref(
    binding: ExecutableGoalBinding,
    profile: RedGoalContextProfile,
) -> str:
    """Return a root-independent semantic family for one profile-bound skill."""

    if not isinstance(binding, ExecutableGoalBinding):
        raise TypeError("goal family needs an executable binding")
    if not isinstance(profile, RedGoalContextProfile):
        raise TypeError("goal family needs a Red context profile")
    specs = tuple(item for item in profile.providers if item.kind is binding.kind)
    if len(specs) != 1:
        raise RedLivingDexActionFreeInventoryError(
            "available goal binding lacks one profile mechanic"
        )
    spec = specs[0]
    suffix = (
        f":profile-{profile.profile_sha256}:config-{spec.configuration_sha256}"
    )
    if not binding.binding_ref.endswith(suffix):
        raise RedLivingDexActionFreeInventoryError(
            "goal binding does not match its authenticated profile"
        )
    semantic_ref = binding.binding_ref[: -len(suffix)]
    if not semantic_ref:
        raise RedLivingDexActionFreeInventoryError(
            "goal binding lacks a root-independent semantic family"
        )
    return "red.goal-family." + canonical_sha256(
        {
            "goal_kind": binding.kind.value,
            "mechanic": spec.mechanic.value,
            "schema": "pokemon.red.private-goal-transformation-family.v1",
            "semantic_binding_ref": semantic_ref,
        }
    )


def _option_for_kind(
    option_kind: LivingDexOptionKind,
    *,
    capture: GoalManagerContextCapture,
    profile: RedGoalContextProfile,
    before: RedLivingDexOutcomeSnapshot,
    facts: RedLivingDexContextFacts,
    budgets: RedLivingDexScenarioBudgets,
    bindings: GoalBindingSet,
    location_ref: str,
) -> RedBoundLivingDexOption:
    goal_kind = _OPTION_TO_GOAL_KIND.get(option_kind)
    binding = (
        None
        if goal_kind is None
        else next((item for item in bindings.bindings if item.kind is goal_kind), None)
    )
    if binding is not None:
        prospect = _prospect(
            option_kind,
            before=before,
            facts=facts,
            budgets=budgets,
            effort=binding.estimated_effort,
            risk=binding.estimated_risk,
            available=True,
        )
        return bind_red_goal_option(
            binding,
            prospect,
            family_ref=red_living_dex_goal_family_ref(binding, profile),
            location_ref=location_ref,
            resource_pool_ref=(
                "red.resource.capture-items"
                if option_kind is LivingDexOptionKind.ACQUIRE
                else None
            ),
        )

    reason = _unavailable_reason(goal_kind, bindings)
    prospect, resource_pool = _unavailable_prospect(
        option_kind,
        reason,
        before=before,
        facts=facts,
        budgets=budgets,
    )

    def forbidden_execution() -> object:
        raise RedLivingDexActionFreeInventoryError(
            "masked action-free inventory option received execution authority"
        )

    return RedBoundLivingDexOption(
        binding_ref=(
            "red.goal-unavailable."
            f"{capture.capture_id}.{option_kind.value}.{reason.value}"
        ),
        family_ref=f"red.goal-family.unavailable.{option_kind.value}",
        location_ref=location_ref,
        resource_pool_ref=resource_pool,
        prospect=prospect,
        execute=forbidden_execution,
        verify_success=lambda _before, _after: False,
    )


def _prospect(
    kind: LivingDexOptionKind,
    *,
    before: RedLivingDexOutcomeSnapshot,
    facts: RedLivingDexContextFacts,
    budgets: RedLivingDexScenarioBudgets,
    effort: float,
    risk: float,
    available: bool,
    blocker: LivingDexOptionUnavailableReason | None = None,
    required_consumable_units: int | None = None,
    net_storage_slots: int | None = None,
) -> RedLivingDexOptionProspect:
    maximum_completion = max(
        1,
        facts.incomplete_dependency_frontier,
    )
    completion = (
        1
        if available
        and facts.incomplete_dependency_frontier > 0
        and kind in {LivingDexOptionKind.ACQUIRE, LivingDexOptionKind.EVOLVE}
        else 0
    )
    consumables = (
        1
        if required_consumable_units is None
        and available
        and kind is LivingDexOptionKind.ACQUIRE
        else 0
        if required_consumable_units is None
        else required_consumable_units
    )
    storage = (
        1
        if net_storage_slots is None and kind is LivingDexOptionKind.ACQUIRE
        else 0
        if net_storage_slots is None
        else net_storage_slots
    )
    return RedLivingDexOptionProspect(
        kind=kind,
        completion_units=completion,
        maximum_completion_units=maximum_completion,
        immediate_dependency_unlocks=0,
        travel_action_estimate=0,
        execution_action_estimate=(
            max(1, ceil(float(effort) * budgets.maximum_controller_actions))
            if available
            else 0
        ),
        required_consumable_units=consumables,
        net_storage_slots=storage,
        party_risk=float(risk) if available else 0.0,
        irreversible_constraints_exposed=0,
        irreversible_constraint_count=before.irreversible_constraints_remaining,
        prerequisite_confidence=1.0 if available else 0.0,
        mechanical_blocker=blocker,
    )


def _unavailable_prospect(
    kind: LivingDexOptionKind,
    reason: LivingDexOptionUnavailableReason,
    *,
    before: RedLivingDexOutcomeSnapshot,
    facts: RedLivingDexContextFacts,
    budgets: RedLivingDexScenarioBudgets,
) -> tuple[RedLivingDexOptionProspect, str | None]:
    resource_pool: str | None = None
    required = 0
    storage = 1 if kind is LivingDexOptionKind.ACQUIRE else 0
    blocker: LivingDexOptionUnavailableReason | None = reason
    if reason is LivingDexOptionUnavailableReason.MISSING_RESOURCE:
        resource_pool = f"red.resource.goal-{kind.value}"
        required = before.resource_units_for(resource_pool) + 1
        blocker = None
    elif reason is LivingDexOptionUnavailableReason.STORAGE_BLOCKED:
        storage = before.usable_storage_headroom + 1
        blocker = None
    return (
        _prospect(
            kind,
            before=before,
            facts=facts,
            budgets=budgets,
            effort=0.0,
            risk=0.0,
            available=False,
            blocker=blocker,
            required_consumable_units=required,
            net_storage_slots=storage,
        ),
        resource_pool,
    )


def _unavailable_reason(
    goal_kind: GoalKind | None,
    bindings: GoalBindingSet,
) -> LivingDexOptionUnavailableReason:
    if goal_kind is None:
        return LivingDexOptionUnavailableReason.MISSING_CAPABILITY
    opportunity = next(
        (item for item in bindings.opportunities if item.kind is goal_kind),
        None,
    )
    if opportunity is None:
        raise RedLivingDexActionFreeInventoryError(
            "complete goal menu omits a portable goal kind"
        )
    if opportunity.availability is GoalAvailability.AVAILABLE:
        raise RedLivingDexActionFreeInventoryError(
            "available goal opportunity lacks its executable binding"
        )
    reason = opportunity.unavailable_reason
    if not isinstance(reason, GoalUnavailableReason):
        raise RedLivingDexActionFreeInventoryError(
            "masked goal opportunity lacks an unavailable reason"
        )
    if reason is GoalUnavailableReason.MISSING_RESOURCE:
        return LivingDexOptionUnavailableReason.MISSING_RESOURCE
    if reason is GoalUnavailableReason.STORAGE_BLOCKED:
        return LivingDexOptionUnavailableReason.STORAGE_BLOCKED
    if reason not in _UNAVAILABLE_REASON:
        raise RedLivingDexActionFreeInventoryError(
            "goal unavailability cannot be projected safely"
        )
    return _UNAVAILABLE_REASON[reason]


def _select_train(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> tuple[RedLivingDexMaterializationScenario, ...] | None:
    if len(scenarios) < MINIMUM_SETTLED_TRAIN_EXAMPLES:
        return None
    ordered = tuple(sorted(scenarios, key=_scenario_key))
    # (count, offered kinds, up-to-two families or satisfied sentinel) -> indices.
    states: dict[
        tuple[int, frozenset[LivingDexOptionKind], tuple[str, ...]],
        tuple[int, ...],
    ] = {(0, frozenset(), ()): ()}
    for index, scenario in enumerate(ordered):
        additions: dict[
            tuple[int, frozenset[LivingDexOptionKind], tuple[str, ...]],
            tuple[int, ...],
        ] = {}
        scenario_kinds = _option_kinds((scenario,))
        scenario_families = _family_hashes((scenario,))
        for (count, kinds, family_token), selected in states.items():
            if count >= MINIMUM_SETTLED_TRAIN_EXAMPLES:
                continue
            new_key = (
                count + 1,
                kinds | scenario_kinds,
                _merge_family_token(family_token, scenario_families),
            )
            candidate = (*selected, index)
            previous = additions.get(new_key, states.get(new_key))
            if previous is None or candidate < previous:
                additions[new_key] = candidate
        states.update(additions)
    eligible = tuple(
        indices
        for (count, kinds, families), indices in states.items()
        if count == MINIMUM_SETTLED_TRAIN_EXAMPLES
        and len(kinds) >= 4
        and families == (_SATISFIED_FAMILY_TOKEN,)
    )
    if not eligible:
        return None
    selected_indices = min(eligible)
    return tuple(ordered[index] for index in selected_indices)


def _merge_family_token(
    token: tuple[str, ...],
    values: frozenset[str],
) -> tuple[str, ...]:
    if token == (_SATISFIED_FAMILY_TOKEN,):
        return token
    merged = set(token) | set(values)
    if len(merged) >= 3:
        return (_SATISFIED_FAMILY_TOKEN,)
    return tuple(sorted(merged))


def _scenario_key(scenario: RedLivingDexMaterializationScenario) -> tuple[str, str]:
    return scenario.scenario_identity_sha256, scenario.materialization_identity_sha256


def _option_kinds(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> frozenset[LivingDexOptionKind]:
    return frozenset(
        scenario.adapted.menu.candidates[index].features.kind
        for scenario in scenarios
        for index in scenario.adapted.menu.available_indices
    )


def _family_hashes(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> frozenset[str]:
    return frozenset(
        canonical_sha256(
            {
                "family_ref": scenario.adapted.ordered_options[index].family_ref,
                "schema": "pokemon.red.private-transformation-family-join.v1",
            }
        )
        for scenario in scenarios
        for index in scenario.adapted.menu.available_indices
    )


def _location_hashes(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> frozenset[str]:
    return frozenset(
        canonical_sha256(
            {
                "location_ref": scenario.adapted.ordered_options[index].location_ref,
                "schema": "pokemon.red.private-option-location-join.v1",
            }
        )
        for scenario in scenarios
        for index in scenario.adapted.menu.available_indices
    )


def _integer_counter(counts: Counter[int]) -> dict[str, int]:
    return {str(value): counts[value] for value in sorted(counts)}


__all__ = [
    "RED_LIVING_DEX_ACTION_FREE_INVENTORY_SCHEMA",
    "RedLivingDexActionFreeInventory",
    "RedLivingDexActionFreeInventoryError",
    "RedLivingDexInventoryObserverBinding",
    "build_verified_red_living_dex_goal_scenario",
    "freeze_red_living_dex_action_free_inventory",
    "red_living_dex_goal_family_ref",
]
