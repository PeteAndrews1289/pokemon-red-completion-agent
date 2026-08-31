#!/usr/bin/env python3
"""Run one action-free Red census against the frozen clustered powered V2 design.

The command authenticates the public source and private inventory, observes
only still-unused nonsealed roots in isolated emulator instances, enumerates
their genuine Red menu compatibility, preserves immutable lineage partitions,
and emits aggregate path-free capacity bounds.  It has no controller, claim
writer, behavior draw, teacher, outcome reader, model scorer, or fitter.
"""

# ruff: noqa: E402 -- pin script/package roots before project imports.

from __future__ import annotations

import argparse
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
    run_name="red_living_dex_clustered_powered_capacity_support",
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.living_dex_clustered_powered_capacity import (
    audit_living_dex_clustered_powered_capacity,
    build_living_dex_clustered_powered_allocation,
)
from pokemon_red_completion.living_dex_clustered_powered_design import (
    LivingDexClusteredPoweredDesign,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    enumerate_red_living_dex_causal_capabilities,
)
from pokemon_red_completion.red_living_dex_clustered_powered_capacity import (
    adapt_red_living_dex_clustered_powered_capacity,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
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

RESULT_SCHEMA = "pokemon.red.living-dex-clustered-powered-capacity-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-clustered-powered-capacity-failure.v1"


class PoweredCapacityCensusError(RuntimeError):
    """One sanitized action-free census stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise PoweredCapacityCensusError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-design-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--supplemental-state", action="append", default=[], type=Path)
    parser.add_argument(
        "--expected-supplemental-physical-root-sha256",
        action="append",
        default=[],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    diagnostic_type = cast(Any, _PROVIDER_SUPPORT["_DiagnosticState"])
    state = diagnostic_type()
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "design_authentication"
        design = LivingDexClusteredPoweredDesign()
        if args.expected_design_sha256 != design.design_sha256:
            raise PoweredCapacityCensusError(stage)
        stage = "source_authentication"
        source_commit, source_bundle = _support("_authenticate_source")(args)
        stage = "private_input_authentication"
        (
            rom_path,
            rom_sha256,
            rom_bytes,
            contexts,
            _catalog_sha256,
            _context_plan_sha256,
        ) = _support("_authenticate_inputs")(args, source_commit, source_bundle)
        state.authenticated_contexts = len(contexts)
        stage = "supplemental_root_authentication"
        supplements = _support("_authenticate_supplemental_roots")(
            tuple(args.supplemental_state),
            tuple(args.expected_supplemental_physical_root_sha256),
        )
        state.authenticated_supplemental_roots = len(supplements)
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
            powered_lineages = adapt_red_living_dex_clustered_powered_capacity(
                candidates,
                capabilities,
            )
            stage = "constructive_allocation_witness"
            allocation = build_living_dex_clustered_powered_allocation(
                powered_lineages,
                design=design,
            )
            audit = audit_living_dex_clustered_powered_capacity(
                powered_lineages,
                allocation=allocation,
                design=design,
            )
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
                selected=candidates,
                claim_registry=claim_registry,
            )
        hard_reasons = tuple(
            reason for reason in audit.reasons if reason != "exact_allocation_witness_absent"
        )
        if audit.capacity_proven:
            status = "authenticated_action_free_capacity_proven_exact_freeze_required"
        elif hard_reasons:
            status = "authenticated_action_free_capacity_falsified_before_gameplay"
        else:
            status = "necessary_bounds_passed_exact_allocation_freeze_required"
        result = {
            **audit.public_dict(),
            "authenticated_contexts": state.authenticated_contexts,
            "authenticated_supplemental_roots": (state.authenticated_supplemental_roots),
            "consumed_contexts": state.consumed_contexts,
            "consumed_supplemental_roots": state.consumed_supplemental_roots,
            "eligible_root_pool": state.eligible_root_pool,
            "eligible_supplemental_roots": state.eligible_supplemental_roots,
            "hard_capacity_reasons": list(hard_reasons),
            "ineligible_control_contexts": state.ineligible_control_contexts,
            "schema": RESULT_SCHEMA,
            "source_catalog_partition_reused_as_prospective_label": False,
            "source_train_roots": state.source_train_roots,
            "source_validation_roots": state.source_validation_roots,
            "status": status,
        }
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except PoweredCapacityCensusError as error:
        stage = error.stage
    except BaseException:
        pass
    failure = {
        "authenticated_contexts": state.authenticated_contexts,
        "authenticated_supplemental_roots": state.authenticated_supplemental_roots,
        "consumed_contexts": state.consumed_contexts,
        "controller_actions": state.controller_actions,
        "eligible_root_pool": state.eligible_root_pool,
        "emulator_frames": state.emulator_frames,
        "model_fits": state.model_fits,
        "model_predictions": state.model_predictions,
        "outcomes": state.outcomes,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_executions": state.provider_executions,
        "root_claims": state.root_claims,
        "schema": FAILURE_SCHEMA,
        "stage": stage,
        "status": "failed_closed",
        "teacher_queries": state.teacher_queries,
    }
    print(json.dumps(failure, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 1


def _support(name: str) -> Any:
    try:
        return _PROVIDER_SUPPORT[name]
    except KeyError:
        raise PoweredCapacityCensusError("support_binding") from None


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
