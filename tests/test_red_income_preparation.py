from types import SimpleNamespace as N
import pytest
import pokemon_red_completion.red_income_preparation as subject


def scenario(monkeypatch, **changes):
    values = dict(ready=True, hof=True, enabled=True, reuse=object(), restored=True,
                  cash=37, target=16500, reserve=10500, bootstrap=None, ordinary=(),
                  battle=0, badges=255)
    values.update(changes)
    calls = []
    raw = N(battle_state=values['battle'], badge_bits=values['badges'])
    runtime = N(adapter=N(observe=lambda: N(input_ready=values['ready'], game_state=object()),
                          graph=N(completed_ids=lambda _: {'enter_hall_of_fame'} if values['hof'] else set())),
                reader=N(read=lambda: raw))
    monkeypatch.setattr(subject, 'learned_league_controller', lambda _: N(
        income_owned_stock_bootstrap=values['enabled'], income_reuse=values['reuse']))
    monkeypatch.setattr(subject, 'red_economy_snapshot', lambda _: N(cash=values['cash']))

    def qualify(*args):
        calls.append('native_qualification')
        return N(qualification=N(battles=tuple(N(maximum_opponent_level=x) for x in (42, 57, 71))))

    monkeypatch.setattr(subject, 'bind_red_league_funding_execution', qualify)
    kwargs = dict(missing_reserve_cost=lambda _: values['reserve'],
                  collection_cash_target=lambda *_: values['target'],
                  bootstrap_targets=lambda _: values['bootstrap'],
                  ordinary_income_peers=lambda *_: values['ordinary'],
                  party_ready=lambda _: values['restored'])
    class InputForbidden:
        def execute(self, action):
            pytest.fail('Opposition quotation must never execute an input')
    return runtime, InputForbidden(), object(), kwargs, calls


def test_earned_cash_dead_end_quotes_actual_opposition_without_selecting_target(monkeypatch):
    runtime, actions, world, kwargs, calls = scenario(monkeypatch)
    assert subject.qualified_income_preparation_levels(runtime, actions, world, **kwargs) == (42, 57, 71)
    assert calls == ['native_qualification']


@pytest.mark.parametrize('changes', [dict(ready=False), dict(hof=False), dict(enabled=False),
    dict(reuse=None), dict(restored=False), dict(cash=16500), dict(reserve=37),
    dict(bootstrap=(0, 1, 1)), dict(ordinary=(object(),)), dict(battle=1), dict(badges=127)])
def test_ordinary_or_unqualified_contexts_do_not_add_preparation(monkeypatch, changes):
    runtime, actions, world, kwargs, calls = scenario(monkeypatch, **changes)
    assert subject.qualified_income_preparation_levels(runtime, actions, world, **kwargs) is None
    assert not calls


def test_native_qualification_refusal_stays_a_refusal(monkeypatch):
    runtime, actions, world, kwargs, _ = scenario(monkeypatch)
    def refuse(*args):
        raise subject.RedLeagueFundingError('existing party/route/stock guard')
    monkeypatch.setattr(subject, 'bind_red_league_funding_execution', refuse)
    assert subject.qualified_income_preparation_levels(runtime, actions, world, **kwargs) is None
