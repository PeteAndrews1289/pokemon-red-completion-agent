"""Separate masked continuation targets, never a native admission interface.

Coverage is a caller-supplied mathematical assumption, NOT an audit certificate.
Native fitting must independently establish it. This module cannot admit records,
fit a model, mutate legacy outcomes or choose actions.
"""

from dataclasses import dataclass

from .player_short_sequence import SequenceMeasurement

SEQUENCE_TARGET_CONTRACT = "observed-fixed-horizon-masked-sequence-v1"
TASK_TERMINAL_TARGET_CONTRACT = "observed-task-or-horizon-masked-sequence-v2"
RESOURCE_TASK_TARGET_CONTRACT = "observed-registration-task-stock-cost-v3"
TASK_TARGET_CONTRACTS = frozenset((TASK_TERMINAL_TARGET_CONTRACT, RESOURCE_TASK_TARGET_CONTRACT))


def validate_sequence_target_contract(contract):
    if type(contract) is not str or contract not in (
        SEQUENCE_TARGET_CONTRACT,
        TASK_TERMINAL_TARGET_CONTRACT,
        RESOURCE_TASK_TARGET_CONTRACT,
    ):
        raise ValueError("unknown sequence target contract")


SEQUENCE_TARGET_NAMES = (
    "native_progress",
    "completed_quests",
    "actions",
    "frames",
    "observed_cash_debits",
    "observed_cash_credits",
    "battle_losses",
)
SEQUENCE_TARGET_SCALES = (1, 1, 1000, 60000, 1000, 1000, 1)


def sequence_target_names(contract):
    validate_sequence_target_contract(contract)
    if contract == RESOURCE_TASK_TARGET_CONTRACT:
        return (*SEQUENCE_TARGET_NAMES[:4], "cash_outflow_plus_priced_medicine_depletion", *SEQUENCE_TARGET_NAMES[5:])
    return SEQUENCE_TARGET_NAMES


def registration_task_catalog(rom_sha256):
    from .provenance import canonical_sha256
    if type(rom_sha256) is not str or len(rom_sha256) != 64 or any(c not in "0123456789abcdef" for c in rom_sha256):
        raise ValueError("registration task needs exact cartridge identity")
    doc = dict(schema="pokemon.red.next-native-registration-task.v1", rom_sha256=rom_sha256,
               predicate="any-new-native-owned-dex-since-actor-source")
    return dict(doc, task_sha256=canonical_sha256(doc))



@dataclass(frozen=True)
class SequenceTargets:
    raw: tuple[int | None, ...]
    values: tuple[float | None, ...]

    @property
    def known(self) -> tuple[bool, ...]:
        return tuple(value is not None for value in self.values)


def sequence_targets(
    measurement: SequenceMeasurement,
    *,
    covered: frozenset[str] = frozenset(),
    target_contract: str = SEQUENCE_TARGET_CONTRACT,
    priced_medicine_depletion: int | None = None,
) -> SequenceTargets:
    """Keep missing/full-horizon-censored labels unknown, not zero-filled.

    Raw prefix totals survive censoring. 'covered' must be established separately
    by the future native auditor; supplying names alone proves no provenance.
    Reported losses must be replaced by complete audited counts before marking
    battle_losses covered. No importance weights or causal claims are inferred.
    """
    if (
        not isinstance(measurement, SequenceMeasurement)
        or type(covered) is not frozenset
        or not covered <= set(sequence_target_names(target_contract))
    ):
        raise ValueError("sequence target contract differs")
    validate_sequence_target_contract(target_contract)
    from .player_short_sequence import SequenceEnd

    if (
        measurement.end is SequenceEnd.TASK_TERMINAL
        and target_contract not in TASK_TARGET_CONTRACTS
    ):
        raise ValueError("task terminal requires explicit task target contract")
    measurement.__post_init__()
    raw = (
        measurement.new_progress,
        measurement.completed_quests,
        measurement.actions,
        measurement.frames,
        measurement.cash_debits,
        measurement.cash_credits,
        measurement.blackouts,
    )
    if target_contract == RESOURCE_TASK_TARGET_CONTRACT:
        if type(priced_medicine_depletion) is not int or priced_medicine_depletion < 0:
            raise ValueError("task stock cost needs independently verified nonnegative replacement value")
        raw = (*raw[:4], raw[4] + priced_medicine_depletion, *raw[5:])
    elif priced_medicine_depletion is not None:
        raise ValueError("legacy cash-debit channel cannot be relabeled as replacement cost")
    return SequenceTargets(
        raw,
        tuple(
            value / (value + scale)
            if (
                measurement.complete_window
                or (
                    target_contract in TASK_TARGET_CONTRACTS
                    and measurement.complete_observation
                )
            )
            and name in covered
            else None
            for name, scale, value in zip(
                sequence_target_names(target_contract),
                SEQUENCE_TARGET_SCALES,
                raw,
                strict=True,
            )
        ),
    )


def unverified_sequence_targets(measurement, *, target_contract=SEQUENCE_TARGET_CONTRACT):
    """Recorded-only totals; unknown medicine valuation cannot become a zero."""
    if target_contract != RESOURCE_TASK_TARGET_CONTRACT:
        return sequence_targets(measurement, target_contract=target_contract)
    old = sequence_targets(measurement, target_contract=TASK_TERMINAL_TARGET_CONTRACT)
    return SequenceTargets((*old.raw[:4], None, *old.raw[5:]), (None,) * len(old.values))
