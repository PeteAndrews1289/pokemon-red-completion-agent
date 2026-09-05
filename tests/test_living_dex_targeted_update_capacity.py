from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityContext,
    LivingDexTargetedCapacityError,
    LivingDexTargetedCapacityPolicy,
    audit_living_dex_targeted_update_capacity,
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
