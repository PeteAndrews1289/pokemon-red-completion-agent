from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.global_router import (
    MacroEdge,
    MacroPath,
    MacroTransition,
)
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
from pokemon_red_completion.goal_manager_state import (
    CompletionProgress,
    GoalStateEvidence,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.local_router import LocalPath
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import (
    RedGoalBindingOffer,
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
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexConstructedOrigin,
    RedLivingDexObservedProviderOffer,
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
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedRoutedSemanticBoundary,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RouteSegment
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticBudgetCheckpoint,
)


def _sha(value: object) -> str:
    return hashlib.sha256(repr(value).encode("ascii")).hexdigest()


def _root_payloads(index: int) -> tuple[bytes, bytes]:
    state_bytes = f"root-state-{index:02d}".encode("ascii")
    envelope = CapturedProgressEnvelope(
        state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        checkpoint_id=f"root-{index:02d}",
        checkpoint_label="authenticated purpose-built recipe root",
        checkpoints_completed=0,
        checkpoints_total=1,
        verified_objective_ids=(),
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
    LivingDexOptionKind.EVOLVE: RedGoalMechanic.DIGLETT_EVOLUTION,
    LivingDexOptionKind.DEVELOP: RedGoalMechanic.BALANCED_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: RedGoalMechanic.BOX_SWITCH,
    LivingDexOptionKind.RESUPPLY: RedGoalMechanic.MART_RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: RedGoalMechanic.MIDGAME_STORY,
    LivingDexOptionKind.EXPLORE: RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
}


_OPTION_TO_PROVIDER = {
    LivingDexOptionKind.ACQUIRE: RedAreaSurveyGoalProvider,
    LivingDexOptionKind.EVOLVE: RedObservedGoalSkillProvider,
    LivingDexOptionKind.DEVELOP: RedProgressGoalProvider,
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
    if kind in {LivingDexOptionKind.ACQUIRE, LivingDexOptionKind.EXPLORE}:
        return {
            "source_id": f"wild:{token}",
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
    if kind is LivingDexOptionKind.MANAGE_STORAGE:
        return {
            "target_box_index": int(token[-1], 16) % 12,
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
                    "quantity": 1 + int(token[-1], 16) % 9,
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
    if kind in {LivingDexOptionKind.EVOLVE, LivingDexOptionKind.DEVELOP}:
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
        providers.append(
            RedLivingDexSetupProviderRecipe(
                option_kind=kind,
                provider_type=_OPTION_TO_PROVIDER[kind],
                profile=profile,
                expected_family_sha256=_expected_family_sha256(profile, kind, token),
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


class _Meter:
    def __init__(self) -> None:
        self.actions = 0
        self.frames = 0

    def checkpoint(self) -> RoutedSemanticBudgetCheckpoint:
        return RoutedSemanticBudgetCheckpoint(self.actions, self.frames)

    def spend(self, actions: int = 1, frames: int = 10) -> None:
        self.actions += actions
        self.frames += frames


class _Probe:
    def __init__(self) -> None:
        self.executions = 0
        self.verifications = 0

    def execute(self) -> GoalExecutionReport:
        self.executions += 1
        return GoalExecutionReport(0, 0, {})

    def verify(self, _report: GoalExecutionReport) -> GoalVerification:
        self.verifications += 1
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)


class _Runtime:
    def __init__(self, recipe: RedLivingDexSetupSlotRecipe, meter: _Meter) -> None:
        self.recipe = recipe
        self.meter = meter
        self.state_bytes = f"origin-{recipe.recipe_sha256}".encode("ascii")
        self.restores: list[bytes] = []
        self.route_calls: list[str] = []
        self.offer_calls: list[str] = []
        self.probe = _Probe()
        self.restore_spends = False
        self.offer_spends = False
        self.unavailable = False
        self.bad_family = False
        self.bad_root = False
        self.bad_root_state_bytes = False
        self.bad_candidate_restore = False
        self.bad_final_restore = False

    def construct_origin(
        self,
        recipe: RedLivingDexSetupSlotRecipe,
    ) -> RedLivingDexConstructedOrigin:
        if recipe.construction_route is not None:
            steps = len(recipe.construction_route.plan.steps)
            self.meter.spend(steps, 10 * steps)
        envelope = CapturedProgressEnvelope(
            state_sha256=hashlib.sha256(self.state_bytes).hexdigest(),
            checkpoint_id=f"origin-{recipe.recipe_sha256[:16]}",
            checkpoint_label="purpose-built recipe origin",
            checkpoints_completed=0,
            checkpoints_total=1,
            verified_objective_ids=(),
        )
        envelope_bytes = (
            json.dumps(
                envelope.to_dict(),
                ensure_ascii=True,
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        slots = build_red_living_dex_prospective_capture_plan().slots
        index = next(
            index for index, slot in enumerate(slots) if slot.slot_sha256 == recipe.slot_sha256
        )
        root_state_bytes, root_envelope_bytes = _root_payloads(index)
        if self.bad_root_state_bytes:
            root_state_bytes = b"wrong-root-state"
        return RedLivingDexConstructedOrigin(
            state_bytes=self.state_bytes,
            envelope_bytes=envelope_bytes,
            consumed_root_state_bytes=root_state_bytes,
            consumed_root_envelope_bytes=root_envelope_bytes,
            fresh=_fresh(recipe.origin_boundary),
            root_consumption_sha256=(
                _sha("wrong-root") if self.bad_root else recipe.root_consumption_sha256
            ),
            consumed_root_state_sha256=recipe.root_state_sha256,
            consumed_root_envelope_sha256=recipe.root_envelope_sha256,
            construction_route_sha256=(
                None
                if recipe.construction_route is None
                else recipe.construction_route.route_plan_sha256
            ),
        )

    def restore_origin(self, state_bytes: bytes) -> FreshRedGoalObservation:
        self.restores.append(state_bytes)
        if self.restore_spends:
            self.meter.spend()
        if self.bad_candidate_restore and len(self.restores) == 1:
            return _fresh(self.recipe.origin_boundary, capture_item_count=1)
        if self.bad_final_restore and len(self.restores) == len(self.recipe.providers) + 1:
            boundary = RedRoutedSemanticBoundary(
                self.recipe.origin_boundary.map_id,
                (2, 3),
                None,
            )
            return _fresh(boundary)
        return _fresh(self.recipe.origin_boundary)

    def execute_route(
        self,
        route: RedLivingDexSetupRouteRecipe,
    ) -> FreshRedGoalObservation:
        self.route_calls.append(route.recipe_sha256)
        self.meter.spend(len(route.plan.steps), 10 * len(route.plan.steps))
        return _fresh(route.terminal_boundary)

    def offer_provider(
        self,
        recipe: RedLivingDexSetupProviderRecipe,
        fresh: FreshRedGoalObservation,
    ) -> RedLivingDexObservedProviderOffer:
        self.offer_calls.append(recipe.recipe_sha256)
        if self.offer_spends:
            self.meter.spend()
        if self.unavailable:
            offer = RedGoalBindingOffer.unavailable(
                recipe.goal_kind,
                GoalUnavailableReason.MISSING_CAPABILITY,
            )
        else:
            spec = next(item for item in recipe.profile.providers if item.kind is recipe.goal_kind)
            token = recipe.profile.profile_id.removeprefix("recipe-")
            binding = ExecutableGoalBinding(
                binding_ref=(
                    f"{_semantic_binding_ref(recipe.option_kind, token)}"
                    f":profile-{recipe.profile.profile_sha256}:"
                    f"config-{spec.configuration_sha256}"
                ),
                kind=recipe.goal_kind,
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=self.probe.execute,
                verify=self.probe.verify,
            )
            if self.bad_family:
                binding = replace(
                    binding,
                    binding_ref=(
                        f"pokemon.red:test-family:wrong:profile-{recipe.profile.profile_sha256}:"
                        f"config-{spec.configuration_sha256}"
                    ),
                )
            offer = RedGoalBindingOffer.available(binding)
        del fresh
        return RedLivingDexObservedProviderOffer(
            provider_type=recipe.provider_type,
            profile=recipe.profile,
            offer=offer,
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
    plan = build_red_living_dex_setup_recipe_plan(_recipes())
    assert plan.public_dict() == {
        "claim_before_controller_input": True,
        "development_slots": 5,
        "learner_effects": 0,
        "option_count": 45,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "retry_after_controller_input": False,
        "routed_option_count": 26,
        "same_origin_fork_required": True,
        "schema": "pokemon.red.private-living-dex-setup-recipe-plan.v1",
        "slot_count": 15,
        "train_slots": 10,
    }
    with pytest.raises(RedLivingDexSetupRecipeError, match="reused"):
        build_red_living_dex_setup_recipe_plan(_recipes(alias_last_location=True))


def test_recipe_plan_rejects_expected_family_overlap_before_controller_input() -> None:
    recipes = list(_recipes())
    train_acquire = recipes[0].providers[0]
    development = recipes[10]
    development_acquire = replace(
        development.providers[0],
        expected_family_sha256=train_acquire.expected_family_sha256,
    )
    recipes[10] = replace(
        development,
        providers=(development_acquire, *development.providers[1:]),
    )

    with pytest.raises(RedLivingDexSetupRecipeError, match="families overlap"):
        build_red_living_dex_setup_recipe_plan(tuple(recipes))


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
    runtime = _Runtime(recipe, meter)

    result = validate_red_living_dex_setup_recipe(
        slot,
        recipe,
        runtime=runtime,
        meter=meter,
    )

    assert len(runtime.restores) == 4
    assert all(item == runtime.state_bytes for item in runtime.restores)
    assert len(runtime.route_calls) == 1
    assert len(runtime.offer_calls) == 3
    assert runtime.probe.executions == 0
    assert runtime.probe.verifications == 0
    assert result.origin_restore_count == 4
    assert result.attestation.setup_controller_actions == 1
    assert result.attestation.setup_emulator_frames == 10
    assert result.binding.location_sha256 == recipe.location_sha256
    assert result.binding.available_family_sha256s == tuple(
        item.family_sha256 for item in result.fork_proofs
    )
    assert result.public_dict()["provider_executions"] == 0
    assert result.public_dict()["learner_labels"] == 0


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
    runtime = _Runtime(recipe, meter)

    result = validate_red_living_dex_setup_recipe(
        slot,
        recipe,
        runtime=runtime,
        meter=meter,
    )

    assert result.attestation.setup_controller_actions == 2
    assert result.attestation.setup_emulator_frames == 20
    assert len(runtime.route_calls) == 1


def test_validated_capture_private_round_trip_retains_exact_repeatable_bytes() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    runtime = _Runtime(recipe, meter)
    original = validate_red_living_dex_setup_recipe(
        slot,
        recipe,
        runtime=runtime,
        meter=meter,
    )

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
    ),
)
def test_validated_capture_private_restore_rejects_tampering(
    mutation: Any,
    message: str,
) -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    runtime = _Runtime(recipe, meter)
    result = validate_red_living_dex_setup_recipe(
        slot,
        recipe,
        runtime=runtime,
        meter=meter,
    )
    document = deepcopy(result.private_dict())
    mutation(document)

    with pytest.raises(RedLivingDexSetupRecipeError, match=message):
        restore_red_living_dex_validated_setup_capture(document)


@pytest.mark.parametrize(
    ("flag", "message"),
    (
        ("restore_spends", "origin restore changed"),
        ("offer_spends", "provider offer changed"),
        ("unavailable", "available offer"),
        ("bad_family", "frozen recipe"),
        ("bad_root", "authenticated root recipe"),
        ("bad_root_state_bytes", "source state digest"),
        ("bad_candidate_restore", "captured decision state"),
        ("bad_final_restore", "final restored origin boundary differs"),
    ),
)
def test_same_root_validation_fails_closed_on_boundary_mutations(
    flag: str,
    message: str,
) -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[0]
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    meter = _Meter()
    runtime = _Runtime(recipe, meter)
    setattr(runtime, flag, True)

    with pytest.raises(RedLivingDexSetupRecipeError, match=message):
        validate_red_living_dex_setup_recipe(
            slot,
            recipe,
            runtime=runtime,
            meter=meter,
        )


def test_recipe_rejects_a_profile_whose_coordinate_does_not_match_terminal() -> None:
    recipe = _recipe(0, origin_map=int(MapId.ROUTE_1))
    acquire = recipe.providers[0]
    mismatched_profile = _profile(
        LivingDexOptionKind.ACQUIRE,
        RedRoutedSemanticBoundary(int(MapId.ROUTE_1), (9, 8), None),
        "mismatch",
    )
    wrong = replace(acquire, profile=mismatched_profile)
    with pytest.raises(RedLivingDexSetupRecipeError, match="provider profile"):
        replace(recipe, providers=(wrong, *recipe.providers[1:]))


def test_recipe_campaign_claims_all_slots_and_recovers_without_runtime_reentry(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes())
    store = _store(tmp_path)
    meter = _Meter()
    calls: list[str] = []

    def factory(recipe: RedLivingDexSetupSlotRecipe) -> _Runtime:
        ordinal = plan.recipes.index(recipe)
        episode_id = f"red-living-dex-recipe-{ordinal:02d}-{recipe.recipe_sha256[:20]}"
        assert store.inspect_episode_state(episode_id).status == "partial"
        sealed = store.find_sealed_record(
            RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID,
            expected_kind=RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND,
        )
        assert sealed is not None
        assert sealed.read()["recipe_plan_sha256"] == plan.plan_sha256
        calls.append(recipe.recipe_sha256)
        return _Runtime(recipe, meter)

    first = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        runtime_factory=factory,
        meter=meter,
    )

    assert len(calls) == 15
    assert first.inventory_qualification_available is True
    assert first.qualified_inventory().public_dict()["status_counts"] == {
        "complete": 15,
        "failed": 0,
        "interrupted": 0,
    }
    assert first.public_dict()["terminal_status_counts"] == {
        "complete": 15,
        "failed": 0,
        "interrupted": 0,
    }
    before = meter.checkpoint()

    def forbidden_factory(_recipe: RedLivingDexSetupSlotRecipe) -> _Runtime:
        raise AssertionError("a recovered recipe must not reenter its runtime")

    recovered = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        runtime_factory=forbidden_factory,
        meter=meter,
    )

    assert meter.checkpoint() == before
    assert all(
        item.disposition is RedLivingDexSetupRecipeDisposition.RECOVERED_COMPLETE
        for item in recovered.receipts
    )
    assert recovered.qualified_inventory().qualification_sha256 == (
        first.qualified_inventory().qualification_sha256
    )


def test_recipe_campaign_never_retries_a_claimed_validation_failure(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes())
    store = _store(tmp_path)
    meter = _Meter()
    first_calls: list[str] = []

    def failing_factory(recipe: RedLivingDexSetupSlotRecipe) -> _Runtime:
        first_calls.append(recipe.recipe_sha256)
        runtime = _Runtime(recipe, meter)
        runtime.unavailable = True
        return runtime

    with pytest.raises(RedLivingDexSetupRecipeCampaignError, match="durable claim"):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            runtime_factory=failing_factory,
            meter=meter,
        )
    assert first_calls == [plan.recipes[0].recipe_sha256]

    resumed_calls: list[str] = []

    def resumed_factory(recipe: RedLivingDexSetupSlotRecipe) -> _Runtime:
        resumed_calls.append(recipe.recipe_sha256)
        return _Runtime(recipe, meter)

    resumed = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        runtime_factory=resumed_factory,
        meter=meter,
    )

    assert resumed_calls == [item.recipe_sha256 for item in plan.recipes[1:]]
    assert resumed.receipts[0].terminal.status.value == "failed"
    assert resumed.receipts[0].terminal.retry_allowed is False
    assert resumed.receipts[0].disposition is (RedLivingDexSetupRecipeDisposition.RECOVERED_FAILED)
    assert resumed.inventory_qualification_available is True


def test_recipe_campaign_continues_after_a_sanitized_controlled_failure(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes())
    store = _store(tmp_path)
    meter = _Meter()
    calls = 0

    def factory(recipe: RedLivingDexSetupSlotRecipe) -> _Runtime:
        nonlocal calls
        calls += 1
        if recipe is plan.recipes[0]:
            raise RedLivingDexControlledRecipeFailure("root_unavailable")
        return _Runtime(recipe, meter)

    run = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        runtime_factory=factory,
        meter=meter,
    )

    assert calls == 15
    assert run.receipts[0].terminal.reason_code == "root_unavailable"
    assert run.receipts[0].disposition is (RedLivingDexSetupRecipeDisposition.EXECUTED_FAILED)
    assert run.receipts[0].terminal.setup_controller_actions == 0
    assert run.inventory_qualification_available is True


def test_recipe_campaign_counts_runtime_factory_effects_and_fails_closed(
    tmp_path: Path,
) -> None:
    plan = build_red_living_dex_setup_recipe_plan(_recipes())
    store = _store(tmp_path)
    meter = _Meter()

    def actionful_factory(recipe: RedLivingDexSetupSlotRecipe) -> _Runtime:
        meter.spend()
        return _Runtime(recipe, meter)

    with pytest.raises(RedLivingDexSetupRecipeCampaignError, match="durable claim"):
        run_red_living_dex_setup_recipe_campaign(
            store,
            plan,
            runtime_factory=actionful_factory,
            meter=meter,
        )

    def forbidden_first(recipe: RedLivingDexSetupSlotRecipe) -> _Runtime:
        assert recipe is not plan.recipes[0]
        return _Runtime(recipe, meter)

    recovered = run_red_living_dex_setup_recipe_campaign(
        store,
        plan,
        runtime_factory=forbidden_first,
        meter=meter,
    )
    assert recovered.receipts[0].terminal.setup_controller_actions == 2
    assert recovered.receipts[0].terminal.retry_allowed is False
