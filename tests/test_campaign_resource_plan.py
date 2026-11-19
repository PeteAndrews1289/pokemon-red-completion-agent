from copy import deepcopy
from pathlib import Path
import json,pytest,ast
from prepare_campaign_resource_plan import with_project_memory_limits,prepare_resource_plan,PROJECT_PROFILE

def template():
    return dict(schema='pokemon.windows.scoped-cgroup-command.v2',limits={'memory.high':4*1024**3,'memory.max':4*1024**3,'memory.swap.max':0,'memory.oom.group':1},command=['python','-I','-B','bound-worker'],script_sha256='a'*64,outer_seconds=30,absolute_cutoff_utc='2026-11-07T15:00:00+00:00',termination_grace_seconds=2,cgroup_name='pokemon-capacity-example',receipt='/private/result.json')

def profile():return json.loads(PROJECT_PROFILE.read_bytes())

def test_project_default_has_user_authorized_sixteen_gib_ceiling_and_eight_gib_soft_reclaim():
    p=profile();assert p['limits']['memory.high']==8*1024**3 and p['limits']['memory.max']==16*1024**3
    assert p['limits']['memory.swap.max']==0 and p['limits']['memory.oom.group']==1

def test_memory_change_preserves_every_other_declared_guard_and_source_template():
    old=template();original=deepcopy(old);new=with_project_memory_limits(old,profile())
    assert old==original and new['limits']==profile()['limits']
    assert {k:v for k,v in new.items()if k!='limits'}=={k:v for k,v in old.items()if k!='limits'}

@pytest.mark.parametrize('key,value',[('memory.max',17*1024**3),('memory.max',0),('memory.max',float('inf')),('memory.max',True),('memory.high',17*1024**3),('memory.high',0),('memory.swap.max',1),('memory.oom.group',0)])
def test_invalid_profiles_fail_closed(key,value):
    p=profile();p['limits'][key]=value
    with pytest.raises(ValueError):with_project_memory_limits(template(),p)

def test_unexpected_controls_fail_closed():
    p=profile();p['limits']['pids.max']=1
    with pytest.raises(ValueError):with_project_memory_limits(template(),p)

def test_builder_refuses_to_overwrite_existing_plan(tmp_path):
    source=tmp_path/'source.json';source.write_text(json.dumps(template()));old=source.read_bytes()
    with pytest.raises(FileExistsError):prepare_resource_plan(source,source)
    assert source.read_bytes()==old

def test_real_supervisor_admits_raised_ceiling():
    source=Path(__file__).parents[1]/'scripts/scoped_campaign_cgroup_command.py';tree=ast.parse(source.read_text());nodes=[]
    for node in tree.body:
        if isinstance(node,ast.Assign)and any(isinstance(t,ast.Name)and t.id in('limits','high','maximum')for t in node.targets):nodes.append(node)
        elif isinstance(node,ast.If)and any(isinstance(x,ast.Constant)and x.value=='Invalid finite memory containment'for x in ast.walk(node)):nodes.append(node)
    assert len(nodes)==4
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),{'d':with_project_memory_limits(template(),profile())})
