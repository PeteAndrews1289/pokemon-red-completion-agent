#!/usr/bin/env python3
"""Run or recover only the eight train slots from a retired Red root bank.

The command authenticates exact published source and green CI, verifies the
private retirement plan byte-for-byte, reobserves its formerly-development
roots without controller input, and freshly rebuilds every executable recipe.
An explicit --fit-on-complete updates the existing learner only after factual
train admission. Paired development, reserves, teacher queries, Crystal, and
retries outside each frozen reset ordinal are structurally unavailable.
"""

# ruff: noqa: E402 -- pin project import roots before local imports.

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any, Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

import run_red_living_dex_targeted_train as base

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.goal_manager_composition_qualification import (
    open_fixed_account_claim_registry,
    root_claim_is_available,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
)
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LivingDexCausalIntegrationSource,
)
from pokemon_red_completion.living_dex_causal_model_update import LivingDexCausalModelUpdateError
from pokemon_red_completion.living_dex_repeatable_trial_claim import (
    LivingDexRepeatableRootReservation,
    observe_living_dex_repeatable_root_eligibility,
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
    enumerate_red_living_dex_causal_capabilities,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexCurrentConsumerBinding,
    authenticate_red_living_dex_current_consumer,
)
from pokemon_red_completion.red_living_dex_production_runtime import (
    RedLivingDexProductionRuntimeLimits,
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
from pokemon_red_completion.red_living_dex_targeted_bank_retirement_reader import (
    RedLivingDexTargetedBankRetirementDescriptor,
    RedLivingDexTargetedBankRetirementExpectations,
    authenticate_red_living_dex_targeted_bank_retirement_plan,
    load_red_living_dex_targeted_bank_retirement_descriptor,
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
from pokemon_red_completion.red_living_dex_targeted_train_fit import (
    fit_red_living_dex_targeted_train_from_store,
    prepare_red_living_dex_targeted_fit_basis,
)
from pokemon_red_completion.red_living_dex_targeted_train_readiness import (
    audit_red_living_dex_targeted_train_readiness,
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

RESULT_SCHEMA = "pokemon.red.living-dex-retired-bank-train-campaign-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-retired-bank-train-campaign-failure.v1"
DEFAULT_PORT = 8768


class RetiredBankTrainCommandError(RuntimeError):
    """One sanitized production-consumer stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RetiredBankTrainCommandError("arguments")


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
    parser.add_argument("--context-catalog", required=True, type=Path)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", required=True, type=Path)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--expected-model-record-sha256", required=True)
    parser.add_argument("--prior-model-record-id", required=True)
    parser.add_argument("--expected-route-registry-sha256", required=True)
    parser.add_argument("--expected-runtime-identity-sha256", required=True)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--fit-on-complete", action="store_true")
    parser.add_argument("--hold-seconds", default=30, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    fit_executions = 0
    try:
        args = _parser().parse_args(argv)
        if args.hold_seconds < 0:
            raise RetiredBankTrainCommandError("arguments")
        stage = "current_source_authentication"
        consumer = RedLivingDexCurrentConsumerBinding(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=args.expected_source_bundle_sha256,
            exact_ci_run=args.exact_ci_run,
            exact_ci_attempt=args.exact_ci_attempt,
        )
        authenticate_red_living_dex_current_consumer(PROJECT_ROOT, consumer)
        if working_source_bundle_sha256(PROJECT_ROOT) != (args.expected_source_bundle_sha256):
            raise RetiredBankTrainCommandError("current_source_authentication")
        stage = "schedule_envelope_authentication"
        payload = base._read_schedule(args.schedule)
        expectations = _expectations(args)
        descriptor = load_red_living_dex_targeted_bank_retirement_descriptor(
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
        ) = base._authenticate_inputs(args)
        stage = "runtime_authentication"
        runtime = build_runtime_identity()
        require_pyboy_import_origins(runtime)
        if runtime.sha256 != args.expected_runtime_identity_sha256:
            raise RetiredBankTrainCommandError("runtime_authentication")
        route_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
        if route_registry.registry_sha256 != args.expected_route_registry_sha256:
            raise RetiredBankTrainCommandError("route_registry_authentication")
        stage = "action_free_schedule_replay"
        claim_registry = open_fixed_account_claim_registry()
        observed = _observe_retired_roots(
            descriptor,
            contexts,
            rom_path=rom_path,
            rom_bytes=rom_bytes,
            runtime=runtime,
            claim_registry=claim_registry,
            source_commit=consumer.source_commit,
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
            descriptor.schedule_descriptor,
            capabilities,
        )
        binding = authenticate_red_living_dex_targeted_bank_retirement_plan(
            payload,
            expected_plan_sha256=args.expected_schedule_sha256,
            expectations=expectations,
            freshly_derived_binding=fresh_binding,
        )
        train_slots = sum(slot.partition == "train" for slot in binding.schedule.slots)
        stage = "train_fit_basis_authentication"
        source = LivingDexCausalIntegrationSource(
            source_commit=consumer.source_commit,
            source_bundle_sha256=consumer.source_bundle_sha256,
            exact_ci_run=consumer.exact_ci_run,
            exact_ci_attempt=consumer.exact_ci_attempt,
        )
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        prepare_red_living_dex_targeted_fit_basis(
            store,
            binding,
            source=source,
            prior_model_record_id=args.prior_model_record_id,
            prior_model_sha256=args.expected_model_sha256,
            prior_model_record_sha256=args.expected_model_record_sha256,
            claim_registry=claim_registry,
            dry_run=args.preflight_only,
        )
        if args.preflight_only:
            print(
                json.dumps(
                    {
                        **descriptor.public_dict(),
                        "schema": RESULT_SCHEMA,
                        "status": "retired_bank_train_preflight_passed",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0
        stage = "retired_bank_train_execution"
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
            runtime_limits=RedLivingDexProductionRuntimeLimits(
                maximum_controller_actions=(base.MAXIMUM_CAMPAIGN_CONTROLLER_ACTIONS),
                maximum_emulator_frames=base.MAXIMUM_CAMPAIGN_EMULATOR_FRAMES,
            ),
            frame_observer=observer,
        )
        publisher = base._LiveProgressPublisher(state, binding, meter)
        fit_result = None
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
                        "status": "retired_bank_train_campaign_started",
                        "train_slots": train_slots,
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
                    execute=lambda assignment: run_red_living_dex_targeted_train_assignment(
                        assignment,
                        store=store,
                        claim_registry=claim_registry,
                        setup_execution_identity=execution_identity,
                        resolver=resolver,
                        meter=meter,
                    ),
                    effects=meter.checkpoint,
                    publish_progress=publisher,
                )
            finally:
                publisher.close()
            readiness = audit_red_living_dex_targeted_train_readiness(binding, receipts)
            if args.fit_on_complete and readiness.ready:
                stage = "train_model_update"
                state.publish(
                    red_living_dex_targeted_train_dashboard_snapshot(
                        binding,
                        RedLivingDexTargetedTrainDashboardProgress(
                            status="passed",
                            receipts=receipts,
                            effects=meter.checkpoint(),
                            fitting=True,
                        ),
                    )
                )
                fit_result = fit_red_living_dex_targeted_train_from_store(
                    store,
                    binding,
                    receipts,
                    source=source,
                )
                fit_executions = int(not fit_result.recovered_existing_artifact)
                state.publish(
                    red_living_dex_targeted_train_dashboard_snapshot(
                        binding,
                        RedLivingDexTargetedTrainDashboardProgress(
                            status="passed",
                            receipts=receipts,
                            effects=meter.checkpoint(),
                            fit_result=fit_result,
                        ),
                    )
                )
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
                    "model_fits": fit_executions,
                    "fit_requested": args.fit_on_complete,
                    "fit_result": fit_result.public_dict() if fit_result is not None else None,
                    "readiness": readiness.public_dict(),
                    "gameplay_model_predictions": 0,
                    "private_path_fields": 0,
                    "runner_sha256": RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
                    "schema": RESULT_SCHEMA,
                    "status": "retired_bank_train_campaign_terminal",
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
    except RetiredBankTrainCommandError as error:
        stage = error.stage
    except LivingDexCausalModelUpdateError as error:
        stage = "train_model_update_" + error.stage
        fit_executions = error.fit_executions
    except BaseException:
        pass
    print(
        json.dumps(
            {
                "development_slots_opened": 0,
                "model_fits": fit_executions,
                "model_predictions": None if stage.startswith("train_model_update") else 0,
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


def _expectations(
    args: argparse.Namespace,
) -> RedLivingDexTargetedBankRetirementExpectations:
    return RedLivingDexTargetedBankRetirementExpectations(
        source_commit=args.producer_source_commit,
        source_bundle_sha256=args.producer_source_bundle_sha256,
        context_catalog_sha256=args.expected_context_catalog_sha256,
        context_plan_sha256=args.expected_context_plan_sha256,
        model_sha256=args.expected_model_sha256,
        model_record_sha256=args.expected_model_record_sha256,
        rom_sha256=verify_rom(args.rom).sha256,
        route_registry_sha256=args.expected_route_registry_sha256,
        runtime_identity_sha256=args.expected_runtime_identity_sha256,
    )


def _observe_retired_roots(
    descriptor: RedLivingDexTargetedBankRetirementDescriptor,
    contexts: tuple[Any, ...],
    *,
    rom_path: Path,
    rom_bytes: bytes,
    runtime: RuntimeIdentity,
    claim_registry: Path,
    source_commit: str,
    owned_development_claim: Callable[[RedLivingDexAuthenticatedSetupRoot, str], bool]
    | None = None,
) -> tuple[RedLivingDexActionFreeRootObservation, ...]:
    support = base.freezer._PROVIDER_SUPPORT
    state = support["_DiagnosticState"]()
    observe_root = support["_observe_root"]
    schedule = descriptor.schedule_descriptor.schedule
    needed = {
        (slot.physical_root_sha256, slot.lineage_sha256): slot.partition for slot in schedule.slots
    }
    observations: list[RedLivingDexActionFreeRootObservation] = []
    found: set[tuple[str, str]] = set()
    for private in contexts:
        assignment = private.assignment
        capture = private.capture
        profile = private.profile
        if (
            assignment.partition != "validation"
            or not isinstance(capture, GoalManagerContextCapture)
            or not isinstance(profile, RedGoalContextProfile)
        ):
            continue
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
            raise RetiredBankTrainCommandError("private_input_authentication")
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
        key = (root.physical_root_sha256, lineage)
        if key not in needed:
            continue
        if needed[key] == "train":
            eligible = observe_living_dex_repeatable_root_eligibility(
                claim_registry,
                LivingDexRepeatableRootReservation(
                    schedule_sha256=schedule.schedule_sha256,
                    logical_root_sha256=root.root_consumption_sha256,
                    physical_root_sha256=root.physical_root_sha256,
                    runner_sha256=RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
                    source_commit=source_commit,
                ),
            )
        else:
            eligible = all(
                root_claim_is_available(claim_registry, digest)
                for digest in (
                    root.root_consumption_sha256,
                    root.physical_root_sha256,
                )
            )
            # The separate paired consumer may reobserve only its own exact
            # already-claimed roots during immutable recovery. The train command
            # never supplies this callback and retains fresh-development admission.
            if not eligible and owned_development_claim is not None:
                eligible = owned_development_claim(root, lineage)
        if not eligible:
            raise RetiredBankTrainCommandError("root_reservation_authentication")

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
            cluster_partition="development",
        )
        if (
            observation is None
            or not isinstance(observation, RedLivingDexActionFreeRootObservation)
            or key in found
        ):
            raise RetiredBankTrainCommandError("action_free_schedule_replay")
        found.add(key)
        observations.append(observation)
    if found != set(needed):
        raise RetiredBankTrainCommandError("action_free_schedule_replay")
    return tuple(observations)


if __name__ == "__main__":
    raise SystemExit(main())
