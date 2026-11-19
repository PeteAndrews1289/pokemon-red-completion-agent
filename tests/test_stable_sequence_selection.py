"""Frozen-score stable selection and narrow observed recurrence escape."""
import json
from dataclasses import replace
import pytest
from test_player_sequence_policy import setup as legacy_setup
from test_recurrence_parent_exploration import observed_menu
from pokemon_red_completion.player_sequence_policy import SequencePolicy,SequenceChoiceContext
from pokemon_red_completion.player_sequence_value import SequenceValueHead,sequence_feature_width
from pokemon_red_completion.recorded_branch_history import RecordedBranchHistory
from pokemon_red_completion.red_live_option_menu import select_red_live_option,RedLiveOptionSelectionMode as Mode
from pokemon_red_completion.red_recorded_selection_authority import record_selection_authority,replay_selection_authority
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit


def fixture(*,seen=False,changed=None,mode="stable_recurrence"):
    model,options=observed_menu(seen=seen,changed=changed)
    params=(0.0,)*(sequence_feature_width(16)+1)
    head=SequenceValueHead((params,)+(None,)*6,(2,)+(0,)*6,"d"*64,1.0,3,model.model_sha256,16)
    policy=SequencePolicy(model.model_sha256,head,(1.0,)+(0.0,)*6,1.0,
                          kind_balanced_exploration=True,selection_mode=mode)
    ctx=SequenceChoiceContext(options.menu.policy_sha256,"c"*64,
                             (RecordedBranchHistory(0,0,0,0,0,0,0,0),)*len(options.bindings),16)
    return model,options,policy,ctx


def choose(model,options,policy,ctx,seed=17):
    return select_red_live_option(model,options,seed=seed,allow_earning_exploration=True,
                                 sequence_policy=policy,sequence_context=ctx)


def test_legacy_document_identity_and_choices_are_unchanged():
    model,options,policy,ctx,_=legacy_setup()
    document=policy.document();assert "selection_mode"not in document
    loaded=SequencePolicy.from_document(document,expected_sha256=policy.model_sha256)
    assert loaded.selection_mode=="sample"and loaded.document()==document
    assert choose(model,options,policy,ctx).public_dict()==choose(model,options,loaded,ctx).public_dict()
    new=replace(policy,selection_mode="stable")
    assert new.model_sha256!=policy.model_sha256 and new.head==policy.head
    assert new.document()["schema"]=="pokemon.player.sequence-policy.v3"
    assert SequencePolicy.from_document(new.document(),expected_sha256=new.model_sha256)==new


@pytest.mark.parametrize("bad",[None,True,1,"greedy","unknown"])
def test_unknown_or_coerced_mode_refused(bad):
    _,_,policy,_,_=legacy_setup()
    with pytest.raises(ValueError):replace(policy,selection_mode=bad)


@pytest.mark.parametrize("changed",["cash","xp","event","item","unknown"])
def test_real_progress_or_unknown_history_preserves_exact_stable_selection(changed):
    model,options,policy,ctx=fixture(seen=True,changed=changed)
    stable=choose(model,options,replace(policy,selection_mode="stable"),ctx)
    escape=choose(model,options,policy,ctx)
    assert stable.mode is escape.mode is Mode.MODEL_GREEDY
    assert stable.selected_candidate_index==escape.selected_candidate_index
    assert stable.scores==escape.scores and stable.probabilities==escape.probabilities
    assert not escape.public_dict()["sequence"]["recurrence_escape_triggered"]


def test_unseen_context_and_recurring_context_use_declared_modes_without_mask():
    for seen in [False,True]:
        model,options,policy,ctx=fixture(seen=seen)
        before=options.public_dict();stable=choose(model,options,replace(policy,selection_mode="stable"),ctx)
        escape=choose(model,options,policy,ctx)
        assert options.public_dict()==before and escape.options is options
        assert stable.mode is Mode.MODEL_GREEDY
        assert escape.mode is (Mode.MODEL_EXPLORATION if seen else Mode.MODEL_GREEDY)
        assert escape.scores==stable.scores
        if seen:
            expected=choose(model,options,replace(policy,selection_mode="sample"),ctx)
            assert escape.selected_candidate_index==expected.selected_candidate_index
            assert escape.probabilities==expected.probabilities
            assert all(escape.probabilities[i]>0 for i in options.menu.available_indices)
        assert escape.public_dict()["sequence"]["recurrence_escape_triggered"]is seen


def test_live_and_recorded_selection_replay_the_same_trigger():
    model,options,policy,ctx=fixture(seen=True)
    choice=choose(model,options,policy,ctx)
    intent=dict(menu=options.public_dict(),model_sha256=policy.model_sha256,
                sequence_context=ctx.document(),selection_seed=17,
                private_selection_authority=record_selection_authority(options,allow_earning_exploration=True))
    assert replay_selection_authority(model,intent,choice.public_dict(),allow_earning_exploration=True,
                                     sequence_policy=policy)==choice.selected_binding.binding_ref
    forged=json.loads(json.dumps(choice.public_dict()))
    forged["sequence"]["recurrence_escape_triggered"]=False
    with pytest.raises(ValueError,match="replay"):
        replay_selection_authority(model,intent,forged,allow_earning_exploration=True,sequence_policy=policy)


def test_native_missing_history_guard_precedes_claim_and_input(tmp_path,monkeypatch):
    from test_red_native_player import setup
    from pokemon_red_completion.red_native_player import run_native_continuous_player
    model,_,policy,_=fixture(mode="stable_recurrence")
    kw,executed=setup(tmp_path,monkeypatch)
    kw.update(model=model,sequence_policy=policy,sequence_horizon=policy.head.horizon)
    with pytest.raises(ValueError,match="observed movement history"):
        run_native_continuous_player(**kw)
    assert executed==[]


@pytest.mark.parametrize("second_seen",[False,None,True])
def test_tied_maximum_requires_every_maximum_to_have_a_recurrence_witness(second_seen):
    from types import SimpleNamespace
    from pokemon_red_completion.red_live_option_menu import _all_maxima_movement_recurrence
    model,options,policy,ctx=fixture(seen=True)
    move=next(c for c in options.menu.candidates if c.story_unit==OptionStoryUnit("movement",True))
    menu=replace(options.menu,candidates=(move,replace(move,binding_ref="other",movement_revisit=second_seen)))
    assert _all_maxima_movement_recurrence(SimpleNamespace(menu=menu),(1.0,1.0))is(second_seen is True)


@pytest.mark.parametrize("mode",["stable","stable_recurrence","stable_costly_recurrence"])
def test_new_modes_run_and_replay_through_real_native_wrapper(tmp_path,monkeypatch,mode):
    import test_red_native_sequence_policy as native_fixtures
    from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace
    old_policy_setup=native_fixtures.policy_setup
    def policy_setup():
        values=list(old_policy_setup())
        if mode in {"stable_recurrence","stable_costly_recurrence"}:
            from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_story_unit
            values[0]=upgrade_option_value_model_for_story_unit(values[0])
            old=values[2]
            parameters=tuple(None if p is None else (0.0,)*(sequence_feature_width(16)+1) for p in old.head.parameters)
            head=replace(old.head,parameters=parameters,feature_version=16,behavior_model_sha256=values[0].model_sha256,dataset_sha256="e"*64)
            values[2]=replace(old,head=head,baseline_sha256=values[0].model_sha256,selection_mode=mode)
        else:values[2]=replace(values[2],selection_mode=mode)
        return tuple(values)
    monkeypatch.setattr(native_fixtures,"policy_setup",policy_setup)
    old_setup=native_fixtures.setup
    def native_setup(*a,**kw):
        args,executed=old_setup(*a,**kw)
        if mode in {"stable_recurrence","stable_costly_recurrence"}:
            args["movement_revisit_saturation"]=True
            import pokemon_red_completion.red_native_player as native
            import pokemon_red_completion.red_player_lesson_runtime as lesson
            old_capture=native.capture_player_lesson_snapshot
            def capture(runtime):
                observation,snapshot=old_capture(runtime)
                observation.raw.event_flags=None
                return observation,snapshot
            monkeypatch.setattr(native,"capture_player_lesson_snapshot",capture)
            monkeypatch.setattr(lesson,"capture_player_lesson_snapshot",capture)
        return args,executed
    monkeypatch.setattr(native_fixtures,"setup",native_setup)
    args,result,executed,audit_args=native_fixtures.run(tmp_path,monkeypatch)
    assert executed==[2,4,6,8,10,12] and result["model_sha256"]==args["sequence_policy"].model_sha256
    audit=audit_native_sequence_trace(args["output"],**audit_args)
    assert audit.recorded_selector_and_binding_replayed==6
    if mode in {"stable_recurrence","stable_costly_recurrence"}:
        origin=args["output"]/"sequence-recurrence-origin.json"
        record=json.loads(origin.read_text());record["policy_sha256"]="f"*64
        origin.write_text(json.dumps(record))
        with pytest.raises(ValueError,match="sealed source"):
            audit_native_sequence_trace(args["output"],**audit_args)


@pytest.mark.parametrize("mode",["stable","stable_recurrence"])
@pytest.mark.parametrize("conditional",[False,True])
def test_v3_behavior_conditional_roundtrip_keeps_all_weights(mode,conditional):
    model,options,policy,context=fixture(mode=mode)
    if conditional:
        policy=replace(policy,head=replace(policy.head,behavior_model_sha256="b"*64),
                       continuation_behavior_sha256="b"*64)
    document=policy.document()
    assert document["off_policy_improvement_verified"] is False
    assert SequencePolicy.from_document(document,expected_sha256=policy.model_sha256)==policy
    assert document["selection_mode"]==mode
    assert policy.scores(model,options.menu,context)==fixture(mode=mode)[2].scores(model,options.menu,context)


def test_malformed_recurrence_scores_fail_closed_with_typed_choice_error():
    from pokemon_red_completion.red_live_option_menu import RedLiveOptionMenuError, _all_maxima_movement_recurrence
    model,options,policy,context=fixture(seen=True)
    assert not _all_maxima_movement_recurrence(options,(None,)*len(options.menu.candidates))
    choice=select_red_live_option(model,options,seed=9,sequence_policy=policy,sequence_context=context)
    with pytest.raises(RedLiveOptionMenuError,match="stable sequence recurrence authority"):
        replace(choice,scores=(None,)*len(options.menu.candidates))
