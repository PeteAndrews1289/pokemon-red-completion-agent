from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import (
    MacroEdge,
    MacroPath,
    MacroTransition,
)
from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalKind,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_state import (
    CompletionProgress,
    GoalStateEvidence,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.local_router import LocalPath
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MapId,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import red_internal_species_id
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import (
    RedGoalObservation,
    RedStoryGoalBindingProvider,
)
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedMartResupplyGoalProvider,
    RedObservedGoalSkillProvider,
    RedProgressGoalProvider,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    red_living_dex_goal_family_ref,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
    RedResupplyTarget,
    RedStorageTarget,
    RedStoryTarget,
    audit_red_living_dex_provider_curriculum,
    red_living_dex_provider_family_target,
    red_living_dex_targeted_provider_parameters,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupProviderRecipe,
    RedLivingDexSetupRecipeError,
    RedLivingDexSetupRouteRecipe,
    RedLivingDexSetupSlotRecipe,
    build_red_living_dex_setup_recipe_plan,
    restore_red_living_dex_validated_setup_capture,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.red_living_dex_setup_recipe_campaign import (
    RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID,
    RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND,
    RedLivingDexControlledRecipeFailure,
    RedLivingDexSetupRecipeCampaignError,
    RedLivingDexSetupRecipeDisposition,
    run_red_living_dex_setup_recipe_campaign,
)
from pokemon_red_completion.red_living_dex_setup_source import (
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupExecutionIdentity,
    RedLivingDexSetupFailureReason,
    RedLivingDexSetupTrustError,
    RedLivingDexTransformationFamily,
    build_red_living_dex_transformation_family,
)
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedRoutedSemanticBoundary,
    RedSemanticTransportRoute,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RouteSegment


def _sha(value: object) -> str:
    return hashlib.sha256(repr(value).encode("ascii")).hexdigest()


_VERIFIED_TO_CINNABAR = (
    "power_on",
    "begin_adventure",
    "choose_starter",
    "receive_pokedex",
    "reach_pewter",
    "defeat_brock",
    "reach_cerulean",
    "defeat_misty",
    "help_bill",
    "reach_vermilion",
    "obtain_cut",
    "defeat_surge",
    "reach_lavender",
    "rescue_fuji",
    "reach_celadon",
    "clear_rocket_hideout",
    "obtain_silph_scope",
    "reach_fuchsia",
    "obtain_surf",
    "defeat_koga",
)


def _identity() -> RedLivingDexSetupExecutionIdentity:
    return RedLivingDexSetupExecutionIdentity(
        source_commit="a" * 40,
        source_bundle_sha256=_sha("source-bundle"),
        adapter_version_sha256=_sha("adapter-version"),
        state_schema_sha256=_sha("state-schema"),
        observation_schema_sha256=_sha("observation-schema"),
        route_registry_sha256=_sha("route-registry"),
        provider_registry_sha256=_sha("provider-registry"),
        runtime_contract_sha256=_sha("runtime-contract"),
    )


def _root_payloads(index: int) -> tuple[bytes, bytes]:
    state_bytes = f"root-state-{index:02d}".encode("ascii")
    envelope = CapturedProgressEnvelope(
        state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        checkpoint_id=f"root-{index:02d}",
        checkpoint_label="authenticated purpose-built recipe root",
        checkpoints_completed=len(_VERIFIED_TO_CINNABAR),
        checkpoints_total=36,
        verified_objective_ids=_VERIFIED_TO_CINNABAR,
    )
    envelope_bytes = (
        json.dumps(
            envelope.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    return state_bytes, envelope_bytes


_OPTION_TO_GOAL = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}


_OPTION_TO_MECHANIC = {
    LivingDexOptionKind.ACQUIRE: RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
    LivingDexOptionKind.EVOLVE: RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
    LivingDexOptionKind.DEVELOP: RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
    LivingDexOptionKind.MANAGE_STORAGE: RedGoalMechanic.BOX_SWITCH,
    LivingDexOptionKind.RESUPPLY: RedGoalMechanic.MART_RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: RedGoalMechanic.MIDGAME_STORY,
    LivingDexOptionKind.EXPLORE: RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
}


_OPTION_TO_PROVIDER = {
    LivingDexOptionKind.ACQUIRE: RedAreaSurveyGoalProvider,
    LivingDexOptionKind.EVOLVE: RedObservedGoalSkillProvider,
    LivingDexOptionKind.DEVELOP: RedObservedGoalSkillProvider,
    LivingDexOptionKind.MANAGE_STORAGE: RedBoxSwitchGoalProvider,
    LivingDexOptionKind.RESUPPLY: RedMartResupplyGoalProvider,
    LivingDexOptionKind.UNLOCK_ACCESS: RedStoryGoalBindingProvider,
    LivingDexOptionKind.EXPLORE: RedEncounterDiscoveryGoalProvider,
}


def _goal_observation(boundary: RedRoutedSemanticBoundary) -> RedGoalObservation:
    progress = CompletionProgress(0, 1)
    evidence = GoalStateEvidence(
        story=progress,
        registered_collection=progress,
        living_collection=progress,
        level_collection=progress,
        team_readiness=0.0,
        evolution=progress,
        safety=1.0,
        resources=1.0,
        storage=1.0,
        control=1.0,
        world_knowledge=progress,
    )
    unavailable: Any = None
    return RedGoalObservation(
        raw=RawGameState(
            game_started=True,
            map_id=boundary.map_id,
            player_x=boundary.at[1],
            player_y=boundary.at[0],
            party_count=0,
            battle_state=0,
        ),
        game_state=GameState(GameMode.OVERWORLD, location="private-boundary"),
        party=PartyObservation(),
        collection=unavailable,
        collection_observation=unavailable,
        evidence=evidence,
        input_ready=True,
        capture_item_count=0,
        recovery_item_count=0,
        free_storage_slots=0,
        immediate_capture_slots=0,
    )


def _fresh(
    boundary: RedRoutedSemanticBoundary,
    *,
    capture_item_count: int = 0,
) -> FreshRedGoalObservation:
    observation = replace(
        _goal_observation(boundary),
        capture_item_count=capture_item_count,
    )
    provisional = FreshRedGoalObservation(
        "0" * 64,
        observation,
        _traversal(boundary),
    )
    return replace(
        provisional,
        observation_sha256=red_living_dex_setup_fresh_observation_sha256(provisional),
    )


def _traversal(boundary: RedRoutedSemanticBoundary) -> TraversalSnapshot:
    return TraversalSnapshot(
        map_id=boundary.map_id,
        at=boundary.at,
        ready=True,
        mode=boundary.mode,
    )


def _cross_route(
    origin: RedRoutedSemanticBoundary,
    terminal: RedRoutedSemanticBoundary,
    token: object,
) -> RedLivingDexSetupRouteRecipe:
    if origin.map_id == terminal.map_id:
        from pokemon_red_completion.local_router import LocalEdge

        path = LocalPath(
            coordinates=(origin.at, terminal.at),
            edges=(LocalEdge(target=terminal.at, action="right"),),
            modes=(origin.mode, terminal.mode),
        )
        plan = RoutePlan(
            macro_path=MacroPath((origin.map_id,), ()),
            start_at=origin.at,
            start_mode=origin.mode,
            segments=(),
            terminal_approach=path,
            terminal_at=terminal.at,
            terminal_mode=terminal.mode,
        )
    else:
        transition = MacroTransition(
            exit_at=origin.at,
            arrival_at=terminal.at,
            action="right",
        )
        edge = MacroEdge(
            target_map=terminal.map_id,
            coordinate_transitions=(transition,),
        )
        approach = LocalPath(
            coordinates=(origin.at,),
            edges=(),
            modes=(origin.mode,),
        )
        segment = RouteSegment(
            source_map=origin.map_id,
            target_map=terminal.map_id,
            approach=approach,
            transition=transition,
            passage_kind="connection",
            transition_action_in_approach=False,
        )
        plan = RoutePlan(
            macro_path=MacroPath((origin.map_id, terminal.map_id), (edge,)),
            start_at=origin.at,
            start_mode=origin.mode,
            segments=(segment,),
            terminal_approach=None,
            terminal_at=terminal.at,
            terminal_mode=terminal.mode,
        )
    return RedLivingDexSetupRouteRecipe(
        plan,
        planner_binding_sha256=_sha(("planner", token)),
    )


def _profile_parameters(
    kind: LivingDexOptionKind,
    boundary: RedRoutedSemanticBoundary,
    token: str,
) -> dict[str, object]:
    token_index = int(token[1:3], 16)
    token_option = int(token[3:5], 16)
    storage_target_by_slot = (0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 4, 5, 6, 7)
    wild_sources = (
        "wild:ViridianForest:grass",
        "wild:Route2:grass",
        "wild:Route1:grass",
        "wild:Route14:grass",
        "wild:Route16:grass",
        "wild:Route22:grass",
        "wild:Route18:grass",
        "wild:Route4:grass",
        "wild:Route23:grass",
        "wild:CeruleanCave1F:grass",
        "wild:MtMoon1F:grass",
        "wild:Route3:grass",
        "wild:CeruleanCave2F:grass",
        "wild:SeafoamIslands1F:grass",
        "wild:Route24:grass",
    )
    if kind is LivingDexOptionKind.EVOLVE:
        slot = build_red_living_dex_prospective_capture_plan().slots[token_index]
        return red_living_dex_targeted_provider_parameters(slot, kind)
    if kind is LivingDexOptionKind.DEVELOP:
        slot = build_red_living_dex_prospective_capture_plan().slots[token_index]
        return red_living_dex_targeted_provider_parameters(slot, kind)
    if kind in {
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EXPLORE,
    }:
        values: dict[str, object] = {
            "source_id": wild_sources[token_index],
            "label": f"source {token}",
            "map_id": boundary.map_id,
            "player_x": boundary.at[1],
            "player_y": boundary.at[0],
            "forward_directions": ["up"],
            "starting_endpoint": "south",
            "maximum_legs": 2,
            "maximum_seek_steps": 20,
            "maximum_encounters": 4,
        }
        return values
    if kind is LivingDexOptionKind.MANAGE_STORAGE:
        return {
            "target_box_index": storage_target_by_slot[token_index],
            "map_id": boundary.map_id,
            "player_x": boundary.at[1],
            "player_y": boundary.at[0],
        }
    if kind is LivingDexOptionKind.RESUPPLY:
        return {
            "map_id": boundary.map_id,
            "player_x": boundary.at[1],
            "player_y": boundary.at[0],
            "interaction_direction": "up",
            "purchases": [
                {
                    "absolute_index": 0,
                    "item_id": 4,
                    "quantity": 1 + token_index * 3 + token_option,
                    "unit_price": 200,
                }
            ],
        }
    return {}


def _profile(
    kind: LivingDexOptionKind,
    boundary: RedRoutedSemanticBoundary,
    token: str,
) -> RedGoalContextProfile:
    target: tuple[GoalKind, RedGoalMechanic, Mapping[str, object]] = (
        _OPTION_TO_GOAL[kind],
        _OPTION_TO_MECHANIC[kind],
        _profile_parameters(kind, boundary, token),
    )
    providers: list[tuple[GoalKind, RedGoalMechanic, Mapping[str, object]]] = [
        (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
        (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
    ]
    providers = [item for item in providers if item[0] is not target[0]]
    providers.append(target)
    if len(providers) < 3:
        providers.append((GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}))
    providers.sort(key=lambda item: tuple(GoalKind).index(item[0]))
    return parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=f"recipe-{token}",
            providers=tuple(providers),
        )
    )


def _provider_terminal(
    kind: LivingDexOptionKind,
    origin: RedRoutedSemanticBoundary,
    index: int,
) -> RedRoutedSemanticBoundary:
    if kind in {
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
    }:
        return RedRoutedSemanticBoundary(
            int(MapId.CINNABAR_POKECENTER),
            (3, 3),
            None,
        )
    if kind is LivingDexOptionKind.MANAGE_STORAGE:
        return RedRoutedSemanticBoundary(
            int(MapId.VIRIDIAN_POKECENTER),
            (3, 3),
            None,
        )
    if kind is LivingDexOptionKind.RESUPPLY:
        return RedRoutedSemanticBoundary(
            int(MapId.VIRIDIAN_MART),
            (4, 2),
            None,
        )
    del index
    return origin


def _semantic_binding_ref(kind: LivingDexOptionKind, token: str) -> str:
    return f"pokemon.red:test-family:{kind.value}:{token}"


def _expected_family_sha256(
    profile: RedGoalContextProfile,
    kind: LivingDexOptionKind,
    token: str,
) -> str:
    spec = next(item for item in profile.providers if item.kind is _OPTION_TO_GOAL[kind])
    binding = ExecutableGoalBinding(
        binding_ref=(
            f"{_semantic_binding_ref(kind, token)}:profile-{profile.profile_sha256}:"
            f"config-{spec.configuration_sha256}"
        ),
        kind=_OPTION_TO_GOAL[kind],
        estimated_effort=0.2,
        estimated_risk=0.1,
        execute=lambda: GoalExecutionReport(0, 0, {}),
        verify=lambda _report: GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED),
    )
    return canonical_sha256(
        {
            "family_ref": red_living_dex_goal_family_ref(binding, profile),
            "schema": "pokemon.red.private-transformation-family-join.v1",
        }
    )


def _recipe(
    index: int,
    *,
    origin_map: int,
) -> RedLivingDexSetupSlotRecipe:
    slot = build_red_living_dex_prospective_capture_plan().slots[index]
    root_state_bytes, root_envelope_bytes = _root_payloads(index)
    origin = RedRoutedSemanticBoundary(origin_map, (1, 1), None)
    providers: list[RedLivingDexSetupProviderRecipe] = []
    for option_index, kind in enumerate(slot.available_option_kinds):
        terminal = _provider_terminal(kind, origin, option_index)
        token = f"s{index:02x}{option_index:02x}"
        profile = _profile(kind, terminal, token)
        family = build_red_living_dex_transformation_family(
            option_kind=kind,
            profile=profile,
            story_objective_id=(token if kind is LivingDexOptionKind.UNLOCK_ACCESS else None),
        )
        providers.append(
            RedLivingDexSetupProviderRecipe(
                option_kind=kind,
                provider_type=_OPTION_TO_PROVIDER[kind],
                profile=profile,
                family=family,
                route=(
                    None
                    if terminal == origin
                    else _cross_route(origin, terminal, (index, option_index))
                ),
            )
        )
    return RedLivingDexSetupSlotRecipe(
        slot_sha256=slot.slot_sha256,
        partition=slot.partition,
        available_option_kinds=slot.available_option_kinds,
        root_consumption_sha256=_sha(("root", index)),
        root_state_sha256=hashlib.sha256(root_state_bytes).hexdigest(),
        root_envelope_sha256=hashlib.sha256(root_envelope_bytes).hexdigest(),
        base_boundary=origin,
        origin_boundary=origin,
        construction_route=None,
        providers=tuple(providers),
    )


def _recipes(*, alias_last_location: bool = False) -> tuple[RedLivingDexSetupSlotRecipe, ...]:
    maps = (
        int(MapId.ROUTE_1),
        int(MapId.ROUTE_1),
        int(MapId.ROUTE_2),
        int(MapId.ROUTE_2),
        int(MapId.ROUTE_3),
        int(MapId.ROUTE_3),
        int(MapId.ROUTE_4),
        int(MapId.ROUTE_4),
        int(MapId.ROUTE_5),
        int(MapId.ROUTE_5),
        int(MapId.ROUTE_6),
        int(MapId.ROUTE_7),
        int(MapId.ROUTE_8),
        int(MapId.ROUTE_9),
        int(MapId.ROUTE_10),
    )
    if alias_last_location:
        maps = (*maps[:-1], maps[0])
    return tuple(_recipe(index, origin_map=map_id) for index, map_id in enumerate(maps))


_Meter = RedLivingDexSetupEffectMeter


def _cross_protected_effect(meter: _Meter, name: str) -> None:
    recorders = {
        "behavior_draws": meter.record_behavior_draw,
        "learner_labels": meter.record_learner_label,
        "learner_outcomes": meter.record_learner_outcome,
        "model_predictions": meter.record_model_prediction,
        "model_fits": meter.record_model_fit,
        "provider_executions": meter.record_provider_execution,
        "teacher_queries": meter.record_teacher_query,
        "root_claims": meter.record_root_claim,
    }
    recorders[name]()


def _recipe_party(
    recipe: RedLivingDexSetupSlotRecipe,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    development_ref: str | None = None
    evolution_source_ref: str | None = None
    evolution_target_ref: str | None = None
    evolution_level: int | None = None
    for provider in recipe.providers:
        spec = provider.provider_spec
        assert hasattr(spec, "mechanic") and hasattr(spec, "parameters")
        if spec.mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT:
            development_ref = str(spec.parameters["trainee_species_ref"])
        if spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            evolution_source_ref = str(spec.parameters["source_species_ref"])
            evolution_target_ref = str(spec.parameters["target_species_ref"])
            evolution_level = int(spec.parameters["evolution_level"])

    species = [BLASTOISE_SPECIES_ID]
    levels = [60]
    if development_ref is not None:
        development_level = (
            20 if evolution_level is None else max(2, evolution_level - 2)
        )
        species.append(red_internal_species_id(int(development_ref[-3:])))
        levels.append(development_level)
    excluded = {
        *(int(value[-3:]) for value in (development_ref, evolution_source_ref) if value),
        *(() if evolution_target_ref is None else (int(evolution_target_ref[-3:]),)),
        9,
    }
    for national in (25, 50, 64, 72, 100, 104, 120):
        if national in excluded:
            continue
        species.append(red_internal_species_id(national))
        levels.append(60)
        if len(species) == 6:
            break
    assert len(species) == len(levels) == 6
    return tuple(species), tuple(levels)


class _Reader:
    def __init__(self, arm: _Arm) -> None:
        self.arm = arm

    def read(self) -> RawGameState:
        boundary = self.arm.boundary
        species, levels = _recipe_party(self.arm.recipe)
        return RawGameState(
            game_started=True,
            map_id=boundary.map_id,
            player_x=boundary.at[1],
            player_y=boundary.at[0],
            party_count=6,
            battle_state=0,
            bag_item_ids=(int(ItemId.POKE_BALL), int(ItemId.HYPER_POTION)),
            bag_items=(
                (int(ItemId.POKE_BALL), 20),
                (int(ItemId.HYPER_POTION), 20),
            ),
            party_species_ids=species,
            party_levels=levels,
            party_hp=(150, 100, 100, 100, 100, 100),
            party_max_hp=(150, 100, 100, 100, 100, 100),
            party_status=(0, 0, 0, 0, 0, 0),
            party_moves=(
                (0x39, 0x3A, 0x46, 0x82),
                (0xA3, 0x0A, 0x5B, 0),
                (55, 57, 58, 0),
                (55, 57, 58, 0),
                (55, 57, 58, 0),
                (55, 57, 58, 0),
            ),
            party_pp=((25, 15, 10, 10), (20, 35, 10, 0)) + ((25, 15, 10, 0),) * 4,
            player_money=99_999,
        )

    def read_pokedex_state(self) -> RedPokedexState:
        return RedPokedexState(frozenset(), frozenset())

    def read_all_box_states(self) -> RedBoxCollectionState:
        source_ref: str | None = None
        source_level: int | None = None
        for provider in self.arm.recipe.providers:
            spec = provider.provider_spec
            if spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
                source_ref = str(spec.parameters["source_species_ref"])
                source_level = int(spec.parameters["evolution_level"]) - 1
        current = (
            RedCurrentBoxState(
                0,
                (red_internal_species_id(int(source_ref[-3:])),),
                (source_level,),
            )
            if source_ref is not None and source_level is not None
            else RedCurrentBoxState(0, (), ())
        )
        return RedBoxCollectionState(
            (
                current,
                *(RedCurrentBoxState(index, (), ()) for index in range(1, 12)),
            ),
            0,
            False,
        )

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0, 0, 0, 0, 0)


class _StateEmulator:
    def __init__(self, arm: _Arm, meter: _Meter) -> None:
        self.arm = arm
        self.meter = meter
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.payload = b"unloaded"

    def load_state_bytes(self, payload: bytes) -> None:
        if self.arm.factory.ignore_state_bytes:
            return
        self.payload = payload
        if self.arm.factory.restore_spends:
            self.meter.record_controller_actions()
            self.meter.record_emulator_frames(10)

    def save_state_bytes(self) -> bytes:
        return self.payload

    def read_u8(self, _address: int) -> int:
        return 0

    def press(self, _button: str) -> None:
        pass

    def release(self, _button: str) -> None:
        pass

    def tick(self, frames: int) -> None:
        self.frame_count += frames
        self.meter.record_emulator_frames(frames)


class _TraversalObserver:
    def __init__(self, arm: _Arm) -> None:
        self.arm = arm

    def observe(self) -> TraversalSnapshot:
        return _traversal(self.arm.boundary)


class _RouteDelegate:
    def __init__(self, arm: _Arm) -> None:
        self.arm = arm

    def execute(self, action: MacroAction) -> MacroAction:
        terminal = self.arm.pending_terminal
        if terminal is None:
            raise AssertionError("route action lacked a terminal")
        self.arm.boundary = terminal
        if not self.arm.factory.fabricated_arrival_without_state:
            self.arm.emulator.payload = (
                self.arm.emulator.payload
                + f":{terminal.map_id}:{terminal.at[0]}:{terminal.at[1]}".encode("ascii")
            )
        self.arm.factory.meter.record_controller_actions()
        self.arm.emulator.tick(10)
        return action


class _Arm:
    def __init__(
        self,
        factory: _ArmFactory,
        recipe: RedLivingDexSetupSlotRecipe,
        purpose: str,
        ordinal: int,
        sequence: int,
    ) -> None:
        self.factory = factory
        self.recipe = recipe
        self.purpose = purpose
        self.ordinal = ordinal
        self.arm_identity_sha256 = (
            _sha("reused-arm")
            if factory.reuse_arm_identity
            else _sha((recipe.recipe_sha256, purpose, ordinal, sequence))
        )
        self.execution_identity_sha256 = factory.identity.identity_sha256
        self.effect_meter = factory.meter
        self.boundary = (
            recipe.base_boundary if purpose == "construction" else recipe.origin_boundary
        )
        self.pending_terminal: RedRoutedSemanticBoundary | None = None
        self.emulator = _StateEmulator(self, factory.meter)
        self.actions = CountingExecutor(_RouteDelegate(self))
        self.reader = _Reader(self)

    def _profile(self) -> RedGoalContextProfile:
        if self.purpose == "candidate":
            return self.recipe.providers[self.ordinal].profile
        return self.recipe.providers[0].profile

    def _capture(self) -> GoalManagerContextCapture:
        envelope = CapturedProgressEnvelope(
            state_sha256=hashlib.sha256(self.emulator.payload).hexdigest(),
            checkpoint_id=f"arm-{self.arm_identity_sha256[:20]}",
            checkpoint_label="isolated setup arm",
            checkpoints_completed=len(_VERIFIED_TO_CINNABAR),
            checkpoints_total=36,
            verified_objective_ids=_VERIFIED_TO_CINNABAR,
        )
        envelope_bytes = (
            json.dumps(envelope.to_dict(), ensure_ascii=True, sort_keys=True).encode("ascii")
            + b"\n"
        )
        return parse_goal_manager_context_capture(self.emulator.payload, envelope_bytes)

    def observe_fresh(self) -> FreshRedGoalObservation:
        if self.factory.protected_effect_name is not None:
            name = self.factory.protected_effect_name
            self.factory.protected_effect_name = None
            _cross_protected_effect(self.factory.meter, name)
        context = build_red_goal_context_runtime(
            profile=self._profile(),
            capture=self._capture(),
            emulator=self.emulator,
            reader=self.reader,  # type: ignore[arg-type]
            boxed_level_evolution_executor=lambda _request, _actions: GoalExecutionReport(
                0,
                0,
                {},
            ),
        )
        observation = context.adapter.observe()
        provisional = FreshRedGoalObservation(
            "0" * 64,
            observation,
            _traversal(self.boundary),
        )
        return replace(
            provisional,
            observation_sha256=red_living_dex_setup_fresh_observation_sha256(provisional),
        )

    def build_route(
        self,
        route: RedLivingDexSetupRouteRecipe,
        *,
        origin_observation_sha256: str,
    ) -> RedSemanticTransportRoute:
        if self.factory.forged_route_type:
            return object()  # type: ignore[return-value]
        self.pending_terminal = route.terminal_boundary
        return RedSemanticTransportRoute(
            binding_ref=f"test-route-{route.recipe_sha256[:16]}",
            origin_observation_sha256=origin_observation_sha256,
            planner_binding_sha256=route.planner_binding_sha256,
            plan=route.plan,
            actions=self.actions,
            traversal_observer=_TraversalObserver(self),
            emulator=self.emulator,
        )

    def build_goal_context(
        self,
        profile: RedGoalContextProfile,
        capture: GoalManagerContextCapture,
    ):  # type: ignore[no-untyped-def]
        if self.factory.context_spends:
            self.factory.meter.record_controller_actions()
            self.factory.meter.record_emulator_frames(10)
        context = build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=self.emulator,
            reader=self.reader,  # type: ignore[arg-type]
            boxed_level_evolution_executor=lambda _request, _actions: GoalExecutionReport(
                0,
                0,
                {},
            ),
        )
        if self.factory.wrong_context_emulator:
            context.emulator = object()  # type: ignore[assignment]
        return context


class _ArmFactory:
    def __init__(
        self,
        identity: RedLivingDexSetupExecutionIdentity,
        meter: _Meter,
    ) -> None:
        self.identity = identity
        self.meter = meter
        self.arms: list[_Arm] = []
        self.ignore_state_bytes = False
        self.restore_spends = False
        self.context_spends = False
        self.reuse_arm_identity = False
        self.forged_route_type = False
        self.fabricated_arrival_without_state = False
        self.wrong_context_emulator = False
        self.protected_effect_name: str | None = None

    def __call__(
        self,
        recipe: RedLivingDexSetupSlotRecipe,
        purpose: str,
        ordinal: int,
    ) -> _Arm:
        arm = _Arm(self, recipe, purpose, ordinal, len(self.arms))
        self.arms.append(arm)
        return arm


def _root(index: int) -> RedLivingDexAuthenticatedSetupRoot:
    state, envelope = _root_payloads(index)
    return RedLivingDexAuthenticatedSetupRoot(
        root_consumption_sha256=_sha(("root", index)),
        state_bytes=state,
        envelope_bytes=envelope,
    )


def _validate_fixture(
    index: int,
    recipe: RedLivingDexSetupSlotRecipe,
    meter: _Meter,
    factory: _ArmFactory | None = None,
):
    identity = _identity()
    resolved_factory = factory or _ArmFactory(identity, meter)
    return validate_red_living_dex_setup_recipe(
        build_red_living_dex_prospective_capture_plan().slots[index],
        recipe,
        execution_identity=identity,
        root=_root(index),
        arm_factory=resolved_factory,
        meter=meter,
    )


def _store(tmp_path: Path) -> PrivateArtifactRoot:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


def _claim_registry(tmp_path: Path) -> Path:
    registry = tmp_path / "account-claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    return registry


def test_evolution_capability_names_the_provider_the_profile_really_builds() -> None:
    capabilities = {item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES}
    assert capabilities[LivingDexOptionKind.EVOLVE].executor_types == (
        RedObservedGoalSkillProvider,
    )


def test_provider_recipe_rejects_the_old_false_evolution_provenance() -> None:
    recipe = _recipe(1, origin_map=int(MapId.ROUTE_1))
    evolution = recipe.providers[0]
    assert evolution.option_kind is LivingDexOptionKind.EVOLVE
    with pytest.raises(RedLivingDexSetupRecipeError, match="real profile mechanic"):
        replace(evolution, provider_type=RedProgressGoalProvider)


def test_recipe_plan_requires_ten_real_origin_maps_for_ten_logical_scopes() -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    assert plan.public_dict() == {
        "claim_before_controller_input": True,
        "development_slots": 5,
        "execution_identity_bound": True,
        "learner_effects": 0,
        "option_count": 45,
        "physical_origin_count": 10,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "retry_after_controller_input": False,
        "routed_option_count": 26,
        "same_origin_fork_required": True,
        "schema": "pokemon.red.private-living-dex-setup-recipe-plan.v2",
        "semantic_family_count": 39,
        "semantic_family_minimum": 33,
        "slot_count": 15,
        "train_slots": 10,
    }


def test_complete_recipe_capacity_uses_real_targeted_team_families() -> None:
    curriculum = audit_red_living_dex_provider_curriculum()
    plan = build_red_living_dex_setup_recipe_plan(
        _recipes(),
        execution_identity=_identity(),
    )
    families_by_kind = {
        kind: {
            provider.expected_family_sha256
            for recipe in plan.recipes
            for provider in recipe.providers
            if provider.option_kind is kind
        }
        for kind in LivingDexOptionKind
    }
    mechanics = {
        provider.family.mechanic
        for recipe in plan.recipes
        for provider in recipe.providers
    }

    assert len(families_by_kind[LivingDexOptionKind.EVOLVE]) == 5
    assert len(families_by_kind[LivingDexOptionKind.DEVELOP]) == 4
    assert curriculum.public_dict() == {
        "development_family_count": 4,
        "development_offer_count": 6,
        "evolution_family_count": 5,
        "evolution_offer_count": 6,
        "identity_derived_family_count": 0,
        "offer_count": 45,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "raw_controller_sequence_steps": 0,
        "semantic_family_count": 33,
        "teacher_routes": 0,
    }
    assert RedGoalMechanic.TARGETED_LEVEL_EVOLUTION in mechanics
    assert RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT in mechanics
    assert RedGoalMechanic.DIGLETT_EVOLUTION not in mechanics
    assert RedGoalMechanic.BALANCED_TEAM not in mechanics
    assert all(
        "profile" not in json.dumps(provider.family.private_dict(), sort_keys=True)
        and "slot" not in json.dumps(provider.family.private_dict(), sort_keys=True)
        and "route" not in json.dumps(provider.family.private_dict(), sort_keys=True)
        for recipe in plan.recipes
        for provider in recipe.providers
    )
    with pytest.raises(RedLivingDexSetupRecipeError, match="reused"):
        build_red_living_dex_setup_recipe_plan(
            _recipes(alias_last_location=True), execution_identity=_identity()
        )


def test_production_curriculum_binds_every_nontraining_family_without_test_tokens() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    targets = tuple(
        (
            slot.family_scope_id,
            option_kind,
            red_living_dex_provider_family_target(slot, option_kind),
        )
        for slot in plan.slots
        for option_kind in slot.available_option_kinds
    )

    encounter_sources = {
        target.source_id
        for _scope, _kind, target in targets
        if isinstance(target, RedEncounterSourceTarget)
    }
    storage_boxes = {
        target.target_box_index
        for _scope, _kind, target in targets
        if isinstance(target, RedStorageTarget)
    }
    resupply_quantities = {
        target.quantity
        for _scope, _kind, target in targets
        if isinstance(target, RedResupplyTarget)
    }
    story_objectives = {
        target.objective_id
        for _scope, _kind, target in targets
        if isinstance(target, RedStoryTarget)
    }

    assert encounter_sources == {
        "wild:Route2:grass",
        "wild:Route11:grass",
        "wild:Route22:grass",
        "wild:Route24:grass",
        "wild:Route16:grass",
        "wild:Route8:grass",
        "wild:Route21:grass",
    }
    assert storage_boxes == {1, 2, 3, 4, 5}
    assert resupply_quantities == {1, 2, 3, 4}
    assert story_objectives == {
        "cross_victory_road",
        "defeat_blaine",
        "defeat_giovanni",
        "defeat_erika",
        "obtain_strength",
    }
    assert all(
        all(
            forbidden not in field_name.lower()
            for field_name in target.__dataclass_fields__
            for forbidden in ("slot", "profile", "route", "root")
        )
        for _scope, _kind, target in targets
    )


def test_recipe_plan_rejects_expected_family_overlap_before_controller_input() -> None:
    recipes = list(_recipes())
    train_acquire = recipes[0].providers[0]
    development = recipes[10]
    development_acquire = replace(
        development.providers[0],
        family=train_acquire.family,
    )
    recipes[10] = replace(
        development,
        providers=(development_acquire, *development.providers[1:]),
    )

    with pytest.raises(RedLivingDexSetupRecipeError, match="families overlap"):
        build_red_living_dex_setup_recipe_plan(tuple(recipes), execution_identity=_identity())


def test_slot_recipe_rejects_a_candidate_route_from_another_origin() -> None:
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    routed = recipe.providers[1]
    assert routed.route is not None
    wrong_origin = RedRoutedSemanticBoundary(int(MapId.ROUTE_2), (1, 1), None)
    wrong = replace(
        routed,
        route=_cross_route(
            wrong_origin,
            routed.route.terminal_boundary,
            "wrong-origin",
        ),
    )
    with pytest.raises(RedLivingDexSetupRecipeError, match="shared origin"):
        replace(recipe, providers=(recipe.providers[0], wrong, recipe.providers[2]))


def test_route_digest_distinguishes_off_diagonal_coordinate_order() -> None:
    route = _cross_route(
        RedRoutedSemanticBoundary(int(MapId.ROUTE_1), (2, 3), None),
        RedRoutedSemanticBoundary(int(MapId.ROUTE_2), (4, 5), None),
        "yx",
    )
    swapped = _cross_route(
        RedRoutedSemanticBoundary(int(MapId.ROUTE_1), (3, 2), None),
        RedRoutedSemanticBoundary(int(MapId.ROUTE_2), (5, 4), None),
        "xy",
    )
    assert route.route_plan_sha256 != swapped.route_plan_sha256
    assert route.origin_boundary.at == (2, 3)
    assert route.terminal_boundary.at == (4, 5)


def test_same_root_validation_derives_real_menu_without_executing_a_provider() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    identity = _identity()
    factory = _ArmFactory(identity, meter)

    result = validate_red_living_dex_setup_recipe(
        slot,
        recipe,
        execution_identity=identity,
        root=_root(0),
        arm_factory=factory,
        meter=meter,
    )

    assert len(factory.arms) == 5
    assert len({item.arm_identity_sha256 for item in factory.arms}) == 5
    assert meter.provider_executions == 0
    assert result.origin_restore_count == 5
    assert result.attestation.setup_controller_actions == 2
    assert result.attestation.setup_emulator_frames == 20
    assert result.binding.location_sha256 == recipe.location_sha256
    assert result.binding.available_family_sha256s == tuple(
        item.family_sha256 for item in result.fork_proofs
    )
    assert result.binding.menu_sha256 == result.policy_projection.menu.policy_sha256
    assert result.policy_projection.maximum_controller_actions == (
        slot.setup.maximum_controller_actions
    )
    assert result.policy_projection.maximum_emulator_frames == (
        slot.setup.maximum_emulator_frames
    )
    assert result.public_dict()["policy_menu"] == (
        result.policy_projection.menu.policy_dict()
    )
    assert all(
        candidate.binding_ref not in str(result.public_dict()["policy_menu"])
        for candidate in result.policy_projection.menu.candidates
    )
    assert result.public_dict()["provider_executions"] == 0
    assert result.public_dict()["learner_labels"] == 0


def test_same_root_validation_reports_bounded_diagnostic_phases() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    identity = _identity()
    phases: list[str] = []

    validate_red_living_dex_setup_recipe(
        slot,
        recipe,
        execution_identity=identity,
        root=_root(0),
        arm_factory=_ArmFactory(identity, meter),
        meter=meter,
        phase_observer=phases.append,
    )

    assert phases[0] == "construction_arm"
    assert phases[-1] == "capture_assembly"
    assert phases.count("candidate_arm") == len(recipe.providers)
    assert phases.count("candidate_offer") == len(recipe.providers)
    assert "final_restore" in phases


def test_routed_origin_construction_is_counted_before_candidate_forks() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    local_recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    base = RedRoutedSemanticBoundary(int(MapId.ROUTE_2), (2, 3), None)
    construction = _cross_route(
        base,
        local_recipe.origin_boundary,
        "construction",
    )
    recipe = replace(
        local_recipe,
        base_boundary=base,
        construction_route=construction,
    )
    meter = _Meter()
    identity = _identity()
    factory = _ArmFactory(identity, meter)

    result = validate_red_living_dex_setup_recipe(
        slot,
        recipe,
        execution_identity=identity,
        root=_root(0),
        arm_factory=factory,
        meter=meter,
    )

    assert result.attestation.setup_controller_actions == 4
    assert result.attestation.setup_emulator_frames == 40
    assert sum(item.pending_terminal is not None for item in factory.arms) == 2
    assert result.construction_route_recipe_sha256 == construction.recipe_sha256
    assert result.construction_route_plan_sha256 == construction.route_plan_sha256
    assert result.construction_route_report_sha256 is not None
    assert result.construction_route_controller_actions == 2
    assert result.construction_route_emulator_frames == 20

    document = deepcopy(result.private_dict())
    document["construction_route_report_sha256"] = "f" * 64
    with pytest.raises(RedLivingDexSetupRecipeError, match="observer proof tree"):
        restore_red_living_dex_validated_setup_capture(document)


def test_validated_capture_private_round_trip_retains_exact_repeatable_bytes() -> None:
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    original = _validate_fixture(0, recipe, meter)

    restored = restore_red_living_dex_validated_setup_capture(
        json.loads(json.dumps(original.private_dict()))
    )

    assert restored.private_dict() == original.private_dict()
    assert restored.state_bytes == original.state_bytes
    assert restored.envelope_bytes == original.envelope_bytes


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda value: value.__setitem__("learner_labels", 1),
            "learner boundary",
        ),
        (
            lambda value: value.__setitem__("attestation_sha256", "0" * 64),
            "attestation digest",
        ),
        (
            lambda value: value.__setitem__("state_payload_base64", "not-base64"),
            "payload encoding",
        ),
        (
            lambda value: value["fork_proofs"][0].__setitem__(  # type: ignore[index,union-attr]
                "provider_executions", 1
            ),
            "learner boundary",
        ),
        (
            lambda value: value["binding"].__setitem__(  # type: ignore[union-attr]
                "schema", "pokemon.red.private-living-dex-setup-slot-binding.v1"
            ),
            "binding schema",
        ),
        (
            lambda value: value["binding"]["option_bindings"][0].__setitem__(  # type: ignore[index,union-attr]
                "schema", "pokemon.red.private-living-dex-setup-option-binding.v1"
            ),
            "option schema",
        ),
        (
            lambda value: value["fork_proofs"][0].__setitem__(  # type: ignore[index,union-attr]
                "family_sha256", "1" * 64
            ),
            "observer proof tree",
        ),
        (
            lambda value: value["fork_proofs"][1].__setitem__(  # type: ignore[index,union-attr]
                "route_report_sha256", "2" * 64
            ),
            "observer proof tree",
        ),
        (
            lambda value: value["fork_proofs"][0].__setitem__(  # type: ignore[index,union-attr]
                "fork_runtime_sha256", "3" * 64
            ),
            "observer proof tree",
        ),
        (
            lambda value: value.__setitem__("construction_runtime_sha256", "4" * 64),
            "observer proof tree",
        ),
    ),
)
def test_validated_capture_private_restore_rejects_tampering(
    mutation: Any,
    message: str,
) -> None:
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    result = _validate_fixture(0, recipe, meter)
    document = deepcopy(result.private_dict())
    mutation(document)

    with pytest.raises(RedLivingDexSetupRecipeError, match=message):
        restore_red_living_dex_validated_setup_capture(document)


@pytest.mark.parametrize(
    ("flag", "message"),
    (
        ("restore_spends", "restore changed protected effects"),
        ("context_spends", "registry construction changed protected effects"),
        ("ignore_state_bytes", "restore readback differs"),
        ("reuse_arm_identity", "reused an isolated arm identity"),
    ),
)
def test_same_root_validation_fails_closed_on_boundary_mutations(
    flag: str,
    message: str,
) -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    identity = _identity()
    factory = _ArmFactory(identity, meter)
    setattr(factory, flag, True)

    with pytest.raises(RedLivingDexSetupRecipeError, match=message):
        validate_red_living_dex_setup_recipe(
            slot,
            recipe,
            execution_identity=identity,
            root=_root(0),
            arm_factory=factory,
            meter=meter,
        )


@pytest.mark.parametrize(
    "effect_name",
    (
        "behavior_draws",
        "learner_labels",
        "learner_outcomes",
        "model_predictions",
        "model_fits",
        "provider_executions",
        "teacher_queries",
        "root_claims",
    ),
)
def test_same_root_validation_meters_every_protected_authority(
    effect_name: str,
) -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    identity = _identity()
    factory = _ArmFactory(identity, meter)
    factory.protected_effect_name = effect_name

    with pytest.raises(RedLivingDexSetupRecipeError, match="observation changed protected effects"):
        validate_red_living_dex_setup_recipe(
            slot,
            recipe,
            execution_identity=identity,
            root=_root(0),
            arm_factory=factory,
            meter=meter,
        )


def test_same_root_validation_rejects_a_self_attested_meter() -> None:
    class _SelfAttestedMeter:
        def checkpoint(self) -> object:
            return object()

        def record_root_claim(self) -> None:
            pass

    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    identity = _identity()
    real_meter = _Meter()

    with pytest.raises(TypeError, match="comprehensive effect meter"):
        validate_red_living_dex_setup_recipe(
            slot,
            recipe,
            execution_identity=identity,
            root=_root(0),
            arm_factory=_ArmFactory(identity, real_meter),
            meter=_SelfAttestedMeter(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("flag", "message"),
    (
        ("forged_route_type", "different semantic route"),
        ("fabricated_arrival_without_state", "without changing emulator state"),
        ("wrong_context_emulator", "isolated candidate state"),
    ),
)
def test_same_root_validation_rejects_self_attested_route_or_provider_context(
    flag: str,
    message: str,
) -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    identity = _identity()
    factory = _ArmFactory(identity, meter)
    setattr(factory, flag, True)

    with pytest.raises(RedLivingDexSetupRecipeError, match=message):
        validate_red_living_dex_setup_recipe(
            slot,
            recipe,
            execution_identity=identity,
            root=_root(0),
            arm_factory=factory,
            meter=meter,
        )


def test_same_root_validation_rejects_an_arm_from_another_execution_identity() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    identity = _identity()
    other_identity = replace(identity, source_bundle_sha256=_sha("other-source-bundle"))

    with pytest.raises(RedLivingDexSetupRecipeError, match="execution identity"):
        validate_red_living_dex_setup_recipe(
            slot,
            recipe,
            execution_identity=identity,
            root=_root(0),
            arm_factory=_ArmFactory(other_identity, meter),
            meter=meter,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("game_id", "pokemon-blue"),
        ("title", "Pokemon - Blue Version (USA, Europe)"),
        ("rom_sha1", "0" * 40),
        ("rom_sha256", "0" * 64),
        ("source_published", False),
        ("worktree_dirty", True),
    ),
)
def test_execution_identity_rejects_other_titles_or_unpublished_source(
    field: str,
    value: object,
) -> None:
    with pytest.raises(RedLivingDexSetupTrustError):
        replace(_identity(), **{field: value})


def test_same_root_validation_derives_family_from_the_registry_binding() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    acquire = recipe.providers[0]
    wrong_family = RedLivingDexTransformationFamily(
        acquire.family.option_kind,
        acquire.family.goal_kind,
        acquire.family.mechanic,
        {"source_id": "wild:Route2:grass"},
    )
    forged = replace(
        recipe,
        providers=(replace(acquire, family=wrong_family), *recipe.providers[1:]),
    )
    meter = _Meter()
    identity = _identity()

    with pytest.raises(RedLivingDexSetupRecipeError, match="provider family"):
        validate_red_living_dex_setup_recipe(
            slot,
            forged,
            execution_identity=identity,
            root=_root(0),
            arm_factory=_ArmFactory(identity, meter),
            meter=meter,
        )


def test_recipe_rejects_a_profile_whose_coordinate_does_not_match_terminal() -> None:
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    acquire = recipe.providers[0]
    mismatched_profile = _profile(
        LivingDexOptionKind.ACQUIRE,
        RedRoutedSemanticBoundary(int(MapId.ROUTE_1), (9, 8), None),
        "s0000-mismatch",
    )
    wrong = replace(acquire, profile=mismatched_profile)
    with pytest.raises(RedLivingDexSetupRecipeError, match="provider profile"):
        replace(recipe, providers=(wrong, *recipe.providers[1:]))


def test_recipe_campaign_claims_account_wide_and_recovers_without_arm_reentry(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    store = _store(tmp_path)
    registry = _claim_registry(tmp_path)
    meter = _Meter()
    actual = _ArmFactory(plan.execution_identity, meter)
    construction_calls: list[str] = []

    def factory(
        recipe: RedLivingDexSetupSlotRecipe,
        purpose: str,
        ordinal: int,
    ) -> _Arm:
        if purpose == "construction":
            construction_calls.append(recipe.recipe_sha256)
            episode = plan.recipes.index(recipe)
            episode_id = f"red-living-dex-recipe-{episode:02d}-{recipe.recipe_sha256[:20]}"
            assert store.inspect_episode_state(episode_id).status == "partial"
            sealed = store.find_sealed_record(
                RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID,
                expected_kind=RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND,
            )
            assert sealed is not None
            assert sealed.read()["recipe_plan_sha256"] == plan.plan_sha256
            if recipe is not plan.recipes[0]:
                raise RedLivingDexControlledRecipeFailure(
                    RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE
                )
        return actual(recipe, purpose, ordinal)

    first = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=factory,
        meter=meter,
        claim_registry=registry,
    )

    assert construction_calls == [item.recipe_sha256 for item in plan.recipes]
    assert meter.root_claims == 15
    assert first.inventory_qualification_available is False
    assert first.public_dict()["terminal_status_counts"] == {
        "complete": 1,
        "failed": 14,
        "interrupted": 0,
    }
    assert all(
        item.terminal.execution_identity_sha256 == plan.execution_identity.identity_sha256
        for item in first.receipts
    )
    assert all(
        {"reason_code", "setup_controller_actions", "setup_emulator_frames", "status"}.isdisjoint(
            item.public_dict()
        )
        for item in first.receipts
    )
    before = meter.checkpoint()

    def forbidden_factory(
        _recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        raise AssertionError("a recovered recipe must not reenter an isolated arm")

    recovered = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=forbidden_factory,
        meter=meter,
        claim_registry=registry,
    )

    assert meter.checkpoint() == before
    assert recovered.receipts[0].disposition is (
        RedLivingDexSetupRecipeDisposition.RECOVERED_COMPLETE
    )
    assert all(
        item.disposition is RedLivingDexSetupRecipeDisposition.RECOVERED_FAILED
        for item in recovered.receipts[1:]
    )
    assert tuple(item.terminal.private_dict() for item in recovered.receipts) == tuple(
        item.terminal.private_dict() for item in first.receipts
    )


def test_recipe_campaign_never_retries_a_claimed_validation_failure(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    store = _store(tmp_path)
    registry = _claim_registry(tmp_path)
    meter = _Meter()
    failing = _ArmFactory(plan.execution_identity, meter)
    failing.ignore_state_bytes = True

    with pytest.raises(RedLivingDexSetupRecipeCampaignError, match="durable claim"):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            roots=roots,
            arm_factory=failing,
            meter=meter,
            claim_registry=registry,
        )
    assert len(failing.arms) == 1

    resumed_calls: list[str] = []

    def resumed_factory(
        recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        resumed_calls.append(recipe.recipe_sha256)
        raise RedLivingDexControlledRecipeFailure(RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE)

    resumed = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=resumed_factory,
        meter=meter,
        claim_registry=registry,
    )

    assert resumed_calls == [item.recipe_sha256 for item in plan.recipes[1:]]
    assert resumed.receipts[0].terminal.status.value == "failed"
    assert resumed.receipts[0].terminal.retry_allowed is False
    assert resumed.receipts[0].disposition is (RedLivingDexSetupRecipeDisposition.RECOVERED_FAILED)


def test_recipe_campaign_uses_a_closed_failure_vocabulary_and_aggregate_publication(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    store = _store(tmp_path)
    registry = _claim_registry(tmp_path)
    meter = _Meter()
    calls = 0

    def factory(
        _recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        nonlocal calls
        calls += 1
        raise RedLivingDexControlledRecipeFailure(RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE)

    run = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=factory,
        meter=meter,
        claim_registry=registry,
    )

    assert calls == 15
    assert run.receipts[0].terminal.reason_code is (RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE)
    assert run.public_dict()["failure_category_counts"]["root_unavailable"] == 15
    assert run.receipts[0].terminal.setup_controller_actions == 0
    with pytest.raises(
        RedLivingDexSetupRecipeCampaignError,
        match="controlled recipe failure reason",
    ):
        RedLivingDexControlledRecipeFailure("a" * 64)  # type: ignore[arg-type]


def test_recipe_campaign_counts_arm_factory_effects_and_fails_closed(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    store = _store(tmp_path)
    registry = _claim_registry(tmp_path)
    meter = _Meter()
    actual = _ArmFactory(plan.execution_identity, meter)

    def actionful_factory(
        recipe: RedLivingDexSetupSlotRecipe,
        purpose: str,
        ordinal: int,
    ) -> _Arm:
        meter.record_controller_actions()
        meter.record_emulator_frames(10)
        return actual(recipe, purpose, ordinal)

    with pytest.raises(RedLivingDexSetupRecipeCampaignError, match="durable claim"):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            roots=roots,
            arm_factory=actionful_factory,
            meter=meter,
            claim_registry=registry,
        )

    def remaining_failures(
        _recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        raise RedLivingDexControlledRecipeFailure(RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE)

    recovered = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=remaining_failures,
        meter=meter,
        claim_registry=registry,
    )
    assert recovered.receipts[0].terminal.setup_controller_actions == 1
    assert recovered.receipts[0].terminal.retry_allowed is False


@pytest.mark.parametrize(
    "cutpoint",
    (
        "after_plan_seal",
        "after_account_root_claim",
        "after_local_episode_open",
        "after_local_claim",
        "after_capture_append",
        "after_episode_complete",
        "after_terminal_publish",
    ),
)
def test_recipe_campaign_restart_matrix_never_reuses_a_claimed_root(
    tmp_path: Path,
    cutpoint: str,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    store = _store(tmp_path)
    registry = _claim_registry(tmp_path)
    meter = _Meter()
    actual = _ArmFactory(plan.execution_identity, meter)
    armed = True

    def failpoint(name: str, recipe: RedLivingDexSetupSlotRecipe) -> None:
        nonlocal armed
        if armed and recipe is plan.recipes[0] and name == cutpoint:
            armed = False
            raise KeyboardInterrupt(cutpoint)

    with pytest.raises(KeyboardInterrupt, match=cutpoint):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            roots=roots,
            arm_factory=actual,
            meter=meter,
            claim_registry=registry,
            failpoint=failpoint,
        )

    arms_before_restart = len(actual.arms)
    first_recipe_reentered = False

    def recovery_factory(
        recipe: RedLivingDexSetupSlotRecipe,
        purpose: str,
        ordinal: int,
    ) -> _Arm:
        nonlocal first_recipe_reentered
        if recipe is plan.recipes[0]:
            first_recipe_reentered = True
            if cutpoint != "after_plan_seal":
                raise AssertionError("a globally claimed root reentered an arm")
            return actual(recipe, purpose, ordinal)
        raise RedLivingDexControlledRecipeFailure(
            RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE
        )

    recovered = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=recovery_factory,
        meter=meter,
        claim_registry=registry,
    )

    assert meter.root_claims == 15
    assert all(item.terminal.retry_allowed is False for item in recovered.receipts)
    if cutpoint == "after_plan_seal":
        assert first_recipe_reentered is True
        assert len(actual.arms) == arms_before_restart + 5
        assert recovered.receipts[0].terminal.status.value == "complete"
    else:
        assert first_recipe_reentered is False
        assert len(actual.arms) == arms_before_restart
    before_second_recovery = meter.checkpoint()

    def forbidden_factory(
        _recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        raise AssertionError("a terminal campaign must not construct another arm")

    second = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=forbidden_factory,
        meter=meter,
        claim_registry=registry,
    )
    assert meter.checkpoint() == before_second_recovery
    assert tuple(item.terminal.private_dict() for item in second.receipts) == tuple(
        item.terminal.private_dict() for item in recovered.receipts
    )


@pytest.mark.parametrize(
    "cutpoint",
    (
        "after_failure_append",
        "after_failure_terminal_publish",
        "after_failure_episode_abort",
    ),
)
def test_recipe_campaign_failure_restart_matrix_is_also_no_retry(
    tmp_path: Path,
    cutpoint: str,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    store = _store(tmp_path)
    registry = _claim_registry(tmp_path)
    meter = _Meter()
    first_calls = 0
    armed = True

    def controlled_failure(
        recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        nonlocal first_calls
        if recipe is plan.recipes[0]:
            first_calls += 1
        raise RedLivingDexControlledRecipeFailure(
            RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE
        )

    def failpoint(name: str, recipe: RedLivingDexSetupSlotRecipe) -> None:
        nonlocal armed
        if armed and recipe is plan.recipes[0] and name == cutpoint:
            armed = False
            raise KeyboardInterrupt(cutpoint)

    with pytest.raises(KeyboardInterrupt, match=cutpoint):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            roots=roots,
            arm_factory=controlled_failure,
            meter=meter,
            claim_registry=registry,
            failpoint=failpoint,
        )
    assert first_calls == 1

    recovered = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=controlled_failure,
        meter=meter,
        claim_registry=registry,
    )

    assert first_calls == 1
    assert meter.root_claims == 15
    assert recovered.receipts[0].terminal.retry_allowed is False
    assert recovered.receipts[0].terminal.status.value in {"failed", "interrupted"}


@pytest.mark.parametrize(
    "cutpoint",
    (
        "after_prelocal_claim",
        "after_prelocal_failure_append",
        "after_prelocal_episode_abort",
        "after_prelocal_terminal_publish",
    ),
)
def test_prelocal_interruption_recovery_survives_a_second_power_loss(
    tmp_path: Path,
    cutpoint: str,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    store = _store(tmp_path)
    registry = _claim_registry(tmp_path)
    meter = _Meter()

    def first_crash(name: str, recipe: RedLivingDexSetupSlotRecipe) -> None:
        if recipe is plan.recipes[0] and name == "after_account_root_claim":
            raise KeyboardInterrupt(name)

    with pytest.raises(KeyboardInterrupt, match="after_account_root_claim"):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            roots=roots,
            arm_factory=_ArmFactory(plan.execution_identity, meter),
            meter=meter,
            claim_registry=registry,
            failpoint=first_crash,
        )
    assert meter.root_claims == 1
    armed = True

    def second_crash(name: str, recipe: RedLivingDexSetupSlotRecipe) -> None:
        nonlocal armed
        if armed and recipe is plan.recipes[0] and name == cutpoint:
            armed = False
            raise KeyboardInterrupt(name)

    def no_arm(
        _recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        raise AssertionError("prelocal recovery cannot construct an arm")

    with pytest.raises(KeyboardInterrupt, match=cutpoint):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            roots=roots,
            arm_factory=no_arm,
            meter=meter,
            claim_registry=registry,
            failpoint=second_crash,
        )

    def remaining_failures(
        recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        if recipe is plan.recipes[0]:
            raise AssertionError("the twice-interrupted root cannot reenter an arm")
        raise RedLivingDexControlledRecipeFailure(
            RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE
        )

    recovered = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        roots=roots,
        arm_factory=remaining_failures,
        meter=meter,
        claim_registry=registry,
    )
    assert meter.root_claims == 15
    assert recovered.receipts[0].terminal.status.value == "interrupted"
    assert recovered.receipts[0].terminal.retry_allowed is False


def test_account_claim_blocks_the_same_physical_root_in_another_store(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes(), execution_identity=_identity())
    roots = tuple(_root(index) for index in range(15))
    first_directory = tmp_path / "first-store"
    second_directory = tmp_path / "second-store"
    first_directory.mkdir()
    second_directory.mkdir()
    first_store = _store(first_directory)
    second_store = _store(second_directory)
    registry = _claim_registry(tmp_path)
    meter = _Meter()

    def crash_after_global_claim(name: str, recipe: RedLivingDexSetupSlotRecipe) -> None:
        if recipe is plan.recipes[0] and name == "after_account_root_claim":
            raise KeyboardInterrupt(name)

    with pytest.raises(KeyboardInterrupt, match="after_account_root_claim"):
        run_red_living_dex_setup_recipe_campaign(
            first_store,
            plan,
            roots=roots,
            arm_factory=_ArmFactory(plan.execution_identity, meter),
            meter=meter,
            claim_registry=registry,
            failpoint=crash_after_global_claim,
        )

    relabeled_id = _sha("same-bytes-different-catalog-label")
    relabeled_recipe = replace(
        plan.recipes[0],
        root_consumption_sha256=relabeled_id,
    )
    second_plan = build_red_living_dex_setup_recipe_plan(
        (relabeled_recipe, *plan.recipes[1:]),
        execution_identity=plan.execution_identity,
    )
    second_roots = (
        replace(roots[0], root_consumption_sha256=relabeled_id),
        *roots[1:],
    )

    first_root_reentered = False

    def second_store_factory(
        recipe: RedLivingDexSetupSlotRecipe,
        _purpose: str,
        _ordinal: int,
    ) -> _Arm:
        nonlocal first_root_reentered
        if recipe is second_plan.recipes[0]:
            first_root_reentered = True
            raise AssertionError("account-wide consumed root entered another store")
        raise RedLivingDexControlledRecipeFailure(
            RedLivingDexSetupFailureReason.ROOT_UNAVAILABLE
        )

    result = run_red_living_dex_setup_recipe_campaign(
        second_store,
        second_plan,
        roots=second_roots,
        arm_factory=second_store_factory,
        meter=meter,
        claim_registry=registry,
    )

    assert first_root_reentered is False
    assert meter.root_claims == 15
    assert result.receipts[0].terminal.status.value == "interrupted"
    assert result.receipts[0].terminal.setup_controller_actions == 0
