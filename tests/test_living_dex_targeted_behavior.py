from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUnavailableReason,
)
from pokemon_red_completion.living_dex_targeted_behavior import (
    LIVING_DEX_TARGETED_BEHAVIOR_SHA256,
    LivingDexTargetedBehaviorError,
    living_dex_targeted_behavior_integer_weights,
)


def _features(kind: LivingDexOptionKind) -> LivingDexOptionFeatures:
    return LivingDexOptionFeatures(
        kind,
        completion_gain=0.5,
        dependency_unlock_gain=0.5,
        travel_effort=0.2,
        execution_effort=0.3,
        resource_cost=0.1,
        storage_cost=0.1,
        party_risk=0.1,
        irreversibility_risk=0.0,
        uncertainty=0.2,
    )


def _menu() -> LivingDexOptionMenu:
    context = LivingDexOptionContext(0.8, 0.6, 0.5, 0.3, 0.2, 0.4, 0.5)
    return LivingDexOptionMenu(
        context,
        (
            LivingDexOptionCandidate(
                "private.acquire",
                _features(LivingDexOptionKind.ACQUIRE),
                LivingDexOptionAvailability.AVAILABLE,
            ),
            LivingDexOptionCandidate(
                "private.develop",
                _features(LivingDexOptionKind.DEVELOP),
                LivingDexOptionAvailability.AVAILABLE,
            ),
            LivingDexOptionCandidate(
                "private.trade",
                _features(LivingDexOptionKind.TRADE),
                LivingDexOptionAvailability.UNAVAILABLE,
                LivingDexOptionUnavailableReason.MISSING_CAPABILITY,
            ),
        ),
    )


def test_targeted_behavior_favors_focus_without_masking_an_executable_row() -> None:
    weights = living_dex_targeted_behavior_integer_weights(
        _menu(),
        LivingDexOptionKind.DEVELOP,
    )

    assert weights == (1, 98, 0)
    assert all(weights[index] > 0 for index in _menu().available_indices)
    assert isinstance(LIVING_DEX_TARGETED_BEHAVIOR_SHA256, str)
    assert len(LIVING_DEX_TARGETED_BEHAVIOR_SHA256) == 64


def test_targeted_behavior_rejects_a_masked_or_absent_focus() -> None:
    menu = _menu()
    with pytest.raises(LivingDexTargetedBehaviorError, match="not executable"):
        living_dex_targeted_behavior_integer_weights(
            menu,
            LivingDexOptionKind.TRADE,
        )

    absent = replace(menu, candidates=menu.candidates[:2])
    with pytest.raises(LivingDexTargetedBehaviorError, match="not executable"):
        living_dex_targeted_behavior_integer_weights(
            absent,
            LivingDexOptionKind.RESUPPLY,
        )
