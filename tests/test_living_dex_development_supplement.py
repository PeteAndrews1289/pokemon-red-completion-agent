from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementCapability,
    LivingDexDevelopmentSupplementError,
    LivingDexDevelopmentSupplementPlan,
    LivingDexDevelopmentSupplementPolicy,
    select_living_dex_development_supplement,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _kinds(*items: LivingDexOptionKind) -> tuple[LivingDexOptionKind, ...]:
    order = {kind: index for index, kind in enumerate(LivingDexOptionKind)}
    return tuple(sorted(items, key=order.__getitem__))


def _capability(
    ordinal: int,
    *kinds: LivingDexOptionKind,
) -> LivingDexDevelopmentSupplementCapability:
    return LivingDexDevelopmentSupplementCapability(
        lineage_sha256=_sha(("lineage", ordinal)),
        physical_root_sha256=_sha(("root", ordinal)),
        scenario_sha256=_sha(("scenario", ordinal)),
        family_scope_id=f"family-{ordinal}",
        location_scope_id=f"location-{ordinal}",
        available_option_kinds=_kinds(*kinds),
    )


def _policy() -> LivingDexDevelopmentSupplementPolicy:
    return LivingDexDevelopmentSupplementPolicy(
        new_roots=3,
        minimum_surviving_roots=2,
        minimum_new_families=3,
        minimum_new_locations=3,
        held_root_count=2,
        required_total_roots=4,
        held_option_kinds=_kinds(
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.EVOLVE,
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.RESUPPLY,
            LivingDexOptionKind.UNLOCK_ACCESS,
            LivingDexOptionKind.EXPLORE,
        ),
        required_option_kinds=RED_DIRECT_CAUSAL_OPTION_KINDS,
    )


def _sufficient_capabilities(
) -> tuple[LivingDexDevelopmentSupplementCapability, ...]:
    return (
        _capability(
            0,
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.MANAGE_STORAGE,
        ),
        _capability(
            1,
            LivingDexOptionKind.EVOLVE,
            LivingDexOptionKind.MANAGE_STORAGE,
        ),
        _capability(
            2,
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.EXPLORE,
        ),
        _capability(
            3,
            LivingDexOptionKind.RESUPPLY,
            LivingDexOptionKind.UNLOCK_ACCESS,
        ),
    )


def test_selection_is_minimal_deterministic_and_censor_safe() -> None:
    capabilities = _sufficient_capabilities()

    first = select_living_dex_development_supplement(
        capabilities,
        policy=_policy(),
    )
    second = select_living_dex_development_supplement(
        tuple(reversed(capabilities)),
        policy=_policy(),
    )

    assert first == second
    assert len(first.assignments) == 3
    assert first.policy.maximum_setup_censors == 1
    assert first.policy.missing_option_kinds == (
        LivingDexOptionKind.MANAGE_STORAGE,
    )
    assert sum(
        LivingDexOptionKind.MANAGE_STORAGE in item.available_option_kinds
        for item in first.assignments
    ) >= 2
    assert first.public_dict()["coverage_survives_any_allowed_censor"] is True


def test_selection_excludes_train_and_held_identities_before_search() -> None:
    capabilities = (
        *_sufficient_capabilities(),
        _capability(
            4,
            LivingDexOptionKind.MANAGE_STORAGE,
            LivingDexOptionKind.EXPLORE,
        ),
    )
    excluded = capabilities[0]

    plan = select_living_dex_development_supplement(
        capabilities,
        policy=_policy(),
        excluded_lineages=frozenset({excluded.lineage_sha256}),
        excluded_physical_roots=frozenset({excluded.physical_root_sha256}),
    )

    assert excluded not in plan.assignments
    assert all(
        item.lineage_sha256 != excluded.lineage_sha256
        and item.physical_root_sha256 != excluded.physical_root_sha256
        for item in plan.assignments
    )


def test_selection_rejects_coverage_that_one_setup_censor_can_remove() -> None:
    capabilities = (
        _capability(0, LivingDexOptionKind.MANAGE_STORAGE, LivingDexOptionKind.ACQUIRE),
        _capability(1, LivingDexOptionKind.EVOLVE, LivingDexOptionKind.DEVELOP),
        _capability(2, LivingDexOptionKind.RESUPPLY, LivingDexOptionKind.EXPLORE),
        _capability(3, LivingDexOptionKind.UNLOCK_ACCESS, LivingDexOptionKind.ACQUIRE),
    )

    with pytest.raises(
        LivingDexDevelopmentSupplementError,
        match="capacity is insufficient",
    ):
        select_living_dex_development_supplement(
            capabilities,
            policy=_policy(),
        )


def test_plan_rejects_duplicate_lineage_or_noncanonical_order() -> None:
    plan = select_living_dex_development_supplement(
        _sufficient_capabilities(),
        policy=_policy(),
    )
    duplicate = replace(
        plan.assignments[1],
        lineage_sha256=plan.assignments[0].lineage_sha256,
    )
    with pytest.raises(
        LivingDexDevelopmentSupplementError,
        match="coverage differs",
    ):
        LivingDexDevelopmentSupplementPlan(
            plan.policy,
            (plan.assignments[0], duplicate, plan.assignments[2]),
        )

    with pytest.raises(
        LivingDexDevelopmentSupplementError,
        match="order differs",
    ):
        LivingDexDevelopmentSupplementPlan(
            plan.policy,
            tuple(reversed(plan.assignments)),
        )


def test_public_plan_contains_no_private_identity() -> None:
    plan = select_living_dex_development_supplement(
        _sufficient_capabilities(),
        policy=_policy(),
    )
    encoded = str(plan.public_dict())

    assert plan.public_dict()["private_identity_fields"] == 0
    assert plan.public_dict()["outcomes_opened"] == 0
    assert plan.public_dict()["model_predictions"] == 0
    assert all(
        item.lineage_sha256 not in encoded
        and item.physical_root_sha256 not in encoded
        and item.scenario_sha256 not in encoded
        for item in plan.assignments
    )


def test_policy_rejects_impossible_root_arithmetic() -> None:
    with pytest.raises(
        LivingDexDevelopmentSupplementError,
        match="arithmetically impossible",
    ):
        replace(_policy(), minimum_surviving_roots=1)
