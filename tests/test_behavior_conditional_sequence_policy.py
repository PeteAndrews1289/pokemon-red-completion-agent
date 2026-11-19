"""Explicit observational behavior is never silently relabeled as the scorer."""
import copy
from dataclasses import replace
import pytest
from test_player_sequence_policy import setup, select
from pokemon_red_completion.player_sequence_policy import SequencePolicy
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_recorded_selection_authority import record_selection_authority, replay_selection_authority

BEHAVIOR = "b" * 64

def conditional_setup(*args, **kw):
    model, options, legacy, context, calls = setup(*args, **kw)
    head = replace(legacy.head, behavior_model_sha256=BEHAVIOR)
    policy = replace(legacy, head=head, continuation_behavior_sha256=BEHAVIOR)
    return model, options, policy, context, calls


def test_legacy_refuses_foreign_behavior_and_keeps_old_document():
    model, _, policy, _, _ = setup()
    doc = policy.document()
    assert doc["schema"] == "pokemon.player.sequence-policy.v1"
    assert doc["composition"] == "immediate-plus-weighted-continuation-v1"
    assert "continuation_behavior_sha256" not in doc
    with pytest.raises(ValueError, match="composition"):
        replace(policy, head=replace(policy.head, behavior_model_sha256=BEHAVIOR))
    assert SequencePolicy.from_document(doc, expected_sha256=policy.model_sha256) == policy


def test_explicit_behavior_remains_bound_without_changing_predictions_or_baseline():
    model, options, legacy, context, _ = setup()
    _, _, policy, _, calls = conditional_setup()
    doc = policy.document()
    assert doc["schema"] == "pokemon.player.sequence-policy.v2"
    assert doc["baseline_sha256"] == model.model_sha256
    assert doc["continuation_behavior_sha256"] == doc["head"]["behavior_model_sha256"] == BEHAVIOR
    assert not doc["off_policy_improvement_verified"]
    assert not doc["native_admission_verified"] and not doc["live_policy_adopted"]
    assert policy.model_sha256 != legacy.model_sha256
    assert policy.scores(model, options.menu, context) == legacy.scores(model, options.menu, context)
    assert not calls
    assert SequencePolicy.from_document(doc, expected_sha256=policy.model_sha256) == policy


@pytest.mark.parametrize("bad", [None, "c"*64, "bad", True, 0])
def test_no_implicit_or_incorrect_behavior_rebinding(bad):
    _, _, policy, _, _ = conditional_setup()
    with pytest.raises(ValueError):
        replace(policy, continuation_behavior_sha256=bad)


def test_immediate_scorer_is_still_required_exactly():
    model, options, policy, context, calls = conditional_setup()
    foreign = replace(policy, baseline_sha256="c"*64)
    with pytest.raises(ValueError, match="selection"):
        foreign.scores(model, options.menu, context)
    assert not calls


@pytest.mark.parametrize("field,value", [("schema","pokemon.player.sequence-policy.v1"),("continuation_behavior_sha256","c"*64),("off_policy_improvement_verified",True),("continuation_semantics","counterfactual")])
def test_resigned_semantic_tampering_is_rejected(field, value):
    _, _, policy, _, _ = conditional_setup()
    doc = copy.deepcopy(policy.document());doc[field]=value
    with pytest.raises(ValueError):
        SequencePolicy.from_document(doc, expected_sha256=canonical_sha256(doc))


def test_actual_selector_and_inert_executor_replay_use_new_composition_identity():
    model, options, policy, context, calls = conditional_setup()
    choice = select(model, options, policy, context)
    intent=dict(menu=options.public_dict(),selection_seed=23,model_sha256=policy.model_sha256,sequence_context=context.document(),private_selection_authority=record_selection_authority(options,allow_earning_exploration=False))
    assert replay_selection_authority(model,intent,choice.public_dict(),allow_earning_exploration=False,sequence_policy=policy)==choice.selected_binding.binding_ref
    with pytest.raises(ValueError):
        replay_selection_authority(model,intent,choice.public_dict(),allow_earning_exploration=False)
    assert not calls


def test_native_controller_and_sealed_replay_accept_explicit_behavior_without_relabeling(tmp_path, monkeypatch):
    import test_red_native_sequence_policy as native_fixture
    from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace
    monkeypatch.setattr(native_fixture,"policy_setup",conditional_setup)
    args,result,executed,audit_args=native_fixture.run(tmp_path,monkeypatch)
    assert executed and result["model_sha256"]==args["sequence_policy"].model_sha256
    assert args["sequence_policy"].head.behavior_model_sha256==BEHAVIOR
    assert audit_native_sequence_trace(args["output"],**audit_args).model_choices_replayed==6
