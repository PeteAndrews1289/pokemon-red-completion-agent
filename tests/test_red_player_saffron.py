from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_saffron as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


@pytest.mark.parametrize("fault", [None, "closed", "no_gate", "wrong_map", "cash_changed"])
def test_retained_nurse_settlement_preserves_native_state(monkeypatch, fault):
    raw = raw_state()
    raw.map_id = int(s.MapId.SAFFRON_POKECENTER) if fault != "wrong_map" else 141
    raw.status_flags_1 = 0 if fault == "no_gate" else s.SAFFRON_GUARD_ACCESS_MASK
    dialogue = [fault != "closed"]
    em = N(state=b"dialogue", frame_count=0)
    em.save_state_bytes = lambda: em.state
    actions = N(actions_executed=0)
    facts = frozenset({"location:saffron_city"})
    latched = []
    rt = N(
        emulator=em,
        reader=N(
            read=lambda: N(**vars(raw)),
            read_input_readiness=lambda: N(ready=True),
            read_bottom_dialogue_box_visible=lambda: dialogue[0],
        ),
        adapter=N(graph=N(objective=lambda _: N(completion_facts=facts))),
        observer=N(latch_verified_facts=latched.append),
    )
    monkeypatch.setattr(s, "_raw_party_fully_restored", lambda _: True)
    monkeypatch.setattr(s, "_field_ready", lambda _: not dialogue[0])

    def close(*args):
        dialogue[0] = False
        em.state = b"settled"
        actions.actions_executed += 4
        em.frame_count += 120
        if fault == "cash_changed":
            raw.player_money -= 1

    monkeypatch.setattr(s, "_close_menus", close)
    binding = s.saffron_settlement_binding(rt, actions)
    assert actions.actions_executed == 0
    if fault in {"closed", "no_gate", "wrong_map"}:
        assert binding is None
    elif fault:
        with pytest.raises(ValueError):
            binding.execute()
        assert not latched
    else:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert latched == [facts]
        with pytest.raises(ValueError):
            binding.execute()


def raw_state():
    return N(
        battle_state=0,
        restored=True,
        status_flags_1=0,
        player_money=4238,
        bag_items=((73, 1), (3, 5)),
        party_species_ids=(108, 166, 179, 5, 150, 185),
        badge_bits=15,
        event_flags=b"flags",
        map_id=141,
    )


@pytest.mark.parametrize(
    "fault", [None, "hurt", "cash", "bag", "drink", "open", "unknown", "battle"]
)
def test_access_admission_uses_actual_resources(monkeypatch, fault):
    raw = raw_state()
    monkeypatch.setattr(s, "_raw_party_fully_restored", lambda r: r.restored)
    if fault == "hurt":
        raw.restored = False
    if fault == "cash":
        raw.player_money = 199
    if fault == "bag":
        raw.bag_items = tuple((i, 1) for i in range(20))
    if fault == "drink":
        raw.bag_items += ((int(s.ItemId.FRESH_WATER), 1),)
    if fault == "open":
        raw.status_flags_1 = s.SAFFRON_GUARD_ACCESS_MASK
    if fault == "unknown":
        raw.status_flags_1 = None
    if fault == "battle":
        raw.battle_state = 1
    assert s.saffron_access_ready(raw) is (fault is None)


@pytest.mark.parametrize(
    "fault", [None, "wrong_cash", "wrong_party", "no_gate", "hurt_arrival", "unavailable"]
)
def test_access_is_selected_once_and_requires_native_outcome(monkeypatch, fault):
    raw = raw_state()
    latched = []
    called = []
    objective = N(id="reach_saffron", completion_facts=frozenset({"location:saffron_city"}))
    em = N(frame_count=0, state=b"source")
    em.save_state_bytes = lambda: em.state
    rt = N(
        reader=N(read=lambda: N(**vars(raw))),
        emulator=em,
        adapter=N(
            observe=lambda: N(game_state=None),
            graph=N(
                objective=lambda _: objective,
                available_objectives=lambda _: () if fault == "unavailable" else (objective,),
            ),
        ),
        observer=N(latch_verified_facts=latched.append),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_raw_party_fully_restored", lambda r: r.restored)
    monkeypatch.setattr(s, "_origin", lambda *a: None)

    @dataclass
    class Route:
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        @property
        def route_world(self):
            return N(plan_feasible_to_map=lambda *a, **k: N(cost=20))

        def __call__(self, *args):
            raw.map_id = self.destination_map
            if fault == "hurt_arrival":
                raw.restored = False
            actions.actions_executed += 1
            em.frame_count += 16
            em.state = b"arrival"

    def chapter(*args):
        called.append(True)
        raw.map_id = int(s.MapId.SAFFRON_POKECENTER)
        raw.player_money -= 201 if fault == "wrong_cash" else 200
        raw.status_flags_1 = 0 if fault == "no_gate" else s.SAFFRON_GUARD_ACCESS_MASK
        if fault == "wrong_party":
            raw.party_species_ids = (1,)
        actions.actions_executed += 2
        em.frame_count += 32
        em.state = b"terminal"
        return N(passed=True, public_dict=lambda: {"passed": True})

    monkeypatch.setattr(s, "run_saffron_access_chapter", chapter)
    binding = s.saffron_access_binding(rt, actions, route=Route())
    assert actions.actions_executed == 0 and not called and not latched
    if fault == "unavailable":
        assert binding is None
        return
    assert binding.maximum_cash_debit == 200
    if fault:
        with pytest.raises(ValueError):
            binding.execute()
        assert not latched
        assert binding.verify(None).status is GoalDecisionOutcome.FAILED
        if fault == "hurt_arrival":
            assert not called
    else:
        report = binding.execute()
        assert report.actions_executed == 3
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert latched == [objective.completion_facts]
        with pytest.raises(ValueError, match="consumed"):
            binding.execute()
        em.state = b"different"
        assert binding.verify(report).status is GoalDecisionOutcome.FAILED
