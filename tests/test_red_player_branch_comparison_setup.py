from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_player_income_setup import inputs

import pokemon_red_completion.red_player_branch_comparison_setup as setup
from pokemon_red_completion.observation import Badge, EventFlag, MapId, RamAddress
from pokemon_red_completion.red_player_income_setup import _income_fixture_changes


def fixture(monkeypatch):
    memory, args = inputs(monkeypatch)
    cartridge = setup.RedPracticeCartridge(args["rom"])
    monkeypatch.setattr(
        setup,
        "RedPracticeCartridge",
        lambda _: N(species=lambda i: replace(cartridge.species(i), national_number=8)),
    )
    for key in ("money", "balls", "forest_warp", "level", "isolated_training_setup"):
        args.pop(key)
    args.update(partition="development", isolated_comparison_setup=True, hp_percent=50)
    return memory, args


def test_pure_income_planner_never_mutates(monkeypatch):
    memory, args = inputs(monkeypatch)
    args.pop("partition")
    args.pop("isolated_training_setup")
    before = bytes(memory)
    assert _income_fixture_changes(memory, **args)
    assert bytes(memory) == before


@pytest.mark.parametrize("health", [50, 100])
def test_disclosed_comparison_preserves_identity_and_target_events(monkeypatch, health):
    memory, args = fixture(monkeypatch)
    args["hp_percent"] = health
    before = bytes(memory)
    rows = setup.prepare_branch_comparison_fixture(memory, **args)
    touched = {r["address"] for r in rows}
    assert all(memory[i] == v for i, v in enumerate(before) if i not in touched)
    assert all(
        r["before"] == before[r["address"]] and r["after"] == memory[r["address"]] for r in rows
    )
    base = int(RamAddress.PARTY_MON_1)
    assert memory[base] == 179 and memory[base + 33] == 19
    assert memory[base + 12 : base + 14] == before[base + 12 : base + 14]
    assert memory[base + 27 : base + 29] == before[base + 27 : base + 29]
    assert memory[RamAddress.CURRENT_MAP] == MapId.OAKS_LAB
    assert memory[RamAddress.OBTAINED_BADGES] == Badge.BOULDER
    assert memory[0xD3B2] == memory[0xD3B6] == MapId.CERULEAN_POKECENTER
    hp = int.from_bytes(memory[base + 1 : base + 3], "big")
    maximum = int.from_bytes(memory[base + 34 : base + 36], "big")
    assert hp == maximum * health // 100
    for flag in (EventFlag.BEAT_MISTY, EventFlag.BEAT_CERULEAN_RIVAL, EventFlag.GOT_SS_TICKET):
        assert not memory[int(RamAddress.EVENT_FLAGS) + int(flag) // 8] & (1 << (int(flag) % 8))


@pytest.mark.parametrize(
    "key,value",
    [
        ("partition", "train"),
        ("partition", "sealed"),
        ("isolated_comparison_setup", False),
        ("controller_released", False),
        ("battle_state", True),
        ("hp_percent", True),
        ("hp_percent", 75),
        ("rom", b"wrong"),
    ],
)
def test_comparison_invalid_authority_never_writes(monkeypatch, key, value):
    memory, args = fixture(monkeypatch)
    args[key] = value
    before = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_branch_comparison_fixture(memory, **args)
    assert bytes(memory) == before


@pytest.mark.parametrize(
    "flag",
    [
        EventFlag.BEAT_MISTY,
        EventFlag.BEAT_CERULEAN_RIVAL,
        EventFlag.MET_BILL,
        EventFlag.GOT_SS_TICKET,
    ],
)
def test_comparison_will_not_erase_existing_progress(monkeypatch, flag):
    memory, args = fixture(monkeypatch)
    memory[int(RamAddress.EVENT_FLAGS) + int(flag) // 8] |= 1 << (int(flag) % 8)
    before = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_branch_comparison_fixture(memory, **args)
    assert bytes(memory) == before


def test_comparison_progress_stays_development_and_unearned():
    from pokemon_red_completion.observation import RawGameState

    args = dict(
        state_sha256="a" * 64,
        checkpoint_id="comparison",
        earned_objective_ids=("power_on", "begin_adventure", "choose_starter"),
        setup_receipt_sha256="b" * 64,
        synthetic_objective_ids=("reach_cerulean",),
    )
    raw = RawGameState(True, MapId.CERULEAN_POKECENTER, 4, 10, 1, 0)
    envelope, receipt = setup.comparison_progress_baseline(
        raw, isolated_comparison_setup=True, partition="development", **args
    )
    assert receipt["partition"] == "development" and receipt["earned_objective_gain"] == 0
    assert not receipt["campaign_eligible"] and "reach_cerulean" in envelope.verified_objective_ids
    assert not {"help_bill", "defeat_misty"} & set(envelope.verified_objective_ids)
    with pytest.raises(ValueError):
        setup.comparison_progress_baseline(
            raw, isolated_comparison_setup=True, partition="train", **args
        )
