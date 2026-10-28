"""Separate masked continuation targets, never a native admission interface.

Coverage is a caller-supplied mathematical assumption, NOT an audit certificate.
Native fitting must independently establish it. This module cannot admit records,
fit a model, mutate legacy outcomes or choose actions.
"""

from dataclasses import dataclass

from .player_short_sequence import SequenceMeasurement

SEQUENCE_TARGET_CONTRACT = "observed-fixed-horizon-masked-sequence-v1"
SEQUENCE_TARGET_NAMES = (
    "native_progress", "completed_quests", "actions", "frames",
    "observed_cash_debits", "observed_cash_credits", "battle_losses",
)
SEQUENCE_TARGET_SCALES = (1, 1, 1000, 60000, 1000, 1000, 1)


@dataclass(frozen=True)
class SequenceTargets:
    raw: tuple[int, ...]
    values: tuple[float | None, ...]

    @property
    def known(self) -> tuple[bool, ...]:
        return tuple(value is not None for value in self.values)


def sequence_targets(
    measurement: SequenceMeasurement, *, covered: frozenset[str] = frozenset(),
) -> SequenceTargets:
    """Keep missing/full-horizon-censored labels unknown, not zero-filled.

    Raw prefix totals survive censoring. 'covered' must be established separately
    by the future native auditor; supplying names alone proves no provenance.
    Reported losses must be replaced by complete audited counts before marking
    battle_losses covered. No importance weights or causal claims are inferred.
    """
    if (
        not isinstance(measurement, SequenceMeasurement)
        or type(covered) is not frozenset or not covered <= set(SEQUENCE_TARGET_NAMES)
    ):
        raise ValueError("sequence target contract differs")
    measurement.__post_init__()
    raw = (
        measurement.new_progress, measurement.completed_quests, measurement.actions,
        measurement.frames, measurement.cash_debits, measurement.cash_credits,
        measurement.blackouts,
    )
    return SequenceTargets(raw, tuple(
        value / (value + scale) if measurement.complete_window and name in covered else None
        for name, scale, value in zip(
            SEQUENCE_TARGET_NAMES, SEQUENCE_TARGET_SCALES, raw, strict=True,
        )
    ))
