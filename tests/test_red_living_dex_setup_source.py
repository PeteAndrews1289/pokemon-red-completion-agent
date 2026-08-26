from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_state import (
    CompletionProgress,
    GoalStateEvidence,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_manager import (
    RedGoalBindingOffer,
    RedGoalObservation,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_setup_materialization import (
    RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID,
    RedLivingDexSetupMaterializationCheckpoint,
    RedLivingDexSetupMaterializationError,
    materialize_red_living_dex_setup_bindings,
)
from pokemon_red_completion.red_living_dex_setup_source import (
    RED_LIVING_DEX_SETUP_PROTECTED_INPUT_SET_SCHEMA,
    RED_LIVING_DEX_SETUP_SOURCE_ADAPTER_CONTRACT_ID,
    RED_LIVING_DEX_SETUP_SOURCE_ENVELOPE_SCHEMA,
    RED_LIVING_DEX_SETUP_SOURCE_MENU_SCHEMA,
    RED_LIVING_DEX_SETUP_SOURCE_OPTION_SCHEMA,
    RED_LIVING_DEX_SETUP_SOURCE_PRODUCER_CONTRACT_ID,
    RED_LIVING_DEX_SETUP_SOURCE_PROVIDER_SCHEMA,
    RED_LIVING_DEX_SETUP_SOURCE_ROUTE_SCHEMA,
    RED_LIVING_DEX_SETUP_SOURCE_SCHEMA,
    RED_LIVING_DEX_SETUP_SOURCE_SLOT_SCHEMA,
    RedLivingDexSetupCatalogSource,
    RedLivingDexSetupProviderWitness,
    RedLivingDexSetupRouteWitness,
    RedLivingDexSetupSlotWitness,
    RedLivingDexSetupSourceError,
    build_red_living_dex_setup_source_payload,
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedRoutedSemanticBoundary,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan

_GOAL_KIND = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}
_CAPABILITY = {
    item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES
}


def _sha(value: object) -> str:
    return hashlib.sha256(repr(value).encode("ascii")).hexdigest()


def _goal_observation(boundary: RedRoutedSemanticBoundary) -> RedGoalObservation:
    progress = CompletionProgress(0, 1)
    evidence = GoalStateEvidence(
        story=progress,
        registered_collection=progress,
        living_collection=progress,
        level_collection=progress,
        team_readiness=0.0,
        evolution=progress,
        safety=1.0,
        resources=1.0,
        storage=1.0,
        control=1.0,
        world_knowledge=progress,
    )
    unused: Any = None
    return RedGoalObservation(
        raw=RawGameState(
            game_started=True,
            map_id=boundary.map_id,
            player_x=boundary.at[0],
            player_y=boundary.at[1],
            party_count=0,
            battle_state=0,
        ),
        game_state=GameState(GameMode.OVERWORLD, location="private-boundary"),
        party=PartyObservation(),
        collection=unused,
        collection_observation=unused,
        evidence=evidence,
        input_ready=True,
        capture_item_count=0,
        recovery_item_count=0,
        free_storage_slots=0,
        immediate_capture_slots=0,
    )


def _fresh(boundary: RedRoutedSemanticBoundary) -> FreshRedGoalObservation:
    provisional = FreshRedGoalObservation(
        "0" * 64,
        _goal_observation(boundary),
        TraversalSnapshot(
            map_id=boundary.map_id,
            at=boundary.at,
            ready=True,
            mode=boundary.mode,
        ),
    )
    return replace(
        provisional,
        observation_sha256=(
            red_living_dex_setup_fresh_observation_sha256(provisional)
        ),
    )


def _route(
    slot_index: int,
    option_index: int,
) -> RedLivingDexSetupRouteWitness:
    map_id = 10 + slot_index
    coordinates = tuple((x, 1) for x in range(1, option_index + 3))
    edges = tuple(
        LocalEdge(target=target, action="right")
        for target in coordinates[1:]
    )
    plan = RoutePlan(
        macro_path=MacroPath((map_id,), ()),
        start_at=coordinates[0],
        start_mode=None,
        segments=(),
        terminal_approach=LocalPath(
            coordinates=coordinates,
            edges=edges,
            modes=(None,) * len(coordinates),
        ),
        terminal_at=coordinates[-1],
        terminal_mode=None,
    )
    return RedLivingDexSetupRouteWitness(
        plan=plan,
        planner_binding_sha256=_sha(("planner", slot_index, option_index)),
    )


class _ExecutorProbe:
    def __init__(self) -> None:
        self.executions = 0
        self.verifications = 0

    def execute(self) -> GoalExecutionReport:
        self.executions += 1
        return GoalExecutionReport(0, 0, {})

    def verify(self, _report: GoalExecutionReport) -> GoalVerification:
        self.verifications += 1
        return GoalVerification.succeeded()


def _typed_witnesses(
    probe: _ExecutorProbe,
) -> tuple[RedLivingDexSetupSlotWitness, ...]:
    plan = build_red_living_dex_prospective_capture_plan()
    witnesses: list[RedLivingDexSetupSlotWitness] = []
    for slot_index, slot in enumerate(plan.slots):
        origin = RedRoutedSemanticBoundary(10 + slot_index, (1, 1), None)
        providers: list[RedLivingDexSetupProviderWitness] = []
        for option_index, kind in enumerate(slot.available_option_kinds):
            route = None if slot_index == 0 else _route(slot_index, option_index)
            destination = origin if route is None else route.terminal_boundary
            binding = ExecutableGoalBinding(
                binding_ref=(
                    f"private:red-setup:{slot_index}:{option_index}:{kind.value}"
                ),
                kind=_GOAL_KIND[kind],
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=probe.execute,
                verify=probe.verify,
            )
            providers.append(
                RedLivingDexSetupProviderWitness(
                    option_kind=kind,
                    provider_type=_CAPABILITY[kind].executor_types[0],
                    fresh=_fresh(destination),
                    offer=RedGoalBindingOffer.available(binding),
                    route=route,
                )
            )
        witnesses.append(
            RedLivingDexSetupSlotWitness(
                slot_sha256=slot.slot_sha256,
                root_consumption_sha256=_sha(("root", slot_index)),
                state_sha256=_sha(("state", slot_index)),
                origin_boundary=origin,
                observer_binding_sha256=_sha(("observer", slot_index)),
                available_family_sha256s=tuple(
                    _sha(("family", slot.family_scope_id, kind.value))
                    for kind in slot.available_option_kinds
                ),
                location_sha256=_sha(("location", slot.location_scope_id)),
                providers=tuple(providers),
            )
        )
    return tuple(witnesses)


def _contract(kind: LivingDexOptionKind) -> str:
    provider = _CAPABILITY[kind].executor_types[0]
    return f"{provider.__module__}.{provider.__qualname__}"


def _canonical(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _provider_join(row: dict[str, object]) -> str:
    return canonical_sha256(
        {key: value for key, value in row.items() if key != "provider_join_sha256"}
    )


def _route_join(row: dict[str, object]) -> str:
    return canonical_sha256(
        {key: value for key, value in row.items() if key != "route_join_sha256"}
    )


def _envelope(slot: dict[str, object]) -> str:
    return canonical_sha256(
        {
            "available_family_sha256s": slot["available_family_sha256s"],
            "location_sha256": slot["location_sha256"],
            "observer_binding_sha256": slot["observer_binding_sha256"],
            "origin_boundary_sha256": slot["origin_boundary_sha256"],
            "root_consumption_sha256": slot["root_consumption_sha256"],
            "schema": RED_LIVING_DEX_SETUP_SOURCE_ENVELOPE_SCHEMA,
            "slot_sha256": slot["slot_sha256"],
            "state_sha256": slot["state_sha256"],
        }
    )


def _menu(slot: dict[str, object]) -> str:
    options = slot["options"]
    assert isinstance(options, list)
    return canonical_sha256(
        {
            "options": [
                {
                    "option_kind": option["option_kind"],
                    "provider_join_sha256": option["provider_join_sha256"],
                    "route_join_sha256": option["route_join_sha256"],
                }
                for option in options
            ],
            "schema": RED_LIVING_DEX_SETUP_SOURCE_MENU_SCHEMA,
            "slot_sha256": slot["slot_sha256"],
            "state_sha256": slot["state_sha256"],
        }
    )


def _protected(document: dict[str, object]) -> str:
    slots = document["slots"]
    assert isinstance(slots, list)
    return canonical_sha256(
        {
            "prospective_plan_sha256": document["prospective_plan_sha256"],
            "schema": RED_LIVING_DEX_SETUP_PROTECTED_INPUT_SET_SCHEMA,
            "slots": [
                {
                    "envelope_sha256": slot["envelope_sha256"],
                    "menu_sha256": slot["menu_sha256"],
                    "root_consumption_sha256": slot["root_consumption_sha256"],
                    "slot_sha256": slot["slot_sha256"],
                    "state_sha256": slot["state_sha256"],
                }
                for slot in slots
            ],
        }
    )


def _document() -> dict[str, object]:
    plan = build_red_living_dex_prospective_capture_plan()
    slots: list[dict[str, object]] = []
    providers: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    for slot_index, slot in enumerate(plan.slots):
        state = _sha(("state", slot_index))
        origin = _sha(("origin", slot_index))
        options: list[dict[str, object]] = []
        local = slot_index == 0
        for option_index, kind in enumerate(slot.available_option_kinds):
            destination = (
                origin
                if local
                else _sha(("destination", slot_index, option_index, kind.value))
            )
            provider: dict[str, object] = {
                "destination_terminal_boundary_sha256": destination,
                "executable_binding_authenticated": True,
                "executable_binding_sha256": _sha(
                    ("binding", slot_index, option_index, kind.value)
                ),
                "fresh_observation_authenticated": True,
                "fresh_observation_sha256": _sha(
                    ("observation", slot_index, option_index, kind.value)
                ),
                "goal_kind": _GOAL_KIND[kind].value,
                "option_kind": kind.value,
                "origin_state_sha256": state,
                "provider_capability_sha256": _CAPABILITY[kind].capability_sha256,
                "provider_contract_id": _contract(kind),
                "provider_join_sha256": "",
                "provider_offer_available": True,
                "provider_offer_sha256": _sha(
                    ("offer", slot_index, option_index, kind.value)
                ),
                "schema": RED_LIVING_DEX_SETUP_SOURCE_PROVIDER_SCHEMA,
                "slot_sha256": slot.slot_sha256,
                "synthetic": False,
            }
            provider["provider_join_sha256"] = _provider_join(provider)
            providers.append(provider)
            route_join: str | None = None
            if not local:
                route: dict[str, object] = {
                    "destination_terminal_boundary_sha256": destination,
                    "option_kind": kind.value,
                    "origin_boundary_sha256": origin,
                    "origin_state_sha256": state,
                    "provider_join_sha256": provider["provider_join_sha256"],
                    "raw_controller_sequence_steps": 0,
                    "route_join_sha256": "",
                    "route_plan_authenticated": True,
                    "route_plan_sha256": _sha(
                        ("route-plan", slot_index, option_index, kind.value)
                    ),
                    "route_planner_binding_sha256": _sha(
                        ("planner", slot_index, option_index, kind.value)
                    ),
                    "route_source": "semantic-router-v1",
                    "route_terminal_predicate_sha256": _sha(
                        ("terminal", slot_index, option_index, kind.value)
                    ),
                    "schema": RED_LIVING_DEX_SETUP_SOURCE_ROUTE_SCHEMA,
                    "slot_sha256": slot.slot_sha256,
                    "teacher_route": False,
                    "terminal_predicate_authenticated": True,
                }
                route["route_join_sha256"] = _route_join(route)
                route_join = str(route["route_join_sha256"])
                routes.append(route)
            options.append(
                {
                    "option_kind": kind.value,
                    "provider_join_sha256": provider["provider_join_sha256"],
                    "route_join_sha256": route_join,
                    "schema": RED_LIVING_DEX_SETUP_SOURCE_OPTION_SCHEMA,
                }
            )
        source_slot: dict[str, object] = {
            "available_family_sha256s": [
                _sha(("family", slot.family_scope_id, kind.value))
                for kind in slot.available_option_kinds
            ],
            "envelope_sha256": "",
            "location_sha256": _sha(("location", slot.location_scope_id)),
            "menu_sha256": "",
            "observer_binding_sha256": _sha(("observer", slot_index)),
            "options": options,
            "origin_boundary_sha256": origin,
            "root_consumption_sha256": _sha(("root", slot_index)),
            "schema": RED_LIVING_DEX_SETUP_SOURCE_SLOT_SCHEMA,
            "slot_sha256": slot.slot_sha256,
            "state_sha256": state,
        }
        source_slot["envelope_sha256"] = _envelope(source_slot)
        source_slot["menu_sha256"] = _menu(source_slot)
        slots.append(source_slot)
    document: dict[str, object] = {
        "authenticated_input_count": 15,
        "producer_contract_id": RED_LIVING_DEX_SETUP_SOURCE_PRODUCER_CONTRACT_ID,
        "prospective_plan_sha256": plan.plan_sha256,
        "protected_input_set_sha256": "",
        "providers": providers,
        "routes": routes,
        "schema": RED_LIVING_DEX_SETUP_SOURCE_SCHEMA,
        "slots": slots,
    }
    document["protected_input_set_sha256"] = _protected(document)
    return document


def _reseal(document: dict[str, object]) -> None:
    providers = document["providers"]
    routes = document["routes"]
    slots = document["slots"]
    assert isinstance(providers, list)
    assert isinstance(routes, list)
    assert isinstance(slots, list)

    provider_changes: dict[str, str] = {}
    for provider in providers:
        old = str(provider["provider_join_sha256"])
        provider["provider_join_sha256"] = _provider_join(provider)
        provider_changes[old] = str(provider["provider_join_sha256"])
    for slot in slots:
        for option in slot["options"]:
            old = str(option["provider_join_sha256"])
            option["provider_join_sha256"] = provider_changes.get(old, old)
    for route in routes:
        old = str(route["provider_join_sha256"])
        route["provider_join_sha256"] = provider_changes.get(old, old)

    route_changes: dict[str, str] = {}
    for route in routes:
        old = str(route["route_join_sha256"])
        route["route_join_sha256"] = _route_join(route)
        route_changes[old] = str(route["route_join_sha256"])
    for slot in slots:
        for option in slot["options"]:
            old = option["route_join_sha256"]
            if old is not None:
                option["route_join_sha256"] = route_changes.get(str(old), str(old))
        slot["envelope_sha256"] = _envelope(slot)
        slot["menu_sha256"] = _menu(slot)
    document["protected_input_set_sha256"] = _protected(document)


class _Meter:
    def __init__(self) -> None:
        self.authority = 0

    def checkpoint(self) -> RedLivingDexSetupMaterializationCheckpoint:
        return RedLivingDexSetupMaterializationCheckpoint(
            controller_authority_attempts=self.authority
        )


class _Reader:
    def __init__(self, payload: bytes, meter: _Meter | None = None) -> None:
        self.payload = payload
        self.meter = meter
        self.calls = 0
        self.effect_at: int | None = None
        self.changed_at: int | None = None

    def __call__(self) -> bytes:
        self.calls += 1
        if self.effect_at == self.calls and self.meter is not None:
            self.meter.authority += 1
        if self.changed_at == self.calls:
            return self.payload + b" "
        return self.payload


def _store(tmp_path: Path) -> PrivateArtifactRoot:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


def _source(
    document: dict[str, object],
    meter: _Meter,
) -> tuple[RedLivingDexSetupCatalogSource, _Reader]:
    payload = _canonical(document)
    reader = _Reader(payload, meter)
    return (
        RedLivingDexSetupCatalogSource(
            reader,
            hashlib.sha256(payload).hexdigest(),
            meter,
        ),
        reader,
    )


def test_typed_source_producer_derives_complete_plan_without_invoking_bindings(
    tmp_path: Path,
) -> None:
    probe = _ExecutorProbe()
    payload = build_red_living_dex_setup_source_payload(
        _typed_witnesses(probe)
    )
    document = json.loads(payload)

    assert document["producer_contract_id"] == (
        RED_LIVING_DEX_SETUP_SOURCE_PRODUCER_CONTRACT_ID
    )
    assert len(document["slots"]) == 15
    assert len(document["providers"]) == 45
    assert len(document["routes"]) == 42
    assert probe.executions == 0
    assert probe.verifications == 0

    store = _store(tmp_path)
    meter = _Meter()
    reader = _Reader(payload, meter)
    source = RedLivingDexSetupCatalogSource(
        reader,
        hashlib.sha256(payload).hexdigest(),
        meter,
    )
    result = materialize_red_living_dex_setup_bindings(
        store,
        source=source,
        effects_meter=meter,
    )

    assert len(result.plan.bindings) == 15
    assert result.plan.local_slot_count == 1
    assert result.plan.routed_slot_count == 14
    assert reader.calls == 17
    assert probe.executions == 0
    assert probe.verifications == 0


def test_typed_source_producer_rejects_missing_reordered_and_aliased_slots() -> None:
    witnesses = _typed_witnesses(_ExecutorProbe())
    reordered = (witnesses[1], witnesses[0], *witnesses[2:])
    aliased_state = (
        witnesses[0],
        replace(witnesses[1], state_sha256=witnesses[0].state_sha256),
        *witnesses[2:],
    )

    with pytest.raises(RedLivingDexSetupSourceError, match="every typed slot"):
        build_red_living_dex_setup_source_payload(witnesses[:-1])
    with pytest.raises(RedLivingDexSetupSourceError, match="frozen slot"):
        build_red_living_dex_setup_source_payload(reordered)
    with pytest.raises(RedLivingDexSetupSourceError, match="binding plan differs"):
        build_red_living_dex_setup_source_payload(aliased_state)


def test_typed_source_witnesses_reject_forged_provider_and_route_provenance() -> None:
    witnesses = _typed_witnesses(_ExecutorProbe())
    provider = witnesses[1].providers[0]
    assert provider.route is not None

    with pytest.raises(RedLivingDexSetupSourceError, match="observation binding"):
        replace(
            provider,
            fresh=replace(provider.fresh, observation_sha256="f" * 64),
        )
    with pytest.raises(RedLivingDexSetupSourceError, match="not allowlisted"):
        replace(provider, provider_type=object)
    with pytest.raises(RedLivingDexSetupSourceError, match="not semantic-router"):
        replace(provider.route, profile_direction_steps=1)


def test_route_witness_digest_binds_costs_and_traversal_requirements() -> None:
    witnesses = _typed_witnesses(_ExecutorProbe())
    route = witnesses[1].providers[0].route
    assert route is not None
    terminal = route.plan.terminal_approach
    assert terminal is not None
    first = terminal.edges[0]
    changed_edge = replace(
        first,
        cost=first.cost + 1,
        requirements=frozenset({"cut"}),
    )
    changed_path = replace(
        terminal,
        edges=(changed_edge, *terminal.edges[1:]),
    )
    changed_route = replace(
        route,
        plan=replace(route.plan, terminal_approach=changed_path),
    )

    assert changed_route.plan.actions == route.plan.actions
    assert changed_route.plan_sha256 != route.plan_sha256


def test_typed_source_producer_rejects_route_detached_from_slot_origin() -> None:
    witnesses = _typed_witnesses(_ExecutorProbe())
    slot = witnesses[1]
    provider = slot.providers[0]
    assert provider.route is not None
    route = provider.route
    old_path = route.plan.terminal_approach
    assert old_path is not None
    detached_coordinates = ((0, 1), *old_path.coordinates[1:])
    detached_edges = tuple(
        LocalEdge(target=target, action="right")
        for target in detached_coordinates[1:]
    )
    detached_plan = replace(
        route.plan,
        start_at=detached_coordinates[0],
        terminal_approach=LocalPath(
            coordinates=detached_coordinates,
            edges=detached_edges,
            modes=(None,) * len(detached_coordinates),
        ),
    )
    detached_route = replace(route, plan=detached_plan)
    detached_provider = replace(provider, route=detached_route)
    changed_slot = replace(
        slot,
        providers=(detached_provider, *slot.providers[1:]),
    )
    changed = (witnesses[0], changed_slot, *witnesses[2:])

    with pytest.raises(RedLivingDexSetupSourceError, match="slot origin"):
        build_red_living_dex_setup_source_payload(changed)


def test_catalog_source_materializes_exact_authentic_shape_and_rereads_every_join(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    source, reader = _source(_document(), meter)

    result = materialize_red_living_dex_setup_bindings(
        store,
        source=source,
        effects_meter=meter,
    )

    assert reader.calls == 17
    assert len(result.plan.bindings) == 15
    assert sum(len(item.option_bindings) for item in result.plan.bindings) == 45
    assert sum(item.routed_option_count for item in result.plan.bindings) == 42
    assert result.plan.local_slot_count == 1
    assert result.plan.routed_slot_count == 14
    assert result.source_attestation.source_adapter_contract_id == (
        RED_LIVING_DEX_SETUP_SOURCE_ADAPTER_CONTRACT_ID
    )
    assert result.source_attestation.authenticated_input_count == 15
    assert result.effects_before == result.effects_after
    sealed = store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID)
    assert sealed is not None
    assert sealed.read() == result.private_dict()


def test_catalog_source_rejects_noncanonical_and_duplicate_key_payloads() -> None:
    meter = _Meter()
    payload = _canonical(_document())
    variants = (
        b" " + payload,
        payload.replace(
            b'{"authenticated_input_count":',
            b'{"x":1,"x":2,"authenticated_input_count":',
            1,
        ),
    )
    for variant in variants:
        source = RedLivingDexSetupCatalogSource(
            lambda variant=variant: variant,
            hashlib.sha256(variant).hexdigest(),
            meter,
        )
        with pytest.raises(RedLivingDexSetupSourceError, match="canonical"):
            source.attest_source()


def test_catalog_source_rejects_changed_payload_between_attestations(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    source, reader = _source(_document(), meter)
    reader.changed_at = 3

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="private slot source failed",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=source,
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


def test_catalog_reader_cannot_hide_controller_authority(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    meter = _Meter()
    source, reader = _source(_document(), meter)
    reader.effect_at = 2

    with pytest.raises(
        RedLivingDexSetupMaterializationError,
        match="changed a protected effect",
    ):
        materialize_red_living_dex_setup_bindings(
            store,
            source=source,
            effects_meter=meter,
        )
    assert store.find_sealed_record(RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID) is None


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("reordered_slots", "slot order or identity"),
        ("missing_provider", "provider denominator"),
        ("cross_joined_route", "route order or reference|cross-joined"),
        ("teacher_route", "not semantic-router derived"),
        ("synthetic_provider", "unavailable, unauthenticated, or synthetic"),
        ("wrong_provider_contract", "capability provenance"),
        ("shared_location", "reused across logical scopes"),
        ("shared_family", "family scopes overlap"),
        ("duplicate_route_plan", "route plans repeat"),
    ),
)
def test_catalog_source_rejects_fully_rehashed_semantic_forgeries(
    mutation: str,
    message: str,
) -> None:
    document = copy.deepcopy(_document())
    slots: Any = document["slots"]
    providers: Any = document["providers"]
    routes: Any = document["routes"]
    if mutation == "reordered_slots":
        slots[0], slots[1] = slots[1], slots[0]
    elif mutation == "missing_provider":
        providers.pop()
    elif mutation == "cross_joined_route":
        slots[1]["options"][0]["route_join_sha256"], slots[1]["options"][1][
            "route_join_sha256"
        ] = (
            slots[1]["options"][1]["route_join_sha256"],
            slots[1]["options"][0]["route_join_sha256"],
        )
    elif mutation == "teacher_route":
        routes[0]["teacher_route"] = True
    elif mutation == "synthetic_provider":
        providers[0]["synthetic"] = True
    elif mutation == "wrong_provider_contract":
        providers[0]["provider_contract_id"] = _contract(
            LivingDexOptionKind.MANAGE_STORAGE
        )
    elif mutation == "shared_location":
        slots[2]["location_sha256"] = slots[0]["location_sha256"]
    elif mutation == "shared_family":
        slots[4]["available_family_sha256s"][0] = slots[0][
            "available_family_sha256s"
        ][0]
    elif mutation == "duplicate_route_plan":
        routes[1]["route_plan_sha256"] = routes[0]["route_plan_sha256"]
    else:
        raise AssertionError(mutation)
    _reseal(document)
    payload = _canonical(document)
    source = RedLivingDexSetupCatalogSource(
        lambda: payload,
        hashlib.sha256(payload).hexdigest(),
        _Meter(),
    )

    with pytest.raises(RedLivingDexSetupSourceError, match=message):
        source.attest_source()


def test_catalog_source_errors_never_repeat_private_reader_details() -> None:
    meter = _Meter()
    private_detail = "/private/setup/source-catalog.json"

    def fail() -> bytes:
        raise RuntimeError(private_detail)

    source = RedLivingDexSetupCatalogSource(fail, "a" * 64, meter)
    with pytest.raises(RedLivingDexSetupSourceError) as failure:
        source.attest_source()

    assert private_detail not in str(failure.value)
    assert failure.value.__cause__ is None
