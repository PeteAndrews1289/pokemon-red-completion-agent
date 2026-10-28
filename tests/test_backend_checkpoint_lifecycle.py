"""Actual inherited history function, with real retained files and no emulator."""
import ast,json
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion.red_player_configuration import player_lifecycle_fields

def function(source):
 tree=ast.parse(Path(source).read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='retained_gym_switch_history')
 namespace=dict(d=N(prior=N(doc=lambda p:json.loads(p.read_bytes()))),c=N(digest=lambda p:sha256(p.read_bytes()).hexdigest()))
 exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
 return namespace['retained_gym_switch_history']

def source_files(tmp_path):
 ancestor=tmp_path/'ancestor';parent=tmp_path/'parent';ancestor.mkdir();parent.mkdir()
 (ancestor/'PLAN.json').write_text('{}');(ancestor/'terminal.state').write_bytes(b'ancestor')
 (parent/'PLAN.json').write_text(json.dumps(dict(actual_parent=str(ancestor),source_sha256=sha256(b'ancestor').hexdigest())))
 (parent/'terminal.state').write_bytes(b'child')
 result=dict(state_sha256=sha256(b'child').hexdigest(),released=True,**player_lifecycle_fields(scope='live_chunk',released=True,guest_backend_closed=False))
 (parent/'RESULT.json').write_text(json.dumps(result))
 return parent,ancestor,result

def candidate_source():
 # The qualified test runner exports exact staged source path; after root
 # integration this defaults to the current active helper without private paths.
 import os
 return Path(os.environ['LIFECYCLE_TEST_BACKEND_SOURCE']) if 'LIFECYCLE_TEST_BACKEND_SOURCE' in os.environ else Path(__file__).resolve().parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py'

def test_actual_backend_history_accepts_same_live_chunk(tmp_path):
 parent,ancestor,result=source_files(tmp_path)
 assert result['worker_stopped'] is False
 assert function(candidate_source())(parent)==[]

@pytest.mark.parametrize('fault',['held','incomplete','child_hash','ancestor_hash'])
def test_actual_backend_history_preserves_input_and_ancestry_guards(tmp_path,fault):
 parent,ancestor,result=source_files(tmp_path)
 if fault=='held':result['released']=False
 if fault=='incomplete':result['checkpoint_lifecycle']['chunk_complete']=False
 if fault=='child_hash':(parent/'terminal.state').write_bytes(b'changed-child')
 if fault=='ancestor_hash':(ancestor/'terminal.state').write_bytes(b'changed-ancestor')
 (parent/'RESULT.json').write_text(json.dumps(result))
 with pytest.raises(AssertionError):function(candidate_source())(parent)

def test_actual_backend_history_keeps_legacy_receipts_readable(tmp_path):
 parent,ancestor,result=source_files(tmp_path);result=dict(released=True,worker_stopped=True,state_sha256=result['state_sha256'])
 (parent/'RESULT.json').write_text(json.dumps(result))
 assert function(candidate_source())(parent)==[]
