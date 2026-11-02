"""ROM-free evaluation isolation and unchanged TRAIN boundaries."""

import copy
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_evolution_consequence import evolving_documents
from test_red_player_story_training_setup import fixture, party_fixture
from test_red_scoped_training_battlers import A, B
from test_red_train_risk_story import actors as train_actors

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.red_challenge_consequence import project_consequence
from pokemon_red_completion.red_player_branch_comparison_setup import (
    prepare_misty_comparison_fixture,
    prepare_misty_party_comparison_fixture,
)
from pokemon_red_completion.red_preparation_evaluation import evaluate_preparation_phases
from pokemon_red_completion.scenario_lab import ScenarioPartition


@pytest.fixture
def actors(tmp_path, monkeypatch):
    return train_actors.__wrapped__(tmp_path, monkeypatch)


def evaluation_actor(actors):
    _, actor = actors
    return replace(actor, source_partition=ScenarioPartition.DEVELOPMENT,
        qualification_sha256=learned.EVALUATION_RISK_ADMISSION_SHA256,
        train_story_contract=None, train_risk_story_scope=None,
        evaluation_story_scope=actor.train_risk_story_scope)


def test_explicit_evaluation_actor_is_not_training_or_funding(actors):
    actor = evaluation_actor(actors)
    actor.require_story_identity()
    actor.require_story_contract(A)
    with pytest.raises(ValueError):
        actor.require_train_story_scope()
    with pytest.raises(ValueError):
        actor.require_funding_scope()
    with pytest.raises(ValueError):
        actor.require_story_contract(B)
    actor.calls = 1
    with pytest.raises(ValueError):
        actor.require_story_contract(A)


def tower_actor(actors, source):
    actor = evaluation_actor(actors)
    contract = replace(A, objective_id="rescue_fuji",
        battle_plan_id="tower-channeler-copy-comparison", map_id=145,
        trainer_identity=(245, 45, 10), defeated_event=250,
        victory_money=690, victory_items=(), victory_badge_bits=0)
    actor.source_state_sha256 = source
    actor.root_lineage_id = "fresh-development-start-20260928-v1"
    actor.evaluation_story_scope = learned.TrainRiskStoryScope(
        "c" * 64, source, actor.root_lineage_id, contract)
    return actor, contract


@pytest.mark.parametrize("source", sorted(learned.TOWER_EVALUATION_SOURCES))
def test_exact_tower_copies_are_single_episode_diagnostics(actors, source):
    actor, contract = tower_actor(actors, source)
    actor.require_story_contract(contract)
    with pytest.raises(ValueError):
        actor.require_train_story_scope()
    with pytest.raises(ValueError):
        actor.require_funding_scope()
    actor.calls = 1
    with pytest.raises(ValueError):
        actor.require_story_contract(contract)
    assert actor.session.frame_count == 0


@pytest.mark.parametrize("change", ["source", "root", "map", "trainer", "event",
    "objective", "plan", "money", "items", "badge", "train", "test"])
def test_tower_copy_admission_cannot_expand(actors, change):
    actor, contract = tower_actor(actors, sorted(learned.TOWER_EVALUATION_SOURCES)[0])
    if change == "source":
        actor.source_state_sha256 = "d" * 64
    elif change == "root":
        actor.root_lineage_id = "other"
    elif change in ("train", "test"):
        actor.source_partition = ScenarioPartition(change)
    else:
        key, value = {"map": ("map_id", 146), "trainer": ("trainer_identity", (245, 45, 11)),
            "event": ("defeated_event", 251), "objective": ("objective_id", "other"),
            "plan": ("battle_plan_id", "other"), "money": ("victory_money", 691),
            "items": ("victory_items", ((1, 1),)),
            "badge": ("victory_badge_bits", 1)}[change]
        contract = replace(contract, **{key: value})
    actor.evaluation_story_scope = learned.TrainRiskStoryScope(
        "c" * 64, actor.source_state_sha256, actor.root_lineage_id, contract)
    with pytest.raises(ValueError):
        actor.require_story_contract(contract)
    assert actor.calls == 0 and actor.session.frame_count == 0


@pytest.mark.parametrize("name,value", [
    ("source_partition", ScenarioPartition.TRAIN),
    ("source_state_sha256", "f" * 64), ("root_lineage_id", "other"),
    ("train_story_contract", A), ("evaluation_story_scope", None),
    ("qualification_sha256", learned.TRAIN_RISK_ADMISSION_SHA256),
    ("model", None), ("train_funding_diagnostic", True),
])
def test_evaluation_scope_fails_before_input(actors, name, value):
    actor = evaluation_actor(actors)
    setattr(actor, name, value)
    with pytest.raises(ValueError):
        actor.require_story_identity()
    assert actor.calls == 0


@pytest.mark.parametrize("name,value", [
    ("resume", False), ("require_win", True), ("wild_training", True),
    ("train_funding_diagnostic", True), ("expected_map", 1),
    ("authority", learned.TRAIN_RISK_AUTHORITY), ("allow_immune_switch_recovery", True),
])
def test_evaluation_cannot_execute_another_mode(actors, name, value):
    actor = evaluation_actor(actors)
    reader = NS(read=lambda: NS(map_id=A.map_id, battle_state=2),
                read_active_trainer_identity=lambda: A.trainer_identity)
    kwargs = dict(expected_map=A.map_id, timing=None, label="evaluation",
        decision_guard=lambda _: None, resume=True, require_win=False,
        authority=learned.EVALUATION_RISK_AUTHORITY)
    kwargs[name] = value
    with pytest.raises(ValueError):
        actor._play(reader, None, **kwargs)
    assert actor.calls == 0 and actor.session.frame_count == 0


@pytest.mark.parametrize("party", [False, True])
@pytest.mark.parametrize("partition", ["development", "train", "test"])
def test_setup_partition_is_explicit_and_atomic(monkeypatch, party, partition):
    memory, args = (party_fixture if party else fixture)(monkeypatch)[:2]
    args.pop("isolated_training_setup")
    args["isolated_comparison_setup"] = True
    args["partition"] = partition
    if party:
        args.pop("condition", None)
        args["hp_percent"] = 50
        fn = prepare_misty_party_comparison_fixture
    else:
        args.pop("level")
        args.pop("hp_percent")
        fn = prepare_misty_comparison_fixture
    before = bytes(memory)
    if partition == "development":
        assert fn(memory, **args)
    else:
        with pytest.raises(ValueError):
            fn(memory, **args)
        assert bytes(memory) == before


def test_evaluation_outcome_never_enters_train_projector(tmp_path, monkeypatch):
    plan, phases = evolving_documents(tmp_path, monkeypatch)
    plan["source"]["partition"] = plan["partition"] = "development"
    result = evaluate_preparation_phases(plan["source"], plan["before"], phases,
        target=plan["spec"]["challenge_target"],
        evolution_contract=plan["spec"]["evolution_contract"])
    assert result["attempted"] and not result["completed"] and not result["fit_allowed"]
    with pytest.raises(ValueError, match="TRAIN"):
        project_consequence(plan, phases)
    broken = copy.deepcopy(phases)
    broken[-1]["after"]["endpoint"]["events"] = [True]
    with pytest.raises(ValueError, match="endpoint"):
        evaluate_preparation_phases(plan["source"], plan["before"], broken,
            target=plan["spec"]["challenge_target"],
            evolution_contract=plan["spec"]["evolution_contract"])


def test_native_development_snapshot_does_not_construct_train_recorder(tmp_path, monkeypatch):
    from test_native_challenge_consequence import harness, session

    from pokemon_red_completion.red_challenge_consequence import (
        NativeConsequenceRecorder,
        capture_consequence_snapshot,
    )

    args, _ = harness(tmp_path, monkeypatch)
    spec = args.pop("consequence_spec")
    args["source"] = dict(args["source"], partition="development")
    native = session(args)
    snapshot = capture_consequence_snapshot(native, spec.challenge_target)
    assert snapshot["actions"] == snapshot["frames"] == 0
    assert native.consequence is None
    with pytest.raises(ValueError, match="TRAIN"):
        NativeConsequenceRecorder(native, spec)
