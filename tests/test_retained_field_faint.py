"""Exact native failed-tail evidence authorizes settlement, never arbitrary text."""
import json
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
from test_gen1_route_runtime import FakeReader
from test_red_routed_recovery import make_test_raw
from test_red_player_configuration import config
from pokemon_red_completion import red_player_forced_motion as motion
from pokemon_red_completion import red_player_configuration as configuration
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory


def environment(monkeypatch):
    raw = make_test_raw(map_id=197, x=12, y=26, hp=(0, 100), status=(0, 0))
    fake = FakeReader(raw, dialogue_visible=True, moving_direction=4)
    fake.read_all_box_states = lambda: ()
    fake.read_pokedex_state = lambda: ()
    fake.read_pc_items = lambda: ()
    fake.read_overworld_start_menu_visible = lambda: False
    state = N(payload=b"fainted-native-terminal", fault=None, pc=(), xp=0)
    emulator = N(save_state_bytes=lambda: state.payload, frame_count=0, pressed_buttons=())
    runtime = N(reader=fake, emulator=emulator)
    calls = []
    actions = N(actions_executed=0)

    def execute(action):
        assert action.kind in {MacroActionKind.CANCEL, MacroActionKind.WAIT}
        calls.append(action)
        actions.actions_executed += 1
        emulator.frame_count += max(1, action.repeat)
        state.payload = b"settled-native-terminal"
        if action.kind is MacroActionKind.CANCEL and state.fault != "stuck":
            fake.dialogue_visible = False
            fake.moving_direction = 0
        if state.fault == "cash":
            fake.raw = replace(fake.raw, player_money=raw.player_money + 1)
        if state.fault == "healing":
            fake.raw = replace(fake.raw, party_hp=(1, 100))
        if state.fault == "position":
            fake.raw = replace(fake.raw, player_x=13)
        if state.fault == "pc":
            state.pc = ((1, 1),)
        if state.fault == "xp":
            state.xp += 1

    actions.execute = execute
    monkeypatch.setattr(motion, "_purified_message_custody",
                        lambda rt: (state.pc, state.xp, rt.reader.read_all_box_states()))
    diag = json.loads(json.dumps(asdict(raw)))
    diag["party_pp_encoded"] = diag["party_pp"]
    before = deepcopy(diag)
    before["party_hp"] = [3, 100]
    before["party_status"] = [8, 0]
    outcome = dict(error_type="RouteExecutionError",
                   error="Gen I route cannot dismiss 'scripted_dialogue'",
                   failure_phase="execution", safe_terminal=True,
                   terminal_state_sha256=sha256(state.payload).hexdigest(),
                   before=dict(input_ready=True, battle_state=0, buttons_released=True,
                               diagnostics=before),
                   after=dict(input_ready=False, battle_state=0, buttons_released=True,
                              diagnostics=diag))
    return runtime, actions, state, outcome, calls


def test_exact_native_faint_settles_with_existing_handler_and_preserves_loss(monkeypatch):
    rt, actions, state, proof, calls = environment(monkeypatch)
    b = motion.retained_field_faint_binding(rt, actions, outcome=proof)
    assert b.kind is GoalKind.RECOVER_CONTROL
    assert b.binding_ref == "pokemon.red:retained-motion:" + proof["terminal_state_sha256"]
    assert not calls
    assert b.verify(None).status is GoalDecisionOutcome.FAILED
    report = b.execute()
    assert b.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert rt.reader.read().party_hp == (0, 100)
    assert report.evidence["route_details"]["native_field_faint"]
    assert report.evidence["model_queries"] == report.evidence["directional_inputs"] == 0
    assert [c.kind for c in calls] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]
    with pytest.raises(ValueError, match="stale or consumed"):
        b.execute()
    state.payload = b"later"
    assert b.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault", ["sha", "unknown_error", "no_poison", "no_prior_hp",
    "before_not_ready", "after_ready", "after_sha_fields", "species", "status", "battle",
    "npc", "no_dialogue", "held", "all_fainted", "bad_length", "non_integer"])
def test_invalid_or_unrelated_proof_sends_no_inputs(monkeypatch, fault):
    rt, actions, state, proof, calls = environment(monkeypatch)
    before, after = proof["before"], proof["after"]
    if fault == "sha": proof["terminal_state_sha256"] = "0" * 64
    if fault == "unknown_error": proof["error"] = "some other scripted dialogue"
    if fault == "no_poison": before["diagnostics"]["party_status"][0] = 0
    if fault == "no_prior_hp": before["diagnostics"]["party_hp"][0] = 0
    if fault == "before_not_ready": before["input_ready"] = False
    if fault == "after_ready": after["input_ready"] = True
    if fault == "after_sha_fields": after["diagnostics"]["player_money"] += 1
    if fault == "species": before["diagnostics"]["party_species_ids"][0] += 1
    if fault == "status": after["diagnostics"]["party_status"][0] = 8
    if fault == "battle": rt.reader.raw = replace(rt.reader.raw, battle_state=2)
    if fault == "npc": rt.reader.trainer_engagement = True
    if fault == "no_dialogue": rt.reader.dialogue_visible = False
    if fault == "held": rt.emulator.pressed_buttons = ("a",)
    if fault == "all_fainted": rt.reader.raw = replace(rt.reader.raw, party_hp=(0, 0))
    if fault == "bad_length": before["diagnostics"]["party_status"] = [8]
    if fault == "non_integer": before["diagnostics"]["party_hp"][0] = True
    assert motion.retained_field_faint_binding(rt, actions, outcome=proof) is None
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("fault", ["cash", "healing", "position", "pc", "xp", "stuck"])
def test_retained_settlement_rejects_resource_changes_and_exhaustion(monkeypatch, fault):
    rt, actions, state, proof, calls = environment(monkeypatch)
    b = motion.retained_field_faint_binding(rt, actions, outcome=proof)
    state.fault = fault
    with pytest.raises(RuntimeError):
        b.execute()
    assert b.verify(None).status is GoalDecisionOutcome.FAILED
    assert len(calls) <= 64


def test_stale_retained_binding_is_zero_input(monkeypatch):
    rt, actions, state, proof, calls = environment(monkeypatch)
    b = motion.retained_field_faint_binding(rt, actions, outcome=proof)
    state.payload = b"different"
    with pytest.raises(ValueError, match="stale"):
        b.execute()
    assert not calls


def write_parent(tmp_path, state, proof):
    (tmp_path / "terminal.state").write_bytes(state.payload)
    result = dict(state_sha256=sha256(state.payload).hexdigest(), released=True,
                  worker_stopped=True, continuation_reason="native_execution_error",
                  episode=dict(outcomes=[proof]))
    (tmp_path / "RESULT.json").write_text(json.dumps(result))
    return result


def test_configured_player_offers_one_exact_preface_before_ordinary_choices(monkeypatch, tmp_path):
    rt, actions, state, proof, calls = environment(monkeypatch)
    write_parent(tmp_path, state, proof)
    menu = NativeStoryBranchInventory(lambda *_: pytest.fail("must settle first"), lambda *_: ())
    backend = N(assembly=lambda *a, **k: (b"native", None, menu, {}, {}))
    _, _, configured, _, _ = configuration.assemble_configured_player(
        backend, config(), tmp_path, tmp_path, plan_path=tmp_path/"PLAN.json")
    inventory = configured.enumerate_base(rt, actions, object())
    assert len(inventory.bindings) == 1
    b = inventory.bindings[0]
    assert b.binding_ref == "pokemon.red:retained-motion:" + proof["terminal_state_sha256"]
    assert len(inventory.opportunities) == 2
    assert b.verify(b.execute()).status is GoalDecisionOutcome.SUCCEEDED
    assert not rt.reader.read_bottom_dialogue_box_visible()


@pytest.mark.parametrize("fault", ["other_state", "not_released", "not_stopped", "sha",
                                  "missing_result", "bad_proof"])
def test_inventory_requires_exact_retained_parent(monkeypatch, tmp_path, fault):
    rt, actions, state, proof, calls = environment(monkeypatch)
    result = write_parent(tmp_path, state, proof)
    if fault == "other_state": state.payload = b"another-state"
    if fault == "not_released": result["released"] = False
    if fault == "not_stopped": result["worker_stopped"] = False
    if fault == "sha": result["state_sha256"] = "a" * 64
    if fault == "bad_proof": result["episode"]["outcomes"][0]["before"]["input_ready"] = False
    if fault == "missing_result": (tmp_path/"RESULT.json").unlink()
    else: (tmp_path/"RESULT.json").write_text(json.dumps(result))
    assert configuration._retained_field_faint_inventory(rt, actions, parent=tmp_path) is None
    assert not calls
