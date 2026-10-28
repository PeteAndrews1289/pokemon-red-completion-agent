"""ROM-free scoped dispatch; real receipt validators, no native model fit."""

import json
from dataclasses import replace
from types import MappingProxyType
from types import SimpleNamespace as NS

import pytest
from test_red_player_battle_history import publish

from pokemon_red_completion.post_battle_strategy import BattleResult
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
)
from pokemon_red_completion.red_scoped_training_battlers import (
    ScopedTrainingBattlers,
    resolve_story_battler,
    validate_scoped_wild_battler,
)
from pokemon_red_completion.red_story_battle import (
    FrozenStoryBattleController,
    StoryTrainerContract,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

A = StoryTrainerContract("defeat_misty", "misty", 65, (235, 35, 1), 191, 2079)
B = StoryTrainerContract("help_bill", "rival", 3, (225, 25, 8), 152, 595)


def test_native_immutable_cartridge_stats_are_supported_and_changes_rejected(tmp_path):
    p = prototype(tmp_path)
    values = {179: (59, 63, 80, 58, 65)}
    p.public_species_base_stats = MappingProxyType(values)
    pool = ScopedTrainingBattlers(
        p, contracts=(A, B), output=tmp_path / "pool", experiment_sha256="c" * 64,
    )
    assert pool.wild.public_species_base_stats is p.public_species_base_stats
    values[179] = (1, 1, 1, 1, 1)
    with pytest.raises(ValueError, match="identity changed"):
        pool.story(A)
    assert p.session.frame_count == 0


def prototype(tmp_path):
    return FrozenTrainerBattler(
        NS(frame_count=0), None, tmp_path / "unused", "a" * 40, "train-root", "b" * 64, {},
        model_sha256=FROZEN_K_SHA256, qualification_sha256=K_QUALIFICATION_SHA256,
        source_partition=ScenarioPartition.TRAIN,
    )


def setup(tmp_path, monkeypatch):
    p = prototype(tmp_path)
    pool = ScopedTrainingBattlers(
        p, contracts=(A, B), output=tmp_path / "pool", experiment_sha256="c" * 64,
    )

    def play(actor, *args, **kwargs):
        actor.output.mkdir(exist_ok=True)
        publish(actor, wild=kwargs.get("wild_training", False))
        actor.session.frame_count += 10
        return "retained loss"

    monkeypatch.setattr(FrozenTrainerBattler, "_play", play)
    return pool, p


def battle(pool, contract):
    return pool.story(contract).continue_battle(
        None, None, expected_map=contract.map_id, timing=None, decision_guard=lambda _: None,
        story_authority=True,
    )


def test_independent_contracts_keep_same_frozen_model_and_source(tmp_path, monkeypatch):
    pool, p = setup(tmp_path, monkeypatch)
    a, b, wild = pool.story(A), pool.story(B), pool.wild
    assert a is pool.story(A) and a is not b and a is not wild
    assert a.model is b.model is wild.model is p.model
    assert a.session is b.session is wild.session is p.session
    assert a.train_story_contract == A and b.train_story_contract == B
    assert wild.train_story_contract is None
    assert all(actor.source_partition is ScenarioPartition.TRAIN for actor in (a, b, wild))
    assert pool.history() is None and p.calls == 0
    FrozenStoryBattleController(a, (A,))
    with pytest.raises(ValueError, match="differs"):
        FrozenStoryBattleController(a, (B,))
    declaration = json.loads((pool.output / "declaration.json").read_text())
    assert [r["scope"] for r in declaration["actors"]] == ["story", "story", "wild"]
    assert declaration["fit_allowed"] is declaration["authority_promotion"] is False


def test_interleaved_trainers_and_wild_retain_actual_order_and_losses(tmp_path, monkeypatch):
    pool, p = setup(tmp_path, monkeypatch)
    assert battle(pool, A) == "retained loss"
    assert pool.history().result is BattleResult.LOST
    battle(pool, B)
    reader = NS(read=lambda: NS(battle_state=1, map_id=1))
    pool.wild.run_wild_training(
        reader, None, expected_map=1, timing=None, decision_guard=lambda _: None,
    )
    battle(pool, A)
    assert pool.history().result is BattleResult.LOST
    assert len(set(pool.receipts)) == 4 and p.session.frame_count == 40
    rows = [json.loads(path.read_text()) for path in sorted(pool.output.glob("*-end.json"))]
    assert [r["actor"] for r in rows] == [0, 1, 2, 0]
    assert [r["calls_before"] for r in rows] == [0, 0, 0, 1]
    assert [r["before_frame"] for r in rows] == [0, 10, 20, 30]
    assert pool.story(A).train_story_contract == A
    assert pool.story(B).train_story_contract == B and p.calls == 0


def test_unknown_or_altered_contract_fails_without_input(tmp_path, monkeypatch):
    pool, p = setup(tmp_path, monkeypatch)
    for contract in (replace(A, victory_money=1), replace(A, trainer_identity=(235, 35, 2))):
        with pytest.raises(ValueError, match="undeclared"):
            pool.story(contract)
    assert p.session.frame_count == 0 and not tuple(pool.output.glob("battle-*"))


@pytest.mark.parametrize("field,value", [
    ("train_story_contract", B), ("source_partition", ScenarioPartition.DEVELOPMENT),
    ("source_state_sha256", "f" * 64), ("model_sha256", "d" * 64),
    ("qualification_sha256", "e" * 64), ("train_funding_diagnostic", True),
    ("calls", True), ("calls", 1),
])
def test_changed_actor_rejected_before_next_input(tmp_path, monkeypatch, field, value):
    pool, p = setup(tmp_path, monkeypatch)
    setattr(pool.story(A), field, value)
    with pytest.raises(ValueError):
        battle(pool, B)
    assert p.session.frame_count == 0


@pytest.mark.parametrize("file", [
    "declaration.json", "battle-000-start.json", "battle-000-end.json",
    "actor-000/battle-0001/outcome.json",
])
def test_changed_receipt_stops_next_battle(tmp_path, monkeypatch, file):
    pool, p = setup(tmp_path, monkeypatch)
    battle(pool, A)
    pool.history()
    (pool.output / file).write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        battle(pool, B)
    assert p.session.frame_count == 10


def test_execution_error_retains_cost_and_stops_future_dispatch(tmp_path, monkeypatch):
    pool, p = setup(tmp_path, monkeypatch)

    def fail(actor, *args, **kwargs):
        actor.session.frame_count += 7
        raise RuntimeError("incomplete native capture")

    monkeypatch.setattr(FrozenTrainerBattler, "_play", fail)
    with pytest.raises(RuntimeError, match="incomplete"):
        battle(pool, A)
    row = json.loads((pool.output / "battle-000-end.json").read_text())
    assert row["after_frame"] - row["before_frame"] == 7
    assert row["error"]["type"] == "RuntimeError"
    with pytest.raises(ValueError, match="stopped"):
        pool.story(B)
    assert p.session.frame_count == 7 and pool.history() is None


def test_missing_new_capture_never_reuses_stale_loss(tmp_path, monkeypatch):
    pool, _ = setup(tmp_path, monkeypatch)
    battle(pool, A)
    assert pool.history().result is BattleResult.LOST

    def incomplete(actor, *args, **kwargs):
        actor.calls += 1
        actor.session.frame_count += 3

    monkeypatch.setattr(FrozenTrainerBattler, "_play", incomplete)
    battle(pool, B)
    with pytest.raises(ValueError):
        pool.history()
    with pytest.raises(ValueError):
        battle(pool, A)


@pytest.mark.parametrize("change", ["development", "duplicate", "alias", "digest", "nonfresh"])
def test_invalid_declarations_create_no_output(tmp_path, change):
    p = prototype(tmp_path)
    contracts, digest = (A, B), "c" * 64
    if change == "development":
        p.source_partition = ScenarioPartition.DEVELOPMENT
    elif change == "nonfresh":
        p.calls = 1
    elif change == "duplicate":
        contracts = (A, A)
    elif change == "alias":
        contracts = (A, replace(A, victory_money=1))
    else:
        digest = "invalid"
    with pytest.raises(ValueError):
        ScopedTrainingBattlers(p, contracts=contracts, output=tmp_path / "pool",
                              experiment_sha256=digest)
    assert not (tmp_path / "pool").exists()


def test_existing_actor_resolution_is_unchanged(tmp_path):
    p = prototype(tmp_path)
    assert resolve_story_battler(p, A) is p


def test_original_guards_forbid_story_scope_for_wild_and_wild_for_story(tmp_path):
    p = prototype(tmp_path)
    pool = ScopedTrainingBattlers(
        p, contracts=(A, B), output=tmp_path / "pool", experiment_sha256="c" * 64,
    )
    with pytest.raises(ValueError, match="story actor"):
        validate_scoped_wild_battler(pool.story(A))
    with pytest.raises(ValueError, match="declared contract"):
        FrozenStoryBattleController(pool.wild, (A,))
    reader = NS(read=lambda: NS(battle_state=1, map_id=1))
    with pytest.raises(ValueError, match="another battle or mode"):
        pool.story(A).run_wild_training(
            reader, None, expected_map=1, timing=None, decision_guard=lambda _: None,
        )
    assert p.session.frame_count == 0 and pool.failed


def test_no_overlapping_dispatch_and_no_frame_counter_reset(tmp_path, monkeypatch):
    pool, p = setup(tmp_path, monkeypatch)
    original = FrozenTrainerBattler._play

    def reentrant(actor, *args, **kwargs):
        with pytest.raises(ValueError, match="active"):
            battle(pool, B)
        return original(actor, *args, **kwargs)

    monkeypatch.setattr(FrozenTrainerBattler, "_play", reentrant)
    battle(pool, A)
    p.session.frame_count = 0
    with pytest.raises(ValueError, match="backward"):
        battle(pool, B)
    assert len(list(pool.output.glob("*-start.json"))) == 1


def test_story_binding_resolves_exact_actor_and_rechecks_before_travel(tmp_path, monkeypatch):
    from test_red_player_story_battle import setup as story_setup

    from pokemon_red_completion import red_player_story_battle as story

    rt, actions, route, _, _, inputs, _, contract, _ = story_setup(monkeypatch)
    p = replace(prototype(tmp_path), session=rt.emulator)
    pool = ScopedTrainingBattlers(
        p, contracts=(contract, B), output=tmp_path / "pool", experiment_sha256="c" * 64,
    )
    selected = []
    original = story.FrozenStoryBattleController

    def controller(actor, contracts, **kwargs):
        selected.append(actor)
        return original(actor, contracts, **kwargs)

    monkeypatch.setattr(story, "FrozenStoryBattleController", controller)
    binding = story.story_battle_binding(
        rt, actions, contract=contract, route=route, battler=pool,
    )
    assert selected == [pool.story(contract)] and not inputs
    selected[0].source_partition = ScenarioPartition.DEVELOPMENT
    with pytest.raises(ValueError, match="identity"):
        binding.execute()
    assert actions.actions_executed == 0 and not inputs


def test_rival_binding_uses_same_pool_resolution_and_stale_guard(tmp_path, monkeypatch):
    from test_red_player_cerulean_rival import fixture as rival_setup

    from pokemon_red_completion import red_player_cerulean_rival as rival

    rt, actions, _, _, _, inputs, _ = rival_setup(monkeypatch)
    contract = rival.cerulean_rival_contract(None, None)
    p = replace(prototype(tmp_path), session=rt.emulator)
    pool = ScopedTrainingBattlers(
        p, contracts=(A, contract), output=tmp_path / "pool", experiment_sha256="c" * 64,
    )
    route = NS(rom=b"fixture", route_world=NS(plan_feasible_to_map=lambda *a, **k: NS(
        terminal_at=k["goal_at"], cost=25,
    )))
    binding = rival.cerulean_rival_binding(rt, actions, route=route, battler=pool)
    pool.story(contract).source_partition = ScenarioPartition.DEVELOPMENT
    with pytest.raises(ValueError, match="identity"):
        binding.execute()
    assert actions.actions_executed == 0 and not inputs
