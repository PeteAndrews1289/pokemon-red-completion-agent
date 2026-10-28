from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.observation import Badge, EventFlag, MapId, RawGameState
from pokemon_red_completion.red_field_item import RedFieldItem
from pokemon_red_completion.red_finite_item_evolution_goal import RedFiniteItemEvolutionGoalProvider
from pokemon_red_completion.red_goal_context import RedGoalContextError
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(monkeypatch):
    import pokemon_red_completion.red_finite_item_evolution_goal as m

    target = RedFieldItem(10, 13, 2, 59, (54, 13))
    flags = bytearray(320)
    flags[int(EventFlag.GOT_POKEDEX) // 8] |= 1 << (int(EventFlag.GOT_POKEDEX) % 8)
    w = NS(
        raw=RawGameState(
            True,
            13,
            14,
            54,
            6,
            0,
            badge_bits=int(Badge.THUNDER),
            event_flags=bytes(flags),
            player_money=1000,
            bag_items=((3, 10),),
            party_hp=(100,) * 6,
        ),
        collection="before",
        frame_count=0,
        pressed_buttons=(),
        ready=True,
        visible=True,
        moving=False,
        dialogue=False,
        route_fault=False,
        storage_fault=False,
        protected=False,
        prompt=False,
        fail_child=False,
        bad_verdict=False,
        bad_pickup=False,
        pc=(),
        phases=[],
        fly=(int(MapId.CELADON_CITY),),
    )
    w.save_state_bytes = lambda: repr(
        (w.raw, w.collection, w.frame_count, w.pc, w.visible)
    ).encode()
    w.read_pc_items = lambda: w.pc
    w.read_fly_destinations = lambda: w.fly
    w.read_bottom_dialogue_box_visible = lambda: w.dialogue
    w.read_current_map_objects = lambda: (
        NS(sprite_index=2, picture_id=59, at=target.at, visible=w.visible, moving=w.moving),
    )
    adapter = NS(
        observe=lambda: NS(raw=w.raw, collection_observation=w.collection, input_ready=w.ready)
    )
    observer = NS(
        observe=lambda: TraversalSnapshot(
            w.raw.map_id, (w.raw.player_y, w.raw.player_x), w.ready, mode="land"
        )
    )
    actions = CountingExecutor(NS(execute=lambda a: setattr(w, "frame_count", w.frame_count + 10)))

    def plan(start, map_id, *, goal_at):
        if w.route_fault:
            raise RoutePlanningError("blocked")
        return NS(steps=(), terminal_mode="land", terminal_at=goal_at, map_id=map_id)

    world = NS(rom=b"fixture", rules=NS(cut_block_swaps=()), plan_feasible_to_map=plan)
    world.with_current_observation = lambda _: world
    policy = NS(
        evolution_allowed=lambda *a: not w.protected,
        verify_evolution=lambda before, after, *a: before == "before" and after == "after",
    )
    spec = NS(
        kind=GoalKind.EVOLVE_SPECIES,
        parameters=dict(
            source_species_ref="pokemon:national:030",
            target_species_ref="pokemon:national:031",
            item_id=10,
        ),
    )
    runtime = NS(
        adapter=adapter,
        reader=w,
        emulator=w,
        registration_policy=policy,
        profile=NS(providers=(spec,), profile_sha256="a" * 64),
    )

    def request(*a):
        if w.storage_fault:
            raise RedGoalContextError("no boxed precursor")
        return NS(precursor_level=16)

    monkeypatch.setattr(m, "red_field_items", lambda *a: (target,))
    monkeypatch.setattr(m, "fly_menu_indices", lambda *a: ())
    monkeypatch.setattr(m, "bind_native_boxed_item_evolution", lambda r, *a, **k: r)
    monkeypatch.setattr(
        m, "_RedTeamGoalProvider", lambda *a: NS(_boxed_item_evolution_request=request)
    )
    monkeypatch.setattr(m, "level_up_learnsets", lambda *a: {31: ((16, 1),)} if w.prompt else {})
    monkeypatch.setattr(m, "red_fly_landings", lambda *a: ((int(MapId.CELADON_CITY), (10, 10)),))
    monkeypatch.setattr(m, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(m, "Gen1WildFleeHandler", lambda *a, **k: None)
    monkeypatch.setattr(m, "face_pc_boundary", lambda *a: None)

    class Port:
        def __init__(self, actions, *a, **k):
            self.actions = actions

        def execute(self, action):
            self.actions.execute(action)
            if action.kind is MacroActionKind.FIELD_MOVE:
                w.phases.append("fly")
                w.raw = replace(w.raw, map_id=int(MapId.CELADON_CITY), player_y=10, player_x=10)

    monkeypatch.setattr(m, "Gen1FieldMovePort", Port)

    def route(plan, port, *a, **k):
        port.execute(MacroAction(MacroActionKind.WAIT))
        w.raw = replace(
            w.raw, map_id=plan.map_id, player_y=plan.terminal_at[0], player_x=plan.terminal_at[1]
        )
        w.phases.append("route")
        return NS(passed=True, executed_steps=(1,))

    monkeypatch.setattr(m, "execute_route", route)

    def pickup(actions, *a):
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        w.phases.append("pickup")
        w.visible = False
        w.raw = replace(w.raw, bag_items=(*w.raw.bag_items, (10, 2 if w.bad_pickup else 1)))

    monkeypatch.setattr(m, "collect_visible_field_item", pickup)

    def provider(kind, child_actions):
        def execute():
            child_actions.execute(MacroAction(MacroActionKind.WAIT))
            w.phases.append("evolution")
            if w.fail_child:
                raise RuntimeError("child failure retained")
            w.raw = replace(w.raw, bag_items=((3, 10),))
            w.collection = "after"
            return GoalExecutionReport(1, 10, {})

        return NS(
            offer=lambda _: NS(
                binding=NS(
                    execute=execute,
                    verify=lambda _: (
                        GoalVerification.failed(m.GoalFailureReason.OUTCOME_NOT_VERIFIED)
                        if w.bad_verdict
                        else GoalVerification.succeeded()
                    ),
                )
            )
        )

    runtime.provider_for = provider
    return w, RedFiniteItemEvolutionGoalProvider(runtime, actions, world, observer, target)


def test_whole_goal_read_only_offer_exact_consumption_and_single_use(monkeypatch):
    w, p = fixture(monkeypatch)
    before = w.save_state_bytes()
    b = p.offer(p.runtime.adapter.observe()).binding
    assert b is not None and w.save_state_bytes() == before and not w.phases
    report = b.execute()
    assert w.phases == ["route", "pickup", "fly", "route", "evolution"]
    assert (report.actions_executed, report.frames_executed) == (5, 50)
    assert b.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert b.verify(replace(report)).status is GoalDecisionOutcome.FAILED
    with pytest.raises(RuntimeError, match="already attempted"):
        b.execute()
    w.raw = replace(w.raw, player_money=0)
    assert b.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize(
    "fault",
    [
        "visible",
        "moving",
        "ready",
        "dialogue",
        "route_fault",
        "storage_fault",
        "protected",
        "prompt",
        "fly",
        "bag",
        "held",
        "dead",
        "badge",
        "flags",
        "battle",
        "indoors",
    ],
)
def test_unavailable_has_no_input(monkeypatch, fault):
    w, p = fixture(monkeypatch)
    if fault in ("visible", "ready"):
        setattr(w, fault, False)
    elif fault in ("moving", "dialogue", "route_fault", "storage_fault", "protected", "prompt"):
        setattr(w, fault, True)
    elif fault == "fly":
        w.fly = ()
    else:
        changes = dict(
            bag={"bag_items": tuple((i, 1) for i in range(20, 40))},
            held={"bag_items": ((10, 1),)},
            dead={"party_hp": (0,) * 6},
            badge={"badge_bits": 0},
            flags={"event_flags": None},
            battle={"battle_state": 1},
            indoors={"map_id": 170},
        )
        w.raw = replace(w.raw, **changes[fault])
    before = w.save_state_bytes()
    assert p.offer(p.runtime.adapter.observe()).binding is None
    assert w.save_state_bytes() == before and not w.phases and p.actions.actions_executed == 0


@pytest.mark.parametrize("fault", ["source", "actions", "frames", "pc"])
def test_changed_origin_refuses_before_input(monkeypatch, fault):
    w, p = fixture(monkeypatch)
    b = p.offer(p.runtime.adapter.observe()).binding
    if fault == "source":
        w.raw = replace(w.raw, player_money=2)
    elif fault == "actions":
        p.actions.actions_executed += 1
    elif fault == "frames":
        w.frame_count += 1
    else:
        w.pc = ((3, 1),)
    before = w.save_state_bytes(), p.actions.actions_executed
    with pytest.raises(RuntimeError, match="changed"):
        b.execute()
    assert before == (w.save_state_bytes(), p.actions.actions_executed) and not w.phases


def test_failure_retains_acquired_item_and_no_replay(monkeypatch):
    w, p = fixture(monkeypatch)
    b = p.offer(p.runtime.adapter.observe()).binding
    w.fail_child = True
    with pytest.raises(RuntimeError, match="child failure"):
        b.execute()
    assert dict(w.raw.bag_items)[10] == 1 and w.collection == "before"
    with pytest.raises(RuntimeError, match="already attempted"):
        b.execute()


def test_shared_cap_stops_before_child(monkeypatch):
    w, p = fixture(monkeypatch)
    b = replace(p, maximum_actions=4).offer(p.runtime.adapter.observe()).binding
    with pytest.raises(Exception, match="action.*budget|action.*limit"):
        b.execute()
    assert p.actions.actions_executed == 4 and "evolution" not in w.phases
    assert dict(w.raw.bag_items)[10] == 1


def test_bad_pickup_stops_before_transport(monkeypatch):
    w, p = fixture(monkeypatch)
    b = p.offer(p.runtime.adapter.observe()).binding
    w.bad_pickup = True
    with pytest.raises(RuntimeError, match="preparation changed"):
        b.execute()
    assert w.phases == ["route", "pickup"]


def test_component_failure_is_not_success(monkeypatch):
    w, p = fixture(monkeypatch)
    b = p.offer(p.runtime.adapter.observe()).binding
    w.bad_verdict = True
    assert b.verify(b.execute()).status is GoalDecisionOutcome.FAILED


def test_stale_offer_and_invalid_target(monkeypatch):
    w, p = fixture(monkeypatch)
    old = p.runtime.adapter.observe()
    w.raw = replace(w.raw, player_money=2)
    with pytest.raises(ValueError, match="stale"):
        p.offer(old)
    with pytest.raises(ValueError, match="cartridge"):
        replace(p, target=replace(p.target, item_id=11))
    with pytest.raises(ValueError, match="positive"):
        replace(p, maximum_actions=0)
