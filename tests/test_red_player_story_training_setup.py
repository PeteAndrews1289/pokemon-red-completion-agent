from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_player_income_setup import inputs

import pokemon_red_completion.red_player_story_training_setup as setup
from pokemon_red_completion.observation import Badge, MapId, RamAddress


@pytest.mark.parametrize("fault", [None, "partition", "earned"])
def test_bill_setup_never_supplies_bill_progress(monkeypatch, fault):
    from pokemon_red_completion.observation import EventFlag

    memory, args = inputs(monkeypatch)
    for key in ("money", "balls", "forest_warp", "level"):
        args.pop(key)
    flag = int(EventFlag.GOT_SS_TICKET)
    address = int(RamAddress.EVENT_FLAGS) + flag // 8
    if fault == "partition":
        args["partition"] = "development"
    if fault == "earned":
        memory[address] |= 1 << (flag % 8)
    before = bytes(memory)
    if fault:
        with pytest.raises(ValueError):
            setup.prepare_bill_training_fixture(memory, **args)
        assert bytes(memory) == before
    else:
        rows = setup.prepare_bill_training_fixture(memory, **args)
        assert rows and memory[0xD3B2] == memory[0xD3B6] == MapId.BILLS_HOUSE
        assert memory[RamAddress.CURRENT_MAP] == MapId.OAKS_LAB
        assert memory[address] == before[address] == 0
        assert all(memory[r["address"]] == r["after"] for r in rows)


def fixture(monkeypatch):
    memory, args = inputs(monkeypatch)
    cartridge = setup.RedPracticeCartridge(args["rom"])
    monkeypatch.setattr(
        setup,
        "RedPracticeCartridge",
        lambda _: N(species=lambda i: replace(cartridge.species(i), national_number=8)),
    )
    monkeypatch.setattr(
        setup,
        "trainer_headers",
        lambda *a, **k: (N(sprite_index=2, event_flag=186), N(sprite_index=3, event_flag=187)),
    )
    for key in ("money", "balls", "forest_warp"):
        args.pop(key)
    args["hp_percent"] = 50
    return memory, args


def test_fixture_is_disclosed_atomic_and_preserves_native_reward(monkeypatch):
    memory, args = fixture(monkeypatch)
    before = bytes(memory)
    rows = setup.prepare_misty_training_fixture(memory, **args)
    touched = {r["address"] for r in rows}
    assert all(memory[i] == v for i, v in enumerate(before) if i not in touched)
    assert all(
        before[r["address"]] == r["before"] and memory[r["address"]] == r["after"] for r in rows
    )
    base = int(RamAddress.PARTY_MON_1)
    assert memory[base] == memory[RamAddress.PARTY_SPECIES] == 179
    assert memory[base + 12 : base + 14] == before[base + 12 : base + 14]
    assert memory[base + 27 : base + 29] == before[base + 27 : base + 29]
    assert memory[RamAddress.CURRENT_MAP] == MapId.OAKS_LAB
    assert memory[RamAddress.OBTAINED_BADGES] == Badge.BOULDER
    assert memory[0xD3B2] == memory[0xD3B6] == MapId.CERULEAN_GYM
    assert not memory[int(RamAddress.EVENT_FLAGS) + 191 // 8] & ((1 << 7) | (1 << 6))
    hp = int.from_bytes(memory[base + 1 : base + 3], "big")
    maximum = int.from_bytes(memory[base + 34 : base + 36], "big")
    assert hp == maximum // 2


@pytest.mark.parametrize("mutation", ["partition", "level", "health", "headers", "earned"])
def test_bad_fixture_never_partially_writes(monkeypatch, mutation):
    memory, args = fixture(monkeypatch)
    if mutation == "partition":
        args["partition"] = "development"
    elif mutation == "level":
        args["level"] = 31
    elif mutation == "health":
        args["hp_percent"] = True
    elif mutation == "headers":
        monkeypatch.setattr(setup, "trainer_headers", lambda *a, **k: ())
    else:
        memory[int(RamAddress.EVENT_FLAGS) + 191 // 8] = 1 << 7
    before = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_misty_training_fixture(memory, **args)
    assert bytes(memory) == before


def party_fixture(monkeypatch):
    memory, args = inputs(monkeypatch)
    cartridge = setup.RedPracticeCartridge(args["rom"])
    dex = {179: 8, 166: 20, 165: 19, 150: 17, 36: 16, 113: 14, 112: 13}
    moves = {179: (33, 39, 145, 55), 165: (33, 39, 98, 158), 36: (16, 28, 98), 112: (40, 81)}

    def species(i):
        return replace(
            cartridge.species(i), national_number=dex[i], starting_moves=moves.get(i, (33,))
        )

    monkeypatch.setattr(setup, "RedPracticeCartridge", lambda _: N(species=species))
    monkeypatch.setattr(setup, "RED_ROM_SHA256", args["rom_sha256"])
    for key in ("money", "balls", "forest_warp", "level"):
        args.pop(key)
    args["condition"] = "healthy-prepared"
    base = int(RamAddress.PARTY_MON_1)
    memory[RamAddress.CURRENT_MAP] = MapId.CERULEAN_GYM
    memory[base] = memory[RamAddress.PARTY_SPECIES] = 179
    memory[int(RamAddress.PARTY_SPECIES) + 1] = 255
    memory[base + 33] = 14
    memory[base + 12 : base + 14] = b"\x12\x34"
    return memory, args, species


@pytest.mark.parametrize(
    "condition",
    [
        "injured-prepared",
        "healthy-prepared",
        "healthy-less-prepared",
        "healthy-rattata19",
        "healthy-rattata18-progressed",
        "healthy-wartortle19",
    ],
)
def test_four_party_fixture_preserves_ownership_and_consistent_stats(monkeypatch, condition):
    memory, args, species = party_fixture(monkeypatch)
    args["condition"] = condition
    before = bytes(memory)
    rows = setup.prepare_misty_party_training_fixture(memory, **args)
    touched = {r["address"] for r in rows}
    assert all(memory[i] == v for i, v in enumerate(before) if i not in touched)
    assert all(
        before[r["address"]] == r["before"] and memory[r["address"]] == r["after"] for r in rows
    )
    assert memory[RamAddress.PARTY_COUNT] == 4
    assert memory[int(RamAddress.PARTY_SPECIES) + 4] == 255
    ids = (179, 165, 36, 113) if condition == "healthy-less-prepared" else (179, 166, 150, 113)
    levels = (17, 17, 17, 7) if condition == "healthy-less-prepared" else (17, 20, 18, 7)
    if condition == "healthy-rattata19":
        ids, levels = (179, 165, 150, 113), (17, 19, 18, 7)
    elif condition == "healthy-rattata18-progressed":
        ids, levels = (179, 165, 150, 113), (17, 18, 18, 7)
    elif condition == "healthy-wartortle19":
        levels = (19, 20, 18, 7)
    fingerprints = []
    for i, (code, level) in enumerate(zip(ids, levels, strict=True)):
        base = int(RamAddress.PARTY_MON_1) + 44 * i
        stat = species(code).stats_with_dvs(level, (8, 8, 8, 8 + i))
        assert memory[base] == memory[int(RamAddress.PARTY_SPECIES) + i] == code
        assert memory[base + 3] == memory[base + 33] == level
        assert memory[base + 4] == 0 and memory[base + 17 : base + 27] == bytes(10)
        assert memory[base + 12 : base + 14] == b"\x12\x34"
        assert memory[base + 27 : base + 29] == bytes((0x88, 0x88 + i))
        fingerprints.append(bytes(memory[base + 12 : base + 14] + memory[base + 27 : base + 29]))
        xp = species(code).experience_at_level(level)
        if condition == "healthy-rattata18-progressed" and i == 1:
            xp += (species(code).experience_at_level(level + 1) - xp) // 2
        assert int.from_bytes(memory[base + 14 : base + 17], "big") == xp
        assert int.from_bytes(memory[base + 1 : base + 3], "big") == (
            stat.max_hp // 2 if condition == "injured-prepared" else stat.max_hp
        )
        for offset, value in (
            (34, stat.max_hp),
            (36, stat.attack),
            (38, stat.defense),
            (40, stat.speed),
            (42, stat.special),
        ):
            assert int.from_bytes(memory[base + offset : base + offset + 2], "big") == value
        for j in range(4):
            move = memory[base + 8 + j]
            pp = (
                setup.PokemonRedBattleCatalog()
                .resolve_move(setup.pokemon_red_move_ref(move))
                .max_pp
                if move
                else 0
            )
            assert memory[base + 29 + j] == pp
    assert len(set(fingerprints)) == 4


@pytest.mark.parametrize(
    "fault",
    [
        "partition",
        "released",
        "battle",
        "bool-battle",
        "authority",
        "rom",
        "condition",
        "source-count",
        "source-level",
        "map",
        "earned",
        "moves",
        "species",
    ],
)
def test_party_invalid_setup_is_atomic(monkeypatch, fault):
    memory, args, species = party_fixture(monkeypatch)
    if fault == "partition":
        args["partition"] = "development"
    elif fault == "released":
        args["controller_released"] = False
    elif fault == "battle":
        args["battle_state"] = 2
    elif fault == "bool-battle":
        args["battle_state"] = False
    elif fault == "authority":
        args["isolated_training_setup"] = False
    elif fault == "rom":
        args["rom_sha256"] = "0" * 64
    elif fault == "condition":
        args["condition"] = "substitute-party"
    elif fault == "source-count":
        memory[RamAddress.PARTY_COUNT] = 2
    elif fault == "source-level":
        memory[int(RamAddress.PARTY_MON_1) + 33] = 15
    elif fault == "map":
        memory[RamAddress.CURRENT_MAP] = MapId.OAKS_LAB
    elif fault == "earned":
        memory[int(RamAddress.EVENT_FLAGS) + 191 // 8] |= 1 << (191 % 8)
    elif fault == "moves":
        monkeypatch.setattr(
            setup,
            "RedPracticeCartridge",
            lambda _: N(
                species=lambda i: replace(species(i), starting_moves=(33,), level_up_moves=())
            ),
        )
    elif fault == "species":
        monkeypatch.setattr(
            setup,
            "RedPracticeCartridge",
            lambda _: N(species=lambda i: replace(species(i), national_number=151)),
        )
    before = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_misty_party_training_fixture(memory, **args)
    assert bytes(memory) == before
