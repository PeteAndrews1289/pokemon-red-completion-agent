from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pokemon_red_completion.red_battle_catalog import (
    PRET_POKERED_COMMIT,
    RED_BATTLE_CATALOG,
    RedBattleCatalogError,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_battle_scenario import (
    red_battle_move_is_refreshable_model_supported,
    red_battle_refreshable_supported_move_count,
)


def _move(identifier: int) -> str:
    return f"pokemon.red.gb.us.rev0:move:{identifier:03d}"


def _species(identifier: int) -> str:
    return f"pokemon.red.gb.us.rev0:species:{identifier:03d}"


def test_catalog_covers_every_canonical_red_species_and_move() -> None:
    assert PRET_POKERED_COMMIT == "1e96034092686d006e863cace09e87273051a3d8"
    assert RED_BATTLE_CATALOG.move_count == 165
    assert RED_BATTLE_CATALOG.species_count == 151


def test_catalog_builds_stable_game_local_references() -> None:
    assert pokemon_red_move_ref(85) == _move(85)
    assert pokemon_red_species_ref(104) == _species(104)
    for builder in (pokemon_red_move_ref, pokemon_red_species_ref):
        with pytest.raises(RedBattleCatalogError):
            builder(0)


def test_known_move_mechanics_match_pinned_red_source() -> None:
    tackle = RED_BATTLE_CATALOG.resolve_move(_move(33))
    assert tackle.type_name == "normal"
    assert tackle.category == "physical"
    assert tackle.power == 35
    assert tackle.accuracy == 0.95
    assert tackle.max_pp == 35
    assert tackle.effect_flags == frozenset()

    thunderbolt = RED_BATTLE_CATALOG.resolve_move(_move(85))
    assert thunderbolt.type_name == "electric"
    assert thunderbolt.category == "special"
    assert thunderbolt.power == 95
    assert thunderbolt.accuracy == 1.0
    assert thunderbolt.max_pp == 15
    assert thunderbolt.effect_flags == frozenset({"status"})

    night_shade = RED_BATTLE_CATALOG.resolve_move(_move(101))
    assert night_shade.category == "physical"
    assert night_shade.power == 0
    assert night_shade.effect_flags == frozenset({"fixed_damage"})


def test_refreshable_move_support_keeps_the_learner_mechanics_boundary() -> None:
    assert red_battle_move_is_refreshable_model_supported(1)
    assert not red_battle_move_is_refreshable_model_supported(39)
    assert not red_battle_move_is_refreshable_model_supported(120)
    assert red_battle_refreshable_supported_move_count((1, 2, 39, 120)) == 2


def test_known_effect_and_priority_flags_match_red_battle_core() -> None:
    assert RED_BATTLE_CATALOG.resolve_move(_move(98)).priority == 1
    counter = RED_BATTLE_CATALOG.resolve_move(_move(68))
    assert counter.priority == -1
    assert counter.effect_flags == frozenset({"counter"})
    assert RED_BATTLE_CATALOG.resolve_move(_move(63)).effect_flags == frozenset({"recharge"})
    assert RED_BATTLE_CATALOG.resolve_move(_move(105)).effect_flags == frozenset({"heal"})
    assert RED_BATTLE_CATALOG.resolve_move(_move(120)).effect_flags == frozenset({"self_destruct"})
    assert RED_BATTLE_CATALOG.resolve_move(_move(136)).effect_flags == frozenset({"recoil"})


def test_species_types_match_internal_red_species_references() -> None:
    assert RED_BATTLE_CATALOG.resolve_species(_species(177)).types == ("water",)
    assert RED_BATTLE_CATALOG.resolve_species(_species(180)).types == ("fire", "flying")
    assert RED_BATTLE_CATALOG.resolve_species(_species(22)).types == ("water", "flying")
    assert RED_BATTLE_CATALOG.resolve_species(_species(25)).types == ("ghost", "poison")


def test_monotype_is_not_counted_twice() -> None:
    assert RED_BATTLE_CATALOG.type_effectiveness("electric", ("water",)) == 2.0
    assert RED_BATTLE_CATALOG.type_effectiveness("electric", ("water", "water")) == 2.0


def test_exact_gen_one_dual_type_effectiveness_and_immunity() -> None:
    assert RED_BATTLE_CATALOG.type_effectiveness("electric", ("water", "flying")) == 4.0
    assert RED_BATTLE_CATALOG.type_effectiveness("ice", ("dragon", "flying")) == 4.0
    assert RED_BATTLE_CATALOG.type_effectiveness("electric", ("water", "ground")) == 0.0
    assert RED_BATTLE_CATALOG.type_effectiveness("ghost", ("psychic",)) == 0.0
    assert RED_BATTLE_CATALOG.type_effectiveness("bug", ("poison",)) == 2.0
    assert RED_BATTLE_CATALOG.type_effectiveness("normal", ("water",)) == 1.0


@pytest.mark.parametrize(
    "reference,resolver",
    [
        ("pokemon.red.gb.us.rev0:move:33", RED_BATTLE_CATALOG.resolve_move),
        ("pokemon.red.gb.us.rev0:move:000", RED_BATTLE_CATALOG.resolve_move),
        ("pokemon.red.gb.us.rev0:move:166", RED_BATTLE_CATALOG.resolve_move),
        ("pokemon.red.gb.us.rev0:species:031", RED_BATTLE_CATALOG.resolve_species),
        ("pokemon.red.gb.us.rev0:species:999", RED_BATTLE_CATALOG.resolve_species),
        ("pokemon.red.gb.us.rev0:move:033/rom", RED_BATTLE_CATALOG.resolve_move),
        ("pokemon.red.gb.us.rev0:species:177", RED_BATTLE_CATALOG.resolve_move),
    ],
)
def test_unknown_or_malformed_references_fail_closed(reference: str, resolver: object) -> None:
    with pytest.raises(RedBattleCatalogError):
        resolver(reference)  # type: ignore[operator]


def test_catalog_values_are_immutable() -> None:
    mechanics = RED_BATTLE_CATALOG.resolve_move(_move(33))
    with pytest.raises(FrozenInstanceError):
        mechanics.power = 999  # type: ignore[misc]
