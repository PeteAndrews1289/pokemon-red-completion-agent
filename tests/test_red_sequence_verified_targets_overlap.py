"""ROM-free overlap joins through original trace, reconstruction and state audits."""
import json
from dataclasses import replace

import pytest
from test_red_native_player import setup as native_setup
from test_red_sequence_native_audit import read
from test_red_sequence_state_audit import reader

import pokemon_red_completion.red_sequence_verified_targets as module
from pokemon_red_completion.observation import EventFlag
from pokemon_red_completion.player_sequence_targets import TASK_TERMINAL_TARGET_CONTRACT
from pokemon_red_completion.player_short_sequence import SequenceEnd
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_player import run_native_continuous_player


def collected(tmp_path, monkeypatch, *, horizon=4, stride=1, decisions=4):
    args, executed=native_setup(tmp_path,monkeypatch)
    args['limits']=replace(args['limits'],actions=decisions,decisions=decisions)
    args['sequence_horizon']=horizon
    if stride is not None:args['sequence_window_stride']=stride
    run_native_continuous_player(**args)
    root=args['output'];audit_reader=reader(monkeypatch)
    kwargs=dict(store=args['store'],model=args['model'],reader=audit_reader,
        partition=args['source']['partition'],source_sha256=args['source']['state_sha256'],
        expected_native_plan_sha256=canonical_sha256(read(root/'native-plan.json')),
        expected_actor_plan_sha256=canonical_sha256(read(root/'episode/plan.json')),
        expected_actor_result_sha256=canonical_sha256(read(root/'episode/result.json')),
        expected_declaration_sha256=canonical_sha256(read(root/'episode/sequence/declaration.json')),
        expected_catalog_sha256=audit_reader.catalog_sha256)
    return root,kwargs,executed


def test_stride_one_h4_windows_join_their_actual_native_choice_intervals(tmp_path,monkeypatch):
    root,args,executed=collected(tmp_path,monkeypatch)
    files={p:p.read_bytes() for p in (root/'episode/sequence').glob('window-*.json')}
    result=module.verify_sequence_target_channels(root,**args)
    assert [r.measurement.observed_steps for r in result]==[4,3,2,1]
    assert [r.measurement.frames for r in result]==[8,6,4,2]
    assert [r.measurement.new_progress for r in result]==[1,0,0,0]
    assert result[0].targets.known==(True,True,True,True,True,True,False)
    assert all(not any(r.targets.known) for r in result[1:])
    assert all(not r.training_eligible for r in result)
    assert all(p.read_bytes()==content for p,content in files.items())
    assert executed==[2,4,6,8] and args['reader'].emulator.frame_count==0


def test_nonoverlap_default_retains_existing_census_and_censoring(tmp_path,monkeypatch):
    root,args,executed=collected(tmp_path,monkeypatch,horizon=2,stride=None,decisions=3)
    result=module.verify_sequence_target_channels(root,**args)
    assert [r.measurement.observed_steps for r in result]==[2,1]
    assert [r.measurement.frames for r in result]==[4,2]
    assert result[0].targets.known==(True,True,True,True,True,True,False)
    assert not any(result[1].targets.known) and executed==[2,4,6]


@pytest.mark.parametrize('bad_start',[-1,True,4,999])
def test_window_bounds_fail_closed_even_after_a_reconstruction_seam_fault(tmp_path,monkeypatch,bad_start):
    root,args,_=collected(tmp_path,monkeypatch)
    reconstruct=module.reconstruct_sequence_candidates
    def wrong_start(*a,**kw):
        candidates=list(reconstruct(*a,**kw))  # Original authority first verifies all actual records.
        path=root/'episode/sequence/window-000.json';window=read(path)
        window['first_model_choice']=bad_start;path.write_text(json.dumps(window))
        # Explicit fault injection tests the independent join bounds, not native authority.
        candidates[0]=replace(candidates[0],window_sha256=canonical_sha256(window))
        return tuple(candidates)
    monkeypatch.setattr(module,'reconstruct_sequence_candidates',wrong_start)
    with pytest.raises(ValueError,match='window (start or size is invalid|exceeds audited boundaries)'):
        module.verify_sequence_target_channels(root,**args)


def test_window_reread_cannot_change_after_reconstruction(tmp_path,monkeypatch):
    root,args,_=collected(tmp_path,monkeypatch)
    reconstruct=module.reconstruct_sequence_candidates
    def changed(*a,**kw):
        candidates=reconstruct(*a,**kw)
        path=root/'episode/sequence/window-000.json';window=read(path)
        window['first_model_choice']=1;path.write_text(json.dumps(window))
        return candidates
    monkeypatch.setattr(module,'reconstruct_sequence_candidates',changed)
    with pytest.raises(ValueError,match='recorded native sequence window differs'):
        module.verify_sequence_target_channels(root,**args)


def test_join_still_requires_every_independently_audited_choice_to_be_covered(tmp_path,monkeypatch):
    root,args,_=collected(tmp_path,monkeypatch,horizon=2,stride=None,decisions=4)
    reconstruct=module.reconstruct_sequence_candidates
    monkeypatch.setattr(module,'reconstruct_sequence_candidates',lambda *a,**kw: reconstruct(*a,**kw)[:1])
    with pytest.raises(ValueError,match='target census differs'):
        module.verify_sequence_target_channels(root,**args)


def test_task_terminal_uses_each_window_start_not_the_episode_origin(tmp_path,monkeypatch):
    root,args,_=collected(tmp_path,monkeypatch)
    reconstruct=module.reconstruct_sequence_candidates
    # The real native seam observes MET_BILL after first choice. A terminal claim
    # on a later overlapping window cannot count that already-completed predicate.
    task='b'*64;args['expected_task_sha256']=task;args['reader'].task_sha256=task
    marker='event:'+str(int(EventFlag.MET_BILL));args['reader'].task_progress=(marker,)
    observed=[]
    def predicate(initial,terminal):
        observed.append((marker in initial,marker in terminal))
        return marker not in initial and marker in terminal
    args['reader'].task_completed=predicate
    def terminal_seam(*a,**kw):
        kw=dict(kw);kw['expected_task_sha256']=None
        original=reconstruct(*a,**kw)  # All actual trace/window/state records remain audited.
        return tuple(replace(c,measurement=replace(c.measurement,end=SequenceEnd.TASK_TERMINAL),
            target_contract=TASK_TERMINAL_TARGET_CONTRACT) for c in original)
    monkeypatch.setattr(module,'reconstruct_sequence_candidates',terminal_seam)
    with pytest.raises(ValueError,match='task-terminal predicate was not newly completed'):
        module.verify_sequence_target_channels(root,**args)
    assert observed==[(False,True),(True,True)]
