from types import SimpleNamespace as N

import pytest
from test_red_player_story_battle import setup

from pokemon_red_completion import red_player_cut_lesson as s


def fixture(monkeypatch):
    rt, actions, route, raw, lesson, *_ = setup(monkeypatch)
    raw.party_moves = ((33, 39, 55, 145), (71, 0, 0, 0))
    rt.adapter.graph.available_objectives = lambda _: (N(id="defeat_surge"),)
    rt.adapter.observe = lambda: N(game_state=object())
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "capture_player_lesson_snapshot", lambda _: None)
    monkeypatch.setattr(
        s,
        "plan_machine_lesson",
        lambda *a, **k: N(party_slot=k["party_slot"], replace_slot=k["replace_slot"]),
    )
    calls = []
    monkeypatch.setattr(
        s,
        "execute_machine_lesson",
        lambda *a, **k: (calls.append(a[3]), setattr(actions, "actions_executed", 3)),
    )
    return rt, actions, raw, calls


def test_cut_support_uses_empty_slot_and_does_not_credit_surge(monkeypatch):
    rt, actions, raw, calls = fixture(monkeypatch)
    binding = s.cut_lesson_binding(rt, actions, rom=b"rom")
    assert not calls
    report = binding.execute()
    assert (calls[0].party_slot, calls[0].replace_slot) == (2, 2)
    assert report.evidence["objective_completed"] is False
    assert binding.verify(report).status.value == "succeeded"
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_opt_in_status_replacement_keeps_attacks_and_does_not_credit_surge(monkeypatch):
    rt, actions, raw, calls = fixture(monkeypatch)
    raw.party_moves = ((33, 39, 98, 158),)
    assert s.cut_lesson_binding(rt, actions, rom=b"rom") is None
    binding = s.cut_lesson_binding(rt, actions, rom=b"rom", allow_status_replacement=True)
    assert not calls
    report = binding.execute()
    assert (calls[0].party_slot, calls[0].replace_slot) == (1, 2)
    assert report.evidence["replaced_move"] == 39
    assert report.evidence["support"] == "first_compatible_non_hm_status_cut_lesson"
    assert not report.evidence["recipient_selection_learned"]
    assert not report.evidence["replacement_selection_learned"]
    assert report.evidence["objective_completed"] is False


def test_opt_in_still_prefers_empty_compatible_slots(monkeypatch):
    rt, actions, raw, calls = fixture(monkeypatch)
    binding = s.cut_lesson_binding(rt, actions, rom=b"rom", allow_status_replacement=True)
    binding.execute()
    assert (calls[0].party_slot, calls[0].replace_slot) == (2, 2)


def test_opt_in_never_forgets_hm_status_or_attacking_moves(monkeypatch):
    rt, actions, raw, calls = fixture(monkeypatch)
    raw.party_moves = ((148, 33, 55, 145),)
    assert s.cut_lesson_binding(rt, actions, rom=b"rom", allow_status_replacement=True) is None
    assert not calls


def test_status_replacement_fallback_checks_compatibility(monkeypatch):
    rt, actions, raw, calls = fixture(monkeypatch)
    raw.party_moves = ((33, 39, 55, 145), (33, 39, 98, 158))

    def compatible(*args, **kwargs):
        if kwargs["party_slot"] == 1:
            raise ValueError("incompatible")
        return N(party_slot=kwargs["party_slot"], replace_slot=kwargs["replace_slot"])

    monkeypatch.setattr(s, "plan_machine_lesson", compatible)
    binding = s.cut_lesson_binding(rt, actions, rom=b"rom", allow_status_replacement=True)
    binding.execute()
    assert (calls[0].party_slot, calls[0].replace_slot) == (2, 2)


@pytest.mark.parametrize("permission", [None, 1, "true"])
def test_status_replacement_requires_explicit_boolean_zero_input(monkeypatch, permission):
    rt, actions, raw, calls = fixture(monkeypatch)
    with pytest.raises(TypeError, match="boolean"):
        s.cut_lesson_binding(rt, actions, rom=b"rom", allow_status_replacement=permission)
    assert not calls


@pytest.mark.parametrize("fault", ["known", "full", "incompatible", "unavailable", "stale"])
def test_cut_lesson_unavailable_or_stale_zero_input(monkeypatch, fault):
    rt, actions, raw, calls = fixture(monkeypatch)
    if fault == "known":
        raw.party_moves = ((15, 0, 0, 0),)
    if fault == "full":
        raw.party_moves = ((33, 39, 55, 145),)
    if fault == "incompatible":

        def reject(*a, **k):
            raise ValueError("incompatible")

        monkeypatch.setattr(s, "plan_machine_lesson", reject)
    if fault == "unavailable":
        rt.adapter.graph.available_objectives = lambda _: ()
    binding = s.cut_lesson_binding(rt, actions, rom=b"rom")
    if fault == "stale":
        rt.emulator.save_state_bytes = lambda: b"changed"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
    else:
        assert binding is None
    assert not calls
