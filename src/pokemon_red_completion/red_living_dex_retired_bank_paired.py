"""Use the four frozen routed development roots with the saved option model.

This is a consumer of the retired bank, not a new freezer or train runner. The
eight consumed train slots and any reserve are unreachable through this entry.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.claim_first_admission import ClaimFirstRootPair
from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel
from pokemon_red_completion.living_dex_paired_development import (
    LivingDexPairedDevelopmentReceipt,
    ensure_paired_claim,
    execute_living_dex_paired_development,
    private_failure_diagnostic,
    publish_paired_record,
    read_paired_record,
)
from pokemon_red_completion.living_dex_policy_development_journal import _ensure_store_anchor
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_adapter import (
    build_red_living_dex_causal_scenario_from_capture,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import RedLivingDexResolvedSetupSlot
from pokemon_red_completion.red_living_dex_production_runtime import (
    RedLivingDexProductionSetupResolver,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    restore_red_living_dex_validated_setup_capture,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupExecutionIdentity,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    _FrozenTargetedRecipe,
    _require_resolved,
)

RED_LIVING_DEX_RETIRED_PAIRED_RUNNER_SHA256 = canonical_sha256(
    {
        "schema": "pokemon.red.retired-bank-paired-runner.v1",
        "slots": [8, 9, 10, 11],
        "arms": ["living_dex_option_model", "completion_first_control"],
        "both_choices_before_either_outcome": True,
        "retry_started_arm": False,
        "refit": False,
        "promotion": False,
    }
)
_SCHEMA = "pokemon.red.private-retired-bank-paired-setup.v1"
_COLLECTION = "red-retired-bank-paired-setup-v1"


class RedLivingDexRetiredPairedError(ValueError):
    """A paired assignment differs from the frozen four-root contract."""


@dataclass(frozen=True, slots=True)
class RedLivingDexRetiredPairedAssignment:
    binding: RedLivingDexTargetedScheduleBinding
    ordinal: int

    def __post_init__(self) -> None:
        self.binding.__post_init__()
        slots = self.binding.schedule.slots
        if (
            type(self.ordinal) is not int  # noqa: E721
            or self.ordinal not in (8, 9, 10, 11)
            or len(slots) != 12
            or tuple(slot.partition for slot in slots) != ("train",) * 8 + ("development",) * 4
        ):
            raise RedLivingDexRetiredPairedError(
                "paired runner requires one of four frozen development slots"
            )

    @property
    def capability(self) -> RedLivingDexCausalRootCapability:
        return self.binding.capabilities[self.ordinal]

    def setup_claim(
        self,
        identity: RedLivingDexSetupExecutionIdentity,
        *,
        model_sha256: str,
        store_anchor_sha256: str,
    ) -> ClaimFirstRootPair:
        slot = self.binding.schedule.slots[self.ordinal]
        root = self.capability.root.root
        return retired_paired_setup_claim(
            root,
            identity,
            model_sha256=model_sha256,
            store_anchor_sha256=store_anchor_sha256,
            schedule_binding_sha256=self.binding.binding_sha256,
            schedule_sha256=self.binding.schedule.schedule_sha256,
            slot_sha256=slot.slot_sha256,
        )


def retired_paired_setup_claim(
    root: RedLivingDexAuthenticatedSetupRoot,
    identity: RedLivingDexSetupExecutionIdentity,
    *,
    model_sha256: str,
    store_anchor_sha256: str,
    schedule_binding_sha256: str,
    schedule_sha256: str,
    slot_sha256: str,
) -> ClaimFirstRootPair:
    """Same claim for action-free owned-recovery admission and the actual runner."""
    root.__post_init__()
    identity.__post_init__()
    bound = {
        "schedule_binding_sha256": schedule_binding_sha256,
        "slot_sha256": slot_sha256,
        "execution_identity_sha256": identity.identity_sha256,
        "model_sha256": model_sha256,
        "store_anchor_sha256": store_anchor_sha256,
        "schema": _SCHEMA,
    }
    return ClaimFirstRootPair(
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        stage="red-retired-bank-paired-setup",
        execution_identity_sha256=canonical_sha256(bound),
        plan_sha256=schedule_sha256,
        slot_sha256=slot_sha256,
        runner_sha256=RED_LIVING_DEX_RETIRED_PAIRED_RUNNER_SHA256,
        source_commit=identity.source_commit,
    )


@dataclass(frozen=True, slots=True)
class RedLivingDexRetiredPairedReceipt:
    ordinal: int
    setup: dict[str, object]
    comparison: LivingDexPairedDevelopmentReceipt | None

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.retired-bank-paired-result.v1",
            "pair_ordinal": self.ordinal - 8,
            "setup_status": self.setup["status"],
            "setup_failure_phase": self.setup.get("failure_phase"),
            "setup_controller_actions": self.setup.get("controller_actions"),
            "setup_emulator_frames": self.setup.get("emulator_frames"),
            "setup_terminal_sha256": canonical_sha256(self.setup),
            "comparison": None if self.comparison is None else self.comparison.public_dict(),
            "training_targets_emitted": 0,
            "model_fits": 0,
            "private_path_fields": 0,
            "promotion_authorized": False,
        }


def run_red_living_dex_retired_paired_assignment(
    assignment: RedLivingDexRetiredPairedAssignment,
    model: LivingDexOptionValueModel,
    *,
    expected_model_sha256: str,
    store: PrivateArtifactRoot,
    claim_registry: Path,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
    resolver: RedLivingDexProductionSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    observer: Callable[[str, Mapping[str, object]], None] | None = None,
    failpoint: Callable[[str], None] | None = None,
) -> RedLivingDexRetiredPairedReceipt:
    assignment.__post_init__()
    setup_execution_identity.__post_init__()
    resolver.__post_init__()
    model.__post_init__()
    if (
        resolver.producer_execution_identity != setup_execution_identity
        or model.model_sha256 != expected_model_sha256
        or type(meter) is not RedLivingDexSetupEffectMeter
    ):
        raise RedLivingDexRetiredPairedError("paired setup execution identity differs")
    with store.collection_session(_COLLECTION):
        anchor = _ensure_store_anchor(store)
        claim = assignment.setup_claim(
            setup_execution_identity,
            model_sha256=expected_model_sha256,
            store_anchor_sha256=anchor,
        )
        new_claim = ensure_paired_claim(claim_registry, claim)
        prefix = "red-paired-" + claim.claim_sha256[:32]
        frozen = _FrozenTargetedRecipe(assignment.capability)
        root = assignment.capability.root.root
        terminal = read_paired_record(store, prefix + "-setup-terminal")
        stored_capture = read_paired_record(store, prefix + "-capture")
        capture = None
        identity_fields = {
            "schema": _SCHEMA,
            "claim_sha256": claim.claim_sha256,
            "slot_ordinal": assignment.ordinal,
            "recipe_sha256": assignment.capability.recipe.recipe_sha256,
            "execution_identity_sha256": setup_execution_identity.identity_sha256,
        }
        if terminal is not None and any(terminal.get(k) != v for k, v in identity_fields.items()):
            raise RedLivingDexRetiredPairedError("paired setup terminal binding differs")
        if terminal is not None and terminal["status"] != "complete":
            if stored_capture is not None:
                raise RedLivingDexRetiredPairedError("failed paired setup retained a capture")
            return RedLivingDexRetiredPairedReceipt(assignment.ordinal, terminal, None)
        if stored_capture is not None:
            capture = restore_red_living_dex_validated_setup_capture(stored_capture)
        elif terminal is not None:
            raise RedLivingDexRetiredPairedError("paired setup lost its completed capture")
        elif not new_claim:
            terminal = publish_paired_record(
                store,
                prefix + "-setup-terminal",
                {
                    **identity_fields,
                    "status": "interrupted",
                    "failure_phase": "setup_claim_recovery",
                    "controller_actions": None,
                    "emulator_frames": None,
                },
            )
            return RedLivingDexRetiredPairedReceipt(assignment.ordinal, terminal, None)
        else:
            publish_paired_record(store, prefix + "-setup-start", identity_fields)
            before = meter.checkpoint()
            phase = ["resolver_reauthentication"]
            try:
                if failpoint is not None:
                    failpoint("after_setup_claim")
                with resolver(frozen, root, claim, meter=meter) as resolved:
                    _require_resolved(resolved, frozen, setup_execution_identity)
                    capture = validate_red_living_dex_setup_recipe(
                        assignment.capability.slot,
                        resolved.recipe,
                        execution_identity=setup_execution_identity,
                        root=root,
                        arm_factory=resolved.arm_factory,
                        meter=meter,
                        phase_observer=lambda value: phase.__setitem__(0, value),
                    )
            except BaseException as error:
                terminal = publish_paired_record(
                    store,
                    prefix + "-setup-terminal",
                    {
                        **identity_fields,
                        "status": "failed" if isinstance(error, Exception) else "interrupted",
                        "failure_phase": phase[0],
                        "private_diagnostic": private_failure_diagnostic(error),
                        "controller_actions": meter.controller_actions - before.controller_actions,
                        "emulator_frames": meter.emulator_frames - before.emulator_frames,
                    },
                )
                if not isinstance(error, Exception):
                    raise
                return RedLivingDexRetiredPairedReceipt(assignment.ordinal, terminal, None)
            publish_paired_record(store, prefix + "-capture", capture.private_dict())
        if (
            capture.recipe_sha256 != assignment.capability.recipe.recipe_sha256
            or capture.execution_identity_sha256 != setup_execution_identity.identity_sha256
            or capture.binding.slot_sha256 != assignment.capability.slot.slot_sha256
            or capture.binding.partition.value != "development"
        ):
            raise RedLivingDexRetiredPairedError("paired origin capture differs")
        terminal = publish_paired_record(
            store,
            prefix + "-setup-terminal",
            {
                **identity_fields,
                "status": "complete",
                "capture_sha256": canonical_sha256(capture.private_dict()),
                "controller_actions": capture.attestation.setup_controller_actions,
                "emulator_frames": capture.attestation.setup_emulator_frames,
            },
        )

    if capture is None or terminal is None:
        raise RedLivingDexRetiredPairedError("paired setup session suppressed an exception")

    @contextmanager
    def resolve_runtime() -> Iterator[RedLivingDexResolvedSetupSlot]:
        with resolver(frozen, root, claim, meter=meter) as resolved:
            _require_resolved(resolved, frozen, setup_execution_identity)
            yield resolved

    scenario = build_red_living_dex_causal_scenario_from_capture(
        capture,
        setup_execution_identity=setup_execution_identity,
        runtime_resolver=resolve_runtime,
        meter=meter,
        setup_terminal_sha256=canonical_sha256(terminal),
        setup_pair_claim_sha256=claim.claim_sha256,
        causal_source_commit=setup_execution_identity.source_commit,
        causal_runner_sha256=RED_LIVING_DEX_RETIRED_PAIRED_RUNNER_SHA256,
        upstream_lineage_sha256=assignment.binding.schedule.slots[
            assignment.ordinal
        ].lineage_sha256,
    )
    comparison = execute_living_dex_paired_development(
        scenario,
        model,
        expected_model_sha256=expected_model_sha256,
        store=store,
        claim_registry=claim_registry,
        observer=observer,
        failpoint=failpoint,
    )
    return RedLivingDexRetiredPairedReceipt(assignment.ordinal, terminal, comparison)


def retired_paired_campaign_summary(
    receipts: tuple[RedLivingDexRetiredPairedReceipt, ...],
) -> dict[str, object]:
    """Keep all four planned roots, including setup failures, in the denominator."""

    if tuple(item.ordinal for item in receipts) != (8, 9, 10, 11):
        raise RedLivingDexRetiredPairedError(
            "paired summary needs the complete four-root denominator"
        )
    comparisons = [
        item.comparison.public_dict() for item in receipts if item.comparison is not None
    ]
    return {
        "schema": "pokemon.red.retired-bank-paired-campaign.v1",
        "planned_pairs": 4,
        "terminal_pairs": 4,
        "setup_failures": sum(item.comparison is None for item in receipts),
        "settled_pairs": sum(item["utility_delta"] is not None for item in comparisons),
        "descriptive_model_wins": sum(
            item["descriptive_model_win"] is True for item in comparisons
        ),
        "pairs": [item.public_dict() for item in receipts],
        "training_targets_emitted": 0,
        "model_fits": 0,
        "promotion_authorized": False,
        "sealed_red_access": 0,
        "crystal_execution": 0,
        "evidence_scope": "descriptive_development_only",
        "private_path_fields": 0,
    }
