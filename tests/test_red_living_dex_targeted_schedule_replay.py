from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from test_red_living_dex_targeted_schedule_reader import (
    _expectations,
    _payload,
)

from pokemon_red_completion.red_living_dex_targeted_schedule_reader import (
    RedLivingDexTargetedScheduleDescriptor,
    load_red_living_dex_targeted_schedule_descriptor,
)
from pokemon_red_completion.red_living_dex_targeted_schedule_replay import (
    RedLivingDexTargetedScheduleReplayError,
    rebind_red_living_dex_targeted_schedule,
)


def _descriptor():  # type: ignore[no-untyped-def]
    binding, _document, payload = _payload()
    descriptor = load_red_living_dex_targeted_schedule_descriptor(
        payload,
        expected_plan_sha256=hashlib.sha256(payload).hexdigest(),
        expectations=_expectations(),
    )
    return binding, descriptor


def _fresh_edges(binding):  # type: ignore[no-untyped-def]
    unique = {}
    for item in binding.capabilities:
        key = (
            item.root.root.physical_root_sha256,
            item.root.independence_lineage_sha256,
            item.template_ordinal,
        )
        unique[key] = item
    return tuple(unique.values())


def test_targeted_schedule_replays_from_fresh_capability_edges() -> None:
    binding, descriptor = _descriptor()

    replayed = rebind_red_living_dex_targeted_schedule(
        descriptor,
        tuple(reversed(_fresh_edges(binding))),
    )

    assert replayed.private_dict() == binding.private_dict()
    assert replayed.binding_sha256 == descriptor.binding_sha256


def test_targeted_schedule_replay_rejects_missing_or_changed_recipe() -> None:
    binding, descriptor = _descriptor()
    fresh = _fresh_edges(binding)
    with pytest.raises(
        RedLivingDexTargetedScheduleReplayError,
        match="did not replay exactly once",
    ):
        rebind_red_living_dex_targeted_schedule(
            descriptor,
            tuple(
                item
                for item in fresh
                if item is not binding.capabilities[0]
            ),
        )

    changed = replace(
        descriptor.capabilities[0],
        recipe_sha256="9" * 64,
    )
    mutated = RedLivingDexTargetedScheduleDescriptor(
        descriptor.binding_sha256,
        descriptor.schedule,
        (changed, *descriptor.capabilities[1:]),
    )
    with pytest.raises(RedLivingDexTargetedScheduleReplayError):
        rebind_red_living_dex_targeted_schedule(mutated, fresh)


def test_targeted_schedule_replay_rejects_duplicate_matching_edge() -> None:
    binding, descriptor = _descriptor()
    fresh = _fresh_edges(binding)
    duplicate = (binding.capabilities[0], *fresh)

    with pytest.raises(
        RedLivingDexTargetedScheduleReplayError,
        match="exactly once",
    ):
        rebind_red_living_dex_targeted_schedule(descriptor, duplicate)
