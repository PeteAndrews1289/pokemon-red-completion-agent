from pathlib import Path
from types import SimpleNamespace as NS
import ast
import pytest

def function():
    p=Path(__file__).parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py'
    tree=ast.parse(p.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='qualified_income_without_optional_reserve')
    namespace={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),namespace)
    return namespace[node.name]

def binding(**changes):
    return NS(resource_quote=NS(**(dict(purchase_cost=0,funding_proceeds=0,reserves=(),expected_income=29799)|changes)),execute=object(),verify=object())

def test_preserves_same_native_qualified_executor_and_verifier():
    b=binding();assert function()(b,None) is b

def test_existing_enhancement_wins():
    b=binding();enhanced=object();assert function()(b,enhanced) is enhanced

@pytest.mark.parametrize('change',[dict(purchase_cost=1),dict(funding_proceeds=1),dict(reserves=(object(),)),dict(expected_income=0)])
def test_does_not_admit_purchase_sale_stock_or_unquoted_income(change):
    assert function()(binding(**change),None) is None

def test_missing_quote_stays_refused():
    assert function()(NS(resource_quote=None),None) is None

def test_caller_requires_live_qualification_before_optional_reserve():
    p=Path(__file__).parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py';s=p.read_text();start=s.index('def postgame_league_income_peer(');s=s[start:s.index('def postgame_league_frontier_peer(',start)]
    assert s.index('binding = bind_autonomous_league_funding(')<s.index('if binding is None:')<s.index('qualified_income_without_optional_reserve(binding, enhanced)')
    assert 'learned_league_controller(runtime) is None' in s
