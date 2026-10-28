from copy import deepcopy
import json
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_safari_rewards as s
from pokemon_red_completion.actions import MacroActionKind


@pytest.mark.parametrize("fault", [None, "not_ready", "no_hm", "known", "stale", "unsettled"])
def test_strength_lesson_is_explicit_native_and_one_shot(monkeypatch, fault):
    raw = N(bag_items=((199, 1),), party_moves=((33, 39, 57, 58),))
    if fault == "no_hm":
        raw.bag_items = ()
    if fault == "known":
        raw.party_moves = ((70, 39, 57, 58),)
    ready = [fault != "not_ready"]
    state = [b"opening"]
    inputs = []
    rt = N(reader=N(read=lambda: raw), emulator=N(save_state_bytes=lambda: state[0], frame_count=0))
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: ready[0])

    def plan(rom, reader, **kwargs):
        assert kwargs == dict(item_id=199, party_slot=1, replace_slot=1)
        return "legal_strength_lesson"

    def execute(emulator, executor, reader, lesson, *, rom):
        assert lesson == "legal_strength_lesson" and rom == b"rom"
        inputs.append(lesson)
        raw.party_moves = ((70, 39, 57, 58),)
        executor.actions_executed += 1
        emulator.frame_count += 10
        state[0] = b"taught"
        if fault == "unsettled":
            ready[0] = False

    monkeypatch.setattr(s, "plan_machine_lesson", plan)
    monkeypatch.setattr(s, "execute_machine_lesson", execute)
    binding = s.strength_lesson_binding(rt, actions, rom=b"rom", party_slot=1, replace_slot=1)
    assert not inputs
    if fault in {"not_ready", "no_hm", "known"}:
        assert binding is None
        return
    if fault == "stale":
        state[0] = b"different"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert not inputs
        return
    if fault == "unsettled":
        with pytest.raises(RuntimeError, match="field control"):
            binding.execute()
        return
    report = binding.execute()
    assert report.evidence["learned_selection"] is False
    assert binding.verify(report).status.value == "succeeded"
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state[0] = b"different"
    assert binding.verify(report).status.value == "failed"


@pytest.mark.parametrize(
    "owned,seen,expected",
    [
        ({1}, {1, 2}, True),
        ({1}, {1}, True),
        ({1, 2}, {1, 2}, False),
        (set(), {1, 2}, False),
        ({1}, set(), False),
    ],
)
def test_safari_encounters_may_add_seen_but_not_change_owned(owned, seen, expected):
    before = N(owned_species=frozenset({1}), seen_species=frozenset({1}))
    after = N(owned_species=frozenset(owned), seen_species=frozenset(seen))
    assert s.safari_registrations_preserved(before, after) is expected


@pytest.mark.parametrize("fault", [None, "cash", "full", "map", "already_exchanged", "stale"])
def test_safari_offer_is_read_only_and_guards_admission(monkeypatch, fault):
    raw = N(
        map_id=154,
        player_y=3,
        player_x=3,
        party_moves=((33, 39, 145, 55),),
        player_money=499 if fault == "cash" else 5421,
        event_flags=(),
        bag_items=((3, 10),),
    )
    if fault == "full":
        raw.bag_items = tuple((i, 1) for i in range(1, 21))
    if fault == "map":
        raw.map_id = 7
    if fault == "already_exchanged":
        raw.bag_items = ((199, 1),)
    rt = N(
        reader=N(read=lambda: deepcopy(raw)),
        emulator=N(save_state_bytes=lambda: repr(raw).encode()),
    )
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: event in flags)
    actions = N(execute=lambda _: pytest.fail("preflight sent controller input"))
    binding = s.safari_rewards_binding(
        rt,
        actions,
        route=object(),
        party_slot=1,
        replace_slot=3,
        record=lambda *a: pytest.fail("preflight recorded an executed stage"),
    )
    if fault not in {None, "stale"}:
        assert binding is None
    else:
        assert binding.maximum_cash_debit == 500
        if fault == "stale":
            raw.player_money -= 1
            with pytest.raises(ValueError, match="stale"):
                binding.execute()


@pytest.mark.parametrize("fault", [None, "default", "no_route", "stale", "unverified"])
def test_opted_in_center_approach_is_quoted_and_verified_before_paid_admission(monkeypatch, fault):
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification

    raw = N(
        map_id=154,
        player_y=7,
        player_x=3,
        party_moves=((33, 39, 145, 55),),
        party_pp=((35, 30, 30, 25),),
        player_money=700,
        event_flags=(),
        bag_items=((3, 8),),
    )
    rt = N(
        reader=N(
            read=lambda: deepcopy(raw),
            read_all_box_states=lambda: (),
            read_pokedex_state=lambda: N(owned_species=frozenset(), seen_species=frozenset()),
            read_pc_items=lambda: (),
        ),
        emulator=N(save_state_bytes=lambda: repr(raw).encode(), frame_count=0),
    )
    actions = N(actions_executed=0)
    calls, recorded = [], []
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: event in flags)

    def approach_execute():
        calls.append("approach_execute")
        raw.player_y, raw.player_x = 3, 3
        actions.actions_executed += 4
        rt.emulator.frame_count += 40
        return GoalExecutionReport(4, 40, {"native_stance": True})

    def approach_verify(report):
        calls.append("approach_verify")
        assert report.actions_executed == 4
        return (
            GoalVerification.failed(s.GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if fault == "unverified"
            else GoalVerification.succeeded()
        )

    approach = N(estimated_effort=0.01, execute=approach_execute, verify=approach_verify)

    def quote(runtime, executor, **kwargs):
        assert runtime is rt and executor is actions
        assert kwargs == dict(objective_id="obtain_surf", route="route", destination_at=(3, 3))
        calls.append("quote")
        return None if fault == "no_route" else approach

    monkeypatch.setattr(s, "story_travel_binding", quote)
    monkeypatch.setattr(
        s, "red_safari_zone_offers", lambda *args: (N(map_id=s.MapId.SAFARI_ZONE_CENTER),)
    )

    class PaidBoundaryReached(RuntimeError):
        pass

    def admit(em, executor, reader, offer):
        assert (raw.player_y, raw.player_x) == (3, 3)
        calls.append("admission")
        raise PaidBoundaryReached

    monkeypatch.setattr(s, "enter_red_safari_area", admit)
    route = N(rom=b"rom")

    # The quote uses the caller's exact route object, not a relaxed preview.
    def routed_quote(runtime, executor, **kwargs):
        assert kwargs["route"] is route
        return quote(runtime, executor, **dict(kwargs, route="route"))

    monkeypatch.setattr(s, "story_travel_binding", routed_quote)
    def serializable_record(*row):
        json.dumps(row)
        recorded.append(row)

    binding = s.safari_rewards_binding(
        rt,
        actions,
        route=route,
        party_slot=1,
        replace_slot=3,
        record=serializable_record,
        complete_center_approach=fault != "default",
    )
    assert actions.actions_executed == rt.emulator.frame_count == 0 and not recorded
    if fault in {"default", "no_route"}:
        assert binding is None
        assert calls == ([] if fault == "default" else ["quote"])
        return
    assert binding.maximum_cash_debit == 500 and binding.estimated_effort == pytest.approx(0.21)
    if fault == "stale":
        raw.player_money -= 1
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert calls == ["quote"]
    elif fault == "unverified":
        with pytest.raises(RuntimeError, match="native stance"):
            binding.execute()
        assert "admission" not in calls and not recorded
    else:
        with pytest.raises(PaidBoundaryReached):
            binding.execute()
        assert calls == ["quote", "approach_execute", "approach_verify", "admission"]
        assert recorded == [("center_stance_approach", {"native_stance": True})]


@pytest.mark.parametrize("flag", [None, 1, "True"])
def test_center_approach_opt_in_cannot_be_coerced(flag):
    with pytest.raises(TypeError, match="explicit boolean"):
        s.safari_rewards_binding(
            object(),
            object(),
            route=object(),
            party_slot=1,
            replace_slot=1,
            record=lambda *args: None,
            complete_center_approach=flag,
        )


@pytest.mark.parametrize(
    "bag,consumed,valid",
    [
        (((3, 10),), None, True),
        (((3, 10), (64, 1)), 64, True),
        (((3, 10),), 64, False),
        (((198, 1),), None, False),
        (tuple((i, 1) for i in range(1, 21)), None, False),
        (tuple((i, 1) for i in range(1, 21)), 3, True),
    ],
)
def test_reward_inventory(bag, consumed, valid):
    if not valid:
        with pytest.raises(ValueError):
            s.reward_bag(bag, item=198, consumed=consumed)
    else:
        result = s.reward_bag(bag, item=198, consumed=consumed)
        assert result[198] == 1 and (consumed is None or consumed not in result)


@pytest.mark.parametrize("fault", [None, "cash", "party", "item", "events", "battle", "map"])
def test_native_reward_requires_exact_resources_and_event(monkeypatch, fault):
    raw = N(
        map_id=222,
        battle_state=0,
        bag_items=((3, 10),),
        event_flags=(),
        player_money=5000,
        party_species_ids=(186, 179),
        party_levels=(28, 29),
        party_moves=((71, 15), (55, 145)),
        party_pp=((20, 30), (25, 30)),
        party_hp=(82, 77),
        party_status=(0, 0),
        badge_bits=15,
    )
    runtime = N(reader=N(read=lambda: deepcopy(raw)))
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: event in flags)
    inputs = []

    def execute(action):
        inputs.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        raw.event_flags = () if fault == "events" else (42,)
        raw.bag_items = ((3, 10),) if fault == "item" else ((3, 10), (198, 1))
        if fault == "cash":
            raw.player_money -= 1
        if fault == "party":
            raw.party_hp = (1, 77)
        if fault == "battle":
            raw.battle_state = 1
        if fault == "map":
            raw.map_id = 220

    actions = N(execute=execute)
    if fault:
        with pytest.raises(RuntimeError):
            s.collect_hm_reward(runtime, actions, item=198, events=(42,))
    else:
        result = s.collect_hm_reward(runtime, actions, item=198, events=(42,))
        assert result["item"] == 198 and len(inputs) == 2


@pytest.mark.parametrize("remaining", [0, 1, 3])
@pytest.mark.parametrize("fault", [None, "grass", "one_way", "cash", "never_expires"])
def test_time_up_uses_native_walking_and_preserves_resources(monkeypatch, remaining, fault):
    from pokemon_red_completion import safari

    raw = N(
        map_id=219,
        player_y=1,
        player_x=1,
        battle_state=0,
        bag_items=((198, 1),),
        player_money=4921,
        party_species_ids=(179,),
        party_levels=(29,),
        party_moves=((57, 55),),
        party_pp=((15, 25),),
        party_hp=(77,),
        party_status=(0,),
        badge_bits=15,
    )
    session = N(
        in_safari_zone=True, safari_game_over=False, safari_steps=remaining, safari_balls=30
    )
    reader = N(read=lambda: deepcopy(raw), read_safari_session_state=lambda: deepcopy(session))
    runtime = N(reader=reader, emulator=object())
    monkeypatch.setattr(s, "_field_ready", lambda _: True)

    def edge(target, action):
        return N(
            target=target,
            action=action,
            action_kind=MacroActionKind.MOVE,
            requirements=(),
            permits_mode=lambda _: True,
            next_mode=lambda _: "land",
        )

    def neighbors(at):
        if at == (1, 1):
            return (edge((1, 2), "right"),)
        return () if fault == "one_way" else (edge((1, 1), "left"),)

    grass = [[False] * 4 for _ in range(4)]
    grass[1][2] = fault == "grass"
    world = N(local_graphs={219: N(neighbors=neighbors)}, terrain={219: N(grass=grass)})
    world.with_current_observation = lambda _: world
    moves = []

    def move(actions, reader, em, directions, *args, **kwargs):
        moves.extend(directions)
        raw.player_x = 2 if directions[0] == "right" else 1
        session.safari_steps -= 1
        return 0

    def pulse(actions, kind, value=None, **kwargs):
        if kind is MacroActionKind.MOVE:
            moves.append(value)
            assert session.safari_steps == 0
            if fault != "never_expires":
                raw.map_id = int(s.MapId.SAFARI_ZONE_GATE)
                session.in_safari_zone, session.safari_balls = False, 0
                if fault == "cash":
                    raw.player_money -= 1

    monkeypatch.setattr(safari, "_move", move)
    monkeypatch.setattr(safari, "_pulse", pulse)
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            s.expire_paid_safari(runtime, object(), world)
        if fault in {"grass", "one_way"}:
            assert not moves
    else:
        result = s.expire_paid_safari(runtime, object(), world)
        assert result["additional_fee"] == 0 and result["steps"] == remaining
        assert len(moves) == remaining + 1


def test_approach_does_not_face_collected_item_on_departure(monkeypatch):
    reader = N(read_safari_session_state=lambda: object())
    runtime = N(reader=reader, emulator=object())
    world = N(plan_feasible_to_map=lambda *a, **kw: N(steps=()))
    world.with_current_observation = lambda _: world
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda _: N(observe=lambda: object()))
    monkeypatch.setattr(s, "require_objective_route", lambda *a: None)
    monkeypatch.setattr(s, "route_safari_objective", lambda *a, **kw: {"passed": True})
    faced = []
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: faced.append(a))
    assert s.safari_approach(
        runtime, object(), world, map_id=219, target_at=(7, 19), face_target=False
    )["passed"]
    assert not faced


@pytest.mark.parametrize("fault", [None, "cash", "party", "bag", "events", "stale"])
def test_strength_exchange_is_current_party_state_bound_and_verified(monkeypatch, fault):
    raw = N(
        map_id=154,
        player_y=3,
        player_x=3,
        battle_state=0,
        bag_items=((3, 10), (198, 1), (64, 1)),
        event_flags=(),
        player_money=4921,
        party_species_ids=(186, 179),
        party_levels=(28, 29),
        party_moves=((71, 15), (57, 55)),
        party_pp=((20, 30), (15, 25)),
        party_hp=(82, 77),
        party_status=(0, 0),
        badge_bits=15,
    )
    reader = N(
        read=lambda: deepcopy(raw),
        read_all_box_states=lambda: ("boxed",),
        read_pokedex_state=lambda: (1, 2),
        read_pc_items=lambda: (),
    )
    em = N(frame_count=0, save_state_bytes=lambda: repr(raw).encode())
    facts, inputs = [], []
    rt = N(
        reader=reader,
        emulator=em,
        observer=N(latch_verified_facts=facts.append),
        adapter=N(graph=N(objective=lambda _: N(completion_facts={"move:strength_available"}))),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "event_flag_is_set", lambda flags, event: event in flags)

    def approach(*args, **kwargs):
        inputs.append("approach")
        raw.map_id = 155

    def route_back(*args):
        inputs.append("return")
        raw.map_id = 154

    def execute(action):
        inputs.append(action)
        actions.actions_executed += 1
        em.frame_count += 1
        raw.bag_items = ((3, 10), (198, 1), (199, 1))
        raw.event_flags = (
            () if fault == "events" else (s.EventFlag.GAVE_GOLD_TEETH, s.EventFlag.GOT_HM04)
        )
        if fault == "cash":
            raw.player_money -= 1
        if fault == "party":
            raw.party_hp = (1, 77)
        if fault == "bag":
            raw.bag_items = (*raw.bag_items, (40, 1))

    actions.execute = execute
    monkeypatch.setattr(s, "approach_npc", approach)
    monkeypatch.setattr(s, "replace", lambda *a, **kw: route_back)
    binding = s.strength_reward_binding(rt, actions, route=N(rom=b"rom"))
    assert binding.maximum_cash_debit == 0 and not inputs
    if fault == "stale":
        raw.player_money -= 1
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            binding.execute()
        assert not facts
        if fault == "stale":
            assert not inputs
    else:
        report = binding.execute()
        assert not report.evidence["strength_taught"] and facts
        assert binding.verify(report).status.value == "succeeded"
        with pytest.raises(ValueError, match="consumed"):
            binding.execute()
