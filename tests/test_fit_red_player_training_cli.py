import hashlib
import json
import sys
from types import SimpleNamespace

import fit_red_player_training as driver
import pytest
from test_goal_resource_quote import _supply_model

from pokemon_red_completion.provenance import EvaluationIdentityError, SourceIdentity
from pokemon_red_completion.red_player_model import RedPlayerModelRecord
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE


def document(**changes):
    return {
        "schema": "pokemon.red.regional-goal-step-result.v1",
        "objective": REGISTERED_OBJECTIVE,
        "independent_evaluation": False,
        "episode_id": "prospective-train-1",
        **changes,
    }


def declaration(tmp_path, value, name="result.json"):
    path = tmp_path / name
    payload = json.dumps(value).encode()
    path.write_bytes(payload)
    return f"{path}:{hashlib.sha256(payload).hexdigest()}"


def setup_cli(monkeypatch, declarations):
    events = []
    prior = RedPlayerModelRecord(
        _supply_model(), "a" * 64, "b" * 40, "c" * 64,
        "d" * 64, "e" * 64, (), REGISTERED_OBJECTIVE,
    )
    args = ["fit", "--private-artifact-root", "unused",
            "--prior-model-record", "unused",
            "--expected-prior-model-sha256", prior.model.model_sha256]
    for item in declarations:
        args += ["--registered-result", item]
    monkeypatch.setattr("sys.argv", args)
    monkeypatch.setattr(driver, "detect_source_identity",
                        lambda *a, **kw: SourceIdentity("b" * 40, False))
    monkeypatch.setattr(driver, "require_published_source",
                        lambda *a: pytest.fail("local registered fitting required publication"))
    store = SimpleNamespace(find_sealed_record=lambda *a, **kw: None)
    monkeypatch.setattr(driver, "open_private_root", lambda *a, **kw: store)
    monkeypatch.setattr(driver, "load_player_goal_model_record", lambda *a, **kw: prior)
    monkeypatch.setattr(driver, "working_source_bundle_sha256", lambda *a: "c" * 64)

    def fit(actual, **kwargs):
        assert actual is store
        assert kwargs["prior"] is prior
        assert kwargs["source_commit"] == "b" * 40
        assert kwargs["source_bundle_sha256"] == "c" * 64
        assert kwargs["resolve"](prior.model.model_sha256) is prior
        with pytest.raises(ValueError, match="missing"):
            kwargs["resolve"]("f" * 64)
        events.append(kwargs["results"])
        return {"test_only": True}

    monkeypatch.setattr(driver, "fit_incremental_registered_results", fit)
    monkeypatch.setattr(driver, "fit_red_player_update",
                        lambda *a, **kw: pytest.fail("legacy fitter used"))
    return events


def test_registered_cli_uses_incremental_history(tmp_path, monkeypatch):
    rows = (document(), document(episode_id="prospective-train-2",
                                schema="pokemon.red.regional-acquisition-result.v1"))
    declarations = [declaration(tmp_path, row, f"{i}.json") for i, row in enumerate(rows)]
    events = setup_cli(monkeypatch, declarations)
    assert driver.main() == 0
    assert events == [rows]


@pytest.mark.parametrize("changes", [
    {"schema": "pokemon.red.development-measured-choice-result.v1"},
    {"schema": "unknown"},
    {"independent_evaluation": True},
    {"independent_evaluation": 0},
    {"objective": None},
    {"episode_id": ""},
    {"episode_id": 4},
])
def test_rejects_ineligible_result_before_fit(tmp_path, monkeypatch, changes):
    events = setup_cli(monkeypatch, [declaration(tmp_path, document(**changes))])
    with pytest.raises(ValueError, match="native TRAIN"):
        driver.main()
    assert not events


def test_invalid_second_result_cannot_fit_partial_batch(tmp_path, monkeypatch):
    one = declaration(tmp_path, document())
    two = declaration(tmp_path, document(episode_id="second"), "second.json")
    events = setup_cli(monkeypatch, [one, two[:-64] + "0" * 64])
    with pytest.raises(ValueError, match="digest differs"):
        driver.main()
    assert not events


def test_rejects_duplicate_episode_even_in_different_files(tmp_path):
    one = declaration(tmp_path, document())
    two = declaration(tmp_path, document(), "second.json")
    with pytest.raises(ValueError, match="duplicated"):
        driver._registered_results([one, two])


def test_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "duplicate.json"
    payload = b'{"schema":"one","schema":"two"}'
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="duplicate registered"):
        driver._registered_results([f"{path}:{hashlib.sha256(payload).hexdigest()}"])


def test_dirty_source_rejected_before_private_store_open(tmp_path, monkeypatch):
    events = setup_cli(monkeypatch, [declaration(tmp_path, document())])
    monkeypatch.setattr(driver, "detect_source_identity",
                        lambda *a, **kw: SourceIdentity("b" * 40, True))
    monkeypatch.setattr(driver, "open_private_root",
                        lambda *a, **kw: pytest.fail("dirty source opened data"))
    with pytest.raises(EvaluationIdentityError, match="clean"):
        driver.main()
    assert not events


def test_legacy_mode_still_requires_publication(monkeypatch):
    monkeypatch.setattr("sys.argv", ["fit", "--private-artifact-root", "unused",
                        "--prior-model-record", "unused",
                        "--expected-prior-model-sha256", "a" * 64, "--episode", "id:" + "b" * 64])
    monkeypatch.setattr(driver, "detect_source_identity",
                        lambda *a, **kw: SourceIdentity("b" * 40, False))

    def stop(*args):
        raise EvaluationIdentityError("legacy publication checked")

    monkeypatch.setattr(driver, "require_published_source", stop)
    monkeypatch.setattr(driver, "open_private_root",
                        lambda *a, **kw: pytest.fail("legacy publication bypassed"))
    with pytest.raises(EvaluationIdentityError, match="legacy publication checked"):
        driver.main()


def test_modes_cannot_be_mixed(tmp_path, monkeypatch):
    setup_cli(monkeypatch, [declaration(tmp_path, document())])
    monkeypatch.setattr(sys, "argv", [*sys.argv, "--episode", "id:" + "b" * 64])
    with pytest.raises(SystemExit) as error:
        driver.main()
    assert error.value.code == 2


@pytest.mark.parametrize("prefix", ["rpr-model", "rp-model"])
def test_behavior_resolver_accepts_both_authenticated_history_formats(monkeypatch, prefix):
    expected = "a" * 64
    prior = SimpleNamespace(model=SimpleNamespace(model_sha256="b" * 64))
    calls = []
    record = SimpleNamespace(read_bytes=lambda: b"historical authenticated payload")

    def find(name, *, expected_kind):
        calls.append(name)
        assert expected_kind == "red_player_model"
        return record if name == f"{prefix}-{expected}" else None

    loaded = object()

    def load(payload, *, expected_model_sha256):
        assert payload == b"historical authenticated payload"
        assert expected_model_sha256 == expected
        return loaded

    monkeypatch.setattr(driver, "load_player_goal_model_record_bytes", load)
    resolve = driver._behavior_resolver(SimpleNamespace(find_sealed_record=find), prior)
    assert resolve(expected) is loaded
    assert calls[-1] == f"{prefix}-{expected}"


def test_registered_mode_rejects_legacy_prior(tmp_path, monkeypatch):
    events = setup_cli(monkeypatch, [declaration(tmp_path, document())])
    monkeypatch.setattr(driver, "load_player_goal_model_record",
                        lambda *a, **kw: SimpleNamespace(objective=None))
    with pytest.raises(ValueError, match="registered prior"):
        driver.main()
    assert not events
