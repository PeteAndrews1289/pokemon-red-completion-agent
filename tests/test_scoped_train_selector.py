"""Authenticate production selection on TRAIN without a flag or policy swap."""

import json
from dataclasses import asdict
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_consequence_v15_vertical import dispatch_head
from test_private_artifacts import _make_store
from test_recurrence_parent_exploration import observed_menu

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_consequence_choice import (
    branch_recovery_scope_ref,
    validate_greedy_branch_recovery_scope,
)
from pokemon_red_completion.red_native_player import NativeExecutionIdentity, NativePlayerSession
from pokemon_red_completion.red_scoped_train_composition import (
    ScopedTrainComposition,
    ScopedTrainSelectorInference,
    scoped_selector_declaration,
)
from pokemon_red_completion.red_story_battle import StoryTrainerContract


def case(tmp_path):
    _, _, store = _make_store(tmp_path)
    state = b"authenticated original TRAIN state"
    digest = sha256(state).hexdigest()
    context = json.dumps(
        dict(
            schema="pokemon.red.native-player-continuation.v1",
            state_sha256=digest,
            fit_allowed=False,
            grants_new_budget=False,
        )
    ).encode()
    model, _ = observed_menu(seen=False)
    head = dispatch_head()
    objective_ref = ("defeat_giovanni", "defeat_misty")
    flags = dict(
        greedy_selection=True,
        refine_preparation=True,
        defer_unbound_preparation=False,
        allow_singleton_parent_support=False,
        associate_unique_combat=True,
        explore_outside_scope=False,
        explore_on_movement_recurrence=True,
    )
    selector = dict(
        model=model,
        head=head,
        objective_ref=objective_ref,
        challenge_ref=branch_recovery_scope_ref(objective_ref),
        flags=flags,
    )
    declaration = scoped_selector_declaration(**selector)
    q = tmp_path / "qualification.json"
    q.write_text(
        json.dumps(
            dict(
                partition="train",
                full_current_menu_constructed=True,
                original_state_unchanged=True,
                source=dict(sha256=digest),
                native_boundary=dict(state_sha256=digest),
            )
        )
    )
    work = json.dumps(
        dict(
            partition="train",
            fit_allowed=False,
            source_qualification=dict(path=str(q), sha256=sha256(q.read_bytes()).hexdigest()),
            pins={str(q): sha256(q.read_bytes()).hexdigest()},
            production_selector=declaration,
        )
    ).encode()
    output = tmp_path / "native"
    output.mkdir()
    composition = ScopedTrainComposition(
        digest,
        "b" * 64,
        "c" * 40,
        sha256(context).hexdigest(),
        sha256(work).hexdigest(),
        output / "native-plan.json",
        (
            StoryTrainerContract(
                "defeat_erika", "observed-story-obstruction", 134, (219, 19, 1), 86, 330
            ),
        ),
    )
    source = dict(
        partition="train",
        state_sha256=digest,
        origin_sha256="b" * 64,
        source_commit="c" * 40,
        experiment_sha256=composition.work_order_sha256,
    )
    execution = NativeExecutionIdentity("unit-selector", "case", declaration["selector_sha256"], 17)
    native = dict(
        schema="pokemon.red.native-continuous-player.v2",
        source=source,
        execution=asdict(execution),
        automatic_fit=False,
        promotion=False,
    )
    composition.native_plan_path.write_text(json.dumps(native))
    store.publish_sealed_record(
        execution.claim_id, kind="red_native_player_execution", record=native
    )
    session = NativePlayerSession.__new__(NativePlayerSession)
    session.store, session.source, session.execution, session.output = (
        store,
        source,
        execution,
        output,
    )
    session.actions = NS(actions_executed=0)
    session.controller = NS(frames_executed=0)
    return dict(
        composition=composition,
        source=source,
        source_state=state,
        context_bytes=context,
        work_order_bytes=work,
        session=session,
        **selector,
    )


def authenticate(args):
    return ScopedTrainSelectorInference.authenticate(**args)


def guard(args, scope):
    return validate_greedy_branch_recovery_scope(
        allow=True,
        source=args["source"],
        model=args["model"],
        head=args["head"],
        objective_ref=args["objective_ref"],
        challenge_ref=args["challenge_ref"],
        train_selector_scope=scope,
        **args["flags"],
    )


def test_authenticated_selector_retains_model_and_declares_no_learning(tmp_path):
    args = case(tmp_path)
    before = args["model"].model_sha256
    scope = authenticate(args)
    assert guard(args, scope) is True
    assert scope.document()["automatic_fit"] is False
    assert scope.document()["optimizer_admission"] is False
    assert scope.document()["sequence_collector"] is False
    assert scope.document()["source_ancestry_and_fit_admission_not_conferred"] is True
    assert args["model"].model_sha256 == before
    assert args["session"].actions.actions_executed == 0


@pytest.mark.parametrize(
    "fault",
    [
        "state",
        "context",
        "work",
        "partition",
        "native",
        "qualification",
        "late_input",
        "late_frame",
        "flags",
    ],
)
def test_tampered_or_late_scope_fails_before_model_query(tmp_path, monkeypatch, fault):
    args = case(tmp_path)
    monkeypatch.setattr(type(args["model"]), "scores", lambda *a, **k: pytest.fail("model query"))
    if fault == "state":
        args["source_state"] += b"changed"
    elif fault == "context":
        args["context_bytes"] += b" "
    elif fault == "work":
        args["work_order_bytes"] += b" "
    elif fault == "partition":
        args["source"] = {**args["source"], "partition": "development"}
    elif fault == "native":
        args["composition"].native_plan_path.write_text("{}")
    elif fault == "qualification":
        (tmp_path / "qualification.json").write_text("{}")
    elif fault == "late_input":
        args["session"].actions.actions_executed = 1
    elif fault == "late_frame":
        args["session"].controller.frames_executed = 1
    else:
        args["flags"]["greedy_selection"] = 1
    with pytest.raises((ValueError, KeyError)):
        authenticate(args)


@pytest.mark.parametrize(
    "fake", [True, {}, {"schema": "pokemon.red.scoped-train-selector-inference.v1"}]
)
def test_flags_and_decoded_documents_cannot_replace_witness(tmp_path, fake):
    with pytest.raises(ValueError):
        guard(case(tmp_path), fake)


def test_changed_parent_head_flags_or_native_plan_cannot_reuse_witness(tmp_path):
    args = case(tmp_path)
    scope = authenticate(args)
    args["flags"]["explore_outside_scope"] = True
    with pytest.raises(ValueError):
        guard(args, scope)
    args["flags"]["explore_outside_scope"] = False
    path = args["composition"].native_plan_path
    native = json.loads(path.read_bytes())
    native["source"]["state_sha256"] = "f" * 64
    path.write_text(json.dumps(native))
    with pytest.raises(ValueError):
        guard(args, scope)


def test_unwitnessed_train_recurrence_still_fails(tmp_path):
    args = case(tmp_path)
    with pytest.raises(ValueError):
        guard(args, None)


def test_token_constructor_does_not_accept_a_document(tmp_path):
    args = case(tmp_path)
    with pytest.raises(ValueError):
        ScopedTrainSelectorInference(
            {},
            source=args["source"],
            composition=args["composition"],
            native_sha256=canonical_sha256({}),
        )
