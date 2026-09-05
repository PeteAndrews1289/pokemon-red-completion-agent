#!/usr/bin/env python3
"""Audit untouched Red supply for the targeted train and paired-control gate."""

# ruff: noqa: E402 -- pin reviewed script/package roots before project imports.

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
    run_name="red_living_dex_targeted_update_capacity_support",
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.red_living_dex_causal_inventory import (
    audit_red_living_dex_targeted_update_capacity,
    enumerate_red_living_dex_causal_capabilities,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    load_red_living_dex_development_supplement,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    inventory_red_living_dex_development_supply,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    derive_red_living_dex_provider_corridors,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_living_dex_targeted_exclusions import (
    build_red_living_dex_targeted_exclusions,
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

RESULT_SCHEMA = "pokemon.red.living-dex-targeted-update-capacity-audit-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-targeted-update-capacity-audit-failure.v1"


class TargetedUpdateCapacityAuditError(RuntimeError):
    """One sanitized action-free capacity stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise TargetedUpdateCapacityAuditError("arguments")


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
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--supplemental-state", action="append", default=[], type=Path)
    parser.add_argument(
        "--expected-supplemental-physical-root-sha256",
        action="append",
        default=[],
    )
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--expected-model-record-sha256", required=True)
    parser.add_argument(
        "--repeatable-train",
        action="store_true",
        help=(
            "allow up to five reset episodes per authenticated train root while "
            "development remains one-shot and held out"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    state_type = cast(Any, _PROVIDER_SUPPORT["_DiagnosticState"])
    state = state_type()
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
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
        stage = "private_exclusion_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        claim_registry = open_fixed_account_claim_registry()
        supply = inventory_red_living_dex_development_supply(
            store,
            claim_registry=claim_registry,
            expected_model_sha256=args.expected_model_sha256,
            expected_model_record_sha256=args.expected_model_record_sha256,
        )
        supplement = load_red_living_dex_development_supplement(store)
        exclusions = build_red_living_dex_targeted_exclusions(supply, supplement)
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
            stage = "targeted_compatibility_census"
            capabilities = enumerate_red_living_dex_causal_capabilities(
                candidates,
                world=world,
                corridors=corridors,
                effects_before=effects_before,
                effects_after=effects_after,
            )
            result = audit_red_living_dex_targeted_update_capacity(
                capabilities,
                excluded_lineages=exclusions.excluded_lineages,
                excluded_physical_roots=exclusions.development_physical_roots,
                maximum_train_replays_per_context=(
                    5 if args.repeatable_train else 1
                ),
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
        print(
            json.dumps(
                {
                    **result.public_dict(),
                    "authenticated_contexts": state.authenticated_contexts,
                    "authenticated_supplemental_roots": (
                        state.authenticated_supplemental_roots
                    ),
                    "collection_authorized": False,
                    "development_reuse_enabled": False,
                    "exclusions": exclusions.public_dict(),
                    "repeatable_train_enabled": bool(args.repeatable_train),
                    "provider_executions": state.provider_executions,
                    "rom_sha256": rom_sha256,
                    "schema": RESULT_SCHEMA,
                    "source_catalog_partition_reused_as_prospective_label": False,
                    "training_source_policy": (
                        "bounded_resets_from_authenticated_train_only"
                        if args.repeatable_train
                        else "fresh_unclaimed_only"
                    ),
                    "status": (
                        "targeted_update_capacity_ready"
                        if result.capacity_sufficient
                        else "targeted_update_capacity_insufficient"
                    ),
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except TargetedUpdateCapacityAuditError as error:
        stage = error.stage
    except BaseException:
        pass
    print(
        json.dumps(
            {
                "authenticated_contexts": int(
                    getattr(state, "authenticated_contexts", 0)
                ),
                "authenticated_supplemental_roots": int(
                    getattr(state, "authenticated_supplemental_roots", 0)
                ),
                "collection_authorized": False,
                "controller_actions": int(getattr(state, "controller_actions", 0)),
                "emulator_frames": int(getattr(state, "emulator_frames", 0)),
                "model_fits": int(getattr(state, "model_fits", 0)),
                "model_predictions": int(getattr(state, "model_predictions", 0)),
                "outcomes_opened": 0,
                "private_identity_fields": 0,
                "private_path_fields": 0,
                "provider_executions": int(getattr(state, "provider_executions", 0)),
                "root_claims": int(getattr(state, "root_claims", 0)),
                "schema": FAILURE_SCHEMA,
                "stage": _safe_stage(stage),
                "status": "failed_closed",
                "teacher_queries": int(getattr(state, "teacher_queries", 0)),
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _safe_stage(stage: object) -> str:
    if (
        isinstance(stage, str)
        and stage
        and all(
            character.islower() or character.isdigit() or character == "_"
            for character in stage
        )
    ):
        return stage
    return "unexpected_failure"


def _support(name: str) -> Any:
    try:
        return _PROVIDER_SUPPORT[name]
    except KeyError:
        raise TargetedUpdateCapacityAuditError("support_binding") from None


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
