from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_clustered_curriculum import (
    LivingDexClusteredCurriculumError,
    LivingDexClusteredScenarioCapability,
    schedule_living_dex_clustered_curriculum,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_clustered_successor import (
    RED_LIVING_DEX_CLUSTERED_SUCCESSOR_POLICY,
    RedLivingDexClusteredSuccessorDesign,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _inventory() -> tuple[LivingDexClusteredScenarioCapability, ...]:
    kinds = tuple(LivingDexOptionKind)
    capabilities: list[LivingDexClusteredScenarioCapability] = []
    for partition, count in (("train", 16), ("development", 4)):
        for ordinal in range(count):
            menu = tuple(
                sorted(
                    {
                        kinds[ordinal % len(kinds)],
                        kinds[(ordinal + 1) % len(kinds)],
                        kinds[(ordinal + 3) % len(kinds)],
                    },
                    key=kinds.index,
                )
            )
            capabilities.append(
                LivingDexClusteredScenarioCapability(
                    lineage_sha256=_sha((partition, "lineage", ordinal)),
                    physical_root_sha256=_sha((partition, "root", ordinal)),
                    partition=partition,  # type: ignore[arg-type]
                    template_sha256=_sha((partition, "template", ordinal)),
                    available_option_kinds=menu,
                )
            )
    return tuple(capabilities)


def test_successor_design_overprovisions_setup_attrition_without_authority() -> None:
    design = RedLivingDexClusteredSuccessorDesign()
    public = design.public_dict()

    assert public["observed_setup_yield"] == {
        "numerator": 5,
        "denominator": 8,
    }
    assert public["expected_settled_examples_at_observed_yield"] == {
        "numerator": 10,
        "denominator": 1,
    }
    assert public["minimum_new_settled_examples"] == 3
    assert public["outcome_aware_admission"] is False
    assert public["development_is_read_only"] is True


def test_successor_policy_requires_twenty_distinct_lineages_and_all_kinds() -> None:
    schedule = schedule_living_dex_clustered_curriculum(
        _inventory(),
        policy=RED_LIVING_DEX_CLUSTERED_SUCCESSOR_POLICY,
    )
    public = schedule.public_dict()

    assert public["train_scenarios"] == 16
    assert public["train_lineages"] == 16
    assert public["development_scenarios"] == 4
    assert public["development_lineages"] == 4
    assert public["maximum_observed_scenarios_per_lineage"] == 1
    assert len(public["train_option_kinds"]) >= 7  # type: ignore[arg-type]
    assert len(public["development_option_kinds"]) >= 7  # type: ignore[arg-type]
    assert public["lineage_overlap"] == 0


def test_successor_policy_fails_closed_when_one_train_lineage_is_missing() -> None:
    inventory = _inventory()

    with pytest.raises(
        LivingDexClusteredCurriculumError,
        match="train inventory is insufficient",
    ):
        schedule_living_dex_clustered_curriculum(
            inventory[1:],
            policy=RED_LIVING_DEX_CLUSTERED_SUCCESSOR_POLICY,
        )


def test_successor_design_module_contains_no_effect_authority() -> None:
    source = __import__(
        "pokemon_red_completion.red_living_dex_clustered_successor",
        fromlist=["unused"],
    ).__file__
    assert source is not None
    payload = Path(source).read_text(encoding="utf-8")

    for forbidden in (
        "PyBoy",
        "write_root_claim",
        "CompletionFirstGoalTeacher",
        ".press(",
        ".tick(",
        "model.fit(",
        "selected_candidate_index",
    ):
        assert forbidden not in payload
