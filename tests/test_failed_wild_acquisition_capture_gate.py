"""Typed ordinary acquisition tails never reuse an older capture allocation."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace as N
import json
import sys

import pytest
from test_red_live_option_menu import _binding
from pokemon_red_completion import red_player_configuration as configuration
from pokemon_red_completion.goal_manager import GoalKind


def publish(tmp_path, monkeypatch, fault=None):
    prior=tmp_path/"prior";prior.mkdir()
    prior_state=b"old allocated capture"
    prior_context=dict(state_sha256=sha256(prior_state).hexdigest(),
                       spent=dict(actions=7,frames=120,decisions=1,seconds=1))
    prior_bytes=json.dumps(prior_context).encode()
    (prior/"terminal.state").write_bytes(prior_state)
    (prior/"CONTEXT.json").write_bytes(prior_bytes)
    old_receipt=prior/"snorlax-old/001-paused";old_receipt.mkdir(parents=True)
    (old_receipt/"receipt.json").write_text("{}")
    parent=tmp_path/"ordinary-work";parent.mkdir()
    state=b"changed ordinary wild after RUN KO"
    context=dict(state_sha256=sha256(state).hexdigest(),
                 spent=dict(actions=222,frames=12840,decisions=12,seconds=4))
    if fault=="frames":context["spent"]["frames"]=120
    context_bytes=json.dumps(context).encode()
    (parent/"terminal.state").write_bytes(state)
    (parent/"CONTEXT.json").write_bytes(context_bytes)
    outcome=dict(selected_kind="acquire_species",terminal_state_sha256=sha256(state).hexdigest(),
                 error_type="RouteExecutionError",
                 error_chain=[dict(error_type="RouteExecutionError",reason_code="world_state_diverged")])
    if fault=="successful_capture":
        outcome.update(error_type=None,error_chain=[],verification="succeeded")
    if fault=="paused_capture":outcome["error_type"]="OneOffCapturePaused"
    if fault=="chain":outcome["error_chain"][0]["reason_code"]="other"
    if fault=="terminal":outcome["terminal_state_sha256"]="0"*64
    result=dict(released=True,**configuration.player_lifecycle_fields(
                    scope="live_chunk",released=True,guest_backend_closed=False),
                state_sha256=context["state_sha256"],context_sha256=sha256(context_bytes).hexdigest(),
                spent=context["spent"],continuation_reason="native_execution_error",
                episode=dict(outcomes=[outcome]))
    if fault=="result":result["context_sha256"]="0"*64
    if fault=="unreleased":result["checkpoint_lifecycle"]["inputs_released"]=False
    plan=dict(partition="train" if fault=="partition" else "development",
              actual_parent=str(prior),source_sha256=prior_context["state_sha256"],
              context_sha256=sha256(prior_bytes).hexdigest(),inherited_spent=prior_context["spent"])
    if fault=="source":plan["source_sha256"]="0"*64
    if fault=="prior_context":plan["context_sha256"]="0"*64
    (parent/"RESULT.json").write_text(json.dumps(result))
    (parent/"PLAN.json").write_text(json.dumps(plan))
    raw=N(battle_state=1,active_party_index=None if fault=="unknown_active" else 0,
          party_hp=(25,40)if fault=="living"else(0,0)if fault=="blackout"else(0,40))
    original = 132 if fault in {"snorlax_missing", "transformed_snorlax"} else 73 if fault=="legend" else None if fault=="unknown_identity" else 116
    raw.map_id=23 if fault in {"snorlax_missing", "transformed_snorlax"} else 228
    raw.enemy_species_id=166 if fault=="transformed_snorlax" else original
    runtime=N(reader=N(read=lambda:raw,read_retained_wild_identity=lambda: (
        None if original is None else N(original_species_id=original))),
        emulator=N(save_state_bytes=lambda:state))
    calls=[]
    def restore(*args,**kwargs):
        calls.append(kwargs)
        return _binding(GoalKind.RECOVER_CONTROL,
            binding_ref="pokemon.red:retained-capture:"+sha256(state).hexdigest(),calls=[])
    monkeypatch.setitem(sys.modules,"red_earned_run_completion_20261005",
                        N(retained_capture_binding=restore))
    return parent,runtime,calls,result,raw


def test_authenticated_failed_ordinary_acquire_stops_before_old_capture_allocation(tmp_path,monkeypatch):
    parent,runtime,calls,_,_=publish(tmp_path,monkeypatch)
    before=(parent/"CONTEXT.json").read_bytes()
    assert configuration._retained_capture_inventory(runtime,object(),parent=parent,
                                                       output=tmp_path/"out")is None
    assert not calls and(parent/"CONTEXT.json").read_bytes()==before


@pytest.mark.parametrize("fault",["successful_capture","paused_capture","chain","terminal",
    "result","unreleased","partition","source","prior_context","frames","unknown_active","living","blackout",
    "snorlax_missing","transformed_snorlax","legend","unknown_identity"])
def test_applicability_never_waives_capture_types_live_scope_or_ancestry(tmp_path,monkeypatch,fault):
    parent,runtime,calls,_,_=publish(tmp_path,monkeypatch,fault)
    with pytest.raises(ValueError,match="zero-input"):
        configuration._retained_capture_inventory(runtime,object(),parent=parent,output=tmp_path/"out")
    assert not calls


@pytest.mark.parametrize("invalid",[False,True])
def test_current_receipt_keeps_precedence_and_invalid_allocation_never_falls_back(tmp_path,monkeypatch,invalid):
    parent,runtime,calls,_,_=publish(tmp_path,monkeypatch,"snorlax_missing")
    receipt=parent/"static-current/001-paused";receipt.mkdir(parents=True)
    (receipt/"receipt.json").write_text("{}")
    if invalid:
        def fail(*args,**kwargs):raise ValueError("current capture allocation mismatch")
        monkeypatch.setitem(sys.modules,"red_earned_run_completion_20261005",
                            N(retained_capture_binding=fail))
        with pytest.raises(ValueError,match="allocation mismatch"):
            configuration._retained_capture_inventory(runtime,object(),parent=parent,output=tmp_path/"out")
    else:
        inventory=configuration._retained_capture_inventory(runtime,object(),parent=parent,output=tmp_path/"out")
        assert len(inventory.bindings)==1 and calls[0]["parent"]==parent
        assert inventory.bindings[0].kind is GoalKind.RECOVER_CONTROL


def test_typed_predicate_does_not_itself_authorize_static_or_ordinary_escape(tmp_path,monkeypatch):
    from pokemon_red_completion import red_player_wild_recovery as recovery
    parent,runtime,calls,_,_=publish(tmp_path,monkeypatch)
    assert configuration._retained_capture_inventory(runtime,object(),parent=parent,output=tmp_path/"out")is None
    seen=[]
    def denied(*args,**kwargs):
        seen.append(kwargs)
        raise ValueError("native one-off needs its retained capture allocation")
    monkeypatch.setattr(recovery,"interrupted_wild_binding",denied)
    with pytest.raises(ValueError,match="one-off"):
        configuration._retained_wild_faint_inventory(runtime,object(),parent=parent,rom=b"fixture")
    assert seen==[dict(rom=b"fixture",allow_fainted_active=True)]and not calls

@pytest.mark.parametrize("original",[73,74,75,131,132,None,True,0,255,"116"])
def test_all_one_off_originals_and_unknown_identity_types_fail_closed(tmp_path,monkeypatch,original):
    parent,runtime,calls,_,_=publish(tmp_path,monkeypatch)
    runtime.reader.read_retained_wild_identity=lambda:N(original_species_id=original)
    with pytest.raises(ValueError,match="zero-input"):
        configuration._retained_capture_inventory(runtime,object(),parent=parent,output=tmp_path/"out")
    assert not calls
