"""Deep frozen-plan authentication for claim-first Red setup execution.

The historical provider-plan record is deliberately path-free and omits live
runtime objects.  Before one slot is claimed, this module authenticates the
entire canonical producer plan and detaches the selected raw recipe from every
caller-owned mutable container.  After the durable pair and local claims, the
Red cold resolver rebuilds that one typed recipe and must match this exact raw
projection before the existing validator can receive controller authority.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA,
    RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA,
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupSlotRecipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA,
    RedLivingDexSetupExecutionIdentity,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PLAN_KEYS = {
    "claim_before_controller_input",
    "execution_identity",
    "execution_identity_sha256",
    "learner_effects",
    "prospective_plan_sha256",
    "recipes",
    "retry_after_controller_input",
    "same_origin_fork_required",
    "schema",
}
_RECIPE_KEYS = {
    "available_option_kinds",
    "base_boundary_sha256",
    "construction_route_sha256",
    "origin_boundary_sha256",
    "partition",
    "providers",
    "root_consumption_sha256",
    "root_envelope_sha256",
    "root_state_sha256",
    "schema",
    "slot_sha256",
}
_EXECUTION_KEYS = {
    "adapter_contract_id",
    "adapter_version_sha256",
    "game_id",
    "observation_schema_sha256",
    "provider_registry_sha256",
    "rom_sha1",
    "rom_sha256",
    "route_registry_sha256",
    "runtime_contract_sha256",
    "schema",
    "source_bundle_sha256",
    "source_commit",
    "source_published",
    "state_schema_sha256",
    "title",
    "worktree_dirty",
}


class RedLivingDexSetupAdmissionError(RuntimeError):
    """A frozen producer plan or postclaim typed recipe differs."""


@dataclass(frozen=True, slots=True)
class FrozenRedLivingDexSetupSlot:
    """Canonical whole-plan proof plus one detached selected recipe."""

    ordinal: int
    producer_plan_sha256: str
    producer_execution_identity_sha256: str
    recipe_sha256: str
    slot_sha256: str
    logical_root_sha256: str
    physical_root_sha256: str
    root_state_sha256: str
    root_envelope_sha256: str
    _plan_payload: bytes = field(repr=False)
    _recipe_payload: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or not 0 <= self.ordinal < 15:  # noqa: E721
            raise RedLivingDexSetupAdmissionError("frozen setup ordinal differs")
        for value, subject in (
            (self.producer_plan_sha256, "producer plan"),
            (self.producer_execution_identity_sha256, "producer execution identity"),
            (self.recipe_sha256, "recipe"),
            (self.slot_sha256, "slot"),
            (self.logical_root_sha256, "logical root"),
            (self.physical_root_sha256, "physical root"),
            (self.root_state_sha256, "root state"),
            (self.root_envelope_sha256, "root envelope"),
        ):
            _require_sha256(value, subject)
        if self.logical_root_sha256 == self.physical_root_sha256:
            raise RedLivingDexSetupAdmissionError("frozen setup root identities collapse")
        plan = _decode_canonical(self._plan_payload, "producer plan")
        recipe = _decode_canonical(self._recipe_payload, "recipe")
        if (
            canonical_sha256(plan) != self.producer_plan_sha256
            or canonical_sha256(recipe) != self.recipe_sha256
        ):
            raise RedLivingDexSetupAdmissionError("frozen setup payload digest differs")

    @property
    def plan_payload(self) -> bytes:
        return bytes(self._plan_payload)

    @property
    def recipe_payload(self) -> bytes:
        return bytes(self._recipe_payload)

    def recipe_document(self) -> dict[str, object]:
        """Return a fresh deep copy; no mutable object crosses the trust seam."""

        return _decode_canonical(self._recipe_payload, "recipe")

    def producer_execution_identity(self) -> RedLivingDexSetupExecutionIdentity:
        """Restore the exact typed producer identity from detached plan bytes."""

        plan = _decode_canonical(self._plan_payload, "producer plan")
        document = plan.get("execution_identity")
        if (
            not isinstance(document, dict)
            or set(document) != _EXECUTION_KEYS
            or document.get("schema")
            != RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA
            or canonical_sha256(document)
            != self.producer_execution_identity_sha256
        ):
            raise RedLivingDexSetupAdmissionError(
                "frozen setup producer execution identity differs"
            )
        try:
            identity = RedLivingDexSetupExecutionIdentity(
                source_commit=_string(document["source_commit"], "source commit"),
                source_bundle_sha256=_string(
                    document["source_bundle_sha256"],
                    "source bundle",
                ),
                adapter_version_sha256=_string(
                    document["adapter_version_sha256"],
                    "adapter version",
                ),
                state_schema_sha256=_string(
                    document["state_schema_sha256"],
                    "state schema",
                ),
                observation_schema_sha256=_string(
                    document["observation_schema_sha256"],
                    "observation schema",
                ),
                route_registry_sha256=_string(
                    document["route_registry_sha256"],
                    "route registry",
                ),
                provider_registry_sha256=_string(
                    document["provider_registry_sha256"],
                    "provider registry",
                ),
                runtime_contract_sha256=_string(
                    document["runtime_contract_sha256"],
                    "runtime contract",
                ),
                game_id=_string(document["game_id"], "game id"),
                title=_string(document["title"], "title"),
                rom_sha1=_string(document["rom_sha1"], "ROM SHA-1"),
                rom_sha256=_string(document["rom_sha256"], "ROM SHA-256"),
                source_published=document["source_published"],  # type: ignore[arg-type]
                worktree_dirty=document["worktree_dirty"],  # type: ignore[arg-type]
                adapter_contract_id=_string(
                    document["adapter_contract_id"],
                    "adapter contract",
                ),
            )
        except (TypeError, ValueError):
            raise RedLivingDexSetupAdmissionError(
                "frozen setup producer execution identity differs"
            ) from None
        if identity.private_dict() != document:
            raise RedLivingDexSetupAdmissionError(
                "frozen setup producer execution identity differs"
            )
        return identity

    def reauthenticate(
        self,
        plan_document: Mapping[str, object],
        *,
        root: RedLivingDexAuthenticatedSetupRoot,
    ) -> None:
        current = authenticate_frozen_red_living_dex_setup_slot(
            plan_document,
            expected_plan_sha256=self.producer_plan_sha256,
            ordinal=self.ordinal,
            root=root,
        )
        if current != self:
            raise RedLivingDexSetupAdmissionError("frozen setup plan changed after admission")

    def require_resolved_recipe(self, recipe: RedLivingDexSetupSlotRecipe) -> None:
        if not isinstance(recipe, RedLivingDexSetupSlotRecipe):
            raise TypeError("postclaim resolver must return a Red setup recipe")
        recipe.__post_init__()
        if (
            recipe.recipe_sha256 != self.recipe_sha256
            or recipe.slot_sha256 != self.slot_sha256
            or recipe.root_consumption_sha256 != self.logical_root_sha256
            or recipe.root_state_sha256 != self.root_state_sha256
            or recipe.root_envelope_sha256 != self.root_envelope_sha256
            or recipe.private_dict() != self.recipe_document()
        ):
            raise RedLivingDexSetupAdmissionError(
                "postclaim resolved recipe differs from the frozen producer recipe"
            )


def authenticate_frozen_red_living_dex_setup_slot(
    plan_document: Mapping[str, object],
    *,
    expected_plan_sha256: str,
    ordinal: int,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> FrozenRedLivingDexSetupSlot:
    """Authenticate the whole immutable plan and detach exactly one slot."""

    if not isinstance(plan_document, Mapping):
        raise TypeError("frozen setup admission needs a plan mapping")
    expected = _require_sha256(expected_plan_sha256, "expected producer plan")
    if type(ordinal) is not int or not 0 <= ordinal < 15:  # noqa: E721
        raise RedLivingDexSetupAdmissionError("frozen setup ordinal differs")
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("frozen setup admission needs an authenticated root")
    root.__post_init__()
    try:
        plan_payload = _canonical_payload(dict(plan_document))
        detached_plan = _decode_canonical(plan_payload, "producer plan")
    except (TypeError, ValueError, OverflowError):
        raise RedLivingDexSetupAdmissionError("frozen setup plan is not canonical JSON") from None
    if (
        set(detached_plan) != _PLAN_KEYS
        or detached_plan.get("schema") != RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA
        or canonical_sha256(detached_plan) != expected
        or detached_plan.get("claim_before_controller_input") is not True
        or detached_plan.get("retry_after_controller_input") is not False
        or detached_plan.get("same_origin_fork_required") is not True
        or detached_plan.get("learner_effects") != 0
    ):
        raise RedLivingDexSetupAdmissionError("frozen setup producer plan differs")
    execution = detached_plan.get("execution_identity")
    recipes = detached_plan.get("recipes")
    if (
        not isinstance(execution, dict)
        or canonical_sha256(execution) != detached_plan.get("execution_identity_sha256")
        or not isinstance(recipes, list)
        or len(recipes) != 15
        or any(not isinstance(item, dict) for item in recipes)
    ):
        raise RedLivingDexSetupAdmissionError("frozen setup producer inventory differs")
    recipe = recipes[ordinal]
    assert isinstance(recipe, dict)
    if (
        set(recipe) != _RECIPE_KEYS
        or recipe.get("schema") != RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA
        or recipe.get("root_consumption_sha256") != root.root_consumption_sha256
        or recipe.get("root_state_sha256") != root.state_sha256
        or recipe.get("root_envelope_sha256") != root.envelope_sha256
    ):
        raise RedLivingDexSetupAdmissionError("frozen setup selected recipe differs")
    recipe_payload = _canonical_payload(recipe)
    return FrozenRedLivingDexSetupSlot(
        ordinal=ordinal,
        producer_plan_sha256=expected,
        producer_execution_identity_sha256=_require_sha256(
            detached_plan["execution_identity_sha256"],
            "producer execution identity",
        ),
        recipe_sha256=canonical_sha256(recipe),
        slot_sha256=_require_sha256(recipe["slot_sha256"], "slot"),
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        root_state_sha256=root.state_sha256,
        root_envelope_sha256=root.envelope_sha256,
        _plan_payload=plan_payload,
        _recipe_payload=recipe_payload,
    )


def _canonical_payload(document: dict[str, object]) -> bytes:
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


def _decode_canonical(payload: bytes, subject: str) -> dict[str, object]:
    if not isinstance(payload, bytes) or not payload:
        raise RedLivingDexSetupAdmissionError(f"frozen setup {subject} payload is absent")
    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RedLivingDexSetupAdmissionError(
            f"frozen setup {subject} payload cannot be decoded"
        ) from None
    if not isinstance(document, dict) or _canonical_payload(document) != payload:
        raise RedLivingDexSetupAdmissionError(f"frozen setup {subject} is not canonical")
    return document


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexSetupAdmissionError(f"frozen setup {subject} digest differs")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexSetupAdmissionError(f"frozen setup {subject} differs")
    return value


__all__ = [
    "FrozenRedLivingDexSetupSlot",
    "RedLivingDexSetupAdmissionError",
    "authenticate_frozen_red_living_dex_setup_slot",
]
