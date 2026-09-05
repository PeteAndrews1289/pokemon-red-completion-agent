#!/usr/bin/env python3
"""Run or recover the frozen ten-slot targeted Red train campaign.

The command authenticates clean published source and exact green CI, reads the
private schedule by exact hash, re-observes its roots without controller input,
rebuilds every Red recipe from cartridge mechanics, and only then exposes the
ten train slots to the reset-aware runner.  Development, model fitting, teacher
queries, counterfactual execution, and Crystal are structurally absent.
"""

# ruff: noqa: E402 -- pin project import roots before local imports.

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import webbrowser
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

import freeze_red_living_dex_targeted_schedule as freezer

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.goal_manager_composition_qualification import (
    open_fixed_account_claim_registry,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.progress_dashboard import (
    DashboardFrameObserver,
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfile
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexTargetedScheduleBinding,
    enumerate_red_living_dex_causal_capabilities,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexCurrentConsumerBinding,
    authenticate_red_living_dex_current_consumer,
)
from pokemon_red_completion.red_living_dex_production_runtime import (
    RedLivingDexProductionSetupResolver,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    derive_red_living_dex_provider_corridors,
)
from pokemon_red_completion.red_living_dex_setup_identity import (
    compose_red_living_dex_setup_execution_identity,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_living_dex_targeted_schedule_reader import (
    RedLivingDexTargetedScheduleDescriptor,
    RedLivingDexTargetedScheduleExpectations,
    authenticate_red_living_dex_targeted_schedule_plan,
    load_red_living_dex_targeted_schedule_descriptor,
)
from pokemon_red_completion.red_living_dex_targeted_schedule_replay import (
    rebind_red_living_dex_targeted_schedule,
)
from pokemon_red_completion.red_living_dex_targeted_train_campaign import (
    run_red_living_dex_targeted_train_campaign,
)
from pokemon_red_completion.red_living_dex_targeted_train_dashboard import (
    RedLivingDexTargetedTrainDashboardProgress,
    red_living_dex_targeted_train_dashboard_snapshot,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
    run_red_living_dex_targeted_train_assignment,
)
from pokemon_red_completion.rom import verify_rom
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

RESULT_SCHEMA = "pokemon.red.living-dex-targeted-train-campaign-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-targeted-train-campaign-failure.v1"
DEFAULT_PORT = 8768
_MAXIMUM_PLAN_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexTargetedTrainCommandError(RuntimeError):
    """One sanitized production-command stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected"
        super().__init__(self.stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedLivingDexTargetedTrainCommandError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", default=1, type=int)
    parser.add_argument("--schedule", required=True, type=Path)
    parser.add_argument("--expected-schedule-sha256", required=True)
    parser.add_argument("--producer-source-commit", required=True)
    parser.add_argument("--producer-source-bundle-sha256", required=True)
    parser.add_argument("--capacity-result-sha256", required=True)
    parser.add_argument("--context-catalog", required=True, type=Path)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", required=True, type=Path)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--expected-model-record-sha256", required=True)
    parser.add_argument("--expected-route-registry-sha256", required=True)
    parser.add_argument("--expected-runtime-identity-sha256", required=True)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--hold-seconds", default=30, type=int)
    return parser


class _LiveProgressPublisher:
    """Refresh action/frame counters while the blocking emulator call runs."""

    def __init__(
        self,
        state: DashboardState,
        binding: RedLivingDexTargetedScheduleBinding,
        meter: RedLivingDexSetupEffectMeter,
    ) -> None:
        self._state = state
        self._binding = binding
        self._meter = meter
        self._lock = threading.Lock()
        self._progress = RedLivingDexTargetedTrainDashboardProgress()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def __call__(self, progress: RedLivingDexTargetedTrainDashboardProgress) -> None:
        with self._lock:
            self._progress = progress
        self._publish()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._poll,
            name="targeted-train-dashboard-publisher",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._publish()

    def _poll(self) -> None:
        while not self._stopped.wait(0.5):
            self._publish()

    def _publish(self) -> None:
        try:
            with self._lock:
                current = self._progress
            progress = replace(current, effects=self._meter.checkpoint())
            snapshot = red_living_dex_targeted_train_dashboard_snapshot(
                self._binding,
                progress,
            )
            self._state.publish(snapshot)
        except BaseException:
            self._stopped.set()


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        if args.hold_seconds < 0:
            raise RedLivingDexTargetedTrainCommandError("arguments")
        stage = "current_source_authentication"
        consumer = RedLivingDexCurrentConsumerBinding(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=args.expected_source_bundle_sha256,
            exact_ci_run=args.exact_ci_run,
            exact_ci_attempt=args.exact_ci_attempt,
        )
        authenticate_red_living_dex_current_consumer(PROJECT_ROOT, consumer)
        if working_source_bundle_sha256(PROJECT_ROOT) != (
            args.expected_source_bundle_sha256
        ):
            raise RedLivingDexTargetedTrainCommandError(
                "current_source_authentication"
            )
        stage = "schedule_envelope_authentication"
        payload = _read_schedule(args.schedule)
        expectations = _expectations(args)
        descriptor = load_red_living_dex_targeted_schedule_descriptor(
            payload,
            expected_plan_sha256=args.expected_schedule_sha256,
            expectations=expectations,
        )
        stage = "private_input_authentication"
        (
            rom_path,
            _rom_sha256,
            rom_bytes,
            contexts,
            _catalog_sha256,
            _context_plan_sha256,
        ) = _authenticate_inputs(args)
        stage = "runtime_authentication"
        runtime = build_runtime_identity()
        require_pyboy_import_origins(runtime)
        if runtime.sha256 != args.expected_runtime_identity_sha256:
            raise RedLivingDexTargetedTrainCommandError("runtime_authentication")
        route_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
        if route_registry.registry_sha256 != args.expected_route_registry_sha256:
            raise RedLivingDexTargetedTrainCommandError(
                "route_registry_authentication"
            )
        stage = "action_free_schedule_replay"
        observed = _observe_scheduled_roots(
            descriptor,
            contexts,
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            runtime=runtime,
        )
        world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
        corridors = derive_red_living_dex_provider_corridors(world)
        replay_meter = RedLivingDexSetupEffectMeter()
        before = replay_meter.checkpoint()
        capabilities = enumerate_red_living_dex_causal_capabilities(
            observed,
            world=world,
            corridors=corridors,
            effects_before=before,
            effects_after=replay_meter.checkpoint(),
        )
        fresh_binding = rebind_red_living_dex_targeted_schedule(
            descriptor,
            capabilities,
        )
        binding = authenticate_red_living_dex_targeted_schedule_plan(
            payload,
            expected_plan_sha256=args.expected_schedule_sha256,
            expectations=expectations,
            freshly_derived_binding=fresh_binding,
        )
        if args.preflight_only:
            print(
                json.dumps(
                    {
                        "controller_actions": 0,
                        "development_slots_opened": 0,
                        "emulator_frames": 0,
                        "model_fits": 0,
                        "model_predictions": 0,
                        "private_identity_fields": 0,
                        "private_path_fields": 0,
                        "schema": RESULT_SCHEMA,
                        "status": "targeted_train_campaign_preflight_passed",
                        "teacher_queries": 0,
                        "train_slots": sum(
                            slot.partition == "train"
                            for slot in binding.schedule.slots
                        ),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        stage = "targeted_train_execution"
        meter = RedLivingDexSetupEffectMeter()
        state = DashboardState(
            red_living_dex_targeted_train_dashboard_snapshot(
                binding,
                RedLivingDexTargetedTrainDashboardProgress(),
            )
        )
        observer = DashboardFrameObserver(state, maximum_fps=12)
        execution_identity = compose_red_living_dex_setup_execution_identity(
            source_commit=consumer.source_commit,
            source_bundle_sha256=consumer.source_bundle_sha256,
            route_registry_sha256=route_registry.registry_sha256,
            runtime_identity=runtime,
        )
        resolver = RedLivingDexProductionSetupResolver(
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            producer_execution_identity=execution_identity,
            frame_observer=observer,
        )
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        claim_registry = open_fixed_account_claim_registry()
        publisher = _LiveProgressPublisher(state, binding, meter)
        with ProgressDashboardServer(state, port=args.port) as dashboard:
            if not args.no_browser:
                webbrowser.open(dashboard.url)
            print(
                json.dumps(
                    {
                        "dashboard_url": dashboard.url,
                        "development_slots_opened": 0,
                        "model_fits": 0,
                        "schema": RESULT_SCHEMA,
                        "status": "targeted_train_campaign_started",
                        "train_slots": 10,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                flush=True,
            )
            publisher.start()
            try:
                receipts = run_red_living_dex_targeted_train_campaign(
                    binding,
                    source_commit=consumer.source_commit,
                    execute=lambda assignment: (
                        run_red_living_dex_targeted_train_assignment(
                            assignment,
                            store=store,
                            claim_registry=claim_registry,
                            setup_execution_identity=execution_identity,
                            resolver=resolver,
                            meter=meter,
                        )
                    ),
                    effects=meter.checkpoint,
                    publish_progress=publisher,
                )
            finally:
                publisher.close()
            if args.hold_seconds:
                time.sleep(args.hold_seconds)
        print(
            json.dumps(
                {
                    "causal_train_examples_recorded": sum(
                        bool(item.public_dict()["causal_train_example_recorded"])
                        for item in receipts
                    ),
                    "controller_actions": meter.controller_actions,
                    "development_slots_opened": 0,
                    "emulator_frames": meter.emulator_frames,
                    "model_fits": 0,
                    "model_predictions": 0,
                    "private_path_fields": 0,
                    "runner_sha256": RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
                    "schema": RESULT_SCHEMA,
                    "status": "targeted_train_campaign_terminal",
                    "teacher_queries": 0,
                    "train_slots_terminal": len(receipts),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except SystemExit as error:
        if error.code == 0:
            return 0
        stage = "arguments"
    except RedLivingDexTargetedTrainCommandError as error:
        stage = error.stage
    except BaseException:
        pass
    print(
        json.dumps(
            {
                "development_slots_opened": 0,
                "model_fits": 0,
                "model_predictions": 0,
                "private_identity_fields": 0,
                "private_path_fields": 0,
                "schema": FAILURE_SCHEMA,
                "stage": stage,
                "status": "failed_closed",
                "teacher_queries": 0,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _expectations(args: argparse.Namespace) -> RedLivingDexTargetedScheduleExpectations:
    return RedLivingDexTargetedScheduleExpectations(
        source_commit=args.producer_source_commit,
        source_bundle_sha256=args.producer_source_bundle_sha256,
        capacity_result_sha256=args.capacity_result_sha256,
        context_catalog_sha256=args.expected_context_catalog_sha256,
        context_plan_sha256=args.expected_context_plan_sha256,
        model_sha256=args.expected_model_sha256,
        model_record_sha256=args.expected_model_record_sha256,
        rom_sha256=verify_rom(args.rom).sha256,
        route_registry_sha256=args.expected_route_registry_sha256,
        runtime_identity_sha256=args.expected_runtime_identity_sha256,
    )


def _authenticate_inputs(
    args: argparse.Namespace,
) -> tuple[Path, str, bytes, tuple[Any, ...], str, str]:
    support = cast(Mapping[str, object], freezer._PROVIDER_SUPPORT)
    function = cast(Any, support["_authenticate_inputs"])
    return cast(
        tuple[Path, str, bytes, tuple[Any, ...], str, str],
        function(
            args,
            args.producer_source_commit,
            args.producer_source_bundle_sha256,
        ),
    )


def _observe_scheduled_roots(
    descriptor: RedLivingDexTargetedScheduleDescriptor,
    contexts: tuple[Any, ...],
    *,
    rom_path: Path,
    rom_bytes: bytes,
    runtime: RuntimeIdentity,
) -> tuple[RedLivingDexActionFreeRootObservation, ...]:
    support = cast(Mapping[str, object], freezer._PROVIDER_SUPPORT)
    state = cast(Any, support["_DiagnosticState"])()
    observe_root = cast(Any, support["_observe_root"])
    needed = {
        (slot.physical_root_sha256, slot.lineage_sha256, slot.partition)
        for slot in descriptor.schedule.slots
    }
    observations: list[RedLivingDexActionFreeRootObservation] = []
    found: set[tuple[str, str, str]] = set()
    for private in contexts:
        assignment = private.assignment
        capture = private.capture
        profile = private.profile
        if not isinstance(capture, GoalManagerContextCapture) or not isinstance(
            profile,
            RedGoalContextProfile,
        ):
            raise RedLivingDexTargetedTrainCommandError(
                "private_input_authentication"
            )
        envelope_bytes = (
            json.dumps(
                capture.envelope.to_dict(),
                ensure_ascii=True,
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
        logical_root = root_consumption_sha256(
            state_sha256=capture.state_sha256,
            envelope_sha256=capture.envelope_sha256,
        )
        if logical_root != private.root_consumption_sha256:
            raise RedLivingDexTargetedTrainCommandError(
                "private_input_authentication"
            )
        root = RedLivingDexAuthenticatedSetupRoot(
            root_consumption_sha256=logical_root,
            state_bytes=capture.state_bytes,
            envelope_bytes=envelope_bytes,
        )
        lineage = canonical_sha256(
            {
                "root_lineage_id": assignment.root_lineage_id,
                "schema": "pokemon.red.private-provider-capacity-lineage.v1",
            }
        )
        partition = "train" if assignment.partition == "train" else "development"
        key = (root.physical_root_sha256, lineage, partition)
        if key not in needed:
            continue

        def observe_goal(
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

        observation = observe_root(
            root,
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            runtime=runtime,
            state=state,
            observe_goal=observe_goal,
            independence_lineage_sha256=lineage,
            prospective_independence_authenticated=True,
            cluster_partition=partition,
        )
        if (
            observation is None
            or not isinstance(observation, RedLivingDexActionFreeRootObservation)
            or key in found
        ):
            raise RedLivingDexTargetedTrainCommandError(
                "action_free_schedule_replay"
            )
        found.add(key)
        observations.append(observation)
    if found != needed:
        raise RedLivingDexTargetedTrainCommandError("action_free_schedule_replay")
    return tuple(observations)


def _read_schedule(path: Path) -> bytes:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.lstat()
        if (
            resolved.is_symlink()
            or not resolved.is_file()
            or not 0 < metadata.st_size <= _MAXIMUM_PLAN_BYTES
        ):
            raise OSError
        payload = resolved.read_bytes()
    except OSError:
        raise RedLivingDexTargetedTrainCommandError(
            "schedule_envelope_authentication"
        ) from None
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
