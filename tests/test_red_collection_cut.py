"""Discriminating Cut integration tests; no ROM or saved-game inputs."""
from dataclasses import replace

import pytest
from test_gen1_field_moves import CutMenuWorld, cut_state
from test_red_living_dex_wild_corridor import _local_discovery_profile

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort
from pokemon_red_completion.gen1_traversal import cut_capabilities
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    _thaw,
    bind_capture_cut_profile,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_resource_goal_router import _cut_enabled, _supported_plan
from pokemon_red_completion.red_routed_semantic_goal import (
    RedRoutedSemanticGoalError,
    RedSemanticTransportRoute,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan


def profile_with_cut(value):
    profile = _local_discovery_profile()
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id,
        providers=tuple(
            (s.kind, s.mechanic, {
                **_thaw(s.parameters), **({"cut_transport": value}
                    if s.kind is GoalKind.ACQUIRE_SPECIES else {}),
            }) for s in profile.providers
        ),
    ))


def test_cut_is_prospective_explicit_and_idempotent():
    before = _local_discovery_profile()
    original = before.profile_sha256
    after = bind_capture_cut_profile(before)
    assert after.profile_sha256 != original
    assert before.profile_sha256 == original
    assert not any("cut_transport" in s.parameters for s in before.providers)
    assert bind_capture_cut_profile(after) == after
    assert sum(_cut_enabled(s) for s in after.providers) == 1
    assert not any(_cut_enabled(s) for s in profile_with_cut(False).providers)


@pytest.mark.parametrize("value", [1, 0, "true", None, [], {}])
def test_cut_flag_rejects_non_boolean(value):
    with pytest.raises(RedGoalContextProfileError, match="Cut transport"):
        profile_with_cut(value)


def cut_plan(action="cut:right", mode="land"):
    return RoutePlan(
        MacroPath((0,), ()), (0, 1), mode, (),
        LocalPath(
            ((0, 1), (0, 1), (0, 2)),
            (LocalEdge((0, 1), action, action_kind=MacroActionKind.FIELD_MOVE),
             LocalEdge((0, 2), "right")),
            (mode, mode, mode),
        ), (0, 2), mode,
    )


@pytest.mark.parametrize("action", ["surf:right", "strength:activate", "fly:pallet_town",
                                         "cut", "cut:northeast"])
def test_cut_permission_does_not_open_other_field_actions(action):
    assert not _supported_plan(cut_plan(action), allow_cut=True)


def test_cut_plan_needs_explicit_option_and_stays_on_land():
    assert not _supported_plan(cut_plan())
    assert _supported_plan(cut_plan(), allow_cut=True)
    assert not _supported_plan(cut_plan(mode="water"), allow_cut=True)


class Scene(CutMenuWorld):
    frame_count = 0

    def execute(self, action):
        self.frame_count += action.repeat
        if (self.stage == "field" and self.tile_in_front == 0x2C
                and action.kind is MacroActionKind.MOVE and action.value == "right"):
            self.actions.append(action)
            self.raw = replace(self.raw, player_x=self.raw.player_x + 1)
            return action
        return super().execute(action)

    def observe(self):
        return TraversalSnapshot(
            self.raw.map_id, (self.raw.player_y, self.raw.player_x), True,
            mode="land", capabilities=cut_capabilities(self.raw),
        )


def transport(scene, actions=None):
    actions = actions if actions is not None else CountingExecutor(scene)
    field = Gen1FieldMovePort(actions, scene, scene, cut_block_swaps={0x35: 0x4C})
    return RedSemanticTransportRoute(
        "cut-test", "a" * 64, "b" * 64, cut_plan(), actions, scene, scene,
        field_actions=field,
    )


def test_real_field_macro_expands_into_counted_inputs_then_walks_and_verifies():
    scene = Scene()
    route = transport(scene)
    binding = route.route_binding()
    assert scene.actions == [] and scene.frame_count == 0
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert report.evidence["verified_cuts"] == 1
    assert report.actions_executed == len(scene.actions) > 2
    assert report.frames_executed == scene.frame_count > 0
    assert all(a.kind is not MacroActionKind.FIELD_MOVE for a in scene.actions)
    assert scene.raw.player_x == 2
    assert scene.raw.party_hp == (25,)
    assert scene.blocks.rows == ((0x01, 0x4C),)


@pytest.mark.parametrize("change", [
    {"badge_bits": 0}, {"party_hp": (0,)}, {"party_moves": ((33,),)},
    {"party_moves": ()},
])
def test_lost_capability_after_binding_rejects_before_any_input(change):
    scene = Scene()
    route = transport(scene)
    binding = route.route_binding()
    scene.raw = replace(scene.raw, **change)
    with pytest.raises(RedRoutedSemanticGoalError, match="origin|capability"):
        binding.execute()
    assert scene.actions == [] and scene.frame_count == 0


def test_field_port_cannot_bypass_controller_meter():
    scene = Scene()
    route = transport(scene)
    route.field_actions.delegate = CountingExecutor(scene)
    with pytest.raises(RedRoutedSemanticGoalError, match="meter"):
        route.__post_init__()


def test_cut_capability_uses_holder_not_species_or_unrelated_fainted_member():
    raw = replace(cut_state(), party_count=2, party_hp=(0, 10),
                  party_moves=((33,), (15,)))
    assert cut_capabilities(raw) == frozenset({"move:cut"})
    assert cut_capabilities(replace(raw, party_hp=(10, 0))) == frozenset()


def test_expanded_cut_inputs_cannot_bypass_primitive_action_budget():
    from pokemon_red_completion.goal_manager_composition_qualification import (
        CompositionActionBudgetExhausted,
        HardCompositionActionLimiter,
    )
    scene = Scene()
    limiter = HardCompositionActionLimiter(
        scene, maximum_actions_per_decision=3, maximum_episode_actions=3,
    )
    route = transport(scene, CountingExecutor(limiter))
    binding = route.route_binding()
    with pytest.raises(CompositionActionBudgetExhausted):
        binding.execute()
    assert len(scene.actions) == 3
    assert route.field_actions.cut_receipts == []


def test_retargeting_keeps_cut_option_without_mutating_old_profile():
    from test_red_living_dex_wild_corridor import _graph, _terrain

    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )
    old = _local_discovery_profile()
    bound = bind_capture_cut_profile(old)
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget("wild:Route2:grass"), _terrain(), _graph(),
    )
    moved = retarget_red_wild_profile(bound, corridor)
    assert moved.providers[0].parameters["cut_transport"] is True
    assert "cut_transport" not in retarget_red_wild_profile(old, corridor).providers[0].parameters


def test_router_port_uses_decoded_swap_table_and_original_meter():
    from types import SimpleNamespace

    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
    scene = Scene()
    counted = CountingExecutor(scene)
    spec = bind_capture_cut_profile(_local_discovery_profile()).providers[0]
    world = SimpleNamespace(rules=SimpleNamespace(cut_block_swaps=(
        SimpleNamespace(before=0x35, after=0x4C),
        SimpleNamespace(before=0x51, after=0x61),
    )))
    router = RedResourceGoalRouter(
        SimpleNamespace(reader=scene, emulator=scene), counted, world,
    )
    port = router.field_actions_for(spec)
    assert port.delegate is counted
    assert port.cut_block_swaps == {0x35: 0x4C, 0x51: 0x61}
    assert router.field_actions_for(_local_discovery_profile().providers[0]) is None
    assert scene.actions == []


def test_replans_keep_cut_scope_without_allowing_surf():
    from types import SimpleNamespace

    from pokemon_red_completion.red_resource_goal_router import (
        RedResourceGoalRouter,
        RedResourceGoalRoutingError,
    )
    world = SimpleNamespace(replanner=lambda: lambda _: cut_plan())
    router = RedResourceGoalRouter(None, None, world)
    with pytest.raises(RedResourceGoalRoutingError, match="unsupported"):
        router._replan(None)
    assert router._replan(None, allow_cut=True) == cut_plan()
    world.replanner = lambda: lambda _: cut_plan("surf:right")
    with pytest.raises(RedResourceGoalRoutingError, match="unsupported"):
        router._replan(None, allow_cut=True)
