"""CLI orchestration only; real episode admission is tested separately."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_forward_goal_learning import examples
from test_goal_resource_quote import _supply_model
from test_red_player_training import _plan

from pokemon_red_completion.provenance import SourceIdentity
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fit_red_forward_goal.py"


def harness(monkeypatch, *, dirty=False, digest_mismatch=False, missing_forward=False):
    module = runpy.run_path(str(SCRIPT))
    namespace = module["main"].__globals__
    model = _supply_model()
    rows = examples()
    published, loaded, model_reads = [], [], []

    def open_episode(episode_id):
        plan = RedPlayerTrainingPlan({**_plan(model).document, "episode_id": episode_id})
        metadata = {"player_training_plan": dict(plan.document)}
        if not missing_forward:
            metadata.update(
                forward_goal_plan=rows[0].plan.public_dict(),
                forward_story_objective="defeat_champion",
            )
        return SimpleNamespace(
            manifest_sha256="b" * 64 if digest_mismatch else "a" * 64,
            read_header=lambda: {"metadata": metadata},
        )

    def publish(record_id, *, kind, record):
        published.append((record_id, kind, record))
        return SimpleNamespace(summary=SimpleNamespace(record_sha256="e" * 64))

    store = SimpleNamespace(open_episode=open_episode, publish_sealed_record=publish)

    def admit(actual_store, **kwargs):
        assert actual_store is store
        assert kwargs["behavior_model"] is model
        loaded.append(kwargs)
        return rows[int(kwargs["episode_id"].rsplit("-", 1)[-1]) - 1]

    def read_model(path, *, expected_model_sha256):
        model_reads.append((path, expected_model_sha256))
        return SimpleNamespace(model=model)

    monkeypatch.setitem(
        namespace,
        "detect_source_identity",
        lambda *a, **k: SourceIdentity(
            "1" * 40,
            dirty,
        ),
    )
    monkeypatch.setitem(namespace, "working_source_bundle_sha256", lambda *_: "2" * 64)
    monkeypatch.setitem(namespace, "open_private_root", lambda *a, **k: store)
    monkeypatch.setitem(namespace, "load_player_goal_model_record", read_model)
    monkeypatch.setitem(namespace, "load_red_forward_episode", admit)
    args = [
        "--private-artifact-root",
        "/unused/private",
        "--behavior-model-record",
        "/unused/model",
        "--expected-behavior-model-sha256",
        model.model_sha256,
        "--episode",
        "goal-episode-1:" + "a" * 64,
        "--episode",
        "goal-episode-2:" + "a" * 64,
    ]
    return module["main"], args, published, loaded, model_reads


def test_cli_fits_admitted_rows_and_publishes_only_separate_shadow_record(monkeypatch, capsys):
    main, args, published, loaded, model_reads = harness(monkeypatch)
    assert main(args) == 0
    assert len(loaded) == 2 and len(model_reads) == len(published) == 1
    identity, kind, document = published[0]
    assert identity.startswith("red-forward-fit-") and kind == "red_forward_goal_shadow_fit"
    assert document["authority"] == document["model"]["authority"] == "unqualified-shadow"
    assert document["player_model_changed"] is False
    assert document["independent_evaluation"] is False
    assert len(document["outcomes"]) == 2 and document["model"]["settled_examples"] == 2
    assert document["training_mse_after"][1] < document["training_mse_before"][1]
    assert json.loads(capsys.readouterr().out)["record_sha256"] == "e" * 64


@pytest.mark.parametrize("fault", ["dirty", "digest", "missing", "duplicate", "few", "ridge"])
def test_cli_refuses_bad_inputs_without_publishing_or_modifying_actor(monkeypatch, fault):
    main, args, published, _, _ = harness(
        monkeypatch,
        dirty=fault == "dirty",
        digest_mismatch=fault == "digest",
        missing_forward=fault == "missing",
    )
    if fault == "duplicate":
        args[-1] = args[-3]
    elif fault == "few":
        args = args[:-2]
    elif fault == "ridge":
        args.extend(["--ridge", "-1"])
    with pytest.raises((RuntimeError, ValueError, KeyError)):
        main(args)
    assert published == []


def test_cli_help_needs_no_model_private_data_or_emulator():
    main = runpy.run_path(str(SCRIPT))["main"]
    with pytest.raises(SystemExit) as stopped:
        main(["--help"])
    assert stopped.value.code == 0
