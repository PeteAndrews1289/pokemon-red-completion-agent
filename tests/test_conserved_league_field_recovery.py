import json
from dataclasses import replace
import pytest
from test_red_faint_recovery import fixture,raw_party,apply_choice
from test_red_live_option_menu import _model
from pokemon_red_completion.goal_manager import GoalKind,GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding,GoalVerification
from pokemon_red_completion.red_faint_recovery import RedFaintRecoveryError,FieldRecoveryChoice
from pokemon_red_completion.red_league_field_recovery import LeagueFieldRecovery

def setup(monkeypatch,tmp_path,raw,*,conserve=True):
    provider,reader,calls=fixture(monkeypatch);reader.raw=raw
    model=_model()
    session=LeagueFieldRecovery(model,model.model_sha256,tmp_path/'campaign',lambda:json.dumps({'hp':reader.raw.party_hp,'bag':reader.raw.bag_items,'status':reader.raw.party_status}).encode(),10000,maximum_items=6,selection_mode='deterministic_safety',conserve_owned_medicine=conserve)
    binding=ExecutableGoalBinding('next-income-room',GoalKind.RESUPPLY,.5,.5,lambda:None,lambda _:GoalVerification.succeeded())
    return provider,reader,calls,session,binding

@pytest.mark.parametrize('hp',[75,85,100])
def test_healthy_three_quarter_or_higher_preserves_owned_restore(monkeypatch,tmp_path,hp):
    raw=raw_party(hp=(hp,100),maximum=(100,100),bag=((16,2),))
    provider,reader,calls,session,binding=setup(monkeypatch,tmp_path,raw)
    session.claim();assert session.choose(provider,lambda _:binding) is binding
    assert reader.raw==raw and not calls and not session.consumed
    campaign=json.loads((session.output/'campaign.json').read_text())
    assert campaign['conserve_owned_medicine'] is True and campaign['heal_below_fraction']==.75
    assert campaign['learned_medicine'] is False and campaign['model_queries']==0

def test_default_still_exposes_original_small_hp_restore(monkeypatch,tmp_path):
    raw=raw_party(hp=(85,100),maximum=(100,100),bag=((16,2),))
    provider,reader,calls,session,_=setup(monkeypatch,tmp_path,raw,conserve=False)
    assert session._supported_offer(provider,provider.adapter.observe()).binding is not None
    assert reader.raw==raw and not calls

@pytest.mark.parametrize('hp,status,bag',[(74,0,((16,1),)),(0,0,((53,1),)),(100,8,((52,1),))])
def test_wounded_fainted_or_statused_member_still_has_a_real_owned_item(monkeypatch,tmp_path,hp,status,bag):
    raw=raw_party(hp=(100,hp),maximum=(100,100),status=(0,status),bag=bag)
    provider,reader,calls,session,_=setup(monkeypatch,tmp_path,raw)
    assert session._supported_offer(provider,provider.adapter.observe()).binding is not None
    assert reader.raw==raw and not calls

def test_existing_recipient_restriction_is_never_broadened(monkeypatch,tmp_path):
    raw=raw_party(hp=(85,0),maximum=(100,100),bag=((16,1),(53,1)))
    provider,reader,calls,session,_=setup(monkeypatch,tmp_path,raw)
    provider.eligible_party_indices=frozenset({0})
    offer=session._supported_offer(provider,provider.adapter.observe())
    assert offer.binding is None and offer.unavailable_reason is GoalUnavailableReason.NO_LEGAL_TARGET
    assert reader.raw==raw and not calls

@pytest.mark.parametrize('bad',[
    {'party_hp':None},{'party_hp':(True,100)},{'party_max_hp':(100,)},
    {'bag_items':((16,1),(16,1))},{'party_hp':(0,0)},
])
def test_conservation_does_not_hide_invalid_party_or_inventory(monkeypatch,tmp_path,bad):
    raw=raw_party(hp=(85,100),maximum=(100,100),bag=((16,1),))
    provider,reader,calls,session,_=setup(monkeypatch,tmp_path,raw)
    observation=replace(provider.adapter.observe(),raw=replace(raw,**bad))
    with pytest.raises(RedFaintRecoveryError):session._supported_offer(provider,observation)
    assert not calls

@pytest.mark.parametrize('changes',[{'conserve_owned_medicine':1},{'conserve_owned_medicine':True,'selection_mode':'model'}])
def test_conservation_cannot_be_mislabeled_as_learned_medicine(tmp_path,changes):
    model=_model();params=dict(model=model,model_sha256=model.model_sha256,output=tmp_path/'no-output',snapshot=lambda:b's',target_cash=1000)
    with pytest.raises(ValueError):LeagueFieldRecovery(**(params|changes))
    assert not (tmp_path/'no-output').exists()
