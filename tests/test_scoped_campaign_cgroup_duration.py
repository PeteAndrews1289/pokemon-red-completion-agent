"""Exercise the real duration-admission branch without root,cgroups or a ROM."""
from pathlib import Path
import ast
import pytest

SOURCE=Path(__file__).parents[1]/"scripts/scoped_campaign_cgroup_command.py"
TREE=ast.parse(SOURCE.read_text())
NODES=[]
for node in TREE.body:
    if isinstance(node,ast.Assign)and any(isinstance(t,ast.Name)and t.id=="timeout"for t in node.targets):
        NODES.append(node)
    if isinstance(node,ast.If)and any(isinstance(x,ast.Constant)and x.value=="Invalid bounded command time"for x in ast.walk(node)):
        NODES.append(node)
assert len(NODES)==2
GUARD=compile(ast.fix_missing_locations(ast.Module(body=NODES,type_ignores=[])),str(SOURCE),"exec")

@pytest.mark.parametrize("value",[1,30,180,7200,30000,30001,40420,43200])
def test_finite_authorized_durations_are_admitted(value):
    namespace={"d":{"outer_seconds":value}}
    exec(GUARD,namespace)
    assert namespace["timeout"]==value

@pytest.mark.parametrize("value",[0,-1,43201,float("inf"),float("nan"),None,"43200"])
def test_expired_unbounded_or_oversized_duration_is_rejected(value):
    with pytest.raises(ValueError,match="Invalid bounded command time"):
        exec(GUARD,{"d":{"outer_seconds":value}})
