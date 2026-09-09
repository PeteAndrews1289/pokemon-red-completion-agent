"""Registered-only completion V1; legacy living/level contracts stay unchanged.

These projections do not authorize a skill or change old learner rewards. The
runtime must explicitly opt into this objective and bind its initial memory.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from .collection import CollectionObservation
from .pokedex import PokedexTarget
from .registration_memory import RegistrationSnapshot

REGISTERED_OBJECTIVE = "pokemon.registered-collection.v1"


def collection_registration_refs(
    memory: RegistrationSnapshot, collection: CollectionObservation, *,
    run_id: str, snapshot_sha256: str, national_ids: Mapping[str, int],
) -> frozenset[str]:
    """Bind stored registration to the current semantic inventory for planning.

    Returns globally credited references in this adapter's namespace only.
    Reject stale local inventory/checkpoint joins; do not replace it with global
    stock. The returned set feeds registered capture/evolution projections.
    """
    mapping = dict(national_ids)
    if (any(not isinstance(s, str) or not s for s in mapping)
            or any(type(n) is not int or n <= 0 for n in mapping.values())
            or len(set(mapping.values())) != len(mapping)):
        raise ValueError("adapter mapping must bind unique positive National identifiers")
    local = memory.latest(run_id)
    if local is None or local.snapshot_sha256 != snapshot_sha256:
        raise ValueError("registered planning needs the current recorded checkpoint")
    counts = Counter(s.species_ref for s in collection.specimens)
    if not collection.owned_species | counts.keys() <= mapping.keys():
        raise ValueError("adapter mapping is missing local species")
    if (frozenset(mapping[s] for s in collection.owned_species) != local.owned
            or {mapping[s]: n for s, n in counts.items()} != local.physical_counts):
        raise ValueError("registered planning inventory differs from recorded local state")
    return frozenset(s for s, n in mapping.items() if n in memory.registered)


@dataclass(frozen=True, slots=True)
class RegisteredCollectionReport:
    objective: str
    memory_sha256: str
    target: frozenset[int]
    globally_registered: frozenset[int]
    locally_registered: frozenset[int]
    physical_species: frozenset[int]

    @property
    def missing(self) -> frozenset[int]:
        return self.target - self.globally_registered

    @property
    def globally_credited_but_not_local(self) -> frozenset[int]:
        return (self.target & self.globally_registered) - self.locally_registered

    @property
    def passed(self) -> bool:
        # Story completion is a separate predicate. This is registration only.
        return not self.missing


def summarize_registered_collection(
    target: PokedexTarget, memory: RegistrationSnapshot, *, run_id: str,
) -> RegisteredCollectionReport:
    """Use declared title availability without changing local flags or stock."""
    local = memory.latest(run_id)
    return RegisteredCollectionReport(
        REGISTERED_OBJECTIVE, memory.sha256, target.obtainable, memory.registered,
        local.owned if local is not None else frozenset(),
        frozenset(local.physical_counts) if local is not None else frozenset(),
    )


def new_registration_credit(
    before: RegistrationSnapshot, after: RegistrationSnapshot, *, target: PokedexTarget,
) -> frozenset[int]:
    """Novelty only, not the full learning reward. Duplicates have zero credit.

    A frozen initial snapshot separates inherited credit from new achievements.
    Actual resource costs and action attribution belong to the outcome verifier.
    """
    if not {row.sha256 for row in before.observations} <= {
        row.sha256 for row in after.observations
    }:
        raise ValueError("registration history was removed or rewritten")
    return (after.registered - before.registered) & target.obtainable
