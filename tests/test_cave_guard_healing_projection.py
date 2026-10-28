from dataclasses import dataclass
from types import SimpleNamespace as S
import pytest
import pokemon_red_completion.gen1_regional_access as access
from test_gen1_regional_access import cartridge

@dataclass(frozen=True)
class World:
    rom: bytes
    object_blockers: dict
    local_graphs: dict
    terrain: dict
    def _graph_for_terrain(self, terrain):
        return ('rebuilt', self.object_blockers[3], terrain)

def world():
    return World(b'fixture', {3:frozenset({(12,4),(8,30)}),7:frozenset({(1,2)})},
                 {3:'old-city',7:'other-graph'}, {3:'city-terrain'})

def test_hidden_guard_only_changes_exact_native_object(cartridge):
    before=world();calls=[]
    after=access.observed_cave_guard_world(before,S(read_toggleable_object_hidden=lambda i:calls.append(i)or True))
    assert calls==[8,8]
    assert before.object_blockers[3]==frozenset({(12,4),(8,30)})
    assert after.object_blockers=={3:frozenset({(8,30)}),7:frozenset({(1,2)})}
    assert after.local_graphs[7]=='other-graph'
    assert after.local_graphs[3]==('rebuilt',frozenset({(8,30)}),'city-terrain')
    assert after.rom==before.rom and after.terrain==before.terrain

def test_present_guard_keeps_identical_world(cartridge):
    before=world()
    assert access.observed_cave_guard_world(before,S(read_toggleable_object_hidden=lambda _:False))is before

def test_unknown_reader_does_not_optimistically_remove_guard():
    before=world();assert access.observed_cave_guard_world(before,object())is before

@pytest.mark.parametrize('value',[None,0,1,'hidden'])
def test_nonboolean_visibility_is_rejected(cartridge,value):
    with pytest.raises(ValueError,match='visibility must be boolean'):
        access.observed_cave_guard_world(world(),S(read_toggleable_object_hidden=lambda _:value))

def test_changed_visibility_cannot_install_projection(cartridge):
    flags=iter([True,False])
    with pytest.raises(ValueError,match='changed during projection'):
        access.observed_cave_guard_world(world(),S(read_toggleable_object_hidden=lambda _:next(flags)))

def test_already_removed_guard_retains_other_masks(cartridge):
    before=world();before.object_blockers[3]=frozenset({(8,30)})
    assert access.observed_cave_guard_world(before,S(read_toggleable_object_hidden=lambda _:True))is before
