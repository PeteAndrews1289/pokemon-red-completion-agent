from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityContext,
    LivingDexTargetedCapacityError,
    LivingDexTargetedCapacityPolicy,
    audit_living_dex_targeted_schedule_root_diversity,
    audit_living_dex_targeted_update_capacity,
    freeze_living_dex_targeted_schedule,
    require_living_dex_targeted_schedule_root_diversity,
)


def _context(
    ordinal: int,
    partition: str,
    *kinds: LivingDexOptionKind,
) -> LivingDexTargetedCapacityContext:
    return LivingDexTargetedCapacityContext(
        lineage_sha256=f"{ordinal + 1:064x}",
        physical_root_sha256=f"{ordinal + 101:064x}",
        partition=partition,  # type: ignore[arg-type]
        available_option_kinds=tuple(sorted(kinds, key=list(LivingDexOptionKind).index)),
    )


def _sufficient() -> tuple[LivingDexTargetedCapacityContext, ...]:
    rows: list[LivingDexTargetedCapacityContext] = []
    train_roles = (
        *((LivingDexOptionKind.ACQUIRE,) * 4),
        *((LivingDexOptionKind.DEVELOP,) * 4),
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY,
    )
    development_roles = (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.UNLOCK_ACCESS,
    )
    for ordinal, kind in enumerate(train_roles):
        rows.append(_context(ordinal, "train", kind, LivingDexOptionKind.EXPLORE))
    for offset, kind in enumerate(development_roles, start=len(rows)):
        rows.append(_context(offset, "development", kind, LivingDexOptionKind.EXPLORE))
    return tuple(rows)


def test_frozen_v1_policy_is_ten_train_and_eight_paired_development_roots() -> None:
    policy = LivingDexTargetedCapacityPolicy.v1()

    assert policy.train_roots == 10
    assert policy.development_roots == 8
    assert dict(policy.train_focus_kind_counts) == {
        LivingDexOptionKind.ACQUIRE: 4,
        LivingDexOptionKind.DEVELOP: 4,
        LivingDexOptionKind.MANAGE_STORAGE: 1,
        LivingDexOptionKind.RESUPPLY: 1,
    }
    assert policy.minimum_settled_train == 8
    assert policy.maximum_train_setup_censors == 2


def test_exact_matching_accepts_complete_disjoint_capacity() -> None:
    result = audit_living_dex_targeted_update_capacity(_sufficient())

    assert result.capacity_sufficient
    assert result.train_maximum_matching == 10
    assert result.development_maximum_matching == 8
    public = result.public_dict()
    assert public["train_context_deficit"] == 0
    assert public["development_context_deficit"] == 0
    assert public["controller_actions"] == 0
    assert public["outcomes_opened"] == 0
    assert public["model_fits"] == 0
    assert public["private_identity_fields"] == 0
    assert public["maximum_train_replays_per_context"] == 1


def test_repeatable_train_matching_reuses_two_roots_without_reusing_development() -> None:
    rows = (
        _context(
            0,
            "train",
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.RESUPPLY,
        ),
        _context(
            1,
            "train",
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.RESUPPLY,
        ),
        *_sufficient()[10:],
    )

    result = audit_living_dex_targeted_update_capacity(
        rows,
        maximum_train_replays_per_context=5,
    )

    assert result.capacity_sufficient
    assert result.train_contexts == 2
    assert result.train_maximum_matching == 10
    assert result.development_maximum_matching == 8
    assert result.public_dict()["maximum_train_replays_per_context"] == 5


def test_repeatable_train_bound_cannot_hide_one_root_bottleneck() -> None:
    rows = (_sufficient()[0], *_sufficient()[10:])

    result = audit_living_dex_targeted_update_capacity(
        rows,
        maximum_train_replays_per_context=5,
    )

    assert not result.capacity_sufficient
    assert result.train_maximum_matching <= 5


def test_repeatable_train_bound_is_bounded() -> None:
    with pytest.raises(LivingDexTargetedCapacityError, match="replay bound"):
        audit_living_dex_targeted_update_capacity(
            _sufficient(),
            maximum_train_replays_per_context=33,
        )


def test_freeze_builds_complete_private_schedule_and_path_free_public_receipt() -> None:
    rows = (
        _context(
            0,
            "train",
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.RESUPPLY,
        ),
        _context(
            1,
            "train",
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.RESUPPLY,
        ),
        *_sufficient()[10:],
    )

    schedule = freeze_living_dex_targeted_schedule(
        rows,
        maximum_train_replays_per_context=5,
    )

    train = tuple(slot for slot in schedule.slots if slot.partition == "train")
    development = tuple(slot for slot in schedule.slots if slot.partition == "development")
    assert len(train) == 10
    assert len(development) == 8
    assert {slot.lineage_sha256 for slot in train} == {
        rows[0].lineage_sha256,
        rows[1].lineage_sha256,
    }
    assert sorted(
        slot.reset_ordinal for slot in train if slot.lineage_sha256 == rows[0].lineage_sha256
    ) == list(range(5))
    assert sorted(
        slot.reset_ordinal for slot in train if slot.lineage_sha256 == rows[1].lineage_sha256
    ) == list(range(5))
    assert len({slot.lineage_sha256 for slot in development}) == 8
    public = schedule.public_dict()
    encoded = str(public)
    assert public["train_resets"] == 10
    assert public["train_roots"] == 2
    assert public["development_roots"] == 8
    assert public["development_replays"] == 0
    assert public["outcomes_opened"] == 0
    assert all(row.lineage_sha256 not in encoded for row in rows)


def test_freeze_rejects_incomplete_capacity() -> None:
    with pytest.raises(LivingDexTargetedCapacityError, match="insufficient"):
        freeze_living_dex_targeted_schedule(
            (_sufficient()[0], *_sufficient()[10:]),
            maximum_train_replays_per_context=5,
        )


def test_root_diversity_guard_rejects_the_two_root_confounded_design() -> None:
    rows = (
        _context(
            0,
            "train",
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.RESUPPLY,
        ),
        _context(
            1,
            "train",
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.RESUPPLY,
        ),
        *_sufficient()[10:],
    )
    schedule = freeze_living_dex_targeted_schedule(
        rows,
        maximum_train_replays_per_context=5,
    )

    result = audit_living_dex_targeted_schedule_root_diversity(schedule)

    assert not result.diversity_sufficient
    assert result.train_physical_roots == 2
    assert result.maximum_slots_on_one_physical_root == 5
    assert result.reasons == (
        "insufficient_distinct_train_physical_roots",
        "excessive_train_slot_root_concentration",
        "insufficient_focus_kind_root_diversity",
    )
    encoded = str(result.public_dict())
    assert rows[0].physical_root_sha256 not in encoded
    assert rows[1].physical_root_sha256 not in encoded
    with pytest.raises(LivingDexTargetedCapacityError, match="root diversity"):
        require_living_dex_targeted_schedule_root_diversity(schedule)


def test_root_diversity_guard_accepts_independent_train_roots() -> None:
    result = require_living_dex_targeted_schedule_root_diversity(
        freeze_living_dex_targeted_schedule(_sufficient())
    )

    assert result.diversity_sufficient
    assert result.train_physical_roots == 10
    assert result.maximum_slots_on_one_physical_root == 1
    assert dict(result.physical_roots_by_focus_kind) == {
        LivingDexOptionKind.ACQUIRE: 4,
        LivingDexOptionKind.DEVELOP: 4,
    }


def test_schedule_validation_rejects_development_replay_or_cross_partition_overlap() -> None:
    schedule = freeze_living_dex_targeted_schedule(_sufficient())
    development_index = next(
        index for index, slot in enumerate(schedule.slots) if slot.partition == "development"
    )
    with pytest.raises(LivingDexTargetedCapacityError, match="development"):
        replace(
            schedule.slots[development_index],
            reset_ordinal=1,
        )

    mutated = list(schedule.slots)
    mutated[development_index] = replace(
        mutated[development_index],
        lineage_sha256=schedule.slots[0].lineage_sha256,
    )
    with pytest.raises(LivingDexTargetedCapacityError, match="separation"):
        replace(schedule, slots=tuple(mutated))


def test_matching_detects_shared_kind_bottleneck_not_just_raw_count() -> None:
    rows = list(_sufficient())
    rows[:4] = [
        _context(index, "train", LivingDexOptionKind.DEVELOP, LivingDexOptionKind.EXPLORE)
        for index in range(4)
    ]

    result = audit_living_dex_targeted_update_capacity(rows)

    assert not result.capacity_sufficient
    assert result.train_contexts == 10
    assert result.train_maximum_matching == 6
    assert result.public_dict()["train_context_deficit"] == 4
    assert result.reasons == ("insufficient_train_kind_compatible_lineages",)


def test_partitions_cannot_supply_each_other() -> None:
    rows = tuple(replace(row, partition="development") for row in _sufficient())

    result = audit_living_dex_targeted_update_capacity(rows)

    assert result.train_maximum_matching == 0
    assert not result.capacity_sufficient


def test_rejects_reused_lineage_or_physical_root() -> None:
    rows = _sufficient()
    with pytest.raises(LivingDexTargetedCapacityError, match="lineage"):
        audit_living_dex_targeted_update_capacity((*rows, rows[0]))

    duplicated_root = replace(
        rows[-1],
        physical_root_sha256=rows[0].physical_root_sha256,
    )
    with pytest.raises(LivingDexTargetedCapacityError, match="physical"):
        audit_living_dex_targeted_update_capacity((*rows[:-1], duplicated_root))


def test_policy_rejects_impossible_censor_floor() -> None:
    policy = LivingDexTargetedCapacityPolicy.v1()
    with pytest.raises(LivingDexTargetedCapacityError, match="impossible"):
        replace(policy, minimum_settled_train=9)
