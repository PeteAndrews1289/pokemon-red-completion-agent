from __future__ import annotations

import json
from copy import deepcopy

import pytest

from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
)
from pokemon_red_completion.living_dex_policy_codec import (
    LivingDexPolicyCodecError,
    living_dex_private_menu_dict,
    restore_living_dex_policy_menu,
    restore_living_dex_private_menu,
)


def _menu(prefix: str = "private.red") -> LivingDexOptionMenu:
    context = LivingDexOptionContext(0.9, 0.7, 0.5, 0.2, 0.4, 0.3, 0.6)
    candidates = tuple(
        LivingDexOptionCandidate(
            f"{prefix}.{index}.species-map-item",
            LivingDexOptionFeatures(
                kind,
                completion_gain=0.9 - index * 0.1,
                dependency_unlock_gain=0.4 + index * 0.1,
                travel_effort=0.2 + index * 0.1,
                execution_effort=0.3 + index * 0.1,
                resource_cost=0.1,
                storage_cost=0.2,
                party_risk=0.1,
                irreversibility_risk=0.0,
                uncertainty=0.2,
            ),
            LivingDexOptionAvailability.AVAILABLE,
        )
        for index, kind in enumerate(
            (
                LivingDexOptionKind.ACQUIRE,
                LivingDexOptionKind.EVOLVE,
                LivingDexOptionKind.UNLOCK_ACCESS,
            )
        )
    )
    return LivingDexOptionMenu(context, candidates)


def test_policy_round_trip_is_identity_free_and_private_round_trip_is_exact() -> None:
    menu = _menu()
    policy = menu.policy_dict()
    encoded = json.dumps(policy, sort_keys=True)
    assert "private.red" not in encoded
    assert "species-map-item" not in encoded

    learner = restore_living_dex_policy_menu(policy)
    assert learner.policy_dict() == policy
    assert learner.policy_sha256 == menu.policy_sha256
    assert tuple(row.binding_ref for row in learner.candidates) == (
        "policy-row-0",
        "policy-row-1",
        "policy-row-2",
    )

    private = living_dex_private_menu_dict(menu)
    restored = restore_living_dex_private_menu(private)
    assert restored == menu
    assert restored.policy_sha256 == learner.policy_sha256


@pytest.mark.parametrize(
    "mutation",
    (
        "extra-menu-field",
        "binding-census",
        "policy-digest",
        "feature-name-order",
        "one-hot-kind",
        "interaction",
        "availability",
        "normalization",
    ),
)
def test_private_codec_rejects_semantic_and_shape_mutations(mutation: str) -> None:
    document = deepcopy(living_dex_private_menu_dict(_menu()))
    policy = document["policy"]
    assert isinstance(policy, dict)
    candidates = policy["candidates"]
    assert isinstance(candidates, list)
    first = candidates[0]
    assert isinstance(first, dict)
    features = first["features"]
    assert isinstance(features, dict)
    values = features["values"]
    assert isinstance(values, list)
    if mutation == "extra-menu-field":
        policy["title"] = "red"
    elif mutation == "binding-census":
        bindings = document["binding_refs"]
        assert isinstance(bindings, list)
        bindings.pop()
    elif mutation == "policy-digest":
        document["policy_sha256"] = "0" * 64
    elif mutation == "feature-name-order":
        names = features["feature_names"]
        assert isinstance(names, list)
        names[0], names[1] = names[1], names[0]
    elif mutation == "one-hot-kind":
        values[0] = 0.0
    elif mutation == "interaction":
        values[-1] = 0.99
    elif mutation == "availability":
        first["availability"] = "unavailable"
    elif mutation == "normalization":
        features["normalization"] = "title-specific"
    else:  # pragma: no cover
        raise AssertionError(mutation)

    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_private_menu(document)
