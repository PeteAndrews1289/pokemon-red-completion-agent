"""Durable no-retry campaign for purpose-built Red setup recipes.

The recipe plan is sealed before any slot can touch the controller.  Every
slot then receives an exclusive durable episode claim before its runtime is
constructed.  Complete captures retain their exact repeatable state bytes;
failed and interrupted claims remain permanent terminals.  Restart may only
recover an existing terminal or continue a never-claimed slot.

This campaign performs setup validation only.  It never draws a behavior
choice, executes a provider, observes a learner outcome, asks a teacher, fits a
model, or opens a benchmark/sealed root.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from pokemon_red_completion.goal_manager_composition_qualification import (
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureSetupStatus,
    LivingDexCaptureSetupTerminal,
    LivingDexQualifiedCaptureInventory,
    qualify_living_dex_capture_inventory,
)
from pokemon_red_completion.private_artifacts import (
    CollectionSession,
    EpisodeArtifactState,
    EpisodeWriter,
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupForkRuntimeFactory,
    RedLivingDexSetupRecipeError,
    RedLivingDexSetupRecipePlan,
    RedLivingDexSetupSlotRecipe,
    RedLivingDexValidatedSetupCapture,
    restore_red_living_dex_validated_setup_capture,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupFailureReason,
    RedLivingDexSetupProtectedEffectCheckpoint,
)

RED_LIVING_DEX_RECIPE_PLAN_SEAL_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-plan-seal.v2"
RED_LIVING_DEX_RECIPE_CLAIM_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-claim.v2"
RED_LIVING_DEX_RECIPE_TERMINAL_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-terminal.v2"
RED_LIVING_DEX_RECIPE_RUN_SCHEMA = "pokemon.red.living-dex-setup-recipe-run.v2"

RED_LIVING_DEX_RECIPE_COLLECTION_ID = "red-living-dex-setup-recipe-campaign-v1"
RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID = "red-living-dex-setup-recipe-plan-v1"
RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND = "red_living_dex_setup_recipe_plan"
RED_LIVING_DEX_RECIPE_TERMINAL_RECORD_KIND = "red_living_dex_setup_recipe_terminal"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RED_LIVING_DEX_RECIPE_RUNNER_SHA256 = canonical_sha256(
    {
        "account_wide_claim_before_local_episode": True,
        "isolated_arm_per_candidate": True,
        "no_retry_after_root_claim": True,
        "schema": "pokemon.red.living-dex-setup-recipe-runner-contract.v2",
    }
)


class RedLivingDexSetupRecipeCampaignError(RuntimeError):
    """A recipe campaign claim, terminal, or recovery is invalid."""


class RedLivingDexSetupRecipeDisposition(StrEnum):
    """How the current process obtained one permanent terminal."""

    EXECUTED_COMPLETE = "executed_complete"
    EXECUTED_FAILED = "executed_failed"
    RECOVERED_COMPLETE = "recovered_complete"
    RECOVERED_FAILED = "recovered_failed"
    RECOVERED_INTERRUPTED = "recovered_interrupted"


class RedLivingDexControlledRecipeFailure(RuntimeError):
    """A sanitized expected setup failure that may not retry."""

    def __init__(self, reason_code: RedLivingDexSetupFailureReason) -> None:
        if not isinstance(reason_code, RedLivingDexSetupFailureReason):
            raise RedLivingDexSetupRecipeCampaignError("controlled recipe failure reason differs")
        self.reason_code = reason_code
        super().__init__(reason_code.value)


RedLivingDexSetupRecipeFailpoint = Callable[[str, RedLivingDexSetupSlotRecipe], None]


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRecipeTerminal:
    """Immutable whole-slot terminal independent of episode naming."""

    recipe_plan_sha256: str
    recipe_sha256: str
    slot_sha256: str
    execution_identity_sha256: str
    claim_sha256: str
    status: LivingDexCaptureSetupStatus
    reason_code: RedLivingDexSetupFailureReason | None
    setup_controller_actions: int | None
    setup_emulator_frames: int | None
    attestation_sha256: str | None
    retry_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for digest_value, subject in (
            (self.recipe_plan_sha256, "recipe terminal plan"),
            (self.recipe_sha256, "recipe terminal recipe"),
            (self.slot_sha256, "recipe terminal slot"),
            (self.execution_identity_sha256, "recipe terminal execution identity"),
            (self.claim_sha256, "recipe terminal claim"),
        ):
            _require_sha256(digest_value, subject)
        if not isinstance(self.status, LivingDexCaptureSetupStatus):
            raise RedLivingDexSetupRecipeCampaignError("recipe terminal status differs")
        known = self.setup_controller_actions is not None
        if known != (self.setup_emulator_frames is not None):
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe terminal accounting is partially known"
            )
        if known:
            assert self.setup_controller_actions is not None
            assert self.setup_emulator_frames is not None
            for numeric_value, subject in (
                (self.setup_controller_actions, "recipe terminal actions"),
                (self.setup_emulator_frames, "recipe terminal frames"),
            ):
                if type(numeric_value) is not int or numeric_value < 0:  # noqa: E721
                    raise RedLivingDexSetupRecipeCampaignError(f"{subject} differ")
        if self.status is LivingDexCaptureSetupStatus.COMPLETE:
            if not known or self.reason_code is not None or self.attestation_sha256 is None:
                raise RedLivingDexSetupRecipeCampaignError(
                    "complete recipe terminal evidence differs"
                )
            _require_sha256(self.attestation_sha256, "recipe terminal attestation")
        elif (
            not isinstance(self.reason_code, RedLivingDexSetupFailureReason)
            or self.attestation_sha256 is not None
        ):
            raise RedLivingDexSetupRecipeCampaignError(
                "noncomplete recipe terminal evidence differs"
            )
        if self.retry_allowed:
            raise RedLivingDexSetupRecipeCampaignError("claimed recipe terminal cannot retry")

    @property
    def accounting_known(self) -> bool:
        return self.setup_controller_actions is not None

    def private_dict(self) -> dict[str, object]:
        return {
            "attestation_sha256": self.attestation_sha256,
            "claim_sha256": self.claim_sha256,
            "execution_identity_sha256": self.execution_identity_sha256,
            "reason_code": (None if self.reason_code is None else self.reason_code.value),
            "recipe_plan_sha256": self.recipe_plan_sha256,
            "recipe_sha256": self.recipe_sha256,
            "retry_allowed": self.retry_allowed,
            "schema": RED_LIVING_DEX_RECIPE_TERMINAL_SCHEMA,
            "setup_controller_actions": self.setup_controller_actions,
            "setup_emulator_frames": self.setup_emulator_frames,
            "slot_sha256": self.slot_sha256,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRecipeReceipt:
    """One aggregate-safe view of a permanent private terminal."""

    recipe: RedLivingDexSetupSlotRecipe
    terminal: RedLivingDexSetupRecipeTerminal
    artifact_state: EpisodeArtifactState
    disposition: RedLivingDexSetupRecipeDisposition
    capture: RedLivingDexValidatedSetupCapture | None

    def __post_init__(self) -> None:
        if not isinstance(self.recipe, RedLivingDexSetupSlotRecipe):
            raise TypeError("recipe receipt needs its recipe")
        if not isinstance(self.terminal, RedLivingDexSetupRecipeTerminal):
            raise TypeError("recipe receipt needs its terminal")
        if not isinstance(self.artifact_state, EpisodeArtifactState):
            raise TypeError("recipe receipt needs its artifact state")
        if not isinstance(self.disposition, RedLivingDexSetupRecipeDisposition):
            raise TypeError("recipe receipt disposition differs")
        if (
            self.terminal.recipe_sha256 != self.recipe.recipe_sha256
            or self.terminal.slot_sha256 != self.recipe.slot_sha256
        ):
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe receipt terminal is joined to another recipe"
            )
        if self.terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
            if self.capture is None or self.artifact_state.status != "complete":
                raise RedLivingDexSetupRecipeCampaignError(
                    "complete recipe receipt lacks its capture"
                )
            if (
                self.capture.recipe_sha256 != self.recipe.recipe_sha256
                or self.capture.attestation.attestation_sha256 != self.terminal.attestation_sha256
            ):
                raise RedLivingDexSetupRecipeCampaignError(
                    "recipe receipt capture differs from its terminal"
                )
        elif self.capture is not None:
            raise RedLivingDexSetupRecipeCampaignError(
                "noncomplete recipe receipt cannot expose a capture"
            )

    @property
    def newly_executed(self) -> bool:
        return self.disposition in {
            RedLivingDexSetupRecipeDisposition.EXECUTED_COMPLETE,
            RedLivingDexSetupRecipeDisposition.EXECUTED_FAILED,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "accounting_known": self.terminal.accounting_known,
            "behavior_draws": 0,
            "disposition": self.disposition.value,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "new_runtime_invocation": self.newly_executed,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "retry_allowed": False,
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRecipeRun:
    """Restart-safe accounting over the complete frozen denominator."""

    plan: RedLivingDexSetupRecipePlan
    receipts: tuple[RedLivingDexSetupRecipeReceipt, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RedLivingDexSetupRecipePlan):
            raise TypeError("recipe run needs its plan")
        if (
            not isinstance(self.receipts, tuple)
            or len(self.receipts) != len(self.plan.recipes)
            or any(not isinstance(item, RedLivingDexSetupRecipeReceipt) for item in self.receipts)
            or tuple(item.recipe for item in self.receipts) != self.plan.recipes
        ):
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe run does not account for every slot in order"
            )
        if any(
            item.terminal.execution_identity_sha256 != self.plan.execution_identity.identity_sha256
            for item in self.receipts
        ):
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe run terminals use another execution identity"
            )

    @property
    def inventory_qualification_available(self) -> bool:
        if any(not item.terminal.accounting_known for item in self.receipts):
            return False
        try:
            self.qualified_inventory()
        except (RedLivingDexSetupRecipeCampaignError, ValueError):
            return False
        return True

    def qualified_inventory(self) -> LivingDexQualifiedCaptureInventory:
        terminals: list[LivingDexCaptureSetupTerminal] = []
        for slot, receipt in zip(
            self.plan.prospective_plan.slots,
            self.receipts,
            strict=True,
        ):
            terminal = receipt.terminal
            if not terminal.accounting_known:
                raise RedLivingDexSetupRecipeCampaignError(
                    "recipe run has unknown terminal accounting"
                )
            assert terminal.setup_controller_actions is not None
            assert terminal.setup_emulator_frames is not None
            terminals.append(
                LivingDexCaptureSetupTerminal(
                    slot_sha256=slot.slot_sha256,
                    claim_sha256=terminal.claim_sha256,
                    status=terminal.status,
                    setup_controller_actions=terminal.setup_controller_actions,
                    setup_emulator_frames=terminal.setup_emulator_frames,
                    attestation=(None if receipt.capture is None else receipt.capture.attestation),
                )
            )
        return qualify_living_dex_capture_inventory(
            self.plan.prospective_plan,
            terminals,
        )

    def public_dict(self) -> dict[str, object]:
        statuses = Counter(item.terminal.status.value for item in self.receipts)
        dispositions = Counter(item.disposition.value for item in self.receipts)
        known = tuple(item for item in self.receipts if item.terminal.accounting_known)
        failures = Counter(
            item.terminal.reason_code.value
            for item in self.receipts
            if item.terminal.reason_code is not None
        )
        return {
            "all_slots_terminal": len(self.receipts) == len(self.plan.recipes),
            "behavior_draws": 0,
            "disposition_counts": {
                item.value: dispositions[item.value] for item in RedLivingDexSetupRecipeDisposition
            },
            "inventory_qualification_available": self.inventory_qualification_available,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "model_predictions": 0,
            "plan": self.plan.public_dict(),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "failure_category_counts": {
                item.value: failures[item.value] for item in RedLivingDexSetupFailureReason
            },
            "retry_allowed": False,
            "schema": RED_LIVING_DEX_RECIPE_RUN_SCHEMA,
            "setup_controller_actions_known_total": sum(
                item.terminal.setup_controller_actions or 0 for item in known
            ),
            "setup_emulator_frames_known_total": sum(
                item.terminal.setup_emulator_frames or 0 for item in known
            ),
            "terminal_accounting_known": len(known),
            "terminal_accounting_unknown": len(self.receipts) - len(known),
            "terminal_status_counts": {
                item.value: statuses[item.value] for item in LivingDexCaptureSetupStatus
            },
            "teacher_queries": 0,
        }


def run_red_living_dex_setup_recipe_campaign(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupRecipePlan,
    *,
    roots: tuple[RedLivingDexAuthenticatedSetupRoot, ...],
    arm_factory: RedLivingDexSetupForkRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    failpoint: RedLivingDexSetupRecipeFailpoint | None = None,
) -> RedLivingDexSetupRecipeRun:
    """Execute never-claimed recipes and recover every existing terminal."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("recipe campaign needs a validated private root")
    if not isinstance(plan, RedLivingDexSetupRecipePlan):
        raise TypeError("recipe campaign needs a frozen recipe plan")
    plan.__post_init__()
    if (
        not isinstance(roots, tuple)
        or len(roots) != len(plan.recipes)
        or any(not isinstance(item, RedLivingDexAuthenticatedSetupRoot) for item in roots)
    ):
        raise TypeError("recipe campaign needs one authenticated root per recipe")
    for recipe, root in zip(plan.recipes, roots, strict=True):
        root.__post_init__()
        if (
            root.root_consumption_sha256 != recipe.root_consumption_sha256
            or root.state_sha256 != recipe.root_state_sha256
            or root.envelope_sha256 != recipe.root_envelope_sha256
        ):
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe campaign root inventory differs from its plan"
            )
    if not callable(arm_factory):
        raise TypeError("recipe campaign needs an isolated-arm factory")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("recipe campaign needs a comprehensive effect meter")
    if not isinstance(claim_registry, Path):
        raise TypeError("recipe campaign needs an account claim registry")
    if failpoint is not None and not callable(failpoint):
        raise TypeError("recipe campaign failpoint must be callable")
    try:
        registry = open_fixed_account_claim_registry(claim_registry)
    except FreshCompositionQualificationError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None
    _seal_plan(store, plan)
    _trip_failpoint(failpoint, "after_plan_seal", plan.recipes[0])
    receipts: list[RedLivingDexSetupRecipeReceipt] = []
    try:
        with (
            fixed_account_claim_registry_lease(registry, exclusive=True),
            store.collection_session(RED_LIVING_DEX_RECIPE_COLLECTION_ID) as session,
        ):
            for ordinal, (slot, recipe, root) in enumerate(
                zip(
                    plan.prospective_plan.slots,
                    plan.recipes,
                    roots,
                    strict=True,
                )
            ):
                receipts.append(
                    _run_recipe(
                        store,
                        session,
                        plan,
                        slot,
                        recipe,
                        root,
                        ordinal=ordinal,
                        arm_factory=arm_factory,
                        meter=meter,
                        claim_registry=registry,
                        failpoint=failpoint,
                    )
                )
    except FreshCompositionQualificationError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None
    return RedLivingDexSetupRecipeRun(plan, tuple(receipts))


def _seal_plan(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupRecipePlan,
) -> None:
    record = {
        "claim_before_controller_input": True,
        "learner_effects": 0,
        "recipe_plan": plan.private_dict(),
        "recipe_plan_sha256": plan.plan_sha256,
        "retry_after_controller_input": False,
        "schema": RED_LIVING_DEX_RECIPE_PLAN_SEAL_SCHEMA,
    }
    try:
        sealed = store.publish_sealed_record(
            RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID,
            kind=RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND,
            record=record,
        )
        # The artifact store round-trips JSON tuples as lists.  Compare the
        # canonical document rather than Python container identity.
        if canonical_sha256(sealed.read()) != canonical_sha256(record):
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe campaign plan seal failed verification"
            )
    except RedLivingDexSetupRecipeCampaignError:
        raise
    except PrivateArtifactError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None


def _run_recipe(
    store: PrivateArtifactRoot,
    session: CollectionSession,
    plan: RedLivingDexSetupRecipePlan,
    slot: object,
    recipe: RedLivingDexSetupSlotRecipe,
    root: RedLivingDexAuthenticatedSetupRoot,
    *,
    ordinal: int,
    arm_factory: RedLivingDexSetupForkRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    failpoint: RedLivingDexSetupRecipeFailpoint | None,
) -> RedLivingDexSetupRecipeReceipt:
    from pokemon_red_completion.living_dex_capture_curriculum import (
        LivingDexProspectiveCaptureSlot,
    )

    if not isinstance(slot, LivingDexProspectiveCaptureSlot):
        raise TypeError("recipe campaign slot differs")
    session.require_store(store)
    episode_id = _episode_id(recipe, ordinal)
    claim = _claim_record(plan, recipe)
    claim_sha256 = canonical_sha256(claim)
    terminal = _find_terminal(store, plan, recipe, claim_sha256)
    state = session.inspect_episode(episode_id)
    if terminal is not None:
        _require_account_claim(claim_registry, plan, root)
        if state.status == "partial":
            state = session.recover_interrupted_episode(episode_id)
        return _receipt_from_terminal(
            store,
            plan,
            recipe,
            episode_id,
            state,
            terminal,
            newly_executed=False,
        )
    if state.status == "partial":
        _require_account_claim(claim_registry, plan, root)
        state = session.recover_interrupted_episode(episode_id)
    if state.status == "complete":
        _require_account_claim(claim_registry, plan, root)
        capture = _load_capture(store, plan, recipe, episode_id)
        terminal = _complete_terminal(plan, recipe, claim_sha256, capture)
        _publish_terminal(store, recipe, terminal)
        _trip_failpoint(failpoint, "after_terminal_publish", recipe)
        return RedLivingDexSetupRecipeReceipt(
            recipe,
            terminal,
            state,
            RedLivingDexSetupRecipeDisposition.RECOVERED_COMPLETE,
            capture,
        )
    if state.status in {"failed", "interrupted"}:
        _require_account_claim(claim_registry, plan, root)
        reason_code = _restore_reason_code(state.reason_code)
        status = (
            LivingDexCaptureSetupStatus.INTERRUPTED
            if state.status == "interrupted"
            or reason_code is RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED
            else LivingDexCaptureSetupStatus.FAILED
        )
        terminal = RedLivingDexSetupRecipeTerminal(
            recipe_plan_sha256=plan.plan_sha256,
            recipe_sha256=recipe.recipe_sha256,
            slot_sha256=recipe.slot_sha256,
            execution_identity_sha256=plan.execution_identity.identity_sha256,
            claim_sha256=claim_sha256,
            status=status,
            reason_code=reason_code,
            setup_controller_actions=None,
            setup_emulator_frames=None,
            attestation_sha256=None,
        )
        _publish_terminal(store, recipe, terminal)
        return RedLivingDexSetupRecipeReceipt(
            recipe,
            terminal,
            state,
            (
                RedLivingDexSetupRecipeDisposition.RECOVERED_FAILED
                if status is LivingDexCaptureSetupStatus.FAILED
                else RedLivingDexSetupRecipeDisposition.RECOVERED_INTERRUPTED
            ),
            None,
        )
    if state.status == "invalid":
        raise RedLivingDexSetupRecipeCampaignError("recipe episode cannot be authenticated")
    if state.status != "absent":
        raise RedLivingDexSetupRecipeCampaignError("recipe episode has an unsupported state")
    newly_claimed = _claim_account_root(
        claim_registry,
        plan,
        root,
        meter=meter,
    )
    if newly_claimed:
        _trip_failpoint(failpoint, "after_account_root_claim", recipe)
    else:
        # A matching account marker with no local episode proves a prior
        # process died after global consumption and before local durability.
        # The physical root is permanently spent; record that fact without
        # constructing a controller-capable arm.
        return _record_prelocal_interruption(
            store,
            plan,
            recipe,
            episode_id=episode_id,
            claim=claim,
            claim_sha256=claim_sha256,
            failpoint=failpoint,
        )
    return _execute_recipe(
        store,
        plan,
        slot,
        recipe,
        episode_id=episode_id,
        claim=claim,
        claim_sha256=claim_sha256,
        root=root,
        arm_factory=arm_factory,
        meter=meter,
        failpoint=failpoint,
    )


def _execute_recipe(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupRecipePlan,
    slot: object,
    recipe: RedLivingDexSetupSlotRecipe,
    *,
    episode_id: str,
    claim: Mapping[str, object],
    claim_sha256: str,
    root: RedLivingDexAuthenticatedSetupRoot,
    arm_factory: RedLivingDexSetupForkRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
    failpoint: RedLivingDexSetupRecipeFailpoint | None,
) -> RedLivingDexSetupRecipeReceipt:
    from pokemon_red_completion.living_dex_capture_curriculum import (
        LivingDexProspectiveCaptureSlot,
    )

    assert isinstance(slot, LivingDexProspectiveCaptureSlot)
    before = _checkpoint(meter)
    with store.begin_episode(episode_id) as writer:
        _trip_failpoint(failpoint, "after_local_episode_open", recipe)
        writer.append("claim", claim, durable=True)
        _trip_failpoint(failpoint, "after_local_claim", recipe)
        if _checkpoint(meter) != before:
            raise RedLivingDexSetupRecipeCampaignError("recipe claim changed protected effects")
        try:
            capture = validate_red_living_dex_setup_recipe(
                slot,
                recipe,
                execution_identity=plan.execution_identity,
                root=root,
                arm_factory=arm_factory,
                meter=meter,
            )
            after = _checkpoint(meter)
            actions, frames = _delta(before, after)
            if (
                actions != capture.attestation.setup_controller_actions
                or frames != capture.attestation.setup_emulator_frames
            ):
                raise RedLivingDexSetupRecipeCampaignError(
                    "recipe campaign and validator budgets differ"
                )
            writer.append("capture", capture.private_dict(), durable=True)
            _trip_failpoint(failpoint, "after_capture_append", recipe)
        except RedLivingDexControlledRecipeFailure as error:
            return _settle_failed(
                store,
                writer,
                plan,
                recipe,
                claim_sha256=claim_sha256,
                before=before,
                meter=meter,
                reason_code=error.reason_code,
                failpoint=failpoint,
            )
        except BaseException as error:
            interrupted = not isinstance(error, Exception)
            _settle_failed(
                store,
                writer,
                plan,
                recipe,
                claim_sha256=claim_sha256,
                before=before,
                meter=meter,
                reason_code=(
                    RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED
                    if interrupted
                    else RedLivingDexSetupFailureReason.RECIPE_EXECUTION_FAILED
                ),
                interrupted=interrupted,
                failpoint=failpoint,
            )
            if interrupted:
                raise
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe execution failed after durable claim"
            ) from None
        summary = writer.complete()
    _trip_failpoint(failpoint, "after_episode_complete", recipe)
    state = EpisodeArtifactState(
        episode_id,
        "complete",
        manifest_sha256=summary.manifest_sha256,
    )
    terminal = _complete_terminal(plan, recipe, claim_sha256, capture)
    _publish_terminal(store, recipe, terminal)
    _trip_failpoint(failpoint, "after_terminal_publish", recipe)
    return RedLivingDexSetupRecipeReceipt(
        recipe,
        terminal,
        state,
        RedLivingDexSetupRecipeDisposition.EXECUTED_COMPLETE,
        capture,
    )


def _settle_failed(
    store: PrivateArtifactRoot,
    writer: EpisodeWriter,
    plan: RedLivingDexSetupRecipePlan,
    recipe: RedLivingDexSetupSlotRecipe,
    *,
    claim_sha256: str,
    before: RedLivingDexSetupProtectedEffectCheckpoint,
    meter: RedLivingDexSetupEffectMeter,
    reason_code: RedLivingDexSetupFailureReason,
    interrupted: bool = False,
    failpoint: RedLivingDexSetupRecipeFailpoint | None = None,
) -> RedLivingDexSetupRecipeReceipt:
    actions, frames = _delta(before, _checkpoint(meter))
    status = (
        LivingDexCaptureSetupStatus.INTERRUPTED
        if interrupted
        else LivingDexCaptureSetupStatus.FAILED
    )
    terminal = RedLivingDexSetupRecipeTerminal(
        recipe_plan_sha256=plan.plan_sha256,
        recipe_sha256=recipe.recipe_sha256,
        slot_sha256=recipe.slot_sha256,
        execution_identity_sha256=plan.execution_identity.identity_sha256,
        claim_sha256=claim_sha256,
        status=status,
        reason_code=reason_code,
        setup_controller_actions=actions,
        setup_emulator_frames=frames,
        attestation_sha256=None,
    )
    writer.append("failure", terminal.private_dict(), durable=True)
    _trip_failpoint(failpoint, "after_failure_append", recipe)
    _publish_terminal(store, recipe, terminal)
    _trip_failpoint(failpoint, "after_failure_terminal_publish", recipe)
    summary = writer.abort(reason_code.value)
    _trip_failpoint(failpoint, "after_failure_episode_abort", recipe)
    state = EpisodeArtifactState(
        summary.episode_id,
        "failed",
        reason_code=reason_code.value,
        manifest_sha256=summary.manifest_sha256,
    )
    return RedLivingDexSetupRecipeReceipt(
        recipe,
        terminal,
        state,
        (
            RedLivingDexSetupRecipeDisposition.RECOVERED_INTERRUPTED
            if interrupted
            else RedLivingDexSetupRecipeDisposition.EXECUTED_FAILED
        ),
        None,
    )


def _complete_terminal(
    plan: RedLivingDexSetupRecipePlan,
    recipe: RedLivingDexSetupSlotRecipe,
    claim_sha256: str,
    capture: RedLivingDexValidatedSetupCapture,
) -> RedLivingDexSetupRecipeTerminal:
    return RedLivingDexSetupRecipeTerminal(
        recipe_plan_sha256=plan.plan_sha256,
        recipe_sha256=recipe.recipe_sha256,
        slot_sha256=recipe.slot_sha256,
        execution_identity_sha256=plan.execution_identity.identity_sha256,
        claim_sha256=claim_sha256,
        status=LivingDexCaptureSetupStatus.COMPLETE,
        reason_code=None,
        setup_controller_actions=capture.attestation.setup_controller_actions,
        setup_emulator_frames=capture.attestation.setup_emulator_frames,
        attestation_sha256=capture.attestation.attestation_sha256,
    )


def _claim_record(
    plan: RedLivingDexSetupRecipePlan,
    recipe: RedLivingDexSetupSlotRecipe,
) -> dict[str, object]:
    return {
        "behavior_draws": 0,
        "claim_before_controller_input": True,
        "execution_identity_sha256": plan.execution_identity.identity_sha256,
        "learner_effects": 0,
        "recipe_plan_sha256": plan.plan_sha256,
        "recipe_sha256": recipe.recipe_sha256,
        "retry_after_controller_input": False,
        "same_origin_fork_required": True,
        "schema": RED_LIVING_DEX_RECIPE_CLAIM_SCHEMA,
        "slot_sha256": recipe.slot_sha256,
    }


def _load_capture(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupRecipePlan,
    recipe: RedLivingDexSetupSlotRecipe,
    episode_id: str,
) -> RedLivingDexValidatedSetupCapture:
    try:
        reader = store.open_episode(episode_id)
        claims = tuple(reader.iter_stream("claim", max_records=1))
        captures = tuple(reader.iter_stream("capture", max_records=1))
    except PrivateArtifactError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None
    if len(claims) != 1 or claims[0] != _claim_record(plan, recipe):
        raise RedLivingDexSetupRecipeCampaignError("complete recipe artifact lacks its exact claim")
    if len(captures) != 1:
        raise RedLivingDexSetupRecipeCampaignError("complete recipe artifact lacks one capture")
    try:
        capture = restore_red_living_dex_validated_setup_capture(captures[0])
    except RedLivingDexSetupRecipeError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None
    if (
        capture.recipe_sha256 != recipe.recipe_sha256
        or capture.binding.slot_sha256 != recipe.slot_sha256
        or capture.execution_identity_sha256 != plan.execution_identity.identity_sha256
    ):
        raise RedLivingDexSetupRecipeCampaignError("stored capture differs from its recipe")
    return capture


def _publish_terminal(
    store: PrivateArtifactRoot,
    recipe: RedLivingDexSetupSlotRecipe,
    terminal: RedLivingDexSetupRecipeTerminal,
) -> None:
    try:
        sealed = store.publish_sealed_record(
            _terminal_record_id(recipe),
            kind=RED_LIVING_DEX_RECIPE_TERMINAL_RECORD_KIND,
            record=terminal.private_dict(),
        )
        if sealed.read() != terminal.private_dict():
            raise RedLivingDexSetupRecipeCampaignError("recipe terminal publication differs")
    except RedLivingDexSetupRecipeCampaignError:
        raise
    except PrivateArtifactError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None


def _find_terminal(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupRecipePlan,
    recipe: RedLivingDexSetupSlotRecipe,
    claim_sha256: str,
) -> RedLivingDexSetupRecipeTerminal | None:
    try:
        sealed = store.find_sealed_record(
            _terminal_record_id(recipe),
            expected_kind=RED_LIVING_DEX_RECIPE_TERMINAL_RECORD_KIND,
        )
    except PrivateArtifactError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None
    if sealed is None:
        return None
    terminal = _restore_terminal(sealed.read())
    if (
        terminal.recipe_plan_sha256 != plan.plan_sha256
        or terminal.recipe_sha256 != recipe.recipe_sha256
        or terminal.slot_sha256 != recipe.slot_sha256
        or terminal.execution_identity_sha256 != plan.execution_identity.identity_sha256
        or terminal.claim_sha256 != claim_sha256
    ):
        raise RedLivingDexSetupRecipeCampaignError(
            "stored recipe terminal differs from the active plan"
        )
    return terminal


def _receipt_from_terminal(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupRecipePlan,
    recipe: RedLivingDexSetupSlotRecipe,
    episode_id: str,
    state: EpisodeArtifactState,
    terminal: RedLivingDexSetupRecipeTerminal,
    *,
    newly_executed: bool,
) -> RedLivingDexSetupRecipeReceipt:
    if terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
        capture = _load_capture(store, plan, recipe, episode_id)
        disposition = (
            RedLivingDexSetupRecipeDisposition.EXECUTED_COMPLETE
            if newly_executed
            else RedLivingDexSetupRecipeDisposition.RECOVERED_COMPLETE
        )
    else:
        capture = None
        disposition = (
            RedLivingDexSetupRecipeDisposition.EXECUTED_FAILED
            if newly_executed
            else RedLivingDexSetupRecipeDisposition.RECOVERED_FAILED
            if terminal.status is LivingDexCaptureSetupStatus.FAILED
            else RedLivingDexSetupRecipeDisposition.RECOVERED_INTERRUPTED
        )
    return RedLivingDexSetupRecipeReceipt(
        recipe,
        terminal,
        state,
        disposition,
        capture,
    )


def _restore_terminal(
    document: Mapping[str, object],
) -> RedLivingDexSetupRecipeTerminal:
    expected = {
        "attestation_sha256",
        "claim_sha256",
        "execution_identity_sha256",
        "reason_code",
        "recipe_plan_sha256",
        "recipe_sha256",
        "retry_allowed",
        "schema",
        "setup_controller_actions",
        "setup_emulator_frames",
        "slot_sha256",
        "status",
    }
    if set(document) != expected or document["schema"] != RED_LIVING_DEX_RECIPE_TERMINAL_SCHEMA:
        raise RedLivingDexSetupRecipeCampaignError("stored recipe terminal fields differ")
    if document["retry_allowed"] is not False:
        raise RedLivingDexSetupRecipeCampaignError("stored recipe terminal permits retry")
    try:
        status = LivingDexCaptureSetupStatus(_string(document["status"], "terminal status"))
    except ValueError:
        raise RedLivingDexSetupRecipeCampaignError(
            "stored recipe terminal status differs"
        ) from None
    return RedLivingDexSetupRecipeTerminal(
        recipe_plan_sha256=_string(document["recipe_plan_sha256"], "terminal plan"),
        recipe_sha256=_string(document["recipe_sha256"], "terminal recipe"),
        slot_sha256=_string(document["slot_sha256"], "terminal slot"),
        execution_identity_sha256=_string(
            document["execution_identity_sha256"],
            "terminal execution identity",
        ),
        claim_sha256=_string(document["claim_sha256"], "terminal claim"),
        status=status,
        reason_code=_optional_reason_code(document["reason_code"]),
        setup_controller_actions=_optional_integer(
            document["setup_controller_actions"],
            "terminal actions",
        ),
        setup_emulator_frames=_optional_integer(
            document["setup_emulator_frames"],
            "terminal frames",
        ),
        attestation_sha256=_optional_string(
            document["attestation_sha256"],
            "terminal attestation",
        ),
    )


def _claim_account_root(
    registry: Path,
    plan: RedLivingDexSetupRecipePlan,
    root: RedLivingDexAuthenticatedSetupRoot,
    *,
    meter: RedLivingDexSetupEffectMeter,
) -> bool:
    if not root_claim_is_available(registry, root.physical_root_sha256):
        _require_account_claim(registry, plan, root)
        return False
    before = _checkpoint(meter)
    write_root_claim(
        registry,
        root_consumption_sha256=root.physical_root_sha256,
        execution_identity_sha256=plan.execution_identity.identity_sha256,
        source_commit=plan.execution_identity.source_commit,
        runner_sha256=RED_LIVING_DEX_RECIPE_RUNNER_SHA256,
    )
    meter.record_root_claim()
    expected = replace(before, root_claims=before.root_claims + 1)
    if _checkpoint(meter) != expected:
        raise RedLivingDexSetupRecipeCampaignError(
            "account root claim changed unrelated protected effects"
        )
    _require_account_claim(registry, plan, root)
    return True


def _require_account_claim(
    registry: Path,
    plan: RedLivingDexSetupRecipePlan,
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    marker = read_root_claim(registry, root.physical_root_sha256)
    if (
        marker["execution_identity_sha256"] != plan.execution_identity.identity_sha256
        or marker["source_commit"] != plan.execution_identity.source_commit
        or marker["runner_sha256"] != RED_LIVING_DEX_RECIPE_RUNNER_SHA256
    ):
        raise RedLivingDexSetupRecipeCampaignError(
            "account root claim belongs to another execution"
        )


def _record_prelocal_interruption(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupRecipePlan,
    recipe: RedLivingDexSetupSlotRecipe,
    *,
    episode_id: str,
    claim: Mapping[str, object],
    claim_sha256: str,
    failpoint: RedLivingDexSetupRecipeFailpoint | None,
) -> RedLivingDexSetupRecipeReceipt:
    reason = RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED
    terminal = RedLivingDexSetupRecipeTerminal(
        recipe_plan_sha256=plan.plan_sha256,
        recipe_sha256=recipe.recipe_sha256,
        slot_sha256=recipe.slot_sha256,
        execution_identity_sha256=plan.execution_identity.identity_sha256,
        claim_sha256=claim_sha256,
        status=LivingDexCaptureSetupStatus.INTERRUPTED,
        reason_code=reason,
        setup_controller_actions=0,
        setup_emulator_frames=0,
        attestation_sha256=None,
    )
    with store.begin_episode(episode_id) as writer:
        writer.append("claim", claim, durable=True)
        _trip_failpoint(failpoint, "after_prelocal_claim", recipe)
        writer.append("failure", terminal.private_dict(), durable=True)
        _trip_failpoint(failpoint, "after_prelocal_failure_append", recipe)
        summary = writer.abort(reason.value)
    _trip_failpoint(failpoint, "after_prelocal_episode_abort", recipe)
    _publish_terminal(store, recipe, terminal)
    _trip_failpoint(failpoint, "after_prelocal_terminal_publish", recipe)
    return RedLivingDexSetupRecipeReceipt(
        recipe,
        terminal,
        EpisodeArtifactState(
            episode_id,
            "failed",
            reason_code=reason.value,
            manifest_sha256=summary.manifest_sha256,
        ),
        RedLivingDexSetupRecipeDisposition.RECOVERED_INTERRUPTED,
        None,
    )


def _restore_reason_code(value: str | None) -> RedLivingDexSetupFailureReason:
    # ``EpisodeWriter.__exit__`` uses this one fixed internal reason when the
    # process leaves before our runner can publish its own closed terminal.
    # Translate it at the boundary; never expose or accept arbitrary strings.
    if value in {None, "unhandled_exception"}:
        return RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED
    try:
        return RedLivingDexSetupFailureReason(value)
    except ValueError:
        raise RedLivingDexSetupRecipeCampaignError(
            "stored recipe failure reason is outside the closed vocabulary"
        ) from None


def _optional_reason_code(value: object) -> RedLivingDexSetupFailureReason | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RedLivingDexSetupRecipeCampaignError("terminal reason differs")
    return _restore_reason_code(value)


def _trip_failpoint(
    failpoint: RedLivingDexSetupRecipeFailpoint | None,
    name: str,
    recipe: RedLivingDexSetupSlotRecipe,
) -> None:
    if failpoint is not None:
        failpoint(name, recipe)


def _episode_id(recipe: RedLivingDexSetupSlotRecipe, ordinal: int) -> str:
    return f"red-living-dex-recipe-{ordinal:02d}-{recipe.recipe_sha256[:20]}"


def _terminal_record_id(recipe: RedLivingDexSetupSlotRecipe) -> str:
    return f"red-living-dex-recipe-terminal-{recipe.recipe_sha256[:24]}"


def _checkpoint(
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexSetupProtectedEffectCheckpoint:
    value = meter.checkpoint()
    if not isinstance(value, RedLivingDexSetupProtectedEffectCheckpoint):
        raise RedLivingDexSetupRecipeCampaignError("recipe campaign effect checkpoint differs")
    return value


def _delta(
    before: RedLivingDexSetupProtectedEffectCheckpoint,
    after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> tuple[int, int]:
    try:
        return before.action_frame_delta(after)
    except RuntimeError as error:
        raise RedLivingDexSetupRecipeCampaignError(str(error)) from None


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexSetupRecipeCampaignError(f"{subject} digest differs")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexSetupRecipeCampaignError(f"{subject} differs")
    return value


def _optional_string(value: object, subject: str) -> str | None:
    if value is None:
        return None
    return _string(value, subject)


def _optional_integer(value: object, subject: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexSetupRecipeCampaignError(f"{subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_RECIPE_COLLECTION_ID",
    "RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID",
    "RED_LIVING_DEX_RECIPE_RUN_SCHEMA",
    "RedLivingDexControlledRecipeFailure",
    "RedLivingDexSetupRecipeCampaignError",
    "RedLivingDexSetupRecipeDisposition",
    "RedLivingDexSetupRecipeReceipt",
    "RedLivingDexSetupRecipeRun",
    "RedLivingDexSetupRecipeTerminal",
    "run_red_living_dex_setup_recipe_campaign",
]
