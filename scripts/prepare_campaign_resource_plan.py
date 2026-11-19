"""Prepare a new resource plan using the current project memory ceiling.

Existing frozen plans are immutable;this writes only a new requested output.
Preparing a plan never launches a process or authorizes gameplay.
"""
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,json

PROJECT_PROFILE=Path(__file__).resolve().parents[1]/'configs/windows-player-resource-limits.json'

def with_project_memory_limits(plan,profile):
    if plan.get('schema')!='pokemon.windows.scoped-cgroup-command.v2':
        raise ValueError('Unsupported scoped resource plan')
    if profile.get('schema')!='pokemon.windows.player-resource-limits.v1':
        raise ValueError('Unsupported project memory profile')
    limits=profile['limits']
    if set(limits)!={'memory.high','memory.max','memory.swap.max','memory.oom.group'}:
        raise ValueError('Unexpected resource controls')
    if any(type(v)is not int for v in limits.values()):
        raise ValueError('Memory controls must be integers')
    if not 16777216<=limits['memory.high']<=limits['memory.max']<=16*1024**3:
        raise ValueError('Invalid finite project memory ceiling')
    if limits['memory.swap.max']!=0 or limits['memory.oom.group']!=1:
        raise ValueError('Existing swap and group-kill guards must be preserved')
    updated=deepcopy(plan);updated['limits']=dict(limits)
    return updated

def prepare_resource_plan(template,output,profile_path=PROJECT_PROFILE):
    template,output,profile_path=map(Path,(template,output,profile_path))
    source=template.read_bytes();profile_bytes=profile_path.read_bytes()
    plan=with_project_memory_limits(json.loads(source),json.loads(profile_bytes))
    plan['memory_profile']=dict(path=str(profile_path.resolve()),sha256=hashlib.sha256(profile_bytes).hexdigest())
    with output.open('x')as handle:json.dump(plan,handle,indent=2,sort_keys=True);handle.write('\n')
    assert template.read_bytes()==source
    return dict(path=str(output.resolve()),sha256=hashlib.sha256(output.read_bytes()).hexdigest())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--template',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(prepare_resource_plan(args.template,args.output)))
