"""Production Red runtime for one already-claimed living-dex setup slot.

The resolver is deliberately cold: constructing it or calling it opens no
emulator.  Its returned scope may be entered only by the claim-first campaign,
after the account pair and local episode claim are durable.  The scope first
rebuilds the selected recipe from live cartridge truth, then owns every PyBoy
arm in one ``ExitStack`` so success, ordinary failure, and ``BaseException``
all close without SRAM/RTC writes.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, replace
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.captured_progress import (
    CapturedProgressEnvelope,
    parse_captured_progress,
)
from pokemon_red_completion.claim_first_admission import ClaimFirstRootPair
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import (
    CausallyMeteredEmulator,
    EmulatorFrameObserver,
    PyBoyAdapter,
)
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.gen1_field_moves import (
    Gen1FieldMovePort,
    gen1_field_capabilities,
)
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import (
    RedGoalContextProfile,
    RedGoalContextRuntime,
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_manager import PokemonRedGoalStateAdapter
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexClaimedRootObservation,
    build_red_living_dex_provider_recipe_for_claimed_root,
    derive_red_living_dex_provider_corridors,
    observe_red_living_dex_provider_root_facts,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupRouteRecipe,
    RedLivingDexSetupSlotRecipe,
)
from pokemon_red_completion.red_living_dex_setup_source import (
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
)
from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedSemanticTransportRoute,
)
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_executor import RouteExecutionLimits
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

RED_LIVING_DEX_SETUP_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=16,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)

_MAXIMUM_ROUTE_FLEES = 16
_MAXIMUM_ROUTE_TRAINER_BATTLES = 8
_ROUTE_STABILIZATION_FRAMES = 180


class RedLivingDexProductionRuntimeError(RuntimeError):
    """The postclaim Red resolver or one isolated runtime differs."""


@dataclass(frozen=True, slots=True)
class RedLivingDexProductionRuntimeLimits:
    """Process-wide controller limits shared by every isolated arm."""

    maximum_controller_actions: int
    maximum_emulator_frames: int

    def __post_init__(self) -> None:
        if (
            type(self.maximum_controller_actions) is not int  # noqa: E721
            or self.maximum_controller_actions <= 0
            or type(self.maximum_emulator_frames) is not int  # noqa: E721
            or self.maximum_emulator_frames <= 0
        ):
            raise RedLivingDexProductionRuntimeError(
                "production runtime limits must be positive"
            )


class RedLivingDexFrozenRecipeAccess(Protocol):
    """Authenticated recipe access shared by train and development admissions."""

    def __post_init__(self) -> None: ...

    @property
    def template_ordinal(self) -> int: ...

    def require_resolved_recipe(self, recipe: RedLivingDexSetupSlotRecipe) -> None: ...


@dataclass(frozen=True, slots=True)
class RedLivingDexProductionSetupResolver:
    """Cold callable returning one controller-capable postclaim scope."""

    rom_path: Path
    rom_bytes: bytes
    producer_execution_identity: RedLivingDexSetupExecutionIdentity
    runtime_limits: RedLivingDexProductionRuntimeLimits | None = None
    frame_observer: EmulatorFrameObserver | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rom_path, Path):
            raise TypeError("production Red resolver needs a ROM Path")
        if not isinstance(self.rom_bytes, bytes) or not self.rom_bytes:
            raise TypeError("production Red resolver needs immutable ROM bytes")
        if hashlib.sha256(self.rom_bytes).hexdigest() != POKEMON_RED_US_REV_0.sha256:
            raise RedLivingDexProductionRuntimeError(
                "production resolver cartridge differs from Red"
            )
        if not isinstance(
            self.producer_execution_identity,
            RedLivingDexSetupExecutionIdentity,
        ):
            raise TypeError("production resolver needs its producer identity")
        self.producer_execution_identity.__post_init__()
        if self.runtime_limits is not None:
            if not isinstance(
                self.runtime_limits,
                RedLivingDexProductionRuntimeLimits,
            ):
                raise TypeError("production resolver limits differ")
            self.runtime_limits.__post_init__()
        if self.frame_observer is not None and not isinstance(
            self.frame_observer,
            EmulatorFrameObserver,
        ):
            raise TypeError("production resolver frame observer differs")

    def __call__(
        self,
        frozen: RedLivingDexFrozenRecipeAccess,
        root: RedLivingDexAuthenticatedSetupRoot,
        pair_claim: ClaimFirstRootPair,
        *,
        meter: RedLivingDexSetupEffectMeter,
    ) -> AbstractContextManager[RedLivingDexResolvedSetupSlot]:
        # Returning this object is intentionally runtime-free.  Emulator
        # construction begins only in its __enter__, which the campaign calls
        # after both durable claims and plan reauthentication.
        return _ProductionResolverScope(
            resolver=self,
            frozen=frozen,
            root=root,
            pair_claim=pair_claim,
            meter=meter,
        )

    def build_emulator(self, meter: RedLivingDexSetupEffectMeter) -> Any:
        if type(meter) is not RedLivingDexSetupEffectMeter:
            raise TypeError("production resolver needs the concrete effect meter")
        observer = (
            None
            if self.frame_observer is None
            else _MeteredFrameObserver(
                self.frame_observer,
                meter=meter,
            )
        )
        return PyBoyAdapter(
            self.rom_path,
            watch=False,
            speed=None,
            expected_rom=POKEMON_RED_US_REV_0,
            frame_observer=observer,
        )


@dataclass(slots=True)
class _ProductionResolverScope(AbstractContextManager[RedLivingDexResolvedSetupSlot]):
    resolver: RedLivingDexProductionSetupResolver
    frozen: RedLivingDexFrozenRecipeAccess
    root: RedLivingDexAuthenticatedSetupRoot
    pair_claim: ClaimFirstRootPair
    meter: RedLivingDexSetupEffectMeter
    _stack: ExitStack | None = None

    def __enter__(self) -> RedLivingDexResolvedSetupSlot:
        if self._stack is not None:
            raise RedLivingDexProductionRuntimeError(
                "production resolver scope cannot be entered twice"
            )
        self.frozen.__post_init__()
        self.root.__post_init__()
        self.pair_claim.__post_init__()
        if (
            self.pair_claim.logical_root_sha256 != self.root.root_consumption_sha256
            or self.pair_claim.physical_root_sha256 != self.root.physical_root_sha256
        ):
            raise RedLivingDexProductionRuntimeError(
                "production resolver received another claimed root"
            )
        if type(self.meter) is not RedLivingDexSetupEffectMeter:
            raise TypeError("production resolver needs the concrete effect meter")

        stack = ExitStack()
        self._stack = stack
        try:
            world = StrategicScenarioRouteWorld.from_rom(self.resolver.rom_bytes)
            corridors = derive_red_living_dex_provider_corridors(world)
            observation = self._observe_claimed_root()
            recipe = build_red_living_dex_provider_recipe_for_claimed_root(
                self.frozen.template_ordinal,
                observation,
                world=world,
                corridors=corridors,
                expected_rom_sha256=self.resolver.producer_execution_identity.rom_sha256,
            )
            self.frozen.require_resolved_recipe(recipe)
            factory = _ProductionArmFactory(
                resolver=self.resolver,
                stack=stack,
                root=self.root,
                world=world,
                producer_execution_identity=(self.resolver.producer_execution_identity),
                meter=self.meter,
            )
            return RedLivingDexResolvedSetupSlot(
                recipe=recipe,
                producer_execution_identity=(self.resolver.producer_execution_identity),
                arm_factory=factory,
                title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
                runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
            )
        except BaseException:
            stack.close()
            self._stack = None
            raise

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        stack = self._stack
        self._stack = None
        if stack is None:
            return False
        return bool(stack.__exit__(exception_type, exception, traceback))

    def _observe_claimed_root(self) -> RedLivingDexClaimedRootObservation:
        with ExitStack() as observer_stack:
            raw = self.resolver.build_emulator(self.meter)
            _register_emulator(observer_stack, raw)
            _start_emulator(raw)
            before = self.meter.checkpoint()
            raw_frame_before = raw.frame_count
            raw.load_state_bytes(self.root.state_bytes)
            readback = raw.save_state_bytes()
            if (
                not isinstance(readback, bytes)
                or hashlib.sha256(readback).digest()
                != hashlib.sha256(self.root.state_bytes).digest()
                or raw.frame_count != raw_frame_before
                or raw.pressed_buttons != frozenset()
                or self.meter.checkpoint() != before
            ):
                raise RedLivingDexProductionRuntimeError(
                    "claimed root restore changed protected effects or bytes"
                )
            reader = PokemonRedStateReader(raw)
            envelope = parse_captured_progress(
                self.root.envelope_bytes,
                state_bytes=self.root.state_bytes,
            )
            goal_observation = PokemonRedGoalStateAdapter(
                reader,
                CapturedPokemonRedObserver(reader, COMPLETION_QUEST, envelope),
                COMPLETION_QUEST,
            ).observe()
            traversal = Gen1TraversalObserver(
                reader,
                hazard_projector=Gen1TrainerSightProjector(
                    self.resolver.rom_bytes,
                    reader,
                ),
                capability_projector=lambda observed: gen1_field_capabilities(
                    raw,
                    observed,
                ),
            ).observe()
            facts = observe_red_living_dex_provider_root_facts(goal_observation)
            if (
                raw.frame_count != raw_frame_before
                or raw.pressed_buttons != frozenset()
                or self.meter.checkpoint() != before
            ):
                raise RedLivingDexProductionRuntimeError(
                    "claimed root observation changed protected effects"
                )
            return RedLivingDexClaimedRootObservation(
                root=self.root,
                traversal=traversal,
                facts=facts,
                observed_state_sha256=self.root.state_sha256,
                pair_claim=self.pair_claim,
            )


class _ProductionArmFactory:
    """Construct fresh arms and register every close before returning."""

    def __init__(
        self,
        *,
        resolver: RedLivingDexProductionSetupResolver,
        stack: ExitStack,
        root: RedLivingDexAuthenticatedSetupRoot,
        world: StrategicScenarioRouteWorld,
        producer_execution_identity: RedLivingDexSetupExecutionIdentity,
        meter: RedLivingDexSetupEffectMeter,
    ) -> None:
        self._resolver = resolver
        self._stack = stack
        self._root = root
        self._world = world
        self._identity = producer_execution_identity
        self._meter = meter
        self._sequence = 0

    def __call__(
        self,
        recipe: RedLivingDexSetupSlotRecipe,
        purpose: str,
        ordinal: int,
    ) -> _ProductionArm:
        if purpose not in {"construction", "candidate", "final_restore"}:
            raise RedLivingDexProductionRuntimeError("production setup arm purpose differs")
        raw = self._resolver.build_emulator(self._meter)
        _register_emulator(self._stack, raw)
        _start_emulator(raw)
        metered = _build_metered_emulator(
            raw,
            self._meter,
            limits=self._resolver.runtime_limits,
        )
        reader = PokemonRedStateReader(metered)
        controller = FrameSafeExecutor(
            metered,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        metered_actions = _AttemptMeteredActionExecutor(
            controller,
            emulator=metered,
            meter=self._meter,
            limits=self._resolver.runtime_limits,
        )
        actions = _FieldAwareCountingExecutor(
            metered_actions,
            reader=reader,
            emulator=metered,
            cut_block_swaps={swap.before: swap.after for swap in self._world.rules.cut_block_swaps},
        )
        traversal = Gen1TraversalObserver(
            reader,
            hazard_projector=Gen1TrainerSightProjector(
                self._resolver.rom_bytes,
                reader,
            ),
            capability_projector=lambda observed: gen1_field_capabilities(
                metered,
                observed,
            ),
        )
        arm = _ProductionArm(
            recipe=recipe,
            purpose=purpose,
            ordinal=ordinal,
            sequence=self._sequence,
            emulator=metered,
            reader=reader,
            actions=actions,
            traversal_observer=traversal,
            world=self._world,
            root=self._root,
            execution_identity=self._identity,
            meter=self._meter,
        )
        self._sequence += 1
        return arm


@dataclass(slots=True)
class _ProductionArm:
    recipe: RedLivingDexSetupSlotRecipe
    purpose: str
    ordinal: int
    sequence: int
    emulator: CausallyMeteredEmulator
    reader: PokemonRedStateReader
    actions: _FieldAwareCountingExecutor
    traversal_observer: Gen1TraversalObserver
    world: StrategicScenarioRouteWorld
    root: RedLivingDexAuthenticatedSetupRoot
    execution_identity: RedLivingDexSetupExecutionIdentity
    meter: RedLivingDexSetupEffectMeter

    @property
    def arm_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "ordinal": self.ordinal,
                "producer_execution_identity_sha256": (self.execution_identity.identity_sha256),
                "purpose": self.purpose,
                "recipe_sha256": self.recipe.recipe_sha256,
                "runtime_factory_sha256": RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
                "schema": "pokemon.red.living-dex-isolated-arm.v1",
                "sequence": self.sequence,
            }
        )

    @property
    def execution_identity_sha256(self) -> str:
        return self.execution_identity.identity_sha256

    @property
    def effect_meter(self) -> RedLivingDexSetupEffectMeter:
        return self.meter

    def _profile(self) -> RedGoalContextProfile:
        if self.purpose == "candidate":
            return self.recipe.providers[self.ordinal].profile
        return self.recipe.providers[0].profile

    def observe_fresh(self) -> FreshRedGoalObservation:
        capture = self._current_capture()
        context = self.build_goal_context(self._profile(), capture)
        observation = context.adapter.observe()
        traversal = self.traversal_observer.observe()
        provisional = FreshRedGoalObservation(
            "0" * 64,
            observation,
            traversal,
        )
        return replace(
            provisional,
            observation_sha256=(red_living_dex_setup_fresh_observation_sha256(provisional)),
        )

    def build_route(
        self,
        recipe: RedLivingDexSetupRouteRecipe,
        *,
        origin_observation_sha256: str,
    ) -> RedSemanticTransportRoute:
        interruption = Gen1RouteInterruptionHandler(
            self.actions,
            self.reader,
            maximum_flees=_MAXIMUM_ROUTE_FLEES,
            maximum_trainer_battles=_MAXIMUM_ROUTE_TRAINER_BATTLES,
            stabilization_frames=_ROUTE_STABILIZATION_FRAMES,
            route_name="claim-first Red living-dex setup route",
        )
        return RedSemanticTransportRoute(
            binding_ref=f"red-setup-{recipe.recipe_sha256[:20]}",
            origin_observation_sha256=origin_observation_sha256,
            planner_binding_sha256=recipe.planner_binding_sha256,
            plan=recipe.plan,
            actions=self.actions,
            traversal_observer=self.traversal_observer,
            emulator=self.emulator,
            interruption_handler=interruption,
            replanner=self.world.replanner(),
            route_limits=RED_LIVING_DEX_SETUP_ROUTE_LIMITS,
        )

    def build_goal_context(
        self,
        profile: RedGoalContextProfile,
        capture: GoalManagerContextCapture,
    ) -> RedGoalContextRuntime:
        return build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=self.emulator,
            reader=self.reader,
            boxed_level_evolution_executor=_forbid_provider_execution,
        )

    def _current_capture(self) -> GoalManagerContextCapture:
        state = self.emulator.save_state_bytes()
        source = parse_captured_progress(
            self.root.envelope_bytes,
            state_bytes=self.root.state_bytes,
        )
        envelope = CapturedProgressEnvelope(
            state_sha256=hashlib.sha256(state).hexdigest(),
            checkpoint_id=source.checkpoint_id,
            checkpoint_label=source.checkpoint_label,
            checkpoints_completed=source.checkpoints_completed,
            checkpoints_total=source.checkpoints_total,
            verified_objective_ids=source.verified_objective_ids,
        )
        envelope_bytes = (
            json.dumps(
                envelope.to_dict(),
                ensure_ascii=True,
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        return parse_goal_manager_context_capture(state, envelope_bytes)


@dataclass(slots=True)
class _MeteredFrameObserver:
    """Translate each fresh emulator onto the shared metered frame timeline."""

    delegate: EmulatorFrameObserver
    meter: RedLivingDexSetupEffectMeter
    _disabled: bool = False
    _last_logical_frame: int = 0
    _pending_projection: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.delegate, EmulatorFrameObserver):
            raise TypeError("metered frame observer needs a frame observer")
        if type(self.meter) is not RedLivingDexSetupEffectMeter:
            raise TypeError("metered frame observer needs the concrete effect meter")

    def wants_frame(self, logical_frame: int) -> bool:
        if self._disabled:
            return False
        try:
            projected = self._project(logical_frame)
            self._last_logical_frame = logical_frame
            wanted = self.delegate.wants_frame(projected)
            self._pending_projection = projected if wanted else None
            return wanted
        except Exception:
            self._disabled = True
            self._pending_projection = None
            return False

    def publish_frame(
        self,
        width: int,
        height: int,
        rgb: bytes,
        logical_frame: int,
    ) -> None:
        if self._disabled:
            return
        try:
            if (
                self._pending_projection is None
                or logical_frame != self._last_logical_frame
            ):
                raise ValueError("unrequested frame")
            projected = self._pending_projection
            self._pending_projection = None
            self.delegate.publish_frame(
                width,
                height,
                rgb,
                projected,
            )
        except Exception:
            # Rendering is intentionally outside the controller trust boundary.
            # A broken or closed dashboard can remove observability, never alter
            # the selected skill's execution or factual outcome.
            self._disabled = True
            self._pending_projection = None

    def _project(self, logical_frame: int) -> int:
        if (
            type(logical_frame) is not int  # noqa: E721
            or logical_frame < self._last_logical_frame
        ):
            raise TypeError("emulator logical frame differs")
        return (
            self.meter.emulator_frames
            + logical_frame
            - self._last_logical_frame
        )


def _build_metered_emulator(
    delegate: Any,
    meter: RedLivingDexSetupEffectMeter,
    *,
    limits: RedLivingDexProductionRuntimeLimits | None = None,
) -> CausallyMeteredEmulator:
    """Bind campaign accounting to the emulator-owned primitive boundary."""

    def admit_frames(frames: int) -> None:
        if limits is not None and (
            type(frames) is not int  # noqa: E721
            or frames < 0
            or meter.emulator_frames + frames > limits.maximum_emulator_frames
        ):
            raise RedLivingDexProductionRuntimeError(
                "production emulator frame bound exhausted"
            )

    return CausallyMeteredEmulator(
        delegate,
        record_frames=meter.record_emulator_frames,
        admit_frames=admit_frames,
    )


class _AttemptMeteredActionExecutor:
    """Reserve action authority first and reconcile frames even on failure."""

    __slots__ = ("_delegate", "_emulator", "_limits", "_meter")

    def __init__(
        self,
        delegate: Any,
        *,
        emulator: CausallyMeteredEmulator,
        meter: RedLivingDexSetupEffectMeter,
        limits: RedLivingDexProductionRuntimeLimits | None = None,
    ) -> None:
        self._delegate = delegate
        self._emulator = emulator
        self._meter = meter
        self._limits = limits

    def execute(self, action: MacroAction) -> object:
        if (
            self._limits is not None
            and self._meter.controller_actions
            >= self._limits.maximum_controller_actions
        ):
            raise RedLivingDexProductionRuntimeError(
                "production controller action bound exhausted"
            )
        before_frame = self._emulator.frame_count
        before_meter_frames = self._meter.emulator_frames
        self._meter.record_controller_actions()
        try:
            return self._delegate.execute(action)
        finally:
            actual_delta = self._emulator.frame_count - before_frame
            metered_delta = self._meter.emulator_frames - before_meter_frames
            if actual_delta < 0 or metered_delta < 0 or metered_delta > actual_delta:
                raise RedLivingDexProductionRuntimeError(
                    "production action frame reconciliation differs"
                )
            if actual_delta > metered_delta:
                self._meter.record_emulator_frames(actual_delta - metered_delta)


class _SuccessfulCountingDelegate:
    __slots__ = ("_owner", "_raw")

    def __init__(
        self,
        owner: _FieldAwareCountingExecutor,
        raw: _AttemptMeteredActionExecutor,
    ) -> None:
        self._owner = owner
        self._raw = raw

    def execute(self, action: MacroAction) -> object:
        result = self._raw.execute(action)
        self._owner.actions_executed += 1
        return result


class _FieldAwareCountingExecutor(CountingExecutor):
    """Count actual compiled macro dispatches, including field-menu pulses."""

    def __init__(
        self,
        raw: _AttemptMeteredActionExecutor,
        *,
        reader: PokemonRedStateReader,
        emulator: CausallyMeteredEmulator,
        cut_block_swaps: dict[int, int],
    ) -> None:
        super().__init__(raw)  # type: ignore[arg-type]
        self._raw = raw
        self._field = Gen1FieldMovePort(
            _SuccessfulCountingDelegate(self, raw),
            reader,
            emulator,
            cut_block_swaps=cut_block_swaps,
        )

    def execute(self, action: MacroAction) -> object:
        if action.kind is MacroActionKind.FIELD_MOVE:
            return self._field.execute(action)
        result = self._raw.execute(action)
        self.actions_executed += 1
        return result


def _register_emulator(stack: ExitStack, emulator: Any) -> None:
    close = getattr(emulator, "close", None)
    if not callable(close):
        raise RedLivingDexProductionRuntimeError("production emulator lacks a close boundary")
    stack.callback(close)


def _start_emulator(emulator: Any) -> None:
    start = getattr(emulator, "start", None)
    if not callable(start):
        raise RedLivingDexProductionRuntimeError("production emulator lacks a start boundary")
    frame_before = getattr(emulator, "frame_count", None)
    pressed_before = getattr(emulator, "pressed_buttons", None)
    started = start()
    if (
        started is not emulator
        or type(frame_before) is not int  # noqa: E721
        or frame_before < 0
        or getattr(emulator, "frame_count", None) != frame_before
        or pressed_before != frozenset()
        or getattr(emulator, "pressed_buttons", None) != frozenset()
    ):
        raise RedLivingDexProductionRuntimeError(
            "production emulator start changed protected effects"
        )


def _forbid_provider_execution(*_args: object, **_kwargs: object) -> GoalExecutionReport:
    raise RedLivingDexProductionRuntimeError(
        "setup validation may construct but never execute a provider"
    )


__all__ = [
    "RED_LIVING_DEX_RUNTIME_FACTORY_SHA256",
    "RED_LIVING_DEX_TITLE_ADAPTER_SHA256",
    "RedLivingDexProductionRuntimeError",
    "RedLivingDexProductionRuntimeLimits",
    "RedLivingDexProductionSetupResolver",
]
