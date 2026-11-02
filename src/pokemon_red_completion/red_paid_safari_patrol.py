"""Conservative mechanical patrol selection within one model-chosen area.

Quotes count possible grass landings, not encounters or capture probabilities.
The existing live executor still authenticates admission and the actual exit.
"""

from .red_safari_acquisition import RedSafariPatrolPlan


def choose_paid_safari_patrol(
    legacy, two_grass, *, terrain, steps_after_admission, quote_exit_steps
):
    """Prefer a two-grass lane only with strictly more safely budgeted landings."""
    if type(steps_after_admission) is not int or steps_after_admission < 0:
        raise ValueError("paid Safari remaining steps must be a nonnegative integer")
    if not isinstance(legacy, RedSafariPatrolPlan):
        raise TypeError("paid Safari selection requires the existing patrol")
    evidence = {"selected": "legacy", "exit_margin_steps": 18,
                "steps_after_admission": steps_after_admission,
                "encounter_or_success_prediction": False}
    if two_grass is None:
        return legacy, evidence
    if (not isinstance(two_grass, RedSafariPatrolPlan)
            or two_grass.source_id != legacy.source_id
            or two_grass.map_id != legacy.map_id
            or two_grass.start_at != legacy.start_at
            or terrain.map_id != legacy.map_id):
        raise ValueError("paid Safari alternatives must share one area and entry")

    def grass(plan):
        points = (plan.first_at, plan.second_at)
        if any(not (0 <= y < terrain.height and 0 <= x < terrain.width)
               for y, x in points):
            raise ValueError("paid Safari patrol leaves its terrain")
        flags = tuple(bool(terrain.grass[y][x]) for y, x in points)
        if sum(flags) != plan.encounter_tile_count:
            raise ValueError("paid Safari declared grass differs from terrain")
        return flags

    old_grass, new_grass = grass(legacy), grass(two_grass)
    if not all(new_grass):
        return legacy, evidence

    def quote(plan, flags):
        try:
            lengths = quote_exit_steps(plan)
        except Exception:
            # Any unavailable prospective quote preserves the executable legacy
            # offer. Interrupts/system exits still propagate.
            return None
        if (not isinstance(lengths, (tuple, list)) or len(lengths) != 2
                or any(type(n) is not int or n < 0 for n in lengths)):
            return None
        walks = max(0, steps_after_admission - len(plan.approach_directions)
                    - max(lengths) - 18)
        # The approach ends at first_at; the first patrol step lands on second_at.
        landings = ((walks + 1) // 2) * flags[1] + (walks // 2) * flags[0]
        return {"approach_steps": len(plan.approach_directions),
                "exit_steps": list(lengths), "patrol_step_budget": walks,
                "grass_landing_upper_bound": landings}

    old, new = quote(legacy, old_grass), quote(two_grass, new_grass)
    evidence.update(legacy=old, two_grass=new)
    if old is not None and new is not None and (
            new["grass_landing_upper_bound"] > old["grass_landing_upper_bound"]):
        evidence["selected"] = "two_grass"
        return two_grass, evidence
    return legacy, evidence
