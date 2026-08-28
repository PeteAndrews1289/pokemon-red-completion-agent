from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_causal_capacity_schedule import (
    LivingDexCausalCapacitySchedule,
    LivingDexCausalCapacityScheduleError,
    build_living_dex_causal_capacity_schedule,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)


def _schedule() -> LivingDexCausalCapacitySchedule:
    plan = build_red_living_dex_prospective_capture_plan()
    train = tuple(
        slot.available_option_kinds
        for slot in plan.slots
        if slot.partition is LivingDexCapturePartition.TRAIN
    )
    development = tuple(
        slot.available_option_kinds
        for slot in plan.slots
        if slot.partition is LivingDexCapturePartition.DEVELOPMENT
    )
    return build_living_dex_causal_capacity_schedule(train, development)


def test_schedule_expands_the_fifteen_genuine_menus_to_powered_demand() -> None:
    schedule = _schedule()
    train = tuple(item for item in schedule.slots if item.partition == "train")
    development = tuple(
        item for item in schedule.slots if item.partition == "development"
    )

    assert len(train) == 90
    assert len(development) == 105
    assert Counter(item.template_ordinal for item in train) == Counter(
        {index: 9 for index in range(10)}
    )
    assert Counter(item.template_ordinal for item in development) == Counter(
        {index: 21 for index in range(5)}
    )
    assert Counter(item.focus_kind for item in development) == Counter(
        {kind: 15 for kind in RED_DIRECT_CAUSAL_OPTION_KINDS}
    )


def test_capacity_positions_are_balanced_without_becoming_behavior_draws() -> None:
    schedule = _schedule()
    public = schedule.public_dict()

    for template in range(10):
        assert Counter(
            item.assigned_candidate_index
            for item in schedule.slots
            if item.partition == "train" and item.template_ordinal == template
        ) == Counter({0: 3, 1: 3, 2: 3})
    assert public["capacity_only_not_behavior_assignment"] is True
    assert public["behavior_commitments"] == 0
    assert public["model_choices"] == 0
    assert public["outcomes_observed"] == 0
    assert public["root_claims"] == 0


def test_schedule_is_canonical_and_contains_no_private_or_title_identity() -> None:
    first = _schedule()
    second = _schedule()

    assert first == second
    assert first.schedule_sha256 == second.schedule_sha256
    encoded = str(first.public_dict()).lower()
    assert "species" not in encoded
    assert "map" not in encoded
    assert "root_sha" not in encoded
    assert first.public_dict()["private_identity_fields"] == 0
    assert first.public_dict()["private_path_fields"] == 0


def test_mutation_cannot_relabel_development_or_repeat_a_logical_slot() -> None:
    schedule = _schedule()
    slots = list(schedule.slots)
    development_index = next(
        index for index, item in enumerate(slots) if item.partition == "development"
    )
    with pytest.raises(LivingDexCausalCapacityScheduleError, match="policy choice"):
        replace(
            slots[development_index],
            assigned_candidate_index=0,
        )

    slots = list(schedule.slots)
    slots[1] = slots[0]
    with pytest.raises(LivingDexCausalCapacityScheduleError, match="logical slot"):
        LivingDexCausalCapacitySchedule(
            train_menus=schedule.train_menus,
            development_menus=schedule.development_menus,
            slots=tuple(slots),
        )
