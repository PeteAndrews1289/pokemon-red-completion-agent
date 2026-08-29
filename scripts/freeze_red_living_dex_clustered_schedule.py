#!/usr/bin/env python3
"""Freeze the exact Red 8+4 clustered curriculum without controller input.

This command repeats the authenticated, action-free root observation used by
the public capacity census, reproduces its exact clustered schedule, joins the
twelve selected scenarios to their private Red contexts and setup recipes, and
publishes one immutable sealed plan.  It has no behavior selector, claim writer,
controller executor, teacher, outcome reader, model scorer, or fitter.
"""

# ruff: noqa: E402 -- pin reviewed script/package roots before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

_PROVIDER_SUPPORT = runpy.run_path(
    str(SCRIPTS_ROOT / "freeze_red_living_dex_provider_plan.py"),
    run_name="red_living_dex_clustered_schedule_support",
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
    enumerate_red_living_dex_causal_capabilities,
    schedule_red_living_dex_clustered_integration,
)
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
    RedLivingDexClusteredFrozenScenario,
    RedLivingDexClusteredPrivatePlan,
    RedLivingDexClusteredScheduleBindings,
    validate_red_living_dex_clustered_private_plan,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    derive_red_living_dex_provider_corridors,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.runtime_identity import (
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)

RESULT_SCHEMA = "pokemon.red.living-dex-clustered-schedule-freeze-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-clustered-schedule-freeze-failure.v1"
CENSUS_RECEIPT_PATH = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-clustered-curriculum-census-v1-2026-08-29.json"
)
CENSUS_RECEIPT_SHA256 = "f55d54101b89fb440495d87cfc78e8c7a32cf386271ce81dc8ce7fa922c296f7"
EXPECTED_SCHEDULE_SHA256 = "35c00f382b5cd0f52b5231f0114eee7f423beb49c9fe4235ffe840fcc51dc905"
EXPECTED_POLICY_SHA256 = "dc72fb9449f7279c12b673b266e0973d01b62577f99d22ec7fdb14fceb8589be"


class ClusteredScheduleFreezeError(RuntimeError):
    """One sanitized action-free freezer stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise ClusteredScheduleFreezeError("arguments")


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
    parser.add_argument("--supplemental-state", action="append", default=[], type=Path)
    parser.add_argument(
        "--expected-supplemental-physical-root-sha256",
        action="append",
        default=[],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    state_type = cast(Any, _PROVIDER_SUPPORT["_DiagnosticState"])
    state = state_type()
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "census_evidence_authentication"
        _authenticate_census_receipt()
        stage = "source_authentication"
        source_commit, source_bundle = _support("_authenticate_source")(args)
        stage = "private_input_authentication"
        (
            rom_path,
            rom_sha256,
            rom_bytes,
            contexts,
            catalog_sha256,
            context_plan_sha256,
        ) = _support("_authenticate_inputs")(args, source_commit, source_bundle)
        state.authenticated_contexts = len(contexts)
        stage = "supplemental_root_authentication"
        supplements = _support("_authenticate_supplemental_roots")(
            tuple(args.supplemental_state),
            tuple(args.expected_supplemental_physical_root_sha256),
        )
        state.authenticated_supplemental_roots = len(supplements)
        stage = "private_namespace_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "runtime_authentication"
        runtime = build_runtime_identity()
        require_pyboy_import_origins(runtime)
        stage = "route_world_derivation"
        route_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
        world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
        corridors = derive_red_living_dex_provider_corridors(world)
        meter = RedLivingDexSetupEffectMeter()
        effects_before = meter.checkpoint()
        stage = "action_free_root_observation"
        claim_registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(claim_registry, exclusive=False):
            candidates = _support("_observe_candidates")(
                contexts,
                rom_path=rom_path,
                rom_bytes=rom_bytes,
                runtime=runtime,
                claim_registry=claim_registry,
                state=state,
            )
            candidates = (
                *candidates,
                *_support("_observe_supplemental_candidates")(
                    supplements,
                    rom_path=rom_path,
                    rom_bytes=rom_bytes,
                    runtime=runtime,
                    claim_registry=claim_registry,
                    state=state,
                ),
            )
            effects_after = meter.checkpoint()
            stage = "complete_template_compatibility_census"
            capabilities = enumerate_red_living_dex_causal_capabilities(
                candidates,
                world=world,
                corridors=corridors,
                effects_before=effects_before,
                effects_after=effects_after,
            )
            schedule = schedule_red_living_dex_clustered_integration(capabilities)
            if (
                schedule.schedule_sha256 != EXPECTED_SCHEDULE_SHA256
                or schedule.policy.policy_sha256 != EXPECTED_POLICY_SHA256
            ):
                raise ClusteredScheduleFreezeError("clustered_schedule_reproduction")
            stage = "private_assignment_join"
            selected_capabilities = _selected_capabilities(schedule, capabilities)
            frozen_assignments = _frozen_assignments(
                schedule,
                selected_capabilities,
                contexts,
            )
            selected_roots = _selected_roots(selected_capabilities)
            stage = "protected_input_integrity"
            _support("_require_integrity")(
                args,
                source_commit=source_commit,
                source_bundle=source_bundle,
                rom_path=rom_path,
                rom_sha256=rom_sha256,
                rom_bytes=rom_bytes,
                runtime=runtime,
                route_registry_sha256=route_registry.registry_sha256,
                selected=selected_roots,
                claim_registry=claim_registry,
            )
            stage = "private_plan_encoding"
            bindings = RedLivingDexClusteredScheduleBindings(
                source_commit=source_commit,
                source_bundle_sha256=source_bundle,
                rom_sha256=rom_sha256,
                goal_registry_sha256=_sha(args.expected_registry_sha256),
                route_registry_sha256=route_registry.registry_sha256,
                context_catalog_sha256=catalog_sha256,
                context_plan_sha256=context_plan_sha256,
                runtime_identity_sha256=runtime.sha256,
                census_receipt_sha256=CENSUS_RECEIPT_SHA256,
            )
            plan = RedLivingDexClusteredPrivatePlan(
                bindings=bindings,
                schedule=schedule,
                assignments=frozen_assignments,
            )
            document = plan.private_dict()
            validate_private_record(document)
            validate_red_living_dex_clustered_private_plan(
                document,
                expected_bindings=bindings,
                expected_schedule_sha256=EXPECTED_SCHEDULE_SHA256,
                expected_policy_sha256=EXPECTED_POLICY_SHA256,
            )
            stage = "private_plan_publication"
            result = _publish_and_reopen(
                store,
                plan=plan,
                bindings=bindings,
                expected_schedule_sha256=EXPECTED_SCHEDULE_SHA256,
                expected_policy_sha256=EXPECTED_POLICY_SHA256,
            )
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except ClusteredScheduleFreezeError as error:
        stage = error.stage
    except BaseException:
        pass
    print(
        json.dumps(
            _failure_receipt(stage, state),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _authenticate_census_receipt() -> None:
    try:
        payload = CENSUS_RECEIPT_PATH.read_bytes()
        receipt = json.loads(payload)
        clustered = receipt["clustered_gate"]
        protected = receipt["protected_effects"]
    except BaseException:
        raise ClusteredScheduleFreezeError("census_evidence_authentication") from None
    if (
        hashlib.sha256(payload).hexdigest() != CENSUS_RECEIPT_SHA256
        or receipt.get("status")
        != "clustered_integration_capacity_passed_private_schedule_freeze_pending"
        or clustered.get("gate_passed") is not True
        or clustered.get("schedule_sha256") != EXPECTED_SCHEDULE_SHA256
        or clustered.get("policy_sha256") != EXPECTED_POLICY_SHA256
        or clustered.get("train_scenarios") != 8
        or clustered.get("development_scenarios") != 4
        or clustered.get("lineage_overlap") != 0
        or protected.get("collection_authorized") is not False
        or any(value != 0 for key, value in protected.items() if key != "collection_authorized")
    ):
        raise ClusteredScheduleFreezeError("census_evidence_authentication")


def _selected_capabilities(
    schedule: Any,
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
) -> tuple[RedLivingDexCausalRootCapability, ...]:
    by_key: dict[tuple[str, str], RedLivingDexCausalRootCapability] = {}
    for capability in capabilities:
        key = (
            capability.root.root.physical_root_sha256,
            capability.slot.slot_sha256,
        )
        if key in by_key:
            raise ClusteredScheduleFreezeError("private_assignment_join")
        by_key[key] = capability
    selected: list[RedLivingDexCausalRootCapability] = []
    for assignment in schedule.assignments:
        try:
            selected.append(
                by_key[
                    (
                        assignment.capability.physical_root_sha256,
                        assignment.capability.template_sha256,
                    )
                ]
            )
        except KeyError:
            raise ClusteredScheduleFreezeError("private_assignment_join") from None
    return tuple(selected)


def _frozen_assignments(
    schedule: Any,
    selected: tuple[RedLivingDexCausalRootCapability, ...],
    contexts: tuple[Any, ...],
) -> tuple[RedLivingDexClusteredFrozenScenario, ...]:
    contexts_by_root: dict[str, list[Any]] = {}
    for context in contexts:
        try:
            root_sha256 = context.root_consumption_sha256
        except BaseException:
            raise ClusteredScheduleFreezeError("private_assignment_join") from None
        contexts_by_root.setdefault(root_sha256, []).append(context)
    frozen: list[RedLivingDexClusteredFrozenScenario] = []
    for assignment, capability in zip(
        schedule.assignments,
        selected,
        strict=True,
    ):
        matches = contexts_by_root.get(
            capability.root.root.root_consumption_sha256,
            [],
        )
        if len(matches) != 1:
            raise ClusteredScheduleFreezeError("private_assignment_join")
        context = matches[0]
        try:
            context_identity = context.context_identity_sha256
            root_available = context.root_available
        except BaseException:
            raise ClusteredScheduleFreezeError("private_assignment_join") from None
        if root_available is not True:
            raise ClusteredScheduleFreezeError("private_assignment_join")
        frozen.append(
            RedLivingDexClusteredFrozenScenario(
                assignment=assignment,
                capability=capability,
                context_identity_sha256=context_identity,
            )
        )
    return tuple(frozen)


def _selected_roots(
    selected: tuple[RedLivingDexCausalRootCapability, ...],
) -> tuple[RedLivingDexActionFreeRootObservation, ...]:
    roots: dict[str, RedLivingDexActionFreeRootObservation] = {}
    for capability in selected:
        root = capability.root
        roots.setdefault(root.root.physical_root_sha256, root)
    return tuple(roots[key] for key in sorted(roots))


def _publish_and_reopen(
    store: PrivateArtifactRoot,
    *,
    plan: RedLivingDexClusteredPrivatePlan,
    bindings: RedLivingDexClusteredScheduleBindings,
    expected_schedule_sha256: str = EXPECTED_SCHEDULE_SHA256,
    expected_policy_sha256: str = EXPECTED_POLICY_SHA256,
) -> dict[str, object]:
    record = store.publish_sealed_record(
        RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
        kind=RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
        record=plan.private_dict(),
    )
    reopened = store.find_sealed_record(
        RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
        expected_kind=RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
    )
    if reopened is None or reopened.summary != record.summary:
        raise ClusteredScheduleFreezeError("private_plan_reopen")
    schedule = validate_red_living_dex_clustered_private_plan(
        reopened.read(),
        expected_bindings=bindings,
        expected_schedule_sha256=expected_schedule_sha256,
        expected_policy_sha256=expected_policy_sha256,
    )
    if schedule != plan.schedule:
        raise ClusteredScheduleFreezeError("private_plan_reopen")
    return {
        **plan.public_dict(),
        "plan_manifest_sha256": reopened.summary.manifest_sha256,
        "plan_record_sha256": reopened.summary.record_sha256,
        "private_plan_reopened": True,
        "schema": RESULT_SCHEMA,
    }


def _failure_receipt(stage: str, state: Any) -> dict[str, object]:
    safe_stage = (
        stage
        if isinstance(stage, str)
        and stage
        and all(
            character.islower() or character.isdigit() or character == "_" for character in stage
        )
        else "unexpected_failure"
    )
    return {
        "behavior_commitments": 0,
        "collection_authorized": False,
        "controller_actions": int(getattr(state, "controller_actions", 0)),
        "development_outcomes_opened": 0,
        "emulator_frames": int(getattr(state, "emulator_frames", 0)),
        "model_fits": int(getattr(state, "model_fits", 0)),
        "model_predictions": int(getattr(state, "model_predictions", 0)),
        "outcomes_observed": int(getattr(state, "outcomes", 0)),
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_executions": int(getattr(state, "provider_executions", 0)),
        "root_claims": int(getattr(state, "root_claims", 0)),
        "schema": FAILURE_SCHEMA,
        "stage": safe_stage,
        "status": "failed_closed",
        "teacher_queries": int(getattr(state, "teacher_queries", 0)),
        "unselected_action_targets": 0,
    }


def _support(name: str) -> Any:
    try:
        return _PROVIDER_SUPPORT[name]
    except KeyError:
        raise ClusteredScheduleFreezeError("support_binding") from None


def _sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ClusteredScheduleFreezeError("arguments")
    return value


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
