"""Frozen, source-bound operating evidence for training venues.

Party-development outcomes may compare trainees or venues, but the outcome
being measured cannot also invent the venue facts used as its model input.
This module keeps that boundary explicit.  Each prior is derived from audited
unit ratios over independent roots, bound to the exact private venue band, and
frozen in a registry before a prospective outcome catalog is constructed.

Public projections expose only digests and counts.  Area labels, encounter
conditions, roots, and state identities remain in the private registry used by
the title adapter.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.party_development_rank import VenueOperationalPrior
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.team_training import GrindingArea

PARTY_DEVELOPMENT_VENUE_PRIOR_EVIDENCE_SCHEMA = (
    "pokemon.core.party-development-venue-prior-evidence.v1"
)
PARTY_DEVELOPMENT_VENUE_PRIOR_REGISTRY_SCHEMA = (
    "pokemon.core.party-development-venue-prior-registry.v1"
)

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class PartyDevelopmentVenuePriorError(ValueError):
    """Raised when venue evidence is mutable, unbound, or self-referential."""


@dataclass(frozen=True, slots=True)
class VenuePriorUnitRatio:
    """One auditable unit interval represented by integer evidence."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if (
            type(self.numerator) is not int  # noqa: E721
            or type(self.denominator) is not int  # noqa: E721
            or self.denominator <= 0
            or not 0 <= self.numerator <= self.denominator
        ):
            raise PartyDevelopmentVenuePriorError(
                "venue-prior ratio must be bounded non-negative integer evidence"
            )

    @property
    def value(self) -> float:
        return self.numerator / self.denominator

    def public_dict(self) -> dict[str, int]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
        }

    @classmethod
    def from_dict(cls, value: object) -> VenuePriorUnitRatio:
        if not isinstance(value, Mapping) or set(value) != {
            "denominator",
            "numerator",
        }:
            raise PartyDevelopmentVenuePriorError("venue-prior ratio document is invalid")
        return cls(
            numerator=value["numerator"],  # type: ignore[arg-type]
            denominator=value["denominator"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class VenuePriorEvidence:
    """Independent measurements for one exact private venue definition."""

    evidence_id: str
    venue: GrindingArea
    source_commit: str
    source_bundle_sha256: str
    measurement_contract_sha256: str
    operational_contract_sha256: str
    support_root_lineage_ids: tuple[str, ...]
    support_state_sha256: tuple[str, ...]
    outcome_receipt_sha256: tuple[str, ...]
    reliability: VenuePriorUnitRatio
    expected_yield: VenuePriorUnitRatio
    matchup_safety: VenuePriorUnitRatio
    travel_cost: VenuePriorUnitRatio
    recovery_cost: VenuePriorUnitRatio

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or _SAFE_ID.fullmatch(self.evidence_id) is None:
            raise PartyDevelopmentVenuePriorError("venue-prior evidence id is invalid")
        if not isinstance(self.venue, GrindingArea):
            raise PartyDevelopmentVenuePriorError(
                "venue-prior evidence needs an exact training venue"
            )
        if (
            not isinstance(self.source_commit, str)
            or _GIT_OID.fullmatch(self.source_commit) is None
        ):
            raise PartyDevelopmentVenuePriorError("venue-prior evidence source commit is invalid")
        _require_digest(self.source_bundle_sha256, subject="source bundle")
        _require_digest(
            self.measurement_contract_sha256,
            subject="measurement contract",
        )
        _require_digest(
            self.operational_contract_sha256,
            subject="operational contract",
        )
        roots = self.support_root_lineage_ids
        states = self.support_state_sha256
        if (
            not isinstance(roots, tuple)
            or not roots
            or len(roots) != len(states)
            or any(not isinstance(root, str) or _SAFE_ID.fullmatch(root) is None for root in roots)
            or any(
                not isinstance(state, str) or _SHA256.fullmatch(state) is None for state in states
            )
            or len(roots) != len(set(roots))
            or len(states) != len(set(states))
            or tuple(zip(roots, states, strict=True))
            != tuple(sorted(zip(roots, states, strict=True)))
        ):
            raise PartyDevelopmentVenuePriorError(
                "venue-prior support roots and states must be unique canonical pairs"
            )
        receipts = self.outcome_receipt_sha256
        if (
            not isinstance(receipts, tuple)
            or not receipts
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in receipts
            )
            or receipts != tuple(sorted(set(receipts)))
        ):
            raise PartyDevelopmentVenuePriorError("venue-prior outcome receipt digests are invalid")
        for value in (
            self.reliability,
            self.expected_yield,
            self.matchup_safety,
            self.travel_cost,
            self.recovery_cost,
        ):
            if not isinstance(value, VenuePriorUnitRatio):
                raise PartyDevelopmentVenuePriorError(
                    "venue-prior measurements must use auditable unit ratios"
                )

    @property
    def support_count(self) -> int:
        return len(self.support_root_lineage_ids)

    @property
    def venue_binding_sha256(self) -> str:
        return canonical_sha256(_venue_document(self.venue))

    @property
    def evidence_sha256(self) -> str:
        return canonical_sha256(self._evidence_document())

    def operational_prior(self) -> VenueOperationalPrior:
        return VenueOperationalPrior(
            available=True,
            reliability=self.reliability.value,
            expected_yield=self.expected_yield.value,
            matchup_safety=self.matchup_safety.value,
            travel_cost=self.travel_cost.value,
            recovery_cost=self.recovery_cost.value,
            support_count=self.support_count,
            evidence_sha256=self.evidence_sha256,
            frozen_before_scenario=True,
        )

    def _evidence_document(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_VENUE_PRIOR_EVIDENCE_SCHEMA,
            "evidence_id": self.evidence_id,
            "venue_binding_sha256": self.venue_binding_sha256,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "measurement_contract_sha256": self.measurement_contract_sha256,
            "operational_contract_sha256": self.operational_contract_sha256,
            "support_root_lineage_ids": list(self.support_root_lineage_ids),
            "support_state_sha256": list(self.support_state_sha256),
            "outcome_receipt_sha256": list(self.outcome_receipt_sha256),
            "measurements": {
                "reliability": self.reliability.public_dict(),
                "expected_yield": self.expected_yield.public_dict(),
                "matchup_safety": self.matchup_safety.public_dict(),
                "travel_cost": self.travel_cost.public_dict(),
                "recovery_cost": self.recovery_cost.public_dict(),
            },
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self._evidence_document(),
            "venue": _venue_document(self.venue),
            "evidence_sha256": self.evidence_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_VENUE_PRIOR_EVIDENCE_SCHEMA,
            "evidence_sha256": self.evidence_sha256,
            "venue_binding_sha256": self.venue_binding_sha256,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "measurement_contract_sha256": self.measurement_contract_sha256,
            "operational_contract_sha256": self.operational_contract_sha256,
            "support_count": self.support_count,
            "outcome_receipt_count": len(self.outcome_receipt_sha256),
            "private_venue_identity_public": False,
            "support_identity_public": False,
            "private_path_fields": 0,
        }

    @classmethod
    def from_private_dict(cls, value: object) -> VenuePriorEvidence:
        if not isinstance(value, Mapping) or set(value) != {
            "evidence_id",
            "evidence_sha256",
            "measurement_contract_sha256",
            "measurements",
            "operational_contract_sha256",
            "outcome_receipt_sha256",
            "schema",
            "source_bundle_sha256",
            "source_commit",
            "support_root_lineage_ids",
            "support_state_sha256",
            "venue",
            "venue_binding_sha256",
        }:
            raise PartyDevelopmentVenuePriorError("venue-prior evidence document is invalid")
        if value["schema"] != PARTY_DEVELOPMENT_VENUE_PRIOR_EVIDENCE_SCHEMA:
            raise PartyDevelopmentVenuePriorError("venue-prior evidence schema is unsupported")
        venue = _venue_from_document(value["venue"])
        measurements = value["measurements"]
        if not isinstance(measurements, Mapping) or set(measurements) != {
            "expected_yield",
            "matchup_safety",
            "recovery_cost",
            "reliability",
            "travel_cost",
        }:
            raise PartyDevelopmentVenuePriorError("venue-prior measurement document is invalid")
        result = cls(
            evidence_id=value["evidence_id"],  # type: ignore[arg-type]
            venue=venue,
            source_commit=value["source_commit"],  # type: ignore[arg-type]
            source_bundle_sha256=value["source_bundle_sha256"],  # type: ignore[arg-type]
            measurement_contract_sha256=value[  # type: ignore[arg-type]
                "measurement_contract_sha256"
            ],
            operational_contract_sha256=value[  # type: ignore[arg-type]
                "operational_contract_sha256"
            ],
            support_root_lineage_ids=_string_tuple(
                value["support_root_lineage_ids"], subject="support roots"
            ),
            support_state_sha256=_string_tuple(
                value["support_state_sha256"], subject="support states"
            ),
            outcome_receipt_sha256=_string_tuple(
                value["outcome_receipt_sha256"], subject="outcome receipts"
            ),
            reliability=VenuePriorUnitRatio.from_dict(measurements["reliability"]),
            expected_yield=VenuePriorUnitRatio.from_dict(measurements["expected_yield"]),
            matchup_safety=VenuePriorUnitRatio.from_dict(measurements["matchup_safety"]),
            travel_cost=VenuePriorUnitRatio.from_dict(measurements["travel_cost"]),
            recovery_cost=VenuePriorUnitRatio.from_dict(measurements["recovery_cost"]),
        )
        if value["venue_binding_sha256"] != result.venue_binding_sha256:
            raise PartyDevelopmentVenuePriorError("venue-prior venue binding digest differs")
        if value["evidence_sha256"] != result.evidence_sha256:
            raise PartyDevelopmentVenuePriorError("venue-prior evidence digest differs")
        return result


@dataclass(frozen=True, slots=True)
class PartyDevelopmentVenuePriorRegistry:
    """Immutable venue evidence available before prospective outcomes."""

    source_commit: str
    source_bundle_sha256: str
    entries: tuple[VenuePriorEvidence, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_commit, str)
            or _GIT_OID.fullmatch(self.source_commit) is None
        ):
            raise PartyDevelopmentVenuePriorError("venue-prior registry source commit is invalid")
        _require_digest(self.source_bundle_sha256, subject="registry source bundle")
        if (
            not isinstance(self.entries, tuple)
            or any(not isinstance(item, VenuePriorEvidence) for item in self.entries)
            or self.entries
            != tuple(sorted(self.entries, key=lambda item: item.venue_binding_sha256))
        ):
            raise PartyDevelopmentVenuePriorError(
                "venue-prior entries must use canonical venue-binding order"
            )
        for attribute, subject in (
            ("venue_binding_sha256", "venue binding"),
            ("evidence_sha256", "evidence"),
            ("evidence_id", "evidence id"),
        ):
            values = tuple(getattr(item, attribute) for item in self.entries)
            if len(values) != len(set(values)):
                raise PartyDevelopmentVenuePriorError(f"venue-prior registry repeats a {subject}")
        measurement_contracts = {item.measurement_contract_sha256 for item in self.entries}
        if len(measurement_contracts) > 1:
            raise PartyDevelopmentVenuePriorError(
                "venue-prior registry crosses measurement contracts"
            )

    @classmethod
    def freeze(
        cls,
        *,
        source_commit: str,
        source_bundle_sha256: str,
        entries: tuple[VenuePriorEvidence, ...],
    ) -> PartyDevelopmentVenuePriorRegistry:
        return cls(
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            entries=tuple(sorted(entries, key=lambda item: item.venue_binding_sha256)),
        )

    @property
    def registry_sha256(self) -> str:
        return canonical_sha256(self._registry_document())

    def evidence_for(self, venue: GrindingArea) -> VenuePriorEvidence | None:
        if not isinstance(venue, GrindingArea):
            raise TypeError("venue must be a GrindingArea")
        binding = canonical_sha256(_venue_document(venue))
        return next(
            (item for item in self.entries if item.venue_binding_sha256 == binding),
            None,
        )

    def prior_for(
        self,
        venue: GrindingArea,
        *,
        operational_contract_sha256: str,
    ) -> VenueOperationalPrior:
        _require_digest(
            operational_contract_sha256,
            subject="requested operational contract",
        )
        evidence = self.evidence_for(venue)
        return (
            evidence.operational_prior()
            if evidence is not None
            and evidence.operational_contract_sha256 == operational_contract_sha256
            else VenueOperationalPrior()
        )

    def require_scenario_is_independent(
        self, *, root_lineage_id: str, initial_state_sha256: str
    ) -> None:
        if not isinstance(root_lineage_id, str) or _SAFE_ID.fullmatch(root_lineage_id) is None:
            raise PartyDevelopmentVenuePriorError("prospective root lineage is invalid")
        _require_digest(initial_state_sha256, subject="prospective initial state")
        if any(root_lineage_id in item.support_root_lineage_ids for item in self.entries):
            raise PartyDevelopmentVenuePriorError("prospective root already supports a venue prior")
        if any(initial_state_sha256 in item.support_state_sha256 for item in self.entries):
            raise PartyDevelopmentVenuePriorError(
                "prospective state already supports a venue prior"
            )

    def _registry_document(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_VENUE_PRIOR_REGISTRY_SCHEMA,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "entries": [item.private_dict() for item in self.entries],
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self._registry_document(),
            "registry_sha256": self.registry_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_VENUE_PRIOR_REGISTRY_SCHEMA,
            "registry_sha256": self.registry_sha256,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "entry_count": len(self.entries),
            "venue_binding_sha256": [item.venue_binding_sha256 for item in self.entries],
            "evidence_sha256": [item.evidence_sha256 for item in self.entries],
            "operational_contract_sha256": [
                item.operational_contract_sha256 for item in self.entries
            ],
            "support_count": sum(item.support_count for item in self.entries),
            "measurement_contract_sha256": (
                self.entries[0].measurement_contract_sha256 if self.entries else None
            ),
            "private_venue_identity_public": False,
            "support_identity_public": False,
            "outcomes_opened": 0,
            "teacher_queries": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }

    @classmethod
    def from_private_dict(cls, value: object) -> PartyDevelopmentVenuePriorRegistry:
        if not isinstance(value, Mapping) or set(value) != {
            "entries",
            "registry_sha256",
            "schema",
            "source_bundle_sha256",
            "source_commit",
        }:
            raise PartyDevelopmentVenuePriorError("venue-prior registry document is invalid")
        if value["schema"] != PARTY_DEVELOPMENT_VENUE_PRIOR_REGISTRY_SCHEMA:
            raise PartyDevelopmentVenuePriorError("venue-prior registry schema is unsupported")
        rows = value["entries"]
        if not isinstance(rows, list):
            raise PartyDevelopmentVenuePriorError("venue-prior registry entries must be a list")
        result = cls(
            source_commit=value["source_commit"],  # type: ignore[arg-type]
            source_bundle_sha256=value["source_bundle_sha256"],  # type: ignore[arg-type]
            entries=tuple(VenuePriorEvidence.from_private_dict(row) for row in rows),
        )
        if value["registry_sha256"] != result.registry_sha256:
            raise PartyDevelopmentVenuePriorError("venue-prior registry digest differs")
        return result


def _venue_document(venue: GrindingArea) -> dict[str, object]:
    return {
        "schema": "pokemon.core.party-development-private-venue-binding.v1",
        "area_id": venue.area_id,
        "conditions": list(venue.conditions),
        "minimum_encounter_level": venue.minimum_encounter_level,
        "maximum_encounter_level": venue.maximum_encounter_level,
        "rare_maximum_encounter_level": venue.rare_maximum_encounter_level,
        "has_nearby_healer": venue.has_nearby_healer,
        "measured_samples": venue.measured_samples,
    }


def _venue_from_document(value: object) -> GrindingArea:
    if not isinstance(value, Mapping) or set(value) != {
        "area_id",
        "conditions",
        "has_nearby_healer",
        "maximum_encounter_level",
        "measured_samples",
        "minimum_encounter_level",
        "rare_maximum_encounter_level",
        "schema",
    }:
        raise PartyDevelopmentVenuePriorError("venue-prior private venue binding is invalid")
    if value["schema"] != "pokemon.core.party-development-private-venue-binding.v1":
        raise PartyDevelopmentVenuePriorError("venue-prior private venue schema is unsupported")
    conditions = _string_tuple(value["conditions"], subject="venue conditions")
    return GrindingArea(
        area_id=value["area_id"],  # type: ignore[arg-type]
        minimum_encounter_level=value["minimum_encounter_level"],  # type: ignore[arg-type]
        maximum_encounter_level=value["maximum_encounter_level"],  # type: ignore[arg-type]
        has_nearby_healer=value["has_nearby_healer"],  # type: ignore[arg-type]
        rare_maximum_encounter_level=value[  # type: ignore[arg-type]
            "rare_maximum_encounter_level"
        ],
        measured_samples=value["measured_samples"],  # type: ignore[arg-type]
        conditions=conditions,
    )


def _string_tuple(value: object, *, subject: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PartyDevelopmentVenuePriorError(f"venue-prior {subject} must be a string list")
    return tuple(value)


def _require_digest(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PartyDevelopmentVenuePriorError(f"venue-prior {subject} digest is invalid")


__all__ = [
    "PARTY_DEVELOPMENT_VENUE_PRIOR_EVIDENCE_SCHEMA",
    "PARTY_DEVELOPMENT_VENUE_PRIOR_REGISTRY_SCHEMA",
    "PartyDevelopmentVenuePriorError",
    "PartyDevelopmentVenuePriorRegistry",
    "VenuePriorEvidence",
    "VenuePriorUnitRatio",
]
