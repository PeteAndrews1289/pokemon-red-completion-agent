"""Explicit Surf integration exercises the actual metered field-menu compiler."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_gen1_field_moves import MenuWorld, surf_state
from test_red_collection_cut import cut_plan
from test_red_living_dex_wild_corridor import _local_discovery_profile

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_field_moves import ALWAYS_ON_BIKE_MASK, Gen1FieldMovePort
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import OverworldMovementMode
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    _thaw,
    bind_capture_surf_profile,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_resource_goal_router import (
    RedResourceGoalRouter,
    RedResourceGoalRoutingError,
    _supported_plan,
    _surf_enabled,
    collection_field_capabilities,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    RedRoutedSemanticGoalError,
    RedSemanticTransportRoute,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan


def surf_plan(*, map_id=0, entry="surf:right", start_mode="land"):
    return RoutePlan(
        MacroPath((map_id,), ()), (17, 4), start_mode, (),
        LocalPath(((17, 4), (17, 5), (17, 6)), (
            LocalEdge((17, 5), entry, action_kind=MacroActionKind.FIELD_MOVE,
                      requirements=frozenset({"move:surf"}),
                      required_mode="land", result_mode="water"),
            LocalEdge((17, 6), "right", required_mode="water", result_mode="land"),
        ), (start_mode, "water", "land")), (17, 6), "land",
    )


def test_surf_is_explicit_idempotent_and_does_not_grant_cut():
    old = _local_discovery_profile()
    new = bind_capture_surf_profile(old)
    assert new.profile_sha256 != old.profile_sha256
    assert bind_capture_surf_profile(new) == new
    assert "surf_transport" not in old.providers[0].parameters
    assert _surf_enabled(new.providers[0])
    assert "cut_transport" not in new.providers[0].parameters
    assert not _supported_plan(surf_plan())
    assert not _supported_plan(surf_plan(), allow_cut=True)
    assert _supported_plan(surf_plan(), allow_surf=True)
    assert not _supported_plan(cut_plan(), allow_surf=True)


@pytest.mark.parametrize("value", [1, 0, "true", None, [], {}])
def test_surf_flag_is_strict_boolean(value):
    profile = _local_discovery_profile()
    with pytest.raises(RedGoalContextProfileError, match="Surf transport"):
        parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id=profile.profile_id,
            providers=tuple((s.kind, s.mechanic, {
                **_thaw(s.parameters), **({"surf_transport":value} if i == 0 else {}),
            }) for i, s in enumerate(profile.providers)),
        ))


def test_surf_false_stays_closed_and_other_providers_cannot_gain_it():
    profile = _local_discovery_profile()
    specs = list(profile.providers)
    disabled = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple((s.kind,s.mechanic,{
            **_thaw(s.parameters), **({"surf_transport":False} if i == 0 else {}),
        }) for i,s in enumerate(specs)),
    ))
    assert not _surf_enabled(disabled.providers[0])
    assert not _surf_enabled(SimpleNamespace(
        mechanic=specs[1].mechanic, parameters={"surf_transport":True},
    ))


@pytest.mark.parametrize("action", [
    "surf", "surf:northeast", "strength:activate", "fly:pallet_town",
])
def test_surf_does_not_grant_arbitrary_macros(action):
    assert not _supported_plan(surf_plan(entry=action), allow_surf=True)


def test_unmodeled_current_puzzle_stays_closed():
    assert not _supported_plan(surf_plan(map_id=0xA2), allow_surf=True)
    assert not _supported_plan(surf_plan(start_mode="water"), allow_surf=True)


def test_plain_arrow_cannot_enter_water():
    plan = surf_plan()
    local = plan.terminal_approach
    forged = replace(plan, terminal_approach=replace(local, edges=(
        replace(local.edges[0], action="right", action_kind=MacroActionKind.MOVE), local.edges[1],
    )))
    assert not _supported_plan(forged, allow_surf=True)


class SurfScene(MenuWorld):
    frame_count = 0

    def execute(self, action):
        self.frame_count += action.repeat
        if (self.stage == "field" and self.mode is OverworldMovementMode.SURFING
                and action.kind is MacroActionKind.MOVE and action.value == "right"):
            self.actions.append(action)
            self.raw = replace(self.raw, player_x=6)
            self.mode = OverworldMovementMode.WALKING
            return action
        return super().execute(action)

    def observe(self):
        return TraversalSnapshot(
            self.raw.map_id, (self.raw.player_y, self.raw.player_x), True,
            mode=self.mode.traversal_mode,
            capabilities=collection_field_capabilities(
                self, self.raw, allow_cut=False, allow_surf=True,
            ),
        )


def transport(scene, actions=None):
    actions = actions if actions is not None else CountingExecutor(scene)
    return RedSemanticTransportRoute(
        "surf-test", "a"*64, "b"*64, surf_plan(), actions, scene, scene,
        field_actions=Gen1FieldMovePort(actions, scene, scene),
    )


def test_real_surf_menu_is_counted_and_returns_to_land():
    scene = SurfScene()
    route = transport(scene)
    binding = route.route_binding()
    assert not scene.actions and scene.frame_count == 0
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert report.evidence["verified_surfs"] == 1
    assert report.evidence["verified_cuts"] == 0
    assert report.actions_executed == len(scene.actions) > 2
    assert report.frames_executed == scene.frame_count > 0
    assert scene.mode is OverworldMovementMode.WALKING and scene.raw.player_x == 6
    assert all(a.kind is not MacroActionKind.FIELD_MOVE for a in scene.actions)


@pytest.mark.parametrize("change", [{"badge_bits":0}, {"party_hp":(15,0)},
                                         {"party_moves":((33,),(33,))}])
def test_lost_badge_or_holder_rejects_before_input(change):
    scene = SurfScene()
    binding = transport(scene).route_binding()
    scene.raw = replace(scene.raw, **change)
    with pytest.raises(RedRoutedSemanticGoalError, match="origin|capability"):
        binding.execute()
    assert not scene.actions and scene.frame_count == 0


def test_live_title_permission_loss_rejects_before_input():
    scene = SurfScene()
    binding = transport(scene).route_binding()
    scene.status_flags_6 = ALWAYS_ON_BIKE_MASK
    with pytest.raises(RedRoutedSemanticGoalError, match="origin|capability"):
        binding.execute()
    assert not scene.actions and scene.frame_count == 0


def test_primitive_budget_cannot_be_bypassed_by_surf_macro():
    from pokemon_red_completion.goal_manager_composition_qualification import (
        CompositionActionBudgetExhausted,
        HardCompositionActionLimiter,
    )
    scene = SurfScene()
    port = CountingExecutor(HardCompositionActionLimiter(
        scene, maximum_actions_per_decision=3, maximum_episode_actions=3,
    ))
    route = transport(scene, port)
    with pytest.raises(CompositionActionBudgetExhausted):
        route.route_binding().execute()
    assert len(scene.actions) == 3 and route.field_actions.receipts == []


def test_replan_and_retarget_preserve_only_declared_surf():
    from test_red_living_dex_wild_corridor import _graph, _terrain

    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )
    world = SimpleNamespace(replanner=lambda: lambda _: surf_plan())
    router = RedResourceGoalRouter(None, None, world)
    with pytest.raises(RedResourceGoalRoutingError, match="unsupported"):
        router._replan(None, allow_cut=True)
    assert router._replan(None, allow_surf=True) == surf_plan()
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    profile = bind_capture_surf_profile(_local_discovery_profile())
    moved = retarget_red_wild_profile(profile, corridor)
    assert moved.providers[0].parameters["surf_transport"] is True


def test_surf_only_port_has_the_original_primitive_meter():
    scene = SurfScene()
    count = CountingExecutor(scene)
    router = RedResourceGoalRouter(SimpleNamespace(reader=scene, emulator=scene), count,
                                   SimpleNamespace(rules=SimpleNamespace(cut_block_swaps=())))
    spec = bind_capture_surf_profile(_local_discovery_profile()).providers[0]
    assert router.field_actions_for(spec).delegate is count
    assert collection_field_capabilities(
        scene, surf_state(), allow_cut=False, allow_surf=False,
    ) == frozenset()
