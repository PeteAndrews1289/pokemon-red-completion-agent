from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_victory_road as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import MapId, OverworldMovementMode
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(monkeypatch):
    raw = N(
        map_id=int(MapId.VIRIDIAN_POKECENTER),
        player_y=3,
        player_x=3,
        badge_bits=255,
        event_flags=bytes(320),
        party_hp=(149, 144),
        party_species_ids=(28, 132),
        party_levels=(49, 31),
        party_moves=((33, 39, 58, 57), (29, 133, 156, 0)),
        bag_items=((199, 1),),
        player_money=26467,
    )
    state = N(payload=b"source", ready=True, legal=True, fault=None, blocked=False)
    actions = N(actions_executed=0)
    em = N(frame_count=0, save_state_bytes=lambda: state.payload)
    reader = N(read=lambda: deepcopy(raw))
    rt = N(
        reader=reader,
        emulator=em,
        adapter=N(
            observe=lambda: N(game_state=object()),
            graph=N(available_objectives=lambda _: (N(id=s.OBJECTIVE),) if state.legal else ()),
        ),
    )
    calls = []

    @dataclass
    class World:
        def with_current_observation(self, _):
            return self

        def plan_feasible_to_map(self, _, target):
            if state.blocked:
                raise RoutePlanningError("blocked actual route")
            assert target == int(MapId.ROUTE_22)
            return N(terminal_at=(8, 33), cost=25, steps=())

    @dataclass
    class Route:
        route_world: World
        rom: bytes = b"rom"
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        def __call__(self, *args):
            calls.append((self.destination_map, self.destination_at))
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            if state.fault == "map":
                raw.map_id = 1
            if state.fault == "cash":
                raw.player_money -= 1
            if state.fault == "bag":
                raw.bag_items = ()
            if state.fault == "level":
                raw.party_levels = (100, 31)
            if state.fault == "ready":
                state.ready = False
            actions.actions_executed += 1
            em.frame_count += 12
            state.payload = b"terminal"

    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready)
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: object())
    return rt, actions, Route(World()), raw, state, calls


def option(rt, actions, route):
    return s.victory_road_story_option(
        rt, actions, None, route=route, battler=object(), preparation_plan=object()
    )


def test_current_earned_approach_is_zero_input_then_verified_partial_progress(monkeypatch):
    rt, a, route, _, state, calls = fixture(monkeypatch)
    binding, challenge = option(rt, a, route)
    assert not calls and a.actions_executed == 0 and not challenge.opposition_known
    report = binding.execute()
    assert calls == [(33, (8, 33))] and report.evidence["objective_completed"] is False
    assert binding.story_objective_ref == s.OBJECTIVE and binding.maximum_cash_debit == 0
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"later"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault", ["map", "cash", "bag", "level", "ready"])
def test_changed_native_boundary_or_resources_never_verify(monkeypatch, fault):
    rt, a, route, _, state, _ = fixture(monkeypatch)
    binding, _ = option(rt, a, route)
    state.fault = fault
    with pytest.raises(RuntimeError, match="terminal"):
        binding.execute()


@pytest.mark.parametrize(
    "fault",
    ["badges", "legal", "no_living", "funds_unknown", "bag_unknown", "blocked", "unready"],
)
def test_unavailable_source_refuses_without_input(monkeypatch, fault):
    rt, a, route, raw, state, calls = fixture(monkeypatch)
    if fault == "badges":
        raw.badge_bits = 127
    if fault == "legal":
        state.legal = False
    if fault == "no_living":
        raw.party_hp = (0, 0)
    if fault == "funds_unknown":
        raw.player_money = None
    if fault == "bag_unknown":
        raw.bag_items = None
    if fault == "blocked":
        state.blocked = True
    if fault == "unready":
        state.ready = False
    assert option(rt, a, route) is None and not calls and a.actions_executed == 0


def test_post_preparation_origin_does_not_require_viridian(monkeypatch):
    rt, a, route, raw, _, calls = fixture(monkeypatch)
    raw.map_id = int(MapId.VERMILION_POKECENTER)
    binding, _ = option(rt, a, route)
    assert a.actions_executed == 0 and not calls
    report = binding.execute()
    assert calls == [(33, (8, 33))]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def fly_fixture(monkeypatch):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    raw.map_id, raw.player_y, raw.player_x = int(MapId.ROUTE_7), 10, 18
    raw.party_count = 2
    raw.party_moves = ((19, 33, 39, 57), (29, 133, 156, 0))
    state.mode = OverworldMovementMode.WALKING
    state.dialogue = False
    state.pending = None
    state.fly_menu = None
    state.destinations = (int(MapId.VIRIDIAN_CITY),)
    state.walk_cost = 400
    state.landing_blocked = False
    state.onward_blocked = False
    rt.reader.read_overworld_movement_mode = lambda: state.mode
    rt.reader.read_input_readiness = lambda: N(ready=state.ready)
    rt.reader.read_bottom_dialogue_box_visible = lambda: state.dialogue
    rt.reader.read_pending_trainer_battle_identity = lambda: state.pending
    rt.reader.read_fly_menu_state = lambda: state.fly_menu
    rt.reader.read_fly_destinations = lambda: state.destinations
    landing = (26, 23)

    @dataclass
    class Observed:
        map_id: int = int(MapId.ROUTE_7)
        at: tuple = (10, 18)
        last_outside_map: int = int(MapId.ROUTE_7)
        occupied: frozenset = frozenset()
        ready: bool = True
        mode: str = "land"
        interruption: object = None

    @dataclass
    class World:
        def with_current_observation(self, _):
            return self

        @property
        def local_graphs(self):
            return {int(MapId.VIRIDIAN_CITY): N(edges={landing: {}})}

        @property
        def object_blockers(self):
            return {int(MapId.VIRIDIAN_CITY): {landing} if state.landing_blocked else set()}

        def plan_feasible_to_map(self, observed, target):
            assert target == int(MapId.ROUTE_22)
            if observed.map_id == int(MapId.VIRIDIAN_CITY) and state.onward_blocked:
                raise RoutePlanningError("onward route is not feasible")
            cost = 25 if observed.map_id == int(MapId.VIRIDIAN_CITY) else state.walk_cost
            return N(terminal_at=(8, 33), cost=cost, steps=())

    class Port:
        def __init__(self, delegate, reader, memory):
            assert delegate.delegate is actions and reader is rt.reader and memory is rt.emulator

        def execute(self, action):
            calls.append(action.value)
            assert action.value == "fly:viridian_city"
            raw.map_id = int(MapId.VIRIDIAN_CITY)
            raw.player_y, raw.player_x = landing
            if state.fault == "map":
                raw.map_id = int(MapId.PALLET_TOWN)
            if state.fault == "cash":
                raw.player_money -= 1
            if state.fault == "bag":
                raw.bag_items = ()
            if state.fault == "level":
                raw.party_levels = (100, 31)
            actions.actions_executed += 1
            rt.emulator.frame_count += 12
            state.payload = b"flown"
            return {"destination_map": raw.map_id, "actions": 1}

    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=Observed))
    monkeypatch.setattr(s, "Gen1FieldMovePort", Port)
    monkeypatch.setattr(s, "red_fly_landings", lambda _: ((int(MapId.VIRIDIAN_CITY), landing),))
    route.route_world = World()
    return rt, actions, route, raw, state, calls


@pytest.mark.parametrize("rival_defeated", [False, True])
def test_earned_fly_is_zero_input_then_shortens_only_the_selected_rival_approach(
    monkeypatch, rival_defeated,
):
    rt, actions, route, raw, state, calls = fly_fixture(monkeypatch)
    if rival_defeated:
        events = bytearray(raw.event_flags)
        events[1318 // 8] |= 1 << (1318 % 8)
        raw.event_flags = bytes(events)
    binding, challenge = option(rt, actions, route)
    assert not calls and not actions.actions_executed and not challenge.combat_required
    assert binding.story_objective_ref == s.OBJECTIVE and binding.maximum_cash_debit == 0
    report = binding.execute()
    assert calls == ["fly:viridian_city"]
    phase = "route22-return-fly" if rival_defeated else "route22-approach-fly"
    assert report.evidence["phase"] == phase
    assert report.evidence["objective_completed"] is False
    assert report.evidence["result"]["navigation_learned"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"later"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault", ["map", "cash", "bag", "level"])
@pytest.mark.parametrize("rival_defeated", [False, True])
def test_fly_approach_keeps_native_landing_and_resource_verification(
    monkeypatch, fault, rival_defeated,
):
    rt, actions, route, raw, state, _ = fly_fixture(monkeypatch)
    if rival_defeated:
        events = bytearray(raw.event_flags)
        events[1318 // 8] |= 1 << (1318 % 8)
        raw.event_flags = bytes(events)
    binding, _ = option(rt, actions, route)
    state.fault = fault
    with pytest.raises(RuntimeError, match="terminal"):
        binding.execute()


@pytest.mark.parametrize("fault", [
    "no_holder", "holder_fainted", "surfing", "dialogue", "pending", "fly_menu",
    "unvisited", "landing_blocked", "onward_blocked", "shorter_walk", "already_viridian",
])
@pytest.mark.parametrize("rival_defeated", [False, True])
def test_unavailable_or_unhelpful_flight_retains_the_existing_walk(
    monkeypatch, fault, rival_defeated,
):
    rt, actions, route, raw, state, calls = fly_fixture(monkeypatch)
    if rival_defeated:
        events = bytearray(raw.event_flags)
        events[1318 // 8] |= 1 << (1318 % 8)
        raw.event_flags = bytes(events)
    if fault == "no_holder":
        raw.party_moves = ((33, 39, 57, 0), (29, 133, 156, 0))
    if fault == "holder_fainted":
        raw.party_hp = (0, 144)
    if fault == "surfing":
        state.mode = OverworldMovementMode.SURFING
    if fault in {"dialogue", "landing_blocked", "onward_blocked"}:
        setattr(state, fault, True)
    if fault in {"pending", "fly_menu"}:
        setattr(state, fault, object())
    if fault == "unvisited":
        state.destinations = ()
    if fault == "shorter_walk":
        state.walk_cost = 65
    if fault == "already_viridian":
        raw.map_id = int(MapId.VIRIDIAN_CITY)
        if rival_defeated:
            # At the earned gate the top-level story option advances through
            # the badge corridor, rather than offering another return trip.
            monkeypatch.setattr(s, "quote_badge_corridor", lambda *args: object())
    binding, _ = option(rt, actions, route)
    assert not calls and actions.actions_executed == 0
    if fault == "already_viridian" and rival_defeated:
        assert binding.binding_ref.startswith("pokemon.red:victory-road:badge-corridor:")
        return
    phase = "route22-return" if rival_defeated else "route22-approach"
    assert binding.binding_ref.startswith("pokemon.red:victory-road:" + phase + ":")


@pytest.mark.parametrize("fault", [None, "blocked", "cross_map", "water_quote", "water_after",
                                   "map", "cash", "bag", "level", "ready"])
def test_selected_return_lands_normally_before_the_walking_only_flight(monkeypatch, fault):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    raw.map_id, raw.player_y, raw.player_x = int(MapId.ROUTE_7), 10, 18
    raw.party_count = 2
    raw.party_moves = ((19, 33, 39, 57), (29, 133, 156, 0))
    state.fault = fault
    rt.reader.read_fly_destinations = lambda: (int(MapId.VIRIDIAN_CITY),)
    rt.reader.read_overworld_movement_mode = lambda: (
        OverworldMovementMode.WALKING if state.payload == b"terminal"
        and fault != "water_after" else OverworldMovementMode.SURFING
    )
    shore = (11, 18)
    edge = N(target=shore, kind="water_exit", required_mode="water", result_mode="land")

    class World:
        local_graphs = {raw.map_id: N(edges={(10, 18): (edge,)})}

        def plan_feasible_to_map(self, start, target, *, goal_at):
            assert target == raw.map_id and goal_at == shore
            if fault == "blocked":
                raise RoutePlanningError("no native shore route")
            return N(cost=1, terminal_mode="water" if fault == "water_quote" else "land",
                     steps=(N(source_map=raw.map_id,
                              expected_map=0 if fault == "cross_map" else raw.map_id),))

    start = N(mode="water", ready=True, interruption=None, at=(10, 18))
    result = s._rival_land_before_fly_option(
        rt, actions, route, world=World(), start=start, record=None, objective_ref=s.OBJECTIVE,
    )
    assert not calls and actions.actions_executed == 0
    if fault in {"blocked", "cross_map", "water_quote"}:
        assert result is None
        return
    binding, _ = result
    assert binding.story_objective_ref == s.OBJECTIVE and binding.maximum_cash_debit == 0
    if fault is not None:
        with pytest.raises(RuntimeError, match="terminal"):
            binding.execute()
        return
    report = binding.execute()
    assert calls == [(int(MapId.ROUTE_7), shore)]
    assert report.evidence["phase"] == "route22-land-before-fly"
    assert report.evidence["objective_completed"] is False
    assert report.evidence["result"]["flight_executed"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"changed"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_stale_flight_refuses_before_dispatch(monkeypatch):
    rt, actions, route, _, state, calls = fly_fixture(monkeypatch)
    binding, _ = option(rt, actions, route)
    state.payload = b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls and actions.actions_executed == 0


@pytest.mark.parametrize("reachable", [True, False])
def test_defeated_rival_keeps_remote_return_as_an_unforced_peer(monkeypatch, reachable):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    raw.map_id = int(MapId.VERMILION_POKECENTER)
    events = bytearray(raw.event_flags)
    events[1318 // 8] |= 1 << (1318 % 8)
    raw.event_flags = bytes(events)
    state.blocked = not reachable
    result = option(rt, actions, route)
    assert (result is not None) is reachable
    assert not calls and actions.actions_executed == 0 and state.payload == b"source"
    if reachable:
        binding, challenge = result
        assert not challenge.opposition_known
        assert binding.story_objective_ref == s.OBJECTIVE
        report = binding.execute()
        assert report.evidence["phase"] == "route22-return"
        assert report.evidence["objective_completed"] is False
        assert calls == [(33, (8, 33))]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize("reachable", [True, False])
def test_badge_corridor_advertises_only_an_actual_living_holder_route(monkeypatch, reachable):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    events = bytearray(raw.event_flags)
    events[1318 // 8] |= 1 << (1318 % 8)
    raw.event_flags = bytes(events)
    quotes = []

    def quote(rom, reader, memory):
        quotes.append((rom, reader, memory))
        if not reachable:
            raise RoutePlanningError("only Surf holder is fainted")
        return object()

    monkeypatch.setattr(s, "quote_badge_corridor", quote)
    result = option(rt, actions, route)
    assert (result is not None) is reachable
    assert len(quotes) == 1
    assert not calls and actions.actions_executed == 0 and state.payload == b"source"


def test_stale_binding_refuses_before_inputs(monkeypatch):
    rt, a, route, _, state, calls = fixture(monkeypatch)
    binding, _ = option(rt, a, route)
    state.payload = b"unrelated"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls and a.actions_executed == 0


@pytest.mark.parametrize("objective_ref", sorted(s.LEAGUE_OBJECTIVES))
def test_completed_crossing_exposes_only_unfinished_league_access(monkeypatch, objective_ref):
    rt, actions, route, raw, _, calls = fixture(monkeypatch)
    raw.map_id = int(MapId.VERMILION_POKECENTER)
    events = bytearray(raw.event_flags)
    events[1318 // 8] |= 1 << (1318 % 8)
    raw.event_flags = bytes(events)
    rt.adapter.graph.available_objectives = lambda _: (N(id=objective_ref),)
    rt.adapter.graph.completed_ids = lambda _: (s.OBJECTIVE,)
    binding, _ = s.victory_road_story_option(
        rt, actions, None, route=route, battler=object(), preparation_plan=object(),
        access_objective_ref=objective_ref,
    )
    assert not calls and actions.actions_executed == 0
    assert binding.story_objective_ref == objective_ref
    report = binding.execute()
    assert report.evidence["objective"] == objective_ref
    assert report.evidence["objective_completed"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    "fault", ("cross_unfinished", "goal_completed", "unrelated", "rival_alive")
)
def test_league_access_does_not_reopen_or_skip_native_gates(monkeypatch, fault):
    rt, actions, route, raw, _, calls = fixture(monkeypatch)
    events = bytearray(raw.event_flags)
    if fault != "rival_alive":
        events[1318 // 8] |= 1 << (1318 % 8)
    raw.event_flags = bytes(events)
    ref = "defeat_lorelei" if fault != "unrelated" else "help_bill"
    rt.adapter.graph.available_objectives = (
        lambda _: () if fault == "goal_completed" else (N(id=ref),)
    )
    rt.adapter.graph.completed_ids = lambda _: () if fault == "cross_unfinished" else (s.OBJECTIVE,)
    assert s.victory_road_story_option(
        rt, actions, None, route=route, battler=object(), preparation_plan=object(),
        access_objective_ref=ref,
    ) is None
    assert not calls and actions.actions_executed == 0


def test_access_arrival_at_indigo_never_latches_a_league_victory(monkeypatch):
    rt, actions, _, raw, _, _ = fixture(monkeypatch)
    raw.map_id = int(MapId.INDIGO_PLATEAU)
    monkeypatch.setattr(s, "semantic_facts", lambda _: pytest.fail("access cannot complete quests"))
    binding, _ = s._mechanics_option(
        rt, actions, phase="reach-indigo", operation=lambda: {}, valid=lambda _: True,
        objective_ref="defeat_lorelei",
    )
    report = binding.execute()
    assert report.evidence["objective_completed"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="cannot complete"):
        s._mechanics_option(rt, actions, phase="bad", operation=lambda: {}, valid=lambda _: True,
                            objective_ref="defeat_lorelei", completes_objective=True)


def indigo_fly_fixture(monkeypatch):
    rt,actions,route,raw,state,calls=fly_fixture(monkeypatch)
    town=int(MapId.INDIGO_PLATEAU)
    landing=(6,8)
    state.destinations=(town,)

    class World(type(route.route_world)):
        @property
        def local_graphs(self):
            return {town:N(edges={landing:{}})}

        @property
        def object_blockers(self):
            return {town:{landing} if state.landing_blocked else set()}

        def plan_feasible_to_map(self,*a,**k):
            pytest.fail("an earned direct Indigo flight does not replay Victory Road")

    class Port:
        def __init__(self,delegate,reader,memory):
            assert delegate.delegate is actions and reader is rt.reader

        def execute(self,action):
            assert action.value == "fly:indigo_plateau"
            calls.append(action.value)
            raw.map_id=town
            raw.player_y,raw.player_x=landing
            if state.fault == "cash":
                raw.player_money-=1
            actions.actions_executed+=1
            rt.emulator.frame_count+=12
            state.payload=b"indigo"
            return {"destination_map":town,"actions":1}

    route.route_world=World()
    monkeypatch.setattr(s,"Gen1FieldMovePort",Port)
    monkeypatch.setattr(s,"red_fly_landings",lambda _:((town,landing),))
    return rt,actions,route,raw,state,calls


@pytest.mark.parametrize("fault", [None,"unvisited","surfing","pending","dialogue",
                                  "no_badge","blocked_landing","cash_mutation"])
def test_earned_indigo_return_is_native_guarded_navigation_not_league_credit(monkeypatch,fault):
    rt,actions,route,raw,state,calls=indigo_fly_fixture(monkeypatch)
    if fault == "unvisited":
        state.destinations=()
    if fault == "surfing":
        state.mode=OverworldMovementMode.SURFING
    if fault == "pending":
        state.pending=(224,5)
    if fault == "dialogue":
        state.dialogue=True
    if fault == "no_badge":
        raw.badge_bits=0
    if fault == "blocked_landing":
        state.landing_blocked=True
    if fault == "cash_mutation":
        state.fault="cash"
    from dataclasses import replace
    observer=s.Gen1TraversalObserver(rt.reader).observe()
    if fault == "surfing":
        observer=replace(observer,mode="water")
    row=s._rival_fly_approach_option(rt,actions,route,world=route.route_world,start=observer,
        walking_plan=None,record=None,objective_ref="defeat_lorelei",phase="indigo-return-fly",
        landing_town=MapId.INDIGO_PLATEAU,onward_destination=MapId.INDIGO_PLATEAU)
    assert not calls and actions.actions_executed == 0
    if fault not in {None,"cash_mutation"}:
        assert row is None
        return
    binding,_=row
    if fault == "cash_mutation":
        with pytest.raises(RuntimeError,match="did not prove its terminal"):
            binding.execute()
        return
    report=binding.execute()
    assert calls == ["fly:indigo_plateau"]
    assert report.evidence["phase"] == "indigo-return-fly"
    assert report.evidence["objective_completed"] is False
    assert binding.story_objective_ref == "defeat_lorelei"
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_league_access_route_uses_earned_indigo_before_any_cave_quote(monkeypatch):
    rt,actions,route,raw,state,calls=indigo_fly_fixture(monkeypatch)
    row=s._route_option(rt,actions,route,world=route.route_world,phase="route22-return",
        destination_map=int(MapId.ROUTE_22),objective_ref="defeat_lorelei")
    assert row is not None and not calls and state.payload == b"source"
    report=row[0].execute()
    assert raw.map_id == int(MapId.INDIGO_PLATEAU)
    assert report.evidence["objective_completed"] is False


def test_indoor_league_return_quotes_only_its_real_departure_before_fly(monkeypatch):
    from pokemon_red_completion import red_indoor_departure_plan as indoor

    rt,actions,route,raw,state,calls=indigo_fly_fixture(monkeypatch)
    raw.map_id=int(MapId.FUCHSIA_POKECENTER)
    outside=int(MapId.FUCHSIA_CITY)
    target=(3,23)
    quoted=[]
    monkeypatch.setattr(indoor,"bounded_indoor_departure",lambda start,world:
        quoted.append(world) or N(terminal_map=outside,terminal_at=target,cost=12))
    row=s._route_option(rt,actions,route,world=route.route_world,phase="route22-return",
        destination_map=int(MapId.ROUTE_22),objective_ref="defeat_lorelei")
    assert len(quoted)==1 and not calls and state.payload == b"source"
    report=row[0].execute()
    assert calls == [(outside,target)]
    assert raw.map_id == outside and (raw.player_y,raw.player_x) == target
    assert report.evidence["phase"] == "indigo-return-departure"
    assert report.evidence["objective_completed"] is False
    assert report.evidence["result"]["flight_executed"] is False


def test_strength_lesson_uses_actual_compatible_living_empty_slot(monkeypatch):
    rt, _, _, raw, _, _ = fixture(monkeypatch)
    calls = []
    monkeypatch.setattr(
        s, "RedPracticeCartridge", lambda _: N(species=lambda _: N(tmhm_moves=(70,)))
    )
    monkeypatch.setattr(s, "plan_machine_lesson", lambda *a, **k: calls.append(k) or k)
    lesson = s._strength_lesson(rt, b"rom")
    assert lesson == dict(item_id=199, party_slot=2, replace_slot=4)
    raw.party_hp = (149, 0)
    assert s._strength_lesson(rt, b"rom") == dict(item_id=199, party_slot=1, replace_slot=1)
    raw.bag_items = ()
    assert s._strength_lesson(rt, b"rom") is None


def test_strength_lesson_never_forgets_an_hm_or_uses_incompatible_member(monkeypatch):
    rt, _, _, raw, _, _ = fixture(monkeypatch)
    raw.party_moves = ((15, 19, 57, 148), (15, 19, 57, 70))
    monkeypatch.setattr(
        s, "RedPracticeCartridge", lambda _: N(species=lambda _: N(tmhm_moves=(70,)))
    )
    monkeypatch.setattr(s, "plan_machine_lesson", lambda *a, **k: pytest.fail("no legal lesson"))
    assert s._strength_lesson(rt, b"rom") is None
