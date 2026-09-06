#!/usr/bin/env python3
"""Freeze an action-free Red development-bank retirement and successor split."""

# ruff: noqa: E402 -- pin reviewed project roots before local imports.

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
    run_name="red_living_dex_targeted_bank_retirement_support",
)
_WRITER_SUPPORT = runpy.run_path(
    str(SCRIPTS_ROOT / "freeze_red_living_dex_targeted_schedule.py"),
    run_name="red_living_dex_targeted_bank_retirement_writer",
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
)
from pokemon_red_completion.living_dex_causal_model_update import _model_from_record
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.red_living_dex_causal_inventory import (
    enumerate_red_living_dex_causal_capabilities,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    load_red_living_dex_development_supplement,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    derive_red_living_dex_provider_corridors,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_living_dex_targeted_bank_retirement import (
    plan_red_living_dex_targeted_bank_retirement,
)
from pokemon_red_completion.red_living_dex_targeted_exclusions import (
    load_red_living_dex_targeted_training_exclusions,
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

RESULT_SCHEMA = "pokemon.red.living-dex-targeted-bank-retirement-freeze-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-targeted-bank-retirement-freeze-failure.v1"
PRIVATE_PLAN_SCHEMA = "pokemon.red.private-living-dex-targeted-bank-retirement-plan.v1"


class TargetedBankRetirementFreezeError(RuntimeError):
    """One sanitized action-free retirement stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise TargetedBankRetirementFreezeError("arguments")


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
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--expected-model-record-sha256", required=True)
    parser.add_argument("--prior-model-record-id", required=True)
    parser.add_argument("--plan-out", type=Path, required=True)
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
            context_catalog_sha256,
            context_plan_sha256,
        ) = _support("_authenticate_inputs")(args, source_commit, source_bundle)
        state.authenticated_contexts = len(contexts)
        stage = "private_exclusion_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        claim_registry = open_fixed_account_claim_registry()
        prior = store.find_sealed_record(
            args.prior_model_record_id,
            expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
        )
        if prior is None or (
            prior.summary.record_sha256 != args.expected_model_record_sha256
            or _model_from_record(prior).model_sha256 != args.expected_model_sha256
        ):
            raise TargetedBankRetirementFreezeError("prior_model_authentication")
        supplement = load_red_living_dex_development_supplement(store)
        exclusions = load_red_living_dex_targeted_training_exclusions(store, supplement)
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
            effects_after = meter.checkpoint()
            stage = "outcome_blind_bank_retirement"
            capabilities = enumerate_red_living_dex_causal_capabilities(
                candidates,
                world=world,
                corridors=corridors,
                effects_before=effects_before,
                effects_after=effects_after,
            )
            frozen = plan_red_living_dex_targeted_bank_retirement(
                capabilities,
                excluded_lineages=exclusions.excluded_lineages,
                excluded_physical_roots=exclusions.development_physical_roots,
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
        stage = "private_plan_publication"
        private_plan = {
            "binding": frozen.private_dict(),
            "binding_sha256": frozen.binding_sha256,
            "context_catalog_sha256": context_catalog_sha256,
            "context_plan_sha256": context_plan_sha256,
            "freezer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "model_record_sha256": args.expected_model_record_sha256,
            "model_sha256": args.expected_model_sha256,
            "rom_sha256": rom_sha256,
            "route_registry_sha256": route_registry.registry_sha256,
            "runtime_identity_sha256": runtime.sha256,
            "schema": PRIVATE_PLAN_SCHEMA,
            "source_bundle_sha256": source_bundle,
            "source_commit": source_commit,
        }
        plan_sha256 = _writer("_write_new_private_json")(
            args.plan_out,
            private_plan,
        )
        print(
            json.dumps(
                {
                    **frozen.public_dict(),
                    "collection_authorized": False,
                    "model_fit_authorized": False,
                    "outcome_collection_authorized": False,
                    "plan_sha256": plan_sha256,
                    "schema": RESULT_SCHEMA,
                    "source_bundle_sha256": source_bundle,
                    "source_commit": source_commit,
                    "status": "targeted_bank_retirement_frozen",
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except TargetedBankRetirementFreezeError as error:
        stage = error.stage
    except BaseException:
        pass
    print(
        json.dumps(
            {
                "authenticated_contexts": int(getattr(state, "authenticated_contexts", 0)),
                "controller_actions": int(getattr(state, "controller_actions", 0)),
                "emulator_frames": int(getattr(state, "emulator_frames", 0)),
                "model_fits": 0,
                "model_predictions": 0,
                "outcomes_opened": 0,
                "private_identity_fields": 0,
                "private_path_fields": 0,
                "root_claims": 0,
                "schema": FAILURE_SCHEMA,
                "stage": _safe_stage(stage),
                "status": "failed_closed",
                "teacher_queries": 0,
            },
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
            character.islower() or character.isdigit() or character == "_" for character in stage
        )
    ):
        return stage
    return "unexpected_failure"


def _support(name: str) -> Any:
    try:
        return _PROVIDER_SUPPORT[name]
    except KeyError:
        raise TargetedBankRetirementFreezeError("support_binding") from None


def _writer(name: str) -> Any:
    try:
        return _WRITER_SUPPORT[name]
    except KeyError:
        raise TargetedBankRetirementFreezeError("writer_binding") from None


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
