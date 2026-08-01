"""Pokémon Red adapter for the game-neutral trajectory ontology."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    RequiredMovePolicy,
)
from pokemon_red_completion.collection_protocol import BattleStartOffset
from pokemon_red_completion.executor import ExecutedAction
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    location_label,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.trajectory import (
    DecisionContext,
    DecisionRecord,
    RecordingExecutor,
    SemanticSnapshot,
    SparseEvent,
    TrajectorySink,
)

POKEMON_CORE_ONTOLOGY_ID = "pokemon.core.v1"
POKEMON_RED_ADAPTER_ID = "pokemon.red.gb.us.rev0.v1"
POKEMON_RED_GAME_ID = "pokemon.mainline:red:gb:us:rev0"
POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID = "pokemon-red-qualified-teacher-v1"
POKEMON_BATTLE_MOVE_SKILL_ID = "pokemon.core:battle:move_selection"


class RedSemanticReader(Protocol):
    def read(self) -> RawGameState: ...

    def read_input_readiness(self) -> InputReadiness: ...

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState: ...


@dataclass(frozen=True, slots=True)
class PokemonRedObservationEncoder:
    """Translate revision-specific WRAM observations into reusable concepts.

    The returned source observation intentionally includes both normalized concepts and
    namespaced Red references. Future policy feature views may select only normalized fields;
    raw addresses, event bytes, ROM data, and filesystem state never cross this adapter.
    """

    reader: RedSemanticReader

    @classmethod
    def from_state_reader(
        cls,
        reader: PokemonRedStateReader,
    ) -> PokemonRedObservationEncoder:
        return cls(reader)

    def snapshot(self) -> SemanticSnapshot:
        raw = self.reader.read()
        return self.snapshot_from_raw(raw)

    def snapshot_from_raw(
        self,
        raw: RawGameState,
        *,
        battle_menu: BattleMenuState | None = None,
    ) -> SemanticSnapshot:
        """Encode the exact policy observation without rereading raw game state."""

        if not isinstance(raw, RawGameState):
            raise TypeError("raw must be a RawGameState")
        controls = self.reader.read_input_readiness()
        observed_battle_menu = (
            self.reader.read_battle_menu_state(raw) if battle_menu is None else battle_menu
        )
        if not isinstance(observed_battle_menu, BattleMenuState):
            raise TypeError("battle_menu must be a BattleMenuState")
        mode = _observable_mode(raw, controls)
        location = _map_label(raw.map_id) if raw.game_started else None
        input_ready = raw.game_started and mode != "terminal" and controls.ready
        max_hp = raw.first_party_max_hp
        enemy_max_hp = raw.enemy_max_hp
        in_battle = raw.game_started and raw.battle_state in {1, 2}

        features: dict[str, object] = {
            "adapter_id": POKEMON_RED_ADAPTER_ID,
            "ontology_id": POKEMON_CORE_ONTOLOGY_ID,
            "control": {
                # Readiness is evidence about whether input can be accepted, not a
                # claim that any particular action is legal in the unseen UI state.
                "input_ready": input_ready,
            },
            "world": {
                "area_ref": _area_ref(location),
                "area_kind": _area_kind(location),
                "position": {
                    "x": raw.player_x if raw.game_started else None,
                    "y": raw.player_y if raw.game_started else None,
                },
            },
            "progress": {
                "badge_count": int(raw.badge_bits or 0).bit_count(),
            },
            "party": {
                "count": raw.party_count,
                "species_refs": tuple(
                    _local_ref("species", species) for species in (raw.party_species_ids or ())
                ),
                "lead": {
                    "species_ref": (
                        _local_ref("species", raw.party_species_ids[0])
                        if raw.party_species_ids
                        else None
                    ),
                    "level": raw.first_party_level,
                    "hp": raw.first_party_hp,
                    "max_hp": max_hp,
                    "hp_ratio": _ratio(raw.first_party_hp, max_hp),
                    "status": _status_ref(raw.first_party_status),
                    "moves": _observable_moves(raw),
                },
            },
            "battle": (
                {
                    "active": True,
                    "kind": "trainer" if raw.battle_state == 2 else "wild",
                    "opponent_species_ref": (
                        _local_ref("species", raw.enemy_species_id)
                        if raw.enemy_species_id is not None
                        else None
                    ),
                    "opponent_level": raw.enemy_level,
                    "opponent_hp": raw.enemy_hp,
                    "opponent_max_hp": enemy_max_hp,
                    "opponent_hp_ratio": _ratio(raw.enemy_hp, enemy_max_hp),
                    "player_attack_stage": _normalize_stage(raw.player_attack_stage),
                    "player_accuracy_stage": _normalize_stage(raw.player_accuracy_stage),
                    "opponent_defense_stage": _normalize_stage(raw.enemy_defense_stage),
                    "player_disabled_move_slot": raw.player_disabled_move_slot,
                    "player_disable_turns": raw.player_disable_turns,
                    "opponent_using_trapping_move": raw.enemy_using_trapping_move,
                }
                if in_battle
                else None
            ),
            "menu": _known_battle_menu(raw, observed_battle_menu),
        }
        return SemanticSnapshot(
            game_id=POKEMON_RED_GAME_ID,
            mode=mode,
            location=_area_ref(location),
            facts=_observable_concepts(raw),
            features=features,
        )


@dataclass(slots=True)
class PokemonRedBattleDecisionObserver:
    """Create privacy-safe battle-move labels at the shared policy boundary."""

    encoder: PokemonRedObservationEncoder
    recorder: RecordingExecutor[MacroAction, ExecutedAction]
    _next_decision_index: int = field(default=0, init=False)
    _next_battle_index: int = field(default=0, init=False)
    _active_battle_instance_id: str | None = field(default=None, init=False)
    _active_battle_intent: BattleIntent | None = field(default=None, init=False)

    def note_instrumentation_failure(self) -> None:
        """Make observer loss visible to the episode qualification gate."""

        self.recorder.note_instrumentation_failure()

    def battle_started(self, *, intent: BattleIntent | None) -> None:
        """Start or resume one physical encounter without consulting private state."""

        if not isinstance(intent, BattleIntent):
            raise ValueError("battle intent is required when recording starts")
        if self._active_battle_instance_id is not None:
            if intent != self._active_battle_intent:
                raise ValueError("battle intent changed while resuming an active battle")
            return
        battle_index = self._next_battle_index
        self._next_battle_index += 1
        self._active_battle_instance_id = f"{self.recorder.episode_id}:battle:{battle_index}"
        self._active_battle_intent = intent

    def battle_finished(self) -> None:
        """Close the active encounter only after the runtime observes battle exit."""

        self._active_battle_instance_id = None
        self._active_battle_intent = None

    def decision_scope(
        self,
        *,
        policy_state: RawGameState,
        policy_menu: BattleMenuState,
        selected_slot: int,
        intent: BattleIntent | None,
    ) -> AbstractContextManager[None]:
        """Return a fail-open span linking one move choice to its executions."""

        # Observable world features remain part of the general policy view and
        # may be ablated explicitly by a battle-specialist training export.
        return self.recorder.decision_scope(
            lambda: self._build_decision(
                policy_state=policy_state,
                policy_menu=policy_menu,
                selected_slot=selected_slot,
                intent=intent,
            )
        )

    def _build_decision(
        self,
        *,
        policy_state: RawGameState,
        policy_menu: BattleMenuState,
        selected_slot: int,
        intent: BattleIntent | None,
    ) -> DecisionRecord:
        if not isinstance(intent, BattleIntent):
            raise ValueError("battle decision intent is required for recording")
        battle_instance_id = self._active_battle_instance_id
        if battle_instance_id is None:
            raise ValueError("battle decision lacks an active battle instance")
        if intent != self._active_battle_intent:
            raise ValueError("battle intent changed inside one battle instance")
        if (
            not isinstance(selected_slot, int)
            or isinstance(selected_slot, bool)
            or not 1 <= selected_slot <= 4
        ):
            raise ValueError("selected_slot must be a one-based move slot")

        decision_index = self._next_decision_index
        self._next_decision_index += 1
        snapshot = self.encoder.snapshot_from_raw(
            policy_state,
            battle_menu=policy_menu,
        )
        payload = snapshot.to_dict()
        features = payload["features"]
        if not isinstance(features, dict):
            raise ValueError("battle decision snapshot lacks semantic features")
        menu = features.get("menu")
        if not isinstance(menu, dict) or menu.get("kind") != "battle_main":
            raise ValueError("battle decision snapshot must expose the main battle menu")
        party = features.get("party")
        if not isinstance(party, dict):
            raise ValueError("battle decision snapshot lacks party features")
        lead = party.get("lead")
        if not isinstance(lead, dict):
            raise ValueError("battle decision snapshot lacks lead-party features")
        moves = lead.get("moves")
        if not isinstance(moves, list):
            raise ValueError("battle decision snapshot lacks move features")
        slot_index = selected_slot - 1
        selected_moves = [
            move
            for move in moves
            if isinstance(move, dict) and move.get("slot_index") == slot_index
        ]
        if len(selected_moves) != 1:
            raise ValueError("selected battle move is absent from the policy snapshot")
        pp = selected_moves[0].get("pp")
        if not isinstance(pp, int) or isinstance(pp, bool) or pp <= 0:
            raise ValueError("selected battle move lacks usable PP")
        required_move_ref: str | None = None
        if intent.required_move_policy is RequiredMovePolicy.EXACT_REQUIRED:
            candidate_ref = selected_moves[0].get("move_ref")
            if not isinstance(candidate_ref, str) or not candidate_ref:
                raise ValueError("required battle move lacks a semantic reference")
            required_move_ref = intent.required_move_ref
            if candidate_ref != required_move_ref:
                raise ValueError("selected battle move does not match the declared requirement")

        return DecisionRecord(
            decision_id=f"{self.recorder.episode_id}:decision:{decision_index}",
            episode_id=self.recorder.episode_id,
            step_index=self.recorder.next_step_index,
            snapshot=snapshot,
            context=DecisionContext(
                objective_id=intent.objective_id,
                policy_id=POKEMON_RED_QUALIFIED_TEACHER_POLICY_ID,
                actor="deterministic_teacher",
                metadata={
                    "skill_id": POKEMON_BATTLE_MOVE_SKILL_ID,
                    "battle_instance_id": battle_instance_id,
                    "battle_plan_id": intent.battle_plan_id,
                    "battle_goal": intent.goal.value,
                    "battle_policy_context": {
                        "goal": intent.goal.value,
                        "move_policy": intent.required_move_policy.value,
                        "required_move_ref": required_move_ref,
                    },
                    "teacher_recovery_marker": intent.resource_policy.value,
                },
            ),
            decision_type="battle_move_selection",
            action={
                "kind": "select_move",
                "slot_index": slot_index,
            },
        )


@dataclass(slots=True)
class PokemonRedBattleScheduleObserver:
    """Persist one path-free attestation for every applied schedule offset."""

    encoder: PokemonRedObservationEncoder
    recorder: RecordingExecutor[MacroAction, ExecutedAction]
    sink: TrajectorySink
    schedule_sha256: str
    _recorded_plan_ids: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schedule_sha256, str)
            or len(self.schedule_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.schedule_sha256)
        ):
            raise ValueError("schedule_sha256 must be a lowercase SHA-256 digest")

    def note_instrumentation_failure(self) -> None:
        self.recorder.note_instrumentation_failure()

    def offset_applied(
        self,
        *,
        intent: BattleIntent,
        offset: BattleStartOffset,
        before_state: RawGameState,
        before_menu: BattleMenuState,
        after_state: RawGameState,
        after_menu: BattleMenuState,
    ) -> None:
        if intent.battle_plan_id != offset.battle_plan_id:
            raise ValueError("schedule attestation intent does not match its offset")
        if offset.battle_plan_id in self._recorded_plan_ids:
            raise ValueError("schedule attestation duplicated a battle plan")
        try:
            ordinal = RED_BATTLE_PLAN_IDS.index(offset.battle_plan_id) + 1
        except ValueError as error:
            raise ValueError("schedule attestation references an unknown battle plan") from error
        before = self.encoder.snapshot_from_raw(before_state, battle_menu=before_menu)
        after = self.encoder.snapshot_from_raw(after_state, battle_menu=after_menu)
        execution_step_index = (
            self.recorder.next_step_index - 1 if offset.frames > 0 else None
        )
        self.sink.record_event(
            SparseEvent(
                event_id=f"{self.recorder.episode_id}:schedule:{ordinal}",
                episode_id=self.recorder.episode_id,
                step_index=self.recorder.next_step_index,
                kind="battle_start_offset_applied",
                payload={
                    "after_snapshot_sha256": after.sha256,
                    "battle_ordinal": ordinal,
                    "battle_plan_id": offset.battle_plan_id,
                    "before_snapshot_sha256": before.sha256,
                    "execution_step_index": execution_step_index,
                    "frames": offset.frames,
                    "schedule_sha256": self.schedule_sha256,
                },
            )
        )
        self._recorded_plan_ids.add(offset.battle_plan_id)


def _observable_mode(raw: RawGameState, controls: InputReadiness) -> str:
    """Return only modes justified by the policy-visible observation.

    Red's compact raw state cannot distinguish dialogue, menus, map transitions, and
    scripted movement. Those states therefore share one conservative blocked mode.
    """

    if not raw.game_started:
        return "booting"
    if raw.map_id == MapId.HALL_OF_FAME:
        return "terminal"
    if raw.battle_state in {1, 2}:
        return "battle"
    if controls.ready:
        return "interactive"
    return "scripted_or_blocked"


def _observable_concepts(raw: RawGameState) -> tuple[str, ...]:
    """Derive shared concepts without consulting privileged story/event bytes."""

    if not raw.game_started:
        return ()
    concepts: set[str] = set()
    if (raw.party_count or 0) > 0:
        concepts.add("pokemon.core:party:available")
    if int(raw.badge_bits or 0).bit_count():
        concepts.add("pokemon.core:progress:badge_obtained")
    if raw.battle_state in {1, 2}:
        concepts.add("pokemon.core:battle:active")
    if raw.map_id == MapId.HALL_OF_FAME:
        concepts.add("pokemon.core:progress:game_complete")
    return tuple(sorted(concepts))


def _map_label(map_id: int | None) -> str | None:
    """Prefer curated labels, then fall back to a known MapId enum name."""

    if map_id is None:
        return None
    label = location_label(map_id)
    try:
        enum_label = MapId(map_id).name.lower()
    except ValueError:
        return label
    if label is None or label.startswith("map_"):
        return enum_label
    return label


def _observable_moves(raw: RawGameState) -> tuple[dict[str, object], ...]:
    moves: list[dict[str, object]] = []
    for slot_index, move_id in enumerate(raw.first_party_moves or ()):
        if move_id == 0:
            continue
        pp = (
            raw.first_party_pp[slot_index] & 0x3F
            if raw.first_party_pp and slot_index < len(raw.first_party_pp)
            else None
        )
        moves.append(
            {
                "slot_index": slot_index,
                "move_ref": pokemon_red_move_ref(move_id),
                "pp": pp,
            }
        )
    return tuple(moves)


def _known_battle_menu(
    raw: RawGameState,
    menu: BattleMenuState,
) -> dict[str, object] | None:
    if raw.battle_state not in {1, 2}:
        return None
    if menu.phase is BattleMenuPhase.MAIN:
        return {
            "kind": "battle_main",
            "selected_command_index": menu.selected_main_command,
        }
    if menu.phase is BattleMenuPhase.MOVE:
        return {
            "kind": "battle_move",
            "selected_move_index": (
                menu.selected_move_slot - 1 if menu.selected_move_slot is not None else None
            ),
        }
    return None


def _local_ref(kind: str, identifier: int) -> str:
    return f"pokemon.red.gb.us.rev0:{kind}:{identifier:03d}"


def _area_ref(location: str | None) -> str | None:
    if location is None:
        return None
    return f"pokemon.red.gb.us.rev0:area:{location}"


def _area_kind(location: str | None) -> str | None:
    if location is None:
        return None
    if any(
        token in location
        for token in (
            "indigo_plateau",
            "loreleis_room",
            "brunos_room",
            "agathas_room",
            "lances_room",
            "champions_room",
            "hall_of_fame",
        )
    ):
        return "league"
    if location.startswith("route_"):
        if "gate" in location:
            return "gate"
        return "route"
    if "gym" in location:
        return "gym"
    if "pokecenter" in location:
        return "healing"
    if "mart" in location:
        return "shop"
    if "gate" in location:
        return "gate"
    if any(
        token in location
        for token in (
            "cave",
            "tunnel",
            "forest",
            "mt_moon",
            "mansion",
            "hideout",
            "pokemon_tower",
            "silph_co",
            "victory_road",
        )
    ):
        return "dungeon"
    if "underground_path" in location:
        return "passage"
    if location.startswith("safari_zone"):
        return "wilderness"
    if location.startswith("ss_anne"):
        return "ship"
    if location == "vermilion_dock":
        return "transit"
    if location.endswith(("_city", "_town", "_island")):
        return "settlement"
    return "interior"


def _ratio(current: int | None, maximum: int | None) -> float | None:
    if current is None or maximum is None or maximum <= 0:
        return None
    return round(current / maximum, 6)


def _normalize_stage(value: int | None) -> int | None:
    if value is None:
        return None
    return max(-6, min(6, value - 7))


def _status_ref(value: int | None) -> str | None:
    if value in {None, 0}:
        return None
    assert value is not None
    if value & 0x07:
        return "sleep"
    if value & 0x08:
        return "poison"
    if value & 0x10:
        return "burn"
    if value & 0x20:
        return "freeze"
    if value & 0x40:
        return "paralysis"
    return "other"
