from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from test_red_living_dex_provider_plan import _corridors, _roots, _RouteWorld

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
)
from pokemon_red_completion.red_living_dex_clustered_powered_capacity import (
    adapt_red_living_dex_clustered_powered_capacity,
    audit_red_living_dex_clustered_powered_capacity,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    build_red_living_dex_provider_recipe_for_action_free_root,
)


@lru_cache(maxsize=1)
def _red_fixture() -> tuple[
    tuple[RedLivingDexActionFreeRootObservation, ...],
    tuple[RedLivingDexCausalRootCapability, ...],
]:
    plan = build_red_living_dex_prospective_capture_plan()
    roots = tuple(
        replace(
            root,
            cluster_partition="train" if index < 4 else "development",
        )
        for index, root in enumerate(_roots()[:6])
    )
    capabilities: list[RedLivingDexCausalRootCapability] = []
    for root in roots:
        for ordinal, slot in enumerate(plan.slots):
            partition = (
                "train" if slot.partition is LivingDexCapturePartition.TRAIN else "development"
            )
            if root.cluster_partition != partition:
                continue
            capabilities.append(
                RedLivingDexCausalRootCapability(
                    root=root,
                    template_ordinal=ordinal,
                    slot=slot,
                    recipe=build_red_living_dex_provider_recipe_for_action_free_root(
                        slot,
                        root,
                        world=_RouteWorld(),
                        corridors=_corridors(),
                    ),
                )
            )
    return roots, tuple(capabilities)


def test_red_adapter_preserves_partition_and_projects_only_digest_capacity() -> None:
    roots, capabilities = _red_fixture()
    adapted = adapt_red_living_dex_clustered_powered_capacity(
        roots,
        capabilities,
    )

    assert len(adapted) == 6
    assert [item.partition for item in adapted].count("train") == 4
    assert [item.partition for item in adapted].count("development") == 2
    assert all(item.scenarios for item in adapted)
    assert all(item.same_reset_policy_forks_feasible for item in adapted)
    assert all(len(item.pressure_vector) == 7 for item in adapted)
    assert all(len(item.scenarios) == (10 if item.partition == "train" else 5) for item in adapted)


def test_small_red_inventory_fails_before_gameplay_and_never_claims_capacity() -> None:
    roots, capabilities = _red_fixture()
    audit = audit_red_living_dex_clustered_powered_capacity(
        roots,
        capabilities,
    )
    public = audit.public_dict()

    assert audit.capacity_proven is False
    assert audit.train_lineage_deficit == 32
    assert audit.development_lineage_deficit == 98
    assert audit.contingency_lineage_deficit == 3
    assert public["collection_authorized"] is False
    assert public["controller_actions"] == 0
    assert public["emulator_frames"] == 0
    assert public["outcomes"] == 0
    assert public["root_claims"] == 0
