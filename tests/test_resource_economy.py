from __future__ import annotations

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalUnavailableReason,
)
from pokemon_red_completion.resource_economy import (
    CollectionResourceDecision,
    ResourceEconomyError,
    ResourceEconomyState,
    ResourceRenewalKind,
    ResourceRenewalOption,
)


def _masked(
    kind: ResourceRenewalKind,
    reason: GoalUnavailableReason,
) -> ResourceRenewalOption:
    return ResourceRenewalOption(
        kind=kind,
        availability=GoalAvailability.UNAVAILABLE,
        affordability=0.0 if kind is ResourceRenewalKind.PURCHASE else None,
        unavailable_reason=reason,
    )


def _complete_options(
    *overrides: ResourceRenewalOption,
) -> tuple[ResourceRenewalOption, ...]:
    by_kind = {
        kind: _masked(kind, GoalUnavailableReason.NO_LEGAL_TARGET)
        for kind in ResourceRenewalKind
    }
    by_kind.update((option.kind, option) for option in overrides)
    return tuple(by_kind[kind] for kind in ResourceRenewalKind)


def test_bankrupt_capture_state_blocks_instead_of_looping_into_acquisition() -> None:
    economy = ResourceEconomyState(
        reserve_satisfaction=0.0,
        acquisition_resource_available=False,
        options=_complete_options(
            _masked(ResourceRenewalKind.PURCHASE, GoalUnavailableReason.MISSING_RESOURCE),
            _masked(ResourceRenewalKind.EARN, GoalUnavailableReason.NO_LEGAL_TARGET),
            _masked(ResourceRenewalKind.SELL, GoalUnavailableReason.NO_LEGAL_TARGET),
            _masked(ResourceRenewalKind.FIND, GoalUnavailableReason.MISSING_CAPABILITY),
        ),
    )

    assert economy.hard_blocked
    assert economy.collection_decision(
        acquisition_binding_available=False
    ) is CollectionResourceDecision.BLOCKED
    assert economy.public_dict()["raw_currency_included"] is False


def test_available_purchase_precedes_acquisition_when_the_reserve_is_empty() -> None:
    economy = ResourceEconomyState(
        reserve_satisfaction=0.0,
        acquisition_resource_available=False,
        options=_complete_options(
            ResourceRenewalOption(
                kind=ResourceRenewalKind.PURCHASE,
                availability=GoalAvailability.AVAILABLE,
                affordability=1.0,
                expected_reserve_gain=0.8,
            ),
        ),
    )

    assert economy.collection_decision(
        acquisition_binding_available=True
    ) is CollectionResourceDecision.REPLENISH


def test_unknown_income_path_is_investigated_not_declared_impossible() -> None:
    economy = ResourceEconomyState(
        reserve_satisfaction=0.0,
        acquisition_resource_available=False,
        options=_complete_options(
            ResourceRenewalOption(
                kind=ResourceRenewalKind.EARN,
                availability=GoalAvailability.UNKNOWN,
                unavailable_reason=GoalUnavailableReason.WORLD_STATE_UNKNOWN,
            ),
        ),
    )

    assert not economy.hard_blocked
    assert economy.collection_decision(
        acquisition_binding_available=False
    ) is CollectionResourceDecision.INVESTIGATE


def test_resource_contract_rejects_label_like_or_contradictory_affordances() -> None:
    with pytest.raises(ResourceEconomyError, match="positive"):
        ResourceRenewalOption(
            kind=ResourceRenewalKind.PURCHASE,
            availability=GoalAvailability.AVAILABLE,
            affordability=1.0,
            expected_reserve_gain=0.0,
        )
    with pytest.raises(ResourceEconomyError, match="duplicated"):
        ResourceEconomyState(
            reserve_satisfaction=0.0,
            acquisition_resource_available=False,
            options=(
                _masked(
                    ResourceRenewalKind.PURCHASE,
                    GoalUnavailableReason.MISSING_RESOURCE,
                ),
                _masked(
                    ResourceRenewalKind.PURCHASE,
                    GoalUnavailableReason.MISSING_RESOURCE,
                ),
            ),
        )
    with pytest.raises(ResourceEconomyError, match="every renewal kind"):
        ResourceEconomyState(
            reserve_satisfaction=0.0,
            acquisition_resource_available=False,
            options=(
                _masked(
                    ResourceRenewalKind.PURCHASE,
                    GoalUnavailableReason.MISSING_RESOURCE,
                ),
            ),
        )
