"""Explicit policy/task wiring, unchanged defaults, and pre-input refusals."""
import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS
import pytest
import run_configured_red_player as driver
from test_player_sequence_policy import setup as policy_setup
from test_red_native_player import setup
from pokemon_red_completion.red_native_player import run_native_continuous_player
from pokemon_red_completion.player_sequence_targets import TASK_TERMINAL_TARGET_CONTRACT as TASK


def policy_plan(tmp_path):
    model, _, policy, _, _ = policy_setup()
    policy = replace(policy, head=replace(policy.head, horizon=2, target_contract=TASK))
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy.document()))
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(dict(schema="pokemon.red.pure-parent-prospective-state-catalog.v1", task_sha256="a"*64)))
    plan = dict(partition="development", goal_selection=dict(mode="exploration", reason="comparison"),
                sequence_policy=dict(path=str(path), content_sha256=sha256(path.read_bytes()).hexdigest(),
                    policy_sha256=policy.model_sha256, target_contract=TASK, task_sha256="a"*64,
                    task_catalog=dict(path=str(catalog), content_sha256=sha256(catalog.read_bytes()).hexdigest()),
                    window_stride=1, reason="frozen inference; no task terminal annotation"))
    return model, policy, plan


def test_explicit_task_head_reaches_real_native_collector(tmp_path, monkeypatch):
    model, policy, plan = policy_plan(tmp_path)
    kw, executed = setup(tmp_path, monkeypatch)
    kw.update(model=model, limits=replace(kw["limits"], decisions=3, actions=3),
              **driver.declared_sequence_options(plan, model))
    result = run_native_continuous_player(**kw)
    assert executed and result["model_sha256"] == policy.model_sha256
    d = json.loads((kw["output"] / "episode/sequence/declaration.json").read_text())
    assert d["target_contract"] == TASK and d["task_sha256"] == "a"*64 and d["window_stride"] == 1
    terminal = json.loads((kw["output"] / "episode/sequence/result.json").read_text())
    assert terminal.get("task_terminal") is None
    assert not d["training_eligible"]


@pytest.mark.parametrize("fault", ["raw", "policy", "task", "contract", "stride", "greedy", "mix", "model", "partition", "wrong_task", "catalog_content", "catalog_schema"])
def test_bad_declarations_never_reach_native_input(tmp_path, monkeypatch, fault):
    model, policy, plan = policy_plan(tmp_path)
    kw, executed = setup(tmp_path, monkeypatch)
    spec = plan["sequence_policy"]
    if fault == "raw": spec["content_sha256"] = "b"*64
    elif fault == "policy": spec["policy_sha256"] = "b"*64
    elif fault == "task": spec["task_sha256"] = "invalid"
    elif fault == "contract": spec["target_contract"] = "fixed-horizon"
    elif fault == "stride": spec["window_stride"] = True
    elif fault == "greedy": plan["goal_selection"]["mode"] = "greedy"
    elif fault == "mix": plan["goal_selection"]["exploration_mix"] = .5
    elif fault == "model": model = NS(model_sha256="b"*64, feature_version=model.feature_version)
    elif fault == "partition": plan["partition"] = "train"
    elif fault == "wrong_task": spec["task_sha256"] = "0"*64
    elif fault == "catalog_content": spec["task_catalog"]["content_sha256"] = "0"*64
    elif fault == "catalog_schema":
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps(dict(schema="wrong", task_sha256="a"*64)))
        spec["task_catalog"]["content_sha256"] = sha256(path.read_bytes()).hexdigest()
    with pytest.raises((ValueError, TypeError)):
        options = driver.declared_sequence_options(plan, model)
        run_native_continuous_player(**dict(kw, model=model, **options))
    assert executed == []


@pytest.mark.parametrize("fault", ["no_horizon", "wrong_contract", "no_task"])
def test_native_contract_refused_before_claim_or_input(tmp_path, monkeypatch, fault):
    model, policy, plan = policy_plan(tmp_path)
    kw, executed = setup(tmp_path, monkeypatch)
    options = driver.declared_sequence_options(plan, model)
    if fault == "no_horizon": options["sequence_horizon"] = None
    elif fault == "wrong_contract": options["sequence_target_contract"] = "bad"
    else: options["sequence_task_sha256"] = None
    with pytest.raises(ValueError):
        run_native_continuous_player(**dict(kw, model=model, **options))
    assert executed == []


def test_legacy_defaults_and_continuation_recipe_guard():
    assert driver.declared_sequence_options({}) == {}
    assert driver.declared_resource_safety({}) is False
    driver.validate_continued_sequence_wiring({}, {})
    with pytest.raises(ValueError, match="continuation"):
        driver.validate_continued_sequence_wiring(dict(sequence_policy={"new": True}), {})
    with pytest.raises(ValueError, match="continuation"):
        driver.validate_continued_sequence_wiring(dict(force_resource_safety=True), {})


@pytest.mark.parametrize("mode", ["inspect", "loan_copy_source", "evolution_copy", "boxed_machine_copy", "prepared_evolution_copy"])
def test_unsupported_selector_modes_fail_before_backend(mode):
    with pytest.raises(ValueError, match="ordinary shared"):
        driver.validate_sequence_runner_mode(dict(sequence_policy={}), NS(**{mode: True}))
