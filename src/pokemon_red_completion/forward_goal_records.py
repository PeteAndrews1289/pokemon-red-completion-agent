"""Strict decoding of prospective forward-goal records, without file authority.

The caller authenticates the containing episode and actual observation evidence.
Replaying these pure records checks chronology, cumulative accounting and targets;
it does not run a game, teacher or actor and cannot turn an old outcome into a new
goal trajectory. All derived fields are recomputed, not trusted from JSON.
"""

from collections.abc import Iterable, Mapping
from typing import cast

from .forward_goal import (
    ForwardGoalChoice,
    ForwardGoalCounters,
    ForwardGoalOutcome,
    ForwardGoalPlan,
    ForwardGoalRecorder,
    ForwardGoalTerminal,
)
from .forward_goal_learning import ForwardGoalModel
from .provenance import canonical_sha256


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise ValueError("forward-goal record must be an object")
    return value


def _same(actual: Mapping[str, object], expected: Mapping[str, object]) -> None:
    if canonical_sha256(actual) != canonical_sha256(expected):
        raise ValueError("forward-goal record fields or derived values differ")


def _tuple(value: object) -> tuple:
    if not isinstance(value, list):
        raise ValueError("forward-goal recorded vector must be a JSON array")
    return tuple(value)


def restore_forward_goal_plan(value: object) -> ForwardGoalPlan:
    row = _mapping(value)
    plan = ForwardGoalPlan(
        cast(str, row.get("goal_family")),
        cast(str, row.get("verifier_sha256")),
        cast(str, row.get("continuation_sha256")),
        cast(int, row.get("max_actions")),
        cast(int, row.get("max_frames")),
        cast(int, row.get("max_resources")),
        cast(int, row.get("max_macros")),
    )
    _same(row, plan.public_dict())
    return plan


def restore_forward_goal_choice(value: object) -> ForwardGoalChoice:
    row = _mapping(value)
    choice = ForwardGoalChoice(
        cast(str, row.get("decision_sha256")),
        cast(str, row.get("root_sha256")),
        cast(str, row.get("partition")),
        _tuple(row.get("context_names")),
        _tuple(row.get("context")),
        _tuple(row.get("candidate_names")),
        tuple(_tuple(candidate) for candidate in _tuple(row.get("candidates"))),
        cast(int, row.get("selected_index")),
        _tuple(row.get("probabilities")),
    )
    _same(row, choice.public_dict())
    return choice


def restore_forward_goal_counters(value: object) -> ForwardGoalCounters:
    row = _mapping(value)
    counters = ForwardGoalCounters(
        *(
            cast(int, row.get(k))
            for k in (
                "actions",
                "frames",
                "resources",
                "macros",
            )
        )
    )
    _same(row, counters.public_dict())
    return counters


def restore_forward_goal_outcome(value: object) -> ForwardGoalOutcome:
    row = _mapping(value)
    outcome = ForwardGoalOutcome(
        restore_forward_goal_plan(row.get("plan")),
        restore_forward_goal_choice(row.get("choice")),
        ForwardGoalTerminal(cast(str, row.get("terminal"))),
        restore_forward_goal_counters(row.get("counters")),
        cast(bool | None, row.get("observed_goal")),
    )
    _same(row, outcome.public_dict())
    return outcome


def restore_forward_goal_model(value: object) -> ForwardGoalModel:
    """Restore exact shadow parameters; loading never grants controller authority."""
    row = _mapping(value)
    model = ForwardGoalModel(
        (
            cast(str, row.get("goal_family")),
            cast(str, row.get("verifier_sha256")),
            cast(str, row.get("continuation_sha256")),
        ),
        _tuple(row.get("context_names")),
        _tuple(row.get("candidate_names")),
        _tuple(row.get("mean")),
        _tuple(row.get("scale")),
        tuple(_tuple(v) for v in _tuple(row.get("coefficients"))),
        _tuple(row.get("intercept")),
        cast(str, row.get("dataset_sha256")),
        cast(int, row.get("settled_examples")),
        cast(int, row.get("censored_examples")),
        cast(float, row.get("ridge")),
        cast(float, row.get("importance_cap")),
    )
    _same(row, model.public_dict())
    return model


def read_forward_goal_events(
    events: Iterable[Mapping[str, object]],
    *,
    expected_plan: ForwardGoalPlan,
) -> ForwardGoalOutcome:
    """Validate one complete, bounded, generic forward stream in recorded order."""
    emitted: list[dict[str, object]] = []
    recorder = ForwardGoalRecorder(expected_plan, emitted.append)
    count = 0
    for count, event in enumerate(events, 1):
        if count > expected_plan.max_macros + 3:
            raise ValueError("forward-goal stream exceeds its declared observation bound")
        row = _mapping(event)
        kind = row.get("kind")
        if kind == "forward_goal_declaration":
            if count != 1:
                raise ValueError("forward-goal declaration must be first")
            recorder.declare(initial_goal=False)
        elif kind == "forward_goal_anchor":
            if count != 2:
                raise ValueError("forward-goal anchor must precede all spending")
            recorder.anchor(restore_forward_goal_choice(row.get("choice")))
        elif kind == "forward_goal_observation":
            declared_outcome = (
                None if row.get("outcome") is None else restore_forward_goal_outcome(row["outcome"])
            )
            recorder.observe(
                restore_forward_goal_counters(row.get("counters")),
                goal=cast(bool | None, row.get("goal")),
                stop=declared_outcome is not None,
                interrupted=(
                    declared_outcome is not None
                    and declared_outcome.terminal is ForwardGoalTerminal.INTERRUPTED
                ),
            )
        else:
            raise ValueError("unknown forward-goal event")
        _same(row, emitted[-1])
    if count < 3 or recorder.outcome is None:
        raise ValueError("forward-goal episode has no durable terminal")
    return recorder.outcome
