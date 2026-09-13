"""The learner may see financial features, not cartridge item identifiers."""

from dataclasses import replace

from test_living_dex_option_value import _menu

from pokemon_red_completion.living_dex_option_value import LivingDexOptionMenu
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.resource_economy_observation import (
    EconomyMode,
    EconomyOffer,
    EconomySnapshot,
)


def test_financial_policy_projection_does_not_expose_item_identity():
    base = _menu()
    candidates = tuple(replace(c, economy_offer=EconomyOffer(EconomyMode.OTHER))
                       for c in base.candidates)
    menus = tuple(LivingDexOptionMenu(
        replace(base.context, economy_snapshot=EconomySnapshot(200, ((key, count),)),
                target_cash=1000), candidates,
    ) for key, count in (("red-item-001", 3), ("other-title-item", 9)))
    assert menus[0].policy_dict() == menus[1].policy_dict()
    for menu in menus:
        document = menu.policy_dict()
        assert "red-item" not in str(document)
        assert "other-title-item" not in str(document)
        restored = restore_living_dex_policy_menu(document)
        assert restored.policy_dict() == document
        assert restored.candidate_vector(0) == menu.candidate_vector(0)
        assert candidates[0].features.vector(menu.context, feature_version=4) == (
            candidates[0].features.vector(menu.context, feature_version=3)
        )
