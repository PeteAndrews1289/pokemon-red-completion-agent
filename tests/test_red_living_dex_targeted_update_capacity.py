from __future__ import annotations

from dataclasses import replace

from test_red_living_dex_clustered_train_runner import _successor_clustered_fixture
from test_red_living_dex_provider_plan import _root as _provider_root
from test_red_living_dex_setup_recipe import _recipes
from test_red_living_dex_setup_recipe import _root as _setup_root

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
    audit_red_living_dex_targeted_update_capacity,
    freeze_red_living_dex_targeted_schedule,
    red_living_dex_targeted_capacity_contexts,
)


def _capabilities():  # type: ignore[no-untyped-def]
    plan, _binding = _successor_clustered_fixture()
    return tuple(item.capability for item in plan.assignments)


def _repeatable_capabilities() -> tuple[RedLivingDexCausalRootCapability, ...]:
    slots = build_red_living_dex_prospective_capture_plan().slots
    recipes = _recipes()
    capabilities: list[RedLivingDexCausalRootCapability] = []
    specifications = (
        *((ordinal, template) for ordinal in range(2) for template in (0, 7, 9)),
        *(
            (2 + offset, template)
            for offset, template in enumerate((10, 12, 13, 14, 11, 10, 13, 11))
        ),
    )
    for ordinal, template_ordinal in specifications:
        partition = "train" if ordinal < 2 else "development"
        slot = slots[template_ordinal]
        assert (slot.partition is LivingDexCapturePartition.TRAIN) == (partition == "train")
        root = _setup_root(100 + ordinal)
        recipe = replace(
            recipes[template_ordinal],
            root_consumption_sha256=root.root_consumption_sha256,
            root_state_sha256=root.state_sha256,
            root_envelope_sha256=root.envelope_sha256,
        )
        observation = replace(
            _provider_root(100 + ordinal),
            root=root,
            observed_state_sha256=root.state_sha256,
            independence_lineage_sha256=canonical_sha256({"lineage": 100 + ordinal}),
            cluster_partition=partition,
        )
        capabilities.append(
            RedLivingDexCausalRootCapability(
                root=observation,
                template_ordinal=template_ordinal,
                slot=slot,
                recipe=recipe,
            )
        )
    return tuple(capabilities)


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
    assert second.physical_root_sha256 not in {item.physical_root_sha256 for item in filtered}


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

    contexts = red_living_dex_targeted_capacity_contexts((crossed, *capabilities[1:]))

    assert len(contexts) == 19
    assert first.root.independence_lineage_sha256 not in {item.lineage_sha256 for item in contexts}


def test_red_repeatable_schedule_binds_one_recipe_per_semantic_slot() -> None:
    capabilities = _repeatable_capabilities()

    frozen = freeze_red_living_dex_targeted_schedule(
        capabilities,
        maximum_train_replays_per_context=5,
    )

    assert len(frozen.schedule.slots) == 18
    assert len(frozen.capabilities) == 18
    assert frozen.public_dict()["train_resets"] == 10
    assert frozen.public_dict()["train_roots"] == 2
    assert frozen.public_dict()["development_roots"] == 8
    assert frozen.public_dict()["red_recipes_bound"] == 18
    assert frozen.public_dict()["cartridge_specific_policy_features"] == 0
