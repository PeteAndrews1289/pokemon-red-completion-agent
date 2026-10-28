"""A failed history read cannot replace a native battle error or loss certificate."""
from types import SimpleNamespace as S
import pytest
import pokemon_red_completion.red_league_funding_execution as execution
from pokemon_red_completion.battle_runtime import BattleRuntimeError
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager_runtime import GoalVerification
from test_red_league_funding_execution import _runtime, _Delegate


@pytest.mark.parametrize('with_field_recovery',[False,True])
@pytest.mark.parametrize('native_kind',['error','certified_loss','success'])
def test_battle_observation_preserves_native_failure_and_requires_success_history(monkeypatch,with_field_recovery,native_kind):
    runtime,_=_runtime()
    runtime.league_story_battle_controller=S(controller_name='scoped',declared_level_deficit=30)
    observation_error=FileNotFoundError('retained incomplete outcome')
    original=(execution.RedLeagueFundingBattleLoss({'terminal_sha256':'a'*64})
              if native_kind=='certified_loss'else BattleRuntimeError('native sleeping turn failure'))
    seen=[]
    def observe(objective):
        seen.append(objective)
        raise observation_error
    def run_native(*args,**kwargs):
        if native_kind!='success':raise original
        return S()
    class Skill:
        def __init__(self,*args,**kwargs):pass
        def availability(self,state):return S(executable=True)
        def execute(self):raise AssertionError('substituted at native gate')
    field=(S(choose=lambda provider,next_goal:next_goal(runtime.adapter.observe()))if with_field_recovery else None)
    monkeypatch.setattr(execution,'learned_league_controller',lambda rt:S(field_recovery=field))
    monkeypatch.setattr(execution,'RedFaintAwareFieldRestoreGoalProvider',lambda *args:object())
    monkeypatch.setattr(execution,'RedCartridgeLoreleiSkill',Skill)
    monkeypatch.setattr(execution,'run_retained_league_battle',run_native)
    reuse=S(bind=lambda rt,*args:rt,observe_battle=observe)
    expected=observation_error if native_kind=='success'else original
    with pytest.raises(type(expected))as caught:
        execution._run_battle(runtime,CountingExecutor(_Delegate()),object(),
            'defeat_agatha',100,'scoped',0,development_reuse=reuse)
    assert caught.value is expected
    assert seen==['defeat_agatha']
    if native_kind!='success':
        assert original.__notes__==['Battle-history observation also failed: FileNotFoundError: retained incomplete outcome']
    if native_kind=='certified_loss':assert original.certificate=={'terminal_sha256':'a'*64}
