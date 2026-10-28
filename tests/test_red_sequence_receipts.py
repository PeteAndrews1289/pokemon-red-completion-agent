"""Project real runner-shaped, ROM-free fixtures; no native training admission."""

import json
import shutil
from hashlib import sha256

import pytest
from test_red_continuous_player import (
    test_setback_then_safety_recovery_then_fresh_choice as build_run,
)

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.player_short_sequence import SequenceEnd, measure_sequence
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_sequence_receipts import read_sequence_receipts


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def episode(tmp_path, monkeypatch):
    build_run(tmp_path, monkeypatch, None, GoalKind.ADVANCE_STORY, GoalFailureReason.RESOURCE_LOST)
    return tmp_path / "run"


def project(path, **kwargs):
    return read_sequence_receipts(path, **{
        "expected_plan_sha256": canonical_sha256(read(path / "plan.json")),
        "expected_result_sha256": canonical_sha256(read(path / "result.json")),
        "source_sha256": sha256((path / "step-000/before.state").read_bytes()).hexdigest(),
        **kwargs,
    })


def change_row(path, ordinal, mutate):
    file = path / f"step-{ordinal:03d}/outcome.json"
    row = read(file)
    mutate(row)
    write(file, row)
    result = read(path / "result.json")
    result["outcomes"][ordinal] = row
    write(path / "result.json", result)


def test_existing_runner_records_attach_support_cost_once(episode):
    before_bytes = {p: p.read_bytes() for p in episode.rglob("*") if p.is_file()}
    result = project(episode)
    assert len(result.choices) == 2 and result.support_steps == 1
    assert [(s.actions, s.frames, s.cash_debits) for s in result.choices] == [
        (2, 20, 40), (1, 10, 20),
    ]
    assert result.leading_support_actions == 0
    assert result.choices[0].after_sha256 == result.choices[1].before_sha256
    assert not result.training_eligible and result.native_verification_required
    assert not result.loss_accounting_complete and not result.executor_ownership_verified
    assert all(p.stages == (None, None, None, None) for p in result.previews)
    window = measure_sequence(
        result.choices, horizon=2, end=SequenceEnd.HORIZON, initial_quests=result.initial_quests,
    )
    assert window.cash_debits == 60 and window.completed_quests == 0
    assert window.cash_accounting_basis == "sum_of_observed_boundary_changes_not_gross_flows"
    assert before_bytes == {p: p.read_bytes() for p in episode.rglob("*") if p.is_file()}


def test_choice_identity_excludes_future_outcome_and_future_preview_stays_unknown(episode):
    first = project(episode)
    change_row(
        episode, 2, lambda r: r["after"].update(completed_objectives=["first", "later quest"]),
    )
    second = project(episode)
    assert first.previews == second.previews
    assert [s.decision_sha256 for s in first.choices] == [s.decision_sha256 for s in second.choices]
    assert second.choices[-1].quests == ("first", "later quest")


@pytest.mark.parametrize("kind", ["income", "debit"])
def test_signed_cash_change_is_preserved_without_inventing_gross_flows(episode, kind):
    def mutate(row):
        delta = -100 if kind == "income" else 100
        row["after"]["cash"] = row["before"]["cash"] - delta
        row["measured_cost"]["cash_spent"] = delta
        row["observed_cost"]["cash_spent"] = delta
    change_row(episode, 2, mutate)
    result = project(episode)
    last = result.choices[-1]
    assert (last.cash_debits, last.cash_credits) == ((0, 100) if kind == "income" else (100, 0))


@pytest.mark.parametrize("fault", [
    "before_state", "terminal_state", "facts", "intent_state", "execution_state",
    "ordinal", "partial", "cost", "choice", "authority", "error", "progress_loss",
    "menu_digest", "selected_index", "result_omission", "extra_started",
])
def test_malformed_or_spliced_records_cannot_be_projected(episode, fault):
    folder = episode / "step-002"
    if fault in {"before_state", "terminal_state"}:
        name = "before.state" if fault == "before_state" else "terminal.state"
        (folder / name).write_bytes(b"x")
    elif fault in {"intent_state", "execution_state", "menu_digest", "selected_index"}:
        name = "intent.json" if fault == "intent_state" else (
            "decision.json" if fault == "selected_index" else "execution-started.json"
        )
        doc = read(folder / name)
        key = "selected_candidate_index" if fault == "selected_index" else (
            "menu_sha256" if fault == "menu_digest" else "state_sha256"
        )
        doc[key] = 999 if fault == "selected_index" else "f" * 64
        write(folder / name, doc)
        if fault == "selected_index":
            change_row(episode, 2, lambda r: r.update(choice=doc))
    elif fault == "extra_started":
        extra = episode / "step-003"
        extra.mkdir()
        write(extra / "execution-started.json", {})
    elif fault == "result_omission":
        doc = read(episode / "result.json")
        doc["outcomes"].pop()
        write(episode / "result.json", doc)
    else:
        def mutate(row):
            if fault == "facts":
                row["before"]["cash"] += 1
            elif fault == "partial":
                row["after"]["completed_actions"] -= 1
            elif fault == "cost":
                row["observed_cost"]["frames"] += 1
            elif fault == "progress_loss":
                row["after"]["completed_objectives"] = []
            else:
                row.update({
                    "ordinal": {"ordinal": 5}, "choice": {"choice": {}},
                    "authority": {"learning_eligible": False}, "error": {"error": "partial"},
                }[fault])
        change_row(episode, 2, mutate)
    with pytest.raises(ValueError):
        project(episode)


def test_pinned_declarations_and_source_cannot_be_silently_replaced(episode):
    for name in ("expected_plan_sha256", "expected_result_sha256", "source_sha256"):
        with pytest.raises(ValueError):
            project(episode, **{name: "f" * 64})


def test_leading_support_is_not_assigned_to_a_future_model_choice(episode, tmp_path):
    target = tmp_path / "leading-support"
    target.mkdir()
    for name in ("plan.json", "result.json"):
        shutil.copyfile(episode / name, target / name)
    rows = []
    for new, old in enumerate((1, 2)):
        folder = target / f"step-{new:03d}"
        shutil.copytree(episode / f"step-{old:03d}", folder)
        row = read(folder / "outcome.json")
        row["ordinal"] = new
        row["after"]["completed_objectives"] = ["first", "support-earned"]
        if new == 1:
            row["before"]["completed_objectives"] = ["first", "support-earned"]
            before = read(folder / "before.json")
            before["facts"] = row["before"]
            write(folder / "before.json", before)
        write(folder / "outcome.json", row)
        rows.append(row)
    result = read(target / "result.json")
    result.update(executed_decisions=2, model_decisions=1, support_decisions=1, outcomes=rows)
    write(target / "result.json", result)
    projected = project(target)
    assert len(projected.choices) == 1 and projected.leading_support_actions == 1
    assert projected.leading_support_debits == 20
    assert projected.choices[0].actions == 1 and projected.choices[0].cash_debits == 20
    assert projected.initial_quests == projected.leading_support_quests
    assert projected.initial_quests == ("first", "support-earned")
    window = measure_sequence(
        projected.choices, horizon=1, end=SequenceEnd.HORIZON,
        initial_quests=projected.initial_quests,
    )
    assert window.completed_quests == 0


def test_nested_logs_do_not_become_additional_choices(episode):
    nested = episode / "step-000" / "nested-battle"
    nested.mkdir()
    write(nested / "outcome.json", {"actions": 99999})
    assert sum(s.actions for s in project(episode).choices) == 3
