"""Registered-only outcome reconstruction; historical labels remain unchanged."""

from collections.abc import Mapping
from dataclasses import replace

from .goal_manager import GoalKind
from .living_dex_option_value import LivingDexObservedOutcome
from .red_living_dex_causal_adapter import red_living_dex_outcome_from_observations
from .red_registered_observation import REGISTERED_OBSERVATION_SCHEMA
from .registered_checkpoint import RegisteredCollectionCheckpoint, require_registered_transition


def red_registered_outcome_from_observations(
    before: Mapping[str, object], after: Mapping[str, object], *,
    selected_kind: GoalKind, succeeded: bool, actions: int, frames: int,
    maximum_actions: int, maximum_frames: int,
) -> LivingDexObservedOutcome:
    """Reconstruct novelty from sets, retaining existing actual resource costs.

    A malformed/lost-inventory transition raises instead of producing a success
    target. Callers must quarantine that episode, not silently fit a failure as
    another arm's success. Interrupted observations never reach this function.
    """
    if (before.get("schema") != REGISTERED_OBSERVATION_SCHEMA
            or after.get("schema") != REGISTERED_OBSERVATION_SCHEMA
            or not isinstance(selected_kind, GoalKind)):
        raise ValueError("registered outcome observation schema differs")
    old = RegisteredCollectionCheckpoint.from_public(before.get("registration"))
    new = RegisteredCollectionCheckpoint.from_public(after.get("registration"))
    require_registered_transition(
        old, new, selected_kind=selected_kind,
        require_selected_goal_progress=succeeded,
    )
    old_local, new_local = before.get("semantic_observation"), after.get("semantic_observation")
    if not isinstance(old_local, Mapping) or not isinstance(new_local, Mapping):
        raise ValueError("registered outcome resource observations differ")
    for local, checkpoint in ((old_local, old), (new_local, new)):
        collection = local.get("collection")
        if collection != {
            "registered": checkpoint.registered_species,
            "registered_target": len(checkpoint.target_species),
            "living": 0, "living_target": 0, "level_cap": 0, "level_cap_target": 0,
        }:
            raise ValueError("registered outcome projected counts differ")
    costs = red_living_dex_outcome_from_observations(
        old_local, new_local, succeeded=succeeded, actions=actions, frames=frames,
        maximum_actions=maximum_actions, maximum_frames=maximum_frames,
    )
    novelty = len((set(new.global_species) - set(old.global_species)) & set(old.target_species))
    return replace(
        costs, verified_success=succeeded,
        completion_gain=novelty / max(1, len(old.target_species)),
        irreversible_loss=0.0,
    )
