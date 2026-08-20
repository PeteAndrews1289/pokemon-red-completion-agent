import pytest

from pokemon_red_completion.resource_planning import (
    ResourceOffer,
    ResourcePlanningError,
    ResourceRequirement,
    ResourceRole,
    plan_resource_budget,
)


def test_resource_budget_composes_shared_reserves_and_buys_cheapest_items() -> None:
    plan = plan_resource_budget(
        money=5_000,
        quantities={
            ResourceRole.CAPTURE: 3,
            ResourceRole.HP_RECOVERY: 1,
        },
        requirements=(
            ResourceRequirement(ResourceRole.CAPTURE, 10),
            ResourceRequirement(ResourceRole.CAPTURE, 8),
            ResourceRequirement(ResourceRole.HP_RECOVERY, 4),
        ),
        offers=(
            ResourceOffer("pokemon.core:item:great_ball", ResourceRole.CAPTURE, 600),
            ResourceOffer("pokemon.core:item:poke_ball", ResourceRole.CAPTURE, 200),
            ResourceOffer("pokemon.core:item:super_potion", ResourceRole.HP_RECOVERY, 700),
        ),
    )

    assert plan.funded
    assert [(item.item_ref, item.quantity) for item in plan.purchases] == [
        ("pokemon.core:item:poke_ball", 7),
        ("pokemon.core:item:super_potion", 3),
    ]
    assert plan.total_cost == 3_500
    assert plan.money_remaining == 1_500
    assert dict(plan.final_quantities) == {
        ResourceRole.CAPTURE: 10,
        ResourceRole.HP_RECOVERY: 4,
    }


def test_resource_budget_reports_unfunded_contract_without_shrinking_it() -> None:
    plan = plan_resource_budget(
        money=500,
        quantities={ResourceRole.CAPTURE: 1},
        requirements=(ResourceRequirement(ResourceRole.CAPTURE, 6),),
        offers=(ResourceOffer("pokemon.core:item:poke_ball", ResourceRole.CAPTURE, 200),),
    )

    assert not plan.funded
    assert plan.purchases[0].quantity == 2
    assert plan.shortfalls[0].missing_quantity == 3
    assert plan.shortfalls[0].minimum_additional_money == 500
    assert plan.public_dict()["funded"] is False


def test_resource_budget_respects_limited_shop_stock_then_uses_next_offer() -> None:
    plan = plan_resource_budget(
        money=2_000,
        quantities={},
        requirements=(ResourceRequirement(ResourceRole.STATUS_RECOVERY, 4),),
        offers=(
            ResourceOffer(
                "pokemon.core:item:full_heal",
                ResourceRole.STATUS_RECOVERY,
                300,
                maximum_quantity=2,
            ),
            ResourceOffer(
                "pokemon.core:item:alternate_cure",
                ResourceRole.STATUS_RECOVERY,
                400,
            ),
        ),
    )

    assert plan.funded
    assert [item.quantity for item in plan.purchases] == [2, 2]


@pytest.mark.parametrize("invalid", (-1, True, 1.5))
def test_resource_budget_rejects_invalid_money(invalid: object) -> None:
    with pytest.raises(ResourcePlanningError, match="money"):
        plan_resource_budget(money=invalid, quantities={}, requirements=(), offers=())  # type: ignore[arg-type]
