from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_fishing_acquisition as fishing
from pokemon_red_completion.gen1_cartridge import FishingSlot, RodKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext


def _slot(species: int, level: int = 15) -> FishingSlot:
    return FishingSlot(level, species, RodKind.SUPER)


def _offer(map_id: int, species: tuple[int, ...]) -> fishing.RedFishingDestinationOffer:
    slots = tuple(_slot(number) for number in species)
    return fishing.RedFishingDestinationOffer(
        f"fishing-map-private-{map_id}", map_id, slots, tuple(sorted(set(species)))
    )


def _context() -> LivingDexOptionContext:
    return LivingDexOptionContext(0.8, 0.2, 0.5, 0.4, 0.1, 0.3, 0.7)


def test_offer_exposes_only_identity_free_policy_features():
    offer = _offer(23, (116, 116, 117))

    assert offer.productive_slot_count == 3
    assert offer.policy_features() == {
        "encounter_slot_count": 3,
        "missing_species_count": 2,
        "productive_slot_count": 3,
    }
    assert offer.public_dict()["private_map_fields"] == 0
    assert "116" not in str(offer.public_dict())


def test_offer_rejects_non_super_or_unavailable_missing_species():
    with pytest.raises(ValueError):
        fishing.RedFishingDestinationOffer(
            "fishing-map-private-23",
            23,
            (FishingSlot(5, 129, RodKind.OLD),),
            (129,),
        )
    with pytest.raises(ValueError):
        fishing.RedFishingDestinationOffer(
            "fishing-map-private-23", 23, (_slot(116),), (117,)
        )


def test_cartridge_inventory_filters_registered_and_non_targets(monkeypatch):
    monkeypatch.setattr(
        fishing,
        "RED_SOLO_COLLECTION_CONTRACT",
        SimpleNamespace(target_species=(116, 117, 118)),
    )
    monkeypatch.setattr(fishing, "red_species_number", lambda number: number)
    monkeypatch.setattr(
        fishing,
        "fishing_tables",
        lambda _rom: SimpleNamespace(
            by_map={
                23: (_slot(116), _slot(117)),
                24: (_slot(118),),
                25: (_slot(119),),
            }
        ),
    )

    offers = fishing.red_super_rod_destination_offers(b"rom", {116})

    assert [(offer.map_id, offer.missing_species_numbers) for offer in offers] == [
        (23, (117,)),
        (24, (118,)),
    ]


def test_menu_requires_two_executable_distinguishable_destinations():
    offers = (_offer(23, (116, 116)), _offer(24, (117, 118)))
    menu = fishing.red_fishing_destination_menu(
        _context(),
        offers,
        route_steps=(12, 60),
        maximum_route_steps=100,
        free_storage_slots=40,
    )

    assert len(menu.candidates) == 2
    assert len({menu.candidate_vector(index) for index in menu.available_indices}) == 2
    assert all(candidate.features.resource_cost == 0.0 for candidate in menu.candidates)
    assert all("23" not in candidate.binding_ref for candidate in menu.candidates)

    with pytest.raises(ValueError, match="two|distinct"):
        fishing.red_fishing_destination_menu(
            _context(),
            offers[:1],
            route_steps=(12,),
            maximum_route_steps=100,
            free_storage_slots=40,
        )


class _Model:
    feature_version = 1
    model_sha256 = "a" * 64

    def scores(self, menu, _utility):
        return tuple(float(index) for index in range(len(menu.candidates)))


def test_selection_is_seeded_and_public_receipt_hides_bindings():
    offers = (_offer(23, (116, 116)), _offer(24, (117, 118)))
    menu = fishing.red_fishing_destination_menu(
        _context(),
        offers,
        route_steps=(12, 60),
        maximum_route_steps=100,
        free_storage_slots=40,
    )

    first = fishing.select_red_fishing_destination(_Model(), menu, offers, seed=7)
    second = fishing.select_red_fishing_destination(_Model(), menu, offers, seed=7)

    assert first == second
    assert first.selected_offer in offers
    assert sum(first.probabilities) == pytest.approx(1.0)
    public = first.public_dict()
    assert public["teacher_labels"] == 0
    assert public["private_map_fields"] == 0
    assert "fishing-map-private" not in str(public)
