from __future__ import annotations

from copy import deepcopy

import pytest
from test_red_living_dex_clustered_train_runner import (
    _successor_clustered_fixture,
)

from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SHA256,
    RedLivingDexClusteredDevelopmentRunnerError,
    authenticate_red_living_dex_clustered_development_selection,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    RedLivingDexClusteredTrainRunnerError,
    authenticate_red_living_dex_clustered_train_selection,
)


def test_development_selection_addresses_only_frozen_suffix() -> None:
    plan, binding = _successor_clustered_fixture()

    selection = authenticate_red_living_dex_clustered_development_selection(
        plan.private_dict(),
        16,
        binding=binding,
    )

    assert selection.ordinal == 16
    expected_template = plan.assignments[16].capability.template_ordinal
    assert selection.template_ordinal == expected_template
    assert selection.selection_contract_sha256 == (
        RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_SELECTION_SHA256
    )
    assert selection.public_dict() == {
        "controller_api": False,
        "development_accessible": True,
        "model_predictions": 0,
        "ordinal_within_development": 0,
        "partition": "development",
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "setup_executions": 0,
        "template_ordinal": expected_template,
        "train_accessible": False,
    }


@pytest.mark.parametrize("ordinal", [15, 20])
def test_development_selection_rejects_outside_held_suffix(ordinal: int) -> None:
    plan, binding = _successor_clustered_fixture()

    with pytest.raises(
        RedLivingDexClusteredDevelopmentRunnerError,
        match="structurally inaccessible",
    ):
        authenticate_red_living_dex_clustered_development_selection(
            plan.private_dict(),
            ordinal,
            binding=binding,
        )


def test_historical_train_consumer_still_rejects_development() -> None:
    plan, binding = _successor_clustered_fixture()

    with pytest.raises(
        RedLivingDexClusteredTrainRunnerError,
        match="structurally inaccessible",
    ):
        authenticate_red_living_dex_clustered_train_selection(
            plan.private_dict(),
            16,
            binding=binding,
        )


def test_development_selection_rejects_plan_or_partition_mutation() -> None:
    plan, binding = _successor_clustered_fixture()
    private = plan.private_dict()

    changed_plan = deepcopy(private)
    changed_plan["private_plan_sha256"] = "0" * 64
    with pytest.raises(
        RedLivingDexClusteredDevelopmentRunnerError,
        match="authentication failed",
    ):
        authenticate_red_living_dex_clustered_development_selection(
            changed_plan,
            16,
            binding=binding,
        )

    changed_partition = deepcopy(private)
    assignments = changed_partition["assignments"]
    assert isinstance(assignments, list)
    assignment = assignments[16]
    assert isinstance(assignment, dict)
    assignment["partition"] = "train"
    with pytest.raises(
        RedLivingDexClusteredDevelopmentRunnerError,
        match="authentication failed",
    ):
        authenticate_red_living_dex_clustered_development_selection(
            changed_partition,
            16,
            binding=binding,
        )
