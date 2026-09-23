"""Resource-verified incidental escape when party slot one has fainted."""

from .actions import MacroAction, MacroActionKind
from .battle_runtime import note_observed_battle_exit
from .observation import BattleMenuPhase
from .route_1_wild import Route1WildFleeEvidence


def validate_flee_party(before, raw):
    """Require complete observations; pre-existing faints may not conceal new ones."""
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
        if field in fields and old != new:
            raise ValueError("escape party resources changed")
    if not any(hp > 0 for hp in before.party_hp):
        raise ValueError("escape requires a living party member")
    if any(
        not (new == 0 if old == 0 else 0 < new <= old)
        for old, new in zip(before.party_hp, raw.party_hp, strict=True)
    ):
        raise ValueError("escape party HP invalid or new faint")
    for field in ("bag_items", "player_money", "badge_bits", "event_flags"):
        old, new = getattr(before, field), getattr(raw, field)
        if old is None or new != old:
            raise ValueError("escape protected state changed")


def flee_with_fainted_lead(
    executor, reader, encounter, *, expected_map_id, route_name, stabilization_frames, error_type
):
    """Disclosed RUN support; no attacks, item use, or reserve selection."""
    if type(stabilization_frames) is not int or stabilization_frames <= 0:
        raise ValueError("escape needs positive stabilization frames")
    attempts = 0
    dismissals = 0

    def check(raw):
        if (
            raw.map_id != expected_map_id
            or raw.battle_state not in (0, 1)
            or (raw.player_y, raw.player_x) != (encounter.player_y, encounter.player_x)
        ):
            raise error_type(f"{route_name} escape boundary changed")
        try:
            validate_flee_party(encounter, raw)
        except ValueError as exc:
            raise error_type(f"{route_name}: {exc}") from exc

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
                pp_preserved=True,
                status_preserved=True,
                control_ready=reader.read_input_readiness().ready,
                run_attempts=attempts,
                stabilization_frames=stabilization_frames,
                hp_scope="whole_party",
            )
            if not evidence.verified:
                raise error_type("party escape terminal did not verify")
            note_observed_battle_exit()
            return evidence
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            # Battle entry may still report the fainted lead before auto-sendout.
            pulse(MacroActionKind.CANCEL, frames=240)
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
