"""Generic Red capability for evolving one retained boxed precursor.

The dependency policy chooses *evolve*; this title adapter performs the Red-only
mechanics needed when the chosen precursor is in Bill's PC.  It routes to an
exact PC boundary, deposits one explicitly bound non-escort party member,
withdraws the exact precursor, routes back to a training boundary, invokes one
bounded participation-training executor, and verifies the collection through a
fresh independent observation.

No species family is hard-coded.  Species and storage coordinates are private
bindings, while the public report contains only transition and cost facts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import RedCurrentBoxState
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import (
    red_internal_species_number,
    red_species_number,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    BoundRedCapability,
    SemanticVenueRouteBinding,
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    ProspectiveRedCapabilityBinding,
    RedDependencyCapabilityRole,
    RedDependencySpeciesBinding,
    RedDualCapabilityScenarioSpec,
)
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID
from pokemon_red_completion.red_pc_storage import (
    RedPCDepositReport,
    RedPCWithdrawReport,
    deposit_party_member,
    open_bills_pc,
    withdraw_box_member,
)
from pokemon_red_completion.red_team_training import close_menu
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    InterruptionHandler,
    RouteActionPort,
    RouteExecutionLimits,
    RouteExecutionReport,
    RouteReplanner,
    RouteResourceManager,
    TraversalObserver,
    TraversalSnapshot,
    execute_route,
)

RED_BOXED_LEVEL_EVOLUTION_SCHEMA = "pokemon.red.private-boxed-level-evolution.v1"
RED_BOXED_LEVEL_EVOLUTION_REPORT_SCHEMA = "pokemon.red.boxed-level-evolution-execution-report.v1"
RED_OBSERVED_SEMANTIC_BOUNDARY_SCHEMA = "pokemon.red.private-observed-semantic-boundary.v1"
RED_OBSERVED_SEMANTIC_BOUNDARY_REPORT_SCHEMA = "pokemon.red.observed-semantic-boundary-report.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedBoxedLevelEvolutionError(RuntimeError):
    """The boxed evolution crossed its frozen storage or collection boundary."""


class _CountedActionPort(RouteActionPort, Protocol):
    actions_executed: int


class _RedStorageStateReader(Protocol):
    def read(self) -> object: ...

    def read_current_box_state(self) -> RedCurrentBoxState: ...

    def read_input_readiness(self) -> object: ...


@dataclass(frozen=True, slots=True)
class ObservedSemanticBoundaryBinding:
    """An exact destination already occupied at the authenticated reset.

    This is deliberately not a zero-step route.  It binds the semantic boundary
    to an independent live observation and permits no controller action.  The
    private map, coordinate, and observer identity never enter policy rows or a
    public report.
    """

    map_id: int
    at: tuple[int, int]
    observer_binding_sha256: str
    boundary_source: str = "authenticated_live_observation"

    def __post_init__(self) -> None:
        if type(self.map_id) is not int or self.map_id < 0:  # noqa: E721
            raise RedBoxedLevelEvolutionError("observed semantic boundary map differs")
        if (
            not isinstance(self.at, tuple)
            or len(self.at) != 2
            or any(type(value) is not int or value < 0 for value in self.at)  # noqa: E721
        ):
            raise RedBoxedLevelEvolutionError("observed semantic boundary coordinate differs")
        _require_sha256(
            self.observer_binding_sha256,
            "observed semantic boundary observer",
        )
        if self.boundary_source != "authenticated_live_observation":
            raise RedBoxedLevelEvolutionError("observed semantic boundary source differs")

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": RED_OBSERVED_SEMANTIC_BOUNDARY_SCHEMA,
                "map_id": self.map_id,
                "at": list(self.at),
                "observer_binding_sha256": self.observer_binding_sha256,
                "boundary_source": self.boundary_source,
            }
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_OBSERVED_SEMANTIC_BOUNDARY_SCHEMA,
            "authenticated_live_observation": True,
            "controller_actions": 0,
            "route_steps": 0,
            "map_identity_fields": 0,
            "coordinate_identity_fields": 0,
            "observer_identity_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class ObservedSemanticBoundaryReport:
    """Action-free proof that execution still occupies the frozen boundary."""

    binding: ObservedSemanticBoundaryBinding
    observed: TraversalSnapshot
    controller_actions: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ObservedSemanticBoundaryBinding):
            raise TypeError("observed boundary report needs its binding")
        if not isinstance(self.observed, TraversalSnapshot):
            raise TypeError("observed boundary report needs a traversal snapshot")
        if (
            self.observed.map_id != self.binding.map_id
            or self.observed.at != self.binding.at
            or not self.observed.ready
            or self.observed.interruption is not None
            or type(self.controller_actions) is not int  # noqa: E721
            or self.controller_actions != 0
        ):
            raise RedBoxedLevelEvolutionError(
                "observed semantic boundary does not match the frozen destination"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_OBSERVED_SEMANTIC_BOUNDARY_REPORT_SCHEMA,
            "passed": True,
            "controller_actions": 0,
            "route_steps": 0,
            "map_identity_fields": 0,
            "coordinate_identity_fields": 0,
            "observer_identity_fields": 0,
        }


SemanticPCBoundaryAccess = SemanticVenueRouteBinding | ObservedSemanticBoundaryBinding


@dataclass(frozen=True, slots=True)
class BoundedEvolutionTrainingResult:
    """Exact mechanics cost returned by the injected participation trainer."""

    battles_completed: int
    healing_trips: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0  # noqa: E721
            for value in (self.battles_completed, self.healing_trips)
        ):
            raise RedBoxedLevelEvolutionError("bounded evolution training cost differs")
        if self.battles_completed < 1:
            raise RedBoxedLevelEvolutionError(
                "bounded evolution did not complete a training battle"
            )


@dataclass(frozen=True, slots=True)
class BoxedLevelEvolutionPlan:
    """All private identities frozen before an evolve option can be scored."""

    reset_state_sha256: str
    species_binding: RedDependencySpeciesBinding
    precursor_internal_species_id: int
    evolved_internal_species_id: int
    current_box_index: int
    precursor_box_slot: int
    deposit_party_slot: int
    deposit_internal_species_id: int
    route_to_pc: SemanticPCBoundaryAccess
    route_to_training: SemanticVenueRouteBinding
    training_binding_sha256: str
    pc_facing: str | None = None

    def __post_init__(self) -> None:
        _require_sha256(self.reset_state_sha256, "boxed evolution reset state")
        if self.pc_facing not in {None, "up", "down", "left", "right"}:
            raise RedBoxedLevelEvolutionError("boxed evolution PC facing differs")
        _require_sha256(self.training_binding_sha256, "boxed evolution training binding")
        if not isinstance(self.species_binding, RedDependencySpeciesBinding):
            raise TypeError("boxed evolution needs a species binding")
        for name in (
            "precursor_internal_species_id",
            "evolved_internal_species_id",
            "deposit_internal_species_id",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise RedBoxedLevelEvolutionError(f"{name} differs")
        if red_internal_species_number(self.precursor_internal_species_id) != red_species_number(
            self.species_binding.precursor_species_ref
        ) or red_internal_species_number(self.evolved_internal_species_id) != red_species_number(
            self.species_binding.evolved_species_ref
        ):
            raise RedBoxedLevelEvolutionError("boxed evolution internal species binding differs")
        if self.deposit_internal_species_id in {
            self.precursor_internal_species_id,
            self.evolved_internal_species_id,
            BLASTOISE_SPECIES_ID,
        }:
            raise RedBoxedLevelEvolutionError(
                "boxed evolution deposit would remove a target or qualified escort"
            )
        if type(self.current_box_index) is not int or not 0 <= self.current_box_index < 12:  # noqa: E721
            raise RedBoxedLevelEvolutionError("boxed evolution current box differs")
        if type(self.precursor_box_slot) is not int or not 1 <= self.precursor_box_slot <= 20:  # noqa: E721
            raise RedBoxedLevelEvolutionError("boxed evolution precursor box slot differs")
        if type(self.deposit_party_slot) is not int or not 1 <= self.deposit_party_slot <= 6:  # noqa: E721
            raise RedBoxedLevelEvolutionError("boxed evolution deposit party slot differs")
        if not isinstance(
            self.route_to_pc,
            (SemanticVenueRouteBinding, ObservedSemanticBoundaryBinding),
        ) or not isinstance(self.route_to_training, SemanticVenueRouteBinding):
            raise TypeError("boxed evolution needs semantic PC access and a training route")
        pc_map, pc_at = _pc_access_terminal(self.route_to_pc)
        if (
            pc_map != self.route_to_training.plan.macro_path.maps[0]
            or pc_at != self.route_to_training.plan.start_at
        ):
            raise RedBoxedLevelEvolutionError(
                "boxed evolution PC access and training route do not share one exact boundary"
            )

    @property
    def skill_binding_sha256(self) -> str:
        document: dict[str, object] = {
            "schema": RED_BOXED_LEVEL_EVOLUTION_SCHEMA,
            "reset_state_sha256": self.reset_state_sha256,
            "dependency_binding_sha256": self.species_binding.binding_sha256,
            "precursor_internal_species_id": self.precursor_internal_species_id,
            "evolved_internal_species_id": self.evolved_internal_species_id,
            "current_box_index": self.current_box_index,
            "precursor_box_slot": self.precursor_box_slot,
            "deposit_party_slot": self.deposit_party_slot,
            "deposit_internal_species_id": self.deposit_internal_species_id,
            "route_to_training_plan_sha256": self.route_to_training.plan_sha256,
            "route_to_training_planner_binding_sha256": (
                self.route_to_training.planner_binding_sha256
            ),
            "training_binding_sha256": self.training_binding_sha256,
        }
        if isinstance(self.route_to_pc, SemanticVenueRouteBinding):
            # Preserve every already-published route-backed skill identity.
            document.update(
                {
                    "route_to_pc_plan_sha256": self.route_to_pc.plan_sha256,
                    "route_to_pc_planner_binding_sha256": (self.route_to_pc.planner_binding_sha256),
                }
            )
        else:
            document.update(
                {
                    "pc_access_kind": "observed_semantic_boundary",
                    "pc_boundary_binding_sha256": self.route_to_pc.binding_sha256,
                }
            )
        if self.pc_facing is not None:
            document["pc_facing"] = self.pc_facing
        return canonical_sha256(document)

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema": RED_BOXED_LEVEL_EVOLUTION_SCHEMA,
            "goal_kind": GoalKind.EVOLVE_SPECIES.value,
            "execution_role": (RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION.value),
            "semantic_routes": (
                2 if isinstance(self.route_to_pc, SemanticVenueRouteBinding) else 1
            ),
            "storage_operations": 2,
            "participation_training": True,
            "model_predictions": 0,
            "controller_actions": 0,
            "species_identity_fields": 0,
            "storage_identity_fields": 0,
            "route_identity_fields": 0,
        }
        if isinstance(self.route_to_pc, ObservedSemanticBoundaryBinding):
            result["observed_semantic_boundaries"] = 1
        return result


@dataclass(frozen=True, slots=True)
class BoxedLevelEvolutionExecutionReport:
    """Exact settled transition and mechanics cost from one selected evolve option."""

    plan: BoxedLevelEvolutionPlan
    before_ledger: DependencySpecimenLedger
    after_ledger: DependencySpecimenLedger
    route_to_pc: RouteExecutionReport | ObservedSemanticBoundaryReport
    deposit: RedPCDepositReport
    withdraw: RedPCWithdrawReport
    route_to_training: RouteExecutionReport
    training: BoundedEvolutionTrainingResult
    controller_actions: int

    def __post_init__(self) -> None:
        if not isinstance(self.plan, BoxedLevelEvolutionPlan):
            raise TypeError("boxed evolution report needs its plan")
        if not isinstance(self.before_ledger, DependencySpecimenLedger) or not isinstance(
            self.after_ledger,
            DependencySpecimenLedger,
        ):
            raise TypeError("boxed evolution report needs specimen ledgers")
        pc_access_passed = (
            isinstance(self.route_to_pc, RouteExecutionReport) and self.route_to_pc.passed
        ) or (
            isinstance(self.route_to_pc, ObservedSemanticBoundaryReport)
            and isinstance(self.plan.route_to_pc, ObservedSemanticBoundaryBinding)
            and self.route_to_pc.binding == self.plan.route_to_pc
        )
        if not pc_access_passed or (
            not isinstance(self.route_to_training, RouteExecutionReport)
            or not self.route_to_training.passed
        ):
            raise RedBoxedLevelEvolutionError("boxed evolution semantic route failed")
        if (
            not isinstance(self.deposit, RedPCDepositReport)
            or not self.deposit.passed
            or not isinstance(self.withdraw, RedPCWithdrawReport)
            or not self.withdraw.passed
        ):
            raise RedBoxedLevelEvolutionError("boxed evolution storage transition failed")
        if not isinstance(self.training, BoundedEvolutionTrainingResult):
            raise TypeError("boxed evolution report needs training evidence")
        if type(self.controller_actions) is not int or self.controller_actions <= 0:  # noqa: E721
            raise RedBoxedLevelEvolutionError("boxed evolution controller cost differs")
        if self.after_ledger != _expected_evolution_ledger(self.plan, self.before_ledger):
            raise RedBoxedLevelEvolutionError(
                "boxed evolution did not produce the exact retained-specimen transition"
            )

    def public_dict(self) -> dict[str, object]:
        route_backed_pc = isinstance(self.route_to_pc, RouteExecutionReport)
        result: dict[str, object] = {
            "schema": RED_BOXED_LEVEL_EVOLUTION_REPORT_SCHEMA,
            "settled": True,
            "semantic_routes_passed": 2 if route_backed_pc else 1,
            "acknowledged_route_steps": (
                (
                    len(self.route_to_pc.executed_steps)
                    if isinstance(self.route_to_pc, RouteExecutionReport)
                    else 0
                )
                + len(self.route_to_training.executed_steps)
            ),
            "deposit_transition_passed": True,
            "withdraw_transition_passed": True,
            "completed_training_battles": self.training.battles_completed,
            "healing_trips": self.training.healing_trips,
            "exact_evolution_transition": True,
            "required_living_preserved": True,
            "controller_actions": self.controller_actions,
            "model_predictions": 0,
            "species_identity_fields": 0,
            "storage_identity_fields": 0,
            "route_identity_fields": 0,
        }
        if not route_backed_pc:
            result["observed_semantic_boundaries_passed"] = 1
        return result


@dataclass(slots=True)
class RedBoxedLevelEvolutionAdapter:
    """Action-free qualification followed by one fail-closed boxed evolution."""

    plan: BoxedLevelEvolutionPlan
    actions: _CountedActionPort
    reader: _RedStorageStateReader
    traversal_observer: TraversalObserver
    observe_collection: Callable[[], CollectionObservation]
    train_evolution: Callable[[int, int], BoundedEvolutionTrainingResult]
    interruption_handler: InterruptionHandler | None = None
    replanner: RouteReplanner | None = None
    resource_manager: RouteResourceManager | None = None
    route_limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS

    def __post_init__(self) -> None:
        if not isinstance(self.plan, BoxedLevelEvolutionPlan):
            raise TypeError("boxed evolution adapter needs a plan")
        if (
            not callable(getattr(self.actions, "execute", None))
            or type(getattr(self.actions, "actions_executed", None)) is not int
        ):  # noqa: E721
            raise TypeError("boxed evolution adapter needs one counted action port")
        if any(
            not callable(getattr(self.reader, name, None))
            for name in ("read", "read_current_box_state", "read_input_readiness")
        ):
            raise TypeError("boxed evolution adapter needs a Red storage state reader")
        if not callable(getattr(self.traversal_observer, "observe", None)):
            raise TypeError("boxed evolution adapter needs a traversal observer")
        if not callable(self.observe_collection) or not callable(self.train_evolution):
            raise TypeError("boxed evolution adapter needs observers and training")
        if not isinstance(self.route_limits, RouteExecutionLimits):
            raise TypeError("boxed evolution adapter needs route limits")

    def qualify(
        self,
        scenario: RedDualCapabilityScenarioSpec,
        before_ledger: DependencySpecimenLedger,
    ) -> BoundRedCapability:
        """Prove the exact box/party/route boundary without controller input."""

        before_actions = self.actions.actions_executed
        self._require_ready(scenario, before_ledger)
        if self.actions.actions_executed != before_actions:
            raise RedBoxedLevelEvolutionError(
                "boxed evolution qualification executed a controller action"
            )
        evidence = ProspectiveRedCapabilityBinding(
            GoalKind.EVOLVE_SPECIES,
            RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
            self.plan.reset_state_sha256,
            self.plan.skill_binding_sha256,
            True,
        )
        return BoundRedCapability(
            evidence,
            self.plan.species_binding.binding_sha256,
            lambda: self.execute(scenario, before_ledger),
        )

    def execute(
        self,
        scenario: RedDualCapabilityScenarioSpec,
        before_ledger: DependencySpecimenLedger,
    ) -> BoxedLevelEvolutionExecutionReport:
        """Execute the selected title-specific mechanic exactly once."""

        self._require_ready(scenario, before_ledger)
        action_start = self.actions.actions_executed
        first_access = self._enter_pc()

        if self.plan.pc_facing is not None:
            from pokemon_red_completion.red_pc_storage import face_pc_boundary

            face_pc_boundary(
                self.actions,
                self.reader,  # type: ignore[arg-type]
                self.plan.pc_facing,  # type: ignore[arg-type]
            )

        open_bills_pc(self.actions, self.reader)  # type: ignore[arg-type]
        deposit = deposit_party_member(
            self.actions,  # type: ignore[arg-type]
            self.reader,  # type: ignore[arg-type]
            party_slot=self.plan.deposit_party_slot,
            expected_species_id=self.plan.deposit_internal_species_id,
        )
        if not deposit.passed:
            raise RedBoxedLevelEvolutionError("boxed evolution deposit did not pass")
        withdraw = withdraw_box_member(
            self.actions,  # type: ignore[arg-type]
            self.reader,  # type: ignore[arg-type]
            box_slot=self.plan.precursor_box_slot,
            expected_species_id=self.plan.precursor_internal_species_id,
        )
        if not withdraw.passed:
            raise RedBoxedLevelEvolutionError("boxed evolution withdrawal did not pass")
        close_menu(self.actions, self.reader)  # type: ignore[arg-type]

        raw = self.reader.read()
        party = getattr(raw, "party_species_ids", None)
        if (
            not isinstance(party, tuple)
            or len(party) != 6
            or BLASTOISE_SPECIES_ID not in party
            or self.plan.precursor_internal_species_id not in party
            or self.plan.deposit_internal_species_id in party
        ):
            raise RedBoxedLevelEvolutionError("boxed evolution storage preparation differs")
        second_route = self._execute_route(self.plan.route_to_training)
        training = self.train_evolution(
            self.plan.precursor_internal_species_id,
            self.plan.evolved_internal_species_id,
        )
        if not isinstance(training, BoundedEvolutionTrainingResult):
            raise RedBoxedLevelEvolutionError(
                "boxed evolution trainer returned no bounded evidence"
            )
        after = dependency_specimen_ledger(self.observe_collection())
        expected = _expected_evolution_ledger(self.plan, before_ledger)
        if after != expected:
            raise RedBoxedLevelEvolutionError(
                "boxed evolution independent collection observation differs"
            )
        return BoxedLevelEvolutionExecutionReport(
            self.plan,
            before_ledger,
            after,
            first_access,
            deposit,
            withdraw,
            second_route,
            training,
            self.actions.actions_executed - action_start,
        )

    def _enter_pc(
        self,
    ) -> RouteExecutionReport | ObservedSemanticBoundaryReport:
        access = self.plan.route_to_pc
        if isinstance(access, SemanticVenueRouteBinding):
            return self._execute_route(access)
        return self._observe_semantic_boundary(access)

    def _execute_route(
        self,
        route: SemanticVenueRouteBinding,
    ) -> RouteExecutionReport:
        report = execute_route(
            route.plan,
            self.actions,
            self.traversal_observer,
            interruption_handler=self.interruption_handler,
            replanner=self.replanner,
            resource_manager=self.resource_manager,
            limits=self.route_limits,
        )
        if not report.passed or report.terminal.map_id != route.plan.terminal_map:
            raise RedBoxedLevelEvolutionError("boxed evolution semantic route failed")
        return report

    def _observe_semantic_boundary(
        self,
        binding: ObservedSemanticBoundaryBinding,
    ) -> ObservedSemanticBoundaryReport:
        action_start = self.actions.actions_executed
        snapshot = self.traversal_observer.observe()
        raw = self.reader.read()
        if (
            getattr(raw, "map_id", None) != binding.map_id
            or (getattr(raw, "player_y", None), getattr(raw, "player_x", None)) != binding.at
            or getattr(raw, "battle_state", None) != 0
            or self.actions.actions_executed != action_start
        ):
            raise RedBoxedLevelEvolutionError(
                "live game state differs from the observed semantic boundary"
            )
        return ObservedSemanticBoundaryReport(
            binding,
            snapshot,
            self.actions.actions_executed - action_start,
        )

    def _require_ready(
        self,
        scenario: RedDualCapabilityScenarioSpec,
        before_ledger: DependencySpecimenLedger,
    ) -> None:
        if not isinstance(scenario, RedDualCapabilityScenarioSpec):
            raise TypeError("boxed evolution qualification needs a scenario")
        if not isinstance(before_ledger, DependencySpecimenLedger):
            raise TypeError("boxed evolution qualification needs a ledger")
        binding = self.plan.species_binding
        if (
            before_ledger.count(binding.precursor_species_ref) != scenario.before.precursor_count
            or before_ledger.count(binding.evolved_species_ref) != scenario.before.evolved_count
        ):
            raise RedBoxedLevelEvolutionError(
                "boxed evolution ledger does not implement the scenario"
            )
        observed = dependency_specimen_ledger(self.observe_collection())
        if observed != before_ledger:
            raise RedBoxedLevelEvolutionError(
                "boxed evolution collection differs from the shared reset ledger"
            )
        pc_access = self.plan.route_to_pc
        if isinstance(pc_access, SemanticVenueRouteBinding):
            snapshot = self.traversal_observer.observe()
            plan = pc_access.plan
            if (
                snapshot.map_id != plan.macro_path.maps[0]
                or snapshot.at != plan.start_at
                or not snapshot.ready
                or snapshot.interruption is not None
            ):
                raise RedBoxedLevelEvolutionError(
                    "boxed evolution route does not start at the observed reset"
                )
        else:
            self._observe_semantic_boundary(pc_access)
        raw = self.reader.read()
        party = getattr(raw, "party_species_ids", None)
        battle_state = getattr(raw, "battle_state", None)
        readiness = self.reader.read_input_readiness()
        if (
            not isinstance(party, tuple)
            or len(party) != 6
            or battle_state != 0
            or getattr(readiness, "ready", None) is not True
            or party[self.plan.deposit_party_slot - 1] != self.plan.deposit_internal_species_id
            or BLASTOISE_SPECIES_ID not in party
            or self.plan.precursor_internal_species_id in party
        ):
            raise RedBoxedLevelEvolutionError("boxed evolution party boundary is not executable")
        box = self.reader.read_current_box_state()
        slot = self.plan.precursor_box_slot - 1
        if (
            not isinstance(box, RedCurrentBoxState)
            or box.box_index != self.plan.current_box_index
            or len(box.species_ids) >= 20
            or slot >= len(box.species_ids)
            or box.species_ids[slot] != self.plan.precursor_internal_species_id
        ):
            raise RedBoxedLevelEvolutionError(
                "boxed evolution current-box boundary is not executable"
            )


def _pc_access_terminal(
    access: SemanticPCBoundaryAccess,
) -> tuple[int, tuple[int, int]]:
    if isinstance(access, SemanticVenueRouteBinding):
        return access.plan.terminal_map, access.plan.terminal_at
    if isinstance(access, ObservedSemanticBoundaryBinding):
        return access.map_id, access.at
    raise TypeError("boxed evolution PC access differs")


def _expected_evolution_ledger(
    plan: BoxedLevelEvolutionPlan,
    before: DependencySpecimenLedger,
) -> DependencySpecimenLedger:
    counts = dict(before.specimen_counts)
    precursor = plan.species_binding.precursor_species_ref
    evolved = plan.species_binding.evolved_species_ref
    if counts.get(precursor, 0) < 1:
        raise RedBoxedLevelEvolutionError("boxed evolution precursor is absent")
    counts[precursor] -= 1
    if counts[precursor] == 0:
        del counts[precursor]
    counts[evolved] = counts.get(evolved, 0) + 1
    return DependencySpecimenLedger(tuple(sorted(counts.items())))


def _require_sha256(value: str, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedBoxedLevelEvolutionError(f"{subject} SHA-256 is invalid")


__all__ = [
    "RED_BOXED_LEVEL_EVOLUTION_REPORT_SCHEMA",
    "RED_BOXED_LEVEL_EVOLUTION_SCHEMA",
    "RED_OBSERVED_SEMANTIC_BOUNDARY_REPORT_SCHEMA",
    "RED_OBSERVED_SEMANTIC_BOUNDARY_SCHEMA",
    "BoundedEvolutionTrainingResult",
    "BoxedLevelEvolutionExecutionReport",
    "BoxedLevelEvolutionPlan",
    "ObservedSemanticBoundaryBinding",
    "ObservedSemanticBoundaryReport",
    "RedBoxedLevelEvolutionAdapter",
    "RedBoxedLevelEvolutionError",
    "SemanticPCBoundaryAccess",
]
