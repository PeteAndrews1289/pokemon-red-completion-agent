from types import SimpleNamespace as S
import pytest
from pokemon_red_completion import red_battle_practice_factory as f
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.observation import BattleMenuPhase,RamAddress

class Memory:
    def __init__(self,moves):self.moves=moves;self.reads=[]
    def __getitem__(self,address):self.reads.append(address);return self.moves[address-int(RamAddress.ENEMY_MOVES)]
    def __setitem__(self,*a):pytest.fail('read-only adapter wrote memory')

@pytest.mark.parametrize('moves',[(64,28,15,31),(44,39,61,55),(64,0,0,0)])
def test_native_training_opposition_is_semantic_and_read_only(moves):
    memory=Memory(moves);reader=S(read=lambda:S(battle_state=2),read_battle_menu_state=lambda raw:S(phase=BattleMenuPhase.MAIN))
    observed=f.observed_train_practice_opponent_moves(reader,memory,partition=ScenarioPartition.TRAIN)
    assert tuple(int(x.move_ref.rsplit(':',1)[1])for x in observed)==tuple(x for x in moves if x)
    assert all(x.pp>0 for x in observed)and len(memory.reads)==4

@pytest.mark.parametrize('scope',[ScenarioPartition.DEVELOPMENT,None,'train'])
def test_nontraining_scope_rejected_before_memory_access(scope):
    memory=Memory((64,0,0,0))
    with pytest.raises(f.BattlePracticeError,match='TRAIN scope'):
        f.observed_train_practice_opponent_moves(object(),memory,partition=scope)
    assert memory.reads==[]

@pytest.mark.parametrize('battle,phase',[(0,BattleMenuPhase.MAIN),(1,BattleMenuPhase.MAIN),(2,None)])
def test_nonmain_source_rejected_before_memory_read(battle,phase):
    memory=Memory((64,0,0,0));reader=S(read=lambda:S(battle_state=battle),read_battle_menu_state=lambda raw:S(phase=phase))
    with pytest.raises(f.BattlePracticeError,match='trainer MAIN'):
        f.observed_train_practice_opponent_moves(reader,memory,partition=ScenarioPartition.TRAIN)
    assert memory.reads==[]

@pytest.mark.parametrize('moves',[(0,0,0,0),(64,0,15,0),(64,64,0,0)])
def test_ambiguous_inventory_rejected(moves):
    memory=Memory(moves);reader=S(read=lambda:S(battle_state=2),read_battle_menu_state=lambda raw:S(phase=BattleMenuPhase.MAIN))
    with pytest.raises(f.BattlePracticeError,match='inventory differs'):
        f.observed_train_practice_opponent_moves(reader,memory,partition=ScenarioPartition.TRAIN)
