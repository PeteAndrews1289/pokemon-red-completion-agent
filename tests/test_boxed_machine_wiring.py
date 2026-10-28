from types import SimpleNamespace as N
import pytest
import run_configured_red_player as driver
import pokemon_red_completion.red_machine_teaching as teaching
import pokemon_red_completion.red_boxed_machine_options as boxed


def machine_fixture(monkeypatch):
    monkeypatch.setattr(teaching,'verify_rom_bytes',lambda rom:None)
    monkeypatch.setattr(teaching,'RedPracticeCartridge',lambda rom:
        N(species=lambda species:N(tmhm_moves=(57,61))))
    raw=N(party_species_ids=(28,),party_moves=((70,39,145,57),),
        party_pp=((15,30,30,15),),bag_items=((211,1),(198,1)))
    return raw


def test_storage_quote_and_actual_party_share_the_same_lesson_validator(monkeypatch):
    raw=machine_fixture(monkeypatch)
    quoted=teaching.plan_observed_machine_lesson(b'fixture',bag_items=raw.bag_items,
        species_id=28,moves=raw.party_moves[0],item_id=211,party_slot=1,replace_slot=2)
    actual=teaching.plan_machine_lesson(b'fixture',N(read=lambda:raw),
        item_id=211,party_slot=1,replace_slot=2)
    assert quoted==actual and quoted.move_id==61


@pytest.mark.parametrize('change',[
    dict(replace_slot=1),dict(item_id=198),dict(item_id=True),
    dict(party_slot=False),dict(replace_slot=0),dict(bag_items=()),
    dict(moves=(70,0,0,0),replace_slot=3),dict(species_id=True)])
def test_quote_cannot_overwrite_hm_repeat_or_invent_a_lesson(monkeypatch,change):
    raw=machine_fixture(monkeypatch)
    values=dict(bag_items=raw.bag_items,species_id=28,moves=raw.party_moves[0],
        item_id=211,party_slot=1,replace_slot=2);values.update(change)
    with pytest.raises(ValueError):teaching.plan_observed_machine_lesson(b'fixture',**values)


def test_boxed_scope_is_explicit_and_development_only():
    p=dict(partition='development',owned_machine_options=dict(
        mode='boxed_frontier_attack_capacity_v2',reason='Prospective copied native qualification'))
    assert driver.declared_owned_machine_options(p)
    p['partition']='sealed'
    with pytest.raises(ValueError,match='DEVELOPMENT'):driver.declared_owned_machine_options(p)


def test_boxed_options_preserve_prior_dependencies_and_use_current_world(monkeypatch):
    menu=N(enumerate_owned_machines=lambda *a:('field-dependency',))
    seen=[];holder={'world':'first'}
    monkeypatch.setattr(driver,'owned_machine_options',lambda *a,**k:('party-machine',))
    def observe(*args,rom,world):
        seen.append((args,rom,world));return ('boxed-machine',)
    monkeypatch.setattr(boxed,'boxed_frontier_machine_options',observe)
    driver.connect_owned_machine_options(menu,rom=b'fixture',include_boxed_frontier=True,
        boxed_world=lambda:holder['world'])
    holder['world']='current';runtime=N(reader=N(read=lambda:N(badge_bits=255)))
    observation=object();actions=object()
    assert menu.enumerate_owned_machines(runtime,actions,observation)==(
        'field-dependency','party-machine','boxed-machine')
    assert seen==[((runtime,actions,observation),b'fixture','current')]


@pytest.mark.parametrize('enabled,world',[(True,None),(True,'not callable'),(1,lambda:None)])
def test_boxed_scope_never_implicitly_invents_a_route_binding(enabled,world):
    with pytest.raises(ValueError,match='route binding'):
        driver.connect_owned_machine_options(N(enumerate_owned_machines=None),rom=b'fixture',
            include_boxed_frontier=enabled,boxed_world=world)
