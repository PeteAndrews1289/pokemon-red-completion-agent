"""Write-once provisioning for fresh rootless living-Dex V2 openings.

This module is the only V2 stage allowed to know the four opening payloads before
comparison. It persists a private provision plan first, publishes the four
opening records from that immutable plan, and derives the public commitment roster
only from manifest metadata returned by :mod:`private_artifacts`.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyMultiplicity,
    DependencyMultiset,
)
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    ROOTLESS_DEPENDENCY_DEVELOPMENT_OPENING_SCHEMA_V2,
    ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
    ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT,
    ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT,
    FreshDependencyStructureV2,
    FreshDevelopmentCommitmentRosterV2,
    FreshDevelopmentCommitmentV2,
    FreshDevelopmentOpeningV2,
    LivingDexDependencyEvaluationV2Error,
    require_fresh_development_opening_set_v2,
)
from pokemon_red_completion.private_artifacts import (
    PrivateSealedRecord,
    SealedRecordManifestMetadata,
)

ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_SCHEMA = (
    "pokemon-private.rootless-dependency-development-provision-plan.v2"
)
ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_ID = "rootless-v2-development-provision"
ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_KIND = "rootless-dependency-provision-plan-v2"


class LivingDexDependencyProvisionV2Error(ValueError):
    """The fresh provision plan or immutable opening set is invalid."""


class V2ProvisionStore(Protocol):
    """Narrow private-store capability required by the provisioning stage."""

    def find_sealed_record(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> PrivateSealedRecord | None: ...

    def publish_sealed_record(
        self,
        record_id: str,
        *,
        kind: str,
        record: Mapping[str, object],
    ) -> PrivateSealedRecord: ...

    def inspect_sealed_record_metadata(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> SealedRecordManifestMetadata | None: ...


@dataclass(frozen=True, slots=True)
class ProvisionedV2DevelopmentCommitments:
    """Private provision completion plus its payload-blind public roster."""

    openings: tuple[FreshDevelopmentOpeningV2, ...]
    roster: FreshDevelopmentCommitmentRosterV2

    def __post_init__(self) -> None:
        require_fresh_development_opening_set_v2(self.openings)
        if tuple(row.scenario_id for row in self.openings) != tuple(
            row.record_id for row in self.roster.rows
        ):
            raise LivingDexDependencyProvisionV2Error(
                "V2 provision opening and commitment order differs"
            )


def generate_v2_development_openings() -> tuple[FreshDevelopmentOpeningV2, ...]:
    """Generate one fresh counterbalanced four-row private opening set.

    Requirement counts are sampled uniformly from the complete preregistered
    inclusive domain. No model, outcome, ROM, or controller state is consulted.
    """

    span = (
        ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT
        - ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT
        + 1
    )
    structures: list[FreshDependencyStructureV2] = []
    while len(structures) < 2:
        candidate = FreshDependencyStructureV2(
            required_precursor_count=(
                ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT + secrets.randbelow(span)
            ),
            required_evolved_count=(
                ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT + secrets.randbelow(span)
            ),
        )
        if candidate not in structures:
            structures.append(candidate)

    openings: list[FreshDevelopmentOpeningV2] = []
    for family_index, structure in enumerate(structures):
        family_id = f"rootless-v2-family-{secrets.token_hex(16)}"
        for multiplicity in DependencyMultiplicity:
            scarce = multiplicity is DependencyMultiplicity.SCARCE
            assigned_action = (
                GoalKind.ACQUIRE_SPECIES
                if scarce == (family_index == 0)
                else GoalKind.EVOLVE_SPECIES
            )
            precursor_count = structure.required_precursor_count
            if multiplicity is DependencyMultiplicity.DUPLICATE_READY:
                precursor_count += structure.required_evolved_count
            openings.append(
                FreshDevelopmentOpeningV2(
                    scenario_id=f"rootless-v2-development-{secrets.token_hex(16)}",
                    family_id=family_id,
                    nonce=secrets.token_hex(32),
                    multiplicity=multiplicity,
                    structure=structure,
                    before=DependencyMultiset(precursor_count, 0),
                    assigned_action=assigned_action,
                )
            )

    result = tuple(sorted(openings, key=lambda row: row.scenario_id))
    require_fresh_development_opening_set_v2(result)
    return result


def provision_v2_development_commitments(
    store: V2ProvisionStore,
) -> ProvisionedV2DevelopmentCommitments:
    """Publish or resume exactly one immutable V2 opening set.

    The provision plan is durable before the first opening publication. A later
    invocation therefore resumes the same identities and never substitutes a row
    after interruption. Public commitments are built from manifest-only metadata;
    they are not synthetic hashes invented by this module.
    """

    existing_plan = store.find_sealed_record(
        ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_ID,
        expected_kind=ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_KIND,
    )
    if existing_plan is None:
        generated = generate_v2_development_openings()
        existing_plan = store.publish_sealed_record(
            ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_ID,
            kind=ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_KIND,
            record=_provision_plan_document(generated),
        )
    openings = _openings_from_provision_plan(existing_plan.read())

    for opening in openings:
        store.publish_sealed_record(
            opening.scenario_id,
            kind=ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
            record=opening.private_dict(),
        )

    metadata: list[SealedRecordManifestMetadata] = []
    for opening in openings:
        row = store.inspect_sealed_record_metadata(
            opening.scenario_id,
            expected_kind=ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
        )
        if row is None:
            raise LivingDexDependencyProvisionV2Error("provisioned V2 opening metadata is absent")
        metadata.append(row)
    roster = commitment_roster_from_metadata_v2(metadata)
    return ProvisionedV2DevelopmentCommitments(openings, roster)


def commitment_roster_from_metadata_v2(
    metadata: Sequence[SealedRecordManifestMetadata],
) -> FreshDevelopmentCommitmentRosterV2:
    """Convert exactly four authenticated manifest-only rows into the V2 roster."""

    if (
        not isinstance(metadata, Sequence)
        or len(metadata) != 4
        or any(not isinstance(row, SealedRecordManifestMetadata) for row in metadata)
    ):
        raise LivingDexDependencyProvisionV2Error(
            "V2 commitment inventory requires four manifest metadata rows"
        )
    rows: list[FreshDevelopmentCommitmentV2] = []
    for row in metadata:
        if row.kind != ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2:
            raise LivingDexDependencyProvisionV2Error("V2 commitment inventory record kind differs")
        rows.append(
            FreshDevelopmentCommitmentV2(
                record_id=row.record_id,
                manifest_sha256=row.manifest_sha256,
                declared_record_sha256=row.declared_record_sha256,
                declared_total_bytes=row.declared_total_bytes,
            )
        )
    return FreshDevelopmentCommitmentRosterV2(tuple(sorted(rows, key=lambda row: row.record_id)))


def parse_v2_development_opening(
    value: Mapping[str, object],
) -> FreshDevelopmentOpeningV2:
    """Strictly parse one full V2 opening at the later comparison boundary."""

    expected = {
        "schema",
        "scenario_id",
        "family_id",
        "nonce",
        "partition",
        "multiplicity",
        "structure",
        "before",
        "assigned_action",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise LivingDexDependencyProvisionV2Error("V2 opening fields differ")
    structure = value.get("structure")
    before = value.get("before")
    if (
        value.get("schema") != ROOTLESS_DEPENDENCY_DEVELOPMENT_OPENING_SCHEMA_V2
        or value.get("partition") != "development"
        or not isinstance(structure, Mapping)
        or set(structure) != {"required_precursor_count", "required_evolved_count"}
        or not isinstance(before, Mapping)
        or set(before) != {"precursor_count", "evolved_count"}
    ):
        raise LivingDexDependencyProvisionV2Error("V2 opening fields differ")
    scenario_id = value.get("scenario_id")
    family_id = value.get("family_id")
    nonce = value.get("nonce")
    multiplicity = value.get("multiplicity")
    assigned_action = value.get("assigned_action")
    required_precursor = structure.get("required_precursor_count")
    required_evolved = structure.get("required_evolved_count")
    precursor = before.get("precursor_count")
    evolved = before.get("evolved_count")
    if (
        not isinstance(scenario_id, str)
        or not isinstance(family_id, str)
        or not isinstance(nonce, str)
        or type(required_precursor) is not int  # noqa: E721
        or type(required_evolved) is not int  # noqa: E721
        or type(precursor) is not int  # noqa: E721
        or type(evolved) is not int  # noqa: E721
        or not isinstance(multiplicity, str)
        or not isinstance(assigned_action, str)
    ):
        raise LivingDexDependencyProvisionV2Error("V2 opening fields differ")
    try:
        opening = FreshDevelopmentOpeningV2(
            scenario_id=scenario_id,
            family_id=family_id,
            nonce=nonce,
            multiplicity=DependencyMultiplicity(multiplicity),
            structure=FreshDependencyStructureV2(required_precursor, required_evolved),
            before=DependencyMultiset(precursor, evolved),
            assigned_action=GoalKind(assigned_action),
        )
    except (LivingDexDependencyEvaluationV2Error, ValueError):
        raise LivingDexDependencyProvisionV2Error("V2 opening fields differ") from None
    if opening.private_dict() != dict(value):
        raise LivingDexDependencyProvisionV2Error("V2 opening is not canonical")
    return opening


def _provision_plan_document(
    openings: tuple[FreshDevelopmentOpeningV2, ...],
) -> dict[str, object]:
    require_fresh_development_opening_set_v2(openings)
    return {
        "schema": ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_SCHEMA,
        "status": "frozen",
        "rows": [opening.private_dict() for opening in openings],
        "row_count": 4,
        "replacement_allowed": False,
    }


def _openings_from_provision_plan(
    value: Mapping[str, object],
) -> tuple[FreshDevelopmentOpeningV2, ...]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "status",
        "rows",
        "row_count",
        "replacement_allowed",
    }:
        raise LivingDexDependencyProvisionV2Error("V2 provision plan fields differ")
    rows = value.get("rows")
    if (
        value.get("schema") != ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_SCHEMA
        or value.get("status") != "frozen"
        or value.get("row_count") != 4
        or value.get("replacement_allowed") is not False
        or not isinstance(rows, list)
        or any(not isinstance(row, Mapping) for row in rows)
    ):
        raise LivingDexDependencyProvisionV2Error("V2 provision plan fields differ")
    openings = tuple(parse_v2_development_opening(row) for row in rows)
    require_fresh_development_opening_set_v2(openings)
    if _provision_plan_document(openings) != dict(value):
        raise LivingDexDependencyProvisionV2Error("V2 provision plan is not canonical")
    return openings


def canonical_v2_opening_bytes(opening: FreshDevelopmentOpeningV2) -> bytes:
    """Return the exact newline-canonical record bytes used by private storage."""

    if not isinstance(opening, FreshDevelopmentOpeningV2):
        raise TypeError("opening must be FreshDevelopmentOpeningV2")
    return (
        json.dumps(
            opening.private_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
