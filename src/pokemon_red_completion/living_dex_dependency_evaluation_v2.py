"""Pure design contract for a fresh rootless living-Dex evaluation.

V1 proved that the small dependency ranker can fit eight deterministic examples,
but its held-out seal was invalidated when common inventory decoded development
payloads before fitting.  This module defines the successor experiment without
opening private storage, fitting a model, or decoding an evaluation row.

The contract deliberately separates four things:

* public recomputation of the eight deterministic train values;
* four fresh, opaque V2 development commitments;
* a one-shot fit identity; and
* a later, separately claimed comparison identity bound to an externally pinned
  completed fit bundle.

It is a design and identity module, not an execution runner.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyMultiplicity,
    DependencyMultiset,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
)
from pokemon_red_completion.provenance import canonical_sha256

ROOTLESS_DEPENDENCY_EVALUATION_DESIGN_V2_SCHEMA = (
    "pokemon.core.rootless-living-dex-dependency-evaluation-design.v2"
)
ROOTLESS_DEPENDENCY_DEVELOPMENT_COMMITMENT_V2_SCHEMA = (
    "pokemon.core.rootless-dependency-development-commitment.v2"
)
ROOTLESS_DEPENDENCY_DEVELOPMENT_ROSTER_V2_SCHEMA = (
    "pokemon.core.rootless-dependency-development-commitments.v2"
)
ROOTLESS_DEPENDENCY_TRAIN_REVALIDATION_V2_SCHEMA = (
    "pokemon.core.rootless-dependency-train-revalidation.v2"
)
ROOTLESS_DEPENDENCY_FIT_CLAIM_V2_SCHEMA = "pokemon.core.rootless-dependency-fit-claim.v2"
ROOTLESS_DEPENDENCY_COMPARISON_CLAIM_V2_SCHEMA = (
    "pokemon.core.rootless-dependency-comparison-claim.v2"
)
ROOTLESS_DEPENDENCY_STAGE_CONTRACT_V2_SCHEMA = "pokemon.core.rootless-dependency-stage-contract.v2"
ROOTLESS_DEPENDENCY_COUNTER_CONTRACT_V2_SCHEMA = (
    "pokemon.core.rootless-dependency-counter-contract.v2"
)

ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2: Final = "rootless-living-dex-dependency-fresh-evaluation-v2"
ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2: Final = (
    "rootless-living-dex-dependency-development-opening-v2"
)
ROOTLESS_DEPENDENCY_DEVELOPMENT_OPENING_SCHEMA_V2: Final = (
    "pokemon-private.rootless-dependency-development-opening.v2"
)
ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT: Final = 17
ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT: Final = 10_000
ROOTLESS_DEPENDENCY_V2_NONCE_BYTES: Final = 32

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_V2_RECORD_ID = re.compile(r"rootless-v2-development-[0-9a-f]{32}\Z")
_V2_FAMILY_ID = re.compile(r"rootless-v2-family-[0-9a-f]{32}\Z")
_MAX_DECLARED_OPENING_BYTES = 16 * 1024

# These public identities are permanently evaluation-ineligible.  The list covers
# the V1 semantic design/roster/campaign/dataset, fit/model/binding records, the
# never-executed comparison manifest, and the evidence records that closed them.
# The V1 opening payload hashes are intentionally not public.  V2 nevertheless
# cannot reproduce them: it uses a new schema/record namespace and a requirement
# domain >=17, whereas the V1 generator used 3..15.
RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES: Final[frozenset[str]] = frozenset(
    {
        "0eee3874c664bdda0bdd6f4cfb3ec3f3e6b36f8b442173a37f8dcdd5a6cf0686",
        "0f1089aa0a66da4c6f626eb3b8cbb5383bdecdd0d785847cc56b02a4d1eac48d",
        "2390c2c22fe19df799cc5ad664053b5baf1c0e1bfaf7694f6464ad66f51f4a29",
        "27f2358d88e9dab138452e6a1bba06dcc69bdc0d4420222e32b490bebea3e7f4",
        "32b68cbf7a459f3e1c0464af134be31d1ac3cd87591df3d54176627821d1feed",
        "3e8b6fea80f742e3e90abe6cf40307d5c95a35f940c1a3e64f5147edbf989545",
        "404e3a028cce695e23d20a4df8dc26ccfebbf48ca100800a5fe8e6a0d0bc9b92",
        "415af97d2414fb2da0083c45df30154ac70c05bbd4c83c852006120c953cf3c4",
        "64099c3611a47e6aeba02340d9bc92dfc8e7af1ea4f0f5104f78b893467184db",
        "66c578705d2440bb36f3b10062dab793258cbae0fdd7dfc51a36d33664555d24",
        "6d650fc903493b490d6b990b5df6166b99425977e0931830329d84c24b1e1ba2",
        "8207eb89a430a5bbb6bca7bd960e000c728710fded2bceef027dd4179e385f37",
        "99a1563783ff5bad79cacf2664cfc3d075872125855b7424b86882aff6c6e256",
        "b57cd393eb28338d94a90a35974b106a379444c638e8b1923aa38cf3f35d140a",
        "babe6a96a13f732573bbd1cd93227d27d75ea291ab70fa7c7fd35edf531b5bc8",
        "d570fcc4e47667219b9ecf6881d534a05415901d3b2d12164f112eaa337b9d7b",
        "d6f48d3429d99850e52fb75c43f6a84d27bdfd3e611d43fbf0f66e377f9f749e",
        "ee102f6711de77de8335860dce2b7c855414985c57d1cb6222914f9e63f85be4",
        "f115731b24f1b3343ef88af7bdef619d93ca6c11b914eb7e19d6e4253424ccd8",
        "f7630b8b09ba5b6962892335588bb376129a74554dee8442962ac1c92f5c4ce6",
        "f8da36c20abffa69de8a7b62492f8bc64fd9c58e2ca40ff084cacb0511da95f7",
    }
)

_ZERO_COUNTERS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "atomic_goal_episodes_added": 0,
        "authority_promotions_added": 0,
        "causal_train_examples_added": 0,
        "composition_attempts_added": 0,
        "development_episode_attempts_added": 0,
        "model_fits_added": 0,
        "outcome_questions_added": 0,
        "synthetic_rootless_atomic_goal_episodes_added": 0,
        "synthetic_rootless_model_fits_added": 0,
        "synthetic_rootless_train_outcomes_added": 0,
        "synthetic_rootless_unseen_comparisons_added": 0,
        "transfer_results_added": 0,
        "unseen_comparisons_added": 0,
        "verified_composition_episodes_added": 0,
        "verified_outcome_examples_added": 0,
    }
)


class LivingDexDependencyEvaluationV2Error(ValueError):
    """The fresh V2 design or one of its prospective identities is invalid."""


class RootlessDependencyEvaluationStageV2(StrEnum):
    DESIGN = "design"
    PROVISION = "provision"
    FIT_PREFLIGHT = "fit_preflight"
    FIT = "fit"
    COMPARISON_PREFLIGHT = "comparison_preflight"
    COMPARISON = "comparison"


@dataclass(frozen=True, slots=True)
class FreshDependencyStructureV2:
    """Private held-out dependency requirements, disjoint from every V1 domain."""

    required_precursor_count: int
    required_evolved_count: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int  # noqa: E721
            or not (
                ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT
                <= value
                <= ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT
            )
            for value in (
                self.required_precursor_count,
                self.required_evolved_count,
            )
        ):
            raise LivingDexDependencyEvaluationV2Error(
                "V2 dependency structure overlaps an excluded domain"
            )

    def private_dict(self) -> dict[str, int]:
        return {
            "required_precursor_count": self.required_precursor_count,
            "required_evolved_count": self.required_evolved_count,
        }


@dataclass(frozen=True, slots=True)
class FreshDevelopmentOpeningV2:
    """One future private opening; never embedded in the public design."""

    scenario_id: str
    family_id: str
    nonce: str
    multiplicity: DependencyMultiplicity
    structure: FreshDependencyStructureV2
    before: DependencyMultiset
    assigned_action: GoalKind

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenario_id, str)
            or _V2_RECORD_ID.fullmatch(self.scenario_id) is None
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 opening identity is unsafe")
        if not isinstance(self.family_id, str) or _V2_FAMILY_ID.fullmatch(self.family_id) is None:
            raise LivingDexDependencyEvaluationV2Error("V2 family identity is unsafe")
        if (
            not isinstance(self.nonce, str)
            or _SHA256.fullmatch(self.nonce) is None
            or len(set(self.nonce)) < 8
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 opening nonce is invalid")
        if not isinstance(self.multiplicity, DependencyMultiplicity):
            raise LivingDexDependencyEvaluationV2Error("V2 opening multiplicity differs")
        if not isinstance(self.structure, FreshDependencyStructureV2):
            raise LivingDexDependencyEvaluationV2Error("V2 opening structure differs")
        expected_precursor = self.structure.required_precursor_count
        if self.multiplicity is DependencyMultiplicity.DUPLICATE_READY:
            expected_precursor += self.structure.required_evolved_count
        if self.before != DependencyMultiset(expected_precursor, 0):
            raise LivingDexDependencyEvaluationV2Error("V2 opening multiset differs")
        if self.assigned_action not in {
            GoalKind.ACQUIRE_SPECIES,
            GoalKind.EVOLVE_SPECIES,
        }:
            raise LivingDexDependencyEvaluationV2Error("V2 opening action differs")

    @property
    def derived_reward(self) -> int:
        positive = (
            self.multiplicity is DependencyMultiplicity.SCARCE
            and self.assigned_action is GoalKind.ACQUIRE_SPECIES
        ) or (
            self.multiplicity is DependencyMultiplicity.DUPLICATE_READY
            and self.assigned_action is GoalKind.EVOLVE_SPECIES
        )
        return 1 if positive else -1

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_DEVELOPMENT_OPENING_SCHEMA_V2,
            "scenario_id": self.scenario_id,
            "family_id": self.family_id,
            "nonce": self.nonce,
            "partition": "development",
            "multiplicity": self.multiplicity.value,
            "structure": self.structure.private_dict(),
            "before": self.before.public_dict(),
            "assigned_action": self.assigned_action.value,
        }

    def canonical_private_bytes(self) -> bytes:
        return (
            json.dumps(
                self.private_dict(),
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )


def require_fresh_development_opening_set_v2(
    openings: tuple[FreshDevelopmentOpeningV2, ...],
) -> None:
    """Validate the future private four-row denominator without publishing it."""

    if (
        not isinstance(openings, tuple)
        or len(openings) != 4
        or any(not isinstance(row, FreshDevelopmentOpeningV2) for row in openings)
    ):
        raise LivingDexDependencyEvaluationV2Error(
            "V2 opening set must contain exactly four typed rows"
        )
    if tuple(sorted(openings, key=lambda row: row.scenario_id)) != openings:
        raise LivingDexDependencyEvaluationV2Error("V2 opening set order differs")
    if len({row.scenario_id for row in openings}) != 4 or len({row.nonce for row in openings}) != 4:
        raise LivingDexDependencyEvaluationV2Error("V2 opening identities must be distinct")
    families: dict[str, list[FreshDevelopmentOpeningV2]] = {}
    for row in openings:
        families.setdefault(row.family_id, []).append(row)
    if len(families) != 2:
        raise LivingDexDependencyEvaluationV2Error("V2 opening set must contain two families")
    structures: set[FreshDependencyStructureV2] = set()
    for rows in families.values():
        if (
            len(rows) != 2
            or {row.multiplicity for row in rows} != set(DependencyMultiplicity)
            or {row.assigned_action for row in rows}
            != {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
            or len({row.structure for row in rows}) != 1
        ):
            raise LivingDexDependencyEvaluationV2Error(
                "each V2 family must contain both multiplicities and treatments"
            )
        structures.add(rows[0].structure)
    if len(structures) != 2:
        raise LivingDexDependencyEvaluationV2Error("V2 family structures must be distinct")
    if Counter(row.assigned_action for row in openings) != {
        GoalKind.ACQUIRE_SPECIES: 2,
        GoalKind.EVOLVE_SPECIES: 2,
    } or Counter(row.derived_reward for row in openings) != {-1: 2, 1: 2}:
        raise LivingDexDependencyEvaluationV2Error(
            "V2 opening treatments and derived rewards must be balanced"
        )


@dataclass(frozen=True, slots=True)
class FreshDevelopmentCommitmentV2:
    """Payload-blind metadata for one future sealed development opening."""

    record_id: str
    manifest_sha256: str
    declared_record_sha256: str
    declared_total_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or _V2_RECORD_ID.fullmatch(self.record_id) is None:
            raise LivingDexDependencyEvaluationV2Error(
                "V2 development record identity is unsafe or not fresh"
            )
        _fresh_sha256(self.manifest_sha256, subject="V2 development manifest")
        _fresh_sha256(self.declared_record_sha256, subject="V2 development record")
        if self.manifest_sha256 == self.declared_record_sha256:
            raise LivingDexDependencyEvaluationV2Error(
                "V2 manifest and declared payload identities must be distinct"
            )
        if (
            type(self.declared_total_bytes) is not int  # noqa: E721
            or not 1 <= self.declared_total_bytes <= _MAX_DECLARED_OPENING_BYTES
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 declared opening size is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_DEVELOPMENT_COMMITMENT_V2_SCHEMA,
            "record_id": self.record_id,
            "record_kind": ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
            "manifest_sha256": self.manifest_sha256,
            "declared_record_sha256": self.declared_record_sha256,
            "declared_total_bytes": self.declared_total_bytes,
            "payload_opened": False,
            "payload_integrity_verified": False,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> FreshDevelopmentCommitmentV2:
        expected = {
            "schema",
            "record_id",
            "record_kind",
            "manifest_sha256",
            "declared_record_sha256",
            "declared_total_bytes",
            "payload_opened",
            "payload_integrity_verified",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise LivingDexDependencyEvaluationV2Error("V2 commitment fields differ")
        record_id = value.get("record_id")
        manifest_sha256 = value.get("manifest_sha256")
        declared_record_sha256 = value.get("declared_record_sha256")
        declared_total_bytes = value.get("declared_total_bytes")
        if (
            value.get("schema") != ROOTLESS_DEPENDENCY_DEVELOPMENT_COMMITMENT_V2_SCHEMA
            or value.get("record_kind") != ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2
            or value.get("payload_opened") is not False
            or value.get("payload_integrity_verified") is not False
            or not isinstance(record_id, str)
            or not isinstance(manifest_sha256, str)
            or not isinstance(declared_record_sha256, str)
            or type(declared_total_bytes) is not int  # noqa: E721
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 commitment fields differ")
        row = cls(
            record_id=record_id,
            manifest_sha256=manifest_sha256,
            declared_record_sha256=declared_record_sha256,
            declared_total_bytes=declared_total_bytes,
        )
        if row.public_dict() != dict(value):
            raise LivingDexDependencyEvaluationV2Error("V2 commitment fields differ")
        return row


@dataclass(frozen=True, slots=True)
class FreshDevelopmentCommitmentRosterV2:
    rows: tuple[FreshDevelopmentCommitmentV2, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple) or len(self.rows) != 4:
            raise LivingDexDependencyEvaluationV2Error(
                "V2 development roster must contain exactly four commitments"
            )
        if any(not isinstance(row, FreshDevelopmentCommitmentV2) for row in self.rows):
            raise LivingDexDependencyEvaluationV2Error("V2 development roster row differs")
        if tuple(sorted(self.rows, key=lambda row: row.record_id)) != self.rows:
            raise LivingDexDependencyEvaluationV2Error(
                "V2 development commitments must use canonical record order"
            )
        identities = [row.record_id for row in self.rows]
        manifests = [row.manifest_sha256 for row in self.rows]
        payloads = [row.declared_record_sha256 for row in self.rows]
        if any(len(set(values)) != 4 for values in (identities, manifests, payloads)):
            raise LivingDexDependencyEvaluationV2Error(
                "V2 development commitments must be independently distinct"
            )
        if set(manifests) & set(payloads):
            raise LivingDexDependencyEvaluationV2Error(
                "V2 manifest and payload identity domains must not overlap"
            )
        _fresh_sha256(self.roster_sha256, subject="V2 development roster")

    @property
    def roster_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_DEVELOPMENT_ROSTER_V2_SCHEMA,
            "row_count": 4,
            "rows": [row.public_dict() for row in self.rows],
            "payloads_opened": 0,
            "payloads_decoded": 0,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> FreshDevelopmentCommitmentRosterV2:
        if not isinstance(value, Mapping) or set(value) != {
            "schema",
            "row_count",
            "rows",
            "payloads_opened",
            "payloads_decoded",
        }:
            raise LivingDexDependencyEvaluationV2Error("V2 roster fields differ")
        rows = value.get("rows")
        if (
            value.get("schema") != ROOTLESS_DEPENDENCY_DEVELOPMENT_ROSTER_V2_SCHEMA
            or value.get("row_count") != 4
            or value.get("payloads_opened") != 0
            or value.get("payloads_decoded") != 0
            or not isinstance(rows, list)
            or any(not isinstance(row, Mapping) for row in rows)
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 roster fields differ")
        roster = cls(tuple(FreshDevelopmentCommitmentV2.from_dict(row) for row in rows))
        if roster.public_dict() != dict(value):
            raise LivingDexDependencyEvaluationV2Error("V2 roster fields differ")
        return roster


@dataclass(frozen=True, slots=True)
class EvaluationExecutionBindingV2:
    """Reviewed executable identity for exactly one future operation."""

    operation: Literal["fit", "comparison"]
    source_commit: str
    source_bundle_sha256: str
    runner_sha256: str
    runtime_sha256: str

    def __post_init__(self) -> None:
        if self.operation not in {"fit", "comparison"}:
            raise LivingDexDependencyEvaluationV2Error("V2 operation differs")
        if (
            not isinstance(self.source_commit, str)
            or _SOURCE_COMMIT.fullmatch(self.source_commit) is None
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 source commit is invalid")
        for subject, value in (
            ("source bundle", self.source_bundle_sha256),
            ("runner", self.runner_sha256),
            ("runtime", self.runtime_sha256),
        ):
            _fresh_sha256(value, subject=f"V2 {subject}")

    @property
    def execution_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": "pokemon.core.rootless-dependency-execution-binding.v2",
                **self.public_dict(),
            }
        )

    def public_dict(self) -> dict[str, str]:
        return {
            "operation": self.operation,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "runner_sha256": self.runner_sha256,
            "runtime_sha256": self.runtime_sha256,
        }


@dataclass(frozen=True, slots=True)
class RootlessDependencyEvaluationDesignV2:
    """One future V2 experiment after its four commitments are provisioned."""

    development_roster: FreshDevelopmentCommitmentRosterV2

    def __post_init__(self) -> None:
        if not isinstance(self.development_roster, FreshDevelopmentCommitmentRosterV2):
            raise LivingDexDependencyEvaluationV2Error("V2 development roster differs")
        _fresh_sha256(self.design_sha256, subject="V2 semantic design")

    @property
    def train_revalidation_sha256(self) -> str:
        return canonical_sha256(rootless_dependency_train_revalidation_contract_v2())

    @property
    def design_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_EVALUATION_DESIGN_V2_SCHEMA,
            "lane_id": ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
            "development_roster": self.development_roster.public_dict(),
            "development_structure_domain": {
                "minimum_required_count": ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT,
                "maximum_required_count": ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT,
                "v1_generator_domain_excluded": "3_through_15",
                "public_train_domain_excluded": "1_through_2",
                "families": 2,
                "multiplicities_per_family": 2,
                "ranker_numeric_support": (
                    "continuous_numeric_features_without_embedding_or_bounded_integer_lookup"
                ),
            },
            "train_revalidation": rootless_dependency_train_revalidation_contract_v2(),
            "ranker_contract": rootless_dependency_ranker_contract_v2(),
            "stage_contract": rootless_dependency_stage_contract_v2(),
            "counter_contract": rootless_dependency_counter_contract_v2(),
            "retired_v1_identity_set_sha256": retired_v1_identity_set_sha256(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> RootlessDependencyEvaluationDesignV2:
        expected = {
            "schema",
            "lane_id",
            "development_roster",
            "development_structure_domain",
            "train_revalidation",
            "ranker_contract",
            "stage_contract",
            "counter_contract",
            "retired_v1_identity_set_sha256",
        }
        roster_value = value.get("development_roster") if isinstance(value, Mapping) else None
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value.get("schema") != ROOTLESS_DEPENDENCY_EVALUATION_DESIGN_V2_SCHEMA
            or value.get("lane_id") != ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2
            or not isinstance(roster_value, Mapping)
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 design fields differ")
        design = cls(FreshDevelopmentCommitmentRosterV2.from_dict(roster_value))
        if design.public_dict() != dict(value):
            raise LivingDexDependencyEvaluationV2Error("V2 design fields differ")
        return design


@dataclass(frozen=True, slots=True)
class DependencyFitClaimV2:
    design_sha256: str
    development_roster_sha256: str
    train_revalidation_sha256: str
    ranker_contract_sha256: str
    execution_binding: EvaluationExecutionBindingV2

    def __post_init__(self) -> None:
        for subject, value in (
            ("design", self.design_sha256),
            ("development roster", self.development_roster_sha256),
            ("train revalidation", self.train_revalidation_sha256),
            ("ranker contract", self.ranker_contract_sha256),
        ):
            _fresh_sha256(value, subject=f"V2 fit {subject}")
        if (
            not isinstance(self.execution_binding, EvaluationExecutionBindingV2)
            or self.execution_binding.operation != "fit"
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 fit execution binding differs")
        _fresh_sha256(self.semantic_claim_sha256, subject="V2 fit semantic claim")
        _fresh_sha256(self.execution_identity_sha256, subject="V2 fit execution identity")

    @property
    def semantic_claim_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": ROOTLESS_DEPENDENCY_FIT_CLAIM_V2_SCHEMA,
                "lane_id": ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
                "design_sha256": self.design_sha256,
                "development_roster_sha256": self.development_roster_sha256,
                "train_revalidation_sha256": self.train_revalidation_sha256,
                "ranker_contract_sha256": self.ranker_contract_sha256,
                "retry_allowed": False,
            }
        )

    @property
    def execution_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": "pokemon.core.rootless-dependency-fit-execution-identity.v2",
                "semantic_claim_sha256": self.semantic_claim_sha256,
                "execution_binding_sha256": self.execution_binding.execution_identity_sha256,
            }
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_FIT_CLAIM_V2_SCHEMA,
            "design_sha256": self.design_sha256,
            "development_roster_sha256": self.development_roster_sha256,
            "train_revalidation_sha256": self.train_revalidation_sha256,
            "ranker_contract_sha256": self.ranker_contract_sha256,
            "semantic_claim_sha256": self.semantic_claim_sha256,
            "execution_binding": self.execution_binding.public_dict(),
            "execution_identity_sha256": self.execution_identity_sha256,
            "claim_before_fit": True,
            "development_payloads_permitted": 0,
            "retry_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class DependencyComparisonClaimV2:
    design_sha256: str
    development_roster_sha256: str
    fit_claim_sha256: str
    fit_execution_identity_sha256: str
    fit_bundle_pins: DependencyEvaluationBundlePins
    execution_binding: EvaluationExecutionBindingV2

    def __post_init__(self) -> None:
        for subject, value in (
            ("design", self.design_sha256),
            ("development roster", self.development_roster_sha256),
            ("fit claim", self.fit_claim_sha256),
            ("fit execution identity", self.fit_execution_identity_sha256),
        ):
            _fresh_sha256(value, subject=f"V2 comparison {subject}")
        if not isinstance(self.fit_bundle_pins, DependencyEvaluationBundlePins):
            raise LivingDexDependencyEvaluationV2Error("V2 comparison fit bundle pins differ")
        for value in self.fit_bundle_pins.public_dict().values():
            _fresh_sha256(value, subject="V2 comparison fit bundle")
        if self.fit_bundle_pins.fit_identity.design_sha256 != self.design_sha256:
            raise LivingDexDependencyEvaluationV2Error(
                "V2 comparison design and completed fit differ"
            )
        if (
            not isinstance(self.execution_binding, EvaluationExecutionBindingV2)
            or self.execution_binding.operation != "comparison"
        ):
            raise LivingDexDependencyEvaluationV2Error("V2 comparison execution binding differs")
        _fresh_sha256(self.semantic_claim_sha256, subject="V2 comparison semantic claim")
        _fresh_sha256(self.execution_identity_sha256, subject="V2 comparison execution identity")
        if self.semantic_claim_sha256 == self.fit_claim_sha256:
            raise LivingDexDependencyEvaluationV2Error(
                "V2 fit and comparison claims must be distinct"
            )

    @property
    def semantic_claim_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": ROOTLESS_DEPENDENCY_COMPARISON_CLAIM_V2_SCHEMA,
                "lane_id": ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
                "design_sha256": self.design_sha256,
                "development_roster_sha256": self.development_roster_sha256,
                "fit_claim_sha256": self.fit_claim_sha256,
                "fit_execution_identity_sha256": self.fit_execution_identity_sha256,
                "fit_bundle_pins": self.fit_bundle_pins.public_dict(),
                "development_rows": 4,
                "retry_allowed": False,
            }
        )

    @property
    def execution_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": "pokemon.core.rootless-dependency-comparison-execution-identity.v2",
                "semantic_claim_sha256": self.semantic_claim_sha256,
                "execution_binding_sha256": self.execution_binding.execution_identity_sha256,
            }
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_COMPARISON_CLAIM_V2_SCHEMA,
            "design_sha256": self.design_sha256,
            "development_roster_sha256": self.development_roster_sha256,
            "fit_claim_sha256": self.fit_claim_sha256,
            "fit_execution_identity_sha256": self.fit_execution_identity_sha256,
            "fit_bundle_pins": self.fit_bundle_pins.public_dict(),
            "semantic_claim_sha256": self.semantic_claim_sha256,
            "execution_binding": self.execution_binding.public_dict(),
            "execution_identity_sha256": self.execution_identity_sha256,
            "fit_bundle_authenticated_before_payload_open": True,
            "claim_before_payload_open": True,
            "development_payloads_exactly": 4,
            "retry_allowed": False,
        }


def build_dependency_fit_claim_v2(
    design: RootlessDependencyEvaluationDesignV2,
    *,
    execution_binding: EvaluationExecutionBindingV2,
) -> DependencyFitClaimV2:
    if not isinstance(design, RootlessDependencyEvaluationDesignV2):
        raise TypeError("design must be a RootlessDependencyEvaluationDesignV2")
    return DependencyFitClaimV2(
        design_sha256=design.design_sha256,
        development_roster_sha256=design.development_roster.roster_sha256,
        train_revalidation_sha256=design.train_revalidation_sha256,
        ranker_contract_sha256=canonical_sha256(rootless_dependency_ranker_contract_v2()),
        execution_binding=execution_binding,
    )


def build_dependency_comparison_claim_v2(
    design: RootlessDependencyEvaluationDesignV2,
    *,
    fit_claim: DependencyFitClaimV2,
    fit_bundle_pins: DependencyEvaluationBundlePins,
    execution_binding: EvaluationExecutionBindingV2,
) -> DependencyComparisonClaimV2:
    if not isinstance(design, RootlessDependencyEvaluationDesignV2):
        raise TypeError("design must be a RootlessDependencyEvaluationDesignV2")
    if not isinstance(fit_claim, DependencyFitClaimV2):
        raise TypeError("fit_claim must be a DependencyFitClaimV2")
    if (
        fit_claim.design_sha256 != design.design_sha256
        or fit_claim.development_roster_sha256 != design.development_roster.roster_sha256
        or fit_claim.train_revalidation_sha256 != design.train_revalidation_sha256
    ):
        raise LivingDexDependencyEvaluationV2Error(
            "V2 comparison cannot replace its frozen fit design"
        )
    return DependencyComparisonClaimV2(
        design_sha256=design.design_sha256,
        development_roster_sha256=design.development_roster.roster_sha256,
        fit_claim_sha256=fit_claim.semantic_claim_sha256,
        fit_execution_identity_sha256=fit_claim.execution_identity_sha256,
        fit_bundle_pins=fit_bundle_pins,
        execution_binding=execution_binding,
    )


def rootless_dependency_evaluation_blueprint_v2() -> dict[str, object]:
    """Return the public design qualified in this lane, before provisioning."""

    return {
        "schema": "pokemon.core.rootless-dependency-evaluation-blueprint.v2",
        "lane_id": ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
        "commitment_contract": {
            "schema": ROOTLESS_DEPENDENCY_DEVELOPMENT_COMMITMENT_V2_SCHEMA,
            "roster_schema": ROOTLESS_DEPENDENCY_DEVELOPMENT_ROSTER_V2_SCHEMA,
            "opening_schema": ROOTLESS_DEPENDENCY_DEVELOPMENT_OPENING_SCHEMA_V2,
            "record_id_pattern": _V2_RECORD_ID.pattern,
            "record_kind": ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
            "rows": 4,
            "payload_fields_public": [],
            "metadata_fields_public": [
                "record_id",
                "manifest_sha256",
                "declared_record_sha256",
                "declared_total_bytes",
            ],
            "minimum_required_count": ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT,
            "maximum_required_count": ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT,
            "private_opening_fields": [
                "scenario_id",
                "family_id",
                "nonce",
                "partition",
                "multiplicity",
                "structure",
                "before",
                "assigned_action",
            ],
            "opening_contains_outcome_or_reward": False,
            "nonce_bytes": ROOTLESS_DEPENDENCY_V2_NONCE_BYTES,
            "nonce_generation": "cryptographically_secure_random_at_provisioning",
            "nonce_inside_committed_private_payload": True,
            "commitment_dictionary_attack_falsifies_provisioning": True,
            "v1_opening_reuse_allowed": False,
        },
        "train_revalidation": rootless_dependency_train_revalidation_contract_v2(),
        "ranker_contract": rootless_dependency_ranker_contract_v2(),
        "stage_contract": rootless_dependency_stage_contract_v2(),
        "counter_contract": rootless_dependency_counter_contract_v2(),
        "retired_v1_identity_set_sha256": retired_v1_identity_set_sha256(),
        "private_artifact_accesses": 0,
        "model_fits": 0,
        "development_payloads_decoded": 0,
        "comparisons": 0,
    }


def rootless_dependency_train_revalidation_contract_v2() -> dict[str, object]:
    rows = _canonical_train_value_rows_v2()
    return {
        "schema": ROOTLESS_DEPENDENCY_TRAIN_REVALIDATION_V2_SCHEMA,
        "source": "public_canonical_train_semantics_recomputed_without_v1_artifact_reads",
        "rows": 8,
        "canonical_values_sha256": canonical_sha256(
            {
                "schema": "pokemon.core.rootless-dependency-train-values.v2",
                "rows": rows,
            }
        ),
        "canonical_values": rows,
        "expected_actions": {"acquire_species": 4, "evolve_species": 4},
        "expected_rewards": {"negative": 4, "positive": 4},
        "v1_train_artifact_reads": 0,
        "new_outcomes_added": 0,
        "new_atomic_episodes_added": 0,
        "fit_identity_must_be_fresh": True,
    }


def rootless_dependency_ranker_contract_v2() -> dict[str, object]:
    return {
        "schema": "pokemon.core.rootless-dependency-ranker-contract.v2",
        "head": "separate_rootless_state_by_action_interaction_ranker",
        "objective": "pairwise-logistic-ridge-fixed-v1",
        "feature_names": [
            "adds_precursor",
            "consumes_precursor",
            "has_precursor_surplus_x_adds_precursor",
            "has_precursor_surplus_x_consumes_precursor",
        ],
        "iterations": 512,
        "learning_rate": 0.08,
        "ridge": 0.05,
        "hyperparameter_search": False,
        "development_input_to_fit": False,
        "numeric_support": (
            "continuous_numeric_features_without_embedding_or_bounded_integer_lookup"
        ),
        "required_count_support_inclusive": [
            ROOTLESS_DEPENDENCY_V2_MINIMUM_REQUIREMENT_COUNT,
            ROOTLESS_DEPENDENCY_V2_MAXIMUM_REQUIREMENT_COUNT,
        ],
        "fit_record_design_sha256": "must_equal_outer_v2_design_sha256",
        "fit_train_dataset_sha256": "must_equal_v2_train_revalidation_record_sha256",
        "v1_fit_or_model_reuse_allowed": False,
        "gameplay_goal_manager_updated": False,
    }


def rootless_dependency_stage_contract_v2() -> dict[str, object]:
    return {
        "schema": ROOTLESS_DEPENDENCY_STAGE_CONTRACT_V2_SCHEMA,
        "ordered_stages": [stage.value for stage in RootlessDependencyEvaluationStageV2],
        "process_boundaries": [
            ["provision", "fit_preflight"],
            ["fit", "comparison_preflight"],
            ["comparison_preflight", "comparison"],
        ],
        "fit": {
            "metadata_only_commitment_inspection": True,
            "development_payloads_opened": 0,
            "claim_before_computation": True,
            "one_shot": True,
            "retry_allowed": False,
            "purpose": "untainted_compliance_replacement_not_new_learning_output",
        },
        "comparison_preflight": {
            "metadata_only_commitment_inspection": True,
            "development_payloads_opened": 0,
            "externally_pinned_exact_fit_bundle_required": True,
            "comparison_claim_consumed": False,
        },
        "comparison": {
            "fresh_process_required": True,
            "externally_pinned_exact_fit_bundle_required": True,
            "claim_before_first_payload_open": True,
            "development_payloads_opened": 4,
            "aggregate_only_public_result": True,
            "one_shot": True,
            "retry_allowed": False,
        },
        "same_process_fit_and_comparison_allowed": False,
        "replacement_openings_allowed": False,
        "retired_v1_identity_reuse_allowed": False,
    }


def rootless_dependency_counter_contract_v2() -> dict[str, object]:
    return {
        "schema": ROOTLESS_DEPENDENCY_COUNTER_CONTRACT_V2_SCHEMA,
        "design_provision_preflight_and_train_revalidation": dict(_ZERO_COUNTERS),
        "completed_fit": {
            **dict(_ZERO_COUNTERS),
        },
        "failed_or_interrupted_fit": dict(_ZERO_COUNTERS),
        "completed_comparison": {
            **dict(_ZERO_COUNTERS),
            "synthetic_rootless_unseen_comparisons_added": 1,
            "unseen_comparisons_added": 1,
        },
        "failed_or_interrupted_comparison": dict(_ZERO_COUNTERS),
        "synthetic_results_are_gameplay": False,
        "completed_fit_event": (
            "clean_replacement_artifact_for_already_counted_identical_eight_row_fit"
        ),
        "completed_fit_adds_learning_counter": False,
        "completed_comparison_uses_fresh_v2_development_rows": True,
        "completed_fit_is_authority": False,
        "completed_comparison_is_transfer": False,
    }


def retired_v1_identity_set_sha256() -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.core.retired-rootless-dependency-v1-identities.v1",
            "sha256s": sorted(RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES),
        }
    )


def _canonical_train_value_rows_v2() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    structures = ((1, 1), (2, 1), (1, 2), (2, 2))
    for family, (required_precursor, required_evolved) in enumerate(structures):
        for multiplicity_index, multiplicity in enumerate(DependencyMultiplicity):
            scarce = multiplicity is DependencyMultiplicity.SCARCE
            assigned_action = (
                GoalKind.ACQUIRE_SPECIES if scarce == (family % 2 == 0) else GoalKind.EVOLVE_SPECIES
            )
            positive = (scarce and assigned_action is GoalKind.ACQUIRE_SPECIES) or (
                not scarce and assigned_action is GoalKind.EVOLVE_SPECIES
            )
            rows.append(
                {
                    "scenario_id": f"rootless-train-{family + 1:02d}-{multiplicity_index + 1:02d}",
                    "family_ordinal": family,
                    "multiplicity": multiplicity.value,
                    "required_precursor_count": required_precursor,
                    "required_evolved_count": required_evolved,
                    "assigned_action": assigned_action.value,
                    "derived_reward": 1 if positive else -1,
                }
            )
    return rows


def _fresh_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexDependencyEvaluationV2Error(f"{subject} identity is invalid")
    if value in RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES:
        raise LivingDexDependencyEvaluationV2Error(f"{subject} reuses a retired V1 identity")
    return value
