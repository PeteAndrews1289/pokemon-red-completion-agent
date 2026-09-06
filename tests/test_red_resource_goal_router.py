from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_skills import _adapter, _AreaExecutor, _MartPort, _raw, _Reader

import pokemon_red_completion.red_resource_goal_router as routing
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalOpportunityEnumerator
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedGoalSkillAvailability,
    RedMartPurchase,
    RedMartResupplyGoalProvider,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError


class _Port(_MartPort):
    def __init__(self, reader):
        super().__init__(reader)
        self.spend_on_route = False
        self.mode = "land"

    def execute(self, action):
        if action.kind is MacroActionKind.MOVE and action.value == "right":
            self.reader.raw = replace(
                self.reader.raw,
                player_x=4,
                player_money=0 if self.spend_on_route else self.reader.raw.player_money,
            )
        return super().execute(action)

    def observe(self):
        raw = self.reader.raw
        return TraversalSnapshot(
            raw.map_id, (raw.player_y, raw.player_x), self.reader.ready, mode=self.mode
        )


class _World:
    rom = b"synthetic cartridge is never decoded"

    def __init__(self):
        self.plans = []
        self.fail = False
        self.action = "right"
        self.action_kind = MacroActionKind.MOVE

    def plan_feasible_to_map(self, start, goal_map, *, goal_at):
        self.plans.append((start, goal_map, goal_at))
        if self.fail:
            raise RoutePlanningError("synthetic blocked route")
        return RoutePlan(
            macro_path=MacroPath((start.map_id,), ()),
            start_at=start.at,
            segments=(),
            terminal_approach=LocalPath(
                (start.at, goal_at),
                (LocalEdge(goal_at, self.action, action_kind=self.action_kind),),
                ("land", "land"),
            ),
            terminal_at=goal_at,
            start_mode="land",
            terminal_mode="land",
        )

    def replanner(self):
        return lambda request: self.plan_feasible_to_map(
            request.current,
            request.original_plan.terminal_map,
            goal_at=request.original_plan.terminal_at,
        )


@pytest.fixture
def fixture(monkeypatch):
    reader = _Reader(
        raw=replace(
            _raw(poke_balls=0, hyper_potions=10),
            map_id=int(MapId.VIRIDIAN_MART),
            player_x=3,
            player_y=2,
            player_money=5_000,
        ),
        ready=True,
    )
    port = _Port(reader)
    actions = CountingExecutor(port)
    adapter = _adapter(reader)
    provider = RedMartResupplyGoalProvider(
        MapId.VIRIDIAN_MART,
        4,
        2,
        "up",
        (RedMartPurchase(0, ItemId.POKE_BALL, 10, 200),),
        actions,
        reader,
        port,
        adapter,
        wait_frames=1,
    )
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="synthetic-resource-chain",
            providers=(
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
                (
                    GoalKind.RESUPPLY,
                    RedGoalMechanic.MART_RESUPPLY,
                    {
                        "map_id": int(MapId.VIRIDIAN_MART),
                        "player_x": 4,
                        "player_y": 2,
                        "interaction_direction": "up",
                        "purchases": [
                            {
                                "absolute_index": 0,
                                "item_id": int(ItemId.POKE_BALL),
                                "quantity": 10,
                                "unit_price": 200,
                            }
                        ],
                    },
                ),
                (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
            ),
        )
    )
    runtime = SimpleNamespace(
        adapter=adapter,
        reader=reader,
        emulator=port,
        profile=profile,
        enumerator=lambda _actions: RedGoalOpportunityEnumerator((provider,)),
        provider_for=lambda kind, _actions: provider,
    )
    world = _World()
    monkeypatch.setattr(routing, "Gen1TraversalObserver", lambda *_a, **_k: port)
    monkeypatch.setattr(routing, "Gen1TrainerSightProjector", lambda *_a: None)

    def buy(received_actions, _emulator, _timing, *, item, quantity, target_bag_quantity, **_):
        inventory = dict(reader.raw.bag_items)
        inventory[item] = target_bag_quantity
        reader.raw = replace(
            reader.raw,
            bag_items=tuple(inventory.items()),
            bag_item_ids=tuple(inventory),
            player_money=reader.raw.player_money - 200 * quantity,
        )
        received_actions.execute(MacroAction(MacroActionKind.WAIT))

    monkeypatch.setattr("pokemon_red_completion.red_goal_skills._buy_mart_item", buy)
    monkeypatch.setattr("pokemon_red_completion.red_goal_skills._close_menus", lambda *_a: None)
    router = routing.RedResourceGoalRouter(runtime, actions, world)
    return SimpleNamespace(
        reader=reader,
        port=port,
        actions=actions,
        adapter=adapter,
        provider=provider,
        world=world,
        router=router,
    )


def _supply(bindings):
    return next(item for item in bindings.opportunities if item.kind is GoalKind.RESUPPLY)


@pytest.mark.parametrize("at_clerk", [False, True])
def test_quotes_bind_actual_prices_funds_and_reserves_without_actions(fixture, at_clerk):
    f = fixture
    f.router.quote_resource_costs = True
    if at_clerk:
        f.reader.raw = replace(f.reader.raw, player_x=4)
    before = f.port.frame_count
    result = f.router.enumerate(f.adapter.observe())
    supply = _supply(result)
    quote = supply.resource_quote
    assert quote.available_funds == 5_000
    assert quote.purchase_cost == 2_000
    assert quote.reserves[0].available == 0
    assert quote.reserves[0].purchased == 10
    assert quote.cost_units == pytest.approx(0.4)
    assert result.require(supply.binding_ref).resource_quote == quote
    assert f.actions.actions_executed == 0 and f.port.frame_count == before
    f.reader.raw = replace(f.reader.raw, player_money=2_500)
    refreshed = f.router.enumerate(f.adapter.observe())
    changed_supply = _supply(refreshed)
    changed = changed_supply.resource_quote
    assert changed.available_funds == 2_500 and changed.cost_units == pytest.approx(0.8)
    with pytest.raises(routing.RedResourceGoalRoutingError, match="quote changed"):
        result.require(supply.binding_ref).execute()
    assert f.actions.actions_executed == 0 and f.port.frame_count == before
    report = refreshed.require(changed_supply.binding_ref).execute()
    assert refreshed.require(changed_supply.binding_ref).verify(report).status.value == "succeeded"
    assert f.reader.raw.player_money == 500
    assert dict(f.reader.raw.bag_items)[int(ItemId.POKE_BALL)] == 10


def test_legacy_router_keeps_quotes_absent(fixture):
    supply = _supply(fixture.router.enumerate(fixture.adapter.observe()))
    assert supply.resource_quote is None
    assert "resource_quote" not in supply.policy_dict()


def test_remote_supply_uses_actual_route_and_fresh_mart_then_disappears(fixture):
    f = fixture
    before = f.port.frame_count
    result = f.router.enumerate(f.adapter.observe())
    supply = _supply(result)
    assert f.actions.actions_executed == 0 and f.port.frame_count == before
    assert len(f.world.plans) == 1
    assert f.world.plans[0][0].at == (2, 3)
    assert f.world.plans[0][2] == (2, 4)
    binding = result.require(supply.binding_ref)
    report = binding.execute()
    assert binding.verify(report).status.value == "succeeded"
    assert f.reader.raw.player_x == 4
    assert f.reader.raw.player_money == 3_000
    assert dict(f.reader.raw.bag_items)[int(ItemId.POKE_BALL)] == 10
    assert report.actions_executed == f.actions.actions_executed
    assert report.frames_executed == f.port.frame_count - before
    assert _supply(f.router.enumerate(f.adapter.observe())).unavailable_reason is (
        GoalUnavailableReason.NO_LEGAL_TARGET
    )
    assert "synthetic-resource-chain" not in json.dumps(supply.policy_dict())


def test_changed_money_at_arrival_prevents_destination_input(fixture):
    f = fixture
    f.port.spend_on_route = True
    result = f.router.enumerate(f.adapter.observe())
    binding = result.require(_supply(result).binding_ref)
    report = binding.execute()
    assert binding.verify(report).status.value == "failed"
    assert f.reader.raw.player_x == 4
    assert int(ItemId.POKE_BALL) not in dict(f.reader.raw.bag_items)
    assert report.evidence["destination_executed"] is False


@pytest.mark.parametrize("money", [0, 1_999, None])
def test_cannot_offer_supply_that_live_money_cannot_buy(fixture, money):
    f = fixture
    f.reader.raw = replace(f.reader.raw, player_money=money)
    supply = _supply(f.router.enumerate(f.adapter.observe()))
    assert supply.unavailable_reason is GoalUnavailableReason.MISSING_RESOURCE
    assert not f.world.plans and f.actions.actions_executed == 0


@pytest.mark.parametrize("failure", ["no_route", "field_action", "field_direction", "surf_mode"])
def test_unsupported_transport_remains_unavailable(fixture, failure):
    f = fixture
    f.world.fail = failure == "no_route"
    f.world.action = "cut" if failure == "field_action" else "right"
    if failure == "field_direction":
        f.world.action_kind = MacroActionKind.FIELD_MOVE
    f.port.mode = "surf" if failure == "surf_mode" else "land"
    supply = _supply(f.router.enumerate(f.adapter.observe()))
    assert supply.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert f.actions.actions_executed == 0


def test_local_provider_is_not_replaced_by_transport(fixture):
    f = fixture
    f.reader.raw = replace(f.reader.raw, player_x=4)
    result = f.router.enumerate(f.adapter.observe())
    assert not f.world.plans
    assert not _supply(result).binding_ref.startswith("red-resource-goal:")


def test_capture_route_uses_same_resources_and_verifies_retained_specimens(fixture):
    f = fixture
    f.reader.raw = replace(
        f.reader.raw,
        map_id=int(MapId.ROUTE_1),
        bag_items=((int(ItemId.POKE_BALL), 10),),
        bag_item_ids=(int(ItemId.POKE_BALL),),
    )
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=_AreaExecutor(f.reader, f.actions),
        actions=f.actions,
        emulator=f.port,
        adapter=f.adapter,
        boundary=lambda current: (
            RedGoalSkillAvailability.available()
            if current.raw.player_x == 4
            else RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        ),
    )
    f.router.runtime.profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="synthetic-resource-capture",
            providers=(
                (
                    GoalKind.ACQUIRE_SPECIES,
                    RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                    {
                        "source_id": "wild:Route1:grass",
                        "label": "synthetic source",
                        "map_id": int(MapId.ROUTE_1),
                        "player_x": 4,
                        "player_y": 2,
                        "forward_directions": ["up"],
                        "starting_endpoint": "south",
                        "maximum_legs": 8,
                        "maximum_seek_steps": 8,
                        "maximum_encounters": 8,
                    },
                ),
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
                (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
            ),
        )
    )
    f.router.runtime.provider_for = lambda *_a: provider
    f.router.runtime.enumerator = lambda *_a: RedGoalOpportunityEnumerator((provider,))
    before = f.adapter.observe().collection.collection.living_count
    result = f.router.enumerate(f.adapter.observe())
    assert len(result.bindings) == 1 and result.bindings[0].kind is GoalKind.ACQUIRE_SPECIES
    report = result.bindings[0].execute()
    assert result.bindings[0].verify(report).status.value == "succeeded"
    assert f.adapter.observe().collection.collection.living_count > before
    assert f.actions.actions_executed == report.actions_executed
    assert not f.router.enumerate(f.adapter.observe()).bindings


def test_resource_offer_cannot_hide_controller_effects_in_planning(fixture):
    f = fixture
    planner = f.world.plan_feasible_to_map

    def unsafe(*args, **kwargs):
        f.actions.execute(MacroAction(MacroActionKind.WAIT))
        return planner(*args, **kwargs)

    f.world.plan_feasible_to_map = unsafe
    with pytest.raises(routing.RedResourceGoalRoutingError, match="enumeration changed"):
        f.router.enumerate(f.adapter.observe())


def test_resource_replan_cannot_introduce_an_unsupported_field_action(fixture):
    f = fixture
    f.world.action = "cut"
    f.world.replanner = lambda: (
        lambda _request: f.world.plan_feasible_to_map(
            f.port.observe(), int(MapId.VIRIDIAN_MART), goal_at=(2, 4)
        )
    )
    with pytest.raises(routing.RedResourceGoalRoutingError, match="unsupported field action"):
        f.router._replan(object())
