"""ROM-free regressions for guarded native poison travel around earned Strength."""
from types import SimpleNamespace
import pytest
import pokemon_red_completion.red_player_safari_rewards as rewards

def vitals(hp=(93,), status=(8,)):
    return SimpleNamespace(party_hp=hp, party_status=status)

@pytest.mark.parametrize('before,after,expected', [
    (vitals((93,),(0,)),vitals((93,),(0,)),True),
    (vitals((93,),(8,)),vitals((67,),(8,)),True),
    (vitals((132,119,0,77,93,132),(0,0,0,0,8,64)),vitals((132,119,0,77,67,132),(0,0,0,0,8,64)),True),
    (vitals((0,93),(0,8)),vitals((0,92),(0,8)),True),
    (vitals((93,),(64,)),vitals((93,),(64,)),True),
    (vitals((93,),(0,)),vitals((92,),(0,)),False),
    (vitals((93,),(64,)),vitals((92,),(64,)),False),
    (vitals((93,),(8,)),vitals((94,),(8,)),False),
    (vitals((93,),(0,)),vitals((92,),(8,)),False),
    (vitals((93,),(8,)),vitals((92,),(0,)),False),
    (vitals((1,),(8,)),vitals((0,),(0,)),False),
    (vitals((1,),(8,)),vitals((0,),(8,)),False),
    (vitals((93,),(8,)),vitals((92,),(64,)),False),
    (vitals((93,),(8,)),vitals((92,91),(8,8)),False),
    (vitals(None,(8,)),vitals(None,(8,)),False),
    (vitals((93,),None),vitals((93,),None),False),
])
def test_strength_trip_vitals_only_admits_existing_nonfaint_poison(before,after,expected):
    assert rewards.strength_exchange_travel_vitals_preserved(before,after) is expected

def npc_raw(*, hp, status=8, received=False):
    return SimpleNamespace(
        map_id=rewards.MapId.WARDENS_HOUSE,battle_state=0,
        bag_items=((199,1),) if received else ((64,1),),
        event_flags=bytes([2]) if received else bytes([0]),
        player_money=15304,party_species_ids=(166,),party_levels=(43,),
        party_moves=((33,85,98,158),),party_pp=((35,14,30,15),),
        party_hp=(hp,),party_status=(status,),badge_bits=31,
    )

@pytest.mark.parametrize('status',[0,8])
def test_npc_dialogue_still_rejects_hp_damage_even_if_poisoned(monkeypatch,status):
    before=npc_raw(hp=93,status=status);after=npc_raw(hp=92,status=status)
    reads=iter([before,after]);runtime=SimpleNamespace(reader=SimpleNamespace(read=lambda:next(reads)))
    monkeypatch.setattr(rewards,'_field_ready',lambda runtime:True)
    def no_input(action):raise AssertionError('Exact NPC guard should reject before input')
    with pytest.raises(RuntimeError,match='HM reward changed protected party_hp'):
        rewards.collect_hm_reward(runtime,SimpleNamespace(execute=no_input),item=199,consumed=64,events=(1,))

def test_npc_dialogue_keeps_exact_preexisting_poison_vitals(monkeypatch):
    before=npc_raw(hp=93);after=npc_raw(hp=93,received=True)
    reads=iter([before,after]);runtime=SimpleNamespace(reader=SimpleNamespace(read=lambda:next(reads)))
    monkeypatch.setattr(rewards,'_field_ready',lambda runtime:True)
    def no_input(action):raise AssertionError('Mock receipt is already observed')
    result=rewards.collect_hm_reward(runtime,SimpleNamespace(execute=no_input),item=199,consumed=64,events=(1,))
    assert result=={'item':199,'consumed':64,'events':[1]}