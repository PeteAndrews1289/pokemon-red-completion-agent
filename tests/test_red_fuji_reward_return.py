"""A model-owned healing detour must not send a rescued Fuji back to the Tower."""

from types import SimpleNamespace as N

import pytest
from test_red_player_early_story_options import fixture
from test_red_player_story_travel import setup

from pokemon_red_completion import red_player_early_story_options as early
from pokemon_red_completion import red_player_story_obstruction as obstruction
from pokemon_red_completion import red_player_story_travel as travel


def flags(*events):
    result = bytearray(320)
    for event in events:
        result[event // 8] |= 1 << (event % 8)
    return bytes(result)


@pytest.mark.parametrize("room", [141, 148, 149, 4])
@pytest.mark.parametrize(
    "events,bag,home",
    [
        ((279, 1231), (), True),
        ((271, 273, 274, 275), (), False),
        ((279,), (), False),
        ((1231,), (), False),
        ((279, 1231, 296), (), False),
        ((279, 1231), ((73, 1),), False),
        ((279, 1231), None, False),
    ],
)
def test_destination_requires_both_rescue_flags_and_unclaimed_reward(room, events, bag, home):
    raw = N(map_id=room, event_flags=flags(*events), bag_items=bag)
    before = vars(raw).copy()
    assert travel.story_destination_map("rescue_fuji", raw) == (149 if home else 148)
    assert travel.story_destination_map("reach_celadon", raw) == 6
    assert vars(raw) == before


@pytest.mark.parametrize("events", [None, b"", bytes(154)])
def test_incomplete_observation_cannot_authorize_fuji_relocation(events):
    assert travel.story_destination_map("rescue_fuji", N(event_flags=events, bag_items=())) == 148


def test_home_route_never_claims_flute_or_rescue_completion(monkeypatch):
    rt, actions, route, raw, lesson = setup(monkeypatch)
    raw.map_id, raw.event_flags = 148, flags(279, 1231)
    objective = N(id="rescue_fuji", completion_facts=frozenset({"quest:fuji_rescued"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.observer.latch_verified_facts = lambda _: pytest.fail("travel synthesized gift completion")
    before_bag = raw.bag_items
    binding = travel.story_travel_binding(rt, actions, objective_id="rescue_fuji", route=route)
    assert binding is not None and binding.story_approach_only
    assert actions.actions_executed == 0
    report = binding.execute()
    assert raw.map_id == 149 and raw.bag_items == before_bag
    assert not report.evidence["objective_completed"]
    assert binding.verify(report).status.value == "succeeded"
    assert "rescue_fuji" not in lesson["completed_objectives"]


@pytest.mark.parametrize("blocked", [False, True])
def test_tower_return_drops_obsolete_fuji_coordinate_but_keeps_story_actor(monkeypatch, blocked):
    rt, route, actor, binding, calls, raw = fixture(
        monkeypatch, objective="rescue_fuji", room=148, flags=(279, 1231),
    )
    raw.bag_items = ()
    monkeypatch.setattr(
        early, "map_object_events", lambda *a: pytest.fail("absent Tower Fuji queried")
    )
    def quote(*a, **kw):
        assert kw["objective_id"] == "rescue_fuji"
        assert kw["frontier"] is True and kw["destination_at"] is None
        assert kw["stop_at_map_boundary"] is True
        return None if blocked else binding
    monkeypatch.setattr(early, "story_travel_binding", quote)
    # Native rescue implies these guards are beaten; the planner does not need
    # to fabricate a fresh trainer when the destination is the reward house.
    raw.event_flags = flags(271, 273, 274, 275, 279, 1231)
    def blocked_quote(*a, **kw):
        assert blocked and kw["battler"] is actor
        assert kw["objective_id"] == "rescue_fuji"
        assert kw["frontier"] is True and kw["destination_at"] is None
        return binding
    monkeypatch.setattr(early, "obstructing_story_battle_binding", blocked_quote)
    row = early.fuji_story_option(rt, N(), route=route, battler=actor, combat_levels=(37,))
    assert row[0].story_objective_ref == "rescue_fuji"
    assert row[1].combat_required is blocked


def test_obstruction_preview_uses_the_same_reward_house_destination(monkeypatch):
    raw = N(map_id=148, event_flags=flags(279, 1231), bag_items=())
    rt = N(reader=N(read=lambda: raw, read_current_map_objects=lambda: ()))
    start = N(map_id=148)
    observed = []
    monkeypatch.setattr(obstruction, "_field_ready", lambda _: True)
    monkeypatch.setattr(
        obstruction, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: start)
    )
    monkeypatch.setattr(obstruction, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(obstruction, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(obstruction, "map_object_events", lambda *a: ())
    monkeypatch.setattr(obstruction, "trainer_sight_zones", lambda *a: ())
    def preview(rom, world, actual, zones, destination, **kw):
        assert actual is start and destination == 149
        observed.append(destination)
        return ()
    monkeypatch.setattr(obstruction, "blocking_story_trainers", preview)
    assert obstruction.obstructing_story_battle_binding(
        rt, N(), objective_id="rescue_fuji", route=N(rom=b"rom", route_world=N()), battler=N(),
    ) is None
    assert observed == [149]
