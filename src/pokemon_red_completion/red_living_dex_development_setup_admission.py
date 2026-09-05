"""Frozen Red setup admission for held clustered development assignments.

The qualified train setup admission is historical evidence and deliberately
cannot address held rows.  This versioned sibling authenticates the complete
clustered plan, one development-only selection, the exact Red producer
identity, and one logical/physical root join.  It only detaches canonical
bytes; it exposes no emulator, controller, model, teacher, or outcome API.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    RedLivingDexClusteredDevelopmentRunnerError,
    RedLivingDexClusteredDevelopmentSelection,
    RedLivingDexDevelopmentPlanBinding,
    authenticate_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    RedLivingDexClusteredTrainPlanBinding,
)
from pokemon_red_completion.red_living_dex_development_supplement_plan import (
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    RedLivingDexDevelopmentSupplementBinding,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA,
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupSlotRecipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA,
    RedLivingDexSetupExecutionIdentity,
)

RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SCHEMA = (
    "pokemon.red.living-dex-development-setup-admission.v1"
)
RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SHA256 = canonical_sha256(
    {
        "controller_api": False,
        "development_only": True,
        "full_plan_reauthentication": True,
        "logical_and_physical_root_join": True,
        "model_predictions": 0,
        "schema": RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SCHEMA,
        "teacher_queries": 0,
        "training_targets": 0,
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
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


class RedLivingDexDevelopmentSetupAdmissionError(RuntimeError):
    """A held Red setup plan, identity, root, or recipe differs."""


@dataclass(frozen=True, slots=True)
class FrozenRedLivingDexDevelopmentSetupSlot:
    """Canonical whole-plan proof plus one detached development recipe."""

    selection: RedLivingDexClusteredDevelopmentSelection
    binding: RedLivingDexDevelopmentPlanBinding = field(repr=False)
    producer_execution_identity_sha256: str = field(repr=False)
    producer_runtime_identity_sha256: str = field(repr=False)
    admission_contract_sha256: str = field(
        default=RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SHA256,
        repr=False,
    )
    _plan_payload: bytes = field(default=b"", repr=False)
    _recipe_payload: bytes = field(default=b"", repr=False)
    _producer_execution_payload: bytes = field(default=b"", repr=False)

    def __post_init__(self) -> None:
        if not isinstance(
            self.selection,
            RedLivingDexClusteredDevelopmentSelection,
        ):
            raise TypeError("development setup needs a held selection")
        self.selection.__post_init__()
        if not isinstance(
            self.binding,
            (RedLivingDexClusteredTrainPlanBinding, RedLivingDexDevelopmentSupplementBinding),
        ):
            raise TypeError("development setup needs its plan binding")
        self.binding.__post_init__()
        for value, subject in (
            (
                self.producer_execution_identity_sha256,
                "producer execution identity",
            ),
            (self.producer_runtime_identity_sha256, "runtime identity"),
            (self.admission_contract_sha256, "admission contract"),
        ):
            _require_sha256(value, subject)
        if self.admission_contract_sha256 != RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SHA256:
            raise RedLivingDexDevelopmentSetupAdmissionError(
                "development setup admission contract differs"
            )
        plan = _decode_canonical(self._plan_payload, "producer plan")
        recipe = _decode_canonical(self._recipe_payload, "recipe")
        identity = self.producer_execution_identity()
        current = authenticate_red_living_dex_development_selection(
            plan,
            self.selection.ordinal,
            binding=self.binding,
        )
        if current != self.selection:
            raise RedLivingDexDevelopmentSetupAdmissionError("development setup selection differs")
        _require_plan_identity_join(
            plan,
            identity,
            runtime_identity_sha256=self.producer_runtime_identity_sha256,
        )
        _require_selected_recipe_join(plan, self.selection, recipe)

    @property
    def template_ordinal(self) -> int:
        """Expose the authenticated recipe template to the shared Red runtime."""
        return self.selection.template_ordinal

    @property
    def plan_payload(self) -> bytes:
        return bytes(self._plan_payload)

    @property
    def recipe_payload(self) -> bytes:
        return bytes(self._recipe_payload)

    def recipe_document(self) -> dict[str, object]:
        return _decode_canonical(self._recipe_payload, "recipe")

    def producer_execution_identity(self) -> RedLivingDexSetupExecutionIdentity:
        document = _decode_canonical(
            self._producer_execution_payload,
            "producer execution identity",
        )
        if (
            set(document) != _EXECUTION_KEYS
            or document.get("schema") != RED_LIVING_DEX_SETUP_EXECUTION_IDENTITY_SCHEMA
            or canonical_sha256(document) != self.producer_execution_identity_sha256
        ):
            raise RedLivingDexDevelopmentSetupAdmissionError(
                "development setup producer identity differs"
            )
        try:
            identity = RedLivingDexSetupExecutionIdentity(
                source_commit=_string(document.get("source_commit"), "source commit"),
                source_bundle_sha256=_string(
                    document.get("source_bundle_sha256"),
                    "source bundle",
                ),
                adapter_version_sha256=_string(
                    document.get("adapter_version_sha256"),
                    "adapter version",
                ),
                state_schema_sha256=_string(
                    document.get("state_schema_sha256"),
                    "state schema",
                ),
                observation_schema_sha256=_string(
                    document.get("observation_schema_sha256"),
                    "observation schema",
                ),
                route_registry_sha256=_string(
                    document.get("route_registry_sha256"),
                    "route registry",
                ),
                provider_registry_sha256=_string(
                    document.get("provider_registry_sha256"),
                    "provider registry",
                ),
                runtime_contract_sha256=_string(
                    document.get("runtime_contract_sha256"),
                    "runtime contract",
                ),
                game_id=_string(document.get("game_id"), "game id"),
                title=_string(document.get("title"), "title"),
                rom_sha1=_string(document.get("rom_sha1"), "ROM SHA-1"),
                rom_sha256=_string(document.get("rom_sha256"), "ROM SHA-256"),
                source_published=document.get("source_published"),  # type: ignore[arg-type]
                worktree_dirty=document.get("worktree_dirty"),  # type: ignore[arg-type]
                adapter_contract_id=_string(
                    document.get("adapter_contract_id"),
                    "adapter contract",
                ),
            )
        except (TypeError, ValueError):
            raise RedLivingDexDevelopmentSetupAdmissionError(
                "development setup producer identity differs"
            ) from None
        if identity.private_dict() != document:
            raise RedLivingDexDevelopmentSetupAdmissionError(
                "development setup producer identity differs"
            )
        return identity

    def reauthenticate(
        self,
        plan_document: Mapping[str, object],
        *,
        root: RedLivingDexAuthenticatedSetupRoot,
    ) -> None:
        current = authenticate_frozen_red_living_dex_development_setup_slot(
            plan_document,
            selection=self.selection,
            binding=self.binding,
            root=root,
            producer_execution_identity=self.producer_execution_identity(),
            expected_runtime_identity_sha256=(self.producer_runtime_identity_sha256),
        )
        if current != self:
            raise RedLivingDexDevelopmentSetupAdmissionError(
                "development setup plan changed after admission"
            )

    def require_resolved_recipe(self, recipe: RedLivingDexSetupSlotRecipe) -> None:
        if not isinstance(recipe, RedLivingDexSetupSlotRecipe):
            raise TypeError("development resolver must return a Red setup recipe")
        recipe.__post_init__()
        if (
            recipe.recipe_sha256 != self.selection.recipe_sha256
            or recipe.slot_sha256 != self.selection.slot_sha256
            or recipe.root_consumption_sha256 != self.selection.logical_root_sha256
            or recipe.root_state_sha256 != self.selection.root_state_sha256
            or recipe.root_envelope_sha256 != self.selection.root_envelope_sha256
            or _canonical_payload(recipe.private_dict()) != self._recipe_payload
        ):
            raise RedLivingDexDevelopmentSetupAdmissionError(
                "development resolved recipe differs from frozen plan"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "admission_contract_sha256": self.admission_contract_sha256,
            "controller_api": False,
            "model_predictions": 0,
            "ordinal_within_development": (self.selection.ordinal - self.selection.train_scenarios),
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "setup_executions": 0,
            "template_ordinal": self.selection.template_ordinal,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        }


def authenticate_frozen_red_living_dex_development_setup_slot(
    plan_document: Mapping[str, object],
    *,
    selection: RedLivingDexClusteredDevelopmentSelection,
    binding: RedLivingDexDevelopmentPlanBinding,
    root: RedLivingDexAuthenticatedSetupRoot,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity,
    expected_runtime_identity_sha256: str,
) -> FrozenRedLivingDexDevelopmentSetupSlot:
    """Detach exactly one held setup after full plan and root authentication."""

    if not isinstance(plan_document, Mapping):
        raise TypeError("development setup admission needs a plan mapping")
    if not isinstance(
        selection,
        RedLivingDexClusteredDevelopmentSelection,
    ):
        raise TypeError("development setup admission needs a held selection")
    selection.__post_init__()
    if not isinstance(
        binding, (RedLivingDexClusteredTrainPlanBinding, RedLivingDexDevelopmentSupplementBinding)
    ):
        raise TypeError("development setup admission needs a plan binding")
    binding.__post_init__()
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("development setup admission needs an authenticated root")
    root.__post_init__()
    if not isinstance(
        producer_execution_identity,
        RedLivingDexSetupExecutionIdentity,
    ):
        raise TypeError("development setup admission needs a producer identity")
    producer_execution_identity.__post_init__()
    runtime_identity = _require_sha256(
        expected_runtime_identity_sha256,
        "runtime identity",
    )
    try:
        plan_payload = _canonical_payload(dict(plan_document))
        plan = _decode_canonical(plan_payload, "producer plan")
        current = authenticate_red_living_dex_development_selection(
            plan,
            selection.ordinal,
            binding=binding,
        )
    except (
        RedLivingDexClusteredDevelopmentRunnerError,
        TypeError,
        ValueError,
        OverflowError,
    ):
        raise RedLivingDexDevelopmentSetupAdmissionError(
            "development setup producer plan differs"
        ) from None
    if current != selection:
        raise RedLivingDexDevelopmentSetupAdmissionError("development setup selection differs")
    _require_plan_identity_join(
        plan,
        producer_execution_identity,
        runtime_identity_sha256=runtime_identity,
    )
    assignments = plan.get("assignments")
    if not isinstance(assignments, list):
        raise RedLivingDexDevelopmentSetupAdmissionError("development setup assignments differ")
    selected = assignments[selection.ordinal]
    if not isinstance(selected, dict) or not isinstance(
        selected.get("recipe"),
        dict,
    ):
        raise RedLivingDexDevelopmentSetupAdmissionError(
            "development setup selected recipe differs"
        )
    recipe = selected["recipe"]
    assert isinstance(recipe, dict)
    _require_root_join(selection, root)
    _require_selected_recipe_join(plan, selection, recipe)
    return FrozenRedLivingDexDevelopmentSetupSlot(
        selection=selection,
        binding=binding,
        producer_execution_identity_sha256=(producer_execution_identity.identity_sha256),
        producer_runtime_identity_sha256=runtime_identity,
        _plan_payload=plan_payload,
        _recipe_payload=_canonical_payload(recipe),
        _producer_execution_payload=_canonical_payload(producer_execution_identity.private_dict()),
    )


def _require_plan_identity_join(
    plan: Mapping[str, object],
    identity: RedLivingDexSetupExecutionIdentity,
    *,
    runtime_identity_sha256: str,
) -> None:
    if (
        plan.get("schema")
        not in (
            RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA,
            RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA,
        )
        or plan.get("source_commit") != identity.source_commit
        or plan.get("source_bundle_sha256") != identity.source_bundle_sha256
        or plan.get("route_registry_sha256") != identity.route_registry_sha256
        or plan.get("rom_sha256") != identity.rom_sha256
        or plan.get("runtime_identity_sha256") != runtime_identity_sha256
    ):
        raise RedLivingDexDevelopmentSetupAdmissionError(
            "development setup producer identity binding differs"
        )


def _require_root_join(
    selection: RedLivingDexClusteredDevelopmentSelection,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    if (
        root.root_consumption_sha256 != selection.logical_root_sha256
        or root.physical_root_sha256 != selection.physical_root_sha256
        or root.state_sha256 != selection.root_state_sha256
        or root.envelope_sha256 != selection.root_envelope_sha256
    ):
        raise RedLivingDexDevelopmentSetupAdmissionError("development setup root differs")


def _require_selected_recipe_join(
    plan: Mapping[str, object],
    selection: RedLivingDexClusteredDevelopmentSelection,
    recipe: Mapping[str, object],
) -> None:
    assignments = plan.get("assignments")
    if not isinstance(assignments, list):
        raise RedLivingDexDevelopmentSetupAdmissionError("development setup assignments differ")
    selected = assignments[selection.ordinal]
    if not isinstance(selected, Mapping):
        raise RedLivingDexDevelopmentSetupAdmissionError(
            "development setup selected assignment differs"
        )
    if (
        set(recipe) != _RECIPE_KEYS
        or recipe.get("schema") != RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA
        or recipe.get("partition") != "development"
        or canonical_sha256(recipe) != selection.recipe_sha256
        or selected.get("recipe_sha256") != selection.recipe_sha256
        or selected.get("template_sha256") != selection.slot_sha256
        or recipe.get("slot_sha256") != selection.slot_sha256
        or recipe.get("root_consumption_sha256") != selection.logical_root_sha256
        or recipe.get("root_state_sha256") != selection.root_state_sha256
        or recipe.get("root_envelope_sha256") != selection.root_envelope_sha256
    ):
        raise RedLivingDexDevelopmentSetupAdmissionError(
            "development setup selected recipe differs"
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
        raise RedLivingDexDevelopmentSetupAdmissionError(
            f"development setup {subject} payload is absent"
        )
    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RedLivingDexDevelopmentSetupAdmissionError(
            f"development setup {subject} cannot be decoded"
        ) from None
    if not isinstance(document, dict) or _canonical_payload(document) != payload:
        raise RedLivingDexDevelopmentSetupAdmissionError(
            f"development setup {subject} is not canonical"
        )
    return document


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexDevelopmentSetupAdmissionError(f"development setup {subject} differs")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexDevelopmentSetupAdmissionError(f"development setup {subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SCHEMA",
    "RED_LIVING_DEX_DEVELOPMENT_SETUP_ADMISSION_SHA256",
    "FrozenRedLivingDexDevelopmentSetupSlot",
    "RedLivingDexDevelopmentSetupAdmissionError",
    "authenticate_frozen_red_living_dex_development_setup_slot",
]
