"""Five-root Red development preflight for the frozen option-value model.

The batch is deliberately development-only.  It authenticates two preserved
historical held rows and all three supplement rows, joins the exact train-only
model record, and exercises the production preflight for every root without a
ROM, model prediction, claim, controller action, or outcome.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    observe_claim_first_pair_availability,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.red_living_dex_causal_invocation import (
    RedLivingDexAuthenticatedConsumer,
)
from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    RedLivingDexClusteredDevelopmentPreflightReceipt,
    preflight_red_living_dex_development_assignment,
)
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    RedLivingDexClusteredDevelopmentSelection,
    load_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN,
    RedLivingDexClusteredTrainPlanBinding,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT,
    RedLivingDexDevelopmentSupplementBinding,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    load_red_living_dex_development_model,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)

RED_LIVING_DEX_DEVELOPMENT_BATCH_PREFLIGHT_SCHEMA = (
    "pokemon.red.living-dex-development-batch-preflight.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_HISTORICAL_CASES = (
    (FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN, 10),
    (FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN, 11),
)


class RedLivingDexDevelopmentBatchError(RuntimeError):
    """The exact five-root development batch differs or has side effects."""


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentBatchAssignment:
    """One private root joined to one explicit development-only plan row."""

    binding: RedLivingDexClusteredTrainPlanBinding | RedLivingDexDevelopmentSupplementBinding = (
        field(repr=False)
    )
    ordinal: int
    root: RedLivingDexAuthenticatedSetupRoot = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(
            self.binding,
            (RedLivingDexClusteredTrainPlanBinding, RedLivingDexDevelopmentSupplementBinding),
        ):
            raise TypeError("development batch assignment needs its plan binding")
        self.binding.__post_init__()
        if type(self.ordinal) is not int:  # noqa: E721
            raise TypeError("development batch assignment needs an integer ordinal")
        if not isinstance(self.root, RedLivingDexAuthenticatedSetupRoot):
            raise TypeError("development batch assignment needs its authenticated root")
        self.root.__post_init__()


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentBatchPreflightReceipt:
    model_sha256: str
    model_record_sha256: str
    cases: tuple[RedLivingDexClusteredDevelopmentPreflightReceipt, ...] = field(
        repr=False
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.model_sha256, str)
            or _SHA256.fullmatch(self.model_sha256) is None
            or not isinstance(self.model_record_sha256, str)
            or _SHA256.fullmatch(self.model_record_sha256) is None
            or not isinstance(self.cases, tuple)
            or len(self.cases) != 5
            or any(
                not isinstance(item, RedLivingDexClusteredDevelopmentPreflightReceipt)
                for item in self.cases
            )
        ):
            raise RedLivingDexDevelopmentBatchError(
                "development batch preflight receipt differs"
            )
        for item in self.cases:
            item.__post_init__()
        selections = tuple(item.selection for item in self.cases)
        if (
            sum(item.plan_kind == "clustered" for item in selections) != 2
            or sum(item.plan_kind == "supplement" for item in selections) != 3
            or len({item.upstream_lineage_sha256 for item in selections}) != 5
            or len({item.logical_root_sha256 for item in selections}) != 5
            or len({item.physical_root_sha256 for item in selections}) != 5
            or len(
                {(item.root_state_sha256, item.root_envelope_sha256) for item in selections}
            )
            != 5
        ):
            raise RedLivingDexDevelopmentBatchError(
                "development batch roots are not five independent cases"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "cases_ready": 5,
            "controller_actions": 0,
            "development_outcomes_opened": 0,
            "emulator_frames": 0,
            "historical_cases_ready": 2,
            "model_fits": 0,
            "model_predictions": 0,
            "model_record_sha256": self.model_record_sha256,
            "model_sha256": self.model_sha256,
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_DEVELOPMENT_BATCH_PREFLIGHT_SCHEMA,
            "status": "five_development_roots_ready_without_effects",
            "supplement_cases_ready": 3,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentBatchInputReceipt:
    """Five real inputs joined without source bootstrap, runtime, or gameplay."""

    model_sha256: str
    model_record_sha256: str
    selections: tuple[RedLivingDexClusteredDevelopmentSelection, ...] = field(
        repr=False
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.model_sha256, str)
            or _SHA256.fullmatch(self.model_sha256) is None
            or not isinstance(self.model_record_sha256, str)
            or _SHA256.fullmatch(self.model_record_sha256) is None
            or not isinstance(self.selections, tuple)
            or len(self.selections) != 5
            or any(
                not isinstance(item, RedLivingDexClusteredDevelopmentSelection)
                for item in self.selections
            )
        ):
            raise RedLivingDexDevelopmentBatchError(
                "development batch input receipt differs"
            )
        for item in self.selections:
            item.__post_init__()
        if (
            sum(item.plan_kind == "clustered" for item in self.selections) != 2
            or sum(item.plan_kind == "supplement" for item in self.selections) != 3
            or len({item.upstream_lineage_sha256 for item in self.selections}) != 5
            or len({item.logical_root_sha256 for item in self.selections}) != 5
            or len({item.physical_root_sha256 for item in self.selections}) != 5
            or len(
                {
                    (item.root_state_sha256, item.root_envelope_sha256)
                    for item in self.selections
                }
            )
            != 5
        ):
            raise RedLivingDexDevelopmentBatchError(
                "development batch input roots are not five independent cases"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "cases_ready": 5,
            "claims_available": 5,
            "controller_actions": 0,
            "development_outcomes_opened": 0,
            "emulator_frames": 0,
            "exact_source_ci_binding": False,
            "historical_cases_ready": 2,
            "model_fits": 0,
            "model_predictions": 0,
            "model_record_sha256": self.model_record_sha256,
            "model_sha256": self.model_sha256,
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "production_resolver_rehearsed": False,
            "rigor": "development_repeatable",
            "root_claims": 0,
            "runtime_authenticated": False,
            "schema": "pokemon.red.living-dex-development-batch-input-readiness.v1",
            "status": "five_development_inputs_ready_without_runtime_or_effects",
            "supplement_cases_ready": 3,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        }


def inspect_red_living_dex_development_batch_inputs(
    store: PrivateArtifactRoot,
    *,
    assignments: tuple[RedLivingDexDevelopmentBatchAssignment, ...],
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexDevelopmentBatchInputReceipt:
    """Join the five development inputs in the repeatable, pre-runtime tier."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development batch input inspection needs its private store")
    if not isinstance(assignments, tuple) or len(assignments) != 5:
        raise RedLivingDexDevelopmentBatchError(
            "development batch needs exactly five assignments"
        )
    if any(not isinstance(item, RedLivingDexDevelopmentBatchAssignment) for item in assignments):
        raise TypeError("development batch contains another assignment type")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("development batch input inspection needs its protected-effect meter")
    for item in assignments:
        item.__post_init__()
    _require_frozen_batch_shape(assignments)
    before = meter.checkpoint()
    model_record = load_red_living_dex_development_model(
        store,
        expected_model_sha256=(FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_sha256),
        expected_model_record_sha256=(
            FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_record_sha256
        ),
    )
    claim_registry = fixed_account_claim_registry_root()
    selections: list[RedLivingDexClusteredDevelopmentSelection] = []
    for assignment in _canonical_assignments(assignments):
        selection, _document = load_red_living_dex_development_selection(
            store,
            assignment.ordinal,
            binding=assignment.binding,
        )
        _exact_root_loader(assignment)(selection)
        if not observe_claim_first_pair_availability(
            claim_registry,
            selection.logical_root_sha256,
            selection.physical_root_sha256,
        ):
            raise RedLivingDexDevelopmentBatchError(
                "development batch root pair is unavailable"
            )
        selections.append(selection)
    if meter.checkpoint() != before:
        raise RedLivingDexDevelopmentBatchError(
            "development batch input inspection changed protected effects"
        )
    return RedLivingDexDevelopmentBatchInputReceipt(
        model_sha256=model_record.model.model_sha256,
        model_record_sha256=model_record.file_sha256,
        selections=tuple(selections),
    )


def preflight_red_living_dex_development_batch(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexAuthenticatedConsumer,
    assignments: tuple[RedLivingDexDevelopmentBatchAssignment, ...],
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexDevelopmentBatchPreflightReceipt:
    """Authenticate the frozen five-root batch without gameplay or scoring."""

    if not isinstance(project_root, Path):
        raise TypeError("development batch preflight needs a project Path")
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development batch preflight needs its private store")
    if not isinstance(consumer, RedLivingDexAuthenticatedConsumer):
        raise TypeError("development batch preflight needs its authenticated consumer")
    consumer.__post_init__()
    if not isinstance(assignments, tuple) or len(assignments) != 5:
        raise RedLivingDexDevelopmentBatchError(
            "development batch needs exactly five assignments"
        )
    if any(not isinstance(item, RedLivingDexDevelopmentBatchAssignment) for item in assignments):
        raise TypeError("development batch contains another assignment type")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("development batch preflight needs its protected-effect meter")
    for item in assignments:
        item.__post_init__()
    _require_frozen_batch_shape(assignments)
    before = meter.checkpoint()
    model_record = load_red_living_dex_development_model(
        store,
        expected_model_sha256=(FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_sha256),
        expected_model_record_sha256=(
            FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_record_sha256
        ),
    )
    receipts: list[RedLivingDexClusteredDevelopmentPreflightReceipt] = []
    for assignment in _canonical_assignments(assignments):
        receipts.append(
            preflight_red_living_dex_development_assignment(
                project_root,
                store,
                consumer=consumer,
                ordinal=assignment.ordinal,
                root_loader=_exact_root_loader(assignment),
                meter=meter,
                model_record=model_record,
                expected_model_sha256=(
                    FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_sha256
                ),
                expected_model_record_sha256=(
                    FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_record_sha256
                ),
                binding=assignment.binding,
            )
        )
    if meter.checkpoint() != before:
        raise RedLivingDexDevelopmentBatchError(
            "development batch preflight changed protected effects"
        )
    return RedLivingDexDevelopmentBatchPreflightReceipt(
        model_sha256=model_record.model.model_sha256,
        model_record_sha256=model_record.file_sha256,
        cases=tuple(receipts),
    )


def _require_frozen_batch_shape(
    assignments: tuple[RedLivingDexDevelopmentBatchAssignment, ...],
) -> None:
    supplement = tuple(
        item
        for item in assignments
        if isinstance(item.binding, RedLivingDexDevelopmentSupplementBinding)
    )
    historical = tuple(
        item
        for item in assignments
        if isinstance(item.binding, RedLivingDexClusteredTrainPlanBinding)
    )
    if (
        len(supplement) != 3
        or len(historical) != 2
        or any(
            item.binding != FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT
            for item in supplement
        )
        or {item.ordinal for item in supplement} != {0, 1, 2}
        or {(item.binding, item.ordinal) for item in historical}
        != set(_HISTORICAL_CASES)
        or len({(item.binding.private_plan_sha256, item.ordinal) for item in assignments}) != 5
        or len({item.root.root_consumption_sha256 for item in assignments}) != 5
        or len({item.root.physical_root_sha256 for item in assignments}) != 5
        or len({(item.root.state_sha256, item.root.envelope_sha256) for item in assignments}) != 5
    ):
        raise RedLivingDexDevelopmentBatchError("development batch shape differs")


def _canonical_assignments(
    assignments: tuple[RedLivingDexDevelopmentBatchAssignment, ...],
) -> tuple[RedLivingDexDevelopmentBatchAssignment, ...]:
    return tuple(
        sorted(
            assignments,
            key=lambda item: (
                isinstance(item.binding, RedLivingDexDevelopmentSupplementBinding),
                item.binding.private_plan_sha256,
                item.ordinal,
            ),
        )
    )


def _exact_root_loader(
    expected: RedLivingDexDevelopmentBatchAssignment,
):  # type: ignore[no-untyped-def]
    def load(selection):  # type: ignore[no-untyped-def]
        if (
            selection.ordinal != expected.ordinal
            or selection.private_plan_sha256 != expected.binding.private_plan_sha256
        ):
            raise RedLivingDexDevelopmentBatchError(
                "development batch selected another root"
            )
        return expected.root

    return load


__all__ = [
    "RED_LIVING_DEX_DEVELOPMENT_BATCH_PREFLIGHT_SCHEMA",
    "RedLivingDexDevelopmentBatchAssignment",
    "RedLivingDexDevelopmentBatchError",
    "RedLivingDexDevelopmentBatchInputReceipt",
    "RedLivingDexDevelopmentBatchPreflightReceipt",
    "inspect_red_living_dex_development_batch_inputs",
    "preflight_red_living_dex_development_batch",
]
