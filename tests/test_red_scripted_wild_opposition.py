"""Candidate-only callback/source/actor preservation checks, without an emulator."""
from dataclasses import dataclass, replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import test_gen1_scripted_wild as fixtures
from test_red_live_option_menu import _binding

from pokemon_red_completion import gen1_scripted_wild as q
from pokemon_red_completion import red_player_early_story_options as early
from pokemon_red_completion import red_player_tower as tower
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress
from pokemon_red_completion.player_option_challenge import OptionChallenge


def proof_fixture(monkeypatch):
    monkeypatch.setattr(fixtures,'p',q)
    s=fixtures.fixture(level=17)
    monkeypatch.setattr(q,'verify_rom_bytes',lambda payload:None)
    return s


def binding_fixture(monkeypatch):
    s=proof_fixture(monkeypatch)
    s.raw.player_y,s.raw.player_x,s.raw.player_money=14,11,101
    s.state=b'unchanged-native-fixture'
    s.emulator=N(save_state_bytes=lambda:s.state,frame_count=0)
    s.diagnostics=[]
    s.actions=N(actions_executed=0,record_diagnostic_event=lambda name,body:s.diagnostics.append((name,body)))
    s.memory_reads=[]
    def read_u8(address):
        s.memory_reads.append(address)
        if address==int(RamAddress.CURRENT_MAP):return s.raw.map_id
        if address==int(RamAddress.IS_IN_BATTLE):return s.raw.battle_state
        return s.phases[address]
    s.reader=PokemonRedStateReader(N(read_u8=read_u8))
    s.reader.read=lambda:s.raw
    s.runtime=N(reader=s.reader,emulator=s.emulator)
    @dataclass
    class World:
        local_graphs:dict
        object_blockers:dict
        def plan_feasible_to_map(self,*args,**kwargs):return None
    @dataclass
    class Route:
        route_world:World
        rom:bytes
        destination_map:int=147
        destination_at:tuple=(16,11)
    s.route=Route(World({147:LocalGraph({(16,11):()})},{147:frozenset()}),bytes(s.image))
    s.actor=N(model_sha256=tower.FROZEN_K_SHA256,qualification_sha256=tower.K_QUALIFICATION_SHA256)
    monkeypatch.setattr(tower,'verify_rom_bytes',lambda _:None)
    monkeypatch.setattr(tower,'_field_ready',lambda _:True)
    monkeypatch.setattr(tower,'_origin',lambda *args:None)
    return s


def test_default_binding_does_not_run_quote_or_change_actor_interface(monkeypatch):
    s=binding_fixture(monkeypatch)
    binding=tower.marowak_binding(s.runtime,s.actions,route=s.route,battler=s.actor)
    assert binding is not None and s.memory_reads==[] and s.diagnostics==[]
    assert s.actions.actions_executed==s.emulator.frame_count==0


def test_opt_in_quotes_exact_source_and_preserves_existing_binding_execution(monkeypatch):
    s=binding_fixture(monkeypatch)
    baseline=tower.marowak_binding(s.runtime,s.actions,route=s.route,battler=s.actor)
    seen=[]
    binding=tower.marowak_binding(s.runtime,s.actions,route=s.route,battler=s.actor,
                                  observe_binding=lambda witness,b:seen.append((witness,b)))
    witness,observed=seen[0]
    assert observed is binding and witness.binding_ref==binding.binding_ref==baseline.binding_ref
    assert witness.source_sha256==sha256(s.state).hexdigest() and witness.opposition.level==17
    assert binding.execute.__code__ is baseline.execute.__code__
    assert binding.verify.__code__ is baseline.verify.__code__
    assert (binding.kind,binding.estimated_effort,binding.estimated_risk,binding.maximum_cash_debit)==(
        baseline.kind,baseline.estimated_effort,baseline.estimated_risk,baseline.maximum_cash_debit)
    assert s.diagnostics[0][0]=='scripted_wild_opposition_quote'
    assert s.actions.actions_executed==s.emulator.frame_count==0 and s.state==b'unchanged-native-fixture'


@pytest.mark.parametrize('fault',['unsupported_reader','local_phase','current_phase','override','unsupported_grammar'])
def test_unavailable_quote_preserves_admitted_binding_without_callback(monkeypatch,fault):
    s=binding_fixture(monkeypatch)
    if fault=='unsupported_reader':s.reader.read_scripted_wild_opposition=None
    elif fault=='local_phase':s.phases[s.local]=4
    elif fault=='current_phase':s.phases[s.current]=4
    elif fault=='override':s.phases[s.override]=16
    elif fault=='unsupported_grammar':s.route.rom=b'unsupported'
    seen=[]
    binding=tower.marowak_binding(s.runtime,s.actions,route=s.route,battler=s.actor,
                                  observe_binding=lambda *x:seen.append(x))
    assert binding is not None and seen==[] and s.diagnostics==[]
    assert s.actions.actions_executed==s.emulator.frame_count==0


@pytest.mark.parametrize('fault',['state','frames','actions'])
def test_observer_native_boundary_changes_are_rejected(monkeypatch,fault):
    s=binding_fixture(monkeypatch)
    def observer(*args):
        if fault=='state':s.state=b'changed'
        elif fault=='frames':s.emulator.frame_count+=1
        else:s.actions.actions_executed+=1
    with pytest.raises(ValueError,match='native boundary'):
        tower.marowak_binding(s.runtime,s.actions,route=s.route,battler=s.actor,observe_binding=observer)


def test_already_engaged_battle_keeps_old_recovery_owner_without_preview(monkeypatch):
    s=binding_fixture(monkeypatch)
    s.raw.battle_state=1;s.raw.player_y,s.raw.player_x=16,10
    seen=[]
    b=tower.marowak_binding(s.runtime,s.actions,route=s.route,battler=s.actor,
                           observe_binding=lambda *x:seen.append(x))
    assert b.kind is GoalKind.RECOVER_CONTROL and seen==[] and s.memory_reads==[]


def early_fixture(monkeypatch,*,fault=None):
    s=proof_fixture(monkeypatch)
    s.binding=_binding(GoalKind.ADVANCE_STORY,binding_ref='private:exact-wild',calls=[])
    s.actor=object();s.trainer=object();s.calls=[]
    s.state=b'early-current-enumeration-state'
    s.emulator=N(save_state_bytes=lambda:s.state,frame_count=0)
    s.runtime=N(reader=N(read=lambda:s.raw),emulator=s.emulator)
    s.actions=N(actions_executed=0)
    s.route=N(rom=bytes(s.image))
    monkeypatch.setattr(early,'_legal',lambda *args:True)
    monkeypatch.setattr(early,'fuji_binding',lambda *args,**kwargs:None)
    def offer(*args,**kwargs):
        s.calls.append(kwargs)
        callback=kwargs.get('observe_binding')
        if callback is not None and fault!='unsupported':
            proof=q._decode_layout(s.route.rom,147).opposition
            if fault=='wrong_event':proof=replace(proof,defeated_event=270)
            if fault=='wrong_rom_hash':proof=replace(proof,rom_sha256='0'*64)
            elif fault=='wrong_layout_hash':proof=replace(proof,layout_sha256='0'*64)
            elif fault=='wrong_region_pin':
                pins=list(proof.region_pins);at,n,_=pins[0];pins[0]=(at,n,'0'*64)
                proof=replace(proof,region_pins=tuple(pins))
            elif fault=='wrong_level':proof=replace(proof,level=proof.level+1)
            source='a'*64 if fault=='wrong_source' else sha256(s.state).hexdigest()
            witness=q.BoundScriptedWildOpposition(proof,source,s.binding.binding_ref)
            callback(witness,s.binding)
            if fault=='duplicate':callback(witness,s.binding)
            elif fault=='mutate_state':s.state=b'mutated-after-quote'
            elif fault=='mutate_frames':s.emulator.frame_count+=1
            elif fault=='mutate_actions':s.actions.actions_executed+=1
        return replace(s.binding) if fault=='other_binding' else s.binding
    monkeypatch.setattr(early,'marowak_binding',offer)
    return s


def test_fuji_uses_existing_numeric_challenge_only_with_exact_admitted_wild_witness(monkeypatch):
    s=early_fixture(monkeypatch)
    b,c=early.fuji_story_option(s.runtime,s.actions,route=s.route,battler=s.actor,
                               trainer_battler=s.trainer,combat_levels=(13,))
    assert c==OptionChallenge.from_levels(combat_levels=(13,),opponent_levels=(17,))
    assert b.execute is s.binding.execute and b.verify is s.binding.verify
    assert b.binding_ref==s.binding.binding_ref and s.calls[0]['battler'] is s.actor
    assert b.story_objective_ref=='rescue_fuji'


@pytest.mark.parametrize('fault',['duplicate','wrong_event','other_binding'])
def test_fuji_rejects_wrong_or_duplicate_binding_witness(monkeypatch,fault):
    s=early_fixture(monkeypatch,fault=fault)
    with pytest.raises(ValueError,match='witness'):
        early.fuji_story_option(s.runtime,s.actions,route=s.route,battler=s.actor,combat_levels=(13,))


def test_fuji_keeps_unknown_when_reader_cannot_supply_witness(monkeypatch):
    s=early_fixture(monkeypatch,fault='unsupported')
    _,c=early.fuji_story_option(s.runtime,s.actions,route=s.route,battler=s.actor,combat_levels=(13,))
    assert c==OptionChallenge(True,False,0,0,0)


def test_no_declared_combat_roles_skips_quote_and_preserves_unknown(monkeypatch):
    s=early_fixture(monkeypatch)
    _,c=early.fuji_story_option(s.runtime,s.actions,route=s.route,battler=s.actor,combat_levels=())
    assert c==OptionChallenge(True,False,0,0,0) and 'observe_binding' not in s.calls[0]


@pytest.mark.parametrize('fault',['wrong_source','wrong_rom_hash','wrong_layout_hash','wrong_region_pin','wrong_level'])
def test_fuji_refuses_typed_quote_from_different_source_or_cartridge(monkeypatch,fault):
    s=early_fixture(monkeypatch,fault=fault)
    with pytest.raises(ValueError,match='witness'):
        early.fuji_story_option(s.runtime,s.actions,route=s.route,battler=s.actor,combat_levels=(13,))


@pytest.mark.parametrize('fault',['mutate_state','mutate_frames','mutate_actions'])
def test_fuji_refuses_enumerator_mutating_native_boundary_after_quote(monkeypatch,fault):
    s=early_fixture(monkeypatch,fault=fault)
    with pytest.raises(ValueError,match='native boundary'):
        early.fuji_story_option(s.runtime,s.actions,route=s.route,battler=s.actor,combat_levels=(13,))


@pytest.mark.parametrize('fault',['rom_hash','layout_hash','region_pin','level','different_current_rom'])
def test_binding_owner_refuses_foreign_or_stale_reader_quote(monkeypatch,fault):
    s=binding_fixture(monkeypatch)
    proof=q._decode_layout(s.route.rom,147).opposition
    if fault=='rom_hash':proof=replace(proof,rom_sha256='0'*64)
    elif fault=='layout_hash':proof=replace(proof,layout_sha256='0'*64)
    elif fault=='region_pin':
        pins=list(proof.region_pins);at,n,_=pins[0];pins[0]=(at,n,'0'*64)
        proof=replace(proof,region_pins=tuple(pins))
    elif fault=='level':proof=replace(proof,level=proof.level+1)
    else:
        other=bytearray(s.route.rom);other[-1]^=1;s.route.rom=bytes(other)
    s.reader.read_scripted_wild_opposition=lambda *args,**kwargs:proof
    seen=[]
    with pytest.raises(ValueError,match='witness'):
        tower.marowak_binding(s.runtime,s.actions,route=s.route,battler=s.actor,
                              observe_binding=lambda *args:seen.append(args))
    assert seen==[]
