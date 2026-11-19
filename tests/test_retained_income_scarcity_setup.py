from hashlib import sha256
import pytest
import pokemon_red_completion.red_player_income_setup as setup
from pokemon_red_completion.observation import RamAddress

@pytest.fixture
def source(monkeypatch):
 payload=b'ROM-free assigned TRAIN fixture';monkeypatch.setattr(setup,'_RETAINED_LEAGUE_TRAIN_PARENTS',frozenset({sha256(payload).hexdigest()}))
 memory={int(RamAddress.PLAYER_MONEY):0,int(RamAddress.PLAYER_MONEY)+1:0x60,int(RamAddress.PLAYER_MONEY)+2:0,int(RamAddress.NUM_BAG_ITEMS):3}
 for i,v in enumerate((4,5,16,4,53,6,255)):memory[int(RamAddress.BAG_ITEMS)+i]=v
 return memory,dict(source_state=payload,isolated_training_setup=True,controller_released=True,battle_state=0,partition='train')

def test_only_cash_and_ordinary_balls_removed_medicine_retained(source):
 memory,kwargs=source;before=dict(memory);rows=setup.prepare_retained_income_scarcity_fixture(memory,**kwargs)
 assert memory[int(RamAddress.PLAYER_MONEY)+2]==8
 assert memory[int(RamAddress.NUM_BAG_ITEMS)]==2
 assert tuple(memory[int(RamAddress.BAG_ITEMS)+i]for i in range(5))==(16,4,53,6,255)
 allowed={int(RamAddress.PLAYER_MONEY)+i for i in range(3)}|{int(RamAddress.NUM_BAG_ITEMS)}|{int(RamAddress.BAG_ITEMS)+i for i in range(5)}
 assert {r['address']for r in rows}==allowed
 assert all(r['before']==before[r['address']]and r['after']==memory[r['address']]for r in rows)

@pytest.mark.parametrize('change',[dict(partition='development'),dict(partition='sealed'),dict(isolated_training_setup=False),dict(controller_released=False),dict(battle_state=1),dict(source_state=b'unregistered')])
def test_invalid_authority_or_source_rejects_before_writes(source,change):
 memory,kwargs=source;before=dict(memory);kwargs.update(change)
 with pytest.raises(ValueError):setup.prepare_retained_income_scarcity_fixture(memory,**kwargs)
 assert memory==before

def test_changed_starting_resources_reject_before_writes(source):
 memory,kwargs=source;memory[int(RamAddress.PLAYER_MONEY)+2]=9;before=dict(memory)
 with pytest.raises(ValueError):setup.prepare_retained_income_scarcity_fixture(memory,**kwargs)
 assert memory==before
