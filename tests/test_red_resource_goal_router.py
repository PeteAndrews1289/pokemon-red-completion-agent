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
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_capture_access import required_wild_source_items
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    bind_resupply_fly_profile,
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
from pokemon_red_completion.red_routed_capture_items import bind_capture_item_support
from pokemon_red_completion.red_routed_semantic_goal import FreshRedGoalObservation
from pokemon_red_completion.route_executor import ReplanRequest, TraversalSnapshot
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
            request.goal_map,
            goal_at=request.goal_at,
        )

    def with_current_observation(self, reader):
        return self


@pytest.mark.parametrize("wrapper", [False, 1, "handler"])
def test_resource_interruption_extension_rejects_noncallables_before_input(wrapper):
    with pytest.raises(TypeError, match="wrapper must be callable"):
        routing.RedResourceGoalRouter(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            interruption_handler_wrapper=wrapper,
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


@pytest.mark.parametrize("supported", [False, True])
def test_resource_route_wraps_only_observed_transport_without_input(fixture, supported):
    f = fixture
    calls = []

    def wrap(inner, spec):
        calls.append((inner, spec))
        return (
            inner
            if supported
            else SimpleNamespace(handled_interruption_kinds=frozenset({"battle:2"}))
        )

    f.router.interruption_handler_wrapper = wrap
    before = f.reader.raw
    before_frames = f.port.frame_count
    menu = f.router.enumerate(f.adapter.observe())
    assert len(calls) == 1 and calls[0][1].kind is GoalKind.RESUPPLY
    assert f.reader.raw == before and f.actions.actions_executed == 0
    assert f.port.frame_count == before_frames
    assert _supply(menu).availability is (
        routing.GoalAvailability.AVAILABLE if supported else routing.GoalAvailability.UNAVAILABLE
    )


@pytest.mark.parametrize("at_clerk", [False, True])
def test_exact_reserve_survives_local_route_quote_and_arrival(fixture, at_clerk):
    from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget

    f = fixture
    f.reader.raw = replace(
        f.reader.raw,
        bag_items=(),
        bag_item_ids=(),
        player_money=3175,
        player_x=4 if at_clerk else 3,
    )
    f.router.capture_reserve = CapturePreparationBudget(ItemId.POKE_BALL, 1, 5)
    f.router.quote_resource_costs = True
    before = f.adapter.observe()
    assert not f.provider.resource_availability(before).executable
    binding = f.router.enumerate(before).require(_supply(f.router.enumerate(before)).binding_ref)
    assert binding.resource_quote.purchase_cost == 1000
    assert f.actions.actions_executed == 0
    report = binding.execute()
    assert binding.verify(report).succeeded
    assert f.reader.raw.player_money == 2175
    assert dict(f.reader.raw.bag_items)[int(ItemId.POKE_BALL)] == 5
    assert (
        _supply(f.router.enumerate(f.adapter.observe())).availability
        is routing.GoalAvailability.UNAVAILABLE
    )
    assert f.router.runtime.provider_for(GoalKind.RESUPPLY, f.actions) is f.provider


@pytest.mark.parametrize("change", ["cash", "stock"])
def test_reserve_quote_change_rejected_before_route_input(fixture, change):
    from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget

    f = fixture
    f.reader.raw = replace(f.reader.raw, bag_items=(), bag_item_ids=(), player_money=3175)
    f.router.capture_reserve = CapturePreparationBudget(ItemId.POKE_BALL, 1, 5)
    f.router.quote_resource_costs = True
    menu = f.router.enumerate(f.adapter.observe())
    binding = menu.require(_supply(menu).binding_ref)
    f.reader.raw = replace(
        f.reader.raw,
        **(
            {"player_money": 3000}
            if change == "cash"
            else {
                "bag_items": ((int(ItemId.POKE_BALL), 1),),
                "bag_item_ids": (int(ItemId.POKE_BALL),),
            }
        ),
    )
    from pokemon_red_completion.red_goal_skills import RedGoalSkillError

    with pytest.raises((routing.RedResourceGoalRoutingError, RedGoalSkillError)):
        binding.execute()
    assert f.actions.actions_executed == 0


@pytest.mark.parametrize("cash,bag", [(0, ()), (3175, None), (3175, ((4, 5),))])
def test_unavailable_reserve_never_falls_back_to_original_order(fixture, cash, bag):
    from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget

    f = fixture
    f.reader.raw = replace(
        f.reader.raw,
        player_money=cash,
        bag_items=bag,
        bag_item_ids=() if bag is None else tuple(i for i, _ in bag),
    )
    f.router.capture_reserve = CapturePreparationBudget(ItemId.POKE_BALL, 1, 5)
    f.router.quote_resource_costs = True
    menu = f.router.enumerate(f.adapter.observe())
    assert not any(b.kind is GoalKind.RESUPPLY for b in menu.bindings)
    assert f.actions.actions_executed == 0


def test_route_limit_covers_every_declared_handler_interruption() -> None:
    assert routing._MAX_ROUTE_FLEES == 128
    assert routing._MAX_ROUTE_TRAINER_BATTLES == 32
    assert routing._MAX_ROUTE_SCRIPTED_DIALOGUES == 4
    assert routing._ROUTE_LIMITS.max_interruptions == (
        routing._MAX_ROUTE_FLEES
        + routing._MAX_ROUTE_TRAINER_BATTLES
        + routing._MAX_ROUTE_SCRIPTED_DIALOGUES
    )


def test_explicit_fly_precedes_an_available_cross_region_walk(fixture, monkeypatch):
    f = fixture
    f.router.runtime.profile = bind_resupply_fly_profile(f.router.runtime.profile)
    flight = ExecutableGoalBinding(
        "synthetic-preferred-flight",
        GoalKind.RESUPPLY,
        0.2,
        0.1,
        lambda: GoalExecutionReport(0, 0, {}),
        lambda _report: GoalVerification.succeeded(),
    )
    calls = []

    def bind(*args):
        calls.append(args[1].parameters["fly_transport"])
        return flight

    monkeypatch.setattr(
        "pokemon_red_completion.red_collection_fly.bind_collection_fly",
        bind,
    )
    f.world.plan_feasible_to_map = lambda *_a, **_k: pytest.fail(
        "walking planner ran before explicit Fly"
    )

    result = f.router.enumerate(f.adapter.observe())

    assert result.bindings == (flight,)
    assert calls == [True]
    assert f.actions.actions_executed == 0


def test_illegal_explicit_fly_falls_back_to_walking(fixture, monkeypatch):
    f = fixture
    f.router.runtime.profile = bind_resupply_fly_profile(f.router.runtime.profile)
    calls = []

    def bind(*_args):
        calls.append("fly")
        return None

    monkeypatch.setattr(
        "pokemon_red_completion.red_collection_fly.bind_collection_fly",
        bind,
    )

    result = f.router.enumerate(f.adapter.observe())

    assert calls == ["fly"]
    assert len(f.world.plans) == 1
    assert any(binding.kind is GoalKind.RESUPPLY for binding in result.bindings)
    assert f.actions.actions_executed == 0


def test_router_does_not_advertise_route_without_every_interruption_capability(
    fixture,
    monkeypatch,
):
    f = fixture
    monkeypatch.setattr(
        routing,
        "Gen1RouteInterruptionHandler",
        lambda *_a, **_k: SimpleNamespace(
            handled_interruption_kinds=frozenset({"wild_battle", "trainer_engagement", "battle:2"})
        ),
    )

    result = f.router.enumerate(f.adapter.observe())

    assert _supply(result).unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert all(binding.kind is not GoalKind.RESUPPLY for binding in result.bindings)
    assert f.actions.actions_executed == 0


@pytest.mark.parametrize("include_offers", [None, False])
def test_capture_only_menu_skips_center_offers_but_keeps_escort_and_route_guard(
    fixture,
    monkeypatch,
    include_offers,
):
    f = fixture
    f.router.routed_recovery = True
    if include_offers is not None:
        f.router.include_recovery_offers = include_offers
    calls = []

    def center(router, bindings, observation, *, prepare_escort):
        calls.append("center")
        assert callable(prepare_escort)
        return bindings

    def escort(router, bindings, observation):
        calls.append("escort")
        return bindings

    def guard(*args, **kwargs):
        calls.append("guard")
        assert kwargs["maximum_flees"] == routing._MAX_ROUTE_FLEES
        assert kwargs["maximum_scripted_dialogues"] == routing._MAX_ROUTE_SCRIPTED_DIALOGUES
        return SimpleNamespace(
            handled_interruption_kinds=routing._REQUIRED_ROUTE_INTERRUPTION_KINDS
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_routed_recovery.bind_routed_center_recovery",
        center,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_routed_recovery.guarded_collection_route_handler",
        guard,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_capture_preparation.bind_capture_escort",
        escort,
    )
    before = f.port.frame_count
    result = f.router.enumerate(f.adapter.observe())
    assert _supply(result).binding_ref
    assert calls == (
        ["guard", "center", "escort"] if include_offers is None else ["guard", "escort"]
    )
    assert f.actions.actions_executed == 0 and f.port.frame_count == before


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


def test_routed_kind_filter_skips_unrelated_transport_but_keeps_local_menu(fixture):
    f = fixture
    result = f.router.enumerate_routed_kinds(
        f.adapter.observe(), frozenset({GoalKind.ACQUIRE_SPECIES})
    )
    assert not f.world.plans
    assert _supply(result).unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert f.actions.actions_executed == 0
    for invalid in (set(), frozenset(), frozenset({"acquire"})):
        with pytest.raises(TypeError, match="GoalKind frozenset"):
            f.router.enumerate_routed_kinds(f.adapter.observe(), invalid)


def test_missing_capture_item_uses_only_explicit_item_support(fixture, monkeypatch):
    f = fixture
    f.reader.raw = replace(
        f.reader.raw,
        map_id=int(MapId.ROUTE_1),
        bag_items=((int(ItemId.POKE_BALL), 10),),
        bag_item_ids=(int(ItemId.POKE_BALL),),
    )
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:PokemonTower3F:grass",
        area_executor=_AreaExecutor(f.reader, f.actions, source_id="wild:PokemonTower3F:grass"),
        actions=f.actions,
        emulator=f.port,
        adapter=f.adapter,
        required_capture_items=required_wild_source_items("wild:PokemonTower3F:grass"),
    )
    f.router.runtime.profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="synthetic-capture-item-support",
            providers=(
                (
                    GoalKind.ACQUIRE_SPECIES,
                    RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                    {
                        "source_id": "wild:PokemonTower3F:grass",
                        "label": "synthetic Tower source",
                        "map_id": int(MapId.POKEMON_TOWER_3F),
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
    supported = ExecutableGoalBinding(
        "synthetic-capture-item-support",
        GoalKind.ACQUIRE_SPECIES,
        0.4,
        0.2,
        lambda: GoalExecutionReport(0, 0, {}),
        lambda _report: GoalVerification.succeeded(),
    )
    calls = []

    def bind(*args):
        calls.append(args)
        return supported

    monkeypatch.setattr(
        "pokemon_red_completion.red_routed_capture_items.bind_capture_item_support",
        bind,
    )
    before = (f.actions.actions_executed, f.port.frame_count)

    disabled = f.router.enumerate(f.adapter.observe())
    assert not calls
    assert all(binding.kind is not GoalKind.ACQUIRE_SPECIES for binding in disabled.bindings)

    f.router.prepare_capture_items = True
    enabled = f.router.enumerate(f.adapter.observe())
    assert len(calls) == 1
    assert calls[0][2] is provider
    assert enabled.require(supported.binding_ref) is supported
    assert (f.actions.actions_executed, f.port.frame_count) == before


@pytest.mark.parametrize("poke_balls,expected", [(10, True), (0, False)])
def test_capture_item_support_planning_is_action_free_and_requires_other_resources(
    fixture,
    poke_balls,
    expected,
):
    f = fixture
    f.reader.raw = replace(
        f.reader.raw,
        map_id=int(MapId.ROUTE_1),
        bag_items=(((int(ItemId.POKE_BALL), poke_balls),) if poke_balls else ()),
        bag_item_ids=((int(ItemId.POKE_BALL),) if poke_balls else ()),
    )
    f.reader.read_pc_items = lambda: ((int(ItemId.SILPH_SCOPE), 1),)
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:PokemonTower3F:grass",
        area_executor=_AreaExecutor(f.reader, f.actions, source_id="wild:PokemonTower3F:grass"),
        actions=f.actions,
        emulator=f.port,
        adapter=f.adapter,
        required_capture_items=(ItemId.SILPH_SCOPE,),
    )
    spec = SimpleNamespace(
        parameters={
            "map_id": int(MapId.POKEMON_TOWER_3F),
            "player_x": 4,
            "player_y": 2,
        }
    )
    observation = f.adapter.observe()
    fresh = FreshRedGoalObservation("0" * 64, observation, f.port.observe())
    before = (f.actions.actions_executed, f.port.frame_count)

    binding = bind_capture_item_support(f.router, spec, provider, observation, fresh, f.port)

    assert (binding is not None) is expected
    if binding is not None:
        assert binding.kind is GoalKind.ACQUIRE_SPECIES
        assert binding.search_source_ref == ("pokemon.red:acquisition:wild:PokemonTower3F:grass")
    assert (f.actions.actions_executed, f.port.frame_count) == before


def test_inventory_route_cache_reuses_identical_success_and_failure_queries(fixture):
    f = fixture
    f.router.route_plan_cache = {}
    first = f.router.enumerate(f.adapter.observe())
    second = f.router.enumerate(f.adapter.observe())
    assert _supply(first).policy_dict() == _supply(second).policy_dict()
    assert len(f.world.plans) == 1

    f.router.route_plan_cache.clear()
    f.world.plans.clear()
    f.world.fail = True
    assert _supply(f.router.enumerate(f.adapter.observe())).unavailable_reason is (
        GoalUnavailableReason.MISSING_CAPABILITY
    )
    assert _supply(f.router.enumerate(f.adapter.observe())).unavailable_reason is (
        GoalUnavailableReason.MISSING_CAPABILITY
    )
    assert len(f.world.plans) == 1


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


def test_walking_mart_search_does_not_borrow_capture_field_capabilities(fixture):
    f = fixture
    spec = next(s for s in f.router.runtime.profile.providers if s.kind is GoalKind.RESUPPLY)
    start = replace(
        f.port.observe(),
        capabilities=frozenset(
            {
                "move:cut",
                "move:surf",
                "story:gate_open",
            }
        ),
    )
    fresh = FreshRedGoalObservation("0" * 64, f.adapter.observe(), start)
    assert f.router._plan(spec, fresh) is not None
    assert f.world.plans[0][0].capabilities == frozenset({"story:gate_open"})
    assert start.capabilities == frozenset({"move:cut", "move:surf", "story:gate_open"})
    assert f.actions.actions_executed == 0


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


@pytest.mark.parametrize("search_surcharge", [0.0, 0.096])
@pytest.mark.parametrize("quote_trainers", [None, 0, 3])
def test_capture_route_uses_same_resources_and_verifies_retained_specimens(
    fixture,
    monkeypatch,
    search_surcharge,
    quote_trainers,
):
    f = fixture
    f.reader.raw = replace(
        f.reader.raw,
        map_id=int(MapId.ROUTE_1),
        bag_items=((int(ItemId.POKE_BALL), 10),),
        bag_item_ids=(int(ItemId.POKE_BALL),),
    )
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        search_effort_surcharge=search_surcharge,
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
    calls = []
    events = []
    f.port.record_diagnostic_event = lambda kind, payload: events.append((kind, payload))

    def quote(plan, observation, rom, reader):
        calls.append(plan)
        return dict(ordinary_trainers_crossed=quote_trainers, risk_is_probability=False)

    monkeypatch.setattr(routing, "ordinary_route_work_quote", quote)
    if quote_trainers is not None:
        f.router.quote_capture_route_work = True
    before = f.adapter.observe().collection.collection.living_count
    before_frames = f.port.frame_count
    result = f.router.enumerate(f.adapter.observe())
    assert len(result.bindings) == 1 and result.bindings[0].kind is GoalKind.ACQUIRE_SPECIES
    expected = routing.route_work_estimates(0.361 + search_surcharge, quote_trainers or 0)
    assert result.bindings[0].estimated_effort == pytest.approx(expected[0])
    assert result.bindings[0].estimated_risk == pytest.approx(expected[1])
    assert len(calls) == int(quote_trainers is not None)
    assert len(events) == int(quote_trainers is not None)
    if events:
        assert events[0][0] == "capture_route_work_quote"
        assert events[0][1]["ordinary_trainers_crossed"] == quote_trainers
    assert f.actions.actions_executed == 0 and f.port.frame_count == before_frames
    original_raw = f.reader.raw
    f.reader.raw = replace(original_raw, player_x=2)
    refreshed = f.router.enumerate(f.adapter.observe()).bindings[0]
    assert refreshed.binding_ref != result.bindings[0].binding_ref
    assert refreshed.search_memory_source == result.bindings[0].search_memory_source
    f.reader.raw = replace(original_raw, player_x=4)
    local = f.router.enumerate(f.adapter.observe()).bindings[0]
    assert local.search_memory_source == refreshed.search_memory_source
    assert local.search_memory_source == "pokemon.red:acquisition:wild:Route1:grass"
    f.reader.raw = original_raw
    report = result.bindings[0].execute()
    assert "prospective_route_work" not in report.evidence
    assert result.bindings[0].verify(report).status.value == "succeeded"
    assert f.adapter.observe().collection.collection.living_count > before
    assert f.actions.actions_executed == report.actions_executed
    assert not f.router.enumerate(f.adapter.observe()).bindings


def test_ordinary_route_work_counts_unique_active_intersecting_lanes(monkeypatch):
    from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone

    plan = RoutePlan(
        macro_path=MacroPath((1,), ()), start_at=(2, 2), start_mode="land",
        segments=(), terminal_approach=LocalPath(
            ((2, 2), (2, 3), (2, 4)),
            (LocalEdge((2, 3), "right"), LocalEdge((2, 4), "right")),
            ("land", "land", "land"),
        ), terminal_at=(2, 4), terminal_mode="land",
    )
    zone = TrainerSightZone(1, 1, 200, 1, (2, 1), TrainerFacing.RIGHT, 3, 1, False, False)
    zones = (zone, replace(zone, sprite_index=2, at=(8, 1)),
             replace(zone, sprite_index=3, defeated=True))
    flags = bytes(2)
    checks = []

    def headers(rom, maps, *, full_event_offsets):
        checks.append((rom, maps, full_event_offsets))
        return ()

    monkeypatch.setattr(routing, "trainer_headers", headers)
    monkeypatch.setattr(routing, "map_object_events", lambda *_: ())
    monkeypatch.setattr(
        routing, "static_trainer_sight_zones", lambda h, o, f: zones if f == flags else (),
    )
    monkeypatch.setattr(routing, "trainer_sight_zones", lambda *_: ())
    reader = SimpleNamespace(read_current_map_objects=lambda: ())
    quote = routing.ordinary_route_work_quote(plan, SimpleNamespace(raw=SimpleNamespace(
        event_flags=flags)), b"quote", reader)
    assert checks == [(b"quote", {1}, True)]
    assert quote["ordinary_trainers_crossed"] == 1
    assert quote["sight_lane_tiles_crossed"] == 3
    assert quote["walking_steps"] == 2
    assert quote["scripted_battles_quoted"] is False
    assert quote["battle_count_guaranteed"] is False
    assert quote["enemy_rosters_used"] is False
    assert quote["risk_is_probability"] is False
    # A moved live trainer overrides the static lane, never double-counting it.
    monkeypatch.setattr(routing, "trainer_sight_zones", lambda *_: (replace(zone, at=(9, 1)),))
    quote = routing.ordinary_route_work_quote(plan, SimpleNamespace(raw=SimpleNamespace(
        event_flags=flags)), b"quote", reader)
    assert quote["ordinary_trainers_crossed"] == 0 and quote["current_live_overrides"] == 1


@pytest.mark.parametrize("count", [0, 1, 5, 8, 12, 32])
def test_route_work_is_a_bounded_monotonic_proxy(count):
    effort, risk = routing.route_work_estimates(0.5, count)
    assert effort == min(1.0, 0.5 + count / 16)
    assert risk == min(1.0, 0.18 + count / 8)


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_route_work_rejects_invalid_counts(count):
    with pytest.raises(ValueError, match="nonnegative ordinary trainer"):
        routing.route_work_estimates(0.5, count)


@pytest.mark.parametrize("permission", [1, None, "yes"])
def test_route_work_requires_explicit_boolean_permission(permission):
    with pytest.raises(TypeError, match="permission must be boolean"):
        routing.RedResourceGoalRouter(SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
                                      quote_capture_route_work=permission)


def test_route_work_never_changes_supply_projection(fixture, monkeypatch):
    def forbidden(*_args):
        raise AssertionError("a supply quote must not decode capture hazards")

    monkeypatch.setattr(routing, "ordinary_route_work_quote", forbidden)
    baseline = _supply(fixture.router.enumerate(fixture.adapter.observe()))
    fixture.router.quote_capture_route_work = True
    quoted = _supply(fixture.router.enumerate(fixture.adapter.observe()))
    assert quoted == baseline and fixture.actions.actions_executed == 0


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
    start = f.port.observe()
    with pytest.raises(routing.RedResourceGoalRoutingError, match="unsupported field action"):
        f.router._replan(ReplanRequest(start, int(MapId.VIRIDIAN_MART), (2, 4), {}, 1))


@pytest.mark.parametrize("allow_cut", [False, True])
@pytest.mark.parametrize("allow_surf", [False, True])
def test_resource_replan_refreshes_live_objects_without_relaxing_constraints(
    fixture, allow_cut, allow_surf,
):
    f = fixture
    start = replace(f.port.observe(), capabilities=frozenset({
        routing.CUT_CAPABILITY, routing.SURF_CAPABILITY, "story:gate_open"}))
    blocked = {start.map_id: frozenset({(1, 1)})}
    request = ReplanRequest(start, int(MapId.VIRIDIAN_MART), (2, 4), blocked, 1)
    expected = f.world.plan_feasible_to_map(start, request.goal_map, goal_at=request.goal_at)
    observed = []

    def refreshed(reader):
        assert reader is f.reader
        observed.append(reader)

        def plan(current):
            assert current.current.at == start.at
            assert current.goal_map == request.goal_map and current.goal_at == request.goal_at
            assert current.blocked == blocked and current.ordinal == request.ordinal
            assert current.current.capabilities == frozenset({"story:gate_open"}) | (
                {routing.CUT_CAPABILITY} if allow_cut else set()) | (
                {routing.SURF_CAPABILITY} if allow_surf else set())
            return expected

        return SimpleNamespace(replanner=lambda: plan)

    f.world.with_current_observation = refreshed
    f.world.replanner = lambda: pytest.fail("stale cartridge occupancy reused")
    assert f.router._replan(request, allow_cut=allow_cut, allow_surf=allow_surf) == expected
    assert observed == [f.reader]
    assert f.actions.actions_executed == 0


def test_resource_replan_rejects_unsettled_live_projection(fixture):
    f = fixture

    def unsafe(_reader):
        raise ValueError("current routing observation needs a settled field boundary")

    f.world.with_current_observation = unsafe
    with pytest.raises(ValueError, match="settled field boundary"):
        f.router._replan(ReplanRequest(f.port.observe(), int(MapId.VIRIDIAN_MART),
                                      (2, 4), {}, 1))
    assert f.actions.actions_executed == 0


def test_resource_transport_connects_existing_semantic_observer(fixture, monkeypatch):
    observed = []
    def traversal(reader, **kwargs):
        assert reader is fixture.reader
        observed.append(kwargs["observe_progress"])
        return fixture.port
    monkeypatch.setattr(routing, "Gen1TraversalObserver", traversal)
    fixture.router.enumerate(fixture.adapter.observe())
    assert observed == [fixture.adapter.semantic_observer.observe_raw]
    assert fixture.actions.actions_executed == 0


@pytest.mark.parametrize("indoor, observed", [(True, True), (True, False), (False, True)])
def test_walking_capture_observes_indoor_arrival_before_canonical_patch(fixture, indoor, observed):
    f = fixture
    before_frames = f.port.frame_count
    target = int(MapId.POKEMON_MANSION_2F if indoor else MapId.ROUTE_2)
    spec = SimpleNamespace(mechanic=RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        parameters=dict(map_id=target, player_y=22, player_x=1, observed_local_capture=observed))
    queries = []
    planner = f.world.plan_feasible_to_map

    def quote(start, goal_map, *, goal_at):
        queries.append((goal_map, goal_at))
        # Synthetic exact entry, distinct from the disconnected declared patch.
        return planner(start, goal_map, goal_at=(2, 4) if goal_at is None else goal_at)

    f.world.plan_feasible_to_map = quote
    plan = f.router._plan(
        spec, FreshRedGoalObservation("0" * 64, f.adapter.observe(), f.port.observe())
    )
    expected = None if indoor and observed else (22, 1)
    assert queries == [(target, expected)]
    assert plan.terminal_at == ((2, 4) if expected is None else expected)
    assert spec.parameters["player_y"] == 22 and spec.parameters["player_x"] == 1
    assert f.actions.actions_executed == 0 and f.port.frame_count == before_frames


@pytest.mark.parametrize("result", ["same_source", "absent", "different_source"])
def test_walking_capture_arrival_rebinds_only_its_observed_source(fixture, monkeypatch, result):
    import pokemon_red_completion.red_observed_local_capture as local

    f = fixture
    before_frames = f.port.frame_count
    source = "wild:PokemonMansion2F:grass"
    spec = SimpleNamespace(
        kind=GoalKind.ACQUIRE_SPECIES, mechanic=RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        parameters=dict(map_id=int(MapId.POKEMON_MANSION_2F),
                        observed_local_capture=True, source_id=source))
    child = ExecutableGoalBinding("observed:arrival", GoalKind.ACQUIRE_SPECIES, 0.1, 0.1,
        lambda: pytest.fail("arrival quotation must not execute capture"),
        lambda _: GoalVerification.succeeded(), search_source_ref="pokemon.red:acquisition:" +
        (source if result == "same_source" else "wild:Route2:grass"))
    calls = []

    def bind(router, received_spec, observation):
        calls.append((router, received_spec, observation))
        return None if result == "absent" else child

    monkeypatch.setattr(local, "bind_observed_local_capture", bind)
    fallback = object()
    provider = routing._observed_capture_destination_provider(f.router, spec, fallback)
    observation = f.adapter.observe()
    if result == "different_source":
        with pytest.raises(routing.RedResourceGoalRoutingError, match="changed its source"):
            provider.offer(observation)
    else:
        offer = provider.offer(observation)
        assert offer.binding is (None if result == "absent" else child)
        if result == "absent":
            assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert calls == [(f.router, spec, observation)]
    assert f.actions.actions_executed == 0 and f.port.frame_count == before_frames


@pytest.mark.parametrize("indoor, observed", [(True, False), (False, True)])
def test_unopted_or_outdoor_capture_preserves_original_destination_provider(indoor, observed):
    spec = SimpleNamespace(mechanic=RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        parameters=dict(map_id=int(MapId.POKEMON_MANSION_2F if indoor else MapId.ROUTE_2),
                        observed_local_capture=observed))
    provider = object()
    assert routing._observed_capture_destination_provider(None, spec, provider) is provider
