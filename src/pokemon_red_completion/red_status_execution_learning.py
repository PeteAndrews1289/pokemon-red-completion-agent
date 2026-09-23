"""TRAIN-only decision eligibility; never selects or masks an actor action.

An awake action remains eligible even if paralysis, confusion, a miss or an
opponent knockout subsequently suppresses it. Post-outcome filtering would bias
learning. Sleeping turns still count in whole-battle return and qualification.
"""

from .red_balanced_status_features import BALANCED_STATUS_NAMES

ELIGIBILITY_SCHEMA = "pokemon.red.status.predecision-learning-eligibility.v1"


def eligible_target(target):
    if target["role"] != "train":
        raise ValueError("eligibility cannot relabel evaluation data")
    rows = [v for v in target["vectors"]
            if v[BALANCED_STATUS_NAMES.index("choice.status")]]
    if len(rows) != 1:
        raise ValueError("expected one status contrast")
    asleep = rows[0][BALANCED_STATUS_NAMES.index("choice.player_asleep")]
    if asleep not in (0., 1.):
        raise ValueError("sleep indicator must be boolean")
    return not bool(asleep)


def split_targets(targets):
    eligible, excluded = [], []
    for target in targets:
        if eligible_target(target):
            eligible.append(target)
        else:
            excluded.append({"capture_id": target["capture_id"], "reason": "predecision_sleep"})
    return eligible, {"schema": ELIGIBILITY_SCHEMA, "input_count": len(targets),
                      "eligible_count": len(eligible), "excluded": excluded}
