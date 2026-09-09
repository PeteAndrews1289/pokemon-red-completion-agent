"""Prospective Red registration binding; never applied to an old result implicitly."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from .collection import CollectionObservation
from .provenance import canonical_sha256
from .red_collection import RED_COLLECTION_GAME_ID, RED_SOLO_COLLECTION_CONTRACT, red_species_ref
from .registered_collection import REGISTERED_OBJECTIVE, collection_registration_refs
from .registration_memory import RegistrationSnapshot


@dataclass(frozen=True, slots=True)
class RedRegistrationPolicy:
    """Immutable initial global credit and explicit physical reserves.

    The initial ledger is frozen for a run. Later local owned flags add credit;
    another concurrent game's writes cannot silently change this run's objective.
    The controller must retain this binding in new checkpoint/outcome metadata.
    Construction is not permission to reinterpret a legacy model's rewards.
    """

    initial_memory: RegistrationSnapshot
    run_id: str
    initial_snapshot_sha256: str
    initial_collection: CollectionObservation
    protected_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        initial = self.initial_memory.latest(self.run_id)
        if initial is None or initial.game_id != RED_COLLECTION_GAME_ID:
            raise ValueError("Red registered binding requires an actual Red run identity")
        object.__setattr__(self, "initial_collection", replace(
            self.initial_collection,
            owned_species=frozenset(self.initial_collection.owned_species),
            specimens=tuple(self.initial_collection.specimens),
            box_counts=tuple(self.initial_collection.box_counts),
        ))
        self.registered(self.initial_collection)
        counts = Counter(s.species_ref for s in self.initial_collection.specimens)
        protected = dict(self.protected_counts)
        universe = set(RED_SOLO_COLLECTION_CONTRACT.species_universe)
        if any(s not in universe or type(n) is not int or not 0 <= n <= counts[s]
               for s, n in protected.items()):
            raise ValueError("registered policy reserves must name actual physical stock")
        object.__setattr__(self, "protected_counts", MappingProxyType(protected))

    def registered(self, current: CollectionObservation) -> frozenset[str]:
        initial = collection_registration_refs(
            self.initial_memory, self.initial_collection, run_id=self.run_id,
            snapshot_sha256=self.initial_snapshot_sha256,
            national_ids={red_species_ref(n): n for n in range(1, 152)},
        )
        if not self.initial_collection.owned_species <= current.owned_species:
            raise ValueError("registered runtime lost local owned flags")
        if not {s.species_ref for s in current.specimens} <= current.owned_species:
            raise ValueError("registered runtime physical stock lacks local registration")
        return initial | current.owned_species

    @property
    def targets(self) -> frozenset[str]:
        return frozenset(RED_SOLO_COLLECTION_CONTRACT.target_species)

    def document(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.registered-runtime-binding.v1",
            "objective": REGISTERED_OBJECTIVE,
            "initial_memory_sha256": self.initial_memory.sha256,
            "initial_snapshot_sha256": self.initial_snapshot_sha256,
            "run_id": self.run_id,
            "targets": sorted(self.targets),
            "protected_counts": dict(sorted(self.protected_counts.items())),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document())

    def evolution_allowed(
        self, current: CollectionObservation, source: str, target: str,
    ) -> bool:
        """No last-copy quota; explicit reserves and actual local stock still apply."""
        registered = self.registered(current)
        counts = Counter(s.species_ref for s in current.specimens)
        return (target in self.targets and target not in registered
                and counts[source] > self.protected_counts.get(source, 0))

    def verify_evolution(
        self, before: CollectionObservation, after: CollectionObservation,
        source: str, target: str,
    ) -> bool:
        if not self.evolution_allowed(before, source, target):
            return False
        self.registered(after)
        expected = Counter(s.species_ref for s in before.specimens)
        expected[source] -= 1
        expected[target] += 1
        return (Counter(s.species_ref for s in after.specimens) == expected
                and before.owned_species <= after.owned_species
                and target in after.owned_species)
