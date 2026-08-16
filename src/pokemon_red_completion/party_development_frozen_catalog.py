"""Durable private 8+6 inputs frozen before any party outcome is opened.

The prospective binding intentionally publishes only feature digests. Training,
however, later needs the exact identity-free feature rows that produced those
digests. This module retains those rows beside reconstruction-only capture and
profile identities, without retaining a filesystem path or a selected answer.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentCatalogError,
    PartyDevelopmentProspectiveBinding,
    PartyDevelopmentProspectiveCatalog,
)
from pokemon_red_completion.party_development_rank import (
    PartyDevelopmentCandidateSet,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PARTY_DEVELOPMENT_FROZEN_QUESTION_SCHEMA = (
    "pokemon.core.party-development-frozen-question.v1"
)
PARTY_DEVELOPMENT_FROZEN_CATALOG_SCHEMA = (
    "pokemon.core.party-development-frozen-catalog.v1"
)

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class PartyDevelopmentFrozenCatalogError(ValueError):
    """Raised when retained catalog inputs cannot reproduce their binding."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentFrozenQuestion:
    """One feature menu plus only the identities needed to reconstruct it."""

    capture_id: str
    capture_envelope_sha256: str
    profile_id: str
    profile_file_sha256: str
    binding: PartyDevelopmentProspectiveBinding
    candidate_set: PartyDevelopmentCandidateSet
    materialization_artifact_id: str | None = None
    materialization_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        for value, subject in (
            (self.capture_id, "capture"),
            (self.profile_id, "profile"),
        ):
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise PartyDevelopmentFrozenCatalogError(
                    f"frozen party-development {subject} identity is invalid"
                )
        for value, subject in (
            (self.capture_envelope_sha256, "capture envelope"),
            (self.profile_file_sha256, "profile file"),
        ):
            _require_digest(value, subject=subject)
        if not isinstance(self.binding, PartyDevelopmentProspectiveBinding):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development binding is invalid"
            )
        if not isinstance(self.candidate_set, PartyDevelopmentCandidateSet):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development candidate set is invalid"
            )
        try:
            self.binding.require_candidate_set(self.candidate_set)
        except (PartyDevelopmentCatalogError, TypeError) as error:
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development features differ from their binding"
            ) from error
        if self.binding.initial_state_sha256 == self.capture_envelope_sha256:
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development state and envelope identities collide"
            )
        materialized = self.materialization_artifact_id is not None
        if materialized:
            if (
                not isinstance(self.materialization_artifact_id, str)
                or _SAFE_ID.fullmatch(self.materialization_artifact_id) is None
                or self.materialization_manifest_sha256 is None
                or self.capture_id == self.profile_id
            ):
                raise PartyDevelopmentFrozenCatalogError(
                    "frozen prepared question lacks exact materialization lineage"
                )
            _require_digest(
                self.materialization_manifest_sha256,
                subject="materialization manifest",
            )
        elif (
            self.materialization_manifest_sha256 is not None
            or self.capture_id != self.profile_id
        ):
            raise PartyDevelopmentFrozenCatalogError(
                "direct frozen question carries partial materialization lineage"
            )

    @property
    def scenario_id(self) -> str:
        return self.binding.scenario_id

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": PARTY_DEVELOPMENT_FROZEN_QUESTION_SCHEMA,
            "capture_id": self.capture_id,
            "capture_envelope_sha256": self.capture_envelope_sha256,
            "profile_id": self.profile_id,
            "profile_file_sha256": self.profile_file_sha256,
            "binding": self.binding.public_dict(),
            "candidate_set": self.candidate_set.public_dict(),
            "materialization_artifact_id": self.materialization_artifact_id,
            "materialization_manifest_sha256": (
                self.materialization_manifest_sha256
            ),
            "answer_selected": False,
            "outcome_opened": False,
            "controller_actions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "private_path_fields": 0,
        }

    @classmethod
    def from_private_dict(cls, value: object) -> PartyDevelopmentFrozenQuestion:
        expected = {
            "answer_selected",
            "binding",
            "candidate_set",
            "capture_envelope_sha256",
            "capture_id",
            "controller_actions",
            "materialization_artifact_id",
            "materialization_manifest_sha256",
            "model_predictions",
            "outcome_opened",
            "private_path_fields",
            "profile_file_sha256",
            "profile_id",
            "schema",
            "teacher_queries",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value["schema"] != PARTY_DEVELOPMENT_FROZEN_QUESTION_SCHEMA
            or value["answer_selected"] is not False
            or value["outcome_opened"] is not False
            or value["controller_actions"] != 0
            or value["teacher_queries"] != 0
            or value["model_predictions"] != 0
            or value["private_path_fields"] != 0
        ):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development question document is invalid"
            )
        try:
            return cls(
                capture_id=value["capture_id"],
                capture_envelope_sha256=value["capture_envelope_sha256"],
                profile_id=value["profile_id"],
                profile_file_sha256=value["profile_file_sha256"],
                binding=PartyDevelopmentProspectiveBinding.from_public_dict(
                    value["binding"]
                ),
                candidate_set=PartyDevelopmentCandidateSet.from_public_dict(
                    value["candidate_set"]
                ),
                materialization_artifact_id=value["materialization_artifact_id"],
                materialization_manifest_sha256=(
                    value["materialization_manifest_sha256"]
                ),
            )
        except PartyDevelopmentFrozenCatalogError:
            raise
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development question document is invalid"
            ) from error


@dataclass(frozen=True, slots=True)
class PartyDevelopmentFrozenCatalog:
    """Exact first-fit inputs, still carrying no answer, outcome, or authority."""

    questions: tuple[PartyDevelopmentFrozenQuestion, ...]
    reservation_plan_file_sha256: str
    reservation_plan_sha256: str
    inventory_file_sha256: str
    inventory_sha256: str
    pp_plan_file_sha256: str
    pp_plan_sha256: str
    context_catalog_file_sha256: str
    context_catalog_sha256: str
    venue_prior_registry_file_sha256: str
    venue_prior_registry_sha256: str
    rom_sha256: str
    source_commit: str
    source_bundle_sha256: str
    prospective_catalog_sha256: str
    catalog_sha256: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.reservation_plan_file_sha256, "reservation-plan file"),
            (self.reservation_plan_sha256, "reservation plan"),
            (self.inventory_file_sha256, "inventory file"),
            (self.inventory_sha256, "inventory"),
            (self.pp_plan_file_sha256, "PP-plan file"),
            (self.pp_plan_sha256, "PP plan"),
            (self.context_catalog_file_sha256, "context-catalog file"),
            (self.context_catalog_sha256, "context catalog"),
            (self.venue_prior_registry_file_sha256, "venue-registry file"),
            (self.venue_prior_registry_sha256, "venue registry"),
            (self.rom_sha256, "ROM"),
            (self.source_bundle_sha256, "source bundle"),
            (self.prospective_catalog_sha256, "prospective catalog"),
            (self.catalog_sha256, "frozen catalog"),
        ):
            _require_digest(value, subject=subject)
        if (
            not isinstance(self.source_commit, str)
            or _GIT_OID.fullmatch(self.source_commit) is None
        ):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development source commit is invalid"
            )
        if (
            not isinstance(self.questions, tuple)
            or len(self.questions) != 14
            or any(
                not isinstance(item, PartyDevelopmentFrozenQuestion)
                for item in self.questions
            )
            or self.questions
            != tuple(sorted(self.questions, key=lambda item: item.scenario_id))
        ):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development catalog needs exactly fourteen ordered questions"
            )
        for attribute, subject in (
            ("scenario_id", "scenario"),
            ("capture_id", "capture"),
            ("capture_envelope_sha256", "capture envelope"),
            ("profile_id", "profile"),
        ):
            values = tuple(getattr(item, attribute) for item in self.questions)
            if len(values) != len(set(values)):
                raise PartyDevelopmentFrozenCatalogError(
                    f"frozen party-development catalog repeats a {subject}"
                )
        prospective = PartyDevelopmentProspectiveCatalog.freeze(
            tuple(item.binding for item in self.questions)
        )
        partitions = Counter(item.binding.partition for item in self.questions)
        if partitions != {
            ScenarioPartition.TRAIN: 8,
            ScenarioPartition.DEVELOPMENT: 6,
        }:
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development catalog is not exact 8+6"
            )
        for partition in (
            ScenarioPartition.TRAIN,
            ScenarioPartition.DEVELOPMENT,
        ):
            kinds = {
                item.binding.kind
                for item in self.questions
                if item.binding.partition is partition
            }
            if kinds != set(TrainingChoiceKind):
                raise PartyDevelopmentFrozenCatalogError(
                    "frozen party-development partition lacks a choice kind"
                )
        if len(
            [
                item
                for item in self.questions
                if item.materialization_artifact_id is not None
            ]
        ) != 2:
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development catalog needs two prepared contexts"
            )
        if (
            any(item.binding.source_commit != self.source_commit for item in self.questions)
            or any(
                item.binding.source_bundle_sha256 != self.source_bundle_sha256
                for item in self.questions
            )
            or any(
                item.binding.venue_prior_registry_sha256
                != self.venue_prior_registry_sha256
                for item in self.questions
            )
            or prospective.catalog_sha256 != self.prospective_catalog_sha256
        ):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development catalog crosses authenticated inputs"
            )
        if self.catalog_sha256 != canonical_sha256(self._catalog_document()):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development catalog digest differs"
            )

    @classmethod
    def freeze(
        cls,
        questions: tuple[PartyDevelopmentFrozenQuestion, ...],
        *,
        reservation_plan_file_sha256: str,
        reservation_plan_sha256: str,
        inventory_file_sha256: str,
        inventory_sha256: str,
        pp_plan_file_sha256: str,
        pp_plan_sha256: str,
        context_catalog_file_sha256: str,
        context_catalog_sha256: str,
        venue_prior_registry_file_sha256: str,
        venue_prior_registry_sha256: str,
        rom_sha256: str,
        source_commit: str,
        source_bundle_sha256: str,
    ) -> PartyDevelopmentFrozenCatalog:
        ordered = tuple(sorted(questions, key=lambda item: item.scenario_id))
        prospective_catalog_sha256 = PartyDevelopmentProspectiveCatalog.freeze(
            tuple(item.binding for item in ordered)
        ).catalog_sha256
        document = _catalog_document(
            questions=ordered,
            reservation_plan_file_sha256=reservation_plan_file_sha256,
            reservation_plan_sha256=reservation_plan_sha256,
            inventory_file_sha256=inventory_file_sha256,
            inventory_sha256=inventory_sha256,
            pp_plan_file_sha256=pp_plan_file_sha256,
            pp_plan_sha256=pp_plan_sha256,
            context_catalog_file_sha256=context_catalog_file_sha256,
            context_catalog_sha256=context_catalog_sha256,
            venue_prior_registry_file_sha256=venue_prior_registry_file_sha256,
            venue_prior_registry_sha256=venue_prior_registry_sha256,
            rom_sha256=rom_sha256,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            prospective_catalog_sha256=prospective_catalog_sha256,
        )
        return cls(
            questions=ordered,
            reservation_plan_file_sha256=reservation_plan_file_sha256,
            reservation_plan_sha256=reservation_plan_sha256,
            inventory_file_sha256=inventory_file_sha256,
            inventory_sha256=inventory_sha256,
            pp_plan_file_sha256=pp_plan_file_sha256,
            pp_plan_sha256=pp_plan_sha256,
            context_catalog_file_sha256=context_catalog_file_sha256,
            context_catalog_sha256=context_catalog_sha256,
            venue_prior_registry_file_sha256=venue_prior_registry_file_sha256,
            venue_prior_registry_sha256=venue_prior_registry_sha256,
            rom_sha256=rom_sha256,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            prospective_catalog_sha256=prospective_catalog_sha256,
            catalog_sha256=canonical_sha256(document),
        )

    def _catalog_document(self) -> dict[str, object]:
        return _catalog_document(
            questions=self.questions,
            reservation_plan_file_sha256=self.reservation_plan_file_sha256,
            reservation_plan_sha256=self.reservation_plan_sha256,
            inventory_file_sha256=self.inventory_file_sha256,
            inventory_sha256=self.inventory_sha256,
            pp_plan_file_sha256=self.pp_plan_file_sha256,
            pp_plan_sha256=self.pp_plan_sha256,
            context_catalog_file_sha256=self.context_catalog_file_sha256,
            context_catalog_sha256=self.context_catalog_sha256,
            venue_prior_registry_file_sha256=self.venue_prior_registry_file_sha256,
            venue_prior_registry_sha256=self.venue_prior_registry_sha256,
            rom_sha256=self.rom_sha256,
            source_commit=self.source_commit,
            source_bundle_sha256=self.source_bundle_sha256,
            prospective_catalog_sha256=self.prospective_catalog_sha256,
        )

    def private_dict(self) -> dict[str, object]:
        return {**self._catalog_document(), "catalog_sha256": self.catalog_sha256}

    @classmethod
    def from_private_dict(cls, value: object) -> PartyDevelopmentFrozenCatalog:
        expected = {
            "answer_selected",
            "authority_promoted",
            "catalog_sha256",
            "context_catalog_file_sha256",
            "context_catalog_sha256",
            "controller_actions",
            "crystal_cases_opened",
            "inventory_file_sha256",
            "inventory_sha256",
            "model_predictions",
            "model_updates",
            "outcomes_opened",
            "pp_plan_file_sha256",
            "pp_plan_sha256",
            "private_path_fields",
            "prospective_catalog_sha256",
            "questions",
            "reservation_plan_file_sha256",
            "reservation_plan_sha256",
            "rom_sha256",
            "schema",
            "sealed_red_cases_opened",
            "source_bundle_sha256",
            "source_commit",
            "teacher_queries",
            "venue_prior_registry_file_sha256",
            "venue_prior_registry_sha256",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != expected
            or value["schema"] != PARTY_DEVELOPMENT_FROZEN_CATALOG_SCHEMA
            or value["answer_selected"] is not False
            or value["authority_promoted"] is not False
            or value["controller_actions"] != 0
            or value["crystal_cases_opened"] != 0
            or value["model_predictions"] != 0
            or value["model_updates"] != 0
            or value["outcomes_opened"] != 0
            or value["private_path_fields"] != 0
            or value["sealed_red_cases_opened"] != 0
            or value["teacher_queries"] != 0
            or not isinstance(value["questions"], list)
        ):
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development catalog document is invalid"
            )
        try:
            return cls(
                questions=tuple(
                    PartyDevelopmentFrozenQuestion.from_private_dict(item)
                    for item in value["questions"]
                ),
                reservation_plan_file_sha256=value[
                    "reservation_plan_file_sha256"
                ],
                reservation_plan_sha256=value["reservation_plan_sha256"],
                inventory_file_sha256=value["inventory_file_sha256"],
                inventory_sha256=value["inventory_sha256"],
                pp_plan_file_sha256=value["pp_plan_file_sha256"],
                pp_plan_sha256=value["pp_plan_sha256"],
                context_catalog_file_sha256=value["context_catalog_file_sha256"],
                context_catalog_sha256=value["context_catalog_sha256"],
                venue_prior_registry_file_sha256=value[
                    "venue_prior_registry_file_sha256"
                ],
                venue_prior_registry_sha256=value["venue_prior_registry_sha256"],
                rom_sha256=value["rom_sha256"],
                source_commit=value["source_commit"],
                source_bundle_sha256=value["source_bundle_sha256"],
                prospective_catalog_sha256=value["prospective_catalog_sha256"],
                catalog_sha256=value["catalog_sha256"],
            )
        except PartyDevelopmentFrozenCatalogError:
            raise
        except (TypeError, ValueError) as error:
            raise PartyDevelopmentFrozenCatalogError(
                "frozen party-development catalog document is invalid"
            ) from error

    def public_summary(self) -> dict[str, object]:
        partitions = Counter(item.binding.partition.value for item in self.questions)
        kinds = Counter(
            f"{item.binding.partition.value}:{item.binding.kind.value}"
            for item in self.questions
        )
        goals = Counter(
            f"{item.binding.partition.value}:{item.binding.goal.value}"
            for item in self.questions
        )
        widths = Counter(
            f"{item.binding.partition.value}:{len(item.candidate_set.candidates)}"
            for item in self.questions
        )
        available_widths = Counter(
            f"{item.binding.partition.value}:{sum(item.binding.candidate_available)}"
            for item in self.questions
        )
        return {
            "schema": "pokemon.core.party-development-frozen-catalog-summary.v1",
            "status": "exact_inputs_frozen_outcomes_closed",
            "catalog_sha256": self.catalog_sha256,
            "reservation_plan_file_sha256": self.reservation_plan_file_sha256,
            "reservation_plan_sha256": self.reservation_plan_sha256,
            "inventory_file_sha256": self.inventory_file_sha256,
            "inventory_sha256": self.inventory_sha256,
            "pp_plan_file_sha256": self.pp_plan_file_sha256,
            "pp_plan_sha256": self.pp_plan_sha256,
            "context_catalog_file_sha256": self.context_catalog_file_sha256,
            "context_catalog_sha256": self.context_catalog_sha256,
            "venue_prior_registry_file_sha256": (
                self.venue_prior_registry_file_sha256
            ),
            "venue_prior_registry_sha256": self.venue_prior_registry_sha256,
            "rom_sha256": self.rom_sha256,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "prospective_catalog_sha256": self.prospective_catalog_sha256,
            "question_count": len(self.questions),
            "partition_counts": dict(sorted(partitions.items())),
            "choice_kind_partition_counts": dict(sorted(kinds.items())),
            "goal_partition_counts": dict(sorted(goals.items())),
            "candidate_width_partition_counts": dict(sorted(widths.items())),
            "available_width_partition_counts": dict(
                sorted(available_widths.items())
            ),
            "prepared_context_count": sum(
                item.materialization_artifact_id is not None
                for item in self.questions
            ),
            "materialization_manifest_sha256": sorted(
                item.materialization_manifest_sha256
                for item in self.questions
                if item.materialization_manifest_sha256 is not None
            ),
            "binding_sha256": [item.binding.binding_sha256 for item in self.questions],
            "candidate_feature_values_public": False,
            "capture_identity_public": False,
            "profile_identity_public": False,
            "answers_selected": 0,
            "outcomes_opened": 0,
            "controller_actions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }


def _catalog_document(
    *,
    questions: tuple[PartyDevelopmentFrozenQuestion, ...],
    reservation_plan_file_sha256: str,
    reservation_plan_sha256: str,
    inventory_file_sha256: str,
    inventory_sha256: str,
    pp_plan_file_sha256: str,
    pp_plan_sha256: str,
    context_catalog_file_sha256: str,
    context_catalog_sha256: str,
    venue_prior_registry_file_sha256: str,
    venue_prior_registry_sha256: str,
    rom_sha256: str,
    source_commit: str,
    source_bundle_sha256: str,
    prospective_catalog_sha256: str,
) -> dict[str, object]:
    return {
        "schema": PARTY_DEVELOPMENT_FROZEN_CATALOG_SCHEMA,
        "questions": [item.private_dict() for item in questions],
        "reservation_plan_file_sha256": reservation_plan_file_sha256,
        "reservation_plan_sha256": reservation_plan_sha256,
        "inventory_file_sha256": inventory_file_sha256,
        "inventory_sha256": inventory_sha256,
        "pp_plan_file_sha256": pp_plan_file_sha256,
        "pp_plan_sha256": pp_plan_sha256,
        "context_catalog_file_sha256": context_catalog_file_sha256,
        "context_catalog_sha256": context_catalog_sha256,
        "venue_prior_registry_file_sha256": venue_prior_registry_file_sha256,
        "venue_prior_registry_sha256": venue_prior_registry_sha256,
        "rom_sha256": rom_sha256,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "prospective_catalog_sha256": prospective_catalog_sha256,
        "answer_selected": False,
        "outcomes_opened": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }


def _require_digest(value: object, *, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PartyDevelopmentFrozenCatalogError(
            f"frozen party-development {subject} digest is invalid"
        )


__all__ = [
    "PARTY_DEVELOPMENT_FROZEN_CATALOG_SCHEMA",
    "PARTY_DEVELOPMENT_FROZEN_QUESTION_SCHEMA",
    "PartyDevelopmentFrozenCatalog",
    "PartyDevelopmentFrozenCatalogError",
    "PartyDevelopmentFrozenQuestion",
]
