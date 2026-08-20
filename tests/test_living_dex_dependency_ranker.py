from __future__ import annotations

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyMultiplicity,
    DevelopmentCommitmentRoster,
    DevelopmentCommitmentRow,
    build_rootless_living_dex_dependency_design,
    materialize_train_dependency_outcome,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DEPENDENCY_RANKER_FEATURE_NAMES,
    DependencyRankerModel,
    LivingDexDependencyRankerError,
    dependency_train_examples,
    fit_dependency_ranker,
)


def _design():
    roster = DevelopmentCommitmentRoster(
        tuple(
            DevelopmentCommitmentRow(
                f"rootless-development-{index:016x}",
                f"{index + 1:064x}",
            )
            for index in range(4)
        )
    )
    return build_rootless_living_dex_dependency_design(roster)


def test_fixed_interaction_ranker_learns_all_eight_train_preferences() -> None:
    design = _design()
    outcomes = tuple(
        materialize_train_dependency_outcome(scenario) for scenario in design.train_scenarios
    )

    fit = fit_dependency_ranker(design, outcomes)

    assert fit.train_accuracy == 1.0
    assert fit.fitted_cross_entropy < fit.baseline_cross_entropy
    assert fit.model.feature_names == DEPENDENCY_RANKER_FEATURE_NAMES
    assert DependencyRankerModel.from_dict(fit.model.to_dict()) == fit.model
    for scenario in design.train_scenarios:
        expected = (
            GoalKind.ACQUIRE_SPECIES
            if scenario.multiplicity is DependencyMultiplicity.SCARCE
            else GoalKind.EVOLVE_SPECIES
        )
        assert fit.model.preferred_action(scenario) is expected


def test_train_examples_turn_negative_assigned_outcomes_into_other_action_targets() -> None:
    design = _design()
    outcomes = tuple(
        materialize_train_dependency_outcome(scenario) for scenario in design.train_scenarios
    )

    examples = dependency_train_examples(design, outcomes)

    assert len(examples) == 8
    for example in examples:
        if example.reward == 1:
            assert example.preferred_action is example.assigned_action
        else:
            assert example.preferred_action is not example.assigned_action


@pytest.mark.parametrize("mutation", ("missing", "interrupted", "duplicate", "forged"))
def test_train_roster_mutations_fail_closed(mutation: str) -> None:
    design = _design()
    outcomes = [
        materialize_train_dependency_outcome(scenario) for scenario in design.train_scenarios
    ]
    if mutation == "missing":
        outcomes.pop()
    elif mutation == "interrupted":
        outcomes[0] = materialize_train_dependency_outcome(
            design.train_scenarios[0], interrupted=True
        )
    elif mutation == "duplicate":
        outcomes[-1] = outcomes[0]
    else:
        object.__setattr__(
            outcomes[0],
            "scenario_id",
            design.train_scenarios[2].scenario_id,
        )

    with pytest.raises((LivingDexDependencyRankerError, ValueError)):
        fit_dependency_ranker(design, outcomes)


def test_model_loader_rejects_fabricated_feature_names_and_integer_weights() -> None:
    design = _design()
    fit = fit_dependency_ranker(
        design,
        tuple(
            materialize_train_dependency_outcome(scenario) for scenario in design.train_scenarios
        ),
    )
    document = fit.model.to_dict()
    document["feature_names"] = [*DEPENDENCY_RANKER_FEATURE_NAMES[:-1], "species"]
    with pytest.raises(LivingDexDependencyRankerError):
        DependencyRankerModel.from_dict(document)

    document = fit.model.to_dict()
    document["weights"] = [1, 2, 3, 4]
    with pytest.raises(LivingDexDependencyRankerError):
        DependencyRankerModel.from_dict(document)
