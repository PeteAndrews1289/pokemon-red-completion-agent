from dataclasses import dataclass, replace

import pytest
from test_red_player_story_fly import setup
from test_red_movement_recurrence import facts
from test_story_unit_v16 import candidate, context

from pokemon_red_completion import red_player_story_fly as fly
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_option_value import LivingDexOptionMenu
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_movement_recurrence import (
    menu_with_movement_history,
    observe_movement_boundary,
)


@pytest.mark.parametrize("arrival", [False, True])
def test_flight_endpoint_is_actual_landing_and_never_completion_saturation(monkeypatch, arrival):
    runtime, actions, args, live, _, _, _ = setup(monkeypatch, arrival=arrival)
    binding = fly.story_fly_binding(runtime, actions, **args)
    expected = None if arrival else canonical_sha256(dict(map=0, at=(3, 4)))
    assert binding.movement_endpoint_sha256 == expected
    assert actions.actions_executed == live.calls == 0
    report = binding.execute()
    assert report.evidence["native_fly"]["destination_map"] == 0
    assert (live.raw.player_y, live.raw.player_x) == (3, 4)
    assert binding.verify(report).status.value == "succeeded"


def test_flight_endpoint_survives_source_identity_changes(monkeypatch):
    runtime, actions, args, live, _, _, _ = setup(monkeypatch)
    first = fly.story_fly_binding(runtime, actions, **args)
    live.state = b"a different observed clock or source identity"
    second = fly.story_fly_binding(runtime, actions, **args)
    assert first.binding_ref != second.binding_ref
    assert first.movement_endpoint_sha256 == second.movement_endpoint_sha256
    assert first.movement_endpoint_sha256 is not None
    assert actions.actions_executed == live.calls == 0


def test_real_flight_binding_participates_in_existing_observed_revisit_rule(monkeypatch):
    runtime, actions, args, live, _, _, _ = setup(monkeypatch)
    binding = fly.story_fly_binding(runtime, actions, **args)
    projected = replace(candidate(), story_unit=binding.story_unit)

    @dataclass(frozen=True)
    class Options:
        menu: object
        bindings: tuple

    other = replace(binding, binding_ref="another legal alternative", movement_endpoint_sha256=None)
    options = Options(
        LivingDexOptionMenu(context(), (projected, replace(projected, binding_ref="other"))),
        (binding, other),
    )
    memory = GoalSearchMemory()
    current = facts()
    current["diagnostics"].update(map_id=10, player_y=5, player_x=6)
    novel = menu_with_movement_history(options, memory, current)
    assert novel.menu.candidates[0].movement_revisit is False
    landing = facts()
    landing["diagnostics"].update(map_id=0, player_y=3, player_x=4)
    observe_movement_boundary(memory, landing)
    repeated = menu_with_movement_history(options, memory, current)
    assert repeated.menu.candidates[0].movement_revisit is True
    assert repeated.bindings is options.bindings
    assert (novel.menu.candidates[0].vector(context(), feature_version=16)
            == repeated.menu.candidates[0].vector(context(), feature_version=16))
    assert actions.actions_executed == live.calls == 0

