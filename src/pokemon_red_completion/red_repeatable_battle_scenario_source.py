"""Red adapter for action-free repeatable battle scenario source inspection."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from pokemon_red_completion.battle_scenario_source_venue import (
    battle_scenario_reachable_venues,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_battle_scenario import (
    red_battle_move_is_model_supported,
)
from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattlePartyOption,
    RepeatableBattleScenarioFactoryError,
    RepeatableBattleSourceKind,
    RepeatableBattleSourceObservation,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


class RedRepeatableBattleSourceSession(Protocol):
    """Read-only state-restore surface needed by the source adapter."""

    def load_state_bytes(self, payload: bytes) -> None: ...

    def read_u8(self, address: int) -> int: ...


RedRepeatableBattleSourceSessionFactory = Callable[
    [], AbstractContextManager[RedRepeatableBattleSourceSession]
]


def inspect_repeatable_red_battle_source(
    state_bytes: bytes,
    *,
    source_id: str,
    source_lineage_id: str,
    partition: ScenarioPartition,
    source_commit: str,
    session_factory: RedRepeatableBattleSourceSessionFactory,
) -> RepeatableBattleSourceObservation:
    """Restore and classify one private Red state without advancing a frame."""

    if not isinstance(state_bytes, bytes) or not state_bytes:
        raise RepeatableBattleScenarioFactoryError("source state bytes are unavailable")
    if not callable(session_factory):
        raise TypeError("session_factory must be callable")
    with session_factory() as session:
        session.load_state_bytes(state_bytes)
        reader = PokemonRedStateReader(session)
        raw = reader.read()
        if raw.battle_state == 0:
            venues = battle_scenario_reachable_venues(
                raw,
                last_blackout_map=reader.read_last_blackout_map(),
                current_map_tileset=session.read_u8(RamAddress.CURRENT_MAP_TILESET),
            )
            source_kind = RepeatableBattleSourceKind.FIELD
            active_party_index = None
            reachable_venue_ids = tuple(item.venue_id for item in venues)
        elif raw.battle_state == 2:
            menu = reader.read_battle_menu_state(raw)
            if menu.phase is not BattleMenuPhase.MAIN:
                raise RepeatableBattleScenarioFactoryError(
                    "trainer source is not at the MAIN policy boundary"
                )
            source_kind = RepeatableBattleSourceKind.TRAINER_BATTLE
            active_party_index = raw.active_party_index
            reachable_venue_ids = ()
        else:
            raise RepeatableBattleScenarioFactoryError(
                "source must be a safe field or trainer-battle boundary"
            )
    return adapt_repeatable_red_battle_source(
        raw,
        source_id=source_id,
        source_lineage_id=source_lineage_id,
        partition=partition,
        state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        source_commit=source_commit,
        source_kind=source_kind,
        active_party_index=active_party_index,
        reachable_venue_ids=reachable_venue_ids,
    )


def adapt_repeatable_red_battle_source(
    raw: RawGameState,
    *,
    source_id: str,
    source_lineage_id: str,
    partition: ScenarioPartition,
    state_sha256: str,
    source_commit: str,
    source_kind: RepeatableBattleSourceKind,
    active_party_index: int | None,
    reachable_venue_ids: tuple[str, ...],
) -> RepeatableBattleSourceObservation:
    """Convert a coherent Red observation into the shared source contract."""

    if not isinstance(raw, RawGameState):
        raise TypeError("raw must be a RawGameState")
    if raw.map_id is None or raw.party_count is None:
        raise RepeatableBattleScenarioFactoryError("source observation is incomplete")
    expected_battle_state = (
        0 if source_kind is RepeatableBattleSourceKind.FIELD else 2
    )
    if raw.battle_state != expected_battle_state:
        raise RepeatableBattleScenarioFactoryError(
            "source kind differs from the observed battle state"
        )
    arrays = (
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
    )
    if any(not isinstance(value, tuple) or len(value) != raw.party_count for value in arrays):
        raise RepeatableBattleScenarioFactoryError(
            "source party arrays are incomplete"
        )
    assert raw.party_species_ids is not None
    assert raw.party_hp is not None
    assert raw.party_max_hp is not None
    assert raw.party_moves is not None
    assert raw.party_pp is not None
    options = tuple(
        option
        for index in range(raw.party_count)
        if (
            option := _party_option(
                party_index=index,
                species_id=raw.party_species_ids[index],
                hp=raw.party_hp[index],
                max_hp=raw.party_max_hp[index],
                move_ids=raw.party_moves[index],
                current_pp=raw.party_pp[index],
            )
        )
        is not None
    )
    return RepeatableBattleSourceObservation(
        source_id=source_id,
        source_lineage_id=source_lineage_id,
        partition=partition,
        state_sha256=state_sha256,
        source_commit=source_commit,
        expected_map=raw.map_id,
        source_kind=source_kind,
        active_party_index=active_party_index,
        reachable_venue_ids=tuple(sorted(reachable_venue_ids)),
        party_options=options,
    )


def red_party_menu_semantic_sha256(
    *,
    species_id: int,
    move_ids: tuple[int, ...],
    current_pp: tuple[int, ...],
) -> str:
    """Hash menu mechanics without retaining Red species, move, or slot identities."""

    if len(move_ids) != 4 or len(current_pp) != 4:
        raise RepeatableBattleScenarioFactoryError("Red move arrays must contain four slots")
    catalog = PokemonRedBattleCatalog()
    species = catalog.resolve_species(pokemon_red_species_ref(species_id))
    moves: list[dict[str, object]] = []
    for move_id, pp in zip(move_ids, current_pp, strict=True):
        if not red_battle_move_is_model_supported(move_id, pp, catalog=catalog):
            continue
        mechanics = catalog.resolve_move(pokemon_red_move_ref(move_id))
        moves.append(
            {
                "type": mechanics.type_name,
                "category": mechanics.category,
                "power": mechanics.power,
                "accuracy": mechanics.accuracy,
                "maximum_pp": mechanics.max_pp,
                "current_pp_fraction": round(pp / mechanics.max_pp, 8),
                "priority": mechanics.priority,
                "effect_flags": sorted(mechanics.effect_flags),
            }
        )
    if len(moves) < 2:
        raise RepeatableBattleScenarioFactoryError(
            "party menu has fewer than two supported damaging moves"
        )
    return canonical_sha256(
        {
            "schema": "pokemon.core.battle.party-menu-mechanics.v1",
            "player_types": sorted(species.types),
            "moves": sorted(moves, key=canonical_sha256),
        }
    )


def _party_option(
    *,
    party_index: int,
    species_id: int,
    hp: int,
    max_hp: int,
    move_ids: tuple[int, ...],
    current_pp: tuple[int, ...],
) -> RepeatableBattlePartyOption | None:
    if type(hp) is not int or type(max_hp) is not int or hp <= 0 or max_hp <= 0:  # noqa: E721
        return None
    if hp > max_hp:
        raise RepeatableBattleScenarioFactoryError("party HP exceeds its maximum")
    if len(move_ids) != 4 or len(current_pp) != 4:
        raise RepeatableBattleScenarioFactoryError(
            "Red move arrays must contain four slots"
        )
    catalog = PokemonRedBattleCatalog()
    supported = sum(
        red_battle_move_is_model_supported(move_id, pp, catalog=catalog)
        for move_id, pp in zip(move_ids, current_pp, strict=True)
    )
    if supported < 2:
        return None
    return RepeatableBattlePartyOption(
        party_index=party_index,
        menu_semantic_sha256=red_party_menu_semantic_sha256(
            species_id=species_id,
            move_ids=move_ids,
            current_pp=current_pp,
        ),
        supported_move_count=supported,
        hp_ratio=hp / max_hp,
    )


__all__ = [
    "RedRepeatableBattleSourceSession",
    "RedRepeatableBattleSourceSessionFactory",
    "adapt_repeatable_red_battle_source",
    "inspect_repeatable_red_battle_source",
    "red_party_menu_semantic_sha256",
]
