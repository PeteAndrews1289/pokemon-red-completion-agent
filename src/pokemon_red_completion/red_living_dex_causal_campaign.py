"""Freeze and run one bounded Red setup-to-causal-example campaign.

The campaign is the missing composition seam between the already durable Red
setup capture and the title-neutral selected-arm journal.  Freezing is
action-free: it binds one unretired train recipe, its exact current setup
consumer, and the causal runner without opening a ROM or constructing a
runtime.  Execution first settles the claim-first setup and only then exposes
a *cold* Red resolver to the causal journal.  The resolver is entered after the
journal has claimed the causal root, committed its behavior policy, and chosen
one row, so no unselected runtime can be constructed.

This module does not fit a model, query a teacher, execute Crystal, open a
sealed benchmark, or replay the game.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    CLAIM_FIRST_EXECUTION_IDENTITY_SCHEMA,
    ClaimFirstExecutionIdentity,
    observe_claim_first_pair_availability,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalReceipt,
    materialize_living_dex_causal_example,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_adapter import (
    build_red_living_dex_causal_scenario_from_capture,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    RedLivingDexClaimedSetupResolver,
    RedLivingDexClaimFirstReceipt,
    RedLivingDexResolvedSetupSlot,
    run_red_living_dex_claim_first_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_admission import (
    FrozenRedLivingDexSetupSlot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)

RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_SCHEMA = (
    "pokemon.red.private-living-dex-causal-campaign-plan.v1"
)
RED_LIVING_DEX_CAUSAL_CAMPAIGN_RECEIPT_SCHEMA = (
    "pokemon.red.living-dex-causal-campaign-receipt.v1"
)
RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_ID = (
    "red-living-dex-causal-campaign-plan-v1"
)
RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_KIND = (
    "red_living_dex_causal_campaign_plan"
)
RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256 = canonical_sha256(
    {
        "causal_pair_claim_before_behavior": True,
        "complete_identity_free_menu_before_behavior": True,
        "independent_selected_outcome": True,
        "no_fit_or_promotion": True,
        "no_retry_after_controller_release": True,
        "schema": "pokemon.red.living-dex-causal-campaign-runner.v1",
        "selected_only_cold_runtime": True,
        "setup_pair_claim_before_runtime": True,
        "target_free_interruption": True,
        "title_neutral_learner_example": True,
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedLivingDexCausalCampaignError(RuntimeError):
    """One frozen Red causal campaign cannot be authenticated safely."""


@dataclass(frozen=True, slots=True)
class RedLivingDexFrozenCausalCampaign:
    """One private, action-free setup-to-example commitment."""

    outer_execution_identity: ClaimFirstExecutionIdentity = field(repr=False)
    ordinal: int
    producer_plan_sha256: str
    producer_execution_identity_sha256: str
    recipe_sha256: str
    slot_sha256: str
    logical_root_sha256: str
    physical_root_sha256: str
    root_state_sha256: str
    root_envelope_sha256: str
    partition: str
    retired_physical_root_sha256s: tuple[str, ...] = field(repr=False)
    retired_physical_roots_commitment_sha256: str
    retired_physical_root_count: int
    causal_source_commit: str
    causal_runner_sha256: str = RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256

    def __post_init__(self) -> None:
        if not isinstance(self.outer_execution_identity, ClaimFirstExecutionIdentity):
            raise TypeError("causal campaign needs its setup execution identity")
        self.outer_execution_identity.__post_init__()
        if type(self.ordinal) is not int or not 0 <= self.ordinal < 15:  # noqa: E721
            raise RedLivingDexCausalCampaignError("causal campaign ordinal differs")
        for value, subject in (
            (self.producer_plan_sha256, "producer plan"),
            (self.producer_execution_identity_sha256, "producer execution"),
            (self.recipe_sha256, "recipe"),
            (self.slot_sha256, "slot"),
            (self.logical_root_sha256, "logical root"),
            (self.physical_root_sha256, "physical root"),
            (self.root_state_sha256, "root state"),
            (self.root_envelope_sha256, "root envelope"),
            (
                self.retired_physical_roots_commitment_sha256,
                "retired-root commitment",
            ),
            (self.causal_runner_sha256, "causal runner"),
        ):
            _require_sha256(value, subject=subject)
        if self.logical_root_sha256 == self.physical_root_sha256:
            raise RedLivingDexCausalCampaignError(
                "causal campaign root identities collapse"
            )
        if self.partition != "train":
            raise RedLivingDexCausalCampaignError(
                "first causal campaign must use the train partition"
            )
        if not isinstance(self.retired_physical_root_sha256s, tuple) or (
            tuple(sorted(set(self.retired_physical_root_sha256s)))
            != self.retired_physical_root_sha256s
        ):
            raise RedLivingDexCausalCampaignError(
                "causal campaign retired-root inventory differs"
            )
        for value in self.retired_physical_root_sha256s:
            _require_sha256(value, subject="retired physical root")
        expected_retired_commitment = canonical_sha256(
            {
                "physical_root_sha256s": list(self.retired_physical_root_sha256s),
                "schema": "pokemon.red.private-retired-causal-setup-roots.v1",
            }
        )
        if (
            type(self.retired_physical_root_count) is not int  # noqa: E721
            or self.retired_physical_root_count
            != len(self.retired_physical_root_sha256s)
            or self.retired_physical_root_count < 1
            or self.retired_physical_roots_commitment_sha256
            != expected_retired_commitment
            or self.physical_root_sha256 in self.retired_physical_root_sha256s
        ):
            raise RedLivingDexCausalCampaignError(
                "causal campaign lacks an explicit retired-root exclusion"
            )
        if (
            not isinstance(self.causal_source_commit, str)
            or _GIT_COMMIT.fullmatch(self.causal_source_commit) is None
            or self.causal_source_commit
            != self.outer_execution_identity.source_commit
            or self.causal_runner_sha256
            != RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256
        ):
            raise RedLivingDexCausalCampaignError(
                "causal campaign current source differs"
            )
        outer = self.outer_execution_identity
        if (
            outer.runner_sha256 != RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256
            or outer.producer_plan_sha256 != self.producer_plan_sha256
            or outer.producer_execution_identity_sha256
            != self.producer_execution_identity_sha256
            or outer.recipe_sha256 != self.recipe_sha256
            or outer.slot_sha256 != self.slot_sha256
            or outer.logical_root_sha256 != self.logical_root_sha256
            or outer.physical_root_sha256 != self.physical_root_sha256
        ):
            raise RedLivingDexCausalCampaignError(
                "causal campaign setup identity differs"
            )

    @property
    def campaign_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "causal_runner_sha256": self.causal_runner_sha256,
            "causal_source_commit": self.causal_source_commit,
            "complete_menu_bound_before_behavior": True,
            "logical_root_sha256": self.logical_root_sha256,
            "no_fit_or_promotion": True,
            "no_retry_after_controller_release": True,
            "ordinal": self.ordinal,
            "outer_execution_identity": self.outer_execution_identity.private_dict(),
            "outer_execution_identity_sha256": (
                self.outer_execution_identity.identity_sha256
            ),
            "partition": self.partition,
            "physical_root_sha256": self.physical_root_sha256,
            "producer_execution_identity_sha256": (
                self.producer_execution_identity_sha256
            ),
            "producer_plan_sha256": self.producer_plan_sha256,
            "recipe_sha256": self.recipe_sha256,
            "retired_physical_root_count": self.retired_physical_root_count,
            "retired_physical_root_sha256s": list(
                self.retired_physical_root_sha256s
            ),
            "retired_physical_roots_commitment_sha256": (
                self.retired_physical_roots_commitment_sha256
            ),
            "root_envelope_sha256": self.root_envelope_sha256,
            "root_state_sha256": self.root_state_sha256,
            "schema": RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_SCHEMA,
            "selected_only_cold_runtime": True,
            "slot_sha256": self.slot_sha256,
            "teacher_queries": 0,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "action_free_freeze": True,
            "causal_examples": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "exact_menu_bound_before_behavior": True,
            "learner_labels": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "partition": self.partition,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "retired_root_exclusions": self.retired_physical_root_count,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_SCHEMA,
            "selected_slots": 1,
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexCausalCampaignReceipt:
    """Joined setup and selected-arm result for one frozen campaign."""

    plan: RedLivingDexFrozenCausalCampaign
    setup: RedLivingDexClaimFirstReceipt
    causal: LivingDexCausalReceipt | None

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RedLivingDexFrozenCausalCampaign):
            raise TypeError("causal campaign receipt needs its plan")
        self.plan.__post_init__()
        if not isinstance(self.setup, RedLivingDexClaimFirstReceipt):
            raise TypeError("causal campaign receipt needs its setup result")
        if self.causal is not None and not isinstance(self.causal, LivingDexCausalReceipt):
            raise TypeError("causal campaign receipt has another causal result")
        if (
            self.setup.frozen.recipe_sha256 != self.plan.recipe_sha256
            or self.setup.frozen.slot_sha256 != self.plan.slot_sha256
            or self.setup.frozen.logical_root_sha256 != self.plan.logical_root_sha256
            or self.setup.frozen.physical_root_sha256 != self.plan.physical_root_sha256
        ):
            raise RedLivingDexCausalCampaignError(
                "causal campaign receipt setup join differs"
            )
        setup_complete = (
            self.setup.terminal.status is LivingDexCaptureSetupStatus.COMPLETE
        )
        if setup_complete != (self.causal is not None):
            raise RedLivingDexCausalCampaignError(
                "causal campaign receipt completion join differs"
            )
        if self.causal is not None and (
            self.causal.scenario.identity.partition != self.plan.partition
            or self.causal.scenario.identity.runner_sha256
            != self.plan.causal_runner_sha256
            or self.causal.scenario.identity.source_commit
            != self.plan.causal_source_commit
        ):
            raise RedLivingDexCausalCampaignError(
                "causal campaign learner join differs"
            )

    def public_dict(self) -> dict[str, object]:
        causal = None if self.causal is None else self.causal.public_dict()
        return {
            "causal_train_example_recorded": bool(
                causal is not None and causal["causal_train_example_recorded"]
            ),
            "causal_disposition": (
                None if self.causal is None else self.causal.disposition.value
            ),
            "controller_actions_public": False,
            "model_fits": 0,
            "model_predictions": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "retry_allowed": bool(
                self.causal is not None and self.causal.retry_allowed
            ),
            "schema": RED_LIVING_DEX_CAUSAL_CAMPAIGN_RECEIPT_SCHEMA,
            "setup_status": self.setup.terminal.status.value,
            "teacher_queries": 0,
        }


RedLivingDexFrozenPlanLoader = Callable[[], Mapping[str, object]]


def freeze_red_living_dex_causal_campaign(
    store: PrivateArtifactRoot,
    *,
    frozen: FrozenRedLivingDexSetupSlot,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    retired_physical_root_sha256s: Sequence[str],
    claim_registry: Path,
) -> RedLivingDexFrozenCausalCampaign:
    """Persist exactly one action-free train campaign.

    At least one explicit retirement is mandatory so the consumed V2 selected
    root cannot be silently rediscovered under the successor campaign.
    """

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("causal campaign freeze needs a private artifact root")
    if not isinstance(frozen, FrozenRedLivingDexSetupSlot):
        raise TypeError("causal campaign freeze needs one frozen setup slot")
    frozen.__post_init__()
    if not isinstance(outer_execution_identity, ClaimFirstExecutionIdentity):
        raise TypeError("causal campaign freeze needs one setup consumer identity")
    outer_execution_identity.__post_init__()
    if not isinstance(claim_registry, Path):
        raise TypeError("causal campaign freeze needs an account claim registry")
    retired = tuple(retired_physical_root_sha256s)
    if not retired or len(retired) != len(set(retired)):
        raise RedLivingDexCausalCampaignError(
            "causal campaign retired-root set differs"
        )
    for value in retired:
        _require_sha256(value, subject="retired physical root")
    if frozen.physical_root_sha256 in retired:
        raise RedLivingDexCausalCampaignError(
            "causal campaign selected a retired physical root"
        )
    recipe = frozen.recipe_document()
    if recipe.get("partition") != "train":
        raise RedLivingDexCausalCampaignError(
            "causal campaign selected a non-train recipe"
        )
    pair = outer_execution_identity.root_pair(stage="setup-capture")
    if not observe_claim_first_pair_availability(
        claim_registry,
        pair.logical_root_sha256,
        pair.physical_root_sha256,
    ):
        raise RedLivingDexCausalCampaignError(
            "causal campaign selected an unavailable root pair"
        )
    plan = RedLivingDexFrozenCausalCampaign(
        outer_execution_identity=outer_execution_identity,
        ordinal=frozen.ordinal,
        producer_plan_sha256=frozen.producer_plan_sha256,
        producer_execution_identity_sha256=(
            frozen.producer_execution_identity_sha256
        ),
        recipe_sha256=frozen.recipe_sha256,
        slot_sha256=frozen.slot_sha256,
        logical_root_sha256=frozen.logical_root_sha256,
        physical_root_sha256=frozen.physical_root_sha256,
        root_state_sha256=frozen.root_state_sha256,
        root_envelope_sha256=frozen.root_envelope_sha256,
        partition="train",
        retired_physical_root_sha256s=tuple(sorted(retired)),
        retired_physical_roots_commitment_sha256=canonical_sha256(
            {
                "physical_root_sha256s": sorted(retired),
                "schema": "pokemon.red.private-retired-causal-setup-roots.v1",
            }
        ),
        retired_physical_root_count=len(retired),
        causal_source_commit=outer_execution_identity.source_commit,
    )
    sealed = store.publish_sealed_record(
        RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_ID,
        kind=RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_KIND,
        record=plan.private_dict(),
    )
    if sealed.read() != plan.private_dict():
        raise RedLivingDexCausalCampaignError(
            "causal campaign plan publication differs"
        )
    return plan


def load_red_living_dex_causal_campaign(
    store: PrivateArtifactRoot,
) -> RedLivingDexFrozenCausalCampaign:
    """Restore the one immutable private campaign plan."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("causal campaign load needs a private artifact root")
    sealed = store.find_sealed_record(
        RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_ID,
        expected_kind=RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_KIND,
    )
    if sealed is None:
        raise RedLivingDexCausalCampaignError("causal campaign plan is absent")
    return restore_red_living_dex_causal_campaign(sealed.read())


def restore_red_living_dex_causal_campaign(
    document: Mapping[str, object],
) -> RedLivingDexFrozenCausalCampaign:
    """Strictly restore one canonical campaign plan document."""

    expected = {
        "causal_runner_sha256",
        "causal_source_commit",
        "complete_menu_bound_before_behavior",
        "logical_root_sha256",
        "no_fit_or_promotion",
        "no_retry_after_controller_release",
        "ordinal",
        "outer_execution_identity",
        "outer_execution_identity_sha256",
        "partition",
        "physical_root_sha256",
        "producer_execution_identity_sha256",
        "producer_plan_sha256",
        "recipe_sha256",
        "retired_physical_root_count",
        "retired_physical_root_sha256s",
        "retired_physical_roots_commitment_sha256",
        "root_envelope_sha256",
        "root_state_sha256",
        "schema",
        "selected_only_cold_runtime",
        "slot_sha256",
        "teacher_queries",
    }
    if not isinstance(document, Mapping) or set(document) != expected:
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign fields differ"
        )
    if (
        document["schema"] != RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_SCHEMA
        or document["complete_menu_bound_before_behavior"] is not True
        or document["selected_only_cold_runtime"] is not True
        or document["no_retry_after_controller_release"] is not True
        or document["no_fit_or_promotion"] is not True
        or document["teacher_queries"] != 0
    ):
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign contract differs"
        )
    outer_document = document["outer_execution_identity"]
    if not isinstance(outer_document, Mapping):
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign setup identity differs"
        )
    outer = _restore_outer_identity(outer_document)
    if outer.identity_sha256 != document["outer_execution_identity_sha256"]:
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign setup identity digest differs"
        )
    try:
        retired_raw = document["retired_physical_root_sha256s"]
        if not isinstance(retired_raw, list) or any(
            not isinstance(item, str) for item in retired_raw
        ):
            raise TypeError("retired roots differ")
        plan = RedLivingDexFrozenCausalCampaign(
            outer_execution_identity=outer,
            ordinal=_integer(document["ordinal"], subject="ordinal"),
            producer_plan_sha256=_string(
                document["producer_plan_sha256"], subject="producer plan"
            ),
            producer_execution_identity_sha256=_string(
                document["producer_execution_identity_sha256"],
                subject="producer execution",
            ),
            recipe_sha256=_string(document["recipe_sha256"], subject="recipe"),
            slot_sha256=_string(document["slot_sha256"], subject="slot"),
            logical_root_sha256=_string(
                document["logical_root_sha256"], subject="logical root"
            ),
            physical_root_sha256=_string(
                document["physical_root_sha256"], subject="physical root"
            ),
            root_state_sha256=_string(
                document["root_state_sha256"], subject="root state"
            ),
            root_envelope_sha256=_string(
                document["root_envelope_sha256"], subject="root envelope"
            ),
            partition=_string(document["partition"], subject="partition"),
            retired_physical_root_sha256s=tuple(retired_raw),
            retired_physical_roots_commitment_sha256=_string(
                document["retired_physical_roots_commitment_sha256"],
                subject="retired roots",
            ),
            retired_physical_root_count=_integer(
                document["retired_physical_root_count"],
                subject="retired-root count",
            ),
            causal_source_commit=_string(
                document["causal_source_commit"], subject="causal source"
            ),
            causal_runner_sha256=_string(
                document["causal_runner_sha256"], subject="causal runner"
            ),
        )
    except (TypeError, ValueError):
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign values differ"
        ) from None
    if plan.private_dict() != dict(document):
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign does not replay"
        )
    return plan


def run_red_living_dex_causal_campaign(
    plan: RedLivingDexFrozenCausalCampaign,
    *,
    store: PrivateArtifactRoot,
    plan_loader: RedLivingDexFrozenPlanLoader,
    frozen: FrozenRedLivingDexSetupSlot,
    root: RedLivingDexAuthenticatedSetupRoot,
    resolver: RedLivingDexClaimedSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
) -> RedLivingDexCausalCampaignReceipt:
    """Execute or recover one setup, then materialize only its selected arm."""

    if not isinstance(plan, RedLivingDexFrozenCausalCampaign):
        raise TypeError("causal campaign run needs its frozen plan")
    plan.__post_init__()
    if not isinstance(frozen, FrozenRedLivingDexSetupSlot):
        raise TypeError("causal campaign run needs its frozen setup slot")
    frozen.__post_init__()
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("causal campaign run needs its authenticated root")
    root.__post_init__()
    if not callable(plan_loader) or not isinstance(
        resolver, RedLivingDexClaimedSetupResolver
    ):
        raise TypeError("causal campaign run needs cold plan and runtime resolvers")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("causal campaign run needs the comprehensive effect meter")
    if not isinstance(store, PrivateArtifactRoot) or not isinstance(claim_registry, Path):
        raise TypeError("causal campaign run needs private store and claim registry")
    if load_red_living_dex_causal_campaign(store) != plan:
        raise RedLivingDexCausalCampaignError(
            "causal campaign differs from the immutable stored plan"
        )
    _require_frozen_join(plan, frozen, root=root)

    setup = run_red_living_dex_claim_first_setup_slot(
        store,
        plan_loader=plan_loader,
        expected_producer_plan_sha256=plan.producer_plan_sha256,
        ordinal=plan.ordinal,
        root=root,
        outer_execution_identity=plan.outer_execution_identity,
        resolver=resolver,
        meter=meter,
        claim_registry=claim_registry,
    )
    if setup.terminal.status is not LivingDexCaptureSetupStatus.COMPLETE:
        return RedLivingDexCausalCampaignReceipt(plan, setup, None)
    capture = setup.capture
    if capture is None:
        raise RedLivingDexCausalCampaignError(
            "complete causal campaign setup lacks its capture"
        )
    setup_pair = plan.outer_execution_identity.root_pair(stage="setup-capture")

    @contextmanager
    def resolve_runtime():  # type: ignore[no-untyped-def]
        before = meter.checkpoint()
        frozen.reauthenticate(plan_loader(), root=root)
        if meter.checkpoint() != before:
            raise RedLivingDexCausalCampaignError(
                "causal campaign reauthentication changed protected effects"
            )
        scope = resolver(frozen, root, setup_pair, meter=meter)
        if meter.checkpoint() != before:
            raise RedLivingDexCausalCampaignError(
                "causal campaign cold resolver changed protected effects"
            )
        with scope as resolved:
            _require_causal_resolved_slot(plan, resolved)
            yield resolved

    scenario = build_red_living_dex_causal_scenario_from_capture(
        capture,
        setup_execution_identity=frozen.producer_execution_identity(),
        runtime_resolver=resolve_runtime,
        meter=meter,
        setup_terminal_sha256=canonical_sha256(setup.terminal.private_dict()),
        setup_pair_claim_sha256=setup_pair.claim_sha256,
        causal_source_commit=plan.causal_source_commit,
        causal_runner_sha256=plan.causal_runner_sha256,
    )
    causal = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=claim_registry,
    )
    return RedLivingDexCausalCampaignReceipt(plan, setup, causal)


def _require_causal_resolved_slot(
    plan: RedLivingDexFrozenCausalCampaign,
    resolved: RedLivingDexResolvedSetupSlot,
) -> None:
    """Rebind the post-selection runtime to the exact frozen setup consumer."""

    if not isinstance(resolved, RedLivingDexResolvedSetupSlot):
        raise TypeError("causal campaign resolver returned another runtime type")
    resolved.__post_init__()
    if (
        resolved.recipe.recipe_sha256 != plan.recipe_sha256
        or resolved.recipe.slot_sha256 != plan.slot_sha256
        or resolved.producer_execution_identity.identity_sha256
        != plan.producer_execution_identity_sha256
        or resolved.title_adapter_sha256
        != plan.outer_execution_identity.title_adapter_sha256
        or resolved.runtime_factory_sha256
        != plan.outer_execution_identity.runtime_factory_sha256
    ):
        raise RedLivingDexCausalCampaignError(
            "causal campaign selected runtime identity differs"
        )


def _require_frozen_join(
    plan: RedLivingDexFrozenCausalCampaign,
    frozen: FrozenRedLivingDexSetupSlot,
    *,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    if (
        frozen.ordinal != plan.ordinal
        or frozen.producer_plan_sha256 != plan.producer_plan_sha256
        or frozen.producer_execution_identity_sha256
        != plan.producer_execution_identity_sha256
        or frozen.recipe_sha256 != plan.recipe_sha256
        or frozen.slot_sha256 != plan.slot_sha256
        or frozen.logical_root_sha256 != plan.logical_root_sha256
        or frozen.physical_root_sha256 != plan.physical_root_sha256
        or frozen.root_state_sha256 != plan.root_state_sha256
        or frozen.root_envelope_sha256 != plan.root_envelope_sha256
        or root.root_consumption_sha256 != plan.logical_root_sha256
        or root.physical_root_sha256 != plan.physical_root_sha256
        or root.state_sha256 != plan.root_state_sha256
        or root.envelope_sha256 != plan.root_envelope_sha256
    ):
        raise RedLivingDexCausalCampaignError(
            "causal campaign frozen setup join differs"
        )
    frozen.reauthenticate(
        # Reconstruct from the detached canonical plan bytes without touching
        # the caller's loader; execution reauthenticates the live loader again.
        _decode_frozen_plan(frozen),
        root=root,
    )


def _decode_frozen_plan(frozen: FrozenRedLivingDexSetupSlot) -> Mapping[str, object]:
    import json

    try:
        document = json.loads(frozen.plan_payload.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise RedLivingDexCausalCampaignError(
            "causal campaign detached plan cannot be decoded"
        ) from None
    if not isinstance(document, dict):
        raise RedLivingDexCausalCampaignError(
            "causal campaign detached plan differs"
        )
    return document


def _restore_outer_identity(document: Mapping[str, object]) -> ClaimFirstExecutionIdentity:
    expected = {
        "exact_ci_attempt",
        "exact_ci_run",
        "logical_root_sha256",
        "physical_root_sha256",
        "producer_execution_identity_sha256",
        "producer_manifest_sha256",
        "producer_plan_sha256",
        "producer_private_plan_sha256",
        "recipe_sha256",
        "runner_sha256",
        "runtime_factory_sha256",
        "schema",
        "slot_sha256",
        "source_bundle_sha256",
        "source_commit",
        "source_published",
        "title_adapter_sha256",
        "worktree_dirty",
    }
    if (
        set(document) != expected
        or document.get("schema") != CLAIM_FIRST_EXECUTION_IDENTITY_SCHEMA
        or document.get("source_published") is not True
        or document.get("worktree_dirty") is not False
    ):
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign outer identity fields differ"
        )
    try:
        identity = ClaimFirstExecutionIdentity(
            source_commit=_string(document["source_commit"], subject="source commit"),
            source_bundle_sha256=_string(
                document["source_bundle_sha256"], subject="source bundle"
            ),
            exact_ci_run=_integer(document["exact_ci_run"], subject="CI run"),
            exact_ci_attempt=_integer(
                document["exact_ci_attempt"], subject="CI attempt"
            ),
            producer_execution_identity_sha256=_string(
                document["producer_execution_identity_sha256"],
                subject="producer execution",
            ),
            producer_plan_sha256=_string(
                document["producer_plan_sha256"], subject="producer plan"
            ),
            producer_private_plan_sha256=_string(
                document["producer_private_plan_sha256"],
                subject="producer private plan",
            ),
            producer_manifest_sha256=_string(
                document["producer_manifest_sha256"], subject="producer manifest"
            ),
            slot_sha256=_string(document["slot_sha256"], subject="slot"),
            recipe_sha256=_string(document["recipe_sha256"], subject="recipe"),
            logical_root_sha256=_string(
                document["logical_root_sha256"], subject="logical root"
            ),
            physical_root_sha256=_string(
                document["physical_root_sha256"], subject="physical root"
            ),
            title_adapter_sha256=_string(
                document["title_adapter_sha256"], subject="title adapter"
            ),
            runtime_factory_sha256=_string(
                document["runtime_factory_sha256"], subject="runtime factory"
            ),
            runner_sha256=_string(document["runner_sha256"], subject="runner"),
        )
    except (TypeError, ValueError):
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign outer identity differs"
        ) from None
    if identity.private_dict() != dict(document):
        raise RedLivingDexCausalCampaignError(
            "stored causal campaign outer identity does not replay"
        )
    return identity


def _string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexCausalCampaignError(f"causal campaign {subject} differs")
    return value


def _integer(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexCausalCampaignError(f"causal campaign {subject} differs")
    return value


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexCausalCampaignError(
            f"causal campaign {subject} SHA-256 differs"
        )
    return value


__all__ = [
    "RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_ID",
    "RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_RECORD_KIND",
    "RED_LIVING_DEX_CAUSAL_CAMPAIGN_PLAN_SCHEMA",
    "RED_LIVING_DEX_CAUSAL_CAMPAIGN_RECEIPT_SCHEMA",
    "RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256",
    "RedLivingDexCausalCampaignError",
    "RedLivingDexCausalCampaignReceipt",
    "RedLivingDexFrozenCausalCampaign",
    "freeze_red_living_dex_causal_campaign",
    "load_red_living_dex_causal_campaign",
    "restore_red_living_dex_causal_campaign",
    "run_red_living_dex_causal_campaign",
]
