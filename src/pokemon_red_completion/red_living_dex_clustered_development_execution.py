"""Compose held Red setup with one exact model-led development outcome.

This is the first title adapter path that lets a fitted living-Pokedex option
model choose a real held Red branch.  Setup remains deterministic and
claim-first; the model sees only the title-neutral menu; only the selected
branch may receive controller authority; and its outcome is evaluation data,
never a training target.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstExecutionIdentity,
    observe_claim_first_pair_availability,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.living_dex_goal_model_record import (
    LivingDexGoalModelRecord,
)
from pokemon_red_completion.living_dex_goal_policy import (
    DEFAULT_LIVING_DEX_GOAL_UTILITY,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
)
from pokemon_red_completion.living_dex_policy_development_journal import (
    LivingDexPolicyDevelopmentReceipt,
    execute_living_dex_policy_development,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_adapter import (
    build_red_living_dex_causal_scenario_from_capture,
)
from pokemon_red_completion.red_living_dex_causal_invocation import (
    RedLivingDexAuthenticatedConsumer,
    RedLivingDexLateProductionResolver,
    authenticate_red_living_dex_execution_runtime,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    RedLivingDexClusteredDevelopmentSelection,
    RedLivingDexDevelopmentPlanBinding,
    reopen_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    RedLivingDexClusteredTrainPlanBinding,
)
from pokemon_red_completion.red_living_dex_development_setup_admission import (
    FrozenRedLivingDexDevelopmentSetupSlot,
    authenticate_frozen_red_living_dex_development_setup_slot,
)
from pokemon_red_completion.red_living_dex_development_setup_journal import (
    RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256,
    RedLivingDexDevelopmentSetupFailpoint,
    RedLivingDexDevelopmentSetupReceipt,
    RedLivingDexDevelopmentSetupResolver,
    run_red_living_dex_development_setup,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    RedLivingDexDevelopmentSupplementBinding,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_identity import (
    compose_red_living_dex_setup_execution_identity,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
)

RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_EXECUTION_SCHEMA = (
    "pokemon.red.living-dex-clustered-development-execution.v1"
)
RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_EXECUTION_SHA256 = canonical_sha256(
    {
        "development_outcome_is_training_target": False,
        "exact_model_choice": True,
        "one_selected_runtime": True,
        "schema": RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_EXECUTION_SCHEMA,
        "setup_runner_sha256": RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256,
        "teacher_queries": 0,
        "title_neutral_model_boundary": True,
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

RedLivingDexDevelopmentRootLoader = Callable[
    [RedLivingDexClusteredDevelopmentSelection],
    RedLivingDexAuthenticatedSetupRoot,
]


class RedLivingDexClusteredDevelopmentExecutionError(RuntimeError):
    """A Red held setup and title-neutral model execution do not join."""


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredDevelopmentPreflightReceipt:
    selection: RedLivingDexClusteredDevelopmentSelection
    model_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.selection,
            RedLivingDexClusteredDevelopmentSelection,
        ):
            raise TypeError("Red development preflight needs its selection")
        self.selection.__post_init__()
        _require_sha256(self.model_sha256, "preflight model")

    def public_dict(self) -> dict[str, object]:
        return {
            "claim_available": True,
            "controller_actions": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "model_sha256": self.model_sha256,
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "schema": ("pokemon.red.living-dex-clustered-development-preflight.v1"),
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredDevelopmentReceipt:
    selection: RedLivingDexClusteredDevelopmentSelection
    setup: RedLivingDexDevelopmentSetupReceipt
    development: LivingDexPolicyDevelopmentReceipt | None

    def __post_init__(self) -> None:
        if not isinstance(
            self.selection,
            RedLivingDexClusteredDevelopmentSelection,
        ):
            raise TypeError("Red development receipt needs its selection")
        self.selection.__post_init__()
        if not isinstance(self.setup, RedLivingDexDevelopmentSetupReceipt):
            raise TypeError("Red development receipt needs its setup")
        self.setup.__post_init__()
        if self.setup.frozen.selection != self.selection:
            raise RedLivingDexClusteredDevelopmentExecutionError(
                "Red development receipt selection differs"
            )
        if self.setup.terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
            if not isinstance(
                self.development,
                LivingDexPolicyDevelopmentReceipt,
            ):
                raise RedLivingDexClusteredDevelopmentExecutionError(
                    "complete Red setup lacks a development outcome"
                )
            self.development.__post_init__()
        elif self.development is not None:
            raise RedLivingDexClusteredDevelopmentExecutionError(
                "failed Red setup opened a development outcome"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "development": (None if self.development is None else self.development.public_dict()),
            "development_outcomes_opened": int(self.development is not None),
            "model_fits": 0,
            "model_predictions": int(self.development is not None),
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "schema": RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_EXECUTION_SCHEMA,
            "setup": self.setup.public_dict(),
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        }


def run_red_living_dex_clustered_development_assignment(
    *,
    selection: RedLivingDexClusteredDevelopmentSelection,
    binding: RedLivingDexDevelopmentPlanBinding,
    store: PrivateArtifactRoot,
    plan_loader: Callable[[], Mapping[str, object]],
    root: RedLivingDexAuthenticatedSetupRoot,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    resolver: RedLivingDexDevelopmentSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    model: LivingDexOptionValueModel,
    expected_model_sha256: str,
    utility: LivingDexOptionUtility = DEFAULT_LIVING_DEX_GOAL_UTILITY,
    setup_failpoint: RedLivingDexDevelopmentSetupFailpoint | None = None,
    development_failpoint: Callable[[str], None] | None = None,
) -> RedLivingDexClusteredDevelopmentReceipt:
    """Execute or recover one held Red row through both durable journals."""

    if not isinstance(
        selection,
        RedLivingDexClusteredDevelopmentSelection,
    ):
        raise TypeError("Red development execution needs a held selection")
    selection.__post_init__()
    if not isinstance(
        binding, (RedLivingDexClusteredTrainPlanBinding, RedLivingDexDevelopmentSupplementBinding)
    ):
        raise TypeError("Red development execution needs its plan binding")
    binding.__post_init__()
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("Red development execution needs a private store")
    if not callable(plan_loader):
        raise TypeError("Red development execution needs a plan loader")
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("Red development execution needs an authenticated root")
    root.__post_init__()
    if not isinstance(
        producer_execution_identity,
        RedLivingDexSetupExecutionIdentity,
    ):
        raise TypeError("Red development execution needs a producer identity")
    producer_execution_identity.__post_init__()
    if not isinstance(outer_execution_identity, ClaimFirstExecutionIdentity):
        raise TypeError("Red development execution needs an outer identity")
    outer_execution_identity.__post_init__()
    if not isinstance(resolver, RedLivingDexDevelopmentSetupResolver):
        raise TypeError("Red development execution needs a cold Red resolver")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("Red development execution needs the protected meter")
    if not isinstance(claim_registry, Path):
        raise TypeError("Red development execution needs a claim registry Path")
    if not isinstance(model, LivingDexOptionValueModel):
        raise TypeError("Red development execution needs an option model")
    model.__post_init__()
    expected_model = _require_sha256(expected_model_sha256, "model")
    if model.model_sha256 != expected_model or (
        isinstance(binding, RedLivingDexDevelopmentSupplementBinding)
        and expected_model != binding.model_sha256
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development model identity differs"
        )
    if not isinstance(utility, LivingDexOptionUtility):
        raise TypeError("Red development execution needs a utility")
    utility.__post_init__()
    _require_root_join(selection, root)
    _require_outer_join(
        selection,
        binding=binding,
        producer_execution_identity=producer_execution_identity,
        outer_execution_identity=outer_execution_identity,
    )

    first_document = plan_loader()
    runtime_identity = _require_sha256(
        first_document.get("runtime_identity_sha256"),
        "producer runtime identity",
    )
    frozen = authenticate_frozen_red_living_dex_development_setup_slot(
        first_document,
        selection=selection,
        binding=binding,
        root=root,
        producer_execution_identity=producer_execution_identity,
        expected_runtime_identity_sha256=runtime_identity,
    )
    setup = run_red_living_dex_development_setup(
        frozen,
        store=store,
        plan_loader=plan_loader,
        root=root,
        outer_execution_identity=outer_execution_identity,
        resolver=resolver,
        meter=meter,
        claim_registry=claim_registry,
        failpoint=setup_failpoint,
    )
    if setup.terminal.status is not LivingDexCaptureSetupStatus.COMPLETE:
        return RedLivingDexClusteredDevelopmentReceipt(selection, setup, None)
    capture = setup.capture
    if capture is None:
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "complete Red development setup lacks its capture"
        )
    setup_pair = outer_execution_identity.root_pair(stage="development-setup")

    @contextmanager
    def resolve_runtime() -> Iterator[RedLivingDexResolvedSetupSlot]:
        before = meter.checkpoint()
        frozen.reauthenticate(plan_loader(), root=root)
        if meter.checkpoint() != before:
            raise RedLivingDexClusteredDevelopmentExecutionError(
                "Red development reauthentication changed effects"
            )
        scope = resolver(frozen, root, setup_pair, meter=meter)
        if meter.checkpoint() != before:
            raise RedLivingDexClusteredDevelopmentExecutionError(
                "Red development resolver changed effects"
            )
        with scope as resolved:
            _require_resolved_runtime(frozen, resolved)
            yield resolved

    scenario = build_red_living_dex_causal_scenario_from_capture(
        capture,
        setup_execution_identity=producer_execution_identity,
        runtime_resolver=resolve_runtime,
        meter=meter,
        setup_terminal_sha256=canonical_sha256(setup.terminal.private_dict()),
        setup_pair_claim_sha256=setup_pair.claim_sha256,
        causal_source_commit=outer_execution_identity.source_commit,
        causal_runner_sha256=(RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_EXECUTION_SHA256),
        upstream_lineage_sha256=selection.upstream_lineage_sha256,
    )
    development = execute_living_dex_policy_development(
        scenario,
        model,
        utility=utility,
        expected_model_sha256=expected_model,
        store=store,
        claim_registry=claim_registry,
        failpoint=development_failpoint,
    )
    return RedLivingDexClusteredDevelopmentReceipt(
        selection,
        setup,
        development,
    )


def preflight_red_living_dex_clustered_development_assignment(
    *,
    selection: RedLivingDexClusteredDevelopmentSelection,
    binding: RedLivingDexDevelopmentPlanBinding,
    plan_document: Mapping[str, object],
    root: RedLivingDexAuthenticatedSetupRoot,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    model: LivingDexOptionValueModel,
    expected_model_sha256: str,
) -> RedLivingDexClusteredDevelopmentPreflightReceipt:
    """Authenticate the complete live join without a runtime or prediction."""

    if not isinstance(
        selection,
        RedLivingDexClusteredDevelopmentSelection,
    ):
        raise TypeError("Red development preflight needs a held selection")
    selection.__post_init__()
    if not isinstance(
        binding, (RedLivingDexClusteredTrainPlanBinding, RedLivingDexDevelopmentSupplementBinding)
    ):
        raise TypeError("Red development preflight needs its plan binding")
    binding.__post_init__()
    if not isinstance(plan_document, Mapping):
        raise TypeError("Red development preflight needs a plan mapping")
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("Red development preflight needs an authenticated root")
    root.__post_init__()
    if not isinstance(
        producer_execution_identity,
        RedLivingDexSetupExecutionIdentity,
    ):
        raise TypeError("Red development preflight needs a producer identity")
    producer_execution_identity.__post_init__()
    if not isinstance(outer_execution_identity, ClaimFirstExecutionIdentity):
        raise TypeError("Red development preflight needs an outer identity")
    outer_execution_identity.__post_init__()
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("Red development preflight needs the protected meter")
    if not isinstance(claim_registry, Path):
        raise TypeError("Red development preflight needs a claim registry Path")
    if not isinstance(model, LivingDexOptionValueModel):
        raise TypeError("Red development preflight needs an option model")
    model.__post_init__()
    expected_model = _require_sha256(expected_model_sha256, "model")
    if model.model_sha256 != expected_model or (
        isinstance(binding, RedLivingDexDevelopmentSupplementBinding)
        and expected_model != binding.model_sha256
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development model identity differs"
        )
    before = meter.checkpoint()
    _require_root_join(selection, root)
    _require_outer_join(
        selection,
        binding=binding,
        producer_execution_identity=producer_execution_identity,
        outer_execution_identity=outer_execution_identity,
    )
    runtime_identity = _require_sha256(
        plan_document.get("runtime_identity_sha256"),
        "producer runtime identity",
    )
    authenticate_frozen_red_living_dex_development_setup_slot(
        plan_document,
        selection=selection,
        binding=binding,
        root=root,
        producer_execution_identity=producer_execution_identity,
        expected_runtime_identity_sha256=runtime_identity,
    )
    if not observe_claim_first_pair_availability(
        claim_registry,
        selection.logical_root_sha256,
        selection.physical_root_sha256,
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development root pair is unavailable"
        )
    if meter.checkpoint() != before:
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development preflight changed protected effects"
        )
    return RedLivingDexClusteredDevelopmentPreflightReceipt(
        selection,
        expected_model,
    )


def execute_red_living_dex_development_assignment(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexAuthenticatedConsumer,
    ordinal: int,
    root_loader: RedLivingDexDevelopmentRootLoader,
    rom_path: Path,
    meter: RedLivingDexSetupEffectMeter,
    model_record: LivingDexGoalModelRecord,
    expected_model_sha256: str,
    expected_model_record_sha256: str,
    binding: RedLivingDexDevelopmentPlanBinding,
) -> RedLivingDexClusteredDevelopmentReceipt:
    """Execute or recover one authenticated development row in production."""

    if not isinstance(rom_path, Path):
        raise TypeError("Red development invocation needs its Red ROM Path")
    prepared = _prepare_red_living_dex_development_invocation(
        project_root,
        store,
        consumer=consumer,
        ordinal=ordinal,
        root_loader=root_loader,
        meter=meter,
        model_record=model_record,
        expected_model_sha256=expected_model_sha256,
        expected_model_record_sha256=expected_model_record_sha256,
        binding=binding,
    )
    resolver = RedLivingDexLateProductionResolver(
        rom_path=rom_path,
        producer_execution_identity=prepared.producer_execution_identity,
    )
    return run_red_living_dex_clustered_development_assignment(
        selection=prepared.selection,
        binding=binding,
        store=store,
        plan_loader=prepared.load_plan,
        root=prepared.root,
        producer_execution_identity=prepared.producer_execution_identity,
        outer_execution_identity=prepared.outer_execution_identity,
        resolver=resolver,
        meter=meter,
        claim_registry=prepared.claim_registry,
        model=prepared.model,
        expected_model_sha256=expected_model_sha256,
    )


def preflight_red_living_dex_development_assignment(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexAuthenticatedConsumer,
    ordinal: int,
    root_loader: RedLivingDexDevelopmentRootLoader,
    meter: RedLivingDexSetupEffectMeter,
    model_record: LivingDexGoalModelRecord,
    expected_model_sha256: str,
    expected_model_record_sha256: str,
    binding: RedLivingDexDevelopmentPlanBinding,
) -> RedLivingDexClusteredDevelopmentPreflightReceipt:
    """Authenticate one production development row without a ROM or prediction."""

    before = meter.checkpoint()
    prepared = _prepare_red_living_dex_development_invocation(
        project_root,
        store,
        consumer=consumer,
        ordinal=ordinal,
        root_loader=root_loader,
        meter=meter,
        model_record=model_record,
        expected_model_sha256=expected_model_sha256,
        expected_model_record_sha256=expected_model_record_sha256,
        binding=binding,
    )
    result = preflight_red_living_dex_clustered_development_assignment(
        selection=prepared.selection,
        binding=binding,
        plan_document=prepared.load_plan(),
        root=prepared.root,
        producer_execution_identity=prepared.producer_execution_identity,
        outer_execution_identity=prepared.outer_execution_identity,
        meter=meter,
        claim_registry=prepared.claim_registry,
        model=prepared.model,
        expected_model_sha256=expected_model_sha256,
    )
    if meter.checkpoint() != before:
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development production preflight changed protected effects"
        )
    return result


@dataclass(frozen=True, slots=True)
class _PreparedRedLivingDexDevelopmentInvocation:
    selection: RedLivingDexClusteredDevelopmentSelection
    root: RedLivingDexAuthenticatedSetupRoot
    producer_execution_identity: RedLivingDexSetupExecutionIdentity
    outer_execution_identity: ClaimFirstExecutionIdentity
    claim_registry: Path
    model: LivingDexOptionValueModel
    load_plan: Callable[[], Mapping[str, object]]


def _prepare_red_living_dex_development_invocation(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexAuthenticatedConsumer,
    ordinal: int,
    root_loader: RedLivingDexDevelopmentRootLoader,
    meter: RedLivingDexSetupEffectMeter,
    model_record: LivingDexGoalModelRecord,
    expected_model_sha256: str,
    expected_model_record_sha256: str,
    binding: RedLivingDexDevelopmentPlanBinding,
) -> _PreparedRedLivingDexDevelopmentInvocation:
    """Join current source, exact plan/model, one root and the staged runtime."""

    if not isinstance(project_root, Path):
        raise TypeError("Red development invocation needs a project Path")
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("Red development invocation needs its private store")
    if not isinstance(consumer, RedLivingDexAuthenticatedConsumer):
        raise TypeError("Red development invocation needs its authenticated consumer")
    consumer.__post_init__()
    if not callable(root_loader):
        raise TypeError("Red development invocation needs one selected-root loader")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("Red development invocation needs its protected-effect meter")
    if not isinstance(model_record, LivingDexGoalModelRecord):
        raise TypeError("Red development invocation needs its authenticated model record")
    model_record.__post_init__()
    model = model_record.model
    model.__post_init__()
    expected_model = _require_sha256(expected_model_sha256, "model")
    expected_model_record = _require_sha256(
        expected_model_record_sha256,
        "model record",
    )
    if (
        model.model_sha256 != expected_model
        or model_record.file_sha256 != expected_model_record
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development model identity differs"
        )
    if not isinstance(
        binding, (RedLivingDexClusteredTrainPlanBinding, RedLivingDexDevelopmentSupplementBinding)
    ):
        raise TypeError("Red development invocation needs its plan binding")
    binding.__post_init__()
    if isinstance(binding, RedLivingDexDevelopmentSupplementBinding) and (
        binding.model_sha256 != expected_model
        or binding.model_record_sha256 != expected_model_record
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development model identity differs"
        )

    selection, first_record, first_document = reopen_red_living_dex_development_selection(
        store,
        ordinal,
        binding=binding,
    )
    root = root_loader(selection)
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("Red development root loader returned another type")
    root.__post_init__()
    _require_root_join(selection, root)
    runtime = authenticate_red_living_dex_execution_runtime(
        project_root,
        _require_sha256(
            first_document.get("runtime_identity_sha256"),
            "producer runtime identity",
        ),
    )
    producer_identity = compose_red_living_dex_setup_execution_identity(
        source_commit=_require_source_commit(first_document.get("source_commit")),
        source_bundle_sha256=_require_sha256(
            first_document.get("source_bundle_sha256"),
            "producer source bundle",
        ),
        route_registry_sha256=_require_sha256(
            first_document.get("route_registry_sha256"),
            "producer route registry",
        ),
        runtime_identity=runtime,
    )
    current = consumer.binding
    outer = ClaimFirstExecutionIdentity(
        source_commit=current.source_commit,
        source_bundle_sha256=current.source_bundle_sha256,
        exact_ci_run=current.exact_ci_run,
        exact_ci_attempt=current.exact_ci_attempt,
        producer_execution_identity_sha256=producer_identity.identity_sha256,
        producer_plan_sha256=selection.private_plan_sha256,
        producer_private_plan_sha256=selection.private_plan_sha256,
        producer_manifest_sha256=binding.plan_manifest_sha256,
        slot_sha256=selection.slot_sha256,
        recipe_sha256=selection.recipe_sha256,
        logical_root_sha256=selection.logical_root_sha256,
        physical_root_sha256=selection.physical_root_sha256,
        title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
        runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
        runner_sha256=RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256,
    )
    previous_record = first_record

    def load_plan() -> Mapping[str, object]:
        nonlocal previous_record
        current_selection, current_record, current_document = (
            reopen_red_living_dex_development_selection(
                store,
                ordinal,
                binding=binding,
            )
        )
        if current_selection != selection or current_record is previous_record:
            raise RedLivingDexClusteredDevelopmentExecutionError(
                "Red development plan reauthentication differs"
            )
        previous_record = current_record
        return current_document

    return _PreparedRedLivingDexDevelopmentInvocation(
        selection=selection,
        root=root,
        producer_execution_identity=producer_identity,
        outer_execution_identity=outer,
        claim_registry=fixed_account_claim_registry_root(),
        model=model,
        load_plan=load_plan,
    )


def _require_source_commit(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development producer source commit differs"
        )
    return value


def _require_outer_join(
    selection: RedLivingDexClusteredDevelopmentSelection,
    *,
    binding: RedLivingDexDevelopmentPlanBinding,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity,
    outer_execution_identity: ClaimFirstExecutionIdentity,
) -> None:
    if (
        outer_execution_identity.producer_plan_sha256 != selection.private_plan_sha256
        or outer_execution_identity.producer_private_plan_sha256 != selection.private_plan_sha256
        or outer_execution_identity.producer_manifest_sha256 != binding.plan_manifest_sha256
        or outer_execution_identity.producer_execution_identity_sha256
        != producer_execution_identity.identity_sha256
        or outer_execution_identity.slot_sha256 != selection.slot_sha256
        or outer_execution_identity.recipe_sha256 != selection.recipe_sha256
        or outer_execution_identity.logical_root_sha256 != selection.logical_root_sha256
        or outer_execution_identity.physical_root_sha256 != selection.physical_root_sha256
        or outer_execution_identity.runner_sha256 != RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development outer identity differs"
        )


def _require_root_join(
    selection: RedLivingDexClusteredDevelopmentSelection,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    if (
        selection.logical_root_sha256 != root.root_consumption_sha256
        or selection.physical_root_sha256 != root.physical_root_sha256
        or selection.root_state_sha256 != root.state_sha256
        or selection.root_envelope_sha256 != root.envelope_sha256
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError("Red development root differs")


def _require_resolved_runtime(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    resolved: RedLivingDexResolvedSetupSlot,
) -> None:
    if not isinstance(resolved, RedLivingDexResolvedSetupSlot):
        raise TypeError("Red development resolver returned another runtime")
    resolved.__post_init__()
    frozen.require_resolved_recipe(resolved.recipe)
    if (
        resolved.producer_execution_identity.identity_sha256
        != frozen.producer_execution_identity_sha256
    ):
        raise RedLivingDexClusteredDevelopmentExecutionError(
            "Red development runtime identity differs"
        )


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexClusteredDevelopmentExecutionError(f"Red development {subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_EXECUTION_SCHEMA",
    "RED_LIVING_DEX_CLUSTERED_DEVELOPMENT_EXECUTION_SHA256",
    "RedLivingDexClusteredDevelopmentExecutionError",
    "RedLivingDexClusteredDevelopmentPreflightReceipt",
    "RedLivingDexClusteredDevelopmentReceipt",
    "RedLivingDexDevelopmentRootLoader",
    "execute_red_living_dex_development_assignment",
    "preflight_red_living_dex_development_assignment",
    "preflight_red_living_dex_clustered_development_assignment",
    "run_red_living_dex_clustered_development_assignment",
]
