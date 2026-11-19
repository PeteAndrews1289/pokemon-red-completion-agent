"""Paid-loop witness conserves all scores, menus and old contracts."""
import copy
from dataclasses import replace
import pytest
from test_red_movement_recurrence import facts
from test_red_integrated_play import _facts, _report
from test_stable_sequence_selection import fixture, choose
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.goal_manager_runtime import GoalVerification, GoalFailureReason
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_costly_search_recurrence import cashless_progress, witnesses, record_failure
from pokemon_red_completion.player_sequence_policy import SequencePolicy, SequenceChoiceContext
from pokemon_red_completion.red_live_option_menu import _recurrence_escape, RedLiveOptionSelectionMode as Mode
SRC="pokemon.red:paid-safari:test"
OBJ="d"*64
CTX=dict(binding_ref="test", source_ref=SRC, objective_sha256=OBJ)


def remembered():
    f=facts();f["cash"]=5000
    m=GoalSearchMemory()
    for cash in (4500,4000):
        m.record_costly_search_failure(SRC,OBJ,cashless_progress(f),cash)
    return m,f


@pytest.mark.parametrize("cash,expected",[(4000,True),(3500,True),(4001,False),(5000,False)])
def test_cash_fee_never_creates_novelty_but_cash_above_recorded_floor_does(cash,expected):
    m,f=remembered();f["cash"]=cash
    assert witnesses([CTX],m,f)==(expected,)


@pytest.mark.parametrize("change",["xp","hp","pp","party","event","item","registration","objective","coins","unknown"])
def test_progress_and_unknown_cannot_trigger(change):
    m,f=remembered();f["cash"]=4000
    if change=="xp":f["player_lesson"]["party"][0]["experience"]+=1
    elif change=="hp":f["player_lesson"]["party"][0]["hp"]+=1
    elif change=="pp":f["player_lesson"]["party"][0]["moves"][0][1]-=1
    elif change=="party":f["player_lesson"]["party"][0]["specimen_ref"]="different"
    elif change=="event":f["movement_event_flags"]="0101"
    elif change=="item":f["diagnostics"]["bag_items"]=[[4,3]]
    elif change=="registration":f["owned_species"].append("new")
    elif change=="objective":f["completed_objectives"].append("reward")
    elif change=="coins":f["movement_coins"]+=1
    else:f.pop("movement_event_flags")
    assert witnesses([CTX],m,f)==((None,) if change=="unknown" else (False,))


def test_two_executed_certified_failures_required_and_full_old_memory_roundtrip():
    m=GoalSearchMemory();f=facts();progress=cashless_progress(f)
    assert "costly_search_failures" not in m.private_dict()
    assert not m.costly_search_seen(SRC,OBJ,progress,100)
    m.record_costly_search_failure(SRC,OBJ,progress,100)
    assert not m.costly_search_seen(SRC,OBJ,progress,100)
    prior=GoalSearchMemory.from_private_dict(m.private_dict())
    m.record_costly_search_failure(SRC,OBJ,progress,0)
    assert m.costly_search_seen(SRC,OBJ,progress,0)
    m.require_extension(prior)
    restored=GoalSearchMemory.from_private_dict(m.private_dict())
    assert restored.private_dict()==m.private_dict()
    with pytest.raises(ValueError):prior.require_extension(restored)
    forged=m.private_dict();next(iter(forged["costly_search_failures"].values()))[1]=1
    with pytest.raises(ValueError):GoalSearchMemory.from_private_dict(forged).require_extension(restored)


@pytest.mark.parametrize("value",[[],[0,0],[True,0],[1,True],[1,-1],[1,1000000],[1,0,2],"bad"])
def test_malformed_memory_rejected(value):
    m,f=remembered();d=m.private_dict();d["costly_search_failures"][next(iter(d["costly_search_failures"]))]=value
    with pytest.raises(ValueError):GoalSearchMemory.from_private_dict(d)


@pytest.mark.parametrize("fault",[None,"capture","cash","unknown","event","xp","error","unsafe","departure"])
def test_only_complete_paid_no_payoff_execution_records(fault):
    before_f=dict(facts(),**_facts());after_f=copy.deepcopy(before_f)
    after_f.update(_facts(1))
    before=AutonomousSnapshot(b"before",before_f,True)
    after=AutonomousSnapshot(b"after",after_f,fault!="unsafe")
    report=_report();error=None
    if fault=="capture":report=replace(report,evidence={**report.evidence,"captures":1})
    elif fault=="cash":after_f["cash"]+=1
    elif fault=="unknown":after_f.pop("movement_event_flags")
    elif fault=="event":after_f["movement_event_flags"]="0101"
    elif fault=="xp":after_f["player_lesson"]["party"][0]["experience"]+=1
    elif fault=="error":error=RuntimeError("failed")
    elif fault=="departure":report=replace(report,evidence={**report.evidence,"paid_session_departure":{}})
    m=GoalSearchMemory()
    passed=record_failure(m,CTX,before,after,report,
                         GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED),error)
    assert passed is (fault is None)
    assert ("costly_search_failures" in m.private_dict()) is (fault is None)


@pytest.mark.parametrize("seen",[False,True])
def test_new_identity_old_weights_exact_scores_and_full_sampler(seen):
    model,options,old,ctx=fixture(seen=False,mode="stable")
    new=replace(old,selection_mode="stable_costly_recurrence")
    flags=tuple(seen for _ in options.bindings)
    newctx=replace(ctx,costly_search_witnesses=flags)
    stable=choose(model,options,old,ctx)
    choice=choose(model,options,new,newctx)
    assert new.model_sha256!=old.model_sha256 and new.head==old.head
    assert new.document()["schema"]=="pokemon.player.sequence-policy.v4"
    assert SequencePolicy.from_document(new.document(),expected_sha256=new.model_sha256)==new
    assert SequenceChoiceContext.from_document(newctx.document())==newctx
    assert choice.scores==stable.scores and choice.options is options
    assert choice.mode is (Mode.MODEL_EXPLORATION if seen else Mode.MODEL_GREEDY)
    if seen:
        sampled=choose(model,options,replace(old,selection_mode="sample"),ctx)
        assert choice.probabilities==sampled.probabilities
        assert choice.selected_candidate_index==sampled.selected_candidate_index
        assert all(choice.probabilities[i]>0 for i in options.menu.available_indices)
    else:
        assert choice.selected_candidate_index==stable.selected_candidate_index
        assert choice.probabilities==stable.probabilities


@pytest.mark.parametrize("second",[True,False,None])
def test_every_tied_maximum_needs_witness(second):
    from types import SimpleNamespace
    model,options,old,ctx=fixture(seen=False,mode="stable")
    policy=replace(old,selection_mode="stable_costly_recurrence")
    scores=tuple(1.0 for _ in options.bindings)
    flags=(True,)+(second,)*(len(options.bindings)-1)
    assert _recurrence_escape(options,scores,policy,replace(ctx,costly_search_witnesses=flags)) is (second is True)


def test_witness_cannot_be_silently_applied_to_old_mode_or_omitted_for_new_mode():
    model,options,old,ctx=fixture(mode="stable")
    for policy,context in [(old,replace(ctx,costly_search_witnesses=(False,)*len(options.bindings))),
                           (replace(old,selection_mode="stable_costly_recurrence"),ctx)]:
        with pytest.raises(ValueError):choose(model,options,policy,context)


@pytest.mark.parametrize("fault",[None,"missing_session","unknown_session","in_session","game_over","unknown_party","capture"])
def test_current_native_layout_requires_actual_session_and_known_physical_facts(fault):
    before=dict(facts(),actions=0,completed_actions=0,frames=0,cash=5000,
                battle_state=0,input_ready=True,buttons_released=True,
                costly_search_session=dict(in_safari_zone=False,safari_game_over=False,
                                           safari_balls=30,safari_steps=0))
    after=copy.deepcopy(before);after.update(actions=1,completed_actions=1,frames=10,cash=4500)
    report=_report()
    if fault=="missing_session":after.pop("costly_search_session")
    elif fault=="unknown_session":after["costly_search_session"]["in_safari_zone"]=None
    elif fault=="in_session":after["costly_search_session"]["in_safari_zone"]=True
    elif fault=="game_over":after["costly_search_session"]["safari_game_over"]=True
    elif fault=="unknown_party":after["player_lesson"]["party"][0].pop("experience")
    elif fault=="capture":report=replace(report,evidence={**report.evidence,"captures":1})
    m=GoalSearchMemory()
    assert record_failure(m,CTX,AutonomousSnapshot(b"a",before,True),AutonomousSnapshot(b"b",after,True),
                          report,GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED),None) is (fault is None)
    assert bool(m.private_dict().get("costly_search_failures")) is (fault is None)


def test_explicit_search_target_does_not_eagerly_require_fallback_registration_context():
    from types import SimpleNamespace
    from test_red_integrated_play import _paid_binding
    from pokemon_red_completion.red_costly_search_recurrence import search_contexts
    binding=replace(_paid_binding(),search_objective_sha256=OBJ)
    contexts=search_contexts(SimpleNamespace(bindings=(binding,)),{})
    assert contexts[0]["objective_sha256"]==OBJ
    assert witnesses(contexts,GoalSearchMemory(),{})==(None,)
