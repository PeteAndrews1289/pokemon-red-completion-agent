from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureCurriculumError,
    LivingDexCapturePartition,
    LivingDexProspectiveCapturePlan,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic
from pokemon_red_completion.red_goal_manager import RedStoryGoalBindingProvider
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedEncounterSourceDevelopmentGoalProvider,
    RedMartResupplyGoalProvider,
    RedProgressGoalProvider,
    RedRouteGoalProvider,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_CONCRETE_ROUTED_SETUP_BINDINGS_CAPABILITY,
    RED_DURABLE_SETUP_RUNNER_CAPABILITY,
    RED_LIVING_DEX_CAPTURE_FEASIBILITY_SCHEMA,
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    RED_LIVING_DEX_OBSERVER_CONTRACT_SHA256,
    RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS,
    RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES,
    RED_ROUTED_SEMANTIC_COMPONENTS,
    RED_ROUTED_SEMANTIC_GOAL_CAPABILITY,
    RedLivingDexCapturePlanError,
    RedLivingDexCapturePlanFeasibility,
    RedLivingDexExecutorCapability,
    RedLivingDexExecutorStatus,
    build_red_living_dex_prospective_capture_plan,
    qualify_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    RedFreshGoalDestinationBinder,
    RedSemanticTransportRoute,
    build_red_routed_semantic_goal_composer,
)
from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalComposer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_PUBLIC_PLAN = (
    PROJECT_ROOT / "configs/red-living-dex-prospective-capture-plan-v1.json"
)


def _qualification() -> RedLivingDexCapturePlanFeasibility:
    return qualify_red_living_dex_prospective_capture_plan()


def test_red_plan_freezes_exact_10_plus_5_schedule_and_probability() -> None:
    result = _qualification()
    plan = result.plan

    assert len(plan.partition_slots(LivingDexCapturePartition.TRAIN)) == 10
    assert len(plan.partition_slots(LivingDexCapturePartition.DEVELOPMENT)) == 5
    assert plan.minimum_train_selected_kind_probability == Fraction(2144, 2187)
    assert plan.minimum_train_selected_kind_probability > Fraction(98, 100)
    assert plan.plan_sha256 == (
        "d718c4d615f3ba86a0dc7d17e9f5327df0b6cace6d74f4e7b02d12c964a3b0ee"
    )

    public = plan.public_dict()
    assert public["partition_counts"] == {"development": 5, "train": 10}
    assert public["menu_width_counts"] == {"3": 15}
    assert public["train_family_scope_count"] == 3
    assert public["development_family_scope_count"] == 5
    assert public["development_location_scope_count"] == 5
    assert public["family_scope_overlap"] == 0
    assert public["location_scope_overlap"] == 0


def test_red_plan_uses_every_existing_portable_kind_except_trade() -> None:
    result = _qualification()

    assert result.scheduled_option_kinds == (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.UNLOCK_ACCESS,
        LivingDexOptionKind.EXPLORE,
    )
    assert result.mission_missing_option_kinds == (LivingDexOptionKind.TRADE,)
    assert result.pilot_plan_contract_satisfied is True
    assert result.pilot_execution_ready is False
    assert result.full_mission_ready is False


def test_capability_audit_is_complete_and_bound_to_real_goal_mechanics() -> None:
    assert tuple(item.option_kind for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES) == tuple(
        LivingDexOptionKind
    )
    capabilities = {
        item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES
    }

    assert capabilities[LivingDexOptionKind.ACQUIRE].goal_kind is GoalKind.ACQUIRE_SPECIES
    assert capabilities[LivingDexOptionKind.ACQUIRE].mechanics == (
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
    )
    assert capabilities[LivingDexOptionKind.ACQUIRE].executor_types == (
        RedAreaSurveyGoalProvider,
    )
    assert capabilities[LivingDexOptionKind.EVOLVE].goal_kind is GoalKind.EVOLVE_SPECIES
    assert capabilities[LivingDexOptionKind.EVOLVE].mechanics == (
        RedGoalMechanic.DIGLETT_EVOLUTION,
    )
    assert capabilities[LivingDexOptionKind.EVOLVE].executor_types == (
        RedProgressGoalProvider,
    )
    assert capabilities[LivingDexOptionKind.DEVELOP].mechanics == (
        RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
        RedGoalMechanic.BALANCED_TEAM,
    )
    assert capabilities[LivingDexOptionKind.DEVELOP].executor_types == (
        RedEncounterSourceDevelopmentGoalProvider,
        RedProgressGoalProvider,
    )
    assert capabilities[LivingDexOptionKind.MANAGE_STORAGE].mechanics == (
        RedGoalMechanic.BOX_SWITCH,
    )
    assert capabilities[LivingDexOptionKind.MANAGE_STORAGE].executor_types == (
        RedBoxSwitchGoalProvider,
    )
    assert capabilities[LivingDexOptionKind.RESUPPLY].mechanics == (
        RedGoalMechanic.MART_RESUPPLY,
    )
    assert capabilities[LivingDexOptionKind.RESUPPLY].executor_types == (
        RedMartResupplyGoalProvider,
    )
    assert capabilities[LivingDexOptionKind.UNLOCK_ACCESS].mechanics == (
        RedGoalMechanic.MIDGAME_STORY,
    )
    assert capabilities[LivingDexOptionKind.UNLOCK_ACCESS].executor_types == (
        RedStoryGoalBindingProvider,
    )
    assert capabilities[LivingDexOptionKind.EXPLORE].mechanics == (
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
    )
    assert capabilities[LivingDexOptionKind.EXPLORE].executor_types == (
        RedEncounterDiscoveryGoalProvider,
        RedRouteGoalProvider,
    )
    trade = capabilities[LivingDexOptionKind.TRADE]
    assert trade.status is RedLivingDexExecutorStatus.MISSING
    assert trade.missing_reason == "missing-repeatable-semantic-trade-executor"
    assert trade.goal_kind is None
    assert trade.mechanics == ()


def test_plan_credits_the_routed_seam_but_keeps_concrete_setup_closed() -> None:
    result = _qualification()

    assert result.locally_composable_slot_count == 1
    assert result.routed_slot_count == 14
    assert result.implemented_runtime_capabilities == (
        RED_ROUTED_SEMANTIC_GOAL_CAPABILITY,
    )
    assert result.unresolved_runtime_capabilities == (
        RED_CONCRETE_ROUTED_SETUP_BINDINGS_CAPABILITY,
        RED_DURABLE_SETUP_RUNNER_CAPABILITY,
    )
    assert (
        RoutedSemanticGoalComposer,
        RedSemanticTransportRoute,
        RedFreshGoalDestinationBinder,
        build_red_routed_semantic_goal_composer,
    ) == RED_ROUTED_SEMANTIC_COMPONENTS
    assert (
        result.mission_missing_option_kinds[0].value
        != RED_ROUTED_SEMANTIC_GOAL_CAPABILITY
    )


def test_setup_requests_are_unique_bounded_and_emit_no_learner_effects() -> None:
    plan = build_red_living_dex_prospective_capture_plan()

    assert len({slot.slot_id for slot in plan.slots}) == 15
    assert len({slot.root_slot_id for slot in plan.slots}) == 15
    assert len({slot.setup.setup_plan_sha256 for slot in plan.slots}) == 15
    assert {slot.setup.observer_contract_sha256 for slot in plan.slots} == {
        RED_LIVING_DEX_OBSERVER_CONTRACT_SHA256
    }
    for slot in plan.slots:
        setup = slot.setup
        assert setup.maximum_controller_actions == (
            RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS
        )
        assert setup.maximum_emulator_frames == (
            RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES
        )
        assert setup.claim_before_controller_input is True
        assert setup.retry_after_controller_input is False
        assert setup.capture_before_behavior_draw is True
        assert setup.learner_labels_emitted == 0
        assert setup.learner_behavior_draws == 0
        assert setup.learner_outcomes_observed == 0
        assert setup.learner_teacher_queries == 0


def test_public_feasibility_is_path_free_and_refuses_training_claims() -> None:
    public = _qualification().public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert public["schema"] == RED_LIVING_DEX_CAPTURE_FEASIBILITY_SCHEMA
    assert public["qualification_sha256"] == (
        "48d859dad473fe2018c60d664ac9fe91f470c05b70a419e12494ebae7725f3eb"
    )
    assert public["rom_accesses"] == 0
    assert public["setup_controller_actions"] == 0
    assert public["setup_emulator_frames"] == 0
    assert public["learner_effects"] == 0
    assert public["private_identity_fields"] == 0
    assert public["private_path_fields"] == 0
    assert public["pilot_execution_ready"] is False
    assert public["full_mission_ready"] is False
    for forbidden in (
        ".gb",
        "binding_ref",
        "player_x",
        "player_y",
        "species_ref",
        "state_sha256",
    ):
        assert forbidden not in encoded


def test_removing_one_train_slot_destroys_the_censor_reserve() -> None:
    plan = build_red_living_dex_prospective_capture_plan()

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="pre-registered train reserve",
    ):
        LivingDexProspectiveCapturePlan((*(plan.slots[:9]), *plan.slots[10:]))


def test_one_menu_substitution_destroys_selected_kind_probability() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    slots = list(plan.slots)
    slots[0] = replace(
        slots[0],
        available_option_kinds=slots[1].available_option_kinds,
    )

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="selected-kind coverage probability",
    ):
        LivingDexProspectiveCapturePlan(tuple(slots))


def test_collapsing_a_train_family_scope_fails_after_censoring() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    slots = list(plan.slots)
    for index in (7, 8, 9):
        slots[index] = replace(
            slots[index],
            family_scope_id="train-family-scope-b",
        )

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="selected train family coverage",
    ):
        LivingDexProspectiveCapturePlan(tuple(slots))


def test_development_location_overlap_is_not_a_public_labeling_shortcut() -> None:
    plan = build_red_living_dex_prospective_capture_plan()
    slots = list(plan.slots)
    slots[10] = replace(
        slots[10],
        location_scope_id=slots[0].location_scope_id,
    )

    with pytest.raises(
        LivingDexCaptureCurriculumError,
        match="train and development locations overlap",
    ):
        LivingDexProspectiveCapturePlan(tuple(slots))


def test_scheduling_trade_cannot_hide_the_missing_executor() -> None:
    result = _qualification()
    slots = list(result.plan.slots)
    slots[0] = replace(
        slots[0],
        available_option_kinds=(
            LivingDexOptionKind.TRADE,
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.EXPLORE,
        ),
    )
    plan = LivingDexProspectiveCapturePlan(tuple(slots))

    with pytest.raises(
        RedLivingDexCapturePlanError,
        match="schedules a missing local executor",
    ):
        RedLivingDexCapturePlanFeasibility(
            plan=plan,
            capabilities=result.capabilities,
            implemented_runtime_capabilities=(
                result.implemented_runtime_capabilities
            ),
            unresolved_runtime_capabilities=(
                result.unresolved_runtime_capabilities
            ),
        )


def test_route_composition_blocker_cannot_be_removed_from_a_nonlocal_plan() -> None:
    result = _qualification()

    with pytest.raises(
        RedLivingDexCapturePlanError,
        match="hides implemented routed-goal composition",
    ):
        RedLivingDexCapturePlanFeasibility(
            plan=result.plan,
            capabilities=result.capabilities,
            implemented_runtime_capabilities=(),
            unresolved_runtime_capabilities=(
                result.unresolved_runtime_capabilities
            ),
        )


def test_concrete_setup_blockers_cannot_be_erased_or_marked_implemented() -> None:
    result = _qualification()

    with pytest.raises(
        RedLivingDexCapturePlanError,
        match="hides concrete setup execution blockers",
    ):
        RedLivingDexCapturePlanFeasibility(
            plan=result.plan,
            capabilities=result.capabilities,
            implemented_runtime_capabilities=(
                result.implemented_runtime_capabilities
            ),
            unresolved_runtime_capabilities=(),
        )

    with pytest.raises(
        RedLivingDexCapturePlanError,
        match="status overlaps",
    ):
        RedLivingDexCapturePlanFeasibility(
            plan=result.plan,
            capabilities=result.capabilities,
            implemented_runtime_capabilities=(
                RED_ROUTED_SEMANTIC_GOAL_CAPABILITY,
                RED_CONCRETE_ROUTED_SETUP_BINDINGS_CAPABILITY,
            ),
            unresolved_runtime_capabilities=(
                RED_CONCRETE_ROUTED_SETUP_BINDINGS_CAPABILITY,
                RED_DURABLE_SETUP_RUNNER_CAPABILITY,
            ),
        )


def test_capability_audit_cannot_drop_trade_or_forge_goal_mapping() -> None:
    result = _qualification()
    without_trade = tuple(
        item
        for item in result.capabilities
        if item.option_kind is not LivingDexOptionKind.TRADE
    )
    with pytest.raises(
        RedLivingDexCapturePlanError,
        match="capability audit is incomplete",
    ):
        RedLivingDexCapturePlanFeasibility(
            plan=result.plan,
            capabilities=without_trade,
            implemented_runtime_capabilities=(
                result.implemented_runtime_capabilities
            ),
            unresolved_runtime_capabilities=(
                result.unresolved_runtime_capabilities
            ),
        )

    acquire = result.capabilities[0]
    with pytest.raises(
        RedLivingDexCapturePlanError,
        match="goal mapping differs",
    ):
        RedLivingDexExecutorCapability(
            option_kind=LivingDexOptionKind.ACQUIRE,
            status=RedLivingDexExecutorStatus.IMPLEMENTED_LOCAL_CONTRACT,
            goal_kind=GoalKind.EVOLVE_SPECIES,
            mechanics=acquire.mechanics,
            boundary_scopes=acquire.boundary_scopes,
            executor_types=acquire.executor_types,
        )

    with pytest.raises(
        RedLivingDexCapturePlanError,
        match="executor provenance differs",
    ):
        replace(acquire, executor_types=(RedMartResupplyGoalProvider,))


def test_plan_and_qualification_are_byte_stable_across_rebuilds() -> None:
    first = _qualification()
    second = _qualification()

    assert first.plan.plan_sha256 == second.plan.plan_sha256
    assert first.qualification_sha256 == second.qualification_sha256
    assert first.public_dict() == second.public_dict()


def test_tracked_public_plan_is_exactly_the_derived_rom_free_result() -> None:
    expected = _qualification().public_dict()
    actual = json.loads(FROZEN_PUBLIC_PLAN.read_text(encoding="utf-8"))

    assert actual == expected


def test_public_plan_generator_check_accepts_the_tracked_result() -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/regenerate_red_living_dex_capture_plan.py",
            "--check",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
