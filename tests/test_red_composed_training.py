from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from test_red_switch_control_examples import composed_case

from pokemon_red_completion.red_composed_training import (
    ControlProposalTable,
    composed_stage_inputs,
    composed_switch_inventory,
    control_proposal_tables,
    fit_composed_once,
    whole_metrics,
)
from pokemon_red_completion.red_trainer_budgeted_fit import (
    RegretBudget,
    fit_budgeted_head,
    selected_regret,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel


def chooser():
    return TrainerHeadModel("two", ("x", "y"), np.eye(2), np.zeros(2), np.array([0.0, 1.0]), 1)


def pair(value):
    return TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (1,), mean_returns=(-10.0, float(value)))


@pytest.mark.parametrize("seed", range(8))
def test_compiled_control_regret_matches_actual_pipeline_for_any_switch(seed):
    target, model = composed_case()
    rng = np.random.default_rng(seed)
    changed = replace(
        model, switch=replace(model.switch, weights2=rng.normal(size=model.switch.weights2.shape))
    )
    tables = control_proposal_tables([target], model)
    inventory = composed_switch_inventory(tables, model.control)
    assert inventory.regret(changed.switch) == pytest.approx(
        whole_metrics(changed, [target])["control"]["regret"], abs=1e-12
    )
    observed = target["heads"]["control"]["returns"]
    assert all(v in observed for t in tables for p in t.control_pairs for v in p.mean_returns)


def test_singleton_cost_and_original_group_denominator_are_preserved():
    switch = chooser()
    a = ControlProposalTable(((1.0, 0.0), (0.0, 1.0)), (pair(8), pair(2)), 10.0)
    b = ControlProposalTable(((1.0, 0.0),), (pair(1),), 7.0)
    inventory = composed_switch_inventory((a, b), chooser())
    assert len(inventory.cases) == 1 and inventory.control_contexts == 2
    assert inventory.offset == 4
    assert inventory.regret(switch) == 7  # ((10-2)+(7-1))/2
    alone = composed_switch_inventory((b,), chooser())
    assert not alone.cases and alone.regret(switch) == 6


def test_actual_controller_not_perfect_controller_determines_returns():
    switch = chooser()
    pair0 = TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (0,), mean_returns=(9.0, -5.0))
    table = ControlProposalTable(((1.0, 0.0), (0.0, 1.0)), (pair0, pair0), 9.0)
    inventory = composed_switch_inventory((table,), chooser())
    assert inventory.regret(switch) == 14


def test_control_only_contexts_supply_switch_retention():
    target, model = composed_case()
    del target["heads"]["switch"]
    tables = control_proposal_tables([target], model)
    assert tables and composed_switch_inventory(tables, model.control).cases
    head, fresh, _, budgets = composed_stage_inputs(
        model, model, [target], {"anchors": [target]}, "composed_switch"
    )
    assert head == "switch" and fresh
    assert [b.name for b in budgets] == ["control/anchors"]


def test_switch_only_improvement_that_destroys_control_is_a_violation():
    initial = chooser()
    reversed_switch = replace(initial, weights2=-initial.weights2)
    explicit = TrainerHeadExample(((1.0, 0.0), (0.0, 1.0)), (0,), mean_returns=(5.0, 0.0))
    table = ControlProposalTable(explicit.candidate_vectors, (pair(-10), pair(10)), 10.0)
    inventory = composed_switch_inventory((table,), chooser())
    assert selected_regret(reversed_switch, (explicit,)) < selected_regret(initial, (explicit,))
    assert inventory.regret(initial) == 0 and inventory.regret(reversed_switch) == 20
    child, receipt = fit_budgeted_head(
        initial,
        (explicit,),
        (explicit,),
        (RegretBudget("actual-control", inventory.cases, 0, inventory.offset),),
        epochs=30,
        learning_rate=0.05,
        update_rule="joint_ranking_v1",
    )
    assert inventory.regret(child) == 0 and all(h["feasible"] for h in receipt["history"])


@pytest.mark.parametrize("rule", ["joint_ranking_v1", "joint_ranking_curvature_v1"])
def test_compatible_composed_correction_really_learns(rule):
    initial = TrainerHeadModel(
        "three", ("x", "y", "z"), np.eye(3) * 0.1, np.zeros(3), np.array([-0.5, 0.01, 1.0]), 1
    )
    old = ControlProposalTable(((0.0, 0.0, 1.0), (0.0, 0.0, -1.0)), (pair(10), pair(0)), 10.0)
    new = ControlProposalTable(((1.0, 0.0, 0.0), (0.0, 0.0, 0.0)), (pair(10), pair(0)), 10.0)
    oi = composed_switch_inventory((old,), chooser())
    ni = composed_switch_inventory((new,), chooser())
    child, r = fit_budgeted_head(
        initial,
        ni.cases,
        oi.cases,
        (RegretBudget("control/old", oi.cases, 0, oi.offset),),
        epochs=80,
        learning_rate=0.05,
        update_rule=rule,
    )
    assert ni.regret(initial) == 10 and ni.regret(child) == oi.regret(child) == 0
    assert r["accepted_steps"] > 0


def test_decline_single_proposal_and_no_control_context():
    target, model = composed_case()
    target["legacy_model_input"] = None
    target["heads"] = {
        "control": {
            "choice_refs": ["pokemon.core:battle:decline-switch", "pokemon.core:battle:switch:2"],
            "returns": [2.0, -1.0],
            "best_indices": [0],
        }
    }
    tables = control_proposal_tables([target], model)
    assert tables[0].control_pairs[0].mean_returns == (2.0, -1.0)
    assert not composed_switch_inventory(tables, model.control).cases
    target, model = composed_case()
    del target["heads"]["control"]
    assert control_proposal_tables([target], model) == ()


def test_source_admission_rejects_development_and_mutation():
    target, model = composed_case()
    original = deepcopy(target)
    weights = model.to_dict()
    control_proposal_tables([target], model)
    assert target == original and model.to_dict() == weights
    target["partition"] = "development"
    with pytest.raises(ValueError):
        control_proposal_tables([target], model)


@pytest.mark.parametrize("rule", ["joint_ranking_v1", "joint_ranking_curvature_v1"])
def test_three_stage_fit_is_bounded_and_frozen_components_stay_unchanged(rule):
    target, model = composed_case()
    child, r = fit_composed_once(
        model, [target], {"anchors": [target]}, epochs=2, switch_update_rule=rule
    )
    assert r["fits"] == 1
    assert set(r["stages"]) == {"control_coverage", "composed_switch", "control_finish"}
    assert all(len(s["fit"]["steps"]) <= 2 for s in r["stages"].values())
    assert r["stages"]["composed_switch"]["fit"]["update_rule"] == rule
    assert r["stages"]["control_coverage"]["fit"]["update_rule"] == "joint_ranking_v1"
    assert child.move.to_dict() == model.move.to_dict()
    assert child.damage_reference.to_dict() == model.damage_reference.to_dict()
    assert not r["retention_regressions"]


def test_timing_means_not_cached_summary_supply_values():
    target, model = composed_case()
    head = target["heads"]["control"]
    head["timing_returns"] = [[v + 2 for v in head["returns"]], [v + 4 for v in head["returns"]]]
    tables = control_proposal_tables([target], model)
    assert tables[0].best_full_return == max(head["returns"]) + 3
