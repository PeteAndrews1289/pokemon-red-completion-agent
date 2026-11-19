"""Declared task completion/cost must not be displaced by helper surplus."""

from dataclasses import replace

import pytest
from test_party_development_outcomes import _completion, _trial
from test_party_development_workload import _binding, _project

from pokemon_red_completion.party_development_catalog import PartyDevelopmentCatalogError
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE,
    PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE,
    adapt_party_development_outcomes_v2,
)
from pokemon_red_completion.red_teacher_venue import venue_outcome_objective
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeError


def comparison(*, target=True, fault=None):
    menu = _project()
    complete = _completion(registered=11, evolution_steps=0, level_deficit=24)
    fast = _trial(menu, 0, gain=100, frames=1000, completion_after=complete,
                  evolution_completed=True)
    slow = _trial(menu, 1, gain=400, frames=7000,
                  completion_after=replace(complete, level_floor_deficit=23),
                  evolution_completed=True)
    if fault == "fast_partial":
        fast = replace(fast, evolution_completed=False,
                       completion_after=_completion(level_deficit=24))
    if fault == "slow_regression":
        slow = replace(slow, completion_after=replace(complete, living_target_count=8))
    if fault == "both_partial":
        fast = replace(fast, evolution_completed=False, completion_after=_completion())
        slow = replace(slow, evolution_completed=False,
                       completion_after=_completion(level_deficit=24))
    objective = (PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE if target
                 else PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE)
    binding = _binding(menu, objective)
    if fault == "old_binding":
        binding = _binding(menu, PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE)
    return adapt_party_development_outcomes_v2(
        menu, (fast, slow), scenario_id=binding.scenario_id,
        root_lineage_id=binding.root_lineage_id,
        initial_state_sha256=binding.initial_state_sha256, partition=binding.partition,
        prospective_binding=binding, total_task_efficiency=True,
        target_task_efficiency=target,
    )


def test_old_objective_retains_its_helper_surplus_preference():
    assert comparison(target=False).best_candidate_indices == (1,)


def test_opt_in_target_task_prefers_full_cost_before_helper_surplus():
    result = comparison()
    assert result.best_candidate_indices == (0,)
    assert result.objective == PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE
    assert result.outcomes[0].frames_executed == 1000
    assert result.outcomes[1].frames_executed == 7000


@pytest.mark.parametrize("fault,winner", [("fast_partial", 1), ("slow_regression", 0),
                                         ("both_partial", 1)])
def test_completion_safety_and_partial_progress_remain_truthful(fault, winner):
    assert comparison(fault=fault).best_candidate_indices == (winner,)


def test_cannot_relabel_a_prior_binding():
    with pytest.raises(PartyDevelopmentCatalogError, match="objective"):
        comparison(fault="old_binding")


@pytest.mark.parametrize("bad", [1, None, "true"])
def test_new_scope_requires_boolean(bad):
    with pytest.raises(ScenarioOutcomeError, match="explicit total task"):
        comparison(target=bad)
    with pytest.raises(ValueError, match="explicit boolean"):
        venue_outcome_objective({"target_task_efficiency": bad})


def test_teacher_default_and_opt_in_are_separate():
    assert venue_outcome_objective({}) == PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE
    assert venue_outcome_objective({"target_task_efficiency": True}) == (
        PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE
    )
