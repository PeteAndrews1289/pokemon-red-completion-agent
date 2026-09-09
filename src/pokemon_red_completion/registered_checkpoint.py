"""Versioned registration facts at the player boundary, separate from living quotas.

The compatibility properties serve the existing bounded executor only. Serialized
records name registrations explicitly and retain the sets needed to verify novelty.
They never authorize release or turn shared credit into local physical stock.
"""

from __future__ import annotations

from dataclasses import dataclass

from .goal_manager import GoalKind
from .goal_manager_composition_runtime import (
    GoalManagerCompositionError,
    LivingCollectionCheckpoint,
)
from .provenance import canonical_sha256
from .registered_collection import REGISTERED_OBJECTIVE

REGISTERED_CHECKPOINT_SCHEMA = "pokemon.core.registered-collection-checkpoint.v1"


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisteredCollectionCheckpoint(LivingCollectionCheckpoint):
    """Frozen global credit, actual local flags and physical inventory.

    Inherited numeric fields are validated projections, not independent claims.
    ``required_specimens_remaining`` is compatibility access to the missing-entry
    count; its historical name is deliberately absent from the new serialization.
    """

    global_species: tuple[str, ...]
    local_species: tuple[str, ...]
    target_species: tuple[str, ...]
    protected_counts: tuple[tuple[str, int], ...]
    binding_sha256: str

    def __post_init__(self) -> None:
        super(RegisteredCollectionCheckpoint, self).__post_init__()
        for values in (self.global_species, self.local_species, self.target_species):
            if (not isinstance(values, tuple)
                    or any(not isinstance(s, str) or not s for s in values)
                    or tuple(sorted(set(values))) != values):
                raise ValueError("registered checkpoint species must be sorted unique references")
        counts = dict(self.specimen_counts)
        if (not set(counts) <= set(self.local_species)
                or not set(self.local_species) <= set(self.global_species)):
            raise ValueError("registered checkpoint global/local/physical views disagree")
        if (not isinstance(self.protected_counts, tuple)
                or tuple(sorted(self.protected_counts)) != self.protected_counts
                or len(dict(self.protected_counts)) != len(self.protected_counts)
                or any(not isinstance(s, str) or type(n) is not int or n < 0
                       or n > counts.get(s, 0) for s, n in self.protected_counts)):
            raise ValueError("registered checkpoint lost protected physical stock")
        if (not isinstance(self.binding_sha256, str) or len(self.binding_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.binding_sha256)):
            raise ValueError("registered checkpoint binding differs")
        missing = tuple(sorted(set(self.target_species) - set(self.global_species)))
        if (self.registered_species != len(set(self.global_species) & set(self.target_species))
                or self.living_species != len(counts)
                or self.required_specimens_remaining != len(missing)
                or self.retained_captures != sum(counts.values())
                or self.undeclared_specimen_losses != 0
                or self.required_specimens_sha256 != canonical_sha256({
                    "schema": "pokemon.core.missing-registrations.v1", "missing": missing,
                })
                or self.specimen_ledger_sha256 != canonical_sha256({
                    "schema": "pokemon.core.registered-physical-ledger.v1",
                    "counts": self.specimen_counts,
                    "local": self.local_species,
                    "global": self.global_species,
                })):
            raise ValueError("registered checkpoint projections differ")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": REGISTERED_CHECKPOINT_SCHEMA,
            "objective": REGISTERED_OBJECTIVE,
            "binding_sha256": self.binding_sha256,
            "completion_contract_sha256": self.completion_contract_sha256,
            "registered_species": self.registered_species,
            "local_registered_species": len(self.local_species),
            "living_species": self.living_species,
            "required_registrations_remaining": self.required_specimens_remaining,
            "total_living_specimens": self.retained_captures,
            "storage_headroom": self.storage_headroom,
            "required_registrations_sha256": self.required_specimens_sha256,
            "specimen_ledger_sha256": self.specimen_ledger_sha256,
            "global_species": list(self.global_species),
            "local_species": list(self.local_species),
            "target_species": list(self.target_species),
            "specimen_counts": [list(item) for item in self.specimen_counts],
            "protected_counts": [list(item) for item in self.protected_counts],
            "allowed_evolutions": [list(item) for item in self.allowed_evolutions],
        }

    @classmethod
    def from_public(cls, document: object) -> RegisteredCollectionCheckpoint:
        if not isinstance(document, dict) or document.get("schema") != REGISTERED_CHECKPOINT_SCHEMA:
            raise ValueError("registered checkpoint schema differs")
        try:
            result = cls(
                registered_species=document["registered_species"],
                living_species=document["living_species"],
                required_specimens_remaining=document["required_registrations_remaining"],
                retained_captures=document["total_living_specimens"],
                storage_headroom=document["storage_headroom"],
                undeclared_specimen_losses=0,
                completion_contract_sha256=document["completion_contract_sha256"],
                specimen_ledger_sha256=document["specimen_ledger_sha256"],
                required_specimens_sha256=document["required_registrations_sha256"],
                specimen_counts=tuple(tuple(item) for item in document["specimen_counts"]),
                allowed_evolutions=tuple(tuple(item) for item in document["allowed_evolutions"]),
                global_species=tuple(document["global_species"]),
                local_species=tuple(document["local_species"]),
                target_species=tuple(document["target_species"]),
                protected_counts=tuple(tuple(item) for item in document["protected_counts"]),
                binding_sha256=document["binding_sha256"],
            )
        except (KeyError, TypeError) as error:
            raise ValueError("registered checkpoint fields differ") from error
        if result.public_dict() != document:
            raise ValueError("registered checkpoint document differs")
        return result


def require_registered_transition(
    before: RegisteredCollectionCheckpoint,
    after: RegisteredCollectionCheckpoint,
    *, selected_kind: GoalKind,
    require_selected_goal_progress: bool = True,
) -> None:
    """Allow legitimate evolution, never unexplained loss or regressed credit.

    Duplicate acquisition is legal even without novelty. Preparation and actual
    costs remain observable; only first global registration is completion gain.
    """
    if (before.binding_sha256 != after.binding_sha256
            or before.completion_contract_sha256 != after.completion_contract_sha256
            or before.target_species != after.target_species
            or before.protected_counts != after.protected_counts
            or before.allowed_evolutions != after.allowed_evolutions
            or not set(before.global_species) <= set(after.global_species)
            or not set(before.local_species) <= set(after.local_species)
            or set(after.global_species) - set(before.global_species)
               != (set(after.local_species) - set(before.local_species)
                   - set(before.global_species))):
        raise GoalManagerCompositionError("registered collection binding or credit regressed")
    old, new = dict(before.specimen_counts), dict(after.specimen_counts)
    decreases = {s: n - new.get(s, 0) for s, n in old.items() if n > new.get(s, 0)}
    increases = {s: n - old.get(s, 0) for s, n in new.items() if n > old.get(s, 0)}
    evolution = (
        selected_kind is GoalKind.EVOLVE_SPECIES
        and len(decreases) == len(increases) == 1
        and list(decreases.values()) == list(increases.values()) == [1]
        and (next(iter(decreases)), next(iter(increases))) in before.allowed_evolutions
        and next(iter(increases)) in after.local_species
    )
    if decreases and not evolution:
        raise GoalManagerCompositionError("registered collection lost an undeclared specimen")
    changed = (before.global_species != after.global_species
               or before.local_species != after.local_species or old != new)
    if selected_kind not in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES} and changed:
        raise GoalManagerCompositionError("registered non-collection goal changed collection")
    if selected_kind is GoalKind.ACQUIRE_SPECIES:
        if require_selected_goal_progress and not increases:
            raise GoalManagerCompositionError("registered capture has no physical acquisition")
        if not set(after.local_species) - set(before.local_species) <= set(increases):
            raise GoalManagerCompositionError("registered capture flags lack physical evidence")
    if selected_kind is GoalKind.EVOLVE_SPECIES:
        if require_selected_goal_progress and not evolution:
            raise GoalManagerCompositionError("registered evolution lacks exact transformation")
        if evolution and not set(after.local_species) - set(before.local_species) <= set(increases):
            raise GoalManagerCompositionError("registered evolution flags lack transformation")
