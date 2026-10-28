"""ROM-free integration review of paid-patrol composition.

Uses existing synthetic route/admission/indoor fixtures. No cartridge, save,
emulator, model fit, or native input is involved. Root owns execution/admission.
"""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_live_safari as live
import pokemon_red_completion.red_paid_safari_departure as departure
import pokemon_red_completion.red_resource_goal_router as resources
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.red_safari_acquisition import (
    RedSafariZoneOffer, derive_red_safari_patrol,
)
from test_paid_safari_patrol_selection_review import _fixture
from test_red_paid_safari_departure import route_fixture
from test_red_live_safari import (
    pilot_binding, _real_gate_safari_fixture, _LiveGateExecutionController,
)


def _derived():
    legacy, alternative, terrain = _fixture()
    offer = RedSafariZoneOffer(
        legacy.source_id, legacy.map_id, tuple((25, 128) for _ in range(10)), (128,))
    graph = LocalGraph({
        (0, 0): (LocalEdge((1, 0), "down"),),
        (1, 0): (LocalEdge((0, 0), "up"), LocalEdge((2, 0), "down")),
        (2, 0): (LocalEdge((1, 0), "up"), LocalEdge((2, 1), "right")),
        (2, 1): (LocalEdge((2, 0), "left"), LocalEdge((2, 2), "right")),
        (2, 2): (LocalEdge((2, 1), "left"),),
    })
    return legacy, alternative, terrain, offer, graph


def test_default_derivation_is_exact_legacy_and_two_grass_is_opt_in():
    old, alternate, terrain, offer, graph = _derived()
    kwargs = dict(start_at=old.start_at)
    default = derive_red_safari_patrol(offer, terrain, graph, **kwargs)
    explicit_one = derive_red_safari_patrol(
        offer, terrain, graph, minimum_encounter_tiles=1, **kwargs)
    explicit_two = derive_red_safari_patrol(
        offer, terrain, graph, minimum_encounter_tiles=2, **kwargs)
    assert default == explicit_one == old
    assert explicit_two == alternate
    assert default.public_dict() == old.public_dict()


@pytest.mark.parametrize("minimum", [True, False, 0, 3, 1.5])
def test_derivation_rejects_invalid_minimum_before_graph_use(minimum):
    old, _, terrain, offer, graph = _derived()
    with pytest.raises(ValueError, match="one or two"):
        derive_red_safari_patrol(offer, terrain, graph,
                                start_at=old.start_at, minimum_encounter_tiles=minimum)


def test_two_grass_derivation_keeps_warp_object_and_reversibility_constraints():
    old, _, terrain, offer, graph = _derived()
    with pytest.raises(ValueError, match="no reachable"):
        derive_red_safari_patrol(
            offer, terrain, graph, start_at=old.start_at,
            minimum_encounter_tiles=2, excluded={(2, 2)})
    assert derive_red_safari_patrol(
        offer, terrain, graph, start_at=old.start_at, excluded={(2, 2)}) == old
    one_way = LocalGraph({**graph.edges, (2, 2): ()})
    with pytest.raises(ValueError, match="no reachable"):
        derive_red_safari_patrol(offer, terrain, one_way,
                                start_at=old.start_at, minimum_encounter_tiles=2)


def test_geometry_quote_needs_no_live_session_but_wrapper_still_enforces_timer(monkeypatch):
    start, session, plan, world, reader = route_fixture(monkeypatch)
    timer_calls = []
    def no_timer(p, r):
        timer_calls.append((p, r))
        return False
    monkeypatch.setattr(departure, "safari_departure_within_steps", no_timer)
    session.safari_steps = 0
    assert departure.plan_paid_safari_exit_geometry(start, world) is plan
    assert timer_calls == []
    with pytest.raises(ValueError, match="step-safe"):
        departure.plan_paid_safari_departure(start, world, reader)
    assert timer_calls == [(plan, reader)]


@pytest.mark.parametrize("field,value", [
    ("in_safari_zone", False), ("safari_game_over", True), ("safari_balls", 0)])
def test_geometry_does_not_relax_actual_session_preconditions(monkeypatch, field, value):
    start, session, plan, world, reader = route_fixture(monkeypatch)
    setattr(session, field, value)
    assert departure.plan_paid_safari_exit_geometry(start, world) is plan
    with pytest.raises(ValueError, match="ready active"):
        departure.plan_paid_safari_departure(start, world, reader)


def _priced(monkeypatch, capabilities=frozenset(), quote_error=None):
    legacy, alternate, terrain, offer, graph = _derived()
    area = live.RedReachableSafariArea(offer, legacy, 40)
    world = NS(
        terrain={offer.map_id: terrain}, local_graphs={offer.map_id: graph},
        object_blockers={offer.map_id: {(0, 3)}},
        macro_graph=NS(warp_locations={offer.map_id: {(1, 3)}}))
    observed = object()
    controller = object()
    reader = NS(read=lambda: observed)
    projections, quote_starts = [], []
    def caps(memory, raw, **kwargs):
        assert memory is controller and raw is observed
        assert kwargs == {"allow_cut": False, "allow_surf": True}
        projections.append(True)
        return capabilities
    monkeypatch.setattr(resources, "collection_field_capabilities", caps)
    def derive(given, given_terrain, given_graph, **kwargs):
        assert (given, given_terrain, given_graph) == (offer, terrain, graph)
        assert kwargs == {
            "minimum_encounter_tiles": 2,
            "excluded": frozenset({(0, 3), (1, 3)}),
        }
        return alternate
    monkeypatch.setattr(live, "derive_red_safari_offer_patrol", derive)
    def quote(start, supplied_world):
        assert supplied_world is world and start.capabilities == capabilities
        assert start.map_id == offer.map_id and start.mode == "land"
        assert start.last_outside_map == 7
        quote_starts.append(start)
        if quote_error is not None:
            raise quote_error
        return NS(steps=(None,) * {(2, 0): 5, (2, 1): 6, (2, 2): 7}[start.at])
    monkeypatch.setattr(departure, "plan_paid_safari_exit_geometry", quote)
    return area, alternate, world, controller, reader, projections, quote_starts


@pytest.mark.parametrize("capabilities", [frozenset(), frozenset({"move:surf"})])
def test_pricing_forwards_only_observed_capabilities_and_updates_route_effort(monkeypatch, capabilities):
    area, alternate, world, controller, reader, projections, starts = _priced(
        monkeypatch, capabilities)
    result, = live._price_paid_patrol_alternatives((area,), world, controller, reader)
    assert result.patrol is alternate and result.offer is area.offer
    assert result.route_steps == area.route_steps + 1
    assert result.paid_patrol_quote["legal_capabilities"] == sorted(capabilities)
    assert result.paid_patrol_quote["steps_after_admission"] == 324
    assert result.paid_patrol_quote["selected"] == "two_grass"
    assert projections == [True]
    assert [s.at for s in starts] == [
        area.patrol.first_at, area.patrol.second_at, alternate.first_at, alternate.second_at]


@pytest.mark.parametrize("error", [RuntimeError("unavailable route"), OSError("unreadable geometry")])
def test_pricing_unknown_geometry_retains_exact_original_area(monkeypatch, error):
    area, _, world, controller, reader, _, _ = _priced(monkeypatch, quote_error=error)
    result, = live._price_paid_patrol_alternatives((area,), world, controller, reader)
    assert result is area and result.paid_patrol_quote is None


def test_changed_patrol_changes_binding_but_preserves_history_and_deterministic_rebind(monkeypatch):
    area, _, world, controller, reader, _, _ = _priced(monkeypatch)
    first, = live._price_paid_patrol_alternatives((area,), world, controller, reader)
    rebound, = live._price_paid_patrol_alternatives((area,), world, controller, reader)
    assert first == rebound and first is not rebound
    old_binding = pilot_binding(area=area, complete_paid_session=True, world=world)
    selected = pilot_binding(area=first, complete_paid_session=True, world=world)
    actual = pilot_binding(area=rebound, complete_paid_session=True, world=world)
    assert selected.binding_ref == actual.binding_ref != old_binding.binding_ref
    assert selected.search_source_ref == old_binding.search_source_ref
    assert selected.search_objective_sha256 == old_binding.search_objective_sha256
    assert selected.estimated_effort > old_binding.estimated_effort
    private_metadata_only = replace(first, paid_patrol_quote={**first.paid_patrol_quote, "review": True})
    assert pilot_binding(area=private_metadata_only, complete_paid_session=True,
                         world=world).binding_ref == selected.binding_ref


@pytest.mark.parametrize("fault", [None, "capabilities", "steps", "reserve"])
def test_live_binding_rechecks_paid_quote_before_any_search(monkeypatch, fault):
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.goal_manager import GoalSituation
    from pokemon_red_completion.living_dex_option_value import living_dex_option_context_from_goal_situation
    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500)
    actions = CountingExecutor(sim)
    # Existing fixture executes synthetic gate payment and a one-step approach.
    context = living_dex_option_context_from_goal_situation(
        GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    inventory = live.build_red_live_safari_inventory(
        b"rom", frozenset({30}), context, free_storage_slots=2, world=world,
        controller=sim, actions=actions, reader=sim, complete_paid_session=True,
        maximum_encounters=6)
    area, = inventory.areas
    assert len(area.patrol.approach_directions) == 1
    quote = {
        "selected": "two_grass", "steps_after_admission": 500,
        "legal_capabilities": [], "two_grass": {"exit_steps": [51, 52]}}
    # A synthetic certificate exercises the new live guard. Geometry selection
    # itself is covered separately by the real pure selector above.
    area = replace(area, paid_patrol_quote=quote)
    monkeypatch.setattr(resources, "collection_field_capabilities",
                        lambda *_a, **_k: frozenset({"move:surf"}) if fault == "capabilities" else frozenset())
    def reserve(*_):
        if fault == "steps":
            sim.safari_steps = 498
        return 71 if fault == "reserve" else 70
    monkeypatch.setattr(departure, "paid_search_step_reserve", reserve)
    class SearchReached(Exception):
        pass
    search_calls = []
    def search(*_a, **_k):
        search_calls.append(True)
        raise SearchReached()
    monkeypatch.setattr(live, "run_red_area_survey", search)
    binding = pilot_binding(
        area=area, controller=sim, actions=actions, reader=sim,
        world=world, complete_paid_session=True)
    if fault is None:
        with pytest.raises(SearchReached):
            binding.execute()
        assert search_calls == [True]
    else:
        with pytest.raises(live.RedLiveSafariError, match="quote differs after admission"):
            binding.execute()
        assert search_calls == []
    # Retain the paid cost; guard rejection must never trigger a replacement fee.
    assert sim.money == 0 and actions.actions_executed > 0
    with pytest.raises(live.RedLiveSafariError, match="consumed"):
        binding.execute()
    assert sim.money == 0


@pytest.mark.parametrize("changed_quote", [False, True])
def test_indoor_rebind_compares_private_paid_quote_before_spending(monkeypatch, changed_quote):
    import test_red_indoor_safari as indoor_fixture
    original_area = indoor_fixture._area
    certificate = {
        "selected": "two_grass", "steps_after_admission": 500,
        "legal_capabilities": [], "two_grass": {"exit_steps": [51, 52]}}
    def area_with_quote(*args):
        return replace(original_area(*args), paid_patrol_quote=deepcopy(certificate))
    monkeypatch.setattr(indoor_fixture, "_area", area_with_quote)
    original_inventory = indoor_fixture.RedLiveSafariInventory
    builds = []
    def rebuilt(areas, options):
        builds.append(True)
        # The fixture invokes this at projection, then actual rebind. The real
        # indoor wrapper compares the resulting area dataclasses before spending.
        if changed_quote and len(builds) == 2:
            altered = deepcopy(areas[0].paid_patrol_quote)
            altered["two_grass"]["exit_steps"][1] += 1
            areas = (replace(areas[0], paid_patrol_quote=altered),)
        return original_inventory(areas, options)
    monkeypatch.setattr(indoor_fixture, "RedLiveSafariInventory", rebuilt)
    binding, state, calls = indoor_fixture.setup(monkeypatch)
    assert calls == ["project"] and state.frame_count == 0
    if changed_quote:
        with pytest.raises(ValueError, match="offer changed"):
            binding.execute()
        assert calls == ["project", "exit", "rebind"]
        assert state.actions_executed == 3 and state.frame_count == 20
    else:
        report = binding.execute()
        assert calls == ["project", "exit", "rebind", "spend"]
        assert report.actions_executed == 13 and report.frames_executed == 70
