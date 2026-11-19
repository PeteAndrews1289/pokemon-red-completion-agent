"""ROM-free spy on the actual fresh assembly call, using the real plan validator.

No runner module import, model query, emulator, ROM, or backend is constructed.
POKEMON_SOURCE_ROOT is only for running this proposal before copying into tests/.
"""
import ast
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE_ROOT=Path(os.environ.get('POKEMON_SOURCE_ROOT',Path(__file__).resolve().parents[1]))

def assembly_spy(plan,head=None):
    fresh=ast.parse((SOURCE_ROOT/'scripts/run_fresh_red_player.py').read_text())
    configured=ast.parse((SOURCE_ROOT/'scripts/run_configured_red_player.py').read_text())
    declaration=next(n for n in configured.body if isinstance(n,ast.FunctionDef) and n.name=='declared_preparation_context')
    calls=[n for n in ast.walk(fresh) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='assemble_configured_player']
    assert len(calls)==1, 'Every fresh assembly site must be audited if another is added'
    observed=[]
    def assemble(*args,**kwargs):
        observed.append((args,kwargs))
        return kwargs
    scope=dict(plan=plan,declared_readiness_refinement=lambda _:dict(consequence_head=head),assemble_configured_player=assemble,backend=object(),configuration=object(),parent=Path('/unused/source'),output=Path('/unused/output'),holder={'runtime':object()},model=SimpleNamespace(feature_version=16))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(declaration)],type_ignores=[])),'real_preparation_declaration','exec'),scope)
    result=eval(compile(ast.fix_missing_locations(ast.Expression(body=copy.deepcopy(calls[0]))),'actual_fresh_assembly_call','eval'),scope)
    assert len(observed)==1
    assert result['model_feature_version']==16
    assert result['live_party_runtime'] is scope['holder']['runtime']
    assert result['plan_path']==scope['output']/'PLAN.json'
    return result

@pytest.mark.parametrize('flag', ['absent',False,True])
@pytest.mark.parametrize('projection', [None,'unrelated_context','prospective_preparation_party_context_v1'])
def test_fresh_assembly_forwards_declared_or_legacy_context(flag,projection):
    plan={'partition':'development'}
    if flag!='absent':plan['include_preparation_party_context']=flag
    head=None if projection is None else SimpleNamespace(context_projection=projection)
    result=assembly_spy(plan,head)
    expected=flag is True or projection=='prospective_preparation_party_context_v1'
    if expected:assert result['include_preparation_party_context'] is True
    else:assert 'include_preparation_party_context' not in result

@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_fresh_context_rejects_non_boolean_explicit_flags(value):
    with pytest.raises(ValueError,match='explicit DEVELOPMENT booleans'):
        assembly_spy({'partition':'development','include_preparation_party_context':value})

@pytest.mark.parametrize('partition',[None,'train','evaluation'])
def test_fresh_context_rejects_non_development_declaration(partition):
    with pytest.raises(ValueError,match='explicit DEVELOPMENT booleans'):
        assembly_spy({'partition':partition,'include_preparation_party_context':True})

def test_fresh_context_validator_is_imported_from_normal_runner():
    tree=ast.parse((SOURCE_ROOT/'scripts/run_fresh_red_player.py').read_text())
    names={a.name for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='run_configured_red_player' for a in n.names}
    assert 'declared_preparation_context' in names

def test_required_species_forwarding_and_context_are_independent():
    species=['pokemon:national:007','pokemon:national:008']
    result=assembly_spy({'partition':'development','include_preparation_party_context':True,'required_species':species})
    assert result['required_species']==tuple(species)
    assert result['include_preparation_party_context'] is True
