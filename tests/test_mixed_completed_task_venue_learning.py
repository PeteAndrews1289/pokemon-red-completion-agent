"""Completed task contracts stay exact while sharing the existing venue loss."""
from dataclasses import replace
import numpy as np
import pytest
from test_venue_matchup_context import fresh_example
from test_party_development_workload import _binding, _project
from test_party_development_outcome_learning import _initialized_model
from pokemon_red_completion.party_development_outcome_learning import (
    adapt_party_development_model_from_outcomes,
    upgrade_party_development_model_for_matchups,
    PartyDevelopmentOutcomeLearningError,
)
from pokemon_red_completion.party_development_outcomes import PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE as EVO
from pokemon_red_completion.party_development_fixed_target_outcomes import FIXED_LEVEL_READY_OBJECTIVE as READY
from pokemon_red_completion.party_development_rank import PartyDevelopmentGoal
from pokemon_red_completion.scenario_lab import ScenarioPartition


def lesson(tag, objective, *, partition=ScenarioPartition.TRAIN):
    menu, original = fresh_example(tag, partition)
    if objective == READY:
        names = menu.feature_names
        candidates = tuple(replace(c, features=tuple(
            1.0 if name == "context.goal.balance" else
            0.0 if name.startswith("context.goal.") else value
            for name, value in zip(names, c.features)
        )) for c in menu.candidates)
        menu = replace(menu, goal=PartyDevelopmentGoal.BALANCE, candidates=candidates)
    binding = _binding(menu, objective, tag=tag, partition=partition)
    outcomes = tuple(replace(o, criterion_values=(1., 1., 1., float(1000 + 1000*i), *((0.,) * (len(objective.criteria)-4))), frames_executed=1000+1000*i) for i, o in enumerate(original.outcomes))
    example = replace(original, objective=objective, candidates=tuple(replace(c, features=m.features) for c, m in zip(original.candidates, menu.candidates)), outcomes=outcomes, prospective_binding_sha256=binding.binding_sha256)
    binding.require_matches(example)
    return menu, example


def model():
    return upgrade_party_development_model_for_matchups(_initialized_model())


def test_mixed_complete_tasks_optin_keeps_original_targets_bindings_and_unknown_scores():
    _, a = lesson("b", EVO)
    _, b = lesson("c", READY)
    before = (a.public_dict(), b.public_dict(), a.example_sha256, b.example_sha256)
    base = model()
    update = adapt_party_development_model_from_outcomes(base, (a, b), refine_suitability=True, include_observed_stats=True, mix_completed_task_costs=True)
    assert before == (a.public_dict(), b.public_dict(), a.example_sha256, b.example_sha256)
    assert a.objective == EVO and b.objective == READY
    assert update.report.loss_after < update.report.loss_before
    assert update.report.training_example_count == 2
    assert update.report.workload_fit["mixed_completed_task_costs"]["unique_fastest_complete_task_required"]
    np.testing.assert_array_equal(update.model.weights1[:78], base.weights1[:78])
    np.testing.assert_array_equal(update.model.bias1, base.bias1)
    np.testing.assert_array_equal(update.model.weights2, base.weights2)
    np.testing.assert_array_equal(update.model.scores(_project()), base.scores(_project()))


def test_original_mixed_objective_default_still_rejects_before_optimization():
    _, a = lesson("b", EVO)
    _, b = lesson("c", READY)
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="objectives differ"):
        adapt_party_development_model_from_outcomes(model(), (a, b), refine_suitability=True, include_observed_stats=True)


@pytest.mark.parametrize("fault", ["forged_objective", "wrong_priority", "incomplete", "unsafe", "cost_mismatch", "tied_cost", "wrong_goal", "duplicate_root", "development", "unmeasured"])
def test_complete_task_mixing_fails_closed_on_incompatible_measurements(fault):
    _, a = lesson("b", EVO)
    _, b = lesson("c", READY, partition=ScenarioPartition.DEVELOPMENT if fault == "development" else ScenarioPartition.TRAIN)
    if fault == "forged_objective":
        b = replace(b, objective=replace(READY, objective_id="unit-forged-objective"))
    elif fault == "wrong_priority":
        b = replace(b, objective=replace(READY, criteria=(READY.criteria[1], READY.criteria[0], *READY.criteria[2:])))
    elif fault in ("incomplete", "unsafe", "cost_mismatch", "tied_cost"):
        o = b.outcomes[0]
        values = list(o.criterion_values)
        if fault == "incomplete": values[2] = 0.
        elif fault == "unsafe": values[0] = 0.
        elif fault == "cost_mismatch": values[3] = 999.
        else:
            values = list(b.outcomes[1].criterion_values)
            b = replace(b, outcomes=(b.outcomes[0], replace(b.outcomes[1], criterion_values=(1.,1.,1.,1000.,*values[4:]), frames_executed=1000)))
        if fault != "tied_cost": b = replace(b, outcomes=(replace(o, criterion_values=tuple(values)), b.outcomes[1]))
    elif fault == "wrong_goal":
        index = b.feature_names.index("context.goal.balance")
        b = replace(b, candidates=tuple(replace(c, features=tuple(0. if i==index else x for i,x in enumerate(c.features)))for c in b.candidates))
    elif fault == "duplicate_root": b = replace(b, root_lineage_id=a.root_lineage_id)
    elif fault == "unmeasured": b = replace(b, outcomes=(None,b.outcomes[1]))
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        adapt_party_development_model_from_outcomes(model(), (a,b), refine_suitability=True, include_observed_stats=True, mix_completed_task_costs=True)


@pytest.mark.parametrize("kw", [dict(mix_completed_task_costs=1),dict(mix_completed_task_costs=True),dict(mix_completed_task_costs=True,refine_suitability=True)])
def test_mixed_cost_training_requires_explicit_boolean_and_observed_stat_scope(kw):
    _, a = lesson("b", EVO)
    _, b = lesson("c", READY)
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        adapt_party_development_model_from_outcomes(model(),(a,b),**kw)


def test_historical_failed_evolution_arm_keeps_false_completion_and_real_physical_cost():
    from pokemon_red_completion.party_development_outcome_learning import _require_examples
    _, a = lesson("b", EVO)
    _, b = lesson("c", READY)
    failure = replace(a.outcomes[0], criterion_values=(1.,1.,0.,0.,*a.outcomes[0].criterion_values[4:]))
    a = replace(a,outcomes=(failure,a.outcomes[1]))
    _require_examples((a,b),partition=ScenarioPartition.TRAIN,feature_schema_id=a.feature_schema_id,mix_completed_task_costs=True)
    assert a.best_candidate_indices == (1,)
    assert a.outcomes[0].criterion_values[2:4] == (0.,0.)
    assert a.outcomes[0].frames_executed == 1000


@pytest.mark.parametrize("fault", ["false_completion_with_completed_cost", "no_completed_arm"])
def test_failed_evolution_cannot_become_cheap_completed_training(fault):
    from pokemon_red_completion.party_development_outcome_learning import _require_examples
    _, a = lesson("b", EVO)
    _, b = lesson("c", READY)
    if fault == "false_completion_with_completed_cost":
        a = replace(a,outcomes=(replace(a.outcomes[0],criterion_values=(1.,1.,0.,1000.,*a.outcomes[0].criterion_values[4:])),a.outcomes[1]))
    else:
        a = replace(a,outcomes=tuple(replace(o,criterion_values=(1.,1.,0.,0.,*o.criterion_values[4:]))for o in a.outcomes))
    with pytest.raises(PartyDevelopmentOutcomeLearningError):
        _require_examples((a,b),partition=ScenarioPartition.TRAIN,feature_schema_id=a.feature_schema_id,mix_completed_task_costs=True)
