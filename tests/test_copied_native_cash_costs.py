from types import SimpleNamespace as N
import pytest
import run_configured_red_player as driver


def test_gross_debit_is_retained_even_with_larger_rewards():
    result=driver.copied_native_cash_costs(N(observe_cash=lambda:99,
        observed_cash_debits=13,observed_cash_rewards=27,observed_cash_changes=3))
    assert driver.native_cash_deltas(result,())==(13,)
    assert result['observed_cash_rewards']==27 and result['observed_cash_changes']==3


@pytest.mark.parametrize('field,value',[(f,v) for f in (
    'observed_cash_debits','observed_cash_rewards','observed_cash_changes')
    for v in (-1,True,1.5)])
def test_invalid_cash_counters_are_not_zeroed(field,value):
    values=dict(observe_cash=lambda:99,observed_cash_debits=0,
        observed_cash_rewards=0,observed_cash_changes=0)
    values[field]=value
    with pytest.raises(ValueError,match='counter is invalid'):
        driver.copied_native_cash_costs(N(**values))


def test_missing_cash_observer_cannot_claim_zero_costs():
    with pytest.raises(ValueError,match='live cash observation'):
        driver.copied_native_cash_costs(N(observe_cash=None,observed_cash_debits=0,
            observed_cash_rewards=0,observed_cash_changes=0))
