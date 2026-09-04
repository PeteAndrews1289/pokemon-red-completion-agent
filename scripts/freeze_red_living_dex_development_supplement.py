#!/usr/bin/env python3
"""Freeze the exact three-root Red development supplement without gameplay.

This command authenticates the published zero-effect supply audit, the exact
eighteen-example model, the historical held roots, and one action-free Red
capability inventory.  It selects only the measured three-root shortfall and
publishes a private development-only plan.  It has no behavior selector,
model scorer, claim writer, controller executor, teacher, or outcome reader.
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
    run_name="red_living_dex_development_supplement_support",
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.private_artifacts import (
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    enumerate_red_living_dex_causal_capabilities,
)
from pokemon_red_completion.red_living_dex_development_supplement_plan import (
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID,
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND,
    RedLivingDexDevelopmentSupplementBindings,
    freeze_red_living_dex_development_supplement_plan,
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

RESULT_SCHEMA = "pokemon.red.living-dex-development-supplement-freeze-command-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-development-supplement-freeze-command-failure.v1"
SUPPLY_AUDIT_EVIDENCE_PATH = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-development-supply-audit-v1-2026-09-04.json"
)
SUPPLY_AUDIT_EVIDENCE_SHA256 = "629e0a2ed25181b56a3926fae8d8a101aa6f4cc317060535031355e4ef13b42a"


class DevelopmentSupplementFreezeError(RuntimeError):
    """One sanitized action-free freezer stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise DevelopmentSupplementFreezeError("arguments")


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
    return parser


def main(argv: list[str] | None = None) -> int:
    state_type = cast(Any, _PROVIDER_SUPPORT["_DiagnosticState"])
    state = state_type()
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "supply_audit_evidence_authentication"
        _authenticate_supply_audit_evidence()
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
        stage = "private_namespace_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        claim_registry = open_fixed_account_claim_registry()
        stage = "held_supply_authentication"
        supply = inventory_red_living_dex_development_supply(
            store,
            claim_registry=claim_registry,
            expected_model_sha256=args.expected_model_sha256,
            expected_model_record_sha256=args.expected_model_record_sha256,
        )
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
            stage = "complete_template_compatibility_census"
            capabilities = enumerate_red_living_dex_causal_capabilities(
                candidates,
                world=world,
                corridors=corridors,
                effects_before=effects_before,
                effects_after=effects_after,
            )
            contexts_by_root = {
                item.root_consumption_sha256: item.context_identity_sha256 for item in contexts
            }
            if len(contexts_by_root) != len(contexts):
                raise DevelopmentSupplementFreezeError("private_assignment_join")
            stage = "supplement_selection"
            bindings = RedLivingDexDevelopmentSupplementBindings(
                source_commit=source_commit,
                source_bundle_sha256=source_bundle,
                rom_sha256=rom_sha256,
                goal_registry_sha256=_digest(
                    args.expected_registry_sha256,
                    "goal registry",
                ),
                route_registry_sha256=route_registry.registry_sha256,
                context_catalog_sha256=catalog_sha256,
                context_plan_sha256=context_plan_sha256,
                runtime_identity_sha256=runtime.sha256,
                supply_audit_evidence_sha256=(SUPPLY_AUDIT_EVIDENCE_SHA256),
                model_sha256=_digest(args.expected_model_sha256, "model"),
                model_record_sha256=_digest(
                    args.expected_model_record_sha256,
                    "model record",
                ),
            )
            plan = freeze_red_living_dex_development_supplement_plan(
                capabilities,
                supply=supply,
                context_identities=contexts_by_root,
                bindings=bindings,
            )
            selected_roots = tuple(item.capability.root for item in plan.assignments)
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
            document = plan.private_dict()
            validate_private_record(document)
            stage = "private_plan_publication"
            record = store.publish_sealed_record(
                RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID,
                kind=RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND,
                record=document,
            )
            reopened = store.find_sealed_record(
                RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID,
                expected_kind=(RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND),
            )
            if (
                reopened is None
                or reopened.summary != record.summary
                or canonical_sha256(reopened.read())
                != canonical_sha256(document)
            ):
                raise DevelopmentSupplementFreezeError("private_plan_reopen")
        result = {
            **plan.public_dict(),
            "plan_manifest_sha256": record.summary.manifest_sha256,
            "plan_record_sha256": record.summary.record_sha256,
            "private_plan_reopened": True,
            "schema": RESULT_SCHEMA,
        }
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except DevelopmentSupplementFreezeError as error:
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


def _authenticate_supply_audit_evidence() -> None:
    try:
        payload = SUPPLY_AUDIT_EVIDENCE_PATH.read_bytes()
        document = json.loads(payload.decode("ascii"))
        result = document["result"]
        source = document["source"]
        zero = document["zero_effects"]
    except BaseException:
        raise DevelopmentSupplementFreezeError("supply_audit_evidence_authentication") from None
    if (
        hashlib.sha256(payload).hexdigest() != SUPPLY_AUDIT_EVIDENCE_SHA256
        or document.get("status") != "two_held_roots_preserved_three_root_supplement_required"
        or result.get("available_development_roots") != 2
        or result.get("development_root_shortfall") != 2
        or result.get("minimum_new_roots_to_freeze") != 3
        or result.get("missing_option_kinds") != ["manage_storage"]
        or result.get("lineage_overlap_with_train") != 0
        or result.get("state_overlap_with_train") != 0
        or source.get("exact_main_ci_conclusion") != "success"
        or any(value != 0 for value in zero.values())
    ):
        raise DevelopmentSupplementFreezeError("supply_audit_evidence_authentication")


def _digest(value: object, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DevelopmentSupplementFreezeError(f"{subject.replace(' ', '_')}_authentication")
    return value


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
        "training_targets": 0,
        "unselected_action_targets": 0,
    }


def _support(name: str) -> Any:
    try:
        return _PROVIDER_SUPPORT[name]
    except KeyError:
        raise DevelopmentSupplementFreezeError("support_binding") from None


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
