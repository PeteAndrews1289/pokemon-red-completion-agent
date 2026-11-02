from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.red_player_gym_switches import (
    CANS,
    can_stances,
    next_can,
    visible_locks,
)


def test_search_visits_every_can_without_solution_reads():
    history = []
    for i in range(30):
        assert next_can(history, (False, False)) == i % 15
        history.append(dict(can=i % 15, before=[False, False], after=[False, False]))
    assert next_can(history, (True, True)) is None


def test_second_lock_search_rotates_adjacent_choices_across_resets():
    history = [dict(can=4, before=[False, False], after=[True, False])]
    choices = []
    for _ in range(4):
        target = next_can(history, (True, False))
        choices.append(target)
        assert sum(abs(a - b) for a, b in zip(CANS[target], CANS[4], strict=True)) == 2
        history.append(dict(can=target, first_can=4, before=[True, False], after=[False, False]))
        history.append(dict(can=4, before=[False, False], after=[True, False]))
    assert len(set(choices)) == 4
    with pytest.raises(ValueError):
        next_can([], (True, False))


def test_gen1_bug_fallback_includes_can_zero_from_nonadjacent_first():
    history = [dict(can=14, before=[False, False], after=[True, False])]
    choices = []
    for _ in range(3):
        choices.append(next_can(history, (True, False)))
        history.append(
            dict(can=choices[-1], first_can=14, before=[True, False], after=[False, False])
        )
        history.append(dict(can=14, before=[False, False], after=[True, False]))
    assert choices == [11, 13, 0]


def test_visible_event_flags_not_hidden_solution_indices():
    flags = [0] * 320
    flags[0x161 // 8] = 2
    assert visible_locks(N(event_flags=tuple(flags))) == (True, False)
    flags[0x161 // 8] = 3
    assert visible_locks(N(event_flags=tuple(flags))) == (True, True)
    with pytest.raises(ValueError):
        visible_locks(N(event_flags=None))


def test_can_stances_face_the_can():
    for i, target in enumerate(CANS):
        for at, facing in can_stances(i):
            assert tuple(a + d for a, d in zip(at, facing.delta, strict=True)) == target


@pytest.mark.parametrize("fault", [None, "cash", "hp", "stale", "unreachable"])
def test_native_can_binding_preserves_resources_and_is_single_use(monkeypatch, fault):
    from copy import copy

    from test_red_player_story_battle import setup

    from pokemon_red_completion import red_player_gym_switches as s
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.route_plan import RoutePlanningError

    rt, actions, route, raw, *_ = setup(monkeypatch)
    raw.map_id = 92
    raw.event_flags = bytes(320)
    raw.party_moves, raw.party_pp, raw.party_status = ((33, 0, 0, 0),), ((35, 0, 0, 0),), (0,)
    current = [raw]
    rt.reader.read = lambda: current[0]
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: object())
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)
    if fault == "unreachable":

        def reject(*a, **k):
            raise RoutePlanningError("blocked")

        monkeypatch.setattr(
            type(route), "route_world", property(lambda _: N(plan_feasible_to_map=reject))
        )

    def act(action):
        actions.actions_executed += 1
        if action.kind is MacroActionKind.INTERACT:
            current[0] = copy(raw)
            if fault == "cash":
                current[0].player_money -= 1
            if fault == "hp":
                current[0].party_hp = (0,)

    actions.execute = act
    history, records = [], []
    binding = s.gym_switch_binding(rt, actions, route=route, history=history, record=records.append)
    assert actions.actions_executed == 0 and not records
    if fault == "unreachable":
        assert binding is None
        return
    if fault == "stale":
        rt.emulator.save_state_bytes = lambda: b"changed"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
    elif fault:
        with pytest.raises(RuntimeError, match="protected"):
            binding.execute()
    else:
        report = binding.execute()
        assert report.evidence["hidden_lock_indices_read"] is False
        assert report.evidence["objective_completed"] is False
        assert records == history and len(history) == 1
        assert binding.verify(report).status.value == "succeeded"
        with pytest.raises(ValueError, match="consumed"):
            binding.execute()
    if fault:
        assert not records and not history
