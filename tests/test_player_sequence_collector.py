"""Prospective collection under the existing mocked actor, never native fitting."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest
import test_red_continuous_player as continuous
from test_red_sequence_receipts import read

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.player_sequence_collector import SequenceTraceCollector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_sequence_receipts import read_sequence_prefix


def collect(tmp_path, monkeypatch, *, horizon=2, fault=None, partition="development", greedy_fixture=False, declaration_store=None):
    collector = SequenceTraceCollector(
        source_sha256=sha256(b"0").hexdigest(),
        partition=partition,
        horizon=horizon,
        declaration_store=declaration_store,
    )
    original_run = continuous.runner.run_autonomous_options
    original_binding = continuous._binding

    def run(**kwargs):
        if greedy_fixture:
            from pokemon_red_completion.red_live_option_menu import RedLiveOptionSelectionMode
            original_select = continuous.runner.select_red_live_option
            def select(*args, **kw):
                choice = original_select(*args, **kw)
                if choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION:
                    choice = replace(choice, mode=RedLiveOptionSelectionMode.MODEL_GREEDY,
                        scores=tuple(float(j == choice.selected_candidate_index)
                            for j in range(len(choice.scores))),
                        probabilities=tuple(float(j == choice.selected_candidate_index)
                            for j in range(len(choice.probabilities))))
                return choice
            monkeypatch.setattr(continuous.runner, "select_red_live_option", select)
        return original_run(**kwargs, sequence_collector=collector)

    def binding(kind, **kwargs):
        b = original_binding(kind, **kwargs)
        return (
            replace(b, story_objective_ref="private-story")
            if (kind is GoalKind.ADVANCE_STORY)
            else b
        )

    monkeypatch.setattr(continuous.runner, "run_autonomous_options", run)
    monkeypatch.setattr(continuous, "_binding", binding)
    continuous.test_setback_then_safety_recovery_then_fresh_choice(
        tmp_path,
        monkeypatch,
        fault,
        GoalKind.ADVANCE_STORY,
        GoalFailureReason.RESOURCE_LOST,
    )
    return tmp_path / "run", collector


def test_collector_captures_actual_preinput_features_and_attached_recovery(tmp_path, monkeypatch):
    root, collector = collect(tmp_path, monkeypatch)
    first = read(root / "sequence/anchor-000.json")
    second = read(root / "sequence/anchor-001.json")
    window = read(root / "sequence/window-000.json")
    assert len(first["features"]) == len(option_feature_names(6)) + 8
    assert first["previous_outcome_sha256"] == [] and first["features"][-8:] == [0.0] * 8
    assert len(second["previous_outcome_sha256"]) == 2
    assert second["features"][-8] == 0.5  # one prior story choice, not two including healing
    assert "private-story" not in json.dumps(first)
    assert window["complete_window"] and not window["training_eligible"]
    assert window["measurement"]["actions"] == 3
    assert window["measurement"]["frames"] == 30
    assert window["measurement"]["cash_debits"] == 60
    assert window["measurement"]["completed_quests"] == 0
    assert collector.finished
    assert read(root / "sequence/result.json")["projection_error"] is None


def test_window_waits_for_support_and_closes_before_next_model_execution(tmp_path, monkeypatch):
    original_record = continuous.runner._record

    def record(path, document):
        if path.name == "execution-started.json" and path.parent.name == "step-002":
            window = read(path.parent.parent / "sequence/window-000.json")
            assert window["measurement"]["actions"] == 2
            assert window["measurement"]["cash_debits"] == 40
        original_record(path, document)

    monkeypatch.setattr(continuous.runner, "_record", record)
    root, _ = collect(tmp_path, monkeypatch, horizon=1)
    windows = [read(p) for p in sorted((root / "sequence").glob("window-*.json"))]
    assert len(windows) == 2
    assert [w["first_model_choice"] for w in windows] == [0, 1]
    assert sum(w["measurement"]["actions"] for w in windows) == 3


def test_short_prefix_retains_cost_but_is_not_complete(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch, horizon=4)
    window = read(root / "sequence/window-000.json")
    assert not window["complete_window"]
    assert window["measurement"]["end"] == "interrupted"
    assert window["measurement"]["cash_debits"] == 60
    assert window["measurement"]["observed_steps"] == 2


@pytest.mark.parametrize("fault", ["partial", "verdict", "unverified"])
def test_failed_projection_retains_raw_costs_without_inventing_complete_target(
    tmp_path,
    monkeypatch,
    fault,
):
    root, _ = collect(tmp_path, monkeypatch, fault=fault)
    result = read(root / "sequence/result.json")
    assert not result["training_eligible"]
    if fault in {"partial", "verdict"}:
        assert result["projection_error"] is not None and result["windows"] == 0
        assert result["unprojected_observed_costs"][0]["actions"] == 1
    else:
        assert not read(root / "sequence/window-000.json")["complete_window"]
    assert (root / "step-000/outcome.json").is_file()


def test_no_admitted_execution_produces_no_anchor_or_window(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch, fault="budget")
    result = read(root / "sequence/result.json")
    assert result["anchors"] == result["windows"] == 0
    assert (root / "sequence/declaration.json").is_file()


def test_prefix_reader_does_not_open_future_steps_or_final_report(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch)
    plan_sha = canonical_sha256(read(root / "plan.json"))
    digest = canonical_sha256(read(root / "step-000/outcome.json"))
    boundary = read(root / "step-000/outcome.json")["terminal_state_sha256"]
    for path in (root / "result.json", root / "step-001/outcome.json"):
        path.write_text("unreadable future")
    prefix = read_sequence_prefix(
        root,
        expected_plan_sha256=plan_sha,
        source_sha256=sha256(b"0").hexdigest(),
        outcome_sha256=(digest,),
        boundary_sha256=boundary,
    )
    assert len(prefix.choices) == 1 and prefix.choices[0].actions == 1


def test_changed_sealed_past_and_wrong_boundary_fail_closed(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch)
    args = dict(
        expected_plan_sha256=canonical_sha256(read(root / "plan.json")),
        source_sha256=sha256(b"0").hexdigest(),
        outcome_sha256=(canonical_sha256(read(root / "step-000/outcome.json")),),
        boundary_sha256=read(root / "step-000/outcome.json")["terminal_state_sha256"],
    )
    with pytest.raises(ValueError, match="boundary"):
        read_sequence_prefix(root, **{**args, "boundary_sha256": "f" * 64})
    (root / "step-000/outcome.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        read_sequence_prefix(root, **args)


def test_train_annotation_alone_never_admits_or_promotes(tmp_path, monkeypatch):
    root, collector = collect(tmp_path, monkeypatch, partition="train")
    assert read(root / "sequence/declaration.json")["partition"] == "train"
    for path in (root / "sequence").glob("*.json"):
        assert read(path)["training_eligible"] is False
    result = read(root / "sequence/result.json")
    assert result["fit_calls"] == result["promotions"] == 0
    with pytest.raises(ValueError):
        collector.start(root)
    with pytest.raises(ValueError):
        collector.finish()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"horizon": 0},
        {"horizon": 5},
        {"horizon": True},
        {"partition": "sealed"},
        {"source_sha256": "not-a-digest"},
    ],
)
def test_invalid_declaration_rejected(kwargs):
    with pytest.raises(ValueError):
        SequenceTraceCollector(
            **{
                "source_sha256": "a" * 64,
                "partition": "development",
                "horizon": 2,
                **kwargs,
            }
        )


@pytest.mark.parametrize("tamper", [False, True])
def test_native_nested_tuple_evidence_uses_exact_json_identity(tmp_path, tamper):
    from copy import deepcopy

    collector = SequenceTraceCollector(source_sha256="a" * 64, partition="train", horizon=2)
    collector.root = tmp_path
    (tmp_path / "sequence").mkdir()
    step = tmp_path / "step-000"
    step.mkdir()
    outcome = dict(
        ordinal=0,
        observed_cost=dict(actions=1, frames=2, cash_spent=0),
        evidence=dict(party=((28, (10, 20)), (64, (30, 40)))),
    )
    persisted = deepcopy(outcome)
    if tamper:
        persisted["evidence"]["party"] = ((28, (10, 21)), (64, (30, 40)))
    (step / "outcome.json").write_text(json.dumps(persisted))
    if tamper:
        with pytest.raises(ValueError, match="persisted exactly"):
            collector.after_outcome(outcome)
        assert not collector.receipts
    else:
        collector.after_outcome(outcome)
        assert collector.receipts == (canonical_sha256(outcome),)


def test_greedy_model_choices_are_anchored_with_actual_one_hot_probability(tmp_path, monkeypatch):
    # Exercise the passive format with a ROM-free actor fixture. Native selector
    # ownership is independently replayed; this test grants no admission.
    original_record = continuous.runner._record
    def record(path, document):
        if path.name == "plan.json":
            document["greedy_selection"] = True
        original_record(path, document)
    monkeypatch.setattr(continuous.runner, "_record", record)
    root, collector = collect(tmp_path, monkeypatch, greedy_fixture=True)
    assert collector.finished and len(collector.anchors) == 2
    assert all(a["behavior_probability"] == 1.0 for a in collector.anchors)
    assert read(root / "sequence/result.json")["projection_error"] is None
    window = read(root / "sequence/window-000.json")
    assert window["measurement"]["actions"] == 3
    assert window["measurement"]["cash_debits"] == 60
    assert window["training_eligible"] is False


def test_branch_choice_anchor_compares_canonical_json_without_losing_fields(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS
    from test_recurrence_parent_exploration import observed_menu, dispatch_head
    from pokemon_red_completion.red_consequence_choice import select_branch_recovery_live_option
    model, options = observed_menu(seen=True)
    choice = select_branch_recovery_live_option(
        model,
        options, dispatch_head(), objective_ref=("defeat_giovanni", "defeat_misty"),
        seed=17, source_state_sha256="a"*64, greedy_selection=True,
        refine_preparation=True, associate_unique_combat=True,
        explore_on_movement_recurrence=True)
    document=choice.public_dict()
    root=tmp_path/"episode";root.mkdir();step=root/"step-000";step.mkdir()
    (root/"plan.json").write_text(json.dumps(dict(continuous_player=True,
        teacher_actions_allowed=False,model_sha256=choice.model_sha256)))
    (step/"intent.json").write_text(json.dumps(dict(menu=options.public_dict(),state_sha256="a"*64)))
    (step/"decision.json").write_text(json.dumps(document))
    collector=SequenceTraceCollector(source_sha256="a"*64,partition="train",horizon=2,feature_version=16)
    collector.start(root)
    monkeypatch.setattr(collector,"_prefix",lambda *_:NS(choices=()))
    collector.before_execution(ordinal=0,boundary_sha256="a"*64,choice=choice)
    assert len(collector.anchors)==1
    changed=json.loads((step/"decision.json").read_text());changed["scores"][0]+=.01
    (step/"decision.json").write_text(json.dumps(changed))
    collector.anchors.clear()
    with pytest.raises(ValueError,match="pre-input decision differs"):
        collector.before_execution(ordinal=0,boundary_sha256="a"*64,choice=choice)


@pytest.mark.parametrize("fault", [None,"identity","index","score","receipt"])
def test_story_continuation_is_retained_as_support_without_a_model_anchor(tmp_path,monkeypatch,fault):
    from types import SimpleNamespace as NS
    from test_story_kind_commitment import menu, _parent
    from pokemon_red_completion import red_story_kind_commitment as kc
    from pokemon_red_completion.red_sequence_receipts import recorded_story_continuation
    monkeypatch.setattr(kc,"party_fit",lambda _:True)
    parent=_parent(menu(),"private:restore")
    choice,receipt=kc.commit_story_kind(parent,kc.StoryKindCommitment("rescue_fuji"))
    root=tmp_path/"episode";root.mkdir();step=root/"step-000";step.mkdir()
    plan=dict(continuous_player=True,teacher_actions_allowed=False,
        model_sha256=parent.model_sha256,story_kind_commitment=True)
    document=choice.public_dict()
    if fault=="identity":document["model_sha256"]="f"*64
    elif fault=="index":document["selected_candidate_index"]=-1
    elif fault=="score":document["scores"][0]=0.
    elif fault=="receipt":receipt["parent_model_sha256"]="f"*64
    intent=dict(menu=choice.options.public_dict(),state_sha256="a"*64,
        model_sha256=parent.model_sha256)
    for name,value in [("plan.json",plan),("step-000/intent.json",intent),
                       ("step-000/decision.json",document),("step-000/story-kind-commitment.json",receipt)]:
        (root/name).write_text(json.dumps(value))
    if fault:
        with pytest.raises(ValueError,match="story support differs"):
            recorded_story_continuation(step,plan,intent,document)
    else:
        collector=SequenceTraceCollector(source_sha256="a"*64,partition="train",horizon=2)
        collector.start(root)
        monkeypatch.setattr(collector,"_prefix",lambda *_:NS(choices=()))
        monkeypatch.setattr(collector,"_emit",lambda *a,**k:pytest.fail("support prematurely closed a model window"))
        collector.before_execution(ordinal=0,boundary_sha256="a"*64,choice=choice)
        assert collector.anchors==[]


def test_declaration_is_sealed_in_existing_journal_before_first_executor(tmp_path,monkeypatch):
    from test_private_artifacts import _make_store
    _,_,store=_make_store(tmp_path)
    original_record=continuous.runner._record
    checked=[]
    def record(path,document):
        if path.name=="execution-started.json":
            declaration=read(path.parent.parent/"sequence/declaration.json")
            digest=canonical_sha256(declaration)
            sealed=store.find_sealed_record("rnp-sequence-"+digest,
                expected_kind="red_native_sequence_declaration")
            assert sealed is not None and sealed.read()==declaration
            checked.append(path)
        original_record(path,document)
    monkeypatch.setattr(continuous.runner,"_record",record)
    root,collector=collect(tmp_path,monkeypatch,declaration_store=store)
    assert len(checked)==3 and collector.finished
    with pytest.raises(TypeError,match="existing private journal"):
        SequenceTraceCollector(source_sha256="a"*64,partition="train",horizon=2,
            declaration_store={})
