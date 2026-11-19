"""Existing head-free segment continuations stay support, with full costs."""
import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest
from test_story_branch_value import _options, _parent, _story
from pokemon_red_completion.red_story_branch_value import StoryBranchTracker, StoryBranchSegment, refine_story_branch
from pokemon_red_completion.red_sequence_receipts import recorded_story_continuation
from pokemon_red_completion.player_sequence_collector import SequenceTraceCollector


def fixture(tmp_path):
    options = _options([_story("s-a", "objective-a"), _story("s-b", "objective-b")])
    parent = _parent(options, "s-b")
    tracker = StoryBranchTracker()
    decision = refine_story_branch(parent, head=None, tracker=tracker, seed=3,
        segment=StoryBranchSegment("objective-a", 200, 194, 1.0, False, 1), segment_lengths=(200, 200))
    assert decision.deterministic_continuation
    choice = decision.choice()
    receipt = dict(decision.document(), parent_choice=parent.public_dict(), tracker=tracker.document(),
                   objective_refs=[options.binding(i).story_objective_ref for i in decision.story_indices])
    plan = dict(continuous_player=True, teacher_actions_allowed=False, model_sha256=parent.model_sha256,
        story_branch_policy=dict(schema="pokemon.red.story-branch-policy.v1", head=None, head_sha256=None,
                                 exploration_probability=0.0, milestone_commitment=True))
    intent = dict(menu=options.public_dict(), model_sha256=parent.model_sha256, state_sha256="a" * 64,
        private_story_contexts=[dict(binding_ref=b.binding_ref, objective_ref=b.story_objective_ref) for b in options.bindings])
    root=tmp_path/"episode";root.mkdir();step=root/"step-000";step.mkdir()
    return root, step, plan, intent, choice, receipt


@pytest.mark.parametrize("fault", [None, "identity", "index", "score", "probability", "parent", "policy", "objective", "tracker", "segment", "indices"])
def test_branch_support_receipt_is_exact_and_has_no_model_anchor(tmp_path, monkeypatch, fault):
    root, step, plan, intent, choice, receipt = fixture(tmp_path)
    document=choice.public_dict()
    if fault == "identity":document["model_sha256"]="f"*64
    elif fault == "index":document["selected_candidate_index"]=-1
    elif fault == "score":document["scores"][0]=0.0
    elif fault == "probability":document["probabilities"][0]=0.25
    elif fault == "parent":receipt["parent_model_sha256"]="f"*64
    elif fault == "policy":plan["story_branch_policy"]["milestone_commitment"]=False
    elif fault == "objective":receipt["objective_refs"][0]="unrelated"
    elif fault == "tracker":receipt["tracker"]["previous_objective_ref"]="unrelated"
    elif fault == "segment":receipt["segment"]["objective_ref"]="unrelated"
    elif fault == "indices":receipt["story_indices"]=[True]
    for path,doc in [(root/"plan.json",plan),(step/"intent.json",intent),(step/"decision.json",document),(step/"story-branch-private.json",receipt)]:path.write_text(json.dumps(doc))
    if fault:
        with pytest.raises(ValueError):recorded_story_continuation(step, plan, intent, document)
    else:
        assert recorded_story_continuation(step, plan, intent, document)
        collector=SequenceTraceCollector(source_sha256="a"*64,partition="train",horizon=2,feature_version=16)
        collector.start(root)
        monkeypatch.setattr(collector,"_prefix",lambda *_:SimpleNamespace(choices=()))
        monkeypatch.setattr(collector,"_emit",lambda *_args,**_kw:pytest.fail("support closed a model window"))
        collector.before_execution(ordinal=0,boundary_sha256="a"*64,choice=choice)
        assert collector.anchors==[]


@pytest.mark.parametrize("mode", ["no_override", "learned_head", "explored"])
def test_other_branch_choices_are_not_reclassified_as_support(tmp_path, mode):
    root, step, plan, intent, choice, receipt = fixture(tmp_path)
    if mode == "no_override":receipt["selected_candidate_index"]=receipt["parent_selected_candidate_index"]
    elif mode == "learned_head":receipt["head_sha256"]="f"*64
    else:receipt["explored"]=True;receipt["exploration_probability"]=0.1
    (step/"story-branch-private.json").write_text(json.dumps(receipt))
    assert not recorded_story_continuation(step,plan,intent,choice.public_dict())


def test_real_loop_retains_branch_support_cost_and_next_model_choice(tmp_path, monkeypatch):
    from test_recurrence_parent_exploration import observed_menu
    from test_red_continuous_player import facts
    import pokemon_red_completion.red_autonomous_player as runner
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
    model,_ = observed_menu(seen=False)
    state={"n":0};calls=[]
    def execute(ref):
        calls.append(ref);state["n"]+=1
        return GoalExecutionReport(1,10,{})
    options=_options([_story("s-a","objective-a"),_story("s-b","objective-b")],restore=False)
    from test_story_kind_commitment import readiness
    options=replace(options,menu=replace(options.menu,candidates=tuple(replace(c,readiness=readiness())for c in options.menu.candidates)))
    def observe(_):return replace(options,bindings=tuple(replace(b,execute=lambda ref=b.binding_ref:execute(ref))for b in options.bindings))
    def select(_model,opts,**_):return replace(_parent(opts,"s-a" if state["n"]==0 else "s-b"),model_sha256=model.model_sha256)
    def snapshot():
        f=dict(facts(state["n"]),cash=5000)
        if state["n"]>=2:f["completed_objectives"]=list(f["completed_objectives"])+["objective-a"]
        return runner.AutonomousSnapshot(str(state["n"]).encode(),f,True)
    monkeypatch.setattr(runner,"select_red_live_option",select)
    collector=SequenceTraceCollector(source_sha256=sha256(b"0").hexdigest(),partition="development",horizon=2,feature_version=16)
    result=runner.run_autonomous_options(model=model,output=tmp_path/"run",seed=1,maximum_decisions=3,
        snapshot=snapshot,observe=observe,provenance={"source":{"partition":"development"}},
        continuous_player=True,maximum_cash_spent=None,story_milestone_commitment=True,sequence_collector=collector)
    assert result["executed_decisions"]==3, (result.get("stop_reason"),result.get("admission_failure"),result.get("error"))
    assert calls==["s-a","s-a","s-b"]
    assert [r["learning_eligible"]for r in result["outcomes"]]==[True,False,True]
    assert [r["support_role"]for r in result["outcomes"]]==[None,"deterministic_story_continuation",None]
    assert result["model_decisions"]==2 and result["support_decisions"]==1
    assert len(collector.anchors)==2 and collector.finished
    seq=json.loads((tmp_path/"run/sequence/result.json").read_bytes());assert seq["projection_error"]is None
    window=json.loads((tmp_path/"run/sequence/window-000.json").read_bytes())
    assert window["measurement"]["actions"]==3 and window["measurement"]["frames"]==30
