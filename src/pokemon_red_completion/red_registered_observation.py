"""Project a frozen registration objective onto fresh Red observations."""

from collections import Counter
from dataclasses import replace

from .generation_one import GENERATION_ONE_LEVEL_EVOLUTIONS
from .goal_manager_state import CompletionProgress
from .provenance import canonical_sha256
from .red_collection import red_species_ref
from .red_goal_manager import RedGoalObservation
from .red_registration_policy import RedRegistrationPolicy
from .registered_checkpoint import RegisteredCollectionCheckpoint
from .registered_collection import REGISTERED_OBJECTIVE

REGISTERED_OBSERVATION_SCHEMA = "pokemon.red.registered-goal-observation.v1"


def registered_completion_checkpoint(
    observation: RedGoalObservation, policy: RedRegistrationPolicy,
) -> RegisteredCollectionCheckpoint:
    current = observation.collection_observation
    global_species = tuple(sorted(policy.registered(current)))
    local_species = tuple(sorted(current.owned_species))
    targets = tuple(sorted(policy.targets))
    counts = tuple(sorted(Counter(s.species_ref for s in current.specimens).items()))
    missing = tuple(sorted(set(targets) - set(global_species)))
    evolutions = tuple(sorted((red_species_ref(a), red_species_ref(b))
                              for a, b, _ in GENERATION_ONE_LEVEL_EVOLUTIONS))
    return RegisteredCollectionCheckpoint(
        registered_species=len(set(targets) & set(global_species)),
        living_species=len(counts),
        required_specimens_remaining=len(missing),
        retained_captures=sum(n for _, n in counts),
        storage_headroom=observation.immediate_capture_slots,
        undeclared_specimen_losses=0,
        completion_contract_sha256=canonical_sha256({
            "schema": "pokemon.red.registered-completion-contract.v1",
            "objective": REGISTERED_OBJECTIVE, "targets": targets,
            "allowed_evolutions": evolutions,
        }),
        specimen_ledger_sha256=canonical_sha256({
            "schema": "pokemon.core.registered-physical-ledger.v1",
            "counts": counts, "local": local_species, "global": global_species,
        }),
        required_specimens_sha256=canonical_sha256({
            "schema": "pokemon.core.missing-registrations.v1", "missing": missing,
        }),
        specimen_counts=counts, allowed_evolutions=evolutions,
        global_species=global_species, local_species=local_species, target_species=targets,
        protected_counts=tuple(sorted(policy.protected_counts.items())),
        binding_sha256=policy.sha256,
    )


def project_registered_observation(
    observation: RedGoalObservation, policy: RedRegistrationPolicy,
) -> RedGoalObservation:
    checkpoint = registered_completion_checkpoint(observation, policy)
    evolution_targets = set(b for _, b in checkpoint.allowed_evolutions) & policy.targets
    evidence = replace(
        observation.evidence,
        registered_collection=CompletionProgress(
            checkpoint.registered_species, len(policy.targets),
        ),
        # Zero targets mean not required, not a fabricated completed living Dex.
        living_collection=CompletionProgress(0, 0),
        level_collection=CompletionProgress(0, 0),
        evolution=CompletionProgress(
            len(evolution_targets & set(checkpoint.global_species)), len(evolution_targets),
        ),
        # Once the declared story is complete there is no fixed team-level quota.
        # Actual safety, HP, PP and selected evolution requirements remain active.
        team_readiness=(1.0 if observation.evidence.story.satisfaction == 1.0
                        else observation.evidence.team_readiness),
    )
    return replace(observation, evidence=evidence, registered_checkpoint=checkpoint)
