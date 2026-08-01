"""Pokémon Red adapter for the game-neutral party observation contract.

This module is the only place that knows how Red stores a party.  It projects
the revision-specific 44-byte party structure into
:class:`~pokemon_red_completion.party.PartyObservation` so planners and the
balanced-training policy never read raw addresses.

Every offset below is derived from the same pinned pret/pokered structure that
already backs :class:`~pokemon_red_completion.observation.RamAddress`.  The
named first-slot symbols in that enum are re-derived here from ``STRUCT_BASE``
plus an offset, and :mod:`tests.test_red_party` asserts the two agree, so a
future edit to either cannot silently drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from .observation import PARTY_LIMIT, RamAddress, ReadOnlyMemory
from .party import (
    MOVE_SLOT_LIMIT,
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    PartyRole,
    StatusCondition,
)
from .team_training import RosterSlot, TeamRosterPlan

STRUCT_BASE = int(RamAddress.PARTY_MON_1)
PARTY_STRUCT_STRIDE = 44

SPECIES_OFFSET = 0
HP_OFFSET = 1
STATUS_OFFSET = 4
MOVES_OFFSET = 8
EXPERIENCE_OFFSET = 14
PP_OFFSET = 29
LEVEL_OFFSET = 33
MAX_HP_OFFSET = 34

EXPERIENCE_BYTES = 3
PP_VALUE_MASK = 0x3F

SLEEP_COUNTER_MASK = 0x07
POISON_MASK = 0x08
BURN_MASK = 0x10
FREEZE_MASK = 0x20
PARALYSIS_MASK = 0x40

BLASTOISE_SPECIES_ID = 0x1C
HITMONLEE_SPECIES_ID = 0x2B
DUX_SPECIES_ID = 0x40
JOLTEON_SPECIES_ID = 0x68
DUGTRIO_SPECIES_ID = 0x76
SNORLAX_SPECIES_ID = 0x84


class PartyReadError(RuntimeError):
    """Raised when observed party memory cannot describe a coherent party."""


#: The declared balanced roster for Pokémon Red.
#:
#: Each role is bound to a species the qualified route can already reach or is
#: a direct evolution of one it reaches: Blastoise is the starter, Dugtrio
#: evolves from the Diglett the Vermilion chapter already captures, and DUX is
#: the Farfetch'd that chapter already trades for.  Jolteon, Snorlax, and
#: Hitmonlee are reachable but are *not* yet acquired by the current route; see
#: ``docs/project-narrative.md`` for the acquisition work this implies.
#:
#: No slot is a substitution, so no slot carries a substitution reason.  Any
#: future deviation must set ``is_substitution`` and record why.
RED_BALANCED_ROSTER = TeamRosterPlan(
    (
        RosterSlot(PartyRole.LEAD_ATTACKER, BLASTOISE_SPECIES_ID),
        RosterSlot(PartyRole.SPEED_CONTROL, DUGTRIO_SPECIES_ID),
        RosterSlot(PartyRole.FIELD_UTILITY, DUX_SPECIES_ID),
        RosterSlot(PartyRole.SPECIAL_SWEEPER, JOLTEON_SPECIES_ID),
        RosterSlot(PartyRole.BULKY_ABSORBER, SNORLAX_SPECIES_ID),
        RosterSlot(PartyRole.PHYSICAL_SWEEPER, HITMONLEE_SPECIES_ID),
    )
)


def decode_status(status_byte: int) -> StatusCondition:
    """Translate Red's packed status byte into a portable condition.

    The low three bits are a sleep counter rather than a flag, so a sleeping
    Pokémon is detected by a non-zero counter.  Red sets at most one persistent
    condition at a time; sleep is checked first because its counter shares the
    byte with nothing else.
    """

    if status_byte & SLEEP_COUNTER_MASK:
        return StatusCondition.SLEEP
    if status_byte & POISON_MASK:
        return StatusCondition.POISON
    if status_byte & BURN_MASK:
        return StatusCondition.BURN
    if status_byte & FREEZE_MASK:
        return StatusCondition.FREEZE
    if status_byte & PARALYSIS_MASK:
        return StatusCondition.PARALYSIS
    return StatusCondition.HEALTHY


def member_field_address(index: int, offset: int) -> int:
    """Return the absolute address of one field of the ``index``-th party member."""

    if not 0 <= index < PARTY_LIMIT:
        raise ValueError(f"party index must be between 0 and {PARTY_LIMIT - 1}")
    return STRUCT_BASE + index * PARTY_STRUCT_STRIDE + offset


@dataclass(frozen=True, slots=True)
class PokemonRedPartyReader:
    """Projects Red's party memory into the game-neutral contract."""

    memory: ReadOnlyMemory

    def _read_u8(self, index: int, offset: int) -> int:
        return self.memory.read_u8(member_field_address(index, offset))

    def _read_u16_be(self, index: int, offset: int) -> int:
        high = self._read_u8(index, offset)
        low = self._read_u8(index, offset + 1)
        return (high << 8) | low

    def _read_experience(self, index: int) -> int:
        value = 0
        for byte in range(EXPERIENCE_BYTES):
            value = (value << 8) | self._read_u8(index, EXPERIENCE_OFFSET + byte)
        return value

    def _read_moves(self, index: int) -> tuple[MoveObservation, ...]:
        moves: list[MoveObservation] = []
        for slot in range(MOVE_SLOT_LIMIT):
            move_id = self._read_u8(index, MOVES_OFFSET + slot)
            current_pp = self._read_u8(index, PP_OFFSET + slot) & PP_VALUE_MASK
            moves.append(MoveObservation(move_id=move_id, current_pp=current_pp))
        return tuple(moves)

    def _read_member(self, index: int) -> PartyMemberObservation:
        species_id = self._read_u8(index, SPECIES_OFFSET)
        if species_id <= 0:
            raise PartyReadError(f"party slot {index + 1} is counted but holds no species")
        max_hp = self._read_u16_be(index, MAX_HP_OFFSET)
        if max_hp <= 0:
            raise PartyReadError(f"party slot {index + 1} reports no maximum health")
        hp = self._read_u16_be(index, HP_OFFSET)
        if hp > max_hp:
            raise PartyReadError(f"party slot {index + 1} reports health above its maximum")
        return PartyMemberObservation(
            slot=index + 1,
            species_id=species_id,
            level=self._read_u8(index, LEVEL_OFFSET),
            hp=hp,
            max_hp=max_hp,
            status=decode_status(self._read_u8(index, STATUS_OFFSET)),
            moves=self._read_moves(index),
            experience=self._read_experience(index),
        )

    def read(self) -> PartyObservation:
        """Read every counted active-party member.

        A party count above the game's own limit is clamped rather than trusted,
        matching the existing state reader's treatment of the same symbol.
        """

        count = min(self.memory.read_u8(RamAddress.PARTY_COUNT), PARTY_LIMIT)
        members = tuple(self._read_member(index) for index in range(count))
        return PartyObservation(members=members)
