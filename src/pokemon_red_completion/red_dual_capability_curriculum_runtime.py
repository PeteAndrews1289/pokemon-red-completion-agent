"""ROM-free execution seams for Red's acquire-versus-evolve curriculum.

This module binds the public dependency curriculum to reusable mechanics without
choosing an action or opening an emulator.  Route construction remains outside
the seam: callers provide a :class:`RoutePlan` produced by an authenticated
semantic router, never a profile-owned sequence of directions.  The model sees
only the two title-neutral policy rows from the public curriculum; map, species,
route, and skill identities remain private.

The acquisition loop deliberately permits one additional precursor even when
the living-collection planner already has enough.  Otherwise the duplicate-ready
fixture would hide the intentionally suboptimal action instead of measuring its
settled negative outcome.  Utility is decided only by the independent specimen-
ledger verifier after execution.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAcquisitionKind,
    RedAreaExecutionError,
    RedAreaExecutor,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    ProspectiveRedCapabilityBinding,
    ProspectiveRedDualCapabilityScenario,
    RedDependencyCapabilityRole,
    RedDependencySpeciesBinding,
    RedDualCapabilityOutcome,
    RedDualCapabilityScenarioSpec,
    verify_red_dual_capability_outcome,
)
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
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.training_venue import TrainingVenue, WarpSafeVenueWalker

RED_SEMANTIC_VENUE_ROUTE_SCHEMA = "pokemon.red.private-semantic-venue-route.v1"
RED_SEMANTIC_VENUE_CAPTURE_SCHEMA = "pokemon.red.private-semantic-venue-capture.v1"
RED_TARGET_CAPTURE_REPORT_SCHEMA = "pokemon.red.private-target-capture-report.v1"
RED_BOUNDED_EVOLUTION_BINDING_SCHEMA = "pokemon.red.private-bounded-evolution-binding.v1"
RED_BOUND_DUAL_CAPABILITY_SCENARIO_SCHEMA = "pokemon.red.private-bound-dual-capability-scenario.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CAPABILITY_ORDER = (GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES)
_BOUNDED_EVOLUTION_PROVIDERS = {
    (
        "pokemon:national:050",
        "pokemon:national:051",
    ): "pokemon.red:evolution:diglett-to-dugtrio",
}


class RedDualCapabilityRuntimeError(RuntimeError):
    """The semantic implementation crossed its frozen curriculum boundary."""


class _VenueActionPort(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class _VenueStateReader(Protocol):
    def read(self) -> object: ...


@dataclass(frozen=True, slots=True)
class SemanticVenueRouteBinding:
    """One computed route with explicit proof that no profile script supplied it."""

    plan: RoutePlan
    planner_binding_sha256: str
    route_source: str = "authenticated_semantic_router"
    profile_direction_steps: int = 0
    curriculum_direction_steps: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RoutePlan):
            raise TypeError("semantic venue route needs a RoutePlan")
        _require_sha256(self.planner_binding_sha256, "planner binding")
        if self.route_source != "authenticated_semantic_router":
            raise RedDualCapabilityRuntimeError("venue route is not semantic-router derived")
        if (
            type(self.profile_direction_steps) is not int  # noqa: E721
            or type(self.curriculum_direction_steps) is not int  # noqa: E721
            or self.profile_direction_steps != 0
            or self.curriculum_direction_steps != 0
        ):
            raise RedDualCapabilityRuntimeError(
                "profile and curriculum direction sequences are forbidden"
            )
        if not self.plan.steps:
            raise RedDualCapabilityRuntimeError("semantic venue route must cross a real boundary")

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(_route_plan_document(self.plan))

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_SEMANTIC_VENUE_ROUTE_SCHEMA,
            "semantic_router_authenticated": True,
            "acknowledged_step_contracts": len(self.plan.steps),
            "profile_direction_steps": 0,
            "curriculum_direction_steps": 0,
            "map_identity_fields": 0,
            "route_identity_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class SemanticCaptureReadiness:
    """Private pre-score mechanics observed at the shared reset state."""

    reset_state_sha256: str
    ordinary_capture_items: int
    immediate_capture_slots: int
    input_ready: bool
    battle_active: bool

    def __post_init__(self) -> None:
        _require_sha256(self.reset_state_sha256, "capture readiness reset state")
        for name in ("ordinary_capture_items", "immediate_capture_slots"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise RedDualCapabilityRuntimeError(
                    f"{name.replace('_', ' ')} must be non-negative"
                )
        if type(self.input_ready) is not bool or type(self.battle_active) is not bool:
            raise TypeError("capture readiness flags must be boolean")

    @property
    def mechanically_available(self) -> bool:
        return (
            self.input_ready
            and not self.battle_active
            and self.ordinary_capture_items > 0
            and self.immediate_capture_slots > 0
        )


@dataclass(frozen=True, slots=True)
class SemanticCaptureVenue:
    """A cartridge-grounded wild source, without invented training evidence.

    Capturing only needs a semantic destination and a bounded way to take wild
    encounter steps without crossing an exit.  It does not need an encounter
    level band, healer, attack move, or a claim that runtime samples were
    measured.  Those belong to :class:`TrainingVenue` and made non-training
    sources look more evidenced than they were.
    """

    source_id: str
    map_id: int
    excluded_coordinates: frozenset[tuple[int, int]]
    move_wait_frames: int = 120
    maximum_no_progress_cycles: int = 2

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or not self.source_id
            or len(self.source_id) > 256
            or any(character in self.source_id for character in "\r\n\x00")
        ):
            raise RedDualCapabilityRuntimeError("semantic capture venue source is invalid")
        # Reuse the traversal type's strict validation rather than maintaining a
        # second, subtly different coordinate contract.
        self.fresh_walk_to_grass()

    def fresh_walk_to_grass(self) -> WarpSafeVenueWalker:
        return WarpSafeVenueWalker(
            self.map_id,
            self.excluded_coordinates,
            move_wait_frames=self.move_wait_frames,
            maximum_no_progress_cycles=self.maximum_no_progress_cycles,
        )


@dataclass(frozen=True, slots=True)
class SemanticVenueCapturePlan:
    """Private semantic bindings for one bounded target capture."""

    reset_state_sha256: str
    species_binding: RedDependencySpeciesBinding
    source_id: str
    route: SemanticVenueRouteBinding
    venue: TrainingVenue | SemanticCaptureVenue
    maximum_actions: int = 2_000
    maximum_encounters: int = 400
    catalog: RedAcquisitionCatalog = RED_ACQUISITION_CATALOG

    def __post_init__(self) -> None:
        _require_sha256(self.reset_state_sha256, "capture reset state")
        if not isinstance(self.species_binding, RedDependencySpeciesBinding):
            raise TypeError("capture plan needs a species binding")
        if (
            not isinstance(self.source_id, str)
            or not self.source_id
            or len(self.source_id) > 256
            or any(character in self.source_id for character in "\r\n\x00")
        ):
            raise RedDualCapabilityRuntimeError("capture source identity is invalid")
        if not isinstance(self.route, SemanticVenueRouteBinding):
            raise TypeError("capture plan needs a semantic route binding")
        if not isinstance(self.venue, (TrainingVenue, SemanticCaptureVenue)):
            raise TypeError("capture plan needs a bounded capture venue")
        if (
            isinstance(self.venue, SemanticCaptureVenue)
            and self.venue.source_id != self.source_id
        ):
            raise RedDualCapabilityRuntimeError(
                "semantic capture venue differs from the bound wild source"
            )
        if not isinstance(self.catalog, RedAcquisitionCatalog):
            raise TypeError("capture plan needs a Red acquisition catalog")
        if self.catalog != RED_ACQUISITION_CATALOG:
            raise RedDualCapabilityRuntimeError("capture plan must use the canonical Red catalog")
        for name in ("maximum_actions", "maximum_encounters"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise RedDualCapabilityRuntimeError(f"{name} must be positive")
        precursor = self.catalog.method_for(self.species_binding.precursor_species_ref)
        if (
            precursor.kind is not RedAcquisitionKind.WILD
            or precursor.transforms_precursor
            or not precursor.repeatable
            or precursor.source_id != self.source_id
        ):
            raise RedDualCapabilityRuntimeError(
                "precursor is not a repeatable wild target at the bound source"
            )
        if self.route.plan.terminal_map != self.venue.map_id:
            raise RedDualCapabilityRuntimeError(
                "semantic route does not terminate in the measured venue"
            )

    @property
    def skill_binding_sha256(self) -> str:
        venue_document: dict[str, object]
        if isinstance(self.venue, TrainingVenue):
            # Preserve the already-published Diglett capability binding exactly.
            venue_document = {
                "area_id": self.venue.area_id,
                "conditions": list(self.venue.band.conditions),
                "map_id": self.venue.map_id,
                "minimum_encounter_level": self.venue.band.minimum_encounter_level,
                "maximum_encounter_level": self.venue.band.maximum_encounter_level,
                "rare_maximum_encounter_level": (
                    self.venue.band.rare_maximum_encounter_level
                ),
                "measured_samples": self.venue.band.measured_samples,
            }
        else:
            venue_document = {
                "kind": "cartridge_semantic_source",
                "source_id": self.venue.source_id,
                "map_id": self.venue.map_id,
                "excluded_coordinates": [
                    list(coordinate) for coordinate in sorted(self.venue.excluded_coordinates)
                ],
                "move_wait_frames": self.venue.move_wait_frames,
                "maximum_no_progress_cycles": self.venue.maximum_no_progress_cycles,
            }
        return canonical_sha256(
            {
                "schema": RED_SEMANTIC_VENUE_CAPTURE_SCHEMA,
                "reset_state_sha256": self.reset_state_sha256,
                "dependency_binding_sha256": self.species_binding.binding_sha256,
                "source_id": self.source_id,
                "planner_binding_sha256": self.route.planner_binding_sha256,
                "route_plan_sha256": self.route.plan_sha256,
                "venue": venue_document,
                "maximum_actions": self.maximum_actions,
                "maximum_encounters": self.maximum_encounters,
                "capture_quota": 1,
            }
        )

    def public_dict(self) -> dict[str, object]:
        measured = isinstance(self.venue, TrainingVenue)
        return {
            "schema": RED_SEMANTIC_VENUE_CAPTURE_SCHEMA,
            "goal_kind": GoalKind.ACQUIRE_SPECIES.value,
            "execution_role": self.execution_role.value,
            "semantic_route": self.route.public_dict(),
            "measured_venue": measured,
            "cartridge_semantic_venue": not measured,
            "capture_quota": 1,
            "target_identity_fields": 0,
            "venue_identity_fields": 0,
            "route_identity_fields": 0,
        }

    @property
    def execution_role(self) -> RedDependencyCapabilityRole:
        return (
            RedDependencyCapabilityRole.MEASURED_VENUE_CAPTURE
            if isinstance(self.venue, TrainingVenue)
            else RedDependencyCapabilityRole.SEMANTIC_VENUE_CAPTURE
        )


@dataclass(slots=True)
class SemanticVenueAreaExecutor:
    """Give the semantic area loop a warp-safe encounter-step implementation."""

    delegate: RedAreaExecutor
    actions: _VenueActionPort
    reader: _VenueStateReader
    emulator: object
    walker: WarpSafeVenueWalker

    def __post_init__(self) -> None:
        required = (
            "read_collection",
            "encountered_species_ref",
            "capture_encounter",
            "flee_encounter",
            "switch_box",
        )
        if any(not callable(getattr(self.delegate, name, None)) for name in required):
            raise TypeError("venue delegate does not implement the Red area port")
        if not callable(getattr(self.actions, "execute", None)):
            raise TypeError("venue actions do not implement execute")
        if not callable(getattr(self.reader, "read", None)):
            raise TypeError("venue reader does not implement read")
        if not isinstance(self.walker, WarpSafeVenueWalker):
            raise TypeError("venue executor needs a WarpSafeVenueWalker")

    def read_collection(self) -> CollectionObservation:
        return self.delegate.read_collection()

    def encountered_species_ref(self) -> str | None:
        return self.delegate.encountered_species_ref()

    def seek_encounter(self) -> None:
        if self.encountered_species_ref() is not None:
            raise RedAreaExecutionError(
                "semantic venue cannot seek during an encounter",
                reason_code="seek_requested_during_encounter",
            )
        moved = self.walker(self.actions, self.reader, self.emulator)
        if moved not in {0, 1}:
            raise RedAreaExecutionError(
                "semantic venue walker returned an invalid step count",
                reason_code="venue_walker_invalid_step_count",
            )

    def capture_encounter(self, species_ref: str) -> bool | None:
        return self.delegate.capture_encounter(species_ref)

    def flee_encounter(self) -> None:
        self.delegate.flee_encounter()

    def switch_box(self, box_index: int) -> None:
        self.delegate.switch_box(box_index)

    def public_summary(self) -> dict[str, int]:
        return self.walker.public_summary()


@dataclass(frozen=True, slots=True)
class RedTargetCaptureReport:
    """Settled evidence for exactly one bound precursor capture."""

    source_id: str
    target_species_ref: str
    actions_executed: int
    encounters_seen: int
    captures: int
    flees: int
    before_target_count: int
    after_target_count: int

    def __post_init__(self) -> None:
        for name in (
            "actions_executed",
            "encounters_seen",
            "captures",
            "flees",
            "before_target_count",
            "after_target_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise RedDualCapabilityRuntimeError(f"target capture {name} is invalid")
        if self.captures != 1 or self.after_target_count != self.before_target_count + 1:
            raise RedDualCapabilityRuntimeError(
                "target capture did not retain exactly one specimen"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_TARGET_CAPTURE_REPORT_SCHEMA,
            "settled": True,
            "captures": self.captures,
            "encounters_seen": self.encounters_seen,
            "flees": self.flees,
            "target_count_delta": self.after_target_count - self.before_target_count,
            "species_identity_fields": 0,
            "source_identity_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class SemanticVenueCaptureExecutionReport:
    """Private route and capture evidence, with an identity-free projection."""

    plan: SemanticVenueCapturePlan
    route: RouteExecutionReport
    capture: RedTargetCaptureReport
    after_ledger: DependencySpecimenLedger

    def __post_init__(self) -> None:
        if not isinstance(self.plan, SemanticVenueCapturePlan):
            raise TypeError("capture execution report needs its bound plan")
        if not isinstance(self.route, RouteExecutionReport) or not self.route.passed:
            raise RedDualCapabilityRuntimeError("semantic venue route did not pass")
        if self.route.terminal.map_id != self.plan.venue.map_id:
            raise RedDualCapabilityRuntimeError("capture route ended outside the measured venue")
        if not isinstance(self.capture, RedTargetCaptureReport):
            raise TypeError("capture execution report needs target-capture evidence")
        if not isinstance(self.after_ledger, DependencySpecimenLedger):
            raise TypeError("capture execution report needs a specimen ledger")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_SEMANTIC_VENUE_CAPTURE_SCHEMA,
            "route_passed": True,
            "acknowledged_route_steps": len(self.route.executed_steps),
            "capture": self.capture.public_dict(),
            "target_identity_fields": 0,
            "venue_identity_fields": 0,
            "route_identity_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class BoundRedCapability:
    """One private executable joined to its pre-score capability evidence."""

    evidence: ProspectiveRedCapabilityBinding
    dependency_binding_sha256: str
    execute: Callable[[], object]

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, ProspectiveRedCapabilityBinding):
            raise TypeError("bound capability needs prospective evidence")
        _require_sha256(self.dependency_binding_sha256, "dependency binding")
        if not callable(self.execute):
            raise TypeError("bound capability needs an executor")

    def public_dict(self) -> dict[str, object]:
        return {
            "goal_kind": self.evidence.kind.value,
            "execution_role": self.evidence.role.value,
            "mechanically_available": self.evidence.mechanically_available,
            "private_identity_fields": 0,
        }


@dataclass(slots=True)
class RedSemanticVenueCaptureAdapter:
    """Qualify and execute one semantic route followed by one target capture."""

    plan: SemanticVenueCapturePlan
    actions: RouteActionPort
    traversal_observer: TraversalObserver
    area_executor: SemanticVenueAreaExecutor
    interruption_handler: InterruptionHandler | None = None
    replanner: RouteReplanner | None = None
    resource_manager: RouteResourceManager | None = None
    route_limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS

    def __post_init__(self) -> None:
        if not isinstance(self.plan, SemanticVenueCapturePlan):
            raise TypeError("semantic capture adapter needs a capture plan")
        if not callable(getattr(self.actions, "execute", None)):
            raise TypeError("semantic capture adapter needs an action port")
        if not callable(getattr(self.traversal_observer, "observe", None)):
            raise TypeError("semantic capture adapter needs a traversal observer")
        if not isinstance(self.area_executor, SemanticVenueAreaExecutor):
            raise TypeError("semantic capture adapter needs its measured-venue executor")
        if self.area_executor.actions is not self.actions:
            raise RedDualCapabilityRuntimeError(
                "route and encounter traversal must share one bounded action port"
            )
        if self.area_executor.walker.expected_map_id != self.plan.venue.map_id:
            raise RedDualCapabilityRuntimeError("venue walker map differs from the measured venue")
        if isinstance(self.plan.venue, SemanticCaptureVenue):
            expected = self.plan.venue.fresh_walk_to_grass()
            if (
                self.area_executor.walker.excluded_coordinates
                != expected.excluded_coordinates
                or self.area_executor.walker.move_wait_frames != expected.move_wait_frames
                or self.area_executor.walker.maximum_no_progress_cycles
                != expected.maximum_no_progress_cycles
            ):
                raise RedDualCapabilityRuntimeError(
                    "venue walker differs from the semantic capture venue"
                )
        if not isinstance(self.route_limits, RouteExecutionLimits):
            raise TypeError("semantic capture adapter needs route limits")

    def qualify(
        self,
        scenario: RedDualCapabilityScenarioSpec,
        before_ledger: DependencySpecimenLedger,
        readiness: SemanticCaptureReadiness,
    ) -> BoundRedCapability:
        """Authenticate availability without routing, walking, capturing, or scoring."""

        self._require_ready(scenario, before_ledger, readiness)
        evidence = ProspectiveRedCapabilityBinding(
            GoalKind.ACQUIRE_SPECIES,
            self.plan.execution_role,
            self.plan.reset_state_sha256,
            self.plan.skill_binding_sha256,
            True,
        )
        return BoundRedCapability(
            evidence,
            self.plan.species_binding.binding_sha256,
            lambda: self.execute(scenario, before_ledger, readiness),
        )

    def execute(
        self,
        scenario: RedDualCapabilityScenarioSpec,
        before_ledger: DependencySpecimenLedger,
        readiness: SemanticCaptureReadiness,
    ) -> SemanticVenueCaptureExecutionReport:
        """Execute the already-selected acquisition capability exactly once."""

        self._require_ready(scenario, before_ledger, readiness)
        route = execute_route(
            self.plan.route.plan,
            self.actions,
            self.traversal_observer,
            interruption_handler=self.interruption_handler,
            replanner=self.replanner,
            resource_manager=self.resource_manager,
            limits=self.route_limits,
        )
        if not route.passed or route.terminal.map_id != self.plan.venue.map_id:
            raise RedDualCapabilityRuntimeError(
                "semantic traversal did not reach the measured venue"
            )
        capture = run_red_target_capture(
            self.plan.source_id,
            self.plan.species_binding.precursor_species_ref,
            self.area_executor,
            maximum_actions=self.plan.maximum_actions,
            maximum_encounters=self.plan.maximum_encounters,
        )
        after = dependency_specimen_ledger(self.area_executor.read_collection())
        return SemanticVenueCaptureExecutionReport(self.plan, route, capture, after)

    def _require_ready(
        self,
        scenario: RedDualCapabilityScenarioSpec,
        before_ledger: DependencySpecimenLedger,
        readiness: SemanticCaptureReadiness,
    ) -> None:
        if not isinstance(readiness, SemanticCaptureReadiness):
            raise TypeError("capture qualification needs readiness evidence")
        if readiness.reset_state_sha256 != self.plan.reset_state_sha256:
            raise RedDualCapabilityRuntimeError("capture readiness came from another reset state")
        if not readiness.mechanically_available:
            raise RedDualCapabilityRuntimeError("capture resources are not mechanically available")
        _require_scenario_ledger(scenario, self.plan.species_binding, before_ledger)
        observed_ledger = dependency_specimen_ledger(self.area_executor.read_collection())
        if observed_ledger != before_ledger:
            raise RedDualCapabilityRuntimeError(
                "capture collection differs from the shared reset ledger"
            )
        if self.area_executor.encountered_species_ref() is not None:
            raise RedDualCapabilityRuntimeError(
                "capture qualification cannot begin inside an encounter"
            )
        _require_route_start(self.plan.route.plan, self.traversal_observer.observe())


@dataclass(slots=True)
class SelectedRedDualCapability:
    """Exactly one bound action; no API exists for executing both candidates."""

    selected_index: int
    capability: BoundRedCapability
    _executed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.selected_index) is not int or self.selected_index not in {0, 1}:  # noqa: E721
            raise RedDualCapabilityRuntimeError("selected capability index is invalid")
        if not isinstance(self.capability, BoundRedCapability):
            raise TypeError("selection needs one bound capability")
        if self.capability.evidence.kind is not _CAPABILITY_ORDER[self.selected_index]:
            raise RedDualCapabilityRuntimeError("selected index and capability kind differ")

    def execute(self) -> object:
        if self._executed:
            raise RedDualCapabilityRuntimeError("selected capability was already executed")
        self._executed = True
        return self.capability.execute()

    def public_dict(self) -> dict[str, object]:
        return {
            "selected_candidate_index": self.selected_index,
            "selected_goal_kind": self.capability.evidence.kind.value,
            "selected_capability_count": 1,
            "private_identity_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class BoundRedDualCapabilityScenario:
    """One same-reset full menu plus private executors, before model scoring."""

    scenario: RedDualCapabilityScenarioSpec
    species_binding: RedDependencySpeciesBinding
    before_ledger: DependencySpecimenLedger
    capabilities: tuple[BoundRedCapability, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, RedDualCapabilityScenarioSpec):
            raise TypeError("bound scenario needs a scenario spec")
        if not isinstance(self.species_binding, RedDependencySpeciesBinding):
            raise TypeError("bound scenario needs a species binding")
        if not isinstance(self.before_ledger, DependencySpecimenLedger):
            raise TypeError("bound scenario needs a before ledger")
        _require_scenario_ledger(self.scenario, self.species_binding, self.before_ledger)
        if (
            len(self.capabilities) != 2
            or tuple(item.evidence.kind for item in self.capabilities) != _CAPABILITY_ORDER
            or any(
                item.dependency_binding_sha256 != self.species_binding.binding_sha256
                for item in self.capabilities
            )
        ):
            raise RedDualCapabilityRuntimeError(
                "bound scenario needs both capabilities for one dependency"
            )
        ProspectiveRedDualCapabilityScenario(
            self.scenario,
            self.species_binding.binding_sha256,
            tuple(item.evidence for item in self.capabilities),
        )

    @property
    def prospective(self) -> ProspectiveRedDualCapabilityScenario:
        return ProspectiveRedDualCapabilityScenario(
            self.scenario,
            self.species_binding.binding_sha256,
            tuple(item.evidence for item in self.capabilities),
        )

    def policy_rows(self) -> tuple[dict[str, int | str], ...]:
        return self.prospective.policy_rows()

    def bind_selection(self, selected_index: int) -> SelectedRedDualCapability:
        if type(selected_index) is not int or selected_index not in {0, 1}:  # noqa: E721
            raise RedDualCapabilityRuntimeError("selected candidate index is invalid")
        return SelectedRedDualCapability(selected_index, self.capabilities[selected_index])

    def verify_outcome(
        self,
        *,
        selected_kind: GoalKind,
        after_ledger: DependencySpecimenLedger | None,
    ) -> RedDualCapabilityOutcome:
        return verify_red_dual_capability_outcome(
            self.scenario,
            self.species_binding,
            selected_kind=selected_kind,
            before_ledger=self.before_ledger,
            after_ledger=after_ledger,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            **self.prospective.public_dict(),
            "schema": RED_BOUND_DUAL_CAPABILITY_SCENARIO_SCHEMA,
            "candidate_rows": [dict(row) for row in self.policy_rows()],
            "assigned_action": None,
            "teacher_label": None,
            "private_species_fields": 0,
            "private_route_fields": 0,
        }


def bind_bounded_evolution_offer(
    scenario: RedDualCapabilityScenarioSpec,
    species_binding: RedDependencySpeciesBinding,
    before_ledger: DependencySpecimenLedger,
    *,
    reset_state_sha256: str,
    offer: RedGoalBindingOffer,
) -> BoundRedCapability:
    """Join one already-qualified evolution provider to the private dependency."""

    _require_sha256(reset_state_sha256, "evolution reset state")
    _require_scenario_ledger(scenario, species_binding, before_ledger)
    if (
        not isinstance(offer, RedGoalBindingOffer)
        or offer.kind is not GoalKind.EVOLVE_SPECIES
        or not isinstance(offer.binding, ExecutableGoalBinding)
    ):
        raise RedDualCapabilityRuntimeError("bounded evolution offer is unavailable")
    expected_provider = _BOUNDED_EVOLUTION_PROVIDERS.get(
        (
            species_binding.precursor_species_ref,
            species_binding.evolved_species_ref,
        )
    )
    if expected_provider is None or re.fullmatch(
        re.escape(expected_provider)
        + r":profile-[0-9a-f]{64}:config-[0-9a-f]{64}",
        offer.binding.binding_ref,
    ) is None:
        raise RedDualCapabilityRuntimeError(
            "bounded evolution offer does not implement the declared dependency"
        )
    skill_binding_sha256 = canonical_sha256(
        {
            "schema": RED_BOUNDED_EVOLUTION_BINDING_SCHEMA,
            "reset_state_sha256": reset_state_sha256,
            "dependency_binding_sha256": species_binding.binding_sha256,
            "goal_kind": offer.binding.kind.value,
            "provider_binding_ref": offer.binding.binding_ref,
        }
    )
    evidence = ProspectiveRedCapabilityBinding(
        GoalKind.EVOLVE_SPECIES,
        RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
        reset_state_sha256,
        skill_binding_sha256,
        True,
    )
    return BoundRedCapability(
        evidence,
        species_binding.binding_sha256,
        offer.binding.execute,
    )


def build_red_dual_capability_scenario(
    scenario: RedDualCapabilityScenarioSpec,
    species_binding: RedDependencySpeciesBinding,
    before_ledger: DependencySpecimenLedger,
    capabilities: tuple[BoundRedCapability, ...],
) -> BoundRedDualCapabilityScenario:
    """Fail closed unless both independent commands share one reset and dependency."""

    return BoundRedDualCapabilityScenario(
        scenario,
        species_binding,
        before_ledger,
        capabilities,
    )


def dependency_specimen_ledger(
    observation: CollectionObservation,
) -> DependencySpecimenLedger:
    """Project a fresh collection observation into the exact private multiset."""

    if not isinstance(observation, CollectionObservation):
        raise TypeError("dependency ledger needs a CollectionObservation")
    counts = Counter(specimen.species_ref for specimen in observation.specimens)
    return DependencySpecimenLedger(tuple(sorted(counts.items())))


def run_red_target_capture(
    source_id: str,
    target_species_ref: str,
    executor: RedAreaExecutor,
    *,
    maximum_actions: int,
    maximum_encounters: int,
) -> RedTargetCaptureReport:
    """Seek one repeatable target under hard bounds, even when it is redundant."""

    if not isinstance(source_id, str) or not source_id:
        raise RedAreaExecutionError(
            "target capture source is absent",
            reason_code="target_capture_source_missing",
        )
    method = RED_ACQUISITION_CATALOG.method_for(target_species_ref)
    if (
        method.kind is not RedAcquisitionKind.WILD
        or method.source_id != source_id
        or not method.repeatable
        or method.transforms_precursor
    ):
        raise RedAreaExecutionError(
            "target is not a repeatable wild member of this source",
            reason_code="target_capture_source_mismatch",
        )
    for name, value in (
        ("maximum_actions", maximum_actions),
        ("maximum_encounters", maximum_encounters),
    ):
        if type(value) is not int or value <= 0:  # noqa: E721
            raise RedAreaExecutionError(
                f"{name} must be positive",
                reason_code="target_capture_bound_invalid",
            )
    initial = executor.read_collection()
    before_counts = Counter(specimen.species_ref for specimen in initial.specimens)
    if initial.party_size >= initial.party_limit and not initial.current_box_has_room:
        raise RedAreaExecutionError(
            "target capture has no immediate retained-specimen slot",
            reason_code="target_capture_storage_unavailable",
        )
    encounters_seen = 0
    flees = 0
    for action_index in range(maximum_actions):
        encountered = executor.encountered_species_ref()
        if encountered is None:
            executor.seek_encounter()
            encountered = executor.encountered_species_ref()
            if encountered is not None:
                encounters_seen += 1
                if encounters_seen > maximum_encounters:
                    break
            continue
        if encountered != target_species_ref:
            executor.flee_encounter()
            if executor.encountered_species_ref() is not None:
                raise RedAreaExecutionError(
                    "target capture flee did not settle",
                    reason_code="flee_postcondition_failed",
                )
            flees += 1
            continue
        retained = executor.capture_encounter(target_species_ref)
        after = executor.read_collection()
        after_counts = Counter(specimen.species_ref for specimen in after.specimens)
        if retained is False:
            if after_counts != before_counts or executor.encountered_species_ref() is not None:
                raise RedAreaExecutionError(
                    "failed target capture changed the collection",
                    reason_code="capture_retry_postcondition_failed",
                )
            flees += 1
            continue
        if (
            after_counts[target_species_ref] != before_counts[target_species_ref] + 1
            or any(
                after_counts[species] != count
                for species, count in before_counts.items()
                if species != target_species_ref
            )
            or any(
                count
                for species, count in (after_counts - before_counts).items()
                if species != target_species_ref
            )
            or executor.encountered_species_ref() is not None
        ):
            raise RedAreaExecutionError(
                "target capture did not retain exactly one bound precursor",
                reason_code="capture_retention_postcondition_failed",
            )
        return RedTargetCaptureReport(
            source_id=source_id,
            target_species_ref=target_species_ref,
            actions_executed=action_index + 1,
            encounters_seen=encounters_seen,
            captures=1,
            flees=flees,
            before_target_count=before_counts[target_species_ref],
            after_target_count=after_counts[target_species_ref],
        )
    raise RedAreaExecutionError(
        "target capture exhausted its action or encounter bound",
        reason_code="target_capture_bound_exhausted",
    )


def _require_route_start(plan: RoutePlan, current: TraversalSnapshot) -> None:
    if not isinstance(current, TraversalSnapshot):
        raise TypeError("semantic route observer returned an invalid snapshot")
    if (
        current.map_id != plan.macro_path.maps[0]
        or current.at != plan.start_at
        or current.mode != plan.start_mode
        or not current.ready
        or current.interruption is not None
    ):
        raise RedDualCapabilityRuntimeError(
            "semantic route is not executable from the shared reset state"
        )


def _require_scenario_ledger(
    scenario: RedDualCapabilityScenarioSpec,
    binding: RedDependencySpeciesBinding,
    ledger: DependencySpecimenLedger,
) -> None:
    if not isinstance(scenario, RedDualCapabilityScenarioSpec):
        raise TypeError("scenario must be a RedDualCapabilityScenarioSpec")
    if not isinstance(binding, RedDependencySpeciesBinding):
        raise TypeError("binding must be a RedDependencySpeciesBinding")
    if not isinstance(ledger, DependencySpecimenLedger):
        raise TypeError("ledger must be a DependencySpecimenLedger")
    if (
        ledger.count(binding.precursor_species_ref) != scenario.before.precursor_count
        or ledger.count(binding.evolved_species_ref) != scenario.before.evolved_count
    ):
        raise RedDualCapabilityRuntimeError("shared reset ledger differs from the scenario")


def _route_plan_document(plan: RoutePlan) -> dict[str, object]:
    return {
        "schema": RED_SEMANTIC_VENUE_ROUTE_SCHEMA,
        "maps": list(plan.macro_path.maps),
        "start_at": list(plan.start_at),
        "start_mode": plan.start_mode,
        "terminal_at": list(plan.terminal_at),
        "terminal_mode": plan.terminal_mode,
        "steps": [
            {
                "source_map": step.source_map,
                "source_at": list(step.source_at),
                "action": step.action,
                "action_kind": step.action_kind.value,
                "expected_map": step.expected_map,
                "expected_at": list(step.expected_at),
                "kind": step.kind,
                "source_mode": step.source_mode,
                "expected_mode": step.expected_mode,
                "transient_at": (None if step.transient_at is None else list(step.transient_at)),
            }
            for step in plan.steps
        ],
    }


def _require_sha256(value: str, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedDualCapabilityRuntimeError(f"{subject} SHA-256 is invalid")


__all__ = [
    "RED_BOUND_DUAL_CAPABILITY_SCENARIO_SCHEMA",
    "RED_BOUNDED_EVOLUTION_BINDING_SCHEMA",
    "RED_SEMANTIC_VENUE_CAPTURE_SCHEMA",
    "RED_SEMANTIC_VENUE_ROUTE_SCHEMA",
    "RED_TARGET_CAPTURE_REPORT_SCHEMA",
    "BoundRedCapability",
    "BoundRedDualCapabilityScenario",
    "RedDualCapabilityRuntimeError",
    "RedSemanticVenueCaptureAdapter",
    "RedTargetCaptureReport",
    "SelectedRedDualCapability",
    "SemanticCaptureReadiness",
    "SemanticCaptureVenue",
    "SemanticVenueAreaExecutor",
    "SemanticVenueCaptureExecutionReport",
    "SemanticVenueCapturePlan",
    "SemanticVenueRouteBinding",
    "bind_bounded_evolution_offer",
    "build_red_dual_capability_scenario",
    "dependency_specimen_ledger",
    "run_red_target_capture",
]
