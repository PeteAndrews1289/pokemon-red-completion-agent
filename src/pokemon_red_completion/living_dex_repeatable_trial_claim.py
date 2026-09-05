"""Durable claims for preregistered reset trials from the same saved state.

An independent-root claim correctly forbids consuming identical state bytes
twice.  A reset curriculum is different: the schedule prospectively reserves
the underlying root once, then gives each declared reset slot its own durable
trial claim.  The underlying byte identity remains explicit, so reset trials
cannot be misreported as independent worlds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    ClaimFirstRootPair,
    claim_first_pair_registry,
    observe_claim_first_pair_availability,
    read_root_pair_claim,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_REPEATABLE_ROOT_RESERVATION_SCHEMA = (
    "pokemon.core.living-dex-repeatable-root-reservation.v1"
)
LIVING_DEX_REPEATABLE_TRIAL_CLAIM_SCHEMA = (
    "pokemon.core.living-dex-repeatable-trial-claim.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class LivingDexRepeatableTrialClaimError(RuntimeError):
    """A campaign reservation or one reset-trial claim cannot authenticate."""


class LivingDexRepeatableClaimDisposition(StrEnum):
    CREATED = "created"
    RECOVERED = "recovered"


@dataclass(frozen=True, slots=True)
class LivingDexRepeatableRootReservation:
    """Prospective ownership of one underlying state by one frozen schedule."""

    schedule_sha256: str
    logical_root_sha256: str
    physical_root_sha256: str
    runner_sha256: str
    source_commit: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.schedule_sha256, "schedule"),
            (self.logical_root_sha256, "logical root"),
            (self.physical_root_sha256, "physical root"),
            (self.runner_sha256, "runner"),
        ):
            _require_sha256(value, subject=subject)
        if self.logical_root_sha256 == self.physical_root_sha256:
            raise LivingDexRepeatableTrialClaimError(
                "repeatable logical and physical roots collapse"
            )
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise LivingDexRepeatableTrialClaimError(
                "repeatable reservation source commit differs"
            )

    @property
    def reservation_slot_sha256(self) -> str:
        return canonical_sha256(
            {
                "logical_root_sha256": self.logical_root_sha256,
                "physical_root_sha256": self.physical_root_sha256,
                "schedule_sha256": self.schedule_sha256,
                "schema": LIVING_DEX_REPEATABLE_ROOT_RESERVATION_SCHEMA,
            }
        )

    @property
    def execution_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "reservation_slot_sha256": self.reservation_slot_sha256,
                "runner_sha256": self.runner_sha256,
                "schema": LIVING_DEX_REPEATABLE_ROOT_RESERVATION_SCHEMA,
                "source_commit": self.source_commit,
            }
        )

    @property
    def pair_claim(self) -> ClaimFirstRootPair:
        return ClaimFirstRootPair(
            logical_root_sha256=self.logical_root_sha256,
            physical_root_sha256=self.physical_root_sha256,
            stage="targeted-reset-campaign",
            execution_identity_sha256=self.execution_identity_sha256,
            plan_sha256=self.schedule_sha256,
            slot_sha256=self.reservation_slot_sha256,
            runner_sha256=self.runner_sha256,
            source_commit=self.source_commit,
        )


@dataclass(frozen=True, slots=True)
class LivingDexRepeatableTrialClaim:
    """One unique reset slot that still exposes its shared base-root identity."""

    reservation: LivingDexRepeatableRootReservation
    schedule_slot_sha256: str
    reset_ordinal: int

    def __post_init__(self) -> None:
        if not isinstance(self.reservation, LivingDexRepeatableRootReservation):
            raise TypeError("repeatable trial needs its root reservation")
        self.reservation.__post_init__()
        _require_sha256(self.schedule_slot_sha256, subject="schedule slot")
        if type(self.reset_ordinal) is not int or self.reset_ordinal < 0:  # noqa: E721
            raise LivingDexRepeatableTrialClaimError(
                "repeatable trial reset ordinal differs"
            )

    @property
    def trial_claim_sha256(self) -> str:
        return canonical_sha256(
            {
                "base_logical_root_sha256": self.reservation.logical_root_sha256,
                "base_physical_root_sha256": self.reservation.physical_root_sha256,
                "reset_ordinal": self.reset_ordinal,
                "schedule_sha256": self.reservation.schedule_sha256,
                "schedule_slot_sha256": self.schedule_slot_sha256,
                "schema": LIVING_DEX_REPEATABLE_TRIAL_CLAIM_SCHEMA,
            }
        )

    @property
    def execution_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "reservation_claim_sha256": (
                    self.reservation.pair_claim.claim_sha256
                ),
                "runner_sha256": self.reservation.runner_sha256,
                "schema": LIVING_DEX_REPEATABLE_TRIAL_CLAIM_SCHEMA,
                "source_commit": self.reservation.source_commit,
                "trial_claim_sha256": self.trial_claim_sha256,
            }
        )


def ensure_living_dex_repeatable_root_reservation(
    registry: Path,
    reservation: LivingDexRepeatableRootReservation,
) -> LivingDexRepeatableClaimDisposition:
    """Atomically create or exactly recover one base-root reservation."""

    if not isinstance(registry, Path):
        raise TypeError("repeatable reservation needs a claim registry Path")
    if not isinstance(reservation, LivingDexRepeatableRootReservation):
        raise TypeError("repeatable reservation differs")
    reservation.__post_init__()
    expected = reservation.pair_claim
    try:
        restored = read_root_pair_claim(registry, expected.claim_sha256)
    except ClaimFirstAdmissionError:
        restored = None
    if restored is not None:
        if restored != expected:
            raise LivingDexRepeatableTrialClaimError(
                "repeatable root reservation differs"
            )
        return LivingDexRepeatableClaimDisposition.RECOVERED
    try:
        if not observe_claim_first_pair_availability(
            registry,
            reservation.logical_root_sha256,
            reservation.physical_root_sha256,
        ):
            raise LivingDexRepeatableTrialClaimError(
                "repeatable root is owned by another campaign"
            )
        with claim_first_pair_registry(registry) as claims:
            claims.claim(expected)
    except ClaimFirstAdmissionError as error:
        raise LivingDexRepeatableTrialClaimError(str(error)) from None
    return LivingDexRepeatableClaimDisposition.CREATED


def ensure_living_dex_repeatable_trial_claim(
    registry: Path,
    trial: LivingDexRepeatableTrialClaim,
) -> LivingDexRepeatableClaimDisposition:
    """Create or exactly recover one append-only reset-slot claim."""

    if not isinstance(registry, Path):
        raise TypeError("repeatable trial needs a claim registry Path")
    if not isinstance(trial, LivingDexRepeatableTrialClaim):
        raise TypeError("repeatable trial claim differs")
    trial.__post_init__()
    ensure_living_dex_repeatable_root_reservation(registry, trial.reservation)
    expected = {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": trial.trial_claim_sha256,
        "execution_identity_sha256": trial.execution_identity_sha256,
        "source_commit": trial.reservation.source_commit,
        "runner_sha256": trial.reservation.runner_sha256,
    }
    try:
        opened = open_fixed_account_claim_registry(registry)
        with fixed_account_claim_registry_lease(opened, exclusive=True):
            if root_claim_is_available(opened, trial.trial_claim_sha256):
                write_root_claim(
                    opened,
                    root_consumption_sha256=trial.trial_claim_sha256,
                    execution_identity_sha256=trial.execution_identity_sha256,
                    source_commit=trial.reservation.source_commit,
                    runner_sha256=trial.reservation.runner_sha256,
                )
                disposition = LivingDexRepeatableClaimDisposition.CREATED
            else:
                disposition = LivingDexRepeatableClaimDisposition.RECOVERED
            restored = read_root_claim(opened, trial.trial_claim_sha256)
    except FreshCompositionQualificationError as error:
        raise LivingDexRepeatableTrialClaimError(str(error)) from None
    if restored != expected:
        raise LivingDexRepeatableTrialClaimError(
            "repeatable trial claim differs"
        )
    return disposition


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexRepeatableTrialClaimError(
            f"repeatable {subject} SHA-256 differs"
        )
    return value


__all__ = [
    "LIVING_DEX_REPEATABLE_ROOT_RESERVATION_SCHEMA",
    "LIVING_DEX_REPEATABLE_TRIAL_CLAIM_SCHEMA",
    "LivingDexRepeatableClaimDisposition",
    "LivingDexRepeatableRootReservation",
    "LivingDexRepeatableTrialClaim",
    "LivingDexRepeatableTrialClaimError",
    "ensure_living_dex_repeatable_root_reservation",
    "ensure_living_dex_repeatable_trial_claim",
]
