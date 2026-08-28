"""Freeze authentic Red provider recipes without moving the game.

The same-root campaign deliberately cannot invent its own roots, routes, or
provider families.  This module joins those independent pieces before any
root is claimed: exact authenticated capture bytes, one coherent action-free
traversal observation per slot, cartridge-derived encounter corridors, the
semantic router, and the published execution identity.

It only creates prospective recipes.  It does not load a state, execute a
route or provider, query a teacher, draw a behavior choice, observe an
outcome, or fit a model.  The later setup campaign must still restore every
root, execute each transport in an isolated fork, and obtain the real provider
offer at the fresh terminal.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.blaine import BLASTOISE_SPECIES_ID
from pokemon_red_completion.claim_first_admission import ClaimFirstRootPair
from pokemon_red_completion.collection import CollectionLocation, CollectionObservation
from pokemon_red_completion.global_router import MacroGraph, advance_macro_state
from pokemon_red_completion.goal_manager_state import headroom_satisfaction
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionContext,
    LivingDexOptionKind,
)
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_context_profile import RED_GOAL_MANAGER_CONFIG
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
    RedLevelEvolutionTarget,
    RedPartyDevelopmentTarget,
    RedProviderFamilyTarget,
    RedResupplyTarget,
    RedStorageTarget,
    RedStoryTarget,
    audit_red_living_dex_provider_curriculum,
    red_living_dex_provider_family_target,
)
from pokemon_red_completion.red_living_dex_provider_recipe import (
    RedLivingDexProviderRecipeSeed,
    build_red_living_dex_provider_recipe_seed,
    red_living_dex_story_boundary,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupProviderRecipe,
    RedLivingDexSetupRecipePlan,
    RedLivingDexSetupRouteRecipe,
    RedLivingDexSetupSlotRecipe,
    build_red_living_dex_setup_recipe_plan,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
    RedLivingDexSetupProtectedEffectCheckpoint,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
    derive_red_living_dex_wild_corridor,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    RedRoutedSemanticBoundary,
)
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

RED_LIVING_DEX_PROVIDER_PLAN_FREEZE_SCHEMA = (
    "pokemon.red.private-living-dex-provider-plan-freeze.v1"
)
RED_LIVING_DEX_PROVIDER_PLANNER_BINDING_SCHEMA = (
    "pokemon.red.private-living-dex-provider-planner-binding.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexProviderPlanError(RuntimeError):
    """The action-free roots cannot form the frozen authentic curriculum."""


class RedLivingDexProviderRouteWorld(Protocol):
    """Small read-only router surface used by the prospective freezer."""

    @property
    def macro_graph(self) -> MacroGraph: ...

    @property
    def rom(self) -> bytes: ...

    def plan_feasible_to_map(
        self,
        start: TraversalSnapshot,
        goal_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
    ) -> RoutePlan: ...


@dataclass(frozen=True, slots=True)
class RedLivingDexProviderRootFacts:
    """Location-coherent, action-free prerequisites that transport cannot add."""

    map_id: int
    at: tuple[int, int]
    input_ready: bool
    battle_state: int
    party: PartyObservation
    collection: CollectionObservation
    available_story_objective_ids: frozenset[str]
    capture_item_count: int
    recovery_item_count: int
    immediate_capture_slots: int
    bag_item_ids: frozenset[int]
    player_money: int
    resources_satisfaction: float
    world_knowledge_satisfaction: float

    def __post_init__(self) -> None:
        if type(self.map_id) is not int or self.map_id < 0:  # noqa: E721
            raise RedLivingDexProviderPlanError("provider root facts map differs")
        if (
            not isinstance(self.at, tuple)
            or len(self.at) != 2
            or any(type(value) is not int or value < 0 for value in self.at)  # noqa: E721
        ):
            raise RedLivingDexProviderPlanError("provider root facts coordinate differs")
        if (
            self.input_ready is not True
            or type(self.battle_state) is not int  # noqa: E721
            or self.battle_state != 0
        ):
            raise RedLivingDexProviderPlanError(
                "provider root facts are not at ready overworld control"
            )
        if not isinstance(self.party, PartyObservation):
            raise TypeError("provider root facts need a party observation")
        if not isinstance(self.collection, CollectionObservation):
            raise TypeError("provider root facts need a collection observation")
        self.party.__post_init__()
        self.collection.__post_init__()
        party_census = Counter(
            (
                red_species_ref(red_internal_species_number(member.species_id)),
                member.level,
            )
            for member in self.party.members
        )
        collection_party_census = Counter(
            (specimen.species_ref, specimen.level)
            for specimen in self.collection.specimens
            if specimen.location is CollectionLocation.PARTY
        )
        if (
            self.collection.party_size != self.party.size
            or party_census != collection_party_census
            or not {specimen.species_ref for specimen in self.collection.specimens}.issubset(
                self.collection.owned_species
            )
        ):
            raise RedLivingDexProviderPlanError("provider root party and collection facts disagree")
        if not isinstance(self.available_story_objective_ids, frozenset) or any(
            not isinstance(item, str) or not item for item in self.available_story_objective_ids
        ):
            raise RedLivingDexProviderPlanError("provider root story objective facts differ")
        for numeric_value, subject in (
            (self.capture_item_count, "capture items"),
            (self.recovery_item_count, "recovery items"),
            (self.immediate_capture_slots, "capture slots"),
            (self.player_money, "money"),
        ):
            if type(numeric_value) is not int or numeric_value < 0:  # noqa: E721
                raise RedLivingDexProviderPlanError(f"provider root {subject} differ")
        if not isinstance(self.bag_item_ids, frozenset) or any(
            type(item) is not int or not 0 <= item <= 0xFF for item in self.bag_item_ids
        ):
            raise RedLivingDexProviderPlanError("provider root bag identity differs")
        for satisfaction, subject in (
            (self.resources_satisfaction, "resources"),
            (self.world_knowledge_satisfaction, "world knowledge"),
        ):
            if not isinstance(satisfaction, float) or not 0.0 <= satisfaction <= 1.0:
                raise RedLivingDexProviderPlanError(f"provider root {subject} satisfaction differs")


@dataclass(frozen=True, slots=True)
class RedLivingDexActionFreeRootObservation:
    """One exact root joined to a coherent zero-effect traversal read."""

    root: RedLivingDexAuthenticatedSetupRoot
    traversal: TraversalSnapshot
    facts: RedLivingDexProviderRootFacts
    observed_state_sha256: str
    root_claim_available: bool
    option_context: LivingDexOptionContext | None = None
    independence_lineage_sha256: str | None = None
    prospective_independence_authenticated: bool = False

    def __post_init__(self) -> None:
        _validate_root_observation(
            self.root,
            self.traversal,
            self.facts,
            self.observed_state_sha256,
        )
        if self.root_claim_available is not True:
            raise RedLivingDexProviderPlanError("provider-plan root is already consumed")
        if self.option_context is not None:
            if not isinstance(self.option_context, LivingDexOptionContext):
                raise TypeError("provider-plan option context differs")
            self.option_context.__post_init__()
        if self.independence_lineage_sha256 is not None:
            _require_sha256(
                self.independence_lineage_sha256,
                "provider-plan independence lineage",
            )
        if type(self.prospective_independence_authenticated) is not bool:  # noqa: E721
            raise TypeError("provider-plan independence authentication differs")
        if (
            self.prospective_independence_authenticated
            and self.independence_lineage_sha256 is None
        ):
            raise RedLivingDexProviderPlanError(
                "authenticated provider root lacks an episode lineage"
            )


@dataclass(frozen=True, slots=True)
class RedLivingDexClaimedRootObservation:
    """One coherent Red read joined to an already-durable pair claim."""

    root: RedLivingDexAuthenticatedSetupRoot
    traversal: TraversalSnapshot
    facts: RedLivingDexProviderRootFacts
    observed_state_sha256: str
    pair_claim: ClaimFirstRootPair

    def __post_init__(self) -> None:
        _validate_root_observation(
            self.root,
            self.traversal,
            self.facts,
            self.observed_state_sha256,
        )
        if not isinstance(self.pair_claim, ClaimFirstRootPair):
            raise TypeError("claimed provider observation needs a pair claim")
        self.pair_claim.__post_init__()
        if (
            self.pair_claim.logical_root_sha256
            != self.root.root_consumption_sha256
            or self.pair_claim.physical_root_sha256
            != self.root.physical_root_sha256
        ):
            raise RedLivingDexProviderPlanError(
                "claimed provider observation belongs to another root pair"
            )

    @property
    def pair_claim_sha256(self) -> str:
        return self.pair_claim.claim_sha256


def _validate_root_observation(
    root: RedLivingDexAuthenticatedSetupRoot,
    traversal: TraversalSnapshot,
    facts: RedLivingDexProviderRootFacts,
    observed_state_sha256: str,
) -> None:
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("provider-plan observation needs an authenticated root")
    root.__post_init__()
    if not isinstance(traversal, TraversalSnapshot):
        raise TypeError("provider-plan observation needs a traversal snapshot")
    if not traversal.ready or traversal.interruption is not None or traversal.mode != "land":
        raise RedLivingDexProviderPlanError("provider-plan root is not at ready land control")
    if not isinstance(facts, RedLivingDexProviderRootFacts):
        raise TypeError("provider-plan observation needs Red root facts")
    facts.__post_init__()
    if (facts.map_id, facts.at) != (traversal.map_id, traversal.at):
        raise RedLivingDexProviderPlanError(
            "provider-plan Red and traversal observations disagree"
        )
    _require_sha256(observed_state_sha256, "observed root state")
    if observed_state_sha256 != root.state_sha256:
        raise RedLivingDexProviderPlanError(
            "provider-plan traversal was read from another state"
        )


def observe_red_living_dex_provider_root_facts(
    observation: RedGoalObservation,
) -> RedLivingDexProviderRootFacts:
    """Project one coherent live read into the freezer's immutable prerequisites."""

    if not isinstance(observation, RedGoalObservation):
        raise TypeError("provider root facts need a Red goal observation")
    raw = observation.raw
    if (
        raw.map_id is None
        or raw.player_y is None
        or raw.player_x is None
        or raw.battle_state is None
        or raw.player_money is None
    ):
        raise RedLivingDexProviderPlanError("provider root observation lacks a physical boundary")
    bag_item_ids = frozenset(dict(raw.bag_items or ()))
    return RedLivingDexProviderRootFacts(
        map_id=int(raw.map_id),
        at=(raw.player_y, raw.player_x),
        input_ready=observation.input_ready,
        battle_state=raw.battle_state,
        party=observation.party,
        collection=observation.collection_observation,
        available_story_objective_ids=frozenset(
            item.id for item in COMPLETION_QUEST.available_objectives(observation.game_state)
        ),
        capture_item_count=observation.capture_item_count,
        recovery_item_count=observation.recovery_item_count,
        immediate_capture_slots=observation.immediate_capture_slots,
        bag_item_ids=bag_item_ids,
        player_money=raw.player_money,
        resources_satisfaction=observation.evidence.resources,
        world_knowledge_satisfaction=(observation.evidence.world_knowledge.satisfaction),
    )


@dataclass(frozen=True, slots=True)
class RedLivingDexProviderPlanFreeze:
    """Complete private recipe plan plus its zero-effect freeze proof."""

    plan: RedLivingDexSetupRecipePlan
    corridors: tuple[RedLivingDexWildCorridor, ...]
    effects_before: RedLivingDexSetupProtectedEffectCheckpoint
    effects_after: RedLivingDexSetupProtectedEffectCheckpoint

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RedLivingDexSetupRecipePlan):
            raise TypeError("provider-plan freeze needs a setup recipe plan")
        self.plan.__post_init__()
        if not isinstance(self.corridors, tuple) or any(
            not isinstance(item, RedLivingDexWildCorridor) for item in self.corridors
        ):
            raise TypeError("provider-plan freeze corridors differ")
        for corridor in self.corridors:
            corridor.__post_init__()
        if len({item.source_id for item in self.corridors}) != len(self.corridors):
            raise RedLivingDexProviderPlanError(
                "provider-plan freeze repeats an encounter corridor"
            )
        for value in (self.effects_before, self.effects_after):
            if not isinstance(value, RedLivingDexSetupProtectedEffectCheckpoint):
                raise TypeError("provider-plan freeze needs protected-effect checkpoints")
            value.__post_init__()
        if self.effects_before != self.effects_after:
            raise RedLivingDexProviderPlanError("provider-plan freeze crossed a protected effect")

    @property
    def freeze_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "corridor_binding_sha256s": [item.binding_sha256 for item in self.corridors],
            "effects_after": self.effects_after.private_dict(),
            "effects_before": self.effects_before.private_dict(),
            "recipe_plan_sha256": self.plan.plan_sha256,
            "schema": RED_LIVING_DEX_PROVIDER_PLAN_FREEZE_SCHEMA,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self.plan.public_dict(),
            "action_free_root_observations": len(self.plan.recipes),
            "cartridge_derived_corridors": len(self.corridors),
            "controller_actions": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "outcomes": 0,
            "provider_executions": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_PROVIDER_PLAN_FREEZE_SCHEMA,
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class _OriginTarget:
    map_id: int
    at: tuple[int, int] | None


_FIXED_ORIGIN_BY_LOCATION_SCOPE: Mapping[str, _OriginTarget] = {
    "train-location-scope-1": _OriginTarget(
        int(MapId.CINNABAR_POKECENTER),
        (3, 3),
    ),
    "train-location-scope-3": _OriginTarget(
        int(MapId.VIRIDIAN_POKECENTER),
        (3, 3),
    ),
    "train-location-scope-4": _OriginTarget(
        int(MapId.CINNABAR_MART),
        (5, 2),
    ),
    "development-location-scope-0": _OriginTarget(int(MapId.VIRIDIAN_CITY), None),
    "development-location-scope-1": _OriginTarget(int(MapId.PEWTER_CITY), None),
    "development-location-scope-2": _OriginTarget(
        int(MapId.CELADON_POKECENTER),
        (3, 3),
    ),
    "development-location-scope-3": _OriginTarget(
        int(MapId.CINNABAR_ISLAND),
        None,
    ),
}

_ORIGIN_SOURCE_BY_LOCATION_SCOPE = {
    "train-location-scope-0": "wild:Route24:grass",
    "train-location-scope-2": "wild:Route2:grass",
    "development-location-scope-4": "wild:Route21:grass",
}


def derive_red_living_dex_provider_corridors(
    world: StrategicScenarioRouteWorld,
) -> tuple[RedLivingDexWildCorridor, ...]:
    """Derive every scheduled encounter lane from one immutable cartridge."""

    if not isinstance(world, StrategicScenarioRouteWorld):
        raise TypeError("provider corridor derivation needs a Red route world")
    targets = _encounter_targets()
    corridors = tuple(
        derive_red_living_dex_wild_corridor(
            target,
            world.terrain[int(_encounter_map_id(target))],
            world.local_graphs[int(_encounter_map_id(target))],
        )
        for target in targets
    )
    return corridors


def freeze_red_living_dex_provider_plan(
    roots_by_slot: tuple[RedLivingDexActionFreeRootObservation, ...],
    *,
    world: RedLivingDexProviderRouteWorld,
    corridors: tuple[RedLivingDexWildCorridor, ...],
    execution_identity: RedLivingDexSetupExecutionIdentity,
    effects_before: RedLivingDexSetupProtectedEffectCheckpoint,
    effects_after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> RedLivingDexProviderPlanFreeze:
    """Build the complete 15/45/33/10 recipe plan without controller authority."""

    if not isinstance(roots_by_slot, tuple) or any(
        not isinstance(item, RedLivingDexActionFreeRootObservation) for item in roots_by_slot
    ):
        raise TypeError("provider-plan freezer needs an ordered root tuple")
    if not isinstance(execution_identity, RedLivingDexSetupExecutionIdentity):
        raise TypeError("provider-plan freezer needs a Red execution identity")
    execution_identity.__post_init__()
    _require_route_world(world)
    if _route_world_rom_sha256(world) != execution_identity.rom_sha256:
        raise RedLivingDexProviderPlanError("provider-plan route world uses another cartridge")
    if not isinstance(effects_before, RedLivingDexSetupProtectedEffectCheckpoint) or not isinstance(
        effects_after,
        RedLivingDexSetupProtectedEffectCheckpoint,
    ):
        raise TypeError("provider-plan freezer needs protected-effect checkpoints")
    if effects_before != effects_after:
        raise RedLivingDexProviderPlanError("provider-plan inventory crossed a protected effect")
    recipes = build_red_living_dex_provider_recipes(
        roots_by_slot,
        world=world,
        corridors=corridors,
        effects_before=effects_before,
        effects_after=effects_after,
    )
    prospective = build_red_living_dex_prospective_capture_plan()
    plan = build_red_living_dex_setup_recipe_plan(
        recipes,
        execution_identity=execution_identity,
        prospective_plan=prospective,
    )
    return RedLivingDexProviderPlanFreeze(
        plan=plan,
        corridors=tuple(sorted(corridors, key=lambda item: item.source_id)),
        effects_before=effects_before,
        effects_after=effects_after,
    )


def select_red_living_dex_provider_roots(
    candidates: tuple[RedLivingDexActionFreeRootObservation, ...],
    *,
    world: RedLivingDexProviderRouteWorld,
    corridors: tuple[RedLivingDexWildCorridor, ...],
    effects_before: RedLivingDexSetupProtectedEffectCheckpoint,
    effects_after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> tuple[RedLivingDexActionFreeRootObservation, ...]:
    """Choose one unique authentic root per frozen slot without gameplay.

    A source catalog's historical partition is provenance, not a label for
    this new prospective curriculum.  The selector therefore accepts one
    pooled inventory, sorts only opaque physical-root digests, and assigns the
    frozen 10+5 partition from slot order.  Expensive route compatibility is
    evaluated lazily while solving the complete bipartite assignment.  This
    avoids both a greedy early choice consuming the only root that can satisfy
    a later slot and an exhaustive route scan across roots that are never used.
    """

    if not isinstance(candidates, tuple) or any(
        not isinstance(item, RedLivingDexActionFreeRootObservation)
        for item in candidates
    ):
        raise TypeError("provider-plan candidates must be a tuple")
    for item in candidates:
        item.__post_init__()
    for value in (effects_before, effects_after):
        if not isinstance(value, RedLivingDexSetupProtectedEffectCheckpoint):
            raise TypeError("provider-plan selector needs protected-effect checkpoints")
        value.__post_init__()
    if effects_before != effects_after:
        raise RedLivingDexProviderPlanError("provider-plan inventory crossed a protected effect")
    _require_route_world(world)
    corridor_by_source = _validate_corridors(corridors)
    _require_unique_roots(candidates)

    prospective = build_red_living_dex_prospective_capture_plan()
    if len(candidates) < len(prospective.slots):
        raise RedLivingDexProviderPlanError(
            "provider-plan candidate inventory cannot cover every prospective slot"
        )

    ordered_candidates = tuple(
        sorted(candidates, key=lambda item: item.root.physical_root_sha256)
    )
    compatible: dict[int, tuple[RedLivingDexActionFreeRootObservation, ...]] = {}
    for slot_index, slot in enumerate(prospective.slots):
        options: list[RedLivingDexActionFreeRootObservation] = []
        for candidate in ordered_candidates:
            try:
                _require_slot_root_preconditions(slot, candidate.facts)
            except RedLivingDexProviderPlanError:
                continue
            options.append(candidate)
        if not options:
            raise RedLivingDexProviderPlanError(
                "provider-plan candidate inventory leaves an uncovered slot"
            )
        compatible[slot_index] = tuple(options)

    assignments: dict[int, RedLivingDexActionFreeRootObservation] = {}
    used: set[str] = set()
    route_compatible: dict[tuple[int, str], bool] = {}

    def can_route(
        slot_index: int,
        candidate: RedLivingDexActionFreeRootObservation,
    ) -> bool:
        root_sha256 = candidate.root.physical_root_sha256
        key = (slot_index, root_sha256)
        cached = route_compatible.get(key)
        if cached is not None:
            return cached
        try:
            _build_slot_recipe(
                prospective.slots[slot_index],
                candidate,
                world=world,
                corridor_by_source=corridor_by_source,
            )
        except RedLivingDexProviderPlanError:
            route_compatible[key] = False
            return False
        route_compatible[key] = True
        return True

    def assign() -> bool:
        if len(assignments) == len(prospective.slots):
            selected = tuple(
                assignments[index] for index in range(len(prospective.slots))
            )
            try:
                # Pairwise compatibility is necessary, while the complete join
                # also enforces cross-slot family/location capacity.  A failed
                # complete join must backtrack instead of rejecting an
                # inventory that has another valid matching.
                build_red_living_dex_provider_recipes(
                    selected,
                    world=world,
                    corridors=corridors,
                    effects_before=effects_before,
                    effects_after=effects_after,
                )
            except RedLivingDexProviderPlanError:
                return False
            return True
        remaining = tuple(
            index for index in range(len(prospective.slots)) if index not in assignments
        )
        slot_index = min(
            remaining,
            key=lambda index: (
                sum(
                    item.root.physical_root_sha256 not in used
                    for item in compatible[index]
                ),
                index,
            ),
        )
        for candidate in compatible[slot_index]:
            root_sha256 = candidate.root.physical_root_sha256
            if root_sha256 in used or not can_route(slot_index, candidate):
                continue
            assignments[slot_index] = candidate
            used.add(root_sha256)
            if assign():
                return True
            used.remove(root_sha256)
            del assignments[slot_index]
        return False

    if not assign():
        raise RedLivingDexProviderPlanError(
            "provider-plan candidate inventory has no unique complete assignment"
        )
    return tuple(assignments[index] for index in range(len(prospective.slots)))


def _require_slot_root_preconditions(
    slot: LivingDexProspectiveCaptureSlot,
    facts: RedLivingDexProviderRootFacts,
) -> None:
    """Reject an impossible root before invoking the expensive router."""

    for option_kind in slot.available_option_kinds:
        _require_root_preconditions(
            red_living_dex_provider_family_target(slot, option_kind),
            option_kind,
            facts,
        )


def build_red_living_dex_provider_recipe_for_action_free_root(
    slot: LivingDexProspectiveCaptureSlot,
    observation: RedLivingDexActionFreeRootObservation,
    *,
    world: RedLivingDexProviderRouteWorld,
    corridors: tuple[RedLivingDexWildCorridor, ...],
) -> RedLivingDexSetupSlotRecipe:
    """Resolve one genuine menu for an available root without claiming it.

    This is the narrow inventory surface used by the powered-capacity census.
    It accepts only one of the fifteen frozen Red templates, reads no bytes,
    and performs no behavior draw, controller action, provider execution, or
    outcome observation.  An incompatible root raises instead of being
    relabelled or partially counted.
    """

    if not isinstance(slot, LivingDexProspectiveCaptureSlot):
        raise TypeError("action-free provider census needs a prospective slot")
    if not isinstance(observation, RedLivingDexActionFreeRootObservation):
        raise TypeError("action-free provider census needs a root observation")
    slot.__post_init__()
    observation.__post_init__()
    canonical_slots = build_red_living_dex_prospective_capture_plan().slots
    if slot.slot_sha256 not in {item.slot_sha256 for item in canonical_slots}:
        raise RedLivingDexProviderPlanError(
            "action-free provider census received a noncanonical Red template"
        )
    _require_route_world(world)
    corridor_by_source = _validate_corridors(corridors)
    _require_slot_root_preconditions(slot, observation.facts)
    return _build_slot_recipe(
        slot,
        observation,
        world=world,
        corridor_by_source=corridor_by_source,
    )


def build_red_living_dex_provider_recipes(
    roots_by_slot: tuple[RedLivingDexActionFreeRootObservation, ...],
    *,
    world: RedLivingDexProviderRouteWorld,
    corridors: tuple[RedLivingDexWildCorridor, ...],
    effects_before: RedLivingDexSetupProtectedEffectCheckpoint,
    effects_after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> tuple[RedLivingDexSetupSlotRecipe, ...]:
    """Preflight all authentic roots and routes before a publish-bound freeze."""

    if not isinstance(roots_by_slot, tuple) or any(
        not isinstance(item, RedLivingDexActionFreeRootObservation) for item in roots_by_slot
    ):
        raise TypeError("provider-plan freezer needs an ordered root tuple")
    for value in (effects_before, effects_after):
        if not isinstance(value, RedLivingDexSetupProtectedEffectCheckpoint):
            raise TypeError("provider-plan freezer needs protected-effect checkpoints")
        value.__post_init__()
    if effects_before != effects_after:
        raise RedLivingDexProviderPlanError("provider-plan inventory crossed a protected effect")
    _require_route_world(world)
    prospective = build_red_living_dex_prospective_capture_plan()
    audit_red_living_dex_provider_curriculum()
    if len(roots_by_slot) != len(prospective.slots):
        raise RedLivingDexProviderPlanError("provider-plan root census does not cover every slot")
    for item in roots_by_slot:
        item.__post_init__()
    _require_unique_roots(roots_by_slot)
    corridor_by_source = _validate_corridors(corridors)
    return tuple(
        _build_slot_recipe(
            slot,
            root,
            world=world,
            corridor_by_source=corridor_by_source,
        )
        for slot, root in zip(prospective.slots, roots_by_slot, strict=True)
    )


def build_red_living_dex_provider_recipe_for_claimed_root(
    ordinal: int,
    observation: RedLivingDexClaimedRootObservation,
    *,
    world: RedLivingDexProviderRouteWorld,
    corridors: tuple[RedLivingDexWildCorridor, ...],
    expected_rom_sha256: str,
) -> RedLivingDexSetupSlotRecipe:
    """Cold-resolve exactly one selected recipe after durable admission.

    Unlike the inventory freezer, this path neither asks nor asserts whether a
    root is available: the supplied observation must prove the authoritative
    logical-plus-physical pair claim.  It intentionally has no batch API, so a
    caller cannot construct runtimes or routes for unclaimed siblings.
    """

    if type(ordinal) is not int:  # noqa: E721
        raise TypeError("claimed provider ordinal must be an int")
    prospective = build_red_living_dex_prospective_capture_plan()
    if not 0 <= ordinal < len(prospective.slots):
        raise RedLivingDexProviderPlanError("claimed provider ordinal differs")
    if not isinstance(observation, RedLivingDexClaimedRootObservation):
        raise TypeError("claimed provider resolver needs a claimed observation")
    observation.__post_init__()
    _require_route_world(world)
    expected_rom = _require_sha256(expected_rom_sha256, "expected route-world ROM")
    if _route_world_rom_sha256(world) != expected_rom:
        raise RedLivingDexProviderPlanError(
            "claimed provider route world uses another cartridge"
        )
    corridor_by_source = _validate_corridors(corridors)
    return _build_slot_recipe_from_components(
        prospective.slots[ordinal],
        root=observation.root,
        traversal=observation.traversal,
        facts=observation.facts,
        world=world,
        corridor_by_source=corridor_by_source,
    )


def red_living_dex_route_terminal_snapshot(
    world: RedLivingDexProviderRouteWorld,
    start: TraversalSnapshot,
    plan: RoutePlan,
) -> TraversalSnapshot:
    """Project only a route's typed terminal, including retained outside state."""

    _require_route_world(world)
    if not isinstance(start, TraversalSnapshot):
        raise TypeError("route terminal projection needs a traversal snapshot")
    if not isinstance(plan, RoutePlan):
        raise TypeError("route terminal projection needs a route plan")
    plan.__post_init__()
    if (plan.macro_path.maps[0], plan.start_at, plan.start_mode) != (
        start.map_id,
        start.at,
        start.mode,
    ):
        raise RedLivingDexProviderPlanError(
            "route terminal projection starts from another observation"
        )
    state = (start.map_id, start.last_outside_map)
    for expected_map, edge in zip(
        plan.macro_path.maps[1:],
        plan.macro_path.edges,
        strict=True,
    ):
        next_state = advance_macro_state(world.macro_graph, state, edge)
        if next_state is None or next_state[0] != expected_map:
            raise RedLivingDexProviderPlanError(
                "route terminal projection has inconsistent retained-map state"
            )
        state = next_state
    same_map = plan.terminal_map == start.map_id
    return TraversalSnapshot(
        map_id=plan.terminal_map,
        at=plan.terminal_at,
        ready=True,
        mode=plan.terminal_mode,
        occupied=(start.occupied if same_map else frozenset()),
        hazards=(start.hazards if same_map else ()),
        capabilities=start.capabilities,
        resources=start.resources,
        last_outside_map=state[1],
    )


def _build_slot_recipe(
    slot: LivingDexProspectiveCaptureSlot,
    root_observation: RedLivingDexActionFreeRootObservation,
    *,
    world: RedLivingDexProviderRouteWorld,
    corridor_by_source: Mapping[str, RedLivingDexWildCorridor],
) -> RedLivingDexSetupSlotRecipe:
    return _build_slot_recipe_from_components(
        slot,
        root=root_observation.root,
        traversal=root_observation.traversal,
        facts=root_observation.facts,
        world=world,
        corridor_by_source=corridor_by_source,
    )


def _build_slot_recipe_from_components(
    slot: LivingDexProspectiveCaptureSlot,
    *,
    root: RedLivingDexAuthenticatedSetupRoot,
    traversal: TraversalSnapshot,
    facts: RedLivingDexProviderRootFacts,
    world: RedLivingDexProviderRouteWorld,
    corridor_by_source: Mapping[str, RedLivingDexWildCorridor],
) -> RedLivingDexSetupSlotRecipe:
    _require_slot_root_preconditions(slot, facts)
    origin_target = _origin_target(slot, corridor_by_source)
    origin, construction_route, origin_snapshot = _route_to_target(
        world,
        traversal,
        origin_target,
        subject=f"{slot.slot_id} construction",
    )
    providers = tuple(
        _build_provider_recipe(
            slot,
            option_kind,
            origin_snapshot,
            facts,
            world=world,
            corridor_by_source=corridor_by_source,
        )
        for option_kind in slot.available_option_kinds
    )
    return RedLivingDexSetupSlotRecipe(
        slot_sha256=slot.slot_sha256,
        partition=slot.partition,
        available_option_kinds=slot.available_option_kinds,
        root_consumption_sha256=root.root_consumption_sha256,
        root_state_sha256=root.state_sha256,
        root_envelope_sha256=root.envelope_sha256,
        base_boundary=_boundary(traversal),
        origin_boundary=origin,
        construction_route=construction_route,
        providers=providers,
    )


def _build_provider_recipe(
    slot: LivingDexProspectiveCaptureSlot,
    option_kind: LivingDexOptionKind,
    origin: TraversalSnapshot,
    root_facts: RedLivingDexProviderRootFacts,
    *,
    world: RedLivingDexProviderRouteWorld,
    corridor_by_source: Mapping[str, RedLivingDexWildCorridor],
) -> RedLivingDexSetupProviderRecipe:
    target = red_living_dex_provider_family_target(slot, option_kind)
    _require_root_preconditions(target, option_kind, root_facts)
    corridor = (
        corridor_by_source[target.source_id]
        if isinstance(target, RedEncounterSourceTarget)
        else None
    )
    story_boundary = (
        red_living_dex_story_boundary(target) if isinstance(target, RedStoryTarget) else None
    )
    seed = build_red_living_dex_provider_recipe_seed(
        slot,
        option_kind,
        corridor=corridor,
        story_boundary=story_boundary,
    )
    route = _route_to_provider(world, origin, seed, subject=slot.slot_id)
    return RedLivingDexSetupProviderRecipe(
        option_kind=seed.option_kind,
        provider_type=seed.provider_type,
        profile=seed.profile,
        family=seed.family,
        route=route,
    )


def _require_root_preconditions(
    target: RedProviderFamilyTarget,
    option_kind: LivingDexOptionKind,
    facts: RedLivingDexProviderRootFacts,
) -> None:
    """Reject roots already incapable of exposing a scheduled real provider."""

    if isinstance(target, RedEncounterSourceTarget):
        if option_kind is LivingDexOptionKind.ACQUIRE:
            survey = summarize_red_area_survey(
                target.source_id,
                facts.collection,
                RED_ACQUISITION_CATALOG,
            )
            if (
                not survey.missing_species_refs
                or facts.capture_item_count < 1
                or facts.immediate_capture_slots < 1
            ):
                raise RedLivingDexProviderPlanError(
                    "provider-plan acquisition root lacks a legal target"
                )
            return
        if (
            option_kind is not LivingDexOptionKind.EXPLORE
            or facts.world_knowledge_satisfaction >= 1.0
        ):
            raise RedLivingDexProviderPlanError(
                "provider-plan exploration root lacks a legal target"
            )
        return
    if isinstance(target, RedLevelEvolutionTarget):
        source_internal = red_internal_species_id(red_species_number(target.source_species_ref))
        target_internal = red_internal_species_id(red_species_number(target.target_species_ref))
        current_box = facts.collection.current_box_index
        boxed_sources = tuple(
            specimen
            for specimen in facts.collection.specimens
            if specimen.species_ref == target.source_species_ref
            and specimen.location is CollectionLocation.BOX
            and specimen.container_index == current_box
        )
        party_species = facts.party.species_ids()
        deposit_candidates = tuple(
            member
            for member in facts.party.members
            if member.species_id not in {BLASTOISE_SPECIES_ID, source_internal, target_internal}
        )
        living_species = frozenset(specimen.species_ref for specimen in facts.collection.specimens)
        if (
            not boxed_sources
            or target.target_species_ref in living_species
            or source_internal in party_species
            or facts.party.size != 6
            or BLASTOISE_SPECIES_ID not in party_species
            or not facts.collection.current_box_has_room
            or not deposit_candidates
        ):
            raise RedLivingDexProviderPlanError(
                "provider-plan evolution root lacks its boxed precursor"
            )
        return
    if isinstance(target, RedPartyDevelopmentTarget):
        target_internal = red_internal_species_id(red_species_number(target.trainee_species_ref))
        matches = tuple(
            member for member in facts.party.members if member.species_id == target_internal
        )
        if (
            facts.party.size != 6
            or BLASTOISE_SPECIES_ID not in facts.party.species_ids()
            or len(matches) != 1
            or not matches[0].is_trainable
            or matches[0].level + target.level_increment > 100
        ):
            raise RedLivingDexProviderPlanError(
                "provider-plan development root lacks its unique trainee"
            )
        return
    if isinstance(target, RedStorageTarget):
        current = facts.collection.current_box_index
        counts = facts.collection.box_counts
        if (
            target.target_box_index == current
            or counts[target.target_box_index] >= facts.collection.box_capacity
            or facts.collection.box_capacity - counts[target.target_box_index]
            <= facts.collection.box_capacity - counts[current]
        ):
            raise RedLivingDexProviderPlanError(
                "provider-plan storage root lacks a higher-headroom target"
            )
        return
    if isinstance(target, RedResupplyTarget):
        projected = min(
            headroom_satisfaction(
                facts.capture_item_count + target.quantity,
                RED_GOAL_MANAGER_CONFIG.desired_capture_items,
                subject="capture item",
            ),
            headroom_satisfaction(
                facts.recovery_item_count,
                RED_GOAL_MANAGER_CONFIG.desired_recovery_items,
                subject="recovery item",
            ),
        )
        new_bag_slot = int(ItemId.GREAT_BALL) not in facts.bag_item_ids
        if (
            facts.player_money < target.quantity * 600
            or (new_bag_slot and len(facts.bag_item_ids) >= 20)
            or projected <= facts.resources_satisfaction
        ):
            raise RedLivingDexProviderPlanError(
                "provider-plan resupply root lacks resources or headroom"
            )
        return
    if isinstance(target, RedStoryTarget):
        if target.objective_id not in facts.available_story_objective_ids:
            raise RedLivingDexProviderPlanError(
                "provider-plan story root lacks its dependency-legal objective"
            )
        return
    raise RedLivingDexProviderPlanError("provider-plan target has no root-precondition contract")


def _route_to_provider(
    world: RedLivingDexProviderRouteWorld,
    origin: TraversalSnapshot,
    seed: RedLivingDexProviderRecipeSeed,
    *,
    subject: str,
) -> RedLivingDexSetupRouteRecipe | None:
    terminal = seed.terminal_boundary
    if terminal.matches_traversal(origin):
        return None
    plan = _plan(
        world,
        origin,
        terminal.map_id,
        terminal.at,
        subject=f"{subject} {seed.option_kind.value}",
    )
    if RedRoutedSemanticBoundary.from_plan(plan) != terminal:
        raise RedLivingDexProviderPlanError("provider-plan route reached another semantic terminal")
    return _route_recipe(world, plan)


def _route_to_target(
    world: RedLivingDexProviderRouteWorld,
    start: TraversalSnapshot,
    target: _OriginTarget,
    *,
    subject: str,
) -> tuple[
    RedRoutedSemanticBoundary,
    RedLivingDexSetupRouteRecipe | None,
    TraversalSnapshot,
]:
    if (
        start.map_id == target.map_id
        and (target.at is None or start.at == target.at)
        and start.mode == "land"
    ):
        return _boundary(start), None, start
    plan = _plan(
        world,
        start,
        target.map_id,
        target.at,
        subject=subject,
    )
    terminal = red_living_dex_route_terminal_snapshot(world, start, plan)
    if (
        terminal.map_id != target.map_id
        or (target.at is not None and terminal.at != target.at)
        or terminal.mode != "land"
    ):
        raise RedLivingDexProviderPlanError("provider-plan construction reached another origin")
    return _boundary(terminal), _route_recipe(world, plan), terminal


def _plan(
    world: RedLivingDexProviderRouteWorld,
    start: TraversalSnapshot,
    goal_map: int,
    goal_at: tuple[int, int] | None,
    *,
    subject: str,
) -> RoutePlan:
    try:
        plan = world.plan_feasible_to_map(start, goal_map, goal_at=goal_at)
    except RoutePlanningError as error:
        raise RedLivingDexProviderPlanError(f"provider-plan cannot route {subject}") from error
    if not isinstance(plan, RoutePlan):
        raise RedLivingDexProviderPlanError("provider-plan router returned no typed route")
    plan.__post_init__()
    if not plan.steps:
        raise RedLivingDexProviderPlanError(
            "provider-plan router returned an empty cross-boundary route"
        )
    red_living_dex_route_terminal_snapshot(world, start, plan)
    return plan


def _route_recipe(
    world: RedLivingDexProviderRouteWorld,
    plan: RoutePlan,
) -> RedLivingDexSetupRouteRecipe:
    return RedLivingDexSetupRouteRecipe(
        plan=plan,
        planner_binding_sha256=canonical_sha256(
            {
                "planner_contract": (
                    "pokemon_red_completion.strategic_navigation_scenario_runtime."
                    "StrategicScenarioRouteWorld.plan_feasible_to_map"
                ),
                "rom_sha256": _route_world_rom_sha256(world),
                "schema": RED_LIVING_DEX_PROVIDER_PLANNER_BINDING_SCHEMA,
            }
        ),
    )


def _origin_target(
    slot: LivingDexProspectiveCaptureSlot,
    corridor_by_source: Mapping[str, RedLivingDexWildCorridor],
) -> _OriginTarget:
    source_id = _ORIGIN_SOURCE_BY_LOCATION_SCOPE.get(slot.location_scope_id)
    if source_id is not None:
        corridor = corridor_by_source[source_id]
        return _OriginTarget(corridor.map_id, corridor.origin_at)
    target = _FIXED_ORIGIN_BY_LOCATION_SCOPE.get(slot.location_scope_id)
    if target is None:
        raise RedLivingDexProviderPlanError("provider-plan location scope has no authentic origin")
    return target


def _validate_corridors(
    corridors: tuple[RedLivingDexWildCorridor, ...],
) -> dict[str, RedLivingDexWildCorridor]:
    if not isinstance(corridors, tuple) or any(
        not isinstance(item, RedLivingDexWildCorridor) for item in corridors
    ):
        raise TypeError("provider-plan corridors must be a tuple")
    for corridor in corridors:
        corridor.__post_init__()
    by_source = {item.source_id: item for item in corridors}
    expected = {item.source_id for item in _encounter_targets()}
    if len(by_source) != len(corridors) or set(by_source) != expected:
        raise RedLivingDexProviderPlanError(
            "provider-plan corridor inventory differs from the curriculum"
        )
    return by_source


def _encounter_targets() -> tuple[RedEncounterSourceTarget, ...]:
    plan = build_red_living_dex_prospective_capture_plan()
    by_source: dict[str, RedEncounterSourceTarget] = {}
    for slot in plan.slots:
        for option_kind in slot.available_option_kinds:
            target = red_living_dex_provider_family_target(slot, option_kind)
            if isinstance(target, RedEncounterSourceTarget):
                by_source.setdefault(target.source_id, target)
    return tuple(by_source[source] for source in sorted(by_source))


def _encounter_map_id(target: RedEncounterSourceTarget) -> int:
    from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
        map_id_for_wild_source,
    )

    return int(map_id_for_wild_source(target.source_id))


def _require_unique_roots(
    observations: tuple[RedLivingDexActionFreeRootObservation, ...],
) -> None:
    for values, subject in (
        ((item.root.root_consumption_sha256 for item in observations), "root claims"),
        ((item.root.physical_root_sha256 for item in observations), "physical roots"),
        ((item.root.state_sha256 for item in observations), "root states"),
        ((item.root.envelope_sha256 for item in observations), "root envelopes"),
    ):
        materialized = tuple(values)
        if len(set(materialized)) != len(materialized):
            raise RedLivingDexProviderPlanError(f"provider-plan repeats {subject}")


def _require_route_world(world: RedLivingDexProviderRouteWorld) -> None:
    if (
        not isinstance(getattr(world, "macro_graph", None), MacroGraph)
        or not isinstance(getattr(world, "rom", None), bytes)
        or not world.rom
        or not callable(getattr(world, "plan_feasible_to_map", None))
    ):
        raise TypeError("provider-plan freezer needs a read-only route world")


def _route_world_rom_sha256(world: RedLivingDexProviderRouteWorld) -> str:
    _require_route_world(world)
    return hashlib.sha256(world.rom).hexdigest()


def _boundary(snapshot: TraversalSnapshot) -> RedRoutedSemanticBoundary:
    return RedRoutedSemanticBoundary(snapshot.map_id, snapshot.at, snapshot.mode)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexProviderPlanError(f"{subject} digest differs")
    return value


__all__ = [
    "RED_LIVING_DEX_PROVIDER_PLAN_FREEZE_SCHEMA",
    "RED_LIVING_DEX_PROVIDER_PLANNER_BINDING_SCHEMA",
    "RedLivingDexActionFreeRootObservation",
    "RedLivingDexClaimedRootObservation",
    "RedLivingDexProviderPlanError",
    "RedLivingDexProviderPlanFreeze",
    "RedLivingDexProviderRootFacts",
    "RedLivingDexProviderRouteWorld",
    "build_red_living_dex_provider_recipes",
    "build_red_living_dex_provider_recipe_for_action_free_root",
    "build_red_living_dex_provider_recipe_for_claimed_root",
    "derive_red_living_dex_provider_corridors",
    "freeze_red_living_dex_provider_plan",
    "observe_red_living_dex_provider_root_facts",
    "red_living_dex_route_terminal_snapshot",
    "select_red_living_dex_provider_roots",
]
