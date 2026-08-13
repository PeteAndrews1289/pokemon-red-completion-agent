"""Concrete no-save PyBoy sessions for the sealed strategic evaluator.

Construction authenticates only public/runtime identities and the user-supplied
ROM.  A private capture is resolved exclusively inside :meth:`open_case`, which
the sealed executor calls after publishing that case's durable claim.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.cascade import (
    DEFAULT_CASCADE_TIMING,
    POTION_HEAL_AMOUNT,
    _bag_quantity,
    _use_battle_recovery_item,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort, surf_permission
from pokemon_red_completion.gen1_maps import map_graph
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.gen1_traversal import (
    cut_capabilities,
    strength_capabilities,
    surf_capabilities,
    traversal_rules,
)
from pokemon_red_completion.observation import ItemId, PokemonRedStateReader, RawGameState
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
from pokemon_red_completion.red_trajectory import (
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.rom import verify_rom_bytes
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.route_executor import (
    RouteActionPort,
    RouteExecutionLimits,
    execute_route,
)
from pokemon_red_completion.runtime_identity import RuntimeIdentity
from pokemon_red_completion.strategic_navigation_binding import (
    DestinationRouteBinding,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_SCENARIO_COLLECTION_ID,
    STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_EPISODE_PREFIX,
    StrategicNavigationExecution,
    StrategicNavigationScenarioRehearsalAssignment,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    STRATEGIC_SCENARIO_DESTINATIONS,
    STRATEGIC_SCENARIO_ORIGIN_MAPS,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    STRATEGIC_SCENARIO_MAXIMUM_FLEES,
    StrategicScenarioRouteWorld,
    bind_scenario_interruption_limits,
    record_strategic_scenario_rehearsal,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenario,
    StrategicNavigationScenarioRegistry,
)
from pokemon_red_completion.strategic_navigation_sealed_adapter import (
    StrategicSealedAdapterError,
    StrategicSealedCartridgeSession,
    StrategicSealedCartridgeTeacherEvidence,
    strategic_sealed_scenario_assignment_id,
)
from pokemon_red_completion.strategic_navigation_sealed_catalog import (
    STRATEGIC_SEALED_EXECUTION_CONFIGURATION,
    StrategicSealedCaseCatalog,
    StrategicSealedCaseCatalogEntry,
    open_strategic_sealed_case_input,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    StrategicSealedAuthorization,
    StrategicSealedEvaluationCase,
    StrategicSealedEvaluationPlan,
    StrategicSealedRuntimeGrant,
)
from pokemon_red_completion.trajectory import RecordingExecutor

_MAXIMUM_TRAINER_BATTLES = 8
_SEALED_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=16,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)


class StrategicSealedPyBoySessionFactory:
    """Identity-bound factory that opens no capture before ``open_case``."""

    def __init__(
        self,
        *,
        capture_root: str | Path,
        private_root: PrivateArtifactRoot,
        rom_path: str | Path,
        plan: StrategicSealedEvaluationPlan,
        authorization: StrategicSealedAuthorization,
        runtime_grant: StrategicSealedRuntimeGrant,
        catalog: StrategicSealedCaseCatalog,
        scenario_registry: StrategicNavigationScenarioRegistry,
        execution: StrategicNavigationExecution,
        runtime: RuntimeIdentity,
    ) -> None:
        if not isinstance(private_root, PrivateArtifactRoot):
            raise TypeError("private_root must be a validated private artifact root")
        if not isinstance(plan, StrategicSealedEvaluationPlan):
            raise TypeError("plan must be a sealed evaluation plan")
        if not isinstance(authorization, StrategicSealedAuthorization):
            raise TypeError("authorization must be a sealed authorization")
        if not isinstance(runtime_grant, StrategicSealedRuntimeGrant):
            raise TypeError("runtime_grant must be a sealed runtime grant")
        if not isinstance(catalog, StrategicSealedCaseCatalog):
            raise TypeError("catalog must be a sealed case catalog")
        if not isinstance(scenario_registry, StrategicNavigationScenarioRegistry):
            raise TypeError("scenario_registry must be a scenario registry")
        if not isinstance(execution, StrategicNavigationExecution):
            raise TypeError("execution must be a strategic navigation execution")
        if not isinstance(runtime, RuntimeIdentity):
            raise TypeError("runtime must be a runtime identity")
        if (
            authorization.plan_sha256 != plan.plan_sha256
            or runtime_grant.plan_sha256 != plan.plan_sha256
            or runtime_grant.authorization_sha256
            != authorization.authorization_sha256
            or catalog.catalog_sha256 != authorization.case_catalog_sha256
            or runtime_grant.case_catalog_sha256 != catalog.catalog_sha256
            or scenario_registry.registry_sha256
            != plan.source_scenario_registry_sha256
            or execution.source_commit != runtime_grant.source_commit
            or execution.source_bundle_sha256
            != plan.execution_source_bundle_sha256
            or execution.teacher_execution_sha256
            != plan.teacher_execution_sha256
            or runtime.sha256 != catalog.runtime_sha256
        ):
            raise StrategicSealedAdapterError(
                "sealed PyBoy factory identity differs"
            )
        resolved_rom = Path(rom_path).expanduser().resolve()
        try:
            rom = resolved_rom.read_bytes()
        except OSError:
            raise StrategicSealedAdapterError(
                "sealed PyBoy ROM is unavailable"
            ) from None
        fingerprint = verify_rom_bytes(rom, filename=resolved_rom.name)
        if fingerprint.public_dict() != {
            "sha1": catalog.rom_sha1,
            "sha256": catalog.rom_sha256,
            "size_bytes": catalog.rom_size_bytes,
            "title": catalog.rom_title,
        }:
            raise StrategicSealedAdapterError("sealed PyBoy ROM identity differs")
        self._capture_root = Path(capture_root)
        self._private_root = private_root
        self._rom_path = resolved_rom
        self._plan = plan
        self._authorization = authorization
        self._runtime_grant = runtime_grant
        self._catalog = catalog
        self._scenario_registry = scenario_registry
        self._execution = execution
        self._runtime = runtime
        self._rom = rom
        self._route_world = StrategicScenarioRouteWorld.from_rom(self._rom)
        self._rom_adjacent_before = rom_adjacent_artifacts(resolved_rom)

    @property
    def plan_sha256(self) -> str:
        return self._plan.plan_sha256

    @property
    def authorization_sha256(self) -> str:
        return self._authorization.authorization_sha256

    @property
    def case_catalog_sha256(self) -> str:
        return self._catalog.catalog_sha256

    @property
    def runtime_sha256(self) -> str:
        return self._runtime.sha256

    def open_case(
        self,
        case: StrategicSealedEvaluationCase,
        entry: StrategicSealedCaseCatalogEntry,
        scenario: StrategicNavigationScenario,
    ) -> StrategicSealedCartridgeSession:
        """Open one claimed source, relocate if declared, then plan candidates."""

        if self._plan.case(case.case_id) != case or self._catalog.case(
            case.case_id
        ) is not entry:
            raise StrategicSealedAdapterError(
                "sealed PyBoy catalog entry differs from its case"
            )
        if (
            scenario not in self._scenario_registry.scenarios
            or scenario.scenario_id != entry.source_scenario_id
            or scenario.scenario_sha256 != entry.source_scenario_sha256
        ):
            raise StrategicSealedAdapterError(
                "sealed PyBoy scenario differs from its registry"
            )
        captured = open_strategic_sealed_case_input(
            self._capture_root,
            entry=entry,
            scenario=scenario,
        )
        assignment = _sealed_scenario_assignment(
            scenario=scenario,
            entry=entry,
            registry_sha256=self._scenario_registry.registry_sha256,
            execution=self._execution,
        )
        emulator = PyBoyAdapter(self._rom_path, watch=False)
        try:
            emulator.start()
            emulator.load_state_bytes(captured.state_bytes)
            reader = PokemonRedStateReader(emulator)
            raw = reader.read()
            _require_ready_sealed_region(
                scenario.origin_region,
                raw,
                reader,
                subject="source",
            )
            semantic_observer = CapturedPokemonRedObserver(
                reader,
                COMPLETION_QUEST,
                captured.envelope,
            )
            expected_frontier = frozenset(scenario.completed_objective_ids)
            if COMPLETION_QUEST.completed_ids(
                semantic_observer.observe()
            ) != expected_frontier:
                raise StrategicSealedAdapterError(
                    "sealed source capture differs from its scenario frontier"
                )

            def field_capabilities(observed: RawGameState) -> frozenset[str]:
                capabilities = cut_capabilities(observed).union(
                    strength_capabilities(observed)
                )
                permission = surf_permission(emulator, observed)
                return capabilities.union(
                    surf_capabilities(
                        observed,
                        surf_allowed=permission.allowed,
                    )
                )

            traversal_observer = Gen1TraversalObserver(
                reader,
                hazard_projector=Gen1TrainerSightProjector(self._rom, reader),
                capability_projector=field_capabilities,
            )
            specs = tuple(
                STRATEGIC_SCENARIO_DESTINATIONS[objective_id]
                for objective_id in scenario.candidate_objective_ids
            )
            controller = FrameSafeExecutor(
                emulator,
                DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
            counted = CountingExecutor(controller)
            rules = traversal_rules(self._rom, map_graph(self._rom))
            field_actions = Gen1FieldMovePort(
                counted,
                reader,
                emulator,
                cut_block_swaps={
                    swap.before: swap.after for swap in rules.cut_block_swaps
                },
            )
            if case.origin_region != scenario.origin_region:
                origin_maps = STRATEGIC_SCENARIO_ORIGIN_MAPS.get(case.origin_region)
                if origin_maps is None:
                    raise StrategicSealedAdapterError(
                        "sealed challenge relocation region is unsupported"
                    )
                relocation = self._route_world.plan_to_any_map(
                    traversal_observer.observe(),
                    frozenset(map_id.value for map_id in origin_maps),
                )
                execute_route(
                    relocation,
                    field_actions,
                    traversal_observer,
                    interruption_handler=_sealed_interruption_handler(
                        field_actions,
                        reader,
                        emulator,
                        route_name="sealed strategic challenge relocation",
                    ),
                    replanner=self._route_world.replanner(),
                    limits=bind_scenario_interruption_limits(
                        _SEALED_ROUTE_LIMITS,
                        maximum_flees=STRATEGIC_SCENARIO_MAXIMUM_FLEES,
                        maximum_trainer_battles=_MAXIMUM_TRAINER_BATTLES,
                    ),
                )
                if COMPLETION_QUEST.completed_ids(
                    semantic_observer.observe()
                ) != expected_frontier:
                    raise StrategicSealedAdapterError(
                        "sealed challenge relocation changed the scenario frontier"
                    )
            _require_ready_sealed_region(
                case.origin_region,
                reader.read(),
                reader,
                subject="declared",
            )
            start = traversal_observer.observe()
            bindings = self._route_world.plan_bindings(specs, start)
            metadata = _sealed_episode_metadata(
                assignment=assignment,
                case=case,
                plan=self._plan,
                authorization=self._authorization,
                catalog=self._catalog,
                execution=self._execution,
                runtime=self._runtime,
            )
            return _StrategicSealedPyBoySession(
                emulator=emulator,
                rom_path=self._rom_path,
                rom_adjacent_before=self._rom_adjacent_before,
                private_root=self._private_root,
                assignment=assignment,
                scenario=scenario,
                metadata=metadata,
                reader=reader,
                traversal_observer=traversal_observer,
                field_actions=field_actions,
                route_world=self._route_world,
                bindings=bindings,
                origin_region_ref=f"pokemon.red:region:{case.origin_region}",
            )
        except BaseException:
            emulator.close()
            raise


class _StrategicSealedPyBoySession:
    def __init__(
        self,
        *,
        emulator: PyBoyAdapter,
        rom_path: Path,
        rom_adjacent_before: tuple[object, ...],
        private_root: PrivateArtifactRoot,
        assignment: StrategicNavigationScenarioRehearsalAssignment,
        scenario: StrategicNavigationScenario,
        metadata: Mapping[str, object],
        reader: PokemonRedStateReader,
        traversal_observer: Gen1TraversalObserver,
        field_actions: Gen1FieldMovePort,
        route_world: StrategicScenarioRouteWorld,
        bindings: tuple[DestinationRouteBinding, ...],
        origin_region_ref: str,
    ) -> None:
        self._emulator = emulator
        self._rom_path = rom_path
        self._rom_adjacent_before = rom_adjacent_before
        self._private_root = private_root
        self._assignment = assignment
        self._scenario = scenario
        self._metadata = metadata
        self._reader = reader
        self._traversal_observer = traversal_observer
        self._field_actions = field_actions
        self._route_world = route_world
        self._bindings = bindings
        self._origin_region_ref = origin_region_ref
        self._executed = False
        self._closed = False

    @property
    def assignment_id(self) -> str:
        return self._assignment.assignment_id

    @property
    def bindings(self) -> tuple[DestinationRouteBinding, ...]:
        return self._bindings

    def execute_teacher(self) -> StrategicSealedCartridgeTeacherEvidence:
        if self._closed or self._executed:
            raise StrategicSealedAdapterError(
                "sealed PyBoy teacher session is not executable"
            )
        self._executed = True

        def interruption_factory(
            recorder: RecordingExecutor[MacroAction, object],
        ) -> Gen1RouteInterruptionHandler:
            return _sealed_interruption_handler(
                recorder,
                self._reader,
                self._emulator,
                route_name="sealed strategic scenario approach",
            )

        selected = (
            f"pokemon.red:objective:{self._scenario.teacher_objective_id}:approach"
        )
        result = record_strategic_scenario_rehearsal(
            self._private_root,
            assignment=self._assignment,
            scenario=self._scenario,
            metadata=self._metadata,
            snapshot_provider=PokemonRedObservationEncoder.from_state_reader(
                self._reader
            ),
            action_delegate=self._field_actions,
            traversal_observer=self._traversal_observer,
            bindings=self._bindings,
            selected_destination_ref=selected,
            origin_region_ref=self._origin_region_ref,
            interruption_handler_factory=interruption_factory,
            replanner=self._route_world.replanner(),
            limits=bind_scenario_interruption_limits(
                _SEALED_ROUTE_LIMITS,
                maximum_flees=STRATEGIC_SCENARIO_MAXIMUM_FLEES,
                maximum_trainer_battles=_MAXIMUM_TRAINER_BATTLES,
            ),
        )
        return StrategicSealedCartridgeTeacherEvidence(
            execution_status="succeeded",
            selected_destination_ref=selected,
            episode_manifest_sha256=result.dataset.manifest_sha256,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._emulator.close()
        if rom_adjacent_artifacts(self._rom_path) != self._rom_adjacent_before:
            raise StrategicSealedAdapterError(
                "sealed PyBoy session created a ROM-adjacent artifact"
            )


def _sealed_scenario_assignment(
    *,
    scenario: StrategicNavigationScenario,
    entry: StrategicSealedCaseCatalogEntry,
    registry_sha256: str,
    execution: StrategicNavigationExecution,
) -> StrategicNavigationScenarioRehearsalAssignment:
    if execution.source_commit is None:
        raise StrategicSealedAdapterError(
            "sealed scenario assignment lacks a committed source"
        )
    assignment_id = strategic_sealed_scenario_assignment_id(
        entry=entry,
        scenario=scenario,
        registry_sha256=registry_sha256,
        source_bundle_sha256=execution.source_bundle_sha256,
        teacher_execution_sha256=execution.teacher_execution_sha256,
        source_commit=execution.source_commit,
    )
    return StrategicNavigationScenarioRehearsalAssignment(
        collection_id=STRATEGIC_NAVIGATION_SCENARIO_COLLECTION_ID,
        registry_sha256=registry_sha256,
        scenario_id=scenario.scenario_id,
        scenario_sha256=scenario.scenario_sha256,
        scenario_partition=scenario.partition,
        capture_envelope_sha256=entry.capture_envelope_sha256,
        capture_state_sha256=entry.capture_state_sha256,
        checkpoint_id=entry.checkpoint_id,
        assignment_id=assignment_id,
        root_lineage_id=f"red-scenario-rehearsal-root-{assignment_id}",
        episode_id=(
            f"{STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_EPISODE_PREFIX}"
            f"{assignment_id}"
        ),
        source_bundle_sha256=execution.source_bundle_sha256,
        teacher_execution_sha256=execution.teacher_execution_sha256,
        source_commit=execution.source_commit,
    )


def _sealed_episode_metadata(
    *,
    assignment: StrategicNavigationScenarioRehearsalAssignment,
    case: StrategicSealedEvaluationCase,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    catalog: StrategicSealedCaseCatalog,
    execution: StrategicNavigationExecution,
    runtime: RuntimeIdentity,
) -> dict[str, object]:
    metadata = dict(assignment.episode_metadata())
    configuration = json.loads(
        json.dumps(STRATEGIC_SEALED_EXECUTION_CONFIGURATION)
    )
    metadata.update(
        {
            "adapter_id": POKEMON_RED_ADAPTER_ID,
            "configuration": configuration,
            "configuration_sha256": canonical_sha256(configuration),
            "objective_graph_sha256": execution.objective_graph_sha256,
            "ontology_id": POKEMON_CORE_ONTOLOGY_ID,
            "rom_identity": {
                "sha1": catalog.rom_sha1,
                "sha256": catalog.rom_sha256,
                "size_bytes": catalog.rom_size_bytes,
                "title": catalog.rom_title,
            },
            "runtime": runtime.public_dict(),
            "runtime_sha256": runtime.sha256,
            "sealed_evaluation": {
                "authorization_sha256": authorization.authorization_sha256,
                "case_catalog_sha256": catalog.catalog_sha256,
                "case_id": case.case_id,
                "case_sha256": case.case_sha256,
                "ordinal": case.ordinal,
                "origin_region": case.origin_region,
                "plan_sha256": plan.plan_sha256,
                "schema": "strategic-sealed-scenario-episode-binding-v1",
            },
        }
    )
    return metadata


def _sealed_interruption_handler(
    executor: RouteActionPort,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    *,
    route_name: str,
) -> Gen1RouteInterruptionHandler:
    def recovery_required(raw: RawGameState) -> bool:
        return (
            _bag_quantity(cast(Any, emulator), ItemId.POTION) > 0
            and raw.first_party_hp is not None
            and 0 < raw.first_party_hp <= 40
        )

    def recover() -> None:
        _use_battle_recovery_item(
            reader,
            cast(Any, executor),
            cast(Any, emulator),
            DEFAULT_CASCADE_TIMING,
            item=ItemId.POTION,
            heal_amount=POTION_HEAL_AMOUNT,
            max_quantity=99,
            label="sealed strategic route Potion",
        )

    return Gen1RouteInterruptionHandler(
        executor,
        reader,
        maximum_flees=STRATEGIC_SCENARIO_MAXIMUM_FLEES,
        maximum_trainer_battles=_MAXIMUM_TRAINER_BATTLES,
        stabilization_frames=120,
        route_name=route_name,
        trainer_recovery_required=recovery_required,
        trainer_recovery_action=recover,
        maximum_trainer_recoveries=6,
    )


def _require_ready_sealed_region(
    region: str,
    raw: RawGameState,
    reader: PokemonRedStateReader,
    *,
    subject: str,
) -> None:
    origin_maps = STRATEGIC_SCENARIO_ORIGIN_MAPS.get(region)
    if origin_maps is None:
        raise StrategicSealedAdapterError(
            "sealed case origin region is unsupported"
        )
    if (
        not raw.game_started
        or raw.map_id is None
        or raw.map_id not in {map_id.value for map_id in origin_maps}
        or raw.player_y is None
        or raw.player_x is None
        or raw.battle_state != 0
        or not reader.read_input_readiness().ready
    ):
        raise StrategicSealedAdapterError(
            f"sealed capture is not a ready {subject}-origin boundary"
        )
