from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_party_loan as loan
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_native_boxed_evolution import settle_native_evolution
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard


@pytest.mark.parametrize("supported", [True, False])
@pytest.mark.parametrize("phase", ["initial", "replan"])
def test_return_walk_uses_counted_center_waiter_and_preserves_walking_guard(monkeypatch, supported, phase):
    import pokemon_red_completion.red_native_boxed_evolution as evolution
    from pokemon_red_completion.route_executor import ReplanRequest, TraversalSnapshot
    from pokemon_red_completion.route_plan import RoutePlanningError

    position, refreshes, calls = [(4, 3)], [], []
    goal, map_id = (3, 3), 133
    reader = N(read_bottom_dialogue_box_visible=lambda: False)
    runtime = N(reader=reader)
    actions = CountingExecutor(N(execute=lambda action: action))
    observer = N(observe=lambda: TraversalSnapshot(map_id, position[0], True))
    original, replacement = N(walking=True), N(walking=supported)
    world = N()

    def refresh(actual_reader):
        assert actual_reader is reader
        refreshes.append(True)
        return world

    def plan(start, destination, *, goal_at):
        assert start.at == (4, 3) and destination == map_id and goal_at == goal
        if phase == "initial":
            raise RoutePlanningError("observed moving NPC occupies the destination")
        return original

    def waiter(rt, current, port):
        assert rt is runtime and current is world and port is actions
        assert len(refreshes) == (1 if phase == "initial" else 2)

        def replan(request):
            calls.append(request)
            assert request.goal_map == map_id and request.goal_at == goal
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
            return replacement

        return replan

    def execute(route, port, traversal, *, limits, interruption_handler, replanner):
        assert route is (replacement if phase == "initial" else original)
        assert port is actions and traversal is observer
        assert limits is loan._ROUTE_LIMITS and interruption_handler is None
        if phase == "replan":
            assert replanner(ReplanRequest(observer.observe(), map_id, goal,
                {map_id: frozenset({goal})}, 1)) is replacement
        position[0] = goal
        return N(passed=True)

    world.with_current_observation, world.plan_feasible_to_map = refresh, plan
    monkeypatch.setattr(loan, "Gen1TraversalObserver", lambda _: observer)
    monkeypatch.setattr(loan, "prepare_center_departure", lambda *args: None)
    monkeypatch.setattr(loan, "_walking_plan", lambda route: route.walking)
    monkeypatch.setattr(loan, "execute_route", execute)
    monkeypatch.setattr(evolution, "native_evolution_pc_replanner", waiter)
    if supported:
        loan._walk(runtime, actions, world, map_id, goal)
        assert position[0] == goal
    else:
        with pytest.raises(ValueError, match="supported walking-only"):
            loan._walk(runtime, actions, world, map_id, goal)
        assert position[0] == (4, 3)
    assert len(calls) == actions.actions_executed == 1


def setup(monkeypatch, *, fault=None, already_restored=False):
    original = tuple(
        PartyMemberObservation(i + 1, i + 1, 17, 40, 40, experience=5000) for i in range(6)
    )
    refs = ("a", "b", "c", "d", "e", "loan")
    guest = replace(original[-1], species_id=108, level=21, experience=9000)
    state = N(
        members=list(original if already_restored else (*original[:5], guest)),
        refs=list(refs if already_restored else (*refs[:5], "guest")),
        boxes=[]
        if already_restored
        else [
            N(
                preparation_ref="loan",
                species_id=6,
                level=17,
                experience=5000,
                box_index=0,
                box_slot=1,
            )
        ],
        cash=100,
        bag=((1, 1),),
        at=(3, 3),
    )
    if fault == "missing_original":
        state.boxes = []
    if fault == "duplicate_original":
        state.boxes.append(state.boxes[0])
    reader = N(
        read_box_specimen_identities=lambda: tuple(state.boxes),
        read_current_box_state=lambda: N(box_index=0),
    )
    party_reader = N(
        read=lambda: PartyObservation(
            tuple(replace(m, slot=i + 1) for i, m in enumerate(state.members))
        ),
        preparation_specimen_refs=lambda: tuple(state.refs),
    )
    guard = RedPlayerPartyGuard(
        party_reader, PartyObservation(original), refs, frozenset(), reader, frozenset({"loan"})
    )

    def raw():
        return N(
            map_id=182,
            player_y=state.at[0],
            player_x=state.at[1],
            party_species_ids=tuple(m.species_id for m in state.members),
            battle_state=0,
            player_money=state.cash,
            bag_items=state.bag,
        )

    reader.read = raw

    def observe():
        return N(
            raw=raw(),
            input_ready=True,
            collection_observation=N(
                owned_species=frozenset({"original", "guest"}),
                box_counts=(len(state.boxes),),
                box_capacity=20,
                specimens=tuple(
                    N(species_ref=str(m.species_id)) for m in (*state.members, *state.boxes)
                ),
            ),
        )

    runtime = N(reader=reader, adapter=N(party_guard=guard, observe=observe))
    calls = []
    actions = CountingExecutor(N(execute=lambda action: action))

    def step(name):
        calls.append(name)
        actions.execute(MacroAction(MacroActionKind.WAIT))

    def walk(rt, port, world, center, at, **kwargs):
        assert port is actions and rt is runtime
        step("walk")
        state.at = at

    def deposit(port, read, *, party_slot, expected_species_id):
        step("deposit")
        member, ref = state.members.pop(party_slot - 1), state.refs.pop(party_slot - 1)
        assert member.species_id == expected_species_id
        state.boxes.append(
            N(
                preparation_ref=ref,
                species_id=member.species_id,
                level=member.level,
                experience=member.experience,
                box_index=0,
                box_slot=2,
            )
        )
        return N(passed=fault != "deposit_failed")

    def withdraw(port, read, *, box_slot, expected_species_id):
        step("withdraw")
        if fault == "withdraw_failed":
            return N(passed=False)
        box = state.boxes.pop(0)
        assert box.species_id == expected_species_id and box.box_slot == box_slot
        state.refs.append(box.preparation_ref)
        state.members.append(original[-1])
        if fault == "cash":
            state.cash += 1
        if fault == "stock":
            state.boxes.clear()
        return N(passed=True)

    monkeypatch.setattr(loan, "_walk", walk)
    monkeypatch.setattr(loan, "face_pc_boundary", lambda *a: step("face"))
    monkeypatch.setattr(loan, "open_bills_pc", lambda *a: step("open"))
    monkeypatch.setattr(loan, "deposit_party_member", deposit)
    monkeypatch.setattr(loan, "withdraw_box_member", withdraw)
    monkeypatch.setattr(loan, "close_generic_pc_session", lambda *a: step("close"))
    runtime.evolution_settlement = lambda port: loan.restore_guarded_party_loan(runtime, port, None)
    return runtime, actions, state, calls


def test_declared_return_preserves_earned_guest_and_original_without_reset(monkeypatch):
    runtime, actions, state, calls = setup(monkeypatch)
    before = loan._stock(runtime)
    assert settle_native_evolution(runtime, actions) == {"retained_active_roster_restored": True}
    assert loan._stock(runtime) == before
    assert state.refs == ["a", "b", "c", "d", "e", "loan"]
    assert state.boxes[0].preparation_ref == "guest" and state.boxes[0].experience == 9000
    assert actions.actions_executed == len(calls) == 7
    assert calls == ["walk", "face", "open", "deposit", "withdraw", "close", "walk"]
    # Another call cannot deposit a second guest or spend an extra input.
    assert settle_native_evolution(runtime, actions) == {"retained_active_roster_restored": True}
    assert actions.actions_executed == 7


@pytest.mark.parametrize(
    "fault",
    [
        "missing_original",
        "duplicate_original",
        "deposit_failed",
        "withdraw_failed",
        "cash",
        "stock",
    ],
)
def test_return_cannot_hide_missing_identity_failed_exchange_or_changed_resources(
    monkeypatch, fault
):
    runtime, actions, state, calls = setup(monkeypatch, fault=fault)
    with pytest.raises(ValueError):
        settle_native_evolution(runtime, actions)
    if fault in {"missing_original", "duplicate_original"}:
        assert actions.actions_executed == 0 and not calls
    else:
        assert actions.actions_executed > 0
    assert not hasattr(runtime, "load_state_bytes")


def test_no_outstanding_loan_spends_no_input(monkeypatch):
    runtime, actions, _, calls = setup(monkeypatch, already_restored=True)
    assert loan.restore_guarded_party_loan(runtime, actions, None) is False
    assert actions.actions_executed == 0 and not calls


def test_venue_return_normalizes_native_center_enum_before_route_planning(monkeypatch):
    from pokemon_red_completion import red_goal_context as context
    from pokemon_red_completion.observation import MapId, RawGameState

    raw = RawGameState(
        game_started=True,
        map_id=int(MapId.ROUTE_11),
        player_x=13,
        player_y=6,
        party_count=6,
        battle_state=0,
    )
    venue = N(
        is_in_map=lambda r: r.map_id == int(MapId.ROUTE_11),
        is_in_center=lambda r: r.map_id == MapId.VERMILION_POKECENTER,
    )
    for name in (
        "ROUTE_11_TRAINING_VENUE",
        "DIGLETTS_CAVE_TRAINING_VENUE",
        "MANSION_TRAINING_VENUE",
    ):
        monkeypatch.setattr(context, name, venue)
    calls = []
    monkeypatch.setattr(
        loan, "_walk", lambda rt, a, w, destination, at, **kw: calls.append((destination, at, kw))
    )
    loan._reach_center(N(reader=N(read=lambda: raw)), None, None)
    assert calls == [(int(MapId.VERMILION_POKECENTER), (3, 3), {"venue_return": True})]
    assert type(calls[0][0]) is int


@pytest.mark.parametrize("reachable", [True, False])
def test_failed_transition_returns_to_a_reachable_center_without_healing(monkeypatch, reachable):
    from pokemon_red_completion.observation import MapId
    from pokemon_red_completion.route_plan import RoutePlanningError

    raw = N(map_id=int(MapId.CINNABAR_ISLAND))
    runtime, start, calls = N(reader=N(read=lambda: raw)), object(), []
    world = N(with_current_observation=lambda reader: world)
    monkeypatch.setattr(loan, "Gen1TraversalObserver", lambda reader: N(observe=lambda: start))

    def plan(source, destination, *, goal_at):
        assert source is start and goal_at == (3, 3)
        if destination == int(MapId.CINNABAR_POKECENTER) and reachable:
            return N(cost=12, walking=True)
        if destination == int(MapId.VERMILION_POKECENTER):
            return N(cost=1, walking=False)
        raise RoutePlanningError("unreachable")

    world.plan_feasible_to_map = plan
    monkeypatch.setattr(loan, "_walking_plan", lambda p: p.walking)
    monkeypatch.setattr(loan, "_walk", lambda *a, **k: calls.append((a[-2:], k)))
    if reachable:
        loan._reach_center(runtime, None, world)
        assert calls == [((int(MapId.CINNABAR_POKECENTER), (3, 3)), {"venue_return": True})]
    else:
        with pytest.raises(ValueError, match="no executable"):
            loan._reach_center(runtime, None, world)
        assert not calls


@pytest.mark.parametrize(
    "fault", [None, "occupied", "unsettled", "cut", "surf", "wrong_endpoint", "not_ready"]
)
def test_loan_walk_refreshes_live_occupancy_without_relaxing_route_guards(monkeypatch, fault):
    from pokemon_red_completion.route_plan import RoutePlanningError

    reader = N(read_bottom_dialogue_box_visible=lambda: False,
               read_current_map_objects=lambda: ())
    runtime = N(reader=reader)
    start = N(map_id=133, at=(4, 13))
    terminal = N(map_id=133, at=(3, 3), ready=True, interruption=None)
    if fault == "wrong_endpoint":
        terminal.at = (4, 3)
    if fault == "not_ready":
        terminal.ready = False
    observations = iter((start, terminal))
    traversal = N(observe=lambda: next(observations))
    initial_plan = N(walking=True)
    replacement = N(walking=fault not in {"cut", "surf"})
    # The route executor's accumulated blocker and the observed moving NPC
    # remain in the unchanged request. Only stale world geometry is refreshed.
    request = N(current=N(map_id=133, at=(4, 9), occupied=frozenset({(4, 8)})),
        blocked={133: frozenset({(4, 8), (6, 10)})}, goal_map=133, goal_at=(3, 3))
    calls = []

    def plan(observed, destination, *, goal_at):
        assert observed is start and (destination, goal_at) == (133, (3, 3))
        return initial_plan

    def fresh_replan(actual):
        assert actual is request
        assert actual.blocked == {133: frozenset({(4, 8), (6, 10)})}
        calls.append("fresh-replan")
        if fault == "occupied":
            raise RoutePlanningError("the destination is still occupied")
        return replacement

    fresh = N(replanner=lambda: fresh_replan,
              with_current_observation=lambda actual_reader: fresh)

    def refresh(actual_reader):
        assert actual_reader is reader
        calls.append("refresh")
        if fault == "unsettled":
            raise ValueError("current routing observation needs a settled field boundary")
        return fresh

    initial = N(plan_feasible_to_map=plan, with_current_observation=refresh,
        replanner=lambda: pytest.fail("stale occupancy replanner was reused"))
    world = N(with_current_observation=lambda actual_reader: initial)
    actions = object()

    def execute(plan_value, action_port, observer, **kwargs):
        assert plan_value is initial_plan and action_port is actions and observer is traversal
        assert kwargs["replanner"](request) is replacement
        calls.append("replacement-accepted")
        return N(passed=True)

    monkeypatch.setattr(loan, "Gen1TraversalObserver", lambda r: traversal)
    monkeypatch.setattr(loan, "prepare_center_departure", lambda *a: None)
    monkeypatch.setattr(loan, "_walking_plan", lambda p: p.walking)
    monkeypatch.setattr(loan, "execute_route", execute)
    if fault:
        with pytest.raises((ValueError, RoutePlanningError)):
            loan._walk(runtime, actions, world, 133, (3, 3))
        if fault in {"occupied", "unsettled", "cut", "surf"}:
            assert "replacement-accepted" not in calls
    else:
        loan._walk(runtime, actions, world, 133, (3, 3))
        assert calls == ["refresh", "fresh-replan", "replacement-accepted"]
