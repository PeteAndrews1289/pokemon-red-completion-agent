"""Connect the bounded campaign to the existing learner without losing history."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.goal_manager_composition_qualification import root_claim_is_available
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
    LivingDexCausalIntegrationSource,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LIVING_DEX_CAUSAL_COLLECTION_ID,
    LivingDexAuthenticatedCausalExample,
    load_living_dex_authenticated_causal_examples,
)
from pokemon_red_completion.living_dex_causal_model_update import (
    LivingDexCausalModelUpdateAdmission,
    LivingDexCausalModelUpdateResult,
    _model_from_record,
    fit_living_dex_causal_model_update_from_store,
)
from pokemon_red_completion.living_dex_option_value import living_dex_option_train_dataset_sha256
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_targeted_train_readiness import (
    audit_red_living_dex_targeted_train_readiness,
    targeted_receipt_has_settled_example,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RedLivingDexTargetedTrainAssignment,
    RedLivingDexTargetedTrainReceipt,
)

_BASIS_KIND = "red_living_dex_targeted_fit_basis"
_BASIS_SCHEMA = "pokemon.red.private-targeted-fit-basis.v1"


class RedLivingDexTargetedTrainFitError(RuntimeError):
    """A corpus, prior or campaign cannot be admitted to the learner."""


def _basis_id(binding: RedLivingDexTargetedScheduleBinding) -> str:
    return f"lrt-fit-basis-{binding.schedule.schedule_sha256}"


def _row_fingerprints(
    rows: tuple[LivingDexAuthenticatedCausalExample, ...],
) -> dict[str, str]:
    result = {
        item.example.decision_sha256: canonical_sha256(item.example.public_dict()) for item in rows
    }
    if len(result) != len(rows) or any(item.example.partition != "train" for item in rows):
        raise RedLivingDexTargetedTrainFitError("baseline_corpus_identity")
    return result


def prepare_red_living_dex_targeted_fit_basis(
    store: PrivateArtifactRoot,
    binding: RedLivingDexTargetedScheduleBinding,
    *,
    source: LivingDexCausalIntegrationSource,
    prior_model_record_id: str,
    prior_model_sha256: str,
    prior_model_record_sha256: str,
    claim_registry: Path,
    dry_run: bool = False,
) -> None:
    """Persist the full prior corpus before any trial, or authenticate its reopen."""

    expected = {
        "schema": _BASIS_SCHEMA,
        "binding_sha256": binding.binding_sha256,
        "source": source.private_dict(),
        "prior_model_record_id": prior_model_record_id,
        "prior_model_sha256": prior_model_sha256,
        "prior_model_record_sha256": prior_model_record_sha256,
    }
    prior = store.find_sealed_record(
        prior_model_record_id, expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND
    )
    if prior is None or (
        prior.summary.record_sha256 != prior_model_record_sha256
        or _model_from_record(prior).model_sha256 != prior_model_sha256
    ):
        raise RedLivingDexTargetedTrainFitError("basis_prior_join")
    with store.collection_session(LIVING_DEX_CAUSAL_COLLECTION_ID) as session:
        rows = load_living_dex_authenticated_causal_examples(store, collection_session=session)
        fingerprints = _row_fingerprints(rows)
        if not fingerprints:
            raise RedLivingDexTargetedTrainFitError("baseline_corpus_empty")
        with store.collection_session("targeted-fit-basis-v1"):
            retained = store.find_sealed_record(_basis_id(binding), expected_kind=_BASIS_KIND)
            if retained is not None:
                document = retained.read()
                if any(document.get(key) != value for key, value in expected.items()):
                    raise RedLivingDexTargetedTrainFitError("basis_identity_join")
                _require_baseline(document, fingerprints)
                return
            for ordinal, slot in enumerate(binding.schedule.slots):
                if slot.partition != "train":
                    continue
                trial = RedLivingDexTargetedTrainAssignment(
                    binding, ordinal, source.source_commit
                ).trial
                if not root_claim_is_available(claim_registry, trial.trial_claim_sha256):
                    raise RedLivingDexTargetedTrainFitError("basis_must_precede_trials")
            if dry_run:
                return
            store.publish_sealed_record(
                _basis_id(binding),
                kind=_BASIS_KIND,
                record={**expected, "baseline_examples": fingerprints},
            )


def _require_baseline(document: Mapping[str, object], current: dict[str, str]) -> None:
    baseline = document.get("baseline_examples")
    if (
        not isinstance(baseline, Mapping)
        or not baseline
        or any(
            not isinstance(key, str) or not isinstance(value, str) or current.get(key) != value
            for key, value in baseline.items()
        )
    ):
        raise RedLivingDexTargetedTrainFitError("baseline_rows_lost_or_changed")


def fit_red_living_dex_targeted_train_from_store(
    store: PrivateArtifactRoot,
    binding: RedLivingDexTargetedScheduleBinding,
    receipts: tuple[RedLivingDexTargetedTrainReceipt, ...],
    *,
    source: LivingDexCausalIntegrationSource,
) -> LivingDexCausalModelUpdateResult:
    """Require factual coverage, exact retained outcomes and every baseline row."""

    readiness = audit_red_living_dex_targeted_train_readiness(binding, receipts)
    if not readiness.ready:
        raise RedLivingDexTargetedTrainFitError("campaign_not_ready")
    basis = store.find_sealed_record(_basis_id(binding), expected_kind=_BASIS_KIND)
    if basis is None:
        raise RedLivingDexTargetedTrainFitError("fit_basis_missing")
    document = basis.read()
    if (
        document.get("schema") != _BASIS_SCHEMA
        or document.get("binding_sha256") != binding.binding_sha256
        or document.get("source") != source.private_dict()
        or any(item.assignment.source_commit != source.source_commit for item in receipts)
    ):
        raise RedLivingDexTargetedTrainFitError("fit_basis_join")
    with store.collection_session(LIVING_DEX_CAUSAL_COLLECTION_ID) as session:
        rows = load_living_dex_authenticated_causal_examples(store, collection_session=session)
        _require_baseline(document, _row_fingerprints(rows))
        by_trial = {
            item.identity.repeatable_trial_claim_sha256: item
            for item in rows
            if item.identity.repeatable_trial_claim_sha256 is not None
        }
        if len(by_trial) != sum(
            item.identity.repeatable_trial_claim_sha256 is not None for item in rows
        ):
            raise RedLivingDexTargetedTrainFitError("duplicate_factual_trial")
        for receipt in receipts:
            retained = by_trial.get(receipt.assignment.trial.trial_claim_sha256)
            if targeted_receipt_has_settled_example(receipt):
                assert receipt.causal is not None
                if retained is None or (
                    retained.example != receipt.causal.example
                    or retained.identity != receipt.causal.scenario.identity
                    or retained.terminal != receipt.causal.terminal
                    or retained.identity.lineage_sha256 != receipt.assignment.slot.lineage_sha256
                ):
                    raise RedLivingDexTargetedTrainFitError("factual_receipt_corpus_join")
            elif retained is not None:
                raise RedLivingDexTargetedTrainFitError("censored_trial_has_target")
        # The generic fitter reloads under its own lock and requires this exact
        # digest. A concurrent writer cannot silently change what was admitted.
        admission = LivingDexCausalModelUpdateAdmission(
            prior_model_record_id=str(document["prior_model_record_id"]),
            prior_model_sha256=str(document["prior_model_sha256"]),
            prior_model_record_sha256=str(document["prior_model_record_sha256"]),
            train_dataset_sha256=living_dex_option_train_dataset_sha256(
                item.example for item in rows
            ),
            campaign_readiness_sha256=canonical_sha256(
                {
                    "basis_record_sha256": basis.summary.record_sha256,
                    "readiness_sha256": readiness.readiness_sha256,
                    "training_root_treatment": (
                        "row_weighted_repeated_lessons_not_independent_worlds"
                    ),
                }
            ),
        )
    return fit_living_dex_causal_model_update_from_store(store, source=source, admission=admission)
