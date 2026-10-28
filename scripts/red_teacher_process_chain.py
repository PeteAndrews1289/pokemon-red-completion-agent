"""Pure exact launch-chain validator shared by closeout and ROM-free fixtures."""
from datetime import datetime,timezone
from pathlib import Path
def validate_chain(spec,resource,early,setup,root,launch,snapshot,*,pokemon_uid,now):
 R=spec['project_root']
 command=[spec['python'],'-I','-B',spec['worker'],'--case',spec['case'],'--plan-sha256',spec['plan_sha256'],'--phase',spec['phase']]
 if spec['worker_command']!=command:raise ValueError('shared entrypoint phase/case command differs')
 if resource['command']!=command or setup['command']!=command:raise ValueError('exact worker command differs')
 if resource['script_sha256']!=spec['worker_sha256'] or setup['script_sha256']!=spec['worker_sha256']:raise ValueError('worker file pin differs')
 if early['plan_sha256']!=spec['plan_sha256'] or early['worker_sha256']!=spec['worker_sha256']:raise ValueError('early identity pins differ')
 if setup['plan_sha256']!=spec['resource_plan_sha256'] or root['plan_sha256']!=spec['resource_plan_sha256']:raise ValueError('root resource plan differs')
 if len(early['processes'])!=2:raise ValueError('expected exact worker and runuser parent')
 worker,parent=early['processes']
 supervisor=early['supervisor']
 supervisor_command=[spec['python'],'-I','-B',spec['supervisor'],'--plan',spec['resource_plan'],'--plan-sha256',spec['resource_plan_sha256'],'--expected-script',spec['worker']]
 if supervisor['pid']!=setup['launcher_pid'] or supervisor['uid']!=0 or supervisor['command']!=supervisor_command or type(supervisor['start_ticks'])is not int or supervisor['start_ticks']<=0:raise ValueError('root supervisor identity differs')
 if worker['command']!=command or worker['uid']!=pokemon_uid:raise ValueError('worker command or UID differs')
 if parent['command']!=['runuser','--user','pokemon','--',*command] or parent['uid']!=0:raise ValueError('runuser parent command or UID differs')
 if worker['parent_pid']!=parent['pid'] or parent['pid']!=root['child_pid'] or parent['parent_pid']!=setup['launcher_pid']:raise ValueError('Linux parent chain differs')
 if setup['actor_uid']!=pokemon_uid or setup['actor_user']!='pokemon' or root['actor_user']!='pokemon':raise ValueError('root actor identity differs')
 for value in [worker['pid'],parent['pid'],parent['parent_pid'],worker['start_ticks'],parent['start_ticks']]:
  if type(value)is not int or value<=0:raise ValueError('Linux identity quantity invalid')
 if len({worker['pid'],parent['pid'],parent['parent_pid']})!=3:raise ValueError('Linux identities collide')
 if setup['absolute_cutoff_utc']!=resource['absolute_cutoff_utc'] or root['absolute_cutoff_utc']!=resource['absolute_cutoff_utc']:raise ValueError('root cutoff differs')
 if setup['hard_maximum_seconds']!=resource['outer_seconds'] or root['hard_maximum_seconds']!=resource['outer_seconds']:raise ValueError('root time bound differs')
 if setup['group']!=root['group'] or root['group']!='/sys/fs/cgroup/'+resource['cgroup_name']:raise ValueError('root resource group differs')
 expected=['-d',spec['distribution'],'-u','root','--cd',R,'--',spec['python'],'-I','-B',spec['supervisor'],'--plan',spec['resource_plan'],'--plan-sha256',spec['resource_plan_sha256'],'--expected-script',spec['worker']]
 if launch['expected_arguments']!=expected or launch['resource_plan_sha256']!=spec['resource_plan_sha256']:raise ValueError('Windows expected launch differs')
 actual=launch['actual_process']
 if not isinstance(actual,dict)or actual['ProcessId']!=launch['launch_process_id']:raise ValueError('Windows original launch identity missing')
 exact='"'+spec['wsl_executable']+'" '+' '.join(expected)
 if actual['CommandLine']!=exact:raise ValueError('Windows actual command differs')
 if snapshot['original_process']!=actual:raise ValueError('snapshot is not the launched Windows process')
 if snapshot['original_absent']is not True or snapshot['original_live']is not False:raise ValueError('original Windows process still present')
 current=snapshot['actual_process']
 if current and current['ProcessId']==actual['ProcessId'] and current['CreationDate']==actual['CreationDate'] and current['CommandLine']==actual['CommandLine']:raise ValueError('Windows absence declaration contradicts process identity')
 born=datetime.fromisoformat(actual['CreationDate']);observed=datetime.fromisoformat(snapshot['observed_at_utc'])
 if born.utcoffset()is None or observed.utcoffset()is None or now.utcoffset()is None:raise ValueError('process timestamps need timezone')
 age=(now-observed).total_seconds()
 if not -3<=age<90:raise ValueError('Windows snapshot stale or future dated')
 if born>observed:raise ValueError('Windows process born after terminal snapshot')
 return dict(passed=True,worker_uid=pokemon_uid,worker_command=command,worker_pid=worker['pid'],runuser_pid=parent['pid'],root_launcher_pid=setup['launcher_pid'],windows_pid=actual['ProcessId'],windows_command_exact=True,windows_snapshot_age_seconds=age,linux_parent_chain_exact=True,resource_limits_exact=True)
