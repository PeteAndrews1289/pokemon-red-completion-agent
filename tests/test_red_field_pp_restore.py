from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_elixir_plan import finished, state
from test_red_goal_skills import _adapter, _Reader

import pokemon_red_completion.red_field_pp_restore as module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.red_elixir_plan import RedElixirPlanError


def fixture(monkeypatch, fault=None):
    reader = _Reader(raw=state(), ready=True)
    adapter = replace(_adapter(reader), include_pp_restoration=True)
    emulator = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    inputs, stages, targets = [], [], []

    def execute(action):
        inputs.append(action)
        emulator.frame_count += 24

    actions = CountingExecutor(SimpleNamespace(execute=execute))
    monkeypatch.setattr(module, "_open_bag", lambda *_: stages.append("bag"))
    monkeypatch.setattr(module, "_select_bag_item", lambda _a, _e, item, _t: (
        stages.append("item"), pytest.fail("wrong item") if int(item) != 82 else None,
    ))
    monkeypatch.setattr(module, "_select_cursor", lambda _a, _e, index, _t: targets.append(index))
    monkeypatch.setattr(module, "_close_menus", lambda *_: stages.append("closed"))

    def pulse(actions, kind, **_kwargs):
        if fault == "input_error":
            raise RuntimeError("controller failed")
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        if targets and fault != "no_consumption":
            assert targets == [1]  # non-lead, no reorder or hidden lead swap
            reader.raw = finished(state())
            if fault == "wrong_target":
                reader.raw = replace(reader.raw, party_pp=((10, 35, 0, 0), (2, 6, 0, 0)),
                                     first_party_pp=(10, 35, 0, 0))
    monkeypatch.setattr(module, "_pulse", pulse)
    provider = module.RedFieldPpRestoreGoalProvider(actions, reader, emulator, adapter)
    return provider, reader, adapter, inputs, stages


def test_nonlead_pp_use_has_exact_receipt_and_one_shot_success(monkeypatch):
    provider, _reader, adapter, inputs, stages = fixture(monkeypatch)
    offer = provider.offer(adapter.observe())
    assert offer.binding is not None and not inputs
    report = offer.binding.execute()
    assert stages == ["bag", "item", "closed"]
    assert report.evidence["restored_pp"] == 14
    assert report.evidence["owned_items_consumed"] == 1
    assert report.evidence["party_index"] == 1
    assert report.evidence["pp_gain_is_learned_target"] is False
    assert offer.binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    changed = replace(report, evidence={**report.evidence, "restored_pp": 99})
    assert offer.binding.verify(changed).status is GoalDecisionOutcome.FAILED
    count = len(inputs)
    with pytest.raises(module.RedFieldPpRestoreError, match="consumed"):
        offer.binding.execute()
    assert len(inputs) == count


@pytest.mark.parametrize("fault", ["wrong_target", "input_error", "no_consumption"])
def test_partial_failure_has_no_automatic_second_item_attempt(monkeypatch, fault):
    provider, _, adapter, inputs, _ = fixture(monkeypatch, fault)
    binding = provider.offer(adapter.observe()).binding
    with pytest.raises((module.RedFieldPpRestoreError, RedElixirPlanError, RuntimeError)):
        binding.execute()
    count = len(inputs)
    assert count <= 27
    with pytest.raises(module.RedFieldPpRestoreError, match="consumed"):
        binding.execute()
    assert len(inputs) == count


@pytest.mark.parametrize("fault", ["stale", "dialogue", "held", "not_ready"])
def test_stale_selected_pp_use_stops_before_any_controller_input(monkeypatch, fault):
    provider, reader, adapter, inputs, stages = fixture(monkeypatch)
    binding = provider.offer(adapter.observe()).binding
    if fault == "stale":
        reader.raw = replace(reader.raw, player_money=1233)
    elif fault == "dialogue":
        reader.dialogue = True
    elif fault == "held":
        provider.emulator.pressed_buttons = frozenset({"a"})
    else:
        reader.ready = False
    with pytest.raises(module.RedFieldPpRestoreError, match="origin"):
        binding.execute()
    assert not inputs and not stages


def test_old_observation_cannot_opt_itself_into_unaccounted_pp_use(monkeypatch):
    provider, reader, _, inputs, _ = fixture(monkeypatch)
    old = _adapter(reader).observe()
    assert provider.offer(old).binding is None
    assert not inputs


def two_stage_fixture(monkeypatch, *, stock, fault=None):
    provider, reader, adapter, inputs, stages = fixture(monkeypatch)
    reader.raw = replace(state(), bag_items=((53, 3), (82, stock), (4, 2)))
    timeline = []

    def select_target(_actions, _emulator, index, _timing):
        assert index == 1
        timeline.append("target")

    def pulse(actions, kind, **_kwargs):
        assert kind is MacroActionKind.CONFIRM
        assert "consumed" not in timeline, "confirmation spilled beyond item consumption"
        actions.execute(MacroAction(kind))
        if "target" not in timeline:
            return
        if "pp_changed" not in timeline:
            # ItemUsePPRestore writes all four PP slots before printing its
            # success message; RemoveUsedItem runs only after that text returns.
            assert len(inputs) == 3
            pp = (11, 10, 0, 0) if fault == "pp" else (12, 10, 0, 0)
            reader.raw = replace(reader.raw, party_pp=((1, 35, 0, 0), pp))
            timeline.append("pp_changed")
            assert dict(reader.raw.bag_items)[82] == stock
            return
        assert len(inputs) == 4
        assert dict(reader.raw.bag_items)[82] == stock
        if stock == 1 or fault == "extra_elixir":
            bag = ((53, 3), (4, 2))
        else:
            bag = ((53, 3), (82, 1), (4, 2))
        if fault == "other_item":
            bag = ((53, 2), (82, 1), (4, 2))
        reader.raw = replace(reader.raw, bag_items=bag,
                             bag_item_ids=tuple(item for item, _ in bag))
        timeline.append("consumed")

    def close_menus(actions, _reader, _timing):
        assert timeline == ["target", "pp_changed", "consumed"]
        for _ in range(4):
            actions.execute(MacroAction(MacroActionKind.CANCEL))
        timeline.append("closed")

    monkeypatch.setattr(module, "_select_cursor", select_target)
    monkeypatch.setattr(module, "_pulse", pulse)
    monkeypatch.setattr(module, "_close_menus", close_menus)
    return provider, reader, adapter, inputs, stages, timeline


@pytest.mark.parametrize("stock", [1, 2])
def test_pp_effect_precedes_stock_decrement_and_only_cancel_follows(monkeypatch, stock):
    provider, reader, adapter, inputs, _, timeline = two_stage_fixture(
        monkeypatch, stock=stock,
    )
    binding = provider.offer(adapter.observe()).binding
    assert binding is not None
    report = binding.execute()
    assert timeline == ["target", "pp_changed", "consumed", "closed"]
    assert [action.kind for action in inputs] == (
        [MacroActionKind.CONFIRM] * 4 + [MacroActionKind.CANCEL] * 4
    )
    assert dict(reader.raw.bag_items).get(82, 0) == stock - 1
    assert report.evidence["owned_items_consumed"] == 1
    assert report.evidence["restored_pp"] == 14
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize("fault", ["pp", "other_item", "extra_elixir"])
def test_two_stage_tampering_stops_at_decrement_without_retry(monkeypatch, fault):
    provider, _, adapter, inputs, _, timeline = two_stage_fixture(
        monkeypatch, stock=2, fault=fault,
    )
    binding = provider.offer(adapter.observe()).binding
    assert binding is not None
    with pytest.raises(RedElixirPlanError, match="exact PP effect or one-item consumption"):
        binding.execute()
    assert timeline == ["target", "pp_changed", "consumed"]
    assert [action.kind for action in inputs] == [MacroActionKind.CONFIRM] * 4
    with pytest.raises(module.RedFieldPpRestoreError, match="consumed"):
        binding.execute()
    assert len(inputs) == 4
