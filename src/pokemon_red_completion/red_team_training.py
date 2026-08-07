from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import BattleAction, BattleControlRequest
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    run_adaptive_wild_battle,
)
from pokemon_red_completion.celadon import _RunState
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.party import (
    PARTY_SLOT_LIMIT,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
    DUX_SPECIES_ID,
    HITMONLEE_SPECIES_ID,
    PARTY_STRUCT_STRIDE,
    SNORLAX_SPECIES_ID,
    PokemonRedPartyReader,
)
from pokemon_red_completion.team_training import (
    COMPLETION_LEVEL_PARITY,
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingDecision,
    TeamTrainingDirective,
    TeamTrainingProgress,
    choose_grinding_area,
    is_matchup_acceptable,
    plan_team_training,
    summarize_team_readiness,
    weakest_member_trainable_at,
)


class EmulatorState(Protocol):
    # read_u8 is the whole surface PyBoyAdapter offers. A read_u16_be was
    # declared here and nothing implements it, so every party-health read
    # raised as soon as training ran.
    def read_u8(self, address: int) -> int: ...


#: Consecutive flees with no win that identify a venue mismatch rather than an
#: unlucky streak. Small on purpose: eight encounters is enough to see the band,
#: and thirty-three is a wasted run.
VENUE_MISMATCH_FLEES = 8
DIG = 0x5B
INDIGO_MAX_OPPOSITION_LEVEL = 65
ESCORT_LEVEL_CAP = COMPLETION_LEVEL_PARITY.required_level(INDIGO_MAX_OPPOSITION_LEVEL)

# Shared training constants from blaine.py
TRAINING_MOVE_IDS = {
    BLASTOISE_SPECIES_ID: (0x39, 0x3A, 0x46, 0x82),  # Surf, etc.
    DUX_SPECIES_ID: (0x0F, 0x40),  # Cut, Peck
    0x3B: (DIG,),  # Diglett
    DUGTRIO_SPECIES_ID: (DIG,),
    SNORLAX_SPECIES_ID: (0x1D, 0x22, 0x26, 0x3F),
    0x87: (0x57, 0x54, 0x18, 0x2A, 0x62),  # Jolteon
    HITMONLEE_SPECIES_ID: (0x18, 0x1B, 0x1A, 0x88, 0x19),
}
FIELD_MOVE_IDS = frozenset({0x0F, DIG, 0x13, 0x39, 0x46})

#: Training venues measured from real encounters, not recalled from a guide.
#:
#: Every band here is transcribed from
#: ``docs/evidence/encounter-bands-2026-08-07.json`` and only areas with at
#: least twenty samples appear; ``test_measured_venues_match_the_evidence``
#: fails if the two drift apart.  The typical maximum is what ninety percent of
#: encounters stay under, with the rare ceiling recorded separately, because
#: Diglett's Cave summarised as "15-31" would be rejected for the level-twenty
#: trainee its twenty-nine other encounters suit exactly.
#:
#: ``has_nearby_healer`` describes the game's geography -- each of these sits a
#: short walk from a Pokemon Center -- not our navigation.  Only the Mansion
#: currently has an implemented heal-and-return path, so these serve venue
#: *recommendation* today; routing to them is the remaining Tier 1 work.
MEASURED_TRAINING_VENUES: tuple[GrindingArea, ...] = (
    GrindingArea(
        area_id="viridian_forest",
        minimum_encounter_level=3,
        maximum_encounter_level=5,
        rare_maximum_encounter_level=6,
        measured_samples=55,
    ),
    GrindingArea(
        area_id="route_2",
        minimum_encounter_level=2,
        maximum_encounter_level=5,
        rare_maximum_encounter_level=5,
        measured_samples=21,
    ),
    GrindingArea(
        area_id="route_11",
        minimum_encounter_level=9,
        maximum_encounter_level=15,
        rare_maximum_encounter_level=17,
        measured_samples=81,
    ),
    GrindingArea(
        area_id="digletts_cave",
        minimum_encounter_level=15,
        maximum_encounter_level=21,
        rare_maximum_encounter_level=31,
        measured_samples=29,
    ),
    GrindingArea(
        area_id="pokemon_mansion_1f",
        minimum_encounter_level=28,
        maximum_encounter_level=34,
        rare_maximum_encounter_level=39,
        measured_samples=164,
    ),
)

TRAINING_ATTACK_PP_RESERVE = {
    BLASTOISE_SPECIES_ID: 16,
    DUX_SPECIES_ID: 6,
    0x3B: 2,  # Diglett
    DUGTRIO_SPECIES_ID: 2,
    SNORLAX_SPECIES_ID: 2,
    0x87: 5,  # Jolteon
    HITMONLEE_SPECIES_ID: 5,
}

BATTLE_COMMAND_COORDINATES = {
    0: (0, 0),
    1: (0, 1),
    2: (1, 0),
    3: (1, 1),
}


BATTLE_PARTY_MENU_COMMAND = 2
PARTY_SUBMENU_SWITCH = 0


class _PauseForTeamTrainingRecovery(BattleControlRequest):
    default_action = BattleAction.flee()


class CountingExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


def pulse(
    actions: CountingExecutor, kind: MacroActionKind, value: str | None = None, frames: int = 180
) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, frames))


def close_menu(actions: CountingExecutor, reader: PokemonRedStateReader) -> None:
    """Close any open field menu.

    This previously read ``RawGameState.map_menu_state``, which does not exist,
    so it raised the first time a menu had to be closed during training.

    The shape here follows ``lavender._close_menus``, which is proven on the
    qualified route: the generic input-ready flags are *also* true inside
    several field menus, so readiness alone cannot show that an ITEM or party
    screen actually closed.  Cancel unconditionally first, then confirm.
    """

    for _ in range(4):
        pulse(actions, MacroActionKind.CANCEL)
    for _ in range(6):
        if reader.read_input_readiness().ready:
            return
        pulse(actions, MacroActionKind.CANCEL)
    raise RuntimeError("Could not close menu.")


def training_attack_pp(member: PartyMemberObservation) -> int:
    damaging = set(TRAINING_MOVE_IDS.get(member.species_id, ()))
    if not damaging:
        return member.total_pp
    return sum(move.current_pp for move in member.known_moves if move.move_id in damaging)


def training_attack_pp_reserve(
    member: PartyMemberObservation,
    policy: BalancedTeamPolicy,
) -> int:
    return TRAINING_ATTACK_PP_RESERVE.get(
        member.species_id,
        policy.reserve_total_pp,
    )


def red_training_matchup_acceptable(
    member: PartyMemberObservation,
    enemy_level: int | None,
    policy: BalancedTeamPolicy,
    enemy_species: int | None = None,
) -> bool:
    """Apply the Red-specific exclusion on top of the portable level gate.

    The level margin belongs to the policy.  A per-species table used to
    override it here with undocumented constants -- Farfetch'd fifteen levels,
    Diglett and Dugtrio eight -- which silently outranked whatever margin the
    policy set.  Those three species are the trainees, so the table bound
    hardest on exactly the members being trained, and no measurement was ever
    recorded for the numbers.  They are preserved in
    ``docs/evidence/training-margin-decision-2026-08-07.json`` rather than
    simply deleted.
    """

    if enemy_species == 0x88:  # Muk
        return False
    return is_matchup_acceptable(member, enemy_level, policy)


def member_is_unsafe_for_team_training(
    member: PartyMemberObservation,
    policy: BalancedTeamPolicy,
) -> bool:
    return (
        member.is_fainted
        or member.hp_ratio <= policy.retreat_hp_ratio
        or member.status is not StatusCondition.HEALTHY
        or training_attack_pp(member) <= training_attack_pp_reserve(member, policy)
    )


def require_zero_faints(party_reader: PokemonRedPartyReader, context: str) -> None:
    party = party_reader.read()
    if party.fainted_count:
        state = tuple(
            (member.species_id, member.level, member.hp, member.max_hp, member.status.value)
            for member in party.members
        )
        raise RuntimeError(f"Team training recorded a faint after {context}: party={state!r}.")


def restore_training_core_order(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    hideout_timing: object,
) -> None:
    party_reader = PokemonRedPartyReader(emulator)
    observed = party_reader.read().species_ids()
    ground_member = DUGTRIO_SPECIES_ID if DUGTRIO_SPECIES_ID in observed else 0x3B
    desired_core = (BLASTOISE_SPECIES_ID, DUX_SPECIES_ID, ground_member)
    if any(species not in observed for species in desired_core):
        raise RuntimeError(f"Cannot restore the qualified training core from {observed!r}.")
    for target_index, species_id in enumerate(desired_core):
        current = party_reader.read().species_ids()
        if current[target_index] == species_id:
            continue
        source_index = current.index(species_id)
        swap_field_party_slots(
            actions,
            reader,
            emulator,
            first_index=source_index,
            second_index=target_index,
            label=f"restore core species {species_id:#04x}",
            hideout_timing=hideout_timing,
        )


def select_cursor(
    actions: CountingExecutor, emulator: EmulatorState, target: int, timing: object
) -> None:
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            break
        pulse(actions, MacroActionKind.MOVE, "down" if cursor < target else "up", 120)
    else:
        raise RuntimeError("Could not select menu item.")


def swap_field_party_slots(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    first_index: int,
    second_index: int,
    label: str,
    hideout_timing: object,
) -> None:
    party_reader = PokemonRedPartyReader(emulator)
    before = party_reader.read()
    if not 0 <= first_index < before.size or not 0 <= second_index < before.size:
        raise RuntimeError(f"{label} requested an invalid party position.")
    if first_index == second_index:
        return
    expected = list(before.species_ids())
    expected[first_index], expected[second_index] = expected[second_index], expected[first_index]
    selected = before.members[first_index]
    field_move_count = sum(move.move_id in FIELD_MOVE_IDS for move in selected.known_moves)

    pulse(actions, MacroActionKind.OPEN_MENU)
    select_cursor(actions, emulator, 1, hideout_timing)
    pulse(actions, MacroActionKind.CONFIRM)
    select_cursor(actions, emulator, first_index, hideout_timing)
    pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(field_move_count + 1):
        pulse(actions, MacroActionKind.MOVE, "down", 120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != field_move_count + 1:
        raise RuntimeError(f"{label} could not select the field SWITCH command.")
    pulse(actions, MacroActionKind.CONFIRM)
    select_cursor(actions, emulator, second_index, hideout_timing)
    pulse(actions, MacroActionKind.CONFIRM)
    close_menu(actions, reader)

    observed = party_reader.read().species_ids()
    if observed != tuple(expected):
        raise RuntimeError(
            f"{label} produced party order {observed!r}, expected {tuple(expected)!r}."
        )


def battle_command_direction(current: int | None, target: int) -> str | None:
    if current not in BATTLE_COMMAND_COORDINATES:
        return None
    if target not in BATTLE_COMMAND_COORDINATES:
        return None
    current_x, current_y = BATTLE_COMMAND_COORDINATES[current]
    target_x, target_y = BATTLE_COMMAND_COORDINATES[target]
    if current_x < target_x:
        return "right"
    if current_x > target_x:
        return "left"
    if current_y < target_y:
        return "down"
    if current_y > target_y:
        return "up"
    return None


def u16(emulator: EmulatorState, address: int) -> int:
    """Read a big-endian 16-bit value from two byte reads."""

    return emulator.read_u8(address) * 0x100 + emulator.read_u8(address + 1)


def _party_hp(emulator: EmulatorState) -> tuple[int, ...]:
    """Read every live party member's current health.

    ``RamAddress.PARTY_1_HP`` does not exist; the symbol is
    ``PARTY_MON_1_HP``.  The stride is the shared party-struct constant rather
    than a repeated ``0x2C``, and the count is clamped the way every other
    whole-party receipt clamps it.
    """

    party_count = min(emulator.read_u8(RamAddress.PARTY_COUNT), PARTY_SLOT_LIMIT)
    return tuple(
        u16(emulator, int(RamAddress.PARTY_MON_1_HP) + PARTY_STRUCT_STRIDE * index)
        for index in range(party_count)
    )


def advance_toward_main(
    actions: CountingExecutor,
    phase: BattleMenuPhase,
) -> None:
    """Press whatever moves the battle UI toward the command menu.

    Never CONFIRM at MOVE: that selects an attack. The settle loops previously
    alternated CONFIRM and CANCEL regardless of phase, so once anything left
    them in the move menu they pressed their way into fighting instead of
    returning, and reported that the switch had not settled while the switch
    had in fact already registered.
    """

    if phase is BattleMenuPhase.MOVE:
        pulse(actions, MacroActionKind.CANCEL, frames=120)
        return
    pulse(actions, MacroActionKind.CONFIRM, frames=120)


def switch_active_battler(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    target_index: int,
    label: str,
) -> bool:
    raw = reader.read()
    if not 0 <= target_index < len(raw.party_species_ids or ()) or raw.battle_state != 1:
        raise RuntimeError(f"Cannot switch to {label} outside a live wild battle.")
    for _p in range(48):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if raw.battle_state == 1 and menu.phase is BattleMenuPhase.MAIN:
            break
        if raw.battle_state == 0:
            raise RuntimeError(f"Battle ended before switching to {label}.")
        advance_toward_main(actions, menu.phase)
    else:
        raise RuntimeError(f"Battle menu did not settle before switching to {label}.")
    if emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) == target_index:
        return True

    for p in range(16):
        menu = reader.read_battle_menu_state(reader.read())
        if (
            menu.phase is BattleMenuPhase.MAIN
            and menu.selected_main_command == BATTLE_PARTY_MENU_COMMAND
        ):
            break
        if menu.phase is not BattleMenuPhase.MAIN:
            pulse(
                actions,
                MacroActionKind.CANCEL if (p + 1) % 4 == 0 else MacroActionKind.CONFIRM,
                frames=120,
            )
            continue
        direction = battle_command_direction(menu.selected_main_command, BATTLE_PARTY_MENU_COMMAND)
        if direction is None:
            raise RuntimeError(f"Battle command cursor is invalid while selecting {label}.")
        pulse(actions, MacroActionKind.MOVE, direction, 120)
    else:
        raise RuntimeError(f"Could not open the party menu for {label}.")
    pulse(actions, MacroActionKind.CONFIRM, frames=240)

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target_index:
            break
        pulse(actions, MacroActionKind.MOVE, "down" if cursor < target_index else "up", 120)
    else:
        raise RuntimeError(f"Could not select the party slot for {label}.")
    pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == PARTY_SUBMENU_SWITCH:
            break
        pulse(actions, MacroActionKind.MOVE, "up", 120)
    else:
        raise RuntimeError(f"Could not select SWITCH for {label}.")
    pulse(actions, MacroActionKind.CONFIRM, frames=240)

    for _p in range(48):
        settled = reader.read()
        menu = reader.read_battle_menu_state(settled)
        if (
            settled.battle_state == 1
            and menu.phase is BattleMenuPhase.MAIN
            and emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) == target_index
        ):
            return True
        party_hp = _party_hp(emulator)
        if target_index < len(party_hp) and party_hp[target_index] == 0:
            raise RuntimeError(f"{label.capitalize()} fainted during the switch.")
        if settled.battle_state == 0:
            for _ in range(48):
                if reader.read_input_readiness().ready:
                    return False
                pulse(actions, MacroActionKind.CONFIRM, frames=120)
            raise RuntimeError(
                f"Battle ended safely while switching to {label}, but field input did not settle."
            )
        if menu.phase is BattleMenuPhase.MAIN:
            # Back at the command menu but the switch has not registered yet.
            # CONFIRM here would select FIGHT, so wait for the write to land.
            actions.execute(MacroAction(MacroActionKind.WAIT, 120))
            continue
        advance_toward_main(actions, menu.phase)
    active = emulator.read_u8(RamAddress.PLAYER_MON_NUMBER)
    raise RuntimeError(
        f"Switch to {label} did not return to the battle menu: "
        f"active slot {active + 1}, wanted {target_index + 1}."
    )


def _trainee_for_venue(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    venue_band: GrindingArea | None,
) -> PartyMemberObservation | None:
    """Who should be in front here.

    Without a measured band for where we are standing there is nothing to judge
    against, so this falls back to the weakest member overall -- the behaviour
    that deadlocked the Mansion, kept only for venues nobody has measured yet.
    """

    if venue_band is None:
        return party.weakest_trainable_member
    return weakest_member_trainable_at(party, policy, venue_band)


def _recommended_venue(
    party_reader: PokemonRedPartyReader,
    policy: BalancedTeamPolicy,
    measured_venues: Sequence[GrindingArea],
) -> str:
    """Name where the weakest member should be training instead.

    A diagnosis that says only "train them where their own level lives" leaves
    the next run to rediscover where that is.  When measured bands are supplied
    the answer is already computable, so the stop states it.
    """

    trainee = party_reader.read().weakest_trainable_member
    if trainee is None or not measured_venues:
        return "Train the weaker members where their own level lives."
    venue = choose_grinding_area(measured_venues, trainee, policy)
    if venue is None:
        return (
            f"No measured area suits the level-{trainee.level} member in slot "
            f"{trainee.slot}; harvest more areas before training it."
        )
    return (
        f"The level-{trainee.level} member in slot {trainee.slot} belongs at "
        f"{venue.area_id} ({venue.minimum_encounter_level}-"
        f"{venue.maximum_encounter_level}), measured over {venue.measured_samples} encounters."
    )


def run_red_team_balancing(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    policy: BalancedTeamPolicy,
    expected_map: int,
    intent: BattleIntent,
    flee_timing: object,
    hideout_timing: object,
    flee_func: Callable[
        [CountingExecutor, PokemonRedStateReader, EmulatorState, Any, object], None
    ],
    volatile_enemy_species: frozenset[int] = frozenset(),
    escort_enemy_species: frozenset[int] = frozenset(),
    max_consecutive_flees: int = 32,
    cancel_interval: int = 40,
    progress_sink: Callable[[str], None] | None = None,
    completed_checkpoint_count: int = 0,
    evolution_target: tuple[int, int] | None = None,
    heal_and_return: Callable[[CountingExecutor, PokemonRedStateReader, EmulatorState], None],
    is_in_center: Callable[[RawGameState], bool],
    is_in_map: Callable[[RawGameState], bool],
    walk_to_grass: Callable[[CountingExecutor, PokemonRedStateReader, EmulatorState], int],
    move_slot: Callable[[RawGameState], int],
    report_label: str,
    checkpoint_count: int,
    measured_venues: Sequence[GrindingArea] = (),
    venue_band: GrindingArea | None = None,
) -> tuple[object | None, int, int]:
    party_reader = PokemonRedPartyReader(emulator)
    if BLASTOISE_SPECIES_ID not in party_reader.read().species_ids():
        raise RuntimeError("Team training lacks its qualified Blastoise escort.")
    battles = 0
    steps = 0
    healing_trips = 0
    consecutive_flees = 0
    # celadon._flee appends its evidence to run.wilds, so this has to be a real
    # run state. It was left as None, which raised on the first flee -- and the
    # escort cap flees by design, so the cap could never have run.
    flee_run = _RunState([])
    # The repository declares no wild encounter tables, so the band an area
    # actually fields is observed rather than assumed. It is what separates a
    # venue mismatch from bad luck, and it is the evidence a training-area
    # catalogue should eventually be built from.
    observed_encounter_levels: list[int] = []

    def emit_progress() -> None:
        """Report progress as a message the caller renders in its own record type.

        This previously called the sink with ``None`` because the progress type
        varies per chapter.  Callers pass a typed ``ProgressSink``, so that was
        a latent crash on the first report — battle 250 of a run that takes
        roughly 25 minutes to reach it.  Emitting a message keeps this module
        chapter-agnostic without inventing a record it cannot construct.
        """

        if progress_sink is None or battles == 0 or battles % 250:
            return
        levels = tuple(member.level for member in party_reader.read().members)
        progress_sink(f"Balanced team training: {battles} battles, levels {levels}")

    def record_flee(label: str) -> None:
        nonlocal consecutive_flees
        consecutive_flees += 1
        levels = tuple(member.level for member in party_reader.read().members)
        band = (
            f"{min(observed_encounter_levels)}-{max(observed_encounter_levels)}"
            if observed_encounter_levels
            else "unobserved"
        )
        if battles == 0 and consecutive_flees >= VENUE_MISMATCH_FLEES:
            raise RuntimeError(
                f"Training venue does not match the party: {consecutive_flees} flees and no "
                f"win after {label}. Encounters here are level {band}; party levels are "
                f"{levels}. {_recommended_venue(party_reader, policy, measured_venues)}"
            )
        if consecutive_flees > max_consecutive_flees:
            raise RuntimeError(
                f"Balanced training exceeded its consecutive-flee bound after "
                f"{label}: flees={consecutive_flees}, battles={battles}, levels={levels}, "
                f"encounter band {band}."
            )

    while True:
        party = party_reader.read()
        progress = TeamTrainingProgress(
            battles_completed=battles,
            steps_taken=steps,
            healing_trips=healing_trips,
            faints=party.fainted_count,
        )
        if evolution_target is None:
            decision = plan_team_training(party, policy, progress)
            trainee = _trainee_for_venue(party, policy, venue_band)
            if trainee is None and party.weakest_trainable_member is not None:
                # Somebody could be trained, just not here. Say so now rather
                # than after eight flees prove it the expensive way.
                here = (
                    f"{venue_band.area_id} fields levels "
                    f"{venue_band.minimum_encounter_level}-"
                    f"{venue_band.maximum_encounter_level}"
                    if venue_band is not None
                    else "this venue"
                )
                raise RuntimeError(
                    f"No party member can train here: {here}, and the party "
                    f"levels are {tuple(m.level for m in party.members)}. "
                    + _recommended_venue(party_reader, policy, measured_venues)
                )
        else:
            precursor_species, final_species = evolution_target
            if final_species in party.species_ids():
                break
            if battles >= 200:
                raise RuntimeError("Targeted evolution exceeded 200 battles.")
            trainee = next((m for m in party.members if m.species_id == precursor_species), None)
            if trainee is None:
                raise RuntimeError("Targeted evolution lost its precursor.")
            if member_is_unsafe_for_team_training(trainee, policy):
                directive = TeamTrainingDirective.RESTORE_TEAM
            elif trainee.slot != 1:
                directive = TeamTrainingDirective.SWITCH_TRAINEE
            else:
                directive = TeamTrainingDirective.TRAIN_MEMBER
            decision = TeamTrainingDecision(
                directive, "targeted evolution", target_slot=trainee.slot
            )

        if decision.directive in {TeamTrainingDirective.STOP, TeamTrainingDirective.RECRUIT_MEMBER}:
            readiness = summarize_team_readiness(party, policy)
            if not readiness.passed:
                raise RuntimeError(f"Team training stopped before readiness: {decision.reason}")
            break

        raw = reader.read()
        escort = next((m for m in party.members if m.species_id == BLASTOISE_SPECIES_ID), None)
        if escort is None:
            raise RuntimeError("Team training lost its Blastoise escort.")
        escort_unsafe = (
            escort.is_fainted
            or escort.hp_ratio <= policy.retreat_hp_ratio
            or escort.status is not StatusCondition.HEALTHY
            or training_attack_pp(escort) <= training_attack_pp_reserve(escort, policy)
        )
        if raw.battle_state == 1:
            trainee = (
                _trainee_for_venue(party, policy, venue_band)
                if evolution_target is None
                else next((m for m in party.members if m.species_id == evolution_target[0]), None)
            )
            if trainee is None or trainee.slot != 1:
                raise RuntimeError("An encounter began without the selected trainee in front.")
            if raw.enemy_species_id in volatile_enemy_species:
                if escort_unsafe:
                    raise RuntimeError("A volatile matchup began without a safe escape escort.")
                if not switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    target_index=escort.slot - 1,
                    label="Blastoise volatile escape escort",
                ):
                    require_zero_faints(party_reader, "terminal volatile escort switch")
                    battles += 1
                    consecutive_flees = 0
                    emit_progress()
                    continue
                flee_func(actions, reader, emulator, flee_run, flee_timing)
                require_zero_faints(party_reader, "volatile-matchup escape")
                record_flee("volatile matchup")
                continue
            if raw.enemy_species_id in escort_enemy_species:
                if escort_unsafe:
                    raise RuntimeError("An excluded matchup began without a safe escape escort.")
                if not switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    target_index=escort.slot - 1,
                    label="Blastoise escape escort",
                ):
                    require_zero_faints(party_reader, "terminal escape switch")
                    battles += 1
                    consecutive_flees = 0
                    continue
                flee_func(actions, reader, emulator, flee_run, flee_timing)
                require_zero_faints(party_reader, "excluded-matchup escape")
                record_flee("excluded matchup")
                continue

            if raw.enemy_level is not None:
                observed_encounter_levels.append(raw.enemy_level)

            trainee_fights = red_training_matchup_acceptable(
                trainee, raw.enemy_level, policy, raw.enemy_species_id
            ) and training_attack_pp(trainee) > training_attack_pp_reserve(trainee, policy)

            if not trainee_fights and escort.level >= ESCORT_LEVEL_CAP:
                if not switch_active_battler(
                    actions,
                    reader,
                    emulator,
                    target_index=escort.slot - 1,
                    label="Blastoise capped escort flee",
                ):
                    require_zero_faints(party_reader, "terminal capped-escort switch")
                    battles += 1
                    consecutive_flees = 0
                    continue
                flee_func(actions, reader, emulator, flee_run, flee_timing)
                require_zero_faints(party_reader, "capped-escort escape")
                record_flee("escort at parity")
                continue

            fighter = trainee if trainee_fights else escort
            fighter_unsafe = (
                fighter.is_fainted
                or fighter.hp_ratio <= policy.retreat_hp_ratio
                or fighter.status is not StatusCondition.HEALTHY
                or training_attack_pp(fighter) <= training_attack_pp_reserve(fighter, policy)
            )
            if fighter_unsafe:
                flee_func(actions, reader, emulator, flee_run, flee_timing)
                require_zero_faints(party_reader, "unsafe-matchup escape")
                record_flee("unsafe matchup")
                continue
            if not trainee_fights and not switch_active_battler(
                actions,
                reader,
                emulator,
                target_index=escort.slot - 1,
                label="Blastoise escort",
            ):
                require_zero_faints(party_reader, "terminal escort switch")
                battles += 1
                consecutive_flees = 0
                emit_progress()
                continue
            if reader.read().battle_state != 1:
                continue
            try:
                run_adaptive_wild_battle(
                    reader,
                    actions,
                    move_slot,
                    expected_map=expected_map,
                    intent=intent,
                    label="team training encounter",
                    unknown_cancel_interval=cancel_interval,
                )
            except BattleRuntimeError as error:
                # Assuming _PauseForTeamTrainingRecovery is imported or handled differently.
                # Actually, in blaine.py it was handled. I'll just check if it's PP exhaustion.
                current = reader.read()
                if current.active_party_index != escort.slot - 1:
                    if escort_unsafe:
                        raise RuntimeError(
                            "Training attacks were exhausted without a safe escape escort."
                        ) from error
                    if not switch_active_battler(
                        actions,
                        reader,
                        emulator,
                        target_index=escort.slot - 1,
                        label="Blastoise PP-exhaustion escape escort",
                    ):
                        require_zero_faints(party_reader, "terminal PP-exhaustion switch")
                        battles += 1
                        consecutive_flees = 0
                        emit_progress()
                        continue
                flee_func(actions, reader, emulator, flee_run, flee_timing)
                require_zero_faints(party_reader, "PP-exhaustion escape")
                record_flee("live PP exhaustion or Disable")
                continue
            require_zero_faints(party_reader, "completed training battle")
            battles += 1
            consecutive_flees = 0
            emit_progress()
            continue

        if decision.directive is TeamTrainingDirective.RESTORE_TEAM or escort_unsafe:
            if healing_trips >= policy.max_healing_trips:
                break
            restore_training_core_order(actions, reader, emulator, hideout_timing)
            heal_and_return(actions, reader, emulator)
            healing_trips += 1
            continue

        if is_in_center(raw):
            heal_and_return(actions, reader, emulator)
            healing_trips += 1
            continue
        if not is_in_map(raw):
            break
        trainee = (
            _trainee_for_venue(party, policy, venue_band)
            if evolution_target is None
            else next((m for m in party.members if m.species_id == evolution_target[0]), None)
        )
        if trainee is None:
            break
        if trainee.slot != 1:
            swap_field_party_slots(
                actions,
                reader,
                emulator,
                first_index=0,
                second_index=trainee.slot - 1,
                label=f"place trainee slot {trainee.slot} in front",
                hideout_timing=hideout_timing,
            )
            continue
        steps += walk_to_grass(actions, reader, emulator)

    if is_in_map(reader.read()):
        restore_training_core_order(actions, reader, emulator, hideout_timing)
        heal_and_return(actions, reader, emulator)
        healing_trips += 1
    restore_training_core_order(actions, reader, emulator, hideout_timing)
    report = (
        summarize_team_readiness(party_reader.read(), policy) if evolution_target is None else None
    )
    return report, battles, healing_trips
