"""Exercise admission through the real causal journal and existing CPU fitter."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_living_dex_causal_journal import _scenario, _store_and_registry
from test_living_dex_causal_model_update import _publish_prior, _rows, _source
from test_red_living_dex_targeted_bank_retirement import _capabilities

import pokemon_red_completion.red_living_dex_targeted_train_fit as bridge
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
)
from pokemon_red_completion.living_dex_causal_journal import (
    load_living_dex_authenticated_causal_examples,
    materialize_living_dex_causal_example,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_living_dex_targeted_bank_retirement import (
    plan_red_living_dex_targeted_bank_retirement,
)
from pokemon_red_completion.red_living_dex_targeted_train_dashboard import (
    RedLivingDexTargetedTrainDashboardError,
    RedLivingDexTargetedTrainDashboardProgress,
    red_living_dex_targeted_train_dashboard_snapshot,
)
from pokemon_red_completion.red_living_dex_targeted_train_readiness import (
    audit_red_living_dex_targeted_train_readiness,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RedLivingDexTargetedSetupStatus,
    RedLivingDexTargetedTrainAssignment,
    RedLivingDexTargetedTrainReceipt,
)


@pytest.fixture(scope="module")
def binding():
    return plan_red_living_dex_targeted_bank_retirement(_capabilities()).binding


def _start(tmp_path, binding):
    store, registry = _store_and_registry(tmp_path)
    baseline = []
    for ordinal, row in enumerate(_rows(8)):
        scenario, _ = _scenario(f"prior-{ordinal}")
        scenario = replace(
            scenario,
            menu=row.menu,
            identity=replace(scenario.identity, menu_sha256=row.menu.policy_sha256),
        )
        causal = materialize_living_dex_causal_example(
            scenario,
            store=store,
            claim_registry=registry,
        )
        baseline.append(causal.example)
    _publish_prior(store, tuple(baseline))
    prior = store.find_sealed_record(
        LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
        expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
    )
    kwargs = dict(
        source=_source(),
        claim_registry=registry,
        prior_model_record_id=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
        prior_model_sha256=prior.read()["model_sha256"],
        prior_model_record_sha256=prior.summary.record_sha256,
    )
    return store, registry, kwargs


def _collect(store, registry, binding, *, alternate_develop=False, negative=False):
    receipts = []
    for ordinal, slot in enumerate(binding.schedule.slots):
        if slot.partition != "train":
            continue
        assignment = RedLivingDexTargetedTrainAssignment(binding, ordinal, _source().source_commit)
        scenario, _ = _scenario(
            f"trial-{ordinal}",
            lineage=slot.lineage_sha256,
            repeatable_trial_claim_sha256=assignment.trial.trial_claim_sha256,
        )
        kind = (
            LivingDexOptionKind.EXPLORE
            if alternate_develop and slot.focus_kind is LivingDexOptionKind.DEVELOP
            else slot.focus_kind
        )
        # Keep two distinct feature rows with legal support. Both represent the
        # named actual skill here; their identity is not the schedule's focus.
        menu = replace(
            scenario.menu,
            candidates=tuple(
                replace(candidate, features=replace(candidate.features, kind=kind))
                for candidate in scenario.menu.candidates
            ),
        )
        observe = scenario.observe_after

        def outcome(observe=observe):
            observed = observe()
            return (
                replace(
                    observed,
                    outcome=replace(
                        observed.outcome,
                        verified_success=False,
                        completion_gain=0.0,
                    ),
                )
                if negative
                else observed
            )

        scenario = replace(
            scenario,
            menu=menu,
            observe_after=outcome,
            identity=replace(scenario.identity, menu_sha256=menu.policy_sha256),
        )
        causal = materialize_living_dex_causal_example(
            scenario,
            store=store,
            claim_registry=registry,
        )
        receipts.append(
            RedLivingDexTargetedTrainReceipt(
                assignment,
                RedLivingDexTargetedSetupStatus.COMPLETE,
                causal,
            )
        )
    return tuple(receipts)


def test_real_journal_to_existing_fitter_preserves_baseline_negatives_and_recovers(
    tmp_path,
    binding,
):
    store, registry, kwargs = _start(tmp_path, binding)
    bridge.prepare_red_living_dex_targeted_fit_basis(store, binding, **kwargs, dry_run=True)
    assert (
        store.find_sealed_record(
            bridge._basis_id(binding),
            expected_kind=bridge._BASIS_KIND,
        )
        is None
    )
    bridge.prepare_red_living_dex_targeted_fit_basis(store, binding, **kwargs)
    receipts = _collect(store, registry, binding, negative=True)
    readiness = audit_red_living_dex_targeted_train_readiness(binding, receipts)
    assert readiness.ready
    assert readiness.settled_examples == 8
    assert readiness.settled_root_count == 4
    assert dict(readiness.settled_by_kind)[LivingDexOptionKind.DEVELOP] == 4
    result = bridge.fit_red_living_dex_targeted_train_from_store(
        store,
        binding,
        receipts,
        source=_source(),
    )
    assert result.total_examples == 16
    assert result.added_settled_examples == 8
    assert result.successful_examples == 8  # Eight genuine negative lessons were not dropped.
    assert not result.recovered_existing_artifact
    bridge.prepare_red_living_dex_targeted_fit_basis(store, binding, **kwargs)
    recovered = bridge.fit_red_living_dex_targeted_train_from_store(
        store,
        binding,
        receipts,
        source=_source(),
    )
    assert recovered.recovered_existing_artifact
    assert recovered.model_sha256 == result.model_sha256
    snapshot = red_living_dex_targeted_train_dashboard_snapshot(
        binding,
        RedLivingDexTargetedTrainDashboardProgress(
            status="passed",
            receipts=receipts,
            fit_result=result,
        ),
    )
    assert snapshot.experiment.sealed_completed == 1
    assert snapshot.model.mode == "waiting"  # Fitting does not silently deploy a policy.
    assert "not held-out performance" in " ".join(snapshot.events)


def test_actual_choice_not_planned_focus_controls_admission_and_dashboard(tmp_path, binding):
    store, registry, kwargs = _start(tmp_path, binding)
    bridge.prepare_red_living_dex_targeted_fit_basis(store, binding, **kwargs)
    receipts = _collect(store, registry, binding, alternate_develop=True)
    readiness = audit_red_living_dex_targeted_train_readiness(binding, receipts)
    assert not readiness.ready
    assert readiness.reasons == ("insufficient_actual_develop",)
    assert dict(readiness.settled_by_kind)[LivingDexOptionKind.EXPLORE] == 4
    with pytest.raises(bridge.RedLivingDexTargetedTrainFitError, match="campaign_not_ready"):
        bridge.fit_red_living_dex_targeted_train_from_store(
            store,
            binding,
            receipts,
            source=_source(),
        )
    snapshot = red_living_dex_targeted_train_dashboard_snapshot(
        binding,
        RedLivingDexTargetedTrainDashboardProgress(status="passed", receipts=receipts),
    )
    assert "develop 0 of 3" in " ".join(snapshot.events)
    assert "Do not fit" in snapshot.work.next_step
    assert "insufficient_actual_develop" in json.dumps(readiness.public_dict())


def test_early_coverage_does_not_hide_unfinished_slots(tmp_path, binding):
    store, registry, _ = _start(tmp_path, binding)
    receipts = _collect(store, registry, binding)
    # Withhold nonmandatory storage/resupply outcomes: acquire/develop floors
    # are satisfied, but the terminal denominator must still be eight.
    partial = tuple(
        item
        for item in receipts
        if item.assignment.slot.focus_kind
        in {
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.DEVELOP,
        }
    )
    readiness = audit_red_living_dex_targeted_train_readiness(binding, partial)
    assert readiness.settled_examples == 6
    assert readiness.reasons == ("incomplete_train_denominator",)
    with pytest.raises(RedLivingDexTargetedTrainDashboardError, match="unready"):
        red_living_dex_targeted_train_dashboard_snapshot(
            binding,
            RedLivingDexTargetedTrainDashboardProgress(
                status="running",
                receipts=partial,
                fitting=True,
            ),
        )


def test_basis_detects_lost_or_changed_baseline_before_fitting(tmp_path, binding, monkeypatch):
    store, registry, kwargs = _start(tmp_path, binding)
    bridge.prepare_red_living_dex_targeted_fit_basis(store, binding, **kwargs)
    receipts = _collect(store, registry, binding)
    rows = load_living_dex_authenticated_causal_examples(store)
    retained = tuple(row for row in rows if row.identity.repeatable_trial_claim_sha256 is not None)
    monkeypatch.setattr(
        bridge, "load_living_dex_authenticated_causal_examples", lambda *a, **k: retained
    )
    with pytest.raises(bridge.RedLivingDexTargetedTrainFitError, match="baseline_rows_lost"):
        bridge.fit_red_living_dex_targeted_train_from_store(
            store,
            binding,
            receipts,
            source=_source(),
        )


def test_basis_prior_and_receipt_join_fail_before_fit(tmp_path, binding):
    store, registry, kwargs = _start(tmp_path, binding)
    with pytest.raises(bridge.RedLivingDexTargetedTrainFitError, match="basis_prior_join"):
        bridge.prepare_red_living_dex_targeted_fit_basis(
            store,
            binding,
            **{**kwargs, "prior_model_sha256": "f" * 64},
        )
    receipts = _collect(store, registry, binding)
    with pytest.raises(bridge.RedLivingDexTargetedTrainFitError, match="fit_basis_missing"):
        bridge.fit_red_living_dex_targeted_train_from_store(
            store,
            binding,
            receipts,
            source=_source(),
        )
    with pytest.raises(ValueError, match="roster differs"):
        audit_red_living_dex_targeted_train_readiness(binding, receipts + receipts[:1])
