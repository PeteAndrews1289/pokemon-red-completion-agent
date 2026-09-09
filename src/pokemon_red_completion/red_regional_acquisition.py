"""Useful acquisition destinations below the one-option-per-kind goal manager.

Enumeration is action-free. It reuses cartridge corridors and the existing
walking/capture composition, then exposes only normalized semantic features to
the existing value model. No source identity becomes a learned feature.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    living_completion_checkpoint,
)
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionValueModel,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG, RedAcquisitionKind
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfile
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    RedLivingDexMultifamilyError,
    map_id_for_wild_source,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
from pokemon_red_completion.red_living_dex_setup_policy import (
    red_living_dex_setup_candidate_features,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridorError,
    bind_red_local_discovery_profile,
    derive_red_living_dex_wild_corridor,
    retarget_red_wild_profile,
)
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

SOURCE_CHOICE_POLICY = "living-dex-regional-source-softmax-v1"
MAXIMUM_SOURCE_CANDIDATES = 8


def regional_source_memory_key(source_id: str) -> str:
    """Stable across routed and already-local capture bindings."""
    return "pokemon.red:regional-acquisition:" + source_id


@dataclass(frozen=True, slots=True)
class RedRegionalAcquisitionCandidate:
    source_id: str
    profile: RedGoalContextProfile
    binding: ExecutableGoalBinding

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile, RedGoalContextProfile)
            or not isinstance(self.binding, ExecutableGoalBinding)
            or self.binding.kind is not GoalKind.ACQUIRE_SPECIES
        ):
            raise ValueError("regional candidate needs a real capture profile and binding")
        capture = [spec for spec in self.profile.providers if spec.kind is GoalKind.ACQUIRE_SPECIES]
        if len(capture) != 1 or capture[0].parameters.get("source_id") != self.source_id:
            raise ValueError("regional candidate source differs from its capture profile")


def enumerate_red_regional_acquisitions(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_actions: int,
    maximum_frames: int,
    routed_recovery: bool = False,
    prepare_capture_storage: bool = False,
) -> tuple[RedRegionalAcquisitionCandidate, ...]:
    """Return up to eight low-estimated-effort real ordinary-grass options.

    Candidate filtering is deterministic support, not a learned region choice.
    Sources lacking needed specimens, supplies, space or a walking route stay
    unavailable. Route execution must still verify every transition live.
    """
    before = actions.actions_executed, runtime.emulator.frame_count
    sources = sorted(
        {
            method.source_id
            for method in RED_ACQUISITION_CATALOG.methods
            if method.kind is RedAcquisitionKind.WILD
        }
    )
    candidates = []
    for source in sources:
        try:
            map_id = int(map_id_for_wild_source(source))
            if map_id not in world.terrain or map_id not in world.local_graphs:
                continue
            corridor = derive_red_living_dex_wild_corridor(
                RedEncounterSourceTarget(source),
                world.terrain[map_id],
                world.local_graphs[map_id],
                excluded=world.object_blockers[map_id],
            )
            profile = bind_red_local_discovery_profile(
                retarget_red_wild_profile(runtime.profile, corridor, rom=world.rom),
                source,
                world.rom,
            )
        except (RedLivingDexMultifamilyError, RedLivingDexWildCorridorError):
            continue
        routed = RedResourceGoalRouter(
            replace(runtime, profile=profile),
            actions,
            world,
            maximum_controller_actions=maximum_actions,
            maximum_emulator_frames=maximum_frames,
            quote_resource_costs=True,
            routed_recovery=routed_recovery,
            prepare_capture_storage=prepare_capture_storage,
        ).enumerate(observation)
        bindings = [
            binding for binding in routed.bindings if binding.kind is GoalKind.ACQUIRE_SPECIES
        ]
        if len(bindings) > 1:
            raise ValueError("regional source supplied multiple capture bindings")
        if bindings:
            candidates.append(RedRegionalAcquisitionCandidate(source, profile, bindings[0]))
    if before != (actions.actions_executed, runtime.emulator.frame_count):
        raise ValueError("regional source enumeration changed the game")
    candidates.sort(key=lambda candidate: (candidate.binding.estimated_effort, candidate.source_id))
    return tuple(candidates[:MAXIMUM_SOURCE_CANDIDATES])


def regional_acquisition_menu(
    observation: RedGoalObservation,
    candidates: tuple[RedRegionalAcquisitionCandidate, ...],
    memory: GoalSearchMemory,
) -> LivingDexOptionMenu:
    """Use the existing goal-value features, with source-specific search history."""
    if not 2 <= len(candidates) <= MAXIMUM_SOURCE_CANDIDATES or len(
        {candidate.source_id for candidate in candidates}
    ) != len(candidates):
        raise ValueError("regional learning needs two to eight distinct executable sources")
    ledger = living_completion_checkpoint(observation)
    rows = tuple(
        LivingDexOptionCandidate(
            binding_ref=f"regional-policy-row-{index}",
            features=red_living_dex_setup_candidate_features(
                LivingDexOptionKind.ACQUIRE,
                # Same aggregate-effort projection as the current goal-value model.
                # Do not double-charge transport through another route feature.
                route_controller_actions=0,
                maximum_controller_actions=1,
                estimated_effort=candidate.binding.estimated_effort,
                estimated_risk=candidate.binding.estimated_risk,
                storage_unit=observation.situation.storage_pressure,
            ),
            availability=LivingDexOptionAvailability.AVAILABLE,
            search_history=memory.lookup(
                regional_source_memory_key(candidate.source_id),
                ledger.required_specimens_sha256,
            ),
        )
        for index, candidate in enumerate(candidates)
    )
    menu = LivingDexOptionMenu(
        living_dex_option_context_from_goal_situation(observation.situation),
        rows,
    )
    if len({menu.candidate_vector(index) for index in menu.available_indices}) < 2:
        raise ValueError("regional candidates have no distinguishable semantic features")
    return menu


def sample_regional_acquisition(
    model: LivingDexOptionValueModel,
    menu: LivingDexOptionMenu,
    *,
    seed: int,
) -> dict[str, object]:
    """One reproducible, fully supported model-softmax sample; no game input."""
    if type(seed) is not int or seed < 0 or model.feature_version < menu.feature_version:
        raise ValueError("regional selection seed or feature version differs")
    scores = model.scores(menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
    values = [scores[index] for index in menu.available_indices]
    if any(value is None or not math.isfinite(value) for value in values):
        raise ValueError("regional model returned invalid scores")
    utilities = [float(value) for value in values if value is not None]
    peak = max(utilities)
    exp = [math.exp(value - peak) for value in utilities]
    total = sum(exp)
    probabilities = [0.0] * len(menu.candidates)
    for index, value in zip(menu.available_indices, exp, strict=True):
        probabilities[index] = 0.75 * value / total + 0.25 / len(exp)
    selected = random.Random(seed).choices(
        range(len(probabilities)),
        weights=probabilities,
        k=1,
    )[0]
    return {
        "policy_id": SOURCE_CHOICE_POLICY,
        "seed": seed,
        "model_sha256": model.model_sha256,
        "menu_sha256": menu.policy_sha256,
        "scores": list(scores),
        "probabilities": probabilities,
        "selected_candidate_index": selected,
        "exploration_mix": 0.25,
        "temperature": 1.0,
    }
