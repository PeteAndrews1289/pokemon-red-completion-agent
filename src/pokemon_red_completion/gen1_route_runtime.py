"""Pokémon Red/Blue adapters for the game-neutral route executor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleControlRequest,
    recovery_request_matches,
)
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    MoveSlotPolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.battle_semantics import STAB_MULTIPLIER
from pokemon_red_completion.gen1_repel import gen1_repel_resource
from pokemon_red_completion.gen1_story_routing import gen1_story_capabilities
from pokemon_red_completion.observation import (
    EventFlag,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    event_flag_is_set,
)
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.route_1_wild import Route1WildFleeEvidence, flee_wild
from pokemon_red_completion.route_executor import (
    InterruptionReceipt,
    RouteActionPort,
    RouteExecutionError,
    TraversalHazard,
    TraversalSnapshot,
)


class Gen1HazardProjector(Protocol):
    def observe_hazards(self, raw: RawGameState) -> tuple[TraversalHazard, ...]: ...


class Gen1FieldBlackoutPending(RouteExecutionError):
    """Observed poison emptied the party; the route has not settled that loss."""


@dataclass(slots=True)
class Gen1TraversalObserver:
    """Project revision-decoded Red/Blue state into portable traversal state."""

    reader: PokemonRedStateReader
    hazard_projector: Gen1HazardProjector | None = None
    capability_projector: Callable[[RawGameState], frozenset[str]] | None = None
    observe_progress: Callable[[RawGameState], object] | None = None

    def observe(self) -> TraversalSnapshot:
        raw = self.reader.read()
        if (
            not raw.game_started
            or raw.map_id is None
            or raw.player_y is None
            or raw.player_x is None
            or raw.battle_state is None
        ):
            raise RouteExecutionError("Gen I traversal state is unavailable")
        interruption = _interruption_kind(raw.battle_state)
        if interruption is None and self.reader.trainer_engagement_active():
            interruption = "trainer_engagement"
        readiness = self.reader.read_input_readiness()
        input_ready = readiness.ready
        if (
            interruption is None
            and self.reader.read_bottom_dialogue_box_visible()
        ):
            interruption = "scripted_dialogue"
        if (
            interruption is None and not input_ready and raw.ss_anne_departure_pending
            and readiness.joy_ignore == 255 and not readiness.npc_movement_script_table
        ):
            interruption = "native_ship_departure"
        ready = interruption is None and input_ready
        if ready and self.observe_progress is not None:
            # Record only an actually observed field boundary. Planned maps and
            # unsettled battle/script frames cannot supply historical visits.
            # The existing semantic observer still enforces prerequisites.
            self.observe_progress(raw)
        movement_mode = self.reader.read_overworld_movement_mode()
        occupied = frozenset() if not ready else self.reader.read_visible_object_coordinates()
        hazards = (
            ()
            if not ready or self.hazard_projector is None
            else self.hazard_projector.observe_hazards(raw)
        )
        projected_capabilities = (
            self.capability_projector(raw) if self.capability_projector is not None else frozenset()
        )
        if not isinstance(projected_capabilities, frozenset) or any(
            not isinstance(item, str) or not item for item in projected_capabilities
        ):
            raise RouteExecutionError(
                "Gen I capability projector returned an invalid capability set"
            )
        return TraversalSnapshot(
            map_id=raw.map_id,
            at=(raw.player_y, raw.player_x),
            ready=ready,
            interruption=interruption,
            mode=movement_mode.traversal_mode,
            occupied=occupied,
            hazards=hazards,
            capabilities=gen1_story_capabilities(raw).union(projected_capabilities),
            resources=(gen1_repel_resource(raw),),
            last_outside_map=self.reader.read_retained_outside_map(),
        )


@dataclass(slots=True)
class Gen1WildFleeHandler:
    """Restore the exact overworld boundary after a bounded wild encounter."""

    executor: RouteActionPort
    reader: PokemonRedStateReader
    maximum_flees: int
    stabilization_frames: int
    route_name: str = "cartridge-composed route"
    allow_party_faints: bool = False
    emulator: object | None = None
    allow_field_faint_dialogue: bool = False
    field_faint_warps: tuple[tuple[int, tuple[int, int], int, tuple[int, int]], ...] = ()
    evidence: list[Route1WildFleeEvidence] = field(default_factory=list, init=False)
    field_faint_evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)
    field_healing_evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)
    ship_departure_evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)
    _field_boundary: RawGameState | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if type(self.maximum_flees) is not int or self.maximum_flees < 0:  # noqa: E721
            raise ValueError("maximum_flees must be a non-negative integer")
        if type(self.stabilization_frames) is not int or self.stabilization_frames <= 0:  # noqa: E721
            raise ValueError("stabilization_frames must be a positive integer")
        if not self.route_name:
            raise ValueError("a route name is required")
        if type(self.allow_party_faints) is not bool:
            raise TypeError("wild faint recovery opt-in must be boolean")
        if type(self.allow_field_faint_dialogue) is not bool:
            raise TypeError("field faint dialogue opt-in must be boolean")
        if not isinstance(self.field_faint_warps, tuple) or any(
            not isinstance(warp, tuple) or len(warp) != 4
            or any(type(warp[index]) is not int or warp[index] < 0 for index in (0, 2))
            or warp[0] == warp[2]
            or any(not isinstance(warp[index], tuple) or len(warp[index]) != 2
                   or any(type(value) is not int or value < 0 for value in warp[index])
                   for index in (1, 3))
            for warp in self.field_faint_warps
        ):
            raise ValueError("field faint warps need exact declared native endpoints")
        if self.field_faint_warps and not self.allow_field_faint_dialogue:
            raise ValueError("field faint warps require field faint dialogue admission")
        if self.allow_field_faint_dialogue:
            if not self.allow_party_faints:
                raise ValueError("field faint dialogue requires ordinary faint admission")
            self._field_boundary = self.reader.read()

    @property
    def handled_hazard_kinds(self) -> frozenset[str]:
        return frozenset()

    @property
    def handled_interruption_kinds(self) -> frozenset[str]:
        kinds = {"native_ship_departure"}
        if self.maximum_flees:
            kinds.add("wild_battle")
        if self.allow_field_faint_dialogue:
            kinds.add("scripted_dialogue")
        return frozenset(kinds)

    def has_new_field_faint(self, current: RawGameState) -> bool:
        """Select the strict faint verifier; this is not proof of a legal faint."""
        before = self._field_boundary
        return bool(before is not None and before.party_hp is not None
                    and current.party_hp is not None
                    and len(before.party_hp) == len(current.party_hp)
                    and any(old > 0 and hp == 0 for old, hp in
                            zip(before.party_hp, current.party_hp, strict=True)))

    def observe_native_field_boundary(self) -> None:
        """Refresh only after an independently verified native field return."""
        if not self.allow_field_faint_dialogue:
            return
        current = self.reader.read()
        ready = self.reader.read_input_readiness()
        if (current.battle_state != 0 or not ready.ready
                or self.reader.read_bottom_dialogue_box_visible()
                or self.reader.trainer_engagement_active()):
            raise RouteExecutionError("native field boundary is not settled")
        self._field_boundary = current

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        if interruption.interruption == "native_ship_departure":
            return self._settle_ship_departure(interruption)
        if interruption.interruption == "scripted_dialogue" and self.allow_field_faint_dialogue:
            self._raise_new_field_blackout(interruption)
            return self._dismiss_field_faint(interruption)
        if interruption.interruption != "wild_battle":
            raise RouteExecutionError(f"Gen I route cannot dismiss {interruption.interruption!r}")
        if len(self.evidence) >= self.maximum_flees:
            raise RouteExecutionError(
                f"{self.route_name} exceeded its {self.maximum_flees}-flee budget"
            )
        encounter = self.reader.read()
        if (
            encounter.map_id != interruption.map_id
            or (encounter.player_y, encounter.player_x) != interruption.at
        ):
            raise RouteExecutionError("wild interruption drifted before recovery")
        escape, extra = flee_wild, {}
        if self.allow_party_faints:
            from .wild_party_flee import flee_with_fainted_lead

            escape, extra = (
                flee_with_fainted_lead,
                {"allow_new_faints": True, "allow_status_changes": True, "emulator": self.emulator,
                 "allow_opponent_ko_exit": callable(
                     getattr(self.reader, "read_retained_wild_identity", None)
                 )},
            )
            if self.allow_field_faint_dialogue:
                extra["allow_native_purified_transition"] = True
                extra["allow_native_purified_healing"] = True
        receipt = escape(
            self.executor,
            self.reader,
            encounter,
            expected_map_id=interruption.map_id,
            route_name=self.route_name,
            stabilization_frames=self.stabilization_frames,
            error_type=RouteExecutionError,
            **extra,
        )
        self.evidence.append(receipt)
        native_event = None
        if self.allow_field_faint_dialogue:
            from .wild_party_flee import purified_zone_escape_event

            native_event = purified_zone_escape_event(
                encounter, self.reader.read(), allow_healing=True)
            if native_event is not None and native_event.get("resources_restored"):
                native_event["individual_xp_box_dex_custody_verified"] = True
            if native_event is not None:
                record = getattr(self.executor, "record_diagnostic_event", None)
                if callable(record):
                    record("native_purified_zone_escape", dict(
                        actor="rule_based_support", model_queries=0,
                        native_event=native_event, escape=receipt.public_dict(),
                    ))
        if self.allow_field_faint_dialogue:
            self._field_boundary = self.reader.read()
        pending = {}
        if self.reader.trainer_engagement_active():
            # A successful wild escape can reveal an already triggered native
            # trainer at this same tile. Hand it to the declared trainer adapter;
            # a flee receipt is not proof of free traversal or a trainer win.
            after = self.reader.read()
            if (
                not receipt.verified
                or after.battle_state != 0
                or (after.map_id, after.player_y, after.player_x)
                != (receipt.map_id, receipt.player_y, receipt.player_x)
            ):
                raise RouteExecutionError("wild escape successor lacks its verified field boundary")
            pending["pending_interruption_kind"] = "trainer_engagement"
        return InterruptionReceipt(
            kind="wild_battle",
            resumed_map=receipt.map_id,
            resumed_at=(receipt.player_y, receipt.player_x),
            details={
                **receipt.public_dict(), **pending,
                **({"native_field_event": native_event} if native_event is not None else {}),
            },
        )

    def _settle_ship_departure(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        """Wait for one authenticated native animation and its automatic city warp.

        No directional input, dialogue, healing, battle or alternative goal is
        supplied. The caller retains all costs and must replan its original goal.
        """
        before = self.reader.read()
        readiness = self.reader.read_input_readiness()
        if (
            self.ship_departure_evidence or not before.ss_anne_departure_pending
            or (interruption.map_id, interruption.at) != (before.map_id, (2, 14))
            or readiness.ready or readiness.joy_ignore != 255
            or readiness.npc_movement_script_table
            or self.reader.trainer_engagement_active()
            or self.reader.read_bottom_dialogue_box_visible()
        ):
            raise RouteExecutionError("ship departure lacks its exact native pending boundary")
        protected = (
            "party_count", "party_species_ids", "party_levels", "party_hp", "party_max_hp",
            "party_stats", "party_status", "party_moves", "party_pp", "player_money",
            "bag_items", "badge_bits",
        )
        if any(getattr(before, key) is None for key in protected):
            raise RouteExecutionError("ship departure resources are unavailable")
        boxes, dex = self.reader.read_all_box_states(), self.reader.read_pokedex_state()
        assert before.event_flags is not None
        expected_events = bytearray(before.event_flags)
        for flag in (EventFlag.STARTED_WALKING_OUT_OF_DOCK,
                     EventFlag.WALKED_PAST_GUARD_AFTER_SS_ANNE_LEFT):
            expected_events[int(flag) // 8] |= 1 << (int(flag) % 8)
        allowed_bits = {
            int(EventFlag.STARTED_WALKING_OUT_OF_DOCK),
            int(EventFlag.WALKED_PAST_GUARD_AFTER_SS_ANNE_LEFT),
        }
        for pulse in range(33):
            current = self.reader.read()
            controls = self.reader.read_input_readiness()
            # During the native warp the engine changes wCurMap before it
            # replaces the old dock coordinates. This is not city control.
            native_warp_in_flight = bool(
                current.map_id == int(MapId.VERMILION_CITY)
                and (current.player_y, current.player_x) == (0, 14)
                and not controls.ready and controls.joy_ignore == 255
                and controls.simulated_joypad_index == 0
                and controls.player_moving_direction == 8
                and controls.status_flags_5 & 128 and controls.movement_flags & 4
                and current.event_flags is not None
                and event_flag_is_set(
                    current.event_flags, int(EventFlag.STARTED_WALKING_OUT_OF_DOCK)
                )
                and not event_flag_is_set(
                    current.event_flags, int(EventFlag.WALKED_PAST_GUARD_AFTER_SS_ANNE_LEFT)
                )
            )
            if (
                current.battle_state != 0 or current.event_flags is None
                or len(current.event_flags) != len(before.event_flags)
                or any(getattr(current, key) != getattr(before, key) for key in protected)
                or self.reader.read_all_box_states() != boxes
                or self.reader.read_pokedex_state() != dex
                or self.reader.trainer_engagement_active()
                or self.reader.read_bottom_dialogue_box_visible()
                or not native_warp_in_flight and (
                    current.map_id, (current.player_y, current.player_x)
                ) not in {
                    (int(MapId.VERMILION_DOCK), (2, 14)),
                    (int(MapId.VERMILION_DOCK), (1, 14)),
                    (int(MapId.VERMILION_DOCK), (0, 14)),
                    (int(MapId.VERMILION_CITY), (29, 18)),
                    # The city script walks two native UP steps after arrival.
                    # Only the final row29 may be accepted as ready control.
                    (int(MapId.VERMILION_CITY), (30, 18)),
                    (int(MapId.VERMILION_CITY), (31, 18)),
                }
                or any(
                    old & ~new or any((old ^ new) & (1 << bit)
                                     and index * 8 + bit not in allowed_bits
                                     for bit in range(8))
                    for index, (old, new) in enumerate(zip(
                        before.event_flags, current.event_flags, strict=True
                    ))
                )
            ):
                raise RouteExecutionError("ship departure changed its protected native boundary")
            if controls.ready:
                if (
                    current.map_id != int(MapId.VERMILION_CITY)
                    or (current.player_y, current.player_x) != (29, 18)
                    or current.event_flags != bytes(expected_events)
                ):
                    raise RouteExecutionError(
                        "ship departure did not verify its native city landing"
                    )
                receipt = InterruptionReceipt(
                    "native_ship_departure", current.map_id, (29, 18),
                    dict(verified=True, source_map=int(MapId.VERMILION_DOCK),
                         automatic_native_warp=True, wait_actions=pulse,
                         wait_frames_requested=pulse * 96, model_queries=0,
                         protected_resources_unchanged=True),
                    allows_relocation=True, allows_map_transition=True,
                )
                self.ship_departure_evidence.append(receipt)
                return receipt
            if pulse == 32:
                raise RouteExecutionError("ship departure exceeded its bounded settlement")
            self.executor.execute(MacroAction(MacroActionKind.WAIT, repeat=96))
        raise AssertionError("unreachable ship departure settlement")

    def _raise_new_field_blackout(self, interruption: TraversalSnapshot) -> None:
        """Expose one proved loss without dismissing text or claiming route success.

        This separate handoff keeps the surviving-party faint handler unchanged.
        Only a previously living poisoned roster, now entirely fainted with native
        cleared statuses and unchanged resources, can reach the blackout owner.
        """
        before, current = self._field_boundary, self.reader.read()
        ready = self.reader.read_input_readiness()
        if (
            before is None or self.emulator is None or self.emulator.pressed_buttons
            or before.battle_state != 0 or not before.game_started or not current.game_started
            or current.battle_state != 0 or ready.ready or ready.joy_ignore
            or ready.simulated_joypad_index or ready.npc_movement_script_table
            or self.reader.trainer_engagement_active()
            or not self.reader.read_bottom_dialogue_box_visible()
            or (current.map_id, (current.player_y, current.player_x))
            != (interruption.map_id, interruption.at)
            or not before.party_hp or not any(before.party_hp)
            or before.party_count != len(before.party_hp)
            or current.party_hp != (0,) * len(before.party_hp)
            or before.party_status is None
            or len(before.party_status) != len(before.party_hp)
            or current.party_status != (0,) * len(before.party_hp)
            or any(hp > 0 and status != 8 for hp, status in zip(
                before.party_hp, before.party_status, strict=True))
            or any(getattr(before, key) is None or getattr(current, key) != getattr(before, key)
                   for key in (
                       "party_count", "party_species_ids", "party_levels", "party_max_hp",
                       "party_stats", "party_moves", "party_pp", "player_money", "bag_items",
                       "badge_bits", "event_flags"))
        ):
            return
        raise Gen1FieldBlackoutPending(
            "observed all-party field poison faint requires native blackout"
        )

    def _dismiss_field_faint(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        """Existing bounded text settlement for a newly observed poison faint.

        An already-started warp may finish only at its declared native endpoint.
        Later poisoned members may lose the single pending tick after the faint
        message. Unrelated scripts, healing, other damage and resource changes
        remain errors. This never revives or selects a goal or battle action.
        """
        before, current = self._field_boundary, self.reader.read()
        if (
            current.map_id == int(MapId.POKEMON_TOWER_5F)
            and current.event_flags is not None
            and len(current.event_flags) * 8 > int(EventFlag.IN_PURIFIED_ZONE)
            and event_flag_is_set(current.event_flags, int(EventFlag.IN_PURIFIED_ZONE))
        ):
            return self._dismiss_purified_zone(interruption, current)
        ready = self.reader.read_input_readiness()
        if (before is None or current.battle_state != 0 or ready.joy_ignore
                or ready.simulated_joypad_index or ready.npc_movement_script_table
                or self.reader.trainer_engagement_active()
                or not current.party_hp or not before.party_hp or not before.party_status
                or len(current.party_hp) != len(before.party_hp)
                or len(before.party_status) != len(before.party_hp)
                or current.party_species_ids != before.party_species_ids
                or not any(hp > 0 for hp in current.party_hp)
                or len(self.field_faint_evidence) >= len(current.party_hp)):
            raise RouteExecutionError("field dialogue is not an admitted native faint")
        slots = tuple(index + 1 for index, (old_hp, hp, status) in enumerate(zip(
            before.party_hp, current.party_hp, before.party_status, strict=True
        )) if old_hp > 0 and hp == 0 and status & 0x08)
        if not slots:
            raise RouteExecutionError("field dialogue lacks a newly poisoned member faint")
        boxes, dex = self.reader.read_all_box_states(), self.reader.read_pokedex_state()
        handler = Gen1RouteInterruptionHandler(
            self.executor, self.reader, maximum_flees=0, maximum_trainer_battles=0,
            stabilization_frames=self.stabilization_frames, maximum_scripted_dialogues=1,
            max_scripted_dialogue_pulses=32, route_name=self.route_name,
        )
        receipt = handler._dismiss_scripted_dialogue(interruption)
        after = self.reader.read()
        landing = (receipt.resumed_map, receipt.resumed_at)
        same_tile = landing == (interruption.map_id, interruption.at)
        declared_warp = (interruption.map_id, interruption.at,
                         receipt.resumed_map, receipt.resumed_at) in self.field_faint_warps
        # Gen I processes field poison in party order. A faint message pauses
        # that loop; only later, still-poisoned living members can receive its
        # remaining one-point tick. Never admit healing or another faint here.
        pending_ticks = []
        hp_preserved = (after.party_hp is not None and current.party_status is not None
                        and len(after.party_hp) == len(current.party_hp)
                        and len(current.party_status) == len(current.party_hp))
        if hp_preserved:
            for index, (old_hp, hp, status) in enumerate(zip(
                current.party_hp, after.party_hp, current.party_status, strict=True
            ), start=1):
                if type(old_hp) is not int or type(hp) is not int or type(status) is not int:
                    hp_preserved = False
                elif hp != old_hp:
                    if index > min(slots) and status & 0x08 and old_hp > 1 and hp == old_hp - 1:
                        pending_ticks.append(index)
                    else:
                        hp_preserved = False
        if (not (same_tile or declared_warp) or not hp_preserved
                or any(getattr(after, key) != getattr(current, key) for key in (
                    "player_money", "bag_items", "badge_bits", "event_flags",
                    "party_count", "party_species_ids", "party_levels", "party_max_hp",
                    "party_stats", "party_pp",
                    "party_status", "party_moves"))
                or self.reader.read_all_box_states() != boxes
                or self.reader.read_pokedex_state() != dex):
            raise RouteExecutionError("field faint dismissal changed protected resources")
        receipt = replace(receipt, allows_relocation=declared_warp,
            allows_map_transition=declared_warp, details={
            **receipt.details, "native_field_faint": True, "new_fainted_slots": list(slots),
            "pending_native_poison_tick_slots": pending_ticks,
            "declared_native_warp": declared_warp,
            **({"source_map": interruption.map_id} if declared_warp else {}),
            "learned_recovery": False, "model_queries": 0,
        })
        self.field_faint_evidence.append(receipt)
        self._field_boundary = after
        return receipt

    def _dismiss_purified_zone(self, interruption, current):
        """Dismiss only the already observed, native-healed Tower5 message.

        This is shared route mechanics, so a selected Center return and onward
        travel use the same check. No healing is injected and no resource change
        during text dismissal is permitted. Unknown scripts still fail.
        """
        if (
            current.battle_state != 0
            or self.reader.trainer_engagement_active()
            or not current.party_hp
            or current.party_hp != current.party_max_hp
            or current.party_status is None
            or len(current.party_status) != len(current.party_hp)
            or any(current.party_status)
        ):
            raise RouteExecutionError("purified-zone message lacks native whole-party healing")
        boxes, dex = self.reader.read_all_box_states(), self.reader.read_pokedex_state()
        handler = Gen1RouteInterruptionHandler(
            self.executor, self.reader, maximum_flees=0, maximum_trainer_battles=0,
            stabilization_frames=self.stabilization_frames, maximum_scripted_dialogues=1,
            max_scripted_dialogue_pulses=32, route_name=self.route_name,
        )
        receipt = handler._dismiss_scripted_dialogue(interruption)
        after = self.reader.read()
        if (
            (receipt.resumed_map, receipt.resumed_at) != (interruption.map_id, interruption.at)
            or any(getattr(after, key) != getattr(current, key) for key in (
                "player_money", "bag_items", "badge_bits", "event_flags",
                "party_species_ids", "party_levels", "party_hp", "party_max_hp", "party_pp",
                "party_status", "party_moves",
            ))
            or self.reader.read_all_box_states() != boxes
            or self.reader.read_pokedex_state() != dex
        ):
            raise RouteExecutionError("purified-zone dismissal changed protected resources")
        receipt = replace(receipt, allows_relocation=False, details={
            **receipt.details, "native_purified_zone": True, "already_healed": True,
            "learned_recovery": False, "model_queries": 0,
        })
        record = getattr(self.executor, "record_diagnostic_event", None)
        if not callable(record):
            record = getattr(getattr(self.executor, "delegate", None),
                             "record_diagnostic_event", None)
        if callable(record):
            record("native_purified_zone_message", dict(
                actor="rule_based_support", map_id=current.map_id,
                at=[current.player_y, current.player_x], party_hp=list(current.party_hp),
                healing_performed_by_handler=False, **receipt.details,
            ))
        self.field_healing_evidence.append(receipt)
        self._field_boundary = after
        return receipt


_BATTLE_CATALOG = PokemonRedBattleCatalog()
_RELIABLE_FINISH_HP_NUMERATOR = 1
_RELIABLE_FINISH_HP_DENOMINATOR = 3
_RELIABLE_FINISH_POWER_FLOOR = 0.75
_PERFECT_MOVE_ACCURACY = 1.0


def strongest_usable_move_slot(raw: RawGameState) -> int:
    """Choose a damaging move from live mechanics, without chapter identity.

    Expected effective power remains the default.  Near the end of an opponent's
    HP bar, prefer a perfectly accurate move when it retains enough effective
    power to be a credible finisher.  This avoids spending scarce party HP on a
    slightly stronger move's miss risk without teaching a route-specific move.
    """

    moves = raw.battler_moves
    pp = raw.battler_pp
    attacker_id = raw.active_party_species_id
    if attacker_id is None and raw.party_species_ids:
        index = raw.active_party_index or 0
        if 0 <= index < len(raw.party_species_ids):
            attacker_id = raw.party_species_ids[index]
    if moves is None or pp is None or attacker_id is None or raw.enemy_species_id is None:
        raise RouteExecutionError("route battle lacks mechanics-ranked move evidence")

    attacker = _BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(attacker_id))
    defender = _BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(raw.enemy_species_id))
    usable: list[
        tuple[
            tuple[bool, float, float, int, int, int],
            tuple[bool, float, float, int, int],
            int,
        ]
    ] = []
    for index, (move_id, packed_pp) in enumerate(zip(moves, pp, strict=False)):
        slot = index + 1
        current_pp = packed_pp & 0x3F
        if (
            move_id == 0
            or current_pp == 0
            or (raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0)
        ):
            continue
        move = _BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move_id))
        damaging = move.category != "status" and move.power > 0
        effectiveness = _BATTLE_CATALOG.type_effectiveness(
            move.type_name,
            defender.types,
        )
        stab = STAB_MULTIPLIER if move.type_name in attacker.types else 1.0
        effective_power = move.power * effectiveness * stab
        usable.append(
            (
                (
                    damaging,
                    effective_power * move.accuracy,
                    effectiveness,
                    move.power,
                    current_pp,
                    -slot,
                ),
                (
                    damaging,
                    effective_power,
                    move.accuracy,
                    current_pp,
                    -slot,
                ),
                slot,
            )
        )
    if not usable:
        raise RouteExecutionError("route battle has no usable move")
    ordinary_choice = max(usable, key=lambda row: row[0])
    strongest_effective_power = max(
        (row[1][1] for row in usable if row[1][0]),
        default=0.0,
    )
    low_hp = (
        raw.enemy_hp is not None
        and raw.enemy_max_hp is not None
        and 0 < raw.enemy_hp <= raw.enemy_max_hp
        and raw.enemy_hp * _RELIABLE_FINISH_HP_DENOMINATOR
        <= raw.enemy_max_hp * _RELIABLE_FINISH_HP_NUMERATOR
    )
    if low_hp and strongest_effective_power > 0:
        reliable = tuple(
            row
            for row in usable
            if row[1][0]
            and row[1][2] == _PERFECT_MOVE_ACCURACY
            and row[1][1] >= strongest_effective_power * _RELIABLE_FINISH_POWER_FLOOR
        )
        if reliable:
            return max(reliable, key=lambda row: row[1])[2]
    return ordinary_choice[2]


@dataclass(slots=True)
class Gen1RouteInterruptionHandler:
    """Resolve wild encounters and unavoidable trainer battles in one route."""

    executor: RouteActionPort
    reader: PokemonRedStateReader
    maximum_flees: int
    maximum_trainer_battles: int
    stabilization_frames: int
    route_name: str = "cartridge-composed route"
    max_trainer_intro_pulses: int = 32
    move_slot_policy: MoveSlotPolicy = strongest_usable_move_slot
    trainer_recovery_required: Callable[[RawGameState], bool] | None = None
    trainer_recovery_action: Callable[[], None] | None = None
    maximum_trainer_recoveries: int = 0
    maximum_scripted_dialogues: int = 0
    max_scripted_dialogue_pulses: int = 8
    allow_wild_faints: bool = False
    emulator: object | None = None
    # A configured mechanics owner survives wrappers and route replanning.
    wild_handler: Gen1WildFleeHandler | None = field(default=None, repr=False)
    trainer_evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)
    scripted_dialogue_evidence: list[InterruptionReceipt] = field(default_factory=list, init=False)
    _wild: Gen1WildFleeHandler = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.allow_wild_faints) is not bool:
            raise TypeError("wild faint recovery opt-in must be boolean")
        if self.allow_wild_faints and self.emulator is None:
            raise ValueError("wild faint recovery requires its native emulator")
        if type(self.maximum_trainer_battles) is not int or self.maximum_trainer_battles < 0:  # noqa: E721
            raise ValueError("maximum_trainer_battles must be a non-negative integer")
        if type(self.max_trainer_intro_pulses) is not int or self.max_trainer_intro_pulses <= 0:  # noqa: E721
            raise ValueError("max_trainer_intro_pulses must be a positive integer")
        if not callable(self.move_slot_policy):
            raise TypeError("move_slot_policy must be callable")
        if (self.trainer_recovery_required is None) != (self.trainer_recovery_action is None):
            raise ValueError("trainer recovery predicate and action must be configured together")
        if (
            type(self.maximum_trainer_recoveries) is not int  # noqa: E721
            or self.maximum_trainer_recoveries < 0
        ):
            raise ValueError("maximum_trainer_recoveries must be a non-negative integer")
        if self.trainer_recovery_required is not None and self.maximum_trainer_recoveries == 0:
            raise ValueError("configured trainer recovery requires a positive recovery budget")
        if (
            type(self.maximum_scripted_dialogues) is not int  # noqa: E721
            or self.maximum_scripted_dialogues < 0
        ):
            raise ValueError("maximum_scripted_dialogues must be a non-negative integer")
        if (
            type(self.max_scripted_dialogue_pulses) is not int  # noqa: E721
            or self.max_scripted_dialogue_pulses <= 0
        ):
            raise ValueError("max_scripted_dialogue_pulses must be a positive integer")
        if self.wild_handler is not None and (
            self.wild_handler.executor is not self.executor
            or self.wild_handler.reader is not self.reader
            or self.wild_handler.maximum_flees != self.maximum_flees
            or self.wild_handler.stabilization_frames != self.stabilization_frames
            or self.wild_handler.allow_party_faints != self.allow_wild_faints
            or (self.allow_wild_faints and self.wild_handler.emulator is not self.emulator)
        ):
            raise ValueError("composed wild handler differs from its route owner or bounds")
        self._wild = self.wild_handler or Gen1WildFleeHandler(
            self.executor,
            self.reader,
            maximum_flees=self.maximum_flees,
            stabilization_frames=self.stabilization_frames,
            route_name=self.route_name,
            allow_party_faints=self.allow_wild_faints,
            emulator=self.emulator if self.allow_wild_faints else None,
        )

    @property
    def handled_hazard_kinds(self) -> frozenset[str]:
        return frozenset({"trainer_sight"}) if self.maximum_trainer_battles else frozenset()

    def observe_native_field_boundary(self) -> None:
        self._wild.observe_native_field_boundary()

    @property
    def wild_evidence(self) -> tuple[Route1WildFleeEvidence, ...]:
        return tuple(self._wild.evidence)

    @property
    def handled_interruption_kinds(self) -> frozenset[str]:
        """Declare only the dynamic interruptions this configured instance can resolve."""
        kinds = set(self._wild.handled_interruption_kinds)
        if self.maximum_trainer_battles > 0:
            kinds.update(("trainer_engagement", "battle:2"))
        if self.maximum_scripted_dialogues > 0:
            kinds.add("scripted_dialogue")
        return frozenset(kinds)

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        if interruption.interruption == "native_ship_departure":
            return self._wild.handle(interruption)
        if interruption.interruption == "wild_battle":
            return self._wild.handle(interruption)
        if interruption.interruption == "scripted_dialogue":
            if self._wild.allow_field_faint_dialogue and (
                self._wild.has_new_field_faint(self.reader.read())
                or not self.maximum_scripted_dialogues
            ):
                return self._wild.handle(interruption)
            return self._dismiss_scripted_dialogue(interruption)
        if interruption.interruption not in {"trainer_engagement", "battle:2"}:
            raise RouteExecutionError(f"Gen I route cannot dismiss {interruption.interruption!r}")
        if len(self.trainer_evidence) >= self.maximum_trainer_battles:
            raise RouteExecutionError(
                f"{self.route_name} exceeded its {self.maximum_trainer_battles}-trainer budget"
            )

        initial = self.reader.read()
        if (
            initial.map_id != interruption.map_id
            or (
                initial.player_y,
                initial.player_x,
            )
            != interruption.at
        ):
            raise RouteExecutionError("trainer interruption drifted before recovery")
        intro_pulses = 0
        active = initial
        while active.battle_state != 2:
            if active.battle_state == 1:
                raise RouteExecutionError("wild battle replaced a trainer engagement")
            if active.battle_state not in {0, None}:
                raise RouteExecutionError(
                    f"trainer engagement exposed battle state {active.battle_state!r}"
                )
            if intro_pulses >= self.max_trainer_intro_pulses:
                raise RouteExecutionError("trainer engagement exceeded its intro budget")
            self.executor.execute(MacroAction(MacroActionKind.CONFIRM))
            intro_pulses += 1
            active = self.reader.read()

            if (
                active.battle_state == 0
                and not self.reader.trainer_engagement_active()
                and self.reader.read_input_readiness().ready
            ):
                receipt = InterruptionReceipt(
                    kind="trainer_engagement",
                    resumed_map=interruption.map_id,
                    resumed_at=interruption.at,
                    details={
                        "battle_started": False,
                        "intro_pulses": intro_pulses,
                        "verified": True,
                    },
                )
                self.trainer_evidence.append(receipt)
                return receipt

        ordinal = len(self.trainer_evidence) + 1
        battle_plan_id = f"generated-route-map-{interruption.map_id}-trainer-{ordinal}"
        recoveries = 0

        def guarded_policy(raw: RawGameState) -> int:
            if self.trainer_recovery_required is not None and self.trainer_recovery_required(raw):
                raise _PauseRouteTrainerRecovery
            return self.move_slot_policy(raw)

        while True:
            try:
                final = run_adaptive_trainer_battle(
                    self.reader,
                    self.executor,
                    guarded_policy,
                    expected_map=interruption.map_id,
                    intent=BattleIntent(
                        objective_id="route_traversal",
                        battle_plan_id=battle_plan_id,
                        resource_policy=(
                            BattleResourcePolicy.BOUNDED_RECOVERY
                            if self.trainer_recovery_required is not None
                            else BattleResourcePolicy.NO_ADDITIONAL_CONSTRAINT
                        ),
                        recovery_capabilities=(
                            frozenset({BattleRecoveryCapability.RESTORE_HP})
                            if self.trainer_recovery_required is not None
                            else frozenset()
                        ),
                    ),
                    label=f"{self.route_name} trainer {ordinal}",
                    consume_battle_start_schedule=False,
                )
                break
            except BattleRuntimeError as error:
                if not recovery_request_matches(
                    error.__cause__,
                    _PauseRouteTrainerRecovery,
                    accepted_needs=frozenset({"hp"}),
                ):
                    raise RouteExecutionError(str(error)) from error
                if (
                    self.trainer_recovery_action is None
                    or recoveries >= self.maximum_trainer_recoveries
                ):
                    raise RouteExecutionError(
                        f"{self.route_name} exhausted its trainer recovery budget"
                    ) from error
                self.trainer_recovery_action()
                recoveries += 1
        if (
            final.battle_state != 0
            or final.map_id != interruption.map_id
            or (final.player_y, final.player_x) != interruption.at
            or not self.reader.read_input_readiness().ready
        ):
            raise RouteExecutionError("trainer battle failed to restore its route boundary")
        receipt = InterruptionReceipt(
            kind="trainer_engagement",
            resumed_map=interruption.map_id,
            resumed_at=interruption.at,
            details={
                "battle_plan_id": battle_plan_id,
                "battle_started": True,
                "intro_pulses": intro_pulses,
                "recoveries": recoveries,
                "verified": True,
                # An adjacent native trainer can already own the same field
                # boundary after the first battle. Report that observed intro;
                # routing must resolve it separately, not pretend free control.
                **(
                    {"pending_interruption_kind": "trainer_engagement"}
                    if self.reader.trainer_engagement_active()
                    else {}
                ),
            },
        )
        self.trainer_evidence.append(receipt)
        if not self.reader.trainer_engagement_active():
            self.observe_native_field_boundary()
        return receipt

    def _dismiss_scripted_dialogue(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        """Release a bounded overworld text script and report its actual landing."""

        if len(self.scripted_dialogue_evidence) >= self.maximum_scripted_dialogues:
            raise RouteExecutionError(
                f"{self.route_name} exceeded its {self.maximum_scripted_dialogues}-dialogue budget"
            )
        initial = self.reader.read()
        if (
            initial.map_id != interruption.map_id
            or (initial.player_y, initial.player_x) != interruption.at
            or initial.battle_state != 0
            or not self.reader.read_bottom_dialogue_box_visible()
        ):
            raise RouteExecutionError("scripted dialogue drifted before recovery")
        for pulses in range(self.max_scripted_dialogue_pulses + 1):
            active = self.reader.read()
            if active.battle_state != 0:
                successor = _interruption_kind(active.battle_state)
                capacity = (
                    active.battle_state == 2
                    and len(self.trainer_evidence) < self.maximum_trainer_battles
                ) or (
                    active.battle_state == 1
                    and len(self._wild.evidence) < self.maximum_flees
                )
                if (
                    pulses == 0
                    or not capacity
                    or successor not in self.handled_interruption_kinds
                    or (active.map_id, active.player_y, active.player_x)
                    != (initial.map_id, initial.player_y, initial.player_x)
                ):
                    raise RouteExecutionError("scripted dialogue entered a battle")
                # This is a verified observed successor, never free field control
                # or a battle win. The route executor must spend another bounded
                # interruption and invoke the independently configured handler.
                receipt = InterruptionReceipt(
                    kind="scripted_dialogue",
                    resumed_map=active.map_id,
                    resumed_at=(active.player_y, active.player_x),
                    details={
                        "cancel_pulses": pulses,
                        "position_changed": False,
                        "battle_started_during_dialogue": True,
                        "pending_interruption_kind": successor,
                        "verified": True,
                    },
                )
                self.scripted_dialogue_evidence.append(receipt)
                return receipt
            visible = self.reader.read_bottom_dialogue_box_visible()
            ready = self.reader.read_input_readiness().ready
            if ready and not visible:
                if active.map_id is None or active.player_y is None or active.player_x is None:
                    raise RouteExecutionError("scripted dialogue lost its traversal position")
                receipt = InterruptionReceipt(
                    kind="scripted_dialogue",
                    resumed_map=active.map_id,
                    resumed_at=(active.player_y, active.player_x),
                    allows_relocation=True,
                    details={
                        "cancel_pulses": pulses,
                        "position_changed": (
                            active.map_id,
                            active.player_y,
                            active.player_x,
                        )
                        != (
                            initial.map_id,
                            initial.player_y,
                            initial.player_x,
                        ),
                        "verified": True,
                    },
                )
                self.scripted_dialogue_evidence.append(receipt)
                return receipt
            if not visible:
                raise RouteExecutionError(
                    "scripted dialogue disappeared without restoring input readiness"
                )
            if pulses == self.max_scripted_dialogue_pulses:
                break
            self.executor.execute(MacroAction(MacroActionKind.CANCEL))
            self.executor.execute(
                MacroAction(MacroActionKind.WAIT, repeat=self.stabilization_frames)
            )
        raise RouteExecutionError("scripted dialogue exceeded its dismissal budget")


class _PauseRouteTrainerRecovery(BattleControlRequest):
    default_action = BattleAction.recovery()


def _interruption_kind(battle_state: int) -> str | None:
    if battle_state == 0:
        return None
    if battle_state == 1:
        return "wild_battle"
    return f"battle:{battle_state}"
