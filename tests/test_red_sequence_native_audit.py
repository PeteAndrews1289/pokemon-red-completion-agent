"""Replay real frozen selection and sealed traces on the ROM-free native fixture."""

import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation
from test_red_native_player import setup

import pokemon_red_completion.red_sequence_native_audit as audit_module
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_live_option_menu import RedLiveOptionSet, select_red_live_option
from pokemon_red_completion.red_native_player import run_native_continuous_player
from pokemon_red_completion.red_sequence_native_audit import (
    audit_native_sequence_trace,
    replay_recorded_sequence_choice,
)


def read(path):
    return json.loads(path.read_bytes())


def collect(tmp_path, monkeypatch, *, greedy=False):
    args, executed = setup(tmp_path, monkeypatch)
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    args["sequence_horizon"] = 2
    if greedy:
        args["source"]={**args["source"],"partition":"development"}
        del args["sequence_horizon"]  # Greedy is a separate DEVELOPMENT mode.
    run_native_continuous_player(**args,**({"greedy_selection":True} if greedy else {}))
    root = args["output"]
    kwargs = dict(
        store=args["store"], model=args["model"],
        expected_native_plan_sha256=canonical_sha256(read(root / "native-plan.json")),
        expected_actor_result_sha256=canonical_sha256(read(root / "episode/result.json")),
        source_sha256=args["source"]["state_sha256"],
    )
    return root, kwargs, executed


def test_complete_trace_and_policy_replay_do_not_claim_native_truth(tmp_path, monkeypatch):
    root, kwargs, executed = collect(tmp_path, monkeypatch)
    audit = audit_native_sequence_trace(root, **kwargs)
    assert executed == [2, 4, 6]
    assert (audit.actions, audit.frames, audit.model_choices_replayed) == (3, 6, 3)
    assert not audit.training_eligible and not audit.native_state_facts_verified
    assert not audit.source_ancestry_verified and not audit.safety_and_executor_authority_verified
    assert audit.recorded_selector_and_binding_replayed == 3
    assert audit_native_sequence_trace(root, **kwargs) == audit
    assert executed == [2, 4, 6]  # audit performed no extra inputs


def test_audit_formats_trace_and_unreported_input_lookups(tmp_path, monkeypatch):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    original = audit_module.native_action_record_id
    calls = []

    def record_id(kind, declaration, ordinal):
        calls.append((kind, ordinal))
        return original(kind, declaration, ordinal)

    monkeypatch.setattr(audit_module, "native_action_record_id", record_id)
    audit_native_sequence_trace(root, **kwargs)
    assert calls == [(kind, ordinal) for ordinal in range(4)
                     for kind in ("action", "trace")]


@pytest.mark.parametrize("field,value", [
    ("scores", [0, 0]), ("probabilities", [1.0, 0.0]),
    ("selected_candidate_index", -1), ("model_sha256", "f" * 64),
    ("teacher_labels", True), ("mode", "equivalent_exploration"),
])
def test_sampling_replay_rejects_edited_decision(tmp_path, monkeypatch, field, value):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    step = root / "episode/step-000"
    decision = read(step / "decision.json")
    decision[field] = value
    with pytest.raises(ValueError, match="does not replay"):
        replay_recorded_sequence_choice(
            kwargs["model"], read(step / "intent.json"), decision, seed=101, ordinal=0,
        )


def test_seed_and_query_authority_must_match_original_sampler(tmp_path, monkeypatch):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    step = root / "episode/step-000"
    intent, decision = read(step / "intent.json"), read(step / "decision.json")
    with pytest.raises(ValueError, match="seed"):
        replay_recorded_sequence_choice(kwargs["model"], intent, decision, seed=102, ordinal=0)
    intent["query_may_be_consumed"] = False
    with pytest.raises(ValueError, match="query authority"):
        replay_recorded_sequence_choice(kwargs["model"], intent, decision, seed=101, ordinal=0)


@pytest.mark.parametrize("fault", [None,"missing_opt_in","edited_score","wrong_seed","query"])
def test_recorded_greedy_choice_needs_original_seed_and_exact_authority(tmp_path,monkeypatch,fault):
    root,kwargs,executed=collect(tmp_path,monkeypatch,greedy=True)
    step=root/"episode/step-000"
    intent,decision=read(step/"intent.json"),read(step/"decision.json")
    assert decision["mode"]=="model_greedy"
    if fault=="missing_opt_in":
        del intent["private_selection_authority"]["greedy_selection"]
    elif fault=="edited_score":
        decision["scores"][0]+=1
    elif fault=="wrong_seed":
        intent["selection_seed"]+=1
    elif fault=="query":
        intent["query_may_be_consumed"]=False
    if fault:
        with pytest.raises(ValueError):
            replay_recorded_sequence_choice(kwargs["model"],intent,decision,seed=101,ordinal=0)
    else:
        assert replay_recorded_sequence_choice(kwargs["model"],intent,decision,seed=101,ordinal=0)=="model_greedy"
    assert executed==[2,4,6]


def test_forced_support_is_not_certified_as_a_sampled_choice(tmp_path, monkeypatch):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    step = root / "episode/step-000"
    intent, decision = read(step / "intent.json"), read(step / "decision.json")
    decision["mode"] = "deterministic_safety"
    assert replay_recorded_sequence_choice(
        kwargs["model"], intent, decision, seed=101, ordinal=0,
    ) == "support_requires_authority_audit"


def test_equivalent_exploration_replays_real_sampler_without_model_credit(tmp_path, monkeypatch):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    intent = read(root / "episode/step-000/intent.json")
    menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
    first = menu.candidates[0]
    menu = replace(menu, candidates=(first, replace(first, binding_ref="duplicate-features")))
    bindings = tuple(_binding(GoalKind.ADVANCE_STORY, binding_ref=c.binding_ref, calls=[])
                     for c in menu.candidates)
    options = RedLiveOptionSet(
        _situation(resources=0.1), _ordinary_bindings([]), menu, bindings, frozenset(), "a" * 64,
    )
    decision = select_red_live_option(
        kwargs["model"], options, seed=intent["selection_seed"],
    ).public_dict()
    intent.update(menu=options.public_dict(), query_may_be_consumed=False)
    assert replay_recorded_sequence_choice(
        kwargs["model"], intent, decision, seed=101, ordinal=0,
    ) == "equivalent_exploration"
    decision["probabilities"] = [1.0, 0.0]
    with pytest.raises(ValueError, match="does not replay"):
        replay_recorded_sequence_choice(kwargs["model"], intent, decision, seed=101, ordinal=0)


@pytest.mark.parametrize("fault", ["missing", "failed", "gap", "ordinal_bool", "extra"])
def test_native_trace_cannot_hide_or_reassign_input(tmp_path, monkeypatch, fault):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    store = kwargs["store"]
    original = store.find_sealed_record
    identity = f"rnl-trace-{kwargs['expected_native_plan_sha256']}-1"

    def lookup(record_id, **options):
        record = original(record_id, **options)
        if fault == "extra" and record_id == (
            f"rnl-action-{kwargs['expected_native_plan_sha256']}-3"
        ):
            return NS(read=lambda: {})
        if record_id != identity:
            return record
        if fault == "missing":
            return None
        row = record.read()
        if fault == "failed":
            row["succeeded"] = False
        elif fault == "gap":
            row["before_frame"] = 1
        elif fault == "ordinal_bool":
            row["ordinal"] = True
        return NS(read=lambda: row)

    monkeypatch.setattr(
        type(store), "find_sealed_record", lambda self, key, **kw: lookup(key, **kw)
    )
    with pytest.raises(ValueError):
        audit_native_sequence_trace(root, **kwargs)


@pytest.mark.parametrize("file,field,value", [
    ("native-costs.json", "actions_attempted", 2),
    ("native-costs.json", "actions_completed", 2),
    ("native-costs.json", "frames", 5),
    ("native-costs.json", "goal_attempts", 2),
    ("native-costs.json", "seconds", float("nan")),
    ("native-plan.json", "automatic_fit", True),
    ("episode/plan.json", "exploration_mix", 0.5),
])
def test_changed_scope_or_counters_reject_without_touching_receipts(
    tmp_path, monkeypatch, file, field, value,
):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    path = root / file
    row = read(path)
    row[field] = value
    path.write_text(json.dumps(row))
    modified = path.read_bytes()
    with pytest.raises(ValueError):
        audit_native_sequence_trace(root, **kwargs)
    assert path.read_bytes() == modified


def test_changed_terminal_or_source_bytes_reject(tmp_path, monkeypatch):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    for name in ("terminal.state", "source.state"):
        path = root / name
        original = path.read_bytes()
        path.write_bytes(b"wrong state")
        with pytest.raises(ValueError):
            audit_native_sequence_trace(root, **kwargs)
        path.write_bytes(original)


@pytest.mark.parametrize("balanced", [True, False])
def test_sampling_replay_preserves_kind_balanced_and_legacy_receipts(
    tmp_path, monkeypatch, balanced,
):
    root, kwargs, _ = collect(tmp_path, monkeypatch)
    intent = read(root / "episode/step-000/intent.json")
    menu = restore_living_dex_policy_menu(intent["menu"]["menu"])
    first, second = menu.candidates
    menu = replace(menu, candidates=(first, replace(first, binding_ref="same-kind-variant"), second))
    from pokemon_red_completion.living_dex_goal_policy import living_dex_option_kind_for_goal
    bindings = tuple(_binding(next(kind for kind in GoalKind
        if living_dex_option_kind_for_goal(kind, feature_version=menu.feature_version)
           is candidate.features.kind), binding_ref=candidate.binding_ref, calls=[])
        for candidate in menu.candidates)
    options = RedLiveOptionSet(
        _situation(resources=0.1), _ordinary_bindings([]), menu, bindings, frozenset(), "a" * 64,
    )
    decision = select_red_live_option(kwargs["model"], options,
        seed=intent["selection_seed"], kind_balanced_exploration=balanced).public_dict()
    intent.update(menu=options.public_dict(), query_may_be_consumed=True)
    assert replay_recorded_sequence_choice(kwargs["model"], intent, decision,
        seed=101, ordinal=0) == "model_exploration"
    if balanced:
        # Three rows contain two public kinds: each variant gets half its kind's mass.
        assert decision["probabilities"][0] == decision["probabilities"][1]
        decision["sampling_rule"] = "unrecorded-rule"
        with pytest.raises(ValueError, match="does not replay"):
            replay_recorded_sequence_choice(kwargs["model"], intent, decision, seed=101, ordinal=0)
