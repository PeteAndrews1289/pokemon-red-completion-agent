from collections import defaultdict

import pytest

from pokemon_red_completion.observation import EventFlag, MapId, RamAddress
from pokemon_red_completion.red_gift_training_setup import (
    add_isolated_gift_history,
    prepare_isolated_gift,
)
from pokemon_red_completion.red_safari_training_setup import RED_ROM_SHA256


def memory():
    m = defaultdict(int)
    m.update({RamAddress.CURRENT_MAP: MapId.OAKS_LAB, RamAddress.OAKS_LAB_SCRIPT: 10,
              RamAddress.PARTY_COUNT: 1, RamAddress.PARTY_SPECIES: 177,
              0xD3AE: 2, 0xD365: MapId.PALLET_TOWN})
    m.update({0xD3AF+i: b for i, b in enumerate((11, 4, 2, 255, 11, 5, 2, 255))})
    for base, stride in ((0xD16B, 44), (0xD273, 11), (0xD2B5, 11)):
        m.update({base+i: i+1 for i in range(stride)})
    return m


def run(m, **kw):
    args = dict(rom_sha256=RED_ROM_SHA256, isolated_training_setup=True,
                controller_released=True, battle_state=0)
    args.update(kw)
    return prepare_isolated_gift(m, **args)


@pytest.mark.parametrize("full", [False, True])
def test_setup_exact_receipt_preserves_origin_and_excludes_gift_flag(full):
    m = memory()
    before = dict(m)
    receipt = run(m, full_party=full)
    assert m[RamAddress.CURRENT_MAP] == MapId.OAKS_LAB
    assert m[RamAddress.PARTY_COUNT] == (6 if full else 1)
    assert m[0xD3B1] == 4 and m[0xD3B2] == MapId.SILPH_CO_7F
    assert not m[RamAddress.STATUS_FLAGS_4] & 1
    for flag in (EventFlag.BEAT_SILPH_CO_GIOVANNI, EventFlag.BEAT_SILPH_CO_RIVAL):
        assert m[int(RamAddress.EVENT_FLAGS)+int(flag)//8] & 1 << (int(flag)%8)
    for r in receipt:
        assert r["before"] == before.get(r["address"], 0)
        assert r["after"] == m[r["address"]]
    assert all(m[a] == v for a, v in before.items()
               if a not in {r["address"] for r in receipt})
    if full:
        for base, stride in ((0xD16B, 44), (0xD273, 11), (0xD2B5, 11)):
            for slot in range(1, 6):
                assert [m[base+slot*stride+i] for i in range(stride)] == list(range(1,stride+1))


@pytest.mark.parametrize("kw", [dict(rom_sha256="wrong"), dict(isolated_training_setup=False),
    dict(controller_released=False), dict(battle_state=1), dict(battle_state=False),
    dict(full_party=1), dict(approach_fixture=1)])
def test_preflight_never_writes(kw):
    m = memory()
    before = dict(m)
    with pytest.raises(ValueError):
        run(m, **kw)
    assert all(m[a] == v for a, v in before.items())


@pytest.mark.parametrize("address", [RamAddress.CURRENT_MAP, RamAddress.OAKS_LAB_SCRIPT,
    RamAddress.PARTY_COUNT, 0xD3AE, 0xD365, 0xD3AF])
def test_changed_origin_fails_before_any_write(address):
    m = memory()
    m[address] += 1
    before = dict(m)
    with pytest.raises(ValueError):
        run(m)
    assert all(m[a] == v for a, v in before.items())


def test_approach_fixture_has_declared_native_door_and_entrance_prerequisites():
    m = memory()
    run(m, approach_fixture=True)
    assert m[0xD3B1] == 0 and m[0xD3B2] == MapId.SILPH_CO_1F
    for f in (EventFlag.RESCUED_MR_FUJI, EventFlag.RESCUED_MR_FUJI_WORLD,
              EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2, EventFlag.BEAT_SILPH_CO_3F_TRAINER_0,
              0x703):
        assert m[int(RamAddress.EVENT_FLAGS)+int(f)//8] & 1 << (int(f)%8)
    # Closed irrelevant door remains closed; this is not an all-doors-open fixture.
    assert not m[int(RamAddress.EVENT_FLAGS)+0x708//8] & 1 << (0x708%8)


@pytest.mark.parametrize("initial", [0, 255, 0x55, 0xAA])
def test_approach_matches_native_liberation_visibility_without_hiding_items(initial):
    m = memory()
    base = int(RamAddress.TOGGLEABLE_OBJECT_FLAGS)
    m.update({base+i: initial for i in range(32)})
    run(m, approach_fixture=True)
    # Independent transcription of the pinned native script, not imported constants.
    hidden = set(range(10, 17)) | {23, 24, 138, 139, 140, 141, 142, 143,
        145, 146, 147, 151, 152, 153, 154, 158, 159, 160, 163, 164, 165, 166,
        171, 172, 173, 174, 175, 176, 177, 178, 183, 184, 185}
    shown = set(range(17, 23))
    for index in range(256):
        expected = True if index in hidden else False if index in shown else bool(
            initial & (1 << (index % 8)))
        assert bool(m[base+index//8] & (1 << (index%8))) == expected


def test_near_gift_fixture_does_not_modify_city_visibility():
    m = memory()
    base = int(RamAddress.TOGGLEABLE_OBJECT_FLAGS)
    m.update({base+i: 0xA5 for i in range(32)})
    run(m)
    assert all(m[base+i] == 0xA5 for i in range(32))


@pytest.mark.parametrize('species', [(131,), (0,), (152,), (1, 1), (True,)])
def test_history_cannot_create_gift_or_invalid_identity(species):
    m = memory()
    m[RamAddress.CURRENT_MAP] = MapId.SILPH_CO_1F
    before = dict(m)
    with pytest.raises(ValueError):
        add_isolated_gift_history(m, rom_sha256=RED_ROM_SHA256, isolated_training_setup=True,
            controller_released=True, battle_state=0, registered_species=species)
    assert all(m[a] == v for a, v in before.items())


def test_history_only_adds_declared_flags_never_cash_or_party():
    m = memory()
    m[RamAddress.CURRENT_MAP] = MapId.SILPH_CO_1F
    m[RamAddress.POKEDEX_OWNED] = 2
    before = dict(m)
    receipt = add_isolated_gift_history(m, rom_sha256=RED_ROM_SHA256,
        isolated_training_setup=True, controller_released=True, battle_state=0,
        registered_species=(1, 7))
    assert m[RamAddress.POKEDEX_OWNED] == 67
    assert m[RamAddress.POKEDEX_SEEN] == 65
    assert all(m[a] == v for a, v in before.items()
               if a not in {r['address'] for r in receipt})
