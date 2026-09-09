"""Prospective first-choice credit for a finite, independently observed goal.

This is separate from immediate skill-success training. A record describes return
under its declared continuation, not an optimal value or an unchosen alternative.
The recorder has no emulator, policy or file access: its owner supplies observed
monotone counters and a durable append callback. It supplies no historical-episode
converter: the collector must authenticate prospectivity and observed evidence.
The declaration and first choice precede all spending in this recorder.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from .provenance import canonical_sha256

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,79}\Z")


def _positive(value: object, name: str, *, zero: bool = False) -> None:
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError(f"{name} must be a {'nonnegative' if zero else 'positive'} integer")


def _digest(value: object) -> None:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError("forward-goal identity must be a SHA-256 digest")


def _vector(value: object) -> None:
    if (
        not isinstance(value, tuple)
        or not value
        or any(type(x) not in (float, int) or not math.isfinite(x) for x in value)
    ):
        raise ValueError("forward-goal features must be a nonempty finite numeric tuple")


@dataclass(frozen=True, slots=True)
class ForwardGoalPlan:
    """The goal/continuation and fixed denominators, recorded before input.

    ``verifier_sha256`` identifies the semantic target and verifier contract. It
    is provenance only, never a feature. One model supports one such contract.
    Zero resource allowance is valid; any resource spending then exceeds budget.
    The cost proxy is the fixed mean of action, frame and resource use. The
    resource denominator is at least one; zero allowance still forbids spending.
    It is not a substitute for protected-party/specimen guards.
    """

    goal_family: str
    verifier_sha256: str
    continuation_sha256: str
    max_actions: int
    max_frames: int
    max_resources: int
    max_macros: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.goal_family, str) or _NAME.fullmatch(self.goal_family) is None:
            raise ValueError("forward-goal family must be semantic and path-free")
        _digest(self.verifier_sha256)
        _digest(self.continuation_sha256)
        _positive(self.max_actions, "action budget")
        _positive(self.max_frames, "frame budget")
        _positive(self.max_resources, "resource budget", zero=True)
        _positive(self.max_macros, "macro budget")

    @property
    def contract(self) -> tuple[str, str, str]:
        return self.goal_family, self.verifier_sha256, self.continuation_sha256

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.forward-goal-plan.v1",
            "goal_family": self.goal_family,
            "verifier_sha256": self.verifier_sha256,
            "continuation_sha256": self.continuation_sha256,
            "max_actions": self.max_actions,
            "max_frames": self.max_frames,
            "max_resources": self.max_resources,
            "max_macros": self.max_macros,
            "cost_proxy": "fixed-start-budget-mean.v1",
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.public_dict())


@dataclass(frozen=True, slots=True)
class ForwardGoalCounters:
    """Cumulative spending since declaration; never refreshed at a macro boundary."""

    actions: int = 0
    frames: int = 0
    resources: int = 0
    macros: int = 0

    def __post_init__(self) -> None:
        for name in ("actions", "frames", "resources", "macros"):
            _positive(getattr(self, name), name, zero=True)

    def public_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in ("actions", "frames", "resources", "macros")}

    def within(self, plan: ForwardGoalPlan) -> bool:
        return all(
            getattr(self, name) <= getattr(plan, f"max_{name}")
            for name in (
                "actions",
                "frames",
                "resources",
                "macros",
            )
        )

    def exhausted(self, plan: ForwardGoalPlan) -> bool:
        # A zero resource allowance must not prevent a resource-free action.
        return (
            self.actions >= plan.max_actions
            or self.frames >= plan.max_frames
            or self.macros >= plan.max_macros
            or self.resources > plan.max_resources
        )

    def cost(self, plan: ForwardGoalPlan) -> float:
        return (
            math.fsum(
                (
                    self.actions / plan.max_actions,
                    self.frames / plan.max_frames,
                    self.resources / max(1, plan.max_resources),
                )
            )
            / 3
        )


@dataclass(frozen=True, slots=True)
class ForwardGoalChoice:
    """Frozen observed input and first selected option, not a hindsight label.

    Feature schemas are named by the collector and checked again by the fitter.
    Context/candidate interactions are constructed by the model, not by a teacher.
    Identity digests and partition never enter the model's input vector.
    Train anchors require full-support sampling; development may record an honest
    one-hot deterministic probe/policy selection and can never enter the fitter.
    """

    decision_sha256: str
    root_sha256: str
    partition: str
    context_names: tuple[str, ...]
    context: tuple[float, ...]
    candidate_names: tuple[str, ...]
    candidates: tuple[tuple[float, ...], ...]
    selected_index: int
    probabilities: tuple[float, ...]

    def __post_init__(self) -> None:
        _digest(self.decision_sha256)
        _digest(self.root_sha256)
        if self.partition not in {"train", "development"}:
            raise ValueError("forward-goal evidence is train or development only")
        _vector(self.context)
        for names, width in (
            (self.context_names, len(self.context)),
            (self.candidate_names, len(self.candidates[0]) if self.candidates else 0),
        ):
            if (
                not isinstance(names, tuple)
                or len(names) != width
                or len(set(names)) != width
                or any(not isinstance(name, str) or _NAME.fullmatch(name) is None for name in names)
            ):
                raise ValueError("forward-goal feature names differ")
        if not isinstance(self.candidates, tuple) or len(self.candidates) < 2:
            raise ValueError("forward-goal anchor needs two genuine supported options")
        for vector in self.candidates:
            _vector(vector)
            if len(vector) != len(self.candidate_names):
                raise ValueError("forward-goal candidate widths differ")
        if type(self.selected_index) is not int or not 0 <= self.selected_index < len(
            self.candidates
        ):
            raise ValueError("forward-goal selected option differs")
        _vector(self.probabilities)
        if (
            len(self.probabilities) != len(self.candidates)
            or any(not 0 <= p <= 1 for p in self.probabilities)
            or not math.isclose(math.fsum(self.probabilities), 1.0, rel_tol=0, abs_tol=1e-10)
        ):
            raise ValueError("forward-goal probabilities differ")
        if self.probabilities[self.selected_index] <= 0 or (
            self.partition == "train" and any(p <= 0 for p in self.probabilities)
        ):
            raise ValueError("forward-goal train choices need full declared support")

    def public_dict(self) -> dict[str, object]:
        return {
            "decision_sha256": self.decision_sha256,
            "root_sha256": self.root_sha256,
            "partition": self.partition,
            "context_names": list(self.context_names),
            "context": list(self.context),
            "candidate_names": list(self.candidate_names),
            "candidates": [list(row) for row in self.candidates],
            "selected_index": self.selected_index,
            "probabilities": list(self.probabilities),
        }


class ForwardGoalTerminal(StrEnum):
    REACHED = "reached"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class ForwardGoalOutcome:
    plan: ForwardGoalPlan
    choice: ForwardGoalChoice
    terminal: ForwardGoalTerminal
    counters: ForwardGoalCounters
    observed_goal: bool | None

    def __post_init__(self) -> None:
        if not isinstance(self.plan, ForwardGoalPlan) or not isinstance(
            self.choice, ForwardGoalChoice
        ):
            raise ValueError("forward-goal outcome needs its frozen plan and choice")
        if not isinstance(self.terminal, ForwardGoalTerminal) or not isinstance(
            self.counters,
            ForwardGoalCounters,
        ):
            raise ValueError("forward-goal terminal evidence differs")
        if self.censored:
            if self.observed_goal is not None:
                raise ValueError("censored forward-goal evidence cannot carry a terminal label")
        elif type(self.observed_goal) is not bool or (
            (self.terminal is ForwardGoalTerminal.REACHED) != self.observed_goal
        ):
            raise ValueError("settled terminal must agree with its observed goal")

    @property
    def censored(self) -> bool:
        return self.terminal in {ForwardGoalTerminal.INTERRUPTED, ForwardGoalTerminal.UNREADABLE}

    @property
    def target(self) -> tuple[float, float] | None:
        if self.censored:
            return None
        return float(
            bool(self.observed_goal) and self.counters.within(self.plan)
        ), self.counters.cost(self.plan)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.forward-goal-outcome.v1",
            "plan": self.plan.public_dict(),
            "choice": self.choice.public_dict(),
            "terminal": self.terminal.value,
            "counters": self.counters.public_dict(),
            "observed_goal": self.observed_goal,
            "prefix_cost": self.counters.cost(self.plan),
            "target": None if self.target is None else list(self.target),
        }


@dataclass(slots=True)
class ForwardGoalRecorder:
    """Append declaration/anchor/observations; freeze the first durable terminal.

    The append callback must be durable or raise. Callback failure poisons this
    recorder: the owner must stop input and retain diagnostic state, never retry
    an uncertain write in-process. A known durable goal remains known after any
    later checkpoint/report failure. This recorder itself never resumes gameplay.
    """

    plan: ForwardGoalPlan
    append: Callable[[dict[str, object]], None]
    _choice: ForwardGoalChoice | None = field(default=None, init=False)
    _counters: ForwardGoalCounters = field(default_factory=ForwardGoalCounters, init=False)
    _outcome: ForwardGoalOutcome | None = field(default=None, init=False)
    _poisoned: bool = field(default=False, init=False)
    _declared: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.plan, ForwardGoalPlan) or not callable(self.append):
            raise ValueError("forward-goal recorder needs a plan and durable append")

    @property
    def outcome(self) -> ForwardGoalOutcome | None:
        return self._outcome

    def _write(self, event: dict[str, object]) -> None:
        if self._poisoned:
            raise ValueError("forward-goal recorder has an uncertain write")
        try:
            self.append(event)
        except BaseException:
            self._poisoned = True
            raise

    def declare(self, *, initial_goal: bool) -> None:
        if self._declared or type(initial_goal) is not bool or initial_goal:
            raise ValueError("forward goal must be declared once and absent initially")
        self._write({"kind": "forward_goal_declaration", "plan": self.plan.public_dict()})
        self._declared = True

    def anchor(self, choice: ForwardGoalChoice) -> None:
        if (
            not self._declared
            or self._choice is not None
            or not isinstance(choice, ForwardGoalChoice)
        ):
            raise ValueError("forward goal needs one first choice after declaration")
        self._write(
            {
                "kind": "forward_goal_anchor",
                "plan_sha256": self.plan.sha256,
                "choice": choice.public_dict(),
            }
        )
        self._choice = choice

    def observe(
        self,
        counters: ForwardGoalCounters,
        *,
        goal: bool | None,
        stop: bool = False,
        interrupted: bool = False,
    ) -> ForwardGoalOutcome | None:
        if self._choice is None or self._outcome is not None or self._poisoned:
            raise ValueError("forward goal is unanchored, terminal or poisoned")
        if (
            not isinstance(counters, ForwardGoalCounters)
            or type(stop) is not bool
            or type(interrupted) is not bool
        ):
            raise ValueError("forward-goal observation types differ")
        if goal is not None and type(goal) is not bool:
            raise ValueError("forward-goal verifier must return bool or unknown")
        if interrupted and goal is not None:
            raise ValueError("interrupted terminal is unknown, not a substituted observation")
        if any(
            getattr(counters, key) < getattr(self._counters, key)
            for key in (
                "actions",
                "frames",
                "resources",
                "macros",
            )
        ):
            raise ValueError("forward-goal cumulative counters regressed")
        terminal = (
            ForwardGoalTerminal.INTERRUPTED
            if interrupted
            else ForwardGoalTerminal.UNREADABLE
            if goal is None
            else ForwardGoalTerminal.REACHED
            if goal
            else ForwardGoalTerminal.STOPPED
            if stop or counters.exhausted(self.plan)
            else None
        )
        outcome = (
            None
            if terminal is None
            else ForwardGoalOutcome(
                self.plan,
                self._choice,
                terminal,
                counters,
                goal,
            )
        )
        self._write(
            {
                "kind": "forward_goal_observation",
                "plan_sha256": self.plan.sha256,
                "decision_sha256": self._choice.decision_sha256,
                "counters": counters.public_dict(),
                "goal": goal,
                "outcome": None if outcome is None else outcome.public_dict(),
            }
        )
        self._counters = counters
        self._outcome = outcome
        return outcome
