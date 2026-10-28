"""A guest-closed receipt is not a host process exit proof."""
import json
import pytest
from pokemon_red_completion.red_run_spectator import RedRunReader
from test_red_run_spectator import run,write

def explicit(run,*,life=None):
 p=run/'RESULT.json';row=json.loads(p.read_text())
 row['checkpoint_lifecycle']=life if life is not None else dict(
  schema='pokemon.red.checkpoint-quiescence.v1',scope='driver_terminal',
  chunk_complete=True,inputs_released=True,guest_backend_closed=True,
  host_process_exit_confirmed=False)
 write(p,row)
 return row

@pytest.mark.parametrize('probe_active',[False,True])
def test_guest_closed_requires_external_exit_and_always_probes(run,probe_active):
 explicit(run);(run/'PROCESS-EXIT.json').unlink();calls=[]
 def probe(launch,root):calls.append((launch,root));return probe_active
 snapshot,meta=RedRunReader(run,process_probe=probe).read()
 assert len(calls)==1
 assert snapshot.run_status==('running' if probe_active else 'waiting')
 assert meta['lifecycle']==('running' if probe_active else 'not_connected')

def test_external_exit_with_matching_live_process_stays_running(run):
 explicit(run);calls=[]
 snapshot,meta=RedRunReader(run,process_probe=lambda *a:(calls.append(a) or True)).read()
 assert len(calls)==1 and snapshot.run_status=='running' and meta['lifecycle']=='running'

def test_external_exit_and_inactive_process_close_new_receipt(run):
 explicit(run);before={p:p.read_bytes() for p in run.rglob('*') if p.is_file()};calls=[]
 snapshot,meta=RedRunReader(run,process_probe=lambda *a:(calls.append(a) or False)).read()
 assert len(calls)==1 and snapshot.run_status=='failed' and meta['lifecycle']=='stopped'
 assert before=={p:p.read_bytes() for p in run.rglob('*') if p.is_file()}

@pytest.mark.parametrize('life',[{'host_process_exit_confirmed':True},True,{},'host exited'])
def test_in_process_exit_claim_or_malformed_lifecycle_never_becomes_external_proof(run,life):
 explicit(run,life=life);(run/'PROCESS-EXIT.json').unlink()
 snapshot,meta=RedRunReader(run,process_probe=lambda *a:False).read()
 assert snapshot.run_status=='waiting' and meta['lifecycle']=='not_connected'

@pytest.mark.parametrize('exit_claim',[1,'true',False,None])
def test_new_receipt_requires_exact_external_boolean(run,exit_claim):
 explicit(run);write(run/'PROCESS-EXIT.json',dict(worker_exit_confirmed=exit_claim))
 snapshot,meta=RedRunReader(run,process_probe=lambda *a:False).read()
 assert snapshot.run_status=='waiting' and meta['lifecycle']=='not_connected'

def test_explicit_owner_running_is_not_overridden_by_exit_record(run):
 explicit(run);calls=[]
 snapshot,meta=RedRunReader(run,owner_running=True,process_probe=lambda *a:(calls.append(a) or False)).read()
 assert len(calls)==1 and snapshot.run_status=='running' and meta['lifecycle']=='running'

def test_legacy_stopped_display_remains_compatible(run):
 def forbidden(*a):raise AssertionError('legacy already-stopped display keeps original probe behavior')
 snapshot,meta=RedRunReader(run,process_probe=forbidden).read()
 assert snapshot.run_status=='failed' and meta['lifecycle']=='stopped'
