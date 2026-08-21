"""Provisioning seam for rootless living-Dex dependency V2 evaluation."""

from __future__ import annotations

import hashlib
import secrets

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyMultiplicity,
    DependencyMultiset,
)
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    FreshDependencyStructureV2,
    FreshDevelopmentCommitmentRosterV2,
    FreshDevelopmentCommitmentV2,
    FreshDevelopmentOpeningV2,
    require_fresh_development_opening_set_v2,
)


def provision_v2_development_commitments() -> tuple[
    tuple[FreshDevelopmentOpeningV2, ...],
    FreshDevelopmentCommitmentRosterV2,
]:
    """Generate exactly four fresh sealed V2 openings and their public roster.

    This synthetic seam enforces the V2 requirements: 256-bit nonces, distinct
    structures >= 17, and balanced treatments, without saving to a real artifact store.
    """
    structures: list[FreshDependencyStructureV2] = []
    # V2 requires structures in the domain >= 17
    while len(structures) < 2:
        candidate = FreshDependencyStructureV2(
            required_precursor_count=17 + secrets.randbelow(10),
            required_evolved_count=17 + secrets.randbelow(10),
        )
        if candidate not in structures:
            structures.append(candidate)

    openings: list[FreshDevelopmentOpeningV2] = []
    for family_index, structure in enumerate(structures):
        family_id = f"rootless-v2-family-{secrets.token_hex(16)}"
        for multiplicity in DependencyMultiplicity:
            scarce = multiplicity is DependencyMultiplicity.SCARCE
            action = (
                GoalKind.ACQUIRE_SPECIES
                if scarce == (family_index % 2 == 0)
                else GoalKind.EVOLVE_SPECIES
            )
            expected_precursor = structure.required_precursor_count
            if not scarce:
                expected_precursor += structure.required_evolved_count

            before = DependencyMultiset(expected_precursor, 0)
            nonce = secrets.token_hex(32)  # 256-bit secure nonce

            opening = FreshDevelopmentOpeningV2(
                scenario_id=f"rootless-v2-development-{secrets.token_hex(16)}",
                family_id=family_id,
                nonce=nonce,
                multiplicity=multiplicity,
                structure=structure,
                before=before,
                assigned_action=action,
            )
            openings.append(opening)

    openings_tuple = tuple(sorted(openings, key=lambda row: row.scenario_id))
    require_fresh_development_opening_set_v2(openings_tuple)

    commitments: list[FreshDevelopmentCommitmentV2] = []
    for opening in openings_tuple:
        payload_bytes = opening.canonical_private_bytes()
        payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()

        # Synthetic manifest for the opening
        manifest_payload = f"synthetic-manifest-{opening.scenario_id}".encode("ascii")
        manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()

        commitment = FreshDevelopmentCommitmentV2(
            record_id=opening.scenario_id,
            manifest_sha256=manifest_sha256,
            declared_record_sha256=payload_sha256,
            declared_total_bytes=len(payload_bytes),
        )
        commitments.append(commitment)

    roster = FreshDevelopmentCommitmentRosterV2(tuple(commitments))
    return openings_tuple, roster
