from dataclasses import dataclass, replace
from types import SimpleNamespace as NS

import pytest
from test_red_party_preparation import setup

from pokemon_red_completion import red_wild_preparation as w
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "battle",
        "heal",
        "no_xp",
        "depleted",
        "actor",
        "later_battle",
        "low_hp",
        "nonwinning_exit",
    ],
)
@pytest.mark.parametrize("maximum_battles", [1, 3])
def test_wild_excursion_tracks_xp_and_retains_failures(
    tmp_path, monkeypatch, fault, maximum_battles
):
    members, plan = setup()
    live = [members]
    raw = NS(
        map_id=89,
        player_y=3,
        player_x=3,
        player_money=1000,
        bag_items=(),
        party_species_ids=(1, 2, 3),
        party_count=3,
        battle_state=0,
        battle_result=0,
        party_hp=(50, 50, 50),
        party_status=(0, 0, 0),
        party_pp=((20,), (20,), (20,)),
    )
    reader = NS(
        read=lambda: raw,
        read_input_readiness=lambda: NS(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    emulator = NS(pressed_buttons=())
    monkeypatch.setattr(w, "_raw_party_fully_restored", lambda r: fault != "depleted")
    monkeypatch.setattr(w, "observe_preparation_members", lambda *a: live[0])
    monkeypatch.setattr(
        w.RedTrainerEvolutionGuard, "from_rom", lambda *a: NS(matches=lambda *a: True)
    )

    def swap(*a, **k):
        a, b, c = live[0]
        live[0] = (
            replace(b, observation=replace(b.observation, slot=1)),
            replace(a, observation=replace(a.observation, slot=2)),
            c,
        )

    monkeypatch.setattr(w, "swap_field_party_slots", swap)

    def heal(*a):
        if fault == "heal":
            raise RuntimeError("heal failed")
        raw.player_y, raw.player_x = 3, 3

    monkeypatch.setattr(w, "restore_story_team", heal)

    @dataclass
    class Route:
        destination_map: int = 89
        destination_at: tuple = (3, 3)

        def __call__(self, *a):
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at

    actor = FrozenTrainerBattler(
        None,
        None,
        tmp_path,
        "a" * 40,
        "root",
        "b" * 64,
        {},
        model_sha256=FROZEN_K_SHA256,
        qualification_sha256=None if fault == "actor" else K_QUALIFICATION_SHA256,
    )

    battle_calls = []

    def battle(reader, actions, **kwargs):
        battle_calls.append(1)
        kwargs["decision_guard"](raw)
        if fault == "battle" or (fault == "later_battle" and len(battle_calls) == 2):
            raise RuntimeError("battle failed")
        if fault not in {"no_xp", "nonwinning_exit"}:
            first, *rest = live[0]
            live[0] = (
                replace(
                    first,
                    observation=replace(
                        first.observation, experience=first.observation.experience + 200
                    ),
                ),
                *rest,
            )
        raw.battle_state = 0
        if fault == "low_hp":
            first, *rest = live[0]
            live[0] = (replace(first, observation=replace(first.observation, hp=20)), *rest)
        return NS(battle_won=fault != "nonwinning_exit", stop_reason="battle_exited_without_win")

    actor.run_wild_training = battle
    spent = [0, 0]

    def execute(action):
        spent[0] += 1
        spent[1] += 120
        raw.battle_state = 1

    records = {}
    kwargs = dict(
        rom=b"rom",
        reader=reader,
        actions=NS(execute=execute),
        emulator=emulator,
        battler=actor,
        adapter=None,
        source_raw=NS(**vars(raw)),
        plan=plan,
        attempts=(),
        record=lambda k, v: records.__setitem__(k, v),
        cost_snapshot=lambda: tuple(spent),
        hideout_timing=None,
        route=Route(),
        corridor=NS(map_id=22, origin_at=(4, 4), terminal_at=(3, 4), private_dict=lambda: {}),
        maximum_battles=maximum_battles,
    )
    failed = fault not in {None, "low_hp", "nonwinning_exit"} and not (
        fault == "later_battle" and maximum_battles == 1
    )
    if failed:
        with pytest.raises((ValueError, RuntimeError)):
            w.execute_wild_preparation(**kwargs)
    else:
        result = w.execute_wild_preparation(**kwargs)
        expected = 0 if fault == "nonwinning_exit" else 1 if fault == "low_hp" else maximum_battles
        assert result["xp_gained"] == 200 * expected
        assert result["battles"] == expected
        if fault == "nonwinning_exit":
            assert result["status"] == "no_progress"
            assert result["stop_reason"] == "battle_exited_without_win"
            assert raw.map_id == 89 and records["healing-started"]
        if fault == "low_hp" and maximum_battles > 1:
            assert result["stop_reason"] == "party_hp_below_half"
    if fault in {"depleted", "actor"}:
        assert not records and spent == [0, 0]
    else:
        assert records["preparation-cost"]["completed_excursion"] is not failed
        assert records["preparation-attempt"]["attempt"]["failed"] is failed
        assert records["preparation-attempt"]["attempt"]["actions"] == spent[0]
        assert records["preparation-attempt"]["cash_delta"] == 0


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"hp": 0}, "party_fainted"),
        ({"hp": 24}, "party_hp_below_half"),
        ({"hp": 25}, None),
        ({"status": w.StatusCondition.POISON}, "party_status"),
        ({"level": 34}, "trainee_target_reached"),
    ],
)
def test_resource_stop_uses_semantic_party(change, reason):
    members, _ = setup()
    trainee = members[1]
    members = (
        members[0],
        replace(trainee, observation=replace(trainee.observation, **change)),
        members[2],
    )
    assert w.wild_training_return_reason(members, trainee.specimen_ref, 34) == reason


@pytest.mark.parametrize("pp,reason", [(4, "trainee_attack_pp_low"), (5, None)])
def test_attack_pp_stop_excludes_status_pp(pp, reason):
    from pokemon_red_completion.party import MoveObservation

    members, _ = setup()
    trainee = members[1]
    members = (
        members[0],
        replace(
            trainee,
            observation=replace(
                trainee.observation, moves=(MoveObservation(33, pp), MoveObservation(28, 40))
            ),
        ),
        members[2],
    )
    assert w.wild_training_return_reason(members, trainee.specimen_ref, 34) == reason


@pytest.mark.parametrize(
    "hp,expected",
    [
        ((20, 50, 50), None),
        ((20, 20, 50), "insufficient_battle_ready_members"),
        ((0, 50, 50), "party_fainted"),
    ],
)
def test_opt_in_party_depth_keeps_recovery_bound(hp, expected):
    members, _ = setup()
    members = tuple(
        replace(m, observation=replace(m.observation, hp=h))
        for m, h in zip(members, hp, strict=True)
    )
    assert (
        w.wild_training_return_reason(members, members[1].specimen_ref, 34, minimum_ready_members=2)
        == expected
    )


def test_party_depth_does_not_ignore_status_or_invalid_threshold():
    members, _ = setup()
    status = tuple(
        replace(m, observation=replace(m.observation, status=w.StatusCondition.POISON))
        if i == 0
        else m
        for i, m in enumerate(members)
    )
    assert (
        w.wild_training_return_reason(status, members[1].specimen_ref, 34, minimum_ready_members=2)
        == "party_status"
    )
    with pytest.raises(ValueError):
        w.wild_training_return_reason(members, members[1].specimen_ref, 34, minimum_ready_members=4)
