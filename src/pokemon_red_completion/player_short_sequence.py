"""ROM-free short-sequence design primitives; not a TRAIN admission interface.

Previews are prospective adapter assertions, never instructions or future truth.
Measured steps must eventually be reconstructed from authenticated native receipts;
constructing these types alone proves no provenance. No executor, model mutation,
target conversion, or existing-policy integration is provided here.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from .player_option_challenge import CHALLENGE_NAMES, OptionChallenge

MAX_SEQUENCE_STEPS = 4
_SHA = re.compile(r"[0-9a-f]{64}")
SEQUENCE_FEATURE_NAMES = ("preview.stage_fraction", "preview.tail_unknown") + tuple(
    f"preview.step_{index}.{name}"
    for index in range(MAX_SEQUENCE_STEPS)
    for name in CHALLENGE_NAMES
)


@dataclass(frozen=True)
class SequencePreview:
    """Bounded information about a possible branch, not a prescribed route.

    None means the challenge at this stage is unknown. A known noncombat stage
    is OptionChallenge(False, False, 0, 0, 0). Padding is identified by length.
    tail_unknown=False asserts that the preview covers the entire known branch;
    it says nothing about success. Native evidence for either assertion is a
    separate adapter responsibility, not inferred by this prototype.
    """

    stages: tuple[OptionChallenge | None, ...]
    tail_unknown: bool

    def __post_init__(self) -> None:
        if (
            type(self.stages) is not tuple
            or not 1 <= len(self.stages) <= MAX_SEQUENCE_STEPS
            or any(s is not None and not isinstance(s, OptionChallenge) for s in self.stages)
            or type(self.tail_unknown) is not bool
        ):
            raise ValueError("invalid bounded sequence preview")

    def vector(self) -> tuple[float, ...]:
        result = [len(self.stages) / MAX_SEQUENCE_STEPS, float(self.tail_unknown)]
        for stage in self.stages:
            result.extend(
                (0.0,) * len(CHALLENGE_NAMES) if stage is None else (
                    1.0, float(stage.combat_required), float(stage.opposition_known),
                    stage.opponent_fraction, stage.maximum_level_deficit,
                    stage.median_level_deficit,
                )
            )
        result.extend([0.0] * ((MAX_SEQUENCE_STEPS - len(self.stages)) * len(CHALLENGE_NAMES)))
        return tuple(result)


def _identities(values: tuple[str, ...]) -> None:
    if (
        type(values) is not tuple
        or any(type(v) is not str or not v for v in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError("invalid private progress identities")


@dataclass(frozen=True)
class MeasuredSequenceStep:
    """One measured decision and its full execution, including nested recovery.

    Never add a nested execution as another step: that would double count cost.
    Private progress identities permit deduplication; they are not model features.
    There is deliberately no immediate-success reward to sum across the window.
    Cash fields are sums of observed boundary changes, not proven gross flows.
    An income and a purchase inside one boundary may offset each other.
    """

    decision_sha256: str
    behavior_model_sha256: str
    before_sha256: str
    after_sha256: str
    actions: int
    frames: int
    cash_debits: int
    blackouts: int
    progress: tuple[str, ...] = ()
    quests: tuple[str, ...] = ()
    cash_credits: int = 0

    def __post_init__(self) -> None:
        for digest in (
            self.decision_sha256, self.behavior_model_sha256,
            self.before_sha256, self.after_sha256,
        ):
            if type(digest) is not str or _SHA.fullmatch(digest) is None:
                raise ValueError("invalid sequence evidence identity")
        for count in (
            self.actions, self.frames, self.cash_debits, self.cash_credits, self.blackouts,
        ):
            if type(count) is not int or count < 0:
                raise ValueError("invalid measured sequence cost")
        if self.frames < self.actions:
            raise ValueError("sequence frames cannot be less than controller actions")
        _identities(self.progress)
        _identities(self.quests)


class SequenceEnd(StrEnum):
    HORIZON = "horizon"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class SequenceMeasurement:
    """Observed continuation under one recorded policy, not a causal arm effect.

    Raw totals stay available for interrupted prefixes. A prefix is not eligible
    as a full-horizon target. This class itself is never native training evidence.
    """

    first_decision_sha256: str
    behavior_model_sha256: str
    observed_steps: int
    horizon: int
    end: SequenceEnd
    new_progress: int
    completed_quests: int
    actions: int
    frames: int
    cash_debits: int
    blackouts: int
    cash_credits: int

    def __post_init__(self) -> None:
        if any(type(value) is not str or _SHA.fullmatch(value) is None for value in (
            self.first_decision_sha256, self.behavior_model_sha256,
        )):
            raise ValueError("invalid measured sequence identity")
        if (
            type(self.horizon) is not int or not 1 <= self.horizon <= MAX_SEQUENCE_STEPS
            or type(self.observed_steps) is not int
            or not 1 <= self.observed_steps <= self.horizon
            or not isinstance(self.end, SequenceEnd)
            or self.end is SequenceEnd.HORIZON and self.observed_steps != self.horizon
        ):
            raise ValueError("invalid measured sequence horizon")
        if any(type(value) is not int or value < 0 for value in (
            self.new_progress, self.completed_quests, self.actions, self.frames,
            self.cash_debits, self.cash_credits, self.blackouts,
        )) or self.frames < self.actions:
            raise ValueError("invalid measured sequence totals")

    @property
    def cash_accounting_basis(self) -> str:
        return "sum_of_observed_boundary_changes_not_gross_flows"

    @property
    def complete_window(self) -> bool:
        return self.end is SequenceEnd.HORIZON and self.observed_steps == self.horizon


def measure_sequence(
    steps: tuple[MeasuredSequenceStep, ...],
    *,
    horizon: int,
    end: SequenceEnd,
    initial_progress: tuple[str, ...] = (),
    initial_quests: tuple[str, ...] = (),
) -> SequenceMeasurement:
    """Aggregate an actual contiguous prefix; no counterfactual or bootstrap.

    Limits and start boundary must be declared prospectively by the future
    collector. This pure function cannot authenticate that declaration or prove
    independence, and does not admit data into the existing training pipeline.
    """
    if (
        type(horizon) is not int or not 1 <= horizon <= MAX_SEQUENCE_STEPS
        or type(steps) is not tuple or not 1 <= len(steps) <= horizon
        or any(not isinstance(s, MeasuredSequenceStep) for s in steps)
        or not isinstance(end, SequenceEnd)
    ):
        raise ValueError("invalid measured sequence horizon")
    if end is SequenceEnd.HORIZON and len(steps) != horizon:
        raise ValueError("partial sequence cannot claim complete horizon")
    _identities(initial_progress)
    _identities(initial_quests)
    if len({s.decision_sha256 for s in steps}) != len(steps):
        raise ValueError("sequence repeats a decision")
    if len({s.behavior_model_sha256 for s in steps}) != 1:
        raise ValueError("sequence changes continuation policy")
    if any(a.after_sha256 != b.before_sha256 for a, b in zip(steps, steps[1:], strict=False)):
        raise ValueError("sequence state continuity differs")
    progress = {p for s in steps for p in s.progress} - set(initial_progress)
    quests = {q for s in steps for q in s.quests} - set(initial_quests)
    return SequenceMeasurement(
        first_decision_sha256=steps[0].decision_sha256,
        behavior_model_sha256=steps[0].behavior_model_sha256,
        observed_steps=len(steps), horizon=horizon, end=end,
        new_progress=len(progress), completed_quests=len(quests),
        actions=sum(s.actions for s in steps), frames=sum(s.frames for s in steps),
        cash_debits=sum(s.cash_debits for s in steps), blackouts=sum(s.blackouts for s in steps),
        cash_credits=sum(s.cash_credits for s in steps),
    )
