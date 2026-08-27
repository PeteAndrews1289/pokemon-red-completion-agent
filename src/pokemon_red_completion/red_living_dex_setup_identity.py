"""Compose the exact published runtime identity for Red setup recipes.

The execution identity is deliberately path-free.  It binds the clean source
bundle, the installed emulator/runtime inventory, the state and observation
shapes consumed by the adapter, the committed navigation registry, and the
mechanics-derived provider registry.  Filesystem and publication checks remain
the responsibility of the CLI boundary that supplies the source identities.
"""

from __future__ import annotations

import re
from dataclasses import fields, is_dataclass
from typing import Any

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.collection import CollectionObservation, LivingSpecimen
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.goal_manager_context_catalog import GoalManagerContextCapture
from pokemon_red_completion.observation import (
    InputReadiness,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
    RedPokedexState,
)
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalObservation,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
    red_living_dex_setup_materialization_runtime_contract_ids,
    red_living_dex_setup_recipe_runtime_contract_ids,
    red_living_dex_setup_runtime_contract_ids,
    red_living_dex_setup_source_runtime_contract_ids,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
    RedLevelEvolutionTarget,
    RedPartyDevelopmentTarget,
    RedResupplyTarget,
    RedStorageTarget,
    RedStoryTarget,
    audit_red_living_dex_provider_curriculum,
    red_living_dex_provider_family_target,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    RedLivingDexProviderPlanFreeze,
    RedLivingDexProviderRootFacts,
    derive_red_living_dex_provider_corridors,
    freeze_red_living_dex_provider_plan,
    observe_red_living_dex_provider_root_facts,
    select_red_living_dex_provider_roots,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.red_living_dex_setup_recipe_campaign import (
    run_red_living_dex_setup_recipe_campaign,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
)
from pokemon_red_completion.red_player_observer import CapturedPokemonRedObserver
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    is_runtime_identity_public_document,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

RED_LIVING_DEX_SETUP_ADAPTER_VERSION_SCHEMA = (
    "pokemon.red.living-dex-setup-adapter-version.v1"
)
RED_LIVING_DEX_SETUP_STATE_SCHEMA = "pokemon.red.living-dex-setup-state-schema.v1"
RED_LIVING_DEX_SETUP_OBSERVATION_SCHEMA = (
    "pokemon.red.living-dex-setup-observation-schema.v1"
)
RED_LIVING_DEX_PROVIDER_REGISTRY_SCHEMA = (
    "pokemon.red.living-dex-provider-registry.v1"
)
RED_LIVING_DEX_SETUP_RUNTIME_CONTRACT_SCHEMA = (
    "pokemon.red.living-dex-setup-runtime-contract.v1"
)

_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexSetupIdentityError(ValueError):
    """The supplied clean-source/runtime identity cannot be composed."""


def compose_red_living_dex_setup_execution_identity(
    *,
    source_commit: str,
    source_bundle_sha256: str,
    route_registry_sha256: str,
    runtime_identity: RuntimeIdentity,
) -> RedLivingDexSetupExecutionIdentity:
    """Build one exact, path-free identity from authenticated public inputs."""

    if not isinstance(source_commit, str) or _SHA1.fullmatch(source_commit) is None:
        raise RedLivingDexSetupIdentityError("setup identity source commit differs")
    _require_sha256(source_bundle_sha256, "source bundle")
    _require_sha256(route_registry_sha256, "route registry")
    if not isinstance(runtime_identity, RuntimeIdentity):
        raise TypeError("setup identity needs a RuntimeIdentity")
    runtime_document = runtime_identity.public_dict()
    if not is_runtime_identity_public_document(runtime_document):
        raise RedLivingDexSetupIdentityError("setup identity runtime differs")
    runtime_sha256 = runtime_identity.sha256

    adapter_version_sha256 = canonical_sha256(
        {
            "adapter_contract_id": "pokemon.red.living-dex-setup-adapter.v2",
            "adapter_type": _contract_id(PyBoyAdapter),
            "game_id": "pokemon-red",
            "rom_sha256": POKEMON_RED_US_REV_0.sha256,
            "runtime_identity_sha256": runtime_sha256,
            "schema": RED_LIVING_DEX_SETUP_ADAPTER_VERSION_SCHEMA,
            "source_bundle_sha256": source_bundle_sha256,
        }
    )
    state_schema_sha256 = canonical_sha256(
        {
            "capture_envelope_schema": "pokemon-private-captured-progress-v1",
            "dataclasses": _dataclass_schemas(
                CapturedProgressEnvelope,
                GoalManagerContextCapture,
            ),
            "emulator_state_runtime_sha256": runtime_sha256,
            "rom_sha256": POKEMON_RED_US_REV_0.sha256,
            "schema": RED_LIVING_DEX_SETUP_STATE_SCHEMA,
        }
    )
    observation_schema_sha256 = canonical_sha256(
        {
            "dataclasses": _dataclass_schemas(
                RawGameState,
                InputReadiness,
                RedPokedexState,
                RedCurrentBoxState,
                RedBoxCollectionState,
                PartyMemberObservation,
                PartyObservation,
                LivingSpecimen,
                CollectionObservation,
                RedGoalObservation,
                TraversalSnapshot,
                RedLivingDexProviderRootFacts,
                RedLivingDexActionFreeRootObservation,
            ),
            "schema": RED_LIVING_DEX_SETUP_OBSERVATION_SCHEMA,
        }
    )
    provider_registry_sha256 = red_living_dex_provider_registry_sha256()
    runtime_contract_sha256 = canonical_sha256(
        {
            "contract_ids": list(_runtime_contract_ids()),
            "runtime": runtime_document,
            "schema": RED_LIVING_DEX_SETUP_RUNTIME_CONTRACT_SCHEMA,
        }
    )
    return RedLivingDexSetupExecutionIdentity(
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        adapter_version_sha256=adapter_version_sha256,
        state_schema_sha256=state_schema_sha256,
        observation_schema_sha256=observation_schema_sha256,
        route_registry_sha256=route_registry_sha256,
        provider_registry_sha256=provider_registry_sha256,
        runtime_contract_sha256=runtime_contract_sha256,
    )


def red_living_dex_provider_registry_sha256() -> str:
    """Hash every mechanics-derived target in the frozen prospective order."""

    plan = build_red_living_dex_prospective_capture_plan()
    rows = []
    for slot in plan.slots:
        for option_kind in slot.available_option_kinds:
            target = red_living_dex_provider_family_target(slot, option_kind)
            rows.append(
                {
                    "family_scope_id": slot.family_scope_id,
                    "option_kind": option_kind.value,
                    "parameters": _target_parameters(target),
                    "target_contract_id": _contract_id(type(target)),
                }
            )
    return canonical_sha256(
        {
            "audit": audit_red_living_dex_provider_curriculum().public_dict(),
            "prospective_plan_sha256": plan.plan_sha256,
            "rows": rows,
            "schema": RED_LIVING_DEX_PROVIDER_REGISTRY_SCHEMA,
        }
    )


def _target_parameters(
    target: (
        RedEncounterSourceTarget
        | RedLevelEvolutionTarget
        | RedPartyDevelopmentTarget
        | RedResupplyTarget
        | RedStorageTarget
        | RedStoryTarget
    ),
) -> dict[str, object]:
    if isinstance(target, (RedLevelEvolutionTarget, RedPartyDevelopmentTarget)):
        return target.parameters()
    return target.family_parameters()


def _runtime_contract_ids() -> tuple[str, ...]:
    local = (
        build_red_goal_context_runtime,
        PokemonRedGoalStateAdapter,
        CapturedPokemonRedObserver,
        StrategicScenarioRouteWorld.from_rom,
        derive_red_living_dex_provider_corridors,
        observe_red_living_dex_provider_root_facts,
        select_red_living_dex_provider_roots,
        freeze_red_living_dex_provider_plan,
        validate_red_living_dex_setup_recipe,
        run_red_living_dex_setup_recipe_campaign,
        RedLivingDexAuthenticatedSetupRoot,
        RedLivingDexProviderPlanFreeze,
    )
    return tuple(
        sorted(
            {
                *(_contract_id(item) for item in local),
                *red_living_dex_setup_runtime_contract_ids(),
                *red_living_dex_setup_materialization_runtime_contract_ids(),
                *red_living_dex_setup_source_runtime_contract_ids(),
                *red_living_dex_setup_recipe_runtime_contract_ids(),
            }
        )
    )


def _dataclass_schemas(*types: type[object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for type_ in types:
        if not is_dataclass(type_):
            raise RedLivingDexSetupIdentityError("setup identity schema type differs")
        result.append(
            {
                "contract_id": _contract_id(type_),
                "fields": [field.name for field in fields(type_)],
            }
        )
    return result


def _contract_id(value: Any) -> str:
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    if not isinstance(module, str) or not module or not isinstance(qualname, str) or not qualname:
        raise RedLivingDexSetupIdentityError("setup identity contract provenance differs")
    return f"{module}.{qualname}"


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexSetupIdentityError(f"setup identity {subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_PROVIDER_REGISTRY_SCHEMA",
    "RED_LIVING_DEX_SETUP_ADAPTER_VERSION_SCHEMA",
    "RED_LIVING_DEX_SETUP_OBSERVATION_SCHEMA",
    "RED_LIVING_DEX_SETUP_RUNTIME_CONTRACT_SCHEMA",
    "RED_LIVING_DEX_SETUP_STATE_SCHEMA",
    "RedLivingDexSetupIdentityError",
    "compose_red_living_dex_setup_execution_identity",
    "red_living_dex_provider_registry_sha256",
]
