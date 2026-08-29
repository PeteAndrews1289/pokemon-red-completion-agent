"""Red live adapter for the title-neutral selected-arm causal journal.

A validated setup capture already contains the exact shared-origin bytes, one
identity-free policy menu, and an authenticated provider proof for every row.
This adapter reconstructs only the row chosen by the journal.  Runtime opening,
state restore, and observation stay action-free behind the locked gate; the
selected semantic route and provider execute only after the journal has durably
recorded controller release.

Red mechanics remain private here.  The journal and learner receive the same
menu, propensity, outcome, and example schema that a Crystal adapter must use.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.goal_manager_context_catalog import (
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalEffectCheckpoint,
    LivingDexCausalIdentity,
    LivingDexCausalObservation,
    LivingDexCausalResolvedArm,
    LivingDexCausalScenario,
    LivingDexControllerGate,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedOutcome,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupForkRuntime,
    RedLivingDexSetupForkRuntimeFactory,
    RedLivingDexSetupRecipeError,
    RedLivingDexSetupSlotRecipe,
    RedLivingDexValidatedSetupCapture,
    _derived_envelope_bytes,
    _execute_authenticated_route,
    _load_and_read_back,
    _observe_arm,
    _open_arm,
    _require_fresh_at,
    _save_state_bytes,
    _validate_registry_offer,
)
from pokemon_red_completion.red_living_dex_setup_source import (
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupExecutionIdentity,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
)

RED_LIVING_DEX_CAUSAL_ADAPTER_SCHEMA = "pokemon.red.private-living-dex-causal-adapter.v1"
RED_LIVING_DEX_CAUSAL_OUTCOME_PROVENANCE_SCHEMA = (
    "pokemon.red.private-living-dex-causal-outcome-provenance.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedLivingDexCausalAdapterError(RuntimeError):
    """A Red capture cannot cross the shared causal journal honestly."""


class RedLivingDexCausalEffectMeter:
    """Narrow title-neutral view of the runtime's comprehensive Red meter."""

    __slots__ = ("_binding_sha256", "_meter")

    def __init__(self, meter: RedLivingDexSetupEffectMeter, binding_sha256: str) -> None:
        if type(meter) is not RedLivingDexSetupEffectMeter:
            raise TypeError("Red causal adapter needs the comprehensive setup meter")
        self._meter = meter
        self._binding_sha256 = _require_sha256(binding_sha256, subject="effect meter")

    @property
    def binding_sha256(self) -> str:
        return self._binding_sha256

    @property
    def recovery_instance_sha256(self) -> str:
        return self._meter.recovery_instance_sha256

    def checkpoint(self) -> LivingDexCausalEffectCheckpoint:
        checkpoint = self._meter.checkpoint()
        return LivingDexCausalEffectCheckpoint(
            checkpoint.controller_actions,
            checkpoint.emulator_frames,
        )


@dataclass(slots=True)
class _SelectedRuntimeState:
    arm: RedLivingDexSetupForkRuntime
    before: FreshRedGoalObservation
    effect_before: LivingDexCausalEffectCheckpoint
    binding: ExecutableGoalBinding | None = None
    report: GoalExecutionReport | None = None
    route_report_sha256: str | None = None
    execution_exception_type: str | None = None
    provenance_failed: bool = False


RedLivingDexCausalRuntimeResolver = Callable[
    [],
    AbstractContextManager[RedLivingDexResolvedSetupSlot],
]


def build_red_living_dex_causal_scenario(
    recipe: RedLivingDexSetupSlotRecipe,
    capture: RedLivingDexValidatedSetupCapture,
    *,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
    arm_factory: RedLivingDexSetupForkRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
    setup_terminal_sha256: str,
    setup_pair_claim_sha256: str,
    causal_source_commit: str,
    causal_runner_sha256: str,
    upstream_lineage_sha256: str | None = None,
) -> LivingDexCausalScenario:
    """Bind a currently available Red arm factory to the shared journal.

    This compatibility entrypoint is useful for a setup validator that still
    owns its resolver scope.  Production recovery should use
    :func:`build_red_living_dex_causal_scenario_from_capture` so no runtime
    capability exists until the journal has selected one row.
    """

    if not isinstance(recipe, RedLivingDexSetupSlotRecipe):
        raise TypeError("Red causal adapter needs a setup recipe")
    recipe.__post_init__()
    if not isinstance(capture, RedLivingDexValidatedSetupCapture):
        raise TypeError("Red causal adapter needs a validated setup capture")
    capture.__post_init__()
    if not isinstance(setup_execution_identity, RedLivingDexSetupExecutionIdentity):
        raise TypeError("Red causal adapter needs its setup execution identity")
    setup_execution_identity.__post_init__()
    if not callable(arm_factory):
        raise TypeError("Red causal adapter needs an isolated-arm factory")
    if (
        recipe.recipe_sha256 != capture.recipe_sha256
        or recipe.slot_sha256 != capture.binding.slot_sha256
        or capture.execution_identity_sha256 != setup_execution_identity.identity_sha256
        or capture.binding.execution_identity_sha256
        != setup_execution_identity.identity_sha256
        or recipe.available_option_kinds != capture.binding.available_option_kinds
        or tuple(item.recipe_sha256 for item in recipe.providers)
        != tuple(item.provider_recipe_sha256 for item in capture.binding.option_bindings)
    ):
        raise RedLivingDexCausalAdapterError("Red causal setup join differs")

    @contextmanager
    def resolve_runtime() -> Iterator[RedLivingDexResolvedSetupSlot]:
        yield RedLivingDexResolvedSetupSlot(
            recipe=recipe,
            producer_execution_identity=setup_execution_identity,
            arm_factory=arm_factory,
            title_adapter_sha256=canonical_sha256(
                {
                    "adapter": RED_LIVING_DEX_CAUSAL_ADAPTER_SCHEMA,
                    "purpose": "validated-live-factory",
                }
            ),
            runtime_factory_sha256=canonical_sha256(
                {
                    "purpose": "validated-live-factory",
                    "setup_execution_identity_sha256": (
                        setup_execution_identity.identity_sha256
                    ),
                }
            ),
        )

    return build_red_living_dex_causal_scenario_from_capture(
        capture,
        setup_execution_identity=setup_execution_identity,
        runtime_resolver=resolve_runtime,
        meter=meter,
        setup_terminal_sha256=setup_terminal_sha256,
        setup_pair_claim_sha256=setup_pair_claim_sha256,
        causal_source_commit=causal_source_commit,
        causal_runner_sha256=causal_runner_sha256,
        upstream_lineage_sha256=upstream_lineage_sha256,
    )


def build_red_living_dex_causal_scenario_from_capture(
    capture: RedLivingDexValidatedSetupCapture,
    *,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
    runtime_resolver: RedLivingDexCausalRuntimeResolver,
    meter: RedLivingDexSetupEffectMeter,
    setup_terminal_sha256: str,
    setup_pair_claim_sha256: str,
    causal_source_commit: str,
    causal_runner_sha256: str,
    upstream_lineage_sha256: str | None = None,
) -> LivingDexCausalScenario:
    """Bind one capture while keeping every Red runtime behind selection."""

    if not isinstance(capture, RedLivingDexValidatedSetupCapture):
        raise TypeError("Red causal adapter needs a validated setup capture")
    capture.__post_init__()
    if not isinstance(setup_execution_identity, RedLivingDexSetupExecutionIdentity):
        raise TypeError("Red causal adapter needs its setup execution identity")
    setup_execution_identity.__post_init__()
    if not callable(runtime_resolver):
        raise TypeError("Red causal adapter needs a cold runtime resolver")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("Red causal adapter needs the comprehensive setup meter")
    for value, subject in (
        (setup_terminal_sha256, "setup terminal"),
        (setup_pair_claim_sha256, "setup pair claim"),
        (causal_runner_sha256, "causal runner"),
    ):
        _require_sha256(value, subject=subject)
    if not isinstance(causal_source_commit, str) or _GIT_COMMIT.fullmatch(
        causal_source_commit
    ) is None:
        raise RedLivingDexCausalAdapterError("causal source commit differs")
    if (
        capture.execution_identity_sha256 != setup_execution_identity.identity_sha256
        or capture.binding.execution_identity_sha256
        != setup_execution_identity.identity_sha256
        or capture.binding.menu_sha256 != capture.policy_projection.menu.policy_sha256
        or len(capture.binding.option_bindings) < 2
        or len(capture.binding.option_bindings) != len(capture.fork_proofs)
    ):
        raise RedLivingDexCausalAdapterError("Red causal capture join differs")

    binding_sha256s = tuple(
        item.executable_binding_sha256 for item in capture.fork_proofs
    )
    meter_binding_sha256 = canonical_sha256(
        {
            "causal_runner_sha256": causal_runner_sha256,
            "capture_attestation_sha256": capture.attestation.attestation_sha256,
            "schema": "pokemon.red.private-living-dex-causal-effect-meter.v1",
            "setup_execution_identity_sha256": setup_execution_identity.identity_sha256,
        }
    )
    causal_meter = RedLivingDexCausalEffectMeter(meter, meter_binding_sha256)
    lineage_sha256 = (
        canonical_sha256(
            {
                "recipe_sha256": capture.recipe_sha256,
                "schema": "pokemon.red.private-living-dex-causal-lineage.v1",
                "setup_execution_identity_sha256": (
                    setup_execution_identity.identity_sha256
                ),
                "slot_sha256": capture.binding.slot_sha256,
            }
        )
        if upstream_lineage_sha256 is None
        else _require_sha256(
            upstream_lineage_sha256,
            subject="upstream causal lineage",
        )
    )
    origin = capture.policy_projection.origin_policy_observation
    identity = LivingDexCausalIdentity(
        source_commit=causal_source_commit,
        partition=capture.binding.partition.value,
        lineage_sha256=lineage_sha256,
        setup_terminal_sha256=setup_terminal_sha256,
        setup_pair_claim_sha256=setup_pair_claim_sha256,
        setup_attestation_sha256=capture.attestation.attestation_sha256,
        state_sha256=capture.binding.state_sha256,
        envelope_sha256=capture.binding.envelope_sha256,
        menu_sha256=capture.policy_projection.menu.policy_sha256,
        binding_roster_sha256=canonical_sha256(
            {
                "binding_sha256s": list(binding_sha256s),
                "schema": "pokemon.core.living-dex-causal-binding-roster.v1",
            }
        ),
        origin_observation_sha256=canonical_sha256(origin),
        observer_binding_sha256=capture.binding.observer_binding_sha256,
        effect_meter_binding_sha256=causal_meter.binding_sha256,
        runner_sha256=causal_runner_sha256,
    )
    active: list[_SelectedRuntimeState] = []

    @contextmanager
    def resolve_selected(
        index: int,
        gate: LivingDexControllerGate,
    ) -> Iterator[LivingDexCausalResolvedArm]:
        if type(index) is not int or not 0 <= index < len(capture.fork_proofs):  # noqa: E721
            raise RedLivingDexCausalAdapterError("selected Red row differs")
        if active:
            raise RedLivingDexCausalAdapterError("Red selected runtime is already active")
        used_arm_identities: set[str] = set()
        before_resolution = meter.checkpoint()
        try:
            with runtime_resolver() as resolved:
                _require_resolved_runtime(
                    capture,
                    setup_execution_identity=setup_execution_identity,
                    resolved=resolved,
                )
                if meter.checkpoint() != before_resolution:
                    raise RedLivingDexCausalAdapterError(
                        "Red cold runtime resolution changed protected effects"
                    )
                recipe = resolved.recipe
                arm = _open_arm(
                    resolved.arm_factory,
                    recipe,
                    purpose="candidate",
                    ordinal=index,
                    execution_identity=setup_execution_identity,
                    meter=meter,
                    used_arm_identities=used_arm_identities,
                )
                _load_and_read_back(
                    arm,
                    capture.state_bytes,
                    meter=meter,
                    subject="causal selected origin",
                )
                before = _observe_arm(
                    arm,
                    meter=meter,
                    subject="causal selected origin",
                )
                if (
                    gate.released
                    or before.observation_sha256 != capture.origin_observation_sha256
                    or before.observation.public_dict() != origin
                ):
                    raise RedLivingDexCausalAdapterError("Red selected origin differs")
                state = _SelectedRuntimeState(arm, before, causal_meter.checkpoint())
                active.append(state)

                def execute(controller_gate: LivingDexControllerGate) -> None:
                    controller_gate.require_released()
                    try:
                        _execute_selected_provider(
                            state,
                            recipe,
                            capture,
                            selected_index=index,
                            meter=meter,
                        )
                    except BaseException as error:
                        state.execution_exception_type = type(error).__name__
                        if state.binding is None:
                            state.provenance_failed = True
                        raise

                def action_trace() -> dict[str, object]:
                    return _action_trace(state, capture, selected_index=index, meter=meter)

                try:
                    yield LivingDexCausalResolvedArm(
                        binding_sha256s[index],
                        causal_meter,
                        execute,
                        action_trace,
                    )
                finally:
                    active.clear()
        except RedLivingDexSetupRecipeError as error:
            raise RedLivingDexCausalAdapterError(str(error)) from None
        finally:
            active.clear()

    def observe_after() -> LivingDexCausalObservation:
        if len(active) != 1:
            raise RedLivingDexCausalAdapterError("Red causal observer lacks an active runtime")
        return _observe_selected_runtime(
            active[0],
            capture,
            meter=meter,
        )

    return LivingDexCausalScenario(
        identity,
        capture.policy_projection.menu,
        binding_sha256s,
        origin,
        causal_meter,
        resolve_selected,
        observe_after,
    )


def _require_resolved_runtime(
    capture: RedLivingDexValidatedSetupCapture,
    *,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
    resolved: RedLivingDexResolvedSetupSlot,
) -> None:
    if not isinstance(resolved, RedLivingDexResolvedSetupSlot):
        raise TypeError("Red causal runtime resolver returned another type")
    resolved.__post_init__()
    recipe = resolved.recipe
    if (
        recipe.recipe_sha256 != capture.recipe_sha256
        or recipe.slot_sha256 != capture.binding.slot_sha256
        or resolved.producer_execution_identity != setup_execution_identity
        or tuple(item.recipe_sha256 for item in recipe.providers)
        != tuple(
            item.provider_recipe_sha256 for item in capture.binding.option_bindings
        )
        or recipe.available_option_kinds != capture.binding.available_option_kinds
    ):
        raise RedLivingDexCausalAdapterError("Red resolved causal runtime differs")


def _execute_selected_provider(
    state: _SelectedRuntimeState,
    recipe: RedLivingDexSetupSlotRecipe,
    capture: RedLivingDexValidatedSetupCapture,
    *,
    selected_index: int,
    meter: RedLivingDexSetupEffectMeter,
) -> None:
    provider = recipe.providers[selected_index]
    proof = capture.fork_proofs[selected_index]
    expected = capture.binding.option_bindings[selected_index]
    fresh = state.before
    route_report_sha256: str | None = None
    if provider.route is not None:
        fresh, route_report_sha256, _actions, _frames = _execute_authenticated_route(
            state.arm,
            provider.route,
            fresh,
            meter=meter,
        )
    destination_state = _save_state_bytes(
        state.arm.emulator,
        meter=meter,
        subject="causal selected destination",
    )
    destination_envelope = _derived_envelope_bytes(
        capture.envelope_bytes,
        source_state_bytes=capture.state_bytes,
        state_bytes=destination_state,
    )
    context_capture = parse_goal_manager_context_capture(
        destination_state,
        destination_envelope,
    )
    context_before = meter.checkpoint()
    context = state.arm.build_goal_context(provider.profile, context_capture)
    if meter.checkpoint() != context_before:
        raise RedLivingDexCausalAdapterError(
            "Red causal provider construction changed protected effects"
        )
    if (
        type(context) is not RedGoalContextRuntime
        or context.profile.profile_sha256 != provider.profile.profile_sha256
        or context.capture is not context_capture
        or context.capture.state_sha256 != hashlib.sha256(destination_state).hexdigest()
        or context.emulator is not state.arm.emulator
    ):
        raise RedLivingDexCausalAdapterError("Red causal provider context differs")
    observation_before = meter.checkpoint()
    context_observation = context.adapter.observe()
    if meter.checkpoint() != observation_before:
        raise RedLivingDexCausalAdapterError(
            "Red causal provider observation changed protected effects"
        )
    context_fresh = FreshRedGoalObservation(
        red_living_dex_setup_fresh_observation_sha256(
            FreshRedGoalObservation(
                "0" * 64,
                context_observation,
                fresh.traversal,
            )
        ),
        context_observation,
        fresh.traversal,
    )
    _require_fresh_at(
        context_fresh,
        recipe.origin_boundary if provider.route is None else provider.route.terminal_boundary,
        "causal provider observation",
    )
    offer_before = meter.checkpoint()
    observed = context.offer_for(provider.goal_kind, context_observation, state.arm.actions)
    if meter.checkpoint() != offer_before:
        raise RedLivingDexCausalAdapterError(
            "Red causal provider offer changed protected effects"
        )
    (
        binding,
        fresh_sha256,
        executable_sha256,
        offer_sha256,
        family_sha256,
    ) = _validate_registry_offer(provider, context_fresh, observed)
    if (
        fresh_sha256 != proof.fresh_observation_sha256
        or executable_sha256 != proof.executable_binding_sha256
        or offer_sha256 != proof.provider_offer_sha256
        or family_sha256 != proof.family_sha256
        or route_report_sha256 != proof.route_report_sha256
        or expected.expected_executable_binding_sha256 != executable_sha256
        or expected.expected_provider_offer_sha256 != offer_sha256
        or expected.expected_fresh_observation_sha256 != fresh_sha256
        or expected.expected_family_sha256 != family_sha256
    ):
        raise RedLivingDexCausalAdapterError("Red causal provider proof differs")
    state.binding = binding
    state.route_report_sha256 = route_report_sha256
    meter.record_provider_execution()
    report = binding.execute()
    if not isinstance(report, GoalExecutionReport):
        state.provenance_failed = True
        raise RedLivingDexCausalAdapterError("Red causal provider returned invalid evidence")
    state.report = report


def _observe_selected_runtime(
    state: _SelectedRuntimeState,
    capture: RedLivingDexValidatedSetupCapture,
    *,
    meter: RedLivingDexSetupEffectMeter,
) -> LivingDexCausalObservation:
    after = _observe_arm(
        state.arm,
        meter=meter,
        subject="causal selected outcome",
    )
    verification: GoalVerification | None = None
    if state.binding is not None and state.report is not None:
        verification = state.binding.verify(state.report)
        if not isinstance(verification, GoalVerification):
            raise RedLivingDexCausalAdapterError(
                "Red causal provider returned invalid verification"
            )
    outcome = (
        LivingDexObservedOutcome(
            LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.PROVENANCE_FAILED,
        )
        if state.provenance_failed
        else _red_outcome(
            state.before.observation,
            after.observation,
            verification=verification,
            before_effects=capture.policy_projection,
            action_frame_before=state.effect_before,
            meter=meter,
        )
    )
    provenance = {
        "after_observation": after.observation.public_dict(),
        "after_observation_sha256": after.observation_sha256,
        "before_observation": state.before.observation.public_dict(),
        "before_observation_sha256": state.before.observation_sha256,
        "execution_exception_type": state.execution_exception_type,
        "goal_report_sha256": (
            None if state.report is None else _goal_report_sha256(state.report)
        ),
        "observer_binding_sha256": capture.binding.observer_binding_sha256,
        "schema": RED_LIVING_DEX_CAUSAL_OUTCOME_PROVENANCE_SCHEMA,
        "verification_status": (
            None if verification is None else verification.status.value
        ),
    }
    return LivingDexCausalObservation(outcome, provenance)


def _red_outcome(
    before: RedGoalObservation,
    after: RedGoalObservation,
    *,
    verification: GoalVerification | None,
    before_effects: object,
    action_frame_before: LivingDexCausalEffectCheckpoint,
    meter: RedLivingDexSetupEffectMeter,
) -> LivingDexObservedOutcome:
    from pokemon_red_completion.red_living_dex_setup_policy import (
        RedLivingDexSetupPolicyProjection,
    )

    if not isinstance(before_effects, RedLivingDexSetupPolicyProjection):
        raise TypeError("Red causal outcome needs its normalization projection")
    before_public = before.public_dict()
    after_public = after.public_dict()
    del before_public, after_public
    before_collection = before.evidence.living_collection
    after_collection = after.evidence.living_collection
    registered_delta = _progress_delta(
        before.evidence.registered_collection.completed,
        after.evidence.registered_collection.completed,
        after.evidence.registered_collection.target,
    )
    living_delta = _progress_delta(
        before_collection.completed,
        after_collection.completed,
        after_collection.target,
    )
    level_delta = _progress_delta(
        before.evidence.level_collection.completed,
        after.evidence.level_collection.completed,
        after.evidence.level_collection.target,
    )
    story_delta = _progress_delta(
        before.evidence.story.completed,
        after.evidence.story.completed,
        after.evidence.story.target,
    )
    dependency_pressure_delta = max(
        0.0,
        max(before.situation.story_pressure, before.situation.evolution_pressure)
        - max(after.situation.story_pressure, after.situation.evolution_pressure),
    )
    checkpoint = meter.checkpoint()
    actions = max(0, checkpoint.controller_actions - action_frame_before.controller_actions)
    frames = max(0, checkpoint.emulator_frames - action_frame_before.emulator_frames)
    before_resources = before.capture_item_count + before.recovery_item_count
    after_resources = after.capture_item_count + after.recovery_item_count
    living_loss = max(0, before_collection.completed - after_collection.completed)
    verified = (
        verification is not None
        and verification.status is GoalDecisionOutcome.SUCCEEDED
        and living_loss == 0
    )
    return LivingDexObservedOutcome(
        LivingDexOutcomeStatus.SETTLED,
        verified_success=verified,
        completion_gain=max(registered_delta, living_delta, level_delta),
        dependency_unlock_gain=max(story_delta, dependency_pressure_delta),
        action_cost=_ratio(actions, before_effects.maximum_controller_actions),
        frame_cost=_ratio(frames, before_effects.maximum_emulator_frames),
        resource_cost=_ratio(
            max(0, before_resources - after_resources),
            max(1, before_resources),
        ),
        party_cost=max(0.0, after.situation.safety_pressure - before.situation.safety_pressure),
        storage_cost=_ratio(
            max(0, before.free_storage_slots - after.free_storage_slots),
            max(1, before.free_storage_slots),
        ),
        irreversible_loss=_ratio(living_loss, max(1, before_collection.target)),
    )


def _action_trace(
    state: _SelectedRuntimeState,
    capture: RedLivingDexValidatedSetupCapture,
    *,
    selected_index: int,
    meter: RedLivingDexSetupEffectMeter,
) -> dict[str, object]:
    checkpoint = meter.checkpoint()
    actions = checkpoint.controller_actions - state.effect_before.controller_actions
    frames = checkpoint.emulator_frames - state.effect_before.emulator_frames
    return {
        "controller_actions": actions,
        "emulator_frames": frames,
        "execution_exception_type": state.execution_exception_type,
        "goal_report_sha256": (
            None if state.report is None else _goal_report_sha256(state.report)
        ),
        "provider_execution_recorded": meter.provider_executions > 0,
        "route_report_sha256": state.route_report_sha256,
        "schema": "pokemon.red.private-living-dex-causal-action-trace.v1",
        "selected_fork_proof_sha256": canonical_sha256(
            capture.fork_proofs[selected_index].private_dict()
        ),
    }


def _goal_report_sha256(report: GoalExecutionReport) -> str:
    return canonical_sha256(
        {
            "actions_executed": report.actions_executed,
            "evidence": dict(report.evidence),
            "frames_executed": report.frames_executed,
            "schema": "pokemon.core.private-goal-execution-report.v1",
        }
    )


def _progress_delta(before: int, after: int, target: int) -> float:
    return _ratio(max(0, after - before), max(1, target))


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0 if numerator <= 0 else 1.0
    return min(1.0, max(0.0, float(numerator) / float(denominator)))


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexCausalAdapterError(f"Red causal {subject} SHA-256 differs")
    return value


__all__ = [
    "RED_LIVING_DEX_CAUSAL_ADAPTER_SCHEMA",
    "RedLivingDexCausalAdapterError",
    "RedLivingDexCausalEffectMeter",
    "RedLivingDexCausalRuntimeResolver",
    "build_red_living_dex_causal_scenario",
    "build_red_living_dex_causal_scenario_from_capture",
]
