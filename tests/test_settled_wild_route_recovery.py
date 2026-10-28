"""Native wild losses yield a failed route with exact recovery proof, never a win."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_red_routed_recovery import make_test_raw
from test_gen1_route_runtime import FakeReader, reader_as_real
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalRecoveryRequired, GoalVerification
from pokemon_red_completion.route_executor import InterruptionReceipt, TraversalSnapshot
from pokemon_red_completion.route_1_wild import Route1WildFleeEvidence
import pokemon_red_completion.red_routed_recovery as recovery


def native_escape(*, status=False):
    return Route1WildFleeEvidence(
        initial_battle_state=1, final_battle_state=0, battle_result=2,
        expected_map_id=227, map_id=227, player_x=9, player_y=2,
        enemy_species_id=38, enemy_level=45, initial_hp=60,
        final_hp=60 if status else 30, maximum_hp_preserved=True,
        party_preserved=True, level_preserved=True, pp_preserved=True,
        status_preserved=not status, control_ready=True, run_attempts=1,
        stabilization_frames=180, hp_scope='whole_party', party_faints_allowed=True,
        new_fainted_slots=() if status else (1,), status_changes_allowed=True,
        native_status_changes=((1, 0, 64),) if status else (),
    ).public_dict()


def run_handler(*, fault=None, status=False):
    initial = replace(make_test_raw(map_id=227, x=9, y=2, hp=(30, 30)), battle_state=1)
    state = {'raw': initial}
    fake = FakeReader(initial, ready=fault!='unready')
    reader = reader_as_real(fake)
    em = SimpleNamespace(frame_count=0, pressed_buttons=(),
                         save_state_bytes=lambda: repr(state['raw']).encode())
    actions = SimpleNamespace(actions_executed=0)
    details = native_escape(status=status)
    if fault=='receipt': details['verified']=False
    if fault=='scope': details['hp_scope']='first_party_member'
    if fault=='slots': details['new_fainted_slots']=[2]
    if fault=='pp_proof': details['pp_preserved']=False
    if fault=='hp_sum': details['final_hp']=31

    def escape(_):
        state['raw'] = replace(initial, battle_state=0,
            party_hp=(30, 30) if status else (0, 30),
            party_status=(64, 0) if status else (0, 0))
        if fault=='cash': state['raw']=replace(state['raw'],player_money=210)
        if fault=='roster': state['raw']=replace(state['raw'],party_species_ids=(99,25))
        if fault=='all_fainted': state['raw']=replace(state['raw'],party_hp=(0,0))
        if fault=='items': state['raw']=replace(state['raw'],bag_items=((4,1),))
        if fault=='pressed': em.pressed_buttons=('a',)
        if fault=='position': state['raw']=replace(state['raw'],player_x=8)
        actions.actions_executed=0 if fault=='zero_cost' else 3
        em.frame_count=0 if fault=='zero_cost' else 240
        fake.raw=state['raw']
        return InterruptionReceipt('wild_battle',227,(2,9),details)

    handler=recovery.RecoveryRouteInterruptionHandler(actions,reader,
        tuple(initial.party_species_ids),(0,1),allow_wild_faints=fault!='disabled',
        emulator=em,inner=SimpleNamespace(handle=escape))
    handler.handle(TraversalSnapshot(227,(2,9),False,'wild_battle'))


@pytest.mark.parametrize('status',[False,True])
def test_verified_native_escape_yields_exact_metered_failed_route(status):
    with pytest.raises(recovery.SettledNativeWildRecovery) as caught:
        run_handler(status=status)
    stop=caught.value
    assert isinstance(stop,GoalRecoveryRequired)
    assert isinstance(stop,recovery.SettledNativeFieldRecovery) # Existing route family owns propagation.
    assert stop.report.actions_executed==3 and stop.report.frames_executed==240
    assert stop.failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert recovery.settled_route_wild_recovery_evidence(stop.evidence)
    assert recovery.settled_route_field_recovery_evidence(stop.evidence)
    assert stop.evidence['party_hp']==([30,30] if status else [0,30])
    assert stop.evidence['cash_before']==stop.evidence['cash_after']==209
    assert stop.evidence['model_queries']==0


@pytest.mark.parametrize('fault',['receipt','scope','slots','pp_proof','hp_sum',
    'cash','roster','all_fainted','items','pressed','position','zero_cost','disabled','unready'])
def test_unverified_or_changed_wild_exit_still_stops(fault):
    with pytest.raises((GoalRecoveryRequired,recovery.RedRoutedRecoveryError)) as caught:
        run_handler(fault=fault)
    assert not isinstance(caught.value,recovery.SettledNativeWildRecovery)


def certificate():
    with pytest.raises(recovery.SettledNativeWildRecovery) as caught:
        run_handler()
    return deepcopy(caught.value.evidence)


@pytest.mark.parametrize('fault',['schema','verified','support','learned','query','resources',
    'source','terminal','cash','cash_type','actions','frames','hp','revival','all_fainted',
    'slots','slot_bool','wild','scope','ready','initial_battle','final_battle','battle_result',
    'pp','level','party','status','initial_hp','final_hp','attempts','enemy','map','position',
    'stabilization','purified','changes'])
def test_certificate_rejects_forged_or_incomplete_native_proof(fault):
    e=certificate();w=e['wild_escape']
    if fault=='schema':e['schema']='unknown'
    elif fault=='verified':e['verified']=1
    elif fault=='support':e['support']='manual'
    elif fault=='learned':e['learned_recovery']=True
    elif fault=='query':e['model_queries']=True
    elif fault=='resources':e['protected_resources_verified']=False
    elif fault in {'source','terminal'}:e[fault+'_sha256']='bad'
    elif fault=='cash':e['cash_after']+=1
    elif fault=='cash_type':e['cash_before']=True
    elif fault in {'actions','frames'}:e[fault]=0
    elif fault=='hp':e['party_hp']=[0]
    elif fault=='revival':e['party_hp']=[0,31]
    elif fault=='all_fainted':e['party_hp']=[0,0]
    elif fault=='slots':e['new_fainted_slots']=[2]
    elif fault=='slot_bool':e['new_fainted_slots']=[True]
    elif fault=='wild':e['wild_escape']=None
    elif fault=='scope':w['hp_scope']='first_party_member'
    elif fault=='ready':w['control_ready']=False
    elif fault in {'initial_battle','final_battle'}:w[fault+'_state']=2
    elif fault=='battle_result':w['battle_result']=0
    elif fault in {'pp','level','party','status'}:w[fault+'_preserved']=False
    elif fault in {'initial_hp','final_hp'}:w[fault]+=1
    elif fault=='attempts':w['run_attempts']=17
    elif fault=='enemy':w['enemy_species_id']=0
    elif fault=='map':w['map']+=1
    elif fault=='position':w['position']=[True,2]
    elif fault=='stabilization':w['stabilization_frames']=0
    elif fault=='purified':w['native_purified_healing']={'unverified':True}
    elif fault=='changes':w['native_status_changes']=[[1,0,0]]
    assert not recovery.settled_route_wild_recovery_evidence(e)
    assert not recovery.settled_route_field_recovery_evidence(e)


@pytest.mark.parametrize('kind',[GoalKind.ACQUIRE_SPECIES,GoalKind.RESUPPLY,
    GoalKind.RESTORE_TEAM,GoalKind.DEVELOP_TEAM,GoalKind.EVOLVE_SPECIES,GoalKind.ADVANCE_STORY])
@pytest.mark.parametrize('fault',[None,'terminal','hp','destination','error'])
def test_native_wild_recovery_uses_existing_route_census_budget_and_replan(monkeypatch,kind,fault):
    from test_red_route_loss_recovery import route_loss
    from pokemon_red_completion.red_integrated_play import ordinary_player_setback
    _,before,after,report,binding=route_loss(monkeypatch,kind)
    e=deepcopy(dict(report.evidence));proof=certificate()
    proof.update(cash_before=945,cash_after=945,terminal_sha256=after.sha256)
    e['route_setback']=proof
    facts=deepcopy(dict(after.facts));facts.setdefault('diagnostics',{})['party_hp']=[0,30]
    error=None
    if fault=='terminal':proof['terminal_sha256']='b'*64
    if fault=='hp':facts['diagnostics']['party_hp']=[0,29]
    if fault=='destination':e['destination_executed']=True
    if fault=='error':error=RuntimeError('unknown route failure')
    assert ordinary_player_setback(binding,before,replace(after,facts=facts),
        replace(report,evidence=e),GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED),error) is (fault is None)
