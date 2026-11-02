"""ROM-free authentication and existing recovery integration; no model calls."""

import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion import red_player_configuration as config
from pokemon_red_completion import red_player_wild_recovery as recovery
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalVerification


def failed_parent(tmp_path, state=b"retained-fainted-wild"):
    context = dict(state_sha256=sha256(state).hexdigest(), spent=dict(actions=102, frames=5208))
    context_bytes = json.dumps(context).encode()
    result = dict(
        config.player_lifecycle_fields(
            scope="live_chunk", released=True, guest_backend_closed=False
        ),
        state_sha256=context["state_sha256"],
        context_sha256=sha256(context_bytes).hexdigest(),
        released=True,
        spent=context["spent"],
        continuation_reason="native_execution_error",
        episode=dict(
            outcomes=[
                dict(
                    terminal_state_sha256=context["state_sha256"],
                    error_type="RouteExecutionError",
                    failure_reason=None,
                    error_chain=[
                        dict(error_type="RouteExecutionError", reason_code="world_state_diverged")
                    ],
                )
            ]
        ),
    )
    (tmp_path / "terminal.state").write_bytes(state)
    (tmp_path / "CONTEXT.json").write_bytes(context_bytes)
    (tmp_path / "RESULT.json").write_text(json.dumps(result))
    return result


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "state",
        "context",
        "spent",
        "released",
        "error",
        "terminal",
        "trainer",
        "living",
        "all_fainted",
        "unknown_active",
        "bad_chain",
    ],
)
def test_retained_fainted_tail_requires_exact_failed_checkpoint(tmp_path, monkeypatch, fault):
    state = b"retained-fainted-wild"
    result = failed_parent(tmp_path, state)
    if fault == "context":
        result["context_sha256"] = "0" * 64
    if fault == "spent":
        result["spent"] = {}
    if fault == "released":
        result["checkpoint_lifecycle"]["inputs_released"] = False
    if fault == "error":
        result["continuation_reason"] = "ordinary_setback"
    if fault == "bad_chain":
        result["episode"]["outcomes"][-1]["error_chain"][0]["reason_code"] = "other"
    if fault == "terminal":
        result["episode"]["outcomes"][-1]["terminal_state_sha256"] = "0" * 64
    (tmp_path / "RESULT.json").write_text(json.dumps(result))
    raw = N(
        battle_state=2 if fault == "trainer" else 1,
        active_party_index=None if fault == "unknown_active" else 0,
        party_hp=(
            25 if fault == "living" else 0,
            0 if fault == "all_fainted" else 42,
            60,
            66,
            42,
            36,
        ),
    )
    if fault == "all_fainted":
        raw.party_hp = (0,) * 6
    rt = N(
        reader=N(read=lambda: raw),
        emulator=N(save_state_bytes=lambda: b"wrong" if fault == "state" else state),
    )
    calls = []

    def bind(runtime, actions, **kwargs):
        calls.append((runtime, actions, kwargs))
        return replace(
            _binding(
                GoalKind.RECOVER_CONTROL,
                binding_ref="pokemon.red:interrupted-wild:" + sha256(state).hexdigest(),
                calls=[],
            ),
            verify=lambda _: GoalVerification.succeeded(),
        )

    monkeypatch.setattr(recovery, "interrupted_wild_binding", bind)
    actions = object()
    inventory = config._retained_wild_faint_inventory(
        rt, actions, parent=tmp_path, rom=b"synthetic"
    )
    assert bool(inventory) is (fault is None)
    assert len(calls) == int(fault is None)
    if inventory:
        assert calls[0] == (rt, actions, dict(rom=b"synthetic", allow_fainted_active=True))
        assert (
            len(inventory.bindings) == 1 and inventory.bindings[0].kind is GoalKind.RECOVER_CONTROL
        )


def test_public_parent_authentication_accepts_released_live_battle_checkpoint(tmp_path):
    # The unchanged public entry authenticates bytes/costs/quiescence, not field readiness.
    from run_configured_red_player import authenticate_parent

    failed_parent(tmp_path)
    assert authenticate_parent(tmp_path, lambda p: sha256(p.read_bytes()).hexdigest())[
        "spent"
    ] == dict(actions=102, frames=5208)


def test_retained_fainted_binding_crosses_actual_native_preface(tmp_path, monkeypatch):
    from test_red_native_player import setup

    from pokemon_red_completion import red_native_player as native
    from pokemon_red_completion import wild_party_flee
    from pokemon_red_completion.actions import MacroAction, MacroActionKind

    args, executed = setup(tmp_path, monkeypatch)
    args["source"] = dict(args["source"], partition="development")
    recovered = [False]
    captured = native.capture_player_lesson_snapshot

    def capture(runtime):
        observation, snapshot = captured(runtime)
        raw = observation.raw
        raw.battle_state = 0 if recovered[0] else 1
        raw.party_hp = (0, 42, 60, 66, 42, 36)
        raw.active_party_index = 0
        raw.map_id = 197
        raw.player_money = 446
        raw.bag_items = ((4, 3),)
        raw.event_flags = b"unchanged-events"
        raw.badge_bits = 3
        observation.input_ready = recovered[0]
        snapshot["in_battle"] = not recovered[0]
        return observation, snapshot

    monkeypatch.setattr(native, "capture_player_lesson_snapshot", capture)
    monkeypatch.setattr(recovery, "retained_native_static_target", lambda *_: None)
    factory = args["runtime_factory"]

    def runtime_factory(controller):
        rt = factory(controller)
        rt.reader.read = lambda: capture(rt)[0].raw
        rt.reader.read_input_readiness = lambda: N(ready=recovered[0])
        rt.reader.read_bottom_dialogue_box_visible = lambda: False
        return rt

    args["runtime_factory"] = runtime_factory
    parent = tmp_path / "failed-parent"
    parent.mkdir()
    failed_parent(parent, args["emulator"].save_state_bytes())

    def escape(actions, reader, before, **kwargs):
        assert before.party_hp == (0, 42, 60, 66, 42, 36)
        assert kwargs["emulator"].save_state_bytes() == (parent / "terminal.state").read_bytes()
        assert kwargs["allow_new_faints"] and kwargs["allow_status_changes"]
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
        recovered[0] = True
        return N(verified=True, public_dict=lambda: dict(verified=True, hp_scope="whole_party"))

    monkeypatch.setattr(wild_party_flee, "flee_with_fainted_lead", escape)
    monkeypatch.setattr(recovery, "_field_ready", lambda _: recovered[0])
    args["enumerate_bindings"] = lambda rt, actions, observation: (
        config._retained_wild_faint_inventory(rt, actions, parent=parent, rom=b"synthetic")
    )
    args["settle_existing_wild"] = True
    args["limits"] = replace(args["limits"], actions=1, decisions=2)
    result = native.run_native_continuous_player(**args)
    assert recovered[0] and not executed
    assert result["supplied_wild_escape_preface"]["learned"] is False
    assert result["supplied_wild_escape_preface"]["actions"] == 1
    assert result["supplied_wild_escape_preface"]["frames"] == 2
    intent = json.loads((args["output"] / "wild-escape-preface/intent.json").read_bytes())
    assert intent["model_queries"] == 0 and not intent["comparative_choice"]
