"""Conservative alias groups for historical Red trainer-source ancestry."""

from __future__ import annotations

import re

_LEGACY_GOAL_SLOT = re.compile(r"red-goal-v1-\d{3}-")


def trainer_origin_cluster(root_lineage_id: str) -> str:
    """Never mistake different historical labels for independent game starts.

    The old goal-manager and battle-control banks expose state hashes but no
    authenticated clean-power parent trail. Their same-player progression is
    correlated. A future ancestry audit may split this group with proof.
    """
    if (
        _LEGACY_GOAL_SLOT.match(root_lineage_id)
        or root_lineage_id.startswith("training-control-v")
        or root_lineage_id == "red-lab-rival-train-20260917-offset137"
    ):
        return "unresolved-legacy-red-origin"
    return root_lineage_id
