"""Strictly authenticate a private targeted Red schedule against fresh bindings."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

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


def authenticate_red_living_dex_targeted_schedule_plan(
    payload: bytes,
    *,
    expected_plan_sha256: str,
    expectations: RedLivingDexTargetedScheduleExpectations,
    freshly_derived_binding: RedLivingDexTargetedScheduleBinding,
) -> RedLivingDexTargetedScheduleBinding:
    """Return the fresh binding only when every frozen private byte replays."""

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
    if not isinstance(freshly_derived_binding, RedLivingDexTargetedScheduleBinding):
        raise TypeError("targeted private plan needs a fresh Red binding")
    freshly_derived_binding.__post_init__()
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
        document.get("binding_sha256") != freshly_derived_binding.binding_sha256
        or canonical_sha256(document.get("binding"))
        != freshly_derived_binding.binding_sha256
    ):
        raise RedLivingDexTargetedScheduleReaderError(
            "targeted private plan Red binding differs"
        )
    return freshly_derived_binding


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
    "RED_LIVING_DEX_TARGETED_PRIVATE_PLAN_SCHEMA",
    "RedLivingDexTargetedScheduleExpectations",
    "RedLivingDexTargetedScheduleReaderError",
    "authenticate_red_living_dex_targeted_schedule_plan",
]
