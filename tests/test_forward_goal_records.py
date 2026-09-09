from copy import deepcopy

import pytest

from pokemon_red_completion.forward_goal import (
    ForwardGoalChoice,
    ForwardGoalCounters,
    ForwardGoalPlan,
    ForwardGoalRecorder,
)
from pokemon_red_completion.forward_goal_records import (
    read_forward_goal_events,
    restore_forward_goal_choice,
    restore_forward_goal_model,
    restore_forward_goal_outcome,
    restore_forward_goal_plan,
)


def recorded(*, reached=True, interrupted=False):
    plan = ForwardGoalPlan("resource-goal", "a" * 64, "b" * 64, 100, 1000, 2, 2)
    choice = ForwardGoalChoice(
        "c" * 64,
        "d" * 64,
        "train",
        ("energy",),
        (0.2,),
        ("restore",),
        ((0.0,), (1.0,)),
        1,
        (0.4, 0.6),
    )
    events = []
    recorder = ForwardGoalRecorder(plan, events.append)
    recorder.declare(initial_goal=False)
    recorder.anchor(choice)
    recorder.observe(ForwardGoalCounters(10, 100, 1, 1), goal=False)
    recorder.observe(
        ForwardGoalCounters(30, 300, 1, 2),
        goal=None if interrupted else reached,
        interrupted=interrupted,
    )
    return plan, events


@pytest.mark.parametrize("reached", [True, False])
def test_real_recorded_sequence_reconstructs_literal_goal_and_total_cost(reached):
    plan, events = recorded(reached=reached)
    outcome = read_forward_goal_events(events, expected_plan=plan)
    assert outcome.target == pytest.approx((float(reached), 11 / 30))
    assert outcome.counters.actions == 30 and outcome.counters.resources == 1
    assert outcome.choice.context == (0.2,) and outcome.choice.selected_index == 1


def test_interrupted_terminal_never_decodes_a_fit_label():
    plan, events = recorded(interrupted=True)
    outcome = read_forward_goal_events(events, expected_plan=plan)
    assert outcome.target is None and outcome.observed_goal is None and outcome.censored
    assert outcome.counters.frames == 300


@pytest.mark.parametrize("keep", [0, 1, 2, 3])
def test_incomplete_forward_stream_never_becomes_a_settled_example(keep):
    plan, events = recorded()
    with pytest.raises(ValueError):
        read_forward_goal_events(events[:keep], expected_plan=plan)


@pytest.mark.parametrize(
    "damage",
    [
        "swap",
        "duplicate_declaration",
        "late_anchor",
        "extra_terminal",
        "unknown_kind",
        "unknown_field",
        "goal_swap",
        "cost_swap",
        "plan_swap",
        "choice_swap",
        "regressing_actions",
        "regressing_resources",
        "plan_digest",
        "decision_digest",
        "prefix_cost",
        "terminal_kind",
        "counter_extra",
        "censored_label",
    ],
)
def test_mutated_chronology_or_derived_values_are_not_admitted(damage):
    plan, events = recorded(interrupted=damage == "censored_label")
    if damage == "swap":
        events[0], events[1] = events[1], events[0]
    elif damage == "duplicate_declaration":
        events.insert(1, deepcopy(events[0]))
    elif damage == "late_anchor":
        events.insert(3, deepcopy(events[1]))
    elif damage == "extra_terminal":
        events.append(deepcopy(events[-1]))
    elif damage == "unknown_kind":
        events[2]["kind"] = "teacher_success"
    elif damage == "unknown_field":
        events[2]["future_outcome"] = 1
    elif damage == "goal_swap":
        events[-1]["goal"] = False
    elif damage == "cost_swap":
        events[-1]["outcome"]["target"][1] = 0
    elif damage == "plan_swap":
        events[-1]["outcome"]["plan"]["max_resources"] = 99
    elif damage == "choice_swap":
        events[-1]["outcome"]["choice"]["selected_index"] = 0
    elif damage == "regressing_actions":
        events[2]["counters"]["actions"] = 31
    elif damage == "regressing_resources":
        events[2]["counters"]["resources"] = 2
    elif damage == "plan_digest":
        events[1]["plan_sha256"] = "e" * 64
    elif damage == "decision_digest":
        events[2]["decision_sha256"] = "e" * 64
    elif damage == "prefix_cost":
        events[-1]["outcome"]["prefix_cost"] = 0
    elif damage == "terminal_kind":
        events[-1]["outcome"]["terminal"] = "stopped"
    elif damage == "counter_extra":
        events[-1]["counters"]["unused"] = 0
    else:
        events[-1]["outcome"]["target"] = [0, 0]
    with pytest.raises(ValueError):
        read_forward_goal_events(events, expected_plan=plan)


@pytest.mark.parametrize("damage", ["bool", "zero", "extra", "schema"])
def test_plan_decoder_is_strict(damage):
    plan, _ = recorded()
    row = plan.public_dict()
    if damage == "bool":
        row["max_actions"] = True
    elif damage == "zero":
        row["max_frames"] = 0
    elif damage == "extra":
        row["history"] = "pretend"
    else:
        row["schema"] = "old-immediate-schema"
    with pytest.raises(ValueError):
        restore_forward_goal_plan(row)


@pytest.mark.parametrize("damage", ["nan", "tuple", "width", "zero_support", "bool_index"])
def test_choice_decoder_rejects_malformed_or_unexplored_inputs(damage):
    _, events = recorded()
    row = events[1]["choice"]
    if damage == "nan":
        row["context"] = [float("nan")]
    elif damage == "tuple":
        row["context"] = (0.2,)
    elif damage == "width":
        row["candidates"][1].append(0.5)
    elif damage == "zero_support":
        row["probabilities"] = [0, 1]
    else:
        row["selected_index"] = True
    with pytest.raises(ValueError):
        restore_forward_goal_choice(row)


def test_outcome_decoder_keeps_cost_overruns_instead_of_clipping_them():
    plan, events = recorded()
    row = deepcopy(events[-1]["outcome"])
    row["counters"].update(actions=300, frames=3000, resources=6)
    row["target"], row["prefix_cost"] = [0.0, 3.0], 3.0
    outcome = restore_forward_goal_outcome(row)
    assert outcome.observed_goal is True and outcome.target == (0.0, 3.0)


def test_fitted_model_json_round_trip_preserves_predictions_and_shadow_authority():
    import json

    from test_forward_goal_learning import examples, predictions

    from pokemon_red_completion.forward_goal_learning import fit_forward_goal

    original = fit_forward_goal(examples()).model
    restored = restore_forward_goal_model(json.loads(json.dumps(original.public_dict())))
    assert restored == original and restored.sha256 == original.sha256
    assert predictions(restored, 0.25) == predictions(original, 0.25)
    assert restored.public_dict()["authority"] == "unqualified-shadow"


@pytest.mark.parametrize("damage", ["authority", "projection", "heads", "shape", "nan"])
def test_model_loading_rejects_promotion_or_schema_relabeling(damage):
    from test_forward_goal_learning import examples

    from pokemon_red_completion.forward_goal_learning import fit_forward_goal

    row = fit_forward_goal(examples()).model.public_dict()
    if damage == "authority":
        row["authority"] = "live-player"
    elif damage == "projection":
        row["projection"] = "immediate-utility"
    elif damage == "heads":
        row["target_names"].reverse()
    elif damage == "shape":
        row["coefficients"].pop()
    else:
        row["mean"][0] = float("nan")
    with pytest.raises(ValueError):
        restore_forward_goal_model(row)
