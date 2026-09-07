from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import MacroPath
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
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_goal_manager import (
    RedGoalBindingOffer,
    RedGoalObservation,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedFreshGoalDestinationBinder,
    RedRoutedSemanticBoundary,
    RedRoutedSemanticGoalError,
    RedSemanticTransportRoute,
    build_red_routed_semantic_goal_composer,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticGoalError,
    RoutedSemanticGoalLimits,
)

ORIGIN = "a" * 64
PLANNER = "b" * 64
FRESH = "c" * 64


class _World:
    def __init__(self, *, at: tuple[int, int] = (2, 3)) -> None:
        self.map_id = 1
        self.at = at
        self.mode: str | None = None
        self.ready = True
        self.interruption: str | None = None
        self.frame_count = 0
        self.observation_frame_effect = 0
        self.events: list[str] = []

    def execute(self, action: MacroAction) -> MacroAction:
        self.events.append(f"action:{action.value}")
        self.frame_count += action.repeat
        if action.kind is MacroActionKind.MOVE:
            if action.value != "right" or self.at != (2, 3):
                raise AssertionError("test route received an unexpected movement")
            self.at = (2, 4)
        return action

    def observe(self) -> TraversalSnapshot:
        self.events.append("traversal_observe")
        self.frame_count += self.observation_frame_effect
        return TraversalSnapshot(
            self.map_id,
            self.at,
            self.ready,
            interruption=self.interruption,
            mode=self.mode,
        )


def _plan() -> RoutePlan:
    edge = LocalEdge((2, 4), "right")
    return RoutePlan(
        macro_path=MacroPath((1,), ()),
        start_at=(2, 3),
        start_mode=None,
        segments=(),
        terminal_approach=LocalPath(
            ((2, 3), (2, 4)),
            (edge,),
            (None, None),
        ),
        terminal_at=(2, 4),
        terminal_mode=None,
    )


def _observation(world: _World) -> RedGoalObservation:
    unused: Any = None
    return RedGoalObservation(
        raw=RawGameState(
            game_started=True,
            map_id=world.map_id,
            player_x=world.at[1],
            player_y=world.at[0],
            party_count=0,
            battle_state=0,
        ),
        game_state=GameState(GameMode.OVERWORLD, location="private-terminal"),
        party=unused,
        collection=unused,
        collection_observation=unused,
        evidence=unused,
        input_ready=world.ready,
        capture_item_count=0,
        recovery_item_count=0,
        free_storage_slots=0,
        immediate_capture_slots=0,
    )


def _transport(
    world: _World,
    actions: CountingExecutor,
    **overrides: object,
) -> RedSemanticTransportRoute:
    values: dict[str, object] = {
        "binding_ref": "private:red-transport",
        "origin_observation_sha256": ORIGIN,
        "planner_binding_sha256": PLANNER,
        "plan": _plan(),
        "actions": actions,
        "traversal_observer": world,
        "emulator": world,
    }
    values.update(overrides)
    return RedSemanticTransportRoute(**values)  # type: ignore[arg-type]


@dataclass
class _Provider:
    world: _World
    actions: CountingExecutor
    kind: GoalKind = GoalKind.RESUPPLY

    @property
    def emulator(self) -> _World:
        return self.world

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        self.world.events.append("provider_offer")
        assert observation.raw.player_x == 4
        assert observation.raw.player_y == 2
        before_actions = self.actions.actions_executed
        before_frames = self.world.frame_count

        def execute() -> GoalExecutionReport:
            self.world.events.append("destination_execute")
            self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=5))
            return GoalExecutionReport(
                self.actions.actions_executed - before_actions,
                self.world.frame_count - before_frames,
                {"semantic_destination": self.kind.value},
            )

        def verify(report: GoalExecutionReport) -> GoalVerification:
            self.world.events.append("destination_verify")
            if report.actions_executed != 1:
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref="private:red-resupply",
                kind=self.kind,
                estimated_effort=0.1,
                estimated_risk=0.01,
                execute=execute,
                verify=verify,
            )
        )


def _destination(
    world: _World,
    actions: CountingExecutor,
    *,
    observation_sha256: str = FRESH,
    provider: object | None = None,
) -> RedFreshGoalDestinationBinder:
    boundary = RedRoutedSemanticBoundary.from_plan(_plan())

    def observe_fresh() -> FreshRedGoalObservation:
        world.events.append("fresh_goal_observe")
        return FreshRedGoalObservation(
            observation_sha256,
            _observation(world),
            world.observe(),
        )

    return RedFreshGoalDestinationBinder(
        kind=GoalKind.RESUPPLY,
        boundary=boundary,
        observe_fresh=observe_fresh,
        provider=provider or _Provider(world, actions),  # type: ignore[arg-type]
    )


def test_red_composition_routes_then_binds_the_real_semantic_goal() -> None:
    world = _World()
    actions = CountingExecutor(world)
    transport = _transport(world, actions)
    destination = _destination(world, actions)
    composer = build_red_routed_semantic_goal_composer(
        binding_ref="private:red-route-then-resupply",
        transport=transport,
        destination=destination,
        estimated_effort=0.4,
        estimated_risk=0.1,
        limits=RoutedSemanticGoalLimits(10, 100),
    )
    binding = composer.binding()

    report = binding.execute()
    verdict = binding.verify(report)

    assert binding.kind is GoalKind.RESUPPLY
    assert report.actions_executed == 2
    assert report.frames_executed == 6
    assert verdict == GoalVerification.succeeded()
    assert world.at == (2, 4)
    assert world.events.index("action:right") < world.events.index("provider_offer")
    assert world.events.index("provider_offer") < world.events.index("destination_execute")
    assert world.events[-1] == "destination_verify"


@pytest.mark.parametrize("changed_origin", [False, True])
def test_departure_preparation_is_counted_and_cannot_replace_route_origin(changed_origin):
    world = _World()
    actions = CountingExecutor(world)

    def prepare():
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=5))
        if changed_origin:
            world.at = (9, 9)

    transport = _transport(world, actions, prepare_departure=prepare)
    binding = build_red_routed_semantic_goal_composer(
        binding_ref="private:prepared-route",
        transport=transport,
        destination=_destination(world, actions),
        estimated_effort=0.4,
        estimated_risk=0.1,
        limits=RoutedSemanticGoalLimits(10, 100),
    ).binding()
    assert actions.actions_executed == 0
    if changed_origin:
        with pytest.raises(RedRoutedSemanticGoalError, match="changed the route origin"):
            binding.execute()
        assert actions.actions_executed == 1
        assert "action:right" not in world.events
    else:
        report = binding.execute()
        assert report.actions_executed == 3 and report.frames_executed == 11
        assert binding.verify(report) == GoalVerification.succeeded()


def test_public_contracts_hide_route_destination_and_controller_identity() -> None:
    world = _World()
    actions = CountingExecutor(world)
    transport = _transport(world, actions)
    destination = _destination(world, actions)
    composer = build_red_routed_semantic_goal_composer(
        binding_ref="private:red-route-then-resupply",
        transport=transport,
        destination=destination,
        estimated_effort=0.4,
        estimated_risk=0.1,
        limits=RoutedSemanticGoalLimits(10, 100),
    )

    encoded = json.dumps(
        [
            transport.public_dict(),
            destination.public_dict(),
            composer.public_dict(),
        ],
        sort_keys=True,
    )

    for private in (
        "private:red-transport",
        "private:red-resupply",
        ORIGIN,
        PLANNER,
        FRESH,
        "right",
        "map_id",
    ):
        assert private not in encoded
    assert '"transport_is_policy_kind": false' in encoded
    assert '"raw_controller_sequence": false' in encoded


def test_transport_binding_requires_the_exact_live_route_start_without_effects() -> None:
    world = _World(at=(9, 9))
    actions = CountingExecutor(world)
    transport = _transport(world, actions)

    with pytest.raises(RedRoutedSemanticGoalError, match="live origin"):
        transport.route_binding()

    assert actions.actions_executed == 0
    assert world.frame_count == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"route_source": "profile"}, "not semantic-router derived"),
        ({"profile_direction_steps": 1}, "direction sequences"),
        ({"curriculum_direction_steps": 1}, "direction sequences"),
        ({"planner_binding_sha256": "not-a-hash"}, "planner binding"),
    ),
)
def test_transport_rejects_scripted_or_unauthenticated_routes(
    overrides: dict[str, object],
    message: str,
) -> None:
    world = _World()

    with pytest.raises(RedRoutedSemanticGoalError, match=message):
        _transport(world, CountingExecutor(world), **overrides)


def test_transport_verifier_fails_closed_after_terminal_drift() -> None:
    world = _World()
    actions = CountingExecutor(world)
    binding = _transport(world, actions).route_binding()

    report = binding.execute()
    world.at = (4, 3)

    assert binding.verify(report) == GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)


def test_transport_verifier_rejects_an_observer_with_frame_effects() -> None:
    world = _World()
    actions = CountingExecutor(world)
    binding = _transport(world, actions).route_binding()
    report = binding.execute()
    world.observation_frame_effect = 1

    assert binding.verify(report) == GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)


def test_fresh_observation_requires_red_and_traversal_coherence() -> None:
    world = _World(at=(2, 4))
    traversal = world.observe()
    world.at = (3, 4)

    with pytest.raises(RedRoutedSemanticGoalError, match="disagree"):
        FreshRedGoalObservation(FRESH, _observation(world), traversal)


def test_destination_rejects_a_fresh_state_outside_the_route_terminal() -> None:
    world = _World(at=(4, 3))
    actions = CountingExecutor(world)
    destination = _destination(world, actions)

    with pytest.raises(RedRoutedSemanticGoalError, match="route terminal"):
        destination()


def test_destination_preserves_a_provider_unavailability_reason() -> None:
    world = _World(at=(2, 4))
    actions = CountingExecutor(world)

    @dataclass
    class _Unavailable:
        kind: GoalKind = GoalKind.RESUPPLY

        def offer(self, _observation: RedGoalObservation) -> RedGoalBindingOffer:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.MISSING_RESOURCE,
            )

    offer = _destination(world, actions, provider=_Unavailable())()

    assert offer.binding is None
    assert offer.unavailable_reason is GoalUnavailableReason.MISSING_RESOURCE
    assert offer.kind is GoalKind.RESUPPLY


def test_destination_rejects_provider_kind_drift() -> None:
    world = _World(at=(2, 4))
    actions = CountingExecutor(world)

    @dataclass
    class _Drifted:
        kind: GoalKind = GoalKind.RESUPPLY

        def offer(self, _observation: RedGoalObservation) -> RedGoalBindingOffer:
            return RedGoalBindingOffer.unavailable(
                GoalKind.MANAGE_STORAGE,
                GoalUnavailableReason.MISSING_CAPABILITY,
            )

    destination = _destination(world, actions, provider=_Drifted())

    with pytest.raises(RedRoutedSemanticGoalError, match="different goal"):
        destination()


def test_composer_rejects_stale_origin_identity_after_successful_transport() -> None:
    world = _World()
    actions = CountingExecutor(world)
    transport = _transport(world, actions)
    destination = _destination(world, actions, observation_sha256=ORIGIN)
    binding = build_red_routed_semantic_goal_composer(
        binding_ref="private:red-route-then-resupply",
        transport=transport,
        destination=destination,
        estimated_effort=0.4,
        estimated_risk=0.1,
        limits=RoutedSemanticGoalLimits(10, 100),
    ).binding()

    with pytest.raises(RoutedSemanticGoalError, match="origin observation"):
        binding.execute()

    assert "destination_execute" not in world.events


def test_composer_rejects_separate_destination_controller_counters() -> None:
    world = _World()
    route_actions = CountingExecutor(world)
    destination_actions = CountingExecutor(world)
    transport = _transport(world, route_actions)
    destination = _destination(world, destination_actions)

    with pytest.raises(RedRoutedSemanticGoalError, match="action port"):
        build_red_routed_semantic_goal_composer(
            binding_ref="private:red-route-then-resupply",
            transport=transport,
            destination=destination,
            estimated_effort=0.4,
            estimated_risk=0.1,
            limits=RoutedSemanticGoalLimits(10, 100),
        )


def test_transport_and_composite_bindings_are_single_use() -> None:
    world = _World()
    actions = CountingExecutor(world)
    transport = _transport(world, actions)
    destination = _destination(world, actions)
    composer = build_red_routed_semantic_goal_composer(
        binding_ref="private:red-route-then-resupply",
        transport=transport,
        destination=destination,
        estimated_effort=0.4,
        estimated_risk=0.1,
        limits=RoutedSemanticGoalLimits(10, 100),
    )

    with pytest.raises(RedRoutedSemanticGoalError, match="already constructed"):
        transport.route_binding()
    binding = composer.binding()
    with pytest.raises(RoutedSemanticGoalError, match="already constructed"):
        composer.binding()
    report = binding.execute()
    with pytest.raises(RoutedSemanticGoalError, match="already executed"):
        binding.execute()
    assert binding.verify(report) == GoalVerification.succeeded()
