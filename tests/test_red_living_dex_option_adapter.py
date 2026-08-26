from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import replace

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_NORMALIZATION,
    LivingDexOptionAvailability,
    LivingDexOptionKind,
    LivingDexOptionUnavailableReason,
)
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    BoundRedCapability,
    build_red_dual_capability_scenario,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    ProspectiveRedCapabilityBinding,
    RedDependencyCapabilityRole,
    RedDependencySpeciesBinding,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedBoundLivingDexOption,
    RedLivingDexAdaptedScenario,
    RedLivingDexContextFacts,
    RedLivingDexExecutorOrigin,
    RedLivingDexOptionAdapterError,
    RedLivingDexOptionProspect,
    RedLivingDexOutcomeSnapshot,
    RedLivingDexScenarioBudgets,
    adapt_red_living_dex_options,
    bind_red_dual_capability_option,
    bind_red_goal_option,
)

SCENARIO = "1" * 64
ORDERING = "2" * 64
PROBABILITY = "3" * 64
DRAW = "4" * 64
TARGETS = RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species


def _observation(species: tuple[str, ...] = (TARGETS[0],)) -> CollectionObservation:
    specimens = tuple(
        LivingSpecimen(
            species_ref,
            12,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=index,
        )
        for index, species_ref in enumerate(species)
    )
    return CollectionObservation(
        owned_species=frozenset(species),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(len(specimens), 0),
        current_box_index=0,
        box_capacity=20,
    )


def _snapshot(
    *,
    species: tuple[str, ...] = (TARGETS[0],),
    scenario: str = SCENARIO,
    dependencies: int = 2,
    consumables: int = 10,
    health: int = 80,
    irreversible: int = 4,
    actions: int = 100,
    frames: int = 1_000,
    provenance: str = "5" * 64,
    resource_pool_units: tuple[tuple[str, int], ...] | None = None,
) -> RedLivingDexOutcomeSnapshot:
    pools = (
        (("private.resource.capture", consumables),)
        if resource_pool_units is None
        else resource_pool_units
    )
    return RedLivingDexOutcomeSnapshot(
        scenario,
        True,
        _observation(species),
        dependencies,
        consumables,
        pools,
        health,
        100,
        irreversible,
        actions,
        frames,
        provenance,
    )


def _facts() -> RedLivingDexContextFacts:
    return RedLivingDexContextFacts(
        incomplete_dependency_frontier=10,
        blocked_immediate_successors=4,
        access_blocked_targets=5,
        lower_bound_consumable_requirement=20,
        party_readiness_requirement=10,
        current_party_readiness=6,
        unresolved_dependencies=2,
    )


def _budgets() -> RedLivingDexScenarioBudgets:
    return RedLivingDexScenarioBudgets(1_000, 10_000)


def _prospects() -> tuple[RedLivingDexOptionProspect, ...]:
    return (
        RedLivingDexOptionProspect(
            LivingDexOptionKind.ACQUIRE,
            1,
            1,
            2,
            200,
            100,
            2,
            1,
            0.1,
            0,
            4,
            0.9,
        ),
        RedLivingDexOptionProspect(
            LivingDexOptionKind.EVOLVE,
            1,
            1,
            1,
            50,
            250,
            0,
            0,
            0.3,
            1,
            4,
            0.8,
        ),
        RedLivingDexOptionProspect(
            LivingDexOptionKind.MANAGE_STORAGE,
            0,
            1,
            0,
            20,
            80,
            0,
            -5,
            0.0,
            0,
            4,
            1.0,
        ),
        RedLivingDexOptionProspect(
            LivingDexOptionKind.TRADE,
            1,
            1,
            1,
            100,
            200,
            0,
            0,
            0.1,
            1,
            4,
            0.8,
            invariant_safe=False,
        ),
    )


def _options(
    *,
    prefix: str = "private.red",
    execute_calls: list[int] | None = None,
    verify_calls: list[int] | None = None,
    prospects: tuple[RedLivingDexOptionProspect, ...] | None = None,
) -> tuple[RedBoundLivingDexOption, ...]:
    rows = _prospects() if prospects is None else prospects
    result = []
    for index, prospect in enumerate(rows):

        def execute(bound_index: int = index) -> object:
            if execute_calls is not None:
                execute_calls.append(bound_index)
            return {"untrusted": "executor return is not an outcome"}

        def verify(
            before: object,
            after: object,
            bound_index: int = index,
        ) -> bool:
            del before, after
            if verify_calls is not None:
                verify_calls.append(bound_index)
            return True

        result.append(
            RedBoundLivingDexOption(
                f"{prefix}.binding.{index}",
                f"{prefix}.family.{index // 2}",
                f"{prefix}.location.{index}",
                (
                    "private.resource.capture"
                    if prospect.required_consumable_units > 0
                    else None
                ),
                prospect,
                execute,
                verify,
            )
        )
    return tuple(result)


def _adapt(
    options: tuple[RedBoundLivingDexOption, ...] | None = None,
    *,
    ordering: str = ORDERING,
) -> object:
    return adapt_red_living_dex_options(
        _snapshot(),
        _facts(),
        _budgets(),
        _options() if options is None else options,
        ordering_seed_sha256=ordering,
    )


def test_red_adapter_derives_exact_provenance_and_leaks_no_private_identity() -> None:
    red = _adapt(_options(prefix="private.red.species-map-item"))
    crystal_shaped = _adapt(_options(prefix="private.crystal.other-species-map"))

    assert red.menu.policy_dict() == crystal_shaped.menu.policy_dict()  # type: ignore[attr-defined]
    assert red.menu.policy_sha256 == crystal_shaped.menu.policy_sha256  # type: ignore[attr-defined]
    assert len(red.menu.available_indices) == 3  # type: ignore[attr-defined]
    provenance = red.provenance  # type: ignore[attr-defined]
    assert provenance.living_target_count == len(TARGETS)
    assert provenance.retained_living_species_count == 1
    assert provenance.missing_living_species_count == len(TARGETS) - 1
    assert provenance.usable_storage_capacity == 46
    assert provenance.usable_storage_headroom == 45
    assert provenance.public_dict()["normalization"] == LIVING_DEX_OPTION_NORMALIZATION
    context = red.menu.context  # type: ignore[attr-defined]
    assert context.collection_pressure == pytest.approx((len(TARGETS) - 1) / len(TARGETS))
    assert context.dependency_pressure == pytest.approx(0.4)
    assert context.access_pressure == pytest.approx(5 / (len(TARGETS) - 1))
    assert context.resource_pressure == pytest.approx(0.5)
    assert context.storage_pressure == pytest.approx(1 / 46)
    assert context.party_pressure == pytest.approx(0.4)
    assert context.knowledge_pressure == pytest.approx(0.2)

    public = json.dumps(red.public_dict(), sort_keys=True).lower()  # type: ignore[attr-defined]
    for forbidden in (
        "private.red",
        "species-map-item",
        "binding_ref",
        "family_ref",
        "location_ref",
        SCENARIO,
    ):
        assert forbidden not in public


def test_menu_order_is_replayable_and_seeded_without_binding_identity() -> None:
    first = _adapt(_options(prefix="red.secret"), ordering="6" * 64)
    replay = _adapt(_options(prefix="red.secret"), ordering="6" * 64)
    other_title = _adapt(_options(prefix="crystal.secret"), ordering="6" * 64)

    assert [item.prospect.kind for item in first.ordered_options] == [  # type: ignore[attr-defined]
        item.prospect.kind for item in replay.ordered_options  # type: ignore[attr-defined]
    ]
    assert first.menu.policy_dict() == other_title.menu.policy_dict()  # type: ignore[attr-defined]

    original = [item.prospect.kind for item in first.ordered_options]  # type: ignore[attr-defined]
    changed = False
    for value in range(7, 30):
        candidate = _adapt(_options(), ordering=f"{value:064x}")
        if [item.prospect.kind for item in candidate.ordered_options] != original:  # type: ignore[attr-defined]
            changed = True
            break
    assert changed


def test_adapter_derives_invariant_resource_storage_and_unknown_hard_masks() -> None:
    prospects = (
        *_prospects()[:3],
        _prospects()[3],
        RedLivingDexOptionProspect(
            LivingDexOptionKind.RESUPPLY,
            0,
            1,
            0,
            10,
            20,
            11,
            0,
            0.0,
            0,
            4,
            1.0,
        ),
        RedLivingDexOptionProspect(
            LivingDexOptionKind.ACQUIRE,
            1,
            1,
            0,
            10,
            20,
            0,
            46,
            0.0,
            0,
            4,
            1.0,
        ),
        RedLivingDexOptionProspect(
            LivingDexOptionKind.EXPLORE,
            0,
            1,
            1,
            50,
            50,
            0,
            0,
            0.1,
            0,
            4,
            0.0,
            mechanical_blocker=LivingDexOptionUnavailableReason.WORLD_STATE_UNKNOWN,
        ),
    )
    adapted = _adapt(_options(prospects=prospects))
    reasons = {
        candidate.unavailable_reason
        for candidate in adapted.menu.candidates  # type: ignore[attr-defined]
        if candidate.availability is not LivingDexOptionAvailability.AVAILABLE
    }

    assert reasons == {
        LivingDexOptionUnavailableReason.INVARIANT_VIOLATION,
        LivingDexOptionUnavailableReason.MISSING_RESOURCE,
        LivingDexOptionUnavailableReason.STORAGE_BLOCKED,
        LivingDexOptionUnavailableReason.WORLD_STATE_UNKNOWN,
    }
    unknown = next(
        candidate
        for candidate in adapted.menu.candidates  # type: ignore[attr-defined]
        if candidate.unavailable_reason
        is LivingDexOptionUnavailableReason.WORLD_STATE_UNKNOWN
    )
    assert unknown.availability is LivingDexOptionAvailability.UNKNOWN


def test_resource_mask_and_ratio_use_the_selected_private_pool_not_aggregate_items() -> None:
    prospects = (
        *_prospects()[:3],
        RedLivingDexOptionProspect(
            LivingDexOptionKind.TRADE,
            1,
            1,
            0,
            20,
            40,
            2,
            0,
            0.0,
            0,
            4,
            1.0,
        ),
    )
    options = list(_options(prospects=prospects))
    options[3] = replace(
        options[3],
        resource_pool_ref="private.resource.rare-item",
    )
    before = _snapshot(
        resource_pool_units=(
            ("private.resource.capture", 10),
            ("private.resource.rare-item", 0),
        )
    )

    adapted = adapt_red_living_dex_options(
        before,
        _facts(),
        _budgets(),
        tuple(options),
        ordering_seed_sha256=ORDERING,
    )
    index = next(
        index
        for index, option in enumerate(adapted.ordered_options)
        if option.binding_ref.endswith(".3")
    )
    candidate = adapted.menu.candidates[index]
    normalization = adapted.normalization_public_dict()["candidate_rows"]

    assert candidate.unavailable_reason is LivingDexOptionUnavailableReason.MISSING_RESOURCE
    assert normalization[index]["resource_cost"] == {  # type: ignore[index]
        "denominator": 0,
        "numerator": 2,
    }


def test_adapter_rejects_fake_or_indistinguishable_calibration_choices() -> None:
    with pytest.raises(RedLivingDexOptionAdapterError, match="at least three"):
        _adapt(_options()[:2])

    duplicate = _prospects()[0]
    with pytest.raises(RedLivingDexOptionAdapterError, match="policy-distinguishable"):
        _adapt(_options(prospects=(duplicate, duplicate, duplicate)))

    mostly_masked = (
        *_prospects()[:2],
        _prospects()[3],
    )
    with pytest.raises(RedLivingDexOptionAdapterError, match="three genuine"):
        _adapt(_options(prospects=mostly_masked))

    nonrepeatable = replace(_snapshot(), scenario_repeatable=False)
    with pytest.raises(RedLivingDexOptionAdapterError, match="explicitly repeatable"):
        adapt_red_living_dex_options(
            nonrepeatable,
            _facts(),
            _budgets(),
            _options(),
            ordering_seed_sha256=ORDERING,
        )


def test_adapter_does_not_call_any_executor_or_outcome_verifier() -> None:
    execute_calls: list[int] = []
    verify_calls: list[int] = []

    adapted = _adapt(
        _options(execute_calls=execute_calls, verify_calls=verify_calls)
    )

    assert adapted.public_dict()["available_candidate_count"] == 3  # type: ignore[attr-defined]
    assert adapted.public_dict()["authenticated_available_candidate_count"] == 0  # type: ignore[attr-defined]
    assert "executor_origin" not in inspect.signature(RedBoundLivingDexOption).parameters
    assert execute_calls == []
    assert verify_calls == []


def test_adapted_scenario_rejects_forged_normalization_provenance() -> None:
    adapted = _adapt()
    forged = replace(
        adapted.provenance,  # type: ignore[attr-defined]
        maximum_controller_actions=999,
    )

    with pytest.raises(RedLivingDexOptionAdapterError, match="binding differs"):
        RedLivingDexAdaptedScenario(
            adapted.before,  # type: ignore[attr-defined]
            adapted.facts,  # type: ignore[attr-defined]
            adapted.budgets,  # type: ignore[attr-defined]
            forged,
            adapted.menu,  # type: ignore[attr-defined]
            adapted.ordered_options,  # type: ignore[attr-defined]
            adapted.ordering_seed_sha256,  # type: ignore[attr-defined]
        )


def test_existing_semantic_acquire_skill_wraps_without_trusting_its_return_value() -> None:
    scenario = red_dual_capability_scenario_specs()[0]
    binding = RedDependencySpeciesBinding(TARGETS[0], TARGETS[1])
    before = _snapshot()
    world_ledger = before.ledger
    acquire_calls = 0
    evolve_calls = 0

    def acquire() -> object:
        nonlocal acquire_calls, world_ledger
        acquire_calls += 1
        world_ledger = DependencySpecimenLedger(((TARGETS[0], 2),))
        return {"forged_success": False}

    def evolve() -> object:
        nonlocal evolve_calls, world_ledger
        evolve_calls += 1
        world_ledger = DependencySpecimenLedger(((TARGETS[1], 1),))
        return {"forged_success": True}

    capabilities = (
        BoundRedCapability(
            ProspectiveRedCapabilityBinding(
                GoalKind.ACQUIRE_SPECIES,
                RedDependencyCapabilityRole.MEASURED_VENUE_CAPTURE,
                "a" * 64,
                "b" * 64,
                True,
            ),
            binding.binding_sha256,
            acquire,
        ),
        BoundRedCapability(
            ProspectiveRedCapabilityBinding(
                GoalKind.EVOLVE_SPECIES,
                RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
                "a" * 64,
                "c" * 64,
                True,
            ),
            binding.binding_sha256,
            evolve,
        ),
    )
    bound = build_red_dual_capability_scenario(
        scenario,
        binding,
        before.ledger,
        capabilities,
    )
    option = bind_red_dual_capability_option(
        bound,
        0,
        before,
        _prospects()[0],
        location_ref="private.semantic.location",
        resource_pool_ref="private.resource.capture",
    )

    option.execute_once()

    assert acquire_calls == 1
    assert evolve_calls == 0
    assert option.authenticated_executor is True
    assert option.executor_origin is RedLivingDexExecutorOrigin.RED_DUAL_CAPABILITY
    assert option.verify_success(before.ledger, world_ledger) is True
    with pytest.raises(RedLivingDexOptionAdapterError, match="already executed"):
        option.execute_once()


def test_existing_red_goal_skill_wraps_with_its_independent_verifier() -> None:
    verifier_calls = 0

    def verify(report: GoalExecutionReport) -> GoalVerification:
        nonlocal verifier_calls
        verifier_calls += 1
        assert report.evidence["bounded"] is True
        return GoalVerification.succeeded()

    binding = ExecutableGoalBinding(
        binding_ref="private.goal.box-switch",
        kind=GoalKind.MANAGE_STORAGE,
        estimated_effort=0.2,
        estimated_risk=0.1,
        execute=lambda: GoalExecutionReport(12, 200, {"bounded": True}),
        verify=verify,
    )
    option = bind_red_goal_option(
        binding,
        _prospects()[2],
        family_ref="private.goal.family.storage",
        location_ref="private.goal.location.pc",
    )

    report = option.execute_once()

    assert isinstance(report, GoalExecutionReport)
    assert option.authenticated_executor is True
    assert option.executor_origin is RedLivingDexExecutorOrigin.RED_GOAL_SKILL
    assert option.verify_success(_snapshot().ledger, _snapshot().ledger) is True
    assert verifier_calls == 1

    with pytest.raises(RedLivingDexOptionAdapterError, match="option kind differ"):
        bind_red_goal_option(
            binding,
            _prospects()[0],
            family_ref="private.goal.family.storage",
            location_ref="private.goal.location.pc",
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda facts: RedLivingDexContextFacts(
            2,
            3,
            facts.access_blocked_targets,
            facts.lower_bound_consumable_requirement,
            facts.party_readiness_requirement,
            facts.current_party_readiness,
            facts.unresolved_dependencies,
        ),
        lambda facts: RedLivingDexContextFacts(
            facts.incomplete_dependency_frontier,
            facts.blocked_immediate_successors,
            len(TARGETS),
            facts.lower_bound_consumable_requirement,
            facts.party_readiness_requirement,
            facts.current_party_readiness,
            facts.unresolved_dependencies,
        ),
    ),
)
def test_impossible_normalization_counts_fail_closed(
    mutate: Callable[[RedLivingDexContextFacts], RedLivingDexContextFacts],
) -> None:
    with pytest.raises(RedLivingDexOptionAdapterError):
        adapt_red_living_dex_options(
            _snapshot(),
            mutate(_facts()),
            _budgets(),
            _options(),
            ordering_seed_sha256=ORDERING,
        )
