"""ROM-free behavior tests loaded against the exact development overlays."""

from types import SimpleNamespace

from pokemon_red_completion import red_native_boxed_evolution as venue
from pokemon_red_completion.red_trainer_evolution import retained_level_evolution_matches


def test_live_native_inventory_keeps_every_covered_venue_in_original_order(monkeypatch):
    route, cave, mansion = (SimpleNamespace(map_id=i) for i in (22, 197, 165))
    slots = {
        22: ((12, 3), (14, 3)),
        197: ((22, 59), (31, 118)),
        165: ((34, 82), (37, 163)),
    }
    party, exclusions = object(), frozenset({26})
    called = []

    def coverage(got_party, source, policy, encounters, *, resources, escape_species,
                 excluded_helper_species):
        assert got_party is party and source == 165
        assert resources and excluded_helper_species == exclusions
        called.append(encounters)
        return encounters != slots[197]

    monkeypatch.setattr(venue, 'collection_encounter_coverage', coverage)
    assert venue.live_native_evolution_venues(party, 165, (route, cave, mansion), slots, exclusions) == (route, mansion)
    assert called == list(slots.values())


def mon(species, level, xp):
    return SimpleNamespace(species_id=species, level=level, experience=xp)


def test_previous_chunk_can_earn_the_level_for_a_later_cartridge_evolution():
    assert retained_level_evolution_matches(mon(108, 21, 9427), mon(108, 22, 10867),
                                             mon(45, 22, 10867), {(108, 45, 22)})


def test_previous_chunk_rejects_unearned_level_xp_regression_and_wrong_species():
    edges = {(108, 45, 22)}
    assert not retained_level_evolution_matches(mon(108, 22, 10867), mon(108, 22, 10867),
                                                 mon(45, 22, 10867), edges)
    assert not retained_level_evolution_matches(mon(108, 21, 9427), mon(108, 22, 10867),
                                                 mon(45, 22, 10000), edges)
    assert not retained_level_evolution_matches(mon(24, 21, 9427), mon(108, 22, 10867),
                                                 mon(45, 22, 10867), edges)
    assert not retained_level_evolution_matches(mon(108, 21, 9427), mon(108, 22, 10867),
                                                 mon(99, 22, 10867), edges)
