from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from test_red_living_dex_targeted_bank_retirement import _capabilities

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_targeted_bank_retirement import (
    plan_red_living_dex_targeted_bank_retirement,
)
from pokemon_red_completion.red_living_dex_targeted_bank_retirement_reader import (
    RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_PRIVATE_PLAN_SCHEMA,
    RedLivingDexTargetedBankRetirementExpectations,
    RedLivingDexTargetedBankRetirementReaderError,
    authenticate_red_living_dex_targeted_bank_retirement_plan,
    load_red_living_dex_targeted_bank_retirement_descriptor,
)


def _expectations() -> RedLivingDexTargetedBankRetirementExpectations:
    return RedLivingDexTargetedBankRetirementExpectations(
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        context_catalog_sha256="c" * 64,
        context_plan_sha256="d" * 64,
        model_sha256="e" * 64,
        model_record_sha256="f" * 64,
        rom_sha256="1" * 64,
        route_registry_sha256="2" * 64,
        runtime_identity_sha256="3" * 64,
    )


def _payload():  # type: ignore[no-untyped-def]
    frozen = plan_red_living_dex_targeted_bank_retirement(_capabilities())
    document = {
        **_expectations().document_fields(),
        "binding": frozen.private_dict(),
        "binding_sha256": frozen.binding_sha256,
        "freezer_sha256": "4" * 64,
        "schema": RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_PRIVATE_PLAN_SCHEMA,
    }
    payload = (
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )
    return frozen, document, payload


def test_retirement_descriptor_authenticates_split_without_execution_authority() -> None:
    frozen, _document, payload = _payload()

    descriptor = load_red_living_dex_targeted_bank_retirement_descriptor(
        payload,
        expected_plan_sha256=hashlib.sha256(payload).hexdigest(),
        expectations=_expectations(),
    )

    assert descriptor.binding_sha256 == frozen.binding_sha256
    assert descriptor.schedule_descriptor.schedule == frozen.binding.schedule
    assert len(descriptor.retired_train_lineages) == 4
    assert len(descriptor.paired_development_lineages) == 4
    assert len(descriptor.reserve_development_lineages) == 2
    assert not hasattr(descriptor.schedule_descriptor.capabilities[0], "recipe")
    assert descriptor.public_dict()["controller_actions"] == 0
    assert descriptor.public_dict()["outcomes_opened"] == 0


def test_retirement_plan_returns_only_a_fresh_exact_red_binding() -> None:
    frozen, _document, payload = _payload()

    restored = authenticate_red_living_dex_targeted_bank_retirement_plan(
        payload,
        expected_plan_sha256=hashlib.sha256(payload).hexdigest(),
        expectations=_expectations(),
        freshly_derived_binding=frozen.binding,
    )

    assert restored is frozen.binding


def test_retirement_plan_rejects_metadata_or_lineage_reinterpretation() -> None:
    _frozen, document, _payload_bytes = _payload()
    mutations: list[dict[str, object]] = [
        {**document, "model_sha256": "9" * 64},
        {**document, "runtime_identity_sha256": "9" * 64},
    ]
    changed_binding = json.loads(json.dumps(document["binding"]))
    retirement = changed_binding["retirement"]
    retirement["retired_train_lineages"][0] = retirement[
        "reserve_development_lineages"
    ][0]
    mutations.append(
        {
            **document,
            "binding": changed_binding,
            "binding_sha256": canonical_sha256(changed_binding),
        }
    )

    for mutated in mutations:
        payload = (
            json.dumps(mutated, separators=(",", ":"), sort_keys=True).encode(
                "ascii"
            )
            + b"\n"
        )
        with pytest.raises(RedLivingDexTargetedBankRetirementReaderError):
            load_red_living_dex_targeted_bank_retirement_descriptor(
                payload,
                expected_plan_sha256=hashlib.sha256(payload).hexdigest(),
                expectations=_expectations(),
            )


def test_retirement_plan_rejects_noncanonical_duplicate_or_wrong_width_input() -> None:
    _frozen, document, payload = _payload()
    noncanonical = json.dumps(document, indent=2).encode("ascii")
    duplicate = payload[:-2] + b',"schema":"duplicate"}\n'
    for malformed in (noncanonical, duplicate):
        with pytest.raises(
            RedLivingDexTargetedBankRetirementReaderError,
            match="canonical JSON",
        ):
            load_red_living_dex_targeted_bank_retirement_descriptor(
                malformed,
                expected_plan_sha256=hashlib.sha256(malformed).hexdigest(),
                expectations=_expectations(),
            )

    with pytest.raises(RedLivingDexTargetedBankRetirementReaderError):
        replace(_expectations(), source_commit="a" * 39)
    with pytest.raises(RedLivingDexTargetedBankRetirementReaderError):
        replace(_expectations(), rom_sha256="1" * 63)
