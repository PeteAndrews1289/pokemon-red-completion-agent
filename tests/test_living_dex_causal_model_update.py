from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion import living_dex_causal_model_update as update_module
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA,
    LivingDexCausalIntegrationSource,
)
from pokemon_red_completion.living_dex_causal_model_update import (
    LIVING_DEX_CAUSAL_UPDATE_CLAIM_KIND,
    LivingDexCausalModelUpdateAdmission,
    LivingDexCausalModelUpdateError,
    fit_living_dex_causal_model_update_from_store,
)
from pokemon_red_completion.living_dex_goal_model_record import (
    load_living_dex_goal_model_record,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOutcomeStatus,
    fit_living_dex_option_value,
    living_dex_option_train_dataset_sha256,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)


def _store(tmp_path: Path) -> tuple[Path, PrivateArtifactRoot]:
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == private.resolve() else 1

    return private, initialize_private_root(
        private,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


def _rows(count: int = 12) -> tuple[LivingDexObservedArmExample, ...]:
    kinds = tuple(LivingDexOptionKind)
    rows: list[LivingDexObservedArmExample] = []
    for ordinal in range(count):
        context = LivingDexOptionContext(
            *((ordinal * prime % 13) / 12 for prime in (1, 2, 3, 4, 5, 6, 7))
        )
        candidates = tuple(
            LivingDexOptionCandidate(
                f"private-binding-{ordinal}-{candidate_index}",
                LivingDexOptionFeatures(
                    kind=kinds[(ordinal + candidate_index) % len(kinds)],
                    completion_gain=((ordinal + candidate_index + 1) % 11) / 10,
                    dependency_unlock_gain=((ordinal * 2 + candidate_index + 1) % 11)
                    / 10,
                    travel_effort=((ordinal * 3 + candidate_index + 1) % 11) / 10,
                    execution_effort=((ordinal * 4 + candidate_index + 1) % 11) / 10,
                    resource_cost=((ordinal + candidate_index) % 5) / 10,
                    storage_cost=((ordinal + candidate_index + 1) % 5) / 10,
                    party_risk=((ordinal + candidate_index + 2) % 5) / 10,
                    irreversibility_risk=0.0,
                    uncertainty=((ordinal + candidate_index + 3) % 6) / 10,
                ),
                LivingDexOptionAvailability.AVAILABLE,
            )
            for candidate_index in range(3)
        )
        rows.append(
            LivingDexObservedArmExample(
                decision_sha256=f"{ordinal + 1:064x}",
                partition="train",
                menu=LivingDexOptionMenu(context, candidates),
                selected_candidate_index=ordinal % 3,
                behavior_probabilities=(1.0 / 3.0,) * 3,
                outcome=LivingDexObservedOutcome(
                    LivingDexOutcomeStatus.SETTLED,
                    verified_success=ordinal % 4 == 0,
                    completion_gain=(ordinal % 5) / 5,
                    dependency_unlock_gain=(ordinal % 6) / 6,
                    action_cost=((ordinal + 1) % 10) / 10,
                    frame_cost=((ordinal + 2) % 10) / 10,
                    resource_cost=(ordinal % 3) / 10,
                    party_cost=((ordinal + 1) % 3) / 10,
                    storage_cost=((ordinal + 2) % 3) / 10,
                    irreversible_loss=0.0,
                ),
            )
        )
    return tuple(rows)


def _source() -> LivingDexCausalIntegrationSource:
    return LivingDexCausalIntegrationSource(
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        exact_ci_run=123,
        exact_ci_attempt=1,
    )


def _publish_prior(
    store: PrivateArtifactRoot,
    rows: tuple[LivingDexObservedArmExample, ...],
) -> None:
    fit = fit_living_dex_option_value(rows[:8])
    store.publish_sealed_record(
        LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
        kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
        record={
            "authority": "non_authoritative_integration_only",
            "claim_manifest_sha256": "c" * 64,
            "claim_record_sha256": "d" * 64,
            "diagnostics": {
                "coefficient_count": 225,
                "finite_coefficient_count": 225,
                "normal_equation_condition_number": 2.0,
            },
            "model": fit.model.to_dict(),
            "model_sha256": fit.model.model_sha256,
            "readiness_result_sha256": "e" * 64,
            "schema": LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA,
            "source": _source().private_dict(),
            "train_dataset_sha256": fit.model.train_dataset_sha256,
        },
    )


def _patch_corpus(
    monkeypatch: pytest.MonkeyPatch,
    store: PrivateArtifactRoot,
    rows: tuple[LivingDexObservedArmExample, ...],
) -> None:
    def load(
        opened: PrivateArtifactRoot,
        *,
        maximum_examples: int = 100,
        collection_session: object | None = None,
    ) -> tuple[SimpleNamespace, ...]:
        assert opened is store
        assert maximum_examples == 100
        assert collection_session is not None
        collection_session.require_store(opened)  # type: ignore[union-attr]
        return tuple(SimpleNamespace(example=row) for row in rows)

    monkeypatch.setattr(
        update_module,
        "load_living_dex_authenticated_causal_examples",
        load,
    )


def test_extended_corpus_fits_and_reopens_one_immutable_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _publish_prior(store, rows)
    _patch_corpus(monkeypatch, store, rows)

    first = fit_living_dex_causal_model_update_from_store(store, source=_source())
    recovered = fit_living_dex_causal_model_update_from_store(store, source=_source())

    assert first.total_examples == 12
    assert first.settled_examples == 12
    assert first.added_settled_examples == 4
    assert first.model_sha256 != first.prior_model_sha256
    assert not first.recovered_existing_artifact
    assert recovered.recovered_existing_artifact
    assert recovered.model_sha256 == first.model_sha256
    dataset_sha256 = living_dex_option_train_dataset_sha256(rows)
    claim_id = f"lc-update-claim-{dataset_sha256}"
    model_id = f"lc-update-model-{dataset_sha256}"
    assert len(claim_id) == 80
    assert len(model_id) == 80
    assert store.find_sealed_record(
        claim_id,
        expected_kind=LIVING_DEX_CAUSAL_UPDATE_CLAIM_KIND,
    ) is not None
    model_path = private / model_id / "record.json"
    loaded = load_living_dex_goal_model_record(
        model_path,
        expected_model_sha256=first.model_sha256,
    )
    assert loaded.model.settled_examples == 12
    assert loaded.model.model_sha256 == first.model_sha256

    public = first.public_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["development_examples_read"] == 0
    assert public["controller_actions"] == 0
    assert public["fit_executions"] == 1
    assert recovered.public_dict()["fit_executions"] == 0
    assert "private-binding" not in encoded
    assert str(private) not in encoded
    assert dataset_sha256 not in encoded


def test_update_refuses_missing_prior_model_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _patch_corpus(monkeypatch, store, rows)

    with pytest.raises(LivingDexCausalModelUpdateError) as raised:
        fit_living_dex_causal_model_update_from_store(store, source=_source())

    assert raised.value.stage == "prior_model_absent"
    assert not any(path.name.startswith("lc-update-") for path in private.iterdir())


def test_admitted_update_uses_the_named_latest_prior_and_reopens_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _private, store = _store(tmp_path)
    prior_rows = _rows(12)
    _publish_prior(store, prior_rows)
    _patch_corpus(monkeypatch, store, prior_rows)
    previous = fit_living_dex_causal_model_update_from_store(store, source=_source())
    rows = _rows(16)
    _patch_corpus(monkeypatch, store, rows)
    admission = LivingDexCausalModelUpdateAdmission(
        prior_model_record_id=f"lc-update-model-{living_dex_option_train_dataset_sha256(prior_rows)}",
        prior_model_sha256=previous.model_sha256,
        prior_model_record_sha256=previous.model_record_sha256,
        train_dataset_sha256=living_dex_option_train_dataset_sha256(rows),
        campaign_readiness_sha256="e" * 64,
    )
    first = fit_living_dex_causal_model_update_from_store(
        store, source=_source(), admission=admission
    )
    assert first.prior_model_sha256 == previous.model_sha256
    assert first.added_settled_examples == 4
    recovered = fit_living_dex_causal_model_update_from_store(
        store, source=_source(), admission=admission
    )
    assert recovered.recovered_existing_artifact
    assert recovered.model_sha256 == first.model_sha256
    with pytest.raises(LivingDexCausalModelUpdateError, match="admission_corpus_join"):
        fit_living_dex_causal_model_update_from_store(
            store, source=_source(),
            admission=replace(admission, train_dataset_sha256="f" * 64),
        )
    with pytest.raises(LivingDexCausalModelUpdateError, match="admission_prior_join"):
        fit_living_dex_causal_model_update_from_store(
            store, source=_source(),
            admission=replace(admission, prior_model_sha256="f" * 64),
        )


def test_generic_fitter_cannot_silently_admit_reset_campaign_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _publish_prior(store, rows)
    monkeypatch.setattr(
        update_module, "load_living_dex_authenticated_causal_examples",
        lambda *args, **kwargs: tuple(
            SimpleNamespace(
                example=row,
                identity=SimpleNamespace(repeatable_trial_claim_sha256="a" * 64),
            ) for row in rows
        ),
    )
    with pytest.raises(LivingDexCausalModelUpdateError, match="targeted_admission_required"):
        fit_living_dex_causal_model_update_from_store(store, source=_source())
    assert not any(path.name.startswith("lc-update-") for path in private.iterdir())


def test_update_refuses_development_leakage_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _publish_prior(store, rows)
    leaked = (*rows[:-1], LivingDexObservedArmExample(
        decision_sha256=rows[-1].decision_sha256,
        partition="development",
        menu=rows[-1].menu,
        selected_candidate_index=rows[-1].selected_candidate_index,
        behavior_probabilities=rows[-1].behavior_probabilities,
        outcome=rows[-1].outcome,
    ))
    _patch_corpus(monkeypatch, store, leaked)

    with pytest.raises(LivingDexCausalModelUpdateError) as raised:
        fit_living_dex_causal_model_update_from_store(store, source=_source())

    assert raised.value.stage == "corpus_not_extended"
    assert not any(path.name.startswith("lc-update-") for path in private.iterdir())


def test_existing_claim_can_finish_deterministic_publication_after_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _publish_prior(store, rows)
    _patch_corpus(monkeypatch, store, rows)
    original = PrivateArtifactRoot.publish_sealed_record
    interrupted = False

    def publish(
        opened: PrivateArtifactRoot,
        record_id: str,
        *,
        kind: str,
        record: dict[str, object],
    ):
        nonlocal interrupted
        if record_id.startswith("lc-update-model-") and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return original(opened, record_id, kind=kind, record=record)

    monkeypatch.setattr(PrivateArtifactRoot, "publish_sealed_record", publish)
    with pytest.raises(LivingDexCausalModelUpdateError) as raised:
        fit_living_dex_causal_model_update_from_store(store, source=_source())
    assert raised.value.stage == "private_corpus_or_store"
    assert raised.value.fit_executions == 1
    assert raised.value.private_fit_claims == 1
    dataset_sha256 = living_dex_option_train_dataset_sha256(rows)
    assert (private / f"lc-update-claim-{dataset_sha256}").is_dir()
    assert not (private / f"lc-update-model-{dataset_sha256}").exists()

    result = fit_living_dex_causal_model_update_from_store(store, source=_source())
    assert result.model_sha256 != result.prior_model_sha256
    assert not result.recovered_existing_artifact


def test_existing_update_rejects_a_changed_source_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, store = _store(tmp_path)
    rows = _rows()
    _publish_prior(store, rows)
    _patch_corpus(monkeypatch, store, rows)
    fit_living_dex_causal_model_update_from_store(store, source=_source())
    changed = LivingDexCausalIntegrationSource(
        source_commit="f" * 40,
        source_bundle_sha256="b" * 64,
        exact_ci_run=123,
        exact_ci_attempt=1,
    )

    with pytest.raises(LivingDexCausalModelUpdateError) as raised:
        fit_living_dex_causal_model_update_from_store(store, source=changed)

    assert raised.value.stage == "prior_update_claim_join"
