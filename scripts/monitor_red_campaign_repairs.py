"""Adopt live workers and admit signed-off replacement segments in the same cgroup."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,signal,subprocess,sys,time
D=Path(sys.argv[1]);R=Path(__file__).resolve().parents[2]
read=lambda p:json.loads(Path(p).read_bytes());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 q=Path(str(p)+'.atomic');q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');os.replace(q,p)
def state(pid):
 try:return Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split()[0]
 except FileNotFoundError:return None
def alive(pid):return state(pid)not in(None,'Z','X')
def host_sample(path):
 with Path(path).open('rb')as f:
  f.seek(max(0,Path(path).stat().st_size-10000));lines=f.read().splitlines()
 for line in reversed(lines):
  try:
   x=json.loads(line)
   if {'utc','available_bytes','commit_free_bytes'}<=x.keys():return x
  except(ValueError,TypeError):pass
 raise ValueError('No complete Windows sample')
def heartbeat_age(previous_token, changed_at, sample_token, observed_monotonic):
    """Cross-OS UTC is a sample identity,not an elapsed-time clock."""
    if not isinstance(sample_token, str) or not sample_token:
        raise ValueError("Windows heartbeat identity is absent")
    if observed_monotonic < changed_at:
        raise ValueError("heartbeat elapsed clock regressed")
    if sample_token != previous_token:
        previous_token, changed_at = sample_token, observed_monotonic
    return previous_token, changed_at, observed_monotonic - changed_at

p=read(D/'PLAN.json');assert sha(D/'PLAN.json')==sys.argv[2]
assert len(p['runs'])==4 and p['fit_allowed']is False
group=Path(p['group']);assert int((group/'memory.max').read_text())==16*1024**3
old=p['old_supervisor_pid'];assert old is None
slots={x['campaign_identity']:dict(x,history=[])for x in p['runs']}
children={};handled=set();aborted=None;paused=False;sent=None;last_sample=None;start=time.monotonic();last_reclaim=-100
env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
try:
 paused=False
 write(D/'ADOPTION.json',dict(old_supervisor_paused=paused,old_supervisor_pid=old,monitor_pid=os.getpid(),group=str(group),
  adopted_live_pids=[x['worker_pid']for x in slots.values()if alive(x['worker_pid'])],
  original_cutoffs_retained=True,game_inputs=0,emulators_created_by_monitor=0,
  source_writer_required_after_adoption=False,adopted_at_utc=datetime.now(timezone.utc).isoformat()))
 # Require actual new Windows output before admitting any native request.
 # This preserves fail-closed startup even if an old log has a recent UTC.
 host_token = host_sample(p['host_monitor'])['utc']
 host_changed = time.monotonic()
 startup_end = host_changed + 10
 while True:
  candidate = host_sample(p['host_monitor'])['utc']
  if candidate != host_token:
   host_token, host_changed = candidate, time.monotonic()
   break
  if time.monotonic() >= startup_end:
   raise ValueError('Windows heartbeat did not advance before native admission')
  time.sleep(.2)
 write(D/'HOST-HEARTBEAT-QUALIFICATION.json',dict(passed=True,
  distinct_new_sample_observed=True,observed_at_utc=datetime.now(timezone.utc).isoformat(),
  liveness_clock='local_monotonic_sample_change',stale_limit_seconds=10,
  cross_OS_UTC_not_used_for_elapsed_liveness=True,game_inputs=0))
 with(D/'OS-SAMPLES.jsonl').open('a',buffering=1)as log:
  while True:
   now=datetime.now(timezone.utc)
   if now>=datetime.fromisoformat(p['monitor_cutoff_utc']):aborted=aborted or 'original_campaign_window_ending'
   if(D/'STOP').exists():aborted=aborted or 'requested_stop'
   # A repair is a new immutable work order,not a runtime strategic controller.
   if not aborted:
    for request in sorted((D/'requests').glob('*.json')):
     if request.name in handled:continue
     ticket=read(request);assert sha(ticket['job_plan']['path'])==ticket['job_plan']['sha256']
     job=read(ticket['job_plan']['path']);identity=job['campaign_identity'];slot=slots[identity]
     assert not alive(slot['worker_pid']),'Old campaign worker still live'
     assert job['original_cutoff_utc']==slot['cutoff_utc'] and job['original_launched_at_utc']==slot['launched_at_utc']
     assert datetime.now(timezone.utc)<datetime.fromisoformat(slot['cutoff_utc'])
     claim=read(R/'WINDOWS-REPAIR-CLAIM.json');assert claim['active']and claim['source_writer_active']and alive(claim['pid'])
     case=Path(job['case']);assert case.is_relative_to(Path(p['case_root']))
     plan=read(case/'PLAN.json');assert sha(case/'PLAN.json')==job['plan_sha256']
     assert plan['cutoff_utc']==slot['cutoff_utc'] and plan['partition']=='development'and plan['fit_allowed']is False and plan['copy_back']is False
     assert sha(job['worker']['path'])==job['worker']['sha256']
     assert Path(job['worker']['path']).is_relative_to(Path(p['case_root']))
     for path,pin in job['pins'].items():assert sha(path)==pin,path
     slot['history'].append(dict(worker_pid=slot['worker_pid'],case=slot['case'],player_root=slot['player_root']))
     stream=(case/'WORKER.log').open('wb');command=[str(R/'runtime/bin/python'),'-I','-B',job['worker']['path'],str(case),sha(case/'WORKER-PLAN.json'),str(case/'PLAN.json')]
     child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,env=env,start_new_session=True)
     children[child.pid]=dict(child=child,stream=stream)
     slot.update(worker_pid=child.pid,case=str(case),player_root=str(case),repair_request=str(request),restore_ordinal=job['restore_ordinal'],closed=False,passed=None,error=None)
     handled.add(request.name)
     write(case/'MONITOR-ADMISSION.json',dict(monitor_pid=os.getpid(),worker_pid=child.pid,request_sha256=sha(request),accepted_at_utc=now.isoformat(),same_cgroup=str(group)))
   for pid,item in children.items():
    if item['child'].poll()is not None and not item.get('closed'):
     item['stream'].close();item['closed']=True
   host=host_sample(p['host_monitor'])
   wall_age=(datetime.now(timezone.utc)-datetime.fromisoformat(host['utc'])).total_seconds()
   host_token,host_changed,age=heartbeat_age(host_token,host_changed,host['utc'],time.monotonic())
   available=int(next(s.split()[1]for s in Path('/proc/meminfo').read_text().splitlines()if s.startswith('MemAvailable:')))*1024
   sample=dict(utc=now.isoformat(),group_bytes=int((group/'memory.current').read_text()),wsl_available_bytes=available,
    windows_available_bytes=host['available_bytes'],windows_commit_free_bytes=host['commit_free_bytes'],host_sample_age_seconds=age,host_wall_clock_age_seconds=wall_age,
    live_worker_count=sum(alive(x['worker_pid'])for x in slots.values()))
   log.write(json.dumps(sample,sort_keys=True)+'\n');last_sample=sample
   # Reclaim only this job's clean cache before host pressure reaches the
   # unchanged hard OS reserve. No controller inputs or persistent-file changes.
   if (host['available_bytes']<6*1024**3 or host['commit_free_bytes']<4*1024**3) and time.monotonic()-last_reclaim>10:
    stat={line.split()[0]:int(line.split()[1])for line in(group/'memory.stat').read_text().splitlines()}
    if stat.get('file',0)>512*1024**2:
     before=int((group/'memory.current').read_text());cache_error=None
     try:(group/'memory.reclaim').write_text(str(min(1024**3,stat['file']//2)))
     except OSError as e:cache_error=str(e)
     last_reclaim=time.monotonic()
     with(D/'CACHE-RECLAIMS.jsonl').open('a')as cache_log:cache_log.write(json.dumps(dict(utc=now.isoformat(),before_bytes=before,after_bytes=int((group/'memory.current').read_text()),error=cache_error,persistent_files_changed=0,game_inputs=0))+'\n')
   if sample['group_bytes']>int(14*1024**3):aborted=aborted or 'aggregate_memory_reserve'
   if available<3*1024**3:aborted=aborted or 'WSL_memory_reserve'
   if host['available_bytes']<4*1024**3 or host['commit_free_bytes']<2*1024**3:aborted=aborted or 'Windows_memory_reserve'
   if age>10:aborted=aborted or 'stale_Windows_monitor'
   write(D/'STATUS.json',dict(monitor_pid=os.getpid(),old_supervisor_paused=paused,original_cutoffs_retained=True,abort_reason=aborted,
    observed_at_utc=now.isoformat(),runs=list(slots.values()),sample=sample,handled_requests=sorted(handled)))
   if aborted:
    if sent is None:
     sent=time.monotonic()
     for slot in slots.values():
      if alive(slot['worker_pid']):os.killpg(slot['worker_pid'],signal.SIGINT)
    if all(not alive(x['worker_pid'])for x in slots.values()):break
    if time.monotonic()-sent>30:
     for slot in slots.values():
      if alive(slot['worker_pid']):os.killpg(slot['worker_pid'],signal.SIGKILL)
     break
   # Stay available for diagnosed repairs even when all guests have stopped.
   # Only the original finite campaign window or explicit stop closes the monitor.
   time.sleep(1)
except BaseException as e:
 aborted='monitor_exception:'+type(e).__name__+':'+str(e)
finally:
 if aborted:
  for slot in slots.values():
   if alive(slot['worker_pid']):os.killpg(slot['worker_pid'],signal.SIGINT)
  until=time.monotonic()+8
  while any(alive(x['worker_pid'])for x in slots.values())and time.monotonic()<until:time.sleep(.1)
  for slot in slots.values():
   if alive(slot['worker_pid']):os.killpg(slot['worker_pid'],signal.SIGKILL)
 for item in children.values():
  item['child'].wait();item['stream'].close()
 write(D/'RESULT.json',dict(protocol_closed=True,abort_reason=aborted,seconds=time.monotonic()-start,
  all_workers_stopped=all(not alive(x['worker_pid'])for x in slots.values()),runs=list(slots.values()),last_sample=last_sample,
  game_inputs=0,emulators_created_by_monitor=0,fit_calls=0,original_cutoffs_retained=True))
 if paused and alive(old):
  os.kill(old,signal.SIGCONT)
 # Original supervisor can now reap its original workers and close the same root.
print(json.dumps(dict(monitor_closed=True,reason=aborted)),flush=True)
