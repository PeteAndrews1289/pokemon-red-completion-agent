from dataclasses import asdict, replace

import pytest
from test_goal_manager_context_catalog import _entries, _registry

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAvailabilitySnapshot,
    ClaimFirstPairAvailability,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogEntry,
    build_goal_manager_context_catalog_payload,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.red_full_pokedex_training_supply import (
    eligible_training_sources,
    select_training_departure,
    training_source_pair,
)


@pytest.fixture
def source():
    registry = _registry()
    catalog = parse_goal_manager_context_catalog(
        build_goal_manager_context_catalog_payload(registry, _entries(registry)), registry,
    )
    return catalog, registry


def snapshot(entries, claimed=()):
    pairs = sorted({training_source_pair(entry) for entry in entries})
    return ClaimFirstAvailabilitySnapshot("f" * 64, tuple(
        ClaimFirstPairAvailability(*pair, pair not in claimed) for pair in pairs
    ))


def rebuild_entry(registry, entry, **changes):
    data = asdict(entry)
    for field in ("slot_id", "assignment_id", "context_id"):
        data.pop(field)
    return GoalManagerContextCatalogEntry.build(
        assignment=registry.assignment(entry.slot_id), **{**data, **changes},
    )


def test_selects_by_slot_order_and_claims_not_catalog_order_or_focus(source):
    catalog, registry = source
    entries = eligible_training_sources(catalog, registry)
    assert len(entries) == 54
    available = snapshot(entries, (training_source_pair(entries[0]),))
    assert select_training_departure(catalog, registry, available) == entries[1]
    reordered = replace(catalog, entries=tuple(reversed(catalog.entries)))
    assert select_training_departure(reordered, registry, available) == entries[1]


def test_cross_partition_state_alias_is_excluded_even_with_different_envelope(source):
    catalog, registry = source
    first = eligible_training_sources(catalog, registry)[0]
    validation = next(e for e in catalog.entries
                      if registry.assignment(e.slot_id).partition != "train")
    # The independent catalog parser is already tested. Mutate its parsed
    # metadata to exercise the supply boundary's own contamination defense.
    altered = rebuild_entry(registry, validation, state_sha256=first.state_sha256)
    catalog = replace(catalog, entries=tuple(
        altered if e is validation else e for e in catalog.entries))
    assert first not in eligible_training_sources(catalog, registry)


@pytest.mark.parametrize("field", ["capture_id", "state_sha256"])
def test_ambiguous_train_identity_excluded(source, field):
    catalog, registry = source
    first, second = eligible_training_sources(catalog, registry)[:2]
    alias = rebuild_entry(registry, second, **{field: getattr(first, field)})
    altered = replace(catalog, entries=tuple(alias if e is second else e
                                            for e in catalog.entries))
    selected = eligible_training_sources(altered, registry)
    assert first not in selected and second not in selected


@pytest.mark.parametrize("change", ["missing", "extra", "all_claimed"])
def test_partial_or_exhausted_availability_cannot_select(source, change):
    catalog, registry = source
    entries = eligible_training_sources(catalog, registry)
    pairs = tuple(training_source_pair(entry) for entry in entries)
    available = snapshot(entries, pairs if change == "all_claimed" else ())
    if change == "missing":
        available = replace(available, observations=available.observations[1:])
    elif change == "extra":
        available = replace(available, observations=tuple(sorted(
            (*available.observations, ClaimFirstPairAvailability("0" * 64, "1" * 64, True)),
            key=lambda row: (row.logical_root_sha256, row.physical_root_sha256),
        )))
    with pytest.raises(ValueError, match="coverage|no unclaimed"):
        select_training_departure(catalog, registry, available)


def test_registry_mismatch_rejected_before_selection(source):
    catalog, registry = source
    with pytest.raises(ValueError, match="registry differs"):
        eligible_training_sources(replace(catalog, registry_sha256="f" * 64), registry)
