from dataclasses import replace

import pytest

from pokemon_red_completion.observation import (
    PokemonRedStateReader,
    RawGameState,
    SemanticStateError,
    TrainerDamageObservation,
)
from pokemon_red_completion.red_battle_catalog import RedBattleCatalogError
from pokemon_red_completion.red_trainer_damage import (
    TrainerDamageError,
    incoming_damage_bounds,
    ordinary_damage_upper,
)


def damage(**changes):
    values = dict(
        level=50, power=100, attack=100, defense=100, critical=False, stab=False, effectiveness=1.0
    )
    return ordinary_damage_upper(**(values | changes))


def test_hand_calculated_ordinary_critical_stab_and_immunity():
    assert damage() == 46
    assert damage(critical=True) == 86
    assert damage(critical=True, stab=True, effectiveness=2.0) == 258
    assert damage(effectiveness=0.0) == 0
    assert damage(stab=True, effectiveness=0.25) == 18  # conservative ceil


def test_scaling_and_cap_match_integer_cartridge_rules():
    assert damage(attack=257, defense=101) == 114
    assert damage(level=100, power=250, attack=1023, defense=4) == 999
    with pytest.raises(TrainerDamageError, match="divisor"):
        damage(attack=300, defense=3)


@pytest.mark.parametrize(
    "change",
    [
        {"attack": 0},
        {"attack": 1024},
        {"level": 101},
        {"defense": True},
        {"critical": 1},
        {"effectiveness": 3.0},
    ],
)
def test_unknown_arithmetic_never_becomes_safe(change):
    with pytest.raises(TrainerDamageError):
        damage(**change)


def observation(moves=(33, 0, 0, 0)):
    raw = RawGameState(
        game_started=True,
        map_id=1,
        player_x=0,
        player_y=0,
        party_count=2,
        battle_state=2,
        party_max_hp=(200, 160),
        party_status=(0, 0),
        enemy_level=50,
    )
    return TrainerDamageObservation(
        raw,
        moves,
        ("ice", "psychic"),
        100,
        100,
        100,
        100,
        ((100, 100, 100, 100), (200, 50, 200, 50)),
        (("normal",), ("water",)),
    )


def test_separate_physical_special_and_unmodified_critical_stats():
    physical = incoming_damage_bounds(observation((34, 0, 0, 0)))
    assert physical == (86, 47)
    lowered = replace(observation((34, 0, 0, 0)), enemy_attack=10)
    assert incoming_damage_bounds(lowered) == physical  # critical ignores lowered attack
    assert incoming_damage_bounds(observation((8, 0, 0, 0))) == (111, 106)


def test_noncritical_projection_is_explicit_and_keeps_boosted_ordinary_maximum():
    plain = observation((63, 0, 0, 0))
    assert incoming_damage_bounds(plain) == (128, 65)
    assert incoming_damage_bounds(plain, include_critical=False) == (68, 35)
    boosted = replace(plain, enemy_attack=400)
    assert incoming_damage_bounds(boosted) == incoming_damage_bounds(
        boosted, include_critical=False,
    )
    assert incoming_damage_bounds(boosted)[0] > 128
    with pytest.raises(TrainerDamageError, match='explicit boolean'):
        incoming_damage_bounds(plain, include_critical=1)


def test_all_five_multi_hits_count_and_existing_burn_adds_residual():
    assert incoming_damage_bounds(observation((3, 0, 0, 0))) == (70, 40)
    base = observation((3, 0, 0, 0))
    assert incoming_damage_bounds(replace(base, raw=replace(base.raw, party_status=(16, 0)))) == (
        83,
        40,
    )


@pytest.mark.parametrize("move", [69, 101, 149, 90, 68, 120, 35, 117, 118, 119, 144])
def test_unsupported_damage_and_confusion_abstain(move):
    with pytest.raises((TrainerDamageError, RedBattleCatalogError)):
        incoming_damage_bounds(observation((move, 0, 0, 0)))


@pytest.mark.parametrize('move,bound', [(49, 20), (82, 40)])
def test_constant_damage_uses_hp_not_stab_critical_defense_or_type(move, bound):
    current = replace(observation((move, 0, 0, 0)),
                      enemy_attack=900, enemy_special=900,
                      enemy_base_attack=999, enemy_base_special=999,
                      party_types=(('ghost',), ('dragon',)))
    assert incoming_damage_bounds(current) == (bound, bound)
    poisoned = replace(current, raw=replace(current.raw, party_status=(8, 16)))
    assert incoming_damage_bounds(poisoned) == (bound + 13, bound + 10)


@pytest.mark.parametrize('move', [14, 96, 97, 104, 106, 107, 110, 111, 112, 133, 151])
def test_pure_boost_is_zero_immediate_damage_but_existing_residual_remains(move):
    current = observation((move, 0, 0, 0))
    assert incoming_damage_bounds(current) == (0, 0)
    poisoned = replace(current, raw=replace(current.raw, party_status=(8, 0)))
    assert incoming_damage_bounds(poisoned) == (13, 0)


def test_fixed_boost_and_ordinary_inventory_takes_worst_not_sum_or_first_move():
    assert incoming_damage_bounds(observation((97, 82, 33, 0))) == (40, 40)
    assert incoming_damage_bounds(observation((97, 82, 34, 0))) == (86, 47)


class Memory:
    def __init__(self):
        self.values = {
            0xCD23: 50,
            0xCFEA: 25,
            0xCFEB: 24,
            0xD170: 0,
            0xD171: 0,
            0xD19C: 21,
            0xD19D: 21,
        }
        for address, value in {
            0xCFF6: 71,
            0xCFFC: 120,
            0xCD26: 73,
            0xCD2C: 122,
            0xD191: 173,
            0xD195: 167,
            0xD1BD: 80,
            0xD1C1: 89,
            0xD027: 99,
            0xD025: 137,
            0xD02B: 88,
        }.items():
            self.values[address], self.values[address + 1] = divmod(value, 256)

    def read_u8(self, address):
        return self.values.get(address, 0)


def reader(monkeypatch):
    memory = Memory()
    subject = PokemonRedStateReader(memory)
    raw = replace(observation().raw, active_party_index=0)
    monkeypatch.setattr(subject, "read_trainer_entry_moves", lambda _: (33, 0, 0, 0))
    return subject, memory, raw


def test_literal_memory_offsets_distinguish_live_base_stats_and_party_stride(monkeypatch):
    subject, _, raw = reader(monkeypatch)
    result = subject.read_trainer_damage_observation(raw)
    assert (
        result.enemy_attack,
        result.enemy_special,
        result.enemy_base_attack,
        result.enemy_base_special,
    ) == (71, 120, 73, 122)
    assert result.defenses == ((99, 88, 173, 167), (80, 89, 80, 89))
    assert result.party_types == (("normal",), ("water",))
    assert result.enemy_types == ("ice", "psychic")
    assert result.active_self_hit_stats == (137, 99)
    assert result.player_confused is False


def confused_observation(moves=(109, 0, 0, 0), **changes):
    base = observation(moves)
    return replace(
        base,
        raw=replace(base.raw, active_party_index=0, party_levels=(50, 40)),
        active_self_hit_stats=(100, 100),
        **changes,
    )


def test_confusion_adds_typeless_noncritical_self_hit_only_to_active():
    # floor(22*40*100/100/50)+2 =19, not38 critical and noSTAB/type.
    assert incoming_damage_bounds(confused_observation()) == (19, 0)
    assert incoming_damage_bounds(confused_observation((34, 109, 0, 0))) == (105, 47)
    # Confusion has50power: critical44*1.5=66, plus19 self-hit.
    assert incoming_damage_bounds(confused_observation((93, 0, 0, 0))) == (85, 129)
    # Already-confused remains risky even if the new opponent cannot induce it.
    assert incoming_damage_bounds(confused_observation((34, 0, 0, 0), player_confused=True)) == (
        105,
        47,
    )


def test_confusion_uses_live_self_stats_and_rejects_unknown_or_overflowed_stats():
    base = confused_observation()
    assert incoming_damage_bounds(replace(base, active_self_hit_stats=(200, 100))) == (37, 0)
    assert incoming_damage_bounds(replace(base, active_self_hit_stats=(100, 200))) == (10, 0)
    for stats in (None, (0, 100), (100, 1024), (300, 3)):
        with pytest.raises(TrainerDamageError):
            incoming_damage_bounds(replace(base, active_self_hit_stats=stats))


def test_confusion_observation_requires_active_level():
    with pytest.raises(TrainerDamageError, match="active stats"):
        incoming_damage_bounds(observation((109, 0, 0, 0)))


def test_confusion_and_enemy_reflect_are_observed_not_treated_as_a_cure(monkeypatch):
    subject, memory, raw = reader(monkeypatch)
    memory.values[0xD062] = 0x80
    memory.values[0xD069] = 0x04
    result = subject.read_trainer_damage_observation(raw)
    assert result.player_confused is True
    assert result.active_self_hit_stats == (137, 198)
    memory.values[0xD062] = 0x81
    with pytest.raises(SemanticStateError, match="volatile"):
        subject.read_trainer_damage_observation(raw)


def test_changed_confusion_flag_during_read_rejects_stale_bound(monkeypatch):
    subject, memory, raw = reader(monkeypatch)
    calls = 0

    def moves(_):
        nonlocal calls
        calls += 1
        if calls == 2:
            memory.values[0xD062] = 0x80
        return (109, 0, 0, 0)

    monkeypatch.setattr(subject, "read_trainer_entry_moves", moves)
    with pytest.raises(SemanticStateError, match="changed"):
        subject.read_trainer_damage_observation(raw)


@pytest.mark.parametrize(
    "address,value",
    [(0xD062, 1), (0xD063, 128), (0xD064, 1), (0xD064, 8), (0xD069, 8), (0xCD23, 49), (0xCFEA, 6)],
)
def test_unsupported_live_flags_types_and_level_refuse(monkeypatch, address, value):
    subject, memory, raw = reader(monkeypatch)
    memory.values[address] = value
    with pytest.raises(SemanticStateError):
        subject.read_trainer_damage_observation(raw)


def test_real_main_boundary_is_still_required(monkeypatch):
    subject, _, raw = reader(monkeypatch)
    monkeypatch.setattr(subject, "read_trainer_entry_moves", lambda _: None)
    with pytest.raises(SemanticStateError, match="MAIN"):
        subject.read_trainer_damage_observation(raw)
