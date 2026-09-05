#!/usr/bin/env python3
"""Freeze the complete repeatable-train and one-shot-development Red schedule."""

# ruff: noqa: E402 -- pin reviewed project roots before local imports.

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
    run_name="red_living_dex_targeted_schedule_support",
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.red_living_dex_causal_inventory import (
    enumerate_red_living_dex_causal_capabilities,
    freeze_red_living_dex_targeted_schedule,
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

RESULT_SCHEMA = "pokemon.red.living-dex-targeted-schedule-freeze-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-targeted-schedule-freeze-failure.v1"
PRIVATE_PLAN_SCHEMA = "pokemon.red.private-living-dex-targeted-schedule-plan.v1"
MAXIMUM_CAPACITY_BYTES = 512 * 1024


class TargetedScheduleFreezeError(RuntimeError):
    """One sanitized freeze stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise TargetedScheduleFreezeError("arguments")


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
    parser.add_argument("--capacity-result", type=Path, required=True)
    parser.add_argument("--expected-capacity-result-sha256", required=True)
    parser.add_argument("--schedule-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    state_type = cast(Any, _PROVIDER_SUPPORT["_DiagnosticState"])
    state = state_type()
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "source_authentication"
        source_commit, source_bundle = _support("_authenticate_source")(args)
        stage = "capacity_authentication"
        capacity_sha256 = _authenticate_capacity_result(args.capacity_result)
        if capacity_sha256 != _sha256(
            args.expected_capacity_result_sha256,
            stage="capacity_authentication",
        ):
            raise TargetedScheduleFreezeError(stage)
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
            effects_after = meter.checkpoint()
            stage = "outcome_blind_schedule_freeze"
            capabilities = enumerate_red_living_dex_causal_capabilities(
                candidates,
                world=world,
                corridors=corridors,
                effects_before=effects_before,
                effects_after=effects_after,
            )
            frozen = freeze_red_living_dex_targeted_schedule(
                capabilities,
                excluded_lineages=exclusions.excluded_lineages,
                excluded_physical_roots=exclusions.development_physical_roots,
                maximum_train_replays_per_context=5,
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
        stage = "private_schedule_publication"
        freezer_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        private_plan = {
            "binding": frozen.private_dict(),
            "binding_sha256": frozen.binding_sha256,
            "capacity_result_sha256": capacity_sha256,
            "context_catalog_sha256": context_catalog_sha256,
            "context_plan_sha256": context_plan_sha256,
            "freezer_sha256": freezer_sha256,
            "model_record_sha256": args.expected_model_record_sha256,
            "model_sha256": args.expected_model_sha256,
            "rom_sha256": rom_sha256,
            "route_registry_sha256": route_registry.registry_sha256,
            "runtime_identity_sha256": runtime.sha256,
            "schema": PRIVATE_PLAN_SCHEMA,
            "source_bundle_sha256": source_bundle,
            "source_commit": source_commit,
        }
        plan_sha256 = _write_new_private_json(args.schedule_out, private_plan)
        print(
            json.dumps(
                {
                    **frozen.public_dict(),
                    "capacity_result_sha256": capacity_sha256,
                    "collection_authorized": False,
                    "model_fit_authorized": False,
                    "outcome_collection_authorized": False,
                    "plan_sha256": plan_sha256,
                    "schema": RESULT_SCHEMA,
                    "source_bundle_sha256": source_bundle,
                    "source_commit": source_commit,
                    "status": "repeatable_train_and_paired_development_schedule_frozen",
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except TargetedScheduleFreezeError as error:
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


def _authenticate_capacity_result(path: Path) -> str:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.lstat()
        if (
            resolved.is_symlink()
            or not resolved.is_file()
            or not 0 < metadata.st_size <= MAXIMUM_CAPACITY_BYTES
        ):
            raise OSError("unsafe capacity result")
        payload = resolved.read_bytes()
        document = json.loads(payload)
    except (OSError, json.JSONDecodeError):
        raise TargetedScheduleFreezeError("capacity_authentication") from None
    if (
        not isinstance(document, dict)
        or document.get("schema") != "pokemon.red.living-dex-repeatable-train-capacity-result.v1"
        or document.get("status") != "repeatable_train_capacity_ready"
        or document.get("capacity_sufficient") is not True
        or document.get("maximum_train_replays_per_context") != 5
        or document.get("development_reuse_enabled") is not False
        or document.get("train_maximum_matching") != 10
        or document.get("development_maximum_matching") != 8
        or any(
            document.get(key) != 0
            for key in (
                "controller_actions",
                "emulator_frames",
                "model_fits",
                "model_predictions",
                "outcomes_opened",
                "root_claims",
                "teacher_queries",
            )
        )
    ):
        raise TargetedScheduleFreezeError("capacity_authentication")
    return hashlib.sha256(payload).hexdigest()


def _write_new_private_json(path: Path, document: dict[str, object]) -> str:
    destination = path.resolve()
    try:
        if destination == PROJECT_ROOT or PROJECT_ROOT in destination.parents:
            raise OSError("schedule destination is tracked")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise OSError("schedule destination exists")
        payload = (
            json.dumps(
                document,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, TypeError, ValueError):
        raise TargetedScheduleFreezeError("private_schedule_publication") from None
    return hashlib.sha256(payload).hexdigest()


def _sha256(value: object, *, stage: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TargetedScheduleFreezeError(stage)
    return value


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
        raise TargetedScheduleFreezeError("support_binding") from None


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
