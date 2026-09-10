"""Canonical path-free mechanic profiles for Red goal-manager contexts.

The public registry fixes *which semantic need* each slot must exercise.  A
private profile fixes the bounded Red mechanics that are genuinely available
at one captured state.  Profiles contain no callbacks or filesystem paths and
are authenticated by canonical bytes before either preflight or collection.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import cast

from pokemon_red_completion.generation_one import GENERATION_ONE_LEVEL_EVOLUTIONS
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_collection import red_species_number
from pokemon_red_completion.red_goal_manager import RedGoalManagerConfig

RED_GOAL_CONTEXT_PROFILE_SCHEMA = "pokemon-red-goal-manager-context-profile-v1"
RED_GOAL_MANAGER_CONTRACT_ID = "pokemon.red.completion-team.v1"
RED_GOAL_MANAGER_CONFIG = RedGoalManagerConfig()
_MAX_PROFILE_BYTES = 256 * 1024
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DIRECTIONS = frozenset({"up", "right", "down", "left"})


class RedGoalContextProfileError(RuntimeError):
    """Raised when a private context profile is mutable or over-authorized."""


class RedGoalMechanic(StrEnum):
    MIDGAME_STORY = "midgame_story"
    WILD_CORRIDOR_CAPTURE = "wild_corridor_capture"
    WILD_CORRIDOR_DEVELOPMENT = "wild_corridor_development"
    BALANCED_TEAM = "balanced_team"
    DIGLETT_EVOLUTION = "diglett_evolution"
    TARGETED_PARTY_DEVELOPMENT = "targeted_party_development"
    TARGETED_LEVEL_EVOLUTION = "targeted_level_evolution"
    FIELD_RESTORE = "field_restore"
    FIELD_PP_RESTORE = "field_pp_restore"
    CENTER_RESTORE = "center_restore"
    MART_RESUPPLY = "mart_resupply"
    BOX_SWITCH = "box_switch"
    CONTROL_RECOVERY = "control_recovery"
    WILD_CORRIDOR_DISCOVERY = "wild_corridor_discovery"


_MECHANIC_KIND = {
    RedGoalMechanic.MIDGAME_STORY: GoalKind.ADVANCE_STORY,
    RedGoalMechanic.WILD_CORRIDOR_CAPTURE: GoalKind.ACQUIRE_SPECIES,
    RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT: GoalKind.DEVELOP_TEAM,
    RedGoalMechanic.BALANCED_TEAM: GoalKind.DEVELOP_TEAM,
    RedGoalMechanic.DIGLETT_EVOLUTION: GoalKind.EVOLVE_SPECIES,
    RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT: GoalKind.DEVELOP_TEAM,
    RedGoalMechanic.TARGETED_LEVEL_EVOLUTION: GoalKind.EVOLVE_SPECIES,
    RedGoalMechanic.FIELD_RESTORE: GoalKind.RESTORE_TEAM,
    RedGoalMechanic.FIELD_PP_RESTORE: GoalKind.RESTORE_TEAM,
    RedGoalMechanic.CENTER_RESTORE: GoalKind.RESTORE_TEAM,
    RedGoalMechanic.MART_RESUPPLY: GoalKind.RESUPPLY,
    RedGoalMechanic.BOX_SWITCH: GoalKind.MANAGE_STORAGE,
    RedGoalMechanic.CONTROL_RECOVERY: GoalKind.RECOVER_CONTROL,
    RedGoalMechanic.WILD_CORRIDOR_DISCOVERY: GoalKind.EXPLORE,
}


@dataclass(frozen=True, slots=True)
class RedGoalProviderSpec:
    """One finite, schema-validated provider declaration."""

    kind: GoalKind
    mechanic: RedGoalMechanic
    parameters: Mapping[str, object]
    configuration_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GoalKind) or not isinstance(
            self.mechanic, RedGoalMechanic
        ):
            raise RedGoalContextProfileError("provider identity is invalid")
        if _MECHANIC_KIND[self.mechanic] is not self.kind:
            raise RedGoalContextProfileError("provider mechanic and goal kind differ")
        if not isinstance(self.parameters, Mapping):
            raise RedGoalContextProfileError("provider parameters must be a mapping")
        if _SHA256.fullmatch(self.configuration_sha256) is None:
            raise RedGoalContextProfileError("provider configuration digest is invalid")
        expected = _document_sha256(
            {
                "kind": self.kind.value,
                "mechanic": self.mechanic.value,
                "parameters": _thaw(self.parameters),
            }
        )
        if self.configuration_sha256 != expected:
            raise RedGoalContextProfileError("provider configuration digest differs")


@dataclass(frozen=True, slots=True)
class RedGoalContextProfile:
    """Authenticated Red adapter configuration with no private path fields."""

    profile_id: str
    profile_sha256: str
    manager_config: RedGoalManagerConfig
    providers: tuple[RedGoalProviderSpec, ...]

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.profile_id) is None:
            raise RedGoalContextProfileError("context profile identity is invalid")
        if _SHA256.fullmatch(self.profile_sha256) is None:
            raise RedGoalContextProfileError("context profile digest is invalid")
        if not isinstance(self.manager_config, RedGoalManagerConfig):
            raise RedGoalContextProfileError("context manager configuration is invalid")
        if not isinstance(self.providers, tuple) or not 3 <= len(self.providers) <= len(
            GoalKind
        ):
            raise RedGoalContextProfileError(
                "context profile needs between three and nine providers"
            )
        kinds = tuple(provider.kind for provider in self.providers)
        if len(kinds) != len(set(kinds)):
            raise RedGoalContextProfileError("context profile duplicates a goal kind")
        if kinds != tuple(kind for kind in GoalKind if kind in set(kinds)):
            raise RedGoalContextProfileError(
                "context providers must use canonical semantic order"
            )

    def public_dict(self) -> dict[str, object]:
        """Return only identities and semantic coverage, never private parameters."""

        return {
            "schema": "pokemon-red-goal-manager-context-profile-summary-v1",
            "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256,
            "manager_contract_id": RED_GOAL_MANAGER_CONTRACT_ID,
            "provider_kinds": [provider.kind.value for provider in self.providers],
            "provider_count": len(self.providers),
            "private_path_fields": 0,
        }


def build_native_boxed_evolution_profile_payload(
    profile: RedGoalContextProfile, *, source_species: int,
    target_species: int, evolution_level: int,
) -> bytes:
    """Declare useful collection evolution instead of arbitrary party grinding."""
    from pokemon_red_completion.red_collection import red_species_ref
    providers = {
        spec.kind: (spec.kind, spec.mechanic, cast(dict[str, object], _thaw(spec.parameters)))
        for spec in profile.providers if spec.kind is not GoalKind.DEVELOP_TEAM
    }
    providers[GoalKind.EVOLVE_SPECIES] = (
        GoalKind.EVOLVE_SPECIES, RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        {"source_species_ref": red_species_ref(source_species),
         "target_species_ref": red_species_ref(target_species), "evolution_level": evolution_level},
    )
    return build_red_goal_context_profile_payload(
        profile_id=profile.profile_id,
        providers=tuple(providers[kind] for kind in GoalKind if kind in providers),
    )


def bind_capture_surf_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Opt future capture transport into observed Surf; historical profiles stay unchanged."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["surf_transport"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("Surf transport needs an existing capture objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_capture_cut_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Opt future capture transport into observed, land-only Cut execution."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["cut_transport"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("Cut transport needs an existing capture objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_capture_fly_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Opt only the existing wild capture objective into qualified Fly transport."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["fly_transport"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("Fly transport needs an existing capture objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_capture_access_requirements_profile(
    profile: RedGoalContextProfile,
) -> RedGoalContextProfile:
    """Prospective prerequisite-aware acquisition, preserving historical menus."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["capture_access_requirements"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("capture access requirements need a capture objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_travel_capture_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Prospective capture during acquisition travel; old menus remain unchanged."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["travel_capture"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("travel capture needs a capture objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_observed_local_capture_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Opt current-map capture into observed reachable lanes, preserving old profiles."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["observed_local_capture"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("observed local capture needs a capture objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_indoor_fly_departure_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Version indoor access prospectively without changing old checkpoint menus."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic in {
            RedGoalMechanic.WILD_CORRIDOR_CAPTURE, RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        } and parameters.get("fly_transport") is True:
            parameters["indoor_fly_departure"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("indoor departure needs an existing Fly objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_evolution_fly_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Opt the existing evolution objective into qualified Fly transport only."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            parameters["fly_transport"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("Fly transport needs an existing evolution objective")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def require_resupply_only_profile_transition(
    before: RedGoalContextProfile, after: RedGoalContextProfile,
) -> None:
    """An explicit regional shop change may not alter any other playing skill."""
    if not isinstance(before, RedGoalContextProfile) or not isinstance(
        after, RedGoalContextProfile
    ):
        raise TypeError("resupply transition needs two context profiles")
    if before.profile_id != after.profile_id or before.manager_config != after.manager_config:
        raise RedGoalContextProfileError("resupply transition changes the manager contract")
    original = {spec.kind: spec for spec in before.providers}
    changed = {spec.kind: spec for spec in after.providers}
    if original.keys() != changed.keys() or GoalKind.RESUPPLY not in original:
        raise RedGoalContextProfileError("resupply transition changes the provider inventory")
    for kind, spec in original.items():
        if kind is GoalKind.RESUPPLY:
            if spec.mechanic is not RedGoalMechanic.MART_RESUPPLY or (
                changed[kind].mechanic is not RedGoalMechanic.MART_RESUPPLY
            ):
                raise RedGoalContextProfileError(
                    "resupply transition requires the existing Mart skill"
                )
        elif changed[kind] != spec:
            raise RedGoalContextProfileError("resupply transition changes a non-supply skill")


def load_red_goal_context_profile(path: str | Path) -> RedGoalContextProfile:
    """Read one profile without retaining its private filesystem location."""

    try:
        payload = Path(path).read_bytes()
    except OSError:
        raise RedGoalContextProfileError("context profile is unavailable") from None
    return parse_red_goal_context_profile(payload)


def build_red_goal_context_profile_payload(
    *,
    profile_id: str,
    providers: tuple[
        tuple[GoalKind, RedGoalMechanic, Mapping[str, object]],
        ...,
    ],
) -> bytes:
    """Build canonical private profile bytes under the fixed Red contract."""

    document = {
        "schema": RED_GOAL_CONTEXT_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "manager_config": red_goal_manager_contract_document()["manager_config"],
        "providers": [
            {
                "kind": kind.value,
                "mechanic": mechanic.value,
                "parameters": dict(parameters),
            }
            for kind, mechanic, parameters in providers
        ],
    }
    payload = _canonical_line(document)
    parsed = parse_red_goal_context_profile(payload)
    if parsed.profile_id != profile_id:
        raise RedGoalContextProfileError("built context profile identity differs")
    return payload


def bind_cartridge_trainer_story_profile(
    profile: RedGoalContextProfile, *, objective_id: str = "defeat_lorelei",
    maximum_full_restores: int = 0,
    recovery_controller: str = "critical-inclusive",
) -> RedGoalContextProfile:
    """Prospectively replace only the legacy story executor, preserving other goals."""
    if type(maximum_full_restores) is not int or not 0 <= maximum_full_restores <= 2:
        raise RedGoalContextProfileError("story recovery budget must be zero through two")
    if recovery_controller not in {"critical-inclusive", "ordinary-bounded-healing"} or (
        recovery_controller != "critical-inclusive" and not maximum_full_restores
    ):
        raise RedGoalContextProfileError(
            "story recovery controller requires its explicit item budget",
        )
    providers = {
        spec.kind: (spec.kind, spec.mechanic, cast(dict[str, object], _thaw(spec.parameters)))
        for spec in profile.providers
    }
    providers[GoalKind.ADVANCE_STORY] = (
        GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY,
        {"trainer_objective": objective_id,
         **({"maximum_full_restores": maximum_full_restores} if maximum_full_restores else {})},
    )
    if recovery_controller != "critical-inclusive":
        providers[GoalKind.ADVANCE_STORY][2]["recovery_controller"] = recovery_controller
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id,
        providers=tuple(providers[kind] for kind in GoalKind if kind in providers),
    ))


def bind_affordable_field_restore_profile(
    profile: RedGoalContextProfile, *, reserve_last_full_restore: bool = False,
) -> RedGoalContextProfile:
    """Opt into one owned recovery item, without changing historical profiles."""
    if type(reserve_last_full_restore) is not bool:
        raise RedGoalContextProfileError("restoration reserve must be an explicit boolean")
    providers = {
        spec.kind: (spec.kind, spec.mechanic, cast(dict[str, object], _thaw(spec.parameters)))
        for spec in profile.providers
    }
    providers[GoalKind.RESTORE_TEAM] = (
        GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE,
        {"affordable_single_item": True,
         **({"reserve_last_full_restore": True} if reserve_last_full_restore else {})},
    )
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id,
        providers=tuple(providers[kind] for kind in GoalKind if kind in providers),
    ))


def bind_combined_field_restore_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Explicit affordable reserved HP recovery, retaining owned PP as fallback."""
    providers = {
        spec.kind: (spec.kind, spec.mechanic, cast(dict[str, object], _thaw(spec.parameters)))
        for spec in profile.providers
    }
    providers[GoalKind.RESTORE_TEAM] = (
        GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE,
        {"affordable_single_item": True, "reserve_last_full_restore": True,
         "include_pp_fallback": True},
    )
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id,
        providers=tuple(providers[kind] for kind in GoalKind if kind in providers),
    ))


def bind_field_pp_restore_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Prospectively expose one owned PP item; old recovery profiles stay unchanged."""
    providers = {
        spec.kind: (spec.kind, spec.mechanic, cast(dict[str, object], _thaw(spec.parameters)))
        for spec in profile.providers
    }
    providers[GoalKind.RESTORE_TEAM] = (
        GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_PP_RESTORE, {},
    )
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id,
        providers=tuple(providers[kind] for kind in GoalKind if kind in providers),
    ))


def bind_affordable_ball_supply_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Explicit cash-only affordability transition, preserving all other skills."""
    providers = []
    found = False
    for spec in profile.providers:
        parameters = cast(dict[str, object], _thaw(spec.parameters))
        if spec.mechanic is RedGoalMechanic.MART_RESUPPLY:
            parameters.pop("funding_sale", None)
            parameters["affordable_ball_purchase"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedGoalContextProfileError("affordable supply requires an existing Mart skill")
    changed = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))
    require_resupply_only_profile_transition(profile, changed)
    return changed


def build_acquisition_replanning_profile_payload(
    profile: RedGoalContextProfile,
    *,
    completed_battles: int = 4,
) -> bytes:
    """Add the source-local development skill to one wild acquisition profile.

    The transformation is deliberately mechanical: it reuses the already authenticated
    capture corridor byte-for-byte, requires the discovery corridor to describe the same
    source, and adds no route, healing, or root-specific behavior.
    """

    if not isinstance(profile, RedGoalContextProfile):
        raise TypeError("profile must be a RedGoalContextProfile")
    if type(completed_battles) is not int or completed_battles != 4:  # noqa: E721
        raise RedGoalContextProfileError(
            "acquisition replanning requires the qualified four-battle dose"
        )
    if any(provider.kind is GoalKind.DEVELOP_TEAM for provider in profile.providers):
        raise RedGoalContextProfileError(
            "acquisition profile already exposes team development"
        )
    capture = next(
        (
            provider
            for provider in profile.providers
            if provider.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE
        ),
        None,
    )
    discovery = next(
        (
            provider
            for provider in profile.providers
            if provider.mechanic is RedGoalMechanic.WILD_CORRIDOR_DISCOVERY
        ),
        None,
    )
    if capture is None or discovery is None:
        raise RedGoalContextProfileError(
            "acquisition replanning needs capture and discovery corridors"
        )
    capture_parameters = _thaw(capture.parameters)
    discovery_parameters = _thaw(discovery.parameters)
    if capture_parameters != discovery_parameters or not isinstance(
        capture_parameters, dict
    ):
        raise RedGoalContextProfileError(
            "acquisition and discovery corridors describe different sources"
        )
    if capture_parameters.get("map_id") != int(MapId.POKEMON_MANSION_1F):
        raise RedGoalContextProfileError(
            "acquisition replanning requires the measured Mansion venue"
        )
    providers: list[tuple[GoalKind, RedGoalMechanic, Mapping[str, object]]] = [
        (
            provider.kind,
            provider.mechanic,
            cast(Mapping[str, object], _thaw(provider.parameters)),
        )
        for provider in profile.providers
    ]
    providers.append(
        (
            GoalKind.DEVELOP_TEAM,
            RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
            {**capture_parameters, "completed_battles": completed_battles},
        )
    )
    providers.sort(key=lambda row: tuple(GoalKind).index(row[0]))
    return build_red_goal_context_profile_payload(
        profile_id=profile.profile_id,
        providers=tuple(providers),
    )


def red_goal_manager_contract_document() -> dict[str, object]:
    """Return the fixed normalization target admitted for counted Red data."""

    return {
        "manager_config": {
            "desired_capture_items": RED_GOAL_MANAGER_CONFIG.desired_capture_items,
            "desired_recovery_items": RED_GOAL_MANAGER_CONFIG.desired_recovery_items,
            "desired_storage_headroom": RED_GOAL_MANAGER_CONFIG.desired_storage_headroom,
            "required_party_size": RED_GOAL_MANAGER_CONFIG.required_party_size,
            "required_team_level": RED_GOAL_MANAGER_CONFIG.required_team_level,
        },
        "manager_contract_id": RED_GOAL_MANAGER_CONTRACT_ID,
        "perfect_collection_level_target_included": False,
        "schema": "pokemon-red-goal-manager-normalization-contract-v1",
    }


def parse_red_goal_context_profile(payload: bytes) -> RedGoalContextProfile:
    """Authenticate canonical bytes and admit only the finite mechanic schema."""

    if not isinstance(payload, bytes):
        raise TypeError("Red goal context profile must be bytes")
    if not payload or len(payload) > _MAX_PROFILE_BYTES:
        raise RedGoalContextProfileError("context profile size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RedGoalContextProfileError(
            "context profile is not canonical ASCII JSON"
        ) from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise RedGoalContextProfileError(
            "context profile is not canonical ASCII JSON"
        )
    _exact_keys(value, {"schema", "profile_id", "manager_config", "providers"})
    if value["schema"] != RED_GOAL_CONTEXT_PROFILE_SCHEMA:
        raise RedGoalContextProfileError("context profile schema differs")
    profile_id = _safe_id(value["profile_id"], "profile identity")
    manager_config = _parse_manager_config(value["manager_config"])
    raw_providers = value["providers"]
    if not isinstance(raw_providers, list):
        raise RedGoalContextProfileError("context providers must be a list")
    providers = tuple(_parse_provider(item) for item in raw_providers)
    return RedGoalContextProfile(
        profile_id=profile_id,
        profile_sha256=hashlib.sha256(payload).hexdigest(),
        manager_config=manager_config,
        providers=providers,
    )


def _parse_manager_config(value: object) -> RedGoalManagerConfig:
    row = _mapping(value, "manager configuration")
    _exact_keys(
        row,
        {
            "required_party_size",
            "required_team_level",
            "desired_capture_items",
            "desired_recovery_items",
            "desired_storage_headroom",
        },
    )
    try:
        result = RedGoalManagerConfig(
            required_party_size=_integer(row["required_party_size"], "party size"),
            required_team_level=_integer(row["required_team_level"], "team level"),
            desired_capture_items=_integer(
                row["desired_capture_items"], "capture reserve"
            ),
            desired_recovery_items=_integer(
                row["desired_recovery_items"], "recovery reserve"
            ),
            desired_storage_headroom=_integer(
                row["desired_storage_headroom"], "storage reserve"
            ),
        )
    except (TypeError, ValueError) as error:
        raise RedGoalContextProfileError(str(error)) from error
    if result != RED_GOAL_MANAGER_CONFIG:
        raise RedGoalContextProfileError(
            "context manager configuration differs from the fixed Red contract"
        )
    return result


def _parse_provider(value: object) -> RedGoalProviderSpec:
    row = _mapping(value, "provider")
    _exact_keys(row, {"kind", "mechanic", "parameters"})
    try:
        raw_kind = row["kind"]
        raw_mechanic = row["mechanic"]
        if not isinstance(raw_kind, str) or not isinstance(raw_mechanic, str):
            raise TypeError
        kind = GoalKind(raw_kind)
        mechanic = RedGoalMechanic(raw_mechanic)
    except (TypeError, ValueError):
        raise RedGoalContextProfileError("provider kind or mechanic is invalid") from None
    if _MECHANIC_KIND[mechanic] is not kind:
        raise RedGoalContextProfileError("provider mechanic and goal kind differ")
    parameters = _parse_parameters(mechanic, row["parameters"])
    frozen = _freeze(parameters)
    assert isinstance(frozen, Mapping)
    return RedGoalProviderSpec(
        kind=kind,
        mechanic=mechanic,
        parameters=frozen,
        configuration_sha256=_document_sha256(
            {
                "kind": kind.value,
                "mechanic": mechanic.value,
                "parameters": parameters,
            }
        ),
    )


def _parse_parameters(
    mechanic: RedGoalMechanic,
    value: object,
) -> dict[str, object]:
    row = dict(_mapping(value, "provider parameters"))
    if mechanic is RedGoalMechanic.MIDGAME_STORY:
        if not row:
            return row
        _exact_keys(row, {"trainer_objective"} | (
            {"maximum_full_restores"} if "maximum_full_restores" in row else set()
        ) | ({"recovery_controller"} if "recovery_controller" in row else set()))
        if "recovery_controller" in row and (
            row["recovery_controller"] != "ordinary-bounded-healing"
            or "maximum_full_restores" not in row
        ):
            raise RedGoalContextProfileError(
                "ordinary healing requires an explicit positive budget",
            )
        if "maximum_full_restores" in row and (
            type(row["maximum_full_restores"]) is not int
            or row["maximum_full_restores"] not in (1, 2)
        ):
            raise RedGoalContextProfileError("explicit story recovery requires one or two items")
        if row["trainer_objective"] not in (
            "defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance", "defeat_champion",
        ):
            raise RedGoalContextProfileError("cartridge story objective is not supported")
        return row
    if mechanic is RedGoalMechanic.FIELD_RESTORE and row:
        _exact_keys(row, {"affordable_single_item"} | (
            {"reserve_last_full_restore"} if "reserve_last_full_restore" in row else set()
        ) | ({"include_pp_fallback"} if "include_pp_fallback" in row else set()))
        if row["affordable_single_item"] is not True:
            raise RedGoalContextProfileError("single-item recovery requires explicit opt-in")
        if "reserve_last_full_restore" in row and row["reserve_last_full_restore"] is not True:
            raise RedGoalContextProfileError("restoration reserve requires explicit opt-in")
        if "include_pp_fallback" in row and (
            row["include_pp_fallback"] is not True
            or row.get("reserve_last_full_restore") is not True
        ):
            raise RedGoalContextProfileError("combined restoration requires explicit reserved mode")
        return row
    if mechanic in {
        RedGoalMechanic.BALANCED_TEAM,
        RedGoalMechanic.DIGLETT_EVOLUTION,
        RedGoalMechanic.FIELD_RESTORE,
        RedGoalMechanic.FIELD_PP_RESTORE,
        RedGoalMechanic.CENTER_RESTORE,
        RedGoalMechanic.CONTROL_RECOVERY,
    }:
        _exact_keys(row, set())
        return row
    if mechanic is RedGoalMechanic.TARGETED_PARTY_DEVELOPMENT:
        _exact_keys(row, {"trainee_species_ref", "level_increment"})
        trainee_species_ref = _species_ref(
            row["trainee_species_ref"],
            "development trainee",
        )
        level_increment = _positive_integer(
            row["level_increment"],
            "development level increment",
        )
        if level_increment != 1:
            raise RedGoalContextProfileError(
                "targeted development requires one level of progress"
            )
        return {
            "trainee_species_ref": trainee_species_ref,
            "level_increment": level_increment,
        }
    if mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
        optional = {key for key in ("fly_transport", "indoor_fly_departure") if key in row}
        if any(type(row[key]) is not bool for key in optional):
            raise RedGoalContextProfileError("Fly transport must be an explicit boolean")
        if "indoor_fly_departure" in row and row.get("fly_transport") is not True:
            raise RedGoalContextProfileError("indoor departure requires Fly transport")
        _exact_keys(
            row,
            {
                "source_species_ref",
                "target_species_ref",
                "evolution_level",
            } | optional,
        )
        source_species_ref = _species_ref(
            row["source_species_ref"],
            "evolution source",
        )
        target_species_ref = _species_ref(
            row["target_species_ref"],
            "evolution target",
        )
        evolution_level = _positive_integer(
            row["evolution_level"],
            "evolution level",
        )
        if evolution_level > 100:
            raise RedGoalContextProfileError("evolution level is outside Red's level range")
        evolution = (
            red_species_number(source_species_ref),
            red_species_number(target_species_ref),
            evolution_level,
        )
        if evolution not in GENERATION_ONE_LEVEL_EVOLUTIONS:
            raise RedGoalContextProfileError(
                "targeted evolution is not a canonical Red level evolution"
            )
        return {
            "source_species_ref": source_species_ref,
            "target_species_ref": target_species_ref,
            "evolution_level": evolution_level,
            **{key: row[key] for key in optional},
        }
    if mechanic in {
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
    }:
        required = {
            "source_id",
            "label",
            "map_id",
            "player_x",
            "player_y",
            "forward_directions",
            "starting_endpoint",
            "maximum_legs",
            "maximum_seek_steps",
            "maximum_encounters",
        }
        if mechanic is RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT:
            required.add("completed_battles")
        local_species = row.get("source_species_numbers")
        capture_species = row.get("capture_species_numbers")
        if "capture_search_budget" in row:
            search_legs = _positive_integer(row.get("maximum_legs"), "survey legs")
            search_actions = _positive_integer(row.get("maximum_seek_steps"), "seek steps")
            search_encounters = _positive_integer(row.get("maximum_encounters"), "encounter bound")
            if (
                mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE
                or row["capture_search_budget"] != "bounded-search-v1"
                or search_legs > 160 or search_legs % 2 != 0
                or search_actions > 256 or search_encounters > 32
                or search_legs + 2 * search_encounters + 2 > search_actions
            ):
                raise RedGoalContextProfileError("capture search budget differs")
            required.add("capture_search_budget")
        if "surf_transport" in row:
            if mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE or (
                type(row["surf_transport"]) is not bool
            ):
                raise RedGoalContextProfileError("capture Surf transport differs")
            required.add("surf_transport")
        if "cut_transport" in row:
            if mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE or (
                type(row["cut_transport"]) is not bool
            ):
                raise RedGoalContextProfileError("capture Cut transport differs")
            required.add("cut_transport")
        if "fly_transport" in row:
            if mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE or (
                type(row["fly_transport"]) is not bool
            ):
                raise RedGoalContextProfileError("capture Fly transport differs")
            required.add("fly_transport")
        if "indoor_fly_departure" in row:
            if (
                mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE
                or type(row["indoor_fly_departure"]) is not bool
                or row.get("fly_transport") is not True
            ):
                raise RedGoalContextProfileError("indoor departure requires capture Fly transport")
            required.add("indoor_fly_departure")
        if "travel_capture" in row:
            if (mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE
                    or type(row["travel_capture"]) is not bool):
                raise RedGoalContextProfileError("travel capture must be a capture boolean")
            required.add("travel_capture")
        if "observed_local_capture" in row:
            if (
                mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE
                or type(row["observed_local_capture"]) is not bool
            ):
                raise RedGoalContextProfileError("observed local capture must be a boolean")
            required.add("observed_local_capture")
        if "capture_access_requirements" in row:
            if (mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE
                    or type(row["capture_access_requirements"]) is not bool):
                raise RedGoalContextProfileError("capture access requirements must be a boolean")
            required.add("capture_access_requirements")
        if "capture_species_numbers" in row:
            if mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE or (
                not isinstance(capture_species, list)
                or not capture_species
                or any(type(number) is not int or not 1 <= number <= 151
                       for number in capture_species)
                or capture_species != sorted(set(capture_species))
            ):
                raise RedGoalContextProfileError("local capture species are invalid")
            required.add("capture_species_numbers")
        if "capture_status_support" in row:
            if mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE or (
                type(row["capture_status_support"]) is not bool
            ):
                raise RedGoalContextProfileError("capture status support differs")
            required.add("capture_status_support")
        if "source_species_numbers" in row:
            if mechanic is not RedGoalMechanic.WILD_CORRIDOR_DISCOVERY or (
                not isinstance(local_species, list)
                or not local_species
                or any(type(number) is not int or not 1 <= number <= 151
                       for number in local_species)
                or local_species != sorted(set(local_species))
            ):
                raise RedGoalContextProfileError("local discovery species are invalid")
            required.add("source_species_numbers")
        _exact_keys(row, required)
        source_id = _bounded_text(row["source_id"], "source identity")
        label = _bounded_text(row["label"], "corridor label")
        directions = row["forward_directions"]
        if (
            not isinstance(directions, list)
            or not directions
            or len(directions) > 4096
            or any(direction not in _DIRECTIONS for direction in directions)
        ):
            raise RedGoalContextProfileError("corridor directions are invalid")
        starting_endpoint = row["starting_endpoint"]
        if starting_endpoint not in {"south", "north"}:
            raise RedGoalContextProfileError("corridor endpoint is invalid")
        parsed = {
            "source_id": source_id,
            "label": label,
            "map_id": int(_map_id(row["map_id"])),
            "player_x": _integer(row["player_x"], "corridor x coordinate"),
            "player_y": _integer(row["player_y"], "corridor y coordinate"),
            "forward_directions": list(directions),
            "starting_endpoint": starting_endpoint,
            "maximum_legs": _positive_integer(row["maximum_legs"], "survey legs"),
            "maximum_seek_steps": _positive_integer(
                row["maximum_seek_steps"], "seek steps"
            ),
            "maximum_encounters": _positive_integer(
                row["maximum_encounters"], "encounter bound"
            ),
        }
        if mechanic is RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT:
            parsed["completed_battles"] = _positive_integer(
                row["completed_battles"], "development battle dose"
            )
        if local_species is not None:
            parsed["source_species_numbers"] = local_species
        if capture_species is not None:
            parsed["capture_species_numbers"] = capture_species
        if "capture_status_support" in row:
            parsed["capture_status_support"] = row["capture_status_support"]
        if "capture_search_budget" in row:
            parsed["capture_search_budget"] = row["capture_search_budget"]
        if "cut_transport" in row:
            parsed["cut_transport"] = row["cut_transport"]
        if "surf_transport" in row:
            parsed["surf_transport"] = row["surf_transport"]
        if "fly_transport" in row:
            parsed["fly_transport"] = row["fly_transport"]
        if "indoor_fly_departure" in row:
            parsed["indoor_fly_departure"] = row["indoor_fly_departure"]
        if "travel_capture" in row:
            parsed["travel_capture"] = row["travel_capture"]
        if "observed_local_capture" in row:
            parsed["observed_local_capture"] = row["observed_local_capture"]
        if "capture_access_requirements" in row:
            parsed["capture_access_requirements"] = row["capture_access_requirements"]
        return parsed
    if mechanic is RedGoalMechanic.MART_RESUPPLY:
        _exact_keys(
            row,
            {
                "map_id",
                "player_x",
                "player_y",
                "interaction_direction",
                "purchases",
            } | ({"funding_sale"} if "funding_sale" in row else set())
            | ({"affordable_ball_purchase"} if "affordable_ball_purchase" in row else set()),
        )
        purchases = row["purchases"]
        if not isinstance(purchases, list) or not purchases:
            raise RedGoalContextProfileError("Mart purchases must be a non-empty list")
        parsed_purchases = [_parse_purchase(item) for item in purchases]
        if len({item["item_id"] for item in parsed_purchases}) != len(parsed_purchases):
            raise RedGoalContextProfileError("Mart profile purchases an item twice")
        sale_fields = {}
        affordability_fields = {}
        if "affordable_ball_purchase" in row:
            value = row["affordable_ball_purchase"]
            if type(value) is not bool or (
                value and (
                    len(parsed_purchases) != 1
                    or parsed_purchases[0]["item_id"] not in {
                        int(ItemId.POKE_BALL), int(ItemId.GREAT_BALL), int(ItemId.ULTRA_BALL),
                    } or "funding_sale" in row
                )
            ):
                raise RedGoalContextProfileError(
                    "affordable supply needs one ordinary ball/no sale"
                )
            affordability_fields = {"affordable_ball_purchase": value}
        if "funding_sale" in row:
            sale = row["funding_sale"]
            if not isinstance(sale, dict):
                raise RedGoalContextProfileError("Mart funding sale must be a mapping")
            _exact_keys(sale, {"item_id", "quantity", "minimum_retained"})
            item = _integer(sale["item_id"], "funding item")
            quantity = _positive_integer(sale["quantity"], "funding quantity")
            retained = _positive_integer(sale["minimum_retained"], "funding reserve")
            floors = {int(ItemId.HYPER_POTION): 8, int(ItemId.FULL_RESTORE): 6}
            if item not in floors or quantity > 99 or not floors[item] <= retained <= 99:
                raise RedGoalContextProfileError("Mart funding sale violates protected reserve")
            if any(p["item_id"] == item for p in parsed_purchases):
                raise RedGoalContextProfileError("Mart cannot sell and rebuy the same item")
            sale_fields = {"funding_sale": {
                "item_id": item, "quantity": quantity, "minimum_retained": retained,
            }}
        return {
            "map_id": int(_map_id(row["map_id"])),
            "player_x": _integer(row["player_x"], "Mart x coordinate"),
            "player_y": _integer(row["player_y"], "Mart y coordinate"),
            "interaction_direction": _direction(
                row["interaction_direction"], "Mart interaction"
            ),
            "purchases": parsed_purchases,
            **sale_fields,
            **affordability_fields,
        }
    if mechanic is RedGoalMechanic.BOX_SWITCH:
        _exact_keys(
            row,
            {"target_box_index", "map_id", "player_x", "player_y"},
        )
        target = _integer(row["target_box_index"], "target box")
        if not 0 <= target < 12:
            raise RedGoalContextProfileError("target box is outside Red's storage")
        return {
            "target_box_index": target,
            "map_id": int(_map_id(row["map_id"])),
            "player_x": _integer(row["player_x"], "PC x coordinate"),
            "player_y": _integer(row["player_y"], "PC y coordinate"),
        }
    raise RedGoalContextProfileError("provider mechanic is unsupported")


def _parse_purchase(value: object) -> dict[str, int]:
    row = _mapping(value, "Mart purchase")
    _exact_keys(row, {"absolute_index", "item_id", "quantity", "unit_price"})
    try:
        item = ItemId(_integer(row["item_id"], "Mart item"))
    except ValueError:
        raise RedGoalContextProfileError("Mart item is unknown") from None
    return {
        "absolute_index": _integer(row["absolute_index"], "Mart inventory index"),
        "item_id": int(item),
        "quantity": _positive_integer(row["quantity"], "Mart quantity"),
        "unit_price": _positive_integer(row["unit_price"], "Mart unit price"),
    }


def _map_id(value: object) -> MapId:
    try:
        return MapId(_integer(value, "map identity"))
    except ValueError:
        raise RedGoalContextProfileError("map identity is unknown") from None


def _direction(value: object, subject: str) -> str:
    if not isinstance(value, str) or value not in _DIRECTIONS:
        raise RedGoalContextProfileError(f"{subject} direction is invalid")
    return value


def _bounded_text(value: object, subject: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 200
        or "/" in value
        or "\\" in value
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
    ):
        raise RedGoalContextProfileError(f"{subject} is invalid")
    return value


def _species_ref(value: object, subject: str) -> str:
    if not isinstance(value, str):
        raise RedGoalContextProfileError(f"{subject} species reference is invalid")
    try:
        red_species_number(value)
        RED_ACQUISITION_CATALOG.method_for(value)
    except ValueError:
        raise RedGoalContextProfileError(
            f"{subject} species reference is outside Red's living collection contract"
        ) from None
    return value


def _safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise RedGoalContextProfileError(f"{subject} is invalid")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedGoalContextProfileError(f"{subject} must be a non-negative integer")
    return value


def _positive_integer(value: object, subject: str) -> int:
    result = _integer(value, subject)
    if result <= 0:
        raise RedGoalContextProfileError(f"{subject} must be positive")
    return result


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RedGoalContextProfileError(f"{subject} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise RedGoalContextProfileError("context profile fields differ")


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _document_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_line(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
