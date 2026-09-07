"""Bridge a target-specific goal offer to Red's existing boxed-evolution engine.

The goal registry chooses a mechanics-derived species transition and binds the
exact current-box/deposit coordinates from a fresh observation.  This adapter
adds the private route and training dependencies, qualifies the already-tested
boxed engine without input, executes it once, and translates its evidence into
the ordinary goal-manager report.  It contains no species-specific route.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.red_boxed_level_evolution import (
    BoundedEvolutionTrainingResult,
    BoxedLevelEvolutionExecutionReport,
    BoxedLevelEvolutionPlan,
    ObservedSemanticBoundaryBinding,
    RedBoxedLevelEvolutionAdapter,
    SemanticPCBoundaryAccess,
)
from pokemon_red_completion.red_collection import (
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    SemanticVenueRouteBinding,
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    RedDependencySpeciesBinding,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    InterruptionHandler,
    RouteExecutionLimits,
    RouteReplanner,
    RouteResourceManager,
    TraversalObserver,
)


class RedGoalBoxedEvolutionError(RuntimeError):
    """A goal binding could not be joined to the boxed mechanics engine."""


class _FrameCounter(Protocol):
    @property
    def frame_count(self) -> int: ...


@dataclass(slots=True)
class RedGoalBoxedEvolutionExecutor:
    """Callable goal executor backed by :class:`RedBoxedLevelEvolutionAdapter`."""

    reset_state_sha256: str
    route_to_pc: SemanticPCBoundaryAccess
    route_to_training: SemanticVenueRouteBinding
    training_binding_sha256: str
    reader: PokemonRedStateReader
    traversal_observer: TraversalObserver
    observe_collection: Callable[[], CollectionObservation]
    train_evolution: Callable[[int, int], BoundedEvolutionTrainingResult]
    emulator: _FrameCounter
    interruption_handler: InterruptionHandler | None = None
    replanner: RouteReplanner | None = None
    resource_manager: RouteResourceManager | None = None
    route_limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS
    pc_facing: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reset_state_sha256, str) or len(self.reset_state_sha256) != 64:
            raise RedGoalBoxedEvolutionError("boxed goal reset identity differs")
        if not isinstance(
            self.route_to_pc,
            (SemanticVenueRouteBinding, ObservedSemanticBoundaryBinding),
        ):
            raise TypeError("boxed goal needs semantic PC access")
        if not isinstance(self.route_to_training, SemanticVenueRouteBinding):
            raise TypeError("boxed goal needs a semantic training route")
        if any(
            not callable(getattr(self.reader, name, None))
            for name in ("read", "read_current_box_state", "read_input_readiness")
        ):
            raise TypeError("boxed goal needs a Red state reader")
        if not callable(self.observe_collection) or not callable(self.train_evolution):
            raise TypeError("boxed goal needs collection and training adapters")
        if type(getattr(self.emulator, "frame_count", None)) is not int:  # noqa: E721
            raise TypeError("boxed goal needs an emulator frame counter")
        if not isinstance(self.route_limits, RouteExecutionLimits):
            raise TypeError("boxed goal route limits differ")

    def __call__(
        self,
        request: RedBoxedLevelEvolutionGoalRequest,
        actions: CountingExecutor,
    ) -> GoalExecutionReport:
        if not isinstance(request, RedBoxedLevelEvolutionGoalRequest):
            raise TypeError("boxed goal executor needs a state-derived request")
        if not isinstance(actions, CountingExecutor):
            raise TypeError("boxed goal executor needs counted controller authority")
        request.__post_init__()
        before_ledger = dependency_specimen_ledger(self.observe_collection())
        source_ref = red_species_ref(
            red_internal_species_number(request.precursor_internal_species_id)
        )
        target_ref = red_species_ref(
            red_internal_species_number(request.evolved_internal_species_id)
        )
        source_count = before_ledger.count(source_ref)
        target_count = before_ledger.count(target_ref)
        scenarios = red_dual_capability_scenario_specs()
        if target_count != 0 or source_count not in {1, 2}:
            raise RedGoalBoxedEvolutionError(
                "boxed goal does not match a supported living dependency multiplicity"
            )
        scenario = scenarios[source_count - 1]
        species_binding = RedDependencySpeciesBinding(source_ref, target_ref)
        plan = BoxedLevelEvolutionPlan(
            reset_state_sha256=self.reset_state_sha256,
            species_binding=species_binding,
            precursor_internal_species_id=request.precursor_internal_species_id,
            evolved_internal_species_id=request.evolved_internal_species_id,
            current_box_index=request.current_box_index,
            precursor_box_slot=request.precursor_box_slot,
            deposit_party_slot=request.deposit_party_slot,
            deposit_internal_species_id=request.deposit_internal_species_id,
            route_to_pc=self.route_to_pc,
            route_to_training=self.route_to_training,
            training_binding_sha256=self.training_binding_sha256,
            pc_facing=self.pc_facing,
        )
        adapter = RedBoxedLevelEvolutionAdapter(
            plan=plan,
            actions=actions,
            reader=self.reader,
            traversal_observer=self.traversal_observer,
            observe_collection=self.observe_collection,
            train_evolution=self.train_evolution,
            interruption_handler=self.interruption_handler,
            replanner=self.replanner,
            resource_manager=self.resource_manager,
            route_limits=self.route_limits,
        )
        action_start = actions.actions_executed
        frame_start = self.emulator.frame_count
        bound = adapter.qualify(scenario, before_ledger)
        if actions.actions_executed != action_start or self.emulator.frame_count != frame_start:
            raise RedGoalBoxedEvolutionError(
                "boxed goal qualification changed controller or frame state"
            )
        execution = bound.execute()
        if not isinstance(execution, BoxedLevelEvolutionExecutionReport):
            raise RedGoalBoxedEvolutionError("boxed goal engine returned no typed evidence")
        evidence = execution.public_dict()
        return GoalExecutionReport(
            actions_executed=actions.actions_executed - action_start,
            frames_executed=self.emulator.frame_count - frame_start,
            evidence=evidence,
        )


__all__ = [
    "RedGoalBoxedEvolutionError",
    "RedGoalBoxedEvolutionExecutor",
]
