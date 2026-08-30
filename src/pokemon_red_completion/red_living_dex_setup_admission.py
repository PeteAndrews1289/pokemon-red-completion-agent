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
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA,
    validate_red_living_dex_clustered_private_plan,
)
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
    template_ordinal: int
    producer_plan_sha256: str
    producer_execution_identity_sha256: str
    producer_plan_schema: str
    producer_runtime_identity_sha256: str | None
    recipe_sha256: str
    slot_sha256: str
    logical_root_sha256: str
    physical_root_sha256: str
    root_state_sha256: str
    root_envelope_sha256: str
    _plan_payload: bytes = field(repr=False)
    _recipe_payload: bytes = field(repr=False)
    _producer_execution_payload: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:  # noqa: E721
            raise RedLivingDexSetupAdmissionError("frozen setup ordinal differs")
        if (
            type(self.template_ordinal) is not int  # noqa: E721
            or not 0 <= self.template_ordinal < 15
        ):
            raise RedLivingDexSetupAdmissionError(
                "frozen setup template ordinal differs"
            )
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
        execution = _decode_canonical(
            self._producer_execution_payload,
            "producer execution identity",
        )
        if self.producer_plan_schema not in {
            RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA,
            RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA,
        }:
            raise RedLivingDexSetupAdmissionError(
                "frozen setup producer schema differs"
            )
        if plan.get("schema") != self.producer_plan_schema:
            raise RedLivingDexSetupAdmissionError(
                "frozen setup producer schema differs"
            )
        plan_commitment: object
        if self.producer_plan_schema == RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA:
            plan_commitment = canonical_sha256(plan)
            if (
                self.ordinal >= 15
                or self.producer_runtime_identity_sha256 is not None
            ):
                raise RedLivingDexSetupAdmissionError(
                    "legacy frozen setup bounds or runtime identity differ"
                )
        else:
            payload = {
                key: value
                for key, value in plan.items()
                if key != "private_plan_sha256"
            }
            plan_commitment = plan.get("private_plan_sha256")
            if (
                plan_commitment != canonical_sha256(payload)
                or not isinstance(self.producer_runtime_identity_sha256, str)
            ):
                raise RedLivingDexSetupAdmissionError(
                    "clustered frozen setup plan commitment differs"
                )
            _require_sha256(
                self.producer_runtime_identity_sha256,
                "producer runtime identity",
            )
            try:
                clustered_schedule = (
                    validate_red_living_dex_clustered_private_plan(plan)
                )
            except (TypeError, ValueError):
                raise RedLivingDexSetupAdmissionError(
                    "clustered frozen setup schedule differs"
                ) from None
            if self.ordinal >= clustered_schedule.policy.train_scenarios:
                raise RedLivingDexSetupAdmissionError(
                    "clustered frozen setup selected a non-train ordinal"
                )
        if (
            plan_commitment != self.producer_plan_sha256
            or canonical_sha256(recipe) != self.recipe_sha256
            or canonical_sha256(execution)
            != self.producer_execution_identity_sha256
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

        document = _decode_canonical(
            self._producer_execution_payload,
            "producer execution identity",
        )
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
        if self.producer_plan_schema == RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA:
            current = authenticate_frozen_red_living_dex_setup_slot(
                plan_document,
                expected_plan_sha256=self.producer_plan_sha256,
                ordinal=self.ordinal,
                root=root,
            )
        else:
            current = authenticate_frozen_red_living_dex_clustered_train_slot(
                plan_document,
                expected_private_plan_sha256=self.producer_plan_sha256,
                ordinal=self.ordinal,
                root=root,
                producer_execution_identity=self.producer_execution_identity(),
                expected_runtime_identity_sha256=self.producer_runtime_identity_sha256,
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
            or _canonical_payload(recipe.private_dict()) != self._recipe_payload
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
        template_ordinal=ordinal,
        producer_plan_sha256=expected,
        producer_execution_identity_sha256=_require_sha256(
            detached_plan["execution_identity_sha256"],
            "producer execution identity",
        ),
        producer_plan_schema=RED_LIVING_DEX_SETUP_RECIPE_PLAN_SCHEMA,
        producer_runtime_identity_sha256=None,
        recipe_sha256=canonical_sha256(recipe),
        slot_sha256=_require_sha256(recipe["slot_sha256"], "slot"),
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        root_state_sha256=root.state_sha256,
        root_envelope_sha256=root.envelope_sha256,
        _plan_payload=plan_payload,
        _recipe_payload=recipe_payload,
        _producer_execution_payload=_canonical_payload(execution),
    )


def authenticate_frozen_red_living_dex_clustered_train_slot(
    plan_document: Mapping[str, object],
    *,
    expected_private_plan_sha256: str,
    ordinal: int,
    root: RedLivingDexAuthenticatedSetupRoot,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity,
    expected_runtime_identity_sha256: str | None,
) -> FrozenRedLivingDexSetupSlot:
    """Detach one train assignment from the immutable clustered schedule.

    The schedule ordinal and Red template ordinal are intentionally distinct.
    Only the policy-declared leading train rows are addressable, and the
    selected row must independently attest that it belongs to that partition.
    """

    if not isinstance(plan_document, Mapping):
        raise TypeError("clustered setup admission needs a plan mapping")
    expected = _require_sha256(
        expected_private_plan_sha256,
        "expected clustered private plan",
    )
    if type(ordinal) is not int or ordinal < 0:  # noqa: E721
        raise RedLivingDexSetupAdmissionError(
            "clustered setup selected a non-train ordinal"
        )
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("clustered setup admission needs an authenticated root")
    root.__post_init__()
    if not isinstance(
        producer_execution_identity,
        RedLivingDexSetupExecutionIdentity,
    ):
        raise TypeError("clustered setup admission needs its producer identity")
    producer_execution_identity.__post_init__()
    runtime_identity = _require_sha256(
        expected_runtime_identity_sha256,
        "expected producer runtime identity",
    )
    try:
        plan_payload = _canonical_payload(dict(plan_document))
        detached_plan = _decode_canonical(plan_payload, "clustered producer plan")
    except (TypeError, ValueError, OverflowError):
        raise RedLivingDexSetupAdmissionError(
            "clustered setup plan is not canonical JSON"
        ) from None
    try:
        clustered_schedule = validate_red_living_dex_clustered_private_plan(
            detached_plan
        )
    except (TypeError, ValueError):
        raise RedLivingDexSetupAdmissionError(
            "clustered setup producer plan differs"
        ) from None
    payload = {
        key: value
        for key, value in detached_plan.items()
        if key != "private_plan_sha256"
    }
    assignments = detached_plan.get("assignments")
    train_scenarios = clustered_schedule.policy.train_scenarios
    total_scenarios = (
        train_scenarios + clustered_schedule.policy.development_scenarios
    )
    if (
        ordinal >= train_scenarios
        or detached_plan.get("private_plan_sha256") != expected
        or canonical_sha256(payload) != expected
        or detached_plan.get("source_commit")
        != producer_execution_identity.source_commit
        or detached_plan.get("source_bundle_sha256")
        != producer_execution_identity.source_bundle_sha256
        or detached_plan.get("route_registry_sha256")
        != producer_execution_identity.route_registry_sha256
        or detached_plan.get("rom_sha256") != producer_execution_identity.rom_sha256
        or detached_plan.get("runtime_identity_sha256") != runtime_identity
        or not isinstance(assignments, list)
        or len(assignments) != total_scenarios
    ):
        raise RedLivingDexSetupAdmissionError(
            "clustered setup producer binding differs"
        )
    selected = assignments[ordinal]
    if not isinstance(selected, dict):
        raise RedLivingDexSetupAdmissionError(
            "clustered setup selected assignment differs"
        )
    recipe = selected.get("recipe")
    template_ordinal = selected.get("template_ordinal")
    if (
        selected.get("ordinal") != ordinal
        or selected.get("partition") != "train"
        or type(template_ordinal) is not int  # noqa: E721
        or not 0 <= template_ordinal < 15
        or not isinstance(recipe, dict)
        or recipe.get("schema") != RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA
        or canonical_sha256(recipe) != selected.get("recipe_sha256")
        or recipe.get("partition") != "train"
        or recipe.get("root_consumption_sha256")
        != root.root_consumption_sha256
        or recipe.get("root_state_sha256") != root.state_sha256
        or recipe.get("root_envelope_sha256") != root.envelope_sha256
        or selected.get("physical_root_sha256")
        != root.physical_root_sha256
    ):
        raise RedLivingDexSetupAdmissionError(
            "clustered setup selected recipe differs"
        )
    execution_payload = _canonical_payload(
        producer_execution_identity.private_dict()
    )
    return FrozenRedLivingDexSetupSlot(
        ordinal=ordinal,
        template_ordinal=template_ordinal,
        producer_plan_sha256=expected,
        producer_execution_identity_sha256=(
            producer_execution_identity.identity_sha256
        ),
        producer_plan_schema=RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA,
        producer_runtime_identity_sha256=runtime_identity,
        recipe_sha256=_require_sha256(
            selected.get("recipe_sha256"),
            "clustered recipe",
        ),
        slot_sha256=_require_sha256(
            selected.get("template_sha256"),
            "clustered template",
        ),
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        root_state_sha256=root.state_sha256,
        root_envelope_sha256=root.envelope_sha256,
        _plan_payload=plan_payload,
        _recipe_payload=_canonical_payload(recipe),
        _producer_execution_payload=execution_payload,
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
    "authenticate_frozen_red_living_dex_clustered_train_slot",
    "authenticate_frozen_red_living_dex_setup_slot",
]
