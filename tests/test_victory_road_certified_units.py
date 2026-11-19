"""ROM-free certification of actual caller scope; default mechanics stay unknown."""
from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest
from test_red_player_victory_road import fixture, option
from pokemon_red_completion import red_player_victory_road as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit


@pytest.mark.parametrize('phase,mode', [
    ('badge-corridor', 'movement'),
    ('teach-strength', 'interaction'),
    ('follow-dropped-boulder', 'movement'),
])
@pytest.mark.parametrize('fault', [None, 'stale', 'protected', 'terminal'])
def test_certified_callers_preserve_partial_scope_and_native_guards(monkeypatch, phase, mode, fault):
    rt, actions, route, raw, state, calls = fixture(monkeypatch)
    events = bytearray(raw.event_flags)
    events[1318 // 8] |= 1 << (1318 % 8)
    raw.event_flags = bytes(events)
    route.allow_wild_faints = False
    route.allow_field_faint_dialogue = False
    operations = []

    def perform():
        operations.append(phase)
        actions.actions_executed += 2
        rt.emulator.frame_count += 24
        state.payload = b'checked-terminal'
        if fault == 'protected':
            raw.player_money -= 1

    if phase == 'badge-corridor':
        monkeypatch.setattr(s, 'quote_badge_corridor', lambda *args: object())

        def corridor(*args, **kwargs):
            perform()
            raw.map_id = int(MapId.VICTORY_ROAD_1F) if fault != 'terminal' else int(MapId.ROUTE_22)
            raw.player_y, raw.player_x = 17, 8
            return N(map_id=raw.map_id, at=(17, 8))

        monkeypatch.setattr(s, 'traverse_badge_corridor', corridor)
    elif phase == 'teach-strength':
        raw.map_id = int(MapId.VICTORY_ROAD_1F)
        monkeypatch.setattr(s, 'strength_capabilities', lambda _: False)

        @dataclass
        class Lesson:
            party_slot: int = 1

        lesson = Lesson()
        monkeypatch.setattr(s, '_strength_lesson', lambda *args: lesson)

        def teach(*args, **kwargs):
            perform()
            if fault != 'terminal':
                raw.party_moves = ((33, 39, 58, 70), raw.party_moves[1])

        monkeypatch.setattr(s, 'execute_machine_lesson', teach)
    else:
        raw.map_id = int(MapId.VICTORY_ROAD_3F)
        monkeypatch.setattr(s, 'strength_capabilities', lambda _: True)
        monkeypatch.setattr(s, 'observed_puzzle_world', lambda world, reader: world)
        monkeypatch.setattr(s, '_route_option', lambda *args, **kwargs: None)
        monkeypatch.setattr(s, 'next_puzzle', lambda *args: ('final-switch', N(map_id=int(MapId.VICTORY_ROAD_2F))))
        monkeypatch.setattr(s, 'dropped_boulder_follow_available', lambda *args: True)

        def follow(*args):
            perform()
            raw.map_id = int(MapId.VICTORY_ROAD_2F)
            raw.player_y, raw.player_x = (16, 22 if fault != 'terminal' else 21)
            return {'map_id': raw.map_id}

        monkeypatch.setattr(s, 'follow_dropped_boulder', follow)

    binding, challenge = option(rt, actions, route)
    assert not operations and actions.actions_executed == 0 and state.payload == b'source'
    assert binding.binding_ref.startswith('pokemon.red:victory-road:' + phase + ':')
    assert binding.story_unit == OptionStoryUnit(mode, True)
    assert binding.story_approach_only is True
    assert binding.story_objective_ref == s.OBJECTIVE
    assert binding.maximum_cash_debit == 0 and not challenge.combat_required
    if fault == 'stale':
        state.payload = b'different-source'
        with pytest.raises(ValueError, match='stale'):
            binding.execute()
        assert not operations and actions.actions_executed == 0
    elif fault:
        with pytest.raises(RuntimeError, match='did not prove its terminal'):
            binding.execute()
        assert operations == [phase]
    else:
        report = binding.execute()
        assert operations == [phase] and actions.actions_executed == 2
        assert report.evidence['objective_completed'] is False
        assert report.evidence['phase'] == phase
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        with pytest.raises(ValueError, match='consumed'):
            binding.execute()
