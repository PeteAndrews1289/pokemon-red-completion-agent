"""Exercise the shipped helper's early preparation-observation boundary."""
import ast
from pathlib import Path
from types import SimpleNamespace as N


def preparation_function(holder):
    path=Path(__file__).resolve().parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py'
    module=ast.parse(path.read_text())
    assembly=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='assembly')
    preparation=next(n for n in assembly.body if isinstance(n,ast.FunctionDef) and n.name=='preparation')
    namespace=dict(holder=holder)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[preparation],type_ignores=[])),str(path),'exec'),namespace)
    return namespace['preparation']


def test_retained_defeat_is_observed_even_when_boundary_cannot_offer_training():
    latest=N(result=N(value='won'));retained=N(result=N(value='lost'));seen=[]
    runtime=object();observation=N(input_ready=False)
    holder=dict(observe_history=lambda:latest,
        observe_preparation_loss=lambda rt,obs,last:seen.append((rt,obs,last)) or retained)
    assert preparation_function(holder)(runtime,object(),observation)==()
    assert seen==[(runtime,observation,latest)]


def test_legacy_helper_without_retained_history_still_returns_no_unready_offer():
    assert preparation_function(dict(observe_history=lambda:None))(object(),object(),N(input_ready=False))==()
