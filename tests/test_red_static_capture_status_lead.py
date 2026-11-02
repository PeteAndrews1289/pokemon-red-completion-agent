"""Status lead preparation reuses protected swaps and fresh capture offers."""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_capture_preparation import runtime, swap_raw
from test_red_static_capture_goal import fixture

import pokemon_red_completion.red_capture_preparation as m
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_static_capture_goal import RedStaticCaptureGoalProvider


def setup(monkeypatch, tmp_path):
    w, provider = fixture(monkeypatch, tmp_path)
    original = provider.offer(w.observe()).binding
    provider = replace(provider, require_status_success=True)
    rt = runtime(weak=False)
    rt.reader.raw = replace(rt.reader.raw, party_moves=((33, 0, 0, 0), (78, 0, 0, 0)),
                            party_pp=((35, 0, 0, 0), (30, 0, 0, 0)))
    rt.emulator = NS(frame_count=0)
    actions = NS(actions_executed=0)
    captures, observations = [], []

    def offer(self, obs):
        observations.append(obs)

        def execute():
            assert obs == rt.adapter.observe(), "stale capture offer executed"
            captures.append(obs.party)
            actions.actions_executed += 3
            rt.emulator.frame_count += 30
            return GoalExecutionReport(3, 30, {"capture": True})

        return RedGoalBindingOffer.available(replace(
            original, execute=execute, verify=lambda report: report.evidence["capture"],
        ))

    monkeypatch.setattr(RedStaticCaptureGoalProvider, "offer", offer)
    monkeypatch.setattr(m, "close_menu", lambda *_: None)

    def swap(*args, **kwargs):
        assert kwargs["source_index"] == 1 and kwargs["destination_index"] == 0
        swap_raw(rt.reader)
        actions.actions_executed += 2
        rt.emulator.frame_count += 20

    monkeypatch.setattr(m, "swap_party_slots", swap)
    return provider, rt, actions, captures, observations


def test_read_only_offer_swap_fresh_rebind_and_complete_costs(monkeypatch, tmp_path):
    p, rt, actions, captures, observations = setup(monkeypatch, tmp_path)
    before = rt.adapter.observe()
    binding = m.status_prepared_static_offer(p, rt, actions, before).binding
    assert actions.actions_executed == 0 and not captures
    assert rt.adapter.observe() == before
    report = binding.execute()
    assert observations == [before, rt.adapter.observe()]
    assert captures[0].lead.moves[0].move_id == 78
    assert report.actions_executed == 5 and report.frames_executed == 50
    assert report.evidence["status_lead_preparation"] == {
        "qualified": True, "swapped": True, "setup_training_rows": 0,
    }
    assert binding.verify(report)
    with pytest.raises(RedCaptureLeadError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize("fault", ["hp", "pp", "status", "no_move"])
def test_missing_status_capability_is_action_free(monkeypatch, tmp_path, fault):
    p, rt, actions, captures, _ = setup(monkeypatch, tmp_path)
    changes = {"hp": {"party_hp": (180, 90)}, "pp": {"party_pp": ((35, 0, 0, 0), (0, 0, 0, 0))},
               "status": {"party_status": (0, 0x40)},
               "no_move": {"party_moves": ((33, 0, 0, 0), (33, 0, 0, 0))}}[fault]
    rt.reader.raw = replace(rt.reader.raw, **changes)
    assert m.status_prepared_static_offer(p, rt, actions, rt.adapter.observe()).binding is None
    assert not captures and actions.actions_executed == 0


def test_stale_offer_and_unenforced_status_refused(monkeypatch, tmp_path):
    p, rt, actions, captures, _ = setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="status-enforcing"):
        m.status_prepared_static_offer(replace(p, require_status_success=False), rt, actions,
                                       rt.adapter.observe())
    binding = m.status_prepared_static_offer(p, rt, actions, rt.adapter.observe()).binding
    rt.reader.raw = replace(rt.reader.raw, player_money=999)
    with pytest.raises(RedCaptureLeadError, match="changed"):
        binding.execute()
    assert not captures and actions.actions_executed == 0


def test_already_leading_helper_needs_no_swap(monkeypatch, tmp_path):
    p, rt, actions, captures, _ = setup(monkeypatch, tmp_path)
    swap_raw(rt.reader)
    monkeypatch.setattr(m, "swap_party_slots", lambda *_a, **_k: pytest.fail("unneeded swap"))
    binding = m.status_prepared_static_offer(p, rt, actions, rt.adapter.observe()).binding
    report = binding.execute()
    assert not report.evidence["status_lead_preparation"]["swapped"]
    assert len(captures) == 1 and actions.actions_executed == 3


def test_failed_swap_cannot_activate_capture(monkeypatch, tmp_path):
    p, rt, actions, captures, _ = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(m, "swap_party_slots", lambda *_a, **_k: None)
    binding = m.status_prepared_static_offer(p, rt, actions, rt.adapter.observe()).binding
    with pytest.raises(RedCaptureLeadError, match="post-swap"):
        binding.execute()
    assert not captures


def test_optional_status_no_helper_retains_exact_native_offer(monkeypatch, tmp_path):
    p, rt, actions, captures, observations = setup(monkeypatch, tmp_path)
    p = replace(p, require_status_success=False, weaken_capture=True)
    rt.reader.raw = replace(rt.reader.raw, party_moves=((33, 0, 0, 0), (33, 0, 0, 0)))
    before = rt.adapter.observe()
    monkeypatch.setattr(m, "swap_party_slots", lambda *_a, **_k: pytest.fail("no helper swap"))
    binding = m.optional_status_static_offer(p, rt, actions, before).binding
    assert rt.adapter.observe() == before and actions.actions_executed == 0
    assert not captures and observations == [before]
    report = binding.execute()
    assert report.actions_executed == 3 and len(captures) == 1
    assert "optional_status_lead_preparation" not in report.evidence
    assert binding.verify(report)


def test_optional_status_available_helper_reuses_guarded_swap(monkeypatch, tmp_path):
    p, rt, actions, captures, observations = setup(monkeypatch, tmp_path)
    p = replace(p, require_status_success=False, weaken_capture=True)
    before = rt.adapter.observe()
    binding = m.optional_status_static_offer(p, rt, actions, before).binding
    assert actions.actions_executed == 0 and not captures
    report = binding.execute()
    assert observations == [before, rt.adapter.observe()]
    assert captures[0].lead.moves[0].move_id == 78
    assert report.actions_executed == 5 and report.frames_executed == 50
    assert report.evidence["optional_status_lead_preparation"]["swapped"]
    assert binding.verify(report)


@pytest.mark.parametrize("changes", [
    {"require_status_success": True}, {"weaken_capture": False}, {"prepare_status": False},
])
def test_optional_status_requires_explicit_contract(monkeypatch, tmp_path, changes):
    p, rt, actions, captures, _ = setup(monkeypatch, tmp_path)
    p = replace(p, require_status_success=False, weaken_capture=True)
    with pytest.raises(ValueError, match="explicit live-weakening"):
        m.optional_status_static_offer(replace(p, **changes), rt, actions, rt.adapter.observe())
    assert actions.actions_executed == 0 and not captures


def test_optional_status_cannot_bypass_original_admission(monkeypatch, tmp_path):
    from pokemon_red_completion.goal_manager import GoalUnavailableReason
    p, rt, actions, captures, _ = setup(monkeypatch, tmp_path)
    p = replace(p, require_status_success=False, weaken_capture=True)
    monkeypatch.setattr(RedStaticCaptureGoalProvider, "offer", lambda *_:
        RedGoalBindingOffer.unavailable(p.kind, GoalUnavailableReason.MISSING_RESOURCE))
    assert m.optional_status_static_offer(p, rt, actions, rt.adapter.observe()).binding is None
    assert not captures and actions.actions_executed == 0


def test_optional_status_stale_source_does_not_activate(monkeypatch, tmp_path):
    p, rt, actions, captures, _ = setup(monkeypatch, tmp_path)
    p = replace(p, require_status_success=False, weaken_capture=True)
    binding = m.optional_status_static_offer(p, rt, actions, rt.adapter.observe()).binding
    rt.reader.raw = replace(rt.reader.raw, player_money=998)
    with pytest.raises(RedCaptureLeadError, match="changed"):
        binding.execute()
    assert not captures
