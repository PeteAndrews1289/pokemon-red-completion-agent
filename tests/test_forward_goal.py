"""ROM-free, literal forward-goal accounting and durable-order regressions."""

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from pokemon_red_completion.forward_goal import (
    ForwardGoalChoice,
    ForwardGoalCounters,
    ForwardGoalOutcome,
    ForwardGoalPlan,
    ForwardGoalRecorder,
    ForwardGoalTerminal,
)


def plan(**changes):
    return replace(ForwardGoalPlan("story", "a" * 64, "b" * 64, 100, 1000, 4, 3), **changes)


def choice(**changes):
    return replace(
        ForwardGoalChoice(
            "c" * 64,
            "d" * 64,
            "train",
            ("pp_deficit",),
            (0.25,),
            ("restore", "effort"),
            ((1.0, 0.1), (0.0, 0.5)),
            1,
            (0.4, 0.6),
        ),
        **changes,
    )


def recorder(**changes):
    events = []
    item = ForwardGoalRecorder(plan(**changes), events.append)
    item.declare(initial_goal=False)
    item.anchor(choice())
    return item, events


def test_declaration_anchor_and_observations_have_durable_order_and_literal_input():
    item, events = recorder()
    assert [event["kind"] for event in events] == [
        "forward_goal_declaration",
        "forward_goal_anchor",
    ]
    assert events[0]["plan"]["cost_proxy"] == "fixed-start-budget-mean.v1"
    assert events[1]["choice"]["context"] == [0.25]
    assert events[1]["choice"]["candidates"] == [[1.0, 0.1], [0.0, 0.5]]
    assert events[1]["choice"]["probabilities"] == [0.4, 0.6]
    assert item.observe(ForwardGoalCounters(10, 200, 1, 1), goal=False) is None
    assert events[-1]["outcome"] is None
    outcome = item.observe(ForwardGoalCounters(30, 500, 2, 2), goal=True)
    assert outcome.target == pytest.approx((1.0, 0.4333333333333333))
    assert [event["kind"] for event in events].count("forward_goal_anchor") == 1
    assert events[-1]["decision_sha256"] == "c" * 64


@pytest.mark.parametrize("initial_goal", [True, None, 0, 1, "false"])
def test_goal_must_be_exactly_false_initially(initial_goal):
    events = []
    item = ForwardGoalRecorder(plan(), events.append)
    with pytest.raises(ValueError):
        item.declare(initial_goal=initial_goal)
    assert events == []


def test_anchor_cannot_precede_declaration_or_be_replaced_by_later_choice():
    events = []
    item = ForwardGoalRecorder(plan(), events.append)
    with pytest.raises(ValueError):
        item.anchor(choice())
    with pytest.raises(ValueError):
        item.observe(ForwardGoalCounters(), goal=False)
    assert events == []
    item.declare(initial_goal=False)
    with pytest.raises(ValueError):
        item.observe(ForwardGoalCounters(1), goal=False)
    item.anchor(choice())
    with pytest.raises(ValueError):
        item.anchor(choice(selected_index=0, decision_sha256="e" * 64))
    with pytest.raises(ValueError):
        item.declare(initial_goal=False)
    assert len(events) == 2


def test_failed_attempt_charges_all_cumulative_spending_not_just_last_macro():
    item, events = recorder()
    item.observe(ForwardGoalCounters(10, 100, 1, 1), goal=False)
    outcome = item.observe(ForwardGoalCounters(40, 500, 3, 2), goal=False, stop=True)
    assert outcome.terminal is ForwardGoalTerminal.STOPPED
    assert outcome.target == pytest.approx((0.0, 0.55))
    assert events[-1]["counters"] == {"actions": 40, "frames": 500, "resources": 3, "macros": 2}
    assert outcome.public_dict()["prefix_cost"] == pytest.approx(0.55)


@pytest.mark.parametrize(
    "counter",
    [
        ForwardGoalCounters(101, 0, 0, 1),
        ForwardGoalCounters(0, 1001, 0, 1),
        ForwardGoalCounters(0, 0, 5, 1),
        ForwardGoalCounters(0, 0, 0, 4),
    ],
)
def test_each_exceeded_budget_blocks_late_success_but_preserves_observed_fact(counter):
    item, _ = recorder()
    outcome = item.observe(counter, goal=True)
    assert outcome.observed_goal is True
    assert outcome.terminal is ForwardGoalTerminal.REACHED
    assert outcome.target[0] == 0.0


def test_exact_budget_completion_is_positive_and_overruns_are_not_clipped():
    item, _ = recorder()
    assert item.observe(ForwardGoalCounters(100, 1000, 4, 3), goal=True).target == (1.0, 1.0)
    late, _ = recorder()
    outcome = late.observe(ForwardGoalCounters(200, 3000, 8, 4), goal=True)
    assert outcome.target == pytest.approx((0.0, 2.3333333333333335))


@pytest.mark.parametrize(
    "counter",
    [
        ForwardGoalCounters(100),
        ForwardGoalCounters(frames=1000),
        ForwardGoalCounters(macros=3),
        ForwardGoalCounters(resources=5),
    ],
)
def test_known_false_goal_at_exhausted_budget_is_settled_failure(counter):
    item, _ = recorder()
    outcome = item.observe(counter, goal=False)
    assert outcome.terminal is ForwardGoalTerminal.STOPPED
    assert outcome.target[0] == 0.0


def test_exact_resource_allowance_does_not_prevent_resource_free_continuation():
    item, _ = recorder()
    assert item.observe(ForwardGoalCounters(10, 100, 4, 1), goal=False) is None
    assert item.observe(ForwardGoalCounters(20, 200, 4, 2), goal=True).target[0] == 1.0


def test_zero_resource_allowance_has_finite_cost_and_allows_resource_free_actions():
    item, _ = recorder(max_resources=0)
    assert item.observe(ForwardGoalCounters(10, 100, 0, 1), goal=False) is None
    outcome = item.observe(ForwardGoalCounters(30, 500, 0, 2), goal=True)
    assert outcome.target == pytest.approx((1.0, 0.26666666666666666))
    forbidden, _ = recorder(max_resources=0)
    outcome = forbidden.observe(ForwardGoalCounters(30, 500, 1, 2), goal=True)
    assert outcome.target[0] == 0.0
    assert outcome.target[1] == pytest.approx(0.6)


def test_zero_resource_budget_cannot_reduce_cost_when_an_extra_item_is_spent():
    declared = plan(max_resources=0)
    before = ForwardGoalCounters(200, 2000, 0, 2).cost(declared)
    after = ForwardGoalCounters(200, 2000, 1, 2).cost(declared)
    assert before == pytest.approx(1.3333333333333333)
    assert after == pytest.approx(1.6666666666666667)
    assert after > before


@pytest.mark.parametrize(
    "interrupted,terminal",
    [
        (False, ForwardGoalTerminal.UNREADABLE),
        (True, ForwardGoalTerminal.INTERRUPTED),
    ],
)
def test_unknown_terminal_retains_prefix_cost_without_failure_or_cost_target(interrupted, terminal):
    item, events = recorder()
    outcome = item.observe(
        ForwardGoalCounters(40, 500, 3, 2),
        goal=None,
        stop=True,
        interrupted=interrupted,
    )
    assert outcome.terminal is terminal
    assert outcome.censored is True and outcome.target is None
    assert outcome.public_dict()["prefix_cost"] == pytest.approx(0.55)
    assert events[-1]["outcome"]["target"] is None
    assert events[-1]["outcome"]["observed_goal"] is None


@pytest.mark.parametrize("interrupted", [False, True])
def test_unreadable_exhausted_budget_does_not_fabricate_failure(interrupted):
    item, _ = recorder()
    outcome = item.observe(
        ForwardGoalCounters(200, 3000, 8, 4),
        goal=None,
        interrupted=interrupted,
    )
    assert outcome.censored is True and outcome.target is None
    assert outcome.public_dict()["prefix_cost"] == pytest.approx(2.3333333333333335)


@pytest.mark.parametrize("goal", [True, False])
def test_interruption_may_not_substitute_a_terminal_label(goal):
    item, events = recorder()
    with pytest.raises(ValueError):
        item.observe(ForwardGoalCounters(10), goal=goal, interrupted=True)
    assert len(events) == 2 and item.outcome is None


def test_first_durable_completion_is_frozen_after_later_reporting_error():
    item, events = recorder()
    first = item.observe(ForwardGoalCounters(30, 500, 2, 2), goal=True)
    try:
        raise OSError("later checkpoint publication failed")
    except OSError:
        with pytest.raises(ValueError):
            item.observe(ForwardGoalCounters(50, 600, 2, 3), goal=None, interrupted=True)
    assert item.outcome is first
    assert first.target == pytest.approx((1.0, 0.4333333333333333))
    assert len(events) == 3


def test_known_failure_cannot_be_replaced_with_later_completion():
    item, events = recorder()
    failed = item.observe(ForwardGoalCounters(20, 200, 0, 1), goal=False, stop=True)
    with pytest.raises(ValueError):
        item.observe(ForwardGoalCounters(30, 300, 0, 2), goal=True)
    assert item.outcome is failed and failed.target[0] == 0.0
    assert len(events) == 3


class AbruptWrite(BaseException):
    """An interrupted durable write need not be an Exception subclass."""


@pytest.mark.parametrize(
    "failed_kind",
    [
        "forward_goal_declaration",
        "forward_goal_anchor",
        "forward_goal_observation",
    ],
)
@pytest.mark.parametrize("error_type", [OSError, AbruptWrite])
@pytest.mark.parametrize("append_before_raising", [False, True])
def test_uncertain_writes_poison_recorder_and_never_retry(
    failed_kind,
    error_type,
    append_before_raising,
):
    events = []
    calls = []
    failure = error_type("uncertain durable append")

    def append(event):
        calls.append(event["kind"])
        if event["kind"] == failed_kind:
            if append_before_raising:
                events.append(event)
            raise failure
        events.append(event)

    item = ForwardGoalRecorder(plan(), append)
    with pytest.raises(error_type) as raised:
        item.declare(initial_goal=False)
        item.anchor(choice())
        item.observe(ForwardGoalCounters(30, 500, 2, 2), goal=True)
    assert raised.value is failure
    assert item.outcome is None  # No claim that a possibly appended terminal was durable.
    previous_calls = list(calls)
    for operation in (
        lambda: item.declare(initial_goal=False),
        lambda: item.anchor(choice()),
        lambda: item.observe(ForwardGoalCounters(30, 500, 2, 2), goal=True),
    ):
        with pytest.raises(ValueError):
            operation()
    assert calls == previous_calls


@pytest.mark.parametrize("name", ["actions", "frames", "resources", "macros"])
def test_each_cumulative_counter_must_be_monotone(name):
    item, events = recorder()
    prior = ForwardGoalCounters(20, 200, 2, 1)
    item.observe(prior, goal=False)
    with pytest.raises(ValueError, match="regressed"):
        item.observe(replace(prior, **{name: getattr(prior, name) - 1}), goal=True)
    assert len(events) == 3 and item.outcome is None
    assert item.observe(prior, goal=True).target == pytest.approx((1.0, 0.3))


@pytest.mark.parametrize(
    "changes",
    [
        {"max_actions": 0},
        {"max_frames": -1},
        {"max_resources": -1},
        {"max_macros": 0},
        {"max_actions": True},
        {"max_frames": 1.0},
        {"max_resources": False},
        {"goal_family": "../story"},
        {"goal_family": ""},
        {"verifier_sha256": "A" * 64},
        {"continuation_sha256": "b" * 63},
    ],
)
def test_plan_strictness(changes):
    with pytest.raises(ValueError):
        plan(**changes)


@pytest.mark.parametrize("name", ["actions", "frames", "resources", "macros"])
@pytest.mark.parametrize("value", [-1, True, 1.0, None])
def test_counter_strictness(name, value):
    with pytest.raises(ValueError):
        ForwardGoalCounters(**{name: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"context": ()},
        {"context": [0.25]},
        {"context": (True,)},
        {"context": (float("nan"),)},
        {"context": (float("inf"),)},
        {"context_names": ("pp_deficit", "extra")},
        {"context_names": ["pp_deficit"]},
        {"candidate_names": ("restore", "restore")},
        {"candidate_names": ("bad/name", "effort")},
        {"candidates": ((1.0, 0.1),)},
        {"candidates": ((1.0, 0.1), (0.0,))},
        {"candidates": ((True, 0.1), (0.0, 0.5))},
        {"candidates": ((1.0, 0.1), (0.0, float("nan")))},
        {"selected_index": True},
        {"selected_index": -1},
        {"selected_index": 2},
        {"probabilities": (0.0, 1.0)},
        {"probabilities": (0.4, 0.5)},
        {"probabilities": (True, False)},
        {"probabilities": (0.4, 0.6, 0.0)},
        {"probabilities": (0.4, float("inf"))},
        {"probabilities": [0.4, 0.6]},
        {"partition": "sealed"},
        {"partition": "test"},
        {"root_sha256": "root"},
    ],
)
def test_choice_features_and_propensities_are_strict(changes):
    with pytest.raises(ValueError):
        choice(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"goal": 1},
        {"goal": "true"},
        {"goal": False, "stop": 1},
        {"goal": None, "interrupted": 1},
    ],
)
def test_observation_flags_are_not_truthy_coercions(changes):
    item, events = recorder()
    with pytest.raises(ValueError):
        item.observe(ForwardGoalCounters(), **changes)
    assert len(events) == 2


@pytest.mark.parametrize(
    "terminal,observed",
    [
        (ForwardGoalTerminal.REACHED, False),
        (ForwardGoalTerminal.STOPPED, True),
        (ForwardGoalTerminal.STOPPED, None),
        (ForwardGoalTerminal.REACHED, 1),
        (ForwardGoalTerminal.INTERRUPTED, False),
        (ForwardGoalTerminal.UNREADABLE, True),
        ("reached", True),
    ],
)
def test_outcome_cannot_mismatch_terminal_evidence(terminal, observed):
    with pytest.raises(ValueError):
        ForwardGoalOutcome(plan(), choice(), terminal, ForwardGoalCounters(), observed)


def test_choice_input_has_no_future_outcome_fields_and_is_frozen():
    anchored = choice()
    assert {field.name for field in fields(anchored)} == {
        "decision_sha256",
        "root_sha256",
        "partition",
        "context_names",
        "context",
        "candidate_names",
        "candidates",
        "selected_index",
        "probabilities",
    }
    before = anchored.public_dict()
    outcome = ForwardGoalOutcome(
        plan(),
        anchored,
        ForwardGoalTerminal.REACHED,
        ForwardGoalCounters(30, 500, 2, 2),
        True,
    )
    assert anchored.public_dict() == before
    assert outcome.public_dict()["choice"] == before
    assert "target" not in before and "observed_goal" not in before
    with pytest.raises(FrozenInstanceError):
        anchored.selected_index = 0
    detached = anchored.public_dict()
    detached["context"][0] = 0.9
    detached["candidates"][0][0] = 42.0
    assert anchored.context == (0.25,) and anchored.candidates[0] == (1.0, 0.1)


def test_provenance_and_future_observations_do_not_change_observed_actor_features():
    first = choice()
    other_identity = choice(
        decision_sha256="e" * 64,
        root_sha256="f" * 64,
        partition="development",
    )
    assert first.context == other_identity.context == (0.25,)
    assert first.candidates == other_identity.candidates == ((1.0, 0.1), (0.0, 0.5))
    first_plan = plan()
    changed_budget = plan(max_actions=200)
    assert first_plan.contract == changed_budget.contract
    assert first_plan.sha256 != changed_budget.sha256
    with pytest.raises(FrozenInstanceError):
        first_plan.max_actions = 200
