"""Independent state transitions distinguish attempt, effect and safe exit."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_capture_status_runtime as runtime
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    RawGameState,
    WildCaptureIdentity,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_autonomous_player import _exception_chain


class World:
    def __init__(self):
        self.raw = RawGameState(
            True,
            35,
            5,
            30,
            2,
            1,
            enemy_species_id=108,
            enemy_hp=25,
            active_party_index=0,
            active_party_hp=50,
            active_party_max_hp=50,
            party_species_ids=(48, 28),
            bag_items=((4, 4),),
        )
        self.party = PartyObservation(
            (
                PartyMemberObservation(1, 48, 13, 50, 50, moves=(MoveObservation(95, 10),)),
                PartyMemberObservation(2, 28, 63, 200, 200, moves=(MoveObservation(57, 10),)),
            )
        )
        self.status = 0
        self.turns = 0
        self.boundaries = 0

    def read(self):
        return self.raw

    def read_enemy_capture_status(self):
        return self.status

    def read_wild_capture_identity(self):
        if self.raw.battle_state != 1 or (self.raw.enemy_hp or 0) <= 0:
            return None
        return WildCaptureIdentity(
            self.raw.enemy_species_id,
            self.raw.enemy_species_id,
            False,
            (0, 0),
        )

    def read_enemy_capture_moves(self):
        return (33, 45, 0, 0)

    def turn(self, *_args, **kwargs):
        assert kwargs["selected_slot"] == 1
        assert kwargs["expected_battle_state"] == 1
        self.turns += 1
        first = self.party.members[0]
        self.party = replace(
            self.party,
            members=(
                replace(first, moves=(replace(first.moves[0], current_pp=10 - self.turns),)),
                self.party.members[1],
            ),
        )
        return SimpleNamespace(move_executed=True)


def setup(monkeypatch):
    world = World()
    monkeypatch.setattr(
        runtime, "PokemonRedPartyReader", lambda _: SimpleNamespace(read=lambda: world.party)
    )
    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", world.turn)

    def boundary(*_args, **_kwargs):
        world.boundaries += 1

    monkeypatch.setattr(runtime, "advance_battle_to_policy_boundary", boundary)

    def switch(_actions, _reader, _emulator, index, **_kwargs):
        world.raw = replace(world.raw, active_party_index=index)

    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    return world, runtime.RedCaptureStatusPreparer(object(), object(), world)


@pytest.mark.parametrize("stale_hp", [None, 0, 25, 54])
def test_target_hp_is_latched_after_introduction_initializes_opponent(monkeypatch, stale_hp):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, enemy_hp=stale_hp)

    def initialize(*_args, **_kwargs):
        world.boundaries += 1
        if world.boundaries == 1:
            world.raw = replace(world.raw, enemy_hp=63, enemy_max_hp=63)

    monkeypatch.setattr(runtime, "advance_battle_to_policy_boundary", initialize)
    assert prepare()
    assert world.turns == 3
    assert all(row["target_hp_before"] == row["target_hp_after"] == 63 for row in prepare.reports)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"party_species_ids": (48,)}, runtime.CaptureStatusDrift.PARTY_SPECIES),
        ({"bag_items": ((4, 3),)}, runtime.CaptureStatusDrift.BAG_ITEMS),
    ],
)
def test_introduction_still_protects_party_and_bag(monkeypatch, change, reason):
    world, prepare = setup(monkeypatch)

    def drift(*_args, **_kwargs):
        world.raw = replace(world.raw, **change)

    monkeypatch.setattr(runtime, "advance_battle_to_policy_boundary", drift)
    with pytest.raises(runtime.RedCaptureStatusError) as stopped:
        prepare()
    assert stopped.value.reason_code == reason.value
    assert world.turns == 0 and prepare.attempts == 0


def test_failed_introduction_does_not_latch_target_or_spend_status_attempt(monkeypatch):
    world, prepare = setup(monkeypatch)

    def timeout(*_args, **_kwargs):
        raise RuntimeError("bounded introduction expired")

    monkeypatch.setattr(runtime, "advance_battle_to_policy_boundary", timeout)
    with pytest.raises(RuntimeError, match="bounded introduction expired"):
        prepare()
    assert prepare.latched_original_species_id is None
    assert prepare.attempts == world.turns == 0


def test_settled_original_identity_must_match_declared_capture_target(monkeypatch):
    world, prepare = setup(monkeypatch)
    prepare.expected_original_species_id = 185
    with pytest.raises(runtime.RedCaptureStatusError) as stopped:
        prepare()
    assert stopped.value.reason_code == runtime.CaptureStatusDrift.ORIGINAL_SPECIES.value
    assert prepare.latched_original_species_id is None
    assert prepare.attempts == world.turns == 0


def test_live_capture_binds_requested_species_before_intro_settlement(monkeypatch):
    import pokemon_red_completion.surge as surge
    from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref

    world, _ = setup(monkeypatch)
    target = red_species_ref(red_internal_species_number(world.raw.enemy_species_id))

    def changed_spawn(*_args, before_throw, **_kwargs):
        world.raw = replace(world.raw, enemy_species_id=185)
        return before_throw()

    monkeypatch.setattr(surge, "_try_catch_wild", changed_spawn)
    capture = surge.LiveWildEncounterExecutor(
        object(),
        object(),
        world,
        surge.DEFAULT_SURGE_TIMING,
        label="declared capture",
        capture_status_support=True,
    )
    with pytest.raises(runtime.RedCaptureStatusError) as stopped:
        capture.capture_encounter(target)
    assert stopped.value.reason_code == runtime.CaptureStatusDrift.ORIGINAL_SPECIES.value
    assert world.turns == 0


def test_volatile_capture_identity_is_not_read_before_initialization(monkeypatch):
    world, prepare = setup(monkeypatch)
    identity = world.read_wild_capture_identity

    def initialized_identity():
        assert world.boundaries > 0
        return identity()

    monkeypatch.setattr(world, "read_wild_capture_identity", initialized_identity)
    assert prepare()


@pytest.mark.parametrize("hp", [18, 25])
def test_already_settled_main_needs_no_introduction_input_or_full_hp(monkeypatch, hp):
    from pokemon_red_completion.battle_runtime import advance_battle_to_policy_boundary

    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, enemy_hp=hp, enemy_max_hp=25, active_party_index=1)
    world.status = 3
    monkeypatch.setattr(
        world,
        "read_battle_menu_state",
        lambda _: BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0),
        raising=False,
    )
    monkeypatch.setattr(
        runtime, "advance_battle_to_policy_boundary", advance_battle_to_policy_boundary
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("already settled asleep target requires no setup input")

    prepare.actions = SimpleNamespace(execute=forbidden)
    monkeypatch.setattr(runtime, "switch_active_battler", forbidden)
    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", forbidden)
    assert prepare()
    assert prepare.throw_preparations[0]["target_hp"] == hp
    assert prepare.attempts == 0


def test_preserved_frozen_catcher_can_throw_at_observed_status_without_switch(monkeypatch):
    world, prepare = setup(monkeypatch)
    prepare.preserve_viable_active = True
    world.status = 0x40
    world.party = replace(
        world.party,
        members=(
            replace(world.party.members[0], status=StatusCondition.FREEZE),
            world.party.members[1],
        ),
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("a living frozen catcher can use the ball menu without a switch")

    monkeypatch.setattr(runtime, "switch_active_battler", forbidden)
    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", forbidden)
    assert prepare()
    assert prepare.attempts == world.turns == 0
    assert prepare.throw_preparations[0]["target_status"] == "paralysis"
    assert world.raw.enemy_hp == 25 and world.raw.bag_items == ((4, 4),)


def test_frozen_catcher_preservation_does_not_override_default_switch_policy(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.status = 0x40
    world.party = replace(
        world.party,
        members=(
            replace(world.party.members[0], status=StatusCondition.FREEZE),
            world.party.members[1],
        ),
    )
    assert prepare()
    assert world.raw.active_party_index == 1


@pytest.mark.parametrize(
    "floor,hp,level,status,expected_slot",
    [
        (70, 175, 70, StatusCondition.PARALYSIS, 0),
        (None, 175, 70, StatusCondition.PARALYSIS, 1),
        (70, 175, 69, StatusCondition.PARALYSIS, 1),
        (70, 117, 70, StatusCondition.PARALYSIS, 1),
        (70, 0, 70, StatusCondition.PARALYSIS, 1),
        (70, 175, 70, StatusCondition.POISON, 1),
        (70, 175, 70, StatusCondition.BURN, 1),
    ],
)
def test_prepared_paralyzed_catcher_can_throw_without_unnecessary_switch(
    monkeypatch,
    floor,
    hp,
    level,
    status,
    expected_slot,
):
    world, prepare = setup(monkeypatch)
    prepare.preserve_viable_active = True
    prepare.minimum_prepared_helper_level = floor
    world.status = 0x40
    world.party = PartyObservation(
        (
            PartyMemberObservation(
                1, 131, level, hp, 235, status=status, moves=(MoveObservation(86, 19),)
            ),
            PartyMemberObservation(2, 28, 100, 331, 331, moves=(MoveObservation(57, 10),)),
        )
    )
    assert prepare()
    assert world.raw.active_party_index == expected_slot
    assert world.turns == prepare.attempts == 0
    assert prepare.throw_preparations[-1]["target_status"] == "paralysis"


@pytest.mark.parametrize(
    "floor,hp,level,pp,expected_slot",
    [
        (None, 138, 56, 10, 1),
        (55, 138, 56, 10, 0),
        (55, 95, 56, 10, 1),
        (55, 138, 30, 10, 1),
        (55, 138, 56, 0, 1),
    ],
)
def test_explicit_prepared_helper_avoids_sleep_wasting_switch_without_weakening_health_or_pp(
    monkeypatch,
    floor,
    hp,
    level,
    pp,
    expected_slot,
):
    world, prepare = setup(monkeypatch)
    prepare.preserve_viable_active = True
    prepare.minimum_prepared_helper_level = floor
    world.status = 3
    world.party = PartyObservation(
        (
            PartyMemberObservation(1, 48, level, hp, 190, moves=(MoveObservation(95, pp),)),
            PartyMemberObservation(2, 28, 100, 331, 331, moves=(MoveObservation(57, 10),)),
        )
    )
    assert prepare()
    assert world.raw.active_party_index == expected_slot
    assert world.turns == prepare.attempts == 0


def test_prepared_level_floor_excludes_unprepared_status_reserve(monkeypatch):
    world, prepare = setup(monkeypatch)
    prepare.preserve_viable_active = True
    prepare.minimum_prepared_helper_level = 55
    assert prepare()
    assert world.turns == prepare.attempts == 0
    assert prepare.throw_preparations[-1]["target_status"] == StatusCondition.HEALTHY.value


@pytest.mark.parametrize("floor", [0, 101, True, 55.0])
def test_invalid_prepared_helper_floor_rejected_before_input(floor):
    with pytest.raises(ValueError, match="prepared capture helper"):
        runtime.RedCaptureStatusPreparer(
            object(),
            object(),
            object(),
            preserve_viable_active=True,
            minimum_prepared_helper_level=floor,
        )


@pytest.mark.parametrize("hp", [24, 26])
def test_setup_switch_still_rejects_any_target_hp_change(monkeypatch, hp):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1)

    def drift(*_args, **_kwargs):
        world.raw = replace(world.raw, enemy_hp=hp)

    monkeypatch.setattr(runtime, "switch_active_battler", drift)
    with pytest.raises(runtime.RedCaptureStatusError) as stopped:
        prepare()
    assert stopped.value.reason_code == runtime.CaptureStatusDrift.TARGET_HP.value
    assert world.turns == prepare.attempts == 0


@pytest.mark.parametrize("escape_move", [18, 46, 100])
@pytest.mark.parametrize("species", [108, 148, 6])
def test_escape_effect_bypasses_setup_without_species_allowlist(monkeypatch, escape_move, species):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1, enemy_species_id=species)
    monkeypatch.setattr(world, "read_enemy_capture_moves", lambda: (33, escape_move, 0, 0))

    def forbidden(*_args, **_kwargs):
        pytest.fail("escape target must get a ball before setup/switch input")

    monkeypatch.setattr(runtime, "switch_active_battler", forbidden)
    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", forbidden)
    assert prepare() is True
    assert prepare.bypassed_for_escape and prepare.attempts == 0
    assert world.turns == 0 and prepare.reports == []
    assert world.raw.active_party_index == 1 and world.raw.bag_items == ((4, 4),)


def test_missing_opponent_moves_do_not_imply_safe_status_setup(monkeypatch):
    world, prepare = setup(monkeypatch)
    monkeypatch.setattr(world, "read_enemy_capture_moves", lambda: None)
    with pytest.raises(runtime.RedCaptureStatusError, match="moves are unavailable"):
        prepare()
    assert world.turns == 0 and not prepare.bypassed_for_escape


def test_status_misses_are_bounded_across_balls_not_relabelled_as_success(monkeypatch):
    world, prepare = setup(monkeypatch)
    assert prepare()
    assert world.turns == 3 and prepare.attempts == 3
    assert not prepare.bypassed_for_escape
    assert [row["status_success"] for row in prepare.reports] == [False] * 3
    assert all(row["target_hp_before"] == row["target_hp_after"] == 25 for row in prepare.reports)
    assert prepare()
    assert world.turns == 3


def test_only_observed_sleep_stops_after_one_attempt(monkeypatch):
    world, prepare = setup(monkeypatch)

    def sleep(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.status = 3
        return result

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", sleep)
    assert prepare()
    assert world.turns == 1 and world.boundaries == 2
    assert prepare.reports[0]["status_success"] is True
    assert prepare.reports[0]["condition"] == "sleep"
    assert prepare()
    assert world.turns == 1


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"enemy_hp": 24}, runtime.CaptureStatusDrift.TARGET_HP),
        ({"enemy_species_id": 185}, runtime.CaptureStatusDrift.ORIGINAL_SPECIES),
        ({"party_species_ids": (48,)}, runtime.CaptureStatusDrift.PARTY_SPECIES),
        ({"bag_items": ((4, 3),)}, runtime.CaptureStatusDrift.BAG_ITEMS),
    ],
)
def test_status_preparation_rejects_target_damage_and_inventory_drift(
    monkeypatch,
    change,
    reason,
):
    world, prepare = setup(monkeypatch)

    def drift(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, **change)
        return result

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", drift)
    with pytest.raises(runtime.RedCaptureStatusError) as stopped:
        prepare()
    assert stopped.value.reason_code == reason.value
    assert _exception_chain(stopped.value)[0]["reason_code"] == reason.value
    assert world.turns == 1


def test_status_guard_names_departed_battle_without_input(monkeypatch):
    world, prepare = setup(monkeypatch)
    changed = replace(world.raw, battle_state=0)
    with pytest.raises(runtime.RedCaptureStatusError) as stopped:
        prepare._require_protected(
            changed,
            None,
            25,
            world.raw.party_species_ids,
            world.raw.bag_items,
        )
    assert stopped.value.reason_code == runtime.CaptureStatusDrift.BATTLE_STATE.value
    assert world.turns == 0


def test_status_guard_names_transformed_display_mismatch_without_input(monkeypatch):
    world, prepare = setup(monkeypatch)
    prepare.latched_original_species_id = world.raw.enemy_species_id
    identity = WildCaptureIdentity(108, 185, True, (0, 0))
    with pytest.raises(runtime.RedCaptureStatusError) as stopped:
        prepare._require_protected(
            world.raw,
            identity,
            25,
            world.raw.party_species_ids,
            world.raw.bag_items,
        )
    assert stopped.value.reason_code == runtime.CaptureStatusDrift.DISPLAYED_SPECIES.value
    assert world.turns == 0


def test_pp_proof_is_not_optional(monkeypatch):
    _, prepare = setup(monkeypatch)
    monkeypatch.setattr(
        runtime,
        "execute_bounded_battle_move_turn",
        lambda *_args, **_kwargs: SimpleNamespace(move_executed=True),
    )
    with pytest.raises(runtime.RedCaptureStatusError, match="PP differs"):
        prepare()


def test_wild_teleport_exit_is_not_status_success(monkeypatch):
    world, prepare = setup(monkeypatch)

    def flee(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, battle_state=0)
        return result

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", flee)
    assert prepare() is False
    assert prepare.reports == [{"attempt": 1, "encounter_ended": True, "status_success": False}]


def test_helper_switch_is_verified_before_owned_move(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1)
    switches = []

    def switch(_actions, _reader, _emulator, index, **_kwargs):
        switches.append(index)
        world.raw = replace(world.raw, active_party_index=index)

    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    assert prepare()
    assert switches == [0, 1] and world.turns == 3


def test_absent_helper_does_not_choose_damaging_replacement(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.party = replace(
        world.party,
        members=(
            replace(world.party.members[0], moves=(MoveObservation(1, 20),)),
            world.party.members[1],
        ),
    )
    assert prepare()
    assert world.turns == 0 and prepare.reports == []


def test_unconfirmed_native_faint_aborts_before_another_status_attempt(monkeypatch):
    world, prepare = setup(monkeypatch)

    def faint(*args, **kwargs):
        result = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, active_party_hp=0)
        return result

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", faint)
    with pytest.raises(runtime.RedCaptureStatusError, match="fainted"):
        prepare()
    assert world.turns == 1


def configure_rest_target(monkeypatch, world):
    world.raw = replace(world.raw, enemy_hp=47, enemy_max_hp=137)
    monkeypatch.setattr(world, "read_enemy_capture_moves", lambda: (29, 133, 156, 0))


@pytest.mark.parametrize("status_move", [95, 78])
def test_opponent_rest_healing_is_not_our_sleep_or_paralysis_success(monkeypatch, status_move):
    world, prepare = setup(monkeypatch)
    configure_rest_target(monkeypatch, world)
    world.party = replace(
        world.party,
        members=(
            replace(world.party.members[0], moves=(MoveObservation(status_move, 10),)),
            world.party.members[1],
        ),
    )

    def rest(*args, **kwargs):
        turn = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, enemy_hp=137)
        world.status = 2
        return turn

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", rest)
    assert prepare()
    assert prepare.attempts == world.turns == 1
    assert prepare.reports[0]["status_success"] is False
    assert prepare.reports[0]["opponent_recovery_observed"] is True
    assert prepare.reports[0]["target_hp_before"] == 47
    assert prepare.reports[0]["target_hp_after"] == 137
    assert prepare.opponent_recoveries[0]["phase"] == "status_turn"
    assert prepare.throw_preparations[-1]["target_status"] == "sleep"
    assert prepare.throw_preparations[-1]["target_hp"] == 137


def test_opponent_rest_during_helper_switch_avoids_unneeded_status_move(monkeypatch):
    world, prepare = setup(monkeypatch)
    configure_rest_target(monkeypatch, world)
    world.raw = replace(world.raw, active_party_index=1)

    def switch(_a, _r, _e, index, **kwargs):
        world.raw = replace(world.raw, active_party_index=index, enemy_hp=137)
        world.status = 2

    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    assert prepare()
    assert world.turns == prepare.attempts == 0
    assert prepare.reports == []
    assert len(prepare.opponent_recoveries) == 1
    assert prepare.opponent_recoveries[0]["phase"] == "helper_switch"


def test_opponent_rest_during_protective_switch_updates_throw_observation(monkeypatch):
    world, prepare = setup(monkeypatch)
    configure_rest_target(monkeypatch, world)
    world.status = 0x40

    def switch(_a, _r, _e, index, **kwargs):
        world.raw = replace(world.raw, active_party_index=index, enemy_hp=137)
        world.status = 2

    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    assert prepare()
    assert world.turns == prepare.attempts == 0
    assert prepare.opponent_recoveries[0]["phase"] == "catcher_switch"
    assert prepare.throw_preparations[-1]["target_status"] == "sleep"


def test_opponent_rest_settlement_is_verified_before_next_input(monkeypatch):
    world, prepare = setup(monkeypatch)
    configure_rest_target(monkeypatch, world)

    def settle(*args, **kwargs):
        world.boundaries += 1
        if world.boundaries == 2:
            world.raw = replace(world.raw, enemy_hp=137)
            world.status = 2

    monkeypatch.setattr(runtime, "advance_battle_to_policy_boundary", settle)
    assert prepare()
    assert world.turns == 1
    assert prepare.opponent_recoveries[0]["phase"] == "status_settlement"
    assert prepare.reports[0]["status_success"] is False


@pytest.mark.parametrize(
    "hp,max_hp,status,moves",
    [
        (46, 137, 2, (29, 133, 156, 0)),  # damage
        (100, 137, 2, (29, 133, 156, 0)),  # unexplained partial healing
        (137, 137, 0, (29, 133, 156, 0)),  # no observed sleep
        (137, 137, 3, (29, 133, 156, 0)),  # not the Rest sleep counter
        (137, 137, 2, (29, 133, 0, 0)),  # no native recovery move
        (138, 138, 2, (29, 133, 156, 0)),  # changed maximum HP
    ],
)
def test_rest_exception_still_rejects_unexplained_hp_transition(
    monkeypatch, hp, max_hp, status, moves
):
    world, prepare = setup(monkeypatch)
    configure_rest_target(monkeypatch, world)
    monkeypatch.setattr(world, "read_enemy_capture_moves", lambda: moves)

    def drift(*args, **kwargs):
        turn = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, enemy_hp=hp, enemy_max_hp=max_hp)
        world.status = status
        return turn

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", drift)
    with pytest.raises(runtime.RedCaptureStatusError) as stop:
        prepare()
    assert stop.value.reason_code == runtime.CaptureStatusDrift.TARGET_HP.value
    assert not prepare.opponent_recoveries


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"bag_items": ((4, 3),)}, runtime.CaptureStatusDrift.BAG_ITEMS),
        ({"party_species_ids": (48,)}, runtime.CaptureStatusDrift.PARTY_SPECIES),
        ({"enemy_species_id": 185}, runtime.CaptureStatusDrift.TARGET_HP),
        ({"map_id": 99}, runtime.CaptureStatusDrift.MAP),
    ],
)
def test_rest_never_bypasses_capture_custody_guards(monkeypatch, change, reason):
    world, prepare = setup(monkeypatch)
    configure_rest_target(monkeypatch, world)

    def drift(*args, **kwargs):
        turn = world.turn(*args, **kwargs)
        world.raw = replace(world.raw, enemy_hp=137, **change)
        world.status = 2
        return turn

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", drift)
    with pytest.raises(runtime.RedCaptureStatusError) as stop:
        prepare()
    assert stop.value.reason_code == reason.value
    assert not prepare.opponent_recoveries


def test_rest_does_not_waive_owned_pp_proof(monkeypatch):
    world, prepare = setup(monkeypatch)
    configure_rest_target(monkeypatch, world)

    def rest_without_owned_pp(*args, **kwargs):
        world.raw = replace(world.raw, enemy_hp=137)
        world.status = 2
        return SimpleNamespace(move_executed=True)

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", rest_without_owned_pp)
    with pytest.raises(runtime.RedCaptureStatusError, match="PP differs"):
        prepare()
    assert not prepare.reports


def test_disabled_status_slot_is_not_submitted(monkeypatch):
    from pokemon_red_completion.battle_runtime import _choose_usable_slot

    world, prepare = setup(monkeypatch)
    first = replace(world.party.members[0], moves=tuple(
        MoveObservation(move, 10) for move in (33, 45, 43, 95)
    ))
    world.party = replace(world.party, members=(first, world.party.members[1]))
    world.raw = replace(
        world.raw, active_party_moves=(33, 45, 43, 95), active_party_pp=(10, 10, 10, 10),
        player_disabled_move_slot=4, player_disable_turns=2,
    )

    def guarded_turn(*_args, **kwargs):
        # Use the unchanged executor legality guard: this must never receive
        # the observed disabled status slot, rather than tolerating its error.
        _choose_usable_slot(
            lambda _raw: kwargs["selected_slot"], world.raw,
            intent=None, label="non-damaging capture status",
        )
        raise AssertionError("No usable status move was available")

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", guarded_turn)
    assert prepare()
    assert prepare.attempts == world.turns == 0
    assert prepare.reports == []
    assert world.status == 0
    assert world.party.members[0].moves[3].current_pp == 10
    assert prepare.throw_preparations[-1]["target_status"] == StatusCondition.HEALTHY.value


def test_disable_from_opponent_reply_prevents_another_status_attempt(monkeypatch):
    world, prepare = setup(monkeypatch)
    ordinary_turn = world.turn

    def disable_reply(*args, **kwargs):
        result = ordinary_turn(*args, **kwargs)
        world.raw = replace(
            world.raw, player_disabled_move_slot=1, player_disable_turns=3,
        )
        return result

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", disable_reply)
    assert prepare()
    assert prepare.attempts == world.turns == 1
    assert len(prepare.reports) == 1
    assert not prepare.reports[0]["status_success"]
    assert world.status == 0


def test_disable_observed_after_switch_prevents_stale_status_submission(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1)

    def opponent_disables_helper(_actions, _reader, _emulator, index, **_kwargs):
        world.raw = replace(
            world.raw, active_party_index=index,
            player_disabled_move_slot=1, player_disable_turns=2,
        )

    monkeypatch.setattr(runtime, "switch_active_battler", opponent_disables_helper)
    assert prepare()
    assert prepare.attempts == world.turns == 0
    assert world.status == 0


def test_active_disable_does_not_remove_bench_status_capability(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.raw = replace(
        world.raw, active_party_index=1,
        player_disabled_move_slot=1, player_disable_turns=3,
    )
    switches = []

    def ordinary_switch(_actions, _reader, _emulator, index, **_kwargs):
        switches.append(index)
        world.raw = replace(
            world.raw, active_party_index=index,
            player_disabled_move_slot=0, player_disable_turns=0,
        )

    ordinary_turn = world.turn

    def sleep_turn(*args, **kwargs):
        result = ordinary_turn(*args, **kwargs)
        world.status = 3
        return result

    monkeypatch.setattr(runtime, "switch_active_battler", ordinary_switch)
    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", sleep_turn)
    assert prepare()
    assert switches[0] == 0
    assert prepare.attempts == world.turns == 1
    assert prepare.reports[0]["status_success"]


@pytest.mark.parametrize(("slot", "turns"), [(1, 0), (1, None), (2, 3)])
def test_inactive_disable_preserves_existing_status_behavior(monkeypatch, slot, turns):
    world, prepare = setup(monkeypatch)
    world.raw = replace(
        world.raw, player_disabled_move_slot=slot, player_disable_turns=turns,
    )
    assert prepare()
    assert prepare.attempts == world.turns == 3


@pytest.mark.parametrize("move", (120, 153))
@pytest.mark.parametrize("drift", (None, "same_move", "other_effect", "bag", "storage", "party_pp", "other_hp", "faint", "money", "tile", "field", "losing_result"))
def test_renewable_switch_self_destruct(monkeypatch, move, drift):
    world, prepare = setup(monkeypatch)
    prepare.allow_renewable_self_destruct_exit = True
    world.status = 3
    world.raw = replace(world.raw, party_hp=(50, 200), party_moves=((95,), (57,)), party_pp=((10,), (10,)),
                        player_money=541, party_status=(0, 0))
    buffer = [move, 7] if drift == "same_move" else [111, 11]
    box = ["unchanged"]
    prepare.emulator = SimpleNamespace(pressed_buttons=(), read_u8=lambda a: buffer[a - runtime.RamAddress.ENEMY_MOVE_NUM])
    world.read_enemy_capture_moves = lambda: (120, 153, 113, 129)
    world.read_pokedex_state = lambda: SimpleNamespace(owned_species=(1, 2))
    world.read_current_box_state = lambda: SimpleNamespace(box_index=2)
    world.read_box_specimen_identities = lambda: tuple(box)
    world.read_input_readiness = lambda: SimpleNamespace(ready=drift != "field")
    world.read_bottom_dialogue_box_visible = world.read_overworld_start_menu_visible = lambda: False

    def switch(_actions, _reader, _emulator, slot, **options):
        assert options["allow_wild_field_return"] and slot == 1
        changes = {"bag": {"bag_items": ((4, 1),)}, "party_pp": {"party_pp": ((9,), (10,))},
                   "other_hp": {"party_hp": (49, 136)}, "faint": {"party_hp": (50, 0)},
                   "money": {"player_money": 500}, "tile": {"player_y": 1}, "losing_result": {"battle_result": 1}}
        settled = dict(battle_state=0, battle_result=0, enemy_hp=0, party_hp=(50, 136))
        settled.update(changes.get(drift, {}))
        world.raw = replace(world.raw, **settled)
        if drift == "storage":
            box.clear()
        buffer[:] = [move, 9 if drift == "other_effect" else 7]

    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    if drift:
        with pytest.raises(runtime.RedCaptureStatusError, match="unverified wild exit"):
            prepare()
    else:
        assert prepare() is False
        assert prepare.reports[-1]["opponent_self_destruct_move"] == move
        assert prepare.reports[-1]["balls_spent"] == 0
    assert not prepare.throw_preparations
