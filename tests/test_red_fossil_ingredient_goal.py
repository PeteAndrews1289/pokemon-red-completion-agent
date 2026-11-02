from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import Badge, EventFlag, RawGameState
from pokemon_red_completion.red_fossil_ingredient_goal import RedFossilIngredientGoalProvider
from pokemon_red_completion.red_npc_item_gift import RedNPCItemGift
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(monkeypatch, *, party_size=6):
    import pokemon_red_completion.red_fossil_ingredient_goal as m

    gift = RedNPCItemGift(52, 3, 32, (2, 15), 31, 1, 105, 5, 52)
    w = NS(
        raw=RawGameState(
            True,
            14,
            10,
            10,
            party_size,
            0,
            badge_bits=int(Badge.THUNDER),
            event_flags=bytes(320),
            player_money=1000,
            bag_items=((3, 10),),
            party_species_ids=(28,) * party_size,
            party_hp=(100,) * party_size,
        ),
        owned=frozenset({9}),
        boxes=(),
        frame_count=0,
        pressed_buttons=(),
        phases=[],
        ready=True,
        fly=(8,),
        route_fault=False,
        revive_fault=False,
    )
    w.save_state_bytes = lambda: repr((w.raw, w.owned, w.boxes, w.frame_count)).encode()
    w.read = lambda: w.raw
    w.read_pokedex_state = lambda: NS(owned_species=w.owned)
    w.read_all_box_states = lambda: NS(current_box_index=0, boxes=(NS(species_ids=w.boxes),))
    w.read_fly_destinations = lambda: w.fly
    w.read_bottom_dialogue_box_visible = lambda: False
    adapter = NS(observe=lambda: NS(raw=w.raw, input_ready=w.ready))
    observer = NS(
        observe=lambda: TraversalSnapshot(
            w.raw.map_id, (w.raw.player_y, w.raw.player_x), w.ready, mode="land"
        )
    )
    actions = CountingExecutor(
        NS(execute=lambda a: setattr(w, "frame_count", w.frame_count + a.repeat))
    )

    def plan(start, map_id, *, goal_at):
        if w.route_fault or (map_id == 52 and goal_at != (3, 15)):
            raise RoutePlanningError("blocked")
        return NS(steps=(), terminal_mode="land", terminal_at=goal_at, map_id=map_id)

    world = NS(rules=NS(cut_block_swaps=()), plan_feasible_to_map=plan)
    world.with_current_observation = lambda _: world
    monkeypatch.setattr(m, "old_amber_gift", lambda _: gift)
    monkeypatch.setattr(m, "fly_menu_indices", lambda _: ())
    monkeypatch.setattr(m, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(m, "Gen1FieldMovePort", lambda actions, *a, **k: actions)
    monkeypatch.setattr(m, "Gen1WildFleeHandler", lambda *a, **k: None)

    def route(p, port, obs, **kwargs):
        port.execute(MacroAction(MacroActionKind.WAIT, repeat=10))
        w.raw = replace(
            w.raw, map_id=p.map_id, player_y=p.terminal_at[0], player_x=p.terminal_at[1]
        )
        w.phases.append("route")
        return NS(passed=True, executed_steps=(1,))

    monkeypatch.setattr(m, "execute_route", route)
    monkeypatch.setattr(m, "face_pc_boundary", lambda *a: None)

    def collect(*args, **kwargs):
        w.phases.append("gift")
        flags = bytearray(w.raw.event_flags)
        flags[105 // 8] |= 1 << (105 % 8)
        w.raw = replace(w.raw, bag_items=(*w.raw.bag_items, (31, 1)), event_flags=bytes(flags))
        return {"source_removed": True}

    monkeypatch.setattr(m, "collect_npc_item_gift", collect)

    class Revival:
        def __init__(self, actions, *args, **kwargs):
            self.actions = actions

        def execute(self, target):
            w.phases.append("revival")
            self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=10))
            if w.revive_fault:
                raise RuntimeError("revival fault retained")
            w.owned |= {142}
            if party_size == 6:
                w.boxes += (171,)
            else:
                w.raw = replace(
                    w.raw,
                    party_count=party_size + 1,
                    party_species_ids=(*w.raw.party_species_ids, 171),
                )
            w.raw = replace(
                w.raw, bag_items=tuple((i, n) for i, n in w.raw.bag_items if i != 31), map_id=170
            )
            return NS(public_dict=lambda: {"registration_added": True})

    monkeypatch.setattr(m, "RedRoutedFossilRevival", Revival)
    p = RedFossilIngredientGoalProvider(b"fixture", adapter, w, w, actions, world, observer)
    return w, p


@pytest.mark.parametrize("party_size", [5, 6])
def test_whole_ingredient_goal_is_read_only_then_exact_acquisition(monkeypatch, party_size):
    w, p = fixture(monkeypatch, party_size=party_size)
    before = w.save_state_bytes()
    b = p.offer(p.adapter.observe()).binding
    assert b is not None and before == w.save_state_bytes() and not w.phases
    report = b.execute()
    assert w.phases == ["route", "gift", "route", "revival"]
    assert report.actions_executed == 3 and report.frames_executed == 30
    assert b.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert b.verify(replace(report)).status is GoalDecisionOutcome.FAILED
    with pytest.raises(RuntimeError, match="already attempted"):
        b.execute()


@pytest.mark.parametrize("fault", ["source", "actions", "frames"])
def test_changed_source_refuses_without_input(monkeypatch, fault):
    w, p = fixture(monkeypatch)
    b = p.offer(p.adapter.observe()).binding
    if fault == "source":
        w.raw = replace(w.raw, player_money=2)
    if fault == "actions":
        p.actions.actions_executed += 1
    if fault == "frames":
        w.frame_count += 1
    before = (p.actions.actions_executed, w.frame_count)
    with pytest.raises(RuntimeError, match="source changed"):
        b.execute()
    assert before == (p.actions.actions_executed, w.frame_count) and not w.phases


@pytest.mark.parametrize(
    "fault",
    [
        "owned",
        "consumed",
        "flags",
        "fossil",
        "pending",
        "bag_full",
        "box_full",
        "dead",
        "badge",
        "fly",
        "indoors",
        "battle",
        "not_ready",
        "route",
    ],
)
def test_unavailable_conditions_never_touch_controller(monkeypatch, fault):
    w, p = fixture(monkeypatch)
    if fault == "owned":
        w.owned |= {142}
    if fault in {"consumed", "pending"}:
        flag = 105 if fault == "consumed" else int(EventFlag.GAVE_FOSSIL_TO_LAB)
        flags = bytearray(320)
        flags[flag // 8] |= 1 << (flag % 8)
        w.raw = replace(w.raw, event_flags=bytes(flags))
    if fault == "flags":
        w.raw = replace(w.raw, event_flags=None)
    if fault == "fossil":
        w.raw = replace(w.raw, bag_items=((42, 1),))
    if fault == "bag_full":
        w.raw = replace(w.raw, bag_items=tuple((i, 1) for i in range(1, 21)))
    if fault == "box_full":
        w.boxes = (28,) * 20
    if fault == "dead":
        w.raw = replace(w.raw, party_hp=(0,) * 6)
    if fault == "badge":
        w.raw = replace(w.raw, badge_bits=0)
    if fault == "fly":
        w.fly = ()
    if fault == "indoors":
        w.raw = replace(w.raw, map_id=170)
    if fault == "battle":
        w.raw = replace(w.raw, battle_state=1)
    if fault == "not_ready":
        w.ready = False
    if fault == "route":
        w.route_fault = True
    assert p.offer(p.adapter.observe()).binding is None
    assert not w.phases and p.actions.actions_executed == w.frame_count == 0


def test_partial_failure_preserves_ingredient_and_prevents_binding_replay(monkeypatch):
    w, p = fixture(monkeypatch)
    b = p.offer(p.adapter.observe()).binding
    w.revive_fault = True
    with pytest.raises(RuntimeError, match="revival fault"):
        b.execute()
    assert (31, 1) in w.raw.bag_items and 142 not in w.owned
    with pytest.raises(RuntimeError, match="already attempted"):
        b.execute()


def test_shared_hard_action_budget_stops_before_reviving(monkeypatch):
    w, p = fixture(monkeypatch)
    p = replace(p, maximum_actions=2)
    b = p.offer(p.adapter.observe()).binding
    with pytest.raises(RuntimeError, match="budget"):
        b.execute()
    assert p.actions.actions_executed == 2 and w.frame_count == 20 and 142 not in w.owned


@pytest.mark.parametrize("fault", ["party", "box", "dex", "money", "bag", "state"])
def test_verified_result_cannot_be_reused_after_any_terminal_drift(monkeypatch, fault):
    w, p = fixture(monkeypatch)
    b = p.offer(p.adapter.observe()).binding
    report = b.execute()
    if fault == "party":
        w.raw = replace(w.raw, party_species_ids=(28,))
    if fault == "box":
        w.boxes = ()
    if fault == "dex":
        w.owned |= {1}
    if fault == "money":
        w.raw = replace(w.raw, player_money=999)
    if fault == "bag":
        w.raw = replace(w.raw, bag_items=())
    if fault == "state":
        w.frame_count += 1
    assert b.verify(report).status is GoalDecisionOutcome.FAILED
