from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.observation import MapId, RawGameState, semantic_facts, semantic_location_facts
from pokemon_red_completion.red_player_field_goals import restoration_progress_preserved
from pokemon_red_completion.route import COMPLETION_QUEST


def raw_at(map_id, *, started=True):
    return RawGameState(started, map_id, 7, 7, 1, 0, badge_bits=255)


@pytest.mark.parametrize("map_id,expected", [
    (MapId.INDIGO_PLATEAU, "story:victory_road_cleared"),
    (MapId.INDIGO_PLATEAU_LOBBY, "story:victory_road_cleared"),
    (MapId.CINNABAR_POKECENTER, "location:cinnabar_island"),
    (MapId.FUCHSIA_POKECENTER, "location:fuchsia_city"),
])
def test_arrival_facts_are_canonical_native_map_facts(map_id, expected):
    raw = raw_at(map_id)
    assert semantic_location_facts(raw) == frozenset({expected})
    assert semantic_location_facts(raw) <= semantic_facts(raw)
    assert not semantic_location_facts(raw_at(map_id, started=False))


@pytest.mark.parametrize("map_id", [None, MapId.VICTORY_ROAD_1F, MapId.VIRIDIAN_CITY])
def test_nonarrival_map_does_not_witness_victory_road(map_id):
    assert "story:victory_road_cleared" not in semantic_location_facts(raw_at(map_id))


def check(required, *, raw=None, before=(), after=("new",), catalog=("new",), after_catalog=None):
    graph = N(objective=lambda _: N(completion_facts=frozenset(required)))
    runtime = N(adapter=N(graph=graph))
    return restoration_progress_preserved(
        runtime,
        {"completed_objectives": before, "objective_catalog": catalog},
        {"completed_objectives": after, "objective_catalog": catalog if after_catalog is None else after_catalog},
        raw or raw_at(MapId.INDIGO_PLATEAU_LOBBY),
    )


def test_real_victory_road_arrival_contract_is_not_a_location_prefix():
    required = COMPLETION_QUEST.objective("cross_victory_road").completion_facts
    assert required == frozenset({"story:victory_road_cleared"})
    assert check(required)


@pytest.mark.parametrize("required", [
    (), ("badge:earth",), ("story:pokedex_received",),
    ("league:lorelei_defeated",), ("story:victory_road_cleared", "badge:earth"),
    ("story:victory_road_cleared", "story:pokedex_received"),
    ("location:invented",),
])
def test_restoration_cannot_adopt_unrelated_or_mixed_progress(required):
    assert not check(required)


def test_real_arrival_requires_actual_current_destination():
    assert not check(("story:victory_road_cleared",), raw=raw_at(MapId.VICTORY_ROAD_1F))
    assert not check(("story:victory_road_cleared",), raw=raw_at(MapId.INDIGO_PLATEAU_LOBBY, started=False))


def test_existing_ordinary_location_discovery_still_passes():
    assert check(("location:fuchsia_city",), raw=raw_at(MapId.FUCHSIA_POKECENTER))


@pytest.mark.parametrize("kwargs", [
    {"before": ("old",), "after": ("new",), "catalog": ("old", "new")},
    {"after_catalog": ("new", "added")},
    {"after": ("unlisted",)},
])
def test_restoration_keeps_catalog_and_monotonic_progress_guards(kwargs):
    assert not check(("story:victory_road_cleared",), **kwargs)


def test_no_progress_change_remains_valid_without_extra_witness():
    assert check((), before=("new",), after=("new",), raw=raw_at(None))
