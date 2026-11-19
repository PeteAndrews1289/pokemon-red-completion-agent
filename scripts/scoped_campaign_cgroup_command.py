from pathlib import Path
import argparse,hashlib,json,os,pwd,re,sys
from datetime import datetime,timezone,timedelta
p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--expected-script',required=True);args=p.parse_args()
raw=Path(args.plan).read_bytes()
if hashlib.sha256(raw).hexdigest()!=args.plan_sha256:raise ValueError('Resource plan identity changed')
d=json.loads(raw);root=(Path(__file__).resolve().parents[2]/'windows-seven-goal-implementation-20261017/capacity-planning').resolve();script=Path(args.expected_script).resolve();python=str(Path(__file__).resolve().parents[2]/'runtime/bin/python')
if d['schema']!='pokemon.windows.scoped-cgroup-command.v2' or os.geteuid()!=0:raise ValueError('Invalid root resource declaration')
if not script.is_relative_to(root) or hashlib.sha256(script.read_bytes()).hexdigest()!=d['script_sha256'] or d['command'][:4]!=[python,'-I','-B',str(script)]:raise ValueError('Unbound unprivileged command')
if not re.fullmatch(r'pokemon-capacity-[a-z0-9-]+',d['cgroup_name']):raise ValueError('Unscoped cgroup')
limits=d['limits'];high=limits['memory.high'];maximum=limits['memory.max']
if not 16777216<=high<=maximum<=17179869184 or limits['memory.swap.max']!=0 or limits['memory.oom.group']!=1:raise ValueError('Invalid finite memory containment')
timeout=d.get('outer_seconds',30)
if not isinstance(timeout,(int,float)) or not 1<=timeout<=43200:raise ValueError('Invalid bounded command time')
absolute=datetime.fromisoformat(d['absolute_cutoff_utc'])
if absolute.tzinfo is None or absolute.utcoffset().total_seconds()!=0:raise ValueError('Absolute cutoff must be UTC')
remaining=(absolute-datetime.now(timezone.utc)).total_seconds()
grace=d.get('termination_grace_seconds',2)
if type(grace) not in (int,float) or not 0.1<=grace<=15:raise ValueError('Invalid reserved cancellation grace')
hard_seconds=min(float(timeout),remaining)
if hard_seconds<=grace:raise ValueError('Absolute cutoff expired or lacks cancellation reserve')
soft_seconds=hard_seconds-grace
soft_absolute=absolute-timedelta(seconds=grace)
group=Path('/sys/fs/cgroup')/d['cgroup_name'];group.mkdir(exist_ok=True)
if (group/'cgroup.procs').read_text().strip():raise ValueError('Resource cgroup already occupied')
for key,value in limits.items():
 if key not in ['memory.high','memory.max','memory.swap.max','memory.oom.group']:raise ValueError('Unexpected resource control')
 (group/key).write_text(str(value))
 if (group/key).read_text().strip()!=str(value):raise ValueError('Resource control not applied')
for key in ['memory.events','memory.stat','memory.current','memory.peak']:
 if not (group/key).is_file():raise ValueError('Missing native controller evidence')
user=pwd.getpwnam('pokemon');receipt=Path(d['receipt']).resolve()
if d.get('allow_scoped_cache_reclaim') is True:
    os.chown(group/'memory.reclaim',user.pw_uid,user.pw_gid)
elif d.get('allow_scoped_cache_reclaim') not in(None,False):raise ValueError('Invalid scoped cache reclaim opt-in')
if not receipt.is_relative_to(root):raise ValueError('Unscoped receipt')
record=dict(utc_started_at=datetime.now(timezone.utc).isoformat(),absolute_cutoff_utc=absolute.isoformat(),hard_maximum_seconds=hard_seconds,cancellation_reserve_seconds=grace,work_admission_seconds=soft_seconds,schema='pokemon.windows.scoped-cgroup-native-launch.v2',plan_sha256=args.plan_sha256,script_sha256=d['script_sha256'],command=d['command'],launcher_pid=os.getpid(),root_setup_only=True,actor_user='pokemon',actor_uid=user.pw_uid,group=str(group),limits=limits,before_events=(group/'memory.events').read_text(),before_current=int((group/'memory.current').read_text()),originals_archive_and_global_wsl_configuration_unchanged=True)
fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.fchown(fd,user.pw_uid,user.pw_gid)
with os.fdopen(fd,'w') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
import time,signal
started=time.monotonic();child=os.fork()
if child==0:
    (group/'cgroup.procs').write_text(str(os.getpid()))
    os.execv('/usr/sbin/runuser',['runuser','--user','pokemon','--',*d['command']])
timed_out=False;sent_at=None;status=None;cancelled_at_utc=None
while True:
    got,waitstatus=os.waitpid(child,os.WNOHANG)
    if got:status=waitstatus;break
    elapsed=time.monotonic()-started
    now_utc=datetime.now(timezone.utc)
    if (elapsed>=soft_seconds or now_utc>=soft_absolute) and sent_at is None:
        timed_out=True;sent_at=time.monotonic();cancelled_at_utc=now_utc.isoformat()
        for target in (group/'cgroup.procs').read_text().split():
            try:os.kill(int(target),signal.SIGINT)
            except ProcessLookupError:pass
    if elapsed>=hard_seconds or now_utc>=absolute:
        timed_out=True
        for target in (group/'cgroup.procs').read_text().split():
            try:os.kill(int(target),signal.SIGKILL)
            except ProcessLookupError:pass
    time.sleep(0.02)
remaining=[int(x) for x in (group/'cgroup.procs').read_text().split()]
if remaining:
    for target in remaining:
        try:os.kill(target,signal.SIGKILL)
        except ProcessLookupError:pass
    for _ in range(100):
        if not (group/'cgroup.procs').read_text().strip():break
        time.sleep(0.02)
exit_record=dict(utc_exited_at=datetime.now(timezone.utc).isoformat(),absolute_cutoff_utc=absolute.isoformat(),hard_maximum_seconds=hard_seconds,cancellation_reserve_seconds=grace,cancelled_at_utc=cancelled_at_utc,schema='pokemon.windows.scoped-cgroup-native-exit.v2',plan_sha256=args.plan_sha256,child_pid=child,native_exit_code=os.waitstatus_to_exitcode(status),timed_out=timed_out,seconds=time.monotonic()-started,group=str(group),limits=limits,events=(group/'memory.events').read_text(),memory_current=int((group/'memory.current').read_text()),memory_peak=int((group/'memory.peak').read_text()),memory_stat=(group/'memory.stat').read_text(),remaining_pids=[int(x) for x in (group/'cgroup.procs').read_text().split()],actor_user='pokemon',root_setup_and_exit_evidence_only=True,emulator_launch_count_not_inferred=True)
exit_path=receipt.with_name('ROOT-EXIT-RECEIPT.json');fd=os.open(exit_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.fchown(fd,user.pw_uid,user.pw_gid)
with os.fdopen(fd,'w') as f:json.dump(exit_record,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:v for k,v in exit_record.items() if k!='memory_stat'}),flush=True)
code=os.waitstatus_to_exitcode(status);sys.exit((128-code) if code<0 else (124 if timed_out else code))
