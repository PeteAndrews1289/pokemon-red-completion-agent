from types import SimpleNamespace as N
from dataclasses import replace
from hashlib import sha256
import copy
import pytest

from pokemon_red_completion.red_story_field_recovery import NativeFieldFaintStop, certify_story_field_recovery
from pokemon_red_completion.red_routed_recovery import SettledNativeFieldRecovery
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.goal_manager import GoalKind, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from test_red_live_option_menu import _binding


def fixture():
    actions=N(actions_executed=0);emu=N(frame_count=0,save_state_bytes=lambda:b"source")
    raw=N(player_money=100,party_hp=(20,0))
    def handle(_):
        actions.actions_executed+=2;emu.frame_count+=32
        emu.save_state_bytes=lambda:b"terminal"
        return N(details=dict(native_field_faint=True,verified=True,new_fainted_slots=[2]))
    inner=N(handle=handle,handled_interruption_kinds=frozenset({"scripted_dialogue"}))
    return NativeFieldFaintStop(inner,actions,N(read=lambda:raw),emu),raw


def test_only_strict_verified_faint_stops_and_retains_actual_meter():
    handler,_=fixture()
    assert handler.handled_interruption_kinds==frozenset({"scripted_dialogue"})
    with pytest.raises(SettledNativeFieldRecovery) as err: handler.handle(None)
    e=err.value.report.evidence
    assert e["actions"]==2 and e["frames"]==32 and e["new_fainted_slots"]==[2]
    assert e["terminal_sha256"]==sha256(b"terminal").hexdigest()


@pytest.mark.parametrize("kind",["wild_battle","scripted_dialogue"])
def test_other_verified_interruptions_are_not_converted_to_faints(kind):
    h,_=fixture(); receipt=N(kind=kind,details=dict(verified=True))
    h.inner.handle=lambda _:receipt
    assert h.handle(None) is receipt


def test_unknown_failure_is_never_normalized():
    h,_=fixture()
    def fail(_): raise RuntimeError("unknown")
    h.inner.handle=fail
    with pytest.raises(RuntimeError,match="unknown"): h.handle(None)


@pytest.mark.parametrize("fault",[None,"unverified","no_cost","unknown_slots","cash"])
def test_faint_proof_fails_closed(fault):
    h,r=fixture();original=h.inner.handle
    def handle(x):
        receipt=original(x)
        if fault=="unverified":receipt.details["verified"]=False
        if fault=="no_cost":h.actions.actions_executed=0
        if fault=="unknown_slots":receipt.details["new_fainted_slots"]=[1]
        if fault=="cash":r.player_money-=1
        return receipt
    h.inner.handle=handle
    with pytest.raises(SettledNativeFieldRecovery if fault is None else RuntimeError):h.handle(None)


@pytest.mark.parametrize("fault",[None,"source","terminal","objective","kind","custody","cash","owned","completed","cost","partial","unknown_error","reason","hp"])
def test_failed_story_route_requires_exact_boundary_custody_and_no_success(fault):
    from test_red_integrated_play import _facts
    h,r=fixture()
    with pytest.raises(SettledNativeFieldRecovery) as err:h.handle(None)
    cert=dict(err.value.report.evidence)
    # The native producer separately checks all protected raw fields.
    raw=N(**{k:() for k in ["bag_items","event_flags","party_species_ids","party_levels","party_max_hp","party_stats","party_pp","party_moves"]},
          player_money=100,badge_bits=31,party_count=2,party_hp=(20,0))
    evidence=certify_story_field_recovery(err.value,raw,raw,b"before",b"terminal","reach_cinnabar")
    facts=_facts();facts.update(cash=100,completed_objectives=["obtain_surf"],
         retained_party_continuation={"native_identity_verified":True,"individuals":{"one":{"species_ref":"pokemon:national:009","level":39,"experience":53386}}})
    after=copy.deepcopy(facts);after.update(actions=2,completed_actions=2,frames=32,diagnostics={"party_hp":[20,0]})
    before=AutonomousSnapshot(b"before",facts,True)
    binding=replace(_binding(GoalKind.ADVANCE_STORY,binding_ref="pokemon.red:story-travel:abc",calls=[]),story_objective_ref="reach_cinnabar")
    reason=GoalFailureReason.RECOVERY_REQUIRED;error=None
    if fault in {"source","terminal"}:evidence[fault+"_sha256"]="0"*64
    if fault=="objective":evidence["objective_completed"]=True
    if fault=="kind":binding=replace(binding,kind=GoalKind.ACQUIRE_SPECIES,story_objective_ref=None)
    if fault=="custody":after["retained_party_continuation"]["individuals"]["one"]["experience"]+=1
    if fault=="cash":after["cash"]-=1
    if fault=="owned":after["owned_species"]=[]
    if fault=="completed":after["completed_objectives"]=[]
    if fault=="cost":after["frames"]=31
    if fault=="partial":after["completed_actions"]=1
    if fault=="unknown_error":error=RuntimeError("unknown")
    if fault=="reason":reason=GoalFailureReason.OUTCOME_NOT_VERIFIED
    if fault=="hp":after["diagnostics"]["party_hp"]=[20,1]
    terminal=AutonomousSnapshot(b"terminal",after,True)
    report=GoalExecutionReport(2,32,evidence)
    assert ordinary_player_setback(binding,before,terminal,report,GoalVerification.failed(reason),error) is (fault is None)
