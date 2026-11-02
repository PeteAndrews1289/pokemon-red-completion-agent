from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_routed_semantic_goal import _observation
from test_red_static_capture_goal import fixture as capture_fixture

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.red_routed_static_capture import RedRoutedStaticCaptureGoalProvider
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError


def setup(monkeypatch, tmp_path):
    import pokemon_red_completion.red_pc_storage as storage
    import pokemon_red_completion.red_routed_static_capture as routed
    import pokemon_red_completion.red_static_capture_goal as capture

    w, p = capture_fixture(monkeypatch, tmp_path)
    w.raw = replace(w.raw, player_x=3, party_hp=(100,))
    w.read_all_box_states = lambda: NS(current_box_index=0, boxes=(NS(species_ids=()),))
    adapter = NS(
        observe=lambda: replace(
            _observation(NS(map_id=w.raw.map_id, at=(w.raw.player_y, w.raw.player_x), ready=True)),
            raw=w.raw,
        )
    )

    def dispatch(action):
        w.frame_count += action.repeat
        if action.kind is MacroActionKind.MOVE:
            assert action.value == "right"
            w.raw = replace(w.raw, player_x=4)

    actions = CountingExecutor(NS(execute=dispatch))
    p = replace(p, actions=actions, adapter=adapter, prepare_facing=True)

    def admit(reader, *args, **kwargs):
        if reader.read().player_x != 4:
            raise ValueError("not adjacent")

    monkeypatch.setattr(capture, "require_static_capture_admission", admit)
    monkeypatch.setattr(storage, "face_pc_boundary", lambda *args: None)
    monkeypatch.setattr(
        routed,
        "observe_static_capture",
        lambda *args: NS(registered=145 in w.owned, consumed=not w.visible),
    )
    monkeypatch.setattr(routed, "red_living_dex_setup_fresh_observation_sha256", lambda _: "e" * 64)

    def catch(*args, budget, commit_throw, **kwargs):
        budget.throws_committed = 1
        commit_throw(budget)
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=10))
        flags = bytearray(320)
        flags[1129 // 8] |= 1 << (1129 % 8)
        w.raw = replace(
            w.raw,
            party_species_ids=(28, 75),
            party_count=2,
            bag_items=((3, 20),),
            event_flags=bytes(flags),
        )
        w.owned |= {145}
        w.visible = False
        return NS(captured=True, consumed_event=True, source_removed=True)

    monkeypatch.setattr(capture, "execute_static_capture", catch)
    plan = RoutePlan(
        MacroPath((83,), ()),
        (10, 3),
        None,
        (),
        LocalPath(((10, 3), (10, 4)), (LocalEdge((10, 4), "right"),), (None, None)),
        (10, 4),
        None,
    )
    requests = []

    def plan_to(start, map_id, *, goal_at):
        requests.append(goal_at)
        if goal_at != (10, 4):
            raise RoutePlanningError("blocked side")
        return plan

    world = NS(rules=NS(cut_block_swaps=()), plan_feasible_to_map=plan_to)
    world.with_current_observation = lambda _: world
    observer = NS(
        observe=lambda: TraversalSnapshot(w.raw.map_id, (w.raw.player_y, w.raw.player_x), True)
    )
    provider = RedRoutedStaticCaptureGoalProvider(p, world, observer)
    return w, p, provider, requests


def test_route_offer_is_read_only_then_fresh_capture_and_total_cost_verified(monkeypatch, tmp_path):
    w, p, provider, requests = setup(monkeypatch, tmp_path)
    before = w.save_state_bytes()
    offer = provider.offer(p.adapter.observe())
    assert offer.binding is not None and len(requests) == 4
    assert w.save_state_bytes() == before and not list(tmp_path.iterdir())
    report = offer.binding.execute()
    assert offer.binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert report.actions_executed == p.actions.actions_executed == 2
    assert report.frames_executed == w.frame_count
    assert 145 in w.owned and not w.visible
    with pytest.raises(RuntimeError):
        offer.binding.execute()


def test_prospective_readiness_rechecks_stock_after_transport(monkeypatch, tmp_path):
    from test_red_capture_readiness import observation

    from pokemon_red_completion.observation import ItemId
    from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget

    w, p, provider, _ = setup(monkeypatch, tmp_path)
    observe_original = p.adapter.observe
    p.adapter.observe = lambda: replace(observe_original(), party=observation().party,
                                       immediate_capture_slots=5)
    p = replace(p, ball=ItemId.GREAT_BALL, max_throws=5,
                readiness_budget=CapturePreparationBudget(ItemId.GREAT_BALL, 5, 20))
    provider = replace(provider, capture=p)
    original = p.actions.delegate.execute

    def spend(action):
        original(action)
        if action.kind is MacroActionKind.MOVE:
            w.raw = replace(w.raw, bag_items=((3, 4),))

    p.actions.delegate.execute = spend
    binding = provider.offer(p.adapter.observe()).binding
    assert binding is not None
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    assert 145 not in w.owned and w.visible
    assert not list(tmp_path.iterdir())  # No encounter/throw commitment.


@pytest.mark.parametrize("fault", ["money", "frames", "actions"])
def test_routed_offer_rejects_changed_source_before_input(monkeypatch, tmp_path, fault):
    w, p, provider, _ = setup(monkeypatch, tmp_path)
    binding = provider.offer(p.adapter.observe()).binding
    if fault == "money":
        w.raw = replace(w.raw, player_money=1)
    if fault == "frames":
        w.frame_count += 1
    if fault == "actions":
        p.actions.execute(MacroAction(MacroActionKind.WAIT))
    count = p.actions.actions_executed
    with pytest.raises(RuntimeError, match="source changed"):
        binding.execute()
    assert p.actions.actions_executed == count and not list(tmp_path.iterdir())


@pytest.mark.parametrize("fault", ["registered", "consumed", "balls", "dead", "box_full", "limit"])
def test_unavailable_goals_do_not_generate_capture_actions(monkeypatch, tmp_path, fault):
    w, p, provider, _ = setup(monkeypatch, tmp_path)
    if fault == "registered":
        w.owned |= {145}
    if fault == "consumed":
        w.visible = False
    if fault == "balls":
        w.raw = replace(w.raw, bag_items=())
    if fault == "dead":
        w.raw = replace(w.raw, party_hp=(0,))
    if fault == "box_full":
        w.raw = replace(w.raw, party_count=6)
        w.read_all_box_states = lambda: NS(current_box_index=0, boxes=(NS(species_ids=(28,) * 20),))
    if fault == "limit":
        provider.world.plan_feasible_to_map = lambda *a, **k: (_ for _ in ()).throw(
            RoutePlanningError("puzzle not supported")
        )
    assert provider.offer(p.adapter.observe()).binding is None
    assert p.actions.actions_executed == 0 and not list(tmp_path.iterdir())


def test_arrival_rebinds_resources_instead_of_using_origin_capture_offer(monkeypatch, tmp_path):
    w, p, provider, _ = setup(monkeypatch, tmp_path)
    binding = provider.offer(p.adapter.observe()).binding
    import pokemon_red_completion.red_static_capture_goal as capture

    monkeypatch.setattr(
        capture,
        "require_static_capture_admission",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("new destination constraint")),
    )
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    assert w.raw.player_x == 4 and 145 not in w.owned
    assert not list(tmp_path.iterdir())
