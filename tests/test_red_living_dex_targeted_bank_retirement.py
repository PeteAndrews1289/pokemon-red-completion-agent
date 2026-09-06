from __future__ import annotations

from dataclasses import replace

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
)
from pokemon_red_completion.red_living_dex_targeted_bank_retirement import (
    plan_red_living_dex_targeted_bank_retirement,
)


def _capabilities() -> tuple[RedLivingDexCausalRootCapability, ...]:
    slots = build_red_living_dex_prospective_capture_plan().slots
    recipes = _recipes()
    capabilities: list[RedLivingDexCausalRootCapability] = []
    for root_ordinal in range(10):
        root = _setup_root(300 + root_ordinal)
        observation = replace(
            _provider_root(300 + root_ordinal),
            root=root,
            observed_state_sha256=root.state_sha256,
            independence_lineage_sha256=canonical_sha256(
                {"retirement-lineage": root_ordinal}
            ),
            cluster_partition="development",
        )
        for template_ordinal, (slot, recipe) in enumerate(
            zip(slots, recipes, strict=True)
        ):
            capabilities.append(
                RedLivingDexCausalRootCapability(
                    root=observation,
                    template_ordinal=template_ordinal,
                    slot=slot,
                    recipe=replace(
                        recipe,
                        root_consumption_sha256=root.root_consumption_sha256,
                        root_state_sha256=root.state_sha256,
                        root_envelope_sha256=root.envelope_sha256,
                    ),
                )
            )
    return tuple(capabilities)


def test_red_retirement_binds_train_and_development_recipes_without_relabeling_source() -> None:
    result = plan_red_living_dex_targeted_bank_retirement(_capabilities())

    assert len(result.binding.schedule.slots) == 12
    assert len(result.binding.capabilities) == 12
    assert all(
        capability.root.cluster_partition == "development"
        for capability in result.binding.capabilities
    )
    for slot, capability in zip(
        result.binding.schedule.slots,
        result.binding.capabilities,
        strict=True,
    ):
        assert (
            capability.slot.partition is LivingDexCapturePartition.TRAIN
        ) == (slot.partition == "train")
    public = result.public_dict()
    assert public["source_partition_preserved_as_provenance"] is True
    assert public["source_partition_retained_for_evaluation"] is False
    assert public["evaluation_status_forfeited_roots"] == 4
    assert public["paired_development_roots"] == 4
    assert public["reserve_development_roots"] == 2
    assert public["controller_actions"] == 0
    encoded = str(public)
    assert all(
        capability.root.root.physical_root_sha256 not in encoded
        for capability in _capabilities()
    )
