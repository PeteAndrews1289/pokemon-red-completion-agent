from __future__ import annotations

from dataclasses import fields, replace

import pytest

import pokemon_red_completion.lavender as lavender_module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.lavender import (
    BATTLE_RECOVERY_THRESHOLD,
    DEFAULT_LAVENDER_TIMING,
    DUX_BATTLE_RECOVERY_THRESHOLD,
    FINAL_TUNNEL_GRASS_SPECIES,
    FINAL_TUNNEL_RECOVERY_THRESHOLD,
    LAVENDER_CHECKPOINT_COUNT,
    PROTECTED_PARTY,
    ROUTE_9_MIN_SUPER_POTION_RESERVE,
    TUNNEL_TRAINER_7_BATTLE_RECOVERY_THRESHOLD,
    LavenderChapterReport,
    LavenderCheckpoint,
    LavenderTiming,
    TrainerEvidence,
)
from pokemon_red_completion.observation import (
    BULBASAUR_SPECIES_ID,
    ItemId,
    MapId,
    RawGameState,
)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.LAVENDER_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        party_species_ids=PROTECTED_PARTY,
        first_party_hp=79,
        first_party_max_hp=79,
        first_party_status=0,
        first_party_moves=(44, 39, 61, 55),
        first_party_pp=(25, 30, 20, 25),
    )


def _report() -> LavenderChapterReport:
    raw = _raw()
    records = tuple(
        LavenderCheckpoint(f"gate_{index}", f"Gate {index}", raw)
        for index in range(LAVENDER_CHECKPOINT_COUNT)
    )
    trainers = tuple(
        TrainerEvidence(
            f"trainer {index}",
            MapId.ROCK_TUNNEL_1F,
            0x441 + index,
            0xCE,
            0x06,
            index + 1,
            44,
            1,
        )
        for index in range(12)
    )
    return LavenderChapterReport(
        records=records,
        trainers=trainers,
        wild_flees=(),
        final_raw=raw,
        party_hp=(79, 52, 37),
        party_max_hp=(79, 52, 37),
        party_status=(0, 0, 0),
        repels_purchased=4,
        repels_used=4,
        parlyz_heals_purchased=3,
        parlyz_heals_used=2,
        parlyz_heals_remaining=1,
        antidotes_purchased=1,
        antidotes_remaining=1,
        awakenings_used=3,
        awakenings_remaining=2,
        starting_super_potions=1,
        super_potions_purchased=15,
        super_potions_used=4,
        super_potions_remaining=12,
        purchase_cost=13200,
        tm28_sale_proceeds=1000,
        money_remaining=1234,
        route_10_trainer_2_bypassed=True,
        frames_executed=100,
        actions_executed=50,
        controller_released=True,
    )


def test_lavender_timing_is_positive_and_bounded() -> None:
    assert LavenderTiming() == DEFAULT_LAVENDER_TIMING
    assert all(
        isinstance(getattr(DEFAULT_LAVENDER_TIMING, field.name), int)
        and getattr(DEFAULT_LAVENDER_TIMING, field.name) > 0
        for field in fields(LavenderTiming)
    )


def test_rock_center_exit_normalizes_false_ready_nurse_dialogue() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.actions: list[object] = []

        def execute(self, action: object) -> None:
            self.actions.append(action)

        def read(self) -> RawGameState:
            return replace(
                _raw(),
                map_id=MapId.ROCK_TUNNEL_POKECENTER,
                player_x=3,
                player_y=3,
            )

        def read_input_readiness(self) -> object:
            return type("Readiness", (), {"ready": True})()

    runtime = Runtime()
    lavender_module._normalize_rock_center_exit_dialogue(
        runtime,  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
        LavenderTiming(wait_frames=1),
    )

    assert [getattr(action, "kind", None) for action in runtime.actions] == [
        MacroActionKind.CANCEL,
        MacroActionKind.WAIT,
    ] * 4


@pytest.mark.parametrize(
    ("projected_money", "preserve_existing_sale", "expected"),
    (
        (10_000, False, 0),
        (10_000, True, 1),
        (9_741, False, 2),
        (9_701, False, 2),
    ),
)
def test_obsolete_potion_sale_funds_variable_capture_spend(
    projected_money: int,
    preserve_existing_sale: bool,
    expected: int,
) -> None:
    assert (
        lavender_module._required_potion_sale_quantity(
            available=6,
            projected_money=projected_money,
            required_cost=10_000,
            preserve_existing_sale=preserve_existing_sale,
        )
        == expected
    )


def test_obsolete_potion_sale_rejects_an_unfunded_plan() -> None:
    with pytest.raises(lavender_module.LavenderChapterError, match="exceed"):
        lavender_module._required_potion_sale_quantity(
            available=1,
            projected_money=9_700,
            required_cost=10_000,
            preserve_existing_sale=False,
        )


def test_supply_income_detour_is_source_stable_and_reversible() -> None:
    assert (
        *(("right",) * 10),
        *(("down",) * 10),
        "right",
        "right",
    ) == lavender_module.CENTER_EXTERIOR_TO_MART_APPROACH
    assert lavender_module.MART_EXTERIOR_TO_ROUTE_11 == ("right",) * 17
    assert (
        *(("right",) * 9),
        *(("down",) * 9),
        "right",
    ) == lavender_module.ROUTE_11_TO_SUPPLY_GAMBLER
    assert (
        "left",
        *(("up",) * 9),
        *(("left",) * 9),
    ) == lavender_module.SUPPLY_GAMBLER_TO_ROUTE_11_ENTRY
    assert (
        "left",
        "left",
        *(("up",) * 10),
        *(("left",) * 10),
    ) == lavender_module.MART_TO_CENTER_EXTERIOR
    assert lavender_module.ROUTE_11_GAMBLER_PAYOUT == 1_260
    assert lavender_module.TM24_SALE_PROCEEDS == 1_000


def test_final_tunnel_battles_use_seed_safe_recovery_thresholds() -> None:
    assert BATTLE_RECOVERY_THRESHOLD == 40
    assert lavender_module.TUNNEL_RECOVERY_THRESHOLD == 40
    assert DUX_BATTLE_RECOVERY_THRESHOLD == 20
    assert ROUTE_9_MIN_SUPER_POTION_RESERVE == 5
    assert TUNNEL_TRAINER_7_BATTLE_RECOVERY_THRESHOLD == 40
    assert FINAL_TUNNEL_RECOVERY_THRESHOLD == 90
    assert lavender_module.TUNNEL_PARLYZ_HEALS_PURCHASED == 3
    assert lavender_module.TUNNEL_AWAKENINGS_PURCHASED == 3
    assert lavender_module.TUNNEL_AWAKENING_RESERVE == 5
    assert lavender_module.POST_MART_RNG_ALIGNMENT_FRAMES == 47
    assert (
        lavender_module.POST_MART_RNG_ALIGNMENT_FRAMES
        + (lavender_module.TUNNEL_PARLYZ_HEALS_PURCHASED - 1) * 144
        == 335
    )
    assert lavender_module.EARLY_POKE_BALL_CAPACITY_RESERVE == 1


def test_lavender_paralysis_top_up_restores_a_fixed_reserve() -> None:
    assert tuple(lavender_module._parlyz_top_up_quantity(quantity) for quantity in range(4)) == (
        3,
        2,
        1,
        0,
    )
    with pytest.raises(lavender_module.LavenderChapterError):
        lavender_module._parlyz_top_up_quantity(4)


def test_lavender_antidote_top_up_preserves_an_existing_surplus() -> None:
    assert tuple(lavender_module._antidote_top_up_quantity(quantity) for quantity in range(3)) == (
        1,
        0,
        0,
    )


def test_final_tunnel_policy_spends_bite_evidence_then_exploits_with_bubblebeam() -> None:
    assert lavender_module._ranked_lavender_move_slots(
        move_slot=1,
        starting_selected_pp=25,
        current_selected_pp=25,
        finish_with_bubblebeam=True,
        enemy_species_id=0xA9,
        active_party_index=0,
    ) == (1, 3, 4)
    assert lavender_module._ranked_lavender_move_slots(
        move_slot=1,
        starting_selected_pp=25,
        current_selected_pp=24,
        finish_with_bubblebeam=True,
        enemy_species_id=0xA9,
        active_party_index=1,
    ) == (3, 1, 4)


def test_slowpoke_policy_proves_required_move_then_uses_unresisted_bite() -> None:
    assert lavender_module._ranked_lavender_move_slots(
        move_slot=3,
        starting_selected_pp=20,
        current_selected_pp=20,
        finish_with_bubblebeam=False,
        enemy_species_id=lavender_module.SLOWPOKE_SPECIES_ID,
        active_party_index=0,
    ) == (3, 1, 4)
    assert lavender_module._ranked_lavender_move_slots(
        move_slot=3,
        starting_selected_pp=20,
        current_selected_pp=19,
        finish_with_bubblebeam=False,
        enemy_species_id=lavender_module.SLOWPOKE_SPECIES_ID,
        active_party_index=0,
    ) == (1, 3, 4)
    assert lavender_module._ranked_lavender_move_slots(
        move_slot=1,
        starting_selected_pp=25,
        current_selected_pp=25,
        finish_with_bubblebeam=False,
        enemy_species_id=lavender_module.SLOWPOKE_SPECIES_ID,
        active_party_index=0,
    ) == (1, 3, 4)


def test_status_locked_dux_escapes_to_a_living_story_lead() -> None:
    asleep = replace(
        _raw(),
        active_party_index=0,
        active_party_status=0x04,
    )

    assert lavender_module._dux_status_escape_target(asleep, (20, 50, 30), True) == 1
    assert lavender_module._dux_status_escape_target(asleep, (20, 0, 30), True) is None
    assert (
        lavender_module._dux_status_escape_target(
            replace(asleep, active_party_status=0), (20, 50, 30), True
        )
        is None
    )
    assert lavender_module._dux_status_escape_target(asleep, (20, 50, 30), False) is None


def test_fainted_route_helper_continues_with_the_first_living_teammate() -> None:
    fainted = replace(
        _raw(),
        battle_state=2,
        active_party_index=0,
        active_party_hp=0,
    )

    assert lavender_module._fainted_battler_pivot_target(fainted, (0, 73, 42)) == 1
    assert lavender_module._fainted_battler_pivot_target(fainted, (0, 0, 42)) == 2
    assert lavender_module._fainted_battler_pivot_target(fainted, (0, 0, 0)) is None
    assert (
        lavender_module._fainted_battler_pivot_target(
            replace(fainted, active_party_hp=1),
            (1, 73, 42),
        )
        is None
    )


def test_status_recovery_prefers_a_healthy_pivot_before_spending_awakening() -> None:
    asleep = replace(
        _raw(),
        active_party_index=0,
        active_party_status=0x05,
    )

    assert lavender_module._dux_status_recovery_strategy(
        asleep,
        (20, 50, 30),
        True,
        awakenings=2,
        parlyz_heals=2,
    ) == ("pivot", 1)
    assert lavender_module._dux_status_recovery_strategy(
        asleep,
        (20, 0, 30),
        True,
        awakenings=2,
        parlyz_heals=2,
    ) == ("awakening", None)

    paralyzed_story_lead = replace(
        asleep,
        active_party_index=1,
        active_party_status=0x40,
    )
    assert lavender_module._dux_status_recovery_strategy(
        paralyzed_story_lead,
        (20, 50, 30),
        True,
        awakenings=2,
        parlyz_heals=2,
    ) == ("parlyz_heal", None)
    assert lavender_module._dux_status_recovery_strategy(
        paralyzed_story_lead,
        (20, 50, 30),
        True,
        awakenings=2,
        parlyz_heals=1,
    ) == ("none", None)


def test_story_lead_uses_bite_after_a_dux_grass_status_escape() -> None:
    assert BULBASAUR_SPECIES_ID in FINAL_TUNNEL_GRASS_SPECIES
    assert lavender_module._ranked_lavender_move_slots(
        move_slot=1,
        starting_selected_pp=35,
        current_selected_pp=24,
        finish_with_bubblebeam=False,
        enemy_species_id=next(iter(lavender_module.FINAL_TUNNEL_GRASS_SPECIES)),
        active_party_index=1,
    ) == (1, 3, 4)
    for species in FINAL_TUNNEL_GRASS_SPECIES:
        assert lavender_module._ranked_lavender_move_slots(
            move_slot=1,
            starting_selected_pp=25,
            current_selected_pp=24,
            finish_with_bubblebeam=True,
            enemy_species_id=species,
            active_party_index=0,
        ) == (1, 3, 4)


def test_final_tunnel_role_pivot_tracks_enemy_type_and_live_reserves() -> None:
    grass_against_wartortle = replace(
        _raw(),
        active_party_index=1,
        enemy_species_id=0xB9,
    )

    assert (
        lavender_module._final_tunnel_pivot_target(
            grass_against_wartortle,
            (50, 30, 20),
            True,
        )
        == 0
    )
    assert (
        lavender_module._final_tunnel_pivot_target(
            replace(grass_against_wartortle, active_party_index=0),
            (50, 30, 20),
            True,
        )
        is None
    )
    assert (
        lavender_module._final_tunnel_pivot_target(
            replace(grass_against_wartortle, active_party_index=0, enemy_species_id=0x04),
            (50, 30, 20),
            True,
        )
        == 1
    )
    assert (
        lavender_module._final_tunnel_pivot_target(
            grass_against_wartortle,
            (0, 30, 20),
            True,
        )
        is None
    )
    assert (
        lavender_module._final_tunnel_pivot_target(
            grass_against_wartortle,
            (50, 30, 20),
            False,
        )
        is None
    )
    assert (
        lavender_module._final_tunnel_pivot_target(
            grass_against_wartortle,
            (50, 30, 20),
            True,
            required_move_spent=False,
        )
        is None
    )
    assert (
        lavender_module._final_tunnel_pivot_target(
            grass_against_wartortle,
            (50, 30, 20),
            True,
            dux_unavailable=True,
        )
        is None
    )
    assert (
        lavender_module._final_tunnel_pivot_target(
            replace(grass_against_wartortle, active_party_index=0),
            (50, 30, 20),
            True,
            dux_unavailable=True,
        )
        == 1
    )


def test_final_sleep_reserve_is_prepared_then_restores_the_story_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    runtime = object()
    monkeypatch.setattr(
        lavender_module,
        "_swap",
        lambda *_args, **_kwargs: calls.append(("swap", _args[3])),
    )
    monkeypatch.setattr(
        lavender_module,
        "_heal_if_below",
        lambda *_args, **_kwargs: calls.append(("heal", (_args[5], _args[6]))),
    )
    monkeypatch.setattr(
        lavender_module,
        "_cure_tunnel_status_if_present",
        lambda *_args, **_kwargs: calls.append(("cure", None)),
    )

    lavender_module._prepare_dux_sleep_pivot(
        runtime,
        runtime,
        runtime,
        lavender_module._RunState([], []),
        DEFAULT_LAVENDER_TIMING,
    )

    assert calls == [
        ("swap", lavender_module.DUX),
        ("heal", (0, lavender_module.TRAVERSAL_RECOVERY_THRESHOLD)),
        ("cure", None),
        ("swap", lavender_module.WARTORTLE),
    ]


@pytest.mark.parametrize("sleep_counter", range(1, 8))
def test_tunnel_field_recovery_cures_every_sleep_counter(
    monkeypatch: pytest.MonkeyPatch,
    sleep_counter: int,
) -> None:
    status = sleep_counter
    quantity = 2
    used: list[ItemId] = []
    run = lavender_module._RunState([], [])

    monkeypatch.setattr(lavender_module, "_party_status", lambda _emulator: (status,))
    monkeypatch.setattr(
        lavender_module,
        "_bag",
        lambda _emulator: {ItemId.AWAKENING: quantity},
    )

    def fake_use(*_args: object, **_kwargs: object) -> None:
        nonlocal status, quantity
        used.append(_args[-1])
        status = 0
        quantity -= 1

    monkeypatch.setattr(lavender_module, "_use_bag_item", fake_use)

    lavender_module._cure_tunnel_status_if_present(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        run,
        DEFAULT_LAVENDER_TIMING,
    )

    assert used == [ItemId.AWAKENING]
    assert run.awakenings_used == 1


def test_field_recovery_skips_a_full_hp_target_even_above_its_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = object()
    monkeypatch.setattr(lavender_module, "_party_hp", lambda _emulator: (60, 20, 20))
    monkeypatch.setattr(lavender_module, "_party_max_hp", lambda _emulator: (60, 40, 40))

    assert not lavender_module._heal_if_below(
        runtime,
        runtime,
        runtime,
        lavender_module._RunState([], []),
        LavenderTiming(),
        0,
        90,
    )


def test_wild_flee_accepts_only_declared_purified_zone_restoration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emulator = object()
    before = replace(
        _raw(),
        map_id=MapId.POKEMON_TOWER_5F,
        player_x=11,
        player_y=9,
        battle_state=1,
        first_party_hp=65,
        first_party_max_hp=91,
        first_party_pp=(18, 30, 13, 25),
    )
    final = replace(
        before,
        battle_state=0,
        first_party_hp=91,
        first_party_pp=(25, 30, 20, 25),
    )
    monkeypatch.setattr(lavender_module, "_party_hp", lambda _emulator: (91, 49, 36))
    monkeypatch.setattr(lavender_module, "_party_max_hp", lambda _emulator: (91, 49, 36))
    monkeypatch.setattr(lavender_module, "_party_status", lambda _emulator: (0, 0, 0))
    monkeypatch.setattr(lavender_module, "_bag", lambda _emulator: {})
    monkeypatch.setattr(lavender_module, "_event", lambda _emulator, _event: True)

    rejected = lavender_module._RunState([], [])
    with pytest.raises(lavender_module.LavenderChapterError, match="purified_zone_heal=False"):
        lavender_module._record_wild_flee_evidence(
            before,
            final,
            emulator,
            rejected,
            before.party_species_ids,
            before.first_party_pp,
            (65, 49, 36),
            {},
        )

    accepted = lavender_module._RunState([], [])
    lavender_module._record_wild_flee_evidence(
        before,
        final,
        emulator,
        accepted,
        before.party_species_ids,
        before.first_party_pp,
        (65, 49, 36),
        {},
        allow_purified_zone_heal=True,
    )

    assert len(accepted.wilds) == 1
    assert accepted.wilds[0].pp_preserved
    assert accepted.wilds[0].hp_safe


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_lavender_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(LavenderTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_LAVENDER_TIMING, **{field.name: invalid})


def test_lavender_report_requires_all_route_resource_and_party_gates() -> None:
    report = _report()
    assert report.passed

    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, trainers=report.trainers[:-1]),
        replace(report, trainers=report.trainers[:-1] + (report.trainers[0],)),
        replace(report, party_hp=(78, 52, 37)),
        replace(report, party_status=(0, 8, 0)),
        replace(report, repels_used=3),
        replace(report, parlyz_heals_used=0),
        replace(report, parlyz_heals_remaining=0),
        replace(report, antidotes_remaining=0),
        replace(report, awakenings_remaining=0),
        replace(report, starting_super_potions=4),
        replace(report, super_potions_remaining=3),
        replace(report, purchase_cost=10899),
        replace(report, tm28_sale_proceeds=999),
        replace(report, route_10_trainer_2_bypassed=False),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_lavender_report_accounts_for_a_surge_consumed_starting_potion() -> None:
    report = replace(_report(), starting_super_potions=0, super_potions_used=3)

    assert report.passed


def test_lavender_public_report_exposes_exact_resources_and_trainers() -> None:
    public = _report().public_dict()

    assert public["status"] == "ok"
    assert len(public["trainer_battles"]) == 12
    assert public["inventory"] == {
        "repels_purchased": 4,
        "repels_used": 4,
        "parlyz_heals_purchased": 3,
        "parlyz_heals_used": 2,
        "parlyz_heals_remaining": 1,
        "antidotes_purchased": 1,
        "antidotes_remaining": 1,
        "awakenings_used": 3,
        "awakenings_remaining": 2,
        "awakenings_purchased": 3,
        "starting_super_potions": 1,
        "super_potions_purchased": 15,
        "super_potions_used": 4,
        "super_potions_remaining": 12,
        "purchase_cost": 13200,
        "tm28_sale_proceeds": 1000,
        "money_remaining": 1234,
    }
    assert public["route_10_trainer_2_bypassed"] is True
    assert public["party"]["species"] == list(PROTECTED_PARTY)


def test_move_retries_the_same_step_after_a_no_movement_wild_flee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runtime:
        def __init__(self) -> None:
            self.raw = replace(
                _raw(),
                map_id=MapId.ROUTE_9,
                player_x=1,
                player_y=1,
                battle_state=0,
            )
            self.move_pulses = 0

        def execute(self, action: object) -> None:
            if getattr(action, "kind", None) is not MacroActionKind.MOVE:
                return
            self.move_pulses += 1
            if self.move_pulses == 1:
                self.raw = replace(self.raw, battle_state=1)
            else:
                self.raw = replace(self.raw, player_x=2)

        def read(self) -> RawGameState:
            return self.raw

    runtime = Runtime()

    def qualified_flee(*_args: object) -> None:
        runtime.raw = replace(runtime.raw, battle_state=0)

    monkeypatch.setattr(lavender_module, "_flee", qualified_flee)
    final = lavender_module._move(
        runtime,
        runtime,
        runtime,
        lavender_module._RunState([], []),
        ("right",),
        LavenderTiming(movement_retries=2),
        "wild retry regression",
    )

    assert runtime.move_pulses == 2
    assert (final.player_x, final.player_y) == (2, 1)
