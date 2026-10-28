from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _situation
from test_red_super_rod_support import _GiftActions, _raw, _Reader

from pokemon_red_completion import red_autonomous_fishing as f
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_super_rod_support import SUPER_ROD_STATUS_MASK
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(monkeypatch):
    reader = _Reader(_raw())
    reader.read_pokedex_state = lambda: N(owned_species=(7, 8, 9))
    em = N(frame_count=0, pressed_buttons=frozenset(),
           save_state_bytes=lambda: repr(reader.raw).encode())
    guarded = []
    rt = N(reader=reader, emulator=em, registration_policy=object(),
           adapter=N(party_guard=N(verify_active_roster_restored=lambda: guarded.append(True))))
    actions = N(actions_executed=0)
    obs = N(raw=reader.raw, input_ready=True, situation=_situation())
    plan = N(steps=(object(), object()))
    world = N(rom=b"rom", plan_feasible_to_map=lambda *a, **k: plan)
    monkeypatch.setattr(f, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(f, "red_super_rod_destination_offers", lambda *a: (object(),))
    monkeypatch.setattr(f, "_supported_plan", lambda *a, **k: True)
    calls = []

    def support(*args, **kwargs):
        calls.append(kwargs)

        def execute():
            reader.raw = replace(reader.raw,
                bag_items=reader.raw.bag_items + ((int(ItemId.SUPER_ROD), 1),),
                status_flags_1=reader.raw.status_flags_1 | SUPER_ROD_STATUS_MASK)
            actions.actions_executed += 4
            em.frame_count += 96
            return N(public_dict=lambda: {"gift_controls_learned": False})

        return N(execute=execute)

    monkeypatch.setattr(f, "RedRoutedSuperRodSupport", support)
    return rt, obs, actions, world, guarded, calls


@pytest.mark.parametrize("missing", ("input", "live_input", "battle", "registration",
                                     "received", "bag_room", "productive", "route", "supported"))
def test_missing_prerequisite_conditions_offer_nothing_and_send_no_input(monkeypatch, missing):
    rt, obs, actions, world, _, calls = fixture(monkeypatch)
    if missing == "input":
        obs.input_ready = False
    elif missing == "live_input":
        rt.reader.ready = False
    elif missing == "battle":
        obs.raw = replace(obs.raw, battle_state=1)
    elif missing == "registration":
        rt.registration_policy = None
    elif missing == "received":
        rt.reader.raw = replace(rt.reader.raw,
            bag_items=((int(ItemId.SUPER_ROD), 1),), status_flags_1=SUPER_ROD_STATUS_MASK)
    elif missing == "bag_room":
        rt.reader.raw = replace(rt.reader.raw, bag_items=tuple((i, 1) for i in range(80, 100)))
    elif missing == "productive":
        monkeypatch.setattr(f, "red_super_rod_destination_offers", lambda *a: ())
    elif missing == "route":
        world.plan_feasible_to_map = lambda *a, **k: (_ for _ in ()).throw(RoutePlanningError("no"))
    else:
        monkeypatch.setattr(f, "_supported_plan", lambda *a, **k: False)
    source = rt.emulator.save_state_bytes()
    assert f.autonomous_fishing_prerequisite_option(rt, obs, actions, world) is None
    assert source == rt.emulator.save_state_bytes()
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0


def test_rod_is_action_free_resource_peer_and_reuses_exact_executor_then_disappears(monkeypatch):
    rt, obs, actions, world, guarded, calls = fixture(monkeypatch)
    def wrapper(inner):
        return inner
    source = rt.emulator.save_state_bytes()
    row = f.autonomous_fishing_prerequisite_option(
        rt, obs, actions, world, interruption_handler_wrapper=wrapper)
    assert row.binding.kind is GoalKind.RESUPPLY
    assert row.candidate.features.completion_gain == 0
    assert row.candidate.features.resource_cost == 0
    assert not calls and rt.emulator.save_state_bytes() == source
    assert row.binding.verify(GoalExecutionReport(0, 0, {})).status is GoalDecisionOutcome.FAILED
    report = row.binding.execute()
    assert report.actions_executed == 4 and report.frames_executed == 96
    assert calls[0]["interruption_handler_wrapper"] is wrapper and guarded == [True]
    assert calls[0]["maximum_gift_confirm_pulses"] == 64
    assert report.evidence["no_destination_selected"]
    assert not report.evidence["learned_gift_controls"]
    assert row.binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert row.binding.verify(replace(report)).status is GoalDecisionOutcome.FAILED
    with pytest.raises(ValueError, match="stale or consumed"):
        row.binding.execute()
    assert f.autonomous_fishing_prerequisite_option(rt, obs, actions, world) is None
    rt.reader.raw = replace(rt.reader.raw, player_money=59)
    assert row.binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_rod_stale_origin_never_runs_the_support(monkeypatch):
    rt, obs, actions, world, _, calls = fixture(monkeypatch)
    row = f.autonomous_fishing_prerequisite_option(rt, obs, actions, world)
    rt.reader.raw = replace(rt.reader.raw, player_money=59)
    with pytest.raises(ValueError, match="stale or consumed"):
        row.binding.execute()
    assert not calls


@pytest.mark.parametrize("fault", ("bag", "money", "dex"))
def test_rod_refuses_unverified_gift_resources(monkeypatch, fault):
    rt, obs, actions, world, _, _ = fixture(monkeypatch)
    original = f.RedRoutedSuperRodSupport

    def support(*a, **k):
        inner = original(*a, **k)

        def execute():
            result = inner.execute()
            if fault == "bag":
                rt.reader.raw = replace(rt.reader.raw, bag_items=rt.reader.raw.bag_items[1:])
            elif fault == "money":
                rt.reader.raw = replace(rt.reader.raw, player_money=0)
            else:
                rt.reader.read_pokedex_state = lambda: N(owned_species=())
            return result

        return N(execute=execute)

    monkeypatch.setattr(f, "RedRoutedSuperRodSupport", support)
    row = f.autonomous_fishing_prerequisite_option(rt, obs, actions, world)
    with pytest.raises(ValueError, match="protected resources"):
        row.binding.execute()


def test_rod_routes_may_earn_native_trainer_income_without_inventing_a_purchase(monkeypatch):
    rt, obs, actions, world, _, _ = fixture(monkeypatch)
    original = f.RedRoutedSuperRodSupport

    def support(*a, **k):
        inner = original(*a, **k)

        def execute():
            result = inner.execute()
            rt.reader.raw = replace(rt.reader.raw, player_money=500)
            return result

        return N(execute=execute)

    monkeypatch.setattr(f, "RedRoutedSuperRodSupport", support)
    row = f.autonomous_fishing_prerequisite_option(rt, obs, actions, world)
    report = row.binding.execute()
    assert row.binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert row.binding.maximum_cash_debit == 0


@pytest.mark.parametrize("kwargs", ({"maximum_actions": 0}, {"maximum_frames": True},
                                    {"interruption_handler_wrapper": "not callable"}))
def test_prerequisite_rejects_invalid_declared_limits(monkeypatch, kwargs):
    rt, obs, actions, world, _, _ = fixture(monkeypatch)
    with pytest.raises((TypeError, ValueError)):
        f.autonomous_fishing_prerequisite_option(rt, obs, actions, world, **kwargs)


def retained_text(monkeypatch, *, settle_on=15):
    rt, _, _, _, guarded, _ = fixture(monkeypatch)
    rt.reader.raw = replace(rt.reader.raw,
        bag_items=rt.reader.raw.bag_items + ((int(ItemId.SUPER_ROD), 1),),
        status_flags_1=SUPER_ROD_STATUS_MASK)
    rt.reader.dialogue = True
    delegate = _GiftActions(rt.reader, rt.emulator, acquire_on=99, settle_on=settle_on)
    return rt, CountingExecutor(delegate), delegate, guarded


@pytest.mark.parametrize("missing", ("map", "stance", "facing", "acquired",
                                     "input", "dialogue", "battle"))
def test_retained_rod_text_only_admits_exact_boundary_without_inputs(monkeypatch, missing):
    rt, actions, delegate, _ = retained_text(monkeypatch)
    if missing == "map":
        rt.reader.raw = replace(rt.reader.raw, map_id=1)
    elif missing == "stance":
        rt.reader.raw = replace(rt.reader.raw, player_y=2)
    elif missing == "facing":
        rt.reader.facing = "up"
    elif missing == "acquired":
        rt.reader.raw = replace(rt.reader.raw, bag_items=((3, 12),), status_flags_1=0)
    elif missing == "input":
        rt.reader.ready = False
    elif missing == "dialogue":
        rt.reader.dialogue = False
    else:
        rt.reader.raw = replace(rt.reader.raw, battle_state=2)
    assert f.acquired_fishing_tool_dialogue_binding(rt, actions) is None
    assert not delegate.kinds and actions.actions_executed == 0


def test_retained_rod_text_uses_existing_settler_and_preserves_gift(monkeypatch):
    rt, actions, delegate, guarded = retained_text(monkeypatch)
    raw = rt.reader.raw
    binding = f.acquired_fishing_tool_dialogue_binding(rt, actions)
    assert binding.kind is GoalKind.RECOVER_CONTROL
    assert binding.verify(GoalExecutionReport(0, 0, {})).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert report.actions_executed == 15 and report.frames_executed == 360
    assert delegate.kinds == [MacroActionKind.CANCEL] * 15
    assert rt.reader.raw == raw and guarded == [True]
    assert report.evidence["new_acquisition"] is False
    assert report.evidence["training_examples"] == 0
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert binding.verify(replace(report)).status is GoalDecisionOutcome.FAILED
    with pytest.raises(ValueError, match="stale or consumed"):
        binding.execute()
    assert f.acquired_fishing_tool_dialogue_binding(rt, actions) is None


def test_stale_retained_rod_text_never_runs(monkeypatch):
    rt, actions, delegate, _ = retained_text(monkeypatch)
    binding = f.acquired_fishing_tool_dialogue_binding(rt, actions)
    rt.reader.raw = replace(rt.reader.raw, player_money=500)
    with pytest.raises(ValueError, match="stale or consumed"):
        binding.execute()
    assert not delegate.kinds


def test_retained_rod_text_keeps_bounded_failure_and_exact_resource_guard(monkeypatch):
    from pokemon_red_completion.red_super_rod_support import RedSuperRodSupportError

    rt, actions, delegate, _ = retained_text(monkeypatch, settle_on=99)
    binding = f.acquired_fishing_tool_dialogue_binding(rt, actions, maximum_confirm_pulses=2)
    with pytest.raises(RedSuperRodSupportError, match="confirmation bound"):
        binding.execute()
    assert len(delegate.kinds) == 2
    rt, actions, delegate, _ = retained_text(monkeypatch)
    inner = delegate.execute

    def corrupt(action):
        inner(action)
        rt.reader.raw = replace(rt.reader.raw, player_money=0)

    delegate.execute = corrupt
    with pytest.raises(RedSuperRodSupportError, match="protected game state"):
        f.acquired_fishing_tool_dialogue_binding(rt, actions).execute()
