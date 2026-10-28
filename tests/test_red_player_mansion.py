from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_mansion as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.route_plan import RoutePlanningError


def setup(monkeypatch, *, map_id=int(MapId.POKEMON_MANSION_1F), switch=False):
    raw = N(
        map_id=map_id,
        player_y=27,
        player_x=5,
        event_flags=b"events",
        bag_items=((4, 5),),
        player_money=14409,
        badge_bits=63,
        party_species_ids=(28,),
        party_levels=(47,),
        party_moves=((57, 58, 33, 39),),
        party_pp=((15, 10, 35, 30),),
        party_hp=(100,),
        battle_state=0,
    )
    state = N(
        payload=b"source",
        switch=switch,
        ready=True,
        blocked=False,
        available=True,
        pickup=None,
        bad_drop=False,
        bad_switch=False,
        bad_cash=False,
        bad_bag=False,
        story_changed=False,
        owned=frozenset(),
        pc=(),
        boxes=(),
    )
    calls = []

    @dataclass
    class World:
        def with_current_observation(self, reader):
            return self

        def plan_feasible_to_map(self, start, target, *, goal_at=(20, 19)):
            if state.blocked:
                raise RoutePlanningError("door closed")
            return N(cost=48, terminal_at=goal_at)

    @dataclass
    class Route:
        route_world: World
        rom: bytes = b"rom"
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        def __call__(self, actions, reader, emulator):
            calls.append((self.destination_map, self.destination_at))
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            actions.actions_executed += 1
            emulator.frame_count += 10
            state.payload = b"routed"

    rt = N(
        reader=N(
            read=lambda: N(**vars(raw)),
            read_all_box_states=lambda: state.boxes,
            read_pc_items=lambda: state.pc,
            read_pokedex_state=lambda: N(owned_species=state.owned),
        ),
        emulator=N(frame_count=0, save_state_bytes=lambda: state.payload),
        adapter=N(
            graph=N(available_objectives=lambda _: (N(id=s.OBJECTIVE),) if state.available else ())
        ),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "field_item_story_option", lambda *a, **k: state.pickup)
    monkeypatch.setattr(s, "settle_story_interaction", lambda *a: None)
    monkeypatch.setattr(s, "story_travel_binding", lambda *a, **k: None)
    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (
            N(raw=rt.reader.read(), game_state=object()),
            {
                "completed_objectives": ["reach_cinnabar"]
                + ([s.OBJECTIVE] if state.story_changed else [])
            },
        ),
    )
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "event_flag_is_set", lambda *a: state.switch)
    monkeypatch.setattr(
        s,
        "Gen1TraversalObserver",
        lambda *a, **k: N(observe=lambda: N(map_id=raw.map_id, at=(raw.player_y, raw.player_x))),
    )
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: None)

    def effect():
        if state.bad_cash:
            raw.player_money += 1
        if state.bad_bag:
            raw.bag_items += ((1, 1),)

    def toggle(actions, reader, emulator, *, expected):
        assert state.switch is not expected
        if not state.bad_switch:
            state.switch = expected
        effect()
        state.payload = b"toggled"
        actions.actions_executed += 1
        emulator.frame_count += 10

    monkeypatch.setattr(s, "_toggle_statue", toggle)

    def pulse(actions, kind, value=None, *, frames):
        assert kind is s.MacroActionKind.MOVE and value == "down"
        raw.map_id = int(MapId.POKEMON_MANSION_1F)
        raw.player_y, raw.player_x = s.DROP_TERMINAL if not state.bad_drop else (0, 0)
        effect()
        state.payload = b"dropped"
        actions.actions_executed += 1
        rt.emulator.frame_count += 10

    monkeypatch.setattr(s, "_pulse", pulse)
    return rt, actions, Route(World()), raw, state, calls


@pytest.mark.parametrize(
    "map_id,switch,expected",
    [
        (int(MapId.POKEMON_MANSION_1F), False, s.UPPER_STATUE),
        (int(MapId.POKEMON_MANSION_2F), False, s.UPPER_STATUE),
        (int(MapId.POKEMON_MANSION_3F), False, s.UPPER_STATUE),
        (int(MapId.POKEMON_MANSION_B1F), True, s.SOUTH_STATUE),
        (int(MapId.POKEMON_MANSION_B1F), False, s.NORTH_STATUE),
    ],
)
def test_observed_switch_controls_only_mechanics_not_story_completion(
    monkeypatch, map_id, switch, expected
):
    rt, actions, route, raw, state, calls = setup(monkeypatch, map_id=map_id, switch=switch)
    binding, challenge = s.mansion_secret_key_option(rt, actions, None, route=route)
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0
    assert not challenge.opposition_known and binding.story_objective_ref == s.OBJECTIVE
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert calls == [expected] and state.switch is not switch
    assert not report.evidence["objective_completed"] and not report.evidence["learned_puzzle"]
    assert report.evidence["sales"] == report.evidence["purchases"] == 0
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_native_floor_drop_must_match_exact_terminal_without_toggling(monkeypatch):
    rt, actions, route, raw, state, calls = setup(
        monkeypatch, map_id=int(MapId.POKEMON_MANSION_3F), switch=True
    )
    binding, _ = s.mansion_secret_key_option(rt, actions, None, route=route)
    report = binding.execute()
    assert calls == [(int(MapId.POKEMON_MANSION_3F), s.DROP_APPROACH)]
    assert raw.map_id == int(MapId.POKEMON_MANSION_1F)
    assert (raw.player_y, raw.player_x) == s.DROP_TERMINAL and state.switch
    assert report.evidence["support"] == "observed_mansion_floor_drop"
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    "fault",
    [
        "unready",
        "off_map",
        "unavailable",
        "unknown_bag",
        "full_bag",
        "already_owned",
        "unknown_cash",
        "fainted",
        "closed_route",
    ],
)
def test_unavailable_mansion_interaction_sends_no_inputs(monkeypatch, fault):
    rt, actions, route, raw, state, calls = setup(monkeypatch)
    if fault == "unready":
        state.ready = False
    if fault == "off_map":
        raw.map_id = int(MapId.CINNABAR_POKECENTER)
    if fault == "unavailable":
        state.available = False
    if fault == "unknown_bag":
        raw.bag_items = None
    if fault == "full_bag":
        raw.bag_items = tuple((i, 1) for i in range(1, 21))
    if fault == "already_owned":
        raw.bag_items += ((int(ItemId.SECRET_KEY), 1),)
    if fault == "unknown_cash":
        raw.player_money = None
    if fault == "fainted":
        raw.party_hp = (0,)
    if fault == "closed_route":
        state.blocked = True
    assert s.mansion_secret_key_option(rt, actions, None, route=route) is None
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("fault", ["stale", "bad_switch", "bad_cash", "bad_bag", "bad_drop"])
def test_resource_and_native_effect_faults_are_not_success(monkeypatch, fault):
    rt, actions, route, raw, state, calls = setup(
        monkeypatch,
        map_id=int(MapId.POKEMON_MANSION_3F)
        if fault == "bad_drop"
        else int(MapId.POKEMON_MANSION_1F),
        switch=fault == "bad_drop",
    )
    binding, _ = s.mansion_secret_key_option(rt, actions, None, route=route)
    if fault == "stale":
        state.payload = b"different"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert not calls
    else:
        setattr(state, fault, True)
        with pytest.raises(RuntimeError):
            binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED


def test_existing_reachable_item_or_travel_has_priority_over_puzzle_support(monkeypatch):
    rt, actions, route, _, state, calls = setup(monkeypatch)
    state.pickup = (object(), object())
    assert s.mansion_secret_key_option(rt, actions, None, route=route) is state.pickup
    assert not calls and actions.actions_executed == 0


@pytest.mark.parametrize("switch", [False, True])
def test_observed_third_floor_phase_precedes_unobserved_staircase_quote(monkeypatch, switch):
    rt, actions, route, _, state, calls = setup(
        monkeypatch, map_id=int(MapId.POKEMON_MANSION_3F), switch=switch
    )
    state.pickup = (object(), object())
    binding, _ = s.mansion_secret_key_option(rt, actions, None, route=route)
    assert binding.binding_ref.startswith("pokemon.red:mansion-interaction:")
    report = binding.execute()
    assert calls == [(int(MapId.POKEMON_MANSION_3F), s.DROP_APPROACH) if switch else s.UPPER_STATUE]
    assert report.evidence["support"] == (
        "observed_mansion_floor_drop" if switch else "observed_mansion_statue"
    )
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing_key",
        "switch_off",
        "off_map",
        "unavailable",
        "unready",
        "unknown_cash",
        "fainted",
        "closed_route",
    ],
)
def test_key_owned_exit_reuses_statue_without_completing_blaine(monkeypatch, fault):
    rt, actions, route, raw, state, calls = setup(
        monkeypatch, map_id=int(MapId.POKEMON_MANSION_B1F), switch=True
    )
    raw.bag_items += ((int(ItemId.SECRET_KEY), 1),)
    rt.adapter.graph.available_objectives = lambda _: (N(id=s.EXIT_OBJECTIVE),)
    if fault == "missing_key":
        raw.bag_items = ((4, 5),)
    if fault == "switch_off":
        state.switch = False
    if fault == "off_map":
        raw.map_id = int(MapId.CINNABAR_POKECENTER)
    if fault == "unavailable":
        rt.adapter.graph.available_objectives = lambda _: ()
    if fault == "unready":
        state.ready = False
    if fault == "unknown_cash":
        raw.player_money = None
    if fault == "fainted":
        raw.party_hp = (0,)
    if fault == "closed_route":
        state.blocked = True
    row = s.mansion_exit_option(rt, actions, None, route=route)
    if fault and fault != "switch_off":
        assert row is None and not calls and actions.actions_executed == 0
        return
    binding, challenge = row
    assert binding.story_objective_ref == s.EXIT_OBJECTIVE and not challenge.opposition_known
    report = binding.execute()
    assert calls == [s.SOUTH_STATUE if fault == "switch_off" else s.NORTH_STATUE]
    assert state.switch is (fault == "switch_off")
    assert report.evidence["objective"] == s.EXIT_OBJECTIVE
    assert not report.evidence["objective_completed"] and not report.evidence["learned_puzzle"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_closed_first_floor_return_uses_reachable_south_statue(monkeypatch):
    rt, actions, route, raw, state, calls = setup(monkeypatch, switch=False)
    raw.bag_items += ((int(ItemId.SECRET_KEY), 1),)
    rt.adapter.graph.available_objectives = lambda _: (N(id=s.EXIT_OBJECTIVE),)
    binding, _ = s.mansion_exit_option(rt, actions, None, route=route)
    report = binding.execute()
    assert calls == [s.SOUTH_STATUE] and state.switch
    assert not report.evidence["objective_completed"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_open_first_floor_return_does_not_toggle_again(monkeypatch):
    rt, actions, route, raw, state, calls = setup(monkeypatch, switch=True)
    raw.bag_items += ((int(ItemId.SECRET_KEY), 1),)
    rt.adapter.graph.available_objectives = lambda _: (N(id=s.EXIT_OBJECTIVE),)
    assert s.mansion_exit_option(rt, actions, None, route=route) is None
    assert not calls and actions.actions_executed == 0


def test_reachable_basement_boundary_takes_priority_over_another_toggle(monkeypatch):
    rt, actions, route, raw, state, calls = setup(
        monkeypatch, map_id=int(MapId.POKEMON_MANSION_B1F), switch=True
    )
    raw.bag_items += ((int(ItemId.SECRET_KEY), 1),)
    rt.adapter.graph.available_objectives = lambda _: (N(id=s.EXIT_OBJECTIVE),)
    travel = object()

    def quote(*args, **kwargs):
        assert kwargs["intermediate_map"] == int(MapId.POKEMON_MANSION_1F)
        assert kwargs["objective_id"] == s.EXIT_OBJECTIVE
        return travel

    monkeypatch.setattr(s, "story_travel_binding", quote)
    binding, _ = s.mansion_exit_option(rt, actions, None, route=route)
    assert binding is travel and not calls and actions.actions_executed == 0


@pytest.mark.parametrize("fault", ["terminal_changed", "story_changed"])
def test_verify_rejects_changed_terminal_or_fabricated_quest(monkeypatch, fault):
    rt, actions, route, raw, state, calls = setup(monkeypatch)
    binding, _ = s.mansion_secret_key_option(rt, actions, None, route=route)
    report = binding.execute()
    if fault == "terminal_changed":
        state.payload = b"different"
    if fault == "story_changed":
        state.story_changed = True
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("map_id", [s.SOUTH_STATUE[0], int(MapId.POKEMON_MANSION_1F)])
@pytest.mark.parametrize("key_owned", [False, True])
def test_selected_restoration_opens_exit_without_key_or_story_selection(
    monkeypatch, map_id, key_owned
):
    from pokemon_red_completion import red_goal_skills as skills
    from pokemon_red_completion import red_player_field_goals as goals
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification

    rt, actions, route, raw, state, calls = setup(monkeypatch, map_id=map_id, switch=False)
    raw.bag_items += ((int(ItemId.MASTER_BALL), 1),)
    if key_owned:
        raw.bag_items += ((int(ItemId.SECRET_KEY), 1),)
    state.available = False
    monkeypatch.setattr(skills, "_raw_party_fully_restored", lambda _: False)
    quoted = []

    def nurse(runtime, executor, *, home_map, route, **kwargs):
        assert state.switch and home_map == int(MapId.CINNABAR_POKECENTER)
        assert kwargs["observe_trainer_hazards"] and kwargs["allow_blackout_return"]
        quoted.append(home_map)
        return N(execute=lambda: GoalExecutionReport(0, 0, {"native_nurse": True}),
                 verify=lambda _: GoalVerification.succeeded())

    monkeypatch.setattr(goals, "routed_restoration_binding", nurse)
    bag = raw.bag_items
    binding = s.mansion_restoration_binding(rt, actions, route=route)
    assert binding.kind is s.GoalKind.RESTORE_TEAM and binding.story_objective_ref is None
    assert binding.maximum_cash_debit == 0
    assert not calls and not quoted and actions.actions_executed == rt.emulator.frame_count == 0
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert calls == [s.SOUTH_STATUE, (int(MapId.POKEMON_MANSION_1F), (20, 19))]
    assert quoted == [int(MapId.CINNABAR_POKECENTER)]
    assert raw.bag_items == bag and not state.story_changed
    assert report.evidence["departure"]["objective"] is None
    assert report.evidence["departure"]["objective_completed"] is False
    assert report.evidence["support"] == "observed_mansion_departure_then_center"
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize(
    "fault",
    ["healthy", "open", "off_map", "unready", "cash", "bag", "events", "fainted", "blocked"],
)
def test_mansion_restoration_ineligible_or_blocked_sends_no_inputs(monkeypatch, fault):
    from pokemon_red_completion import red_goal_skills as skills
    rt, actions, route, raw, state, calls = setup(monkeypatch)
    monkeypatch.setattr(skills, "_raw_party_fully_restored", lambda _: fault == "healthy")
    if fault == "open":
        state.switch = True
    if fault == "off_map":
        raw.map_id = int(MapId.POKEMON_MANSION_3F)
    if fault == "unready":
        state.ready = False
    if fault == "cash":
        raw.player_money = None
    if fault == "bag":
        raw.bag_items = None
    if fault == "events":
        raw.event_flags = None
    if fault == "fainted":
        raw.party_hp = (0,)
    if fault == "blocked":
        state.blocked = True
    assert s.mansion_restoration_binding(rt, actions, route=route) is None
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize(
    "fault", ["stale", "bad_switch", "bad_cash", "bad_bag", "no_nurse", "nurse_failure"]
)
def test_mansion_restoration_retains_departure_or_nurse_failures(monkeypatch, fault):
    from pokemon_red_completion import red_goal_skills as skills
    from pokemon_red_completion import red_player_field_goals as goals
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
    rt, actions, route, raw, state, calls = setup(monkeypatch)
    monkeypatch.setattr(skills, "_raw_party_fully_restored", lambda _: False)
    failed = GoalVerification.failed(s.GoalFailureReason.OUTCOME_NOT_VERIFIED)
    nurse = N(execute=lambda: GoalExecutionReport(0, 0, {}), verify=lambda _: failed)
    monkeypatch.setattr(
        goals, "routed_restoration_binding", lambda *a, **k: None if fault == "no_nurse" else nurse
    )
    binding = s.mansion_restoration_binding(rt, actions, route=route)
    if fault == "stale":
        state.payload = b"changed"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert not calls
    elif fault.startswith("bad_"):
        setattr(state, fault, True)
        with pytest.raises(RuntimeError, match="Mansion"):
            binding.execute()
    elif fault == "no_nurse":
        with pytest.raises(RuntimeError, match="nurse route"):
            binding.execute()
    else:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault", [None, "inside", "switch_on", "unknown_events"])
def test_departure_discards_only_reset_mansion_projections(monkeypatch, fault):
    @dataclass
    class CachedWorld:
        terrain: dict
        local_graphs: dict
        object_blockers: dict
        macro_graph: object
        requirements: object

    base = CachedWorld(
        {m: ("cartridge", m) for m in s.MANSION_MAPS | {8}},
        {m: ("graph", m) for m in s.MANSION_MAPS | {8}},
        {m: frozenset({(1, 2)}) for m in s.MANSION_MAPS | {8}},
        object(), object(),
    )
    world = CachedWorld(
        {m: ("live", m) for m in s.MANSION_MAPS | {8}},
        {m: ("closed", m) for m in s.MANSION_MAPS | {8}},
        {m: frozenset({(3, 4)}) for m in s.MANSION_MAPS | {8}},
        base.macro_graph, base.requirements,
    )
    raw = N(map_id=int(MapId.CINNABAR_POKECENTER), event_flags=b"known")
    if fault == "inside":
        raw.map_id = int(MapId.POKEMON_MANSION_1F)
    if fault == "unknown_events":
        raw.event_flags = None
    monkeypatch.setattr(s, "event_flag_is_set", lambda *a: fault == "switch_on")
    refreshed = s.mansion_departure_world(world, base, raw)
    if fault:
        assert refreshed is world
        return
    for name in ("terrain", "local_graphs", "object_blockers"):
        assert getattr(refreshed, name)[8] == getattr(world, name)[8]
        assert all(getattr(refreshed, name)[m] == getattr(base, name)[m]
                   for m in s.MANSION_MAPS)
        assert all(getattr(world, name)[m] != getattr(base, name)[m]
                   for m in s.MANSION_MAPS)
    assert refreshed.macro_graph is world.macro_graph
    assert refreshed.requirements is world.requirements


@pytest.mark.parametrize("interruption", ["none", "wild", "trainer", "unsettled"])
def test_statue_settles_encounter_before_confirmation(monkeypatch, interruption):
    state = N(switch=False, battle=0, dialogue=False, ready=True, confirms=0, escapes=0)
    reader = N(read=lambda: N(event_flags=b"known", battle_state=state.battle),
               read_bottom_dialogue_box_visible=lambda: state.dialogue)
    monkeypatch.setattr(s, "event_flag_is_set", lambda *a: state.switch)
    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready and not state.battle)

    def pulse(actions, kind, value=None, *, frames):
        if kind is s.MacroActionKind.MOVE:
            assert value == "up" and frames == 120
            state.battle = {"wild": 1, "trainer": 2}.get(interruption, 0)
        if kind is s.MacroActionKind.CONFIRM:
            assert state.battle == 0, "no dialogue Confirm in a battle"
            assert frames == 30
            state.confirms += 1
            state.switch = True

    def settle(runtime, actions):
        if state.battle == 2 or interruption == "unsettled":
            raise RuntimeError("unsupported battle or boundary")
        if state.battle == 1:
            state.battle = 0
            state.escapes += 1
            return {"ordinary_wild_escape": True}
        return None

    monkeypatch.setattr(s, "_pulse", pulse)
    monkeypatch.setattr(s, "settle_story_interaction", settle)
    if interruption in {"trainer", "unsettled"}:
        with pytest.raises(RuntimeError, match="unsupported"):
            s._toggle_statue(N(), reader, N(), expected=True)
        assert state.confirms == 0
    else:
        evidence = s._toggle_statue(N(), reader, N(), expected=True)
        assert state.switch and state.confirms == 1
        assert state.escapes == (interruption == "wild")
        assert evidence == ([{"ordinary_wild_escape": True}] if interruption == "wild" else [])


def test_statue_already_target_or_missing_effect_is_not_success(monkeypatch):
    reader = N(read=lambda: N(event_flags=b"known", battle_state=0),
               read_bottom_dialogue_box_visible=lambda: False)
    pulses = []
    monkeypatch.setattr(s, "event_flag_is_set", lambda *a: True)
    monkeypatch.setattr(s, "_pulse", lambda *a, **k: pulses.append(a[1]))
    with pytest.raises(s.BlaineChapterError, match="began in"):
        s._toggle_statue(N(), reader, N(), expected=True)
    assert not pulses
    monkeypatch.setattr(s, "event_flag_is_set", lambda *a: False)
    monkeypatch.setattr(s, "settle_story_interaction", lambda *a: None)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    with pytest.raises(s.BlaineChapterError, match="did not toggle"):
        s._toggle_statue(N(), reader, N(), expected=True)
    assert pulses.count(s.MacroActionKind.CONFIRM) == 16
