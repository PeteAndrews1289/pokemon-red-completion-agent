from pathlib import Path
import ast
import pytest


def function():
    p=Path(__file__).parents[1]/"scripts/monitor_red_campaign_repairs.py"
    tree=ast.parse(p.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=="heartbeat_age")
    ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),"exec"),ns);return ns[node.name]

@pytest.mark.parametrize("token",["2026-11-08T22:06:44+00:00","2099-01-01T00:00:00Z","2000-01-01T00:00:00Z"])
def test_fresh_heartbeat_progress_is_independent_of_peer_wall_clock(token):
    f=function();new,changed,age=f("previous",10,token,12)
    assert new==token and changed==12 and age==0
    assert f(new,changed,new,21.9)[2]==pytest.approx(9.9)
    assert f(new,changed,new,22.1)[2]>10


def test_frozen_log_does_not_get_freshness_from_recent_looking_utc():
    f=function();token="2099-01-01T00:00:00Z"
    assert f(token,100,token,111)[2]==11
    assert f(token,100,"new sample",111)[2]==0

@pytest.mark.parametrize("token",[None,"",1])
def test_unknown_sample_identity_fails_closed(token):
    with pytest.raises(ValueError):function()("previous",0,token,1)

def test_elapsed_clock_regression_fails_closed():
    with pytest.raises(ValueError):function()("previous",10,"new",9)
