"""Native assisted acquisition curriculum, distinct from comparative policy data.

No actor choice, economy target, production promotion or identity-bearing feature
is invented. The caller must retain prospective declarations and native audits.
"""

from .living_dex_option_value import (
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionKind,
    LivingDexOutcomeStatus,
)
from .red_collection import RED_SOLO_COLLECTION_CONTRACT
from .red_living_dex_setup_policy import red_living_dex_setup_candidate_features
from .red_player_training_plan import COMPLETION_ACTIONS, COMPLETION_FRAMES
from .red_scripted_gift import verify_gift_transition


def gift_curriculum_projection(before, binding):
    """Acquisition-only lesson context, measured before execution, not a menu.

    This lesson has no story, battle-development or access objective. It must
    not be described as identical to the ordinary full-player context.
    """
    targets = set(RED_SOLO_COLLECTION_CONTRACT.target_species)
    collection = before.collection_observation
    slots = 6 - before.raw.party_count + 20 - collection.box_counts[collection.current_box_index]
    if slots <= 0:
        raise ValueError("gift curriculum has no immediate capacity")
    context = LivingDexOptionContext(
        collection_pressure=1-len(collection.owned_species & targets)/len(targets),
        dependency_pressure=0, access_pressure=0, resource_pressure=0,
        storage_pressure=max(0, 1-slots/8), party_pressure=0, knowledge_pressure=0,
    )
    candidate = LivingDexOptionCandidate(
        binding_ref=binding.binding_ref,
        features=red_living_dex_setup_candidate_features(
            LivingDexOptionKind.ACQUIRE, route_controller_actions=0, maximum_controller_actions=1,
            estimated_effort=binding.estimated_effort, estimated_risk=binding.estimated_risk,
            storage_unit=context.storage_pressure),
        availability=LivingDexOptionAvailability.AVAILABLE,
    )
    return context, candidate


def gift_curriculum_outcome(before, after, gift, *, received, actions, frames):
    if (type(actions) is not int or type(frames) is not int
            or not 0 < actions <= 1000 or not 0 < frames <= 80000
            or not verify_gift_transition(before, after, gift, received=received)
            or before.party.members != after.party.members[:len(before.party.members)]):
        raise ValueError("gift curriculum lacks an exact native outcome")
    # Ordinary registered-player labels meter total box headroom, not the
    # immediate admission capacity used above. Party delivery consumes no box.
    old_free = sum(20-n for n in before.collection_observation.box_counts)
    new_free = sum(20-n for n in after.collection_observation.box_counts)
    return LivingDexObservedOutcome(
        LivingDexOutcomeStatus.SETTLED, verified_success=True,
        completion_gain=1/len(RED_SOLO_COLLECTION_CONTRACT.target_species),
        dependency_unlock_gain=0,
        action_cost=actions/COMPLETION_ACTIONS, frame_cost=frames/COMPLETION_FRAMES,
        resource_cost=0, party_cost=0,
        storage_cost=max(0, old_free-new_free)/max(1, old_free), irreversible_loss=0,
    )
