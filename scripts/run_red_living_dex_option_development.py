#!/usr/bin/env python3
"""Run one repeatable Red living-Dex option from full menu to verified outcome."""

# ruff: noqa: E402 -- pin reviewed script/package origins before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

import run_red_dual_capability_preflight as support
from freeze_rootless_execution_manifest import _current_public_bindings
from public_execution_manifest import (
    PublicExecutionManifestError,
    read_tracked_public_evidence,
)

from pokemon_red_completion.blaine import (
    DIGLETT_SPECIES_ID,
    DIGLETTS_CAVE_TRAINING_VENUE,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.encounters import ENCOUNTER_LOG_VARIABLE
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.gen1_field_moves import (
    Gen1FieldMovePort,
    gen1_field_capabilities,
)
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    root_consumption_sha256,
    write_root_claim,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.goal_manager_trajectory import ordered_goal_manager_question
from pokemon_red_completion.observation import ItemId, MapId, PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import (
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    RedSemanticVenueCaptureAdapter,
    SemanticCaptureReadiness,
    SemanticVenueAreaExecutor,
    SemanticVenueCapturePlan,
    SemanticVenueRouteBinding,
    bind_bounded_evolution_offer,
    build_red_dual_capability_scenario,
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    RedDependencySpeciesBinding,
    red_dual_capability_curriculum_design,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.red_living_dex_option_development import (
    execute_red_living_dex_option,
    prepare_red_living_dex_option,
    score_red_living_dex_option,
)
from pokemon_red_completion.red_party import DUGTRIO_SPECIES_ID
from pokemon_red_completion.rom import verify_rom
from pokemon_red_completion.runtime_identity import require_pyboy_import_origins
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor
from pokemon_red_completion.training_venue import WarpSafeVenueWalker

LANE_ID = "repeatable-red-living-dex-option-execution-v1"
RUNNER_RELATIVE = "scripts/run_red_living_dex_option_development.py"
RESULT_SCHEMA = "pokemon.red.living-dex-option-development-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-option-development-failure.v1"
START_RECORD_KIND = "red-living-dex-option-start-v1"
TERMINAL_RECORD_KIND = "red-living-dex-option-terminal-v1"
REDIRECT_RECEIPT_PATH = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-development-redirect-v1-2026-08-25.json"
)
REDIRECT_RECEIPT_SHA256 = "b7678e456333ffa82e26c1507a0677bc6d03a4d25092f56d13e85d62d5facb72"

DEPENDENCIES = tuple(
    sorted(
        {
            *support.DEPENDENCIES,
            "decision=src/pokemon_red_completion/red_living_dex_option_development.py",
            "runner_support=scripts/run_red_dual_capability_preflight.py",
        }
    )
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAX_CONTROLLER_ACTIONS = 5_000
_MAX_CONTROLLER_FRAMES = 4_000_000
_MAX_FRAMES_PER_WINDOW = 4_000_000


class RedLivingDexOptionRunError(RuntimeError):
    """One sanitized failure stage for the repeatable development runner."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
        super().__init__(self.stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedLivingDexOptionRunError("arguments")


@dataclass(frozen=True, slots=True)
class _ExecutionResult:
    public: Mapping[str, object]
    settled: bool


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4))
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        if args.speed is not None and not args.watch:
            raise RedLivingDexOptionRunError("arguments")
        stage = "public_source_authentication"
        gate = _development_gate()
        stage = "private_readiness_authentication"
        readiness = support._prepare_readiness(
            args,
            gate,
            selected_slot_id=_slot_id(args.slot_id),
        )
        stage = "unused_development_context_authentication"
        excluded_reset_states = _excluded_v1_reset_states(args, readiness)
        stage = "model_selected_option_execution"
        result = _execute(args, readiness, excluded_reset_states)
        print(
            json.dumps(
                result.public,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0 if result.settled else 2
    except RedLivingDexOptionRunError as error:
        failure_stage = error.stage
    except BaseException:
        failure_stage = stage
    print(
        json.dumps(
            _failure_receipt(failure_stage),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _development_gate() -> support._PublicGate:
    support._require_script_import_origins()
    support._require_project_import_origins()
    for path, digest in (
        (support.DESIGN_RECEIPT_PATH, support.DESIGN_RECEIPT_SHA256),
        (support.RUNTIME_RECEIPT_PATH, support.RUNTIME_RECEIPT_SHA256),
        (REDIRECT_RECEIPT_PATH, REDIRECT_RECEIPT_SHA256),
    ):
        try:
            read_tracked_public_evidence(
                path,
                repository_root=PROJECT_ROOT,
                expected_sha256=digest,
            )
        except (PublicExecutionManifestError, TypeError, ValueError):
            raise RedLivingDexOptionRunError("public_evidence_authentication") from None
    evaluation_design = support._read_evaluation_design()
    public = _current_public_bindings(
        lane_id=LANE_ID,
        runner=RUNNER_RELATIVE,
        dependencies=list(DEPENDENCIES),
    )
    if public.get("source_bundle_sha256") != working_source_bundle_sha256(PROJECT_ROOT):
        raise RedLivingDexOptionRunError("public_source_authentication")
    gate_identity = canonical_sha256(
        {
            "schema": "pokemon.red.repeatable-development-public-gate.v1",
            "lane_id": LANE_ID,
            "public_bindings": dict(public),
            "curriculum_design_sha256": canonical_sha256(
                red_dual_capability_curriculum_design().public_dict()
            ),
            "evaluation_design_sha256": evaluation_design.design_sha256,
        }
    )
    return support._PublicGate(gate_identity, public, evaluation_design)


def _excluded_v1_reset_states(
    args: argparse.Namespace,
    readiness: support._Readiness,
) -> frozenset[str]:
    if readiness.assignment.slot_id == support.SELECTED_SLOT_ID:
        raise RedLivingDexOptionRunError("retired_v1_context_reuse")
    source_commit = _commit(args.registry_source_commit, "registry source")
    registry = load_committed_goal_manager_registry_at_revision(PROJECT_ROOT, source_commit)
    catalog_bytes = support._read_external_bytes(
        args.context_catalog,
        maximum_bytes=support._MAX_DOCUMENT_BYTES,
        forbidden=(readiness.rom_path,),
    )
    if hashlib.sha256(catalog_bytes).hexdigest() != _sha(
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise RedLivingDexOptionRunError("context_catalog_authentication")
    catalog = parse_goal_manager_context_catalog(catalog_bytes, registry)
    retired = catalog.entry(support.SELECTED_SLOT_ID)
    if (
        readiness.capture.state_sha256 == retired.state_sha256
        and readiness.capture.envelope_sha256 == retired.envelope_sha256
    ):
        raise RedLivingDexOptionRunError("retired_v1_context_reuse")
    return frozenset({retired.state_sha256})


def _execute(
    args: argparse.Namespace,
    readiness: support._Readiness,
    excluded_reset_states: frozenset[str],
) -> _ExecutionResult:
    if os.environ.get(ENCOUNTER_LOG_VARIABLE, "").strip():
        raise RedLivingDexOptionRunError("trajectory_side_channel_environment")
    physical_root = root_consumption_sha256(
        state_sha256=readiness.capture.state_sha256,
        envelope_sha256=readiness.capture.envelope_sha256,
    )
    claim_registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(claim_registry, exclusive=False):
        support._require_fit_claim(claim_registry)
        if not root_claim_is_available(claim_registry, physical_root):
            raise RedLivingDexOptionRunError("development_root_already_consumed")

    require_pyboy_import_origins(readiness.runtime)
    route_world = StrategicScenarioRouteWorld.from_rom(readiness.rom_bytes)
    with PyBoyAdapter(
        readiness.rom_path,
        watch=bool(args.watch),
        speed=args.speed,
        expected_rom=POKEMON_RED_US_REV_0,
    ) as emulator:
        require_pyboy_import_origins(readiness.runtime)
        emulator.load_state_bytes(readiness.capture.state_bytes)
        require_pyboy_import_origins(readiness.runtime)
        frames = WindowedFrameBudgetController(
            emulator,
            maximum_frames_per_window=_MAX_FRAMES_PER_WINDOW,
            maximum_total_frames=_MAX_CONTROLLER_FRAMES,
        )
        reader = PokemonRedStateReader(frames)
        frame_safe = FrameSafeExecutor(
            frames,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        limited = HardCompositionActionLimiter(
            frame_safe,
            maximum_actions_per_decision=_MAX_CONTROLLER_ACTIONS,
            maximum_episode_actions=_MAX_CONTROLLER_ACTIONS,
        )
        actions = CountingExecutor(limited)
        context_runtime = build_red_goal_context_runtime(
            profile=readiness.profile,
            capture=readiness.capture,
            emulator=frames,
            reader=reader,
        )
        observation = context_runtime.adapter.observe()
        battle_state = observation.raw.battle_state
        if type(battle_state) is not int or not 0 <= battle_state <= 0xFF:  # noqa: E721
            raise RedLivingDexOptionRunError("capture_capability_authentication")
        bindings = context_runtime.enumerator(actions).enumerate(observation)
        historical_question = ordered_goal_manager_question(
            assignment_id=readiness.assignment.assignment_id,
            decision_index=0,
            situation=observation.situation,
            opportunities=bindings.opportunities,
        )
        if (
            historical_question.ordered_policy_input_sha256
            != readiness.catalog_entry.question_sha256
            or historical_question.policy_context_sha256
            != readiness.catalog_entry.policy_context_sha256
            or historical_question.available_menu_sha256
            != readiness.catalog_entry.available_menu_sha256
            or goal_binding_manifest_sha256(bindings)
            != readiness.catalog_entry.binding_manifest_sha256
            or tuple(item.kind for item in bindings.bindings)
            != readiness.catalog_entry.available_goal_kinds
        ):
            raise RedLivingDexOptionRunError("historical_context_replay")
        try:
            evolution_binding = next(
                item for item in bindings.bindings if item.kind is GoalKind.EVOLVE_SPECIES
            )
        except StopIteration:
            raise RedLivingDexOptionRunError(
                "evolution_capability_authentication"
            ) from None
        evolution_specs = tuple(
            item for item in readiness.profile.providers if item.kind is GoalKind.EVOLVE_SPECIES
        )
        if len(evolution_specs) != 1 or evolution_binding.binding_ref != (
            "pokemon.red:evolution:diglett-to-dugtrio:"
            f"profile-{readiness.profile.profile_sha256}:"
            f"config-{evolution_specs[0].configuration_sha256}"
        ):
            raise RedLivingDexOptionRunError("evolution_capability_authentication")

        species = RedDependencySpeciesBinding(
            red_species_ref(red_internal_species_number(DIGLETT_SPECIES_ID)),
            red_species_ref(red_internal_species_number(DUGTRIO_SPECIES_ID)),
        )
        before_ledger = dependency_specimen_ledger(observation.collection_observation)
        scenarios = tuple(
            item
            for item in red_dual_capability_scenario_specs()
            if item.before.precursor_count == before_ledger.count(species.precursor_species_ref)
            and item.before.evolved_count == before_ledger.count(species.evolved_species_ref)
        )
        if len(scenarios) != 1:
            raise RedLivingDexOptionRunError("dependency_scenario_authentication")
        scenario = scenarios[0]

        traversal = Gen1TraversalObserver(
            reader,
            hazard_projector=Gen1TrainerSightProjector(readiness.rom_bytes, reader),
            capability_projector=lambda raw: gen1_field_capabilities(frames, raw),
        )
        start = traversal.observe()
        route_plan = route_world.plan_to_map(start, int(MapId.DIGLETTS_CAVE))
        planner_binding = canonical_sha256(
            {
                "schema": "pokemon.red.private-dual-capability-router-binding.v1",
                "rom_sha256": readiness.rom.sha256,
                "source_bundle_sha256": readiness.gate.public_bindings[
                    "source_bundle_sha256"
                ],
                "context_identity_sha256": readiness.context_identity_sha256,
                "goal_map": int(MapId.DIGLETTS_CAVE),
                "route_cost": route_plan.cost,
            }
        )
        route = SemanticVenueRouteBinding(route_plan, planner_binding)
        field_actions = Gen1FieldMovePort(
            actions,
            reader,
            frames,
            cut_block_swaps={
                swap.before: swap.after for swap in route_world.rules.cut_block_swaps
            },
        )
        walker = DIGLETTS_CAVE_TRAINING_VENUE.fresh_walk_to_grass()
        if not isinstance(walker, WarpSafeVenueWalker):
            raise RedLivingDexOptionRunError("capture_capability_authentication")
        live_capture = LiveWildEncounterExecutor(
            frames,
            actions,
            reader,
            DEFAULT_SURGE_TIMING,
            label="semantic target capture",
        )
        area = SemanticVenueAreaExecutor(
            delegate=live_capture,
            actions=field_actions,
            reader=reader,
            emulator=frames,
            walker=walker,
        )
        capture_plan = SemanticVenueCapturePlan(
            readiness.capture.state_sha256,
            species,
            support.DIGLETTS_CAVE_SOURCE_ID,
            route,
            DIGLETTS_CAVE_TRAINING_VENUE,
        )
        route_interruptions = Gen1RouteInterruptionHandler(
            field_actions,
            reader,
            maximum_flees=64,
            maximum_trainer_battles=8,
            stabilization_frames=120,
            route_name="semantic route to capture venue",
        )
        capture_adapter = RedSemanticVenueCaptureAdapter(
            capture_plan,
            field_actions,
            traversal,
            area,
            interruption_handler=route_interruptions,
            replanner=route_world.replanner(),
        )
        readiness_evidence = SemanticCaptureReadiness(
            reset_state_sha256=readiness.capture.state_sha256,
            ordinary_capture_items=_ordinary_capture_items(observation.raw.bag_items),
            immediate_capture_slots=observation.immediate_capture_slots,
            input_ready=observation.input_ready,
            battle_active=battle_state != 0,
        )
        acquire = capture_adapter.qualify(scenario, before_ledger, readiness_evidence)
        evolve = bind_bounded_evolution_offer(
            scenario,
            species,
            before_ledger,
            reset_state_sha256=readiness.capture.state_sha256,
            offer=RedGoalBindingOffer.available(evolution_binding),
        )
        bound = build_red_dual_capability_scenario(
            scenario,
            species,
            before_ledger,
            (acquire, evolve),
        )
        if (
            actions.actions_executed != 0
            or limited.attempted_actions != 0
            or frames.frames_executed
        ):
            raise RedLivingDexOptionRunError("predecision_zero_effect_authentication")

        _root, scenario_identity = support._semantic_identities(
            readiness,
            scenario,
            species,
        )
        model = readiness.authenticated_fit.fit.model
        prepared = prepare_red_living_dex_option(
            bound,
            model_sha256=readiness.authenticated_fit.model_sha256,
            context_identity_sha256=scenario_identity,
            excluded_reset_state_sha256s=excluded_reset_states,
        )
        execution_identity = _claim_development_root(
            readiness,
            physical_root=physical_root,
            preparation_sha256=prepared.preparation_sha256,
        )
        decision = score_red_living_dex_option(prepared, model)
        start_identity = canonical_sha256(
            {
                "schema": "pokemon.red.private-living-dex-option-start-identity.v1",
                "execution_identity_sha256": execution_identity,
                "decision_sha256": decision.decision_sha256,
            }
        )
        start_record = readiness.store.publish_sealed_record(
            f"red-living-option-start-{start_identity[:24]}",
            kind=START_RECORD_KIND,
            record={
                "schema": "pokemon.red.private-living-dex-option-start.v1",
                "lane_id": LANE_ID,
                "source_bundle_sha256": readiness.gate.public_bindings[
                    "source_bundle_sha256"
                ],
                "execution_identity_sha256": execution_identity,
                "slot_id": readiness.assignment.slot_id,
                "physical_root_sha256": physical_root,
                "preparation": prepared.private_dict(),
                "decision": decision.private_dict(),
                "status": "decision_committed_before_controller_input",
            },
        )
        episode = execute_red_living_dex_option(
            decision,
            observe_after_ledger=lambda: dependency_specimen_ledger(
                context_runtime.adapter.observe().collection_observation
            ),
        )
        terminal_identity = canonical_sha256(
            {
                "schema": "pokemon.red.private-living-dex-option-terminal-identity.v1",
                "execution_identity_sha256": execution_identity,
                "episode_sha256": episode.episode_sha256,
            }
        )
        terminal_record = readiness.store.publish_sealed_record(
            f"red-living-option-terminal-{terminal_identity[:24]}",
            kind=TERMINAL_RECORD_KIND,
            record={
                "schema": "pokemon.red.private-living-dex-option-terminal.v1",
                "lane_id": LANE_ID,
                "source_bundle_sha256": readiness.gate.public_bindings[
                    "source_bundle_sha256"
                ],
                "execution_identity_sha256": execution_identity,
                "start_record_manifest_sha256": start_record.summary.manifest_sha256,
                "episode": episode.private_dict(),
                "controller_actions": actions.actions_executed,
                "attempted_controller_actions": limited.attempted_actions,
                "emulator_frames_advanced": frames.frames_executed,
            },
        )
        public = {
            "schema": RESULT_SCHEMA,
            "status": (
                "model_selected_option_settled_and_independently_verified"
                if episode.status == "settled"
                else "model_selected_option_interrupted_and_censored"
            ),
            "partition": "development",
            "episode": episode.public_dict(),
            "candidate_count": 2,
            "selected_capabilities_executed": 1,
            "controller_actions": actions.actions_executed,
            "attempted_controller_actions": limited.attempted_actions,
            "emulator_frames_advanced": frames.frames_executed,
            "model_predictions": 1,
            "teacher_queries": 0,
            "semantic_root_consumed": True,
            "durability": {
                "decision_committed_before_controller_input": True,
                "start_manifest_sha256": start_record.summary.manifest_sha256,
                "terminal_manifest_sha256": terminal_record.summary.manifest_sha256,
                "private_record_identifiers_published": 0,
            },
            "development_episode_attempts_added": 1,
            "verified_outcome_examples_added": 1 if episode.status == "settled" else 0,
            "authority_promotions_added": 0,
            "transfer_results_added": 0,
            "private_path_fields": 0,
            "private_species_fields": 0,
            "private_route_fields": 0,
            "claim_boundary": (
                "one authentic development plumbing episode; no model-quality, completion, "
                "promotion, or transfer claim"
            ),
        }
    require_pyboy_import_origins(readiness.runtime)
    if verify_rom(readiness.rom_path).sha256 != readiness.rom.sha256:
        raise RedLivingDexOptionRunError("protected_input_integrity")
    return _ExecutionResult(public, episode.status == "settled")


def _claim_development_root(
    readiness: support._Readiness,
    *,
    physical_root: str,
    preparation_sha256: str,
) -> str:
    """Consume one physical reset before prediction or controller authority."""

    source_commit = _commit(
        readiness.gate.public_bindings.get("source_commit"),
        "source commit",
    )
    source_bundle = _sha(
        readiness.gate.public_bindings.get("source_bundle_sha256"),
        "source bundle",
    )
    runner_sha256 = _sha(
        readiness.gate.public_bindings.get("runner_sha256"),
        "runner",
    )
    execution_identity = canonical_sha256(
        {
            "schema": "pokemon.red.living-dex-option-development-execution.v1",
            "lane_id": LANE_ID,
            "source_commit": source_commit,
            "source_bundle_sha256": source_bundle,
            "runner_sha256": runner_sha256,
            "physical_root_sha256": _sha(physical_root, "physical root"),
            "context_identity_sha256": readiness.context_identity_sha256,
            "model_sha256": readiness.authenticated_fit.model_sha256,
            "preparation_sha256": _sha(preparation_sha256, "preparation"),
        }
    )
    expected_claim = {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": physical_root,
        "execution_identity_sha256": execution_identity,
        "source_commit": source_commit,
        "runner_sha256": runner_sha256,
    }
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        support._require_fit_claim(registry)
        if not root_claim_is_available(registry, physical_root):
            raise RedLivingDexOptionRunError("development_root_already_consumed")
        write_root_claim(
            registry,
            root_consumption_sha256=physical_root,
            execution_identity_sha256=execution_identity,
            source_commit=source_commit,
            runner_sha256=runner_sha256,
        )
        if read_root_claim(registry, physical_root) != expected_claim:
            raise RedLivingDexOptionRunError("development_root_claim_authentication")
    return execution_identity


def _ordinary_capture_items(raw_items: object) -> int:
    if not isinstance(raw_items, tuple):
        raise RedLivingDexOptionRunError("capture_capability_authentication")
    inventory: dict[int, int] = {}
    for item in raw_items:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or any(type(value) is not int for value in item)  # noqa: E721
        ):
            raise RedLivingDexOptionRunError("capture_capability_authentication")
        item_id, quantity = item
        if not 0 <= item_id <= 0xFF or not 0 <= quantity <= 0xFF or item_id in inventory:
            raise RedLivingDexOptionRunError("capture_capability_authentication")
        inventory[item_id] = quantity
    return sum(
        inventory.get(int(item), 0)
        for item in (ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL)
    )


def _failure_receipt(stage: str) -> dict[str, object]:
    safe_stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
    return {
        "schema": FAILURE_SCHEMA,
        "status": "failed_closed",
        "failure_stage": safe_stage,
        "retry_policy": "development_only; do_not_substitute_context_after_model_selection",
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
        "private_identity_fields": 0,
    }


def _slot_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]+", value) is None
    ):
        raise RedLivingDexOptionRunError("selected_context_authentication")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexOptionRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise RedLivingDexOptionRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
