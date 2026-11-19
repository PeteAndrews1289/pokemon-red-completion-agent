import json,hashlib
from dataclasses import replace
import pytest
from test_red_trainer_proposed_control import setup_case
from pokemon_red_completion import red_observed_component_binding as b
from pokemon_red_completion.red_trainer_proposed_control import expand_observed_effect_control,expand_observed_component_control
from pokemon_red_completion.red_trainer_practice_features import expand_observed_pp_switch

def test_absent_binding_preserves_default(tmp_path):
    p=tmp_path/'not-read.json';assert b.load_observed_league_components(b'{}',p,'old')==(p,'old')

def test_explicit_binding_checks_receipt_schemas_and_old_weights(tmp_path,monkeypatch):
    _,_,parent=setup_case()
    def save(name,doc):
        p=tmp_path/name;p.write_text(json.dumps(doc));return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    pr=save('parent.json',parent.to_dict());monkeypatch.setattr(b,'PARENT_DIGEST',pr['sha256'])
    candidate=replace(parent,control=expand_observed_component_control(expand_observed_effect_control(parent.control)),switch=expand_observed_pp_switch(parent.switch));cr=save('candidate.json',candidate.to_dict());rr=save('fit.json',dict(passed=True,no_DEV_fit=True,only_new_input_rows_updated=True,old_parameters_bit_identical=True,candidate=cr,original_parent=pr));decl=dict(mode='observed_components_v3',model=cr,fit_receipt=rr)
    def call():return b.load_observed_league_components(json.dumps(dict(partition='development',observed_league_components=decl)).encode(),pr['path'],pr['sha256'])
    assert call()==(__import__('pathlib').Path(cr['path']),cr['sha256'])
    changed=candidate.to_dict();changed['switch']['weights1'][0][0]+=1;cr2=save('changed.json',changed);decl['model']=cr2;rr2=save('fit2.json',dict(passed=True,no_DEV_fit=True,only_new_input_rows_updated=True,old_parameters_bit_identical=True,candidate=cr2,original_parent=pr));decl['fit_receipt']=rr2
    with pytest.raises(ValueError,match='input weights'):call()
    decl['fit_receipt']['sha256']='0'*64
    with pytest.raises(ValueError,match='digest'):call()

def test_normal_wiring_retains_opt_in_after_json_chunk_round_trip():
    import run_configured_red_player as runner
    declaration=dict(mode='observed_components_v3',model=dict(path='/p/model.json',sha256='a'*64),fit_receipt=dict(path='/p/fit.json',sha256='b'*64))
    plan=dict(partition='development',observed_league_components=declaration)
    first=runner.player_wiring_declaration(plan)
    second=runner.player_wiring_declaration(json.loads(json.dumps(dict(partition='development',**first))))
    assert first['observed_league_components']==second['observed_league_components']==declaration
    assert 'observed_league_components'not in runner.player_wiring_declaration(dict(partition='development'))
    with pytest.raises(ValueError):runner.player_wiring_declaration(dict(partition='train',observed_league_components=declaration))

@pytest.mark.parametrize('selected_model_sha256',['111ef28dd505a61c6c8b3c0c7521d0d395119afba6f3b0e090a86095a03a4ad2','a'*64])
def test_canonical_income_guard_uses_same_selected_model_reference(tmp_path,monkeypatch,selected_model_sha256):
    import ast
    from pathlib import Path
    from types import SimpleNamespace as N
    import pokemon_red_completion.red_player_model as goals
    source=Path(__file__).resolve().parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py'
    node=next(n for n in ast.walk(ast.parse(source.read_text()))if isinstance(n,ast.FunctionDef)and n.name=='configure_income_reuse')
    model=tmp_path/'goal.json';model.write_bytes(b'{}');declared=tmp_path/'PLAN.json';declared.write_text(json.dumps(dict(partition='development',goal_model_record=dict(path=str(model),content_sha256=hashlib.sha256(model.read_bytes()).hexdigest()))))
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    monkeypatch.setattr(goals,'load_player_goal_model_record_bytes',lambda *a,**k:N(model='goal'))
    namespace=dict(json=json,Path=Path,c=N(sha256=hashlib.sha256,digest=digest),declared=declared,learned_league_components=lambda:(tmp_path/'selected-model.json',selected_model_sha256),declared_income_goal_model_sha256=lambda _: 'b'*64,bind_income_runtime=lambda *a:None,holder=dict(observe_history=lambda:None),production_train_scope=None,declared_conserved_income_support=lambda _:False,snorlax_capture_loan=None,output=tmp_path)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
    controller=N();namespace['configure_income_reuse'](controller)
    assert controller.income_reuse.model_sha256==selected_model_sha256
    assert controller.income_reuse.work_order_sha256==digest(declared)
