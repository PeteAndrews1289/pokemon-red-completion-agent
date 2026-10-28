"""ROM-free dispatch checks; native Tower qualification is separate."""

from types import SimpleNamespace

import pytest

from pokemon_red_completion.red_player_configuration import connect_retained_route22_recovery


def setup(monkeypatch, *, map_id=143, battle_state=2, tower=None, route22=None):
    import pokemon_red_completion.red_player_route22_rival as route
    import pokemon_red_completion.red_player_engaged_story as story

    calls = []
    runtime = SimpleNamespace(reader=SimpleNamespace(read=lambda: SimpleNamespace(
        map_id=map_id, battle_state=battle_state)))
    actor, actions, rom = object(), object(), b"private-cartridge"
    backend = SimpleNamespace(retained_early_trainer_binding=lambda *args, **kwargs:
        calls.append(("ordinary", args, kwargs)) or "ordinary")
    monkeypatch.setattr(route, "retained_second_route22_contract", lambda *_: route22)

    def engaged(*args, **kwargs):
        calls.append(("tower", args, kwargs))
        if isinstance(tower, Exception):
            raise tower
        return tower

    monkeypatch.setattr(story, "engaged_story_binding", engaged)
    connect_retained_route22_recovery(backend,
        {"retained_trainer_binding": lambda *args: calls.append(("route22", args, {})) or "route22"})
    return backend, runtime, actions, rom, actor, calls


def test_already_active_tower_rival_reuses_the_exact_current_actor(monkeypatch):
    expected = object()
    backend, runtime, actions, rom, actor, calls = setup(monkeypatch, tower=expected)
    assert backend.retained_early_trainer_binding(runtime, actions, rom=rom, battler=actor) is expected
    assert len(calls) == 1 and calls[0][0] == "tower"
    assert calls[0][1] == (runtime, actions)
    assert calls[0][2] == dict(rom=rom, battler=actor, objective_id="rescue_fuji",
                              allow_retained_tower=True)


@pytest.mark.parametrize("map_id,battle_state", [(142, 2), (144, 2), (143, 0), (143, 1)])
def test_other_maps_and_nontrainer_states_keep_the_existing_dispatch(monkeypatch, map_id, battle_state):
    backend, runtime, actions, rom, actor, calls = setup(monkeypatch, map_id=map_id, battle_state=battle_state)
    assert backend.retained_early_trainer_binding(runtime, actions, rom=rom, battler=actor) == "ordinary"
    assert [c[0] for c in calls] == ["ordinary"]


def test_absent_tower_contract_does_not_create_a_recovery(monkeypatch):
    backend, runtime, actions, rom, actor, calls = setup(monkeypatch, tower=None)
    assert backend.retained_early_trainer_binding(runtime, actions, rom=rom, battler=actor) == "ordinary"
    assert [c[0] for c in calls] == ["tower", "ordinary"]


def test_wrong_tower_contract_is_not_swallowed_or_replaced(monkeypatch):
    backend, runtime, actions, rom, actor, calls = setup(monkeypatch, tower=ValueError("native rival mismatch"))
    with pytest.raises(ValueError, match="native rival mismatch"):
        backend.retained_early_trainer_binding(runtime, actions, rom=rom, battler=actor)
    assert [c[0] for c in calls] == ["tower"]


def test_existing_route22_executor_and_priority_are_preserved(monkeypatch):
    backend, runtime, actions, rom, actor, calls = setup(monkeypatch, route22=object())
    assert backend.retained_early_trainer_binding(runtime, actions, rom=rom, battler=actor) == "route22"
    assert [c[0] for c in calls] == ["route22"]
