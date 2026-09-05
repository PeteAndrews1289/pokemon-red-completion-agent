from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from test_red_living_dex_targeted_update_capacity import _repeatable_capabilities

from pokemon_red_completion.red_living_dex_causal_inventory import (
    freeze_red_living_dex_targeted_schedule,
)
from pokemon_red_completion.red_living_dex_targeted_schedule_reader import (
    RED_LIVING_DEX_TARGETED_PRIVATE_PLAN_SCHEMA,
    RedLivingDexTargetedScheduleExpectations,
    RedLivingDexTargetedScheduleReaderError,
    authenticate_red_living_dex_targeted_schedule_plan,
)


def _expectations() -> RedLivingDexTargetedScheduleExpectations:
    return RedLivingDexTargetedScheduleExpectations(
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        capacity_result_sha256="c" * 64,
        context_catalog_sha256="d" * 64,
        context_plan_sha256="e" * 64,
        model_sha256="f" * 64,
        model_record_sha256="1" * 64,
        rom_sha256="2" * 64,
        route_registry_sha256="3" * 64,
        runtime_identity_sha256="4" * 64,
    )


def _payload():  # type: ignore[no-untyped-def]
    binding = freeze_red_living_dex_targeted_schedule(
        _repeatable_capabilities(),
        maximum_train_replays_per_context=5,
    )
    document = {
        **_expectations().document_fields(),
        "binding": binding.private_dict(),
        "binding_sha256": binding.binding_sha256,
        "freezer_sha256": "5" * 64,
        "schema": RED_LIVING_DEX_TARGETED_PRIVATE_PLAN_SCHEMA,
    }
    payload = (
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )
    return binding, document, payload


def test_private_schedule_authenticates_every_envelope_and_fresh_binding() -> None:
    binding, _document, payload = _payload()

    restored = authenticate_red_living_dex_targeted_schedule_plan(
        payload,
        expected_plan_sha256=hashlib.sha256(payload).hexdigest(),
        expectations=_expectations(),
        freshly_derived_binding=binding,
    )

    assert restored is binding


def test_private_schedule_rejects_metadata_or_binding_reinterpretation() -> None:
    binding, document, _payload_bytes = _payload()
    for key, value in (
        ("source_bundle_sha256", "9" * 64),
        ("model_sha256", "9" * 64),
        ("runtime_identity_sha256", "9" * 64),
        ("binding_sha256", "9" * 64),
    ):
        mutated = {**document, key: value}
        payload = (
            json.dumps(mutated, separators=(",", ":"), sort_keys=True).encode(
                "ascii"
            )
            + b"\n"
        )
        with pytest.raises(RedLivingDexTargetedScheduleReaderError):
            authenticate_red_living_dex_targeted_schedule_plan(
                payload,
                expected_plan_sha256=hashlib.sha256(payload).hexdigest(),
                expectations=_expectations(),
                freshly_derived_binding=binding,
            )


def test_private_schedule_rejects_noncanonical_or_duplicate_json() -> None:
    binding, document, payload = _payload()
    noncanonical = json.dumps(document, indent=2).encode("ascii")
    duplicate = payload[:-2] + b',"schema":"duplicate"}\n'

    for malformed in (noncanonical, duplicate):
        with pytest.raises(
            RedLivingDexTargetedScheduleReaderError,
            match="canonical JSON",
        ):
            authenticate_red_living_dex_targeted_schedule_plan(
                malformed,
                expected_plan_sha256=hashlib.sha256(malformed).hexdigest(),
                expectations=_expectations(),
                freshly_derived_binding=binding,
            )


def test_expectations_reject_wrong_width_source_or_digest() -> None:
    with pytest.raises(RedLivingDexTargetedScheduleReaderError):
        replace(_expectations(), source_commit="a" * 39)
    with pytest.raises(RedLivingDexTargetedScheduleReaderError):
        replace(_expectations(), rom_sha256="2" * 63)
