"""ROM-free predicate and cost-join tests; no source or native qualification."""

from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_red_sequence_state_audit import Emulator, events

from pokemon_red_completion import red_sequence_state_audit as module
from pokemon_red_completion.observation import SAFFRON_GUARD_ACCESS_MASK, Badge, EventFlag, MapId


def reader(monkeypatch, raw, *, owned=frozenset(), **overrides):
    em = Emulator()
    monkeypatch.setattr(module, "trainer_headers", lambda *a, **k: (NS(event_flag=86),))
    monkeypatch.setattr(
        module,
        "PokemonRedStateReader",
        lambda _: NS(read=lambda: raw, read_pokedex_state=lambda: NS(owned_species=owned)),
    )
    args = dict(
        rom=b"rom",
        expected_rom_sha256=sha256(b"rom").hexdigest(),
        maps=(133, int(MapId.SAFFRON_POKECENTER)),
        events=(86,),
        objectives=("defeat_erika", "reach_saffron", "rescue_fuji"),
    )
    args.update(overrides)
    args["maps"] = tuple(sorted(args["maps"]))
    return module.ScopedStorySequenceStateReader(em, **args)


@pytest.mark.parametrize(
    "flags,badge,guard,map_id,expected",
    [
        ((), 0, 0, 133, ()),
        ((EventFlag.BEAT_ERIKA,), int(Badge.RAINBOW), 0, 133, ()),
        ((EventFlag.BEAT_ERIKA, EventFlag.GOT_TM21), int(Badge.RAINBOW), 0, 133, ("defeat_erika",)),
        ((EventFlag.RESCUED_MR_FUJI,), 0, 0, 133, ()),
        ((EventFlag.RESCUED_MR_FUJI_WORLD,), 0, 0, 133, ()),
        ((EventFlag.RESCUED_MR_FUJI, EventFlag.RESCUED_MR_FUJI_WORLD), 0, 0, 133, ()),
        (
            (EventFlag.RESCUED_MR_FUJI, EventFlag.RESCUED_MR_FUJI_WORLD, EventFlag.GOT_POKE_FLUTE),
            0,
            0,
            133,
            ("rescue_fuji",),
        ),
        ((), 0, SAFFRON_GUARD_ACCESS_MASK, 133, ()),
        ((), 0, 0, int(MapId.SAFFRON_POKECENTER), ()),
        ((), 0, SAFFRON_GUARD_ACCESS_MASK, int(MapId.SAFFRON_POKECENTER), ("reach_saffron",)),
    ],
)
def test_intermediate_native_facts_do_not_fabricate_quest_completion(
    tmp_path, monkeypatch, flags, badge, guard, map_id, expected
):
    raw = NS(
        map_id=map_id,
        battle_state=0,
        player_money=11852,
        event_flags=events(*flags),
        badge_bits=badge,
        status_flags_1=guard,
    )
    audit = reader(monkeypatch, raw)
    p = tmp_path / "native.state"
    p.write_bytes(b"state")
    row = audit.read(p, sha256(b"state").hexdigest())
    assert row.quests == expected and row.cash == 11852
    assert audit.task_completed((), row.progress) is bool(expected)
    assert not audit.task_completed(row.progress, row.progress)
    assert audit.emulator.frame_count == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("badge_bits", True),
        ("badge_bits", int(Badge.RAINBOW)),
        ("status_flags_1", None),
        ("status_flags_1", True),
        ("status_flags_1", 256),
        ("map_id", 1),
        ("battle_state", 1),
        ("player_money", True),
    ],
)
def test_unknown_or_inconsistent_native_story_boundary_rejects(tmp_path, monkeypatch, field, value):
    raw = NS(
        map_id=133,
        battle_state=0,
        player_money=11852,
        event_flags=events(),
        badge_bits=0,
        status_flags_1=0,
    )
    setattr(raw, field, value)
    audit = reader(monkeypatch, raw)
    p = tmp_path / "native.state"
    p.write_bytes(b"state")
    with pytest.raises(ValueError):
        audit.read(p, sha256(b"state").hexdigest())


@pytest.mark.parametrize(
    "objectives",
    [
        (),
        ("rescue_fuji", "defeat_erika"),
        ("defeat_erika", "defeat_erika"),
        ("liberate_silph",),
        ["rescue_fuji"],
    ],
)
def test_unscoped_or_reordered_story_task_rejects(monkeypatch, objectives):
    with pytest.raises(ValueError):
        reader(monkeypatch, None, objectives=objectives)


def test_task_identity_binds_all_competing_objectives_and_maps(monkeypatch):
    full = reader(monkeypatch, None)
    narrow = reader(monkeypatch, None, objectives=("rescue_fuji",))
    elsewhere = reader(monkeypatch, None, maps=(133,))
    assert len({x.task_sha256 for x in (full, narrow, elsewhere)}) == 3
    assert len({x.catalog_sha256 for x in (full, narrow, elsewhere)}) == 3
    assert full.task_completed(("quest:defeat_erika",), ("quest:defeat_erika", "quest:rescue_fuji"))
    assert not narrow.task_completed((), ("quest:defeat_erika",))


def test_owned_native_registrations_are_versioned_progress_not_zero_reward(tmp_path, monkeypatch):
    raw = NS(
        map_id=133,
        battle_state=0,
        player_money=11852,
        event_flags=events(),
        badge_bits=0,
        status_flags_1=0,
    )
    old = reader(monkeypatch, raw)
    explicit = reader(monkeypatch, raw, include_registrations=False)
    new = reader(monkeypatch, raw, include_registrations=True, owned=frozenset({8, 13, 50, 83}))
    assert old.task_sha256 == explicit.task_sha256 and old.catalog_sha256 == explicit.catalog_sha256
    assert new.task_sha256 != old.task_sha256 and new.catalog_sha256 != old.catalog_sha256
    p = tmp_path / "state"
    p.write_bytes(b"state")
    row = new.read(p, sha256(b"state").hexdigest())
    assert row.progress == ("owned-dex:008", "owned-dex:013", "owned-dex:050", "owned-dex:083")
    assert row.quests == () and not new.task_completed((), row.progress)
    assert new.emulator.frame_count == 0


@pytest.mark.parametrize(
    "owned", [None, frozenset({True}), frozenset({0}), frozenset({152}), frozenset({"13"})]
)
def test_unknown_native_registration_channel_cannot_become_zero(tmp_path, monkeypatch, owned):
    raw = NS(
        map_id=133,
        battle_state=0,
        player_money=11852,
        event_flags=events(),
        badge_bits=0,
        status_flags_1=0,
    )
    audit = reader(monkeypatch, raw, include_registrations=True, owned=owned)
    p = tmp_path / "state"
    p.write_bytes(b"state")
    with pytest.raises(ValueError, match="unknown or unstable"):
        audit.read(p, sha256(b"state").hexdigest())


@pytest.mark.parametrize(
    "gift,move,badge,expected",
    [
        (False, 0, 0, ()),
        (True, 0, 0, ("field:hm02-native-gift",)),
        (False, 19, 0, ()),
        (False, 19, int(Badge.THUNDER), ("field:carried-fly-usable",)),
        (True, 19, int(Badge.THUNDER), ("field:carried-fly-usable", "field:hm02-native-gift")),
    ],
)
def test_model_owned_fly_gift_and_usable_move_are_distinct_native_progress(
    tmp_path, monkeypatch, gift, move, badge, expected
):
    raw = NS(
        map_id=133,
        battle_state=0,
        player_money=11852,
        event_flags=events(*((EventFlag.GOT_HM02,) if gift else ())),
        badge_bits=badge,
        status_flags_1=0,
        party_moves=((move, 0, 0, 0),),
    )
    audit = reader(monkeypatch, raw, include_field_progress=True)
    p = tmp_path / "state"
    p.write_bytes(b"state")
    row = audit.read(p, sha256(b"state").hexdigest())
    assert row.progress == expected and row.quests == ()
    assert not audit.task_completed((), row.progress)


@pytest.mark.parametrize('reward_name',["BLAINE_REWARD","GIOVANNI_REWARD"])
@pytest.mark.parametrize('stage',[0,1,2,3])
def test_late_gym_reward_requires_exact_victory_badge_and_TM(tmp_path,monkeypatch,reward_name,stage):
    from pokemon_red_completion import red_gym_reward as rewards
    reward=getattr(rewards,reward_name)
    flags=()if stage==0 else(reward.defeated_event,)if stage<3 else(reward.defeated_event,reward.reward_event)
    raw=NS(map_id=133,battle_state=0,player_money=11852,event_flags=events(*flags),badge_bits=reward.badge if stage>=2 else 0,status_flags_1=0)
    with pytest.raises(ValueError):reader(monkeypatch,raw,objectives=(reward.objective_id,))
    audit=reader(monkeypatch,raw,objectives=(reward.objective_id,),include_late_gym_rewards=True)
    p=tmp_path/'native.state';p.write_bytes(b'state');row=audit.read(p,sha256(b'state').hexdigest())
    assert (reward.objective_id in row.quests)==(stage==3)
    assert audit.task_completed((),row.progress)==(stage==3)
    assert audit.emulator.frame_count==0
