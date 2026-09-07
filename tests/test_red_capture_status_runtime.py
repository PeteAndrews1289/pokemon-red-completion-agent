"""Independent state transitions distinguish attempt, effect and safe exit."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_capture_status_runtime as runtime
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, PartyObservation


class World:
    def __init__(self):
        self.raw = RawGameState(
            True, 35, 5, 30, 2, 1, enemy_species_id=108, enemy_hp=25,
            active_party_index=0, active_party_hp=50, active_party_max_hp=50,
            party_species_ids=(48, 28), bag_items=((4, 4),),
        )
        self.party = PartyObservation((
            PartyMemberObservation(1, 48, 13, 50, 50, moves=(MoveObservation(95, 10),)),
            PartyMemberObservation(2, 28, 63, 200, 200, moves=(MoveObservation(57, 10),)),
        ))
        self.status = 0
        self.turns = 0
        self.boundaries = 0

    def read(self):
        return self.raw

    def read_enemy_capture_status(self):
        return self.status

    def read_enemy_capture_moves(self):
        return (33, 45, 0, 0)

    def turn(self, *_args, **kwargs):
        assert kwargs['selected_slot'] == 1
        assert kwargs['expected_battle_state'] == 1
        self.turns += 1
        first = self.party.members[0]
        self.party = replace(self.party, members=(
            replace(first, moves=(replace(first.moves[0], current_pp=10-self.turns),)),
            self.party.members[1],
        ))
        return SimpleNamespace(move_executed=True)


def setup(monkeypatch):
    world = World()
    monkeypatch.setattr(runtime, 'PokemonRedPartyReader',
                        lambda _: SimpleNamespace(read=lambda: world.party))
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', world.turn)
    def boundary(*_args, **_kwargs):
        world.boundaries += 1
    monkeypatch.setattr(runtime, 'advance_battle_to_policy_boundary', boundary)
    def switch(_actions, _reader, _emulator, index, **_kwargs):
        world.raw = replace(world.raw, active_party_index=index)
    monkeypatch.setattr(runtime, 'switch_active_battler', switch)
    return world, runtime.RedCaptureStatusPreparer(object(), object(), world)


@pytest.mark.parametrize('escape_move', [18, 46, 100])
@pytest.mark.parametrize('species', [108, 148, 6])
def test_escape_effect_bypasses_setup_without_species_allowlist(monkeypatch, escape_move, species):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1, enemy_species_id=species)
    monkeypatch.setattr(world, 'read_enemy_capture_moves', lambda: (33, escape_move, 0, 0))
    def forbidden(*_args, **_kwargs):
        pytest.fail('escape target must get a ball before setup/switch input')
    monkeypatch.setattr(runtime, 'switch_active_battler', forbidden)
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', forbidden)
    assert prepare() is True
    assert prepare.bypassed_for_escape and prepare.attempts == 0
    assert world.turns == 0 and prepare.reports == []
    assert world.raw.active_party_index == 1 and world.raw.bag_items == ((4, 4),)


def test_missing_opponent_moves_do_not_imply_safe_status_setup(monkeypatch):
    world, prepare = setup(monkeypatch)
    monkeypatch.setattr(world, 'read_enemy_capture_moves', lambda: None)
    with pytest.raises(runtime.RedCaptureStatusError, match='moves are unavailable'):
        prepare()
    assert world.turns == 0 and not prepare.bypassed_for_escape


def test_status_misses_are_bounded_across_balls_not_relabelled_as_success(monkeypatch):
    world, prepare = setup(monkeypatch)
    assert prepare()
    assert world.turns == 3 and prepare.attempts == 3
    assert not prepare.bypassed_for_escape
    assert [row['status_success'] for row in prepare.reports] == [False]*3
    assert all(row['target_hp_before'] == row['target_hp_after'] == 25
               for row in prepare.reports)
    assert prepare()
    assert world.turns == 3


def test_only_observed_sleep_stops_after_one_attempt(monkeypatch):
    world, prepare = setup(monkeypatch)
    def sleep(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.status = 3
        return result
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', sleep)
    assert prepare()
    assert world.turns == 1 and world.boundaries == 2
    assert prepare.reports[0]['status_success'] is True
    assert prepare.reports[0]['condition'] == 'sleep'
    assert prepare()
    assert world.turns == 1


@pytest.mark.parametrize('change', [
    {'enemy_hp': 24}, {'enemy_species_id': 185},
    {'party_species_ids': (48,)}, {'bag_items': ((4, 3),)},
])
def test_status_preparation_rejects_target_damage_and_inventory_drift(monkeypatch, change):
    world, prepare = setup(monkeypatch)
    def drift(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, **change)
        return result
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', drift)
    with pytest.raises(runtime.RedCaptureStatusError, match='target, party or bag'):
        prepare()


def test_pp_proof_is_not_optional(monkeypatch):
    _, prepare = setup(monkeypatch)
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn',
                        lambda *_args, **_kwargs: SimpleNamespace(move_executed=True))
    with pytest.raises(runtime.RedCaptureStatusError, match='PP differs'):
        prepare()


def test_wild_teleport_exit_is_not_status_success(monkeypatch):
    world, prepare = setup(monkeypatch)
    def flee(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, battle_state=0)
        return result
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', flee)
    assert prepare() is False
    assert prepare.reports == [{'attempt': 1, 'encounter_ended': True, 'status_success': False}]


def test_helper_switch_is_verified_before_owned_move(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1)
    switches = []
    def switch(_actions, _reader, _emulator, index, **_kwargs):
        switches.append(index)
        world.raw = replace(world.raw, active_party_index=index)
    monkeypatch.setattr(runtime, 'switch_active_battler', switch)
    assert prepare()
    assert switches == [0, 1] and world.turns == 3


def test_absent_helper_does_not_choose_damaging_replacement(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.party = replace(world.party, members=(
        replace(world.party.members[0], moves=(MoveObservation(1, 20),)),
        world.party.members[1],
    ))
    assert prepare()
    assert world.turns == 0 and prepare.reports == []


def test_fainting_aborts_before_another_status_attempt(monkeypatch):
    world, prepare = setup(monkeypatch)
    def faint(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, active_party_hp=0)
        return result
    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', faint)
    with pytest.raises(runtime.RedCaptureStatusError, match='fainted'):
        prepare()
    assert world.turns == 1
