"""ROM-free proof/custody checks; no native progress or TRAIN labels."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as N
import json

import pytest
from test_retained_field_faint import environment, write_parent
from pokemon_red_completion import red_player_forced_motion as motion
from pokemon_red_completion import red_player_configuration as configuration
from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding,GoalExecutionReport,GoalVerification
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
from pokemon_red_completion.red_travel_capture import RegisteredTravelCaptureHandler
from pokemon_red_completion.route_executor import TraversalSnapshot,RouteExecutionError


def native_proof(rt, failed):
    raw=rt.reader.read()
    members=[]
    for i,species in enumerate(raw.party_species_ids):
        attack,defense,speed,special=raw.party_stats[i]
        members.append(dict(species_ref=f'pokemon.red.gb.us.rev0:species:{species:03d}',
            level=raw.party_levels[i],max_hp=raw.party_max_hp[i],hp=3 if i==0 else raw.party_hp[i],
            status='poison' if i==0 else None,stats=dict(attack=attack,defense=defense,speed=speed,special=special),
            moves=[dict(move_ref=f'pokemon.red.gb.us.rev0:move:{move:03d}',pp=pp & 63)
                   for move,pp in zip(raw.party_moves[i],raw.party_pp[i],strict=True)]))
    observation=dict(features=dict(control=dict(input_ready=True),battle=None,menu=None,
        party=dict(count=raw.party_count,members=members),resources=dict(money=raw.player_money),
        progress=dict(badge_count=int(raw.badge_bits).bit_count())))
    episode=dict(final_observation=observation,final_observation_sha256=canonical_sha256(observation),
        capture_id='native-closed-battle',battle_won=True,final_battle_state=0,stop_reason='battle_won',
        teacher_queries=0,memory_write_actions=0,failed_move_executions=0)
    endpoint=dict(outcome_sha256=canonical_sha256(episode),final_state_sha256='e'*64,actor_returned_win=True)
    return dict(schema='pokemon.red.retained-native-field-boundary.v1',episode=episode,endpoint=endpoint,
        capture=dict(partition='development',capture_id=episode['capture_id'],expected_map=raw.map_id,
            source_state_sha256='d'*64),source_chunk_state_sha256='d'*64,
        retained_tail_sha256=failed['terminal_state_sha256'],native_final_state_sha256='e'*64)


def stale_environment(monkeypatch):
    rt,actions,state,failed,calls=environment(monkeypatch)
    failed['error']='field dialogue lacks a newly poisoned member faint'
    rt.reader.raw=replace(rt.reader.raw,badge_bits=31,player_money=1000,party_max_hp=(100,100),party_stats=((100,90,80,120),(80,70,60,100)),
        party_moves=((1,2,0,0),(1,2,0,0)),party_pp=((5,3,0,0),(5,3,0,0)))
    assert all(getattr(rt.reader.raw,k) is not None for k in ('party_count','party_species_ids','party_hp','party_status','party_levels','party_max_hp','party_stats','party_moves','party_pp','player_money','badge_bits'))
    from dataclasses import asdict
    diag=json.loads(json.dumps(asdict(rt.reader.raw)))
    diag['party_pp_encoded']=diag['party_pp']
    failed['after']['diagnostics']=diag
    failed['before']['diagnostics']=deepcopy(diag)
    failed['before']['diagnostics']['party_hp']=[100,100]
    failed['before']['diagnostics']['party_status']=[0,0]
    failed['before_state_sha256']='d'*64
    return rt,actions,state,failed,calls,native_proof(rt,failed)


def rehash(proof):
    proof['episode']['final_observation_sha256']=canonical_sha256(proof['episode']['final_observation'])
    proof['endpoint']['outcome_sha256']=canonical_sha256(proof['episode'])


def test_closed_native_poison_boundary_recovers_exact_tail_without_reconstructing_game_state(monkeypatch):
    rt,actions,state,failed,calls,proof=stale_environment(monkeypatch)
    assert motion.retained_field_faint_binding(rt,actions,outcome=failed) is None
    b=motion.retained_field_faint_binding(rt,actions,outcome=failed,prior_native_boundary=proof)
    assert b is not None and not calls
    report=b.execute()
    assert b.verify(report).status.value=='succeeded'
    assert rt.reader.read().party_hp==(0,100)
    assert report.evidence['model_queries']==report.evidence['directional_inputs']==0


@pytest.mark.parametrize('fault',['episode_sha','observation_sha','final_state_sha','source','partition',
    'capture','map','not_won','not_field','teacher','memory_write','failed_move','unready',
    'money','badges','species','level','stats','pp','unknown_status','no_poison','no_prior_hp','healed_other'])
def test_unrelated_or_changed_native_boundary_never_authorizes_text(monkeypatch,fault):
    rt,actions,state,failed,calls,proof=stale_environment(monkeypatch)
    ep=proof['episode'];f=ep['final_observation']['features'];m=f['party']['members'][0]
    if fault=='episode_sha': proof['endpoint']['outcome_sha256']='0'*64
    elif fault=='observation_sha': ep['final_observation_sha256']='0'*64
    elif fault=='final_state_sha': proof['native_final_state_sha256']='0'*64
    elif fault=='source': proof['capture']['source_state_sha256']='0'*64
    elif fault=='partition': proof['capture']['partition']='train'
    elif fault=='capture': proof['capture']['capture_id']='unrelated'
    elif fault=='map': proof['capture']['expected_map']+=1
    elif fault=='not_won': ep['battle_won']=False
    elif fault=='not_field': ep['final_battle_state']=2
    elif fault=='teacher': ep['teacher_queries']=1
    elif fault=='memory_write': ep['memory_write_actions']=1
    elif fault=='failed_move': ep['failed_move_executions']=1
    elif fault=='unready': f['control']['input_ready']=False
    elif fault=='money': f['resources']['money']+=1
    elif fault=='badges': f['progress']['badge_count']+=1
    elif fault=='species': m['species_ref']='pokemon.red.gb.us.rev0:species:001'
    elif fault=='level': m['level']+=1
    elif fault=='stats': m['stats']['attack']+=1
    elif fault=='pp': m['moves'][0]['pp']+=1
    elif fault=='unknown_status': m['status']='sleep'
    elif fault=='no_poison': m['status']=None
    elif fault=='no_prior_hp': m['hp']=0
    elif fault=='healed_other': f['party']['members'][1]['hp']-=1
    if fault not in {'episode_sha','observation_sha'}: rehash(proof)
    assert motion.retained_field_faint_binding(rt,actions,outcome=failed,prior_native_boundary=proof) is None
    assert not calls and actions.actions_executed==rt.emulator.frame_count==0


def test_verified_trainer_return_refreshes_poison_observer_through_capture_wrapper(monkeypatch):
    rt,actions,state,failed,calls=environment(monkeypatch)
    reader=rt.reader
    reader.dialogue_visible=False;reader.moving_direction=0
    reader.raw=replace(reader.raw,party_hp=(3,100),party_status=(8,0))
    wild=Gen1WildFleeHandler(actions,reader,maximum_flees=0,stabilization_frames=120,
        allow_party_faints=True,allow_field_faint_dialogue=True,emulator=rt.emulator)
    # Simulate the handler created before combat. Its old snapshot is stale.
    wild._field_boundary=replace(reader.raw,party_hp=(100,100),party_status=(0,0))
    capture=RegisteredTravelCaptureHandler.__new__(RegisteredTravelCaptureHandler)
    capture.fallback=wild
    binding=ExecutableGoalBinding('pokemon.red:retained-engagement:exact',GoalKind.RECOVER_CONTROL,
        .1,.1,lambda:GoalExecutionReport(0,0,dict(battle=dict(outcome='won'))),lambda _:GoalVerification.succeeded())
    owner=EngagedStoryRouteHandler(capture,reader,lambda:binding)
    owner.handle(TraversalSnapshot(reader.raw.map_id,(reader.raw.player_y,reader.raw.player_x),False,'battle:2'))
    assert wild._field_boundary.party_hp==(3,100) and wild._field_boundary.party_status==(8,0)
    assert not calls
    reader.raw=replace(reader.raw,party_hp=(0,100),party_status=(0,0))
    reader.dialogue_visible=True;reader.moving_direction=4
    receipt=wild.handle(TraversalSnapshot(reader.raw.map_id,(reader.raw.player_y,reader.raw.player_x),False,'scripted_dialogue'))
    assert receipt.details['new_fainted_slots']==[1]


def test_field_observer_refuses_an_unsettled_boundary_before_replacing_its_evidence(monkeypatch):
    rt,actions,state,failed,calls=environment(monkeypatch)
    handler=Gen1WildFleeHandler(actions,rt.reader,maximum_flees=0,stabilization_frames=120,
        allow_party_faints=True,allow_field_faint_dialogue=True,emulator=rt.emulator)
    before=handler._field_boundary
    with pytest.raises(RouteExecutionError,match='not settled'): handler.observe_native_field_boundary()
    assert handler._field_boundary is before and not calls


@pytest.mark.parametrize('fault',[None,'wrong_tail','wrong_chunk','missing_state','wrong_state'])
def test_configured_parent_binds_prior_field_file_to_exact_chunk_and_tail(monkeypatch,tmp_path,fault):
    rt,actions,state,failed,calls,proof=stale_environment(monkeypatch)
    write_parent(tmp_path,state,failed)
    payload=b'prior-native-battle-final'
    from hashlib import sha256
    proof['native_final_state_sha256']=sha256(payload).hexdigest()
    proof['endpoint']['final_state_sha256']=proof['native_final_state_sha256']
    if fault=='wrong_tail': proof['retained_tail_sha256']='0'*64
    elif fault=='wrong_chunk': proof['source_chunk_state_sha256']='0'*64
    if fault!='missing_state':(tmp_path/'retained-native-field-boundary.state').write_bytes(b'wrong'if fault=='wrong_state'else payload)
    (tmp_path/'retained-native-field-boundary.json').write_text(json.dumps(proof))
    inventory=configuration._retained_field_faint_inventory(rt,actions,parent=tmp_path)
    assert (inventory is None) is (fault is not None)
    assert not calls
