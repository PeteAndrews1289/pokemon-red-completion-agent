"""A status move's effect is not its later condition at the ball boundary."""
from dataclasses import replace

import pytest
from test_red_capture_status_runtime import setup

import pokemon_red_completion.red_capture_status_runtime as runtime
from pokemon_red_completion.capture_support import CaptureSupportSummary
from pokemon_red_completion.observation import WildCaptureIdentity


@pytest.mark.parametrize('expires', [False, True])
def test_status_after_protective_switch_is_observed_not_inferred(monkeypatch, expires):
    world, prepare = setup(monkeypatch)

    def sleep(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.status = 3
        return result

    def switch(_actions, _reader, _emulator, index, **_kwargs):
        assert index == 1
        world.raw = replace(world.raw, active_party_index=index)
        if expires:
            world.status = 0

    monkeypatch.setattr(runtime, 'execute_bounded_battle_move_turn', sleep)
    monkeypatch.setattr(runtime, 'switch_active_battler', switch)
    assert prepare()
    assert prepare.reports[0]['status_success'] is True
    assert prepare.throw_preparations[0]['target_status'] == ('healthy' if expires else 'sleep')
    assert prepare.throw_preparations[0]['active_party_slot'] == 2
    assert prepare.throw_preparations[0]['throw_executed'] is False
    assert world.turns == 1 and world.raw.bag_items == ((4, 4),)


def test_repeated_preparations_do_not_inflate_status_attempts(monkeypatch):
    world, prepare = setup(monkeypatch)
    assert prepare() and prepare()
    assert world.turns == prepare.attempts == len(prepare.reports) == 3
    assert [row['preparation_ordinal'] for row in prepare.throw_preparations] == [1, 2]
    assert all(row['status_attempts_used'] == 3 for row in prepare.throw_preparations)
    assert all(row['target_status'] == 'healthy' for row in prepare.throw_preparations)


@pytest.mark.parametrize('after_switch', [False, True])
def test_escape_bypass_records_fresh_condition_without_an_extra_turn(monkeypatch, after_switch):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1 if after_switch else 0)
    switched = []

    def switch(_actions, _reader, _emulator, index, **_kwargs):
        switched.append(index)
        world.raw = replace(world.raw, active_party_index=index)

    monkeypatch.setattr(runtime, 'switch_active_battler', switch)
    monkeypatch.setattr(world, 'read_enemy_capture_moves',
                        lambda: (100, 0, 0, 0) if not after_switch or switched else (33, 0, 0, 0))
    assert prepare()
    assert world.turns == 0 and prepare.reports == []
    assert len(prepare.throw_preparations) == 1
    assert prepare.throw_preparations[0]['escape_setup_bypassed'] is True
    assert switched == ([0] if after_switch else [])


def test_transformed_identity_is_not_reported_as_a_new_encounter(monkeypatch):
    world, prepare = setup(monkeypatch)
    monkeypatch.setattr(world, 'read_wild_capture_identity',
                        lambda: WildCaptureIdentity(76, 108, True, (0, 0)))
    assert prepare()
    row = prepare.throw_preparations[0]
    assert (row['original_species_id'], row['displayed_species_id'], row['transformed']) == (
        76, 108, True,
    )


def test_ended_encounter_has_no_prepared_throw(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, battle_state=0)
    assert not prepare()
    assert prepare.throw_preparations == []


def test_summary_round_trip_retains_preparation_not_capture_claims():
    summary = CaptureSupportSummary(3, 1, prepared_throws=5, prepared_asleep=1,
                                    prepared_paralyzed=2, prepared_full_hp=5)
    public = summary.public_dict()
    assert CaptureSupportSummary.from_evidence({'capture_support': public}) == summary
    assert public['status_attempts'] == 3 and public['verified_status_observations'] == 1
    assert public['prepared_throws'] == 5 and 'captures' not in public
    assert 'prepared_throws' not in CaptureSupportSummary(0, 0).public_dict()


@pytest.mark.parametrize('changes', [
    {'prepared_throws': True}, {'prepared_throws': -1}, {'prepared_throws': 1001},
    {'prepared_asleep': 3}, {'prepared_paralyzed': 3}, {'prepared_full_hp': 3},
    {'prepared_asleep': 2, 'prepared_paralyzed': 1},
])
def test_summary_rejects_incoherent_counts(changes):
    with pytest.raises(ValueError):
        CaptureSupportSummary(0, 0, **{'prepared_throws': 2, **changes})


def test_preparation_fields_cannot_be_partly_dropped():
    with pytest.raises(ValueError):
        CaptureSupportSummary.from_evidence({'capture_support': {
            'status_attempts': 0, 'verified_status_observations': 0,
            'party_preparations': 0, 'prepared_asleep': 1,
        }})
