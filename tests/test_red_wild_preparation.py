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


def test_opt_in_return_leaves_restoration_for_player(tmp_path, monkeypatch):
    original = w.execute_wild_preparation
    events = {}

    def without_heal(**kwargs):
        saved = kwargs["record"]

        def record(name, value):
            events[name] = value
            saved(name, value)

        return original(**(kwargs | {"restore_on_return": False, "record": record}))

    monkeypatch.setattr(w, "execute_wild_preparation", without_heal)
    test_wild_excursion_tracks_xp_and_retains_failures(tmp_path, monkeypatch, None, 1, False, False)
    assert "healing-started" not in events
    assert events["preparation-attempt"]["attempt"]["heals"] == 0


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
        "no_encounter",
        "later_no_encounter",
        "unsafe_search",
        "bad_home",
        "party_defeated",
        "false_defeat",
        "early_health",
        "zero_xp_faint",
        "zero_xp_faint_strict",
        "all_statused",
        "escort_only_xp",
    ],
)
@pytest.mark.parametrize("maximum_battles", [1, 3, 32, 128])
@pytest.mark.parametrize("field_start", [False, True])
@pytest.mark.parametrize("escort", [False, True])
def test_wild_excursion_tracks_xp_and_retains_failures(
    tmp_path, monkeypatch, fault, maximum_battles, field_start, escort, continue_exits=False, minimum_ready_members=None
):
    members, plan = setup()
    if fault == "reserve_low_nonwinning":
        members = tuple(replace(m, observation=replace(m.observation, hp=hp, max_hp=hp))
                        for m, hp in zip(members, (121, 53, 37), strict=True))
    live = [members]
    raw = NS(
        map_id=9 if field_start else 89,
        player_y=3,
        player_x=3,
        player_money=1000,
        bag_items=(),
        party_species_ids=(1, 2, 3),
        party_count=3,
        battle_state=0,
        battle_result=0,
        party_hp=tuple(m.observation.hp for m in members),
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
    escort_epoch = [0]

    def guard(*args):
        epoch = escort_epoch[0]
        return NS(matches=lambda *a: escort_epoch[0] == epoch)

    monkeypatch.setattr(w.RedTrainerEvolutionGuard, "from_rom", guard)

    def swap(*a, **k):
        a, b, c = live[0]
        live[0] = (
            replace(b, observation=replace(b.observation, slot=1)),
            replace(a, observation=replace(a.observation, slot=2)),
            c,
        )
        raw.party_hp = tuple(m.observation.hp for m in live[0])

    monkeypatch.setattr(w, "swap_field_party_slots", swap)
    escorts = []

    def escort_swap(*args, allow_statused=False):
        assert type(allow_statused) is bool
        assert allow_statused is bool(escorts)
        escorts.append((raw.map_id, allow_statused))
        escort_epoch[0] += 1
        return 0

    monkeypatch.setattr(w, "prepare_training_transport", escort_swap)

    def heal(*a):
        if fault == "heal":
            raise RuntimeError("heal failed")
        if fault == "all_statused":
            raw.party_status = (0, 0, 0)
            live[0] = tuple(
                replace(m, observation=replace(m.observation, status=w.StatusCondition.HEALTHY))
                for m in live[0]
            )
        raw.player_y, raw.player_x = 3, 3

    monkeypatch.setattr(w, "restore_story_team", heal)

    @dataclass
    class Route:
        # Match the real ground transition default; observed geometry has a separate typed fixture.
        observe_terrain: bool = False
        destination_map: int = 89
        destination_at: tuple = (3, 3)

        def __call__(self, *a):
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            if fault == "early_health" and self.destination_map == 22:
                live[0] = tuple(
                    replace(m, observation=replace(m.observation, hp=20)) for m in live[0]
                )
                raw.party_hp = (20, 20, 20)

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
        if fault in {"party_defeated", "false_defeat"}:
            raw.party_hp = (0, 0, 0) if fault == "party_defeated" else (1, 0, 0)
            return NS(battle_won=False, stop_reason="party_defeated")
        if fault == "battle" or (fault == "later_battle" and len(battle_calls) == 2):
            raise RuntimeError("battle failed")
        escape = fault in {"nonwinning_exit", "escape_low_hp", "reserve_low_nonwinning"} or (
            fault == "escape_then_win" and len(battle_calls) == 1
        )
        if fault not in {"no_xp", "zero_xp_faint", "zero_xp_faint_strict"} and not escape:
            first, *rest = live[0]
            recipient = (
                next(m for m in live[0] if m.specimen_ref not in dict(plan.targets))
                if fault in {"escort_only_xp", "reserve_xp_decreased"} else first
            )
            live[0] = tuple(
                replace(m, observation=replace(
                    m.observation, experience=m.observation.experience + 200
                )) if m.specimen_ref == recipient.specimen_ref else m
                for m in live[0]
            )
            if fault == "reserve_xp_decreased":
                live[0] = tuple(
                    replace(m, observation=replace(
                        m.observation, experience=m.observation.experience - 100
                    )) if m.specimen_ref == first.specimen_ref else m
                    for m in live[0]
                )
        raw.battle_state = 0
        if fault == "all_statused":
            raw.party_status = (64, 8, 64)
            live[0] = tuple(
                replace(m, observation=replace(m.observation, status=w.StatusCondition.PARALYSIS))
                for m in live[0]
            )
        if fault in {"low_hp", "escape_low_hp"}:
            first, *rest = live[0]
            live[0] = (replace(first, observation=replace(first.observation, hp=20)), *rest)
        if fault in {"zero_xp_faint", "zero_xp_faint_strict"}:
            first, *rest = live[0]
            live[0] = (replace(first, observation=replace(first.observation, hp=0)), *rest)
            raw.party_hp = (0, 50, 50)
        if fault == "reserve_low_nonwinning":
            first, second, reserve = live[0]
            live[0] = (first, second, replace(reserve, observation=replace(reserve.observation, hp=18)))
            raw.party_hp = tuple(m.observation.hp for m in live[0])
        return NS(battle_won=not escape, stop_reason="battle_exited_without_win")

    actor.run_wild_training = battle
    spent = [0, 0]

    def execute(action):
        spent[0] += 1
        spent[1] += 120
        if fault in {"no_encounter", "unsafe_search"} or (
            fault == "later_no_encounter" and len(battle_calls) == 1
        ):
            raw.battle_state = 0
            if fault == "unsafe_search":
                reader.read_input_readiness = lambda: NS(ready=False)
        else:
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
        recovery_home_map=9 if fault == "bad_home" else 89 if field_start else None,
        prepare_transport_escort=escort,
        allow_health_retreat=fault in {"early_health", "zero_xp_faint", "reserve_low_nonwinning"},
        restore_on_return=fault not in {"early_health", "reserve_low_nonwinning"},
        minimum_ready_members=minimum_ready_members,
        continue_after_nonwinning_exit=continue_exits,
    )
    failed = fault not in {
        None,
        "low_hp",
        "nonwinning_exit",
        "no_encounter",
        "later_no_encounter",
        "early_health",
        "escape_low_hp",
        "escape_then_win",
        "reserve_low_nonwinning",
        "zero_xp_faint",
        "all_statused",
        "escort_only_xp",
    } and not (fault == "later_battle" and maximum_battles == 1)
    if failed:
        with pytest.raises((ValueError, RuntimeError)) as caught:
            w.execute_wild_preparation(**kwargs)
        if fault in {"party_defeated", "false_defeat"}:
            assert isinstance(caught.value, w.WildPreparationDefeat) == (fault == "party_defeated")
    else:
        result = w.execute_wild_preparation(**kwargs)
        expected = (
            0
            if fault in {"nonwinning_exit", "no_encounter", "early_health", "escape_low_hp", "reserve_low_nonwinning"}
            else 1
            if fault in {"low_hp", "later_no_encounter", "zero_xp_faint", "all_statused"}
            else maximum_battles - 1
            if fault == "escape_then_win"
            else maximum_battles
        )
        assert result["xp_gained"] == (0 if fault == "zero_xp_faint" else 200 * expected)
        assert result["battles"] == expected
        assert raw.map_id == 89
        assert len(escorts) == (2 if escort else 0)
        if fault == "escort_only_xp":
            assert result["status"] == "no_progress"
            assert result["stop_reason"] == "trainee_received_no_xp"
            assert all(m.observation.experience == 1000 for m in live[0]
                       if m.specimen_ref in dict(plan.targets))
        if fault == "all_statused":
            assert raw.party_status == (0, 0, 0)
            assert records["healing-started"]
            assert result["stop_reason"] == (
                "party_status" if maximum_battles > 1 else "encounter_limit"
            )
            if escort:
                assert records["return-transport"]["selected_status"] == 64
        if fault == "early_health":
            assert result["status"] == "no_progress"
            assert result["health_limited_return"] is True
            assert result["stop_reason"] == "party_hp_below_half"
            assert not battle_calls and "healing-started" not in records
        if fault == "zero_xp_faint":
            assert result["status"] == "no_progress"
            assert result["health_limited_return"] is True
            assert result["stop_reason"] == "party_fainted"
        if fault == "nonwinning_exit":
            assert result["status"] == "no_progress"
            assert result["stop_reason"] == (
                "encounter_limit" if continue_exits else "battle_exited_without_win"
            )
            assert raw.map_id == 89 and records["healing-started"]
        if fault == "low_hp" and maximum_battles > 1:
            assert result["stop_reason"] == "party_hp_below_half"
        if fault == "no_encounter" or (fault == "later_no_encounter" and maximum_battles > 1):
            assert result["stop_reason"] == "encounter_search_exhausted"
            assert result["status"] == ("complete" if expected else "no_progress")
            assert records["search-exhausted"]["battles_completed"] == expected
            assert records["healing-started"] and len(battle_calls) == expected
    if fault in {"depleted", "actor", "bad_home"}:
        assert not records and spent == [0, 0]
    else:
        assert records["preparation-cost"]["completed_excursion"] is not failed
        if fault == "reserve_xp_decreased":
            assert records["preparation-cost"]["error"] == "wild preparation reserve XP decreased"
            # An impossible decreasing-XP observation cannot become a valid
            # semantic training outcome; the earlier cost receipt still exists.
            assert "preparation-attempt" not in records
            return
        assert records["preparation-attempt"]["attempt"]["failed"] is failed
        assert records["preparation-attempt"]["attempt"]["actions"] == spent[0]
        assert records["preparation-attempt"]["cash_delta"] == 0
    if continue_exits:
        return result, records, battle_calls


def test_negative_target_xp_refuses_invalid_outcome_and_keeps_cost(tmp_path, monkeypatch):
    test_wild_excursion_tracks_xp_and_retains_failures(
        tmp_path, monkeypatch, "reserve_xp_decreased", 1, False, False
    )


@pytest.mark.parametrize(
    "fault,encounters,wins,reason",
    [
        ("nonwinning_exit", 3, 0, "encounter_limit"),
        ("escape_then_win", 3, 2, "encounter_limit"),
        ("escape_low_hp", 1, 0, "party_hp_below_half"),
    ],
)
def test_safe_nonwinning_continuation_counts_attempts_and_keeps_health_stop(
    tmp_path, monkeypatch, fault, encounters, wins, reason
):
    result, records, calls = test_wild_excursion_tracks_xp_and_retains_failures(
        tmp_path, monkeypatch, fault, 3, False, False, continue_exits=True
    )
    assert result["encounters"] == len(calls) == encounters
    assert result["battles"] == wins
    assert result["nonwinning_exits"] == encounters - wins
    assert result["stop_reason"] == reason
    assert records["preparation-cost"]["encounters"] == encounters
    assert sum(k.startswith("wild-encounter-") for k in records) == encounters
    assert records["wild-encounter-001"]["battle_won"] is False


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


@pytest.mark.parametrize("pp,reason", [(4, "attack_support_pp_low"), (5, None)])
def test_status_only_recipient_can_use_learned_switch_but_reserve_pp_is_required(pp, reason):
    from pokemon_red_completion.party import MoveObservation

    members, _ = setup()
    trainee = members[1]
    members = tuple(replace(m, observation=replace(m.observation,
        moves=(MoveObservation(106, 30),) if m is trainee else (MoveObservation(33, pp),)))
        for m in members)
    assert w.wild_training_has_attack_capacity(members)
    assert w.wild_training_return_reason(members, trainee.specimen_ref, 34) == reason
    assert "attack_support_pp_low" in w.HEALTH_LIMITED_RETURNS


@pytest.mark.parametrize("fault,reason", [("none", "trainee_no_attack_support"),
    ("self_destruct", "trainee_no_attack_support"), ("faint", "party_fainted"),
    ("status", "party_status"), ("hp", "party_hp_below_half")])
def test_status_only_recipient_never_waives_party_safety_or_structural_capacity(fault, reason):
    from pokemon_red_completion.party import MoveObservation

    members, _ = setup()
    trainee = members[1]
    members = tuple(replace(m, observation=replace(m.observation,
        moves=(MoveObservation(106, 30),))) for m in members)
    if fault != "none":
        reserve = members[0]
        changed = {"moves": (MoveObservation(120 if fault == "self_destruct" else 33, 20),)}
        changed.update({"hp": 0} if fault == "faint" else
                       {"hp": 24} if fault == "hp" else
                       {"status": w.StatusCondition.POISON} if fault == "status" else {})
        members = (replace(reserve, observation=replace(reserve.observation, **changed)),
                   *members[1:])
    assert w.wild_training_has_attack_capacity(members) is (fault not in {"none", "self_destruct"})
    assert w.wild_training_return_reason(members, trainee.specimen_ref, 34) == reason
    assert "trainee_no_attack_support" not in w.HEALTH_LIMITED_RETURNS


def test_depleted_direct_attacker_still_retreats_with_fresh_reserve():
    from pokemon_red_completion.party import MoveObservation

    members, _ = setup()
    trainee = members[1]
    members = (members[0], replace(trainee, observation=replace(trainee.observation,
        moves=(MoveObservation(33, 0), MoveObservation(106, 30)))), members[2])
    assert (
        w.wild_training_return_reason(members, trainee.specimen_ref, 34) == "trainee_attack_pp_low"
    )


@pytest.mark.parametrize(
    "hp,expected",
    [
        ((20, 50, 50), None),
        ((20, 20, 50), "insufficient_battle_ready_members"),
        ((50, 20, 50), "party_hp_below_half"),
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


def test_transport_uses_visible_speed_not_species_or_level_and_excludes_status():
    raw = NS(
        party_count=3,
        party_hp=(100, 80, 50),
        party_status=(0, 0, 0),
        party_stats=((80, 80, 50, 80), (80, 80, 150, 80), (80, 80, 100, 80)),
    )
    assert w.preparation_transport_slot(raw) == 1
    raw.party_status = (0, 8, 0)
    assert w.preparation_transport_slot(raw) == 2
    raw.party_hp = (100, 80, 0)
    assert w.preparation_transport_slot(raw) == 0
    raw.party_status = (8, 8, 0)
    with pytest.raises(ValueError, match="healthy"):
        w.preparation_transport_slot(raw)


def test_return_transport_allows_living_statused_fallback_but_still_prefers_healthy():
    raw = NS(
        party_count=3,
        party_hp=(100, 80, 0),
        party_status=(64, 8, 0),
        party_stats=((80, 80, 50, 80), (80, 80, 150, 80), (80, 80, 200, 80)),
    )
    assert w.preparation_transport_slot(raw, allow_statused=True) == 1
    raw.party_status = (0, 8, 0)
    assert w.preparation_transport_slot(raw, allow_statused=True) == 0
    raw.party_hp = (0, 0, 0)
    with pytest.raises(ValueError, match="living member"):
        w.preparation_transport_slot(raw, allow_statused=True)


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_statused_transport_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match="opt-in"):
        w.preparation_transport_slot(NS(), allow_statused=value)


def test_statused_return_swap_uses_native_executor_not_state_edit(monkeypatch):
    raw = NS(
        party_count=2,
        party_hp=(42, 73),
        party_status=(64, 8),
        party_stats=((25, 25, 20, 25), (50, 50, 50, 50)),
    )
    calls = []
    monkeypatch.setattr(w, "swap_field_party_slots", lambda *args, **kwargs: calls.append(kwargs))
    reader = NS(read=lambda: raw)
    with pytest.raises(ValueError, match="healthy"):
        w.prepare_training_transport(None, reader, None, None)
    assert not calls
    assert w.prepare_training_transport(None, reader, None, None, allow_statused=True) == 1
    assert calls[0]["first_index"] == 0 and calls[0]["second_index"] == 1
    assert raw.party_status == (64, 8) and raw.party_hp == (42, 73)


@pytest.mark.parametrize("stats", [None, ((1, 2, 3),), ((1, 2, True, 4),), ((1, 2, 0, 4),)])
def test_transport_missing_or_invalid_stats_fail_closed(stats):
    with pytest.raises(ValueError):
        w.preparation_transport_slot(
            NS(party_count=1, party_hp=(10,), party_status=(0,), party_stats=stats)
        )


@pytest.mark.parametrize("minimum,encounters,reason", [
    (None, 1, "party_hp_below_half"),
    (2, 2, "encounter_limit"),
])
def test_healthy_trainee_and_escort_continue_past_depleted_reserve(
    tmp_path, monkeypatch, minimum, encounters, reason
):
    result, records, calls = test_wild_excursion_tracks_xp_and_retains_failures(
        tmp_path, monkeypatch, "reserve_low_nonwinning", 2, False, False,
        continue_exits=True, minimum_ready_members=minimum,
    )
    assert len(calls) == result["encounters"] == result["nonwinning_exits"] == encounters
    assert result["battles"] == result["xp_gained"] == 0
    assert result["stop_reason"] == reason
    assert result["health_limited_return"] is (minimum is None)
    assert records["preparation-cost"]["completed_excursion"] is True
    assert "healing-started" not in records
