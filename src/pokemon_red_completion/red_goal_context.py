"""Instantiate authenticated Red goal-manager profiles as real mechanics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Protocol, cast

from pokemon_red_completion.blaine import (
    DIGLETT_SPECIES_ID,
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_BALANCED_TEAM_TRAINING_INTENT,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TEAM_POLICY,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_TRAINING_VENUE,
    MANSION_VOLATILE_ENEMY_SPECIES,
    ROUTE_11_TRAINING_VENUE,
    _flee,
)
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor, WindowedFrameBudgetController
from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.goal_manager_context_catalog import GoalManagerContextCapture
from pokemon_red_completion.goal_manager_runtime import (
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.observation import (
    ItemId,
    MapId,
    PokemonRedStateReader,
)
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.red_acquisition import RedAreaExecutionPolicy
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    RedGoalProviderSpec,
)
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalBindingOffer,
    RedGoalBindingProvider,
    RedGoalManagerConfig,
    RedGoalObservation,
    RedGoalOpportunityEnumerator,
    RedStoryGoalBindingProvider,
)
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedBoxSwitchGoalProvider,
    RedCenterRestoreGoalProvider,
    RedControlRecoveryGoalProvider,
    RedEncounterDiscoveryGoalProvider,
    RedEncounterSourceDevelopmentGoalProvider,
    RedFieldRestoreGoalProvider,
    RedGoalSkillAvailability,
    RedMartPurchase,
    RedMartResupplyGoalProvider,
    RedObservedGoalSkillProvider,
    RedProgressGoalProvider,
)
from pokemon_red_completion.red_objective_skills import (
    build_red_midgame_objective_skill_registry,
)
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
)
from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
from pokemon_red_completion.red_team_training import (
    FixedPartyTrainingDose,
    member_is_unsafe_for_team_training,
    run_red_team_balancing,
)
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.surge import (
    DEFAULT_SURGE_TIMING,
    LiveWildCorridorSurveyExecutor,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy
from pokemon_red_completion.training_venue import TrainingVenue


class RedGoalContextError(RuntimeError):
    """Raised when a profile cannot bind truthfully to the loaded cartridge."""


class RedGoalContextEmulator(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...


@dataclass(frozen=True, slots=True)
class RedBoxedLevelEvolutionGoalRequest:
    """Exact state-derived binding for the existing boxed-evolution engine."""

    precursor_internal_species_id: int
    evolved_internal_species_id: int
    current_box_index: int
    precursor_box_slot: int
    deposit_party_slot: int
    deposit_internal_species_id: int

    def __post_init__(self) -> None:
        for name in (
            "precursor_internal_species_id",
            "evolved_internal_species_id",
            "deposit_internal_species_id",
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 0xFF:  # noqa: E721
                raise RedGoalContextError(f"boxed evolution {name} differs")
        if (
            type(self.current_box_index) is not int  # noqa: E721
            or not 0 <= self.current_box_index < 12
            or type(self.precursor_box_slot) is not int  # noqa: E721
            or not 1 <= self.precursor_box_slot <= 20
            or type(self.deposit_party_slot) is not int  # noqa: E721
            or not 1 <= self.deposit_party_slot <= 6
        ):
            raise RedGoalContextError("boxed evolution storage binding differs")
        if self.deposit_internal_species_id in {
            self.precursor_internal_species_id,
            self.evolved_internal_species_id,
            BLASTOISE_SPECIES_ID,
        }:
            raise RedGoalContextError("boxed evolution deposit binding is unsafe")


RedBoxedLevelEvolutionGoalExecutor = Callable[
    [RedBoxedLevelEvolutionGoalRequest, CountingExecutor],
    GoalExecutionReport,
]


@dataclass(slots=True)
class RedGoalContextRuntime:
    """Loaded semantic adapter plus a deterministic executable-menu factory."""

    profile: RedGoalContextProfile
    capture: GoalManagerContextCapture
    emulator: RedGoalContextEmulator
    reader: PokemonRedStateReader
    observer: CapturedPokemonRedObserver
    adapter: PokemonRedGoalStateAdapter
    boxed_level_evolution_executor: RedBoxedLevelEvolutionGoalExecutor | None = None
    party_level_evolution_executor: (
        Callable[[int, int, CountingExecutor], GoalExecutionReport] | None
    ) = None
    boxed_level_evolution_readiness: (
        Callable[[RedGoalObservation], RedGoalSkillAvailability] | None
    ) = None

    def provider_for(self, kind: GoalKind, actions: CountingExecutor) -> RedGoalBindingProvider:
        """Build the declared mechanic; callers still need a fresh, verified offer."""

        if not isinstance(kind, GoalKind) or not isinstance(actions, CountingExecutor):
            raise TypeError("provider construction needs a goal kind and counted actions")
        specs = tuple(spec for spec in self.profile.providers if spec.kind is kind)
        if len(specs) != 1:
            raise RedGoalContextError("goal context profile lacks one requested provider")
        return _build_provider(self, specs[0], actions)

    def enumerator(self, actions: CountingExecutor) -> RedGoalOpportunityEnumerator:
        if not isinstance(actions, CountingExecutor):
            raise TypeError("goal context actions must be a CountingExecutor")
        providers = tuple(
            _ProfileBoundProvider(
                provider=_build_provider(self, spec, actions),
                profile_sha256=self.profile.profile_sha256,
                configuration_sha256=spec.configuration_sha256,
            )
            for spec in self.profile.providers
        )
        return RedGoalOpportunityEnumerator(providers)

    def offer_for(
        self,
        kind: GoalKind,
        observation: RedGoalObservation,
        actions: CountingExecutor,
    ) -> RedGoalContextProviderOffer:
        """Construct one offer through the real profile registry.

        This is the narrow action-free seam used by same-root validation.  The
        caller receives the concrete provider class that the registry built,
        not a class name reported by an opaque campaign adapter.
        """

        if not isinstance(kind, GoalKind):
            raise TypeError("goal context offer needs a goal kind")
        if not isinstance(observation, RedGoalObservation):
            raise TypeError("goal context offer needs a Red observation")
        if not isinstance(actions, CountingExecutor):
            raise TypeError("goal context offer actions must be a CountingExecutor")
        specs = tuple(item for item in self.profile.providers if item.kind is kind)
        if len(specs) != 1:
            raise RedGoalContextError("goal context profile lacks one requested provider")
        spec = specs[0]
        provider = _build_provider(self, spec, actions)
        wrapped = _ProfileBoundProvider(
            provider=provider,
            profile_sha256=self.profile.profile_sha256,
            configuration_sha256=spec.configuration_sha256,
        )
        return RedGoalContextProviderOffer(
            provider_type=_provider_contract_type(provider, spec),
            profile_sha256=self.profile.profile_sha256,
            provider_configuration_sha256=spec.configuration_sha256,
            offer=wrapped.offer(observation),
        )


def _provider_contract_type(
    provider: RedGoalBindingProvider,
    spec: RedGoalProviderSpec,
) -> type[object]:
    """Name the concrete semantic offer contract behind a registry adapter."""

    if isinstance(provider, _RedTeamGoalProvider):
        if spec.mechanic is RedGoalMechanic.BALANCED_TEAM:
            return RedProgressGoalProvider
        return RedObservedGoalSkillProvider
    return type(provider)


@dataclass(frozen=True, slots=True)
class RedGoalContextProviderOffer:
    """Registry-authored action-free offer plus concrete provider provenance."""

    provider_type: type[object]
    profile_sha256: str
    provider_configuration_sha256: str
    offer: RedGoalBindingOffer

    def __post_init__(self) -> None:
        if not isinstance(self.provider_type, type):
            raise TypeError("goal context provider type differs")
        for value, subject in (
            (self.profile_sha256, "profile"),
            (self.provider_configuration_sha256, "provider configuration"),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise RedGoalContextError(f"goal context {subject} digest differs")
        if not isinstance(self.offer, RedGoalBindingOffer):
            raise TypeError("goal context provider offer differs")
        self.offer.__post_init__()


def build_red_goal_context_runtime(
    *,
    profile: RedGoalContextProfile,
    capture: GoalManagerContextCapture,
    emulator: RedGoalContextEmulator,
    reader: PokemonRedStateReader,
    boxed_level_evolution_executor: RedBoxedLevelEvolutionGoalExecutor | None = None,
) -> RedGoalContextRuntime:
    """Bind one verified state and finite profile without retaining any paths."""

    if not isinstance(profile, RedGoalContextProfile):
        raise TypeError("profile must be a RedGoalContextProfile")
    if not isinstance(capture, GoalManagerContextCapture):
        raise TypeError("capture must be a verified GoalManagerContextCapture")
    if boxed_level_evolution_executor is not None and not callable(boxed_level_evolution_executor):
        raise TypeError("boxed level evolution executor must be callable")
    observer = CapturedPokemonRedObserver(reader, COMPLETION_QUEST, capture.envelope)
    adapter = PokemonRedGoalStateAdapter(
        reader,
        observer,
        COMPLETION_QUEST,
        config=profile.manager_config,
    )
    # Fail closed now if the envelope's claimed story frontier conflicts with
    # the actual loaded state.  This performs no action.
    adapter.observe()
    return RedGoalContextRuntime(
        profile=profile,
        capture=capture,
        emulator=emulator,
        reader=reader,
        observer=observer,
        adapter=adapter,
        boxed_level_evolution_executor=boxed_level_evolution_executor,
    )


@dataclass(frozen=True, slots=True)
class _ProfileBoundProvider:
    """Put the full private profile identity into the non-policy binding seam."""

    provider: RedGoalBindingProvider
    profile_sha256: str
    configuration_sha256: str

    @property
    def kind(self) -> GoalKind:
        return self.provider.kind

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        offer = self.provider.offer(observation)
        if offer.binding is None:
            return offer
        binding = offer.binding
        return RedGoalBindingOffer.available(
            replace(
                binding,
                binding_ref=(
                    f"{binding.binding_ref}:profile-{self.profile_sha256}:"
                    f"config-{self.configuration_sha256}"
                ),
            )
        )


def _build_provider(
    runtime: RedGoalContextRuntime,
    spec: RedGoalProviderSpec,
    actions: CountingExecutor,
) -> RedGoalBindingProvider:
    mechanic = spec.mechanic
    if mechanic is RedGoalMechanic.MIDGAME_STORY:
        return RedStoryGoalBindingProvider(
            COMPLETION_QUEST,
            build_red_midgame_objective_skill_registry(
                runtime.emulator,
                runtime.reader,
                actions,
            ),
            runtime.observer,
        )
    if mechanic in {
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
    }:
        return _wild_provider(runtime, spec, actions)
    if mechanic in {
        RedGoalMechanic.BALANCED_TEAM,
        RedGoalMechanic.DIGLETT_EVOLUTION,
        RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
        RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
    }:
        return _team_provider(runtime, spec, actions)
    if mechanic is RedGoalMechanic.FIELD_RESTORE:
        return RedFieldRestoreGoalProvider(
            actions,
            runtime.reader,
            runtime.emulator,
            runtime.adapter,
        )
    if mechanic is RedGoalMechanic.CENTER_RESTORE:
        return RedCenterRestoreGoalProvider(
            actions,
            runtime.reader,
            runtime.emulator,
            runtime.adapter,
        )
    if mechanic is RedGoalMechanic.MART_RESUPPLY:
        return _mart_provider(runtime, spec, actions)
    if mechanic is RedGoalMechanic.BOX_SWITCH:
        return _box_provider(runtime, spec, actions)
    if mechanic is RedGoalMechanic.CONTROL_RECOVERY:
        return RedControlRecoveryGoalProvider(
            actions,
            runtime.reader,
            runtime.emulator,
            runtime.adapter,
        )
    raise RedGoalContextError("context profile selected an unsupported mechanic")


def _wild_provider(
    runtime: RedGoalContextRuntime,
    spec: RedGoalProviderSpec,
    actions: CountingExecutor,
) -> RedGoalBindingProvider:
    parameters = spec.parameters
    source_id = _text(parameters, "source_id")
    map_id = MapId(_integer(parameters, "map_id"))
    x = _integer(parameters, "player_x")
    y = _integer(parameters, "player_y")
    area = LiveWildCorridorSurveyExecutor(
        runtime.emulator,
        actions,
        runtime.reader,
        DEFAULT_SURGE_TIMING,
        label=_text(parameters, "label"),
        forward_directions=_directions(parameters, "forward_directions"),
        starting_endpoint=_text(parameters, "starting_endpoint"),
        max_legs=_integer(parameters, "maximum_legs"),
    )

    def boundary(observation: RedGoalObservation) -> RedGoalSkillAvailability:
        raw = observation.raw
        if raw.map_id != map_id or raw.player_x != x or raw.player_y != y:
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        return RedGoalSkillAvailability.available()

    if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
        return RedAreaSurveyGoalProvider(
            source_id=source_id,
            area_executor=area,
            actions=actions,
            emulator=runtime.emulator,
            adapter=runtime.adapter,
            boundary=boundary,
            normalize_after_capture=area.finish_at_starting_endpoint,
            policy=RedAreaExecutionPolicy(
                max_actions=_integer(parameters, "maximum_seek_steps"),
                max_encounters=_integer(parameters, "maximum_encounters"),
                capture_in_requirement_order=True,
                capture_quota=1,
            ),
        )
    if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT:
        return _wild_development_provider(
            runtime,
            spec,
            actions,
            area=area,
            boundary=boundary,
        )
    return RedEncounterDiscoveryGoalProvider(
        source_id=source_id,
        area_executor=area,
        actions=actions,
        emulator=runtime.emulator,
        adapter=runtime.adapter,
        boundary=boundary,
        maximum_seek_steps=_integer(parameters, "maximum_seek_steps"),
        maximum_encounters=_integer(parameters, "maximum_encounters"),
    )


def _wild_development_provider(
    runtime: RedGoalContextRuntime,
    spec: RedGoalProviderSpec,
    actions: CountingExecutor,
    *,
    area: LiveWildCorridorSurveyExecutor,
    boundary: Callable[[RedGoalObservation], RedGoalSkillAvailability],
) -> RedGoalBindingProvider:
    """Bind one fixed local battle dose without permitting travel or healing."""

    parameters = spec.parameters
    source_id = _text(parameters, "source_id")
    map_id = MapId(_integer(parameters, "map_id"))
    completed_battles = _integer(parameters, "completed_battles")
    maximum_seek_steps = _integer(parameters, "maximum_seek_steps")

    def execute() -> GoalExecutionReport:
        if not isinstance(actions.delegate, HardCompositionActionLimiter) or not isinstance(
            runtime.emulator, WindowedFrameBudgetController
        ):
            raise RedGoalContextError(
                "encounter-source development lacks hard action/frame limiters"
            )
        before = runtime.adapter.observe()
        trainee = before.party.weakest_trainable_member
        dose_policy = replace(
            red_team_development_quantum_policy(
                before.party,
                runtime.profile.manager_config,
                kind=GoalKind.DEVELOP_TEAM,
            ),
            max_battles=completed_battles,
            max_steps=maximum_seek_steps,
            max_healing_trips=0,
            max_faints=0,
        )
        if trainee is None or before.party.species_ids().count(trainee.species_id) != 1:
            raise RedGoalContextError(
                "encounter-source development lacks one unique trainable member"
            )
        if before.party.fainted_count or member_is_unsafe_for_team_training(trainee, dose_policy):
            raise RedGoalContextError(
                "encounter-source development needs restoration before its fixed dose"
            )
        if map_id != MANSION_TRAINING_VENUE.map_id:
            raise RedGoalContextError("encounter-source development lacks a measured local venue")
        before_actions = actions.actions_executed
        before_frames = runtime.emulator.frame_count

        def walk_local_source(
            _actions: object,
            _reader: object,
            _emulator: object,
        ) -> int:
            area.seek_encounter()
            return 1

        def reject_recovery(
            _actions: object,
            _reader: object,
            _emulator: object,
        ) -> None:
            raise RedGoalContextError("encounter-source development cannot travel or heal")

        local_venue = TrainingVenue(
            band=MANSION_TRAINING_VENUE.band,
            map_id=int(map_id),
            walk_to_grass=walk_local_source,
            heal_and_return=reject_recovery,
            is_in_center=lambda _raw: False,
            move_slot=MANSION_TRAINING_VENUE.move_slot,
            move_guard=MANSION_TRAINING_VENUE.move_guard,
            battle_timing=MANSION_TRAINING_VENUE.battle_timing,
            walk_to_grass_factory=lambda: walk_local_source,
        )
        _report, battles, healing_trips = run_red_team_balancing(
            actions,
            runtime.reader,
            runtime.emulator,
            policy=dose_policy,
            venues=(local_venue,),
            intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=DEFAULT_HIDEOUT_TIMING,
            flee_func=cast(Callable[..., None], _flee),
            volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            report_label="goal-manager encounter-source development",
            checkpoint_count=1,
            fixed_dose=FixedPartyTrainingDose(
                (trainee.species_id,),
                local_venue.band.identity,
                completed_battles,
            ),
        )
        if battles != completed_battles or healing_trips:
            raise RedGoalContextError("encounter-source development left its fixed local dose")
        # Return to the same source boundary so the next goal-manager decision
        # is based on a fresh, co-available menu rather than corridor interior.
        area.finish_at_starting_endpoint()
        return GoalExecutionReport(
            actions_executed=actions.actions_executed - before_actions,
            frames_executed=runtime.emulator.frame_count - before_frames,
            evidence={
                "bounded": True,
                "source_local": True,
                "completed_battles": battles,
                "healing_trips": healing_trips,
                "travel_transitions": 0,
            },
        )

    def development_boundary(
        observation: RedGoalObservation,
    ) -> RedGoalSkillAvailability:
        result = boundary(observation)
        if not result.executable:
            return result
        trainee = observation.party.weakest_trainable_member
        dose_policy = replace(
            red_team_development_quantum_policy(
                observation.party,
                runtime.profile.manager_config,
                kind=GoalKind.DEVELOP_TEAM,
            ),
            max_battles=completed_battles,
            max_steps=maximum_seek_steps,
            max_healing_trips=0,
            max_faints=0,
        )
        if (
            BLASTOISE_SPECIES_ID not in observation.party.species_ids()
            or trainee is None
            or observation.party.species_ids().count(trainee.species_id) != 1
            or observation.party.fainted_count > 0
            or member_is_unsafe_for_team_training(trainee, dose_policy)
        ):
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        return result

    return RedEncounterSourceDevelopmentGoalProvider(
        source_ref=source_id,
        binding_ref=f"pokemon.red:development:{source_id}",
        adapter=runtime.adapter,
        boundary=development_boundary,
        executor=execute,
        estimated_effort=min(1.0, completed_battles / 12),
        estimated_risk=0.20,
    )


def _team_provider(
    runtime: RedGoalContextRuntime,
    spec: RedGoalProviderSpec,
    actions: CountingExecutor,
) -> RedGoalBindingProvider:
    return _RedTeamGoalProvider(runtime, spec, actions)


@dataclass(frozen=True, slots=True)
class _RedTeamGoalProvider:
    """Bind one short development quantum or one targeted evolution."""

    runtime: RedGoalContextRuntime
    spec: RedGoalProviderSpec
    actions: CountingExecutor

    def __post_init__(self) -> None:
        if not isinstance(self.spec, RedGoalProviderSpec) or self.spec.mechanic not in {
            RedGoalMechanic.BALANCED_TEAM,
            RedGoalMechanic.DIGLETT_EVOLUTION,
            RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT,
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        }:
            raise RedGoalContextError("team provider received an unsupported goal kind")

    @property
    def kind(self) -> GoalKind:
        return self.spec.kind

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        availability = self._availability(observation)
        if not availability.executable:
            assert availability.unavailable_reason is not None
            return RedGoalBindingOffer.unavailable(
                self.kind,
                availability.unavailable_reason,
            )
        policy = (
            None
            if self.spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION
            else self._policy(observation)
        )
        evolution_target = self._evolution_target()
        resume_evolution = (
            self.spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION
            and evolution_target is not None
            and evolution_target[0] in observation.party.species_ids()
            and self.runtime.party_level_evolution_executor is not None
        )
        boxed_request = (
            self._boxed_evolution_request(observation)
            if self.spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION
            and not resume_evolution
            else None
        )
        before_actions = self.actions.actions_executed
        before_frames = self.runtime.emulator.frame_count

        def execute() -> GoalExecutionReport:
            if resume_evolution:
                resume = self.runtime.party_level_evolution_executor
                assert resume is not None and evolution_target is not None
                report = resume(*evolution_target, self.actions)
                if (
                    report.actions_executed != self.actions.actions_executed - before_actions
                    or report.frames_executed != self.runtime.emulator.frame_count - before_frames
                ):
                    raise RedGoalContextError("resumed evolution cost differs from execution")
                return report
            if boxed_request is not None:
                executor = self.runtime.boxed_level_evolution_executor
                if executor is None:
                    raise RedGoalContextError(
                        "boxed evolution executor disappeared after offer construction"
                    )
                report = executor(boxed_request, self.actions)
                if not isinstance(report, GoalExecutionReport):
                    raise RedGoalContextError("boxed evolution executor returned no report")
                if (
                    report.actions_executed != self.actions.actions_executed - before_actions
                    or report.frames_executed != self.runtime.emulator.frame_count - before_frames
                ):
                    raise RedGoalContextError(
                        "boxed evolution report differs from measured execution"
                    )
                return report
            assert policy is not None
            _report, battles, healing_trips = run_red_team_balancing(
                self.actions,
                self.runtime.reader,
                self.runtime.emulator,
                policy=policy,
                venues=(
                    ROUTE_11_TRAINING_VENUE,
                    DIGLETTS_CAVE_TRAINING_VENUE,
                    MANSION_TRAINING_VENUE,
                ),
                intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
                flee_timing=MANSION_TRAINING_FLEE_TIMING,
                hideout_timing=DEFAULT_HIDEOUT_TIMING,
                flee_func=cast(Callable[..., None], _flee),
                volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
                escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
                max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
                cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
                evolution_target=evolution_target,
                development_target_species_id=(
                    self._development_target_species_id()
                    if self.spec.mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT
                    else None
                ),
                report_label=f"goal-manager {self.kind.value}",
                checkpoint_count=1,
            )
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.runtime.emulator.frame_count - before_frames,
                evidence={
                    "bounded": True,
                    "battles": battles,
                    "healing_trips": healing_trips,
                    "evolution_target": evolution_target is not None,
                    "local_level_floor": policy.minimum_level,
                },
            )

        if self.kind is GoalKind.EVOLVE_SPECIES:
            return RedObservedGoalSkillProvider(
                kind=self.kind,
                binding_ref=self._binding_ref(),
                adapter=self.runtime.adapter,
                availability=self._availability,
                executor=execute,
                verifier=self._verify_evolution,
                estimated_effort=0.55,
                estimated_risk=0.22,
            ).offer(observation)
        if self.spec.mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT:
            return RedObservedGoalSkillProvider(
                kind=self.kind,
                binding_ref=self._binding_ref(),
                adapter=self.runtime.adapter,
                availability=self._availability,
                executor=execute,
                verifier=self._verify_development,
                estimated_effort=0.45,
                estimated_risk=0.22,
            ).offer(observation)
        return RedProgressGoalProvider(
            kind=self.kind,
            binding_ref="pokemon.red:development:one-level-quantum",
            adapter=self.runtime.adapter,
            boundary=self._availability,
            executor=execute,
            estimated_effort=0.45,
            estimated_risk=0.22,
        ).offer(observation)

    def _verify_evolution(
        self,
        before: RedGoalObservation,
        after: RedGoalObservation,
        report: GoalExecutionReport,
    ) -> GoalVerification:
        before_story = self.runtime.adapter.graph.completed_ids(before.game_state)
        after_story = self.runtime.adapter.graph.completed_ids(after.game_state)
        evolution_target = self._evolution_target()
        if evolution_target is None:
            raise RedGoalContextError("evolution provider lost its target")
        if self.spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            return self._verify_boxed_evolution(before, after, report)
        target_index = _targeted_evolution_index(
            before.party.species_ids(),
            after.party.species_ids(),
            source_species_id=evolution_target[0],
            target_species_id=evolution_target[1],
        )
        if (
            before_story != after_story
            or after.collection.collection.pokedex_owned_count
            < before.collection.collection.pokedex_owned_count
            or after.collection.collection.living_count < before.collection.collection.living_count
        ):
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
        if (
            target_index is None
            or report.actions_executed <= 0
            or after.raw.battle_state
            or not after.input_ready
            or after.party.fainted_count
            or after.party.members[target_index].level <= before.party.members[target_index].level
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    def _verify_boxed_evolution(
        self,
        before: RedGoalObservation,
        after: RedGoalObservation,
        report: GoalExecutionReport,
    ) -> GoalVerification:
        source_ref = _text(self.spec.parameters, "source_species_ref")
        target_ref = _text(self.spec.parameters, "target_species_ref")
        before_counts = Counter(
            specimen.species_ref for specimen in before.collection_observation.specimens
        )
        expected_counts = before_counts.copy()
        if expected_counts[source_ref] < 1:
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
        expected_counts[source_ref] -= 1
        if expected_counts[source_ref] == 0:
            del expected_counts[source_ref]
        expected_counts[target_ref] += 1
        after_counts = Counter(
            specimen.species_ref for specimen in after.collection_observation.specimens
        )
        before_story = self.runtime.adapter.graph.completed_ids(before.game_state)
        after_story = self.runtime.adapter.graph.completed_ids(after.game_state)
        if (
            report.evidence.get("evolution_partial") is True
            and before_counts == after_counts
            and before_story == after_story
            and after.raw.battle_state == 0
            and after.input_ready
            and not after.party.fainted_count
        ):
            # A bounded experience quantum is resumable work, not a species
            # transformation and not fabricated collection success.
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        evolution_target = self._evolution_target()
        if evolution_target is None:
            raise RedGoalContextError("boxed evolution lost its target")
        evolved_party = tuple(
            member for member in after.party.members if member.species_id == evolution_target[1]
        )
        if (
            before_story != after_story
            or after_counts != expected_counts
            or after.collection.collection.pokedex_owned_count
            < before.collection.collection.pokedex_owned_count
        ):
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
        if (
            report.actions_executed <= 0
            or after.raw.battle_state
            or not after.input_ready
            or after.party.fainted_count
            or len(evolved_party) != 1
            or evolved_party[0].level < _integer(self.spec.parameters, "evolution_level")
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    def _verify_development(
        self,
        before: RedGoalObservation,
        after: RedGoalObservation,
        report: GoalExecutionReport,
    ) -> GoalVerification:
        target_species = self._development_target_species_id()
        increment = _integer(self.spec.parameters, "level_increment")
        before_indexes = tuple(
            index
            for index, member in enumerate(before.party.members)
            if member.species_id == target_species
        )
        before_story = self.runtime.adapter.graph.completed_ids(before.game_state)
        after_story = self.runtime.adapter.graph.completed_ids(after.game_state)
        if (
            len(before_indexes) != 1
            or before_story != after_story
            or before.party.species_ids() != after.party.species_ids()
            or after.collection.collection.pokedex_owned_count
            < before.collection.collection.pokedex_owned_count
            or after.collection.collection.living_count < before.collection.collection.living_count
        ):
            return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
        index = before_indexes[0]
        if (
            report.actions_executed <= 0
            or after.raw.battle_state
            or not after.input_ready
            or after.party.fainted_count
            or after.party.members[index].level < before.party.members[index].level + increment
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    def _availability(
        self,
        observation: RedGoalObservation,
    ) -> RedGoalSkillAvailability:
        raw = observation.raw
        if (
            raw.map_id not in {MapId.CINNABAR_POKECENTER, MapId.VERMILION_POKECENTER}
            or raw.player_x != 3
            or raw.player_y != 3
        ):
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        return self.resource_availability(observation)

    def resource_availability(
        self,
        observation: RedGoalObservation,
    ) -> RedGoalSkillAvailability:
        """Check real resources independently of transport; never invent arrival state."""
        required_size = self.runtime.profile.manager_config.required_party_size
        if BLASTOISE_SPECIES_ID not in observation.party.species_ids():
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        if self.kind is GoalKind.DEVELOP_TEAM:
            if observation.party.size < required_size:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            if self.spec.mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT:
                target_species = self._development_target_species_id()
                targets = tuple(
                    member
                    for member in observation.party.members
                    if member.species_id == target_species
                )
                if len(targets) != 1 or not targets[0].is_trainable:
                    return RedGoalSkillAvailability.unavailable(
                        GoalUnavailableReason.NO_LEGAL_TARGET
                    )
                target = targets[0]
                floor = target.level + _integer(
                    self.spec.parameters,
                    "level_increment",
                )
                if floor > 100:
                    return RedGoalSkillAvailability.unavailable(
                        GoalUnavailableReason.NO_LEGAL_TARGET
                    )
        evolution_target = self._evolution_target()
        evolved_ref = (
            None
            if evolution_target is None
            else red_species_ref(red_internal_species_number(evolution_target[1]))
        )
        living_refs = frozenset(
            specimen.species_ref for specimen in observation.collection_observation.specimens
        )
        if self.spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            if self.runtime.boxed_level_evolution_executor is None:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            if self.runtime.boxed_level_evolution_readiness is not None:
                readiness = self.runtime.boxed_level_evolution_readiness(observation)
                if not readiness.executable:
                    return readiness
            if (
                evolution_target is not None
                and evolution_target[0] in observation.party.species_ids()
                and self.runtime.party_level_evolution_executor is not None
            ):
                if observation.party.species_ids().count(evolution_target[0]) != 1:
                    return RedGoalSkillAvailability.unavailable(
                        GoalUnavailableReason.NO_LEGAL_TARGET
                    )
            else:
                try:
                    self._boxed_evolution_request(observation)
                except RedGoalContextError:
                    return RedGoalSkillAvailability.unavailable(
                        GoalUnavailableReason.NO_LEGAL_TARGET
                    )
            if evolved_ref in living_refs:
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
            return RedGoalSkillAvailability.available()
        if self.kind is GoalKind.EVOLVE_SPECIES and (
            evolution_target is None
            or observation.party.species_ids().count(evolution_target[0]) != 1
            or evolved_ref in living_refs
        ):
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
        return RedGoalSkillAvailability.available()

    def _policy(self, observation: RedGoalObservation) -> BalancedTeamPolicy:
        if self.spec.mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT:
            target_species = self._development_target_species_id()
            target = next(
                (
                    member
                    for member in observation.party.members
                    if member.species_id == target_species
                ),
                None,
            )
            if target is None:
                raise RedGoalContextError("targeted development lost its trainee")
            return replace(
                MANSION_TEAM_POLICY,
                minimum_level=target.level + _integer(self.spec.parameters, "level_increment"),
                required_size=self.runtime.profile.manager_config.required_party_size,
            )
        return red_team_development_quantum_policy(
            observation.party,
            self.runtime.profile.manager_config,
            kind=self.kind,
        )

    def _evolution_target(self) -> tuple[int, int] | None:
        if self.spec.mechanic is RedGoalMechanic.DIGLETT_EVOLUTION:
            return DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID
        if self.spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            return (
                _internal_species_id(_text(self.spec.parameters, "source_species_ref")),
                _internal_species_id(_text(self.spec.parameters, "target_species_ref")),
            )
        return None

    def _development_target_species_id(self) -> int:
        if self.spec.mechanic is not RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT:
            raise RedGoalContextError("development provider has no targeted trainee")
        return _internal_species_id(_text(self.spec.parameters, "trainee_species_ref"))

    def _boxed_evolution_request(
        self,
        observation: RedGoalObservation,
    ) -> RedBoxedLevelEvolutionGoalRequest:
        if self.spec.mechanic is not RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            raise RedGoalContextError("boxed evolution request lacks its mechanic")
        source_ref = _text(self.spec.parameters, "source_species_ref")
        target_ref = _text(self.spec.parameters, "target_species_ref")
        source_internal = _internal_species_id(source_ref)
        target_internal = _internal_species_id(target_ref)
        collection = observation.collection_observation
        current_box = collection.current_box_index
        candidates = tuple(
            specimen
            for specimen in collection.specimens
            if specimen.species_ref == source_ref
            and specimen.location is CollectionLocation.BOX
            and specimen.container_index == current_box
        )
        deposit_candidates = tuple(
            (index + 1, member.species_id)
            for index, member in enumerate(observation.party.members)
            if member.species_id not in {BLASTOISE_SPECIES_ID, source_internal, target_internal}
        )
        if (
            len(candidates) < 1
            or source_internal in observation.party.species_ids()
            or observation.party.size != 6
            or current_box >= len(collection.box_counts)
            or collection.box_counts[current_box] >= collection.box_capacity
            or not deposit_candidates
        ):
            raise RedGoalContextError("boxed evolution has no executable storage binding")
        precursor = min(candidates, key=lambda item: item.slot_index)
        deposit_slot, deposit_species = deposit_candidates[-1]
        return RedBoxedLevelEvolutionGoalRequest(
            precursor_internal_species_id=source_internal,
            evolved_internal_species_id=target_internal,
            current_box_index=current_box,
            precursor_box_slot=precursor.slot_index + 1,
            deposit_party_slot=deposit_slot,
            deposit_internal_species_id=deposit_species,
        )

    def _binding_ref(self) -> str:
        if self.spec.mechanic is RedGoalMechanic.DIGLETT_EVOLUTION:
            return "pokemon.red:evolution:diglett-to-dugtrio"
        if self.spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            source = red_species_number(_text(self.spec.parameters, "source_species_ref"))
            target = red_species_number(_text(self.spec.parameters, "target_species_ref"))
            return f"pokemon.red:evolution:national-{source:03d}-to-national-{target:03d}"
        if self.spec.mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT:
            target = red_species_number(_text(self.spec.parameters, "trainee_species_ref"))
            return f"pokemon.red:development:national-{target:03d}:one-level-quantum"
        raise RedGoalContextError("team provider has no targeted binding")


def _targeted_evolution_index(
    before_species: tuple[int, ...],
    after_species: tuple[int, ...],
    *,
    source_species_id: int,
    target_species_id: int,
) -> int | None:
    """Return the sole exact source-to-target party transition, if present."""

    if len(before_species) != len(after_species):
        return None
    changed = tuple(
        index
        for index, (before, after) in enumerate(zip(before_species, after_species, strict=True))
        if before != after
    )
    if len(changed) != 1:
        return None
    index = changed[0]
    if before_species[index] != source_species_id or after_species[index] != target_species_id:
        return None
    return index


def red_team_development_quantum_policy(
    party: PartyObservation,
    config: RedGoalManagerConfig,
    *,
    kind: GoalKind,
) -> BalancedTeamPolicy:
    """Stop one manager development example after one real progress quantum."""

    if not isinstance(party, PartyObservation) or not party.members:
        raise RedGoalContextError("team development lacks a party")
    if not isinstance(config, RedGoalManagerConfig):
        raise TypeError("config must be a RedGoalManagerConfig")
    if kind is GoalKind.EVOLVE_SPECIES:
        required_size = party.size
        minimum_level = 2
    elif kind is GoalKind.DEVELOP_TEAM:
        required_size = config.required_party_size
        minimum_level = min(
            config.required_team_level,
            (party.minimum_level or 1) + 1,
        )
    else:
        raise RedGoalContextError("development quantum received an unsupported goal kind")
    return replace(
        MANSION_TEAM_POLICY,
        minimum_level=max(2, minimum_level),
        required_size=required_size,
    )


def _mart_provider(
    runtime: RedGoalContextRuntime,
    spec: RedGoalProviderSpec,
    actions: CountingExecutor,
) -> RedGoalBindingProvider:
    parameters = spec.parameters
    raw_purchases = parameters.get("purchases")
    if not isinstance(raw_purchases, tuple):
        raise RedGoalContextError("Mart purchases lost their immutable profile form")
    purchases = tuple(
        RedMartPurchase(
            _integer(_parameter_mapping(item), "absolute_index"),
            ItemId(_integer(_parameter_mapping(item), "item_id")),
            _integer(_parameter_mapping(item), "quantity"),
            _integer(_parameter_mapping(item), "unit_price"),
        )
        for item in raw_purchases
    )
    return RedMartResupplyGoalProvider(
        map_id=MapId(_integer(parameters, "map_id")),
        player_x=_integer(parameters, "player_x"),
        player_y=_integer(parameters, "player_y"),
        interaction_direction=_text(parameters, "interaction_direction"),
        purchases=purchases,
        actions=actions,
        reader=runtime.reader,
        emulator=runtime.emulator,
        adapter=runtime.adapter,
    )


def _box_provider(
    runtime: RedGoalContextRuntime,
    spec: RedGoalProviderSpec,
    actions: CountingExecutor,
) -> RedGoalBindingProvider:
    parameters = spec.parameters
    map_id = MapId(_integer(parameters, "map_id"))
    x = _integer(parameters, "player_x")
    y = _integer(parameters, "player_y")

    def boundary(observation: RedGoalObservation) -> bool:
        raw = observation.raw
        return raw.map_id == map_id and raw.player_x == x and raw.player_y == y

    return RedBoxSwitchGoalProvider(
        target_box_index=_integer(parameters, "target_box_index"),
        pc_boundary=boundary,
        actions=actions,
        reader=runtime.reader,
        emulator=runtime.emulator,
        adapter=runtime.adapter,
    )


def _parameter_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RedGoalContextError("profile parameter object is invalid")
    return value


def _integer(parameters: Mapping[str, object], key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedGoalContextError(f"profile parameter {key} is invalid")
    return value


def _text(parameters: Mapping[str, object], key: str) -> str:
    value = parameters.get(key)
    if not isinstance(value, str) or not value:
        raise RedGoalContextError(f"profile parameter {key} is invalid")
    return value


def _internal_species_id(species_ref: str) -> int:
    try:
        return red_internal_species_id(red_species_number(species_ref))
    except ValueError:
        raise RedGoalContextError("profile species reference is invalid") from None


def _directions(parameters: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = parameters.get(key)
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise RedGoalContextError(f"profile parameter {key} is invalid")
    return value


__all__ = (
    "RedGoalContextError",
    "RedGoalContextProviderOffer",
    "RedGoalContextRuntime",
    "build_red_goal_context_runtime",
    "red_team_development_quantum_policy",
)
