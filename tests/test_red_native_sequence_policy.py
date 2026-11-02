"""Guarded runner integration on a fake cartridge, never an evaluation claim."""

import json
from dataclasses import replace

import pytest
from test_player_sequence_policy import setup as policy_setup
from test_red_native_player import setup
from test_red_sequence_state_audit import reader

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.player_sequence_reconstruction import reconstruct_sequence_candidates
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_player import run_native_continuous_player
from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace
from pokemon_red_completion.red_sequence_verified_targets import verify_sequence_target_channels


def read(path):
    return json.loads(path.read_text())


def run(tmp_path, monkeypatch, *, support=None):
    args, executed = setup(tmp_path, monkeypatch, support=support)
    model, _, policy, _, _ = policy_setup()
    policy = replace(policy, head=replace(policy.head, horizon=2))
    args.update(
        model=model,
        sequence_policy=policy,
        sequence_horizon=2,
        limits=replace(args["limits"], decisions=6, actions=6),
    )

    def enumerate_bindings(runtime, actions, observation):
        original = runtime.enumerator(actions).enumerate(observation)
        return GoalBindingSet(
            original.opportunities,
            tuple(
                replace(b, story_objective_ref="private-story")
                if b.kind is GoalKind.ADVANCE_STORY
                else b
                for b in original.bindings
            ),
        )

    args["enumerate_bindings"] = enumerate_bindings
    result = run_native_continuous_player(**args)
    root = args["output"]
    audit_args = dict(
        store=args["store"],
        model=model,
        sequence_policy=policy,
        expected_native_plan_sha256=canonical_sha256(read(root / "native-plan.json")),
        expected_actor_result_sha256=canonical_sha256(read(root / "episode/result.json")),
        source_sha256=args["source"]["state_sha256"],
    )
    return args, result, executed, audit_args


def test_composite_policy_owns_guarded_execution_and_uses_only_completed_history(
    tmp_path, monkeypatch
):
    args, result, executed, audit_args = run(tmp_path, monkeypatch)
    root, policy = args["output"], args["sequence_policy"]
    episode = root / "episode"
    assert executed == [2, 4, 6, 8, 10, 12] and result["successful_decisions"] == 6
    assert result["model_sha256"] == policy.model_sha256
    assert read(root / "native-plan.json")["execution"]["model_sha256"] == policy.model_sha256
    assert read(episode / "plan.json")["sequence_policy"] == json.loads(
        json.dumps(policy.document())
    )
    declaration = read(episode / "sequence/declaration.json")
    assert declaration["scoring_changed"] and not declaration["training_eligible"]
    prior_story = 0
    for ordinal in range(6):
        step = episode / f"step-{ordinal:03d}"
        intent, decision = read(step / "intent.json"), read(step / "decision.json")
        for p, h in zip(
            intent["private_story_contexts"], intent["sequence_context"]["histories"], strict=True
        ):
            assert h["attempts"] == (prior_story if p["objective_ref"] else 0)
        assert intent["model_sha256"] == decision["model_sha256"] == policy.model_sha256
        assert decision["sequence"]["context_sha256"] == canonical_sha256(
            intent["sequence_context"]
        )
        if read(step / "outcome.json")["selected_kind"] == "advance_story":
            prior_story += 1
    assert prior_story > 0
    audit = audit_native_sequence_trace(root, **audit_args)
    assert audit.recorded_selector_and_binding_replayed == 6 and not audit.training_eligible
    windows = reconstruct_sequence_candidates(
        episode,
        source_sha256=args["source"]["state_sha256"],
        partition=args["source"]["partition"],
        expected_plan_sha256=canonical_sha256(read(episode / "plan.json")),
        expected_result_sha256=audit_args["expected_actor_result_sha256"],
        expected_declaration_sha256=canonical_sha256(declaration),
    )
    assert len(windows) == 3 and all(not w.training_eligible for w in windows)
    with pytest.raises(ValueError, match="declaration"):
        audit_native_sequence_trace(root, **{**audit_args, "sequence_policy": None})


@pytest.mark.parametrize("support", ["control", "restore"])
def test_composite_runner_keeps_support_unlearned_and_replayable(tmp_path, monkeypatch, support):
    args, result, executed, audit_args = run(tmp_path, monkeypatch, support=support)
    assert executed and result["model_decisions"] == 0
    assert "sequence_context" not in read(args["output"] / "episode/step-000/intent.json")
    audit = audit_native_sequence_trace(args["output"], **audit_args)
    assert audit.support_requiring_authority_audit == len(executed)


@pytest.mark.parametrize("fault", ["history", "prefix", "plan"])
def test_changed_recorded_sequence_inputs_are_not_admitted(tmp_path, monkeypatch, fault):
    args, _, _, audit_args = run(tmp_path, monkeypatch)
    root = args["output"]
    path = root / "episode/step-002/intent.json"
    doc = read(path)
    if fault == "history":
        doc["sequence_context"]["histories"][0]["attempts"] += 1
    elif fault == "prefix":
        doc["sequence_context"]["prefix_sha256"] = "f" * 64
    else:
        path = root / "episode/plan.json"
        doc = read(path)
        doc["sequence_policy"]["sequence_weight"] = 999.0
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        audit_native_sequence_trace(root, **audit_args)


@pytest.mark.parametrize("fault", ["no_collector", "horizon", "baseline"])
def test_invalid_native_opt_in_rejects_before_claim_or_input(tmp_path, monkeypatch, fault):
    args, executed = setup(tmp_path, monkeypatch)
    model, _, policy, _, _ = policy_setup()
    args.update(model=model, sequence_policy=policy, sequence_horizon=4)
    if fault == "no_collector":
        args["sequence_horizon"] = None
    elif fault == "horizon":
        args["sequence_horizon"] = 3
    else:
        args["model"] = replace(model, settled_examples=109)
    with pytest.raises(ValueError, match="matching"):
        run_native_continuous_player(**args)
    assert not executed and not args["output"].exists()


def test_composite_policy_target_join_still_masks_unverified_losses(tmp_path, monkeypatch):
    args, _, _, audit_args = run(tmp_path, monkeypatch)
    root = args["output"]
    audit_reader = reader(monkeypatch)
    windows = verify_sequence_target_channels(
        root, **audit_args, reader=audit_reader, partition=args["source"]["partition"],
        expected_actor_plan_sha256=canonical_sha256(read(root / "episode/plan.json")),
        expected_declaration_sha256=canonical_sha256(
            read(root / "episode/sequence/declaration.json")),
        expected_catalog_sha256=audit_reader.catalog_sha256,
    )
    assert len(windows) == 3
    assert all(w.targets.known == (True,) * 6 + (False,) for w in windows)
    assert all(not w.training_eligible for w in windows)
