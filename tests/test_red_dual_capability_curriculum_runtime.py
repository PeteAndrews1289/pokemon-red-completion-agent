from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field, replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.red_acquisition import RedAreaExecutionError
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    BoundRedCapability,
    RedDualCapabilityRuntimeError,
    RedSemanticVenueCaptureAdapter,
    SemanticCaptureReadiness,
    SemanticVenueAreaExecutor,
    SemanticVenueCaptureExecutionReport,
    SemanticVenueCapturePlan,
    SemanticVenueRouteBinding,
    bind_bounded_evolution_offer,
    build_red_dual_capability_scenario,
    dependency_specimen_ledger,
    run_red_target_capture,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    RedDependencySpeciesBinding,
    RedDualCapabilityCurriculumError,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, plan_route
from pokemon_red_completion.team_training import GrindingArea
from pokemon_red_completion.training_venue import TrainingVenue, WarpSafeVenueWalker

PRECURSOR = "pokemon:national:050"
EVOLVED = "pokemon:national:051"
SOURCE = "wild:DiglettsCave:grass"
VENUE_MAP = int(MapId.DIGLETTS_CAVE)
OTHER_SOURCE_SPECIMENS = (
    "pokemon:national:010",
    "pokemon:national:014",
    "pokemon:national:014",
    "pokemon:national:025",
)
RESET = "a" * 64


def _route_plan() -> RoutePlan:
    transition = MacroTransition((0, 1), (5, 0), "up")
    macro = MacroGraph({1: (MacroEdge(VENUE_MAP, coordinate_transitions=(transition,)),)})
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((0, 1), action="right"),),
                (0, 1): (),
            }
        )
    }
    return plan_route(macro, local, 1, (0, 0), VENUE_MAP)


def _venue(*, map_id: int = VENUE_MAP) -> TrainingVenue:
    return TrainingVenue(
        band=GrindingArea(
            "measured-semantic-venue",
            2,
            6,
            measured_samples=24,
        ),
        map_id=map_id,
        walk_to_grass=lambda _actions, _reader, _emulator: 0,
        heal_and_return=lambda _actions, _reader, _emulator: None,
        is_in_center=lambda _raw: False,
        move_slot=lambda _raw: 0,
    )


def _observation(precursor_count: int, evolved_count: int = 0) -> CollectionObservation:
    species = (
        *(PRECURSOR for _ in range(precursor_count)),
        *(EVOLVED for _ in range(evolved_count)),
        *OTHER_SOURCE_SPECIMENS,
    )
    specimens = tuple(
        LivingSpecimen(
            species_ref,
            10,
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
        box_counts=(len(specimens),),
        current_box_index=0,
        box_capacity=20,
    )


@dataclass
class _World:
    collection: CollectionObservation
    encounters: list[str]
    map_id: int = 1
    at: tuple[int, int] = (0, 0)
    ready: bool = True
    current_encounter: str | None = None
    actions: list[MacroAction] = field(default_factory=list)

    def execute(self, action: object) -> object:
        assert isinstance(action, MacroAction)
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            self.ready = True
            return action
        assert action.kind is MacroActionKind.MOVE
        assert isinstance(action.value, str)
        if self.map_id == 1 and self.at == (0, 0) and action.value == "right":
            self.at = (0, 1)
        elif self.map_id == 1 and self.at == (0, 1) and action.value == "up":
            self.map_id = VENUE_MAP
            self.at = (5, 0)
        elif self.map_id == VENUE_MAP and self.current_encounter is None and self.encounters:
            self.current_encounter = self.encounters.pop(0)
            self.at = (self.at[0] + 1, self.at[1])
        return action

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(
            self.map_id,
            self.at,
            self.ready and self.current_encounter is None,
            interruption=("wild_battle" if self.current_encounter is not None else None),
        )

    def read(self) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=self.map_id,
            player_x=self.at[1],
            player_y=self.at[0],
            party_count=0,
            battle_state=1 if self.current_encounter is not None else 0,
        )

    def read_collection(self) -> CollectionObservation:
        return self.collection

    def encountered_species_ref(self) -> str | None:
        return self.current_encounter

    def seek_encounter(self) -> None:
        raise AssertionError("semantic venue wrapper, not the delegate, must walk")

    def capture_encounter(self, species_ref: str) -> bool:
        assert self.current_encounter == species_ref
        specimens = self.collection.specimens + (
            LivingSpecimen(
                species_ref,
                10,
                CollectionLocation.BOX,
                container_index=0,
                slot_index=len(self.collection.specimens),
            ),
        )
        self.collection = replace(
            self.collection,
            owned_species=self.collection.owned_species.union({species_ref}),
            specimens=specimens,
            box_counts=(self.collection.box_counts[0] + 1,),
        )
        self.current_encounter = None
        return True

    def flee_encounter(self) -> None:
        assert self.current_encounter is not None
        self.current_encounter = None

    def switch_box(self, _box_index: int) -> None:
        raise AssertionError("fixture has immediate storage room")


def _capture_adapter(
    precursor_count: int,
    *,
    encounters: list[str] | None = None,
) -> tuple[RedSemanticVenueCaptureAdapter, _World, DependencySpecimenLedger]:
    world = _World(
        _observation(precursor_count),
        list(encounters or [PRECURSOR]),
    )
    route = SemanticVenueRouteBinding(_route_plan(), "b" * 64)
    plan = SemanticVenueCapturePlan(
        RESET,
        RedDependencySpeciesBinding(PRECURSOR, EVOLVED),
        SOURCE,
        route,
        _venue(),
        maximum_actions=20,
        maximum_encounters=10,
    )
    area = SemanticVenueAreaExecutor(
        delegate=world,
        actions=world,
        reader=world,
        emulator=world,
        walker=WarpSafeVenueWalker(VENUE_MAP, frozenset(), move_wait_frames=1),
    )
    return (
        RedSemanticVenueCaptureAdapter(plan, world, world, area),
        world,
        dependency_specimen_ledger(world.collection),
    )


def _readiness() -> SemanticCaptureReadiness:
    return SemanticCaptureReadiness(RESET, 10, 4, True, False)


def _evolution_offer(executions: list[str]) -> RedGoalBindingOffer:
    def execute() -> GoalExecutionReport:
        executions.append("evolve")
        return GoalExecutionReport(1, 1, {"bounded": True})

    binding = ExecutableGoalBinding(
        binding_ref=(
            "pokemon.red:evolution:diglett-to-dugtrio:"
            f"profile-{'a' * 64}:config-{'b' * 64}"
        ),
        kind=GoalKind.EVOLVE_SPECIES,
        estimated_effort=0.2,
        estimated_risk=0.1,
        execute=execute,
        verify=lambda _report: GoalVerification.succeeded(),
    )
    return RedGoalBindingOffer.available(binding)


def test_route_binding_rejects_direction_scripts_and_public_projection_is_identity_free() -> None:
    with pytest.raises(
        RedDualCapabilityRuntimeError,
        match="direction sequences are forbidden",
    ):
        SemanticVenueRouteBinding(
            _route_plan(),
            "b" * 64,
            profile_direction_steps=2,
        )

    route = SemanticVenueRouteBinding(_route_plan(), "b" * 64)
    plan = SemanticVenueCapturePlan(
        RESET,
        RedDependencySpeciesBinding(PRECURSOR, EVOLVED),
        SOURCE,
        route,
        _venue(),
    )
    public = json.dumps(plan.public_dict(), sort_keys=True).lower()
    signature = str(inspect.signature(SemanticVenueCapturePlan)).lower()

    for forbidden in (
        PRECURSOR,
        EVOLVED,
        SOURCE.lower(),
        '"map_id":',
        "route_plan_sha256",
        "planner_binding_sha256",
        "forward_directions",
    ):
        assert forbidden not in public
    assert "forward_directions" not in signature
    assert plan.skill_binding_sha256 != route.plan_sha256


def test_capture_plan_rejects_wrong_terminal() -> None:
    route = SemanticVenueRouteBinding(_route_plan(), "b" * 64)
    with pytest.raises(
        RedDualCapabilityRuntimeError,
        match="does not terminate",
    ):
        SemanticVenueCapturePlan(
            RESET,
            RedDependencySpeciesBinding(PRECURSOR, EVOLVED),
            SOURCE,
            route,
            _venue(map_id=3),
        )
def test_qualification_is_action_free_and_fails_closed_on_reset_or_resource_drift() -> None:
    adapter, world, before = _capture_adapter(1)
    scenario = red_dual_capability_scenario_specs()[0]

    capability = adapter.qualify(scenario, before, _readiness())

    assert world.actions == []
    assert capability.evidence.kind is GoalKind.ACQUIRE_SPECIES
    assert capability.evidence.reset_state_sha256 == RESET
    assert capability.evidence.mechanically_available is True
    assert set(capability.public_dict()) == {
        "goal_kind",
        "execution_role",
        "mechanically_available",
        "private_identity_fields",
    }
    with pytest.raises(RedDualCapabilityRuntimeError, match="another reset state"):
        adapter.qualify(scenario, before, replace(_readiness(), reset_state_sha256="c" * 64))
    with pytest.raises(RedDualCapabilityRuntimeError, match="resources are not"):
        adapter.qualify(scenario, before, replace(_readiness(), ordinary_capture_items=0))


def test_semantic_route_and_walker_capture_exact_target_then_ledger_supplies_label() -> None:
    adapter, world, before = _capture_adapter(
        1,
        encounters=["pokemon:national:010", PRECURSOR],
    )
    scenario = red_dual_capability_scenario_specs()[0]
    bound = build_red_dual_capability_scenario(
        scenario,
        adapter.plan.species_binding,
        before,
        (
            adapter.qualify(
                scenario,
                before,
                _readiness(),
            ),
            bind_bounded_evolution_offer(
                scenario,
                adapter.plan.species_binding,
                before,
                reset_state_sha256=RESET,
                offer=_evolution_offer([]),
            ),
        ),
    )
    report = bound.bind_selection(0).execute()
    assert isinstance(report, SemanticVenueCaptureExecutionReport)
    outcome = bound.verify_outcome(
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        after_ledger=report.after_ledger,
    )

    assert report.route.passed
    assert report.capture.captures == 1
    assert report.capture.flees == 1
    assert report.capture.after_target_count == 2
    assert report.public_dict()["target_identity_fields"] == 0
    assert outcome.reward == 1
    assert outcome.exact_selected_transition is True
    assert any(action.value == "right" for action in world.actions)
    assert any(action.value == "up" for action in world.actions)


def test_redundant_capture_remains_executable_and_becomes_a_negative_outcome() -> None:
    adapter, _world, before = _capture_adapter(2)
    scenario = red_dual_capability_scenario_specs()[1]

    bound = build_red_dual_capability_scenario(
        scenario,
        adapter.plan.species_binding,
        before,
        (
            adapter.qualify(scenario, before, _readiness()),
            bind_bounded_evolution_offer(
                scenario,
                adapter.plan.species_binding,
                before,
                reset_state_sha256=RESET,
                offer=_evolution_offer([]),
            ),
        ),
    )
    report = bound.bind_selection(0).execute()
    assert isinstance(report, SemanticVenueCaptureExecutionReport)
    outcome = bound.verify_outcome(
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        after_ledger=report.after_ledger,
    )

    assert report.capture.before_target_count == 2
    assert report.capture.after_target_count == 3
    assert outcome.exact_selected_transition is True
    assert outcome.required_living_preserved is True
    assert outcome.reward == -1


def test_builder_requires_two_distinct_same_reset_offers_and_executes_only_selection() -> None:
    adapter, world, before = _capture_adapter(1)
    scenario = red_dual_capability_scenario_specs()[0]
    acquire = adapter.qualify(scenario, before, _readiness())
    evolution_executions: list[str] = []
    evolve = bind_bounded_evolution_offer(
        scenario,
        adapter.plan.species_binding,
        before,
        reset_state_sha256=RESET,
        offer=_evolution_offer(evolution_executions),
    )
    bound = build_red_dual_capability_scenario(
        scenario,
        adapter.plan.species_binding,
        before,
        (acquire, evolve),
    )

    assert bound.policy_rows() == scenario.policy_rows()
    encoded = json.dumps(bound.public_dict(), sort_keys=True).lower()
    for forbidden in (PRECURSOR, EVOLVED, SOURCE.lower(), "map_id", "binding_sha256"):
        assert forbidden not in encoded
    selected = bound.bind_selection(1)
    selected.execute()
    assert evolution_executions == ["evolve"]
    assert world.actions == []
    assert bound.public_dict()["schema"] == (
        "pokemon.red.private-bound-dual-capability-scenario.v1"
    )
    with pytest.raises(RedDualCapabilityRuntimeError, match="already executed"):
        selected.execute()

    with pytest.raises(RedDualCapabilityRuntimeError, match="both capabilities"):
        build_red_dual_capability_scenario(
            scenario,
            adapter.plan.species_binding,
            before,
            (acquire,),
        )
    mismatched = BoundRedCapability(
        replace(evolve.evidence, reset_state_sha256="d" * 64),
        evolve.dependency_binding_sha256,
        evolve.execute,
    )
    with pytest.raises(
        RedDualCapabilityCurriculumError,
        match="both independent capabilities",
    ):
        build_red_dual_capability_scenario(
            scenario,
            adapter.plan.species_binding,
            before,
            (acquire, mismatched),
        )


def test_unavailable_evolution_and_target_capture_bounds_fail_closed() -> None:
    adapter, world, before = _capture_adapter(1, encounters=["pokemon:national:010"])
    scenario = red_dual_capability_scenario_specs()[0]
    with pytest.raises(RedDualCapabilityRuntimeError, match="evolution offer is unavailable"):
        bind_bounded_evolution_offer(
            scenario,
            adapter.plan.species_binding,
            before,
            reset_state_sha256=RESET,
            offer=RedGoalBindingOffer.unavailable(
                GoalKind.EVOLVE_SPECIES,
                GoalUnavailableReason.MISSING_CAPABILITY,
            ),
        )
    with pytest.raises(
        RedDualCapabilityRuntimeError,
        match="does not implement the declared dependency",
    ):
        bind_bounded_evolution_offer(
            scenario,
            RedDependencySpeciesBinding(PRECURSOR, "pokemon:national:052"),
            before,
            reset_state_sha256=RESET,
            offer=_evolution_offer([]),
        )
    valid = _evolution_offer([])
    assert valid.binding is not None
    forged = RedGoalBindingOffer.available(
        ExecutableGoalBinding(
            binding_ref=(
                "pokemon.red:evolution:diglett-to-dugtrio-extra:"
                f"profile-{'a' * 64}:config-{'b' * 64}"
            ),
            kind=valid.binding.kind,
            estimated_effort=valid.binding.estimated_effort,
            estimated_risk=valid.binding.estimated_risk,
            execute=valid.binding.execute,
            verify=valid.binding.verify,
        )
    )
    with pytest.raises(
        RedDualCapabilityRuntimeError,
        match="does not implement the declared dependency",
    ):
        bind_bounded_evolution_offer(
            scenario,
            adapter.plan.species_binding,
            before,
            reset_state_sha256=RESET,
            offer=forged,
        )
    world.map_id = VENUE_MAP
    world.at = (5, 0)
    with pytest.raises(RedAreaExecutionError, match="exhausted"):
        run_red_target_capture(
            SOURCE,
            PRECURSOR,
            adapter.area_executor,
            maximum_actions=2,
            maximum_encounters=1,
        )
