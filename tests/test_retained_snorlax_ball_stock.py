import ast
from pathlib import Path
from types import SimpleNamespace as NS
from dataclasses import replace
import pytest
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_one_off_capture import OneOffCaptureBudget,OneOffCaptureRequest

SOURCE=Path(__file__).parents[1]/"runtime_helpers/red_earned_run_completion_20261005.py"

def binding(tmp_path,stock,*,committed=5,initial=5,live_ok=True):
    tree=ast.parse(SOURCE.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=="retained_capture_binding")
    receipt=tmp_path/"snorlax-original/001-paused/receipt.json";receipt.parent.mkdir(parents=True);receipt.write_text("{}")
    (tmp_path/"terminal.state").write_bytes(b"state")
    old=OneOffCaptureBudget(OneOffCaptureRequest(0x84,30,ItemId.POKE_BALL),initial,initial,committed)
    seen=[]
    def require(*a,**kw):
        if not live_ok:raise ValueError("capture continuation live state/allocation differs")
    saved=NS(state=b"state",budget=old,receipt_sha256="a"*64,maximum_status_attempts=3,preserve_viable_active=False,minimum_prepared_helper_level=None,status_preparer=lambda *a: NS(attempts=0),require_live_resume=require)
    target=NS(species_number=143,map_id=23,internal_species=0x84,level=30)
    rt=NS(reader=NS(read=lambda:NS(battle_state=1,map_id=23,enemy_level=30,bag_items=tuple(stock.items())),read_wild_capture_identity=lambda:NS(original_species_id=0x84),read_pokedex_state=lambda:NS(owned_species=frozenset())),emulator=NS(save_state_bytes=lambda:b"state"))
    def allocated(request,max_throws,initial_ball_count):
        result=OneOffCaptureBudget(request,max_throws,initial_ball_count);seen.append(result);return result
    ns=dict(route12_snorlax_target=lambda _:target,c=NS(ROM=NS(read_bytes=lambda:b"rom"),digest=lambda _:"b"*64,sha256=__import__("hashlib").sha256,GoalKind=NS(RECOVER_CONTROL="recover")),doc=lambda _:dict(origin_state_sha256="c"*64,allocation_sha256="d"*64),load_capture_checkpoint=lambda *a,**kw:saved,replace=replace,ItemId=ItemId,OneOffCaptureBudget=allocated,OneOffCaptureRequest=OneOffCaptureRequest,ExecutableGoalBinding=lambda *a,**kw:NS(args=a,kwargs=kw),_retained_capture_loss_binding=lambda *a:NS(loss=True))
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),ns)
    return lambda:ns["retained_capture_binding"](rt,object(),parent=tmp_path,output=tmp_path/"out"),seen,old

@pytest.mark.parametrize("stock,ball,count",[({3:4},ItemId.GREAT_BALL,4),({2:7},ItemId.ULTRA_BALL,7),({4:2,3:4},ItemId.POKE_BALL,2),({1:1,3:4},ItemId.GREAT_BALL,4),({1:1},ItemId.MASTER_BALL,1)])
def test_exhausted_retained_allocation_uses_carried_stock_without_erasing_prior_throws(tmp_path,stock,ball,count):
    call,seen,old=binding(tmp_path,stock);call();new=seen[0]
    assert new.request.ball is ball and new.initial_ball_count==new.max_throws==count
    assert new.throws_committed==0 and old.throws_committed==old.initial_ball_count==5

def test_true_exhaustion_still_retains_the_encounter(tmp_path):
    call,seen,old=binding(tmp_path,{40:1})
    result=call()
    assert result.loss and not seen and old.throws_committed==5

def test_unexhausted_receipt_keeps_its_original_budget(tmp_path):
    call,seen,old=binding(tmp_path,{4:3,3:4},committed=2);call()
    assert not seen and old.throws_committed==2

def test_bad_live_authentication_cannot_extend_a_budget(tmp_path):
    call,seen,old=binding(tmp_path,{3:4},live_ok=False)
    with pytest.raises(ValueError,match="allocation differs"):call()
    assert not seen and old.throws_committed==5

@pytest.mark.parametrize("stock,number,accepted",[({},143,True),({3:1},143,False),({1:1},143,False),({},144,False)])
def test_loss_bridge_only_uses_existing_exact_static_recovery_after_true_exhaustion(tmp_path,monkeypatch,stock,number,accepted):
    import hashlib
    from dataclasses import replace
    from test_red_live_option_menu import _binding
    from pokemon_red_completion.goal_manager import GoalKind,GoalFailureReason,GoalDecisionOutcome
    from pokemon_red_completion.goal_manager_runtime import GoalVerification
    import pokemon_red_completion.red_player_wild_recovery as recovery
    tree=ast.parse(SOURCE.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=="_retained_capture_loss_binding")
    calls=[];original=_binding(GoalKind.RECOVER_CONTROL,binding_ref="original",calls=[])
    monkeypatch.setattr(recovery,"interrupted_wild_binding",lambda *a,**kw:(calls.append(kw)or original))
    rt=NS(reader=NS(read=lambda:NS(bag_items=tuple(stock.items()))),emulator=NS(save_state_bytes=lambda:b"exact"));target=NS(species_number=number)
    ns=dict(ItemId=ItemId,c=NS(ROM=NS(read_bytes=lambda:b"rom"),sha256=hashlib.sha256),GoalVerification=GoalVerification,GoalFailureReason=GoalFailureReason,replace=replace)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),ns)
    if not accepted:
        with pytest.raises(ValueError,match="exhausted"):ns[fn.name](rt,object(),target)
        assert not calls
        return
    result=ns[fn.name](rt,object(),target)
    assert calls[0]["consumed_static_target"] is target and calls[0]["rom"]==b"rom"
    assert result.binding_ref=="pokemon.red:retained-capture:"+hashlib.sha256(b"exact").hexdigest()
    verdict=result.verify(result.execute())
    assert verdict.status is GoalDecisionOutcome.FAILED and verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
