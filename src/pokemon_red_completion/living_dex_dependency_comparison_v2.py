"""Aggregate-only comparison preflight for the sealed V2 dependency roster."""

from __future__ import annotations

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    DependencyComparisonClaimV2,
    LivingDexDependencyEvaluationV2Error,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    AuthenticatedDependencyEvaluationFitV2,
)


def preflight_v2_comparison(
    claim: DependencyComparisonClaimV2,
    *,
    authenticated_fit: AuthenticatedDependencyEvaluationFitV2,
) -> None:
    """Preflight the transition to comparison without opening payloads.

    This seam verifies that the exact pinned execution and fit identities
    match the comparison claim, proving that comparison execution is safely
    bound to the authenticated fit before any private record is decoded.
    """
    if not isinstance(claim, DependencyComparisonClaimV2):
        raise TypeError("claim must be DependencyComparisonClaimV2")
    if not isinstance(authenticated_fit, AuthenticatedDependencyEvaluationFitV2):
        raise TypeError("authenticated_fit must be AuthenticatedDependencyEvaluationFitV2")

    if claim.design_sha256 != authenticated_fit.pins.fit_identity.design_sha256:
        raise LivingDexDependencyEvaluationV2Error("V2 comparison preflight design differs")

    if claim.fit_bundle_pins.public_dict() != authenticated_fit.pins.public_dict():
        raise LivingDexDependencyEvaluationV2Error("V2 comparison preflight fit bundle differs")
