from dataclasses import dataclass
from types import SimpleNamespace as NS
import pytest
from pokemon_red_completion import red_income_preparation as m
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_league_funding import RedLeagueFundingError


def declaration():
    return dict(partition="development", owned_stock_income_bootstrap=True,
                native_owned_stock_income=dict(mode=m.NATIVE_OWNED_STOCK_MODE,
                    reason="Bounded owned-stock capability comparison"))


@pytest.mark.parametrize("change", [dict(partition="train"), dict(partition="sealed"),
    dict(owned_stock_income_bootstrap=False), dict(native_owned_stock_income=True),
    dict(native_owned_stock_income=dict(mode="unknown", reason="x")),
    dict(native_owned_stock_income=dict(mode=m.NATIVE_OWNED_STOCK_MODE, reason="")),
    dict(native_owned_stock_income=dict(mode=m.NATIVE_OWNED_STOCK_MODE, reason="x", target=54))])
def test_invalid_declarations_fail_before_provider(change):
    with pytest.raises(ValueError):m.declared_native_owned_stock_income(declaration() | change)


@dataclass(frozen=True)
class Binding:
    kind: object
    resource_quote: object
    binding_ref: str
    execute: object
    verify: object


@pytest.fixture
def setup(monkeypatch):
    import pokemon_red_completion.red_learned_league as league
    import pokemon_red_completion.red_league_funding_execution as execution
    import pokemon_red_completion.red_player_field_goals as skills
    class Controller:
        def require_identity(self):return None
    class Reuse:pass
    controller=Controller();controller.income_owned_stock_bootstrap=True;controller.income_reuse=Reuse()
    raw=NS(badge_bits=255, player_money=8, bag_items=((53,5),(52,2),(16,1)),
           party_levels=(54,54,40,66,59,76), ready=True)
    runtime=NS(reader=NS(read=lambda:raw), adapter=NS(graph=NS(completed_ids=lambda state:{"enter_hall_of_fame"}), observe=lambda:NS(game_state=None)), league_battle_controller=controller)
    events=[];actions=NS(record_diagnostic_event=lambda name,value:events.append((name,value)));calls=[]
    def qualified(rt,world):calls.append((rt,world));return NS(qualification=NS(expected_net_income=29799))
    monkeypatch.setattr(league,"FrozenLeagueController",Controller);monkeypatch.setattr(execution,"ScopedLeagueIncomeReuse",Reuse)
    monkeypatch.setattr(skills,"_field_ready",lambda rt:True);monkeypatch.setattr(skills,"_raw_party_fully_restored",lambda raw:raw.ready)
    monkeypatch.setattr(m,"learned_league_controller",lambda rt:rt.league_battle_controller)
    monkeypatch.setattr(m,"bind_red_league_funding_execution",qualified)
    original=lambda *args:None;backend=NS(income_with_existing_reserve=original);route=NS(route_world=object());execute=lambda:None;verify=lambda report:True
    binding=Binding(GoalKind.RESUPPLY,NS(expected_income=29799),"income",execute,verify)
    return NS(runtime=runtime,raw=raw,backend=backend,original=original,actions=actions,route=route,binding=binding,calls=calls,events=events)


def test_default_keeps_original_object_and_missing_legacy_backend():
    original=lambda *args:None;backend=NS(income_with_existing_reserve=original)
    m.configure_native_owned_stock_income(backend,{})
    assert backend.income_with_existing_reserve is original
    m.configure_native_owned_stock_income(NS(),{})


def test_owned_stock_alternative_keeps_executor_verifier_and_all_stock(setup):
    s=setup;m.configure_native_owned_stock_income(s.backend,declaration())
    result=s.backend.income_with_existing_reserve(s.runtime,s.actions,s.route,s.binding)
    assert result.binding_ref.endswith(":native-qualified-owned-stock-v1")
    assert result.execute is s.binding.execute and result.verify is s.binding.verify
    assert result.resource_quote is s.binding.resource_quote
    assert s.raw.party_levels[2]==40 and s.raw.bag_items==((53,5),(52,2),(16,1))
    assert len(s.calls)==1 and s.events[0][1]["supplied_applicability_not_learned"]
    assert s.events[0][1]["no_inputs"]


def test_reassembly_does_not_stack_or_leak_opt_in(setup):
    s=setup
    for _ in range(2):m.configure_native_owned_stock_income(s.backend,declaration())
    assert s.backend.income_with_existing_reserve.native_owned_stock_original is s.original
    m.configure_native_owned_stock_income(s.backend,{})
    assert s.backend.income_with_existing_reserve is s.original


def test_previous_reserve_offer_wins_without_new_qualification(setup):
    s=setup;sentinel=object();s.backend.income_with_existing_reserve=lambda *args:sentinel
    m.configure_native_owned_stock_income(s.backend,declaration())
    assert s.backend.income_with_existing_reserve(s.runtime,s.actions,s.route,s.binding)is sentinel
    assert not s.calls and not s.events


@pytest.mark.parametrize("stock", [(),((52,2),),((53,5),)])
def test_missing_owned_minimum_does_not_offer_or_procure(setup,stock):
    s=setup;s.raw.bag_items=stock;m.configure_native_owned_stock_income(s.backend,declaration())
    assert s.backend.income_with_existing_reserve(s.runtime,s.actions,s.route,s.binding)is None
    assert not s.calls and not s.events


def test_unrestored_party_keeps_refusal(setup):
    s=setup;s.raw.ready=False;m.configure_native_owned_stock_income(s.backend,declaration())
    assert s.backend.income_with_existing_reserve(s.runtime,s.actions,s.route,s.binding)is None
    assert not s.calls


def test_native_entry_refusal_keeps_refusal(setup,monkeypatch):
    s=setup
    def refuse(*args):raise RedLeagueFundingError("No legal Fly origin")
    monkeypatch.setattr(m,"bind_red_league_funding_execution",refuse);m.configure_native_owned_stock_income(s.backend,declaration())
    assert s.backend.income_with_existing_reserve(s.runtime,s.actions,s.route,s.binding)is None
    assert not s.events


def test_quote_mismatch_is_not_swallowed(setup):
    s=setup;s.binding.resource_quote.expected_income=1;m.configure_native_owned_stock_income(s.backend,declaration())
    with pytest.raises(ValueError,match="qualified quote"):
        s.backend.income_with_existing_reserve(s.runtime,s.actions,s.route,s.binding)


def test_continuation_rejects_silent_applicability_change():
    import run_configured_red_player as driver
    with pytest.raises(ValueError):driver.validate_continued_sequence_wiring(declaration(),{})
