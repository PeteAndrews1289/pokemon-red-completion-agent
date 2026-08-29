from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_clustered_curriculum import (
    LIVING_DEX_CLUSTERED_PUBLIC_SCHEDULE_SCHEMA,
    LivingDexClusteredCurriculumError,
    LivingDexClusteredCurriculumPolicy,
    LivingDexClusteredCurriculumSchedule,
    LivingDexClusteredScenarioCapability,
    schedule_living_dex_clustered_curriculum,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = PROJECT_ROOT / "configs/living-dex-clustered-curriculum-v2.json"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _capability(
    partition: str,
    lineage: int,
    template: int,
    kinds: tuple[LivingDexOptionKind, ...],
) -> LivingDexClusteredScenarioCapability:
    return LivingDexClusteredScenarioCapability(
        lineage_sha256=_sha(f"{partition}-lineage-{lineage}"),
        physical_root_sha256=_sha(f"{partition}-root-{lineage}"),
        partition=partition,  # type: ignore[arg-type]
        template_sha256=_sha(f"{partition}-template-{template}"),
        available_option_kinds=kinds,
    )


def _inventory() -> tuple[LivingDexClusteredScenarioCapability, ...]:
    first = (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
    )
    second = (
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.UNLOCK_ACCESS,
    )
    third = (
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.UNLOCK_ACCESS,
        LivingDexOptionKind.EXPLORE,
    )
    return (
        *(
            _capability("train", lineage, lineage * 2, first)
            for lineage in range(4)
        ),
        *(
            _capability("train", lineage, lineage * 2 + 1, second)
            for lineage in range(4)
        ),
        *(
            _capability("development", lineage, 100 + lineage * 2, first)
            for lineage in range(2)
        ),
        *(
            _capability(
                "development",
                lineage,
                101 + lineage * 2,
                third,
            )
            for lineage in range(2)
        ),
    )


def test_clustered_schedule_is_lineage_locked_and_action_free() -> None:
    inventory = _inventory()
    schedule = schedule_living_dex_clustered_curriculum(inventory)
    public = schedule.public_dict()

    assert public["schema"] == LIVING_DEX_CLUSTERED_PUBLIC_SCHEDULE_SCHEMA
    assert public["train_scenarios"] == 8
    assert public["development_scenarios"] == 4
    assert public["train_lineages"] == 4
    assert public["development_lineages"] == 2
    assert public["maximum_observed_scenarios_per_lineage"] == 2
    assert public["lineage_overlap"] == 0
    assert public["cluster_weighting"] == "equal_total_weight_per_lineage"
    assert set(public["train_option_kinds"]) >= {
        "acquire",
        "develop",
        "evolve",
        "manage_storage",
    }
    assert set(public["development_option_kinds"]) >= {
        "acquire",
        "develop",
        "evolve",
    }
    assert {
        public["controller_actions"],
        public["emulator_frames"],
        public["model_fits"],
        public["model_predictions"],
        public["outcomes_observed"],
        public["root_claims"],
        public["teacher_queries"],
        public["unselected_action_targets"],
    } == {0}


def test_clustered_design_config_binds_the_runtime_policy_and_mission() -> None:
    document = json.loads(DESIGN_PATH.read_text(encoding="ascii"))
    policy = LivingDexClusteredCurriculumPolicy()

    assert document["schema"] == (
        "pokemon.core.living-dex-clustered-curriculum-design.v2"
    )
    assert document["design"]["cluster_policy"] == policy.public_dict()
    assert document["design"]["cluster_policy_sha256"] == policy.policy_sha256
    assert document["design"]["teacher_actions_are_labels"] is False
    assert document["design"]["learner_target"] == (
        "selected_arm_realized_outcome_only"
    )
    assert document["independence"]["partition_unit"] == (
        "authenticated_upstream_episode_lineage"
    )
    assert document["independence"]["within_lineage_scenarios_are_correlated"]
    assert document["evaluation"]["primary_unit"] == (
        "upstream_episode_lineage_cluster"
    )
    assert set(document["authorization"].values()) == {False}
    encoded = json.dumps(document, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_clustered_schedule_is_deterministic_under_inventory_reordering() -> None:
    inventory = _inventory()

    forward = schedule_living_dex_clustered_curriculum(inventory)
    reverse = schedule_living_dex_clustered_curriculum(tuple(reversed(inventory)))

    assert forward.schedule_sha256 == reverse.schedule_sha256
    assert forward.private_dict() == reverse.private_dict()


def test_cluster_weights_give_each_lineage_equal_total_weight() -> None:
    schedule = schedule_living_dex_clustered_curriculum(_inventory())
    totals: defaultdict[str, Fraction] = defaultdict(Fraction)

    for assignment in schedule.assignments:
        totals[assignment.capability.lineage_sha256] += schedule.scenario_weight(
            assignment
        )

    assert set(totals.values()) == {Fraction(1, 1)}


def test_clustered_public_summary_does_not_disclose_private_identities() -> None:
    inventory = _inventory()
    encoded = json.dumps(
        schedule_living_dex_clustered_curriculum(inventory).public_dict(),
        sort_keys=True,
    )

    assert all(item.lineage_sha256 not in encoded for item in inventory)
    assert all(item.physical_root_sha256 not in encoded for item in inventory)
    assert all(item.template_sha256 not in encoded for item in inventory)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_clustered_scheduler_rejects_a_lineage_crossing_partitions() -> None:
    inventory = _inventory()
    crossed = replace(
        inventory[-1],
        lineage_sha256=inventory[0].lineage_sha256,
    )

    with pytest.raises(
        LivingDexClusteredCurriculumError,
        match="lineage crosses partitions",
    ):
        schedule_living_dex_clustered_curriculum((*inventory[:-1], crossed))


def test_clustered_scheduler_rejects_unbounded_lineage_dominance() -> None:
    policy = replace(
        LivingDexClusteredCurriculumPolicy(),
        maximum_scenarios_per_lineage=1,
    )

    with pytest.raises(
        LivingDexClusteredCurriculumError,
        match="cannot satisfy its bounds",
    ):
        schedule_living_dex_clustered_curriculum(
            _inventory(),
            policy=policy,
        )


def test_clustered_schedule_validation_rejects_a_missing_lineage() -> None:
    schedule = schedule_living_dex_clustered_curriculum(_inventory())
    first = schedule.assignments[0]
    second = schedule.assignments[1]
    repeated = replace(
        second,
        capability=replace(
            second.capability,
            lineage_sha256=first.capability.lineage_sha256,
            physical_root_sha256=first.capability.physical_root_sha256,
        ),
        within_lineage_ordinal=1,
    )

    with pytest.raises(LivingDexClusteredCurriculumError):
        LivingDexClusteredCurriculumSchedule(
            policy=schedule.policy,
            assignments=(first, repeated, *schedule.assignments[2:]),
        )


def test_clustered_scheduler_rejects_insufficient_kind_coverage() -> None:
    narrow = (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
    )
    inventory = tuple(
        _capability("train", lineage, lineage, narrow) for lineage in range(4)
    ) + tuple(
        _capability("development", lineage, 100 + lineage, narrow)
        for lineage in range(2)
    )

    with pytest.raises(
        LivingDexClusteredCurriculumError,
        match="train inventory is insufficient",
    ):
        schedule_living_dex_clustered_curriculum(inventory)
