from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_field_goals as f
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification


def setup(monkeypatch):
    raw = N(
        game_started=True,
        map_id=1,
        battle_state=0,
        party_hp=(20,),
        bag_items=(),
        player_money=1500,
        player_y=26,
        player_x=23,
    )
    state = N(
        got_pokedex=False,
        oak_got_parcel=False,
        lab_script=18,
        battled_rival=True,
        first_party_species=177,
        got_oaks_parcel=False,
        parcel_in_bag=False,
        pokedex_snapshot=False,
        pokedex_departure_dialogue=False,
    )
    em = N(pressed_buttons=(), frame_count=0, save_state_bytes=lambda: b"source")
    reader = N(
        read=lambda: raw,
        read_input_readiness=lambda: N(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
        read_oaks_errand_state=lambda _: state,
        read_player_facing=lambda: "up",
        read_current_map_objects=lambda: [N(picture_id=3, at=(2, 5))],
    )
    lesson = dict(
        completed_objectives=["begin_adventure", "choose_starter", "power_on"],
        party=[dict(specimen_ref="s", species_id=177, level=5, experience=159)],
    )
    rt = N(
        reader=reader,
        emulator=em,
        adapter=object(),
        observer=N(latch_verified_facts=lambda _: None),
    )
    monkeypatch.setattr(f, "capture_player_lesson_snapshot", lambda _: (N(raw=raw), lesson.copy()))
    monkeypatch.setattr(
        f, "map_objects", lambda _: {40: [N(text_and_kind=5, sprite=3, movement=255, y=2, x=5)]}
    )

    def observer(reader, **kwargs):
        if kwargs:
            assert kwargs == {"capability_projector": f.cut_capabilities}
        return N(observe=lambda: N())

    monkeypatch.setattr(f, "Gen1TraversalObserver", observer)
    calls = []
    actions = N(actions_executed=0)

    def act(a):
        calls.append(a)
        actions.actions_executed += 1
        em.frame_count += 10

    actions.execute = act

    @dataclass
    class Route:
        rom: bytes = b"rom"
        destination_map: int = 1
        destination_at: tuple = (0, 0)
        maximum_scripted_dialogues: int = 0
        allow_wild_faints: bool = False
        allow_field_faint_dialogue: bool = False

        @property
        def route_world(self):
            return N(
                plan_feasible_to_map=lambda *a, **k: N(cost=10, steps=(1,), terminal_at=(7, 3))
            )

        def __call__(self, *a):
            if self.maximum_scripted_dialogues:
                assert not self.allow_wild_faints and not self.allow_field_faint_dialogue
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            act("travel")

    def parcel(*a):
        state.got_oaks_parcel = state.parcel_in_bag = True

    def dex(*a):
        state.pokedex_snapshot = state.got_pokedex = True
        lesson["completed_objectives"] = lesson["completed_objectives"] + ["receive_pokedex"]

    monkeypatch.setattr(f, "_receive_parcel", parcel)
    monkeypatch.setattr(f, "_receive_pokedex", dex)
    return rt, actions, Route(), state, lesson, calls


@pytest.mark.parametrize("faint_recovery", [False, True])
def test_parcel_is_action_free_until_selected_and_checks_native_result(monkeypatch, faint_recovery):
    rt, a, route, state, lesson, calls = setup(monkeypatch)
    route.allow_wild_faints = route.allow_field_faint_dialogue = faint_recovery
    binding = f.parcel_story_binding(rt, a, route=route)
    assert binding.kind is GoalKind.ADVANCE_STORY and calls == []
    report = binding.execute()
    assert route.allow_wild_faints is faint_recovery
    assert route.allow_field_faint_dialogue is faint_recovery
    assert not report.evidence["lab_rival_replayed"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    state.pokedex_snapshot = False
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize(
    "field,value",
    [
        ("got_pokedex", True),
        ("oak_got_parcel", True),
        ("lab_script", 6),
        ("first_party_species", 99),
        ("got_oaks_parcel", True),
        ("battled_rival", False),
    ],
)
def test_parcel_masks_unmet_or_inconsistent_prerequisites(monkeypatch, field, value):
    rt, a, route, state, _, calls = setup(monkeypatch)
    setattr(state, field, value)
    assert f.parcel_story_binding(rt, a, route=route) is None and not calls


def test_parcel_possession_and_noop_script_do_not_replace_native_rival_flag(monkeypatch):
    rt, a, route, state, _, calls = setup(monkeypatch)
    state.got_oaks_parcel = state.parcel_in_bag = True
    rt.reader.read().bag_items = ((70, 1),)
    state.battled_rival = False
    assert f.parcel_story_binding(rt, a, route=route) is None and not calls


def test_stale_parcel_sends_no_input(monkeypatch):
    rt, a, route, _, _, calls = setup(monkeypatch)
    binding = f.parcel_story_binding(rt, a, route=route)
    rt.emulator.save_state_bytes = lambda: b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls


def test_center_selection_rechecks_current_feasibility_and_cost(monkeypatch):
    rt, actions, route, _, _, calls = setup(monkeypatch)

    def observer(*a, **k):
        assert k["capability_projector"] is f.cut_capabilities
        return N(observe=lambda: object())

    monkeypatch.setattr(f, "Gen1TraversalObserver", observer)
    monkeypatch.setattr(f, "Gen1TrainerSightProjector", lambda *a, **k: object())
    costs = {41: 180, 58: 35}

    def plan(start, center, **kwargs):
        assert kwargs["goal_at"] == (3, 3)
        if center not in costs:
            raise f.RoutePlanningError("blocked")
        return N(cost=costs[center])

    monkeypatch.setattr(
        type(route), "route_world", property(lambda _: N(plan_feasible_to_map=plan))
    )
    centers = frozenset({41, 58})
    assert f.nearest_reachable_player_center(rt, route=route, centers=centers) == 58
    del costs[58]
    assert f.nearest_reachable_player_center(rt, route=route, centers=centers) == 41
    costs.clear()
    assert f.nearest_reachable_player_center(rt, route=route, centers=centers) is None
    assert actions.actions_executed == 0 and not calls


@pytest.mark.parametrize("permission", (False, True, None, 1))
def test_indigo_nurse_inventory_requires_explicit_existing_service_opt_in(monkeypatch, permission):
    rt, actions, route, _, _, calls = setup(monkeypatch)
    monkeypatch.setattr(f, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(f, "Gen1TrainerSightProjector", lambda *a, **k: object())
    quoted = []

    def plan(_start, center, *, goal_at):
        quoted.append((center, goal_at))
        return N(cost=3)

    monkeypatch.setattr(type(route), "route_world",
        property(lambda _: N(plan_feasible_to_map=plan)))
    arguments = dict(route=route,centers=frozenset({int(f.MapId.INDIGO_PLATEAU_LOBBY)}),
                     include_indigo_lobby=permission)
    if permission is True:
        assert f.nearest_reachable_player_center(rt,**arguments) == f.MapId.INDIGO_PLATEAU_LOBBY
        assert quoted == [(int(f.MapId.INDIGO_PLATEAU_LOBBY),(7,7))]
    else:
        with pytest.raises((TypeError,ValueError)):
            f.nearest_reachable_player_center(rt,**arguments)
        assert not quoted
    assert actions.actions_executed == 0 and not calls


@pytest.mark.parametrize("guarded", [False, True])
@pytest.mark.parametrize("blocked", [False, True])
def test_restoration_quote_can_match_current_trainer_reservation(monkeypatch, guarded, blocked):
    rt, actions, route, _, _, calls = setup(monkeypatch)
    projector = object()
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: False)
    monkeypatch.setattr(f, "Gen1TrainerSightProjector", lambda *a, **k: projector)
    monkeypatch.setattr(f, "certified_cash_safe_transition", lambda *a: None)

    def observer(*args, **kwargs):
        assert kwargs["capability_projector"] is f.cut_capabilities
        assert kwargs.get("hazard_projector") is (projector if guarded else None)
        return N(observe=lambda: N(hazards=(projector,) if guarded else ()))

    def plan(start, home, **kwargs):
        assert home == 41 and kwargs["goal_at"] == (3, 3)
        if blocked and start.hazards:
            raise f.RoutePlanningError("actual current trainer sight blocks this clinic")
        return N(cost=10, steps=(1,), terminal_at=(3, 3))

    monkeypatch.setattr(f, "Gen1TraversalObserver", observer)
    monkeypatch.setattr(
        type(route), "route_world", property(lambda _: N(plan_feasible_to_map=plan))
    )
    binding = f.routed_restoration_binding(
        rt,
        actions,
        home_map=41,
        route=route,
        observe_trainer_hazards=guarded,
    )
    assert (binding is None) == (guarded and blocked)
    assert actions.actions_executed == rt.emulator.frame_count == 0 and not calls


@pytest.mark.parametrize("walking", [False, True])
@pytest.mark.parametrize("poisoned", [False, True])
def test_nurse_without_walking_has_no_travel_cash_exposure(monkeypatch, walking, poisoned):
    rt, actions, route, _, _, calls = setup(monkeypatch)
    raw = rt.reader.read()
    raw.map_id, raw.player_y, raw.player_x = 41, 3, 3
    raw.party_status = (8 if poisoned else 0,)
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: False)
    monkeypatch.setattr(f, "certified_cash_safe_transition", lambda *a: None)
    monkeypatch.setattr(type(route), "route_world", property(lambda _: N(
        plan_feasible_to_map=lambda *a, **k: N(
            cost=10 if walking else 0, steps=(1,) if walking else (), terminal_at=(3, 3)
        )
    )))
    binding = f.routed_restoration_binding(rt, actions, home_map=41, route=route)
    assert binding.maximum_cash_debit == (None if walking else 0)
    assert actions.actions_executed == rt.emulator.frame_count == 0 and not calls


@pytest.mark.parametrize("value", [None, 1, "yes", []])
def test_restoration_trainer_observation_requires_explicit_boolean(value):
    with pytest.raises(TypeError, match="trainer observation"):
        f.routed_restoration_binding(
            None, None, home_map=41, route=None, observe_trainer_hazards=value
        )


@pytest.mark.parametrize("fault", [None,"anchor_unchanged","already_indigo","default"])
def test_healthy_indigo_nursing_requires_actual_checkpoint_when_opted_in(monkeypatch,fault):
    rt,actions,route,_,lesson,calls=setup(monkeypatch)
    raw=rt.reader.read()
    raw.map_id,raw.player_y,raw.player_x=174,7,7
    anchor=[9 if fault == "already_indigo" else 7]
    rt.reader.read_last_blackout_map=lambda:anchor[0]
    rt.adapter=N(observe=lambda:object())
    lesson["party"][0]["moves"]=[(19,15)]
    monkeypatch.setattr(f,"_raw_party_fully_restored",lambda _:True)
    monkeypatch.setattr(f,"certified_cash_safe_transition",lambda *a:None)
    monkeypatch.setattr(f,"restoration_progress_preserved",lambda *a:True)
    monkeypatch.setattr(type(route),"route_world",property(lambda _:N(
        plan_feasible_to_map=lambda *a,**k:N(cost=0,steps=(),terminal_at=(7,7)))))

    def nurse():
        actions.execute("normal-nurse")
        if fault != "anchor_unchanged":
            anchor[0]=9
        return GoalExecutionReport(1,10,{"whole_party_restore":True})

    child=N(execute=nurse,verify=lambda _:GoalVerification.succeeded())

    class Provider:
        def __init__(self,*a,**k):
            assert k == dict(require_full_pp_restore=True,include_indigo_lobby=True,
                             require_indigo_checkpoint=True)

        def offer(self,*a):
            return N(binding=child)

    monkeypatch.setattr(f,"RedCenterRestoreGoalProvider",Provider)
    binding=f.routed_restoration_binding(rt,actions,home_map=174,route=route,
        include_indigo_lobby=True,require_indigo_checkpoint=fault != "default")
    if fault in {"default","already_indigo"}:
        assert binding is None and not calls
        return
    assert binding is not None and not calls
    report=binding.execute()
    assert calls == ["normal-nurse"]
    assert binding.verify(report).status is (
        GoalDecisionOutcome.FAILED if fault == "anchor_unchanged" else GoalDecisionOutcome.SUCCEEDED
    )


@pytest.mark.parametrize("home,include,alternatives", [(41,False,frozenset()),
    (174,False,frozenset()),(174,True,frozenset({41}))])
def test_indigo_checkpoint_cannot_substitute_another_center(home,include,alternatives):
    with pytest.raises(ValueError,match="exact lobby"):
        f.routed_restoration_binding(None,None,home_map=home,route=None,
            include_indigo_lobby=include,alternate_centers=alternatives,
            require_indigo_checkpoint=True)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "default",
        "not_poisoned",
        "cash",
        "map",
        "bag",
        "experience",
        "event",
        "unready",
        "not_restored",
        "other_error",
        "no_input",
    ],
)
@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("party_count", [1, 6])
def test_poison_blackout_is_a_measured_failed_restoration_not_a_forgiven_route(
    monkeypatch, fault, pending, party_count,
):
    from copy import deepcopy
    from dataclasses import replace

    from pokemon_red_completion.goal_manager import GoalFailureReason

    rt, actions, route, _, lesson, _ = setup(monkeypatch)
    raw = rt.reader.read()
    # The fresh player can return with only one conscious, poisoned member.
    # Its final field faint must preserve every already-fainted individual.
    raw.party_hp = (7,) + (0,) * (party_count - 1)
    raw.party_status = (0 if fault == "not_poisoned" else 8,) + (0,) * (party_count - 1)
    raw.party_count, raw.party_species_ids = party_count, (177,) * party_count
    raw.party_moves, raw.party_levels = ((33, 39, 145, 0),) * party_count, (6,) * party_count
    raw.badge_bits, raw.event_flags = 0, b"events"
    lesson["objective_catalog"] = list(lesson["completed_objectives"])
    lesson["party"][0]["moves"] = [[33, 35], [39, 30], [145, 30], [0, 0]]
    lesson["party"] = [dict(deepcopy(lesson["party"][0]), specimen_ref=f"retained-{i}")
                       for i in range(party_count)]
    rt.reader.read_last_blackout_map = lambda: 2
    rt.reader.read_input_readiness = lambda: N(
        ready=bool(any(raw.party_hp)) and not (fault == "unready" and raw.map_id == 2)
    )
    rt.reader.read_bottom_dialogue_box_visible = lambda: pending and not any(raw.party_hp)
    rt.emulator.save_state_bytes = lambda: str(rt.emulator.frame_count).encode()
    monkeypatch.setattr(
        f, "capture_player_lesson_snapshot", lambda _: (N(raw=deepcopy(raw)), deepcopy(lesson))
    )
    monkeypatch.setattr(
        f,
        "_raw_party_fully_restored",
        lambda r: r.map_id == 2 and r.party_status == (0,) * party_count
        and fault != "not_restored",
    )
    monkeypatch.setattr(f, "certified_cash_safe_transition", lambda *a: route)

    def blackout(*args):
        if fault != "no_input":
            actions.execute("walk")
        raw.map_id, raw.player_y, raw.player_x = (47 if pending else 2), 26, 13
        raw.party_hp, raw.party_status, raw.player_money = (
            (0,) * party_count if pending else (20,) * party_count,
            (0,) * party_count, 1500 if pending else 750
        )
        if fault == "cash":
            raw.player_money = 749
        if fault == "map":
            raw.map_id = 3
        if fault == "bag":
            raw.bag_items = ((1, 1),)
        if fault == "experience":
            lesson["party"][0]["experience"] += 1
        if fault == "event":
            raw.event_flags = b"changed"
        if fault == "other_error":
            raise RuntimeError("unknown route failure")
        raise f.RouteExecutionError("observed native teleport")

    monkeypatch.setattr(type(route), "__call__", blackout)
    settlements = []

    def settle(actions, reader, emulator, *, allow_field_loss):
        assert pending and allow_field_loss
        assert not any(reader.read().party_hp) and reader.read_bottom_dialogue_box_visible()
        settlements.append(True)
        actions.execute("confirm-native-blackout")
        if fault != "map":
            raw.map_id = 2
        raw.party_hp, raw.player_money = (20,) * party_count, 750
        return dict(blackout_verified=True)

    monkeypatch.setattr(f, "settle_red_blackout", settle)
    binding = f.routed_restoration_binding(
        rt, actions, home_map=41, route=route, allow_blackout_return=fault != "default"
    )
    assert binding is not None and actions.actions_executed == 0
    if fault is not None:
        with pytest.raises(RuntimeError):
            binding.execute()
        return
    assert binding.maximum_cash_debit is None
    report = binding.execute()
    assert report.actions_executed == (2 if pending else 1)
    assert report.frames_executed == (20 if pending else 10)
    assert settlements == ([True] if pending else [])
    receipt = report.evidence["native_blackout_during_selected_restoration"]
    assert receipt["cash_lost"] == 750 and not receipt["learned_recovery"]
    assert receipt["pending_dialogue_settled"] is pending
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST
    assert (
        binding.verify(replace(report, evidence={})).failure_reason
        is GoalFailureReason.OUTCOME_NOT_VERIFIED
    )
    rt.emulator.frame_count += 1
    assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


def test_restoration_blackout_opt_in_is_not_truthy_coercion(monkeypatch):
    rt, actions, route, *_ = setup(monkeypatch)
    with pytest.raises(TypeError, match="explicit restoration"):
        f.routed_restoration_binding(rt, actions, home_map=41, route=route, allow_blackout_return=1)


@pytest.mark.parametrize("fault", [None, "default", "same_map", "cash", "bag", "party",
    "unready", "other_reason", "no_alternative", "second_failure", "not_healed"])
def test_selected_healing_can_replan_once_to_declared_alternate_center(monkeypatch, fault):
    from copy import deepcopy

    rt, actions, route, _, lesson, _ = setup(monkeypatch)
    raw, healed, calls = rt.reader.read(), [False], []
    rt.adapter = N(observe=lambda: object())
    lesson["objective_catalog"] = list(lesson["completed_objectives"])
    lesson["party"][0]["moves"] = [[33, 35]]
    monkeypatch.setattr(f, "capture_player_lesson_snapshot",
        lambda _: (N(raw=deepcopy(raw)), deepcopy(lesson)))
    rt.reader.read_input_readiness = lambda: N(ready=not (fault == "unready" and raw.map_id == 82))
    rt.emulator.save_state_bytes = lambda: str(rt.emulator.frame_count).encode()
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: healed[0])
    monkeypatch.setattr(f, "certified_cash_safe_transition", lambda *a: None)
    selected = []

    def nearest(runtime, *, route, centers):
        selected.append(centers)
        assert centers == frozenset({41})
        return None if fault == "no_alternative" else 41

    monkeypatch.setattr(f, "nearest_reachable_player_center", nearest)

    def travel(self, *args):
        calls.append(self.destination_map)
        actions.execute("walk")
        if len(calls) == 1:
            raw.map_id = 1 if fault == "same_map" else 82
            if fault == "cash":
                raw.player_money -= 1
            if fault == "bag":
                raw.bag_items = ((1, 1),)
            if fault == "party":
                lesson["party"][0]["experience"] += 1
            reason = (f.RouteExecutionFailureReason.WORLD_STATE_DIVERGED
                if fault == "other_reason" else f.RouteExecutionFailureReason.PLANNER_NO_ROUTE)
            raise f.RouteExecutionError("retained route cannot reach original nurse", reason=reason)
        if fault == "second_failure":
            raise f.RouteExecutionError("alternate also blocked",
                reason=f.RouteExecutionFailureReason.PLANNER_NO_ROUTE)
        raw.map_id, (raw.player_y, raw.player_x) = self.destination_map, self.destination_at

    monkeypatch.setattr(type(route), "__call__", travel)

    def nurse():
        assert raw.map_id == 41
        actions.execute("nurse")
        healed[0] = fault != "not_healed"
        return GoalExecutionReport(1, 10, dict(verified=True))

    child = N(execute=nurse, verify=lambda _: GoalVerification.succeeded())
    monkeypatch.setattr(f, "RedCenterRestoreGoalProvider",
        lambda *a, **k: N(offer=lambda _: N(binding=child)))
    binding = f.routed_restoration_binding(rt, actions, home_map=141, route=route,
        alternate_centers=frozenset() if fault == "default" else frozenset({41, 141}))
    assert binding is not None and not calls
    if fault in {None, "not_healed"}:
        report = binding.execute()
        assert calls == [141, 41] and selected == [frozenset({41})]
        assert report.actions_executed == 3 and report.frames_executed == 30
        receipt = report.evidence["alternate_center_replan"]
        assert receipt["original_center"] == 141 and receipt["actual_center"] == 41
        assert receipt["goal_kind_unchanged"] and receipt["model_goal_queries"] == 0
        verdict = binding.verify(report)
        assert verdict.status is (GoalDecisionOutcome.FAILED if fault == "not_healed"
                                  else GoalDecisionOutcome.SUCCEEDED)
    else:
        with pytest.raises(f.RouteExecutionError):
            binding.execute()
        if fault not in {"no_alternative", "second_failure"}:
            assert not selected and calls == [141]


@pytest.mark.parametrize("centers", [None, {41}, frozenset({True}), frozenset({999})])
def test_restoration_alternatives_fail_closed_before_input(monkeypatch, centers):
    rt, actions, route, _, _, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="declared ordinary"):
        f.routed_restoration_binding(rt, actions, home_map=41, route=route,
            alternate_centers=centers)
    assert actions.actions_executed == 0


@pytest.mark.parametrize("fault", ["missing_oak", "money", "party"])
def test_delivery_does_not_hide_unverified_changes(monkeypatch, fault):
    rt, a, route, _, lesson, _ = setup(monkeypatch)
    binding = f.parcel_story_binding(rt, a, route=route)
    if fault == "missing_oak":
        rt.reader.read_current_map_objects = lambda: []
        with pytest.raises(RuntimeError, match="Oak absent"):
            binding.execute()
        return
    report = binding.execute()
    if fault == "money":
        rt.reader.read().player_money = 1000
    else:
        lesson["party"] = [dict(specimen_ref="changed", species_id=177, level=5, experience=159)]
    # Native RawGameState is immutable; replace the observed terminal for cash tampering.
    if fault == "money":
        from copy import copy

        new = copy(rt.reader.read())
        rt.reader.read().player_money = 1500
        new.player_money = 1000
        monkeypatch.setattr(f, "capture_player_lesson_snapshot", lambda _: (N(raw=new), lesson))
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def preparation_quote_fixture(monkeypatch, runtime, route):
    """Typed action-free geometry for tests of fresh child/restoration ownership."""
    from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroPath, MacroTransition
    from pokemon_red_completion.local_router import LocalEdge, LocalPath
    from pokemon_red_completion.route_executor import TraversalSnapshot
    from pokemon_red_completion.route_plan import RoutePlan, RouteSegment

    graph = MacroGraph({}, outside_nodes=frozenset({1}))

    def quote(start, destination, *, goal_at):
        if destination == start.map_id:
            local = None if start.at == goal_at else LocalPath(
                (start.at, goal_at), (LocalEdge(goal_at, "up", cost=10),),
                (start.mode, start.mode),
            )
            return RoutePlan(
                MacroPath((start.map_id,), ()), start.at, start.mode, (), local,
                goal_at, start.mode,
            )
        edge = MacroEdge(destination, cost=10)
        graph.edges[start.map_id] = (*graph.neighbors(start.map_id), edge)
        segment = RouteSegment(
            start.map_id, destination, LocalPath((start.at,), (), (start.mode,)),
            MacroTransition(start.at, goal_at, "up"), "connection", False,
        )
        return RoutePlan(
            MacroPath((start.map_id, destination), (edge,)), start.at, start.mode,
            (segment,), None, goal_at, start.mode,
        )

    world = N(rom=route.rom, macro_graph=graph, plan_feasible_to_map=quote)
    monkeypatch.setattr(type(route), "route_world", property(lambda _: world))

    def observe():
        raw = runtime.reader.read()
        return TraversalSnapshot(
            raw.map_id, (raw.player_y, raw.player_x), True, mode="land",
            last_outside_map=1,
        )

    monkeypatch.setattr(f, "Gen1TraversalObserver", lambda *a, **k: N(observe=observe))
    return N(map_id=12, origin_at=(2, 2))


@pytest.mark.parametrize("missing", [False, True])
def test_preparation_rebinds_at_arrival_not_before(monkeypatch, missing):
    rt, a, route, _, _, calls = setup(monkeypatch)
    corridor = preparation_quote_fixture(monkeypatch, rt, route)
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: True)
    monkeypatch.setattr(f, "observe_preparation_members", lambda *a: ())
    monkeypatch.setattr(f, "preparation_trainee", lambda *a: object())
    bound = []

    def fresh(*args, **kwargs):
        bound.append(rt.reader.read().player_y)
        return (
            None
            if missing
            else N(
                execute=lambda: GoalExecutionReport(0, 0, {}),
                verify=lambda _: GoalVerification.succeeded(),
            )
        )

    monkeypatch.setattr(f, "preparation_binding", fresh)
    binding = f.routed_preparation_binding(
        rt, a, home_map=41, route=route, battler=N(session=rt.emulator), plan=object(),
        corridor=corridor,
    )
    assert not calls and not bound
    if missing:
        with pytest.raises(RuntimeError, match="actual destination"):
            binding.execute()
    else:
        report = binding.execute()
        assert report.actions_executed == 1
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert bound == [3]


def test_routed_indigo_preparation_retains_same_executor_at_nurse(monkeypatch):
    from pokemon_red_completion.observation import MapId

    rt, actions, route, _, _, calls = setup(monkeypatch)
    corridor = preparation_quote_fixture(monkeypatch, rt, route)
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: True)
    monkeypatch.setattr(f, "observe_preparation_members", lambda *a: ())
    monkeypatch.setattr(f, "preparation_trainee", lambda *a: object())
    bound = []

    def fresh(*args, **kwargs):
        bound.append(
            (
                rt.reader.read().map_id,
                rt.reader.read().player_y,
                rt.reader.read().player_x,
                kwargs.get("include_indigo_lobby"),
            )
        )
        return N(
            execute=lambda: GoalExecutionReport(0, 0, {}),
            verify=lambda _: GoalVerification.succeeded(),
        )

    monkeypatch.setattr(f, "preparation_binding", fresh)
    with pytest.raises(ValueError, match="supported Center"):
        f.routed_preparation_binding(
            rt,
            actions,
            home_map=int(MapId.INDIGO_PLATEAU_LOBBY),
            route=route,
            battler=N(session=rt.emulator),
            plan=object(),
            corridor=corridor,
        )
    binding = f.routed_preparation_binding(
        rt,
        actions,
        home_map=int(MapId.INDIGO_PLATEAU_LOBBY),
        route=route,
        include_indigo_lobby=True,
        battler=N(session=rt.emulator),
        plan=object(),
        corridor=corridor,
    )
    assert not calls and not bound
    report = binding.execute()
    assert bound == [(int(MapId.INDIGO_PLATEAU_LOBBY), 7, 7, True)]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    "map_id,rival,available", [(40, False, False), (40, True, True), (1, False, True)]
)
def test_field_preparation_cannot_bypass_opening_battle(monkeypatch, map_id, rival, available):
    rt, a, route, state, _, calls = setup(monkeypatch)
    corridor = preparation_quote_fixture(monkeypatch, rt, route)
    rt.reader.read().map_id = map_id
    state.battled_rival = rival
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: True)
    monkeypatch.setattr(f, "observe_preparation_members", lambda *a: ())
    monkeypatch.setattr(f, "preparation_trainee", lambda *a: object())
    binding = f.routed_preparation_binding(
        rt, a, home_map=41, route=route, battler=N(session=rt.emulator), plan=object(),
        corridor=corridor,
    )
    assert (binding is not None) is available
    assert not calls


@pytest.mark.parametrize("qualified,completes", [(True, True), (False, True), (True, False)])
def test_only_observed_late_handoff_can_use_bounded_recovery(monkeypatch, qualified, completes):
    rt, a, route, state, lesson, calls = setup(monkeypatch)
    state.pokedex_departure_dialogue = qualified

    def stopped(*args):
        raise f.QualifiedPlayError("bounded dialogue stopped")

    monkeypatch.setattr(f, "_receive_pokedex", stopped)
    recovered = []

    def recover(self):
        recovered.append(True)
        self.actions.execute("bounded recovery")
        state.pokedex_snapshot = completes
        if completes:
            lesson["completed_objectives"].append("receive_pokedex")
        return 1

    monkeypatch.setattr(f.RedControlRecoveryGoalProvider, "_recover", recover)
    binding = f.parcel_story_binding(rt, a, route=route)
    if not qualified:
        with pytest.raises(f.QualifiedPlayError):
            binding.execute()
        assert not recovered
    elif not completes:
        with pytest.raises(RuntimeError, match="Pokedex gate"):
            binding.execute()
    else:
        report = binding.execute()
        assert report.evidence["bounded_handoff_recovery"]["model_queries"] == 0
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_handoff_does_not_convert_unknown_error_to_recovery(monkeypatch):
    rt, a, route, state, _, _ = setup(monkeypatch)
    state.pokedex_departure_dialogue = True

    def fail(*a):
        raise ValueError("unknown error")

    monkeypatch.setattr(f, "_receive_pokedex", fail)
    with pytest.raises(ValueError, match="unknown"):
        f.parcel_story_binding(rt, a, route=route).execute()


@pytest.mark.parametrize("fault", [None, "missing_restore", "failed_heal", "unready_heal"])
def test_arrival_damage_restores_then_rebinds_the_unchanged_target(monkeypatch, fault):
    rt, a, route, _, _, calls = setup(monkeypatch)
    corridor = preparation_quote_fixture(monkeypatch, rt, route)
    raw = rt.reader.read()
    healed = [False]
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: raw.player_y != 3 or healed[0])
    monkeypatch.setattr(f, "observe_preparation_members", lambda *args: ())
    monkeypatch.setattr(f, "preparation_trainee", lambda *args: object())
    act = a.execute

    def execute(action):
        act(action)
        if action == "travel":
            raw.map_id = 41

    a.execute = execute
    plan = object()
    rebound = []

    def fresh(*args, **kwargs):
        rebound.append((kwargs["plan"], healed[0]))
        return N(
            execute=lambda: GoalExecutionReport(0, 0, {}),
            verify=lambda _: GoalVerification.succeeded(),
        )

    monkeypatch.setattr(f, "preparation_binding", fresh)
    rt.adapter = N(observe=lambda: object())
    restore_binding = N(kind=GoalKind.RESTORE_TEAM)
    monkeypatch.setattr(
        f,
        "RedCenterRestoreGoalProvider",
        lambda *args, **kwargs: N(
            offer=lambda _: N(binding=None if fault == "missing_restore" else restore_binding)
        ),
    )

    def restore(b):
        assert b is restore_binding
        a.execute("heal")
        if fault == "failed_heal":
            raise RuntimeError("healing failed")
        healed[0] = fault != "unready_heal"
        return GoalExecutionReport(1, 10, {})

    a.execute_restoration = restore
    binding = f.routed_preparation_binding(
        rt, a, home_map=41, route=route, battler=N(session=rt.emulator), plan=plan,
        corridor=corridor,
    )
    assert not calls and not rebound
    if fault:
        with pytest.raises(RuntimeError):
            binding.execute()
        assert not rebound
    else:
        result = binding.execute()
        assert rebound == [(plan, True)]
        assert calls == ["travel", "heal"]
        assert result.actions_executed == 2 and result.frames_executed == 20
        assert result.evidence["arrival_restoration"]["model_queries"] == 0
        assert binding.verify(result).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    "at_home,directive,available",
    [
        (True, f.TeamTrainingDirective.RESTORE_TEAM, True),
        (True, f.TeamTrainingDirective.TRAIN_MEMBER, True),
        (True, f.TeamTrainingDirective.STOP, False),
        (False, f.TeamTrainingDirective.RESTORE_TEAM, False),
    ],
)
def test_injured_arrival_offers_restore_then_original_target_only_at_home(
    monkeypatch, at_home, directive, available
):
    rt, a, route, _, _, calls = setup(monkeypatch)
    corridor = preparation_quote_fixture(monkeypatch, rt, route)
    rt.reader.read().map_id = 41 if at_home else 1
    monkeypatch.setattr(f, "_raw_party_fully_restored", lambda _: False)
    monkeypatch.setattr(f, "observe_preparation_members", lambda *a: ())
    monkeypatch.setattr(f, "next_preparation_decision", lambda *a: N(directive=directive))
    monkeypatch.setattr(f, "preparation_trainee", lambda *a: pytest.fail("unready excursion"))
    binding = f.routed_preparation_binding(
        rt, a, home_map=41, route=route, battler=N(session=rt.emulator), plan=object(),
        corridor=corridor,
    )
    assert (binding is not None) is available
    assert not calls
