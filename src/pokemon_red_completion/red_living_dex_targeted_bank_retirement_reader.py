"""Strictly authenticate a private Red targeted-bank retirement plan.

The descriptor can locate the eight retired-train and four paired-development
recipes, but it does not grant execution authority.  A consumer must freshly
reobserve and rebind every addressed Red recipe before a train slot can run.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.living_dex_targeted_bank_retirement import (
    LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA,
)
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityPolicy,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_targeted_bank_retirement import (
    RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA,
)
from pokemon_red_completion.red_living_dex_targeted_schedule_reader import (
    RedLivingDexTargetedScheduleDescriptor,
    parse_red_living_dex_targeted_binding_descriptor,
)

RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_PRIVATE_PLAN_SCHEMA = (
    "pokemon.red.private-living-dex-targeted-bank-retirement-plan.v1"
)
_MAXIMUM_PLAN_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedLivingDexTargetedBankRetirementReaderError(ValueError):
    """The frozen bank retirement or its fresh Red replay differs."""


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedBankRetirementExpectations:
    """Externally authenticated identities surrounding the retirement plan."""

    source_commit: str
    source_bundle_sha256: str
    context_catalog_sha256: str
    context_plan_sha256: str
    model_sha256: str
    model_record_sha256: str
    rom_sha256: str
    route_registry_sha256: str
    runtime_identity_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise RedLivingDexTargetedBankRetirementReaderError(
                "retired targeted plan source commit differs"
            )
        for name in (
            "source_bundle_sha256",
            "context_catalog_sha256",
            "context_plan_sha256",
            "model_sha256",
            "model_record_sha256",
            "rom_sha256",
            "route_registry_sha256",
            "runtime_identity_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise RedLivingDexTargetedBankRetirementReaderError(
                    f"retired targeted plan {name.replace('_', ' ')} differs"
                )

    def document_fields(self) -> dict[str, str]:
        return {
            name: getattr(self, name)
            for name in (
                "source_commit",
                "source_bundle_sha256",
                "context_catalog_sha256",
                "context_plan_sha256",
                "model_sha256",
                "model_record_sha256",
                "rom_sha256",
                "route_registry_sha256",
                "runtime_identity_sha256",
            )
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedBankRetirementDescriptor:
    """Non-executable identity of the retired, paired, and reserve root split."""

    binding_sha256: str
    schedule_descriptor: RedLivingDexTargetedScheduleDescriptor
    retired_train_lineages: tuple[str, ...]
    paired_development_lineages: tuple[str, ...]
    reserve_development_lineages: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.binding_sha256, str) or _SHA256.fullmatch(
            self.binding_sha256
        ) is None:
            raise RedLivingDexTargetedBankRetirementReaderError(
                "retired targeted binding identity differs"
            )
        if not isinstance(
            self.schedule_descriptor,
            RedLivingDexTargetedScheduleDescriptor,
        ):
            raise TypeError("retired targeted schedule descriptor differs")
        self.schedule_descriptor.__post_init__()
        groups = (
            self.retired_train_lineages,
            self.paired_development_lineages,
            self.reserve_development_lineages,
        )
        if any(
            not isinstance(group, tuple)
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None
                for value in group
            )
            or tuple(sorted(group)) != group
            or len(set(group)) != len(group)
            for group in groups
        ):
            raise RedLivingDexTargetedBankRetirementReaderError(
                "retired targeted lineage groups differ"
            )
        lineage_sets = tuple(set(group) for group in groups)
        if tuple(map(len, groups)) != (4, 4, 2) or any(
            left & right
            for index, left in enumerate(lineage_sets)
            for right in lineage_sets[index + 1 :]
        ):
            raise RedLivingDexTargetedBankRetirementReaderError(
                "retired targeted lineage split differs"
            )
        schedule = self.schedule_descriptor.schedule
        train = {
            slot.lineage_sha256
            for slot in schedule.slots
            if slot.partition == "train"
        }
        development = {
            slot.lineage_sha256
            for slot in schedule.slots
            if slot.partition == "development"
        }
        if (
            train != set(self.retired_train_lineages)
            or development != set(self.paired_development_lineages)
            or len(tuple(slot for slot in schedule.slots if slot.partition == "train"))
            != 8
            or len(
                tuple(
                    slot
                    for slot in schedule.slots
                    if slot.partition == "development"
                )
            )
            != 4
        ):
            raise RedLivingDexTargetedBankRetirementReaderError(
                "retired targeted schedule crossed its lineage split"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "controller_actions": 0,
            "emulator_frames": 0,
            "evaluation_status_forfeited_roots": len(
                self.retired_train_lineages
            ),
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "paired_development_roots": len(
                self.paired_development_lineages
            ),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "reserve_development_roots": len(
                self.reserve_development_lineages
            ),
            "schema": RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_PRIVATE_PLAN_SCHEMA,
            "teacher_queries": 0,
            "train_slots": 8,
        }


def load_red_living_dex_targeted_bank_retirement_descriptor(
    payload: bytes,
    *,
    expected_plan_sha256: str,
    expectations: RedLivingDexTargetedBankRetirementExpectations,
) -> RedLivingDexTargetedBankRetirementDescriptor:
    """Authenticate exact bytes and return a deliberately non-executable index."""

    document = _authenticate_document(
        payload,
        expected_plan_sha256=expected_plan_sha256,
        expectations=expectations,
    )
    try:
        binding = _mapping(document["binding"])
        if set(binding) != {"red_binding", "retirement", "schema"} or binding.get(
            "schema"
        ) != RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA:
            raise ValueError
        red_binding = _mapping(binding["red_binding"])
        retirement = _mapping(binding["retirement"])
        if set(retirement) != {
            "paired_development_lineages",
            "reserve_development_lineages",
            "retired_train_lineages",
            "schedule",
            "schema",
        } or retirement.get("schema") != LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA:
            raise ValueError
        red_schedule = _mapping(red_binding["schedule"])
        retirement_schedule = _mapping(retirement["schedule"])
        if red_schedule != retirement_schedule:
            raise ValueError
        red_binding_sha256 = canonical_sha256(red_binding)
        schedule_descriptor = parse_red_living_dex_targeted_binding_descriptor(
            red_binding,
            expected_binding_sha256=red_binding_sha256,
            policy=LivingDexTargetedCapacityPolicy.retired_bank_v2(),
        )
        descriptor = RedLivingDexTargetedBankRetirementDescriptor(
            binding_sha256=str(document["binding_sha256"]),
            schedule_descriptor=schedule_descriptor,
            retired_train_lineages=_lineages(retirement["retired_train_lineages"]),
            paired_development_lineages=_lineages(
                retirement["paired_development_lineages"]
            ),
            reserve_development_lineages=_lineages(
                retirement["reserve_development_lineages"]
            ),
        )
        if canonical_sha256(binding) != descriptor.binding_sha256:
            raise ValueError
        return descriptor
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan descriptor differs"
        ) from None


def authenticate_red_living_dex_targeted_bank_retirement_plan(
    payload: bytes,
    *,
    expected_plan_sha256: str,
    expectations: RedLivingDexTargetedBankRetirementExpectations,
    freshly_derived_binding: RedLivingDexTargetedScheduleBinding,
) -> RedLivingDexTargetedScheduleBinding:
    """Return a fresh train binding only when it exactly replays the frozen one."""

    if not isinstance(freshly_derived_binding, RedLivingDexTargetedScheduleBinding):
        raise TypeError("retired targeted plan needs a fresh Red binding")
    freshly_derived_binding.__post_init__()
    descriptor = load_red_living_dex_targeted_bank_retirement_descriptor(
        payload,
        expected_plan_sha256=expected_plan_sha256,
        expectations=expectations,
    )
    if (
        descriptor.schedule_descriptor.binding_sha256
        != freshly_derived_binding.binding_sha256
    ):
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan Red binding differs"
        )
    return freshly_derived_binding


def _authenticate_document(
    payload: bytes,
    *,
    expected_plan_sha256: str,
    expectations: RedLivingDexTargetedBankRetirementExpectations,
) -> Mapping[str, object]:
    if not isinstance(payload, bytes):
        raise TypeError("retired targeted private plan must be bytes")
    if (
        not payload
        or len(payload) > _MAXIMUM_PLAN_BYTES
        or not isinstance(expected_plan_sha256, str)
        or _SHA256.fullmatch(expected_plan_sha256) is None
        or hashlib.sha256(payload).hexdigest() != expected_plan_sha256
    ):
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan bytes differ"
        )
    if not isinstance(expectations, RedLivingDexTargetedBankRetirementExpectations):
        raise TypeError("retired targeted private plan expectations differ")
    expectations.__post_init__()
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan is not canonical JSON"
        ) from None
    if not isinstance(document, dict) or _canonical_line(document) != payload:
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan is not canonical JSON"
        )
    if set(document) != {
        "binding",
        "binding_sha256",
        "context_catalog_sha256",
        "context_plan_sha256",
        "freezer_sha256",
        "model_record_sha256",
        "model_sha256",
        "rom_sha256",
        "route_registry_sha256",
        "runtime_identity_sha256",
        "schema",
        "source_bundle_sha256",
        "source_commit",
    }:
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan fields differ"
        )
    if document.get("schema") != (
        RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_PRIVATE_PLAN_SCHEMA
    ):
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan schema differs"
        )
    for name, value in expectations.document_fields().items():
        if document.get(name) != value:
            raise RedLivingDexTargetedBankRetirementReaderError(
                f"retired targeted private plan {name.replace('_', ' ')} differs"
            )
    for name in ("freezer_sha256", "binding_sha256"):
        envelope_value = document.get(name)
        if (
            not isinstance(envelope_value, str)
            or _SHA256.fullmatch(envelope_value) is None
        ):
            raise RedLivingDexTargetedBankRetirementReaderError(
                f"retired targeted private plan {name.replace('_', ' ')} differs"
            )
    if canonical_sha256(document.get("binding")) != document.get("binding_sha256"):
        raise RedLivingDexTargetedBankRetirementReaderError(
            "retired targeted private plan binding envelope differs"
        )
    return document


def _lineages(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError("lineage roster differs")
    return tuple(str(item) for item in value)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise TypeError("expected string-keyed mapping")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_line(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


__all__ = [
    "RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_PRIVATE_PLAN_SCHEMA",
    "RedLivingDexTargetedBankRetirementDescriptor",
    "RedLivingDexTargetedBankRetirementExpectations",
    "RedLivingDexTargetedBankRetirementReaderError",
    "authenticate_red_living_dex_targeted_bank_retirement_plan",
    "load_red_living_dex_targeted_bank_retirement_descriptor",
]
