from dataclasses import replace

import pytest

from pokemon_red_completion.population_selection import (
    PopulationMember,
    PopulationTrial,
    propose_sequence_offspring,
    select_population_parents,
)


def cohort():
    members = (
        PopulationMember("baseline", "venue", "a" * 64, 0, True),
        PopulationMember("candidate", "venue", "b" * 64, 0),
    )
    rows = tuple(
        PopulationTrial(
            member.member_id,
            f"case-{i}",
            str(i) * 64,
            i,
            "c" * 64,
            "d" * 64,
            "e" * 64,
            "f" * 64,
            "train",
            True,
            True,
            True,
            False,
            100 if member.baseline else 60,
            10,
            1,
            0,
            100,
            None,
        )
        for member in members
        for i in (1, 2)
    )
    return members, rows


def test_repeated_completed_tasks_rank_full_cost_and_retain_two_parents():
    members, rows = cohort()
    result = select_population_parents(members, rows)
    assert result["parents"] == ["candidate", "baseline"]
    assert result["baseline_retained"] == "baseline" and not result["automatic_runtime_adoption"]
    assert result["ranking"][0]["target_xp"] == 200
    assert result["ranking"][0]["other_party_xp"] is None
    assert result["selection_is_training"]


def test_one_lucky_completion_or_cheap_partial_cannot_outbreed_reliable_parent():
    members, rows = cohort()
    rows = list(rows)
    rows[-1] = replace(rows[-1], completed=False, frames=1)
    result = select_population_parents(members, rows)
    assert result["parents"] == ["baseline"]
    assert result["ranking"][1]["total_frames"] == 61


def test_all_incomplete_returns_no_parent_without_success_fallback():
    members, rows = cohort()
    result = select_population_parents(members, [replace(x, completed=False) for x in rows])
    assert result["parents"] == [] and result["no_qualified_parents"]


@pytest.mark.parametrize("partition", ["development", "validation", "test", "sealed"])
def test_parent_selection_never_uses_development_or_final_test(partition):
    _, rows = cohort()
    with pytest.raises(ValueError, match="TRAIN"):
        replace(rows[0], partition=partition)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "different_runtime",
        "different_seed",
        "different_objective",
        "same_source",
    ],
)
def test_mismatched_or_duplicated_cohorts_reject(fault):
    members, rows = cohort()
    rows = list(rows)
    if fault == "missing":
        rows.pop()
    if fault == "duplicate":
        rows.append(rows[0])
    if fault == "different_runtime":
        rows[-1] = replace(rows[-1], runtime_sha256="9" * 64)
    if fault == "different_seed":
        rows[-1] = replace(rows[-1], seed=9)
    if fault == "different_objective":
        rows[-1] = replace(rows[-1], objective_sha256="9" * 64)
    if fault == "same_source":
        rows = [replace(x, source_state_sha256="9" * 64) for x in rows]
    with pytest.raises(ValueError):
        select_population_parents(members, rows)


def test_unverified_native_outcome_is_not_a_qualified_parent():
    members, rows = cohort()
    rows = [replace(x, native_verified=False) if x.member_id == "candidate" else x for x in rows]
    assert select_population_parents(members, rows)["parents"] == ["baseline"]


def test_unsafe_or_crashed_trial_cannot_claim_completion():
    _, rows = cohort()
    with pytest.raises(ValueError):
        replace(rows[0], execution_error=True)
    with pytest.raises(ValueError):
        replace(rows[0], safe_terminal=False)


def sequence_parent():
    from pokemon_red_completion.player_sequence_value import (
        SequenceValueHead,
        sequence_feature_width,
    )

    row = tuple(0.1 for _ in range(sequence_feature_width(6) + 1))
    return SequenceValueHead((row,) * 6 + (None,), (2,) * 6 + (0,), "a" * 64, 1.0, 4, "b" * 64)


def test_proposal_is_reproducible_not_a_fit_and_preserves_unknown_losses():
    parent = sequence_parent()
    before = parent.model_sha256
    child, receipt = propose_sequence_offspring(parent, seed=87)
    assert child == propose_sequence_offspring(parent, seed=87)[0]
    assert child != propose_sequence_offspring(parent, seed=88)[0]
    assert parent.model_sha256 == before and child.model_sha256 != before
    assert child.parameters[6] is None and child.sample_counts == parent.sample_counts
    assert receipt["unfitted_search_proposal"] and receipt["optimizer_fit_calls"] == 0
    assert receipt["new_TRAIN_rows"] == 0 and not receipt["runtime_adopted"]


@pytest.mark.parametrize("value", [0, True, -0.1, 0.2, float("nan")])
def test_mutation_proposal_rejects_unbounded_or_deceptive_scale(value):
    with pytest.raises(ValueError):
        propose_sequence_offspring(sequence_parent(), seed=1, relative_scale=value)
