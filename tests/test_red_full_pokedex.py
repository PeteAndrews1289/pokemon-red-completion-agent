import pytest

from pokemon_red_completion.red_full_pokedex import (
    RedFullPokedexCapability,
    RedFullPokedexResolutionKind,
    build_red_full_pokedex_inventory,
)


def test_empty_full_red_inventory_accounts_for_all_151_targets() -> None:
    inventory = build_red_full_pokedex_inventory(frozenset())

    assert inventory.local_registered_count == 0
    assert inventory.missing_local_count == 151
    assert not inventory.full_local_registration_complete
    assert inventory.missing_resolution_counts() == {
        "legitimate_event_input": 1,
        "link_trade": 4,
        "solo_catalog_plan": 124,
        "supporting_save_trade": 11,
        "version_trade": 11,
    }
    assert "unsupported" not in inventory.missing_resolution_counts()


def test_full_local_flags_are_the_only_completion_authority() -> None:
    every_species = frozenset(range(1, 152))
    inventory = build_red_full_pokedex_inventory(every_species)

    assert inventory.local_registered_count == 151
    assert inventory.missing_local_count == 0
    assert inventory.full_local_registration_complete
    assert inventory.status_counts() == {"locally_registered": 151}
    assert inventory.missing_resolution_counts() == {}


def test_shared_credit_and_physical_stock_never_fabricate_local_registration() -> None:
    inventory = build_red_full_pokedex_inventory(
        frozenset(),
        shared_registered_numbers=frozenset({27, 65, 151}),
        physical_specimen_numbers=frozenset({27, 65, 151}),
    )

    for number in (27, 65, 151):
        target = inventory.target(number)
        assert not target.locally_registered
        assert target.shared_registered
        assert target.physical_specimen_present
        assert target.status != "locally_registered"
    assert inventory.local_registered_count == 0
    assert not inventory.full_local_registration_complete


def test_resolution_paths_name_every_external_capability() -> None:
    inventory = build_red_full_pokedex_inventory(frozenset())

    assert (
        inventory.target(7).resolution_kind
        is RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
    )
    assert inventory.target(7).solo_source_id == "gift:OakLab:Squirtle"
    assert inventory.target(27).required_capabilities == (
        RedFullPokedexCapability.PAIRED_BLUE_SAVE,
        RedFullPokedexCapability.LINK_TRADE,
    )
    assert inventory.target(65).required_capabilities == (
        RedFullPokedexCapability.LINK_TRADE,
    )
    assert inventory.target(1).required_capabilities == (
        RedFullPokedexCapability.SUPPORTING_RED_SAVE,
        RedFullPokedexCapability.LINK_TRADE,
    )
    assert inventory.target(134).required_capabilities == (
        RedFullPokedexCapability.SUPPORTING_RED_SAVE,
        RedFullPokedexCapability.LINK_TRADE,
    )
    assert inventory.target(151).required_capabilities == (
        RedFullPokedexCapability.LEGITIMATE_EVENT_INPUT,
    )


def test_local_registration_does_not_erase_the_declared_resolution_path() -> None:
    inventory = build_red_full_pokedex_inventory(frozenset({27}))
    target = inventory.target(27)

    assert target.status == "locally_registered"
    assert target.resolution_kind is RedFullPokedexResolutionKind.VERSION_TRADE
    assert target.required_capabilities == (
        RedFullPokedexCapability.PAIRED_BLUE_SAVE,
        RedFullPokedexCapability.LINK_TRADE,
    )


def test_full_red_inventory_serializes_its_complete_denominator() -> None:
    payload = build_red_full_pokedex_inventory(frozenset()).public_dict()

    assert payload["schema"] == "pokemon.red.full-pokedex-inventory.v1"
    assert payload["target_count"] == 151
    assert payload["local_registered_count"] == 0
    assert payload["missing_local_count"] == 151
    targets = payload["targets"]
    assert isinstance(targets, list)
    assert len(targets) == 151
    assert targets[6]["resolution_kind"] == "solo_catalog_plan"


@pytest.mark.parametrize(
    "numbers",
    ({1}, frozenset({0}), frozenset({152}), frozenset({True})),
)
def test_full_red_inventory_rejects_ambiguous_or_invalid_number_sets(numbers: object) -> None:
    with pytest.raises(ValueError, match="Red National Pokédex numbers"):
        build_red_full_pokedex_inventory(numbers)  # type: ignore[arg-type]


@pytest.mark.parametrize("number", (0, 152, True))
def test_full_red_inventory_rejects_invalid_target_lookup(number: int) -> None:
    inventory = build_red_full_pokedex_inventory(frozenset())

    with pytest.raises(ValueError, match="between 1 and 151"):
        inventory.target(number)
