"""Resource-verified incidental escape when party slot one has fainted."""

from .actions import MacroAction, MacroActionKind
from .battle_runtime import note_observed_battle_exit
from .observation import BattleMenuPhase, EventFlag, MapId, NativeWildTeleportWitness, event_flag_is_set
from .route_1_wild import Route1WildFleeEvidence


def purified_zone_escape_event(before, raw, *, allow_healing=False):
    """Certificate for the native Tower5 location flag, never a generic waiver.

    The cartridge sets the flag/heals at these four cells and clears it outside.
    The default remains event-only. Explicit healing admission additionally
    requires the exact whole-party restoration computed from the old capacities;
    the executor separately verifies native individual/XP/box/dex custody.
    """
    if type(allow_healing) is not bool:
        raise TypeError("native purification healing allowance must be boolean")
    if (
        before.map_id != int(MapId.POKEMON_TOWER_5F)
        or raw.map_id != before.map_id
        or before.battle_state != 1
        or raw.battle_state != 0
        or raw.battle_result != 2
        or (before.player_y, before.player_x) != (raw.player_y, raw.player_x)
        or any(type(value) is not int or value < 0 for value in (raw.player_y, raw.player_x))
        or (before.enemy_species_id, before.enemy_level)
        != (raw.enemy_species_id, raw.enemy_level)
        or before.party_stats is None
        or raw.party_stats != before.party_stats
        or before.event_flags is None
        or raw.event_flags is None
        or len(before.event_flags) != len(raw.event_flags)
        or len(before.event_flags) * 8 <= int(EventFlag.IN_PURIFIED_ZONE)
    ):
        return None
    entered = (raw.player_y, raw.player_x) in {(8, 10), (8, 11), (9, 10), (9, 11)}
    old = event_flag_is_set(before.event_flags, int(EventFlag.IN_PURIFIED_ZONE))
    if old == entered:
        return None
    expected = bytearray(before.event_flags)
    index, bit = divmod(int(EventFlag.IN_PURIFIED_ZONE), 8)
    expected[index] = expected[index] | (1 << bit) if entered else expected[index] & ~(1 << bit)
    if tuple(raw.event_flags) != tuple(expected):
        return None
    if entered:
        from .red_goal_skills import _raw_party_fully_restored

        if not _raw_party_fully_restored(raw):
            return None
        if allow_healing:
            if not _exact_purified_party_restoration(before, raw):
                return None
        elif not _raw_party_fully_restored(before):
            return None
    proof = dict(
        schema="pokemon.red.native-purified-escape-event.v1",
        event="IN_PURIFIED_ZONE", event_flag=int(EventFlag.IN_PURIFIED_ZONE),
        before=old, after=entered, map_id=raw.map_id, at=[raw.player_y, raw.player_x],
        healing_performed_by_handler=False,
    )
    if allow_healing and entered and any(
        getattr(before, key) != getattr(raw, key)
        for key in ("party_hp", "party_status", "party_pp")
    ):
        proof.update(schema="pokemon.red.native-purified-escape-healing.v1",
                     resources_restored=True,
                     hp_before=list(before.party_hp), hp_after=list(raw.party_hp),
                     maximum_hp=list(before.party_max_hp),
                     moves=[list(row) for row in before.party_moves],
                     pp_before=[list(row) for row in before.party_pp],
                     pp_after=[list(row) for row in raw.party_pp],
                     status_before=list(before.party_status), status_after=list(raw.party_status))
    return proof


def _exact_purified_party_restoration(before, raw):
    """Compare the expected native heal; never mutate either observation."""
    from .red_party_pp import decode_red_party_pp

    count = before.party_count
    if (type(count) is not int or not 1 <= count <= 6 or raw.party_count != count
            or any(getattr(before, key) is None
                   or getattr(raw, key) != getattr(before, key)
                   for key in ("party_species_ids", "party_levels", "party_max_hp",
                               "party_moves", "party_stats"))
            or any(getattr(before, key) is None or len(getattr(before, key)) != count
                   for key in ("party_hp", "party_max_hp", "party_status", "party_pp"))
            or not any(hp > 0 for hp in before.party_hp)
            or any(type(hp) is not int or type(maximum) is not int
                   or not 0 <= hp <= maximum or maximum <= 0
                   for hp, maximum in zip(before.party_hp, before.party_max_hp, strict=True))
            or any(type(status) is not int or status not in {*range(8), 8, 16, 32, 64}
                   for status in before.party_status)):
        return False
    try:
        expected_pp = tuple(
            tuple((packed & 0xC0) | slot.maximum_pp
                  for packed, slot in zip(pp, decode_red_party_pp(moves, pp).moves, strict=True))
            for moves, pp in zip(before.party_moves, before.party_pp, strict=True)
        )
    except (ValueError, TypeError):
        return False
    return (raw.party_hp == before.party_max_hp
            and raw.party_status == (0,) * count and raw.party_pp == expected_pp)


def _purified_party_custody(emulator, reader):
    """Private native identities and XP plus unchanged boxed/dex state."""
    if emulator is None:
        raise ValueError("native purification healing needs full custody observation")
    from .red_party import PokemonRedPartyReader

    party = PokemonRedPartyReader(emulator)
    return (party.preparation_specimen_refs(),
            tuple((member.species_id, member.level, member.experience)
                  for member in party.read().members),
            reader.read_all_box_states(), reader.read_pokedex_state())


def verified_purified_flee_receipt(proof, receipt):
    """A serialized native heal cannot silently waive an ordinary escape receipt."""
    from .red_party_pp import decode_red_party_pp

    if (not isinstance(proof, dict)
            or proof.get("schema") != "pokemon.red.native-purified-escape-healing.v1"
            or proof.get("event") != "IN_PURIFIED_ZONE"
            or proof.get("event_flag") != int(EventFlag.IN_PURIFIED_ZONE)
            or proof.get("before") is not False or proof.get("after") is not True
            or proof.get("resources_restored") is not True
            or proof.get("healing_performed_by_handler") is not False
            or proof.get("individual_xp_box_dex_custody_verified") is not True
            or proof.get("map_id") != int(MapId.POKEMON_TOWER_5F)
            or proof.get("at") not in ([8, 10], [8, 11], [9, 10], [9, 11])
            or proof.get("at") != [receipt.player_y, receipt.player_x]
            or receipt.map_id != proof["map_id"] or receipt.expected_map_id != proof["map_id"]
            or receipt.battle_result != 2 or receipt.hp_scope != "whole_party"):
        return False
    try:
        hp0, hp1, maximum = (tuple(proof[key]) for key in ("hp_before", "hp_after", "maximum_hp"))
        s0, s1 = (tuple(proof[key]) for key in ("status_before", "status_after"))
        moves, pp0, pp1 = (tuple(tuple(row) for row in proof[key])
                           for key in ("moves", "pp_before", "pp_after"))
        expected = tuple(tuple((packed & 0xC0) | slot.maximum_pp
                               for packed, slot in zip(pp, decode_red_party_pp(mv, pp).moves, strict=True))
                         for mv, pp in zip(moves, pp0, strict=True))
        count = len(hp0)
        return (1 <= count <= 6 and all(len(vector) == count
                    for vector in (hp1, maximum, s0, s1, moves, pp0, pp1))
                and all(type(hp) is int and type(cap) is int and 0 <= hp <= cap and cap > 0
                        for hp, cap in zip(hp0, maximum, strict=True))
                and any(hp0) and hp1 == maximum and s1 == (0,) * count
                and all(type(s) is int and s in {*range(8), 8, 16, 32, 64} for s in s0)
                and pp1 == expected and receipt.initial_hp == sum(hp0)
                and receipt.final_hp == sum(hp1)
                and (hp0 != hp1 or pp0 != pp1 or s0 != s1)
                and receipt.pp_preserved is (pp0 == pp1)
                and receipt.status_preserved is (s0 == s1))
    except (KeyError, ValueError, TypeError):
        return False


def validate_flee_party(
    before, raw, *, allow_new_faints=False, allow_status_changes=False,
    allow_native_purified_transition=False,
    allow_native_purified_healing=False,
):
    """Preserve complete resources; new native faints need explicit permission."""
    if type(allow_new_faints) is not bool:
        raise TypeError("native faint allowance must be boolean")
    if type(allow_status_changes) is not bool:
        raise TypeError("native status allowance must be boolean")
    if type(allow_native_purified_transition) is not bool:
        raise TypeError("native purification allowance must be boolean")
    if type(allow_native_purified_healing) is not bool:
        raise TypeError("native purification healing allowance must be boolean")
    if allow_native_purified_healing and not allow_native_purified_transition:
        raise ValueError("native purification healing needs its exact location transition")
    healing = (purified_zone_escape_event(before, raw, allow_healing=True)
               if allow_native_purified_healing else None)
    restored = bool(healing and healing.get("resources_restored"))
    count = before.party_count
    fields = (
        "party_species_ids",
        "party_levels",
        "party_max_hp",
        "party_moves",
        "party_pp",
        "party_status",
    )
    if type(count) is not int or not 1 <= count <= 6 or raw.party_count != count:
        raise ValueError("escape party count missing or changed")
    for field in (*fields, "party_hp"):
        old, new = getattr(before, field), getattr(raw, field)
        if old is None or new is None or len(old) != count or len(new) != count:
            raise ValueError("escape party observations incomplete")
        native_status = field == "party_status" and allow_status_changes
        if native_status and any(
            type(value) is not int or value not in {*range(8), 8, 16, 32, 64}
            for value in (*old, *new)
        ):
            raise ValueError("escape status value invalid")
        if (field in fields and old != new and not native_status
                and not (restored and field in {"party_status", "party_pp"})):
            raise ValueError("escape party resources changed")
    if not any(hp > 0 for hp in before.party_hp):
        raise ValueError("escape requires a living party member")
    if not restored and any(
        not (new == 0 if old == 0 else (0 if allow_new_faints else 1) <= new <= old)
        for old, new in zip(before.party_hp, raw.party_hp, strict=True)
    ):
        raise ValueError("escape party HP invalid or new faint")
    if not any(hp > 0 for hp in raw.party_hp):
        raise ValueError("escape cannot conceal a blackout")
    for field in ("bag_items", "player_money", "badge_bits", "event_flags"):
        old, new = getattr(before, field), getattr(raw, field)
        if old is None or new != old:
            if (
                field == "event_flags"
                and allow_native_purified_transition
                and purified_zone_escape_event(
                    before, raw, allow_healing=allow_native_purified_healing) is not None
            ):
                continue
            raise ValueError("escape protected state changed")


def flee_with_fainted_lead(
    executor,
    reader,
    encounter,
    *,
    expected_map_id,
    route_name,
    stabilization_frames,
    error_type,
    allow_new_faints=False,
    allow_status_changes=False,
    emulator=None,
    allow_opponent_ko_exit=False,
    allow_native_purified_transition=False,
    allow_native_purified_healing=False,
):
    """RUN support; no attacks/items, with disclosed compulsory replacements."""
    if type(stabilization_frames) is not int or stabilization_frames <= 0:
        raise ValueError("escape needs positive stabilization frames")
    if type(allow_opponent_ko_exit) is not bool:
        raise TypeError("ordinary opponent KO closure requires an explicit boolean")
    if type(allow_native_purified_transition) is not bool:
        raise TypeError("native purification allowance must be boolean")
    if type(allow_native_purified_healing) is not bool:
        raise TypeError("native purification healing allowance must be boolean")
    if allow_native_purified_healing and not allow_native_purified_transition:
        raise ValueError("native purification healing needs its exact location transition")
    custody = None
    if (allow_native_purified_healing
            and encounter.map_id == int(MapId.POKEMON_TOWER_5F)
            and (encounter.player_y, encounter.player_x) in {(8, 10), (8, 11), (9, 10), (9, 11)}):
        from .red_goal_skills import _raw_party_fully_restored

        if not _raw_party_fully_restored(encounter):
            try:
                custody = _purified_party_custody(emulator, reader)
            except ValueError as exc:
                raise error_type(f"{route_name}: {exc}") from exc
    if allow_opponent_ko_exit:
        identity_reader = getattr(reader, "read_retained_wild_identity", None)
        identity = identity_reader() if callable(identity_reader) else None
        # Conservative Gen I one-off protection, including transformed targets.
        # These are cartridge internal species IDs, never actor features.
        if identity is None or identity.original_species_id in {73, 74, 75, 131, 132}:
            raise error_type("ordinary opponent KO closure lacks protected native identity")
    attempts = 0
    dismissals = 0
    next_mon_choices = 0
    forced_switch_slots = []
    teleport_witness = None

    def check(raw):
        nonlocal teleport_witness
        if (
            raw.map_id != expected_map_id
            or raw.battle_state not in (0, 1)
            or (raw.player_y, raw.player_x) != (encounter.player_y, encounter.player_x)
        ):
            raise error_type(f"{route_name} escape boundary changed")
        try:
            validate_flee_party(
                encounter,
                raw,
                allow_new_faints=allow_new_faints,
                allow_status_changes=allow_status_changes,
                allow_native_purified_transition=allow_native_purified_transition,
                allow_native_purified_healing=allow_native_purified_healing,
            )
            event = (purified_zone_escape_event(encounter, raw, allow_healing=True)
                     if allow_native_purified_healing else None)
            if event and event.get("resources_restored"):
                if custody is None or _purified_party_custody(emulator, reader) != custody:
                    raise ValueError("native purification healing changed individual/XP/box/dex custody")
        except ValueError as exc:
            raise error_type(f"{route_name}: {exc}") from exc

        observe_teleport = getattr(reader, 'read_live_wild_teleport_witness', None)
        observed = observe_teleport(raw) if callable(observe_teleport) else None
        if type(observed) is NativeWildTeleportWitness:
            if (observed.map_id, observed.player_x, observed.player_y,
                    observed.enemy_species_id, observed.enemy_level) == (
                    encounter.map_id, encounter.player_x, encounter.player_y,
                    encounter.enemy_species_id, encounter.enemy_level):
                teleport_witness = observed

    def pulse(kind, value=None, frames=120):
        executor.execute(MacroAction(kind, value))
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))

    check(encounter)
    for _ in range(128):
        raw = reader.read()
        check(raw)
        if raw.battle_state == 0:
            if not reader.read_input_readiness().ready:
                if dismissals >= 16:
                    raise error_type("party escape exit settlement budget")
                pulse(MacroActionKind.CANCEL, frames=24)
                dismissals += 1
                continue
            executor.execute(MacroAction(MacroActionKind.WAIT, repeat=stabilization_frames))
            raw = reader.read()
            check(raw)
            healing = (purified_zone_escape_event(encounter, raw, allow_healing=True)
                       if allow_native_purified_healing else None)
            if healing and healing.get("resources_restored"):
                # check() just authenticated the complete native custody tuple.
                healing["individual_xp_box_dex_custody_verified"] = True
            else:
                healing = None
            evidence = Route1WildFleeEvidence(
                initial_battle_state=1,
                final_battle_state=raw.battle_state,
                battle_result=raw.battle_result,
                expected_map_id=expected_map_id,
                map_id=raw.map_id,
                player_x=raw.player_x,
                player_y=raw.player_y,
                enemy_species_id=encounter.enemy_species_id or 0,
                enemy_level=encounter.enemy_level or 0,
                initial_hp=sum(encounter.party_hp),
                final_hp=sum(raw.party_hp),
                maximum_hp_preserved=True,
                party_preserved=True,
                level_preserved=True,
                pp_preserved=raw.party_pp == encounter.party_pp,
                status_preserved=raw.party_status == encounter.party_status,
                status_changes_allowed=allow_status_changes,
                ordinary_opponent_ko_exit=(
                    allow_opponent_ko_exit and raw.enemy_hp == 0 and raw.battle_result == 0
                ),
                native_status_changes=tuple(
                    (slot, old, new)
                    for slot, (old, new) in enumerate(
                        zip(encounter.party_status, raw.party_status, strict=True), 1
                    )
                    if old != new
                ),
                control_ready=reader.read_input_readiness().ready,
                run_attempts=attempts,
                stabilization_frames=stabilization_frames,
                hp_scope="whole_party",
                # Cancelling the native "Use next POKEMON?" prompt can
                # escape without ever reaching RUN. Full-party checks above
                # still prohibit new faints, attacks, resource or event changes.
                faint_prompt_exit=(
                    attempts == 0 and (encounter.battler_hp == 0 or next_mon_choices > 0)
                ),
                party_faints_allowed=allow_new_faints,
                new_fainted_slots=tuple(
                    i
                    for i, (old, new) in enumerate(
                        zip(encounter.party_hp, raw.party_hp, strict=True), 1
                    )
                    if old > 0 and new == 0
                ),
                forced_switch_slots=tuple(forced_switch_slots),
                native_purified_healing=healing,
                native_opponent_teleport_exit=(teleport_witness if teleport_witness is not None
                    and raw.battle_result == 0 and raw.enemy_hp == teleport_witness.enemy_hp
                    and (raw.map_id, raw.player_x, raw.player_y, raw.enemy_species_id, raw.enemy_level)
                        == (teleport_witness.map_id, teleport_witness.player_x, teleport_witness.player_y,
                            teleport_witness.enemy_species_id, teleport_witness.enemy_level)
                    else None),
            )
            if not evidence.verified:
                raise error_type("party escape terminal did not verify")
            note_observed_battle_exit()
            return evidence
        if allow_opponent_ko_exit and raw.enemy_hp == 0:
            # A retained victory can still own a move-learning YES/NO gate.
            # Blind B chooses NO at "Abandon learning?" and restarts the
            # dialogue forever. Reuse the actor's observed preservation action;
            # never select a replacement or relax the complete-party proof.
            detector = getattr(reader, "read_move_learning_prompt", None)
            prompt = detector(raw) if callable(detector) else None
            if prompt is not None:
                from .battle_runtime import move_learning_preservation_action

                action = move_learning_preservation_action(prompt)
                pulse(action.kind, action.value, frames=24)
                continue
        if emulator is not None and raw.battler_hp == 0:
            from .battle_recovery import _forced_party_menu_ready, switch_active_battler

            if _forced_party_menu_ready(emulator, raw.party_count):
                target = next(i for i, hp in enumerate(raw.party_hp) if hp > 0)
                switch_active_battler(
                    executor,
                    reader,
                    emulator,
                    target,
                    expected_battle_state=1,
                    label="mechanical wild escape replacement",
                    wait_frames=120,
                    resume_forced_switch=True,
                )
                forced_switch_slots.append(target + 1)
                continue
        read_prompt = getattr(reader, "read_wild_next_mon_prompt", None)
        next_mon = read_prompt(raw) if callable(read_prompt) else None
        if next_mon is not None:
            if type(next_mon) is not int or next_mon not in {0, 1}:
                raise error_type("wild faint prompt cursor invalid")
            if next_mon == 0:
                pulse(MacroActionKind.MOVE, "down")
            else:
                if next_mon_choices >= 16:
                    raise error_type("wild faint escape prompt budget")
                pulse(MacroActionKind.CONFIRM, frames=240)
                next_mon_choices += 1
            continue
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            # Native faint text needs A before its observed YES/NO gate.
            # A cannot choose an attack while this authenticated battler is dead.
            # Living entry text retains the historical safe B settlement.
            pulse(
                MacroActionKind.CONFIRM
                if callable(read_prompt) and raw.battler_hp == 0
                else MacroActionKind.CANCEL,
                frames=240,
            )
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            pulse(MacroActionKind.CANCEL)
            continue
        if menu.phase is not BattleMenuPhase.MAIN:
            raise error_type("party escape requires MAIN, not a party choice")
        index = raw.active_party_index
        if (
            type(index) is not int
            or not 0 <= index < raw.party_count
            or raw.party_hp[index] <= 0
            or raw.active_party_hp != raw.party_hp[index]
        ):
            raise error_type("party escape MAIN has no authenticated living battler")
        command = menu.selected_main_command
        if command == 3:
            if attempts >= 16:
                raise error_type("party escape RUN budget")
            pulse(MacroActionKind.CONFIRM, frames=240)
            attempts += 1
        elif command in (0, 1, 2):
            pulse(MacroActionKind.MOVE, {0: "right", 1: "right", 2: "down"}[command])
        else:
            raise error_type("party escape command unknown")
    raise error_type("party escape transition budget")
