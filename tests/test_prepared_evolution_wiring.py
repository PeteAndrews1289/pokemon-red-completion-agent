from types import SimpleNamespace as N

import pytest
import run_configured_red_player as driver
import pokemon_red_completion.red_boxed_machine_options as boxed
import pokemon_red_completion.red_prepared_evolution_options as prepared


def test_v3_is_explicit_and_development_only():
    p=dict(partition='development',owned_machine_options=dict(
        mode='boxed_frontier_evolution_bundles_v3',reason='Whole option native qualification'))
    assert driver.declared_owned_machine_options(p)
    for partition in ('train','benchmark','sealed'):
        with pytest.raises(ValueError,match='DEVELOPMENT'):
            driver.declared_owned_machine_options(dict(p,partition=partition))


def test_complete_recipes_use_collection_port_and_preserve_prior_observers(monkeypatch):
    ordinary=('ordinary-evolution',);old_calls=[];seen={}
    def original(*args):old_calls.append(args);return ordinary
    menu=N(enumerate_collection=original,enumerate_owned_machines=lambda *a:('field-machine',))
    holder=dict(configured_route=N(route_world='old-world'))
    cfg=N(admits=lambda binding:binding!='excluded')
    p=dict(partition='development',owned_machine_options=dict(
        mode='boxed_frontier_evolution_bundles_v3',reason='Whole option native qualification'))
    monkeypatch.setattr(driver,'owned_machine_options',lambda *a,**k:('party-machine',))
    monkeypatch.setattr(boxed,'boxed_frontier_machine_options',lambda *a,**k:('boxed-machine',))
    def quotes(*args,rom,world):seen['world']=world;return ('typed-choice',)
    monkeypatch.setattr(boxed,'quoted_boxed_frontier_machine_options',quotes)
    def recipes(*args,**kwargs):seen.update(kwargs);return ('prepared-evolution',)
    monkeypatch.setattr(prepared,'prepared_evolution_options',recipes)
    driver.connect_declared_machine_options(menu,p,rom=b'fixture',holder=holder,configuration=cfg)
    holder['configured_route']=N(route_world='new-world')
    rt=N(reader=N(read=lambda:N(badge_bits=255)));actions=object();obs=object()
    assert menu.enumerate_collection(rt,actions,obs)==ordinary+('prepared-evolution',)
    assert menu.enumerate_owned_machines(rt,actions,obs)==(
        'field-machine','party-machine','boxed-machine')
    assert seen['enumerate_collection'] is original and seen['admits'] is cfg.admits
    assert seen['machine_choices']==('typed-choice',) and seen['evolution_options'] is ordinary
    assert seen['world']=='new-world' and old_calls==[(rt,actions,obs)]


def test_prepostgame_collection_is_unchanged(monkeypatch):
    original=lambda *a:('ordinary',)
    menu=N(enumerate_collection=original,enumerate_owned_machines=None)
    def forbidden(*a,**k):raise AssertionError('not postgame')
    monkeypatch.setattr(boxed,'quoted_boxed_frontier_machine_options',forbidden)
    driver.connect_owned_machine_options(menu,rom=b'fixture',include_boxed_frontier=True,
        boxed_world=forbidden,include_prepared_evolution=True,admits=lambda _:True)
    assert menu.enumerate_collection(N(reader=N(read=lambda:N(badge_bits=31))),N(),N())==('ordinary',)


@pytest.mark.parametrize('changes',[
    dict(include_boxed_frontier=False),dict(admits=None),dict(include_prepared_evolution=1),
    dict(collection=None)])
def test_recipe_wiring_rejects_missing_dependencies_before_replacing_any_port(changes):
    original=lambda *a:()
    menu=N(enumerate_collection=changes.pop('collection',original),enumerate_owned_machines=original)
    args=dict(rom=b'fixture',include_boxed_frontier=True,boxed_world=lambda:N(),
        include_prepared_evolution=True,admits=lambda _:True);args.update(changes)
    with pytest.raises(ValueError):driver.connect_owned_machine_options(menu,**args)
    assert menu.enumerate_owned_machines is original


@pytest.mark.parametrize('mode',['direct_attack_capacity_v1','boxed_frontier_attack_capacity_v2'])
def test_old_modes_do_not_install_a_collection_wrapper(mode,monkeypatch):
    original=lambda *a:()
    menu=N(enumerate_collection=original,enumerate_owned_machines=None)
    p=dict(partition='development',owned_machine_options=dict(mode=mode,reason='Old declaration'))
    driver.connect_declared_machine_options(menu,p,rom=b'fixture',holder={},configuration=N())
    assert menu.enumerate_collection is original
