from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from test_red_living_dex_setup_recipe import _identity, _recipes, _root

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_admission import (
    RedLivingDexSetupAdmissionError,
    authenticate_frozen_red_living_dex_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    build_red_living_dex_setup_recipe_plan,
)


def _fixture(ordinal: int = 0):  # type: ignore[no-untyped-def]
    plan = build_red_living_dex_setup_recipe_plan(
        _recipes(),
        execution_identity=_identity(),
    )
    root = _root(ordinal)
    document = plan.private_dict()
    frozen = authenticate_frozen_red_living_dex_setup_slot(
        document,
        expected_plan_sha256=plan.plan_sha256,
        ordinal=ordinal,
        root=root,
    )
    return plan, root, document, frozen


def test_authenticates_whole_plan_and_detaches_one_exact_recipe() -> None:
    plan, root, document, frozen = _fixture(3)
    recipe = plan.recipes[3]

    assert frozen.producer_plan_sha256 == plan.plan_sha256
    assert frozen.producer_execution_identity_sha256 == plan.execution_identity.identity_sha256
    assert frozen.recipe_sha256 == recipe.recipe_sha256
    assert frozen.slot_sha256 == recipe.slot_sha256
    assert frozen.logical_root_sha256 == root.root_consumption_sha256
    assert frozen.physical_root_sha256 == root.physical_root_sha256
    assert canonical_sha256(frozen.recipe_document()) == recipe.recipe_sha256
    assert frozen.recipe_document() == document["recipes"][3]
    assert frozen.recipe_document() is not document["recipes"][3]
    assert frozen.producer_execution_identity() == plan.execution_identity
    frozen.require_resolved_recipe(recipe)


def test_json_round_trip_preserves_tuple_valued_recipe_semantics() -> None:
    plan, _root_value, _document, frozen = _fixture(4)
    purchases = plan.recipes[4].providers[1].family.semantic_parameters["purchases"]

    assert isinstance(purchases, tuple)
    assert isinstance(
        frozen.recipe_document()["providers"][1]["family"]["semantic_parameters"][
            "purchases"
        ],
        list,
    )
    frozen.require_resolved_recipe(plan.recipes[4])


def test_caller_nested_mutation_cannot_change_the_detached_descriptor() -> None:
    _plan, root, document, frozen = _fixture(2)
    original_payload = frozen.plan_payload
    recipes = document["recipes"]
    assert isinstance(recipes, list)
    recipe = recipes[2]
    assert isinstance(recipe, dict)
    providers = recipe["providers"]
    assert isinstance(providers, list)
    provider = providers[0]
    assert isinstance(provider, dict)
    family = provider["family"]
    assert isinstance(family, dict)
    parameters = family["semantic_parameters"]
    assert isinstance(parameters, dict)
    parameters["mutated_after_authentication"] = True

    assert frozen.plan_payload == original_payload
    assert "mutated_after_authentication" not in str(frozen.recipe_document())
    with pytest.raises(RedLivingDexSetupAdmissionError, match="producer plan differs"):
        frozen.reauthenticate(document, root=root)


@pytest.mark.parametrize(
    "mutation",
    (
        "other_recipe_nested_family",
        "selected_recipe_route",
        "execution_identity",
        "control_flag",
    ),
)
def test_reauthentication_rejects_any_deep_plan_drift(mutation: str) -> None:
    _plan, root, document, frozen = _fixture(0)
    changed = copy.deepcopy(document)
    recipes = changed["recipes"]
    assert isinstance(recipes, list)
    if mutation == "other_recipe_nested_family":
        providers = recipes[14]["providers"]
        providers[0]["family"]["semantic_parameters"]["drift"] = True
    elif mutation == "selected_recipe_route":
        recipes[0]["construction_route_sha256"] = "f" * 64
    elif mutation == "execution_identity":
        execution = changed["execution_identity"]
        assert isinstance(execution, dict)
        execution["source_commit"] = "e" * 40
        changed["execution_identity_sha256"] = canonical_sha256(execution)
    else:
        changed["retry_after_controller_input"] = True

    with pytest.raises(RedLivingDexSetupAdmissionError):
        frozen.reauthenticate(changed, root=root)


def test_root_substitution_and_resolved_recipe_substitution_fail_closed() -> None:
    plan, _root_zero, document, frozen = _fixture(0)
    with pytest.raises(RedLivingDexSetupAdmissionError, match="selected recipe"):
        authenticate_frozen_red_living_dex_setup_slot(
            document,
            expected_plan_sha256=plan.plan_sha256,
            ordinal=0,
            root=_root(1),
        )
    with pytest.raises(RedLivingDexSetupAdmissionError, match="resolved recipe differs"):
        frozen.require_resolved_recipe(
            replace(plan.recipes[0], root_consumption_sha256="b" * 64)
        )


def test_plan_hash_cannot_be_recomputed_by_an_attacker_at_consumption() -> None:
    plan, root, document, frozen = _fixture(0)
    changed = copy.deepcopy(document)
    changed["learner_effects"] = 1
    attacker_hash = canonical_sha256(changed)

    with pytest.raises(RedLivingDexSetupAdmissionError, match="producer plan differs"):
        authenticate_frozen_red_living_dex_setup_slot(
            changed,
            expected_plan_sha256=plan.plan_sha256,
            ordinal=0,
            root=root,
        )
    assert attacker_hash != frozen.producer_plan_sha256
