"""The endgame collection chapter, as far as it currently goes.

The module is a skeleton: it can read the collection and rank what to acquire
next, and then stops because routing to a source is not built. That is a fine
thing to have, but it has to be honest about which half works.

An earlier version of this file monkey-patched ``read_collection`` away so the
test "wouldn't need fake memory". That method was calling
``reader.read_party_state()``, which does not exist, so it raised
``AttributeError`` on its first call -- and the patch removed the only thing
that would have shown it. The suite was green over a module whose entry point
could not run. So the reading half is now exercised for real.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from pokemon_red_completion.collection_chapter import RedCollectionExecutor, run_collection
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import (
    RED_BOX_LIMIT,
    RamAddress,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)


class FakeMemory:
    """Enough memory for a Pokedex read, a party read, and a box read.

    Everything reads as zero except the party count, which is what the party
    adapter clamps against. A party of zero is a legitimate observation here:
    the point is that the read completes against the real adapters rather than
    against a stub.
    """

    def __init__(self) -> None:
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        self.reads.append(int(address))
        return 0

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        return 0


def _empty_reader() -> Mock:
    """A reader over a fresh game: nothing caught, nothing stored.

    Built from the real observation types rather than mocks, so a change to
    their shape reaches this test instead of sliding past it.
    """

    reader = Mock()
    reader.read_pokedex_state.return_value = RedPokedexState(
        owned_species=frozenset(), seen_species=frozenset()
    )
    reader.read_all_box_states.return_value = RedBoxCollectionState(
        boxes=tuple(
            RedCurrentBoxState(box_index=index, species_ids=(), levels=())
            for index in range(RED_BOX_LIMIT)
        ),
        current_box_index=0,
        storage_initialized=True,
    )
    return reader


def test_reading_the_collection_uses_adapters_that_exist() -> None:
    """The regression guard.

    ``read_collection`` reaches for the Pokedex, the party and the boxes. If it
    asks any of them for a method they do not have, this raises AttributeError
    rather than passing quietly.
    """

    memory = FakeMemory()
    reader = _empty_reader()

    executor = RedCollectionExecutor(Mock(spec=CountingExecutor), reader, memory)
    observation = executor.read_collection()

    assert observation is not None
    reader.read_pokedex_state.assert_called_once()
    reader.read_all_box_states.assert_called_once()
    assert any(read == int(RamAddress.PARTY_COUNT) for read in memory.reads), (
        "the party must be read from memory through the party adapter"
    )


def test_the_collection_loop_stops_where_routing_is_missing() -> None:
    """Documents the boundary, and will fail the day routing lands.

    This is a placeholder assertion by design: it pins what is *not* built, so
    it turns red when someone builds it and forgets to update the shape here.
    """

    memory = FakeMemory()
    reader = _empty_reader()

    with pytest.raises(NotImplementedError, match="Navigation to source"):
        run_collection(Mock(spec=CountingExecutor), reader, memory)
