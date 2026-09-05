from __future__ import annotations

from dataclasses import replace

from test_red_living_dex_clustered_train_runner import _successor_clustered_fixture

from pokemon_red_completion.red_living_dex_causal_inventory import (
    audit_red_living_dex_targeted_update_capacity,
    red_living_dex_targeted_capacity_contexts,
)


def _capabilities():  # type: ignore[no-untyped-def]
    plan, _binding = _successor_clustered_fixture()
    return tuple(item.capability for item in plan.assignments)


def test_red_adapter_preserves_immutable_upstream_partitions_without_identity_leak() -> None:
    contexts = red_living_dex_targeted_capacity_contexts(_capabilities())

    assert len(contexts) == 20
    assert sum(item.partition == "train" for item in contexts) == 16
    assert sum(item.partition == "development" for item in contexts) == 4
    assert len({item.lineage_sha256 for item in contexts}) == 20
    assert len({item.physical_root_sha256 for item in contexts}) == 20
    assert all(len(item.available_option_kinds) == 3 for item in contexts)


def test_red_adapter_excludes_previously_used_lineages_and_roots() -> None:
    contexts = red_living_dex_targeted_capacity_contexts(_capabilities())
    first, second = contexts[:2]

    filtered = red_living_dex_targeted_capacity_contexts(
        _capabilities(),
        excluded_lineages=frozenset({first.lineage_sha256}),
        excluded_physical_roots=frozenset({second.physical_root_sha256}),
    )

    assert len(filtered) == 18
    assert first.lineage_sha256 not in {item.lineage_sha256 for item in filtered}
    assert second.physical_root_sha256 not in {
        item.physical_root_sha256 for item in filtered
    }


def test_red_capacity_fails_on_realistic_raw_count_without_eight_development_roots() -> None:
    result = audit_red_living_dex_targeted_update_capacity(_capabilities())

    assert result.development_contexts == 4
    assert result.development_maximum_matching <= 4
    assert not result.capacity_sufficient
    assert "insufficient_development_kind_compatible_lineages" in result.reasons
    public = result.public_dict()
    encoded = str(public)
    assert public["controller_actions"] == 0
    assert public["outcomes_opened"] == 0
    assert public["root_claims"] == 0
    assert all(item.root.root.physical_root_sha256 not in encoded for item in _capabilities())


def test_red_adapter_ignores_partition_crossing_template_edge() -> None:
    capabilities = _capabilities()
    first = capabilities[0]
    crossed = replace(
        first,
        root=replace(first.root, cluster_partition="development"),
    )

    contexts = red_living_dex_targeted_capacity_contexts(
        (crossed, *capabilities[1:])
    )

    assert len(contexts) == 19
    assert first.root.independence_lineage_sha256 not in {
        item.lineage_sha256 for item in contexts
    }
