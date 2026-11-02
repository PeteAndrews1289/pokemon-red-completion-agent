from dataclasses import replace
from types import SimpleNamespace

import pytest
from capture_fresh_red_brock_development import check_new_six_origin
from red_natural_six_preparation import select_patrol, verify_catch

from pokemon_red_completion.local_router import LocalEdge, LocalGraph


def test_patrol_requires_reversible_safe_walk_and_encounter_ground():
    graph = LocalGraph({(1, 1): (LocalEdge((1, 2), "right"),),
                        (1, 2): (LocalEdge((1, 1), "left"),)})
    grid = ((True,) * 4,) * 4
    assert select_patrol(graph, grid, (1, 1), set()) == "right"
    for blocked in ({(1, 1)}, {(1, 2)}):
        with pytest.raises(ValueError):
            select_patrol(graph, grid, (1, 1), blocked)
    with pytest.raises(ValueError):
        select_patrol(LocalGraph({(1, 1): graph.edges[(1, 1)]}), grid, (1, 1), set())
    with pytest.raises(ValueError):
        select_patrol(graph, ((False,) * 4,) * 4, (1, 1), set())


@pytest.mark.parametrize("change", [{"kind": "ledge"}, {"requirements": frozenset({"cut"})},
                                    {"required_mode": "surf"}, {"transient": (2, 2)}])
def test_patrol_does_not_smuggle_special_traversal(change):
    edge = replace(LocalEdge((1, 2), "right"), **change)
    graph = LocalGraph({(1, 1): (edge,), (1, 2): (LocalEdge((1, 1), "left"),)})
    with pytest.raises(ValueError):
        select_patrol(graph, ((True,) * 4,) * 4, (1, 1), set())


def test_patrol_accepts_cartridge_explicit_land_mode():
    graph = LocalGraph({(1, 1): (LocalEdge((1, 2), "right", required_mode="land"),),
                        (1, 2): (LocalEdge((1, 1), "left", required_mode="land"),)})
    assert select_patrol(graph, ((True,) * 4,) * 4, (1, 1), set()) == "right"


def catch_pair():
    before = SimpleNamespace(battle_state=1, map_id=61, party_count=2,
                             party_species_ids=(1, 2), player_money=200,
                             bag_items=((4, 8), (20, 3)))
    after = SimpleNamespace(battle_state=0, map_id=61, party_count=3,
                            party_species_ids=(1, 2, 2), player_money=200,
                            bag_items=((4, 7), (20, 3)))
    return before, after


def test_catch_allows_duplicates_but_requires_actual_paid_ball():
    before, after = catch_pair()
    assert verify_catch(before, after, True) == 1
    after.bag_items = before.bag_items
    with pytest.raises(ValueError):
        verify_catch(before, after, True)


def test_catch_matches_existing_five_throw_controller_bound():
    before, after = catch_pair()
    after.bag_items = ((4, 3), (20, 3))
    assert verify_catch(before, after, True) == 5
    after.bag_items = ((4, 2), (20, 3))
    with pytest.raises(ValueError):
        verify_catch(before, after, True)


@pytest.mark.parametrize("field,value", [("player_money", 999), ("party_count", 4),
    ("party_species_ids", (2, 1, 3)), ("map_id", 62), ("battle_state", 2),
    ("bag_items", ((4, 7), (20, 2)))])
def test_catch_cannot_hide_resource_or_party_changes(field, value):
    before, after = catch_pair()
    setattr(after, field, value)
    with pytest.raises(ValueError):
        verify_catch(before, after, True)


def test_source_ancestry_checks_physical_not_just_new_label():
    old = {"root_lineage_id": "old", "origin_state_sha256": "a" * 64,
           "battle_state_sha256": "b" * 64, "first_party_ot_id": 1}
    new = {"root_lineage_id": "new", "origin_state_sha256": "c" * 64,
           "battle_state_sha256": "d" * 64, "first_party_ot_id": 2, "boot_frames": 3700}
    inventory = {"manifests": []}
    check_new_six_origin(new, inventory, [old])
    for field in old:
        with pytest.raises(ValueError, match="physical ancestry"):
            check_new_six_origin({**new, field: old[field]}, inventory, [old])
    with pytest.raises(ValueError):
        check_new_six_origin({**new, "boot_frames": 3300}, inventory, [old])
