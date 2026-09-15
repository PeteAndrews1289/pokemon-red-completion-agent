"""Select one training departure from provenance, before observing its menu.

This is a metadata-only supply decision, not a learned action or an execution
permit. Callers freeze the returned identity, claim that exact root through the
account registry, and then inspect it once. A failed claim or menu gate must not
select a replacement. No capture, model, emulator or outcome is opened here.
"""

from __future__ import annotations

from collections import Counter

from .claim_first_admission import ClaimFirstAvailabilitySnapshot
from .goal_manager_composition_qualification import root_consumption_sha256
from .goal_manager_context_catalog import (
    GoalManagerContextCatalog,
    GoalManagerContextCatalogEntry,
)
from .goal_manager_protocol import GoalManagerCollectionRegistry
from .provenance import canonical_sha256


def training_source_pair(entry: GoalManagerContextCatalogEntry) -> tuple[str, str]:
    """Use existing account-wide logical and physical collision identities."""
    return (
        root_consumption_sha256(
            state_sha256=entry.state_sha256, envelope_sha256=entry.envelope_sha256,
        ),
        canonical_sha256({
            "schema": "pokemon.red.private-physical-setup-root.v1",
            "state_sha256": entry.state_sha256,
            "envelope_sha256": entry.envelope_sha256,
        }),
    )


def eligible_training_sources(
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> tuple[GoalManagerContextCatalogEntry, ...]:
    """Exclude ambiguous identities and nontrain state aliases before selection.

Exact-byte exclusivity is necessary for training admission. It is not proof of
independent upstream lineage and must never be reported as such.
    """
    if (catalog.registry_sha256 != registry.registry_sha256
            or catalog.source_commit != registry.execution.source_commit
            or catalog.source_bundle_sha256 != registry.execution.source_bundle_sha256):
        raise ValueError("training supply catalog registry differs")
    partitions = {
        entry.slot_id: registry.assignment(entry.slot_id).partition
        for entry in catalog.entries
    }
    nontrain_states = {
        entry.state_sha256 for entry in catalog.entries
        if partitions[entry.slot_id] != "train"
    }
    captures = Counter(entry.capture_id for entry in catalog.entries)
    states = Counter(entry.state_sha256 for entry in catalog.entries)
    return tuple(sorted(
        (entry for entry in catalog.entries
         if partitions[entry.slot_id] == "train"
         and entry.state_sha256 not in nontrain_states
         and captures[entry.capture_id] == 1
         and states[entry.state_sha256] == 1),
        key=lambda entry: entry.slot_id,
    ))


def select_training_departure(
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
    availability: ClaimFirstAvailabilitySnapshot,
) -> GoalManagerContextCatalogEntry:
    """Choose the first unclaimed source without using historical menu quality.

The snapshot must cover precisely the eligible census. Live claim acquisition
is still mandatory after this selection: the snapshot can become stale.
    """
    entries = eligible_training_sources(catalog, registry)
    expected = {training_source_pair(entry) for entry in entries}
    availability.__post_init__()
    observed = {
        (row.logical_root_sha256, row.physical_root_sha256): row.available
        for row in availability.observations
    }
    if not expected or set(observed) != expected:
        raise ValueError("training supply availability coverage differs")
    for entry in entries:
        if observed[training_source_pair(entry)]:
            return entry
    raise ValueError("training supply has no unclaimed eligible source")
