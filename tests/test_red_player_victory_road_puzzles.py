"""ROM-free verification of composition, not a second Strength solver."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_gen1_strength import raw as strength_raw
from test_red_player_victory_road import fixture

from pokemon_red_completion import red_player_victory_road as s
from pokemon_red_completion.gen1_strength import StrengthPlanningError
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import MapId


def contracts(monkeypatch):
    rows = [N(event=i, map_id=m) for i, m in enumerate((108, 194, 198, 198, 194))]
    monkeypatch.setattr(s, "victory_road_first_switch", lambda _: rows[0])
    monkeypatch.setattr(s, "victory_road_second_switches", lambda _: (rows[1], rows[4]))
    monkeypatch.setattr(s, "victory_road_third_floor", lambda _: (rows[2], None))
    monkeypatch.setattr(s, "victory_road_boulder_drop", lambda _: rows[3])
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: event in flags)
    return rows


@pytest.mark.parametrize("completed", range(6))
def test_puzzle_uses_live_events_not_a_cached_success(monkeypatch, completed):
    rows = contracts(monkeypatch)
    result = s.next_puzzle(
        b"rom",
        N(event_flags=set(range(completed)), map_id=(108, 194, 198, 198, 194, 194)[completed]),
    )
    assert result is None if completed == 5 else result[1] is rows[completed]


def test_first_switch_reset_on_second_floor_is_not_a_replay_request(monkeypatch):
    rows = contracts(monkeypatch)
    assert s.next_puzzle(b"rom", N(event_flags=set(), map_id=194)) == ("second-switch", rows[1])
    assert s.next_puzzle(b"rom", N(event_flags=set(range(1, 5)), map_id=194)) is None


@pytest.mark.parametrize("map_id", (9, 174))
def test_indigo_never_decodes_or_replays_transient_cave_flags(monkeypatch, map_id):
    monkeypatch.setattr(s, "victory_road_first_switch", lambda _: pytest.fail("already crossed"))
    assert s.next_puzzle(b"not-a-rom", N(map_id=map_id, event_flags=set())) is None


def test_directional_warp_stance_is_legal_but_outward_input_is_not():
    rows = (
        N(at=(17, 8), kind="return", exit_action="down"),
        N(at=(17, 9), kind="return", exit_action="down"),
        N(at=(1, 1), kind="warp", exit_action=None),
    )
    graph = N(warp_locations={108: ((17, 8), (17, 9), (1, 1), (2, 2))}, neighbors=lambda _: rows)
    assert s.strength_warp_guards(graph, 108) == (
        frozenset({(1, 1), (2, 2)}),
        frozenset({((17, 8), "down"), ((17, 9), "down")}),
    )


def test_mixed_warp_remains_a_forbidden_coordinate():
    graph = N(
        warp_locations={108: ((1, 1),)},
        neighbors=lambda _: (
            N(at=(1, 1), kind="warp", exit_action=None),
            N(at=(1, 1), kind="return", exit_action="down"),
        ),
    )
    assert s.strength_warp_guards(graph, 108) == (frozenset({(1, 1)}), frozenset())


@pytest.mark.parametrize(
    "at,event,available",
    [
        ((15, 21), True, True),
        ((15, 22), True, True),
        ((15, 21), False, False),
        ((15, 25), True, False),
        ((14, 21), True, False),
    ],
)
def test_hole_only_admits_existing_qualified_sources(monkeypatch, at, event, available):
    monkeypatch.setattr(
        s, "victory_road_boulder_drop", lambda _: N(map_id=198, at=(15, 23), event=1638)
    )
    monkeypatch.setattr(s, "event_flag_is_set", lambda *_: event)
    assert (
        s.dropped_boulder_follow_available(
            b"rom", N(map_id=198, player_y=at[0], player_x=at[1], event_flags=())
        )
        is available
    )


@pytest.mark.parametrize("fault", [None, "arrival", "boulder", "money", "source", "battle"])
def test_hole_transition_checks_arrival_boulder_and_resources(monkeypatch, fault):
    before = replace(
        strength_raw((15, 21)),
        map_id=198,
        player_money=4226,
        battle_state=1 if fault == "battle" else 0,
    )
    after = replace(
        before,
        map_id=194,
        player_y=16,
        player_x=21 if fault == "arrival" else 22,
        player_money=before.player_money + (fault == "money"),
    )
    current, steps = [before], []
    monkeypatch.setattr(s, "dropped_boulder_follow_available", lambda *_: fault != "source")
    monkeypatch.setattr(s, "victory_road_boulder_drop", lambda _: N(destination_map=194))

    def step(*args):
        steps.append(args[2])
        current[0] = after

    monkeypatch.setattr(s, "verified_victory_step", step)
    rt = N(
        reader=N(
            read=lambda: current[0],
            read_current_strength_boulders=lambda: (
                N(sprite_index=13, at=(16, 22) if fault == "boulder" else (16, 23)),
            ),
        )
    )
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            s.follow_dropped_boulder(rt, object(), b"rom")
        assert len(steps) == (0 if fault in {"source", "battle"} else 1)
    else:
        assert s.follow_dropped_boulder(rt, object(), b"rom")["dropped_boulder_verified"] is True
        assert steps == ["right"]


@pytest.mark.parametrize("fault", [None, "trainer", "unknown", "wrong_tile", "no_binding",
                                   "unverified", "drift", "hp"])
def test_hole_follow_settles_only_an_acknowledged_ordinary_wild_step(monkeypatch, fault):
    before = replace(strength_raw((15, 21)), map_id=198, player_money=4226, battle_state=0)
    current, steps, escapes = [before], [], []
    monkeypatch.setattr(s, "dropped_boulder_follow_available", lambda *_: True)
    monkeypatch.setattr(s, "victory_road_boulder_drop", lambda _: N(destination_map=194))
    monkeypatch.setattr(s, "_field_ready", lambda _: current[0].battle_state == 0)

    def step(*args):
        steps.append(args[2])
        if len(steps) == 1:
            current[0] = replace(before, player_x=21 if fault == "wrong_tile" else 22,
                                 battle_state=2 if fault == "trainer" else 1)
            message = ("another execution failure" if fault == "unknown" else
                       "verified dropped-boulder follow entered an unexpected battle.")
            raise s.VictoryRoadChapterError(message)
        current[0] = replace(current[0], map_id=194, player_y=16, player_x=22)

    def bind(runtime, actions, *, rom):
        assert rom == b"rom"
        if fault == "no_binding":
            return None

        def execute():
            escapes.append(True)
            current[0] = replace(current[0], battle_state=0,
                player_x=23 if fault == "drift" else 22,
                party_hp=(current[0].party_hp[0] - 1,) if fault == "hp" else current[0].party_hp)
            return N(evidence={"escape": {"verified": True}})

        return N(execute=execute, verify=lambda _: (
            s.GoalVerification.failed(s.GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if fault == "unverified" else s.GoalVerification.succeeded()))

    from pokemon_red_completion import red_player_wild_recovery

    monkeypatch.setattr(s, "verified_victory_step", step)
    monkeypatch.setattr(red_player_wild_recovery, "interrupted_wild_binding", bind)
    rt = N(reader=N(read=lambda: current[0], read_current_strength_boulders=lambda: (
        N(sprite_index=13, at=(16, 23)),)))
    if fault:
        with pytest.raises((s.VictoryRoadChapterError, RuntimeError)):
            s.follow_dropped_boulder(rt, object(), b"rom")
        if fault in {"trainer", "unknown", "wrong_tile"}:
            assert not escapes
    else:
        result = s.follow_dropped_boulder(rt, object(), b"rom")
        assert result["dropped_boulder_verified"] and steps == ["right", "right"]
        assert len(result["ordinary_wild_escapes"]) == len(escapes) == 1


@pytest.mark.parametrize("fault", [None, "event", "block", "map", "cash", "unpassed"])
def test_selected_puzzle_verifies_native_event_and_block_not_just_plan(monkeypatch, fault):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    raw.map_id, raw.event_flags = 108, set()
    contract = N(map_id=108, event=20, changed_block_at=(1, 1), changed_block=23, at=(1, 2))
    # The selected plan is fixed before any native input. Execution and live
    # cartridge effects remain independently verified by this adapter.
    plan = N(steps=(object(),), cost=2, explored_states=3)
    monkeypatch.setattr(s, "_puzzle_plan", lambda *_: (plan, object()))
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: event in flags)
    rt.reader.read_current_map_blocks = lambda: N(
        rows=((0, 0), (0, 22 if fault == "block" else 23))
    )

    def activate(_):
        actions.actions_executed += 1
        rt.emulator.frame_count += 12
        calls.append("activate")

    monkeypatch.setattr(s, "Gen1FieldMovePort", lambda *_: N(execute=activate))
    monkeypatch.setattr(s, "Gen1WildFleeHandler", lambda *_, **kw: object())

    def execute(quoted):
        assert quoted is plan
        calls.append("execute")
        if fault != "event":
            raw.event_flags.add(20)
        if fault == "map":
            raw.map_id = 194
        if fault == "cash":
            raw.player_money -= 1
        state.payload = b"pushed"
        return N(
            passed=fault != "unpassed",
            pushes=(),
        )

    monkeypatch.setattr(
        s, "Gen1StrengthExecutor", lambda *_, **kw: N(execute=execute, interruption_receipts=())
    )
    monkeypatch.setattr(s, "asdict", lambda value: vars(value))
    binding, _ = s._puzzle_option(rt, actions, route, "first-switch", contract, None)
    assert calls == [] and actions.actions_executed == 0
    if fault:
        with pytest.raises(RuntimeError):
            binding.execute()
    else:
        report = binding.execute()
        assert calls == ["activate", "execute"]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert report.evidence["objective_completed"] is False


def test_unsolved_quote_returns_no_binding_and_no_input(monkeypatch):
    rt, a, route, _, _, calls = fixture(monkeypatch)

    def blocked(*_):
        raise StrengthPlanningError("no legal Strength plan")

    monkeypatch.setattr(s, "_puzzle_plan", blocked)
    assert s._puzzle_option(rt, a, route, "first-switch", object(), None) is None
    assert not calls and a.actions_executed == 0


@pytest.mark.parametrize("fault", [None, "event", "boulder", "map"])
def test_drop_requires_event_and_actual_sprite_removal(monkeypatch, fault):
    monkeypatch.setattr(s, "event_flag_is_set", lambda *_: fault != "event")
    rt = N(
        reader=N(
            read_current_strength_boulders=lambda: (
                N(sprite_index=10 if fault == "boulder" else 2),
            )
        )
    )
    raw = N(map_id=194 if fault == "map" else 198, event_flags=())
    assert s._puzzle_verified(rt, "boulder-drop", N(map_id=198, event=1), raw) is (fault is None)


@pytest.mark.parametrize("intermediate", [True, False])
def test_indigo_route_stops_at_next_map_and_only_arrival_can_complete(monkeypatch, intermediate):
    rt, a, route, raw, state, calls = fixture(monkeypatch)
    raw.map_id = 194
    target = int(MapId.ROUTE_23) if intermediate else int(MapId.INDIGO_PLATEAU)
    at = (1, 2)
    route.route_world.plan_feasible_to_map = lambda *_, **kw: N(
        steps=(N(expected_map=194, expected_at=(1, 1)), N(expected_map=target, expected_at=at)),
        terminal_at=(4, 5),
        cost=8,
    )
    fact = frozenset({"story:victory_road_cleared"})
    rt.adapter.graph.objective = lambda _: N(completion_facts=fact)
    rt.observer = N(latch_verified_facts=lambda facts: calls.append(("latch", facts)))
    monkeypatch.setattr(s, "semantic_facts", lambda r: fact if r.map_id == 9 else frozenset())
    binding, _ = s._route_option(
        rt,
        a,
        route,
        world=route.route_world,
        phase="reach-indigo",
        destination_map=9,
        finishes=True,
    )
    assert not calls and a.actions_executed == 0
    report = binding.execute()
    assert calls[0] == (target, at)
    assert report.evidence["objective_completed"] is (not intermediate)
    assert (("latch", fact) in calls) is (not intermediate)
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_completion_never_latches_on_just_the_supplied_predicate(monkeypatch):
    rt, a, _, _, _, calls = fixture(monkeypatch)
    rt.adapter.graph.objective = lambda _: N(
        completion_facts=frozenset({"story:victory_road_cleared"})
    )
    rt.observer = N(latch_verified_facts=lambda *_: pytest.fail("not actually Indigo"))
    monkeypatch.setattr(s, "semantic_facts", lambda _: frozenset())
    binding, _ = s._mechanics_option(
        rt,
        a,
        phase="wrong-arrival",
        operation=lambda: {},
        valid=lambda _: True,
        completes_objective=True,
    )
    with pytest.raises(RuntimeError, match="terminal"):
        binding.execute()
    assert not calls


@pytest.mark.parametrize("map_id", sorted(s.CAVE_MAPS))
@pytest.mark.parametrize("objective_ref", [s.OBJECTIVE, "defeat_lance"])
def test_feasible_cave_exit_precedes_reset_puzzles(monkeypatch, map_id, objective_ref):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    raw.map_id = map_id
    events = bytearray(raw.event_flags)
    events[1318 // 8] |= 1 << (1318 % 8)
    raw.event_flags = bytes(events)
    rt.adapter.graph.available_objectives = lambda _: (N(id=objective_ref),)
    rt.adapter.graph.completed_ids = lambda _: (s.OBJECTIVE,)
    monkeypatch.setattr(s, "strength_capabilities", lambda _: True)
    observed_world = object()
    monkeypatch.setattr(s, "observed_puzzle_world", lambda *_: observed_world)
    monkeypatch.setattr(s, "next_puzzle", lambda *_: pytest.fail("feasible exit comes first"))
    result = (object(), object())
    quotes = []

    def quote(*args, **kwargs):
        quotes.append(kwargs)
        return result

    monkeypatch.setattr(s, "_route_option", quote)
    assert s.victory_road_story_option(
        rt, actions, None, route=route, battler=object(), preparation_plan=object(),
        access_objective_ref=None if objective_ref == s.OBJECTIVE else objective_ref,
    ) is result
    assert quotes == [dict(
        world=observed_world, phase="reach-indigo", destination_map=9,
        record=None, finishes=True, objective_ref=objective_ref,
    )]
    assert not calls and actions.actions_executed == 0 and state.payload == b"source"


@pytest.mark.parametrize("puzzle_available", [True, False])
def test_blocked_cave_exit_keeps_original_puzzle_fallback(monkeypatch, puzzle_available):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    raw.map_id = int(MapId.VICTORY_ROAD_3F)
    events = bytearray(raw.event_flags)
    events[1318 // 8] |= 1 << (1318 % 8)
    raw.event_flags = bytes(events)
    monkeypatch.setattr(s, "strength_capabilities", lambda _: True)
    monkeypatch.setattr(s, "observed_puzzle_world", lambda *_: route.route_world)
    monkeypatch.setattr(s, "_route_option", lambda *a, **k: None)
    contract = N(map_id=raw.map_id)
    monkeypatch.setattr(s, "next_puzzle", lambda *_: ("third-switch", contract))
    result = (object(), object()) if puzzle_available else None
    puzzles = []

    def puzzle(*args, **kwargs):
        puzzles.append((args[3], args[4], kwargs["objective_ref"]))
        return result

    monkeypatch.setattr(s, "_puzzle_option", puzzle)
    assert s.victory_road_story_option(
        rt, actions, None, route=route, battler=object(), preparation_plan=object(),
    ) is result
    assert puzzles == [("third-switch", contract, s.OBJECTIVE)]
    assert not calls and actions.actions_executed == 0 and state.payload == b"source"
