import pytest

from pokemon_red_completion import red_capture_readiness as readiness
from pokemon_red_completion.observation import ItemId


@pytest.mark.parametrize(
    "bag,expected",
    [
        ({2: 5, 3: 8, 1: 1}, (ItemId.GREAT_BALL, 8)),
        ({2: 5, 3: 7, 4: 8}, (ItemId.POKE_BALL, 8)),
        ({2: 24, 3: 8}, (ItemId.ULTRA_BALL, 24)),
        ({2: 99}, (ItemId.ULTRA_BALL, 24)),
        ({3: 5, 2: 7, 4: 7, 1: 99}, None),
        ({}, None),
    ],
)
def test_static_choice_uses_a_sufficient_lot_without_lowering_admission(bag, expected):
    before = dict(bag)
    assert readiness.carried_static_capture_choice(bag) == expected
    assert bag == before


@pytest.mark.parametrize("bag", [None, (), {3: True}, {2: -1}, {4: 100}])
def test_static_choice_does_not_hide_unknown_or_malformed_stock(bag):
    with pytest.raises(ValueError):
        readiness.carried_static_capture_choice(bag)
