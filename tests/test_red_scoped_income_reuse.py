from types import SimpleNamespace

import pytest

from pokemon_red_completion.red_league_funding_execution import ScopedLeagueIncomeReuse
from pokemon_red_completion.red_lorelei_story import (
    ScopedAssistedChampionController,
    ScopedAssistedLeagueRetryController,
)


@pytest.mark.parametrize('objective', ['defeat_lorelei', 'defeat_champion'])
@pytest.mark.parametrize('fault', [None, 'model', 'order', 'target', 'reader', 'conflict', 'state'])
def test_income_reuse_retains_exact_actor_and_native_boundary(monkeypatch, objective, fault):
    owner_type = (ScopedAssistedChampionController if objective == 'defeat_champion'
                  else ScopedAssistedLeagueRetryController)
    owner = object.__new__(owner_type)
    state = [b'actual-field-state']
    runtime = SimpleNamespace(emulator=SimpleNamespace(save_state_bytes=lambda: state[0]),
                              reader=object(), adapter=object())
    actor = SimpleNamespace(model_sha256='a' * 64,
                            development_story_scope=SimpleNamespace(work_order_sha256='b' * 64))
    actor.run = SimpleNamespace(__self__=actor)
    owner.battler = actor
    owner.contract = SimpleNamespace(objective_id=objective)
    guarded = []
    monkeypatch.setattr(owner_type, 'require_objective',
                        lambda self, given, **kwargs: guarded.append((self, given, kwargs)))
    configured = SimpleNamespace(emulator=runtime.emulator, reader=runtime.reader,
        adapter=runtime.adapter, league_story_battle_controller=owner,
        league_battle_controller=None, trainer_battle_runner=actor.run)

    def bind(*_args):
        if fault == 'model':
            actor.model_sha256 = 'c' * 64
        elif fault == 'order':
            actor.development_story_scope.work_order_sha256 = 'c' * 64
        elif fault == 'target':
            owner.contract.objective_id = 'defeat_agatha'
        elif fault == 'reader':
            configured.reader = object()
        elif fault == 'conflict':
            configured.league_battle_controller = object()
        elif fault == 'state':
            state[0] = b'advanced'
        return configured

    reuse = ScopedLeagueIncomeReuse('a' * 64, 'b' * 64, bind)
    if fault:
        with pytest.raises(ValueError, match='exact native actor'):
            reuse.bind(runtime, object(), object(), objective)
        assert not guarded
    else:
        assert reuse.bind(runtime, object(), object(), objective) is configured
        assert guarded == [(owner, objective, {'rematch': True})]
        assert reuse.public_dict()['new_model'] is False


@pytest.mark.parametrize('field,value', [('model_sha256', 'bad'),
    ('work_order_sha256', 'A' * 64), ('bind_runtime', False), ('observe_battle', True)])
def test_bad_reuse_declaration_fails_before_any_binding(field, value):
    params = dict(model_sha256='a' * 64, work_order_sha256='b' * 64,
                  bind_runtime=lambda *_: pytest.fail('binding before declaration guard'))
    with pytest.raises(ValueError):
        ScopedLeagueIncomeReuse(**(params | {field: value}))


@pytest.mark.parametrize('objective', ['defeat_lance', 'defeat_champion'])
def test_income_skill_receives_existing_scoped_readiness_contract(monkeypatch, objective):
    import pokemon_red_completion.red_league_funding_execution as execution
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport

    raw = SimpleNamespace(player_money=100, bag_items=(), party_species_ids=(28, 25))
    runtime = SimpleNamespace(adapter=SimpleNamespace(observe=lambda: SimpleNamespace(
        raw=raw, game_state=object())), emulator=SimpleNamespace(frame_count=0),
        reader=SimpleNamespace(read=lambda: raw))
    configured = SimpleNamespace(league_story_battle_controller=SimpleNamespace(
        controller_name='existing-scoped-mode', declared_level_deficit=30))
    seen = []
    monkeypatch.setattr(ScopedLeagueIncomeReuse, 'bind', lambda *_: configured)
    monkeypatch.setattr(execution, 'learned_league_controller', lambda _: None)

    class Skill:
        def __init__(self, supplied, _actions, _world, **kwargs):
            assert supplied is configured
            seen.append(kwargs)

        def availability(self, _state):
            return SimpleNamespace(executable=True)

        def execute(self):
            raw.player_money += 200
            return GoalExecutionReport(0, 0, {'bag_items_spent': 0})

    monkeypatch.setattr(execution, 'RedCartridgeLoreleiSkill', Skill)
    monkeypatch.setattr(execution, 'RedCartridgeChampionSkill', Skill)
    reuse = ScopedLeagueIncomeReuse('a' * 64, 'b' * 64, lambda *_: configured)
    execution._run_battle(runtime, SimpleNamespace(actions_executed=0), object(),
                          objective, 200, 'frozen-k-development', 0, development_reuse=reuse)
    assert seen[0]['maximum_level_deficit'] == 30
    assert seen[0]['recovery_controller'] == 'existing-scoped-mode'
    assert seen[0]['rematch'] is True
