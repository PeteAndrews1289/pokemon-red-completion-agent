from types import SimpleNamespace as S

import pytest
import pokemon_red_completion.gen1_regional_access as access


@pytest.fixture
def cartridge(monkeypatch):
    access._cave_guard_toggle.cache_clear()
    maps = {3: S(passages=[S(to_map=228, at=(11, 4))]),
            228: S(passages=[S(to_map=226, at=(1, 1))]),
            226: S(passages=[S(to_map=228, at=(2, 2))]),
            227: S(passages=[S(to_map=228, at=(3, 3))])}
    objects = [S(y=12, x=4, movement=255, is_item=False, is_trainer=False)]
    edges = {(12, 4): [S(target=(11, 4))]}
    toggles = {(3, 1): 8}
    monkeypatch.setattr(access, "verify_rom_bytes", lambda rom: None)
    monkeypatch.setattr(access, "map_graph", lambda rom: maps)
    monkeypatch.setattr(access, "map_objects", lambda rom: {3: objects})
    monkeypatch.setattr(access, "walkable_world", lambda rom: {3: object()})
    monkeypatch.setattr(access, "traversal_rules", lambda *args: object())
    monkeypatch.setattr(access, "surf_local_graph", lambda *args: S(edges=edges))
    monkeypatch.setattr(access, "_field_item_toggle_indices", lambda rom: toggles)
    yield maps, objects, edges, toggles
    access._cave_guard_toggle.cache_clear()


@pytest.mark.parametrize("target", [226, 227, 228])
@pytest.mark.parametrize("hidden", [False, True])
def test_remote_gate_tracks_native_visibility_without_goal_or_input(cartridge, target, hidden):
    calls = []
    reader = S(read_toggleable_object_hidden=lambda index: calls.append(index) or hidden)
    assert access.closed_remote_cave_entry(b"fixture", reader, current_map=7,
                                           target_map=target) is (not hidden)
    assert calls == [8]


@pytest.mark.parametrize("current", [226, 227, 228])
@pytest.mark.parametrize("target", [226, 227, 228, 7])
def test_already_inside_never_requires_outside_entry(current, target):
    reader = S(read_toggleable_object_hidden=lambda _: pytest.fail("local gate was read"))
    assert not access.closed_remote_cave_entry(b"invalid", reader,
                                               current_map=current, target_map=target)


def test_unrelated_or_unobservable_gate_preserves_ordinary_route():
    assert not access.closed_remote_cave_entry(b"invalid", object(), current_map=3,
                                               target_map=7)
    assert not access.closed_remote_cave_entry(b"invalid", object(), current_map=3,
                                               target_map=228)


def test_visibility_is_reobserved_after_cartridge_grammar_cache(cartridge):
    values = iter([False, True])
    reader = S(read_toggleable_object_hidden=lambda _: next(values))
    assert access.closed_remote_cave_entry(b"fixture", reader, current_map=3, target_map=228)
    assert not access.closed_remote_cave_entry(b"fixture", reader, current_map=3, target_map=228)
    assert access._cave_guard_toggle.cache_info().misses == 1


@pytest.mark.parametrize("bad", [None, 0, 1, "hidden"])
def test_unknown_visibility_cannot_be_treated_as_closed(cartridge, bad):
    reader = S(read_toggleable_object_hidden=lambda _: bad)
    with pytest.raises(ValueError, match="visibility must be boolean"):
        access.closed_remote_cave_entry(b"fixture", reader, current_map=3, target_map=228)


@pytest.mark.parametrize("mutation", ["second_entry", "other_city", "other_floor", "no_coordinate",
                                       "alternate_approach", "missing_toggle", "moving_guard",
                                       "item", "trainer", "duplicate_guard"])
def test_changed_cartridge_grammar_cannot_suppress_destinations(cartridge, mutation):
    maps, objects, edges, toggles = cartridge
    if mutation == "second_entry": maps[7] = S(passages=[S(to_map=227, at=(4, 4))])
    elif mutation == "other_city": maps[7] = maps.pop(3)
    elif mutation == "other_floor": maps[3].passages[0].to_map = 227
    elif mutation == "no_coordinate": maps[3].passages[0].at = None
    elif mutation == "alternate_approach": edges[(11, 3)] = [S(target=(11, 4))]
    elif mutation == "missing_toggle": toggles.clear()
    elif mutation == "moving_guard": objects[0].movement = 254
    elif mutation == "item": objects[0].is_item = True
    elif mutation == "trainer": objects[0].is_trainer = True
    elif mutation == "duplicate_guard": objects.append(objects[0])
    with pytest.raises(ValueError): access._cave_guard_toggle(b"fixture")
