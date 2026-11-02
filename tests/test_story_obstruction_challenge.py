"""ROM-free challenge observation tests; no native input, model query, or fit."""

import ast
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion import red_player_early_story_options as p
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_story_battle import StoryTrainerContract


def fixture(monkeypatch):
    raw = N(map_id=51, event_flags=bytes(320), bag_items=())
    s = N(
        raw=raw,
        state=b"observed-native-fixture",
        frame_count=0,
        actions=N(actions_executed=0),
        calls=[],
        quote_calls=[],
        fault=None,
    )
    s.emulator = N(save_state_bytes=lambda: s.state, frame_count=0)
    s.runtime = N(
        reader=N(read=lambda: s.raw),
        emulator=s.emulator,
        adapter=N(
            observe=lambda: N(game_state=None),
            graph=N(available_objectives=lambda _: (N(id="reach_pewter"),)),
        ),
    )
    s.route = N(rom=b"fixture-cartridge")
    s.binding = _binding(GoalKind.ADVANCE_STORY, binding_ref="private:exact-obstruction", calls=[])
    s.contract = StoryTrainerContract(
        "reach_pewter", "observed-story-obstruction", 51, (202, 2, 3), 1380, 70
    )
    s.quote_levels = (7,)
    s.travel = None
    monkeypatch.setattr(p, "_field_ready", lambda _: True)
    monkeypatch.setattr(p, "story_travel_binding", lambda *a, **k: s.travel)

    def obstruct(*args, **kwargs):
        s.calls.append(kwargs)
        observer = kwargs.get("observe_binding")
        if observer is not None and s.binding is not None:
            if s.fault != "missing_witness":
                observer(s.contract, object() if s.fault == "other_binding" else s.binding)
            if s.fault == "duplicate":
                observer(s.contract, s.binding)
        if s.fault == "source":
            s.state = b"different-state"
        if s.fault == "frames":
            s.emulator.frame_count += 1
        if s.fault == "actions":
            s.actions.actions_executed += 1
        return None if s.fault == "no_returned_binding" else s.binding

    def quote(rom, trainer_class, trainer_set):
        s.quote_calls.append((rom, trainer_class, trainer_set))
        if s.fault == "quote_frames":
            s.emulator.frame_count += 1
        return N(party=tuple(N(level=level) for level in s.quote_levels))

    monkeypatch.setattr(p, "obstructing_story_battle_binding", obstruct)
    monkeypatch.setattr(p, "trainer_party_quote", quote)
    return s


def early(s, levels=(13,)):
    return p.early_story_travel_option(
        s.runtime,
        s.actions,
        objective_id="reach_pewter",
        route=s.route,
        battler="unchanged-actor",
        combat_levels=levels,
    )


def test_exact_known_levels_reach_existing_challenge_without_identity_features(monkeypatch):
    s = fixture(monkeypatch)
    binding, challenge = early(s)
    assert binding.binding_ref == s.binding.binding_ref
    assert binding.execute is s.binding.execute and binding.verify is s.binding.verify
    assert binding.story_unit == s.binding.story_unit is None
    assert binding.estimated_effort == s.binding.estimated_effort
    assert binding.estimated_risk == s.binding.estimated_risk
    assert challenge == OptionChallenge.from_levels(combat_levels=(13,), opponent_levels=(7,))
    assert s.quote_calls == [(s.route.rom, 202, 3)]
    assert s.calls[0]["battler"] == "unchanged-actor"
    assert s.calls[0]["frontier"] is True and s.calls[0]["allow_sequence"] is True
    assert s.calls[0]["intermediate_map"] is None
    public = json.dumps(challenge.public_dict())
    assert all(
        private not in public
        for private in ("reach_pewter", "exact-obstruction", "trainer", "1380")
    )
    assert s.actions.actions_executed == 0 and s.emulator.frame_count == 0
    assert s.state == b"observed-native-fixture"


def test_no_combat_members_retains_truthful_unknown_opposition(monkeypatch):
    s = fixture(monkeypatch)
    binding, challenge = early(s, ())
    assert binding.binding_ref == s.binding.binding_ref
    assert challenge == OptionChallenge(True, False, 0.0, 0.0, 0.0)
    assert s.quote_calls == []
    assert s.actions.actions_executed == 0


def test_absent_obstruction_stays_absent_without_quoting_or_dispatch(monkeypatch):
    s = fixture(monkeypatch)
    s.binding = None
    assert early(s) is None
    assert s.quote_calls == [] and s.actions.actions_executed == 0


def test_noncombat_travel_keeps_exact_old_row_and_skips_opposition_work(monkeypatch):
    s = fixture(monkeypatch)
    s.travel = replace(s.binding, binding_ref="private:travel")
    expected = p._row(s.travel, "reach_pewter", route=s.route)
    assert early(s) == expected
    assert s.calls == s.quote_calls == []


@pytest.mark.parametrize(
    "fault",
    [
        "objective",
        "map",
        "plan",
        "event",
        "reward_item",
        "badge",
        "type",
        "other_binding",
        "duplicate",
        "missing_witness",
        "no_returned_binding",
        "source",
        "frames",
        "actions",
        "quote_frames",
    ],
)
def test_witness_or_boundary_mismatch_fails_closed(monkeypatch, fault):
    s = fixture(monkeypatch)
    s.fault = fault
    if fault == "objective":
        s.contract = replace(s.contract, objective_id="reach_cerulean")
    elif fault == "map":
        s.contract = replace(s.contract, map_id=52)
    elif fault == "plan":
        s.contract = replace(s.contract, battle_plan_id="unrelated-component")
    elif fault == "event":
        events = bytearray(s.raw.event_flags)
        events[1380 // 8] |= 1 << (1380 % 8)
        s.raw.event_flags = bytes(events)
    elif fault == "reward_item":
        s.contract = replace(s.contract, victory_items=((4, 1),))
    elif fault == "badge":
        s.contract = replace(s.contract, victory_badge_bits=1)
    elif fault == "type":
        s.contract = object()
    with pytest.raises(ValueError, match="arrival"):
        early(s)


@pytest.mark.parametrize("levels", [[13], (True,), (0,), (101,), (13,) * 7])
def test_malformed_combat_role_levels_rejected_without_input(monkeypatch, levels):
    s = fixture(monkeypatch)
    with pytest.raises(ValueError, match="combat-role"):
        early(s, levels)
    assert s.calls == s.quote_calls == []
    assert s.actions.actions_executed == 0


def compile_arrival(s, members):
    path = (
        Path(p.__file__).resolve().parents[2]
        / "runtime_helpers/red_whole_player_inventory_20261006.py"
    )
    arrivals = [
        n
        for n in ast.walk(ast.parse(path.read_text()))
        if isinstance(n, ast.FunctionDef) and n.name == "arrival"
    ]
    assert len(arrivals) == 1
    code = compile(
        ast.fix_missing_locations(ast.Module(body=arrivals, type_ignores=[])), str(path), "exec"
    )
    namespace = dict(
        include_rewards=False,
        route=s.route,
        holder={"actor": "unchanged-actor", "plan": object()},
        story_travel_binding=lambda *a, **k: s.travel,
        observed_story_obstruction_option=p.observed_story_obstruction_option,
        replace=replace,
        OptionChallenge=OptionChallenge,
        d=N(observe_preparation_members=lambda *a: members),
    )
    exec(code, namespace)
    return namespace["arrival"]


@pytest.mark.parametrize(
    "roles,expected",
    [
        ((("combat", 13), ("undecided", 99), ("utility", 88)), (13,)),
        ((("combat", 13), ("combat", 9), ("undecided", 99)), (13, 9)),
        ((("undecided", 13), ("utility", 99)), ()),
    ],
)
def test_actual_arrival_uses_only_current_combat_roles(monkeypatch, roles, expected):
    s = fixture(monkeypatch)
    members = tuple(N(purpose=N(value=role), observation=N(level=level)) for role, level in roles)
    arrival = compile_arrival(s, members)
    binding, challenge = arrival("reach_pewter", s.runtime, s.actions, None)
    assert binding.binding_ref == s.binding.binding_ref
    assert challenge == (
        OptionChallenge.from_levels(combat_levels=expected, opponent_levels=(7,))
        if expected
        else OptionChallenge(True, False, 0.0, 0.0, 0.0)
    )
    assert len(s.quote_calls) == int(bool(expected))
    assert s.actions.actions_executed == 0


def test_actual_arrival_noncombat_travel_does_not_observe_preparation(monkeypatch):
    s = fixture(monkeypatch)
    s.travel = replace(s.binding, binding_ref="private:travel")
    arrival = compile_arrival(s, ())
    arrival.__globals__["d"].observe_preparation_members = lambda *a: pytest.fail(
        "travel read combat roles"
    )
    binding, challenge = arrival("reach_pewter", s.runtime, s.actions, None)
    assert binding.binding_ref == s.travel.binding_ref
    assert challenge == OptionChallenge(False, False, 0.0, 0.0, 0.0)
    assert s.calls == s.quote_calls == []
