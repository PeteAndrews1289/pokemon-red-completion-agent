"""Concrete action-free source for the prospective Red setup campaign.

The whole-plan materializer deliberately accepts a small protocol.  This
module is Red's concrete implementation of that protocol: read one exact,
canonical private catalog, authenticate every frozen slot, join each option to
an allowlisted Red provider attestation, join routed options to an authenticated
semantic-router attestation, and derive the setup binding returned to the
materializer.

The catalog contains only private evidence digests.  It contains no filesystem
path, controller sequence, teacher route, behavior choice, outcome, or model
target.  The reader is invoked and the exact payload digest is checked on every
source interaction so a changed input set cannot pass the materializer's final
reattestation.  The materializer's independent meter remains the authority for
proving that all reads and joins were action-free.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pokemon_red_completion.global_router import MacroEdge, MacroTransition
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_setup_campaign import (
    RedLivingDexSetupCampaignError,
    RedLivingDexSetupOptionBinding,
    RedLivingDexSetupSlotBinding,
    RedLivingDexSetupTransportKind,
    build_red_living_dex_setup_binding_plan,
)
from pokemon_red_completion.red_living_dex_setup_materialization import (
    RedLivingDexSetupMaterializationMeter,
    RedLivingDexSetupPrivateSourceAttestation,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedRoutedSemanticBoundary,
)
from pokemon_red_completion.route_plan import RoutePlan

RED_LIVING_DEX_SETUP_SOURCE_SCHEMA = (
    "pokemon.red.private-living-dex-setup-source-catalog.v1"
)
RED_LIVING_DEX_SETUP_SOURCE_SLOT_SCHEMA = (
    "pokemon.red.private-living-dex-setup-source-slot.v1"
)
RED_LIVING_DEX_SETUP_SOURCE_OPTION_SCHEMA = (
    "pokemon.red.private-living-dex-setup-source-option.v1"
)
RED_LIVING_DEX_SETUP_SOURCE_PROVIDER_SCHEMA = (
    "pokemon.red.private-living-dex-setup-provider-attestation.v1"
)
RED_LIVING_DEX_SETUP_SOURCE_ROUTE_SCHEMA = (
    "pokemon.red.private-living-dex-setup-route-attestation.v1"
)
RED_LIVING_DEX_SETUP_SOURCE_ENVELOPE_SCHEMA = (
    "pokemon.red.private-living-dex-setup-source-envelope.v1"
)
RED_LIVING_DEX_SETUP_SOURCE_MENU_SCHEMA = (
    "pokemon.red.private-living-dex-setup-source-menu.v1"
)
RED_LIVING_DEX_SETUP_PROTECTED_INPUT_SET_SCHEMA = (
    "pokemon.red.private-living-dex-setup-protected-input-set.v1"
)
RED_LIVING_DEX_SETUP_SOURCE_ADAPTER_CONTRACT_ID = (
    "pokemon_red_completion.red_living_dex_setup_source."
    "RedLivingDexSetupCatalogSource"
)
RED_LIVING_DEX_SETUP_SOURCE_PRODUCER_CONTRACT_ID = (
    "pokemon_red_completion.red_living_dex_setup_source."
    "build_red_living_dex_setup_source_payload"
)
RED_LIVING_DEX_SETUP_PROVIDER_OFFER_WITNESS_SCHEMA = (
    "pokemon.red.private-living-dex-setup-provider-offer-witness.v1"
)
RED_LIVING_DEX_SETUP_EXECUTABLE_WITNESS_SCHEMA = (
    "pokemon.red.private-living-dex-setup-executable-witness.v1"
)
RED_LIVING_DEX_SETUP_FRESH_OBSERVATION_WITNESS_SCHEMA = (
    "pokemon.red.private-living-dex-setup-fresh-observation-witness.v1"
)
RED_LIVING_DEX_SETUP_ROUTE_PLAN_WITNESS_SCHEMA = (
    "pokemon.red.private-living-dex-setup-route-plan-witness.v1"
)

MAXIMUM_SOURCE_PAYLOAD_BYTES = 2_000_000

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTRACT_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{2,255}\Z")

_GOAL_KIND_BY_OPTION = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}


def _contract_id(value: type[object]) -> str:
    return f"{value.__module__}.{value.__qualname__}"


_CAPABILITY_BY_KIND = {
    item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES
}
_PROVIDER_CONTRACTS_BY_KIND = {
    kind: tuple(_contract_id(value) for value in capability.executor_types)
    for kind, capability in _CAPABILITY_BY_KIND.items()
}


class RedLivingDexSetupSourceError(RuntimeError):
    """An authenticated private Red source catalog is invalid."""


SourcePayloadReader = Callable[[], bytes]


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRouteWitness:
    """One computed semantic-router plan retained only as private evidence."""

    plan: RoutePlan
    planner_binding_sha256: str
    route_source: str = "semantic-router-v1"
    profile_direction_steps: int = 0
    curriculum_direction_steps: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RoutePlan):
            raise TypeError("Red setup route witness needs a RoutePlan")
        self.plan.__post_init__()
        if not self.plan.steps:
            raise RedLivingDexSetupSourceError(
                "Red setup route witness must cross a real boundary"
            )
        _require_sha256(
            self.planner_binding_sha256,
            "Red setup route witness planner binding",
        )
        if (
            self.route_source != "semantic-router-v1"
            or type(self.profile_direction_steps) is not int  # noqa: E721
            or type(self.curriculum_direction_steps) is not int  # noqa: E721
            or self.profile_direction_steps != 0
            or self.curriculum_direction_steps != 0
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup route witness is not semantic-router derived"
            )
        if self.origin_boundary.sha256 == self.terminal_boundary.sha256:
            raise RedLivingDexSetupSourceError(
                "Red setup route witness does not leave its origin"
            )

    @property
    def origin_boundary(self) -> RedRoutedSemanticBoundary:
        return RedRoutedSemanticBoundary(
            self.plan.macro_path.maps[0],
            self.plan.start_at,
            self.plan.start_mode,
        )

    @property
    def terminal_boundary(self) -> RedRoutedSemanticBoundary:
        return RedRoutedSemanticBoundary.from_plan(self.plan)

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(_route_plan_witness_document(self.plan))


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupProviderWitness:
    """One fresh destination observation and available real-provider offer."""

    option_kind: LivingDexOptionKind
    provider_type: type[object]
    fresh: FreshRedGoalObservation
    offer: RedGoalBindingOffer
    route: RedLivingDexSetupRouteWitness | None

    def __post_init__(self) -> None:
        if not isinstance(self.option_kind, LivingDexOptionKind):
            raise RedLivingDexSetupSourceError(
                "Red setup provider witness option kind differs"
            )
        capability = _CAPABILITY_BY_KIND.get(self.option_kind)
        if (
            capability is None
            or self.provider_type not in capability.executor_types
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup provider witness contract is not allowlisted"
            )
        if not isinstance(self.fresh, FreshRedGoalObservation):
            raise TypeError("Red setup provider witness needs a fresh observation")
        self.fresh.__post_init__()
        expected_fresh = red_living_dex_setup_fresh_observation_sha256(
            self.fresh
        )
        if self.fresh.observation_sha256 != expected_fresh:
            raise RedLivingDexSetupSourceError(
                "Red setup provider witness observation binding differs"
            )
        if (
            not isinstance(self.offer, RedGoalBindingOffer)
            or self.offer.kind is not _GOAL_KIND_BY_OPTION[self.option_kind]
            or self.offer.binding is None
            or self.offer.unavailable_reason is not None
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup provider witness is not an available executable offer"
            )
        self.offer.binding.__post_init__()
        if self.offer.binding.kind is not self.offer.kind:
            raise RedLivingDexSetupSourceError(
                "Red setup provider witness executable kind differs"
            )
        if self.route is not None:
            if not isinstance(self.route, RedLivingDexSetupRouteWitness):
                raise TypeError("Red setup provider witness route differs")
            self.route.__post_init__()
            terminal = self.route.terminal_boundary
            if (
                not terminal.matches_traversal(self.fresh.traversal)
                or not terminal.matches_goal_observation(self.fresh.observation)
            ):
                raise RedLivingDexSetupSourceError(
                    "Red setup provider witness differs from its route terminal"
                )

    @property
    def executable_binding_sha256(self) -> str:
        assert self.offer.binding is not None
        return red_living_dex_setup_executable_binding_sha256(
            self.offer.binding
        )

    @property
    def provider_offer_sha256(self) -> str:
        return canonical_sha256(
            {
                "executable_binding_sha256": self.executable_binding_sha256,
                "fresh_observation_sha256": self.fresh.observation_sha256,
                "goal_kind": self.offer.kind.value,
                "provider_contract_id": _contract_id(self.provider_type),
                "schema": RED_LIVING_DEX_SETUP_PROVIDER_OFFER_WITNESS_SCHEMA,
            }
        )


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupSlotWitness:
    """Authenticated private facts needed to bind one frozen setup slot."""

    slot_sha256: str
    root_consumption_sha256: str
    state_sha256: str
    origin_boundary: RedRoutedSemanticBoundary
    observer_binding_sha256: str
    available_family_sha256s: tuple[str, ...]
    location_sha256: str
    providers: tuple[RedLivingDexSetupProviderWitness, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.slot_sha256, "Red setup witness slot"),
            (self.root_consumption_sha256, "Red setup witness root"),
            (self.state_sha256, "Red setup witness state"),
            (self.observer_binding_sha256, "Red setup witness observer"),
            (self.location_sha256, "Red setup witness location"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.origin_boundary, RedRoutedSemanticBoundary):
            raise TypeError("Red setup slot witness origin differs")
        self.origin_boundary.__post_init__()
        if (
            not isinstance(self.available_family_sha256s, tuple)
            or any(
                _SHA256.fullmatch(value) is None
                for value in self.available_family_sha256s
            )
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup slot witness families differ"
            )
        if (
            not isinstance(self.providers, tuple)
            or any(
                not isinstance(item, RedLivingDexSetupProviderWitness)
                for item in self.providers
            )
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup slot witness providers differ"
            )
        for provider in self.providers:
            provider.__post_init__()


def red_living_dex_setup_fresh_observation_sha256(
    fresh: FreshRedGoalObservation,
) -> str:
    """Bind coherent private Red/traversal truth without exposing it publicly."""

    if not isinstance(fresh, FreshRedGoalObservation):
        raise TypeError("Red setup observation witness differs")
    fresh.__post_init__()
    return canonical_sha256(
        {
            "goal_observation": fresh.observation.public_dict(),
            "schema": RED_LIVING_DEX_SETUP_FRESH_OBSERVATION_WITNESS_SCHEMA,
            "traversal": {
                "at": list(fresh.traversal.at),
                "interruption": fresh.traversal.interruption,
                "map_id": fresh.traversal.map_id,
                "mode": fresh.traversal.mode,
                "ready": fresh.traversal.ready,
            },
        }
    )


def red_living_dex_setup_executable_binding_sha256(
    binding: ExecutableGoalBinding,
) -> str:
    """Bind the private executable metadata without invoking either callable."""

    if not isinstance(binding, ExecutableGoalBinding):
        raise TypeError("Red setup executable witness differs")
    binding.__post_init__()
    return canonical_sha256(
        {
            "binding_ref": binding.binding_ref,
            "estimated_effort": binding.estimated_effort,
            "estimated_risk": binding.estimated_risk,
            "execute_contract_id": _callable_contract_id(
                binding.execute,
                "Red setup executable",
            ),
            "goal_kind": binding.kind.value,
            "schema": RED_LIVING_DEX_SETUP_EXECUTABLE_WITNESS_SCHEMA,
            "verify_contract_id": _callable_contract_id(
                binding.verify,
                "Red setup verifier",
            ),
        }
    )


def build_red_living_dex_setup_source_payload(
    witnesses: Sequence[RedLivingDexSetupSlotWitness],
) -> bytes:
    """Encode one exact 15/45 private catalog from typed runtime witnesses."""

    if not isinstance(witnesses, Sequence):
        raise TypeError("Red setup source witnesses must be a sequence")
    prospective = build_red_living_dex_prospective_capture_plan()
    frozen = tuple(witnesses)
    if (
        len(frozen) != len(prospective.slots)
        or any(
            not isinstance(item, RedLivingDexSetupSlotWitness)
            for item in frozen
        )
    ):
        raise RedLivingDexSetupSourceError(
            "Red setup source needs every typed slot witness"
        )

    slots: list[dict[str, object]] = []
    providers: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    for witness, slot in zip(frozen, prospective.slots, strict=True):
        witness.__post_init__()
        if (
            witness.slot_sha256 != slot.slot_sha256
            or len(witness.providers) != len(slot.available_option_kinds)
            or len(witness.available_family_sha256s)
            != len(slot.available_option_kinds)
            or tuple(item.option_kind for item in witness.providers)
            != slot.available_option_kinds
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup source witness differs from its frozen slot"
            )
        local = _slot_is_locally_composable(slot)
        options: list[dict[str, object]] = []
        for provider in witness.providers:
            if local != (provider.route is None):
                raise RedLivingDexSetupSourceError(
                    "Red setup source witness local/routed shape differs"
                )
            if provider.route is None:
                destination = witness.origin_boundary
                if (
                    not destination.matches_traversal(provider.fresh.traversal)
                    or not destination.matches_goal_observation(
                        provider.fresh.observation
                    )
                ):
                    raise RedLivingDexSetupSourceError(
                        "Red setup local witness leaves its origin"
                    )
            else:
                if provider.route.origin_boundary != witness.origin_boundary:
                    raise RedLivingDexSetupSourceError(
                        "Red setup route witness starts outside its slot origin"
                    )
                destination = provider.route.terminal_boundary

            capability = _CAPABILITY_BY_KIND[provider.option_kind]
            provider_row: dict[str, object] = {
                "destination_terminal_boundary_sha256": destination.sha256,
                "executable_binding_authenticated": True,
                "executable_binding_sha256": (
                    provider.executable_binding_sha256
                ),
                "fresh_observation_authenticated": True,
                "fresh_observation_sha256": provider.fresh.observation_sha256,
                "goal_kind": _GOAL_KIND_BY_OPTION[provider.option_kind].value,
                "option_kind": provider.option_kind.value,
                "origin_state_sha256": witness.state_sha256,
                "provider_capability_sha256": capability.capability_sha256,
                "provider_contract_id": _contract_id(provider.provider_type),
                "provider_join_sha256": "",
                "provider_offer_available": True,
                "provider_offer_sha256": provider.provider_offer_sha256,
                "schema": RED_LIVING_DEX_SETUP_SOURCE_PROVIDER_SCHEMA,
                "slot_sha256": slot.slot_sha256,
                "synthetic": False,
            }
            provider_row["provider_join_sha256"] = _provider_join_sha256(
                provider_row
            )
            providers.append(provider_row)

            route_join_sha256: str | None = None
            if provider.route is not None:
                route_row: dict[str, object] = {
                    "destination_terminal_boundary_sha256": destination.sha256,
                    "option_kind": provider.option_kind.value,
                    "origin_boundary_sha256": witness.origin_boundary.sha256,
                    "origin_state_sha256": witness.state_sha256,
                    "provider_join_sha256": provider_row[
                        "provider_join_sha256"
                    ],
                    "raw_controller_sequence_steps": 0,
                    "route_join_sha256": "",
                    "route_plan_authenticated": True,
                    "route_plan_sha256": provider.route.plan_sha256,
                    "route_planner_binding_sha256": (
                        provider.route.planner_binding_sha256
                    ),
                    "route_source": provider.route.route_source,
                    "route_terminal_predicate_sha256": destination.sha256,
                    "schema": RED_LIVING_DEX_SETUP_SOURCE_ROUTE_SCHEMA,
                    "slot_sha256": slot.slot_sha256,
                    "teacher_route": False,
                    "terminal_predicate_authenticated": True,
                }
                route_row["route_join_sha256"] = _route_join_sha256(route_row)
                route_join_sha256 = _string(
                    route_row["route_join_sha256"],
                    "Red setup route join",
                )
                routes.append(route_row)
            options.append(
                {
                    "option_kind": provider.option_kind.value,
                    "provider_join_sha256": provider_row[
                        "provider_join_sha256"
                    ],
                    "route_join_sha256": route_join_sha256,
                    "schema": RED_LIVING_DEX_SETUP_SOURCE_OPTION_SCHEMA,
                }
            )

        slot_row: dict[str, object] = {
            "available_family_sha256s": list(
                witness.available_family_sha256s
            ),
            "envelope_sha256": "",
            "location_sha256": witness.location_sha256,
            "menu_sha256": "",
            "observer_binding_sha256": witness.observer_binding_sha256,
            "options": options,
            "origin_boundary_sha256": witness.origin_boundary.sha256,
            "root_consumption_sha256": witness.root_consumption_sha256,
            "schema": RED_LIVING_DEX_SETUP_SOURCE_SLOT_SCHEMA,
            "slot_sha256": slot.slot_sha256,
            "state_sha256": witness.state_sha256,
        }
        slot_row["envelope_sha256"] = _envelope_sha256(slot_row)
        slot_row["menu_sha256"] = _menu_sha256(slot_row)
        slots.append(slot_row)

    document: dict[str, object] = {
        "authenticated_input_count": len(slots),
        "producer_contract_id": RED_LIVING_DEX_SETUP_SOURCE_PRODUCER_CONTRACT_ID,
        "prospective_plan_sha256": prospective.plan_sha256,
        "protected_input_set_sha256": _protected_input_set_sha256(
            prospective.plan_sha256,
            slots,
        ),
        "providers": providers,
        "routes": routes,
        "schema": RED_LIVING_DEX_SETUP_SOURCE_SCHEMA,
        "slots": slots,
    }
    payload = (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    catalog = _decode_catalog(payload, hashlib.sha256(payload).hexdigest())
    try:
        build_red_living_dex_setup_binding_plan(
            tuple(
                _materialize_slot(
                    slot,
                    source_slot,
                    providers=catalog.providers,
                    routes=catalog.routes,
                )
                for slot, source_slot in zip(
                    prospective.slots,
                    catalog.slots,
                    strict=True,
                )
            ),
            prospective_plan=prospective,
        )
    except RedLivingDexSetupCampaignError:
        raise RedLivingDexSetupSourceError(
            "Red setup source witness binding plan differs"
        ) from None
    return payload


@dataclass(frozen=True, slots=True)
class _Catalog:
    payload_sha256: str
    protected_input_set_sha256: str
    authenticated_input_count: int
    slots: tuple[Mapping[str, object], ...]
    providers: Mapping[str, Mapping[str, object]]
    routes: Mapping[str, Mapping[str, object]]


@dataclass(slots=True)
class RedLivingDexSetupCatalogSource:
    """Reread and join one exact private Red setup catalog without acting."""

    read_payload: SourcePayloadReader
    expected_payload_sha256: str
    effects_meter: RedLivingDexSetupMaterializationMeter

    def __post_init__(self) -> None:
        if not callable(self.read_payload):
            raise TypeError("Red setup source needs a private payload reader")
        _require_sha256(self.expected_payload_sha256, "Red setup source payload")
        if not isinstance(
            self.effects_meter,
            RedLivingDexSetupMaterializationMeter,
        ):
            raise TypeError("Red setup source needs the protected-effect meter")

    def attest_source(self) -> RedLivingDexSetupPrivateSourceAttestation:
        catalog = self._read_catalog()
        return RedLivingDexSetupPrivateSourceAttestation(
            source_manifest_sha256=catalog.payload_sha256,
            source_adapter_contract_id=(
                RED_LIVING_DEX_SETUP_SOURCE_ADAPTER_CONTRACT_ID
            ),
            authenticated_input_count=catalog.authenticated_input_count,
            protected_input_set_sha256=catalog.protected_input_set_sha256,
        )

    def materialize_slot(
        self,
        slot: LivingDexProspectiveCaptureSlot,
    ) -> RedLivingDexSetupSlotBinding:
        if not isinstance(slot, LivingDexProspectiveCaptureSlot):
            raise TypeError("Red setup source needs a prospective slot")
        catalog = self._read_catalog()
        source_slot = next(
            (
                item
                for item in catalog.slots
                if item["slot_sha256"] == slot.slot_sha256
            ),
            None,
        )
        if source_slot is None:
            raise RedLivingDexSetupSourceError(
                "Red setup source does not contain the requested slot"
            )
        return _materialize_slot(
            slot,
            source_slot,
            providers=catalog.providers,
            routes=catalog.routes,
        )

    def _read_catalog(self) -> _Catalog:
        try:
            payload = self.read_payload()
        except Exception:
            raise RedLivingDexSetupSourceError(
                "Red setup source payload read failed"
            ) from None
        if not isinstance(payload, bytes):
            raise RedLivingDexSetupSourceError(
                "Red setup source payload is not immutable bytes"
            )
        if not payload or len(payload) > MAXIMUM_SOURCE_PAYLOAD_BYTES:
            raise RedLivingDexSetupSourceError(
                "Red setup source payload size differs"
            )
        observed = hashlib.sha256(payload).hexdigest()
        if observed != self.expected_payload_sha256:
            raise RedLivingDexSetupSourceError(
                "Red setup source payload authentication failed"
            )
        return _decode_catalog(payload, observed)


def _decode_catalog(payload: bytes, payload_sha256: str) -> _Catalog:
    document = _decode_canonical_object(payload)
    _exact_keys(
        document,
        {
            "authenticated_input_count",
            "producer_contract_id",
            "prospective_plan_sha256",
            "protected_input_set_sha256",
            "providers",
            "routes",
            "schema",
            "slots",
        },
        "Red setup source catalog",
    )
    if document["schema"] != RED_LIVING_DEX_SETUP_SOURCE_SCHEMA:
        raise RedLivingDexSetupSourceError("Red setup source schema differs")
    if (
        document["producer_contract_id"]
        != RED_LIVING_DEX_SETUP_SOURCE_PRODUCER_CONTRACT_ID
    ):
        raise RedLivingDexSetupSourceError(
            "Red setup source producer contract differs"
        )

    prospective = build_red_living_dex_prospective_capture_plan()
    if document["prospective_plan_sha256"] != prospective.plan_sha256:
        raise RedLivingDexSetupSourceError(
            "Red setup source prospective plan differs"
        )
    authenticated_input_count = _integer(
        document["authenticated_input_count"],
        "Red setup authenticated input count",
    )
    if authenticated_input_count != len(prospective.slots):
        raise RedLivingDexSetupSourceError(
            "Red setup authenticated input count differs"
        )
    protected_input_set_sha256 = _require_sha256(
        document["protected_input_set_sha256"],
        "Red setup protected input set",
    )

    raw_slots = _sequence(document["slots"], "Red setup source slots")
    raw_providers = _sequence(
        document["providers"],
        "Red setup source providers",
    )
    raw_routes = _sequence(document["routes"], "Red setup source routes")
    if len(raw_slots) != len(prospective.slots):
        raise RedLivingDexSetupSourceError(
            "Red setup source must contain every frozen slot"
        )

    slots = tuple(
        _validate_slot(item, expected)
        for item, expected in zip(raw_slots, prospective.slots, strict=True)
    )
    providers = _validate_providers(raw_providers, slots, prospective.slots)
    routes = _validate_routes(
        raw_routes,
        slots,
        prospective.slots,
        providers,
    )
    _validate_catalog_joins(slots, prospective.slots, providers, routes)
    _validate_scope_bindings(slots, prospective.slots)
    expected_protected = _protected_input_set_sha256(
        prospective.plan_sha256,
        slots,
    )
    if protected_input_set_sha256 != expected_protected:
        raise RedLivingDexSetupSourceError(
            "Red setup protected input set binding differs"
        )
    return _Catalog(
        payload_sha256=payload_sha256,
        protected_input_set_sha256=protected_input_set_sha256,
        authenticated_input_count=authenticated_input_count,
        slots=slots,
        providers=providers,
        routes=routes,
    )


def _validate_slot(
    value: object,
    expected: LivingDexProspectiveCaptureSlot,
) -> Mapping[str, object]:
    slot = _mapping(value, "Red setup source slot")
    _exact_keys(
        slot,
        {
            "available_family_sha256s",
            "envelope_sha256",
            "location_sha256",
            "menu_sha256",
            "observer_binding_sha256",
            "options",
            "origin_boundary_sha256",
            "root_consumption_sha256",
            "schema",
            "slot_sha256",
            "state_sha256",
        },
        "Red setup source slot",
    )
    if slot["schema"] != RED_LIVING_DEX_SETUP_SOURCE_SLOT_SCHEMA:
        raise RedLivingDexSetupSourceError("Red setup source slot schema differs")
    if slot["slot_sha256"] != expected.slot_sha256:
        raise RedLivingDexSetupSourceError(
            "Red setup source slot order or identity differs"
        )
    for name, subject in (
        ("root_consumption_sha256", "Red setup source root"),
        ("state_sha256", "Red setup source state"),
        ("origin_boundary_sha256", "Red setup source origin boundary"),
        ("envelope_sha256", "Red setup source envelope"),
        ("menu_sha256", "Red setup source menu"),
        ("observer_binding_sha256", "Red setup source observer"),
        ("location_sha256", "Red setup source location"),
    ):
        _require_sha256(slot[name], subject)

    families = _sequence(
        slot["available_family_sha256s"],
        "Red setup source families",
    )
    if len(families) != len(expected.available_option_kinds):
        raise RedLivingDexSetupSourceError(
            "Red setup source family count differs"
        )
    for value in families:
        _require_sha256(value, "Red setup source family")

    options = _sequence(slot["options"], "Red setup source options")
    if len(options) != len(expected.available_option_kinds):
        raise RedLivingDexSetupSourceError(
            "Red setup source option count differs"
        )
    local = _slot_is_locally_composable(expected)
    for option, expected_kind in zip(
        options,
        expected.available_option_kinds,
        strict=True,
    ):
        row = _mapping(option, "Red setup source option")
        _exact_keys(
            row,
            {
                "option_kind",
                "provider_join_sha256",
                "route_join_sha256",
                "schema",
            },
            "Red setup source option",
        )
        if row["schema"] != RED_LIVING_DEX_SETUP_SOURCE_OPTION_SCHEMA:
            raise RedLivingDexSetupSourceError(
                "Red setup source option schema differs"
            )
        if _option_kind(row["option_kind"]) is not expected_kind:
            raise RedLivingDexSetupSourceError(
                "Red setup source option order or kind differs"
            )
        _require_sha256(
            row["provider_join_sha256"],
            "Red setup source provider join",
        )
        route_join = row["route_join_sha256"]
        if local:
            if route_join is not None:
                raise RedLivingDexSetupSourceError(
                    "Red setup local option invents a route"
                )
        else:
            _require_sha256(route_join, "Red setup source route join")

    if slot["envelope_sha256"] != _envelope_sha256(slot):
        raise RedLivingDexSetupSourceError(
            "Red setup source envelope binding differs"
        )
    if slot["menu_sha256"] != _menu_sha256(slot):
        raise RedLivingDexSetupSourceError(
            "Red setup source menu binding differs"
        )
    return slot


def _validate_providers(
    values: Sequence[object],
    slots: Sequence[Mapping[str, object]],
    prospective_slots: Sequence[LivingDexProspectiveCaptureSlot],
) -> Mapping[str, Mapping[str, object]]:
    expected_refs = tuple(
        _string(
            option["provider_join_sha256"],
            "Red setup source provider reference",
        )
        for slot in slots
        for option in _mapping_sequence(
            slot["options"],
            "Red setup source options",
        )
    )
    if len(values) != len(expected_refs):
        raise RedLivingDexSetupSourceError(
            "Red setup source provider denominator differs"
        )

    providers: dict[str, Mapping[str, object]] = {}
    ordered_refs: list[str] = []
    expected_rows = tuple(
        (source_slot, prospective_slot, kind)
        for source_slot, prospective_slot in zip(
            slots,
            prospective_slots,
            strict=True,
        )
        for kind in prospective_slot.available_option_kinds
    )
    for value, (source_slot, prospective_slot, expected_kind) in zip(
        values,
        expected_rows,
        strict=True,
    ):
        row = _mapping(value, "Red setup source provider")
        _exact_keys(
            row,
            {
                "destination_terminal_boundary_sha256",
                "executable_binding_authenticated",
                "executable_binding_sha256",
                "fresh_observation_authenticated",
                "fresh_observation_sha256",
                "goal_kind",
                "option_kind",
                "origin_state_sha256",
                "provider_capability_sha256",
                "provider_contract_id",
                "provider_join_sha256",
                "provider_offer_available",
                "provider_offer_sha256",
                "schema",
                "slot_sha256",
                "synthetic",
            },
            "Red setup source provider",
        )
        if row["schema"] != RED_LIVING_DEX_SETUP_SOURCE_PROVIDER_SCHEMA:
            raise RedLivingDexSetupSourceError(
                "Red setup source provider schema differs"
            )
        join = _require_sha256(
            row["provider_join_sha256"],
            "Red setup provider join",
        )
        if join != _provider_join_sha256(row):
            raise RedLivingDexSetupSourceError(
                "Red setup provider join authentication differs"
            )
        if join in providers:
            raise RedLivingDexSetupSourceError("Red setup provider join repeats")
        if (
            row["slot_sha256"] != prospective_slot.slot_sha256
            or _option_kind(row["option_kind"]) is not expected_kind
            or _goal_kind(row["goal_kind"]) is not _GOAL_KIND_BY_OPTION[expected_kind]
            or row["origin_state_sha256"] != source_slot["state_sha256"]
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup provider is cross-joined"
            )
        capability = _CAPABILITY_BY_KIND[expected_kind]
        contract = _string(
            row["provider_contract_id"],
            "Red setup provider contract",
        )
        if (
            _CONTRACT_ID.fullmatch(contract) is None
            or contract not in _PROVIDER_CONTRACTS_BY_KIND[expected_kind]
            or row["provider_capability_sha256"]
            != capability.capability_sha256
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup provider capability provenance differs"
            )
        for name, subject in (
            (
                "destination_terminal_boundary_sha256",
                "Red setup provider destination",
            ),
            ("fresh_observation_sha256", "Red setup provider observation"),
            ("provider_offer_sha256", "Red setup provider offer"),
            (
                "executable_binding_sha256",
                "Red setup provider executable binding",
            ),
        ):
            _require_sha256(row[name], subject)
        if len(
            {
                row["fresh_observation_sha256"],
                row["provider_offer_sha256"],
                row["executable_binding_sha256"],
            }
        ) != 3:
            raise RedLivingDexSetupSourceError(
                "Red setup provider evidence aliases"
            )
        if not (
            _boolean(
                row["fresh_observation_authenticated"],
                "Red setup fresh observation authentication",
            )
            and _boolean(
                row["provider_offer_available"],
                "Red setup provider availability",
            )
            and _boolean(
                row["executable_binding_authenticated"],
                "Red setup executable binding authentication",
            )
            and not _boolean(row["synthetic"], "Red setup provider synthetic flag")
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup provider is unavailable, unauthenticated, or synthetic"
            )
        ordered_refs.append(join)
        providers[join] = row

    if tuple(ordered_refs) != expected_refs:
        raise RedLivingDexSetupSourceError(
            "Red setup provider order or reference differs"
        )
    return providers


def _validate_routes(
    values: Sequence[object],
    slots: Sequence[Mapping[str, object]],
    prospective_slots: Sequence[LivingDexProspectiveCaptureSlot],
    providers: Mapping[str, Mapping[str, object]],
) -> Mapping[str, Mapping[str, object]]:
    expected_refs = tuple(
        _string(option["route_join_sha256"], "Red setup source route reference")
        for source_slot, prospective_slot in zip(
            slots,
            prospective_slots,
            strict=True,
        )
        if not _slot_is_locally_composable(prospective_slot)
        for option in _mapping_sequence(
            source_slot["options"],
            "Red setup source options",
        )
    )
    if len(values) != len(expected_refs):
        raise RedLivingDexSetupSourceError(
            "Red setup source route denominator differs"
        )
    routes: dict[str, Mapping[str, object]] = {}
    ordered_refs: list[str] = []
    expected_rows = tuple(
        (source_slot, prospective_slot, kind, option)
        for source_slot, prospective_slot in zip(
            slots,
            prospective_slots,
            strict=True,
        )
        if not _slot_is_locally_composable(prospective_slot)
        for kind, option in zip(
            prospective_slot.available_option_kinds,
            _mapping_sequence(source_slot["options"], "Red setup source options"),
            strict=True,
        )
    )
    for value, (source_slot, prospective_slot, expected_kind, option) in zip(
        values,
        expected_rows,
        strict=True,
    ):
        row = _mapping(value, "Red setup source route")
        _exact_keys(
            row,
            {
                "destination_terminal_boundary_sha256",
                "option_kind",
                "origin_boundary_sha256",
                "origin_state_sha256",
                "provider_join_sha256",
                "raw_controller_sequence_steps",
                "route_join_sha256",
                "route_plan_authenticated",
                "route_plan_sha256",
                "route_planner_binding_sha256",
                "route_source",
                "route_terminal_predicate_sha256",
                "schema",
                "slot_sha256",
                "teacher_route",
                "terminal_predicate_authenticated",
            },
            "Red setup source route",
        )
        if row["schema"] != RED_LIVING_DEX_SETUP_SOURCE_ROUTE_SCHEMA:
            raise RedLivingDexSetupSourceError(
                "Red setup source route schema differs"
            )
        join = _require_sha256(
            row["route_join_sha256"],
            "Red setup route join",
        )
        if join != _route_join_sha256(row):
            raise RedLivingDexSetupSourceError(
                "Red setup route join authentication differs"
            )
        if join in routes:
            raise RedLivingDexSetupSourceError("Red setup route join repeats")
        provider_ref = _require_sha256(
            row["provider_join_sha256"],
            "Red setup route provider join",
        )
        provider = providers.get(provider_ref)
        if provider is None:
            raise RedLivingDexSetupSourceError(
                "Red setup route provider join is absent"
            )
        if (
            join != option["route_join_sha256"]
            or provider_ref != option["provider_join_sha256"]
            or row["slot_sha256"] != prospective_slot.slot_sha256
            or _option_kind(row["option_kind"]) is not expected_kind
            or row["origin_state_sha256"] != source_slot["state_sha256"]
            or row["origin_boundary_sha256"]
            != source_slot["origin_boundary_sha256"]
            or row["destination_terminal_boundary_sha256"]
            != provider["destination_terminal_boundary_sha256"]
        ):
            raise RedLivingDexSetupSourceError("Red setup route is cross-joined")
        for name, subject in (
            ("route_plan_sha256", "Red setup route plan"),
            (
                "route_terminal_predicate_sha256",
                "Red setup route terminal predicate",
            ),
            (
                "route_planner_binding_sha256",
                "Red setup route planner binding",
            ),
        ):
            _require_sha256(row[name], subject)
        if (
            row["destination_terminal_boundary_sha256"]
            == row["origin_boundary_sha256"]
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup routed option does not leave its origin"
            )
        if not (
            row["route_source"] == "semantic-router-v1"
            and _integer(
                row["raw_controller_sequence_steps"],
                "Red setup route raw controller sequence",
            )
            == 0
            and not _boolean(row["teacher_route"], "Red setup teacher route")
            and _boolean(
                row["route_plan_authenticated"],
                "Red setup route plan authentication",
            )
            and _boolean(
                row["terminal_predicate_authenticated"],
                "Red setup terminal predicate authentication",
            )
        ):
            raise RedLivingDexSetupSourceError(
                "Red setup route provenance is not semantic-router derived"
            )
        ordered_refs.append(join)
        routes[join] = row

    if tuple(ordered_refs) != expected_refs:
        raise RedLivingDexSetupSourceError(
            "Red setup route order or reference differs"
        )
    route_plans = tuple(row["route_plan_sha256"] for row in routes.values())
    if len(route_plans) != len(set(route_plans)):
        raise RedLivingDexSetupSourceError("Red setup route plans repeat")
    return routes


def _validate_catalog_joins(
    slots: Sequence[Mapping[str, object]],
    prospective_slots: Sequence[LivingDexProspectiveCaptureSlot],
    providers: Mapping[str, Mapping[str, object]],
    routes: Mapping[str, Mapping[str, object]],
) -> None:
    used_providers: list[str] = []
    used_routes: list[str] = []
    for source_slot, prospective_slot in zip(
        slots,
        prospective_slots,
        strict=True,
    ):
        local = _slot_is_locally_composable(prospective_slot)
        for option in _mapping_sequence(
            source_slot["options"],
            "Red setup source options",
        ):
            provider_ref = _string(
                option["provider_join_sha256"],
                "Red setup provider reference",
            )
            provider = providers.get(provider_ref)
            if provider is None:
                raise RedLivingDexSetupSourceError(
                    "Red setup provider reference is absent"
                )
            used_providers.append(provider_ref)
            if local:
                if (
                    provider["destination_terminal_boundary_sha256"]
                    != source_slot["origin_boundary_sha256"]
                ):
                    raise RedLivingDexSetupSourceError(
                        "Red setup local provider leaves its origin"
                    )
                continue
            route_ref = _string(
                option["route_join_sha256"],
                "Red setup route reference",
            )
            route = routes.get(route_ref)
            if route is None or route["provider_join_sha256"] != provider_ref:
                raise RedLivingDexSetupSourceError(
                    "Red setup route/provider join differs"
                )
            used_routes.append(route_ref)
    if (
        len(used_providers) != len(set(used_providers))
        or set(used_providers) != set(providers)
    ):
        raise RedLivingDexSetupSourceError(
            "Red setup provider accounting differs"
        )
    if len(used_routes) != len(set(used_routes)) or set(used_routes) != set(routes):
        raise RedLivingDexSetupSourceError("Red setup route accounting differs")


def _validate_scope_bindings(
    slots: Sequence[Mapping[str, object]],
    prospective_slots: Sequence[LivingDexProspectiveCaptureSlot],
) -> None:
    families_by_scope: dict[str, set[str]] = {}
    scope_to_location: dict[str, str] = {}
    location_to_scope: dict[str, str] = {}
    for source_slot, prospective_slot in zip(
        slots,
        prospective_slots,
        strict=True,
    ):
        families_by_scope.setdefault(
            prospective_slot.family_scope_id,
            set(),
        ).update(
            _string(value, "Red setup family")
            for value in _sequence(
                source_slot["available_family_sha256s"],
                "Red setup families",
            )
        )
        location = _string(
            source_slot["location_sha256"],
            "Red setup location",
        )
        existing = scope_to_location.setdefault(
            prospective_slot.location_scope_id,
            location,
        )
        if existing != location:
            raise RedLivingDexSetupSourceError(
                "Red setup location scope maps to multiple locations"
            )
        existing_scope = location_to_scope.setdefault(
            location,
            prospective_slot.location_scope_id,
        )
        if existing_scope != prospective_slot.location_scope_id:
            raise RedLivingDexSetupSourceError(
                "Red setup location is reused across logical scopes"
            )

    rows = tuple(families_by_scope.items())
    for index, (left_scope, left_families) in enumerate(rows):
        for right_scope, right_families in rows[index + 1 :]:
            if left_scope != right_scope and left_families & right_families:
                raise RedLivingDexSetupSourceError(
                    "Red setup family scopes overlap"
                )


def _materialize_slot(
    slot: LivingDexProspectiveCaptureSlot,
    source_slot: Mapping[str, object],
    *,
    providers: Mapping[str, Mapping[str, object]],
    routes: Mapping[str, Mapping[str, object]],
) -> RedLivingDexSetupSlotBinding:
    option_bindings: list[RedLivingDexSetupOptionBinding] = []
    legacy_execution_identity_sha256 = canonical_sha256(
        {
            "schema": "pokemon.red.retired-setup-source-execution-identity.v1",
            "slot_sha256": slot.slot_sha256,
        }
    )
    family_sha256s = tuple(
        _string(value, "Red setup family")
        for value in _sequence(
            source_slot["available_family_sha256s"],
            "Red setup families",
        )
    )
    for option_index, (kind, option) in enumerate(
        zip(
            slot.available_option_kinds,
            _mapping_sequence(source_slot["options"], "Red setup source options"),
            strict=True,
        )
    ):
        provider_ref = _string(
            option["provider_join_sha256"],
            "Red setup provider reference",
        )
        provider = providers[provider_ref]
        route_ref = option["route_join_sha256"]
        route = None if route_ref is None else routes[_string(route_ref, "Red setup route")]
        transport = (
            RedLivingDexSetupTransportKind.LOCAL
            if route is None
            else RedLivingDexSetupTransportKind.ROUTED
        )
        option_bindings.append(
            RedLivingDexSetupOptionBinding(
                option_kind=kind,
                goal_kind=_GOAL_KIND_BY_OPTION[kind],
                transport_kind=transport,
                provider_contract_id=_string(
                    provider["provider_contract_id"],
                    "Red setup provider contract",
                ),
                provider_capability_sha256=_string(
                    provider["provider_capability_sha256"],
                    "Red setup provider capability",
                ),
                provider_recipe_sha256=provider_ref,
                expected_family_sha256=family_sha256s[option_index],
                execution_identity_sha256=legacy_execution_identity_sha256,
                origin_state_sha256=_string(
                    source_slot["state_sha256"],
                    "Red setup origin state",
                ),
                origin_boundary_sha256=_string(
                    source_slot["origin_boundary_sha256"],
                    "Red setup origin boundary",
                ),
                destination_terminal_boundary_sha256=_string(
                    provider["destination_terminal_boundary_sha256"],
                    "Red setup provider destination",
                ),
                expected_fresh_observation_sha256=_string(
                    provider["fresh_observation_sha256"],
                    "Red setup fresh observation",
                ),
                expected_provider_offer_sha256=_string(
                    provider["provider_offer_sha256"],
                    "Red setup provider offer",
                ),
                expected_executable_binding_sha256=_string(
                    provider["executable_binding_sha256"],
                    "Red setup executable binding",
                ),
                route_plan_sha256=(
                    None
                    if route is None
                    else _string(route["route_plan_sha256"], "Red setup route plan")
                ),
                route_terminal_predicate_sha256=(
                    None
                    if route is None
                    else _string(
                        route["route_terminal_predicate_sha256"],
                        "Red setup route terminal predicate",
                    )
                ),
                route_planner_binding_sha256=(
                    None
                    if route is None
                    else _string(
                        route["route_planner_binding_sha256"],
                        "Red setup route planner binding",
                    )
                ),
            )
        )
    return RedLivingDexSetupSlotBinding(
        slot_sha256=slot.slot_sha256,
        setup_plan_sha256=slot.setup.setup_plan_sha256,
        terminal_predicate_sha256=slot.setup.terminal_predicate_sha256,
        observer_contract_sha256=slot.setup.observer_contract_sha256,
        execution_identity_sha256=legacy_execution_identity_sha256,
        partition=slot.partition,
        available_option_kinds=slot.available_option_kinds,
        root_consumption_sha256=_string(
            source_slot["root_consumption_sha256"],
            "Red setup root",
        ),
        state_sha256=_string(source_slot["state_sha256"], "Red setup state"),
        origin_boundary_sha256=_string(
            source_slot["origin_boundary_sha256"],
            "Red setup origin boundary",
        ),
        envelope_sha256=_string(
            source_slot["envelope_sha256"],
            "Red setup envelope",
        ),
        menu_sha256=_string(source_slot["menu_sha256"], "Red setup menu"),
        observer_binding_sha256=_string(
            source_slot["observer_binding_sha256"],
            "Red setup observer",
        ),
        available_family_sha256s=tuple(
            _string(value, "Red setup family")
            for value in _sequence(
                source_slot["available_family_sha256s"],
                "Red setup families",
            )
        ),
        location_sha256=_string(
            source_slot["location_sha256"],
            "Red setup location",
        ),
        option_bindings=tuple(option_bindings),
    )


def _slot_is_locally_composable(slot: LivingDexProspectiveCaptureSlot) -> bool:
    common: set[str] | None = None
    for kind in slot.available_option_kinds:
        scopes = set(_CAPABILITY_BY_KIND[kind].boundary_scopes)
        common = scopes if common is None else common & scopes
    return bool(common)


def _provider_join_sha256(row: Mapping[str, object]) -> str:
    return canonical_sha256(
        {key: value for key, value in row.items() if key != "provider_join_sha256"}
    )


def _route_join_sha256(row: Mapping[str, object]) -> str:
    return canonical_sha256(
        {key: value for key, value in row.items() if key != "route_join_sha256"}
    )


def _envelope_sha256(slot: Mapping[str, object]) -> str:
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


def _menu_sha256(slot: Mapping[str, object]) -> str:
    return canonical_sha256(
        {
            "options": [
                {
                    "option_kind": option["option_kind"],
                    "provider_join_sha256": option["provider_join_sha256"],
                    "route_join_sha256": option["route_join_sha256"],
                }
                for option in _mapping_sequence(
                    slot["options"],
                    "Red setup source options",
                )
            ],
            "schema": RED_LIVING_DEX_SETUP_SOURCE_MENU_SCHEMA,
            "slot_sha256": slot["slot_sha256"],
            "state_sha256": slot["state_sha256"],
        }
    )


def _protected_input_set_sha256(
    prospective_plan_sha256: str,
    slots: Sequence[Mapping[str, object]],
) -> str:
    return canonical_sha256(
        {
            "prospective_plan_sha256": prospective_plan_sha256,
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


def _route_plan_witness_document(plan: RoutePlan) -> dict[str, object]:
    if not isinstance(plan, RoutePlan):
        raise TypeError("Red setup route plan witness differs")
    plan.__post_init__()
    return {
        "macro_edges": [
            _macro_edge_witness_document(edge)
            for edge in plan.macro_path.edges
        ],
        "maps": list(plan.macro_path.maps),
        "schema": RED_LIVING_DEX_SETUP_ROUTE_PLAN_WITNESS_SCHEMA,
        "segments": [
            {
                "approach": _local_path_witness_document(segment.approach),
                "passage_kind": segment.passage_kind,
                "source_map": segment.source_map,
                "target_map": segment.target_map,
                "transition": _macro_transition_witness_document(
                    segment.transition
                ),
                "transition_action_in_approach": (
                    segment.transition_action_in_approach
                ),
            }
            for segment in plan.segments
        ],
        "start_at": list(plan.start_at),
        "start_mode": plan.start_mode,
        "terminal_approach": (
            None
            if plan.terminal_approach is None
            else _local_path_witness_document(plan.terminal_approach)
        ),
        "terminal_at": list(plan.terminal_at),
        "terminal_mode": plan.terminal_mode,
    }


def _local_path_witness_document(path: LocalPath) -> dict[str, object]:
    if not isinstance(path, LocalPath):
        raise TypeError("Red setup local path witness differs")
    path.__post_init__()
    return {
        "coordinates": [list(item) for item in path.coordinates],
        "edges": [
            _local_edge_witness_document(edge)
            for edge in path.edges
        ],
        "modes": list(path.modes),
    }


def _local_edge_witness_document(edge: LocalEdge) -> dict[str, object]:
    if not isinstance(edge, LocalEdge):
        raise TypeError("Red setup local edge witness differs")
    edge.__post_init__()
    return {
        "action": edge.action,
        "action_kind": edge.action_kind.value,
        "cost": edge.cost,
        "kind": edge.kind,
        "required_mode": edge.required_mode,
        "requirements": sorted(edge.requirements),
        "result_mode": edge.result_mode,
        "target": list(edge.target),
        "transient": None if edge.transient is None else list(edge.transient),
    }


def _macro_edge_witness_document(edge: MacroEdge) -> dict[str, object]:
    if not isinstance(edge, MacroEdge):
        raise TypeError("Red setup macro edge witness differs")
    edge.__post_init__()
    return {
        "arrival_at": (
            None if edge.arrival_at is None else list(edge.arrival_at)
        ),
        "coordinate_transitions": [
            _macro_transition_witness_document(item)
            for item in edge.coordinate_transitions
        ],
        "cost": edge.cost,
        "destination_warp_index": edge.destination_warp_index,
        "exit_action": edge.exit_action,
        "heading": edge.heading,
        "kind": edge.kind,
        "target_at": None if edge.at is None else list(edge.at),
        "target_map": edge.target_map,
    }


def _macro_transition_witness_document(
    transition: MacroTransition,
) -> dict[str, object]:
    if not isinstance(transition, MacroTransition):
        raise TypeError("Red setup macro transition witness differs")
    transition.__post_init__()
    return {
        "action": transition.action,
        "arrival_at": list(transition.arrival_at),
        "exit_at": list(transition.exit_at),
    }


def _callable_contract_id(value: object, subject: str) -> str:
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    if (
        not callable(value)
        or not isinstance(module, str)
        or not module
        or not isinstance(qualname, str)
        or not qualname
    ):
        raise RedLivingDexSetupSourceError(f"{subject} provenance differs")
    return f"{module}.{qualname}"


def _decode_canonical_object(payload: bytes) -> Mapping[str, object]:
    class _DuplicateKey(ValueError):
        pass

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateKey
            result[key] = value
        return result

    try:
        text = payload.decode("ascii")
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RedLivingDexSetupSourceError(
            "Red setup source payload is not canonical unique-key JSON"
        ) from None
    if not isinstance(value, dict):
        raise RedLivingDexSetupSourceError(
            "Red setup source payload must be one object"
        )
    canonical = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    if canonical != payload:
        raise RedLivingDexSetupSourceError(
            "Red setup source payload is not canonical unique-key JSON"
        )
    return value


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    subject: str,
) -> None:
    if set(value) != expected:
        raise RedLivingDexSetupSourceError(f"{subject} fields differ")


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RedLivingDexSetupSourceError(f"{subject} must be one object")
    return value


def _sequence(value: object, subject: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise RedLivingDexSetupSourceError(f"{subject} must be one array")
    return value


def _mapping_sequence(value: object, subject: str) -> tuple[Mapping[str, object], ...]:
    return tuple(_mapping(item, subject) for item in _sequence(value, subject))


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexSetupSourceError(f"{subject} must be one string")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexSetupSourceError(
            f"{subject} must be a non-negative integer"
        )
    return value


def _boolean(value: object, subject: str) -> bool:
    if type(value) is not bool:  # noqa: E721
        raise RedLivingDexSetupSourceError(f"{subject} must be boolean")
    return value


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexSetupSourceError(f"{subject} SHA-256 differs")
    return value


def _option_kind(value: object) -> LivingDexOptionKind:
    if not isinstance(value, str):
        raise RedLivingDexSetupSourceError(
            "Red setup source option kind differs"
        )
    try:
        return LivingDexOptionKind(value)
    except (TypeError, ValueError):
        raise RedLivingDexSetupSourceError(
            "Red setup source option kind differs"
        ) from None


def _goal_kind(value: object) -> GoalKind:
    if not isinstance(value, str):
        raise RedLivingDexSetupSourceError(
            "Red setup source goal kind differs"
        )
    try:
        return GoalKind(value)
    except (TypeError, ValueError):
        raise RedLivingDexSetupSourceError(
            "Red setup source goal kind differs"
        ) from None


__all__ = [
    "MAXIMUM_SOURCE_PAYLOAD_BYTES",
    "RED_LIVING_DEX_SETUP_PROTECTED_INPUT_SET_SCHEMA",
    "RED_LIVING_DEX_SETUP_EXECUTABLE_WITNESS_SCHEMA",
    "RED_LIVING_DEX_SETUP_FRESH_OBSERVATION_WITNESS_SCHEMA",
    "RED_LIVING_DEX_SETUP_PROVIDER_OFFER_WITNESS_SCHEMA",
    "RED_LIVING_DEX_SETUP_ROUTE_PLAN_WITNESS_SCHEMA",
    "RED_LIVING_DEX_SETUP_SOURCE_ADAPTER_CONTRACT_ID",
    "RED_LIVING_DEX_SETUP_SOURCE_ENVELOPE_SCHEMA",
    "RED_LIVING_DEX_SETUP_SOURCE_MENU_SCHEMA",
    "RED_LIVING_DEX_SETUP_SOURCE_OPTION_SCHEMA",
    "RED_LIVING_DEX_SETUP_SOURCE_PRODUCER_CONTRACT_ID",
    "RED_LIVING_DEX_SETUP_SOURCE_PROVIDER_SCHEMA",
    "RED_LIVING_DEX_SETUP_SOURCE_ROUTE_SCHEMA",
    "RED_LIVING_DEX_SETUP_SOURCE_SCHEMA",
    "RED_LIVING_DEX_SETUP_SOURCE_SLOT_SCHEMA",
    "RedLivingDexSetupCatalogSource",
    "RedLivingDexSetupProviderWitness",
    "RedLivingDexSetupRouteWitness",
    "RedLivingDexSetupSlotWitness",
    "RedLivingDexSetupSourceError",
    "SourcePayloadReader",
    "build_red_living_dex_setup_source_payload",
    "red_living_dex_setup_executable_binding_sha256",
    "red_living_dex_setup_fresh_observation_sha256",
]
