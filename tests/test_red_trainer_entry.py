"""Incoming coverage is independent of opponent identity and offensive ranking."""
from dataclasses import replace

import pytest

from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    PokemonRedStateReader,
    RawGameState,
    SemanticStateError,
)
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_battle_catalog import RedBattleCatalogError
from pokemon_red_completion.red_trainer_party import (
    RedTrainerPartyError,
    trainer_entry_candidates,
    trainer_matchup_candidates,
)


def team():
    return PartyObservation((
        PartyMemberObservation(1, 118, 55, 118, 118, moves=(MoveObservation(89, 10),)),
        PartyMemberObservation(2, 28, 60, 200, 200, moves=(MoveObservation(57, 10),)),
        PartyMemberObservation(3, 64, 55, 139, 139, moves=(MoveObservation(163, 20),)),
    ))


def screened(moves, party=None):
    party = party or team()
    candidates = trainer_matchup_candidates(party, opponent_species=72, opponent_level=56)
    return trainer_entry_candidates(party, candidates, incoming_moves=moves)


def test_ice_coverage_rejects_ground_and_flying_but_not_water():
    assert [c.party_slot for c in screened((8, 34, 142, 3))] == [2]
    assert {c.party_slot for c in screened((33, 0, 0, 0))} == {1, 2, 3}


def test_screen_tracks_types_after_party_permutation():
    party = PartyObservation(tuple(
        replace(member, slot=i+1) for i, member in enumerate(reversed(team().members))
    ))
    assert [party.members[c.party_slot-1].species_id for c in screened((8, 0, 0, 0), party)] == [28]


def test_electric_attack_immunity_differs_from_ice_weakness():
    assert [c.party_slot for c in screened((85, 0, 0, 0))] == [1]


def test_status_only_inventory_is_not_fabricated_damage():
    assert len(screened((142, 28, 0, 0))) == 3


@pytest.mark.parametrize("move", [69, 149, 90, 68, 120, 153, 35, 117, 118, 119, 144])
def test_unsupported_effect_is_unknown_not_zero_damage(move):
    with pytest.raises(RedBattleCatalogError, match="entry type screen"):
        screened((move, 0, 0, 0))


@pytest.mark.parametrize("moves", [(0, 0, 0, 0), (8,), (8, 0, 0, 166), (True, 0, 0, 0)])
def test_invalid_inventory_refuses(moves):
    with pytest.raises(RedTrainerPartyError, match="inventory"):
        screened(moves)


@pytest.mark.parametrize("move,level,bound", [(49, None, 20), (82, None, 40), (101, 55, 55)])
def test_fixed_damage_entry_requires_strictly_positive_remaining_hp(move, level, bound):
    party = PartyObservation(tuple(replace(member, hp=bound, max_hp=bound * 2)
                                   for member in team().members))
    candidates = trainer_matchup_candidates(party, opponent_species=72, opponent_level=56)
    assert len(candidates) == 3  # Half-HP eligibility must not mask the entry boundary.
    assert trainer_entry_candidates(party, candidates, incoming_moves=(move, 0, 0, 0),
                                    enemy_level=level) == ()
    healthy = PartyObservation(tuple(replace(member, hp=bound + 1) for member in party.members))
    allowed = trainer_entry_candidates(healthy, candidates, incoming_moves=(move, 0, 0, 0),
                                       enemy_level=level)
    assert allowed == candidates  # Preserve ranking, not just number accepted.


def test_level_damage_uses_enemy_level_not_reserve_level_and_tracks_permutations():
    party = PartyObservation(tuple(replace(member, hp=56, max_hp=100)
                                   for member in team().members))
    for current in (party, PartyObservation(tuple(replace(member, slot=i + 1)
                    for i, member in enumerate(reversed(party.members))))):
        candidates = trainer_matchup_candidates(current, opponent_species=72, opponent_level=56)
        assert len(candidates) == 3
        # The level60 reserve still survives a level55 Night Shade at56HP.
        assert trainer_entry_candidates(current, candidates, incoming_moves=(101, 0, 0, 0),
                                        enemy_level=55) == candidates
        assert trainer_entry_candidates(current, candidates, incoming_moves=(101, 0, 0, 0),
                                        enemy_level=56) == ()


def test_fixed_damage_does_not_hide_other_coverage_or_unsupported_slots():
    candidates = trainer_matchup_candidates(team(), opponent_species=72, opponent_level=56)
    assert [c.party_slot for c in trainer_entry_candidates(
        team(), candidates, incoming_moves=(82, 85, 101, 0), enemy_level=55,
    )] == [1]  # Ground survives; water and flying remain weak to Thunderbolt.
    for moves in ((101, 149, 0, 0), (82, 0, 0, 90), (68, 49, 0, 0)):
        with pytest.raises(RedBattleCatalogError, match="entry type screen"):
            trainer_entry_candidates(team(), candidates, incoming_moves=moves, enemy_level=55)


def test_entry_screen_does_not_guess_missing_night_shade_level():
    with pytest.raises(RedBattleCatalogError, match="observed enemy level"):
        screened((101, 0, 0, 0))


class Memory:
    def __init__(self):
        # Literal pinned battle_struct addresses; deliberately nonuniform data.
        self.values = {0xCFED: 8, 0xCFEE: 34, 0xCFEF: 142, 0xCFF0: 3}
        self.reads = []

    def read_u8(self, address):
        self.reads.append(address)
        return self.values[address]


def observer(monkeypatch):
    memory = Memory()
    reader = PokemonRedStateReader(memory)
    raw = RawGameState(game_started=True, map_id=245, player_x=5, player_y=3,
                       battle_state=2, party_count=6, enemy_species_id=72, enemy_hp=147)
    monkeypatch.setattr(reader, "read", lambda: raw)
    monkeypatch.setattr(reader, "read_battle_menu_state",
                        lambda _: BattleMenuState(BattleMenuPhase.MAIN))
    return reader, memory, raw


def test_adapter_reads_each_real_move_slot_without_inputs(monkeypatch):
    reader, memory, raw = observer(monkeypatch)
    assert reader.read_trainer_entry_moves(raw) == (8, 34, 142, 3)
    assert memory.reads == [0xCFED, 0xCFEE, 0xCFEF, 0xCFF0]


@pytest.mark.parametrize("change", [{"battle_state": 0}, {"battle_state": 1}, {"enemy_hp": 0}])
def test_stale_or_nontrainer_state_cannot_read_move_bytes(monkeypatch, change):
    reader, memory, raw = observer(monkeypatch)
    raw = replace(raw, **change)
    monkeypatch.setattr(reader, "read", lambda: raw)
    assert reader.read_trainer_entry_moves(raw) is None
    assert not memory.reads


def test_expected_state_mismatch_does_not_read_moves(monkeypatch):
    reader, memory, raw = observer(monkeypatch)
    assert reader.read_trainer_entry_moves(replace(raw, enemy_hp=146)) is None
    assert not memory.reads


def test_non_main_menu_is_not_a_switch_boundary(monkeypatch):
    reader, memory, raw = observer(monkeypatch)
    monkeypatch.setattr(reader, "read_battle_menu_state",
                        lambda _: BattleMenuState(BattleMenuPhase.MOVE))
    assert reader.read_trainer_entry_moves(raw) is None
    assert not memory.reads


def test_changed_enemy_during_read_rejects_inventory(monkeypatch):
    reader, _memory, raw = observer(monkeypatch)
    reads = iter((raw, replace(raw, enemy_species_id=19)))
    monkeypatch.setattr(reader, "read", lambda: next(reads))
    with pytest.raises(SemanticStateError, match="changed"):
        reader.read_trainer_entry_moves(raw)


def test_corrupt_move_byte_refuses(monkeypatch):
    reader, memory, raw = observer(monkeypatch)
    memory.values[0xCFF0] = 255
    with pytest.raises(SemanticStateError, match="inventory"):
        reader.read_trainer_entry_moves(raw)
