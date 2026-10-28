"""Narrow Red cash bounds for free walking approaches, not a risk predictor.

No policy features, purchases, funding or learned choices change. Unknown paths
keep the full-wallet reservation. A certified approach forbids random encounter
maps, poison, field moves and scripted dialogue; unexpected battles are rejected
by the existing route executor without choosing a combat action.
"""

from dataclasses import replace
from functools import lru_cache

from .actions import MacroActionKind
from .gen1_cartridge import MAP_ID_LIMIT, WILD_DATA_BANK, WILD_POINTER_ARRAY, bank_offset
from .rom import verify_rom_bytes
from .route_executor import RouteExecutionError


@lru_cache(maxsize=2)
def encounter_free_maps(rom: bytes) -> frozenset[int]:
    verify_rom_bytes(rom)
    result = set()
    for map_id in range(MAP_ID_LIMIT):
        offset = WILD_POINTER_ARRAY + 2 * map_id
        address = int.from_bytes(rom[offset : offset + 2], "little")
        # Invalid pointers are UNKNOWN, never evidence of no encounters.
        if 0x4000 <= address <= 0x7FFF:
            at = bank_offset(WILD_DATA_BANK, address)
            if rom[at : at + 2] == b"\x00\x00":
                result.add(map_id)
    return frozenset(result)


def require_cash_safe_plan(rom, raw, plan):
    hp, statuses = raw.party_hp, getattr(raw, "party_status", None)
    if (
        not hp
        or not any(hp)
        or statuses is None
        or len(statuses) != len(hp)
        or any(type(s) is not int or not 0 <= s <= 255 or s & 8 for s in statuses)
        or not set(plan.macro_path.maps) <= encounter_free_maps(rom)
        or any(s.action_kind is not MacroActionKind.MOVE for s in plan.steps)
    ):
        raise RouteExecutionError("cash-safe approach cannot certify poison/encounters/actions")


def certified_cash_safe_transition(route, raw, plan):
    """Opt in only when the real executor can enforce the same certificate."""
    from .red_training_ground_route import RedVermilionGroundTransition

    if not isinstance(route, RedVermilionGroundTransition):
        return None
    try:
        require_cash_safe_plan(route.rom, raw, plan)
    except RouteExecutionError:
        return None
    return replace(
        route,
        require_cash_safe=True,
        maximum_flees=0,
        maximum_scripted_dialogues=0,
    )


def single_blackout_cash_bound(raw, safe_approach):
    """One authenticated trainer lifecycle returns after its first win/loss."""
    cash = raw.player_money
    if safe_approach is None or type(cash) is not int or not 0 <= cash <= 999999:
        return None
    return cash - cash // 2
