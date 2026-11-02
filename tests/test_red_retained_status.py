from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_retained_status import enrich_retained_status
from pokemon_red_completion.scenario_lab import ScenarioPartition


def fixture():
    legacy = {"features": {"battle": {"opponent_level": 42}}, "policy_visible": True}
    observed = deepcopy(legacy)
    observed["features"]["battle"]["status_context"] = {
        "schema": "pokemon.core.battle.status-context.v1",
        "player_confused": True,
        "opponent_confused": False,
        "player_stages": [-1, 0, 1, 2, 0, 0],
        "opponent_stages": [0] * 6,
    }
    target = {
        "schema": "pokemon.red.trainer-practice-three-head-targets.v1",
        "partition": "train",
        "capture_id": "train-one",
        "root_lineage_id": "train-root",
        "observation_schema": OBSERVATION_SCHEMA_V2,
        "manifest_sha256": "a" * 64,
        "observation": legacy,
        "heads": {"switch": {"returns": [-2, 3]}},
    }
    capture = NS(
        manifest_sha256="a" * 64,
        manifest=NS(
            partition=ScenarioPartition.TRAIN,
            capture_id="train-one",
            root_lineage_id="train-root",
            observation_schema=OBSERVATION_SCHEMA_V2,
            state_sha256="b" * 64,
            initial_observation_sha256=canonical_sha256(legacy),
        ),
    )
    return target, capture, legacy, observed


def test_only_new_native_context_changes_and_inputs_stay_immutable():
    target, capture, legacy, observed = fixture()
    before = deepcopy((target, legacy, observed))
    result, receipt = enrich_retained_status(target, capture, legacy, observed)
    assert (target, legacy, observed) == before
    stripped = deepcopy(result)
    del stripped["observation"]["features"]["battle"]["status_context"]
    assert stripped == target
    assert result["heads"] == target["heads"] and result["heads"] is not target["heads"]
    assert receipt["parent_target_sha256"] == canonical_sha256(target)
    assert receipt["new_training_outcomes"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("partition", "development"),
        ("capture_id", "different"),
        ("root_lineage_id", "different"),
        ("manifest_sha256", "c" * 64),
        ("observation_schema", "older"),
        ("schema", "other"),
    ],
)
def test_rejects_target_identity_drift(field, value):
    target, capture, legacy, observed = fixture()
    target[field] = value
    with pytest.raises(ValueError, match="binding"):
        enrich_retained_status(target, capture, legacy, observed)


@pytest.mark.parametrize("fault", ["partition", "digest", "legacy", "enriched", "existing"])
def test_rejects_native_or_observation_drift(fault):
    target, capture, legacy, observed = fixture()
    if fault == "partition":
        capture.manifest.partition = ScenarioPartition.DEVELOPMENT
    elif fault == "digest":
        capture.manifest.initial_observation_sha256 = "0" * 64
    elif fault == "legacy":
        target["observation"] = {"different": True}
    elif fault == "enriched":
        observed["policy_visible"] = False
    else:
        legacy["features"]["battle"]["status_context"] = {}
        capture.manifest.initial_observation_sha256 = canonical_sha256(legacy)
    with pytest.raises(ValueError):
        enrich_retained_status(target, capture, legacy, observed)


@pytest.mark.parametrize("fault", ["missing", "schema", "bool", "count", "range", "stage_bool"])
def test_refuses_missing_or_malformed_native_status(fault):
    target, capture, legacy, observed = fixture()
    ctx = observed["features"]["battle"]["status_context"]
    if fault == "missing":
        del observed["features"]["battle"]["status_context"]
    elif fault == "schema":
        ctx["schema"] = "unknown"
    elif fault == "bool":
        ctx["player_confused"] = 1
    elif fault == "count":
        ctx["player_stages"] = [0] * 5
    elif fault == "range":
        ctx["player_stages"][0] = 7
    else:
        ctx["player_stages"][0] = True
    with pytest.raises(ValueError, match="context"):
        enrich_retained_status(target, capture, legacy, observed)
