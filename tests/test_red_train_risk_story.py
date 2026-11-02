"""TRAIN-only existing actor integration; synthetic model fixtures, no ROM."""

import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_player_battle_history import publish
from test_red_scoped_training_battlers import A, B, prototype
from test_red_trainer_practice_fit import _target

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.post_battle_strategy import BattleResult
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_scoped_training_battlers import (
    ScopedTrainingBattlers,
    validate_scoped_wild_battler,
)
from pokemon_red_completion.red_story_battle import FrozenStoryBattleController
from pokemon_red_completion.red_trainer_practice_fit import fit_trainer_practice_three_heads
from pokemon_red_completion.scenario_lab import ScenarioPartition


@pytest.fixture
def actors(tmp_path, monkeypatch):
    p = prototype(tmp_path)
    model = fit_trainer_practice_three_heads(
        [_target()], seed=1, epochs=1, require_corpus_floor=False)
    monkeypatch.setattr(learned, "AGATHA_STORY_MODEL_SHA256",
                        learned.canonical_sha256(model.to_dict()))
    risk = replace(p, model=model, model_sha256=learned.AGATHA_STORY_SHA256,
        qualification_sha256=learned.TRAIN_RISK_ADMISSION_SHA256,
        train_story_contract=A, train_risk_story_scope=learned.TrainRiskStoryScope(
            "c" * 64, p.source_state_sha256, p.root_lineage_id, A))
    return p, risk


def pool_for(tmp_path, actors):
    p, risk = actors
    return ScopedTrainingBattlers(p, contracts=(A, B), output=tmp_path / "pool",
        experiment_sha256="c" * 64, story_overrides=(risk,))


@pytest.mark.parametrize("field,value", [
    ("source_partition", ScenarioPartition.DEVELOPMENT),
    ("source_partition", ScenarioPartition.TEST),
    ("model_sha256", learned.FROZEN_K_SHA256), ("model", None),
    ("qualification_sha256", learned.AGATHA_STORY_ADMISSION_SHA256),
    ("source_state_sha256", "f" * 64), ("root_lineage_id", "another"),
    ("train_story_contract", B), ("train_risk_story_scope", None),
    ("train_funding_diagnostic", True), ("story_chain_scope", object()),
])
def test_wrong_actor_scope_refused_before_input(tmp_path, actors, field, value):
    p, risk = actors
    setattr(risk, field, value)
    with pytest.raises(ValueError):
        FrozenStoryBattleController(risk, (A,))
    assert p.session.frame_count == 0 and risk.calls == 0
    assert not list(tmp_path.iterdir())


def test_checkpoint_bytes_must_match_before_parse():
    with pytest.raises(ValueError, match="bytes differ"):
        learned.load_train_risk_story_model(b"{}")


@pytest.mark.parametrize("field,value", [
    ("resume", False), ("require_win", True), ("wild_training", True),
    ("train_funding_diagnostic", True), ("allow_immune_switch_recovery", True),
    ("authority", "frozen-risk-cost-agatha-development"), ("expected_map", 1),
])
def test_other_runtime_modes_refused_before_input(tmp_path, actors, field, value):
    _, risk = actors
    reader = NS(read=lambda: NS(map_id=A.map_id, battle_state=2),
                read_active_trainer_identity=lambda: A.trainer_identity)
    kwargs = dict(expected_map=A.map_id, timing=None, label="scope-test",
        decision_guard=lambda _: None, resume=True, require_win=False,
        authority=learned.TRAIN_RISK_AUTHORITY)
    kwargs[field] = value
    with pytest.raises(ValueError):
        risk._play(reader, None, **kwargs)
    assert risk.calls == 0 and risk.session.frame_count == 0
    assert not list(tmp_path.iterdir())


def test_changed_model_object_refused_before_input(actors, monkeypatch):
    _, risk = actors
    monkeypatch.setattr(learned, "AGATHA_STORY_MODEL_SHA256", "f" * 64)
    with pytest.raises(ValueError, match="model or declared scope"):
        risk.require_story_identity()
    assert risk.calls == 0


@pytest.mark.parametrize("change", ["digest", "root", "contract"])
def test_invalid_declaration_rejected(change):
    args = ["c" * 64, "b" * 64, "root", A]
    args[{"digest": 0, "root": 2, "contract": 3}[change]] = None
    with pytest.raises(ValueError):
        learned.TrainRiskStoryScope(*args)


def test_override_only_selects_declared_story_actor(tmp_path, actors):
    pool = pool_for(tmp_path, actors)
    assert pool.story(A).model_sha256 == learned.AGATHA_STORY_SHA256
    assert pool.story(B).model_sha256 == pool.wild.model_sha256 == learned.FROZEN_K_SHA256
    assert pool.wild.train_risk_story_scope is None
    assert pool.story(A).session is pool.wild.session
    FrozenStoryBattleController(pool.story(A), (A,))
    with pytest.raises(ValueError):
        FrozenStoryBattleController(pool.story(A), (B,))
    with pytest.raises(ValueError):
        validate_scoped_wild_battler(pool.story(A))
    with pytest.raises(ValueError):
        pool.story(A).require_funding_scope()
    with pytest.raises(ValueError):
        pool.story(A).run_wild_training(None, None, expected_map=1,
            timing=None, decision_guard=lambda _: None)
    d = json.loads((pool.output / "declaration.json").read_text())
    assert [a["model_sha256"] for a in d["actors"]] == [
        learned.AGATHA_STORY_SHA256, learned.FROZEN_K_SHA256, learned.FROZEN_K_SHA256]
    assert actors[0].session.frame_count == 0


@pytest.mark.parametrize("change", ["session", "source", "experiment", "duplicate", "undeclared"])
def test_bad_override_rejected_before_output(tmp_path, actors, change):
    p, risk = actors
    overrides = (risk,)
    if change == "session":
        risk.session = NS(frame_count=0)
    elif change == "source":
        risk.source_state_sha256 = "d" * 64
    elif change == "experiment":
        risk.train_risk_story_scope = replace(risk.train_risk_story_scope,
                                              experiment_sha256="d" * 64)
    elif change == "duplicate":
        overrides = (risk, risk)
    else:
        risk.train_story_contract = replace(A, victory_money=1)
        risk.train_risk_story_scope = replace(risk.train_risk_story_scope,
                                              contract=risk.train_story_contract)
    with pytest.raises(ValueError):
        ScopedTrainingBattlers(p, contracts=(A, B), output=tmp_path / "pool",
            experiment_sha256="c" * 64, story_overrides=overrides)
    assert not list(tmp_path.iterdir()) and p.session.frame_count == 0


def test_mixed_history_preserves_actor_identity_order_and_losses(tmp_path, actors, monkeypatch):
    pool = pool_for(tmp_path, actors)

    def play(actor, *args, **kwargs):
        actor.output.mkdir(exist_ok=True)
        publish(actor, wild=kwargs.get("wild_training", False))
        actor.session.frame_count += 10

    monkeypatch.setattr(learned.FrozenTrainerBattler, "_play", play)
    pool.wild.run_wild_training(NS(read=lambda: NS(battle_state=1, map_id=1)), None,
        expected_map=1, timing=None, decision_guard=lambda _: None)
    pool.story(A).continue_battle(None, None, expected_map=A.map_id, timing=None,
                                  decision_guard=lambda _: None, story_authority=True)
    assert pool.history().result is BattleResult.LOST
    assert len(pool.receipts) == 2
    rows = [json.loads(p.read_text()) for p in sorted(pool.output.glob("*-end.json"))]
    assert [r["actor"] for r in rows] == [2, 0]
    assert [r["after_frame"] for r in rows] == [10, 20]
    endpoints = [json.loads((pool.output / f"actor-{i:03d}/battle-0001/endpoint.json").read_text())
                 for i in (2, 0)]
    assert [e["model_sha256"] for e in endpoints] == [learned.FROZEN_K_SHA256,
                                                       learned.AGATHA_STORY_SHA256]


@pytest.mark.parametrize("omit", [False, True])
def test_history_requires_risk_action_scope(tmp_path, actors, omit):
    _, risk = actors
    risk.output.mkdir()
    history = NativeBattlerHistory(risk)
    publish(risk, omit_scope=omit)
    if omit:
        with pytest.raises(ValueError):
            history()
    else:
        assert history().result is BattleResult.LOST


def test_mutating_bound_scope_stops_all_dispatch(tmp_path, actors):
    pool = pool_for(tmp_path, actors)
    actor = pool.story(A)
    actor.train_risk_story_scope = replace(actor.train_risk_story_scope,
                                          experiment_sha256="d" * 64)
    with pytest.raises(ValueError):
        _ = pool.wild
    assert actors[0].session.frame_count == 0
