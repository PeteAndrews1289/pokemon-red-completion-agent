"""Strictly authenticate a private targeted Red schedule against fresh bindings."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LIVING_DEX_TARGETED_SCHEDULE_SCHEMA,
    LivingDexTargetedCapacityPolicy,
    LivingDexTargetedPartition,
    LivingDexTargetedSchedule,
    LivingDexTargetedScheduleSlot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexTargetedScheduleBinding,
)

RED_LIVING_DEX_TARGETED_PRIVATE_PLAN_SCHEMA = (
    "pokemon.red.private-living-dex-targeted-schedule-plan.v1"
)
_MAXIMUM_PLAN_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedLivingDexTargetedScheduleReaderError(ValueError):
    """The private plan or its freshly rederived Red binding differs."""


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedScheduleExpectations:
    """All externally authenticated identities surrounding the private plan."""

    source_commit: str
    source_bundle_sha256: str
    capacity_result_sha256: str
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
            raise RedLivingDexTargetedScheduleReaderError(
                "targeted plan source commit differs"
            )
        for name in (
            "source_bundle_sha256",
            "capacity_result_sha256",
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
                raise RedLivingDexTargetedScheduleReaderError(
                    f"targeted plan {name.replace('_', ' ')} differs"
                )

    def document_fields(self) -> dict[str, str]:
        return {
            name: getattr(self, name)
            for name in (
                "source_commit",
                "source_bundle_sha256",
                "capacity_result_sha256",
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
class RedLivingDexTargetedFrozenCapabilityDescriptor:
    """Non-executable identity of one frozen Red recipe binding."""

    template_ordinal: int
    slot_sha256: str
    recipe_sha256: str

    def __post_init__(self) -> None:
        if type(self.template_ordinal) is not int or self.template_ordinal < 0:  # noqa: E721
            raise RedLivingDexTargetedScheduleReaderError(
                "targeted capability template differs"
            )
        for value in (self.slot_sha256, self.recipe_sha256):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise RedLivingDexTargetedScheduleReaderError(
                    "targeted capability identity differs"
                )


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedScheduleDescriptor:
    """Hash-authenticated but deliberately non-executable schedule index.

    A caller may use this to locate and reobserve the frozen roots.  It cannot
    authorize execution; the resulting Red capabilities must still pass
    :func:`authenticate_red_living_dex_targeted_schedule_plan`.
    """

    binding_sha256: str
    schedule: LivingDexTargetedSchedule
    capabilities: tuple[RedLivingDexTargetedFrozenCapabilityDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.binding_sha256, str) or _SHA256.fullmatch(
            self.binding_sha256
        ) is None:
            raise RedLivingDexTargetedScheduleReaderError(
                "targeted descriptor binding differs"
            )
        if not isinstance(self.schedule, LivingDexTargetedSchedule):
            raise TypeError("targeted descriptor schedule differs")
        self.schedule.__post_init__()
        if (
            not isinstance(self.capabilities, tuple)
            or len(self.capabilities) != len(self.schedule.slots)
            or any(
                not isinstance(item, RedLivingDexTargetedFrozenCapabilityDescriptor)
                for item in self.capabilities
            )
        ):
            raise RedLivingDexTargetedScheduleReaderError(
                "targeted descriptor capabilities differ"
            )
        for slot, capability in zip(
            self.schedule.slots,
            self.capabilities,
            strict=True,
        ):
            capability.__post_init__()
            if capability.slot_sha256 != slot.slot_sha256:
                raise RedLivingDexTargetedScheduleReaderError(
                    "targeted descriptor slot join differs"
                )


def load_red_living_dex_targeted_schedule_descriptor(
    payload: bytes,
    *,
    expected_plan_sha256: str,
    expectations: RedLivingDexTargetedScheduleExpectations,
) -> RedLivingDexTargetedScheduleDescriptor:
    """Load a root-location index after exact byte and metadata authentication.

    The return value carries no execution authority.  Its purpose is to make
    restart-safe, action-free reobservation possible after a base root has
    already received its durable reservation.
    """

    document = _authenticate_document(
        payload,
        expected_plan_sha256=expected_plan_sha256,
        expectations=expectations,
    )
    return parse_red_living_dex_targeted_binding_descriptor(
        document["binding"],
        expected_binding_sha256=str(document["binding_sha256"]),
        policy=LivingDexTargetedCapacityPolicy.v1(),
    )


def parse_red_living_dex_targeted_binding_descriptor(
    value: object,
    *,
    expected_binding_sha256: str,
    policy: LivingDexTargetedCapacityPolicy,
) -> RedLivingDexTargetedScheduleDescriptor:
    """Parse one exact Red binding under an explicitly authenticated policy."""

    if not isinstance(policy, LivingDexTargetedCapacityPolicy):
        raise TypeError("targeted private plan policy differs")
    policy.__post_init__()
    if (
        not isinstance(expected_binding_sha256, str)
        or _SHA256.fullmatch(expected_binding_sha256) is None
    ):
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted descriptor binding differs"
        )
    try:
        binding = _mapping(value)
        if set(binding) != {"bindings", "schedule", "schema"} or binding.get(
            "schema"
        ) != "pokemon.red.private-living-dex-targeted-update-schedule-binding.v1":
            raise ValueError
        schedule_document = _mapping(binding["schedule"])
        if set(schedule_document) != {
            "maximum_train_replays_per_context",
            "policy_sha256",
            "schema",
            "slots",
        } or schedule_document.get("schema") != LIVING_DEX_TARGETED_SCHEDULE_SCHEMA:
            raise ValueError
        if schedule_document.get("policy_sha256") != policy.policy_sha256:
            raise ValueError
        raw_slots = schedule_document["slots"]
        if not isinstance(raw_slots, list):
            raise ValueError
        slots: list[LivingDexTargetedScheduleSlot] = []
        for raw in raw_slots:
            row = _mapping(raw)
            if set(row) != {
                "focus_kind",
                "lineage_sha256",
                "partition",
                "physical_root_sha256",
                "reset_ordinal",
                "schema",
            } or row.get("schema") != (
                "pokemon.core.living-dex-targeted-update-schedule-slot.v1"
            ):
                raise ValueError
            slots.append(
                LivingDexTargetedScheduleSlot(
                    partition=_partition(row["partition"]),
                    focus_kind=LivingDexOptionKind(str(row["focus_kind"])),
                    lineage_sha256=str(row["lineage_sha256"]),
                    physical_root_sha256=str(row["physical_root_sha256"]),
                    reset_ordinal=_integer(row["reset_ordinal"]),
                )
            )
        schedule = LivingDexTargetedSchedule(
            policy=policy,
            maximum_train_replays_per_context=_integer(
                schedule_document["maximum_train_replays_per_context"]
            ),
            slots=tuple(slots),
        )
        raw_capabilities = binding["bindings"]
        if not isinstance(raw_capabilities, list) or len(raw_capabilities) != len(
            slots
        ):
            raise ValueError
        capabilities: list[RedLivingDexTargetedFrozenCapabilityDescriptor] = []
        for slot, raw in zip(slots, raw_capabilities, strict=True):
            row = _mapping(raw)
            if set(row) != {"recipe", "slot_sha256", "template_ordinal"}:
                raise ValueError
            recipe = _mapping(row["recipe"])
            capabilities.append(
                RedLivingDexTargetedFrozenCapabilityDescriptor(
                    template_ordinal=_integer(row["template_ordinal"]),
                    slot_sha256=str(row["slot_sha256"]),
                    recipe_sha256=canonical_sha256(recipe),
                )
            )
            if row["slot_sha256"] != slot.slot_sha256:
                raise ValueError
        descriptor = RedLivingDexTargetedScheduleDescriptor(
            binding_sha256=expected_binding_sha256,
            schedule=schedule,
            capabilities=tuple(capabilities),
        )
        if (
            schedule.private_dict() != dict(schedule_document)
            or canonical_sha256(binding) != descriptor.binding_sha256
        ):
            raise ValueError
        return descriptor
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan binding descriptor differs"
        ) from None


def authenticate_red_living_dex_targeted_schedule_plan(
    payload: bytes,
    *,
    expected_plan_sha256: str,
    expectations: RedLivingDexTargetedScheduleExpectations,
    freshly_derived_binding: RedLivingDexTargetedScheduleBinding,
) -> RedLivingDexTargetedScheduleBinding:
    """Return the fresh binding only when every frozen private byte replays."""

    if not isinstance(freshly_derived_binding, RedLivingDexTargetedScheduleBinding):
        raise TypeError("targeted private plan needs a fresh Red binding")
    freshly_derived_binding.__post_init__()
    descriptor = load_red_living_dex_targeted_schedule_descriptor(
        payload,
        expected_plan_sha256=expected_plan_sha256,
        expectations=expectations,
    )
    if descriptor.binding_sha256 != freshly_derived_binding.binding_sha256:
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan Red binding differs"
        )
    return freshly_derived_binding


def _authenticate_document(
    payload: bytes,
    *,
    expected_plan_sha256: str,
    expectations: RedLivingDexTargetedScheduleExpectations,
) -> Mapping[str, object]:
    if not isinstance(payload, bytes):
        raise TypeError("targeted private schedule must be bytes")
    if (
        not payload
        or len(payload) > _MAXIMUM_PLAN_BYTES
        or not isinstance(expected_plan_sha256, str)
        or _SHA256.fullmatch(expected_plan_sha256) is None
        or hashlib.sha256(payload).hexdigest() != expected_plan_sha256
    ):
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan bytes differ"
        )
    if not isinstance(expectations, RedLivingDexTargetedScheduleExpectations):
        raise TypeError("targeted private plan expectations differ")
    expectations.__post_init__()
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan is not canonical JSON"
        ) from None
    if not isinstance(document, dict) or _canonical_line(document) != payload:
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan is not canonical JSON"
        )
    expected_keys = {
        "binding",
        "binding_sha256",
        "capacity_result_sha256",
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
    }
    if set(document) != expected_keys:
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan fields differ"
        )
    if document.get("schema") != RED_LIVING_DEX_TARGETED_PRIVATE_PLAN_SCHEMA:
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan schema differs"
        )
    for name, value in expectations.document_fields().items():
        if document.get(name) != value:
            raise RedLivingDexTargetedScheduleReaderError(
                f"targeted private plan {name.replace('_', ' ')} differs"
            )
    freezer_sha256 = document.get("freezer_sha256")
    if not isinstance(freezer_sha256, str) or _SHA256.fullmatch(freezer_sha256) is None:
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan freezer differs"
        )
    if (
        not isinstance(document.get("binding_sha256"), str)
        or _SHA256.fullmatch(str(document.get("binding_sha256"))) is None
        or canonical_sha256(document.get("binding"))
        != document.get("binding_sha256")
    ):
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan binding envelope differs"
        )
    return document


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


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise TypeError("expected string-keyed mapping")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:  # noqa: E721
        raise TypeError("expected integer")
    return value


def _partition(value: object) -> LivingDexTargetedPartition:
    if value not in {"train", "development"}:
        raise ValueError("expected partition")
    return cast(LivingDexTargetedPartition, value)


__all__ = [
    "RED_LIVING_DEX_TARGETED_PRIVATE_PLAN_SCHEMA",
    "RedLivingDexTargetedFrozenCapabilityDescriptor",
    "RedLivingDexTargetedScheduleDescriptor",
    "RedLivingDexTargetedScheduleExpectations",
    "RedLivingDexTargetedScheduleReaderError",
    "authenticate_red_living_dex_targeted_schedule_plan",
    "load_red_living_dex_targeted_schedule_descriptor",
    "parse_red_living_dex_targeted_binding_descriptor",
]
