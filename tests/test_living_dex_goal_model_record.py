from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.living_dex_goal_model_record import (
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_RECORD_SCHEMA,
    LivingDexGoalModelRecordError,
    load_living_dex_goal_model_record,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionValueModel,
)


def _model() -> LivingDexOptionValueModel:
    features = len(LIVING_DEX_OPTION_FEATURE_NAMES)
    outcomes = len(LIVING_DEX_OPTION_OUTCOME_NAMES)
    return LivingDexOptionValueModel(
        coefficients=np.zeros((features, outcomes), dtype=np.float64),
        intercept=np.zeros(outcomes, dtype=np.float64),
        feature_mean=np.zeros(features, dtype=np.float64),
        feature_scale=np.ones(features, dtype=np.float64),
        train_dataset_sha256="a" * 64,
        settled_examples=8,
        censored_examples=0,
        ridge=0.25,
        maximum_importance_weight=4.0,
    )


def _record(model: LivingDexOptionValueModel) -> dict[str, object]:
    return {
        "authority": "non_authoritative_integration_only",
        "claim_manifest_sha256": "b" * 64,
        "claim_record_sha256": "c" * 64,
        "diagnostics": {
            "coefficient_count": 225,
            "finite_coefficient_count": 225,
            "normal_equation_condition_number": 10.0,
        },
        "model": model.to_dict(),
        "model_sha256": model.model_sha256,
        "readiness_result_sha256": "d" * 64,
        "schema": LIVING_DEX_CAUSAL_INTEGRATION_MODEL_RECORD_SCHEMA,
        "source": {
            "exact_ci_attempt": 1,
            "exact_ci_run": 123,
            "source_bundle_sha256": "e" * 64,
            "source_commit": "f" * 40,
        },
        "train_dataset_sha256": model.train_dataset_sha256,
    }


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")


def test_strict_loader_rejoins_nested_model_and_path_free_provenance(
    tmp_path: Path,
) -> None:
    model = _model()
    path = tmp_path / "record.json"
    _write(path, _record(model))

    loaded = load_living_dex_goal_model_record(
        path,
        expected_model_sha256=model.model_sha256,
    )

    assert loaded.model.to_dict() == model.to_dict()
    public = loaded.public_dict()
    assert public["model_sha256"] == model.model_sha256
    assert public["settled_examples"] == 8
    assert str(tmp_path) not in json.dumps(public, sort_keys=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda row: row.update(authority="production"), "authority"),
        (lambda row: row.update(schema="wrong"), "schema"),
        (lambda row: row.update(model_sha256="0" * 64), "identity join"),
        (lambda row: row.update(extra=True), "fields"),
    ),
)
def test_strict_loader_rejects_wrapper_mutations(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    model = _model()
    document = _record(model)
    mutation(document)
    path = tmp_path / "record.json"
    _write(path, document)

    with pytest.raises(LivingDexGoalModelRecordError, match=message):
        load_living_dex_goal_model_record(
            path,
            expected_model_sha256=model.model_sha256,
        )


def test_strict_loader_rejects_wrong_expected_identity(tmp_path: Path) -> None:
    model = _model()
    path = tmp_path / "record.json"
    _write(path, _record(model))

    with pytest.raises(LivingDexGoalModelRecordError, match="identity join"):
        load_living_dex_goal_model_record(path, expected_model_sha256="0" * 64)


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b'{"schema":"first","schema":"second"}', "duplicate"),
        (b'{"condition":NaN}', "non-finite"),
    ),
)
def test_strict_loader_rejects_ambiguous_json(
    tmp_path: Path,
    payload: bytes,
    message: str,
) -> None:
    path = tmp_path / "record.json"
    path.write_bytes(payload)

    with pytest.raises(LivingDexGoalModelRecordError, match=message):
        load_living_dex_goal_model_record(path, expected_model_sha256="0" * 64)
