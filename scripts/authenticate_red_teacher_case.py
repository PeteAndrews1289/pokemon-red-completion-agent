"""Shared closeout adapter for the existing native/root/Windows receipt chain."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,fcntl,hashlib,json,os,shutil,pwd,runpy
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--spec',type=Path,required=True);parser.add_argument('--spec-sha256',required=True)
 args=parser.parse_args(argv)
 if sha(args.spec)!=args.spec_sha256:raise ValueError('launch specification differs')
 spec=read(args.spec);phase=spec['phase'];case=Path(spec['case']).resolve()
 if case.parent!=Path(spec['capacity_root']).resolve() or phase not in ('preflight','direct'):raise ValueError('case scope differs')
 D=case/'preflight' if phase=='preflight' else case
 W=Path(spec['windows_receipt_directory_linux']);plan=read(spec['plan'])
 with(Path(spec['source_lock'])).open('a+')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  claim=read(Path(spec['source_claim']));assert claim['source_writer_mission']==spec['mission']and claim.get('active_probe')==str(D)and not claim['actual_running']
  for k in ['worker','plan','package','supervisor','resource_plan','guard','process_chain','closeout']:assert sha(spec[k])==spec[k+'_sha256']
  for p,h in spec['additional_pins'].items():assert sha(p)==h
  early=read(D/'EARLY-LINUX-IDENTITY.json');assert early['plan_sha256']==spec['plan_sha256']and early['worker_sha256']==spec['worker_sha256']
  sameboot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()==early['boot_id']
  for row in [*early['processes'],early['supervisor']]:
   p=Path('/proc')/str(row['pid'])
   if sameboot and p.exists():assert int((p/'stat').read_text().split(') ',1)[1].split()[19])!=row['start_ticks']
  launch_id=spec['identity']
  win=read(W/(launch_id+'.windows-current.json'))
  launch=read(W/(launch_id+'.windows-launch.json'))
  root=read(D/'ROOT-EXIT-RECEIPT.json');setup=read(D/'ROOT-RESOURCE-RECEIPT.json');assert root['plan_sha256']==spec['resource_plan_sha256']and setup['plan_sha256']==spec['resource_plan_sha256'];assert not root['remaining_pids'];group=Path(root['group'])/'cgroup.procs';assert not group.exists()or not group.read_text().strip()
  resource=read(spec['resource_plan'])
  chain=runpy.run_path(spec['process_chain'])['validate_chain'](spec,resource,early,setup,root,launch,win,pokemon_uid=pwd.getpwnam('pokemon').pw_uid,now=datetime.now(timezone.utc))
  result=read(D/'RESULT.json');passed=result['passed']and root['native_exit_code']==0 and not root['timed_out'];native=phase!='preflight'
  closeout=runpy.run_path(spec['closeout'])['classify_closed_phase'](result,phase=phase,processes_absent=True,cgroup_empty=True,terminal_sha256=sha(D/'terminal.state')if(D/'terminal.state').exists()else None)
  controls=closeout['controls_released']
  auth=dict(schema='pokemon.red.machine-value-terminal.v1',observed_at_utc=datetime.now(timezone.utc).isoformat(),phase=phase,passed=passed,plan_sha256=spec['plan_sha256'],package_sha256=spec['package_sha256'],worker_sha256=spec['worker_sha256'],all_original_processes_absent=True,controls_released=controls,supervisor_cgroup_empty=True,windows_parents_absent=True,native_exit_code=root['native_exit_code'],timed_out=root['timed_out'],root_seconds=root['seconds'],full_hold_seconds=resource['outer_seconds'],error=result.get('error'),error_type=result.get('error_type'),traceback=result.get('traceback'),actual_credit=0,fits=0,new_weights=0)
  auth['exact_parent_chain']=chain;auth['closed_phase_classification']=closeout;auth['worker_result_sha256']=sha(D/'RESULT.json');auth['finish_error']=result.get('finish_error');auth['finish_traceback']=result.get('finish_traceback')
  if native:
   if passed:
    pp=read(D/'LIVE-PP-PREINPUT-GATE.json');assert pp['passed']and pp['source_bytes_exact']and pp['inputs']==pp['frames']==0
    assert result['goal_attempts']==1 and result['story_battles']==1
    auth['live_pp_preinput_gate_sha256']=sha(D/'LIVE-PP-PREINPUT-GATE.json')
   physical=closeout['physical_emulator_accounting']
   pre=read(D/'PREINPUT-QUALIFICATION.json')if(D/'PREINPUT-QUALIFICATION.json').exists()else None
   if passed:assert pre and pre['passed']and pre['source_bytes_exact']and pre['source_state_sha256']==plan['source_sha256']and physical==dict(construction_attempts=1,emulators_constructed=1,load_attempts=1,state_loads=1)
   row=result.get('row');auth.update(terminal_sha256=result.get('terminal_sha256'),source_state_sha256=plan['source_sha256'],original_TRAIN_state_sha256=plan['original_TRAIN_state_sha256'],shared_origin_id=plan['shared_origin_id'],preinput_verified=bool(pre and pre['passed']),physical_emulator_accounting=physical,admitted=result.get('admitted',False),row=row,training_admission=result.get('training_admission',False),native_costs=closeout['native_costs'],field_ready=result.get('field_ready'),separate_acquisition_cost=plan['separate_acquisition_cost'],sealed_row_reloaded_by_worker=bool(row and passed))
   if row:
    assert row['partition']=='train' if 'partition'in row else True
  else:
   auth.update(zero_emulator_preflight=True,qualification_sha256=sha(D/'QUALIFICATION.json')if(D/'QUALIFICATION.json').exists()else None)
  for kind in ['launch','current']:shutil.copyfile(W/(launch_id+'.windows-'+kind+'.json'),D/('WINDOWS-'+kind+'.json'))
  with(D/'TERMINAL-AUTHENTICATION.json').open('x')as f:json.dump(auth,f,indent=2,sort_keys=True);f.write('\n')
  claim=read(Path(spec['source_claim']));claim.update(active_probe=None,all_native_workers_stopped=True);(Path(spec['source_claim'])).write_text(json.dumps(claim,indent=2,sort_keys=True)+'\n')
  print(json.dumps({k:v for k,v in auth.items()if k not in ['row','traceback','separate_acquisition_cost']}))
  if native and row:print(json.dumps(dict(outcome=row.get('outcome'),censor_reason=row.get('censor_reason'))))

if __name__=='__main__':main()
