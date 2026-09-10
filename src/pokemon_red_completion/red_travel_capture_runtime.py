"""Prospective acquisition-only connection to existing recorded capture mechanics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from .collection import CollectionObservation
from .executor import CountingExecutor, WindowedFrameBudgetController
from .gen1_cartridge import wild_tables
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .provenance import canonical_sha256
from .red_acquisition import summarize_red_area_survey
from .red_collection import red_internal_species_number, red_species_ref
from .red_goal_context_profile import RedGoalMechanic, RedGoalProviderSpec
from .red_goal_manager import RedGoalBindingOffer, RedGoalBindingProvider, RedGoalObservation
from .red_goal_skills import RedAreaSurveyGoalProvider
from .red_travel_capture import RedTravelCaptureError, RegisteredTravelCaptureHandler
from .route_executor import InterruptionHandler
from .surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor

if TYPE_CHECKING:
    from .red_goal_context import RedGoalContextRuntime
    from .red_resource_goal_router import RedResourceGoalRouter


@lru_cache(maxsize=2)
def _ordinary_species(rom: bytes) -> tuple[tuple[int, frozenset[str]], ...]:
    return tuple(
        (
            map_id,
            frozenset(
                red_species_ref(red_internal_species_number(species)) for _, species in slots
            ),
        )
        for map_id, slots in wild_tables(rom, medium="grass").items()
        if slots
    )


@dataclass
class BoundedTravelCapturePort:
    """Narrow the original recording chain; never create a second controller."""

    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    status_support: bool
    maximum_actions: int = 512
    maximum_frames: int = 120_000
    attempted: bool = False

    def read_collection(self) -> CollectionObservation:
        return self.runtime.adapter.observe().collection_observation

    def capture_encounter(self, species_ref: str) -> bool:
        if self.attempted:
            raise RedTravelCaptureError("travel capture port is already consumed")
        frames = self.runtime.emulator
        if not isinstance(frames, WindowedFrameBudgetController):
            raise RedTravelCaptureError("travel capture needs the existing hard frame controller")
        limited = HardCompositionActionLimiter(
            self.actions,
            maximum_actions_per_decision=self.maximum_actions,
            maximum_episode_actions=self.maximum_actions,
        )
        capture = LiveWildEncounterExecutor(
            frames,
            CountingExecutor(limited),
            self.runtime.reader,
            DEFAULT_SURGE_TIMING,
            label="registered acquisition travel",
            capture_status_support=self.status_support,
        )
        self.attempted = True
        with frames.limit_additional_frames(self.maximum_frames):
            return capture.capture_encounter(species_ref)


def bind_travel_capture_handler(
    router: RedResourceGoalRouter,
    spec: RedGoalProviderSpec,
    fallback: InterruptionHandler,
) -> InterruptionHandler:
    if (
        spec.mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE
        or spec.parameters.get("travel_capture") is not True
    ):
        return fallback
    runtime = router.runtime
    policy = runtime.registration_policy
    if policy is None:
        raise RedTravelCaptureError("travel capture requires a frozen registration policy")
    port = BoundedTravelCapturePort(
        runtime,
        router.actions,
        spec.parameters.get("capture_status_support") is True,
        maximum_actions=min(512, router.maximum_controller_actions),
        maximum_frames=min(120_000, router.maximum_emulator_frames),
    )
    return RegisteredTravelCaptureHandler(
        runtime.reader,
        port,
        fallback,
        policy.registered,
        policy.targets,
        dict(_ordinary_species(router.world.rom)),
        lambda: runtime.emulator.frame_count,
        lambda: router.actions.actions_executed,
        maximum_capture_actions=port.maximum_actions,
        maximum_capture_frames=port.maximum_frames,
    )


@dataclass
class TravelSatisfiedCaptureProvider:
    """Only acknowledge satisfied demand after verified transport and catch.

    The ordinary destination binder still enforces exact arrival. This provider
    does no controller work, never acknowledges an unverified catch, and never
    converts a route exception into success.
    """

    provider: RedGoalBindingProvider
    survey: RedAreaSurveyGoalProvider
    runtime: RedGoalContextRuntime
    initial_missing: frozenset[str]
    handlers: list[InterruptionHandler]
    actions: CountingExecutor
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        for handler in self.handlers:
            if isinstance(handler, RegisteredTravelCaptureHandler) and handler.receipts:
                saved = handler.verified_collection
                current = observation.collection_observation
                if (
                    saved is None
                    or not saved.owned_species <= current.owned_species
                    or Counter(s.species_ref for s in saved.specimens)
                    - Counter(s.species_ref for s in current.specimens)
                ):
                    raise RedTravelCaptureError("travel capture stock or registration was lost")
        missing = summarize_red_area_survey(
            self.survey.source_id, observation.collection_observation, self.survey.catalog
        ).missing_species_refs
        credited = frozenset(
            str(receipt["species_ref"])
            for handler in self.handlers
            if isinstance(handler, RegisteredTravelCaptureHandler)
            for receipt in handler.receipts
            if receipt.get("captured") is True and receipt.get("new_registrations") == 1
        )
        if (
            missing
            or not self.initial_missing
            or not credited.intersection(self.initial_missing)
            or not credited <= observation.collection_observation.owned_species
        ):
            return self.provider.offer(observation)
        if (
            observation.raw.battle_state
            or not observation.input_ready
            or observation.party.fainted_count
            or any(observation.raw.party_status or ())
        ):
            return self.provider.offer(observation)
        report: GoalExecutionReport | None = None
        before = self.actions.actions_executed, self.runtime.emulator.frame_count

        def execute() -> GoalExecutionReport:
            nonlocal report
            if report is not None or self.runtime.adapter.observe() != observation:
                raise RedTravelCaptureError("travel-satisfied arrival changed or was consumed")
            if before != (self.actions.actions_executed, self.runtime.emulator.frame_count):
                raise RedTravelCaptureError("travel-satisfied arrival advanced before execution")
            report = GoalExecutionReport(
                0,
                0,
                {
                    "source_satisfied_during_transport": True,
                    "destination_capture_actions": 0,
                    "new_learning_labels": 0,
                    "capture_survey": {"captures": 0, "encounters_seen": 0, "flees": 0},
                },
            )
            return report

        def verify(actual: GoalExecutionReport) -> GoalVerification:
            if (
                report is None
                or actual is not report
                or self.runtime.adapter.observe() != observation
                or before != (self.actions.actions_executed, self.runtime.emulator.frame_count)
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref="red-travel-satisfied:"
                + canonical_sha256(
                    {
                        "source": self.survey.source_id,
                        "credit": sorted(credited),
                    }
                ),
                kind=self.kind,
                estimated_effort=0.0,
                estimated_risk=0.0,
                execute=execute,
                verify=verify,
            )
        )


def bind_travel_capture_destination(
    router: RedResourceGoalRouter,
    spec: RedGoalProviderSpec,
    provider: RedGoalBindingProvider,
    survey: RedGoalBindingProvider,
    initial: RedGoalObservation,
    handlers: list[InterruptionHandler],
) -> RedGoalBindingProvider:
    if spec.parameters.get("travel_capture") is not True or not isinstance(
        survey, RedAreaSurveyGoalProvider
    ):
        return provider
    missing = summarize_red_area_survey(
        survey.source_id,
        initial.collection_observation,
        survey.catalog,
    ).missing_species_refs
    return TravelSatisfiedCaptureProvider(
        provider,
        survey,
        router.runtime,
        frozenset(missing),
        handlers,
        router.actions,
    )
