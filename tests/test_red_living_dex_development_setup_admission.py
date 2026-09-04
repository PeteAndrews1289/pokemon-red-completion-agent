from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_living_dex_clustered_train_runner import (
    _identity,
    _successor_clustered_fixture,
)

from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    authenticate_red_living_dex_clustered_development_selection,
)
from pokemon_red_completion.red_living_dex_development_setup_admission import (
    RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SHA256,
    RedLivingDexDevelopmentSetupAdmissionError,
    authenticate_frozen_red_living_dex_development_setup_slot,
)


def _admitted():  # type: ignore[no-untyped-def]
    plan, binding = _successor_clustered_fixture()
    selection = authenticate_red_living_dex_clustered_development_selection(
        plan.private_dict(),
        16,
        binding=binding,
    )
    capability = plan.assignments[selection.ordinal].capability
    identity = _identity()
    frozen = authenticate_frozen_red_living_dex_development_setup_slot(
        plan.private_dict(),
        selection=selection,
        binding=binding,
        root=capability.root.root,
        producer_execution_identity=identity,
        expected_runtime_identity_sha256=plan.bindings.runtime_identity_sha256,
    )
    return plan, binding, selection, capability, identity, frozen


def test_development_setup_admits_exact_held_recipe_without_effects() -> None:
    plan, _binding, selection, capability, _identity_value, frozen = _admitted()

    frozen.require_resolved_recipe(capability.recipe)
    frozen.reauthenticate(plan.private_dict(), root=capability.root.root)
    assert frozen.recipe_document() == capability.recipe.private_dict()
    assert frozen.public_dict() == {
        "admission_contract_sha256": (
            RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SHA256
        ),
        "controller_api": False,
        "model_predictions": 0,
        "ordinal_within_development": 0,
        "partition": "development",
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "setup_executions": 0,
        "template_ordinal": selection.template_ordinal,
        "teacher_queries": 0,
        "training_targets_emitted": 0,
    }


def test_development_setup_rejects_root_substitution() -> None:
    plan, binding = _successor_clustered_fixture()
    selection = authenticate_red_living_dex_clustered_development_selection(
        plan.private_dict(),
        16,
        binding=binding,
    )
    wrong_root = plan.assignments[17].capability.root.root

    with pytest.raises(
        RedLivingDexDevelopmentSetupAdmissionError,
        match="root differs",
    ):
        authenticate_frozen_red_living_dex_development_setup_slot(
            plan.private_dict(),
            selection=selection,
            binding=binding,
            root=wrong_root,
            producer_execution_identity=_identity(),
            expected_runtime_identity_sha256=(
                plan.bindings.runtime_identity_sha256
            ),
        )


def test_development_setup_rejects_plan_or_identity_mutation() -> None:
    plan, binding, selection, capability, identity, _frozen = _admitted()
    changed = deepcopy(plan.private_dict())
    changed["source_commit"] = "f" * 40

    with pytest.raises(
        RedLivingDexDevelopmentSetupAdmissionError,
        match="producer plan differs",
    ):
        authenticate_frozen_red_living_dex_development_setup_slot(
            changed,
            selection=selection,
            binding=binding,
            root=capability.root.root,
            producer_execution_identity=identity,
            expected_runtime_identity_sha256=(
                plan.bindings.runtime_identity_sha256
            ),
        )

    with pytest.raises(
        RedLivingDexDevelopmentSetupAdmissionError,
        match="identity binding differs",
    ):
        authenticate_frozen_red_living_dex_development_setup_slot(
            plan.private_dict(),
            selection=selection,
            binding=binding,
            root=capability.root.root,
            producer_execution_identity=replace(identity, source_commit="f" * 40),
            expected_runtime_identity_sha256=(
                plan.bindings.runtime_identity_sha256
            ),
        )


def test_development_setup_detaches_canonical_bytes_and_fails_closed() -> None:
    plan, _binding, _selection, capability, _identity_value, frozen = _admitted()
    mutable = plan.private_dict()
    assignments = mutable["assignments"]
    assert isinstance(assignments, list)
    assignment = assignments[frozen.selection.ordinal]
    assert isinstance(assignment, dict)
    assignment["partition"] = "train"

    assert frozen.recipe_document()["partition"] == "development"
    frozen.require_resolved_recipe(capability.recipe)
    with pytest.raises(
        RedLivingDexDevelopmentSetupAdmissionError,
        match="cannot be decoded",
    ):
        replace(frozen, _recipe_payload=b"not-json\n")


def test_development_setup_public_projection_leaks_no_private_binding() -> None:
    _plan, _binding, selection, _capability, _identity_value, frozen = _admitted()

    encoded = str(frozen.public_dict())
    assert selection.private_plan_sha256 not in encoded
    assert selection.logical_root_sha256 not in encoded
    assert selection.physical_root_sha256 not in encoded
