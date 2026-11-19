"""Authenticated workorder absence means unchanged native seconds, never ROOT seconds."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json,pytest
from pokemon_red_completion.red_sequence_native_audit import actor_admission_seconds
def bind(tmp_path,document,native):
 path=tmp_path/'work-order.json';path.write_text(json.dumps(document,sort_keys=True,indent=2)+'\n');plan=deepcopy(native);plan['source']['experiment_sha256']=sha256(path.read_bytes()).hexdigest();return path,plan
@pytest.mark.parametrize('ROOT',[170,250])
def test_absent_field_uses_exact_native_window_not_ROOT(tmp_path,ROOT):
 native={'source':{},'limits':dict(seconds=300,actions=12000,frames=1200000,decisions=12,heals=16,cash_debits=3000)};doc=dict(native_limits=deepcopy(native['limits']),ROOT_seconds=ROOT);path,plan=bind(tmp_path,doc,native)
 assert actor_admission_seconds(plan,SimpleNamespace(seconds=300),path)==300
@pytest.mark.parametrize('field',['seconds','actions','frames','decisions','heals','cash_debits'])
def test_any_changed_native_limit_still_rejects_after_raw_repin(tmp_path,field):
 native={'source':{},'limits':dict(seconds=300,actions=12000,frames=1200000,decisions=12,heals=16,cash_debits=3000)};doc=dict(native_limits=deepcopy(native['limits']),ROOT_seconds=170);doc['native_limits'][field]+=1;path,plan=bind(tmp_path,doc,native)
 with pytest.raises(ValueError,match='hard limits'):actor_admission_seconds(plan,SimpleNamespace(seconds=300),path)
@pytest.mark.parametrize('value',[None,True,False,0,-1,301,float('nan'),float('inf'),'300'])
def test_explicit_invalid_is_not_absence(tmp_path,value):
 native={'source':{},'limits':dict(seconds=300)};path,plan=bind(tmp_path,dict(native_limits=dict(seconds=300),admission_seconds=value,ROOT_seconds=170),native)
 with pytest.raises(ValueError,match='hard limits'):actor_admission_seconds(plan,SimpleNamespace(seconds=300),path)
def test_explicit_shorter_window_and_raw_digest_stay_enforced(tmp_path):
 native={'source':{},'limits':dict(seconds=300)};path,plan=bind(tmp_path,dict(native_limits=dict(seconds=300),admission_seconds=120,ROOT_seconds=250),native);assert actor_admission_seconds(plan,SimpleNamespace(seconds=300),path)==120
 path.write_text(path.read_text().replace('250','170'))
 with pytest.raises(ValueError,match='sealed experiment'):actor_admission_seconds(plan,SimpleNamespace(seconds=300),path)
