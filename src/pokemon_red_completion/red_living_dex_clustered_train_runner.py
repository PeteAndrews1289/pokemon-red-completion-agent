"""Train-only consumer for the frozen Red clustered living-Dex schedule.

The private schedule contains eight train and four untouched development
assignments.  This module makes only train ordinals addressable, joins one
selected root to its exact Red template, reuses the durable setup pair claim,
and delegates behavior commitment and selected-arm outcome collection to the
title-neutral causal journal.  Development rows are never accepted by the
execution API, and no teacher or counterfactual outcome is available here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
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
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalFailpoint,
    LivingDexCausalReceipt,
    materialize_living_dex_causal_example,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
)
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
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    RedLivingDexClaimedSetupResolver,
    RedLivingDexClaimFirstFailpoint,
    RedLivingDexClaimFirstReceipt,
    RedLivingDexResolvedSetupSlot,
    run_red_living_dex_claim_first_setup_slot,
)
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
    RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_ID,
    RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_KIND,
    validate_red_living_dex_clustered_private_plan,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_admission import (
    FrozenRedLivingDexSetupSlot,
    authenticate_frozen_red_living_dex_clustered_train_slot,
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

RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SCHEMA = (
    "pokemon.red.living-dex-clustered-train-runner.v1"
)
RED_LIVING_DEX_CLUSTERED_TRAIN_RECEIPT_SCHEMA = (
    "pokemon.red.living-dex-clustered-train-receipt.v1"
)
RED_LIVING_DEX_CLUSTERED_TRAIN_PREFLIGHT_SCHEMA = (
    "pokemon.red.living-dex-clustered-train-preflight.v1"
)
RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SHA256 = canonical_sha256(
    {
        "behavior_commitment": "durable-before-controller-release",
        "counterfactual_targets": 0,
        "development_ordinals_addressable": 0,
        "lineage_identity": "frozen-upstream-episode-lineage",
        "logical_and_physical_claim": "atomic",
        "schema": RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SCHEMA,
        "selected_arm_outcome_only": True,
        "train_ordinals": list(range(8)),
    }
)
RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_RUNNER_SHA256 = canonical_sha256(
    {
        "behavior_commitment": "durable-before-controller-release",
        "counterfactual_targets": 0,
        "development_ordinals_addressable": 0,
        "lineage_identity": "frozen-upstream-episode-lineage",
        "logical_and_physical_claim": "atomic",
        "plan_record_id": RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_ID,
        "plan_record_kind": (
            RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_KIND
        ),
        "schema": "pokemon.red.living-dex-clustered-successor-train-runner.v1",
        "selected_arm_outcome_only": True,
        "train_ordinals": list(range(16)),
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexClusteredTrainRunnerError(f"{subject} differs")
    return value


def _require_sha256(value: object, subject: str) -> str:
    return _digest(value, subject)


class RedLivingDexClusteredTrainRunnerError(RuntimeError):
    """The frozen train assignment cannot be authenticated or executed."""


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredTrainPlanBinding:
    """Exact immutable schedule record admitted by this runner version."""

    private_plan_sha256: str
    plan_manifest_sha256: str
    plan_record_sha256: str
    schedule_sha256: str
    policy_sha256: str
    record_id: str = RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID
    record_kind: str = RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND
    train_scenarios: int = 8
    development_scenarios: int = 4
    causal_runner_sha256: str = RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SHA256

    def __post_init__(self) -> None:
        for value, subject in (
            (self.private_plan_sha256, "private plan"),
            (self.plan_manifest_sha256, "plan manifest"),
            (self.plan_record_sha256, "plan record"),
            (self.schedule_sha256, "schedule"),
            (self.policy_sha256, "policy"),
            (self.causal_runner_sha256, "causal runner"),
        ):
            _require_sha256(value, subject)
        if (
            not isinstance(self.record_id, str)
            or _RECORD_NAME.fullmatch(self.record_id) is None
            or not isinstance(self.record_kind, str)
            or _RECORD_NAME.fullmatch(self.record_kind) is None
            or type(self.train_scenarios) is not int  # noqa: E721
            or self.train_scenarios <= 0
            or type(self.development_scenarios) is not int  # noqa: E721
            or self.development_scenarios <= 0
        ):
            raise RedLivingDexClusteredTrainRunnerError(
                "clustered train plan bounds differ"
            )


FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN = (
    RedLivingDexClusteredTrainPlanBinding(
        private_plan_sha256=(
            "2a0462b8ff6f5ec6504a68bf6f801c644583bd6cf7620287cb0bcfdbeb5b567d"
        ),
        plan_manifest_sha256=(
            "03d6802fe801b5607d75209da7e83c37a3ce48a86f9ac7b4d11dbbd050a0ec00"
        ),
        plan_record_sha256=(
            "94fc99a1da9ea48250b4eb460dfa2674adcfaa48d49b4419f414b9c14a190daa"
        ),
        schedule_sha256=(
            "35c00f382b5cd0f52b5231f0114eee7f423beb49c9fe4235ffe840fcc51dc905"
        ),
        policy_sha256=(
            "dc72fb9449f7279c12b673b266e0973d01b62577f99d22ec7fdb14fceb8589be"
        ),
    )
)


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredTrainSelection:
    """One selected train row, with private identities kept out of repr."""

    ordinal: int
    template_ordinal: int
    private_plan_sha256: str
    recipe_sha256: str
    slot_sha256: str
    logical_root_sha256: str = field(repr=False)
    physical_root_sha256: str = field(repr=False)
    root_state_sha256: str = field(repr=False)
    root_envelope_sha256: str = field(repr=False)
    context_identity_sha256: str = field(repr=False)
    upstream_lineage_sha256: str = field(repr=False)
    train_scenarios: int = field(default=8, repr=False)
    causal_runner_sha256: str = field(
        default=RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SHA256,
        repr=False,
    )

    def __post_init__(self) -> None:
        if (
            type(self.train_scenarios) is not int  # noqa: E721
            or self.train_scenarios <= 0
            or type(self.ordinal) is not int  # noqa: E721
            or not 0 <= self.ordinal < self.train_scenarios
        ):
            raise RedLivingDexClusteredTrainRunnerError(
                "development assignment is structurally inaccessible"
            )
        if (
            type(self.template_ordinal) is not int  # noqa: E721
            or not 0 <= self.template_ordinal < 15
        ):
            raise RedLivingDexClusteredTrainRunnerError(
                "selected Red template ordinal differs"
            )
        for value, subject in (
            (self.private_plan_sha256, "selected private plan"),
            (self.recipe_sha256, "selected recipe"),
            (self.slot_sha256, "selected slot"),
            (self.logical_root_sha256, "selected logical root"),
            (self.physical_root_sha256, "selected physical root"),
            (self.root_state_sha256, "selected root state"),
            (self.root_envelope_sha256, "selected root envelope"),
            (self.context_identity_sha256, "selected context"),
            (self.upstream_lineage_sha256, "selected upstream lineage"),
            (self.causal_runner_sha256, "selected causal runner"),
        ):
            _require_sha256(value, subject)

    def public_dict(self) -> dict[str, object]:
        return {
            "development_accessible": False,
            "ordinal": self.ordinal,
            "partition": "train",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "template_ordinal": self.template_ordinal,
        }


RedLivingDexClusteredRootLoader = Callable[
    [RedLivingDexClusteredTrainSelection],
    RedLivingDexAuthenticatedSetupRoot,
]


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredTrainReceipt:
    """Path-free terminal view of one selected train assignment."""

    selection: RedLivingDexClusteredTrainSelection = field(repr=False)
    setup: RedLivingDexClaimFirstReceipt
    causal: LivingDexCausalReceipt | None

    def __post_init__(self) -> None:
        if not isinstance(self.selection, RedLivingDexClusteredTrainSelection):
            raise TypeError("clustered train receipt needs its selection")
        self.selection.__post_init__()
        if not isinstance(self.setup, RedLivingDexClaimFirstReceipt):
            raise TypeError("clustered train receipt needs its setup receipt")
        self.setup.__post_init__()
        if self.setup.frozen.ordinal != self.selection.ordinal:
            raise RedLivingDexClusteredTrainRunnerError(
                "clustered train setup joined another assignment"
            )
        if self.causal is None:
            if self.setup.terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
                raise RedLivingDexClusteredTrainRunnerError(
                    "complete clustered setup lacks its causal terminal"
                )
            return
        if not isinstance(self.causal, LivingDexCausalReceipt):
            raise TypeError("clustered train receipt causal value differs")
        self.causal.__post_init__()
        if (
            self.causal.scenario.identity.partition != "train"
            or self.causal.scenario.identity.lineage_sha256
            != self.selection.upstream_lineage_sha256
        ):
            raise RedLivingDexClusteredTrainRunnerError(
                "clustered causal example crossed partition or lineage"
            )

    @property
    def causal_train_example_recorded(self) -> bool:
        return self.causal is not None and self.causal.example is not None

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_commitments": 0 if self.causal is None else 1,
            "causal_train_example_recorded": self.causal_train_example_recorded,
            "counterfactual_targets": 0,
            "development_outcomes_opened": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "ordinal": self.selection.ordinal,
            "partition": "train",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "schema": RED_LIVING_DEX_CLUSTERED_TRAIN_RECEIPT_SCHEMA,
            "selected_candidate_target_only": (
                self.causal is not None and self.causal.example is not None
            ),
            "teacher_queries": 0,
            "unselected_action_targets": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredTrainPreflightReceipt:
    """ROM-free proof that one train row can reach the atomic claim gate."""

    selection: RedLivingDexClusteredTrainSelection = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.selection, RedLivingDexClusteredTrainSelection):
            raise TypeError("clustered train preflight needs its selection")
        self.selection.__post_init__()

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_commitments": 0,
            "collection_authorized": False,
            "controller_actions": 0,
            "counterfactual_targets": 0,
            "development_outcomes_opened": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "ordinal": self.selection.ordinal,
            "partition": "train",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_CLUSTERED_TRAIN_PREFLIGHT_SCHEMA,
            "selected_root_reads": 1,
            "status": "one_train_assignment_ready_before_claim_or_emulator",
            "teacher_queries": 0,
            "unselected_action_targets": 0,
        }


def load_red_living_dex_clustered_train_selection(
    store: PrivateArtifactRoot,
    ordinal: int,
    *,
    binding: RedLivingDexClusteredTrainPlanBinding = (
        FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN
    ),
) -> RedLivingDexClusteredTrainSelection:
    """Reopen one exact sealed train row without constructing a runtime."""

    selection, _record, _document = _reopen_clustered_train_plan(
        store,
        ordinal,
        binding=binding,
    )
    return selection


def authenticate_red_living_dex_clustered_train_selection(
    document: Mapping[str, object],
    ordinal: int,
    *,
    binding: RedLivingDexClusteredTrainPlanBinding,
) -> RedLivingDexClusteredTrainSelection:
    """Strictly select one train assignment from already reopened bytes."""

    if not isinstance(binding, RedLivingDexClusteredTrainPlanBinding):
        raise TypeError("clustered train selection needs its plan binding")
    binding.__post_init__()
    if (
        type(ordinal) is not int  # noqa: E721
        or not 0 <= ordinal < binding.train_scenarios
    ):
        raise RedLivingDexClusteredTrainRunnerError(
            "development assignment is structurally inaccessible"
        )
    try:
        schedule = validate_red_living_dex_clustered_private_plan(
            document,
            expected_schedule_sha256=binding.schedule_sha256,
            expected_policy_sha256=binding.policy_sha256,
        )
        if document.get("private_plan_sha256") != binding.private_plan_sha256:
            raise ValueError("private plan differs")
        assignments = document.get("assignments")
        if (
            schedule.policy.train_scenarios != binding.train_scenarios
            or schedule.policy.development_scenarios
            != binding.development_scenarios
            or not isinstance(assignments, list)
            or len(assignments)
            != binding.train_scenarios + binding.development_scenarios
        ):
            raise ValueError("assignments differ")
        selected = assignments[ordinal]
        if not isinstance(selected, Mapping):
            raise ValueError("selected assignment differs")
        if selected.get("ordinal") != ordinal or selected.get("partition") != "train":
            raise ValueError("selected partition differs")
        return RedLivingDexClusteredTrainSelection(
            ordinal=ordinal,
            template_ordinal=_integer(
                selected.get("template_ordinal"),
                "selected template ordinal",
            ),
            private_plan_sha256=binding.private_plan_sha256,
            recipe_sha256=_digest(selected.get("recipe_sha256"), "selected recipe"),
            slot_sha256=_digest(selected.get("template_sha256"), "selected slot"),
            logical_root_sha256=_digest(
                selected.get("root_consumption_sha256"),
                "selected logical root",
            ),
            physical_root_sha256=_digest(
                selected.get("physical_root_sha256"),
                "selected physical root",
            ),
            root_state_sha256=_digest(
                selected.get("root_state_sha256"),
                "selected root state",
            ),
            root_envelope_sha256=_digest(
                selected.get("root_envelope_sha256"),
                "selected root envelope",
            ),
            context_identity_sha256=_digest(
                selected.get("context_identity_sha256"),
                "selected context",
            ),
            upstream_lineage_sha256=_digest(
                selected.get("lineage_sha256"),
                "selected upstream lineage",
            ),
            train_scenarios=binding.train_scenarios,
            causal_runner_sha256=binding.causal_runner_sha256,
        )
    except RedLivingDexClusteredTrainRunnerError:
        raise
    except (TypeError, ValueError):
        raise RedLivingDexClusteredTrainRunnerError(
            "clustered train plan authentication failed"
        ) from None


def run_red_living_dex_clustered_train_assignment(
    *,
    selection: RedLivingDexClusteredTrainSelection,
    store: PrivateArtifactRoot,
    plan_loader: Callable[[], Mapping[str, object]],
    root: RedLivingDexAuthenticatedSetupRoot,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    resolver: RedLivingDexClaimedSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    setup_failpoint: RedLivingDexClaimFirstFailpoint | None = None,
    causal_failpoint: LivingDexCausalFailpoint | None = None,
) -> RedLivingDexClusteredTrainReceipt:
    """Execute or recover one train row through the existing durable journals."""

    if not isinstance(selection, RedLivingDexClusteredTrainSelection):
        raise TypeError("clustered train run needs its selected assignment")
    selection.__post_init__()
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("clustered train run needs its private store")
    if not callable(plan_loader):
        raise TypeError("clustered train run needs its immutable plan loader")
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("clustered train run needs its authenticated root")
    root.__post_init__()
    if not isinstance(
        producer_execution_identity,
        RedLivingDexSetupExecutionIdentity,
    ):
        raise TypeError("clustered train run needs its producer execution identity")
    producer_execution_identity.__post_init__()
    if not isinstance(outer_execution_identity, ClaimFirstExecutionIdentity):
        raise TypeError("clustered train run needs its current execution identity")
    outer_execution_identity.__post_init__()
    if not isinstance(resolver, RedLivingDexClaimedSetupResolver):
        raise TypeError("clustered train run needs its cold Red resolver")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("clustered train run needs the comprehensive effect meter")
    if not isinstance(claim_registry, Path):
        raise TypeError("clustered train run needs the account claim registry")
    _require_root_join(selection, root)

    first_document = plan_loader()
    frozen = authenticate_frozen_red_living_dex_clustered_train_slot(
        first_document,
        expected_private_plan_sha256=selection.private_plan_sha256,
        ordinal=selection.ordinal,
        root=root,
        producer_execution_identity=producer_execution_identity,
        expected_runtime_identity_sha256=_digest(
            first_document.get("runtime_identity_sha256"),
            "producer runtime identity",
        ),
    )
    _require_frozen_and_outer_join(
        selection,
        frozen=frozen,
        outer=outer_execution_identity,
    )

    setup = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=plan_loader,
        expected_producer_plan_sha256=selection.private_plan_sha256,
        ordinal=selection.ordinal,
        root=root,
        outer_execution_identity=outer_execution_identity,
        resolver=resolver,
        meter=meter,
        claim_registry=claim_registry,
        producer_execution_identity=producer_execution_identity,
        failpoint=setup_failpoint,
    )
    if setup.terminal.status is not LivingDexCaptureSetupStatus.COMPLETE:
        return RedLivingDexClusteredTrainReceipt(selection, setup, None)
    capture = setup.capture
    if capture is None:
        raise RedLivingDexClusteredTrainRunnerError(
            "complete clustered setup lacks its validated capture"
        )
    setup_pair = outer_execution_identity.root_pair(stage="setup-capture")

    @contextmanager
    def resolve_runtime():  # type: ignore[no-untyped-def]
        before = meter.checkpoint()
        frozen.reauthenticate(plan_loader(), root=root)
        if meter.checkpoint() != before:
            raise RedLivingDexClusteredTrainRunnerError(
                "clustered plan reauthentication changed protected effects"
            )
        scope = resolver(frozen, root, setup_pair, meter=meter)
        if meter.checkpoint() != before:
            raise RedLivingDexClusteredTrainRunnerError(
                "clustered cold resolver changed protected effects"
            )
        with scope as resolved:
            _require_resolved_slot(frozen, resolved)
            yield resolved

    scenario = build_red_living_dex_causal_scenario_from_capture(
        capture,
        setup_execution_identity=producer_execution_identity,
        runtime_resolver=resolve_runtime,
        meter=meter,
        setup_terminal_sha256=canonical_sha256(setup.terminal.private_dict()),
        setup_pair_claim_sha256=setup_pair.claim_sha256,
        causal_source_commit=outer_execution_identity.source_commit,
        causal_runner_sha256=selection.causal_runner_sha256,
        upstream_lineage_sha256=selection.upstream_lineage_sha256,
    )
    causal = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=claim_registry,
        failpoint=causal_failpoint,
    )
    return RedLivingDexClusteredTrainReceipt(selection, setup, causal)


def execute_red_living_dex_clustered_train_assignment(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexAuthenticatedConsumer,
    ordinal: int,
    root_loader: RedLivingDexClusteredRootLoader,
    rom_path: Path,
    meter: RedLivingDexSetupEffectMeter,
    binding: RedLivingDexClusteredTrainPlanBinding = (
        FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN
    ),
) -> RedLivingDexClusteredTrainReceipt:
    """Production bootstrap for one exact train row; no development API exists."""

    if not isinstance(project_root, Path):
        raise TypeError("clustered train invocation needs a project Path")
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("clustered train invocation needs its private store")
    if not isinstance(consumer, RedLivingDexAuthenticatedConsumer):
        raise TypeError("clustered train invocation needs its authenticated consumer")
    consumer.__post_init__()
    if not callable(root_loader):
        raise TypeError("clustered train invocation needs one selected-root loader")
    if not isinstance(rom_path, Path):
        raise TypeError("clustered train invocation needs its Red ROM Path")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("clustered train invocation needs its protected-effect meter")

    selection, first_record, first_document = _reopen_clustered_train_plan(
        store,
        ordinal,
        binding=binding,
    )
    root = root_loader(selection)
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("clustered selected-root loader returned another type")
    root.__post_init__()
    _require_root_join(selection, root)
    runtime = authenticate_red_living_dex_execution_runtime(
        project_root,
        _digest(
            first_document.get("runtime_identity_sha256"),
            "producer runtime identity",
        ),
    )
    producer_identity = compose_red_living_dex_setup_execution_identity(
        source_commit=_string(
            first_document.get("source_commit"),
            "producer source commit",
        ),
        source_bundle_sha256=_digest(
            first_document.get("source_bundle_sha256"),
            "producer source bundle",
        ),
        route_registry_sha256=_digest(
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
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )
    resolver = RedLivingDexLateProductionResolver(
        rom_path=rom_path,
        producer_execution_identity=producer_identity,
    )
    previous_record = first_record

    def load_plan() -> Mapping[str, object]:
        nonlocal previous_record
        current_selection, record, document = _reopen_clustered_train_plan(
            store,
            ordinal,
            binding=binding,
        )
        if record is previous_record or current_selection != selection:
            raise RedLivingDexClusteredTrainRunnerError(
                "clustered plan reauthentication differs"
            )
        previous_record = record
        return document

    return run_red_living_dex_clustered_train_assignment(
        selection=selection,
        store=store,
        plan_loader=load_plan,
        root=root,
        producer_execution_identity=producer_identity,
        outer_execution_identity=outer,
        resolver=resolver,
        meter=meter,
        claim_registry=fixed_account_claim_registry_root(),
    )


def preflight_red_living_dex_clustered_train_assignment(
    project_root: Path,
    store: PrivateArtifactRoot,
    *,
    consumer: RedLivingDexAuthenticatedConsumer,
    ordinal: int,
    root_loader: RedLivingDexClusteredRootLoader,
    meter: RedLivingDexSetupEffectMeter,
    binding: RedLivingDexClusteredTrainPlanBinding = (
        FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN
    ),
) -> RedLivingDexClusteredTrainPreflightReceipt:
    """Authenticate one row and availability without a ROM or emulator instance."""

    if not isinstance(project_root, Path):
        raise TypeError("clustered train preflight needs a project Path")
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("clustered train preflight needs its private store")
    if not isinstance(consumer, RedLivingDexAuthenticatedConsumer):
        raise TypeError("clustered train preflight needs its authenticated consumer")
    consumer.__post_init__()
    if not callable(root_loader):
        raise TypeError("clustered train preflight needs one selected-root loader")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("clustered train preflight needs its protected-effect meter")
    before = meter.checkpoint()
    selection, _record, document = _reopen_clustered_train_plan(
        store,
        ordinal,
        binding=binding,
    )
    root = root_loader(selection)
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("clustered selected-root loader returned another type")
    root.__post_init__()
    _require_root_join(selection, root)
    runtime = authenticate_red_living_dex_execution_runtime(
        project_root,
        _digest(
            document.get("runtime_identity_sha256"),
            "producer runtime identity",
        ),
    )
    producer_identity = compose_red_living_dex_setup_execution_identity(
        source_commit=_string(
            document.get("source_commit"),
            "producer source commit",
        ),
        source_bundle_sha256=_digest(
            document.get("source_bundle_sha256"),
            "producer source bundle",
        ),
        route_registry_sha256=_digest(
            document.get("route_registry_sha256"),
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
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )
    frozen = authenticate_frozen_red_living_dex_clustered_train_slot(
        document,
        expected_private_plan_sha256=selection.private_plan_sha256,
        ordinal=selection.ordinal,
        root=root,
        producer_execution_identity=producer_identity,
        expected_runtime_identity_sha256=runtime.sha256,
    )
    _require_frozen_and_outer_join(selection, frozen=frozen, outer=outer)
    claim_registry = fixed_account_claim_registry_root()
    if not observe_claim_first_pair_availability(
        claim_registry,
        selection.logical_root_sha256,
        selection.physical_root_sha256,
    ):
        raise RedLivingDexClusteredTrainRunnerError(
            "clustered train root pair is unavailable"
        )
    if meter.checkpoint() != before:
        raise RedLivingDexClusteredTrainRunnerError(
            "clustered train preflight changed protected effects"
        )
    return RedLivingDexClusteredTrainPreflightReceipt(selection)


def _reopen_clustered_train_plan(
    store: PrivateArtifactRoot,
    ordinal: int,
    *,
    binding: RedLivingDexClusteredTrainPlanBinding,
) -> tuple[
    RedLivingDexClusteredTrainSelection,
    PrivateSealedRecord,
    Mapping[str, object],
]:
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("clustered train plan reopen needs its private store")
    if not isinstance(binding, RedLivingDexClusteredTrainPlanBinding):
        raise TypeError("clustered train plan reopen needs its binding")
    binding.__post_init__()
    record = store.find_sealed_record(
        binding.record_id,
        expected_kind=binding.record_kind,
    )
    if (
        record is None
        or record.summary.manifest_sha256 != binding.plan_manifest_sha256
        or record.summary.record_sha256 != binding.plan_record_sha256
    ):
        raise RedLivingDexClusteredTrainRunnerError(
            "clustered train plan record differs"
        )
    document = record.read()
    selection = authenticate_red_living_dex_clustered_train_selection(
        document,
        ordinal,
        binding=binding,
    )
    return selection, record, document


def _require_root_join(
    selection: RedLivingDexClusteredTrainSelection,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    if (
        root.root_consumption_sha256 != selection.logical_root_sha256
        or root.physical_root_sha256 != selection.physical_root_sha256
        or root.state_sha256 != selection.root_state_sha256
        or root.envelope_sha256 != selection.root_envelope_sha256
    ):
        raise RedLivingDexClusteredTrainRunnerError(
            "clustered selected root differs"
        )


def _require_frozen_and_outer_join(
    selection: RedLivingDexClusteredTrainSelection,
    *,
    frozen: FrozenRedLivingDexSetupSlot,
    outer: ClaimFirstExecutionIdentity,
) -> None:
    if (
        frozen.ordinal != selection.ordinal
        or frozen.template_ordinal != selection.template_ordinal
        or frozen.producer_plan_sha256 != selection.private_plan_sha256
        or frozen.recipe_sha256 != selection.recipe_sha256
        or frozen.slot_sha256 != selection.slot_sha256
        or frozen.logical_root_sha256 != selection.logical_root_sha256
        or frozen.physical_root_sha256 != selection.physical_root_sha256
        or outer.producer_plan_sha256 != selection.private_plan_sha256
        or outer.producer_private_plan_sha256 != selection.private_plan_sha256
        or outer.producer_execution_identity_sha256
        != frozen.producer_execution_identity_sha256
        or outer.slot_sha256 != selection.slot_sha256
        or outer.recipe_sha256 != selection.recipe_sha256
        or outer.logical_root_sha256 != selection.logical_root_sha256
        or outer.physical_root_sha256 != selection.physical_root_sha256
        or outer.runner_sha256 != RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256
        or outer.title_adapter_sha256 != RED_LIVING_DEX_TITLE_ADAPTER_SHA256
        or outer.runtime_factory_sha256 != RED_LIVING_DEX_RUNTIME_FACTORY_SHA256
    ):
        raise RedLivingDexClusteredTrainRunnerError(
            "clustered train execution identity differs"
        )


def _require_resolved_slot(
    frozen: FrozenRedLivingDexSetupSlot,
    resolved: RedLivingDexResolvedSetupSlot,
) -> None:
    if not isinstance(resolved, RedLivingDexResolvedSetupSlot):
        raise TypeError("clustered resolver returned another runtime type")
    resolved.__post_init__()
    if (
        resolved.recipe.recipe_sha256 != frozen.recipe_sha256
        or resolved.recipe.slot_sha256 != frozen.slot_sha256
        or resolved.producer_execution_identity.identity_sha256
        != frozen.producer_execution_identity_sha256
        or resolved.title_adapter_sha256 != RED_LIVING_DEX_TITLE_ADAPTER_SHA256
        or resolved.runtime_factory_sha256 != RED_LIVING_DEX_RUNTIME_FACTORY_SHA256
    ):
        raise RedLivingDexClusteredTrainRunnerError(
            "clustered selected runtime identity differs"
        )


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexClusteredTrainRunnerError(f"{subject} differs")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexClusteredTrainRunnerError(f"{subject} differs")
    return value


__all__ = [
    "FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN",
    "RED_LIVING_DEX_CLUSTERED_TRAIN_RECEIPT_SCHEMA",
    "RED_LIVING_DEX_CLUSTERED_TRAIN_PREFLIGHT_SCHEMA",
    "RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SCHEMA",
    "RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SHA256",
    "RED_LIVING_DEX_CLUSTERED_SUCCESSOR_TRAIN_RUNNER_SHA256",
    "RedLivingDexClusteredRootLoader",
    "RedLivingDexClusteredTrainPlanBinding",
    "RedLivingDexClusteredTrainPreflightReceipt",
    "RedLivingDexClusteredTrainReceipt",
    "RedLivingDexClusteredTrainRunnerError",
    "RedLivingDexClusteredTrainSelection",
    "authenticate_red_living_dex_clustered_train_selection",
    "execute_red_living_dex_clustered_train_assignment",
    "load_red_living_dex_clustered_train_selection",
    "preflight_red_living_dex_clustered_train_assignment",
    "run_red_living_dex_clustered_train_assignment",
]
