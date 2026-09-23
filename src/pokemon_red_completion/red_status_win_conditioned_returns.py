"""Versioned TRAIN reward: winning efficiency cannot reward an earlier defeat.

V1 remains immutable. This function never selects actions or turns readiness
flags into effect labels. Only actual retained resources and transitions enter.
"""

from math import isfinite

from .red_status_closed_loop_returns import unchanged_status_turns

RETURN_SCHEMA = "pokemon.red.status.win-conditioned-return.v2"
MAX_DECISIONS = 40


def win_conditioned_return(episode):
    steps, stop = episode["decisions"], episode["stop_reason"]
    if not 1 <= len(steps) <= MAX_DECISIONS or stop not in {
            "battle_won", "party_defeated", "player_turn_budget"}:
        raise ValueError("v2 reward requires a retained1-40decision terminal")
    before, after = steps[0]["state_before"], steps[-1]["state_after"]
    own_cap = sum(before["party_max_hp"])
    foe_cap = steps[0]["observation"]["features"]["battle"]["opponent_max_hp"]
    pp = episode["metrics"]["party_pp_spent"]
    values = [own_cap, foe_cap, pp, *after["party_hp"],
              steps[0]["opponent_hp_before"], steps[-1]["opponent_hp_after"]]
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
            for v in values) or own_cap <= 0 or foe_cap <= 0 or pp < 0
            or any(v < 0 for v in after["party_hp"])):
        raise ValueError("v2 reward requires finite measured resources")
    hp = sum(after["party_hp"]) / own_cap
    old_foe, new_foe = (steps[0]["opponent_hp_before"], steps[-1]["opponent_hp_after"])
    if not (0 <= hp <= 1 and 0 <= old_foe <= foe_cap and 0 <= new_foe <= foe_cap):
        raise ValueError("v2 reward resource ratios outside declared single-opponent scope")
    damage = (old_foe - new_foe) / foe_cap
    efficiency = 0.
    if stop == "battle_won":
        efficiency = (.1 * len(steps) / MAX_DECISIONS
                      + .01 * min(pp / MAX_DECISIONS, 1.)
                      + .5 * len(unchanged_status_turns(episode)) / MAX_DECISIONS)
    return (10. if stop == "battle_won" else -10.) + .5 * hp + .5 * damage - efficiency
