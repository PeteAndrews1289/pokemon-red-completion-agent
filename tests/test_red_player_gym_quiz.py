from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_gym_quiz as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.route_plan import RoutePlanningError


def setup(monkeypatch):
    raw = N(
        map_id=int(MapId.CINNABAR_GYM),
        player_y=17,
        player_x=16,
        event_flags=bytes(320),
        bag_items=((43, 1),),
        player_money=14409,
        badge_bits=63,
        party_hp=(143,),
        party_status=(0,),
        party_species_ids=(28,),
        party_levels=(47,),
        party_moves=((57, 58, 33, 39),),
        party_pp=((15, 10, 35, 30),),
    )
    state = N(
        payload=b"source",
        ready=True,
        legal=True,
        fault=None,
        costs={at: index * 20 for index, at in enumerate(s.QUIZ_APPROACHES, 1)},
        boxes=(),
        pc=(),
        dex=(),
        story=(),
    )
    actions, calls = N(actions_executed=0), []
    reader = N(
        read=lambda: deepcopy(raw),
        read_all_box_states=lambda: state.boxes,
        read_pc_items=lambda: state.pc,
        read_pokedex_state=lambda: state.dex,
    )
    em = N(save_state_bytes=lambda: state.payload, frame_count=0)
    rt = N(
        reader=reader,
        emulator=em,
        adapter=N(
            graph=N(available_objectives=lambda _: (N(id=s.OBJECTIVE),) if state.legal else ())
        ),
    )

    @dataclass
    class World:
        def with_current_observation(self, _):
            return self

        def plan_feasible_to_map(self, _, map_id, *, goal_at):
            assert map_id == int(MapId.CINNABAR_GYM)
            if goal_at not in state.costs:
                raise RoutePlanningError("closed observed gate")
            return N(cost=state.costs[goal_at])

    @dataclass
    class Route:
        route_world: World
        rom: bytes = b"rom"
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        def __call__(self, actions, reader, emulator):
            calls.append((self.destination_map, self.destination_at))
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            if state.fault == "approach":
                raw.player_y += 1
            actions.actions_executed += 1
            em.frame_count += 12
            state.payload = b"arrival"

    def lesson(_):
        return N(raw=deepcopy(raw), game_state=object()), dict(
            party=[dict(level=raw.party_levels, hp=raw.party_hp, pp=raw.party_pp)],
            completed_objectives=list(state.story),
        )

    monkeypatch.setattr(s, "capture_player_lesson_snapshot", lesson)
    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready)
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **kw: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **kw: object())

    def answer(actions, reader, emulator, index, value, pulses, *, correct_only):
        assert correct_only and value == s.QUIZ_CORRECT_ANSWERS[index - 1]
        assert pulses == s.QUIZ_TEXT_PULSES[index - 1]
        calls.append(("quiz", index))
        flag = int(s.GYM_GATE_EVENTS[index])
        flags = bytearray(raw.event_flags)
        if state.fault != "gate":
            flags[flag // 8] |= 1 << (flag % 8)
        if state.fault == "other_event":
            flags[0] |= 1
        raw.event_flags = bytes(flags)
        if state.fault == "cash":
            raw.player_money -= 1
        if state.fault == "bag":
            raw.bag_items = ()
        if state.fault == "hp":
            raw.party_hp = (142,)
        if state.fault == "pp":
            raw.party_pp = ((14, 10, 35, 30),)
        if state.fault == "level":
            raw.party_levels = (48,)
        if state.fault == "badge":
            raw.badge_bits = 127
        if state.fault == "boxes":
            state.boxes = (1,)
        if state.fault == "dex":
            state.dex = (1,)
        if state.fault == "pc":
            state.pc = (1,)
        if state.fault == "story":
            state.story = (s.OBJECTIVE,)
        if state.fault == "unready":
            state.ready = False
        actions.actions_executed += 1
        em.frame_count += 12
        state.payload = b"gate-open"

    monkeypatch.setattr(s, "_answer_quiz", answer)
    return rt, actions, Route(World()), raw, state, calls


@pytest.mark.parametrize("index", range(1, 7))
def test_only_reachable_closed_quiz_is_quoted_and_verified_without_story_award(monkeypatch, index):
    rt, actions, route, raw, state, calls = setup(monkeypatch)
    state.costs = {s.QUIZ_APPROACHES[index - 1]: 20}
    binding, challenge = s.cinnabar_quiz_option(rt, actions, route=route)
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0
    assert not challenge.combat_required and binding.story_objective_ref == s.OBJECTIVE
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    report = binding.execute()
    assert calls == [(int(MapId.CINNABAR_GYM), s.QUIZ_APPROACHES[index - 1]), ("quiz", index)]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert report.evidence["native_gate_opened"] and not report.evidence["objective_completed"]
    assert not report.evidence["learned_puzzle"] and report.evidence["trainer_battles"] == 0
    assert raw.badge_bits == 63 and raw.player_money == 14409
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    rt.emulator.save_state_bytes = lambda: b"changed"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_gate_offer_skips_open_panel_and_uses_actual_cost_not_chapter_order(monkeypatch):
    rt, actions, route, raw, state, _ = setup(monkeypatch)
    flags = bytearray(raw.event_flags)
    gate = int(s.GYM_GATE_EVENTS[1])
    flags[gate // 8] |= 1 << (gate % 8)
    raw.event_flags = bytes(flags)
    state.costs[s.QUIZ_APPROACHES[4]] = 1
    binding, _ = s.cinnabar_quiz_option(rt, actions, route=route)
    assert binding.execute().evidence["quiz_index"] == 5


@pytest.mark.parametrize(
    "fault",
    [
        "unready",
        "off_map",
        "completed",
        "unknown_cash",
        "unknown_bag",
        "fainted",
        "blocked",
        "all_open",
    ],
)
def test_unavailable_quiz_never_sends_input(monkeypatch, fault):
    rt, actions, route, raw, state, calls = setup(monkeypatch)
    if fault == "unready":
        state.ready = False
    if fault == "off_map":
        raw.map_id = int(MapId.CINNABAR_POKECENTER)
    if fault == "completed":
        state.legal = False
    if fault == "unknown_cash":
        raw.player_money = None
    if fault == "unknown_bag":
        raw.bag_items = None
    if fault == "fainted":
        raw.party_hp = (0,)
    if fault == "blocked":
        state.costs.clear()
    if fault == "all_open":
        raw.event_flags = bytes([255]) * 320
    assert s.cinnabar_quiz_option(rt, actions, route=route) is None
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize(
    "fault",
    [
        "approach",
        "gate",
        "other_event",
        "cash",
        "bag",
        "hp",
        "pp",
        "level",
        "badge",
        "boxes",
        "dex",
        "pc",
        "story",
        "unready",
    ],
)
def test_quiz_cannot_mask_native_failure_or_change_resources(monkeypatch, fault):
    rt, actions, route, _, state, _ = setup(monkeypatch)
    state.fault = fault
    binding, _ = s.cinnabar_quiz_option(rt, actions, route=route)
    with pytest.raises(RuntimeError, match="quiz"):
        binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED


def test_stale_quiz_refuses_before_input(monkeypatch):
    rt, actions, route, _, state, calls = setup(monkeypatch)
    binding, _ = s.cinnabar_quiz_option(rt, actions, route=route)
    state.payload = b"other-source"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls and actions.actions_executed == rt.emulator.frame_count == 0
