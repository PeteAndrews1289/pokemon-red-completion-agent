from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion import (
    living_dex_causal_integration_fit as integration_fit_module,
)
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID,
    LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_KIND,
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
    LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256,
    LivingDexCausalIntegrationFitError,
    LivingDexCausalIntegrationSource,
    fit_living_dex_causal_integration_from_store,
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


def _rows() -> tuple[LivingDexObservedArmExample, ...]:
    kinds = tuple(LivingDexOptionKind)
    rows: list[LivingDexObservedArmExample] = []
    for ordinal in range(8):
        context = LivingDexOptionContext(
            *((ordinal * prime % 11) / 10 for prime in (1, 2, 3, 4, 5, 6, 7))
        )
        candidates = tuple(
            LivingDexOptionCandidate(
                f"private-binding-{ordinal}-{candidate_index}",
                LivingDexOptionFeatures(
                    kind=kinds[(ordinal + candidate_index) % len(kinds)],
                    completion_gain=((ordinal + candidate_index + 1) % 10) / 10,
                    dependency_unlock_gain=((ordinal * 2 + candidate_index + 1) % 10)
                    / 10,
                    travel_effort=((ordinal * 3 + candidate_index + 1) % 10) / 10,
                    execution_effort=((ordinal * 4 + candidate_index + 1) % 10) / 10,
                    resource_cost=((ordinal + candidate_index) % 4) / 10,
                    storage_cost=((ordinal + candidate_index + 1) % 4) / 10,
                    party_risk=((ordinal + candidate_index + 2) % 4) / 10,
                    irreversibility_risk=0.0,
                    uncertainty=((ordinal + candidate_index + 3) % 5) / 10,
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
                    verified_success=ordinal % 2 == 0,
                    completion_gain=(ordinal % 4) / 4,
                    dependency_unlock_gain=(ordinal % 5) / 5,
                    action_cost=(ordinal + 1) / 10,
                    frame_cost=(ordinal + 2) / 10,
                    resource_cost=(ordinal % 3) / 10,
                    party_cost=((ordinal + 1) % 3) / 10,
                    storage_cost=((ordinal + 2) % 3) / 10,
                    irreversible_loss=0.0,
                ),
            )
        )
    return tuple(rows)


def _readiness() -> SimpleNamespace:
    return SimpleNamespace(
        settled_examples=8,
        train_examples=8,
        candidate_feature_rows=24,
        supported_candidate_feature_rows=24,
        distinct_selected_feature_rows=8,
        variable_target_heads=7,
    )


def _source() -> LivingDexCausalIntegrationSource:
    return LivingDexCausalIntegrationSource(
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        exact_ci_run=123,
        exact_ci_attempt=1,
    )


def _patch_corpus(
    monkeypatch: pytest.MonkeyPatch,
    store: PrivateArtifactRoot,
    rows: tuple[LivingDexObservedArmExample, ...],
) -> list[object]:
    sessions: list[object] = []

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
        sessions.append(collection_session)
        return tuple(SimpleNamespace(example=row) for row in rows)

    monkeypatch.setattr(
        integration_fit_module,
        "load_living_dex_authenticated_causal_examples",
        load,
    )
    monkeypatch.setattr(
        integration_fit_module,
        "require_living_dex_causal_integration_ready",
        lambda examples: _readiness() if len(examples) == 8 else None,
    )
    return sessions


def test_complete_corpus_fits_once_and_reopens_exact_private_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    sessions = _patch_corpus(monkeypatch, store, rows)
    real_fit = integration_fit_module.fit_living_dex_option_value
    fit_calls: list[tuple[LivingDexObservedArmExample, ...]] = []

    def fit(examples: object):
        materialized = tuple(examples)  # type: ignore[arg-type]
        fit_calls.append(materialized)
        return real_fit(materialized)

    monkeypatch.setattr(integration_fit_module, "fit_living_dex_option_value", fit)

    first = fit_living_dex_causal_integration_from_store(
        store,
        source=_source(),
        readiness_result_sha256=LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256,
    )
    recovered = fit_living_dex_causal_integration_from_store(
        store,
        source=_source(),
        readiness_result_sha256=LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256,
    )

    assert len(sessions) == 2
    assert fit_calls == [rows]
    assert first.authentic_examples == 8
    assert first.settled_examples == 8
    assert first.reload_bytes_equal
    assert first.reload_model_equal
    assert not first.recovered_existing_artifact
    assert recovered.recovered_existing_artifact
    assert recovered.model_sha256 == first.model_sha256
    assert recovered.model_record_sha256 == first.model_record_sha256
    assert (private / LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID).is_dir()
    model_record = private / LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID / "record.json"
    assert model_record.is_file()
    assert store.find_sealed_record(
        LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
        expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
    ).read_bytes() == model_record.read_bytes()

    public = first.public_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["status"] == "non_authoritative_integration_fit_complete"
    assert public["fit_executions"] == 1
    assert public["complete_denominator_included"] is True
    assert public["gameplay_model_predictions"] == 0
    assert public["development_examples_read"] == 0
    assert public["authority_promotions"] == 0
    assert "weighted_mse" not in encoded
    assert "train_dataset_sha256" not in encoded
    assert "private-binding" not in encoded
    assert str(private) not in encoded


def test_failed_readiness_stops_before_claim_and_fit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _patch_corpus(monkeypatch, store, rows)
    fit_calls = 0

    def reject(_examples: object) -> object:
        raise ValueError("not ready")

    def forbidden_fit(_examples: object) -> object:
        nonlocal fit_calls
        fit_calls += 1
        raise AssertionError

    monkeypatch.setattr(
        integration_fit_module,
        "require_living_dex_causal_integration_ready",
        reject,
    )
    monkeypatch.setattr(
        integration_fit_module,
        "fit_living_dex_option_value",
        forbidden_fit,
    )

    with pytest.raises(
        LivingDexCausalIntegrationFitError,
        match="private_corpus_or_store",
    ):
        fit_living_dex_causal_integration_from_store(
            store,
            source=_source(),
            readiness_result_sha256=(
                LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
            ),
        )

    assert fit_calls == 0
    assert not (private / LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID).exists()
    assert not (private / LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID).exists()


def test_fit_claim_is_durable_before_fit_and_incomplete_claim_never_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _patch_corpus(monkeypatch, store, rows)
    fit_calls = 0

    def interrupt(_examples: object) -> object:
        nonlocal fit_calls
        fit_calls += 1
        assert store.find_sealed_record(
            LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID,
            expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_KIND,
        ) is not None
        raise KeyboardInterrupt

    monkeypatch.setattr(
        integration_fit_module,
        "fit_living_dex_option_value",
        interrupt,
    )

    with pytest.raises(LivingDexCausalIntegrationFitError) as first:
        fit_living_dex_causal_integration_from_store(
            store,
            source=_source(),
            readiness_result_sha256=(
                LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
            ),
        )
    assert first.value.stage == "model_fit"
    assert first.value.fit_executions == 1
    assert first.value.private_fit_claims == 1
    assert fit_calls == 1
    assert (private / LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID).is_dir()

    with pytest.raises(LivingDexCausalIntegrationFitError) as second:
        fit_living_dex_causal_integration_from_store(
            store,
            source=_source(),
            readiness_result_sha256=(
                LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
            ),
        )
    assert second.value.stage == "incomplete_prior_fit_claim"
    assert second.value.fit_executions == 0
    assert second.value.private_fit_claims == 1
    assert fit_calls == 1
    assert not (private / LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID).exists()


def test_fitter_cannot_silently_omit_one_authenticated_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, store = _store(tmp_path)
    rows = _rows()
    _patch_corpus(monkeypatch, store, rows)
    real_fit = integration_fit_module.fit_living_dex_option_value
    monkeypatch.setattr(
        integration_fit_module,
        "fit_living_dex_option_value",
        lambda examples: real_fit(tuple(examples)[:-1]),
    )

    with pytest.raises(LivingDexCausalIntegrationFitError) as raised:
        fit_living_dex_causal_integration_from_store(
            store,
            source=_source(),
            readiness_result_sha256=(
                LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
            ),
        )

    assert raised.value.stage == "complete_denominator_join"
    assert raised.value.fit_executions == 1
    assert raised.value.private_fit_claims == 1


def test_nonfinite_conditioning_stops_before_model_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, store = _store(tmp_path)
    rows = _rows()
    _patch_corpus(monkeypatch, store, rows)
    monkeypatch.setattr(integration_fit_module.np.linalg, "cond", lambda _matrix: float("inf"))

    with pytest.raises(LivingDexCausalIntegrationFitError) as raised:
        fit_living_dex_causal_integration_from_store(
            store,
            source=_source(),
            readiness_result_sha256=(
                LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
            ),
        )

    assert raised.value.stage == "fit_diagnostics"
    assert raised.value.fit_executions == 1
    assert raised.value.private_fit_claims == 1
    assert (private / LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID).is_dir()
    assert not (private / LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID).exists()
