from __future__ import annotations

import pytest

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.living_dex_targeted_bank_retirement import (
    LivingDexTargetedBankRetirementError,
    plan_living_dex_targeted_bank_retirement,
)
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityContext,
)


def _development_context(ordinal: int) -> LivingDexTargetedCapacityContext:
    return LivingDexTargetedCapacityContext(
        lineage_sha256=f"{ordinal + 1:064x}",
        physical_root_sha256=f"{ordinal + 101:064x}",
        partition="development",
        available_option_kinds=(
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.RESUPPLY,
        ),
    )


def test_retirement_finds_four_diverse_train_roots_and_preserves_reserve() -> None:
    contexts = tuple(_development_context(index) for index in range(10))

    plan = plan_living_dex_targeted_bank_retirement(contexts)

    assert len(plan.retired_train_contexts) == 4
    assert len(plan.paired_development_contexts) == 4
    assert len(plan.reserve_development_contexts) == 2
    assert plan.diversity.diversity_sufficient
    assert plan.diversity.train_lineages == 4
    assert plan.diversity.train_physical_roots == 4
    assert plan.diversity.maximum_slots_on_one_lineage == 2
    assert plan.diversity.maximum_slots_on_one_physical_root == 2
    public = plan.public_dict()
    assert public["evaluation_status_forfeited_roots"] == 4
    assert public["paired_development_roots"] == 4
    assert public["reserve_development_roots"] == 2
    assert public["train_slots"] == 8
    assert public["outcomes_opened"] == 0
    encoded = str(public)
    assert all(context.lineage_sha256 not in encoded for context in contexts)
    assert all(context.physical_root_sha256 not in encoded for context in contexts)


def test_retirement_is_deterministic_across_input_order() -> None:
    contexts = tuple(_development_context(index) for index in range(10))

    forward = plan_living_dex_targeted_bank_retirement(contexts)
    reverse = plan_living_dex_targeted_bank_retirement(tuple(reversed(contexts)))

    assert forward.private_dict() == reverse.private_dict()
    assert forward.plan_sha256 == reverse.plan_sha256


def test_retirement_refuses_an_insufficient_or_pretrained_bank() -> None:
    with pytest.raises(LivingDexTargetedBankRetirementError):
        plan_living_dex_targeted_bank_retirement(
            tuple(_development_context(index) for index in range(7))
        )

    mixed = list(_development_context(index) for index in range(10))
    object.__setattr__(mixed[0], "partition", "train")
    with pytest.raises(LivingDexTargetedBankRetirementError, match="inputs"):
        plan_living_dex_targeted_bank_retirement(tuple(mixed))
