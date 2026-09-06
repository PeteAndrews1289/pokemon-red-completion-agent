from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.claim_first_admission import (
    observe_claim_first_pair_availability,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_claim_is_available,
)
from pokemon_red_completion.living_dex_repeatable_trial_claim import (
    LivingDexRepeatableClaimDisposition,
    LivingDexRepeatableRootReservation,
    LivingDexRepeatableTrialClaim,
    LivingDexRepeatableTrialClaimError,
    ensure_living_dex_repeatable_root_reservation,
    ensure_living_dex_repeatable_trial_claim,
    observe_living_dex_repeatable_root_eligibility,
)
from pokemon_red_completion.provenance import canonical_sha256


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _registry(tmp_path: Path) -> Path:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    registry.chmod(0o700)
    return registry


def _reservation(label: str = "root") -> LivingDexRepeatableRootReservation:
    return LivingDexRepeatableRootReservation(
        schedule_sha256=_sha("schedule"),
        logical_root_sha256=_sha((label, "logical")),
        physical_root_sha256=_sha((label, "physical")),
        runner_sha256=_sha("runner"),
        source_commit="a" * 40,
    )


def test_root_reservation_is_atomic_and_exactly_recoverable(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    reservation = _reservation()

    assert (
        ensure_living_dex_repeatable_root_reservation(registry, reservation)
        is LivingDexRepeatableClaimDisposition.CREATED
    )
    assert not observe_claim_first_pair_availability(
        registry,
        reservation.logical_root_sha256,
        reservation.physical_root_sha256,
    )
    assert (
        ensure_living_dex_repeatable_root_reservation(registry, reservation)
        is LivingDexRepeatableClaimDisposition.RECOVERED
    )


def test_same_base_root_can_hold_distinct_preregistered_reset_claims(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    reservation = _reservation()
    first = LivingDexRepeatableTrialClaim(reservation, _sha("slot-0"), 0)
    second = LivingDexRepeatableTrialClaim(reservation, _sha("slot-1"), 1)

    assert (
        ensure_living_dex_repeatable_trial_claim(registry, first)
        is LivingDexRepeatableClaimDisposition.CREATED
    )
    assert (
        ensure_living_dex_repeatable_trial_claim(registry, second)
        is LivingDexRepeatableClaimDisposition.CREATED
    )
    assert first.trial_claim_sha256 != second.trial_claim_sha256
    assert not root_claim_is_available(registry, first.trial_claim_sha256)
    assert not root_claim_is_available(registry, second.trial_claim_sha256)
    assert (
        ensure_living_dex_repeatable_trial_claim(registry, first)
        is LivingDexRepeatableClaimDisposition.RECOVERED
    )


def test_eligibility_is_read_only_for_unused_and_owned_roots(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    reservation = _reservation()
    assert observe_living_dex_repeatable_root_eligibility(registry, reservation)
    assert observe_claim_first_pair_availability(
        registry, reservation.logical_root_sha256, reservation.physical_root_sha256
    )
    ensure_living_dex_repeatable_root_reservation(registry, reservation)
    before = {path.name: path.read_bytes() for path in registry.iterdir()}
    assert observe_living_dex_repeatable_root_eligibility(registry, reservation)
    assert {path.name: path.read_bytes() for path in registry.iterdir()} == before


@pytest.mark.parametrize(
    "changes",
    [
        {"source_commit": "b" * 40},
        {"runner_sha256": _sha("other-runner")},
        {"schedule_sha256": _sha("other-schedule")},
        {"logical_root_sha256": _sha("other-logical")},
        {"physical_root_sha256": _sha("other-physical")},
    ],
)
def test_eligibility_rejects_another_campaign_or_partial_root_pair(
    tmp_path: Path, changes: dict[str, str]
) -> None:
    registry = _registry(tmp_path)
    reservation = _reservation()
    ensure_living_dex_repeatable_root_reservation(registry, reservation)
    assert not observe_living_dex_repeatable_root_eligibility(
        registry, replace(reservation, **changes)
    )


def test_another_schedule_cannot_relabel_an_existing_root_reservation(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    reservation = _reservation()
    ensure_living_dex_repeatable_root_reservation(registry, reservation)
    changed = replace(reservation, schedule_sha256=_sha("another-schedule"))

    with pytest.raises(
        LivingDexRepeatableTrialClaimError,
        match="owned by another campaign",
    ):
        ensure_living_dex_repeatable_root_reservation(registry, changed)


def test_trial_claim_binds_runner_source_slot_and_reset_ordinal(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    reservation = _reservation()
    trial = LivingDexRepeatableTrialClaim(reservation, _sha("slot"), 0)
    ensure_living_dex_repeatable_trial_claim(registry, trial)

    assert trial.trial_claim_sha256 != replace(trial, reset_ordinal=1).trial_claim_sha256
    assert trial.execution_identity_sha256 != LivingDexRepeatableTrialClaim(
        replace(reservation, runner_sha256=_sha("changed-runner")),
        trial.schedule_slot_sha256,
        trial.reset_ordinal,
    ).execution_identity_sha256
