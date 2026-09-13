"""Pure helper for extracting declared Mart funding departure boundary.

Unblocks model-selected earning versus capture/purchase when inside a declared
Mart with an opt-in funding departure configuration.
"""

from __future__ import annotations

from collections.abc import Mapping

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
)
from pokemon_red_completion.route_executor import TraversalSnapshot


def declared_mart_funding_exit(
    profile: RedGoalContextProfile,
    start: TraversalSnapshot,
) -> int | None:
    """Return observed outdoor map for Mart funding departure, or None.

    Returns start.last_outside_map only when:
    - profile is a RedGoalContextProfile with a single RESUPPLY spec
      (authentication remains the caller's duty)
    - that spec has mechanic RedGoalMechanic.MART_RESUPPLY ("mart_resupply")
    - explicitly sets mart_funding_departure=True (NEW default-off parameter),
      indoor_funding_departure=True, and affordable_ball_purchase=True
    - its declared map_id equals the actual indoor start.map_id (map_id >= 0x25)
    - observed last_outside_map is a valid outdoor integer 0..0x24
    - start is ready, on land, with interruption None

    Never infers destination from map arithmetic, chooses routes, or modifies flags.
    Booleans are explicitly rejected from masquerading as integer map IDs.
    """
    if not isinstance(profile, RedGoalContextProfile):
        return None
    if not isinstance(start, TraversalSnapshot):
        return None

    # start must be ready, on land, and without interruption
    if start.ready is not True:
        return None
    if start.interruption is not None:
        return None
    if start.mode != "land":
        return None

    # start.map_id must be a valid indoor map integer (0x25 or higher)
    # booleans must not masquerade as integer maps (in Python bool is subclass of int)
    if type(start.map_id) is not int:
        return None
    if start.map_id < 0x25:
        return None

    # observed last_outside_map must be a valid outdoor integer 0..0x24
    if type(start.last_outside_map) is not int:
        return None
    if not (0 <= start.last_outside_map <= 0x24):
        return None

    # Exactly one RESUPPLY spec
    resupply_specs = [
        spec
        for spec in profile.providers
        if getattr(spec, "kind", None) is GoalKind.RESUPPLY
    ]
    if len(resupply_specs) != 1:
        return None

    spec = resupply_specs[0]
    if getattr(spec, "mechanic", None) != RedGoalMechanic.MART_RESUPPLY:
        return None

    # Ensure no other provider declares mart_resupply mechanic
    mart_specs = [
        spec
        for spec in profile.providers
        if getattr(spec, "mechanic", None) == RedGoalMechanic.MART_RESUPPLY
    ]
    if len(mart_specs) != 1:
        return None

    params = getattr(spec, "parameters", None)
    if not isinstance(params, Mapping):
        return None

    # NEW default-off parameter mart_funding_departure must be strictly True
    if params.get("mart_funding_departure") is not True:
        return None

    # Existing indoor funding and affordable ball purchase must both be strictly True
    if params.get("indoor_funding_departure") is not True:
        return None
    if params.get("affordable_ball_purchase") is not True:
        return None

    # Declared map_id must be an integer (not bool) and equal start.map_id
    declared_map_id = params.get("map_id")
    if type(declared_map_id) is not int:
        return None
    if declared_map_id != start.map_id:
        return None

    return start.last_outside_map
