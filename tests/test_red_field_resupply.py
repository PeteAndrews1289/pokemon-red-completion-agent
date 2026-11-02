from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_field_item as field
from pokemon_red_completion import red_player_field_item as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress
from pokemon_red_completion.route_plan import RoutePlanningError


def test_native_object_flag_is_read_only_and_bounded():
    calls = []
    reader = PokemonRedStateReader(N(read_u8=lambda at: calls.append(at) or 4))
    assert reader.read_toggleable_object_hidden(58)
    assert calls == [int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + 7]
    assert not reader.read_toggleable_object_hidden(57)
    for invalid in (-1, 256, True, 58.0):
        with pytest.raises(ValueError):
            reader.read_toggleable_object_hidden(invalid)


@pytest.mark.parametrize("hidden", [True, False])
def test_exact_cartridge_item_uses_its_native_global_flag(monkeypatch, hidden):
    target = field.RedFieldItem(82, 145, 4, 61, (10, 12))
    monkeypatch.setattr(field, "red_field_items", lambda *args: (target,))
    monkeypatch.setattr(field, "_field_item_toggle_indices", lambda rom: {(145, 4): 58})
    seen = []
    reader = N(read_toggleable_object_hidden=lambda i: seen.append(i) or hidden)
    assert field.field_item_is_available(b"rom", reader, target) is (not hidden)
    assert seen == [58]
    with pytest.raises(ValueError, match="cartridge"):
        field.field_item_is_available(b"rom", reader, field.RedFieldItem(82, 145, 5, 61, (10, 12)))


def fixture(monkeypatch, *, remote=False):
    target = field.RedFieldItem(82, 145, 4, 61, (10, 12))
    state = N(
        payload=b"source",
        available=True,
        blocked=False,
        full_blocked=False,
        cycling=False,
        changed_cash=False,
        present=True,
        moving=False,
        picture=61,
        pickup_count=0,
        preferred_frontier_blocked=False,
        alternate_frontier_blocked=False,
        wrong_frontier_map=False,
    )
    raw = N(
        map_id=1 if remote else 145,
        player_y=0,
        player_x=0,
        bag_items=(),
        player_money=9000,
        party_hp=(100,),
        party_species_ids=(28,),
        badge_bits=255,
        ready=True,
    )
    runtime = N(
        reader=N(read=lambda: N(**vars(raw))),
        emulator=N(frame_count=0, save_state_bytes=lambda: state.payload),
    )
    runtime.reader.read_current_map_objects = lambda: (
        (N(sprite_index=4, moving=state.moving, picture_id=state.picture, at=target.at),)
        if state.present
        else ()
    )
    actions = N(actions_executed=0)

    @dataclass
    class World:
        def with_current_observation(self, reader):
            return self

        def plan_feasible_to_map(self, origin, map_id, *, goal_at=None):
            if state.blocked or (state.full_blocked and raw.map_id == 1 and map_id == 145):
                raise RoutePlanningError("no real path")
            if (raw.map_id == 1 and map_id == 2 and state.preferred_frontier_blocked
                    and (goal_at is not None or state.alternate_frontier_blocked)):
                raise RoutePlanningError("preferred floor island is disconnected")
            at = (3, 5) if goal_at is None else goal_at
            return N(cost=sum(at), terminal_at=at,
                     terminal_map=3 if state.wrong_frontier_map else map_id)

    @dataclass
    class Route:
        rom: bytes = b"rom"
        route_world: object = None
        destination_map: int = 145
        destination_at: tuple = (0, 0)
        allow_surf: bool = False

        def __call__(self, actions, reader, emulator):
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            actions.actions_executed += 1
            emulator.frame_count += 10
            state.payload = b"arrived"

    monkeypatch.setattr(s, "_field_ready", lambda rt: raw.ready)
    monkeypatch.setattr(s, "red_field_items", lambda *args: (target,))
    monkeypatch.setattr(s, "field_item_is_available", lambda *args: state.available)
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *args, **kwargs: None)
    monkeypatch.setattr(s, "qualified_badge_gate_world", lambda world: world)
    monkeypatch.setattr(s, "_resource_passage_binding", lambda *args: None)
    from pokemon_red_completion import red_player_victory_road

    monkeypatch.setattr(red_player_victory_road, "observed_puzzle_world",
                        lambda world, reader: world.with_current_observation(reader))
    monkeypatch.setattr(
        s,
        "Gen1TraversalObserver",
        lambda *args, **kwargs: N(
            observe=lambda: N(map_id=raw.map_id, at=(raw.player_y, raw.player_x))
        ),
    )
    monkeypatch.setattr(s, "settle_story_interaction", lambda *args: None)
    monkeypatch.setattr(s, "face_pc_boundary", lambda *args: None)
    from pokemon_red_completion import red_story_map_frontier

    monkeypatch.setattr(
        red_story_map_frontier,
        "story_frontier_target",
        lambda world, start, destination: (
            (1, (0, 0)) if state.cycling else (2, (3, 4))
        ),
    )

    def pickup(actions, reader, item):
        assert item is target
        state.pickup_count += 1
        state.available = False
        state.payload = b"collected"
        raw.bag_items = ((82, 1),)
        if state.changed_cash:
            raw.player_money -= 1

    monkeypatch.setattr(s, "collect_visible_field_item", pickup)
    return runtime, actions, Route(route_world=World()), raw, state


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "unready",
        "full",
        "owned",
        "no_hp",
        "hidden",
        "absent",
        "moving",
        "wrong_picture",
        "blocked",
    ],
)
def test_field_resource_observation_never_acts_or_invents_stock(monkeypatch, fault):
    rt, actions, route, raw, state = fixture(monkeypatch)
    if fault == "unready":
        raw.ready = False
    if fault == "full":
        raw.bag_items = tuple((i, 1) for i in range(1, 21))
    if fault == "owned":
        raw.bag_items = ((82, 1),)
    if fault == "no_hp":
        raw.party_hp = (0,)
    if fault == "hidden":
        state.available = False
    if fault == "absent":
        state.present = False
    if fault == "moving":
        state.moving = True
    if fault == "wrong_picture":
        state.picture = 1
    if fault == "blocked":
        state.blocked = True
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    assert (binding is not None) is (fault is None)
    assert actions.actions_executed == rt.emulator.frame_count == 0
    assert state.payload == b"source" and state.pickup_count == 0
    if binding:
        assert binding.kind is GoalKind.RESUPPLY and binding.resource_quote is None
        assert binding.verify(None).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("require_complete_quote", [False, True])
@pytest.mark.parametrize("full_blocked", [False, True])
def test_complete_delivery_inventory_omits_only_unproven_prefixes(
    monkeypatch, require_complete_quote, full_blocked,
):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    state.full_blocked = full_blocked
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82,
                                           require_complete_quote=require_complete_quote)
    assert (binding is None) is (require_complete_quote and full_blocked)
    assert actions.actions_executed == rt.emulator.frame_count == state.pickup_count == 0
    assert state.payload == b"source" and raw.bag_items == () and raw.player_money == 9000
    if binding is not None:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert report.evidence["complete_delivery"] and report.evidence["quantity_acquired"] == 1


@pytest.mark.parametrize("invalid", [None, 0, 1, "true"])
def test_complete_delivery_mode_requires_a_boolean_before_input(monkeypatch, invalid):
    rt, actions, route, _, state = fixture(monkeypatch)
    with pytest.raises(TypeError, match="explicit boolean"):
        s.field_item_resupply_binding(rt, actions, route=route, item_id=82,
                                     require_complete_quote=invalid)
    assert actions.actions_executed == rt.emulator.frame_count == 0
    assert state.payload == b"source"


@pytest.mark.parametrize("remote", [False, True])
def test_resource_choice_requires_the_real_item_for_local_and_remote_delivery(monkeypatch, remote):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=remote)
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    receipt = binding.execute()
    assert binding.verify(receipt).status is GoalDecisionOutcome.SUCCEEDED
    assert receipt.evidence["quantity_acquired"] == 1
    assert receipt.evidence["complete_delivery"] is True
    assert receipt.evidence["learned_authority"] == "resource_goal_choice"
    assert receipt.evidence["purchases"] == receipt.evidence["cash_debit"] == 0
    assert raw.player_money == 9000
    assert state.pickup_count == 1
    assert raw.map_id == 145 and raw.bag_items == ((82, 1),) and not state.available
    assert s.field_item_resupply_binding(rt, actions, route=route, item_id=82) is None
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"different"
    assert binding.verify(receipt).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("fault", ["stale", "cash"])
def test_resource_failure_does_not_report_an_acquisition(monkeypatch, fault, remote):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=remote)
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    if fault == "stale":
        state.payload = b"different"
    else:
        state.changed_cash = True
    with pytest.raises((ValueError, RuntimeError)):
        binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED


def test_unreachable_remote_resource_does_not_offer_partial_stock_or_act(monkeypatch):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    state.blocked = True
    assert s.field_item_resupply_binding(rt, actions, route=route, item_id=82) is None
    assert raw.map_id == 1 and raw.bag_items == () and state.available
    assert actions.actions_executed == rt.emulator.frame_count == state.pickup_count == 0


@pytest.mark.parametrize("paid_map", sorted(s._PAID_SAFARI_MAPS))
@pytest.mark.parametrize("inside", [False, True])
def test_zero_debit_delivery_does_not_quote_unsupported_paid_safari_items(
    monkeypatch, paid_map, inside,
):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    raw.map_id = paid_map if inside else 1
    target = field.RedFieldItem(82, paid_map, 4, 61, (10, 12))
    monkeypatch.setattr(s, "red_field_items", lambda *args: (target,))
    assert s.field_item_resupply_binding(rt, actions, route=route, item_id=82) is None
    assert state.payload == b"source" and state.available and raw.bag_items == ()
    assert actions.actions_executed == rt.emulator.frame_count == state.pickup_count == 0


def test_paid_resource_cannot_hide_an_actual_free_delivery_peer(monkeypatch):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    free = field.RedFieldItem(82, 145, 4, 61, (10, 12))
    paid = field.RedFieldItem(82, min(s._PAID_SAFARI_MAPS), 4, 61, (10, 12))
    monkeypatch.setattr(s, "red_field_items", lambda *args: (paid, free))
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    assert binding is not None and actions.actions_executed == 0
    # The fixture's pickup checks object identity, so verify the selected target
    # before execution rather than replacing a native stock verifier.
    closure = dict(zip(binding.execute.__code__.co_freevars,
                       (cell.cell_contents for cell in binding.execute.__closure__), strict=True))
    assert closure["target"] is free


@pytest.mark.parametrize('remote',[False,True])
def test_uncomposed_delivery_target_is_not_an_executable_offer(monkeypatch,remote):
    rt,actions,route,raw,state=fixture(monkeypatch,remote=remote)
    assert s.field_item_resupply_binding(rt,actions,route=route,item_id=82,
        unsupported_target_maps=frozenset({145})) is None
    assert actions.actions_executed==rt.emulator.frame_count==state.pickup_count==0
    assert state.payload==b'source' and state.available and raw.bag_items==()


def test_uncomposed_target_does_not_mask_an_existing_qualified_peer(monkeypatch):
    rt,actions,route,raw,state=fixture(monkeypatch,remote=True)
    free=field.RedFieldItem(82,145,4,61,(10,12))
    uncomposed=field.RedFieldItem(82,216,4,61,(10,12))
    monkeypatch.setattr(s,'red_field_items',lambda *a:(uncomposed,free))
    binding=s.field_item_resupply_binding(rt,actions,route=route,item_id=82,
        unsupported_target_maps=frozenset({216}))
    closure=dict(zip(binding.execute.__code__.co_freevars,
                    (cell.cell_contents for cell in binding.execute.__closure__), strict=True))
    assert closure['target'] is free and actions.actions_executed==rt.emulator.frame_count==0


@pytest.mark.parametrize('invalid',[None,{145},frozenset({True}),
    frozenset({-1}),frozenset({256}),frozenset({'145'})])
def test_delivery_capability_exclusions_are_explicit_and_bounded(monkeypatch,invalid):
    rt,actions,route,raw,state=fixture(monkeypatch)
    with pytest.raises(ValueError,match='explicit map IDs'):
        s.field_item_resupply_binding(rt,actions,route=route,item_id=82,
            unsupported_target_maps=invalid)
    assert actions.actions_executed==rt.emulator.frame_count==0


def test_bounded_frontiers_are_internal_navigation_not_successful_resupply(monkeypatch):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    state.full_blocked = True
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    assert actions.actions_executed == state.pickup_count == 0
    receipt = binding.execute()
    assert binding.verify(receipt).status is GoalDecisionOutcome.SUCCEEDED
    assert actions.actions_executed == 2 and state.pickup_count == 1
    assert receipt.evidence["quoted_navigation_transitions"] == 2
    assert receipt.evidence["quantity_acquired"] == 1 and raw.map_id == 145


def test_cycling_frontier_cannot_receive_stock_or_report_success(monkeypatch):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    state.full_blocked = state.cycling = True
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    with pytest.raises(RuntimeError, match="did not advance"):
        binding.execute()
    assert actions.actions_executed == 1 and state.pickup_count == 0
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    assert raw.bag_items == () and state.available


@pytest.mark.parametrize("fault", [None, "both_blocked", "wrong_map"])
def test_unreachable_preferred_arrival_uses_only_a_real_same_map_frontier(monkeypatch, fault):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    state.full_blocked = state.preferred_frontier_blocked = True
    state.alternate_frontier_blocked = fault == "both_blocked"
    state.wrong_frontier_map = fault == "wrong_map"
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    assert actions.actions_executed == rt.emulator.frame_count == state.pickup_count == 0
    assert (binding is not None) is (fault is None)
    if fault:
        assert raw.map_id == 1 and raw.bag_items == () and state.available
        return
    receipt = binding.execute()
    assert binding.verify(receipt).status is GoalDecisionOutcome.SUCCEEDED
    assert receipt.evidence["quoted_navigation_transitions"] == 2
    assert state.pickup_count == 1 and raw.bag_items == ((82, 1),)
    assert raw.map_id == 145 and raw.player_money == 9000


@pytest.mark.parametrize("allow_surf", [False, True])
def test_resource_quotes_use_only_the_routes_legal_field_move_scope(monkeypatch, allow_surf):
    rt, actions, route, raw, state = fixture(monkeypatch)
    route.allow_surf = allow_surf
    projections = []
    worlds = []
    monkeypatch.setattr(s, "cut_capabilities", lambda r: frozenset({"cut"}))

    def field_capabilities(emulator, observed):
        assert emulator is rt.emulator and observed.map_id == raw.map_id
        return frozenset({"cut", "surf", "strength"})

    def observer(reader, *, capability_projector, hazard_projector):
        projections.append(capability_projector(reader.read()))
        return N(observe=lambda: N(map_id=raw.map_id, at=(raw.player_y, raw.player_x)))

    monkeypatch.setattr(s, "gen1_field_capabilities", field_capabilities)
    monkeypatch.setattr(s, "Gen1TraversalObserver", observer)
    monkeypatch.setattr(s, "qualified_badge_gate_world",
                        lambda world: worlds.append(world) or world)
    assert s.field_item_resupply_binding(rt, actions, route=route, item_id=82) is not None
    assert worlds == [route.route_world]
    assert projections == [
        frozenset({"cut", "surf", "strength"}) if allow_surf else frozenset({"cut"})
    ]
    assert actions.actions_executed == rt.emulator.frame_count == 0
    assert state.payload == b"source" and state.pickup_count == 0


@pytest.mark.parametrize("fault", [None, "unverified", "objective_credit", "no_progress", "cash"])
def test_resource_delivery_reuses_verified_passage_without_crediting_a_prefix(monkeypatch, fault):
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification

    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    raw.event_flags = b"\x00"
    state.full_blocked = True
    report = GoalExecutionReport(1, 10, dict(
        phase="observed-switch", objective_completed=fault == "objective_credit"))

    def reopen():
        actions.actions_executed += 1
        rt.emulator.frame_count += 10
        state.payload = b"gate-opened"
        if fault != "no_progress":
            raw.event_flags = b"\x01"
            state.full_blocked = False
        if fault == "cash":
            raw.player_money -= 1
        return report

    passage = N(estimated_effort=0.2, execute=reopen, verify=lambda _: (
        GoalVerification.failed(s.GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if fault == "unverified" else GoalVerification.succeeded()))
    monkeypatch.setattr(s, "_resource_passage_binding", lambda *args: passage)
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    assert binding is not None
    assert actions.actions_executed == rt.emulator.frame_count == state.pickup_count == 0
    if fault:
        with pytest.raises(RuntimeError):
            binding.execute()
        assert binding.verify(None).status is GoalDecisionOutcome.FAILED
        if fault != "cash":
            assert state.pickup_count == 0 and raw.bag_items == () and state.available
        return
    receipt = binding.execute()
    assert binding.verify(receipt).status is GoalDecisionOutcome.SUCCEEDED
    assert receipt.evidence["reopened_passages"] == [report.evidence]
    assert receipt.evidence["objective_completed"] is False
    assert receipt.evidence["complete_delivery"] is True
    assert state.pickup_count == 1 and raw.bag_items == ((82, 1),)
    assert actions.actions_executed == 2 and raw.player_money == 9000


def test_direct_delivery_does_not_replay_unneeded_puzzles(monkeypatch):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)

    def forbidden(*args):
        raise AssertionError("A fully feasible delivery needs no puzzle")

    monkeypatch.setattr(s, "_resource_passage_binding", forbidden)
    binding = s.field_item_resupply_binding(rt, actions, route=route, item_id=82)
    receipt = binding.execute()
    assert binding.verify(receipt).status is GoalDecisionOutcome.SUCCEEDED
    assert receipt.evidence["reopened_passages"] == []


@pytest.mark.parametrize("fault", [None, "cash", "bag", "hp", "moves", "status",
                                  "levels", "badge", "event", "unknown", "late_mutation"])
def test_fresh_route_gap_is_failed_only_with_exact_native_preservation(monkeypatch, fault):
    rt, actions, route, raw, state = fixture(monkeypatch, remote=True)
    raw.party_levels=(50,)
    raw.party_max_hp=(100,)
    raw.party_status=(0,)
    raw.party_moves=((33,39,58,57),)
    raw.party_pp=((35,30,10,15),)
    raw.event_flags=b"stable"
    if fault == "unknown":
        raw.party_pp=None
    state.full_blocked=True
    original=type(route).__call__

    def arrive(self, a, reader, em):
        original(self, a, reader, em)
        state.blocked=True
        if fault == "cash":
            raw.player_money-=1
        elif fault == "bag":
            raw.bag_items=((1,1),)
        elif fault == "hp":
            raw.party_hp=(99,)
        elif fault == "moves":
            raw.party_moves=((33,39,59,57),)
        elif fault == "status":
            raw.party_status=(1,)
        elif fault == "levels":
            raw.party_levels=(51,)
        elif fault == "badge":
            raw.badge_bits=127
        elif fault == "event":
            raw.event_flags=b"changed"

    monkeypatch.setattr(type(route),"__call__",arrive)
    binding=s.field_item_resupply_binding(rt,actions,route=route,item_id=82)
    assert binding is not None and actions.actions_executed==rt.emulator.frame_count==0
    if fault not in {None,"late_mutation"}:
        with pytest.raises(RuntimeError,match="no verified safe route stop"):
            binding.execute()
        assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    else:
        report=binding.execute()
        assert report.actions_executed==1 and report.frames_executed==10
        assert report.evidence["schema"]=="pokemon.red.field-delivery-route-stop.v1"
        assert report.evidence["route_unavailable"] and report.evidence["quantity_acquired"]==0
        assert report.evidence["complete_delivery"] is False
        assert binding.verify(report).failure_reason is s.GoalFailureReason.OUTCOME_NOT_VERIFIED
        if fault == "late_mutation":
            raw.bag_items=((1,1),)
            assert binding.verify(report).failure_reason is s.GoalFailureReason.WORLD_STATE_DIVERGED
    assert state.pickup_count==0
    with pytest.raises(ValueError,match="consumed"):
        binding.execute()


def test_reset_passage_quote_uses_only_current_floor_existing_contracts(monkeypatch):
    from pokemon_red_completion import gen1_boulder_switch as puzzles
    from pokemon_red_completion import red_player_victory_road as native

    raw = N(map_id=194)
    runtime = N(reader=N(read=lambda: raw))
    route = N(rom=b"rom")
    first, second, third, final = (N(map_id=i) for i in (108, 194, 198, 194))
    monkeypatch.setattr(puzzles, "victory_road_first_switch", lambda rom: first)
    monkeypatch.setattr(puzzles, "victory_road_second_switches", lambda rom: (second, final))
    monkeypatch.setattr(puzzles, "victory_road_third_floor", lambda rom: (third, None))
    calls = []
    bound = object()

    def option(rt, actions, current_route, name, contract, record):
        calls.append((name, contract))
        return None if contract is second else (bound, None)

    monkeypatch.setattr(native, "_puzzle_option", option)
    assert s._resource_passage_binding(runtime, None, route) is bound
    assert calls == [("second-switch", second), ("final-switch", final)]
    raw.map_id = 9
    calls.clear()
    assert s._resource_passage_binding(runtime, None, route) is None and calls == []
