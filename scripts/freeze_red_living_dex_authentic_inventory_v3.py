#!/usr/bin/env python3
"""Exhaustively census authentic Red option menus without acting.

V3 retires both earlier inventory identities.  It authenticates the frozen
repeatable bank, isolates each context in a fresh emulator instance, accounts
finite context-local restore/observe/enumerate/replay/project failures, and
continues through the bank.  Global authentication, namespace, protected
effect, integrity, encoding, and publication failures remain terminal.  The
runner has no behavior issuer, model, teacher, claim writer, controller
authority, outcome observer invocation, or replay path.
"""

# ruff: noqa: E402 -- pin reviewed script/package origins before project imports.

from __future__ import annotations

import argparse
import json
import runpy
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

_V2_SUPPORT = runpy.run_path(
    str(SCRIPTS_ROOT / "freeze_red_living_dex_authentic_inventory_v2.py"),
    run_name="red_living_dex_authentic_inventory_v3_support",
)

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
)
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import RedGoalContextProfile
from pokemon_red_completion.red_living_dex_exhaustive_inventory_diagnostics import (
    RedLivingDexExhaustiveInventoryCounts,
    RedLivingDexExhaustiveInventoryExclusion,
    RedLivingDexExhaustiveInventoryReason,
    build_red_living_dex_exhaustive_inventory_receipt,
    require_red_living_dex_exhaustive_inventory_accounting,
)
from pokemon_red_completion.red_living_dex_inventory_diagnostics import (
    RedLivingDexInventoryEffects,
)
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedLivingDexOutcomeSnapshot,
    RedLivingDexScenarioBudgets,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexActionFreeInventory,
    RedLivingDexCoverageDiagnostic,
    RedLivingDexCoverageStatus,
    RedLivingDexInventoryObserverBinding,
    build_verified_red_living_dex_goal_scenario,
    diagnose_red_living_dex_action_free_coverage,
)
from pokemon_red_completion.red_living_dex_option_materializer import (
    RedLivingDexMaterializationPlan,
    red_living_dex_verified_capture_scenario_identity,
)
from pokemon_red_completion.rom import verify_rom
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity,
    require_pyboy_import_origins,
)

LANE_ID = "repeatable-red-living-dex-option-value-calibration-v1"
PLAN_SCHEMA = "pokemon.red.private-living-dex-authentic-inventory-plan.v3"
RESULT_SCHEMA = "pokemon.red.living-dex-authentic-inventory-result.v3"
PLAN_RECORD_ID = "red-living-dex-authentic-inventory-plan-v3"
PLAN_RECORD_KIND = "red-living-dex-authentic-inventory-plan-v3"
MAXIMUM_CONTROLLER_ACTIONS = 5_000
MAXIMUM_EMULATOR_FRAMES = 4_000_000
MATERIALIZER_UNCLAIMED_STATUS = "absent"
_MATERIALIZER_CLAIMED_STATUSES = frozenset(
    {"complete", "failed", "interrupted", "partial"}
)
_MAPPED_GOAL_KINDS = frozenset(
    {
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.DEVELOP_TEAM,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.RESUPPLY,
        GoalKind.MANAGE_STORAGE,
        GoalKind.EXPLORE,
    }
)


class _ArgumentError(RuntimeError):
    pass


class _InventoryStop(RuntimeError):
    def __init__(
        self,
        reason: RedLivingDexExhaustiveInventoryReason,
        *,
        coverage: RedLivingDexCoverageDiagnostic | None = None,
    ) -> None:
        self.reason = reason
        self.coverage = coverage
        super().__init__(reason.value)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise _ArgumentError


@dataclass(slots=True)
class _DiagnosticState:
    authenticated_input_contexts: int = 0
    contexts_considered: int = 0
    materializer_namespaces_authenticated: int = 0
    state_restore_attempts: int = 0
    emulator_states_restored: int = 0
    observation_attempts: int = 0
    observations_completed: int = 0
    binding_enumeration_attempts: int = 0
    binding_enumerations_completed: int = 0
    historical_replay_attempts: int = 0
    historical_replays_authenticated: int = 0
    scenario_projection_attempts: int = 0
    complete_menus_projected: int = 0
    zero_effect_checks: int = 0
    coverage_evaluations: int = 0
    ready_coverage_plans: int = 0
    private_plan_encoding_attempts: int = 0
    private_plan_documents_encoded: int = 0
    protected_integrity_attempts: int = 0
    protected_integrity_checks_passed: int = 0
    private_plan_publication_attempts: int = 0
    private_plan_records_confirmed: int = 0
    exclusions: Counter[RedLivingDexExhaustiveInventoryExclusion] = field(
        default_factory=Counter
    )
    behavior_draws: int = 0
    controller_authority_attempts: int = 0
    controller_actions: int = 0
    emulator_frames_advanced: int = 0
    model_fits: int = 0
    model_predictions: int = 0
    outcomes_observed: int = 0
    private_identity_fields_published: int = 0
    private_path_fields: int = 0
    root_claims: int = 0
    teacher_queries: int = 0

    def counts(self) -> RedLivingDexExhaustiveInventoryCounts:
        return RedLivingDexExhaustiveInventoryCounts(
            authenticated_input_contexts=self.authenticated_input_contexts,
            contexts_considered=self.contexts_considered,
            materializer_namespaces_authenticated=(
                self.materializer_namespaces_authenticated
            ),
            state_restore_attempts=self.state_restore_attempts,
            emulator_states_restored=self.emulator_states_restored,
            observation_attempts=self.observation_attempts,
            observations_completed=self.observations_completed,
            binding_enumeration_attempts=self.binding_enumeration_attempts,
            binding_enumerations_completed=self.binding_enumerations_completed,
            historical_replay_attempts=self.historical_replay_attempts,
            historical_replays_authenticated=self.historical_replays_authenticated,
            scenario_projection_attempts=self.scenario_projection_attempts,
            complete_menus_projected=self.complete_menus_projected,
            zero_effect_checks=self.zero_effect_checks,
            coverage_evaluations=self.coverage_evaluations,
            ready_coverage_plans=self.ready_coverage_plans,
            private_plan_encoding_attempts=self.private_plan_encoding_attempts,
            private_plan_documents_encoded=self.private_plan_documents_encoded,
            protected_integrity_attempts=self.protected_integrity_attempts,
            protected_integrity_checks_passed=(
                self.protected_integrity_checks_passed
            ),
            private_plan_publication_attempts=(
                self.private_plan_publication_attempts
            ),
            private_plan_records_confirmed=self.private_plan_records_confirmed,
        )

    def effects(self) -> RedLivingDexInventoryEffects:
        return RedLivingDexInventoryEffects(
            behavior_draws=self.behavior_draws,
            controller_authority_attempts=self.controller_authority_attempts,
            controller_actions=self.controller_actions,
            emulator_frames_advanced=self.emulator_frames_advanced,
            model_fits=self.model_fits,
            model_predictions=self.model_predictions,
            outcomes_observed=self.outcomes_observed,
            private_identity_fields_published=self.private_identity_fields_published,
            private_path_fields=self.private_path_fields,
            root_claims=self.root_claims,
            teacher_queries=self.teacher_queries,
        )


class _ForbiddenActionPort:
    def __init__(self, state: _DiagnosticState) -> None:
        self._state = state

    def execute(self, _action: object) -> object:
        self._state.controller_authority_attempts += 1
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION
        )


@dataclass(frozen=True, slots=True)
class _ProjectedInventory:
    inventory: RedLivingDexActionFreeInventory
    plan: RedLivingDexMaterializationPlan
    private_rows: dict[str, dict[str, object]]
    coverage: RedLivingDexCoverageDiagnostic
    state: _DiagnosticState


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
    return parser


def main(argv: list[str] | None = None) -> int:
    state = _DiagnosticState()
    reason = RedLivingDexExhaustiveInventoryReason.ARGUMENT_AUTHENTICATION
    coverage: RedLivingDexCoverageDiagnostic | None = None
    try:
        args = _parser().parse_args(argv)
        reason = RedLivingDexExhaustiveInventoryReason.SOURCE_AUTHENTICATION
        source_commit, source_bundle = _authenticate_source(args)
        reason = RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
        (
            rom_path,
            rom_sha256,
            _rom_bytes,
            contexts,
            catalog_sha256,
            context_plan_sha256,
        ) = _authenticate_inputs(args, source_commit, source_bundle)
        state.authenticated_input_contexts = len(contexts)
        projected = _inventory(
            args,
            rom_path=rom_path,
            contexts=contexts,
            source_bundle=source_bundle,
            state=state,
        )
        coverage = projected.coverage
        reason = RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_ENCODING
        state.private_plan_encoding_attempts += 1
        document, private_plan_sha256 = _private_plan_document(
            source_commit=source_commit,
            source_bundle=source_bundle,
            rom_sha256=rom_sha256,
            registry_sha256=_sha(args.expected_registry_sha256),
            catalog_sha256=catalog_sha256,
            context_plan_sha256=context_plan_sha256,
            projected=projected,
        )
        state.private_plan_documents_encoded += 1
        reason = RedLivingDexExhaustiveInventoryReason.PROTECTED_INPUT_INTEGRITY
        state.protected_integrity_attempts += 1
        _require_protected_input_integrity(
            rom_path=rom_path,
            rom_sha256=rom_sha256,
            source_bundle=source_bundle,
        )
        state.protected_integrity_checks_passed += 1
        reason = RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_PUBLICATION
        state.private_plan_publication_attempts += 1
        result = _publish(
            args,
            document=document,
            private_plan_sha256=private_plan_sha256,
            projected=projected,
        )
        state.private_plan_records_confirmed += 1
        result["diagnostic"] = _diagnostic_receipt(
            state,
            RedLivingDexExhaustiveInventoryReason.COMPLETE,
            coverage=coverage,
        )
        print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except _ArgumentError:
        reason = RedLivingDexExhaustiveInventoryReason.ARGUMENT_AUTHENTICATION
    except _InventoryStop as error:
        reason = error.reason
        coverage = error.coverage
    except BaseException:
        reason = RedLivingDexExhaustiveInventoryReason.UNEXPECTED_FAILURE
    print(
        json.dumps(
            _diagnostic_receipt(state, reason, coverage=coverage),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _authenticate_source(args: argparse.Namespace) -> tuple[str, str]:
    function = cast(Any, _V2_SUPPORT["_authenticate_source"])
    try:
        return cast(tuple[str, str], function(args))
    except BaseException:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.SOURCE_AUTHENTICATION
        ) from None


def _authenticate_inputs(
    args: argparse.Namespace,
    source_commit: str,
    source_bundle: str,
) -> tuple[Path, str, bytes, tuple[Any, ...], str, str]:
    function = cast(Any, _V2_SUPPORT["_authenticate_inputs"])
    try:
        return cast(
            tuple[Path, str, bytes, tuple[Any, ...], str, str],
            function(args, source_commit, source_bundle),
        )
    except BaseException:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
        ) from None


def _inventory(
    args: argparse.Namespace,
    *,
    rom_path: Path,
    contexts: tuple[Any, ...],
    source_bundle: str,
    state: _DiagnosticState,
) -> _ProjectedInventory:
    try:
        runtime_identity = build_runtime_identity()
        require_pyboy_import_origins(runtime_identity)
    except BaseException:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.RUNTIME_AUTHENTICATION
        ) from None
    try:
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    except BaseException:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.MATERIALIZER_NAMESPACE_AUTHENTICATION
        ) from None
    scenarios = []
    private_rows: dict[str, dict[str, object]] = {}
    budgets = RedLivingDexScenarioBudgets(
        MAXIMUM_CONTROLLER_ACTIONS,
        MAXIMUM_EMULATOR_FRAMES,
    )

    for private in contexts:
        state.contexts_considered += 1
        try:
            assignment = private.assignment
            catalog_entry = private.catalog_entry
            capture = private.capture
            profile = private.profile
            root_available = private.root_available
            physical_root_sha256 = private.root_consumption_sha256
        except BaseException:
            raise _InventoryStop(
                RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
            ) from None
        if not isinstance(capture, GoalManagerContextCapture) or not isinstance(
            profile, RedGoalContextProfile
        ):
            raise _InventoryStop(
                RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
            )
        if assignment.partition not in {"train", "validation"}:
            state.exclusions[
                RedLivingDexExhaustiveInventoryExclusion.SEALED_OR_UNSUPPORTED_PARTITION
            ] += 1
            continue
        if not root_available:
            state.exclusions[
                RedLivingDexExhaustiveInventoryExclusion.CONSUMED_PHYSICAL_ROOT
            ] += 1
            continue
        try:
            scenario_identity = red_living_dex_verified_capture_scenario_identity(
                capture
            )
            episode_id = f"redldx-{scenario_identity}"
            unclaimed = _materializer_episode_is_unclaimed(store, episode_id)
        except _InventoryStop:
            raise
        except BaseException:
            raise _InventoryStop(
                RedLivingDexExhaustiveInventoryReason.MATERIALIZER_NAMESPACE_AUTHENTICATION
            ) from None
        state.materializer_namespaces_authenticated += 1
        if not unclaimed:
            state.exclusions[
                RedLivingDexExhaustiveInventoryExclusion.EXISTING_MATERIALIZER_CLAIM
            ] += 1
            continue

        projected = _project_context(
            assignment=assignment,
            budgets=budgets,
            capture=capture,
            catalog_entry=catalog_entry,
            physical_root_sha256=physical_root_sha256,
            profile=profile,
            rom_path=rom_path,
            runtime_identity=runtime_identity,
            source_bundle=source_bundle,
            state=state,
        )
        if projected is None:
            continue
        scenario, private_row = projected
        scenarios.append(scenario)
        private_rows[scenario.scenario_identity_sha256] = private_row

    try:
        require_red_living_dex_exhaustive_inventory_accounting(
            state.counts(),
            {
                item: state.exclusions[item]
                for item in RedLivingDexExhaustiveInventoryExclusion
            },
        )
    except BaseException:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.EXHAUSTIVE_ACCOUNTING
        ) from None
    state.coverage_evaluations += 1
    try:
        coverage, plan = diagnose_red_living_dex_action_free_coverage(scenarios)
    except BaseException:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.EXHAUSTIVE_ACCOUNTING
        ) from None
    if coverage.status is not RedLivingDexCoverageStatus.READY or plan is None:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.EXACT_COVERAGE,
            coverage=coverage,
        )
    state.ready_coverage_plans += 1
    return _ProjectedInventory(
        inventory=RedLivingDexActionFreeInventory(tuple(scenarios)),
        plan=plan,
        private_rows=private_rows,
        coverage=coverage,
        state=state,
    )


def _project_context(
    *,
    assignment: Any,
    budgets: RedLivingDexScenarioBudgets,
    capture: GoalManagerContextCapture,
    catalog_entry: Any,
    physical_root_sha256: str,
    profile: RedGoalContextProfile,
    rom_path: Path,
    runtime_identity: RuntimeIdentity,
    source_bundle: str,
    state: _DiagnosticState,
) -> tuple[Any, dict[str, object]] | None:
    checks_before = state.zero_effect_checks
    emulator: Any | None = None
    actions: CountingExecutor | None = None
    frame_before: int | None = None
    try:
        emulator_context = PyBoyAdapter(
            rom_path,
            watch=False,
            speed=None,
            expected_rom=POKEMON_RED_US_REV_0,
        )
    except Exception:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.RUNTIME_AUTHENTICATION
        ) from None
    try:
        with emulator_context as emulator:
            require_pyboy_import_origins(runtime_identity)
            frame_before = emulator.frame_count
            state.state_restore_attempts += 1
            try:
                emulator.load_state_bytes(capture.state_bytes)
            except _InventoryStop:
                _record_context_effects(state, emulator, None, frame_before)
                _raise_if_effect(state)
                raise
            except Exception:
                _exclude_context(
                    state,
                    emulator,
                    None,
                    frame_before,
                    RedLivingDexExhaustiveInventoryExclusion.STATE_RESTORE_FAILURE,
                )
                return None
            state.emulator_states_restored += 1
            if emulator.pressed_buttons:
                _record_context_effects(state, emulator, None, frame_before)
                _raise_if_effect(state)

            state.observation_attempts += 1
            try:
                reader = cast(Any, _V2_SUPPORT["_V1_SUPPORT"])[
                    "PokemonRedStateReader"
                ](emulator)
                runtime = build_red_goal_context_runtime(
                    profile=profile,
                    capture=capture,
                    emulator=emulator,
                    reader=reader,
                )
                observation = runtime.adapter.observe()
            except _InventoryStop:
                _record_context_effects(state, emulator, None, frame_before)
                _raise_if_effect(state)
                raise
            except Exception:
                _exclude_context(
                    state,
                    emulator,
                    None,
                    frame_before,
                    RedLivingDexExhaustiveInventoryExclusion.STATE_OBSERVATION_FAILURE,
                )
                return None
            state.observations_completed += 1

            actions = CountingExecutor(_ForbiddenActionPort(state))
            state.binding_enumeration_attempts += 1
            try:
                bindings = runtime.enumerator(actions).enumerate(observation)
            except _InventoryStop:
                _record_context_effects(state, emulator, actions, frame_before)
                _raise_if_effect(state)
                raise
            except Exception:
                _exclude_context(
                    state,
                    emulator,
                    actions,
                    frame_before,
                    RedLivingDexExhaustiveInventoryExclusion.BINDING_ENUMERATION_FAILURE,
                )
                return None
            state.binding_enumerations_completed += 1

            state.historical_replay_attempts += 1
            try:
                _authenticate_historical_menu(
                    assignment,
                    catalog_entry,
                    observation,
                    bindings,
                )
            except _InventoryStop:
                _record_context_effects(state, emulator, actions, frame_before)
                _raise_if_effect(state)
                raise
            except Exception:
                _exclude_context(
                    state,
                    emulator,
                    actions,
                    frame_before,
                    RedLivingDexExhaustiveInventoryExclusion.HISTORICAL_REPLAY_FAILURE,
                )
                return None
            state.historical_replays_authenticated += 1
            mapped_available = tuple(
                binding
                for binding in bindings.bindings
                if binding.kind in _MAPPED_GOAL_KINDS
            )
            if len(mapped_available) < 3:
                _exclude_context(
                    state,
                    emulator,
                    actions,
                    frame_before,
                    RedLivingDexExhaustiveInventoryExclusion.FEWER_THAN_THREE_MAPPED_OPTIONS,
                )
                return None
            if not observation.party.members:
                _exclude_context(
                    state,
                    emulator,
                    actions,
                    frame_before,
                    RedLivingDexExhaustiveInventoryExclusion.EMPTY_PARTY_OBSERVATION,
                )
                return None

            partition = (
                "train" if assignment.partition == "train" else "development"
            )
            state.scenario_projection_attempts += 1
            try:
                before_binding = canonical_sha256(
                    {
                        "capture_id": capture.capture_id,
                        "envelope_sha256": capture.envelope_sha256,
                        "profile_sha256": profile.profile_sha256,
                        "purpose": "living-dex-before-observer-v3",
                        "schema": "pokemon.red.private-living-dex-before-observer.v3",
                        "source_bundle_sha256": source_bundle,
                        "state_sha256": capture.state_sha256,
                    }
                )
                before = _before_snapshot(
                    capture,
                    observation,
                    bindings,
                    observer_binding_sha256=before_binding,
                )
                facts = _context_facts(observation, bindings, profile)
                location_ref = _location_ref(observation)
                observer_binding = canonical_sha256(
                    {
                        "capture_id": capture.capture_id,
                        "envelope_sha256": capture.envelope_sha256,
                        "profile_sha256": profile.profile_sha256,
                        "purpose": "living-dex-fresh-after-observer-v3",
                        "schema": "pokemon.red.private-living-dex-after-observer.v3",
                        "source_bundle_sha256": source_bundle,
                        "state_sha256": capture.state_sha256,
                    }
                )
                attestation = _checkpoint_attestation(
                    assignment=assignment,
                    catalog_entry=catalog_entry,
                    capture=capture,
                    profile=profile,
                    physical_root_sha256=physical_root_sha256,
                    partition=partition,
                )
                scenario = build_verified_red_living_dex_goal_scenario(
                    capture,
                    profile,
                    before,
                    facts,
                    budgets,
                    bindings,
                    partition=partition,
                    location_ref=location_ref,
                    checkpoint_attestation_sha256=canonical_sha256(attestation),
                    observer_binding_sha256=observer_binding,
                    observe_after=RedLivingDexInventoryObserverBinding(
                        observer_binding
                    ),
                )
            except _InventoryStop:
                _record_context_effects(state, emulator, actions, frame_before)
                _raise_if_effect(state)
                raise
            except Exception:
                _exclude_context(
                    state,
                    emulator,
                    actions,
                    frame_before,
                    RedLivingDexExhaustiveInventoryExclusion.SCENARIO_PROJECTION_FAILURE,
                )
                return None
            state.complete_menus_projected += 1
            _record_context_effects(state, emulator, actions, frame_before)
            _raise_if_effect(state)
            return scenario, {
                "assignment_id": assignment.assignment_id,
                "attestation": attestation,
                "capture_id": capture.capture_id,
                "context_id": catalog_entry.context_id,
                "materialization_identity": scenario.private_identity_dict(),
                "partition": partition,
                "physical_root_sha256": physical_root_sha256,
                "profile_sha256": profile.profile_sha256,
                "slot_id": assignment.slot_id,
            }
    except _InventoryStop:
        raise
    except Exception:
        _record_unhandled_context_effects(
            state,
            emulator,
            actions,
            frame_before,
            checks_before,
        )
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.RUNTIME_AUTHENTICATION
        ) from None
    except BaseException:
        _record_unhandled_context_effects(
            state,
            emulator,
            actions,
            frame_before,
            checks_before,
        )
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.UNEXPECTED_FAILURE
        ) from None


def _exclude_context(
    state: _DiagnosticState,
    emulator: Any,
    actions: CountingExecutor | None,
    frame_before: int,
    exclusion: RedLivingDexExhaustiveInventoryExclusion,
) -> None:
    _record_context_effects(state, emulator, actions, frame_before)
    _raise_if_effect(state)
    state.exclusions[exclusion] += 1
    return None


def _record_unhandled_context_effects(
    state: _DiagnosticState,
    emulator: Any | None,
    actions: CountingExecutor | None,
    frame_before: int | None,
    checks_before: int,
) -> None:
    if (
        emulator is not None
        and frame_before is not None
        and state.zero_effect_checks == checks_before
    ):
        _record_context_effects(state, emulator, actions, frame_before)
        _raise_if_effect(state)


def _record_context_effects(
    state: _DiagnosticState,
    emulator: Any,
    actions: CountingExecutor | None,
    frame_before: int,
) -> None:
    frame_delta = emulator.frame_count - frame_before
    if frame_delta < 0:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.EXHAUSTIVE_ACCOUNTING
        )
    state.emulator_frames_advanced += frame_delta
    state.controller_actions += 0 if actions is None else actions.actions_executed
    state.controller_actions += len(emulator.pressed_buttons)
    state.zero_effect_checks += 1


def _raise_if_effect(state: _DiagnosticState) -> None:
    if state.effects().total:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION
        )


def _authenticate_historical_menu(
    assignment: Any,
    catalog_entry: Any,
    observation: Any,
    bindings: GoalBindingSet,
) -> None:
    function = cast(Any, _V2_SUPPORT["_authenticate_historical_menu"])
    function(assignment, catalog_entry, observation, bindings)


def _materializer_episode_is_unclaimed(
    store: PrivateArtifactRoot,
    episode_id: str,
) -> bool:
    status = store.inspect_episode_state(episode_id).status
    if status == MATERIALIZER_UNCLAIMED_STATUS:
        return True
    if status in _MATERIALIZER_CLAIMED_STATUSES:
        return False
    raise _InventoryStop(
        RedLivingDexExhaustiveInventoryReason.MATERIALIZER_NAMESPACE_AUTHENTICATION
    )


def _before_snapshot(
    capture: GoalManagerContextCapture,
    observation: Any,
    bindings: GoalBindingSet,
    *,
    observer_binding_sha256: str,
) -> RedLivingDexOutcomeSnapshot:
    function = cast(Any, _V2_SUPPORT["_before_snapshot"])
    return cast(
        RedLivingDexOutcomeSnapshot,
        function(
            capture,
            observation,
            bindings,
            observer_binding_sha256=observer_binding_sha256,
        ),
    )


def _context_facts(
    observation: Any,
    bindings: GoalBindingSet,
    profile: RedGoalContextProfile,
) -> Any:
    return cast(Any, _V2_SUPPORT["_context_facts"])(
        observation,
        bindings,
        profile,
    )


def _location_ref(observation: Any) -> str:
    return cast(str, cast(Any, _V2_SUPPORT["_location_ref"])(observation))


def _checkpoint_attestation(**kwargs: object) -> dict[str, object]:
    value = cast(dict[str, object], cast(Any, _V2_SUPPORT["_checkpoint_attestation"])(
        **kwargs
    ))
    value["schema"] = "pokemon.red.private-living-dex-capture-attestation.v3"
    return value


def _require_protected_input_integrity(
    *,
    rom_path: Path,
    rom_sha256: str,
    source_bundle: str,
) -> None:
    if verify_rom(rom_path).sha256 != rom_sha256 or rom_sha256 != (
        POKEMON_RED_US_REV_0.sha256
    ):
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.PROTECTED_INPUT_INTEGRITY
        )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.PROTECTED_INPUT_INTEGRITY
        )


def _private_plan_document(
    *,
    source_commit: str,
    source_bundle: str,
    rom_sha256: str,
    registry_sha256: str,
    catalog_sha256: str,
    context_plan_sha256: str,
    projected: _ProjectedInventory,
) -> tuple[dict[str, object], str]:
    selected_rows = []
    for scenario in projected.plan.scenarios:
        try:
            selected_rows.append(
                projected.private_rows[scenario.scenario_identity_sha256]
            )
        except KeyError:
            raise _InventoryStop(
                RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_ENCODING
            ) from None
    payload: dict[str, object] = {
        "context_catalog_sha256": catalog_sha256,
        "context_plan_sha256": context_plan_sha256,
        "coverage_diagnostic": projected.coverage.public_dict(),
        "inventory": projected.inventory.public_dict(),
        "lane_id": LANE_ID,
        "materialization_plan": projected.plan.public_dict(),
        "registry_sha256": registry_sha256,
        "rom_sha256": rom_sha256,
        "scenarios": selected_rows,
        "schema": PLAN_SCHEMA,
        "source_bundle_sha256": source_bundle,
        "source_commit": source_commit,
        "status": "frozen_before_claim_randomization_action_outcome_or_fit",
    }
    validate_private_record(payload)
    private_plan_sha256 = canonical_sha256(payload)
    document = {**payload, "private_plan_sha256": private_plan_sha256}
    validate_private_record(document)
    return document, private_plan_sha256


def _publish(
    args: argparse.Namespace,
    *,
    document: dict[str, object],
    private_plan_sha256: str,
    projected: _ProjectedInventory,
) -> dict[str, object]:
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    record = store.publish_sealed_record(
        PLAN_RECORD_ID,
        kind=PLAN_RECORD_KIND,
        record=document,
    )
    return {
        "claim_boundary": (
            "action-free exhaustive curriculum plan only; no outcome, fit, "
            "authority, policy-quality, completion, or transfer claim"
        ),
        "materialization_plan": projected.plan.public_dict(),
        "plan_manifest_sha256": record.summary.manifest_sha256,
        "private_identity_fields_published": 0,
        "private_path_fields": 0,
        "private_plan_sha256": private_plan_sha256,
        "schema": RESULT_SCHEMA,
        "status": "authenticated_action_free_exhaustive_8_plus_4_plan_frozen",
    }


def _diagnostic_receipt(
    state: _DiagnosticState,
    reason: RedLivingDexExhaustiveInventoryReason,
    *,
    coverage: RedLivingDexCoverageDiagnostic | None,
) -> dict[str, object]:
    return build_red_living_dex_exhaustive_inventory_receipt(
        reason=reason,
        counts=state.counts(),
        exclusions={
            item: state.exclusions[item]
            for item in RedLivingDexExhaustiveInventoryExclusion
        },
        effects=state.effects(),
        coverage=coverage,
    )


def _sha(value: object) -> str:
    function = cast(Any, _V2_SUPPORT["_sha"])
    try:
        return cast(str, function(value))
    except BaseException:
        raise _InventoryStop(
            RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
        ) from None


if __name__ == "__main__":
    raise SystemExit(main())
