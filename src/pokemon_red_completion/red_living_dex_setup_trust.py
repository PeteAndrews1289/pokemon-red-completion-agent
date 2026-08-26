"""Closed trust primitives for authentic Red same-root setup collection.

These values are deliberately independent of filesystem paths and candidate
ordering.  They bind the exact cartridge/runtime that may execute a setup
campaign, meter every authority that must remain dormant during validation,
and describe the semantic transformation offered by a real provider without
using a slot, root, profile, route, or candidate identity as a family label.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    RedGoalProviderSpec,
)

RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA = (
    "pokemon.red.private-living-dex-setup-execution-identity.v2"
)
RED_LIVING_DEX_TRANSFORMATION_FAMILY_SCHEMA = (
    "pokemon.core.private-living-dex-transformation-family.v2"
)
RED_LIVING_DEX_SETUP_PROTECTED_EFFECT_SCHEMA = (
    "pokemon.core.private-living-dex-setup-protected-effects.v2"
)

_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class RedLivingDexSetupTrustError(RuntimeError):
    """An execution identity, family, or protected counter is invalid."""


class RedLivingDexSetupFailureReason(StrEnum):
    """Closed private failure vocabulary; values are safe for aggregation."""

    ARTIFACT_INTEGRITY_FAILED = "artifact_integrity_failed"
    PROCESS_INTERRUPTED = "process_interrupted"
    RECIPE_EXECUTION_FAILED = "recipe_execution_failed"
    ROOT_ALREADY_CONSUMED = "root_already_consumed"
    ROOT_UNAVAILABLE = "root_unavailable"
    SETUP_BUDGET_EXHAUSTED = "setup_budget_exhausted"


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupExecutionIdentity:
    """Exact published Red adapter/runtime identity for one frozen campaign."""

    source_commit: str
    source_bundle_sha256: str
    adapter_version_sha256: str
    state_schema_sha256: str
    observation_schema_sha256: str
    route_registry_sha256: str
    provider_registry_sha256: str
    runtime_contract_sha256: str
    game_id: str = "pokemon-red"
    title: str = POKEMON_RED_US_REV_0.title
    rom_sha1: str = POKEMON_RED_US_REV_0.sha1
    rom_sha256: str = POKEMON_RED_US_REV_0.sha256
    source_published: bool = True
    worktree_dirty: bool = False
    adapter_contract_id: str = "pokemon.red.living-dex-setup-adapter.v2"

    def __post_init__(self) -> None:
        if self.game_id != "pokemon-red" or self.title != POKEMON_RED_US_REV_0.title:
            raise RedLivingDexSetupTrustError("setup execution title differs from Red")
        if self.rom_sha1 != POKEMON_RED_US_REV_0.sha1 or not _SHA1.fullmatch(self.rom_sha1):
            raise RedLivingDexSetupTrustError("setup execution ROM SHA-1 differs")
        if self.rom_sha256 != POKEMON_RED_US_REV_0.sha256:
            raise RedLivingDexSetupTrustError("setup execution ROM SHA-256 differs")
        if not _SHA1.fullmatch(self.source_commit):
            raise RedLivingDexSetupTrustError("setup execution source commit differs")
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.adapter_version_sha256, "adapter version"),
            (self.state_schema_sha256, "state schema"),
            (self.observation_schema_sha256, "observation schema"),
            (self.route_registry_sha256, "route registry"),
            (self.provider_registry_sha256, "provider registry"),
            (self.runtime_contract_sha256, "runtime contract"),
        ):
            _require_sha256(value, f"setup execution {subject}")
        if self.source_published is not True or self.worktree_dirty is not False:
            raise RedLivingDexSetupTrustError("setup execution must use a published clean source")
        if self.adapter_contract_id != "pokemon.red.living-dex-setup-adapter.v2":
            raise RedLivingDexSetupTrustError("setup adapter contract differs")

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "adapter_contract_id": self.adapter_contract_id,
            "adapter_version_sha256": self.adapter_version_sha256,
            "game_id": self.game_id,
            "observation_schema_sha256": self.observation_schema_sha256,
            "provider_registry_sha256": self.provider_registry_sha256,
            "rom_sha1": self.rom_sha1,
            "rom_sha256": self.rom_sha256,
            "route_registry_sha256": self.route_registry_sha256,
            "runtime_contract_sha256": self.runtime_contract_sha256,
            "schema": RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "source_published": self.source_published,
            "state_schema_sha256": self.state_schema_sha256,
            "title": self.title,
            "worktree_dirty": self.worktree_dirty,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "adapter_contract_bound": True,
            "clean_published_source_required": True,
            "exact_red_revision_bound": True,
            "execution_identity_bound": True,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "schema": RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupProtectedEffectCheckpoint:
    """Monotonic census of every authority visible to setup validation."""

    controller_actions: int = 0
    emulator_frames: int = 0
    behavior_draws: int = 0
    learner_labels: int = 0
    learner_outcomes: int = 0
    model_predictions: int = 0
    model_fits: int = 0
    provider_executions: int = 0
    teacher_queries: int = 0
    root_claims: int = 0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise RedLivingDexSetupTrustError(f"setup protected effect {name} differs")

    def private_dict(self) -> dict[str, object]:
        return {
            **{name: getattr(self, name) for name in self.__dataclass_fields__},
            "schema": RED_LIVING_DEX_SETUP_PROTECTED_EFFECT_SCHEMA,
        }

    def action_frame_delta(
        self,
        after: RedLivingDexSetupProtectedEffectCheckpoint,
    ) -> tuple[int, int]:
        if not isinstance(after, RedLivingDexSetupProtectedEffectCheckpoint):
            raise TypeError("setup effect delta needs a protected checkpoint")
        deltas = {
            name: getattr(after, name) - getattr(self, name) for name in self.__dataclass_fields__
        }
        if any(value < 0 for value in deltas.values()):
            raise RedLivingDexSetupTrustError("setup effect counters moved backwards")
        forbidden = {
            name: value
            for name, value in deltas.items()
            if name not in {"controller_actions", "emulator_frames"} and value
        }
        if forbidden:
            raise RedLivingDexSetupTrustError("setup crossed a protected authority")
        return deltas["controller_actions"], deltas["emulator_frames"]


class RedLivingDexSetupEffectMeter:
    """Single executor-owned counter authority for a setup campaign.

    Callers may connect subsystems to the narrow recording methods, but they
    cannot substitute an object that merely reports self-attested zeroes.  The
    validator and durable campaign require this exact concrete type and every
    isolated arm must share this exact instance.
    """

    __slots__ = ("_counts",)

    def __init__(self) -> None:
        self._counts = {
            name: 0 for name in RedLivingDexSetupProtectedEffectCheckpoint.__dataclass_fields__
        }

    def checkpoint(self) -> RedLivingDexSetupProtectedEffectCheckpoint:
        return RedLivingDexSetupProtectedEffectCheckpoint(**self._counts)

    @property
    def controller_actions(self) -> int:
        return self._counts["controller_actions"]

    @property
    def emulator_frames(self) -> int:
        return self._counts["emulator_frames"]

    @property
    def provider_executions(self) -> int:
        return self._counts["provider_executions"]

    @property
    def root_claims(self) -> int:
        return self._counts["root_claims"]

    def record_controller_actions(self, count: int = 1) -> None:
        self._record("controller_actions", count)

    def record_emulator_frames(self, count: int) -> None:
        self._record("emulator_frames", count)

    def record_behavior_draw(self) -> None:
        self._record("behavior_draws", 1)

    def record_learner_label(self) -> None:
        self._record("learner_labels", 1)

    def record_learner_outcome(self) -> None:
        self._record("learner_outcomes", 1)

    def record_model_prediction(self) -> None:
        self._record("model_predictions", 1)

    def record_model_fit(self) -> None:
        self._record("model_fits", 1)

    def record_provider_execution(self) -> None:
        self._record("provider_executions", 1)

    def record_teacher_query(self) -> None:
        self._record("teacher_queries", 1)

    def record_root_claim(self) -> None:
        self._record("root_claims", 1)

    def _record(self, name: str, count: int) -> None:
        if type(count) is not int or count <= 0:  # noqa: E721
            raise RedLivingDexSetupTrustError("protected effect increment differs")
        self._counts[name] += count


@dataclass(frozen=True, slots=True)
class RedLivingDexTransformationFamily:
    """Typed, order-free semantic transformation expected from one provider."""

    option_kind: LivingDexOptionKind
    goal_kind: GoalKind
    mechanic: RedGoalMechanic
    semantic_parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.option_kind, LivingDexOptionKind):
            raise RedLivingDexSetupTrustError("transformation option kind differs")
        if not isinstance(self.goal_kind, GoalKind) or not isinstance(
            self.mechanic, RedGoalMechanic
        ):
            raise RedLivingDexSetupTrustError("transformation mechanic differs")
        if not isinstance(self.semantic_parameters, Mapping) or any(
            not isinstance(key, str) for key in self.semantic_parameters
        ):
            raise RedLivingDexSetupTrustError("transformation parameters differ")
        normalized = _normalize_family_parameters(
            self.option_kind,
            self.goal_kind,
            self.mechanic,
            self.semantic_parameters,
        )
        object.__setattr__(self, "semantic_parameters", MappingProxyType(normalized))

    @property
    def family_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "goal_kind": self.goal_kind.value,
            "mechanic": self.mechanic.value,
            "option_kind": self.option_kind.value,
            "schema": RED_LIVING_DEX_TRANSFORMATION_FAMILY_SCHEMA,
            "semantic_parameters": dict(self.semantic_parameters),
        }


def build_red_living_dex_transformation_family(
    *,
    option_kind: LivingDexOptionKind,
    profile: RedGoalContextProfile,
    story_objective_id: str | None = None,
) -> RedLivingDexTransformationFamily:
    """Derive the only allowed family projection from a validated profile."""

    if not isinstance(profile, RedGoalContextProfile):
        raise TypeError("transformation family needs a Red context profile")
    goal_kind = _goal_kind(option_kind)
    specs = tuple(item for item in profile.providers if item.kind is goal_kind)
    if len(specs) != 1:
        raise RedLivingDexSetupTrustError("transformation family lacks one matching provider")
    spec = specs[0]
    parameters = _project_semantic_parameters(spec, story_objective_id)
    return RedLivingDexTransformationFamily(
        option_kind,
        goal_kind,
        spec.mechanic,
        parameters,
    )


def expected_red_living_dex_binding_core(
    family: RedLivingDexTransformationFamily,
) -> str:
    """Return the exact pre-profile binding identity for a typed family."""

    family.__post_init__()
    values = family.semantic_parameters
    mechanic = family.mechanic
    if mechanic is RedGoalMechanic.MIDGAME_STORY:
        return f"pokemon.red:story:{values['objective_id']}"
    if mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
        return f"pokemon.red:acquisition:{values['source_id']}"
    if mechanic is RedGoalMechanic.WILD_CORRIDOR_DISCOVERY:
        return f"pokemon.red:explore:{values['source_id']}"
    if mechanic is RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT:
        return f"pokemon.red:development:{values['source_id']}"
    if mechanic is RedGoalMechanic.BALANCED_TEAM:
        return "pokemon.red:development:one-level-quantum"
    if mechanic is RedGoalMechanic.DIGLETT_EVOLUTION:
        return f"pokemon.red:evolution:{values['source']}-to-{values['target']}"
    if mechanic is RedGoalMechanic.BOX_SWITCH:
        target_box_index = values["target_box_index"]
        assert type(target_box_index) is int  # noqa: E721
        return f"pokemon.red:storage:switch-box-{target_box_index + 1}"
    if mechanic is RedGoalMechanic.MART_RESUPPLY:
        purchases = values["purchases"]
        assert isinstance(purchases, tuple)
        purchase_ref = "-".join(
            f"{int(item['item_id']):02x}x{int(item['quantity'])}" for item in purchases
        )
        # The executable provider includes its actual Mart map in the private
        # binding.  The map is route/provider provenance, not family identity.
        return f"pokemon.red:resupply:mart-*{purchase_ref}"
    raise RedLivingDexSetupTrustError("transformation mechanic is unsupported")


def red_living_dex_binding_matches_family(
    binding_ref: str,
    family: RedLivingDexTransformationFamily,
    profile: RedGoalContextProfile,
) -> bool:
    """Join a registry-built binding to the typed semantic family exactly."""

    if not isinstance(binding_ref, str):
        return False
    suffix = f":profile-{profile.profile_sha256}:config-"
    if suffix not in binding_ref:
        return False
    core, configuration = binding_ref.rsplit(suffix, 1)
    spec = next((item for item in profile.providers if item.kind is family.goal_kind), None)
    if spec is None or configuration != spec.configuration_sha256:
        return False
    expected = expected_red_living_dex_binding_core(family)
    if family.mechanic is RedGoalMechanic.MART_RESUPPLY:
        prefix, purchase_ref = expected.split("*", 1)
        return core.startswith(prefix) and core.endswith(purchase_ref)
    return core == expected


def _project_semantic_parameters(
    spec: RedGoalProviderSpec,
    story_objective_id: str | None,
) -> dict[str, object]:
    parameters = spec.parameters
    mechanic = spec.mechanic
    if mechanic is RedGoalMechanic.MIDGAME_STORY:
        if not isinstance(story_objective_id, str) or not _SAFE_ID.fullmatch(story_objective_id):
            raise RedLivingDexSetupTrustError("story transformation needs a frozen objective")
        return {"objective_id": story_objective_id}
    if story_objective_id is not None:
        raise RedLivingDexSetupTrustError("non-story transformation cannot carry a story objective")
    if mechanic in {
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
        RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
    }:
        return {"source_id": _safe_parameter(parameters, "source_id")}
    if mechanic is RedGoalMechanic.BALANCED_TEAM:
        return {"dose": "one-level-quantum"}
    if mechanic is RedGoalMechanic.DIGLETT_EVOLUTION:
        return {"source": "diglett", "target": "dugtrio"}
    if mechanic is RedGoalMechanic.BOX_SWITCH:
        return {"target_box_index": _integer_parameter(parameters, "target_box_index")}
    if mechanic is RedGoalMechanic.MART_RESUPPLY:
        raw = parameters.get("purchases")
        if not isinstance(raw, tuple) or not raw:
            raise RedLivingDexSetupTrustError("resupply family purchases differ")
        rows: list[dict[str, int]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise RedLivingDexSetupTrustError("resupply family purchase differs")
            rows.append(
                {
                    "item_id": _integer_parameter(item, "item_id"),
                    "quantity": _positive_parameter(item, "quantity"),
                }
            )
        return {"purchases": tuple(rows)}
    raise RedLivingDexSetupTrustError("provider mechanic cannot form a setup family")


def _normalize_family_parameters(
    option_kind: LivingDexOptionKind,
    goal_kind: GoalKind,
    mechanic: RedGoalMechanic,
    values: Mapping[str, object],
) -> dict[str, object]:
    expected_goal = _goal_kind(option_kind)
    if goal_kind is not expected_goal:
        raise RedLivingDexSetupTrustError("transformation goal mapping differs")
    expected_mechanics = {
        LivingDexOptionKind.ACQUIRE: {RedGoalMechanic.WILD_CORRIDOR_CAPTURE},
        LivingDexOptionKind.EVOLVE: {RedGoalMechanic.DIGLETT_EVOLUTION},
        LivingDexOptionKind.DEVELOP: {
            RedGoalMechanic.BALANCED_TEAM,
            RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
        },
        LivingDexOptionKind.MANAGE_STORAGE: {RedGoalMechanic.BOX_SWITCH},
        LivingDexOptionKind.RESUPPLY: {RedGoalMechanic.MART_RESUPPLY},
        LivingDexOptionKind.UNLOCK_ACCESS: {RedGoalMechanic.MIDGAME_STORY},
        LivingDexOptionKind.EXPLORE: {RedGoalMechanic.WILD_CORRIDOR_DISCOVERY},
    }
    if mechanic not in expected_mechanics[option_kind]:
        raise RedLivingDexSetupTrustError("transformation option mechanic differs")
    expected_keys = {
        RedGoalMechanic.MIDGAME_STORY: {"objective_id"},
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE: {"source_id"},
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY: {"source_id"},
        RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT: {"source_id"},
        RedGoalMechanic.BALANCED_TEAM: {"dose"},
        RedGoalMechanic.DIGLETT_EVOLUTION: {"source", "target"},
        RedGoalMechanic.BOX_SWITCH: {"target_box_index"},
        RedGoalMechanic.MART_RESUPPLY: {"purchases"},
    }[mechanic]
    if set(values) != expected_keys:
        raise RedLivingDexSetupTrustError("transformation parameter fields differ")
    if mechanic is RedGoalMechanic.MIDGAME_STORY:
        _safe_value(values["objective_id"], "story objective")
    elif mechanic in {
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
        RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT,
    }:
        _safe_value(values["source_id"], "encounter source")
    elif mechanic is RedGoalMechanic.BALANCED_TEAM:
        if values["dose"] != "one-level-quantum":
            raise RedLivingDexSetupTrustError("team-development dose differs")
    elif mechanic is RedGoalMechanic.DIGLETT_EVOLUTION:
        source = _safe_value(values["source"], "evolution source")
        target = _safe_value(values["target"], "evolution target")
        if source == target:
            raise RedLivingDexSetupTrustError("evolution family differs")
    elif mechanic is RedGoalMechanic.BOX_SWITCH:
        if (
            type(values["target_box_index"]) is not int
            or not 0
            <= int(  # noqa: E721
                values["target_box_index"]
            )
            < 12
        ):
            raise RedLivingDexSetupTrustError("storage family target differs")
    else:
        purchases = values["purchases"]
        if not isinstance(purchases, tuple) or not purchases:
            raise RedLivingDexSetupTrustError("resupply family purchases differ")
        for item in purchases:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"item_id", "quantity"}
                or type(item["item_id"]) is not int  # noqa: E721
                or not 0 <= int(item["item_id"]) <= 255
                or type(item["quantity"]) is not int  # noqa: E721
                or int(item["quantity"]) <= 0
            ):
                raise RedLivingDexSetupTrustError("resupply family purchase differs")
    return dict(values)


def _goal_kind(option_kind: LivingDexOptionKind) -> GoalKind:
    mapping = {
        LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
        LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
        LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
        LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
        LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
        LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
    }
    try:
        return mapping[option_kind]
    except KeyError:
        raise RedLivingDexSetupTrustError("transformation option kind differs") from None


def _safe_parameter(values: Mapping[str, object], key: str) -> str:
    return _safe_value(values.get(key), key)


def _safe_value(value: object, subject: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise RedLivingDexSetupTrustError(f"{subject} differs")
    return value


def _integer_parameter(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexSetupTrustError(f"{key} differs")
    return value


def _positive_parameter(values: Mapping[str, object], key: str) -> int:
    value = _integer_parameter(values, key)
    if value <= 0:
        raise RedLivingDexSetupTrustError(f"{key} differs")
    return value


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RedLivingDexSetupTrustError(f"{subject} digest differs")
    return value


__all__ = [
    "RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA",
    "RED_LIVING_DEX_SETUP_PROTECTED_EFFECT_SCHEMA",
    "RED_LIVING_DEX_TRANSFORMATION_FAMILY_SCHEMA",
    "RedLivingDexSetupExecutionIdentity",
    "RedLivingDexSetupEffectMeter",
    "RedLivingDexSetupFailureReason",
    "RedLivingDexSetupProtectedEffectCheckpoint",
    "RedLivingDexSetupTrustError",
    "RedLivingDexTransformationFamily",
    "build_red_living_dex_transformation_family",
    "expected_red_living_dex_binding_core",
    "red_living_dex_binding_matches_family",
]
