"""Pokémon Red adapter for the game-neutral trajectory ontology."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    location_label,
)
from pokemon_red_completion.trajectory import SemanticSnapshot

POKEMON_CORE_ONTOLOGY_ID = "pokemon.core.v1"
POKEMON_RED_ADAPTER_ID = "pokemon.red.gb.us.rev0.v1"
POKEMON_RED_GAME_ID = "pokemon.mainline:red:gb:us:rev0"


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
        controls = self.reader.read_input_readiness()
        battle_menu = self.reader.read_battle_menu_state(raw)
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
                }
                if in_battle
                else None
            ),
            "menu": _known_battle_menu(raw, battle_menu),
        }
        return SemanticSnapshot(
            game_id=POKEMON_RED_GAME_ID,
            mode=mode,
            location=_area_ref(location),
            facts=_observable_concepts(raw),
            features=features,
        )


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
                "move_ref": _local_ref("move", move_id),
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
