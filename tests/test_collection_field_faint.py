"""A real shared field-faint settlement must yield, never certify collection."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_gen1_route_runtime import FakeReader, reader_as_real
from test_red_routed_recovery import make_test_raw
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_manager_runtime import GoalRecoveryRequired
from pokemon_red_completion.red_routed_recovery import (
    RedRoutedRecoveryError, guarded_collection_route_handler,
)
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


@pytest.mark.parametrize('fault', [None, 'unpoisoned', 'all_fainted', 'cash',
    'box', 'dex', 'relocation', 'unsettled', 'species', 'trainer', 'disabled',
    'unknown_script'])
def test_collection_route_uses_strict_native_field_faint_recovery(fault):
    initial = make_test_raw(map_id=232, x=25, y=20, hp=(38, 30),
                           status=(0 if fault == 'unpoisoned' else 8, 0))
    fake = FakeReader(initial, moving_direction=4)
    stock = {'box': (), 'dex': ()}
    fake.read_all_box_states = lambda: stock['box']
    fake.read_pokedex_state = lambda: stock['dex']
    actions, events = [], []
    class Emulator:
        pressed_buttons=()
        frame_count=0
        def save_state_bytes(self):return repr(fake.raw).encode()
    emulator=Emulator()

    class Port:
        @property
        def actions_executed(self):return len(actions)
        def execute(self, action):
            actions.append(action)
            emulator.frame_count += action.repeat
            if action.kind is MacroActionKind.CANCEL:
                fake.dialogue_visible = False
                fake.moving_direction = 0
                if fault == 'cash':
                    fake.raw = replace(fake.raw, player_money=999)
                elif fault in {'box', 'dex'}:
                    stock[fault] = ('unexpected',)
                elif fault == 'relocation':
                    fake.raw = replace(fake.raw, player_y=21)
                elif fault == 'unsettled':
                    fake.ready = False
            return action

        def record_diagnostic_event(self, kind, details):
            events.append((kind, details))

    handler = guarded_collection_route_handler(
        Port(), reader_as_real(fake), route_name='copied collection transport',
        maximum_scripted_dialogues=0 if fault == 'unknown_script' else 4,
        allow_field_faints=fault != 'disabled',
        emulator=emulator,
    )
    fake.raw = replace(initial, party_hp=(38 if fault == 'unknown_script' else 0,
                                        0 if fault == 'all_fainted' else 30),
                       party_status=(0, 0))
    if fault == 'species':
        fake.raw = replace(fake.raw, party_species_ids=(99, 25))
    fake.dialogue_visible = True
    fake.trainer_engagement = fault == 'trainer'
    interruption = TraversalSnapshot(232, (20, 25), False, 'scripted_dialogue')
    if fault is None:
        with pytest.raises(GoalRecoveryRequired, match='native faint recovery'):
            handler.handle(interruption)
        assert [a.kind for a in actions] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]
        assert fake.raw.party_hp == (0, 30)  # No revival and no resumed collection.
        assert fake.read_input_readiness().ready
        assert len(events) == 1
        assert events[0][0] == 'collection_native_field_faint'
        assert events[0][1]['new_fainted_slots'] == [1]
        assert events[0][1]['model_queries'] == 0
        assert events[0][1]['native_field_faint'] is True
    else:
        with pytest.raises((RouteExecutionError, RedRoutedRecoveryError)):
            handler.handle(interruption)
        assert not events
        if fault in {'unpoisoned', 'all_fainted', 'species', 'trainer', 'unknown_script'}:
            assert not actions


def test_collection_field_faint_opt_in_requires_native_emulator():
    fake = FakeReader(make_test_raw())
    with pytest.raises(ValueError, match='native emulator'):
        guarded_collection_route_handler(SimpleNamespace(), reader_as_real(fake),
            route_name='unbound field faint', allow_field_faints=True)


def test_collection_field_faint_opt_in_does_not_enable_wild_or_trainer_faints():
    fake = FakeReader(make_test_raw())
    handler = guarded_collection_route_handler(SimpleNamespace(), reader_as_real(fake),
        route_name='field faint only', allow_field_faints=True,
        emulator=SimpleNamespace(pressed_buttons=()))
    assert not handler.allow_wild_faints
    assert not handler.inner._wild.allow_party_faints
