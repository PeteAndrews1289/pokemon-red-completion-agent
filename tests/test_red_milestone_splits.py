"""Milestone measurements never infer missing ancestry or alter player facts."""
from copy import deepcopy
import json
import pytest
from pokemon_red_completion.red_milestone_splits import MilestoneSplits,compare_splits,recorded_case_splits

def facts(*goals,owned=()):return dict(completed_objectives=list(goals),owned_species=list(owned))
def recorder(**kwargs):return MilestoneSplits(source_state_sha256='a'*64,**kwargs)
def observe(t,f,n):t.observe(f,frames=n*100,actions=n*10,wall_seconds=n,state_sha256=str(n)*64)
def row(t,key):return next(r for r in t.document()['rows']if r['id']==key)

def test_first_hit_and_preexisting_are_distinct_and_observational():
    t=recorder();initial=facts('defeat_brock');original=deepcopy(initial);observe(t,initial,10)
    assert initial==original
    assert row(t,'defeat_brock')['status']=='already_completed'
    assert row(t,'defeat_brock')['elapsed']is None
    observe(t,facts('defeat_brock','help_bill'),12)
    first=row(t,'help_bill');assert first['elapsed']==dict(frames=200,actions=20,wall_seconds=2.0)
    assert first['interval']['lower']['frames']==0
    observe(t,facts('defeat_brock','help_bill'),14)
    assert row(t,'help_bill')==first
    assert row(t,'defeat_misty')['status']=='pending'

def test_same_observation_has_shared_interval_not_invented_event_order():
    t=recorder();observe(t,facts(),0);observe(t,facts('help_bill','defeat_misty'),3)
    assert row(t,'help_bill')['interval']==row(t,'defeat_misty')['interval']
    assert row(t,'help_bill')['segment']==row(t,'defeat_misty')['segment']
    assert t.document()['observation_resolution']=='first_confirmed_boundary'

def test_full_route_needs_both_story_facts_and_declared_species():
    required=tuple(f'pokemon:national:{n:03d}'for n in range(1,125));t=recorder(required_species=required)
    observe(t,facts(),0);observe(t,facts('defeat_champion',owned=required),1)
    assert row(t,'registrations_124')['status']=='reached'
    assert row(t,'complete_red_124')['status']=='pending'
    observe(t,facts('defeat_champion','enter_hall_of_fame',owned=required),2)
    assert row(t,'complete_red_124')['status']=='reached'
    u=recorder(required_species=required);observe(u,facts(),0)
    observe(u,facts('defeat_champion','enter_hall_of_fame',owned=required[:-1]+('other',)),1)
    assert row(u,'registrations_124')['status']=='pending'

@pytest.mark.parametrize('values',[(-1,0,0),(0,-1,0),(0,0,float('nan')),(False,0,0),(0,0,float('inf'))])
def test_invalid_clocks_refused(values):
    with pytest.raises(ValueError):recorder().observe(facts(),frames=values[0],actions=values[1],wall_seconds=values[2])

def test_clock_reset_requires_new_scope():
    t=recorder();observe(t,facts(),2)
    with pytest.raises(ValueError):observe(t,facts('help_bill'),1)

def test_comparison_requires_same_checkpoint_and_never_awards_failed_run():
    a,b=recorder(),recorder();observe(a,facts(),0);observe(b,facts(),0)
    observe(a,facts('help_bill'),3);observe(b,facts('help_bill'),5)
    c=compare_splits(a.document(),b.document());r=next(x for x in c['rows']if x['id']=='help_bill')
    assert r['delta']['frames']==-200 and not c['completion_or_fitness_claim']
    doc=b.document();doc['source_state_sha256']='b'*64
    with pytest.raises(ValueError):compare_splits(a.document(),doc)
    doc=b.document();doc['wall_basis']='other'
    with pytest.raises(ValueError):compare_splits(a.document(),doc)

def test_recorded_case_uses_phase_clock_and_preserves_preexisting(tmp_path):
    step=tmp_path/'native/episode/step-000';step.mkdir(parents=True)
    o=dict(before=facts('defeat_brock'),after=facts('defeat_brock','help_bill'),before_state_sha256='a'*64,
        terminal_state_sha256='b'*64,phase_seconds=dict(execution=2,menu_and_boundary_observation=5))
    o['before'].update(frames=0,actions=0);o['after'].update(frames=100,actions=10)
    (step/'outcome.json').write_text(json.dumps(o))
    doc=recorded_case_splits(tmp_path,required_species=())
    assert doc['wall_basis']=='sum_recorded_goal_phases'
    rows={r['id']:r for r in doc['rows']};assert rows['help_bill']['elapsed']['wall_seconds']==7
    assert rows['defeat_brock']['status']=='already_completed'

def test_split_files_are_complete_json(tmp_path):
    t=recorder();observe(t,facts(),0);t.write(tmp_path/'splits.json')
    assert json.loads((tmp_path/'splits.json').read_text())==t.document()


def test_native_opt_in_keeps_state_and_policy_facts_unchanged(tmp_path, monkeypatch):
    from test_red_native_player import setup
    import pokemon_red_completion.red_native_player as native
    args,_=setup(tmp_path,monkeypatch)
    args["execution"]=native.NativeExecutionIdentity(args.pop("run_id"),args.pop("arm_id"),
        args.pop("model").model_sha256,args.pop("seed"))
    session=native.NativePlayerSession(**args,record_milestone_splits=True)
    first=session.snapshot()
    assert "milestone_splits" not in first.facts
    assert session.controller.frames_executed==0 and first.state==b"0"
    report=json.loads((session.output/"milestone-splits.json").read_text())
    assert report["scope"]=="checkpoint" and report["observation_resolution"]=="first_confirmed_boundary"
    assert session.snapshot().facts==first.facts


def test_join_passive_segments_retains_earlier_splits_and_ties():
    from pokemon_red_completion.red_milestone_splits import MilestoneSplits, merge_native_segment_splits
    a=MilestoneSplits(source_state_sha256="a",required_species=())
    a.observe(dict(completed_objectives=[],owned_species=[]),frames=0,actions=0,wall_seconds=0)
    a.observe(dict(completed_objectives=["defeat_brock"],owned_species=[]),frames=100,actions=10,wall_seconds=2,state_sha256="b")
    b=MilestoneSplits(source_state_sha256="b",required_species=())
    b.observe(dict(completed_objectives=["defeat_brock"],owned_species=[]),frames=0,actions=0,wall_seconds=0)
    b.observe(dict(completed_objectives=["defeat_brock","help_bill","defeat_misty"],owned_species=[]),frames=200,actions=20,wall_seconds=3,state_sha256="c")
    doc=merge_native_segment_splits([a.document(),b.document()])
    rows={r["id"]:r for r in doc["rows"]}
    assert rows["defeat_brock"]["elapsed"]["frames"]==100
    assert rows["help_bill"]["elapsed"]["frames"]==300
    assert rows["help_bill"]["segment"]["frames"]==200
    assert rows["defeat_misty"]["segment"]==rows["help_bill"]["segment"]
    assert doc["wall_basis"]=="sum_native_segment_wall" and doc["elapsed"]["wall_seconds"]==5
    b.header["source_state_sha256"]="wrong"
    import pytest
    with pytest.raises(ValueError,match="chain"):merge_native_segment_splits([a.document(),b.document()])


def test_failed_execution_keeps_cost_without_inventing_a_verification_time(tmp_path):
    import json,pytest
    from pokemon_red_completion.red_milestone_splits import recorded_case_splits
    step=tmp_path/'native/episode/step-000';step.mkdir(parents=True)
    facts=dict(completed_objectives=[],owned_species=[],actions=0,frames=0)
    outcome=dict(before=facts,after=dict(facts,actions=3,frames=100),before_state_sha256='a',terminal_state_sha256='b',phase_seconds=dict(execution=2.5,verification=None),failure_phase='execution',error_type='RuntimeError',verification=None)
    (step/'outcome.json').write_text(json.dumps(outcome))
    report=recorded_case_splits(tmp_path,required_species=[])
    assert report['elapsed']==dict(actions=3,frames=100,wall_seconds=2.5)
    assert report['unexecuted_phases'][0]['phase']=='verification'
    outcome['failure_phase']='verification';(step/'outcome.json').write_text(json.dumps(outcome))
    with pytest.raises(ValueError,match='unmeasured'):recorded_case_splits(tmp_path,required_species=[])


def test_badge_splits_use_actual_count_when_blaine_precedes_sabrina():
    from pokemon_red_completion.red_milestone_splits import MilestoneSplits,with_badge_count_splits
    goals=['defeat_brock','defeat_misty','defeat_surge','defeat_erika']
    tracker=MilestoneSplits(source_state_sha256='a')
    tracker.observe(dict(completed_objectives=goals,owned_species=[]),frames=0,actions=0,wall_seconds=0)
    for i,goal in enumerate(['defeat_koga','defeat_blaine','defeat_sabrina'],1):
        goals.append(goal);tracker.observe(dict(completed_objectives=goals,owned_species=[]),frames=100*i,actions=i,wall_seconds=i)
    doc=with_badge_count_splits(tracker.document());rows={r['id']:r for r in doc['rows']}
    assert rows['badges_4']['elapsed']is None
    assert rows['badges_6']['elapsed']['frames']==200 and rows['badges_7']['elapsed']['frames']==300
    assert rows['badges_8']['status']=='pending'
    assert rows['defeat_blaine']['label']=='Blaine · Volcano Badge'
    assert with_badge_count_splits(doc)==doc


def test_pending_campaign_has_no_fabricated_clock_and_live_reference_is_descriptive():
    from pokemon_red_completion.red_milestone_splits import pending_milestone_splits,attach_split_reference,MilestoneSplits
    pending=pending_milestone_splits([f'pokemon:national:{n:03d}'for n in range(1,125)])
    assert pending['timing_started']is False and pending['source_state_sha256']is None
    assert all(row['status']=='pending'and not row.get('elapsed')for row in pending['rows'])
    def measured(frames,state='a'):
        tracker=MilestoneSplits(source_state_sha256=state)
        tracker.observe(dict(completed_objectives=[],owned_species=[]),frames=0,actions=0,wall_seconds=0)
        tracker.observe(dict(completed_objectives=['defeat_brock'],owned_species=[]),frames=frames,actions=2,wall_seconds=3)
        return tracker.document()
    baseline=dict(id='campaign-1',milestone_splits=measured(100))
    current=dict(id='campaign-2',milestone_splits=measured(120))
    result=attach_split_reference(current,baseline)
    row=next(r for r in result['milestone_splits']['comparison']['rows']if r['id']=='defeat_brock')
    assert row['delta']['frames']==20
    assert result['milestone_splits']['comparison']['completed_baseline']is False
    assert 'comparison'not in current['milestone_splits']
    mismatch=attach_split_reference(dict(milestone_splits=measured(120,'different')),baseline)
    assert 'milestone_split_comparison_error'in mismatch


def fresh_fixture(tmp_path):
    import hashlib
    root=tmp_path/'fresh';(root/'bootstrap').mkdir(parents=True);(root/'initial').mkdir()
    (root/'bootstrap/power-on.state').write_bytes(b'power-on')
    (root/'initial/terminal.state').write_bytes(b'starter')
    sha=lambda b:hashlib.sha256(b).hexdigest()
    write=lambda p,x:(root/p).write_text(json.dumps(x))
    write('PLAN.json',dict(schema='pokemon.red.fresh-frozen-player-plan.v1',maximum_state_loads=0,campaign_run_id='campaign-one'))
    write('CLAIM.json',dict(no_resume=True,started_new_attempt=True))
    spent=dict(frames=100,actions=10,seconds=2.5)
    context=dict(state_sha256=sha(b'starter'),spent=spent)
    write('initial/CONTEXT.json',context);write('initial/RESULT.json',dict(context,passed=True))
    write('REALIZED-CONFIGURATION.json',dict(origin_sha256=sha(b'power-on'),origin_id='fallback'))
    write('RESULT.json',dict(state_loads=0))
    t=MilestoneSplits(source_state_sha256=sha(b'starter'),wall_basis='sum_native_segment_wall')
    t.observe(facts('choose_starter'),frames=0,actions=0,wall_seconds=0,state_sha256=sha(b'starter'))
    t.observe(facts('choose_starter','help_bill'),frames=250,actions=20,wall_seconds=4,state_sha256='end')
    return root,t.document(),write


def test_fresh_clock_includes_authenticated_opening_and_retains_interval(tmp_path):
    from pokemon_red_completion.red_milestone_splits import fresh_start_split_projection
    root,original,_=fresh_fixture(tmp_path);doc=fresh_start_split_projection(root,original)
    assert original['scope']=='checkpoint' and doc['scope']=='fresh_start'
    assert doc['elapsed']==dict(frames=350,actions=30,wall_seconds=6.5)
    rows={r['id']:r for r in doc['rows']}
    assert rows['choose_starter']['elapsed']['frames']==100
    assert rows['choose_starter']['interval']['lower']['frames']==0
    assert rows['choose_starter']['confirmation']=='verified_opening_boundary'
    assert rows['help_bill']['elapsed']['frames']==350
    assert rows['help_bill']['segment']['frames']==250
    assert doc['wall_basis']=='opening_plus_sum_native_segment_wall'
    assert doc['identity']['campaign_run_id']=='campaign-one'
    assert compare_splits(doc,doc)['completion_or_fitness_claim'] is False
    changed=deepcopy(doc);changed['source_state_sha256']='other'
    with pytest.raises(ValueError,match='physical state'):compare_splits(doc,changed)


@pytest.mark.parametrize('problem',['restored','opening_changed','wrong_checkpoint','wrong_origin'])
def test_fresh_clock_refuses_unverified_ancestry(tmp_path,problem):
    from pokemon_red_completion.red_milestone_splits import fresh_start_split_projection
    root,doc,write=fresh_fixture(tmp_path)
    if problem=='restored':write('RESULT.json',dict(state_loads=1))
    elif problem=='opening_changed':(root/'initial/terminal.state').write_bytes(b'different')
    elif problem=='wrong_checkpoint':doc['source_state_sha256']='wrong'
    else:write('REALIZED-CONFIGURATION.json',dict(origin_sha256='wrong',origin_id='fallback'))
    with pytest.raises(ValueError):fresh_start_split_projection(root,doc)


def test_repair_history_keeps_same_campaign_costs_and_milestones(tmp_path):
    from pokemon_red_completion.red_milestone_splits import fresh_start_split_projection,extend_split_history
    root,doc,_=fresh_fixture(tmp_path);prefix=fresh_start_split_projection(root,doc)
    t=MilestoneSplits(source_state_sha256='end',wall_basis='sum_native_segment_wall',identity=dict(campaign_run_id='campaign-one'))
    t.observe(facts('choose_starter','help_bill'),frames=0,actions=0,wall_seconds=0,state_sha256='end')
    t.observe(facts('choose_starter','help_bill','defeat_brock'),frames=70,actions=3,wall_seconds=5,state_sha256='next')
    current=t.document();result=extend_split_history(current,prefix,campaign_run_id='campaign-one')
    assert result['elapsed']==dict(frames=420,actions=33,wall_seconds=11.5)
    assert result['scope']=='fresh_start' and result['restoration_disclosed'] is True
    rows={r['id']:r for r in result['rows']}
    assert rows['help_bill']['elapsed']['frames']==350
    assert rows['defeat_brock']['elapsed']['frames']==420
    assert rows['defeat_brock']['segment']['wall_seconds']==5
    assert prefix['elapsed']['frames']==350 and current['elapsed']['frames']==70
    other=deepcopy(current);other['identity']['campaign_run_id']='campaign-two'
    with pytest.raises(ValueError,match='different campaign'):extend_split_history(other,prefix,campaign_run_id='campaign-two')
    other=deepcopy(current);other['source_state_sha256']='wrong'
    with pytest.raises(ValueError,match='physical state'):extend_split_history(other,prefix,campaign_run_id='campaign-one')
    other=deepcopy(current);other['wall_basis']='different'
    with pytest.raises(ValueError,match='clock basis'):extend_split_history(other,prefix,campaign_run_id='campaign-one')
    other=deepcopy(current);next(r for r in other['rows']if r['id']=='defeat_misty')['status']='already_completed'
    with pytest.raises(ValueError,match='unmeasured'):extend_split_history(other,prefix,campaign_run_id='campaign-one')
