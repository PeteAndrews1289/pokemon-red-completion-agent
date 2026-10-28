import pytest
from test_red_safari_training_setup import memory

from pokemon_red_completion.observation import SQUIRTLE_SPECIES_ID, MapId, RamAddress
from pokemon_red_completion.red_player_training_setup import (
    assisted_progress_baseline,
    prepare_center_restore_fixture,
    prepare_mart_fixture,
)
from pokemon_red_completion.red_safari_training_setup import RED_ROM_SHA256


def test_assisted_baseline_preserves_strict_observer_and_discloses_synthetic_history():
    from types import SimpleNamespace

    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
    from pokemon_red_completion.route import COMPLETION_QUEST

    raw = RawGameState(game_started=True, map_id=MapId.SAFFRON_CITY, player_x=1,
                       player_y=1, party_count=1, battle_state=0)
    earned = ("power_on", "begin_adventure", "choose_starter")
    envelope, receipt = assisted_progress_baseline(raw, state_sha256="a"*64,
        checkpoint_id="assisted-gift", earned_objective_ids=earned,
        setup_receipt_sha256="b"*64, isolated_training_setup=True, partition="train")
    state = CapturedPokemonRedObserver(SimpleNamespace(read=lambda: raw),
                                      COMPLETION_QUEST, envelope).observe()
    assert "reach_saffron" in COMPLETION_QUEST.completed_ids(state)
    assert receipt["earned_objective_gain"] == 0 and not receipt["campaign_eligible"]
    assert "reach_celadon" in receipt["inferred_prerequisites"]
    assert set(receipt["synthetic_baseline_objectives"]).isdisjoint(earned)
    assert set(envelope.verified_objective_ids) == (
        set(earned) | set(receipt["synthetic_baseline_objectives"]))


def test_explicit_training_prerequisite_is_not_earned_story_progress():
    from pokemon_red_completion.observation import RawGameState

    envelope, receipt = assisted_progress_baseline(
        RawGameState(True, MapId.CERULEAN_GYM, 4, 10, 1, 0),
        state_sha256="a" * 64, checkpoint_id="misty-training",
        earned_objective_ids=("power_on", "begin_adventure", "choose_starter"),
        setup_receipt_sha256="b" * 64, isolated_training_setup=True, partition="train",
        synthetic_objective_ids=("reach_cerulean",),
    )
    assert "reach_cerulean" in envelope.verified_objective_ids
    assert receipt["declared_synthetic_objectives"] == ["reach_cerulean"]
    assert "reach_cerulean" not in receipt["original_earned_objectives"]
    assert "defeat_misty" not in envelope.verified_objective_ids
    assert receipt["earned_objective_gain"] == 0


@pytest.mark.parametrize("field,value", [("partition", "development"),
    ("isolated_training_setup", False), ("setup_receipt_sha256", "bad"),
    ("earned_objective_ids", ("liberate_silph",))])
def test_assisted_baseline_rejects_implicit_or_inconsistent_authority(field, value):
    from pokemon_red_completion.observation import RawGameState

    args = dict(state_sha256="a"*64, checkpoint_id="assisted-gift",
        earned_objective_ids=("power_on",), setup_receipt_sha256="b"*64,
        isolated_training_setup=True, partition="train")
    args[field] = value
    with pytest.raises(ValueError):
        assisted_progress_baseline(RawGameState(True, MapId.OAKS_LAB, 1, 1, 1, 0), **args)


def fixture():
    m = memory()
    m[RamAddress.PARTY_COUNT] = 1
    m[RamAddress.PARTY_SPECIES] = SQUIRTLE_SPECIES_ID
    m[int(RamAddress.PARTY_MON_1_HP) + 1] = 20
    m[int(RamAddress.PARTY_MON_1_MAX_HP) + 1] = 20
    return m


def apply(m, **overrides):
    return prepare_center_restore_fixture(m, **(dict(
        rom_sha256=RED_ROM_SHA256, isolated_training_setup=True,
        controller_released=True, battle_state=0,
    ) | overrides))


def test_only_declared_fixture_bytes_change():
    m = fixture()
    before = bytes(m)
    receipt = apply(m)
    addresses = {r["address"] for r in receipt}
    assert len(receipt) == 8
    assert all(m[i] == value for i, value in enumerate(before) if i not in addresses)
    assert m[int(RamAddress.PARTY_MON_1_HP) + 1] == 1
    assert m[0xD3B2] == m[0xD3B6] == MapId.VIRIDIAN_POKECENTER
    assert all(before[r["address"]] == r["before"] and m[r["address"]] == r["after"]
               for r in receipt)


@pytest.mark.parametrize("changes", [dict(rom_sha256="wrong"), dict(isolated_training_setup=False),
                                   dict(controller_released=False), dict(battle_state=True)])
def test_unapproved_setup_does_not_write(changes):
    m = fixture()
    before = bytes(m)
    with pytest.raises(ValueError):
        apply(m, **changes)
    assert bytes(m) == before


@pytest.mark.parametrize("address", [RamAddress.PARTY_COUNT, RamAddress.CURRENT_MAP,
                                    RamAddress.PARTY_SPECIES, 0xD3AF, 0xD3AE])
def test_changed_source_does_not_write(address):
    m = fixture()
    m[address] += 1
    before = bytes(m)
    with pytest.raises(ValueError):
        apply(m)
    assert bytes(m) == before


def test_mart_setup_preserves_money_party_items_and_records_all_writes():
    m = fixture()
    before = bytes(m)
    rows = prepare_mart_fixture(m, rom_sha256=RED_ROM_SHA256, isolated_training_setup=True,
                                controller_released=True, battle_state=0)
    changed = {r["address"] for r in rows}
    assert all(before[i] == m[i] for i in range(len(m)) if i not in changed)
    assert m[0xD3B2] == m[0xD3B6] == MapId.VIRIDIAN_MART
    assert m[RamAddress.VIRIDIAN_MART_SCRIPT] == 2
    assert all(before[r["address"]] == r["before"] and m[r["address"]] == r["after"] for r in rows)


@pytest.mark.parametrize("field,value", [("rom_sha256", "bad"), ("controller_released", False),
    ("isolated_training_setup", False), ("battle_state", 2), ("battle_state", False)])
def test_mart_setup_invalid_authority_never_writes(field, value):
    m = fixture()
    before = bytes(m)
    args = dict(rom_sha256=RED_ROM_SHA256, isolated_training_setup=True,
                controller_released=True, battle_state=0)
    args[field] = value
    with pytest.raises(ValueError):
        prepare_mart_fixture(m, **args)
    assert bytes(m) == before
