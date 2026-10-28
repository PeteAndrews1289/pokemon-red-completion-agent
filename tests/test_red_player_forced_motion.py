from copy import deepcopy
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_forced_motion as s
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


def setup(monkeypatch):
    raw = N(
        map_id=45,
        battle_state=0,
        player_y=3,
        player_x=19,
        player_money=20567,
        bag_items=((43, 1),),
        badge_bits=127,
        event_flags=b"events",
        party_hp=(0, 95),
        party_pp=((19, 30, 35, 30), (35, 15, 30, 15)),
        party_status=(0, 0),
        party_species_ids=(186, 150),
        party_levels=(28, 32),
        party_moves=((71, 15, 77, 78), (16, 28, 98, 19)),
    )
    state = N(
        payload=b"source",
        ready=False,
        fault=None,
        text=False,
        joy_ignore=255,
        simulated_joypad_index=1,
        movement_flags=128,
    )
    reader = N(
        read=lambda: deepcopy(raw),
        read_input_readiness=lambda: state,
        read_bottom_dialogue_box_visible=lambda: state.text,
        read_all_box_states=lambda: (),
        read_pc_items=lambda: (),
        read_pokedex_state=lambda: (),
    )
    em = N(frame_count=0, save_state_bytes=lambda: state.payload)
    rt = N(reader=reader, emulator=em)
    actions, calls = N(actions_executed=0), []

    def act(action):
        assert action.kind is MacroActionKind.WAIT
        calls.append(action)
        actions.actions_executed += 1
        em.frame_count += action.repeat
        state.payload = b"waiting"
        if state.fault != "stuck":
            raw.player_y = 2
            state.ready = True
        if state.fault == "path":
            raw.player_x = 18
        if state.fault == "endpoint":
            raw.player_y = 3
        if state.fault == "map":
            raw.map_id = 1
        if state.fault == "battle":
            raw.battle_state = 2
        if state.fault == "cash":
            raw.player_money -= 1
        if state.fault == "hp":
            raw.party_hp = (0, 94)
        if state.fault == "pp":
            raw.party_pp = ()
        if state.fault == "event":
            raw.event_flags = b"changed"

    actions.execute = act
    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready)
    monkeypatch.setattr(s, "spinner_sequences", lambda *a: {(11, 19): ((3, 19), (2, 19))})
    monkeypatch.setattr(
        s, "capture_player_lesson_snapshot", lambda _: (N(), dict(party="unchanged"))
    )
    return rt, actions, raw, state, calls


def test_retained_spinner_wait_is_quoted_without_input_and_preserves_resources(monkeypatch):
    rt, actions, raw, state, calls = setup(monkeypatch)
    binding = s.interrupted_motion_binding(rt, actions, rom=b"rom")
    assert not calls and binding.verify(None).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert (raw.player_y, raw.player_x) == (2, 19)
    assert report.actions_executed == 1 and report.frames_executed == 120
    assert report.evidence["directional_inputs"] == report.evidence["model_queries"] == 0
    assert not report.evidence["learned_recovery"]
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"later"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize(
    "fault", ["ready", "map", "battle", "text", "joy", "index", "flag", "off_path", "ambiguous"]
)
def test_missing_motion_boundary_is_not_an_arbitrary_control_override(monkeypatch, fault):
    rt, actions, raw, state, calls = setup(monkeypatch)
    if fault == "ready":
        state.ready = True
    if fault == "map":
        raw.map_id = 1
    if fault == "battle":
        raw.battle_state = 2
    if fault == "text":
        state.text = True
    if fault == "joy":
        state.joy_ignore = 0
    if fault == "index":
        state.simulated_joypad_index = 0
    if fault == "flag":
        state.movement_flags = 0
    if fault == "off_path":
        raw.player_x = 18
    if fault == "ambiguous":
        monkeypatch.setattr(
            s,
            "spinner_sequences",
            lambda *a: {(11, 19): ((3, 19), (2, 19)), (4, 19): ((3, 19), (3, 18))},
        )
    assert s.interrupted_motion_binding(rt, actions, rom=b"rom") is None
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize(
    "fault", ["path", "endpoint", "map", "battle", "cash", "hp", "pp", "event", "stuck"]
)
def test_motion_recovery_keeps_exact_endpoint_resources_and_finite_waits(monkeypatch, fault):
    rt, actions, _, state, calls = setup(monkeypatch)
    state.fault = fault
    binding = s.interrupted_motion_binding(rt, actions, rom=b"rom", maximum_waits=2)
    with pytest.raises(RuntimeError, match="motion"):
        binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    assert len(calls) <= 2


def test_stale_motion_binding_sends_no_input(monkeypatch):
    rt, actions, _, state, calls = setup(monkeypatch)
    binding = s.interrupted_motion_binding(rt, actions, rom=b"rom")
    state.payload = b"stale"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls


def escort_setup(monkeypatch):
    rt, actions, raw, state, calls = setup(monkeypatch)
    raw.map_id = 2
    raw.party_max_hp, raw.party_stats = (0, 95), ((1, 2, 3, 4),)
    state.joy_ignore, state.npc_movement_script_table = 240, 3
    state.local_script, state.beat_brock = 4, False
    rt.emulator.pressed_buttons = ()
    rt.reader.read_pewter_chapter_state = lambda _: N(
        local_script=state.local_script, beat_brock=state.beat_brock, controls=state)
    actions.execute_old = actions.execute

    def act(action):
        assert action.kind in {MacroActionKind.WAIT, MacroActionKind.CONFIRM}
        if state.text:
            assert action.kind is MacroActionKind.CONFIRM or state.fault == "stuck"
        if action.kind is MacroActionKind.CONFIRM:
            assert not state.npc_movement_script_table and not state.simulated_joypad_index
            state.text, state.local_script = False, 6
            calls.append(action)
            actions.actions_executed += 1
            rt.emulator.frame_count += 12
        elif state.npc_movement_script_table:
            calls.append(action)
            actions.actions_executed += 1
            rt.emulator.frame_count += action.repeat
            state.npc_movement_script_table = state.simulated_joypad_index = 0
            state.text = True
        else:
            state.text = False
            actions.execute_old(action)
            state.local_script = 0
            if state.fault == "script":
                state.local_script, state.ready = 1, False
        state.payload = b"native-escort"
    actions.execute = act
    return rt, actions, raw, state, calls


def test_existing_escort_finishes_native_motion_and_final_text_without_goal_selection(monkeypatch):
    rt, actions, raw, state, calls = escort_setup(monkeypatch)
    binding = s.interrupted_pewter_escort_binding(rt, actions)
    assert not calls and binding.verify(None).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert [a.kind for a in calls] == [MacroActionKind.WAIT, MacroActionKind.CONFIRM,
        MacroActionKind.WAIT]
    assert report.evidence["dialogue_confirms"] == 1
    assert report.evidence["model_queries"] == report.evidence["directional_inputs"] == 0
    assert not report.evidence["learned_recovery"]
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"later"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault",
    ["map", "battle", "phase", "badge", "joy", "npc", "held", "ready"])
def test_escort_only_admits_its_observed_native_boundary(monkeypatch, fault):
    rt, actions, raw, state, calls = escort_setup(monkeypatch)
    if fault == "map":
        raw.map_id = 1
    elif fault == "battle":
        raw.battle_state = 2
    elif fault == "phase":
        state.local_script = 0
    elif fault == "badge":
        state.beat_brock = True
    elif fault == "joy":
        state.joy_ignore = 0
    elif fault == "npc":
        state.npc_movement_script_table = 2
    elif fault == "held":
        rt.emulator.pressed_buttons = ("a",)
    elif fault == "ready":
        state.ready = True
    assert s.interrupted_pewter_escort_binding(rt, actions) is None
    assert not calls


@pytest.mark.parametrize("fault", ["cash", "hp", "pp", "event", "script", "stuck", "stale"])
def test_escort_keeps_resource_checks_and_finite_bound(monkeypatch, fault):
    rt, actions, _, state, calls = escort_setup(monkeypatch)
    binding = s.interrupted_pewter_escort_binding(rt, actions, maximum_waits=3)
    state.fault = fault
    if fault == "stale":
        state.payload = b"stale"
    with pytest.raises((ValueError, RuntimeError), match="escort"):
        binding.execute()
    assert len(calls) <= 6
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
