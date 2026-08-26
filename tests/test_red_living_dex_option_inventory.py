from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from test_red_living_dex_option_adapter import _budgets, _facts, _snapshot
from test_red_living_dex_option_materializer import _adapted, _make_store

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_goal_context_profile import (
    RED_GOAL_MANAGER_CONFIG,
    RedGoalContextProfile,
    RedGoalMechanic,
    RedGoalProviderSpec,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexActionFreeInventory,
    RedLivingDexActionFreeInventoryError,
    RedLivingDexInventoryObserverBinding,
    build_verified_red_living_dex_goal_scenario,
    freeze_red_living_dex_action_free_inventory,
    red_living_dex_goal_family_ref,
)
from pokemon_red_completion.red_living_dex_option_materializer import (
    RedLivingDexMaterializationScenario,
    RedLivingDexOptionMaterializerError,
    bind_verified_red_living_dex_materialization_scenario,
    red_living_dex_verified_capture_scenario_identity,
    run_red_living_dex_materialization_plan,
)

_MAPPED_KINDS = (
    GoalKind.ADVANCE_STORY,
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.DEVELOP_TEAM,
    GoalKind.EVOLVE_SPECIES,
)
_MECHANICS = {
    GoalKind.ADVANCE_STORY: RedGoalMechanic.MIDGAME_STORY,
    GoalKind.ACQUIRE_SPECIES: RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
    GoalKind.DEVELOP_TEAM: RedGoalMechanic.BALANCED_TEAM,
    GoalKind.EVOLVE_SPECIES: RedGoalMechanic.DIGLETT_EVOLUTION,
}
_OPTION_KINDS = (
    LivingDexOptionKind.ACQUIRE,
    LivingDexOptionKind.EVOLVE,
    LivingDexOptionKind.DEVELOP,
    LivingDexOptionKind.MANAGE_STORAGE,
    LivingDexOptionKind.ACQUIRE,
    LivingDexOptionKind.EVOLVE,
    LivingDexOptionKind.DEVELOP,
    LivingDexOptionKind.MANAGE_STORAGE,
)


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _capture(index: int) -> GoalManagerContextCapture:
    state = f"verified-red-inventory-{index}".encode("ascii")
    capture_id = f"red-inventory-{index:03d}"
    envelope = _canonical_line(
        {
            "checkpoint_id": capture_id,
            "checkpoint_label": f"Red inventory {index}",
            "checkpoints_completed": 4,
            "checkpoints_total": 36,
            "schema": "pokemon-private-captured-progress-v1",
            "state_sha256": hashlib.sha256(state).hexdigest(),
            "verified_objective_ids": ["power_on"],
        }
    )
    return parse_goal_manager_context_capture(state, envelope)


def _configuration_sha256(
    kind: GoalKind,
    mechanic: RedGoalMechanic,
    parameters: Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _canonical_line(
            {
                "kind": kind.value,
                "mechanic": mechanic.value,
                "parameters": dict(parameters),
            }
        )
    ).hexdigest()


def _profile(capture_id: str, *, salt: str = "a") -> RedGoalContextProfile:
    providers = tuple(
        RedGoalProviderSpec(
            kind,
            _MECHANICS[kind],
            {},
            _configuration_sha256(kind, _MECHANICS[kind], {}),
        )
        for kind in _MAPPED_KINDS
    )
    return RedGoalContextProfile(
        capture_id,
        salt * 64,
        RED_GOAL_MANAGER_CONFIG,
        providers,
    )


def _bindings(profile: RedGoalContextProfile) -> GoalBindingSet:
    available: list[ExecutableGoalBinding] = []
    opportunities: list[GoalOpportunity] = []
    specs = {item.kind: item for item in profile.providers}
    for kind in GoalKind:
        spec = specs.get(kind)
        if spec is None:
            reason = (
                GoalUnavailableReason.MISSING_RESOURCE
                if kind is GoalKind.RESUPPLY
                else GoalUnavailableReason.STORAGE_BLOCKED
                if kind is GoalKind.MANAGE_STORAGE
                else GoalUnavailableReason.MISSING_CAPABILITY
            )
            opportunities.append(
                GoalOpportunity(
                    binding_ref=f"red.goal.{kind.value}.unavailable",
                    kind=kind,
                    availability=GoalAvailability.UNAVAILABLE,
                    unavailable_reason=reason,
                )
            )
            continue
        binding = ExecutableGoalBinding(
            binding_ref=(
                f"pokemon.red:semantic:{kind.value}:"
                f"profile-{profile.profile_sha256}:"
                f"config-{spec.configuration_sha256}"
            ),
            kind=kind,
            estimated_effort=0.2 + 0.05 * len(available),
            estimated_risk=0.1,
            execute=lambda: GoalExecutionReport(10, 100, {"bounded": True}),
            verify=lambda _report: GoalVerification.succeeded(),
        )
        available.append(binding)
        opportunities.append(binding.opportunity)
    return GoalBindingSet(tuple(opportunities), tuple(available))


def _verified_scenario(
    index: int,
    *,
    partition: str,
    kind: LivingDexOptionKind,
    family: str,
    location: str,
) -> RedLivingDexMaterializationScenario:
    capture = _capture(index)
    identity = red_living_dex_verified_capture_scenario_identity(capture)
    adapted = _adapted(
        index,
        kind=kind,
        family=family,
        location=location,
        execute_calls=[],
        scenario_identity_sha256=identity,
    )
    return bind_verified_red_living_dex_materialization_scenario(
        capture,
        adapted,
        partition=partition,
        observer_binding_sha256=f"{70_000 + index:064x}",
        checkpoint_attestation_sha256=f"{80_000 + index:064x}",
        observe_after=RedLivingDexInventoryObserverBinding(
            f"{70_000 + index:064x}"
        ),
    )


def _inventory_scenarios() -> tuple[RedLivingDexMaterializationScenario, ...]:
    train = tuple(
        _verified_scenario(
            index,
            partition="train",
            kind=kind,
            family=f"train-{index % 3}",
            location=f"train-{index % 2}",
        )
        for index, kind in enumerate(_OPTION_KINDS)
    )
    development = tuple(
        _verified_scenario(
            100 + index,
            partition="development",
            kind=(
                LivingDexOptionKind.ACQUIRE
                if index % 2 == 0
                else LivingDexOptionKind.EVOLVE
            ),
            family=f"development-{index}",
            location=f"development-{index}",
        )
        for index in range(4)
    )
    return (*train, *development)


def test_goal_scenario_projects_complete_authenticated_menu_without_selecting() -> None:
    capture = _capture(500)
    profile = _profile(capture.capture_id)
    bindings = _bindings(profile)
    identity = red_living_dex_verified_capture_scenario_identity(capture)
    before = _snapshot(
        scenario=identity,
        actions=0,
        frames=0,
        resource_pool_units=(("red.resource.capture-items", 10),),
    )
    calls: list[str] = []
    scenario = build_verified_red_living_dex_goal_scenario(
        capture,
        profile,
        before,
        _facts(),
        _budgets(),
        bindings,
        partition="train",
        location_ref="red.location.40",
        checkpoint_attestation_sha256="b" * 64,
        observer_binding_sha256="c" * 64,
        observe_after=lambda: calls.append("observe") or before,
    )

    public = scenario.public_dict()
    assert public["candidate_count"] == len(LivingDexOptionKind)
    assert public["available_candidate_count"] == 4
    assert public["all_available_executors_authenticated"] is True
    assert public["verified_repeatable_capture"] is True
    assert scenario.adapted.menu.policy_sha256
    assert all(not option.consumed for option in scenario.adapted.ordered_options)
    assert calls == []
    encoded = json.dumps(scenario.adapted.public_dict(), sort_keys=True).lower()
    assert capture.capture_id not in encoded
    assert "pokemon.red:semantic" not in encoded


def test_goal_family_removes_profile_and_configuration_identity() -> None:
    first_profile = _profile("red-family-first", salt="a")
    second_profile = _profile("red-family-second", salt="b")
    first = next(
        item
        for item in _bindings(first_profile).bindings
        if item.kind is GoalKind.ACQUIRE_SPECIES
    )
    second = next(
        item
        for item in _bindings(second_profile).bindings
        if item.kind is GoalKind.ACQUIRE_SPECIES
    )

    assert red_living_dex_goal_family_ref(
        first, first_profile
    ) == red_living_dex_goal_family_ref(second, second_profile)
    with pytest.raises(
        RedLivingDexActionFreeInventoryError,
        match="authenticated profile",
    ):
        red_living_dex_goal_family_ref(first, second_profile)


def test_action_free_inventory_freezes_same_exact_plan_in_any_input_order() -> None:
    scenarios = _inventory_scenarios()
    first_inventory, first = freeze_red_living_dex_action_free_inventory(scenarios)
    second_inventory, second = freeze_red_living_dex_action_free_inventory(
        tuple(reversed(scenarios))
    )

    assert first.plan_sha256 == second.plan_sha256
    assert len(first.scenarios) == 12
    assert first.public_dict()["partition_counts"] == {
        "development": 4,
        "train": 8,
    }
    assert first.public_dict()["train_offered_option_kind_count"] == 4
    assert first.public_dict()["family_overlap"] == 0
    assert first.public_dict()["location_overlap"] == 0
    assert first.verified_capture_plan is True
    assert first_inventory.public_dict() == second_inventory.public_dict()
    assert first_inventory.public_dict()["behavior_draws"] == 0
    assert first_inventory.public_dict()["controller_actions"] == 0
    assert first_inventory.public_dict()["observer_descriptors_frozen"] == 12
    assert first_inventory.public_dict()["observer_execution_bindings"] == 0
    assert first_inventory.public_dict()["outcomes_observed"] == 0
    assert all(
        not option.consumed
        for scenario in scenarios
        for option in scenario.adapted.ordered_options
    )


def test_inventory_plan_cannot_open_collection_without_reconstructed_observers(
    tmp_path: Path,
) -> None:
    _root, store = _make_store(tmp_path)
    _inventory, plan = freeze_red_living_dex_action_free_inventory(
        _inventory_scenarios()
    )

    with pytest.raises(
        RedLivingDexOptionMaterializerError,
        match="inventory-only observer",
    ):
        run_red_living_dex_materialization_plan(store, plan)

    assert all(
        store.inspect_episode_state(f"redldx-{scenario.scenario_identity_sha256}").status
        == "absent"
        for scenario in plan.scenarios
    )


def test_inventory_rejects_live_observer_authority() -> None:
    scenarios = _inventory_scenarios()
    object.__setattr__(
        scenarios[0],
        "observe_after",
        lambda: _snapshot(scenario=scenarios[0].scenario_identity_sha256),
    )

    with pytest.raises(
        RedLivingDexActionFreeInventoryError,
        match="live observer authority",
    ):
        RedLivingDexActionFreeInventory(scenarios)


def test_inventory_rejects_synthetic_or_duplicate_capture_provenance() -> None:
    scenarios = _inventory_scenarios()
    synthetic = replace(scenarios[0], adapted=scenarios[0].adapted)
    object.__setattr__(
        synthetic,
        "scenario_origin",
        scenarios[0].scenario_origin.SYNTHETIC_REHEARSAL,
    )
    object.__setattr__(synthetic, "checkpoint_binding_sha256", None)
    object.__setattr__(synthetic, "checkpoint_attestation_sha256", None)
    with pytest.raises(RedLivingDexActionFreeInventoryError, match="synthetic"):
        RedLivingDexActionFreeInventory((synthetic, *scenarios[1:]))
    with pytest.raises(RedLivingDexActionFreeInventoryError, match="scenario identity"):
        RedLivingDexActionFreeInventory((*scenarios, scenarios[0]))

    distinct_duplicate_root = _inventory_scenarios()
    object.__setattr__(
        distinct_duplicate_root[1],
        "checkpoint_binding_sha256",
        distinct_duplicate_root[0].checkpoint_binding_sha256,
    )
    with pytest.raises(RedLivingDexActionFreeInventoryError, match="physical capture"):
        RedLivingDexActionFreeInventory(distinct_duplicate_root)


def test_inventory_rejects_nonrepeatable_or_consumed_contexts() -> None:
    nonrepeatable = _inventory_scenarios()
    object.__setattr__(nonrepeatable[0].adapted.before, "scenario_repeatable", False)
    with pytest.raises(RedLivingDexActionFreeInventoryError, match="nonrepeatable"):
        RedLivingDexActionFreeInventory(nonrepeatable)

    consumed = _inventory_scenarios()
    object.__setattr__(consumed[0].adapted.ordered_options[0], "_consumed", True)
    with pytest.raises(RedLivingDexActionFreeInventoryError, match="consumed"):
        RedLivingDexActionFreeInventory(consumed)


@pytest.mark.parametrize(
    ("binding", "inventory_only"),
    (("A" * 64, True), ("a" * 63, True), ("a" * 64, False)),
)
def test_inventory_observer_descriptor_rejects_identity_or_authority_mutation(
    binding: str,
    inventory_only: bool,
) -> None:
    with pytest.raises(RedLivingDexActionFreeInventoryError):
        RedLivingDexInventoryObserverBinding(binding, inventory_only)


@pytest.mark.parametrize(
    "mutation",
    ("short_train", "short_development", "location_overlap", "family_overlap"),
)
def test_inventory_fails_closed_instead_of_weakening_coverage(mutation: str) -> None:
    scenarios = list(_inventory_scenarios())
    if mutation == "short_train":
        scenarios.pop(0)
    elif mutation == "short_development":
        scenarios.pop()
    elif mutation == "location_overlap":
        for scenario in scenarios:
            if scenario.partition == "development":
                for option in scenario.adapted.ordered_options:
                    object.__setattr__(option, "location_ref", "shared-development-location")
    else:
        train_family = scenarios[0].adapted.ordered_options[
            scenarios[0].adapted.menu.available_indices[0]
        ].family_ref
        for scenario in scenarios:
            if scenario.partition == "development":
                for option in scenario.adapted.ordered_options:
                    object.__setattr__(option, "family_ref", train_family)

    with pytest.raises(RedLivingDexActionFreeInventoryError, match="action-free inventory"):
        freeze_red_living_dex_action_free_inventory(scenarios)
