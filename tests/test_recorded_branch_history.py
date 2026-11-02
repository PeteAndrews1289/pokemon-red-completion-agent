"""Source-local story experience, with no fit or cartridge execution."""

import json
from dataclasses import replace

import pytest
import test_red_continuous_player as continuous
from test_red_live_option_menu import _binding
from test_red_sequence_receipts import project, read, write

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalManagerRuntimeError
from pokemon_red_completion.recorded_branch_history import recorded_branch_history


@pytest.fixture
def context_run(tmp_path, monkeypatch):
    original = continuous._binding

    def binding(kind, **kwargs):
        row = original(kind, **kwargs)
        return replace(row, story_objective_ref="private:quest-A") if (
            kind is GoalKind.ADVANCE_STORY
        ) else row

    monkeypatch.setattr(continuous, "_binding", binding)
    continuous.test_setback_then_safety_recovery_then_fresh_choice(
        tmp_path, monkeypatch, None, GoalKind.ADVANCE_STORY,
        continuous.GoalFailureReason.RESOURCE_LOST,
    )
    return tmp_path / "run"


def history(episode, boundary, objective="private:quest-A", **changes):
    return recorded_branch_history(episode, **{
        "objective_ref": objective, "boundary_sha256": boundary,
        "expected_source_sha256": episode.source_sha256,
        "expected_plan_sha256": episode.plan_sha256,
        **changes,
    })


def test_metadata_is_private_prechoice_and_does_not_change_policy_fields(context_run):
    intent = read(context_run / "step-000/intent.json")
    assert "private:quest-A" in json.dumps(intent["private_story_contexts"])
    assert "private:quest-A" not in json.dumps(intent["menu"])
    assert intent["menu"]["private_binding_fields"] == 0
    projected = project(context_run)
    assert projected.story_contexts == ("private:quest-A", "private:quest-A")


def test_history_uses_only_strictly_earlier_choices_and_attached_support(context_run):
    p = project(context_run)
    first, second = p.choices
    initial = history(p, first.before_sha256)
    assert initial.attempts == initial.actions == 0
    prior = history(p, second.before_sha256)
    totals = (prior.attempts, prior.actions, prior.frames, prior.observed_cash_debits)
    assert totals == (1, 2, 20, 40)
    unknown_branch = history(p, second.before_sha256, "private:quest-B")
    assert unknown_branch.attempts == 0 and prior.vector() != unknown_branch.vector()
    assert history(p, second.after_sha256).attempts == 2


def test_current_or_future_outcome_cannot_affect_current_history(context_run):
    p = project(context_run)
    boundary = p.choices[-1].before_sha256
    changed = replace(p, choices=(p.choices[0], replace(
        p.choices[1], cash_debits=999, blackouts=5, quests=("future-result",),
    )))
    assert history(changed, boundary) == history(p, boundary)


def test_branch_renaming_changes_no_numeric_features(context_run):
    p = project(context_run)
    renamed = replace(p, story_contexts=("other-title:goal",) * 2)
    at = p.choices[-1].before_sha256
    assert history(p, at).vector() == history(renamed, at, "other-title:goal").vector()
    assert all(type(v) is float and 0 <= v <= 1 for v in history(p, at).vector())


def test_same_source_other_plan_and_foreign_source_are_rejected(context_run):
    p = project(context_run)
    for field in ("expected_source_sha256", "expected_plan_sha256"):
        with pytest.raises(ValueError, match="source/plan"):
            history(p, p.choices[-1].before_sha256, **{field: "f" * 64})


def test_legacy_missing_context_is_unknown_not_inferred_from_later_objective(context_run):
    for file in context_run.glob("step-*/intent.json"):
        doc = read(file)
        doc.pop("private_story_contexts", None)
        write(file, doc)
    p = project(context_run)
    assert p.story_contexts == (None, None)
    result = history(p, p.choices[-1].before_sha256)
    assert result.attempts == 0 and result.unattributed_prior_story_choices == 1


@pytest.mark.parametrize("mutation", ["binding", "length", "duplicate", "type", "nonstory"])
def test_context_binding_tampering_rejected(context_run, mutation):
    file = context_run / "step-000/intent.json"
    doc = read(file)
    entries = doc["private_story_contexts"]
    choice = read(context_run / "step-000/decision.json")["selected_candidate_index"]
    if mutation == "binding":
        entries[choice]["binding_ref"] = "wrong-executor"
    elif mutation == "length":
        entries.pop()
    elif mutation == "duplicate":
        entries[1]["binding_ref"] = entries[0]["binding_ref"]
    elif mutation == "type":
        entries[choice]["objective_ref"] = 9
    else:
        # The recovery action is not a story action even if privately mislabeled.
        file = context_run / "step-001/intent.json"
        doc = read(file)
        started = read(context_run / "step-001/execution-started.json")
        selected = read(context_run / "step-001/decision.json")["selected_candidate_index"]
        count = len(doc["menu"]["menu"]["candidates"])
        doc["private_story_contexts"] = [
            {"binding_ref": f"test-other-{i}", "objective_ref": None} for i in range(count)
        ]
        doc["private_story_contexts"][selected] = {
            "binding_ref": started["selected_binding_ref"], "objective_ref": "wrong-kind",
        }
    write(file, doc)
    with pytest.raises(ValueError):
        project(context_run)


@pytest.mark.parametrize("kind,ref", [
    (GoalKind.DEVELOP_TEAM, "story"), (GoalKind.ADVANCE_STORY, ""),
    (GoalKind.ADVANCE_STORY, True),
])
def test_binding_context_requires_nonempty_story_reference(kind, ref):
    with pytest.raises(GoalManagerRuntimeError, match="story context"):
        replace(_binding(kind, binding_ref="binding", calls=[]), story_objective_ref=ref)


def test_boundary_cannot_be_missing_or_ambiguous(context_run):
    p = project(context_run)
    with pytest.raises(ValueError, match="boundary"):
        history(p, "f" * 64)
    ambiguous = replace(p, choices=(p.choices[0], replace(
        p.choices[1], before_sha256=p.choices[0].before_sha256,
    )))
    with pytest.raises(ValueError, match="ambiguous"):
        history(ambiguous, p.choices[0].before_sha256)


def test_private_context_changes_neither_policy_menu_nor_executor():
    from test_red_player_story_menu import branches, menu

    original = branches()
    tagged = tuple(replace(b, story_objective_ref=f"private-goal-{i}")
                   for i, b in enumerate(original))
    _, before = menu(original)
    _, after = menu(tagged)
    assert before.menu.policy_dict() == after.menu.policy_dict()
    for a, b in zip(original, tagged, strict=True):
        assert a.execute is b.execute and a.verify is b.verify


def test_context_is_written_before_selection_and_execution(tmp_path, monkeypatch):
    runner = continuous.runner
    events = []
    original_record = runner._record
    original_binding = continuous._binding

    def record(path, payload):
        if path.name == "intent.json":
            events.append("intent")
            if path.parent.name == "step-000":
                assert "private_story_contexts" in payload
        elif path.name == "decision.json":
            assert events[-1] == "intent"
            events.append("decision")
        elif path.name == "execution-started.json":
            assert events[-1] == "decision"
            events.append("execution")
        original_record(path, payload)

    def binding(kind, **kwargs):
        b = original_binding(kind, **kwargs)
        return replace(b, story_objective_ref="private-goal") if (
            kind is GoalKind.ADVANCE_STORY
        ) else b

    monkeypatch.setattr(runner, "_record", record)
    monkeypatch.setattr(continuous, "_binding", binding)
    continuous.test_setback_then_safety_recovery_then_fresh_choice(
        tmp_path, monkeypatch, None, GoalKind.ADVANCE_STORY,
        continuous.GoalFailureReason.RESOURCE_LOST,
    )
    assert events == ["intent", "decision", "execution"] * 3
