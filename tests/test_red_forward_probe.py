"""Authenticated fit loading is not production authority or new fitting."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_forward_goal_learning import examples
from test_goal_resource_quote import _supply_model
from test_red_player_training import _plan

from pokemon_red_completion.forward_goal import ForwardGoalPlan
from pokemon_red_completion.forward_goal_learning import fit_forward_goal
from pokemon_red_completion.living_dex_option_value import (
    option_feature_names,
    upgrade_option_value_model_for_optional_recovery,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_forward_goal import (
    RED_FORWARD_CONTEXT_NAMES,
    red_forward_continuation_sha256,
    red_forward_execution_flags,
    red_forward_verifier_sha256,
)
from pokemon_red_completion.red_forward_probe import load_red_forward_probe


def fixture():
    tail = upgrade_option_value_model_for_optional_recovery(_supply_model())
    native = dict(_plan(tail).document)
    flags = red_forward_execution_flags()
    plan = ForwardGoalPlan(
        "red-story-objective",
        red_forward_verifier_sha256("defeat_bruno"),
        red_forward_continuation_sha256(
            behavior_policy_id=native["behavior_policy_id"],
            model_sha256=tail.model_sha256,
            source_bundle_sha256=native["source_bundle_sha256"],
            profile_sha256=native["profile_sha256"],
            execution_flags=flags,
        ),
        12000,
        1200000,
        2,
        2,
    )
    names = option_feature_names(3)
    candidates = ((0.0,) * len(names), (1.0,) + (0.0,) * (len(names) - 1))
    rows = tuple(
        replace(
            row,
            plan=plan,
            choice=replace(
                row.choice,
                context_names=RED_FORWARD_CONTEXT_NAMES,
                context=(0.5,) * 7,
                candidate_names=names,
                candidates=candidates,
            ),
        )
        for row in examples()[:2]
    )
    fitted = fit_forward_goal(rows).model
    metadata = {
        **flags,
        "player_training_plan": native,
        "forward_goal_plan_sha256": plan.sha256,
        "forward_story_objective": "defeat_bruno",
    }
    doc = {
        "schema": "pokemon.red.forward-goal-shadow-fit.v1",
        "authority": "unqualified-shadow",
        "player_model_changed": False,
        "independent_evaluation": False,
        "model": fitted.public_dict(),
        "model_sha256": fitted.sha256,
        "behavior_model_sha256": tail.model_sha256,
        "outcomes": [row.public_dict() for row in rows],
        "episodes": [
            {
                "episode_id": "goal-episode-1",
                "manifest_sha256": "a" * 64,
                "training_plan_sha256": canonical_sha256(native),
            }
        ],
    }
    reads = []

    def find(record_id, *, expected_kind):
        reads.append((record_id, expected_kind))
        return SimpleNamespace(summary=SimpleNamespace(record_sha256="d" * 64), read=lambda: doc)

    def open_episode(episode_id):
        reads.append(episode_id)
        return SimpleNamespace(manifest_sha256="a" * 64, read_header=lambda: {"metadata": metadata})

    return SimpleNamespace(
        doc=doc,
        metadata=metadata,
        model=fitted,
        tail=tail,
        plan=plan,
        reads=reads,
        store=SimpleNamespace(find_sealed_record=find, open_episode=open_episode),
    )


def load(f, **changes):
    return load_red_forward_probe(
        f.store,
        **{
            "record_id": "red-forward-fit-" + canonical_sha256(f.doc),
            "expected_record_sha256": "d" * 64,
            "expected_model_sha256": f.model.sha256,
            "tail_seed": 41,
            **changes,
        },
    )


def test_valid_sealed_fit_loads_only_unqualified_first_actor_and_frozen_tail():
    f = fixture()
    probe = load(f)
    assert probe.model == f.model and probe.tail_model_sha256 == f.tail.model_sha256
    assert probe.tail_seed == 41 and probe.fitted_plan == f.plan
    header = probe.header()
    assert header["authority"] == "bounded-training-probe-not-production"
    assert header["recursive_forward_control"] is False
    assert header["continuation_source_equivalence_claimed"] is False
    assert header["native_training_admission"] is False
    assert header["calibrated_probabilities"] is False
    assert f.reads[0][1] == "red_forward_goal_shadow_fit"
    assert f.reads[1] == "goal-episode-1"
    assert "path" not in str(header)


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_record_sha256", "0" * 64),
        ("expected_model_sha256", "0" * 64),
        ("record_id", "red-forward-fit-" + "0" * 64),
        ("tail_seed", -1),
        ("tail_seed", True),
    ],
)
def test_wrong_identity_or_seed_rejects_without_actor(field, value):
    with pytest.raises(ValueError):
        load(fixture(), **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("authority", "production"),
        ("player_model_changed", True),
        ("independent_evaluation", True),
        ("outcomes", []),
        ("episodes", []),
        ("schema", "pokemon.red.forward-goal-shadow-fit.v2"),
        ("behavior_model_sha256", "0" * 64),
        ("model_sha256", "0" * 64),
    ],
)
def test_authenticated_but_semantically_invalid_fit_rejects(field, value):
    f = fixture()
    f.doc[field] = value
    with pytest.raises(ValueError):
        load(f)


@pytest.mark.parametrize("fault", ["manifest", "native_plan", "goal_plan", "flag", "goal"])
def test_original_episode_provenance_and_execution_contract_are_not_assumed(fault):
    f = fixture()
    if fault == "manifest":
        f.doc["episodes"][0]["manifest_sha256"] = "0" * 64
    elif fault == "native_plan":
        f.metadata["player_training_plan"]["seed"] = 999
    elif fault == "goal_plan":
        f.metadata["forward_goal_plan_sha256"] = "0" * 64
    elif fault == "flag":
        f.metadata["routed_recovery"] = True
    else:
        f.metadata["forward_story_objective"] = "defeat_lance"
    with pytest.raises(ValueError):
        load(f)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tail_policy_id", "other"),
        ("fit_record_sha256", "invalid"),
        ("tail_model_sha256", "0" * 64),
        ("profile_sha256", "0" * 64),
        ("fitted_source_bundle_sha256", "0" * 64),
        ("execution_flags", ()),
    ],
)
def test_probe_spec_cannot_expand_or_erase_fitted_scope(field, value):
    with pytest.raises(ValueError):
        replace(load(fixture()), **{field: value})


def test_flag_values_and_duplicate_names_cannot_hide_scope_changes():
    probe = load(fixture())
    with pytest.raises(ValueError):
        replace(probe, execution_flags=(*probe.execution_flags, probe.execution_flags[0]))
    with pytest.raises(ValueError):
        replace(
            probe, execution_flags=((probe.execution_flags[0][0], 0), *probe.execution_flags[1:])
        )


def test_wrong_context_names_cannot_relabel_current_red_resources():
    probe = load(fixture())
    names = ("future_outcome", *probe.model.context_names[1:])
    with pytest.raises(ValueError):
        replace(probe, model=replace(probe.model, context_names=names))
