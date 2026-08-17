"""Prospective, path-free bindings for party-development outcome catalogs.

The generic outcome row intentionally hides private candidate feature values.
That also means it cannot prove on its own that a venue prior existed before an
outcome was opened.  This module freezes the candidate menu, availability,
partition, starting state, source, and independent venue-evidence digests first.
Later outcomes may join only to those exact bindings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.party_development_rank import (
    MAX_PRIOR_SUPPORT,
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    PartyDevelopmentCandidateSet,
    PartyDevelopmentGoal,
    VenueOperationalPrior,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeExample
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PARTY_DEVELOPMENT_PROSPECTIVE_CATALOG_SCHEMA = (
    "pokemon.core.party-development-prospective-catalog.v6"
)
PARTY_DEVELOPMENT_PROSPECTIVE_BINDING_SCHEMA = (
    "pokemon.core.party-development-prospective-binding.v6"
)

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class PartyDevelopmentCatalogError(ValueError):
    """Raised when prospective evidence is missing, mutable, or mismatched."""


class PartyDevelopmentUnavailableReason(StrEnum):
    """Why a party candidate is visible but excluded from causal authority."""

    EXTERNAL_DEPENDENCY = "external_dependency"
    BATTLE_POLICY_INCOMPATIBLE = "battle_policy_incompatible"
    INSUFFICIENT_VENUE_EVIDENCE = "insufficient_venue_evidence"
    INSUFFICIENT_RECOVERY_CAPACITY = "insufficient_recovery_capacity"
    MISSING_RESOURCE = "missing_resource"
    STORAGE_BLOCKED = "storage_blocked"
    STORY_GATE_CLOSED = "story_gate_closed"
    TEMPORARILY_UNSAFE = "temporarily_unsafe"
    TRANSITION_UNAVAILABLE = "transition_unavailable"
    WORLD_STATE_UNKNOWN = "world_state_unknown"


@dataclass(frozen=True, slots=True)
class PartyDevelopmentProspectiveBinding:
    """One candidate menu frozen before any candidate outcome is measured."""

    scenario_id: str
    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    source_commit: str
    source_bundle_sha256: str
    semantic_snapshot_sha256: str
    venue_prior_registry_sha256: str
    outcome_objective_sha256: str
    feature_names_sha256: str
    kind: TrainingChoiceKind
    goal: PartyDevelopmentGoal
    candidate_feature_sha256: tuple[str, ...]
    candidate_available: tuple[bool, ...]
    candidate_unavailable_reasons: tuple[PartyDevelopmentUnavailableReason | None, ...]
    venue_prior_evidence_sha256: tuple[str | None, ...]
    shared_venue_prior_evidence_sha256: str | None
    candidate_menu_sha256: str
    binding_sha256: str
    feature_schema_id: str = PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        for value, subject in (
            (self.scenario_id, "scenario"),
            (self.root_lineage_id, "root lineage"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise PartyDevelopmentCatalogError(
                    f"party-development prospective {subject} is invalid"
                )
        for value, subject in (
            (self.initial_state_sha256, "initial state"),
            (self.source_bundle_sha256, "source bundle"),
            (self.semantic_snapshot_sha256, "semantic snapshot"),
            (self.venue_prior_registry_sha256, "venue-prior registry"),
            (self.outcome_objective_sha256, "outcome objective"),
            (self.feature_names_sha256, "feature names"),
            (self.candidate_menu_sha256, "candidate menu"),
            (self.binding_sha256, "binding"),
        ):
            _require_digest(value, subject=subject)
        if (
            not isinstance(self.source_commit, str)
            or _GIT_OID.fullmatch(self.source_commit) is None
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective source commit is invalid"
            )
        if not isinstance(self.partition, ScenarioPartition):
            raise PartyDevelopmentCatalogError("party-development prospective partition is invalid")
        if not isinstance(self.kind, TrainingChoiceKind) or not isinstance(
            self.goal, PartyDevelopmentGoal
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective decision semantics are invalid"
            )
        if self.feature_schema_id != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID:
            raise PartyDevelopmentCatalogError(
                "party-development prospective feature schema is invalid"
            )
        count = len(self.candidate_feature_sha256)
        if (
            count < 2
            or len(self.candidate_available) != count
            or len(self.candidate_unavailable_reasons) != count
            or len(self.venue_prior_evidence_sha256) != count
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None
                for value in self.candidate_feature_sha256
            )
            or any(not isinstance(value, bool) for value in self.candidate_available)
            or any(
                reason is not None
                and not isinstance(reason, PartyDevelopmentUnavailableReason)
                for reason in self.candidate_unavailable_reasons
            )
            or sum(self.candidate_available) < 2
            or any(
                value is not None
                and (not isinstance(value, str) or _SHA256.fullmatch(value) is None)
                for value in self.venue_prior_evidence_sha256
            )
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective candidate bindings are invalid"
            )
        if any(
            available != (reason is None)
            for available, reason in zip(
                self.candidate_available,
                self.candidate_unavailable_reasons,
                strict=True,
            )
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective availability lacks an exact causal reason"
            )
        if self.shared_venue_prior_evidence_sha256 is not None:
            _require_digest(
                self.shared_venue_prior_evidence_sha256,
                subject="shared venue evidence",
            )
        if self.kind is TrainingChoiceKind.TRAINEE:
            if any(value is not None for value in self.venue_prior_evidence_sha256):
                raise PartyDevelopmentCatalogError(
                    "trainee candidates cannot bind candidate-specific venue evidence"
                )
            if self.shared_venue_prior_evidence_sha256 is None:
                raise PartyDevelopmentCatalogError(
                    "trainee candidates need prospective shared-venue evidence"
                )
        elif self.shared_venue_prior_evidence_sha256 is not None:
            raise PartyDevelopmentCatalogError(
                "venue candidates cannot also bind shared-venue evidence"
            )
        elif any(
            available and evidence is None
            for available, evidence in zip(
                self.candidate_available,
                self.venue_prior_evidence_sha256,
                strict=True,
            )
        ):
            raise PartyDevelopmentCatalogError(
                "available venue candidates need prospective evidence"
            )
        if self.candidate_menu_sha256 != canonical_sha256(self._menu_document()):
            raise PartyDevelopmentCatalogError(
                "party-development prospective candidate menu digest differs"
            )
        if self.binding_sha256 != canonical_sha256(self._binding_document()):
            raise PartyDevelopmentCatalogError(
                "party-development prospective binding digest differs"
            )

    @classmethod
    def build(
        cls,
        *,
        scenario_id: str,
        root_lineage_id: str,
        initial_state_sha256: str,
        partition: ScenarioPartition,
        source_commit: str,
        source_bundle_sha256: str,
        semantic_snapshot_sha256: str,
        candidate_set: PartyDevelopmentCandidateSet,
        venue_priors: tuple[VenueOperationalPrior, ...],
        venue_prior_registry_sha256: str,
        outcome_objective_sha256: str,
        shared_venue_prior: VenueOperationalPrior | None = None,
        candidate_available: tuple[bool, ...] | None = None,
        candidate_unavailable_reasons: (
            tuple[PartyDevelopmentUnavailableReason | None, ...] | None
        ) = None,
    ) -> PartyDevelopmentProspectiveBinding:
        if not isinstance(candidate_set, PartyDevelopmentCandidateSet):
            raise TypeError("candidate_set must be a PartyDevelopmentCandidateSet")
        if (
            not isinstance(venue_priors, tuple)
            or len(venue_priors) != len(candidate_set.candidates)
            or any(not isinstance(item, VenueOperationalPrior) for item in venue_priors)
        ):
            raise PartyDevelopmentCatalogError(
                "venue priors must match the prospective candidate menu"
            )
        available = (
            candidate_available
            if candidate_available is not None
            else tuple(True for _ in candidate_set.candidates)
        )
        if (
            not isinstance(available, tuple)
            or len(available) != len(candidate_set.candidates)
            or any(not isinstance(value, bool) for value in available)
            or sum(available) < 2
        ):
            raise PartyDevelopmentCatalogError("prospective candidate availability is invalid")
        unavailable_reasons = (
            candidate_unavailable_reasons
            if candidate_unavailable_reasons is not None
            else tuple(None for _ in available)
        )
        if (
            not isinstance(unavailable_reasons, tuple)
            or len(unavailable_reasons) != len(available)
            or any(
                reason is not None
                and not isinstance(reason, PartyDevelopmentUnavailableReason)
                for reason in unavailable_reasons
            )
            or any(
                is_available != (reason is None)
                for is_available, reason in zip(
                    available,
                    unavailable_reasons,
                    strict=True,
                )
            )
        ):
            raise PartyDevelopmentCatalogError(
                "prospective candidate availability lacks an exact causal reason"
            )
        _require_priors_match_features(candidate_set, venue_priors)
        if shared_venue_prior is not None and not isinstance(
            shared_venue_prior, VenueOperationalPrior
        ):
            raise PartyDevelopmentCatalogError(
                "shared venue prior must be typed prospective evidence"
            )
        if candidate_set.kind is TrainingChoiceKind.TRAINEE:
            if shared_venue_prior is None or not shared_venue_prior.available:
                raise PartyDevelopmentCatalogError(
                    "trainee candidates need a frozen available shared venue prior"
                )
            if any(prior != shared_venue_prior for prior in venue_priors):
                raise PartyDevelopmentCatalogError(
                    "trainee candidate features must repeat the shared venue prior"
                )
        elif shared_venue_prior is not None:
            raise PartyDevelopmentCatalogError("venue candidates cannot carry a shared venue prior")
        _require_digest(
            venue_prior_registry_sha256,
            subject="venue-prior registry",
        )
        _require_digest(
            semantic_snapshot_sha256,
            subject="semantic snapshot",
        )
        _require_digest(
            outcome_objective_sha256,
            subject="outcome objective",
        )
        feature_digests = tuple(
            _candidate_feature_sha256(
                index=item.candidate_index,
                features=item.features,
                available=available[item.candidate_index],
            )
            for item in candidate_set.candidates
        )
        feature_names_sha256 = _feature_names_sha256(PARTY_DEVELOPMENT_FEATURE_NAMES)
        evidence = (
            tuple(None for _ in venue_priors)
            if candidate_set.kind is TrainingChoiceKind.TRAINEE
            else tuple(item.evidence_sha256 if item.available else None for item in venue_priors)
        )
        shared_evidence = (
            shared_venue_prior.evidence_sha256 if shared_venue_prior is not None else None
        )
        menu_document = _menu_document(
            kind=candidate_set.kind,
            goal=candidate_set.goal,
            candidate_feature_sha256=feature_digests,
            candidate_available=available,
            candidate_unavailable_reasons=unavailable_reasons,
            venue_prior_evidence_sha256=evidence,
            shared_venue_prior_evidence_sha256=shared_evidence,
        )
        menu_sha256 = canonical_sha256(menu_document)
        binding_document = _binding_document(
            scenario_id=scenario_id,
            root_lineage_id=root_lineage_id,
            initial_state_sha256=initial_state_sha256,
            partition=partition,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            semantic_snapshot_sha256=semantic_snapshot_sha256,
            venue_prior_registry_sha256=venue_prior_registry_sha256,
            outcome_objective_sha256=outcome_objective_sha256,
            feature_names_sha256=feature_names_sha256,
            candidate_menu_sha256=menu_sha256,
        )
        return cls(
            scenario_id=scenario_id,
            root_lineage_id=root_lineage_id,
            initial_state_sha256=initial_state_sha256,
            partition=partition,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            semantic_snapshot_sha256=semantic_snapshot_sha256,
            venue_prior_registry_sha256=venue_prior_registry_sha256,
            outcome_objective_sha256=outcome_objective_sha256,
            feature_names_sha256=feature_names_sha256,
            kind=candidate_set.kind,
            goal=candidate_set.goal,
            candidate_feature_sha256=feature_digests,
            candidate_available=available,
            candidate_unavailable_reasons=unavailable_reasons,
            venue_prior_evidence_sha256=evidence,
            shared_venue_prior_evidence_sha256=shared_evidence,
            candidate_menu_sha256=menu_sha256,
            binding_sha256=canonical_sha256(binding_document),
        )

    @classmethod
    def from_public_dict(cls, value: object) -> PartyDevelopmentProspectiveBinding:
        """Restore one path-free binding while recomputing its menu and binding digests."""

        expected = {
            "available_candidate_count",
            "binding_sha256",
            "candidate_count",
            "candidate_feature_sha256",
            "candidate_menu_sha256",
            "candidate_unavailable_reasons",
            "feature_names_sha256",
            "feature_schema_id",
            "goal",
            "initial_state_sha256",
            "kind",
            "outcome_objective_sha256",
            "partition",
            "private_path_fields",
            "root_lineage_id",
            "scenario_id",
            "schema",
            "semantic_snapshot_sha256",
            "shared_venue_prior_evidence_sha256",
            "source_bundle_sha256",
            "source_commit",
            "venue_prior_evidence_sha256",
            "venue_prior_registry_sha256",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value["schema"] != PARTY_DEVELOPMENT_PROSPECTIVE_BINDING_SCHEMA
            or value["feature_schema_id"] != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
            or value["private_path_fields"] != 0
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective binding document is invalid"
            )
        reasons = value["candidate_unavailable_reasons"]
        feature_digests = value["candidate_feature_sha256"]
        evidence_digests = value["venue_prior_evidence_sha256"]
        if (
            not isinstance(reasons, list)
            or not isinstance(feature_digests, list)
            or not isinstance(evidence_digests, list)
            or any(item is not None and not isinstance(item, str) for item in reasons)
            or any(not isinstance(item, str) for item in feature_digests)
            or any(item is not None and not isinstance(item, str) for item in evidence_digests)
            or type(value["candidate_count"]) is not int  # noqa: E721
            or type(value["available_candidate_count"]) is not int  # noqa: E721
            or value["candidate_count"] != len(reasons)
            or value["candidate_count"] != len(feature_digests)
            or value["candidate_count"] != len(evidence_digests)
            or value["available_candidate_count"]
            != sum(item is None for item in reasons)
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective binding rows are invalid"
            )
        try:
            unavailable_reasons = tuple(
                None if item is None else PartyDevelopmentUnavailableReason(item)
                for item in reasons
            )
            return cls(
                scenario_id=value["scenario_id"],
                root_lineage_id=value["root_lineage_id"],
                initial_state_sha256=value["initial_state_sha256"],
                partition=ScenarioPartition(value["partition"]),
                source_commit=value["source_commit"],
                source_bundle_sha256=value["source_bundle_sha256"],
                semantic_snapshot_sha256=value["semantic_snapshot_sha256"],
                venue_prior_registry_sha256=value["venue_prior_registry_sha256"],
                outcome_objective_sha256=value["outcome_objective_sha256"],
                feature_names_sha256=value["feature_names_sha256"],
                kind=TrainingChoiceKind(value["kind"]),
                goal=PartyDevelopmentGoal(value["goal"]),
                candidate_feature_sha256=tuple(feature_digests),
                candidate_available=tuple(item is None for item in unavailable_reasons),
                candidate_unavailable_reasons=unavailable_reasons,
                venue_prior_evidence_sha256=tuple(evidence_digests),
                shared_venue_prior_evidence_sha256=(
                    value["shared_venue_prior_evidence_sha256"]
                ),
                candidate_menu_sha256=value["candidate_menu_sha256"],
                binding_sha256=value["binding_sha256"],
            )
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentCatalogError(
                "party-development prospective binding document is invalid"
            ) from error

    def require_matches(self, example: ScenarioOutcomeExample) -> None:
        if not isinstance(example, ScenarioOutcomeExample):
            raise TypeError("example must be a ScenarioOutcomeExample")
        identity = (
            example.scenario_id,
            example.root_lineage_id,
            example.initial_state_sha256,
            example.partition,
            example.feature_schema_id,
        )
        expected = (
            self.scenario_id,
            self.root_lineage_id,
            self.initial_state_sha256,
            self.partition,
            self.feature_schema_id,
        )
        if identity != expected:
            raise PartyDevelopmentCatalogError(
                "party-development outcome differs from its prospective identity"
            )
        if _feature_names_sha256(example.feature_names) != self.feature_names_sha256:
            raise PartyDevelopmentCatalogError(
                "party-development outcome differs from its prospective feature contract"
            )
        if example.objective.objective_sha256 != self.outcome_objective_sha256:
            raise PartyDevelopmentCatalogError(
                "party-development outcome differs from its prospective objective"
            )
        if example.prospective_binding_sha256 != self.binding_sha256:
            raise PartyDevelopmentCatalogError(
                "party-development outcome does not re-attest its prospective binding"
            )
        observed_available = tuple(item.available for item in example.candidates)
        if observed_available != self.candidate_available:
            raise PartyDevelopmentCatalogError(
                "party-development outcome differs from its prospective availability"
            )
        observed = tuple(
            _candidate_feature_sha256(
                index=item.candidate_index,
                features=item.features,
                available=item.available,
            )
            for item in example.candidates
        )
        if observed != self.candidate_feature_sha256:
            raise PartyDevelopmentCatalogError(
                "party-development outcome differs from its prospective candidate menu"
            )

    def require_candidate_set(self, candidate_set: PartyDevelopmentCandidateSet) -> None:
        """Authenticate retained feature values against this already-frozen binding."""

        if not isinstance(candidate_set, PartyDevelopmentCandidateSet):
            raise TypeError("candidate_set must be a PartyDevelopmentCandidateSet")
        if candidate_set.kind is not self.kind or candidate_set.goal is not self.goal:
            raise PartyDevelopmentCatalogError(
                "retained party-development candidate semantics differ"
            )
        observed = tuple(
            _candidate_feature_sha256(
                index=item.candidate_index,
                features=item.features,
                available=self.candidate_available[item.candidate_index],
            )
            for item in candidate_set.candidates
        )
        if observed != self.candidate_feature_sha256:
            raise PartyDevelopmentCatalogError(
                "retained party-development candidate features differ"
            )

    def _menu_document(self) -> dict[str, object]:
        return _menu_document(
            kind=self.kind,
            goal=self.goal,
            candidate_feature_sha256=self.candidate_feature_sha256,
            candidate_available=self.candidate_available,
            candidate_unavailable_reasons=self.candidate_unavailable_reasons,
            venue_prior_evidence_sha256=self.venue_prior_evidence_sha256,
            shared_venue_prior_evidence_sha256=(self.shared_venue_prior_evidence_sha256),
        )

    def _binding_document(self) -> dict[str, object]:
        return _binding_document(
            scenario_id=self.scenario_id,
            root_lineage_id=self.root_lineage_id,
            initial_state_sha256=self.initial_state_sha256,
            partition=self.partition,
            source_commit=self.source_commit,
            source_bundle_sha256=self.source_bundle_sha256,
            semantic_snapshot_sha256=self.semantic_snapshot_sha256,
            venue_prior_registry_sha256=self.venue_prior_registry_sha256,
            outcome_objective_sha256=self.outcome_objective_sha256,
            feature_names_sha256=self.feature_names_sha256,
            candidate_menu_sha256=self.candidate_menu_sha256,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            **self._binding_document(),
            "binding_sha256": self.binding_sha256,
            "kind": self.kind.value,
            "goal": self.goal.value,
            "feature_schema_id": self.feature_schema_id,
            "candidate_count": len(self.candidate_feature_sha256),
            "available_candidate_count": sum(self.candidate_available),
            "candidate_unavailable_reasons": [
                None if reason is None else reason.value
                for reason in self.candidate_unavailable_reasons
            ],
            "candidate_feature_sha256": list(self.candidate_feature_sha256),
            "venue_prior_evidence_sha256": list(self.venue_prior_evidence_sha256),
            "shared_venue_prior_evidence_sha256": (self.shared_venue_prior_evidence_sha256),
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentProspectiveCatalog:
    """Exact ordered bindings frozen before a party outcome campaign."""

    bindings: tuple[PartyDevelopmentProspectiveBinding, ...]
    catalog_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.bindings, tuple)
            or not self.bindings
            or any(
                not isinstance(item, PartyDevelopmentProspectiveBinding) for item in self.bindings
            )
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective catalog needs typed bindings"
            )
        if tuple(item.scenario_id for item in self.bindings) != tuple(
            sorted(item.scenario_id for item in self.bindings)
        ):
            raise PartyDevelopmentCatalogError(
                "party-development prospective bindings must use scenario order"
            )
        for attribute, subject in (
            ("scenario_id", "scenario"),
            ("root_lineage_id", "root lineage"),
            ("initial_state_sha256", "initial state"),
            ("semantic_snapshot_sha256", "semantic snapshot"),
        ):
            values = tuple(getattr(item, attribute) for item in self.bindings)
            if len(values) != len(set(values)):
                raise PartyDevelopmentCatalogError(
                    f"party-development prospective catalog repeats a {subject}"
                )
        source_identities = {
            (item.source_commit, item.source_bundle_sha256) for item in self.bindings
        }
        if len(source_identities) != 1:
            raise PartyDevelopmentCatalogError(
                "party-development prospective catalog crosses source identities"
            )
        registry_identities = {item.venue_prior_registry_sha256 for item in self.bindings}
        if len(registry_identities) != 1:
            raise PartyDevelopmentCatalogError(
                "party-development prospective catalog crosses venue-prior registries"
            )
        _require_digest(self.catalog_sha256, subject="prospective catalog")
        if self.catalog_sha256 != canonical_sha256(self._catalog_document()):
            raise PartyDevelopmentCatalogError(
                "party-development prospective catalog digest differs"
            )

    @classmethod
    def freeze(
        cls, bindings: tuple[PartyDevelopmentProspectiveBinding, ...]
    ) -> PartyDevelopmentProspectiveCatalog:
        ordered = tuple(sorted(bindings, key=lambda item: item.scenario_id))
        document = {
            "schema": PARTY_DEVELOPMENT_PROSPECTIVE_CATALOG_SCHEMA,
            "bindings": [item.public_dict() for item in ordered],
        }
        return cls(bindings=ordered, catalog_sha256=canonical_sha256(document))

    def require_exact_examples(self, examples: tuple[ScenarioOutcomeExample, ...]) -> None:
        if not isinstance(examples, tuple):
            raise TypeError("examples must be an immutable tuple")
        by_scenario = {item.scenario_id: item for item in examples}
        if (
            len(examples) != len(self.bindings)
            or len(by_scenario) != len(examples)
            or set(by_scenario) != {item.scenario_id for item in self.bindings}
        ):
            raise PartyDevelopmentCatalogError(
                "party-development outcomes do not cover the frozen catalog exactly"
            )
        for binding in self.bindings:
            binding.require_matches(by_scenario[binding.scenario_id])

    def _catalog_document(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_PROSPECTIVE_CATALOG_SCHEMA,
            "bindings": [item.public_dict() for item in self.bindings],
        }

    def public_dict(self) -> dict[str, object]:
        partitions: dict[str, int] = {}
        for item in self.bindings:
            partitions[item.partition.value] = partitions.get(item.partition.value, 0) + 1
        return {
            "schema": PARTY_DEVELOPMENT_PROSPECTIVE_CATALOG_SCHEMA,
            "catalog_sha256": self.catalog_sha256,
            "binding_count": len(self.bindings),
            "partition_counts": dict(sorted(partitions.items())),
            "binding_sha256": [item.binding_sha256 for item in self.bindings],
            "venue_prior_registry_sha256": self.bindings[0].venue_prior_registry_sha256,
            "venue_prior_evidence_count": sum(
                value is not None
                for item in self.bindings
                for value in item.venue_prior_evidence_sha256
            )
            + sum(item.shared_venue_prior_evidence_sha256 is not None for item in self.bindings),
            "candidate_feature_values_public": False,
            "private_path_fields": 0,
            "outcomes_opened": 0,
            "teacher_queries": 0,
            "authority_promoted": False,
        }


def _candidate_feature_sha256(*, index: int, features: tuple[float, ...], available: bool) -> str:
    return canonical_sha256(
        {
            "candidate_index": index,
            "feature_schema_id": PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
            "feature_names": list(PARTY_DEVELOPMENT_FEATURE_NAMES),
            "features": list(features),
            "available": available,
        }
    )


def _require_priors_match_features(
    candidate_set: PartyDevelopmentCandidateSet,
    priors: tuple[VenueOperationalPrior, ...],
) -> None:
    indexes = {
        name: PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)
        for name in (
            "venue.prior_available",
            "venue.prior_reliability",
            "venue.prior_expected_yield",
            "venue.prior_matchup_safety",
            "venue.prior_travel_cost",
            "venue.prior_recovery_cost",
            "venue.prior_support",
        )
    }
    for candidate, prior in zip(candidate_set.candidates, priors, strict=True):
        expected = (
            float(prior.available),
            float(prior.reliability),
            float(prior.expected_yield),
            float(prior.matchup_safety),
            float(prior.travel_cost),
            float(prior.recovery_cost),
            min(1.0, prior.support_count / MAX_PRIOR_SUPPORT),
        )
        observed = tuple(
            candidate.features[indexes[name]]
            for name in (
                "venue.prior_available",
                "venue.prior_reliability",
                "venue.prior_expected_yield",
                "venue.prior_matchup_safety",
                "venue.prior_travel_cost",
                "venue.prior_recovery_cost",
                "venue.prior_support",
            )
        )
        if observed != expected:
            raise PartyDevelopmentCatalogError(
                "venue prior differs from its frozen candidate features"
            )


def _menu_document(
    *,
    kind: TrainingChoiceKind,
    goal: PartyDevelopmentGoal,
    candidate_feature_sha256: tuple[str, ...],
    candidate_available: tuple[bool, ...],
    candidate_unavailable_reasons: tuple[PartyDevelopmentUnavailableReason | None, ...],
    venue_prior_evidence_sha256: tuple[str | None, ...],
    shared_venue_prior_evidence_sha256: str | None,
) -> dict[str, object]:
    return {
        "schema": "pokemon.core.party-development-prospective-menu.v4",
        "kind": kind.value,
        "goal": goal.value,
        "feature_schema_id": PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
        "candidate_feature_sha256": list(candidate_feature_sha256),
        "candidate_available": list(candidate_available),
        "candidate_unavailable_reasons": [
            None if reason is None else reason.value
            for reason in candidate_unavailable_reasons
        ],
        "venue_prior_evidence_sha256": list(venue_prior_evidence_sha256),
        "shared_venue_prior_evidence_sha256": (shared_venue_prior_evidence_sha256),
    }


def _binding_document(
    *,
    scenario_id: str,
    root_lineage_id: str,
    initial_state_sha256: str,
    partition: ScenarioPartition,
    source_commit: str,
    source_bundle_sha256: str,
    semantic_snapshot_sha256: str,
    venue_prior_registry_sha256: str,
    outcome_objective_sha256: str,
    feature_names_sha256: str,
    candidate_menu_sha256: str,
) -> dict[str, object]:
    return {
        "schema": PARTY_DEVELOPMENT_PROSPECTIVE_BINDING_SCHEMA,
        "scenario_id": scenario_id,
        "root_lineage_id": root_lineage_id,
        "initial_state_sha256": initial_state_sha256,
        "partition": partition.value,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "semantic_snapshot_sha256": semantic_snapshot_sha256,
        "venue_prior_registry_sha256": venue_prior_registry_sha256,
        "outcome_objective_sha256": outcome_objective_sha256,
        "feature_names_sha256": feature_names_sha256,
        "candidate_menu_sha256": candidate_menu_sha256,
    }


def _feature_names_sha256(feature_names: tuple[str, ...]) -> str:
    return canonical_sha256(
        {
            "feature_schema_id": PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
            "feature_names": list(feature_names),
        }
    )


def _require_digest(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PartyDevelopmentCatalogError(
            f"party-development prospective {subject} digest is invalid"
        )


__all__ = [
    "PARTY_DEVELOPMENT_PROSPECTIVE_BINDING_SCHEMA",
    "PARTY_DEVELOPMENT_PROSPECTIVE_CATALOG_SCHEMA",
    "PartyDevelopmentCatalogError",
    "PartyDevelopmentProspectiveBinding",
    "PartyDevelopmentProspectiveCatalog",
    "PartyDevelopmentUnavailableReason",
]
