"""Public stored-record codec compatibility; no ROM, model queries or fitting."""
import ast
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace as N

import numpy as np
import pytest
import run_configured_red_player as driver
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES, LivingDexOptionValueModel, option_feature_names,
    upgrade_option_value_model_for_matchup,
)
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE


def stored_record(tmp_path, version=9):
    width = len(option_feature_names(version))
    targets = len(LIVING_DEX_OPTION_OUTCOME_NAMES)
    model = LivingDexOptionValueModel(
        coefficients=np.arange(width * targets, dtype=np.float64).reshape(width, targets) / 10000,
        intercept=np.arange(targets, dtype=np.float64) / 100,
        feature_mean=np.zeros(width), feature_scale=np.ones(width),
        train_dataset_sha256="a" * 64, settled_examples=2, censored_examples=0,
        ridge=.25, maximum_importance_weight=4., feature_version=version,
    )
    document = dict(schema="pokemon.red.registered-player-model.v1",
        authority="bounded_development_only", objective=REGISTERED_OBJECTIVE,
        model=model.to_dict(), model_sha256=model.model_sha256, source_commit="1" * 40,
        source_bundle_sha256="2" * 64, corpus_sha256="3" * 64,
        prior_model_sha256="4" * 64, retained_example_sha256=["5" * 64, "6" * 64])
    path = tmp_path / "record.json"
    path.write_text(json.dumps(document))
    spec = dict(path=str(path), content_sha256=sha256(path.read_bytes()).hexdigest(),
        reason="Authenticated stored model reused with the existing observation codec.")
    return model, path, dict(partition="development", goal_model_record=spec)


def declaration(model):
    converted = upgrade_option_value_model_for_matchup(model)
    return dict(schema="pokemon.red.goal-model-observation-compatibility.v1",
        mode="v9_to_v15_zero_extension_v1", source_model_sha256=model.model_sha256,
        target_model_sha256=converted.model_sha256, reason="Use the existing zero extension without fitting.")


@pytest.fixture(autouse=True)
def forbid_model_queries_and_fits(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Codec qualification must not query or fit a model")
    for name in ("scores", "predict", "predict_candidate", "predict_economy_candidate", "fit"):
        if hasattr(LivingDexOptionValueModel, name):
            monkeypatch.setattr(LivingDexOptionValueModel, name, forbidden)


def backend_without_legacy_loader():
    return N(d=N(prior=N(models=lambda: pytest.fail("Pinned record must not use legacy model loader"))))


def test_no_optin_preserves_default_loader_and_model_identity(monkeypatch):
    model = N(model_sha256="a" * 64)
    monkeypatch.setattr(driver, "upgrade_option_value_model_for_matchup",
        lambda *_: pytest.fail("Default path must not convert"))
    assert driver.declared_goal_model({}, N(goal_model_sha256=model.model_sha256),
        N(d=N(prior=N(models=lambda: (model, object()))))) is model
    assert "goal_model_observation_compatibility" not in driver.player_wiring_declaration({})


def test_no_optin_preserves_authenticated_stored_V9(tmp_path, monkeypatch):
    model, path, plan = stored_record(tmp_path)
    monkeypatch.setattr(driver, "upgrade_option_value_model_for_matchup",
        lambda *_: pytest.fail("Stored V9 default must not convert"))
    loaded = driver.declared_goal_model(plan, N(goal_model_sha256=model.model_sha256), backend_without_legacy_loader())
    assert loaded.to_dict() == model.to_dict()
    assert loaded.feature_version == 9


def test_explicit_codec_preserves_record_config_parameters_and_evidence(tmp_path):
    from test_red_player_configuration import config
    model, path, plan = stored_record(tmp_path)
    plan["goal_model_observation_compatibility"] = declaration(model)
    cfg = replace(config(), goal_model_sha256=model.model_sha256)
    before_config, before_record, before_model = cfg.to_dict(), path.read_bytes(), model.to_dict()
    loaded = driver.declared_goal_model(plan, cfg, backend_without_legacy_loader())
    width = len(model.feature_mean)
    assert loaded.feature_version == 15
    assert loaded.model_sha256 == plan["goal_model_observation_compatibility"]["target_model_sha256"]
    np.testing.assert_array_equal(loaded.coefficients[:width], model.coefficients)
    np.testing.assert_array_equal(loaded.coefficients[width:], 0.)
    np.testing.assert_array_equal(loaded.feature_mean[:width], model.feature_mean)
    np.testing.assert_array_equal(loaded.feature_mean[width:], 0.)
    np.testing.assert_array_equal(loaded.feature_scale[:width], model.feature_scale)
    np.testing.assert_array_equal(loaded.feature_scale[width:], 1.)
    np.testing.assert_array_equal(loaded.intercept, model.intercept)
    assert (loaded.train_dataset_sha256, loaded.settled_examples, loaded.censored_examples) == (
        model.train_dataset_sha256, model.settled_examples, model.censored_examples)
    assert path.read_bytes() == before_record and model.to_dict() == before_model
    assert cfg.to_dict() == before_config
    assert driver.player_wiring_declaration(plan)["goal_model_observation_compatibility"] == plan["goal_model_observation_compatibility"]


@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("mode", "implicit_upgrade"), ("reason", " "),
    ("source_model_sha256", "G" * 64), ("target_model_sha256", True),
    ("source_model_sha256", "f" * 64), ("target_model_sha256", "e" * 64),
])
def test_invalid_or_wrong_compatibility_rejected(tmp_path, field, value):
    model, path, plan = stored_record(tmp_path)
    plan["goal_model_observation_compatibility"] = dict(declaration(model), **{field: value})
    with pytest.raises(ValueError, match="compatibility"):
        driver.declared_goal_model(plan, N(goal_model_sha256=model.model_sha256), backend_without_legacy_loader())


@pytest.mark.parametrize("fault", ["train", "sealed", "no_record", "extra", "V7"])
def test_conversion_is_explicit_stored_V9_DEVELOPMENT_only(tmp_path, fault):
    model, path, plan = stored_record(tmp_path, 7 if fault == "V7" else 9)
    plan["goal_model_observation_compatibility"] = declaration(model)
    if fault in {"train", "sealed"}: plan["partition"] = fault
    if fault == "no_record": plan.pop("goal_model_record")
    if fault == "extra": plan["goal_model_observation_compatibility"]["manual_goal"] = "forced"
    with pytest.raises(ValueError, match="compatibility"):
        driver.declared_goal_model(plan, N(goal_model_sha256=model.model_sha256), backend_without_legacy_loader())


@pytest.mark.parametrize("fault", ["bytes", "configuration"])
def test_original_record_identity_checked_before_conversion(tmp_path, monkeypatch, fault):
    model, path, plan = stored_record(tmp_path)
    plan["goal_model_observation_compatibility"] = declaration(model)
    if fault == "bytes": path.write_text("{}")
    monkeypatch.setattr(driver, "upgrade_option_value_model_for_matchup",
        lambda *_: pytest.fail("Unauthenticated source cannot reach conversion"))
    cfg = N(goal_model_sha256="b" * 64 if fault == "configuration" else model.model_sha256)
    with pytest.raises(ValueError): driver.declared_goal_model(plan, cfg, backend_without_legacy_loader())


def test_public_run_records_stored_and_effective_identity_and_uses_loaded_feature_version():
    tree = ast.parse(Path(driver.__file__).read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    text = ast.unparse(run)
    assert "model = declared_goal_model(plan, configuration, backend)" in text
    assert "model_feature_version=model.feature_version" in text
    assert "stored_model_sha256=configuration.goal_model_sha256" in text
    assert "effective_model_sha256=model.model_sha256" in text
    assert "goal_model_observation_compatibility" in text
