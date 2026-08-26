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
from dataclasses import dataclass, field
from enum import StrEnum

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
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupRecipeError,
    RedLivingDexSetupRecipePlan,
    RedLivingDexSetupRecipeRuntime,
    RedLivingDexSetupSlotRecipe,
    RedLivingDexValidatedSetupCapture,
    restore_red_living_dex_validated_setup_capture,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticBudgetCheckpoint,
)

RED_LIVING_DEX_RECIPE_PLAN_SEAL_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-plan-seal.v1"
RED_LIVING_DEX_RECIPE_CLAIM_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-claim.v1"
RED_LIVING_DEX_RECIPE_TERMINAL_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-terminal.v1"
RED_LIVING_DEX_RECIPE_RUN_SCHEMA = "pokemon.red.living-dex-setup-recipe-run.v1"

RED_LIVING_DEX_RECIPE_COLLECTION_ID = "red-living-dex-setup-recipe-campaign-v1"
RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID = "red-living-dex-setup-recipe-plan-v1"
RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND = "red_living_dex_setup_recipe_plan"
RED_LIVING_DEX_RECIPE_TERMINAL_RECORD_KIND = "red_living_dex_setup_recipe_terminal"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_REASON = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


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

    def __init__(self, reason_code: str) -> None:
        if not isinstance(reason_code, str) or _SAFE_REASON.fullmatch(reason_code) is None:
            raise RedLivingDexSetupRecipeCampaignError("controlled recipe failure reason differs")
        self.reason_code = reason_code
        super().__init__(reason_code)


RedLivingDexSetupRecipeRuntimeFactory = Callable[
    [RedLivingDexSetupSlotRecipe],
    RedLivingDexSetupRecipeRuntime,
]


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRecipeTerminal:
    """Immutable whole-slot terminal independent of episode naming."""

    recipe_plan_sha256: str
    recipe_sha256: str
    slot_sha256: str
    claim_sha256: str
    status: LivingDexCaptureSetupStatus
    reason_code: str | None
    setup_controller_actions: int | None
    setup_emulator_frames: int | None
    attestation_sha256: str | None
    retry_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for digest_value, subject in (
            (self.recipe_plan_sha256, "recipe terminal plan"),
            (self.recipe_sha256, "recipe terminal recipe"),
            (self.slot_sha256, "recipe terminal slot"),
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
            not isinstance(self.reason_code, str)
            or _SAFE_REASON.fullmatch(self.reason_code) is None
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
            "reason_code": self.reason_code,
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
            "partition": self.recipe.partition.value,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "reason_code": self.terminal.reason_code,
            "retry_allowed": False,
            "setup_controller_actions": self.terminal.setup_controller_actions,
            "setup_emulator_frames": self.terminal.setup_emulator_frames,
            "status": self.terminal.status.value,
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
    runtime_factory: RedLivingDexSetupRecipeRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexSetupRecipeRun:
    """Execute never-claimed recipes and recover every existing terminal."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("recipe campaign needs a validated private root")
    if not isinstance(plan, RedLivingDexSetupRecipePlan):
        raise TypeError("recipe campaign needs a frozen recipe plan")
    plan.__post_init__()
    if not callable(runtime_factory):
        raise TypeError("recipe campaign needs a runtime factory")
    if not isinstance(meter, RedLivingDexSetupEffectMeter):
        raise TypeError("recipe campaign needs an independent effect meter")
    _seal_plan(store, plan)
    receipts: list[RedLivingDexSetupRecipeReceipt] = []
    with store.collection_session(RED_LIVING_DEX_RECIPE_COLLECTION_ID) as session:
        for ordinal, (slot, recipe) in enumerate(
            zip(plan.prospective_plan.slots, plan.recipes, strict=True)
        ):
            receipts.append(
                _run_recipe(
                    store,
                    session,
                    plan,
                    slot,
                    recipe,
                    ordinal=ordinal,
                    runtime_factory=runtime_factory,
                    meter=meter,
                )
            )
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
        if sealed.read() != record:
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
    *,
    ordinal: int,
    runtime_factory: RedLivingDexSetupRecipeRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
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
        state = session.recover_interrupted_episode(episode_id)
    if state.status == "complete":
        capture = _load_capture(store, plan, recipe, episode_id)
        terminal = _complete_terminal(plan, recipe, claim_sha256, capture)
        _publish_terminal(store, recipe, terminal)
        return RedLivingDexSetupRecipeReceipt(
            recipe,
            terminal,
            state,
            RedLivingDexSetupRecipeDisposition.RECOVERED_COMPLETE,
            capture,
        )
    if state.status in {"failed", "interrupted"}:
        status = (
            LivingDexCaptureSetupStatus.FAILED
            if state.status == "failed"
            else LivingDexCaptureSetupStatus.INTERRUPTED
        )
        terminal = RedLivingDexSetupRecipeTerminal(
            recipe_plan_sha256=plan.plan_sha256,
            recipe_sha256=recipe.recipe_sha256,
            slot_sha256=recipe.slot_sha256,
            claim_sha256=claim_sha256,
            status=status,
            reason_code=state.reason_code or "process_interrupted",
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
    return _execute_recipe(
        store,
        plan,
        slot,
        recipe,
        episode_id=episode_id,
        claim=claim,
        claim_sha256=claim_sha256,
        runtime_factory=runtime_factory,
        meter=meter,
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
    runtime_factory: RedLivingDexSetupRecipeRuntimeFactory,
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexSetupRecipeReceipt:
    from pokemon_red_completion.living_dex_capture_curriculum import (
        LivingDexProspectiveCaptureSlot,
    )

    assert isinstance(slot, LivingDexProspectiveCaptureSlot)
    before = _checkpoint(meter)
    with store.begin_episode(episode_id) as writer:
        writer.append("claim", claim, durable=True)
        if _checkpoint(meter) != before:
            raise RedLivingDexSetupRecipeCampaignError("recipe claim changed the controller budget")
        try:
            runtime = runtime_factory(recipe)
            if not isinstance(runtime, RedLivingDexSetupRecipeRuntime):
                raise TypeError("recipe factory returned an invalid runtime")
            capture = validate_red_living_dex_setup_recipe(
                slot,
                recipe,
                runtime=runtime,
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
                reason_code=("process_interrupted" if interrupted else "recipe_execution_failed"),
                interrupted=interrupted,
            )
            if interrupted:
                raise
            raise RedLivingDexSetupRecipeCampaignError(
                "recipe execution failed after durable claim"
            ) from None
        summary = writer.complete()
    state = EpisodeArtifactState(
        episode_id,
        "complete",
        manifest_sha256=summary.manifest_sha256,
    )
    terminal = _complete_terminal(plan, recipe, claim_sha256, capture)
    _publish_terminal(store, recipe, terminal)
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
    before: RoutedSemanticBudgetCheckpoint,
    meter: RedLivingDexSetupEffectMeter,
    reason_code: str,
    interrupted: bool = False,
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
        claim_sha256=claim_sha256,
        status=status,
        reason_code=reason_code,
        setup_controller_actions=actions,
        setup_emulator_frames=frames,
        attestation_sha256=None,
    )
    writer.append("failure", terminal.private_dict(), durable=True)
    _publish_terminal(store, recipe, terminal)
    summary = writer.abort(reason_code)
    state = EpisodeArtifactState(
        summary.episode_id,
        "failed",
        reason_code=reason_code,
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
        claim_sha256=_string(document["claim_sha256"], "terminal claim"),
        status=status,
        reason_code=_optional_string(document["reason_code"], "terminal reason"),
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


def _episode_id(recipe: RedLivingDexSetupSlotRecipe, ordinal: int) -> str:
    return f"red-living-dex-recipe-{ordinal:02d}-{recipe.recipe_sha256[:20]}"


def _terminal_record_id(recipe: RedLivingDexSetupSlotRecipe) -> str:
    return f"red-living-dex-recipe-terminal-{recipe.recipe_sha256[:24]}"


def _checkpoint(
    meter: RedLivingDexSetupEffectMeter,
) -> RoutedSemanticBudgetCheckpoint:
    value = meter.checkpoint()
    if not isinstance(value, RoutedSemanticBudgetCheckpoint):
        raise RedLivingDexSetupRecipeCampaignError("recipe campaign effect checkpoint differs")
    return value


def _delta(
    before: RoutedSemanticBudgetCheckpoint,
    after: RoutedSemanticBudgetCheckpoint,
) -> tuple[int, int]:
    actions = after.controller_actions - before.controller_actions
    frames = after.emulator_frames - before.emulator_frames
    if actions < 0 or frames < 0:
        raise RedLivingDexSetupRecipeCampaignError("recipe campaign counters moved backwards")
    return actions, frames


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
