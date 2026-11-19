import sys
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_player_configuration import _retained_capture_inventory


def fixture(tmp_path, monkeypatch, *, battle=1, state=b"exact", journal=True):
    (tmp_path / "terminal.state").write_bytes(b"exact")
    if journal:
        d = tmp_path / "snorlax-original/001-paused"
        d.mkdir(parents=True)
        (d / "receipt.json").write_text("{}")
    rt = NS(
        reader=NS(read=lambda: NS(battle_state=battle)), emulator=NS(save_state_bytes=lambda: state)
    )
    calls = []
    binding = _binding(
        GoalKind.RECOVER_CONTROL,
        binding_ref="pokemon.red:retained-capture:" + sha256(state).hexdigest(),
        calls=[],
    )

    def restore(runtime, actions, *, parent, output):
        calls.append((runtime, actions, parent, output))
        return binding

    module = NS(retained_capture_binding=restore)
    monkeypatch.setitem(sys.modules, "red_earned_run_completion_20261005", module)
    return rt, calls, binding, module


def test_exact_retained_journal_precedes_ordinary_escape_without_execution(tmp_path, monkeypatch):
    rt, calls, binding, _ = fixture(tmp_path, monkeypatch)
    actions = object()
    result = _retained_capture_inventory(rt, actions, parent=tmp_path, output=tmp_path / "out")
    assert result.bindings == (binding,)
    assert len(result.opportunities) == 2
    assert len(calls) == 1 and calls[0][0] is rt and calls[0][1] is actions


@pytest.mark.parametrize(
    "battle,state,journal",
    [(0, b"exact", True), (2, b"exact", True), (1, b"different", True), (1, b"exact", False)],
)
def test_unrelated_state_or_absent_journal_never_invokes_capture(
    tmp_path, monkeypatch, battle, state, journal
):
    rt, calls, _, _ = fixture(tmp_path, monkeypatch, battle=battle, state=state, journal=journal)
    assert (
        _retained_capture_inventory(rt, object(), parent=tmp_path, output=tmp_path / "out") is None
    )
    assert not calls


@pytest.mark.parametrize("fault", ["none", "kind", "reference"])
def test_capture_callback_cannot_replace_exact_retained_binding(tmp_path, monkeypatch, fault):
    rt, _, _, module = fixture(tmp_path, monkeypatch)
    binding = (
        None
        if fault == "none"
        else _binding(
            GoalKind.ACQUIRE_SPECIES if fault == "kind" else GoalKind.RECOVER_CONTROL,
            binding_ref="pokemon.red:retained-capture:"
            + ("0" * 64 if fault == "reference" else sha256(b"exact").hexdigest()),
            calls=[],
        )
    )
    module.retained_capture_binding = lambda *a, **kw: binding
    with pytest.raises(ValueError, match="exact verified binding"):
        _retained_capture_inventory(rt, object(), parent=tmp_path, output=tmp_path / "out")


def test_receipt_authentication_error_propagates_without_escape_fallback(tmp_path, monkeypatch):
    rt, _, _, module = fixture(tmp_path, monkeypatch)

    def invalid(*a, **kw):
        raise ValueError("capture allocation mismatch")

    module.retained_capture_binding = invalid
    with pytest.raises(ValueError, match="allocation mismatch"):
        _retained_capture_inventory(rt, object(), parent=tmp_path, output=tmp_path / "out")


def paired_zero_input_child(child,parent,*,fault=None):
    import json
    child.mkdir()
    state=b"different" if fault=="state" else b"exact"
    (child/"terminal.state").write_bytes(state)
    prior_bytes=(parent/"CONTEXT.json").read_bytes();prior=json.loads(prior_bytes)
    spent=dict(prior["spent"],decisions=3,seconds=2)
    if fault=="actions":spent["actions"]+=1
    context=dict(state_sha256=sha256(state).hexdigest(),spent=spent)
    payload=json.dumps(context).encode();(child/"CONTEXT.json").write_bytes(payload)
    result=dict(context_sha256=sha256(payload).hexdigest(),state_sha256=sha256(state).hexdigest(),spent=spent)
    if fault=="result":result["context_sha256"]="0"*64
    (child/"RESULT.json").write_text(json.dumps(result))
    plan=dict(actual_parent=str(parent),source_sha256=sha256(state).hexdigest(),context_sha256=sha256(prior_bytes).hexdigest(),inherited_spent=prior["spent"])
    if fault=="parent_context":plan["context_sha256"]="0"*64
    (child/"PLAN.json").write_text(json.dumps(plan))


@pytest.mark.parametrize("fault",[None,"actions","result","parent_context"])
def test_zero_input_exports_reconnect_only_authenticated_same_state_receipt_ancestry(tmp_path,monkeypatch,fault):
    import json
    parent=tmp_path/"original";parent.mkdir();rt,calls,binding,module=fixture(parent,monkeypatch)
    context=dict(state_sha256=sha256(b"exact").hexdigest(),spent=dict(actions=7,frames=120,decisions=1,seconds=1))
    (parent/"CONTEXT.json").write_text(json.dumps(context))
    first=tmp_path/"first";paired_zero_input_child(first,parent)
    child=tmp_path/"latest";paired_zero_input_child(child,first,fault=fault)
    if fault is not None:
        with pytest.raises(ValueError,match="zero-input"):_retained_capture_inventory(rt,object(),parent=child,output=tmp_path/"out")
        assert not calls
        return
    result=_retained_capture_inventory(rt,object(),parent=child,output=tmp_path/"out")
    assert result.bindings==(binding,) and len(calls)==1 and calls[0][2]==parent
    assert json.loads((child/"CONTEXT.json").read_text())["spent"]["decisions"]==3


@pytest.mark.parametrize("fault", [None,"capture","result","source","spent","terminal","unchanged"])
def test_authenticated_non_capture_work_ends_journal_search_without_reusing_old_allocation(tmp_path,monkeypatch,fault):
    import json
    parent=tmp_path/"original";parent.mkdir();rt,calls,_,_=fixture(parent,monkeypatch)
    prior=dict(state_sha256=sha256(b"exact").hexdigest(),spent=dict(actions=7,frames=120,decisions=1,seconds=1))
    (parent/"CONTEXT.json").write_text(json.dumps(prior))
    child=tmp_path/"new-native-work";paired_zero_input_child(child,parent)
    state=b"exact" if fault=="unchanged" else b"new ordinary wild"
    (child/"terminal.state").write_bytes(state)
    context=dict(state_sha256=sha256(state).hexdigest(),spent=dict(actions=8,frames=144,decisions=3,seconds=2))
    if fault=="spent":context["spent"]["frames"]=120
    payload=json.dumps(context).encode();(child/"CONTEXT.json").write_bytes(payload)
    outcome=dict(selected_kind="acquire_species" if fault=="capture" else "resupply",terminal_state_sha256=sha256(state).hexdigest())
    if fault=="terminal":outcome["terminal_state_sha256"]="0"*64
    result=dict(context_sha256=sha256(payload).hexdigest(),state_sha256=sha256(state).hexdigest(),spent=context["spent"],episode=dict(outcomes=[outcome]))
    if fault=="result":result["context_sha256"]="0"*64
    (child/"RESULT.json").write_text(json.dumps(result))
    if fault=="source":
        plan=json.loads((child/"PLAN.json").read_text());plan["source_sha256"]="0"*64;(child/"PLAN.json").write_text(json.dumps(plan))
    rt.emulator.save_state_bytes=lambda:state
    if fault:
        with pytest.raises(ValueError,match="zero-input"):_retained_capture_inventory(rt,object(),parent=child,output=tmp_path/"out")
    else:
        assert _retained_capture_inventory(rt,object(),parent=child,output=tmp_path/"out") is None
    assert not calls


@pytest.mark.parametrize("kind",["develop_team","evolve_species"])
def test_authenticated_training_work_does_not_inherit_old_capture_allocation(tmp_path,monkeypatch,kind):
    import json
    parent=tmp_path/"original";parent.mkdir();rt,calls,_,_=fixture(parent,monkeypatch)
    prior=dict(state_sha256=sha256(b"exact").hexdigest(),spent=dict(actions=7,frames=120,decisions=1,seconds=1))
    (parent/"CONTEXT.json").write_text(json.dumps(prior));child=tmp_path/"training";paired_zero_input_child(child,parent)
    state=b"new ordinary training wild";(child/"terminal.state").write_bytes(state)
    context=dict(state_sha256=sha256(state).hexdigest(),spent=dict(actions=8,frames=144,decisions=3,seconds=2));payload=json.dumps(context).encode();(child/"CONTEXT.json").write_bytes(payload)
    result=dict(context_sha256=sha256(payload).hexdigest(),state_sha256=sha256(state).hexdigest(),spent=context["spent"],episode=dict(outcomes=[dict(selected_kind=kind,terminal_state_sha256=sha256(state).hexdigest())]));(child/"RESULT.json").write_text(json.dumps(result));rt.emulator.save_state_bytes=lambda:state
    assert _retained_capture_inventory(rt,object(),parent=child,output=tmp_path/"out") is None
    assert not calls
