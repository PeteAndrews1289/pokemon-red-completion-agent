"""Endgame Pokedex collection chapter for Pokemon Red."""

from __future__ import annotations

import logging
from typing import Any

from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionDirective,
    RedAcquisitionKind,
    RedAreaExecutor,
    plan_red_acquisition,
    rank_red_sources,
)
from pokemon_red_completion.red_collection import (
    RED_SOLO_POKEDEX_TARGET_COUNT,
    red_collection_observation,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader

logger = logging.getLogger(__name__)


class RedCollectionExecutor(RedAreaExecutor):
    def __init__(self, actions: CountingExecutor, reader: PokemonRedStateReader, emulator: Any):
        self._actions = actions
        self._reader = reader
        self._emulator = emulator

    def read_collection(self) -> CollectionObservation:
        """Read the Pokedex, the active party, and the storage boxes.

        The party comes from ``PokemonRedPartyReader``, which is how every
        other call site in the repository reads one. An earlier version asked
        the state reader for ``read_party_state``, which it does not have, so
        this method raised ``AttributeError`` on its first call -- and the only
        test covering it replaced the method with a stub, which is why the
        suite stayed green over a module that could not run.
        """

        return red_collection_observation(
            self._reader.read_pokedex_state(),
            PokemonRedPartyReader(self._emulator).read(),
            self._reader.read_all_box_states(),
        )

    def encountered_species_ref(self) -> str | None:
        raw = self._reader.read()
        if raw.battle_state and raw.enemy_species_id:
            # We would look up species ref here. For now returning None as it's a stub
            return None
        return None

    def seek_encounter(self) -> None:
        raise NotImplementedError("Generic seek_encounter not implemented")

    def capture_encounter(self, species_ref: str) -> bool | None:
        raise NotImplementedError("Generic capture_encounter not implemented")

    def flee_encounter(self) -> None:
        raise NotImplementedError("Generic flee_encounter not implemented")

    def switch_box(self, box_index: int) -> None:
        # Switching boxes needs a PC, and reaching one is route-specific.
        raise NotImplementedError(f"Cannot generically navigate to PC to switch to box {box_index}")


def run_collection(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: Any,
) -> None:
    """Run the endgame collection phase to complete the Pokedex."""

    executor = RedCollectionExecutor(actions, reader, emulator)

    while True:
        obs = executor.read_collection()
        owned_count = len(obs.owned_species)
        logger.info(f"Collection progress: {owned_count} / {RED_SOLO_POKEDEX_TARGET_COUNT}")

        if owned_count >= RED_SOLO_POKEDEX_TARGET_COUNT:
            logger.info("Pokedex collection complete!")
            break

        priorities = rank_red_sources(obs, kinds=frozenset(RedAcquisitionKind))
        if not priorities:
            # Attempt to resolve evolutions/trades if no sources are available
            missing = [
                m.species_ref
                for m in RED_ACQUISITION_CATALOG.methods
                if m.species_ref not in obs.owned_species
            ]
            if not missing:
                break

            for ref in missing:
                try:
                    plan = plan_red_acquisition(ref, obs)
                    if plan.directive in (
                        RedAcquisitionDirective.EVOLVE_SPECIES,
                        RedAcquisitionDirective.PERFORM_TRADE,
                    ):
                        raise NotImplementedError(
                            f"Logic to execute {plan.directive} for {ref} is not yet implemented."
                        )
                except ValueError:
                    pass
            break

        target_source = priorities[0]
        logger.info(
            f"Targeting source {target_source.source_id} for "
            f"{target_source.missing_specimen_count} specimens."
        )

        # Route to the target_source (Currently requires specific navigators)
        raise NotImplementedError(
            f"Navigation to source {target_source.source_id} is not implemented yet."
        )
