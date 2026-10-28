"""Offline DEVELOPMENT-only HP/PP conditioning; never an actor capability.

The caller must isolate/authenticate the parent and retain the receipt before
giving an ordinary read/input controller to the actor. No frames run here.
"""

from hashlib import sha256

from .observation import RamAddress
from .red_party import (
    HP_OFFSET,
    MAX_HP_OFFSET,
    MOVES_OFFSET,
    PP_OFFSET,
    STATUS_OFFSET,
    member_field_address,
)
from .red_party_pp import decode_red_party_pp
from .scenario_lab import ScenarioPartition


def restored_resource_writes(memory, *, partition):
    """Validate the entire field party before returning any prospective writes."""
    if partition is not ScenarioPartition.DEVELOPMENT:
        raise ValueError("resource diagnostic requires DEVELOPMENT")
    if memory[int(RamAddress.IS_IN_BATTLE)]:
        raise ValueError("resource diagnostic requires a field boundary")
    count = memory[int(RamAddress.PARTY_COUNT)]
    if not 1 <= count <= 6:
        raise ValueError("invalid diagnostic party count")
    writes = []
    for index in range(count):

        def at(offset, index=index):
            return member_field_address(index, offset)

        hp = memory[at(HP_OFFSET)] * 256 + memory[at(HP_OFFSET + 1)]
        maximum = memory[at(MAX_HP_OFFSET)] * 256 + memory[at(MAX_HP_OFFSET + 1)]
        if not maximum or hp > maximum or memory[at(STATUS_OFFSET)]:
            raise ValueError("diagnostic requires coherent HP and no initial status")
        moves = tuple(memory[at(MOVES_OFFSET + slot)] for slot in range(4))
        pp = tuple(memory[at(PP_OFFSET + slot)] for slot in range(4))
        decoded = decode_red_party_pp(moves, pp)
        desired = [(at(HP_OFFSET), maximum >> 8), (at(HP_OFFSET + 1), maximum & 255)]
        desired.extend(
            (at(PP_OFFSET + slot), (packed & 0xC0) | move.maximum_pp)
            for slot, (packed, move) in enumerate(zip(pp, decoded.moves, strict=True))
        )
        writes.extend(
            dict(address=a, before=memory[a], after=v) for a, v in desired if memory[a] != v
        )
    return writes


def condition_development_resources(memory, *, partition):
    """Restore current HP/PP only; audit full CPU-visible memory and WRAM aliases."""
    writes = restored_resource_writes(memory, partition=partition)
    before = bytes(memory[a] for a in range(65536))
    for row in writes:
        memory[row["address"]] = row["after"]
    after = bytes(memory[a] for a in range(65536))
    allowed = {r["address"] for r in writes}
    allowed |= {a + 0x2000 for a in allowed if 0xC000 <= a < 0xDE00}
    changed = [a for a, (x, y) in enumerate(zip(before, after, strict=True)) if x != y]
    if (
        not set(changed) <= allowed
        or any(after[r["address"]] != r["after"] for r in writes)
        or restored_resource_writes(memory, partition=partition)
    ):
        raise ValueError("resource diagnostic changed unexpected memory or failed readback")
    return dict(
        schema="pokemon.red.development-resource-intervention.v1",
        partition="development",
        assisted=True,
        actor_memory_writes=0,
        setup_memory_writes=len(writes),
        writes=writes,
        changed_cpu_addresses=changed,
        before_memory_sha256=sha256(before).hexdigest(),
        after_memory_sha256=sha256(after).hexdigest(),
    )
