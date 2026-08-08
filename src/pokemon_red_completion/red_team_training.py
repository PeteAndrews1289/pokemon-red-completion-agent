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
)
from pokemon_red_completion.party import (
    PARTY_SLOT_LIMIT,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_species_ref,
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
    member_needs_training,
    plan_team_training,
    summarize_team_readiness,
)
from pokemon_red_completion.training_candidate_rank import (
    TrainingCandidateDecision,
    TrainingCandidateSet,
    project_trainee_candidates,
    project_venue_candidates,
)
from pokemon_red_completion.training_control import (
    TrainingControlAction,
    TrainingControlDecision,
    TrainingControlPhase,
    project_training_control_observation,
)
from pokemon_red_completion.training_venue import TrainingVenue, venue_for_map


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
SCRATCH = 0x0A
SLASH = 0xA3
INDIGO_MAX_OPPOSITION_LEVEL = 65
ESCORT_LEVEL_CAP = COMPLETION_LEVEL_PARITY.required_level(INDIGO_MAX_OPPOSITION_LEVEL)

# Shared training constants from blaine.py
TRAINING_MOVE_IDS = {
    BLASTOISE_SPECIES_ID: (0x39, 0x3A, 0x46, 0x82),  # Surf, etc.
    DUX_SPECIES_ID: (0x0F, 0x40),  # Cut, Peck
    # Dig is a two-turn charge attack. In a mirror matchup the opponent can
    # surface first and knock out the trainee before its own hit lands, so use
    # immediate attacks whenever the ground line knows one.
    0x3B: (SLASH, SCRATCH, DIG),  # Diglett
    DUGTRIO_SPECIES_ID: (SLASH, SCRATCH, DIG),
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
#: short walk from a Pokemon Center -- not our navigation.  The Mansion and
#: Diglett's Cave now have implemented heal-and-return paths; the Cave's has
#: not yet been validated against the emulator.
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
PARTY_LIST_MENU_TOP = (0, 1)


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
    if enemy_species is not None:
        trainee_types = RED_BATTLE_CATALOG.resolve_species(
            pokemon_red_species_ref(member.species_id)
        ).types
        enemy_types = RED_BATTLE_CATALOG.resolve_species(
            pokemon_red_species_ref(enemy_species)
        ).types
        if any(
            RED_BATTLE_CATALOG.type_effectiveness(enemy_type, trainee_types) > 1.0
            for enemy_type in enemy_types
        ):
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


def trainee_should_fight_directly(
    trainee: PartyMemberObservation,
    *,
    enemy_level: int | None,
    enemy_species: int | None,
    policy: BalancedTeamPolicy,
    participation_only: bool = False,
) -> bool:
    """Whether this trainee should attack rather than earn shared experience."""

    return (
        not participation_only
        and red_training_matchup_acceptable(trainee, enemy_level, policy, enemy_species)
        and training_attack_pp(trainee) > training_attack_pp_reserve(trainee, policy)
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
    actions: CountingExecutor,
    emulator: EmulatorState,
    target: int,
    timing: object,
    label: str = "menu",
) -> None:
    """Move the menu cursor onto ``target``.

    The failure carries the readings.  "Could not select menu item" says
    nothing about whether the cursor was moving and overshot, moving and too
    slow, or not moving at all -- and those want three different fixes.  A
    twenty-five minute run that ends in an unfalsifiable sentence has to be
    repeated to learn anything, so the sequence is reported instead.
    """

    seen: list[int] = []
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        seen.append(cursor)
        if cursor == target:
            return
        pulse(actions, MacroActionKind.MOVE, "down" if cursor < target else "up", 120)
    raise RuntimeError(
        f"Could not select {label} item {target}: cursor read {seen!r} across eight moves, "
        f"with max_menu_item={emulator.read_u8(RamAddress.MAX_MENU_ITEM)}, "
        f"party_count={emulator.read_u8(RamAddress.PARTY_COUNT)}, "
        f"top=({emulator.read_u8(RamAddress.TOP_MENU_ITEM_X)}, "
        f"{emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y)}). "
        + (
            "It never moved, so this menu does not report its cursor at CURRENT_MENU_ITEM."
            if len(set(seen)) == 1
            else "It moved and then stopped, so the menu it is driving is shorter than "
            "the party — which means it is not the menu this code believes it is in."
        )
    )


def _walk_cursor_to(actions: CountingExecutor, emulator: EmulatorState, target: int) -> None:
    """Nudge the cursor toward ``target`` without insisting that it arrive."""

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            return
        pulse(actions, MacroActionKind.MOVE, "down" if cursor < target else "up", 120)


def open_party_member_submenu(
    actions: CountingExecutor,
    emulator: EmulatorState,
    *,
    label: str,
) -> None:
    """Confirm the selected party member until its command submenu appears."""

    seen: list[tuple[int, int]] = []
    for _ in range(8):
        top = (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        )
        seen.append(top)
        if top != PARTY_LIST_MENU_TOP:
            return
        pulse(actions, MacroActionKind.CONFIRM)
    raise RuntimeError(
        f"Could not open the party-member submenu for {label}; "
        f"menu top remained {seen!r}."
    )


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

    # Which submenu row means SWITCH has been guessed wrong three times: at
    # ``field_move_count + 1``, at ``field_move_count``, and by expecting the
    # resulting menu to be as long as the party. Each guess was a claim about
    # the menu's shape, and the shape refused to cooperate -- the switch-target
    # list reports the same length as the submenu it came from, so no reading
    # tells them apart.
    #
    # The party order does. A row either produced the swap we asked for or it
    # did not, and that is visible in memory afterwards without knowing
    # anything about the menu. So each candidate row is tried as a complete
    # open-swap-close, checked against the party, and abandoned if it did
    # nothing. ``field_move_count`` is tried first because it is still the best
    # guess; it is simply no longer required to be right.
    # SWITCH sits one past the field moves, because the submenu is ordered
    # moves, STATS, SWITCH, CANCEL -- measured directly from a captured state:
    # Blastoise, knowing Surf and Strength, gave a five-entry submenu whose row
    # three opened the party list and completed the swap, while rows zero to
    # two left the submenu untouched.
    #
    # That vindicates the formula this file started with. An earlier change in
    # this session moved it to ``field_move_count`` on the theory that the order
    # was moves-then-SWITCH; the theory was wrong and the measurement says so.
    # The search below remains because the count itself can be wrong -- a move
    # this table does not recognise as a field move shifts every row -- but the
    # first candidate is now the one the game was observed to use.
    switch_row = field_move_count + 1
    attempts: list[tuple[int, tuple[int, ...]]] = []
    for row in [switch_row] + [r for r in range(PARTY_SLOT_LIMIT) if r != switch_row]:
        # A heal, field move, or prior candidate can leave a submenu visible
        # even though generic input readiness is true. START does not replace
        # that submenu, so establish the field boundary before every attempt.
        close_menu(actions, reader)
        pulse(actions, MacroActionKind.OPEN_MENU)
        select_cursor(actions, emulator, 1, hideout_timing, "start-menu POKEMON")
        pulse(actions, MacroActionKind.CONFIRM)
        select_cursor(actions, emulator, first_index, hideout_timing, "party source slot")
        open_party_member_submenu(actions, emulator, label=label)
        if row > emulator.read_u8(RamAddress.MAX_MENU_ITEM):
            close_menu(actions, reader)
            continue
        _walk_cursor_to(actions, emulator, row)
        pulse(actions, MacroActionKind.CONFIRM)
        _walk_cursor_to(actions, emulator, second_index)
        pulse(actions, MacroActionKind.CONFIRM)
        close_menu(actions, reader)

        observed = party_reader.read().species_ids()
        attempts.append((row, observed))
        if observed == tuple(expected):
            return
        if observed != before.species_ids():
            raise RuntimeError(
                f"{label} left the party as {observed!r} rather than "
                f"{tuple(expected)!r} after submenu row {row}."
            )

    raise RuntimeError(
        f"{label} could not swap slots {first_index + 1} and {second_index + 1}: "
        f"no submenu row changed the party. Tried (row, resulting order)={attempts!r}."
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
    # The phases seen on the way are the whole diagnosis. A menu stuck in one
    # phase wants a different fix from one cycling between two, and "did not
    # settle" cannot tell them apart -- which is how every other menu in this
    # module cost a run before it started reporting what it saw.
    phases_seen: list[str] = []
    for _p in range(48):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        phases_seen.append(menu.phase.name)
        if raw.battle_state == 1 and menu.phase is BattleMenuPhase.MAIN:
            break
        if raw.battle_state == 0:
            raise RuntimeError(
                f"Battle ended before switching to {label}. Phases seen: {phases_seen!r}."
            )
        advance_toward_main(actions, menu.phase)
    else:
        distinct = sorted(set(phases_seen))
        raise RuntimeError(
            f"Battle menu did not settle before switching to {label} in 48 attempts. "
            f"Phases seen: {distinct!r}; last eight: {phases_seen[-8:]!r}. "
            + (
                "It never left that phase, so advance_toward_main does not know how to."
                if len(distinct) == 1
                else "It kept moving without arriving."
            )
        )
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

    post_switch_phases: list[str] = []
    for _p in range(48):
        settled = reader.read()
        menu = reader.read_battle_menu_state(settled)
        post_switch_phases.append(menu.phase.name)
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
    settled = reader.read()
    active = emulator.read_u8(RamAddress.PLAYER_MON_NUMBER)
    party_hp = _party_hp(emulator)
    # A held-out collection observed the causal switch in PLAYER_MON_NUMBER,
    # but the cursor signature stayed UNKNOWN through the complete bounded
    # settle loop. The next flee or battle primitive has its own menu settle
    # logic, so the verified live target is stronger evidence than rejecting a
    # successful switch solely because one presentation-layer cursor was late.
    if (
        settled.battle_state == 1
        and active == target_index
        and target_index < len(party_hp)
        and party_hp[target_index] > 0
    ):
        return True
    raise RuntimeError(
        f"Switch to {label} did not return to the battle menu: "
        f"active slot {active + 1}, wanted {target_index + 1}; "
        f"phases={sorted(set(post_switch_phases))!r}."
    )


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
    decision_sink: Callable[[TrainingControlDecision], None] | None = None,
    candidate_decision_sink: Callable[[TrainingCandidateDecision], None] | None = None,
    decision_authority: Callable[
        [TrainingControlDecision], TrainingControlAction
    ] | None = None,
    completed_checkpoint_count: int = 0,
    evolution_target: tuple[int, int] | None = None,
    venues: Sequence[TrainingVenue],
    report_label: str,
    checkpoint_count: int,
) -> tuple[object | None, int, int]:
    party_reader = PokemonRedPartyReader(emulator)
    if not venues:
        raise RuntimeError(
            "Team training was given no venue. There is nowhere to walk, nowhere to heal, "
            "and no band to judge a matchup against."
        )
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
    decision_index = 0
    candidate_decision_index = 0

    def emit_candidate_decision(
        observation: TrainingCandidateSet,
        selected_index: int,
        reason: str,
    ) -> None:
        """Publish only choices whose label is observable from portable features."""

        nonlocal candidate_decision_index
        decision = TrainingCandidateDecision(
            candidate_decision_index,
            selected_index,
            observation,
            reason,
        )
        if candidate_decision_sink is not None:
            candidate_decision_sink(decision)
        candidate_decision_index += 1

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
                f"{levels}. {_recommended_venue(party_reader, policy, [v.band for v in venues])}"
            )
        # Once the venue has already produced a win, a long sequence of safe
        # exits is not evidence of a deadlock. A held-out lineage reached 33
        # legitimate flees after 725 wins while the party was still gaining
        # levels. Keep the count as a saturated model feature, but let the
        # existing global step budget bound a genuinely non-progressing run.

    def emit_decision(
        action: TrainingControlAction,
        reason: str,
        *,
        phase: TrainingControlPhase,
        party: PartyObservation,
        progress: TeamTrainingProgress,
        trainee: PartyMemberObservation | None,
        enemy_level: int | None = None,
        fight_allowed: bool = True,
        candidate_actions: tuple[TrainingControlAction, ...] | None = None,
    ) -> TrainingControlAction:
        """Publish supervision before the teacher executes the mechanic."""

        nonlocal decision_index
        pp = training_attack_pp(trainee) if trainee is not None else None
        reserve = training_attack_pp_reserve(trainee, policy) if trainee is not None else None
        safety_reserve = next(
            (member for member in party.members if member.species_id == BLASTOISE_SPECIES_ID),
            None,
        )
        safety_pp = training_attack_pp(safety_reserve) if safety_reserve is not None else None
        safety_pp_reserve = (
            training_attack_pp_reserve(safety_reserve, policy)
            if safety_reserve is not None
            else None
        )
        observation = project_training_control_observation(
            party,
            policy,
            progress,
            phase=phase,
            trainee=trainee,
            attack_pp=pp,
            attack_pp_reserve=reserve,
            safety_reserve=safety_reserve,
            safety_reserve_attack_pp=safety_pp,
            safety_reserve_attack_pp_reserve=safety_pp_reserve,
            enemy_level=enemy_level,
            venue=current_venue.band,
            consecutive_flees=consecutive_flees,
            max_consecutive_flees=max_consecutive_flees,
            fight_allowed=fight_allowed,
            candidate_actions=candidate_actions,
        )
        decision = TrainingControlDecision(decision_index, action, observation, reason)
        if decision_sink is not None:
            decision_sink(decision)
        decision_index += 1
        if decision_authority is None:
            return action
        selected = decision_authority(decision)
        if selected not in observation.candidate_actions:
            raise RuntimeError("training-control authority selected an illegal phase action")
        return selected

    def require_safe_exit(selected: TrainingControlAction, reason: str) -> None:
        if selected is not TrainingControlAction.FLEE:
            raise RuntimeError(
                f"training-control referee rejected {selected.value} at unsafe boundary: {reason}"
            )

    def require_overworld_action(
        selected: TrainingControlAction,
        required: TrainingControlAction,
        reason: str,
    ) -> None:
        if selected is not required:
            raise RuntimeError(
                f"training-control referee rejected {selected.value} at {reason}; "
                f"{required.value} was required"
            )

    optional_overworld_choices = (
        TrainingControlAction.SEEK,
        TrainingControlAction.HEAL,
    )

    # Never None. A venue is needed before any trainee is matched to one --
    # ``plan_team_training`` can ask to RESTORE_TEAM on the first iteration, and
    # an unsafe escort triggers the same branch -- and both paths heal through
    # the venue. Starting from wherever we are standing keeps that honest;
    # falling back to the first venue keeps it total.
    current_venue: TrainingVenue = venue_for_map(venues, reader.read().map_id or -1) or venues[0]

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
            trainee = None
            target_band = None
            bands = tuple(venue.band for venue in venues)
            trainable_members = [m for m in party.members if member_needs_training(m, policy)]
            for member in sorted(trainable_members, key=lambda m: (m.level, m.slot)):
                band = choose_grinding_area(bands, member, policy)
                if band is not None:
                    trainee = member
                    target_band = band
                    break

            if not trainable_members:
                # Nobody is below the floor, so the decision is already STOP and
                # the readiness check below is what should speak.
                pass
            elif trainee is None:
                here = ", ".join(
                    f"{venue.band.area_id} fields levels "
                    f"{venue.band.minimum_encounter_level}-{venue.band.maximum_encounter_level}"
                    for venue in venues
                )
                raise RuntimeError(
                    f"No party member can train here: {here}, and the party "
                    f"levels are {tuple(m.level for m in party.members)}. "
                    + _recommended_venue(party_reader, policy, [v.band for v in venues])
                )
            else:
                current_venue = next(v for v in venues if v.band == target_band)
                trainee_projection = project_trainee_candidates(party, policy, bands)
                if trainee_projection is not None:
                    projected_trainee, selected_index, observation = trainee_projection
                    if projected_trainee == trainee:
                        emit_candidate_decision(
                            observation,
                            selected_index,
                            "weakest venue-compatible member below the level floor",
                        )
                venue_projection = project_venue_candidates(
                    party,
                    policy,
                    trainee,
                    bands,
                )
                if venue_projection is not None:
                    projected_area, selected_index, observation = venue_projection
                    if projected_area == target_band:
                        emit_candidate_decision(
                            observation,
                            selected_index,
                            "highest-yield safe measured venue",
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
            bands = tuple(venue.band for venue in venues)
            target_band = choose_grinding_area(bands, trainee, policy)
            if target_band is None:
                raise RuntimeError(f"No provided venue suits precursor at level {trainee.level}.")
            current_venue = next(v for v in venues if v.band == target_band)
            venue_projection = project_venue_candidates(
                party,
                policy,
                trainee,
                bands,
            )
            if venue_projection is not None:
                projected_area, selected_index, observation = venue_projection
                if projected_area == target_band:
                    emit_candidate_decision(
                        observation,
                        selected_index,
                        "highest-yield safe measured evolution venue",
                    )

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
            selected = emit_decision(
                TrainingControlAction.STOP,
                decision.reason,
                phase=TrainingControlPhase.OVERWORLD,
                party=party,
                progress=progress,
                trainee=trainee,
                candidate_actions=(TrainingControlAction.STOP,),
            )
            require_overworld_action(
                selected,
                TrainingControlAction.STOP,
                "verified training readiness",
            )
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
                trainee
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
                selected = emit_decision(
                    TrainingControlAction.FLEE,
                    "volatile matchup",
                    phase=TrainingControlPhase.BATTLE,
                    party=party_reader.read(),
                    progress=progress,
                    trainee=party_reader.read().lead,
                    enemy_level=raw.enemy_level,
                    fight_allowed=False,
                )
                require_safe_exit(selected, "volatile matchup")
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
                selected = emit_decision(
                    TrainingControlAction.FLEE,
                    "excluded matchup",
                    phase=TrainingControlPhase.BATTLE,
                    party=party_reader.read(),
                    progress=progress,
                    trainee=party_reader.read().lead,
                    enemy_level=raw.enemy_level,
                    fight_allowed=False,
                )
                require_safe_exit(selected, "excluded matchup")
                flee_func(actions, reader, emulator, flee_run, flee_timing)
                require_zero_faints(party_reader, "excluded-matchup escape")
                record_flee("excluded matchup")
                continue

            if raw.enemy_level is not None:
                observed_encounter_levels.append(raw.enemy_level)

            trainee_fights = trainee_should_fight_directly(
                trainee,
                enemy_level=raw.enemy_level,
                enemy_species=raw.enemy_species_id,
                policy=policy,
                participation_only=evolution_target is not None,
            )

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
                selected = emit_decision(
                    TrainingControlAction.FLEE,
                    "escort has reached the parity cap",
                    phase=TrainingControlPhase.BATTLE,
                    party=party_reader.read(),
                    progress=progress,
                    trainee=party_reader.read().lead,
                    enemy_level=raw.enemy_level,
                    fight_allowed=False,
                )
                require_safe_exit(selected, "escort at parity")
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
                selected = emit_decision(
                    TrainingControlAction.FLEE,
                    "selected fighter is unsafe",
                    phase=TrainingControlPhase.BATTLE,
                    party=party,
                    progress=progress,
                    trainee=trainee,
                    enemy_level=raw.enemy_level,
                    fight_allowed=False,
                )
                require_safe_exit(selected, "unsafe selected fighter")
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
            selected = emit_decision(
                TrainingControlAction.FIGHT,
                "matchup and resource gates permit a training battle",
                phase=TrainingControlPhase.BATTLE,
                party=party,
                progress=progress,
                trainee=trainee,
                enemy_level=raw.enemy_level,
            )
            if selected is TrainingControlAction.FLEE:
                flee_func(actions, reader, emulator, flee_run, flee_timing)
                require_zero_faints(party_reader, "model-selected safe escape")
                record_flee("model-selected safe escape")
                continue
            if selected is not TrainingControlAction.FIGHT:
                raise RuntimeError("battle authority did not select fight or flee")
            try:
                run_adaptive_wild_battle(
                    reader,
                    actions,
                    current_venue.move_slot,
                    expected_map=current_venue.map_id,
                    intent=intent,
                    label="team training encounter",
                    unknown_cancel_interval=cancel_interval,
                )
            except BattleRuntimeError as error:
                if not isinstance(error.__cause__, _PauseForTeamTrainingRecovery):
                    raise
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
                selected = emit_decision(
                    TrainingControlAction.FLEE,
                    "live attack PP was exhausted or disabled",
                    phase=TrainingControlPhase.BATTLE,
                    party=party_reader.read(),
                    progress=progress,
                    trainee=party_reader.read().lead,
                    enemy_level=current.enemy_level,
                    fight_allowed=False,
                )
                require_safe_exit(selected, "live PP exhaustion or Disable")
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
            selected = emit_decision(
                TrainingControlAction.HEAL,
                decision.reason if decision.directive is TeamTrainingDirective.RESTORE_TEAM
                else "escort is unsafe",
                phase=TrainingControlPhase.OVERWORLD,
                party=party,
                progress=progress,
                trainee=trainee,
                candidate_actions=(TrainingControlAction.HEAL,),
            )
            require_overworld_action(
                selected,
                TrainingControlAction.HEAL,
                "required recovery boundary",
            )
            restore_training_core_order(actions, reader, emulator, hideout_timing)
            current_venue.heal_and_return(actions, reader, emulator)
            healing_trips += 1
            continue

        if not current_venue.is_in_map(raw):
            selected = emit_decision(
                TrainingControlAction.SEEK,
                "travel to the selected training venue",
                phase=TrainingControlPhase.OVERWORLD,
                party=party,
                progress=progress,
                trainee=trainee,
                candidate_actions=(TrainingControlAction.SEEK,),
            )
            require_overworld_action(
                selected,
                TrainingControlAction.SEEK,
                "venue-travel boundary",
            )
            restore_training_core_order(actions, reader, emulator, hideout_timing)
            current_venue.heal_and_return(actions, reader, emulator)
            healing_trips += 1
            continue
        trainee = (
            trainee
            if evolution_target is None
            else next((m for m in party.members if m.species_id == evolution_target[0]), None)
        )
        if trainee is None:
            break
        if trainee.slot != 1:
            selected = emit_decision(
                TrainingControlAction.SEEK,
                "prepare the selected trainee before seeking an encounter",
                phase=TrainingControlPhase.OVERWORLD,
                party=party,
                progress=progress,
                trainee=trainee,
                candidate_actions=(TrainingControlAction.SEEK,),
            )
            require_overworld_action(
                selected,
                TrainingControlAction.SEEK,
                "trainee-preparation boundary",
            )
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
        selected = emit_decision(
            TrainingControlAction.SEEK,
            "seek a bounded encounter in the selected venue",
            phase=TrainingControlPhase.OVERWORLD,
            party=party,
            progress=progress,
            trainee=trainee,
            candidate_actions=optional_overworld_choices,
        )
        if selected is TrainingControlAction.HEAL:
            if healing_trips >= policy.max_healing_trips:
                raise RuntimeError("training-control authority exhausted the healing budget")
            restore_training_core_order(actions, reader, emulator, hideout_timing)
            current_venue.heal_and_return(actions, reader, emulator)
            healing_trips += 1
            continue
        require_overworld_action(
            selected,
            TrainingControlAction.SEEK,
            "safe encounter-seeking boundary",
        )
        steps += current_venue.walk_to_grass(actions, reader, emulator)

    if current_venue.is_in_map(reader.read()):
        restore_training_core_order(actions, reader, emulator, hideout_timing)
        current_venue.heal_and_return(actions, reader, emulator)
        healing_trips += 1
    restore_training_core_order(actions, reader, emulator, hideout_timing)
    report = (
        summarize_team_readiness(party_reader.read(), policy) if evolution_target is None else None
    )
    return report, battles, healing_trips
