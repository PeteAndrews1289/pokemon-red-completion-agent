#!/usr/bin/env python3
"""Freeze the authentic Red provider recipe plan without controller input.

This command authenticates the existing private Red context bank, restores
each still-unclaimed root in an isolated emulator, performs
memory-only observations, derives cartridge routes, and publishes one sealed
path-free recipe plan.  It has no controller executor, teacher, behavior
randomizer, outcome collector, model scorer, model fitter, or claim writer.
"""

# ruff: noqa: E402 -- pin reviewed script/package origins before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

_AUTHENTICATION_SUPPORT = runpy.run_path(
    str(SCRIPTS_ROOT / "freeze_red_living_dex_multifamily_pilot.py"),
    run_name="red_living_dex_provider_plan_authentication_support",
)

from pokemon_red_completion.captured_progress import (
    CapturedProgressEnvelope,
    parse_captured_progress,
)
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.gen1_field_moves import gen1_field_capabilities
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfile
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalObservation,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    derive_red_living_dex_provider_corridors,
    freeze_red_living_dex_provider_plan,
    observe_red_living_dex_provider_root_facts,
    select_red_living_dex_provider_roots,
)
from pokemon_red_completion.red_living_dex_setup_identity import (
    compose_red_living_dex_setup_execution_identity,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
from pokemon_red_completion.rom import verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)

PLAN_SCHEMA = "pokemon.red.private-living-dex-provider-plan.v1"
RESULT_SCHEMA = "pokemon.red.living-dex-provider-plan-freeze-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-provider-plan-freeze-failure.v1"
PLAN_RECORD_ID = "red-living-dex-provider-plan-v1"
PLAN_RECORD_KIND = "red-living-dex-provider-plan-v1"

_SHA256_LENGTH = 64


class ProviderPlanFreezeError(RuntimeError):
    """One sanitized action-free freeze stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise ProviderPlanFreezeError("arguments")


@dataclass(slots=True)
class _DiagnosticState:
    authenticated_contexts: int = 0
    contexts_considered: int = 0
    consumed_contexts: int = 0
    ineligible_control_contexts: int = 0
    states_restored: int = 0
    observations_completed: int = 0
    eligible_root_pool: int = 0
    source_train_roots: int = 0
    source_validation_roots: int = 0
    authenticated_supplemental_roots: int = 0
    consumed_supplemental_roots: int = 0
    eligible_supplemental_roots: int = 0
    selected_train_roots: int = 0
    selected_development_roots: int = 0
    controller_actions: int = 0
    emulator_frames: int = 0
    provider_executions: int = 0
    teacher_queries: int = 0
    model_predictions: int = 0
    model_fits: int = 0
    outcomes: int = 0
    root_claims: int = 0

    def public_dict(self, *, status: str, stage: str) -> dict[str, object]:
        return {
            "authenticated_contexts": self.authenticated_contexts,
            "authenticated_supplemental_roots": self.authenticated_supplemental_roots,
            "contexts_considered": self.contexts_considered,
            "consumed_contexts": self.consumed_contexts,
            "consumed_supplemental_roots": self.consumed_supplemental_roots,
            "controller_actions": self.controller_actions,
            "eligible_root_pool": self.eligible_root_pool,
            "eligible_supplemental_roots": self.eligible_supplemental_roots,
            "emulator_frames": self.emulator_frames,
            "ineligible_control_contexts": self.ineligible_control_contexts,
            "model_fits": self.model_fits,
            "model_predictions": self.model_predictions,
            "observations_completed": self.observations_completed,
            "outcomes": self.outcomes,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": self.provider_executions,
            "root_claims": self.root_claims,
            "schema": FAILURE_SCHEMA,
            "selected_development_roots": self.selected_development_roots,
            "selected_train_roots": self.selected_train_roots,
            "source_catalog_partition_reused_as_prospective_label": False,
            "source_train_roots": self.source_train_roots,
            "source_validation_roots": self.source_validation_roots,
            "stage": stage,
            "states_restored": self.states_restored,
            "status": status,
            "teacher_queries": self.teacher_queries,
        }


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    parser.add_argument(
        "--supplemental-state",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument(
        "--expected-supplemental-physical-root-sha256",
        action="append",
        default=[],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    state = _DiagnosticState()
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "source_authentication"
        source_commit, source_bundle = _authenticate_source(args)
        stage = "private_input_authentication"
        (
            rom_path,
            rom_sha256,
            rom_bytes,
            contexts,
            catalog_sha256,
            context_plan_sha256,
        ) = _authenticate_inputs(args, source_commit, source_bundle)
        state.authenticated_contexts = len(contexts)
        stage = "supplemental_root_authentication"
        supplemental_roots = _authenticate_supplemental_roots(
            tuple(args.supplemental_state),
            tuple(args.expected_supplemental_physical_root_sha256),
        )
        state.authenticated_supplemental_roots = len(supplemental_roots)
        stage = "private_namespace_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "runtime_authentication"
        runtime = build_runtime_identity()
        require_pyboy_import_origins(runtime)
        stage = "route_world_derivation"
        route_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
        world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
        corridors = derive_red_living_dex_provider_corridors(world)
        execution_identity = compose_red_living_dex_setup_execution_identity(
            source_commit=source_commit,
            source_bundle_sha256=source_bundle,
            route_registry_sha256=route_registry.registry_sha256,
            runtime_identity=runtime,
        )
        meter = RedLivingDexSetupEffectMeter()
        effects_before = meter.checkpoint()

        stage = "action_free_root_observation"
        claim_registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(claim_registry, exclusive=False):
            candidates = _observe_candidates(
                contexts,
                rom_path=rom_path,
                rom_bytes=rom_bytes,
                runtime=runtime,
                claim_registry=claim_registry,
                state=state,
            )
            candidates = (
                *candidates,
                *_observe_supplemental_candidates(
                    supplemental_roots,
                    rom_path=rom_path,
                    rom_bytes=rom_bytes,
                    runtime=runtime,
                    claim_registry=claim_registry,
                    state=state,
                ),
            )
            effects_after = meter.checkpoint()
            stage = "complete_root_assignment"
            selected = select_red_living_dex_provider_roots(
                candidates,
                world=world,
                corridors=corridors,
                effects_before=effects_before,
                effects_after=effects_after,
            )
            selected_counts = Counter(
                item.partition
                for item in build_partitioned_root_rows(selected)
            )
            state.selected_train_roots = selected_counts[
                LivingDexCapturePartition.TRAIN
            ]
            state.selected_development_roots = selected_counts[
                LivingDexCapturePartition.DEVELOPMENT
            ]
            stage = "provider_plan_freeze"
            frozen = freeze_red_living_dex_provider_plan(
                selected,
                world=world,
                corridors=corridors,
                execution_identity=execution_identity,
                effects_before=effects_before,
                effects_after=effects_after,
            )
            stage = "protected_input_integrity"
            _require_integrity(
                args,
                source_commit=source_commit,
                source_bundle=source_bundle,
                rom_path=rom_path,
                rom_sha256=rom_sha256,
                rom_bytes=rom_bytes,
                runtime=runtime,
                route_registry_sha256=route_registry.registry_sha256,
                selected=selected,
                claim_registry=claim_registry,
            )
            stage = "private_plan_encoding"
            document, private_plan_sha256 = _private_plan_document(
                source_commit=source_commit,
                source_bundle=source_bundle,
                rom_sha256=rom_sha256,
                goal_registry_sha256=_sha256(args.expected_registry_sha256),
                catalog_sha256=catalog_sha256,
                context_plan_sha256=context_plan_sha256,
                runtime=runtime,
                route_registry_sha256=route_registry.registry_sha256,
                frozen=frozen,
                state=state,
            )
            stage = "private_plan_publication"
            result = _publish(
                store,
                document=document,
                private_plan_sha256=private_plan_sha256,
                frozen=frozen,
                state=state,
            )
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except ProviderPlanFreezeError as error:
        stage = error.stage
    except BaseException:
        pass
    print(
        json.dumps(
            state.public_dict(status="failed_closed", stage=stage),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


@dataclass(frozen=True, slots=True)
class _PartitionedRoot:
    partition: LivingDexCapturePartition
    root: RedLivingDexActionFreeRootObservation


@dataclass(frozen=True, slots=True)
class _SupplementalRoot:
    root: RedLivingDexAuthenticatedSetupRoot
    envelope: CapturedProgressEnvelope


def build_partitioned_root_rows(
    selected: tuple[RedLivingDexActionFreeRootObservation, ...],
) -> tuple[_PartitionedRoot, ...]:
    """Join selected roots to the immutable prospective partition order."""

    from pokemon_red_completion.red_living_dex_capture_plan import (
        build_red_living_dex_prospective_capture_plan,
    )

    slots = build_red_living_dex_prospective_capture_plan().slots
    if len(selected) != len(slots):
        raise ProviderPlanFreezeError("complete_root_assignment")
    return tuple(
        _PartitionedRoot(slot.partition, root)
        for slot, root in zip(slots, selected, strict=True)
    )


def _authenticate_source(args: argparse.Namespace) -> tuple[str, str]:
    function = cast(Any, _AUTHENTICATION_SUPPORT["_authenticate_source"])
    try:
        return cast(tuple[str, str], function(args))
    except BaseException:
        raise ProviderPlanFreezeError("source_authentication") from None


def _authenticate_inputs(
    args: argparse.Namespace,
    source_commit: str,
    source_bundle: str,
) -> tuple[Path, str, bytes, tuple[Any, ...], str, str]:
    function = cast(Any, _AUTHENTICATION_SUPPORT["_authenticate_inputs"])
    try:
        return cast(
            tuple[Path, str, bytes, tuple[Any, ...], str, str],
            function(args, source_commit, source_bundle),
        )
    except BaseException:
        raise ProviderPlanFreezeError("private_input_authentication") from None


def _authenticate_supplemental_roots(
    state_paths: tuple[Path, ...],
    expected_physical_root_sha256s: tuple[str, ...],
) -> tuple[_SupplementalRoot, ...]:
    """Open explicitly hash-bound legacy checkpoints without retaining paths."""

    if (
        not isinstance(state_paths, tuple)
        or any(not isinstance(item, Path) for item in state_paths)
        or not isinstance(expected_physical_root_sha256s, tuple)
        or any(not isinstance(item, str) for item in expected_physical_root_sha256s)
        or len(state_paths) != len(expected_physical_root_sha256s)
    ):
        raise ProviderPlanFreezeError("supplemental_root_authentication")
    supplements: list[_SupplementalRoot] = []
    seen: set[str] = set()
    for state_path, expected_physical_root_sha256 in zip(
        state_paths,
        expected_physical_root_sha256s,
        strict=True,
    ):
        try:
            state_bytes = state_path.read_bytes()
            source_envelope = state_path.with_suffix(
                state_path.suffix + ".json"
            ).read_bytes()
            envelope = parse_captured_progress(
                source_envelope,
                state_bytes=state_bytes,
            )
            envelope_bytes = (
                json.dumps(
                    envelope.to_dict(),
                    ensure_ascii=True,
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            state_sha256 = hashlib.sha256(state_bytes).hexdigest()
            envelope_sha256 = hashlib.sha256(envelope_bytes).hexdigest()
            root = RedLivingDexAuthenticatedSetupRoot(
                root_consumption_sha256=root_consumption_sha256(
                    state_sha256=state_sha256,
                    envelope_sha256=envelope_sha256,
                ),
                state_bytes=state_bytes,
                envelope_bytes=envelope_bytes,
            )
        except BaseException:
            raise ProviderPlanFreezeError("supplemental_root_authentication") from None
        try:
            expected = _sha256(expected_physical_root_sha256)
        except ProviderPlanFreezeError:
            raise ProviderPlanFreezeError("supplemental_root_authentication") from None
        if root.physical_root_sha256 != expected or expected in seen:
            raise ProviderPlanFreezeError("supplemental_root_authentication")
        seen.add(expected)
        supplements.append(_SupplementalRoot(root=root, envelope=envelope))
    return tuple(supplements)


def _observe_candidates(
    contexts: tuple[Any, ...],
    *,
    rom_path: Path,
    rom_bytes: bytes,
    runtime: RuntimeIdentity,
    claim_registry: Path,
    state: _DiagnosticState,
) -> tuple[RedLivingDexActionFreeRootObservation, ...]:
    """Observe one pooled root inventory without inheriting old partitions.

    The authenticated catalog's train/validation assignment records where a
    capture came from.  The new provider curriculum assigns its own train and
    development slots prospectively, after selection, so reusing that old tag
    here would silently make a different experiment.
    """

    candidates: list[RedLivingDexActionFreeRootObservation] = []
    for private in contexts:
        state.contexts_considered += 1
        try:
            assignment = private.assignment
            capture = private.capture
            profile = private.profile
            claimed_root = private.root_consumption_sha256
            initially_available = private.root_available
        except BaseException:
            raise ProviderPlanFreezeError("private_input_authentication") from None
        if not isinstance(capture, GoalManagerContextCapture) or not isinstance(
            profile, RedGoalContextProfile
        ):
            raise ProviderPlanFreezeError("private_input_authentication")
        if assignment.partition not in {"train", "validation"}:
            raise ProviderPlanFreezeError("private_input_authentication")
        currently_available = root_claim_is_available(claim_registry, claimed_root)
        if not initially_available or not currently_available:
            state.consumed_contexts += 1
            continue

        envelope_bytes = (
            json.dumps(
                capture.envelope.to_dict(),
                ensure_ascii=True,
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        if (
            hashlib.sha256(envelope_bytes).hexdigest() != capture.envelope_sha256
            or root_consumption_sha256(
                state_sha256=capture.state_sha256,
                envelope_sha256=capture.envelope_sha256,
            )
            != claimed_root
        ):
            raise ProviderPlanFreezeError("private_input_authentication")
        root = RedLivingDexAuthenticatedSetupRoot(
            root_consumption_sha256=claimed_root,
            state_bytes=capture.state_bytes,
            envelope_bytes=envelope_bytes,
        )
        if not root_claim_is_available(
            claim_registry,
            root.physical_root_sha256,
        ):
            state.consumed_contexts += 1
            continue

        def observe_catalog_goal(
            reader: PokemonRedStateReader,
            running: PyBoyAdapter,
            profile: RedGoalContextProfile = profile,
            capture: GoalManagerContextCapture = capture,
        ) -> RedGoalObservation:
            return build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=running,
                reader=reader,
            ).adapter.observe()

        observation = _observe_root(
            root,
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            runtime=runtime,
            state=state,
            observe_goal=observe_catalog_goal,
            independence_lineage_sha256=canonical_sha256(
                {
                    "root_lineage_id": assignment.root_lineage_id,
                    "schema": (
                        "pokemon.red.private-provider-capacity-lineage.v1"
                    ),
                }
            ),
            prospective_independence_authenticated=True,
            cluster_partition=(
                "train" if assignment.partition == "train" else "development"
            ),
        )
        if observation is None:
            state.ineligible_control_contexts += 1
            continue
        candidates.append(observation)
        state.eligible_root_pool += 1
        if assignment.partition == "train":
            state.source_train_roots += 1
        else:
            state.source_validation_roots += 1
    return tuple(candidates)


def _observe_supplemental_candidates(
    supplements: tuple[_SupplementalRoot, ...],
    *,
    rom_path: Path,
    rom_bytes: bytes,
    runtime: RuntimeIdentity,
    claim_registry: Path,
    state: _DiagnosticState,
) -> tuple[RedLivingDexActionFreeRootObservation, ...]:
    candidates: list[RedLivingDexActionFreeRootObservation] = []
    for supplement in supplements:
        root = supplement.root
        if not all(
            root_claim_is_available(claim_registry, digest)
            for digest in (
                root.root_consumption_sha256,
                root.physical_root_sha256,
            )
        ):
            state.consumed_supplemental_roots += 1
            continue

        def observe_supplemental_goal(
            reader: PokemonRedStateReader,
            _running: PyBoyAdapter,
            envelope: CapturedProgressEnvelope = supplement.envelope,
        ) -> RedGoalObservation:
            return PokemonRedGoalStateAdapter(
                reader,
                CapturedPokemonRedObserver(
                    reader,
                    COMPLETION_QUEST,
                    envelope,
                ),
                COMPLETION_QUEST,
            ).observe()

        observation = _observe_root(
            root,
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            runtime=runtime,
            state=state,
            observe_goal=observe_supplemental_goal,
            independence_lineage_sha256=canonical_sha256(
                {
                    "physical_root_sha256": root.physical_root_sha256,
                    "schema": (
                        "pokemon.red.private-supplemental-capacity-lineage.v1"
                    ),
                }
            ),
            prospective_independence_authenticated=False,
            cluster_partition=None,
        )
        if observation is None:
            state.ineligible_control_contexts += 1
            continue
        candidates.append(observation)
        state.eligible_root_pool += 1
        state.eligible_supplemental_roots += 1
    return tuple(candidates)


def _observe_root(
    root: RedLivingDexAuthenticatedSetupRoot,
    *,
    rom_path: Path,
    rom_bytes: bytes,
    runtime: RuntimeIdentity,
    state: _DiagnosticState,
    observe_goal: Callable[
        [PokemonRedStateReader, PyBoyAdapter],
        RedGoalObservation,
    ],
    independence_lineage_sha256: str,
    prospective_independence_authenticated: bool,
    cluster_partition: str | None,
) -> RedLivingDexActionFreeRootObservation | None:
    emulator: PyBoyAdapter | None = None
    frame_before = 0
    try:
        with PyBoyAdapter(
            rom_path,
            watch=False,
            speed=None,
            expected_rom=POKEMON_RED_US_REV_0,
        ) as running:
            emulator = running
            require_pyboy_import_origins(runtime)
            frame_before = running.frame_count
            if running.pressed_buttons:
                state.controller_actions += len(running.pressed_buttons)
                raise ProviderPlanFreezeError("zero_effect_authentication")
            running.load_state_bytes(root.state_bytes)
            state.states_restored += 1
            reader = PokemonRedStateReader(running)
            goal_observation = observe_goal(reader, running)
            traversal = Gen1TraversalObserver(
                reader,
                hazard_projector=Gen1TrainerSightProjector(rom_bytes, reader),
                capability_projector=lambda raw: gen1_field_capabilities(running, raw),
            ).observe()
            if (
                not traversal.ready
                or traversal.interruption is not None
                or traversal.mode != "land"
                or not goal_observation.input_ready
                or goal_observation.raw.battle_state != 0
            ):
                _record_zero_effects(running, frame_before=frame_before, state=state)
                require_pyboy_import_origins(runtime)
                return None
            facts = observe_red_living_dex_provider_root_facts(goal_observation)
            state.observations_completed += 1
            _record_zero_effects(running, frame_before=frame_before, state=state)
            require_pyboy_import_origins(runtime)
            return RedLivingDexActionFreeRootObservation(
                root=root,
                traversal=traversal,
                facts=facts,
                observed_state_sha256=root.state_sha256,
                root_claim_available=True,
                option_context=living_dex_option_context_from_goal_situation(
                    goal_observation.situation
                ),
                independence_lineage_sha256=independence_lineage_sha256,
                prospective_independence_authenticated=(
                    prospective_independence_authenticated
                ),
                cluster_partition=cluster_partition,
            )
    except ProviderPlanFreezeError:
        if emulator is not None:
            _record_unaccounted_effects(emulator, frame_before=frame_before, state=state)
        raise
    except BaseException:
        if emulator is not None:
            _record_unaccounted_effects(emulator, frame_before=frame_before, state=state)
        raise ProviderPlanFreezeError("action_free_root_observation") from None


def _record_zero_effects(
    emulator: PyBoyAdapter,
    *,
    frame_before: int,
    state: _DiagnosticState,
) -> None:
    frame_delta = emulator.frame_count - frame_before
    if frame_delta < 0:
        raise ProviderPlanFreezeError("zero_effect_authentication")
    state.emulator_frames += frame_delta
    state.controller_actions += len(emulator.pressed_buttons)
    if frame_delta or emulator.pressed_buttons:
        raise ProviderPlanFreezeError("zero_effect_authentication")


def _record_unaccounted_effects(
    emulator: PyBoyAdapter,
    *,
    frame_before: int,
    state: _DiagnosticState,
) -> None:
    frame_delta = emulator.frame_count - frame_before
    if frame_delta > 0 and state.emulator_frames == 0:
        state.emulator_frames += frame_delta
    if emulator.pressed_buttons and state.controller_actions == 0:
        state.controller_actions += len(emulator.pressed_buttons)


def _require_integrity(
    args: argparse.Namespace,
    *,
    source_commit: str,
    source_bundle: str,
    rom_path: Path,
    rom_sha256: str,
    rom_bytes: bytes,
    runtime: RuntimeIdentity,
    route_registry_sha256: str,
    selected: tuple[RedLivingDexActionFreeRootObservation, ...],
    claim_registry: Path,
) -> None:
    if _authenticate_source(args) != (source_commit, source_bundle):
        raise ProviderPlanFreezeError("protected_input_integrity")
    if (
        verify_rom(rom_path).sha256 != rom_sha256
        or rom_sha256 != POKEMON_RED_US_REV_0.sha256
        or hashlib.sha256(rom_bytes).hexdigest() != rom_sha256
        or working_source_bundle_sha256(PROJECT_ROOT) != source_bundle
    ):
        raise ProviderPlanFreezeError("protected_input_integrity")
    current_runtime = build_runtime_identity()
    require_pyboy_import_origins(current_runtime)
    if current_runtime != runtime:
        raise ProviderPlanFreezeError("protected_input_integrity")
    if (
        load_strategic_navigation_scenario_registry(PROJECT_ROOT).registry_sha256
        != route_registry_sha256
    ):
        raise ProviderPlanFreezeError("protected_input_integrity")
    if any(
        not root_claim_is_available(claim_registry, digest)
        for item in selected
        for digest in (
            item.root.root_consumption_sha256,
            item.root.physical_root_sha256,
        )
    ):
        raise ProviderPlanFreezeError("protected_input_integrity")


def _private_plan_document(
    *,
    source_commit: str,
    source_bundle: str,
    rom_sha256: str,
    goal_registry_sha256: str,
    catalog_sha256: str,
    context_plan_sha256: str,
    runtime: RuntimeIdentity,
    route_registry_sha256: str,
    frozen: Any,
    state: _DiagnosticState,
) -> tuple[dict[str, object], str]:
    payload: dict[str, object] = {
        "context_catalog_sha256": catalog_sha256,
        "context_plan_sha256": context_plan_sha256,
        "controller_actions": state.controller_actions,
        "emulator_frames": state.emulator_frames,
        "execution_identity": frozen.plan.execution_identity.private_dict(),
        "execution_identity_sha256": frozen.plan.execution_identity.identity_sha256,
        "freeze": frozen.private_dict(),
        "freeze_sha256": frozen.freeze_sha256,
        "goal_registry_sha256": goal_registry_sha256,
        "model_fits": state.model_fits,
        "model_predictions": state.model_predictions,
        "outcomes": state.outcomes,
        "provider_executions": state.provider_executions,
        "recipe_plan": frozen.plan.private_dict(),
        "recipe_plan_sha256": frozen.plan.plan_sha256,
        "root_claims": state.root_claims,
        "route_registry_sha256": route_registry_sha256,
        "rom_sha256": rom_sha256,
        "runtime_identity_sha256": runtime.sha256,
        "schema": PLAN_SCHEMA,
        "source_catalog_partition_reused_as_prospective_label": False,
        "source_bundle_sha256": source_bundle,
        "source_commit": source_commit,
        "status": "frozen_before_claim_controller_input_outcome_or_fit",
        "teacher_queries": state.teacher_queries,
    }
    validate_private_record(payload)
    private_plan_sha256 = canonical_sha256(payload)
    document = {**payload, "private_plan_sha256": private_plan_sha256}
    validate_private_record(document)
    return document, private_plan_sha256


def _publish(
    store: PrivateArtifactRoot,
    *,
    document: dict[str, object],
    private_plan_sha256: str,
    frozen: Any,
    state: _DiagnosticState,
) -> dict[str, object]:
    record = store.publish_sealed_record(
        PLAN_RECORD_ID,
        kind=PLAN_RECORD_KIND,
        record=document,
    )
    return {
        **frozen.public_dict(),
        "authenticated_contexts": state.authenticated_contexts,
        "authenticated_supplemental_roots": state.authenticated_supplemental_roots,
        "consumed_contexts": state.consumed_contexts,
        "consumed_supplemental_roots": state.consumed_supplemental_roots,
        "ineligible_control_contexts": state.ineligible_control_contexts,
        "eligible_root_pool": state.eligible_root_pool,
        "eligible_supplemental_roots": state.eligible_supplemental_roots,
        "plan_manifest_sha256": record.summary.manifest_sha256,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "private_plan_sha256": private_plan_sha256,
        "schema": RESULT_SCHEMA,
        "source_catalog_partition_reused_as_prospective_label": False,
        "source_train_roots": state.source_train_roots,
        "source_validation_roots": state.source_validation_roots,
        "status": "authenticated_action_free_provider_plan_frozen",
    }


def _sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProviderPlanFreezeError("arguments")
    return value


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
