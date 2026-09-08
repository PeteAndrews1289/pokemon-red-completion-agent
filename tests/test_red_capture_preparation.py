"""Independent executor checks using real raw-to-semantic party observations."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_skills import _adapter, _raw, _Reader

import pokemon_red_completion.red_capture_preparation as preparation
from pokemon_red_completion.red_capture_lead import RedCaptureLeadError


def runtime(*, weak=True):
    raw = _raw()
    raw = replace(
        raw, party_count=2, party_species_ids=(0x70, 0x1C),
        party_levels=(10, 55), party_hp=(0 if weak else 180, 180),
        party_max_hp=(180, 180), party_status=(0, 0),
        party_moves=((106, 0, 0, 0) if weak else raw.party_moves[0], raw.party_moves[0]),
        party_pp=((35, 0, 0, 0) if weak else raw.party_pp[0], raw.party_pp[0]),
    )
    reader = _Reader(raw=raw, ready=True)
    return SimpleNamespace(reader=reader, adapter=_adapter(reader), emulator=object())


def swap_raw(reader):
    fields = (
        "party_species_ids", "party_levels", "party_hp", "party_max_hp",
        "party_status", "party_moves", "party_pp",
    )
    reader.raw = replace(reader.raw, **{
        field: tuple(reversed(getattr(reader.raw, field))) for field in fields
    })


def test_healthy_lead_needs_no_controller_input(monkeypatch):
    state = runtime(weak=False)
    monkeypatch.setattr(preparation, "close_menu", lambda *_: pytest.fail("unexpected menu"))
    monkeypatch.setattr(preparation, "swap_party_slots", lambda *_a, **_k: pytest.fail("swap"))
    assert preparation.prepare_capture_escort(state, object()) is False


def test_living_source_swaps_with_fainted_destination_preserving_faint(monkeypatch):
    state = runtime()
    monkeypatch.setattr(preparation, "close_menu", lambda *_: None)
    def swap(_emulator, _actions, reader, *, source_index, destination_index, label):
        assert (source_index, destination_index) == (1, 0)
        swap_raw(reader)
    monkeypatch.setattr(preparation, "swap_party_slots", swap)
    assert preparation.prepare_capture_escort(state, object()) is True
    assert state.reader.raw.party_hp == (180, 0)


@pytest.mark.parametrize(
    "damage", ["no_swap", "heal", "position", "bag", "money", "battle", "unready",
               "badges", "events"],
)
def test_post_swap_damage_is_rejected(monkeypatch, damage):
    state = runtime()
    monkeypatch.setattr(preparation, "close_menu", lambda *_: None)
    def swap(*_a, **_k):
        if damage != "no_swap":
            swap_raw(state.reader)
        updates = {
            "heal": {"party_hp": (180, 180)}, "position": {"player_x": 99},
            "bag": {"bag_items": ((4, 1),)}, "money": {"player_money": 999},
            "battle": {"battle_state": 1},
            "badges": {"badge_bits": 255}, "events": {"event_flags": b"changed"},
        }.get(damage, {})
        state.reader.raw = replace(state.reader.raw, **updates)
        if damage == "unready":
            state.reader.ready = False
    monkeypatch.setattr(preparation, "swap_party_slots", swap)
    with pytest.raises(RedCaptureLeadError):
        preparation.prepare_capture_escort(state, object())


@pytest.mark.parametrize(
    "change", [{"party_hp": (0, 170)}, {"player_x": 99}, {"player_money": 999}],
)
def test_change_while_closing_menu_refuses_before_swap(monkeypatch, change):
    state = runtime()
    def close(*_):
        state.reader.raw = replace(state.reader.raw, **change)
    monkeypatch.setattr(preparation, "close_menu", close)
    monkeypatch.setattr(
        preparation, "swap_party_slots", lambda *_a, **_k: pytest.fail("stale swap"),
    )
    with pytest.raises(RedCaptureLeadError):
        preparation.prepare_capture_escort(state, object())


def test_checkpoint_recovery_mode_is_explicit_and_legacy_defaults_off():
    import run_paired_red_bounded_player as runner
    assert runner._checkpoint_routed_recovery({"metadata": {}}) is False
    assert runner._checkpoint_routed_recovery({"metadata": {"routed_recovery": True}}) is True
    for bad in (1, "true", None):
        with pytest.raises(runner.PairedRedBoundedPlayerRunError):
            runner._checkpoint_routed_recovery({"metadata": {"routed_recovery": bad}})


def test_general_lead_executor_rejects_fainted_target_without_input(monkeypatch):
    from pokemon_red_completion.red_capture_lead import RedCaptureLeadPlan

    state = runtime()
    plan = RedCaptureLeadPlan(0, state.adapter.observe().party)
    monkeypatch.setattr(preparation, "close_menu", lambda *_: pytest.fail("unexpected input"))
    with pytest.raises(RedCaptureLeadError, match="fainted"):
        preparation.prepare_observed_lead(state, object(), plan, label="test lead")


@pytest.mark.parametrize("change", [{"badge_bits": 255}, {"event_flags": b"changed"}])
def test_story_change_before_swap_is_rejected_without_swapping(monkeypatch, change):
    state = runtime()
    def close(*_):
        state.reader.raw = replace(state.reader.raw, **change)
    monkeypatch.setattr(preparation, "close_menu", close)
    monkeypatch.setattr(preparation, "swap_party_slots",
                        lambda *_a, **_k: pytest.fail("stale story boundary"))
    with pytest.raises(RedCaptureLeadError):
        preparation.prepare_capture_escort(state, object())
