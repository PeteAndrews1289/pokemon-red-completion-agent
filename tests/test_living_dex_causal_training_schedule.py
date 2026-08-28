from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    LivingDexCausalCurriculumDesign,
)
from pokemon_red_completion.living_dex_causal_training_schedule import (
    LivingDexBlockedBehaviorError,
    LivingDexBlockedBehaviorSchedule,
    freeze_living_dex_blocked_behavior_schedule,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)


def _train_templates() -> tuple[tuple[LivingDexOptionKind, ...], ...]:
    return tuple(
        slot.available_option_kinds
        for slot in build_red_living_dex_prospective_capture_plan().slots
        if slot.partition is LivingDexCapturePartition.TRAIN
    )


def _schedule(entropy: bytes = bytes(range(32))) -> LivingDexBlockedBehaviorSchedule:
    return freeze_living_dex_blocked_behavior_schedule(
        _train_templates(),
        entropy=entropy,
    )


def test_schedule_balances_every_candidate_with_uniform_marginal_support() -> None:
    schedule = _schedule()
    design = LivingDexCausalCurriculumDesign()
    public = schedule.public_dict()

    assert len(schedule.assignments) == design.prospective_train_contexts == 90
    assert Counter(item.candidate_index for item in schedule.assignments) == Counter(
        {0: 30, 1: 30, 2: 30}
    )
    assert Counter(item.selected_kind.value for item in schedule.assignments) == Counter(
        design.prospective_selected_kind_counts
    )
    assert public["full_support_marginal"] == {"denominator": 3, "numerator": 1}
    assert public["unselected_action_targets"] == 0
    assert public["outcomes_observed"] == 0
    assert public["root_claims"] == 0


def test_each_three_root_block_is_one_random_candidate_permutation() -> None:
    schedule = _schedule()

    for template in range(10):
        for block in range(3):
            assignments = tuple(
                item
                for item in schedule.assignments
                if item.template_ordinal == template and item.block_ordinal == block
            )
            assert tuple(item.within_block_ordinal for item in assignments) == (0, 1, 2)
            assert {item.candidate_index for item in assignments} == {0, 1, 2}


def test_schedule_replays_exactly_and_entropy_changes_order_not_coverage() -> None:
    first = _schedule(bytes(range(32)))
    replay = _schedule(bytes(range(32)))
    second = _schedule(bytes(reversed(range(32))))

    assert first == replay
    assert first.schedule_sha256 == replay.schedule_sha256
    assert first.assignments != second.assignments
    assert first.entropy_commitment_sha256 != second.entropy_commitment_sha256
    assert Counter(item.candidate_index for item in first.assignments) == Counter(
        item.candidate_index for item in second.assignments
    )
    assert Counter(item.selected_kind for item in first.assignments) == Counter(
        item.selected_kind for item in second.assignments
    )
    assert "entropy" not in str(first.public_dict()).lower().replace(
        "entropy_committed", ""
    )


def test_schedule_mutations_cannot_hide_an_omitted_or_duplicate_arm() -> None:
    schedule = _schedule()
    assignments = list(schedule.assignments)
    assignments[1] = replace(
        assignments[1],
        candidate_index=assignments[0].candidate_index,
        selected_kind=assignments[0].selected_kind,
    )

    with pytest.raises(LivingDexBlockedBehaviorError, match="candidate permutation"):
        LivingDexBlockedBehaviorSchedule(
            menu_templates=schedule.menu_templates,
            entropy_commitment_sha256=schedule.entropy_commitment_sha256,
            assignments=tuple(assignments),
        )


def test_schedule_rejects_trade_fiction_or_short_entropy() -> None:
    templates = list(_train_templates())
    templates[0] = (
        LivingDexOptionKind.TRADE,
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EXPLORE,
    )
    with pytest.raises(LivingDexBlockedBehaviorError, match="three-kind Red"):
        freeze_living_dex_blocked_behavior_schedule(
            tuple(templates),
            entropy=bytes(range(32)),
        )
    with pytest.raises(LivingDexBlockedBehaviorError, match="256 bits"):
        freeze_living_dex_blocked_behavior_schedule(
            _train_templates(),
            entropy=b"too short",
        )
