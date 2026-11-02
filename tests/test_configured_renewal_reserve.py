"""A return reserve cannot become a newly clipped chunk's PC setup budget."""
from types import SimpleNamespace as N
import copy
import pytest
from run_configured_red_player import configured_execution_limits, configured_renewal_stop_reason

def request(seconds=600):
    return N(decisions=24, actions=30000, frames=2500000, seconds=seconds)

def allowance():
    return dict(decisions=100, actions=100000, frames=10000000, seconds=2000, heals=100)

@pytest.mark.parametrize("axis,value", [("cutoff",12),("seconds",12),("actions",3000),("frames",250000)])
def test_clipped_renewal_cannot_spend_existing_return_reserve(axis,value):
    left=allowance();wall=600
    if axis=="cutoff":wall=value
    else:left[axis]=value
    original=copy.deepcopy(left)
    limits=configured_execution_limits(request(),left,wall)
    assert configured_renewal_stop_reason(request(),left,wall,compulsory_settlement=False)=="insufficient_settlement_allowance"
    assert left==original
    assert limits.seconds==min(600,int(left['seconds']),wall)

@pytest.mark.parametrize("axis,reserve", [("seconds",60),("actions",3000),("frames",250000)])
def test_renewal_admits_only_above_requested_work_and_settlement_reserves(axis,reserve):
    left=allowance();left[axis]=2 * reserve
    assert configured_renewal_stop_reason(request(),left,600,compulsory_settlement=False)=="insufficient_settlement_allowance"
    left[axis]+=1
    assert configured_renewal_stop_reason(request(),left,600,compulsory_settlement=False) is None

@pytest.mark.parametrize("seconds,expected",[(3,None),(12,None),(240,"insufficient_settlement_allowance"),(600,"insufficient_settlement_allowance")])
def test_explicit_short_diagnostic_request_is_not_an_aggregate_clipped_long_request(seconds,expected):
    assert configured_renewal_stop_reason(request(seconds),allowance(),12,compulsory_settlement=False)==expected

@pytest.mark.parametrize("decisions,expected",[(1,"insufficient_settlement_allowance"),(2,None),(24,None)])
def test_existing_compulsory_recovery_retains_its_allowance(decisions,expected):
    left=allowance();left['decisions']=decisions
    assert configured_renewal_stop_reason(request(),left,12,compulsory_settlement=True)==expected

@pytest.mark.parametrize("unsettled",[False,True])
def test_cutoff_is_never_extended_even_for_recovery(unsettled):
    assert configured_renewal_stop_reason(request(),allowance(),0,compulsory_settlement=unsettled)=="declared_cutoff_reached"

@pytest.mark.parametrize("bad",[None,0,1,"yes"])
def test_unknown_control_state_is_not_treated_as_safe_admission(bad):
    with pytest.raises(TypeError,match="boolean"):
        configured_renewal_stop_reason(request(),allowance(),600,compulsory_settlement=bad)


@pytest.mark.parametrize("wall_left,unsettled,admitted",[(12,False,False),(60,False,False),(61,False,False),(119,False,False),(120,False,False),(121,False,True),(12,True,True)])
def test_real_driver_renewal_block_admits_before_assembly_and_keeps_earned_pair(tmp_path,wall_left,unsettled,admitted):
    # Execute the actual after-result renewal block, replacing only the private
    # backend/clock. This checks wiring and output side effects without a ROM.
    import ast, inspect
    from datetime import datetime,UTC,timedelta
    from hashlib import sha256
    import run_configured_red_player as driver
    tree=ast.parse(inspect.getsource(driver.run))
    loop=next(node for node in ast.walk(tree) if isinstance(node,ast.While)
              and any(isinstance(q,ast.Call) and isinstance(q.func,ast.Name)
                      and q.func.id=='execute_player_chunk' for q in ast.walk(node)))
    index=next(i for i,node in enumerate(loop.body) if isinstance(node,ast.Try)
               and any(isinstance(q,ast.Call) and isinstance(q.func,ast.Name)
                       and q.func.id=='remaining_allowance' for q in ast.walk(node)))
    harness=ast.fix_missing_locations(ast.Module(body=[ast.While(test=ast.Constant(True),
        body=loop.body[index:]+[ast.Break()],orelse=[])],type_ignores=[]))
    source=tmp_path/'runs/segment-001';source.mkdir(parents=True)
    (source/'terminal.state').write_bytes(b'earned')
    (source/'CONTEXT.json').write_text('{"earned":true}')
    baseline=dict(decisions=7,actions=100,frames=5000,seconds=9.0,heals=3)
    spent={k:v+1 for k,v in baseline.items()};exported=dict(spent=spent,state_sha256=sha256(b'earned').hexdigest())
    now=datetime(2026,1,1,tzinfo=UTC)
    clock=N(now=lambda tz:now,fromisoformat=datetime.fromisoformat)
    runtime=object();calls=[]
    def assemble(*a,**kw):
        calls.append('assembly')
        return b'earned',lambda control:calls.append('factory'),object(),dict(runtime=runtime),object()
    ns=dict(vars(driver),args=request(),left=allowance(),exported=exported,
        plan=dict(inherited_spent=baseline,allowance=allowance(),cutoff_utc=(now+timedelta(seconds=wall_left)).isoformat(),automatic_runtime_renewal={}),
        copies={k:0 for k in baseline},holder=dict(runtime=runtime),root=tmp_path,
        output=source,parent=source,context=exported,ordinal=1,renewed=0,declaration={},
        backend=object(),configuration=object(),model=N(feature_version=9),refinement={},
        machine_options=False,em=N(save_state_bytes=lambda:b'earned'),
        c=N(digest=lambda p:sha256(p.read_bytes()).hexdigest()),datetime=clock,
        requires_compulsory_settlement=lambda rt:unsettled,assemble_configured_player=assemble,
        driver_terminal_reason=None)
    exec(compile(harness,'<actual driver renewal block>','exec'),ns)
    assert calls==(['assembly','factory'] if admitted else [])
    assert (tmp_path/'runs/segment-002').exists() is admitted
    assert (source/'terminal.state').read_bytes()==b'earned'
    assert exported['spent']==spent and baseline['seconds']==9.0
    assert ns['driver_terminal_reason']==(None if admitted else 'insufficient_settlement_allowance')
    if admitted:
        import json
        declaration=json.loads((tmp_path/'runs/segment-002/PLAN.json').read_text())
        assert declaration['inherited_spent']==spent
        assert declaration['same_live_emulator'] and not declaration['state_restoration']
