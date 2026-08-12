import ast
import inspect
import textwrap
from dataclasses import replace

import pytest

from pokemon_red_completion import blaine as blaine_module
from pokemon_red_completion.blaine import (
    BLAINE_AFTER_MANSION_CHECKPOINT_COUNT,
    BLAINE_ANTIDOTE_SALE_VALUE,
    BLAINE_CAPACITY_SALE_ITEM,
    BLAINE_CHECKPOINT_COUNT,
    BLAINE_EARLY_BIDE_REPLACEMENT_NET_COST,
    BLAINE_GYM_BURGLAR_SET_4_PARTY,
    BLAINE_GYM_BURGLAR_SET_5_PARTY,
    BLAINE_GYM_TRAINER_INCOME,
    BLAINE_INPUT_BAG_SLOT_BOUNDS,
    BLAINE_MAX_WILD_FLEES,
    BLAINE_MONEY_DELTA,
    BLAINE_PARTY,
    BLAINE_TM21_SALE_VALUE,
    BLAINE_TO_GYM_EXIT,
    CENTER_TO_MANSION,
    DIGLETTS_CAVE_TRAINING_VENUE,
    GYM_GATE_EVENTS,
    GYM_QUIZ_ROUTES,
    GYM_RETURN_TO_BLAINE,
    GYM_TRAINER_EVENTS,
    HYDRO_PUMP_LEARN_LEVEL,
    MANSION_1F_TO_3F,
    MANSION_3F_TO_B1F,
    MANSION_B1F_TO_NORTH_STATUE,
    MANSION_B1F_TO_SECRET_KEY,
    MANSION_DEVELOPMENT_POLICY,
    MANSION_DIG_RETURN_MAPS,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_SECRET_KEY_CHECKPOINT_COUNT,
    MANSION_TEAM_POLICY,
    MANSION_TRAINER_EVENTS,
    MANSION_TRAINING_POLICY,
    MANSION_TRAINING_VENUE,
    MANSION_VOLATILE_ENEMY_SPECIES,
    PRE_SAFFRON_BALANCED_ROSTER,
    PRE_SAFFRON_DEVELOPMENT_POLICY,
    PRE_SAFFRON_TEAM_POLICY,
    QUIZ_ANSWERS,
    QUIZ_CORRECT_ANSWERS,
    QUIZ_TEXT_PULSES,
    QUIZ_TRAINER_BATTLE_INDEXES,
    ROUTE_11_TRAINING_VENUE,
    BlaineChapterError,
    BlaineCheckpoint,
    BlaineTurn,
    CinnabarGymTrainerReceipt,
    MansionSecretKeyReport,
    _blaine_capacity_input_slots,
    _blaine_capacity_plan,
    _encounter_party,
    _mansion_training_fainted_pivot_target,
    _mansion_training_move_slot,
    _sell_antidote_before_mansion,
    _settle_mansion_training_forced_switch,
    _team_training_move_guard,
    _team_training_move_slot,
    _tm38_capacity_sale_required,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RawGameState
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation
from pokemon_red_completion.red_team_training import (
    _PauseForTeamTrainingRecovery,
    run_red_team_balancing,
    trainee_should_fight_directly,
)
from pokemon_red_completion.red_team_training import (
    battle_command_direction as _battle_command_direction,
)
from pokemon_red_completion.red_team_training import (
    red_training_matchup_acceptable as _red_training_matchup_acceptable,
)
from pokemon_red_completion.red_team_training import (
    training_attack_pp as _training_attack_pp,
)
from pokemon_red_completion.red_team_training import (
    training_attack_pp_reserve as _training_attack_pp_reserve,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy


def test_blaine_training_calls_only_use_the_shared_balancer_signature() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(blaine_module.run_blaine_chapter)))
    allowed_keywords = set(inspect.signature(run_red_team_balancing).parameters)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_red_team_balancing"
    ]

    assert len(calls) == 2
    assert [
        keyword.arg
        for call in calls
        for keyword in call.keywords
        if keyword.arg not in allowed_keywords
    ] == []
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert ast.dump(keywords["candidate_decision_sink"]) == ast.dump(
            ast.Name(id="training_candidate_decision_sink", ctx=ast.Load())
        )
        assert ast.dump(keywords["candidate_decision_authority"]) == ast.dump(
            ast.Name(id="training_candidate_decision_authority", ctx=ast.Load())
        )


def test_mansion_and_gym_routes_are_source_and_live_stable() -> None:
    assert BLAINE_CHECKPOINT_COUNT == 9
    assert MANSION_SECRET_KEY_CHECKPOINT_COUNT == 4
    assert len(MANSION_1F_TO_3F) == 36
    assert len(MANSION_3F_TO_B1F) == 34
    assert len(MANSION_B1F_TO_NORTH_STATUE) == 54
    assert len(MANSION_B1F_TO_SECRET_KEY) == 35
    assert tuple(len(route) for route in GYM_QUIZ_ROUTES) == (14, 23, 11, 12, 12, 12)
    assert QUIZ_CORRECT_ANSWERS == (True, False, False, False, True, False)
    assert QUIZ_ANSWERS == (False, False, True, False, True, False)
    assert QUIZ_TRAINER_BATTLE_INDEXES == (1, 3)
    assert QUIZ_TEXT_PULSES == (9, 10, 9, 11, 11, 9)
    assert len(BLAINE_TO_GYM_EXIT) == len(GYM_RETURN_TO_BLAINE) == 59
    assert BLAINE_CAPACITY_SALE_ITEM is ItemId.ANTIDOTE
    assert BLAINE_INPUT_BAG_SLOT_BOUNDS == (15, 20)
    assert BLAINE_EARLY_BIDE_REPLACEMENT_NET_COST == 1_300
    assert BLAINE_GYM_TRAINER_INCOME == 6_930
    assert BLAINE_MONEY_DELTA == 11_933
    assert BLAINE_ANTIDOTE_SALE_VALUE == 50
    assert BLAINE_MAX_WILD_FLEES == 3
    assert MANSION_DIG_RETURN_MAPS == (
        MapId.CINNABAR_ISLAND,
        MapId.CELADON_CITY,
        MapId.SAFFRON_CITY,
        MapId.VERMILION_CITY,
    )
    assert CENTER_TO_MANSION == (
        ("down",) * 5 + ("right",) * 7 + ("up",) * 7 + ("left", "up") + ("left",) * 11 + ("up",)
    )
    assert MANSION_TRAINING_POLICY.target_level == 60
    assert HYDRO_PUMP_LEARN_LEVEL == 52
    assert MANSION_TRAINING_POLICY.max_battles < MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL
    assert MANSION_TRAINING_POLICY.preferred_move_slots == (4, 2, 3, 1)
    assert MANSION_TRAINING_POLICY.max_battles == 800
    assert MANSION_DEVELOPMENT_POLICY.workhorse_target_level == 60
    assert MANSION_DEVELOPMENT_POLICY.workhorse_species_id in (
        MANSION_DEVELOPMENT_POLICY.roster.species_ids
    )
    assert MANSION_TEAM_POLICY.required_size == 6
    assert PRE_SAFFRON_TEAM_POLICY.required_size == 4
    assert PRE_SAFFRON_DEVELOPMENT_POLICY.roster is PRE_SAFFRON_BALANCED_ROSTER
    assert set(PRE_SAFFRON_BALANCED_ROSTER.species_ids) < set(
        MANSION_DEVELOPMENT_POLICY.roster.species_ids
    )
    assert MANSION_TEAM_POLICY.max_battles == 7_000
    assert MANSION_TEAM_POLICY.max_battles < MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL
    assert MANSION_TEAM_POLICY.max_healing_trips == 2_000
    assert MANSION_TEAM_POLICY.minimum_direct_level_advantage == 5
    assert MANSION_TEAM_POLICY.max_enemy_level_delta == 0
    assert ROUTE_11_TRAINING_VENUE.band.area_id == "route_11"
    assert ROUTE_11_TRAINING_VENUE.map_id == int(MapId.ROUTE_11)
    assert ROUTE_11_TRAINING_VENUE.battle_timing.max_sleep_reapplications == 4
    assert MANSION_MAX_CONSECUTIVE_FLEES == 32
    assert frozenset({0x76, 0x88}) == MANSION_ESCORT_ENEMY_SPECIES
    assert frozenset({0x37, 0x8F}) == MANSION_VOLATILE_ENEMY_SPECIES


def test_mansion_only_runner_stops_before_training_and_blaine() -> None:
    tree = ast.parse(
        textwrap.dedent(inspect.getsource(blaine_module.run_mansion_secret_key_chapter))
    )
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "_pick_up_secret_key" in calls
    assert "_return_from_mansion_to_cinnabar" in calls
    assert "run_red_team_balancing" not in calls
    assert "_run_mansion_training" not in calls
    assert "run_adaptive_trainer_battle" not in calls


def test_post_mansion_runner_does_not_repeat_the_secret_key_route() -> None:
    tree = ast.parse(
        textwrap.dedent(inspect.getsource(blaine_module.run_blaine_after_mansion_chapter))
    )
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert BLAINE_AFTER_MANSION_CHECKPOINT_COUNT == 5
    assert "_pick_up_secret_key" not in calls
    assert "_move_mansion" not in calls
    assert "run_red_team_balancing" in calls
    assert "run_adaptive_trainer_battle" in calls


def test_mansion_only_report_requires_key_and_preserves_blaine_boundary() -> None:
    terminal = RawGameState(
        game_started=True,
        map_id=MapId.CINNABAR_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=6,
        battle_state=0,
        party_species_ids=(28, 64, 59, 132, 104, 43),
        first_party_hp=150,
        first_party_max_hp=150,
    )
    records = tuple(
        BlaineCheckpoint(f"mansion_{index}", f"Mansion {index}", terminal)
        for index in range(MANSION_SECRET_KEY_CHECKPOINT_COUNT)
    )
    report = MansionSecretKeyReport(
        records=records,
        final_raw=terminal,
        switch_trace=(False, True, False, True),
        trainer_events_before=(False,) * 6,
        trainer_events_after=(False,) * 6,
        wild_flees=(),
        secret_key_quantity=1,
        tm14_quantity=1,
        x_accuracy_retained=True,
        blaine_defeated=False,
        volcano_badge=False,
        initial_bag_slots=17,
        final_bag_slots=19,
        party_hp=(150, 53, 37, 144, 75, 79),
        party_max_hp=(150, 53, 37, 144, 75, 79),
        party_status=(0,) * 6,
        frames_executed=400_000,
        actions_executed=3_000,
        controller_released=True,
    )

    assert report.passed
    assert report.public_dict()["blaine_untouched"] is True
    assert not replace(report, blaine_defeated=True).passed


def test_blaine_antidote_capacity_plan_handles_consumed_and_retained_fillers() -> None:
    assert not _sell_antidote_before_mansion(16, 2)
    assert not _sell_antidote_before_mansion(17, 1)
    assert not _sell_antidote_before_mansion(18, 0)
    assert not _sell_antidote_before_mansion(18, 1)
    assert not _sell_antidote_before_mansion(18, 2)
    assert not _sell_antidote_before_mansion(19, 0)
    assert _sell_antidote_before_mansion(19, 1)
    assert _sell_antidote_before_mansion(19, 2)
    assert _sell_antidote_before_mansion(19, 3)
    assert _sell_antidote_before_mansion(20, 1)
    with pytest.raises(BlaineChapterError, match="Unsupported Blaine Antidote capacity"):
        _sell_antidote_before_mansion(19, 100)
    assert BLAINE_TM21_SALE_VALUE == 2_500


def test_post_mansion_blaine_accepts_both_cartridge_reward_boundaries() -> None:
    assert not _tm38_capacity_sale_required(got_tm38=True, occupied_bag_slots=19)
    assert _tm38_capacity_sale_required(got_tm38=False, occupied_bag_slots=20)
    with pytest.raises(BlaineChapterError, match="withheld TM38 without a full bag"):
        _tm38_capacity_sale_required(got_tm38=False, occupied_bag_slots=19)


def test_blaine_replaces_an_early_sold_bide_capacity_slot() -> None:
    assert _blaine_capacity_plan(15, bide_present=False) == (True, True, 2, 16)
    assert _blaine_capacity_plan(16, bide_present=False) == (True, False, 2, 17)
    assert _blaine_capacity_plan(17, bide_present=True) == (False, False, 2, 17)
    assert _blaine_capacity_plan(19, bide_present=False) == (True, False, 1, 20)


def test_blaine_sells_obsolete_potions_for_capacity_bound_inputs() -> None:
    assert _blaine_capacity_input_slots(18, 5, bide_present=False) == (18, 0)
    assert _blaine_capacity_input_slots(19, 5, bide_present=True) == (19, 0)
    assert _blaine_capacity_input_slots(19, 5, bide_present=False) == (18, 5)
    assert _blaine_capacity_input_slots(20, 5, bide_present=True) == (19, 5)
    assert _blaine_capacity_input_slots(20, 5, bide_present=False) == (19, 5)
    assert _blaine_capacity_input_slots(
        18,
        6,
        bide_present=False,
        force_potion_sale=True,
    ) == (17, 6)
    with pytest.raises(BlaineChapterError, match="unsupported input lineage"):
        _blaine_capacity_input_slots(
            17,
            6,
            bide_present=False,
            force_potion_sale=True,
        )


def test_team_training_navigates_the_two_column_battle_menu() -> None:
    assert _battle_command_direction(0, 2) == "right"
    assert _battle_command_direction(1, 2) == "right"
    assert _battle_command_direction(3, 2) == "up"
    assert _battle_command_direction(2, 2) is None
    assert _battle_command_direction(None, 2) is None


def test_lead_training_skips_a_live_disabled_move() -> None:
    raw = RawGameState(
        True,
        MapId.POKEMON_MANSION_1F,
        5,
        20,
        6,
        1,
        active_party_hp=172,
        active_party_max_hp=172,
        first_party_pp=(8, 4, 0, 3),
        player_disabled_move_slot=4,
        player_disable_turns=3,
    )

    assert _mansion_training_move_slot(raw) == 2
    with pytest.raises(_PauseForTeamTrainingRecovery):
        _mansion_training_move_slot(
            replace(raw, first_party_pp=(8, 0, 0, 0), player_disabled_move_slot=1)
        )
    with pytest.raises(_PauseForTeamTrainingRecovery):
        _mansion_training_move_slot(
            replace(
                raw,
                active_party_hp=154,
                active_party_max_hp=172,
                first_party_pp=(8, 4, 0, 3),
            )
        )


def test_mansion_training_fainted_pivot_uses_the_healthiest_living_reserve() -> None:
    fainted = RawGameState(
        True,
        MapId.POKEMON_MANSION_1F,
        5,
        20,
        6,
        1,
        active_party_hp=0,
    )

    assert _mansion_training_fainted_pivot_target(
        fainted,
        (0, 71, 0, 142, 88, 109),
    ) == 3
    assert _mansion_training_fainted_pivot_target(fainted, (0, 0, 0)) is None
    assert _mansion_training_fainted_pivot_target(
        replace(fainted, active_party_hp=1),
        (1, 71, 142),
    ) is None
    assert _mansion_training_fainted_pivot_target(
        replace(fainted, battle_state=0),
        (0, 71, 142),
    ) is None


def test_mansion_training_forced_switch_retries_a_transient_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def switch(*args: object, **kwargs: object) -> None:
        calls.append(int(args[3]))
        if len(calls) < 3:
            raise blaine_module.ProtectedRecoveryError("still settling")

    monkeypatch.setattr(blaine_module, "switch_active_battler", switch)

    _settle_mansion_training_forced_switch(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        4,
    )

    assert calls == [4, 4, 4]


def test_team_training_selects_damaging_moves_for_the_active_species() -> None:
    base = RawGameState(
        True,
        MapId.POKEMON_MANSION_1F,
        5,
        20,
        3,
        1,
        first_party_hp=100,
        first_party_max_hp=100,
    )

    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x1C,
                active_party_moves=(0x82, 0x46, 0x3A, 0x39),
                active_party_pp=(15, 15, 10, 15),
            )
        )
        == 4
    )
    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x40,
                active_party_moves=(0x40, 0x1C, 0x0F, 0x13),
                active_party_pp=(35, 15, 30, 15),
            )
        )
        == 3
    )


def test_team_training_requests_escape_when_all_species_attacks_are_unusable() -> None:
    base = RawGameState(
        True,
        MapId.POKEMON_MANSION_1F,
        5,
        20,
        3,
        1,
        first_party_hp=100,
        first_party_max_hp=100,
    )

    with pytest.raises(_PauseForTeamTrainingRecovery):
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x40,
                active_party_moves=(0x40, 0x1C, 0x0F, 0x13),
                active_party_pp=(0, 15, 0, 15),
            )
        )
    with pytest.raises(_PauseForTeamTrainingRecovery):
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x40,
                active_party_moves=(0x40, 0x1C, 0x0F, 0x13),
                active_party_pp=(35, 15, 0, 15),
                player_disabled_move_slot=1,
            )
        )
    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x84,
                active_party_moves=(0x22, 0x85, 0x9C, 0),
                active_party_pp=(15, 4, 10, 0),
            )
        )
        == 1
    )
    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x3B,
                active_party_moves=(0x0A, 0x2D, 0x5B, 0x1C),
                active_party_pp=(35, 40, 10, 15),
            )
        )
        == 1
    )
    assert (
        _team_training_move_slot(
            replace(
                base,
                active_party_species_id=0x76,
                active_party_moves=(0x0A, 0x2D, 0x5B, 0xA3),
                active_party_pp=(35, 40, 10, 20),
            )
        )
        == 4
    )


def test_team_training_requests_escape_after_live_hp_crosses_retreat_floor() -> None:
    base = RawGameState(
        True,
        MapId.POKEMON_MANSION_1F,
        5,
        20,
        3,
        1,
        first_party_hp=90,
        first_party_max_hp=100,
        active_party_species_id=0x3B,
        active_party_moves=(0x0A, 0x2D, 0x5B, 0x1C),
        active_party_pp=(35, 40, 10, 15),
    )

    with pytest.raises(_PauseForTeamTrainingRecovery):
        _team_training_move_slot(base)

    assert _team_training_move_slot(replace(base, first_party_hp=91)) == 1


def test_balanced_training_venues_bind_the_policy_independent_retreat_guard() -> None:
    assert all(
        venue.move_guard is _team_training_move_guard
        for venue in (
            ROUTE_11_TRAINING_VENUE,
            DIGLETTS_CAVE_TRAINING_VENUE,
            MANSION_TRAINING_VENUE,
        )
    )


def test_the_policy_margin_governs_and_no_species_silently_overrides_it() -> None:
    """A per-species table used to outrank the policy inside this gate.

    It demanded fifteen levels for Farfetch\'d and eight for Diglett and
    Dugtrio, none of it measured, and those three species are the trainees, so
    it bound hardest on the members being trained. The margin is the policy's
    to state; the gate no longer adds a hidden species-level requirement.
    """

    dux = PartyMemberObservation(
        slot=1,
        species_id=0x40,
        level=45,
        hp=100,
        max_hp=100,
        moves=(MoveObservation(0x0F, 30),),
    )
    policy = BalancedTeamPolicy(
        required_size=3,
        max_enemy_level_delta=0,
        minimum_direct_level_advantage=8,
    )

    # The policy permits up to level 37 (45 - 8), and that is what applies.
    assert _red_training_matchup_acceptable(dux, 37, policy)
    assert not _red_training_matchup_acceptable(dux, 38, policy)
    # The retired table would have refused this one at 31; it no longer speaks.
    assert _red_training_matchup_acceptable(dux, 31, policy)
    # Muk stays excluded outright, which is what this gate is actually for.
    assert not _red_training_matchup_acceptable(dux, 20, policy, 0x88)
    assert _training_attack_pp_reserve(dux, policy) == 6

    dux_with_only_fly = replace(
        dux,
        moves=(
            MoveObservation(0x40, 0),
            MoveObservation(0x1C, 15),
            MoveObservation(0x0F, 0),
            MoveObservation(0x13, 15),
        ),
    )
    assert _training_attack_pp(dux_with_only_fly) == 0

    dugtrio = replace(dux, species_id=0x76, moves=(MoveObservation(0x5B, 10),))
    assert _training_attack_pp_reserve(dugtrio, policy) == 2


def test_team_training_refuses_an_opponents_super_effective_stab_type() -> None:
    """A level lead alone cannot protect Jolteon from a Ground attacker."""

    policy = BalancedTeamPolicy(
        minimum_level=55,
        max_enemy_level_delta=0,
        minimum_direct_level_advantage=5,
    )
    jolteon = PartyMemberObservation(
        slot=1,
        species_id=0x68,
        level=25,
        hp=75,
        max_hp=75,
        moves=(MoveObservation(0x54, 15), MoveObservation(0x18, 30)),
    )
    dux = replace(jolteon, species_id=0x40, level=20)
    diglett = replace(jolteon, species_id=0x3B, level=23)

    assert not _red_training_matchup_acceptable(jolteon, 19, policy, 0x3B)
    assert _red_training_matchup_acceptable(dux, 15, policy, 0x3B)
    assert _red_training_matchup_acceptable(diglett, 17, policy, 0x3B)


def test_targeted_evolution_earns_participation_without_directly_fighting() -> None:
    trainee = PartyMemberObservation(
        slot=1,
        species_id=0x3B,
        level=23,
        hp=38,
        max_hp=38,
        moves=(MoveObservation(0x5B, 10),),
    )
    policy = BalancedTeamPolicy(
        minimum_level=55,
        minimum_direct_level_advantage=5,
    )

    assert trainee_should_fight_directly(
        trainee,
        enemy_level=17,
        enemy_species=0x3B,
        policy=policy,
    )
    assert not trainee_should_fight_directly(
        trainee,
        enemy_level=17,
        enemy_species=0x3B,
        policy=policy,
        participation_only=True,
    )





def test_blaine_source_ids_are_exact() -> None:
    assert MapId.POKEMON_MANSION_1F == 0xA5
    assert MapId.CINNABAR_GYM == 0xA6
    assert MapId.CINNABAR_MART == 0xAC
    assert MapId.POKEMON_MANSION_2F == 0xD6
    assert MapId.POKEMON_MANSION_3F == 0xD7
    assert MapId.POKEMON_MANSION_B1F == 0xD8
    assert ItemId.SECRET_KEY == 0x2B
    assert ItemId.TM14_BLIZZARD == 0xD6
    assert ItemId.TM38_FIRE_BLAST == 0xEE
    assert EventFlag.MANSION_SWITCH_ON == 0x278
    assert EventFlag.GOT_TM38 == 0x298
    assert EventFlag.BEAT_BLAINE == 0x299
    assert tuple(int(event) for event in GYM_TRAINER_EVENTS) == tuple(range(0x29A, 0x2A1))
    assert tuple(int(event) for event in GYM_GATE_EVENTS) == tuple(range(0x2A8, 0x2AF))
    assert tuple(int(event) for event in MANSION_TRAINER_EVENTS) == (
        0x289,
        0x801,
        0x811,
        0x812,
        0x821,
        0x822,
    )


def test_blaine_turn_receipt_collapses_repeated_arcanine_turns() -> None:
    turns = (
        BlaineTurn(0x21, 42, 104, 142, 0, (15, 15, 10, 15), 4),
        BlaineTurn(0xA3, 40, 96, 142, 0, (15, 15, 10, 14), 4),
        BlaineTurn(0xA4, 42, 113, 142, 0, (15, 15, 10, 13), 4),
        BlaineTurn(0x14, 47, 149, 142, 0, (15, 15, 10, 12), 4),
        BlaineTurn(0x14, 47, 76, 142, 0, (15, 15, 10, 11), 4),
    )

    assert _encounter_party(turns) == BLAINE_PARTY


def test_cinnabar_burglar_receipts_pin_party_identity_move_and_income() -> None:
    set_4_turns = tuple(
        BlaineTurn(species, level, 50, 180, 0, (5, 15, 10, 15), 4)
        for species, level in BLAINE_GYM_BURGLAR_SET_4_PARTY
    )
    receipt = CinnabarGymTrainerReceipt(
        quiz_index=1,
        identity=(0xD3, 0xD3, 4),
        expected_party=BLAINE_GYM_BURGLAR_SET_4_PARTY,
        turns=set_4_turns,
        money_before=389,
        money_after=3_629,
        expected_reward=3_240,
    )
    assert receipt.passed
    assert not replace(receipt, money_after=3_628).passed
    assert not replace(receipt, identity=(0xD3, 0xD3, 5)).passed

    set_5_turns = tuple(
        BlaineTurn(species, level, 50, 180, 0, (5, 15, 10, 11), 4)
        for species, level in BLAINE_GYM_BURGLAR_SET_5_PARTY
    )
    assert CinnabarGymTrainerReceipt(
        quiz_index=3,
        identity=(0xD3, 0xD3, 5),
        expected_party=BLAINE_GYM_BURGLAR_SET_5_PARTY,
        turns=set_5_turns,
        money_before=3_629,
        money_after=7_319,
        expected_reward=3_690,
    ).passed


def test_mansion_training_targets_the_league_not_an_internal_spread() -> None:
    """A measured run overshot parity by 19 levels chasing the escort's level."""

    from pokemon_red_completion.blaine import (
        COMPLETION_LEVEL_PARITY,
        INDIGO_MAX_OPPOSITION_LEVEL,
        MANSION_TEAM_POLICY,
    )

    # The floor states why it is what it is, rather than being a hand-tuned constant.
    assert MANSION_TEAM_POLICY.minimum_level == COMPLETION_LEVEL_PARITY.required_level(
        INDIGO_MAX_OPPOSITION_LEVEL
    )
    assert MANSION_TEAM_POLICY.minimum_level == 55
    # A natural playthrough arrives below the League, not above it.
    assert MANSION_TEAM_POLICY.minimum_level < INDIGO_MAX_OPPOSITION_LEVEL

    # The spread must not be able to drag trainees toward an overlevelled escort.
    escort_level = 84
    assert MANSION_TEAM_POLICY.maximum_level_spread >= (
        escort_level - MANSION_TEAM_POLICY.minimum_level
    )


def test_mansion_policy_stops_once_the_party_reaches_league_parity() -> None:
    from pokemon_red_completion.blaine import MANSION_TEAM_POLICY
    from pokemon_red_completion.party import (
        MoveObservation,
        PartyMemberObservation,
        PartyObservation,
    )
    from pokemon_red_completion.team_training import (
        TeamTrainingDirective,
        plan_team_training,
    )

    def member(slot: int, level: int) -> PartyMemberObservation:
        return PartyMemberObservation(
            slot=slot,
            species_id=slot,
            level=level,
            hp=200,
            max_hp=200,
            moves=(MoveObservation(55, 15, 15),),
        )

    # An escort far above parity no longer keeps the block running.
    at_parity = PartyObservation(
        members=(member(1, 84), *(member(slot, 55) for slot in range(2, 7)))
    )
    assert (
        plan_team_training(at_parity, MANSION_TEAM_POLICY).directive
        is TeamTrainingDirective.STOP
    )

    # A member genuinely short of the League still trains.
    below = PartyObservation(
        members=(member(1, 84), member(2, 30), *(member(slot, 55) for slot in range(3, 7)))
    )
    assert (
        plan_team_training(below, MANSION_TEAM_POLICY).directive
        is not TeamTrainingDirective.STOP
    )
