import copy
from dataclasses import replace

import pytest
from test_private_artifacts import _make_store
from test_registered_learning_bridge import observations

from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import GoalManagerCompositionError
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_native_curriculum import (
    CONTRACT,
    OUTCOME_SCHEMA,
    PLAN_SCHEMA,
    NativeCurriculumInput,
    curriculum_projection,
    load_native_curriculum,
    publish_declaration,
    publish_outcome,
    reconstruct_native_curriculum,
    retained_native_curriculum,
)
from pokemon_red_completion.red_player_economy import snapshot_document
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def records(tmp_path, scope="local_red"):
    _, before, _, policy = observations(tmp_path)
    policy = replace(policy, completion_scope=scope)
    before = project_registered_observation(before, policy)
    s = replace(
        before.collection_observation.specimens[-1],
        species_ref=red_species_ref(131),
        location=CollectionLocation.BOX,
        slot_index=10,
    )
    after = project_registered_observation(
        replace(
            before,
            collection_observation=replace(
                before.collection_observation,
                owned_species=before.collection_observation.owned_species | {s.species_ref},
                specimens=(*before.collection_observation.specimens, s),
            ),
        ),
        policy,
    )
    q = GoalManagerQuestion(
        before.situation,
        (
            GoalOpportunity(
                "gift-private",
                GoalKind.ACQUIRE_SPECIES,
                GoalAvailability.AVAILABLE,
                estimated_effort=0.1,
                estimated_risk=0,
            ),
            GoalOpportunity(
                "unsupported",
                GoalKind.EXPLORE,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
            ),
        ),
    )
    plan = dict(
        schema=PLAN_SCHEMA,
        contract=CONTRACT,
        partition="train",
        objective="pokemon.registered-collection.v1",
        question={
            "schema": q.policy_input["schema"],
            "situation": q.situation.policy_dict(),
            "candidates": [x.policy_dict() for x in q.opportunities],
        },
        selected_index=0,
        before=before.public_dict(),
        economy_before=snapshot_document(EconomySnapshot(3000, ())),
        target_cash=3000,
        source=dict(
            origin_sha256="a" * 64,
            state_sha256="b" * 64,
            setup_receipt_sha256="c" * 64,
            source_commit="d" * 40,
            source_bundle_sha256="e" * 64,
            partition="train",
        ),
        maximum_actions=1000,
        maximum_frames=80000,
        teacher_selected=True,
        comparative_choice=False,
    )
    result = dict(
        schema=OUTCOME_SCHEMA,
        declaration_sha256=canonical_sha256(plan),
        after=after.public_dict(),
        succeeded=True,
        trace=[dict(ordinal=0, before_frame=0, after_frame=100, succeeded=True)],
        terminal_state_sha256="f" * 64,
        interventions_during_execution=[],
        native_audit=dict(
            before_sha256="b" * 64, terminal_sha256="f" * 64, input_frames=0, passed=True
        ),
    )
    return plan, result, q


@pytest.mark.parametrize("scope,denominator", [("local_red", 151), ("shared", 124)])
def test_exact_ordinary_projection_and_reward_without_fake_choice(tmp_path, scope, denominator):
    plan, result, q = records(tmp_path, scope)
    context, candidate = curriculum_projection(plan)
    assert context == living_dex_option_context_from_goal_situation(
        q.situation, economy_snapshot=EconomySnapshot(3000, ()), target_cash=3000
    )
    assert (
        candidate.features
        == project_living_dex_goal_candidate(q, 0, feature_version=4, binding_ref="any").features
    )
    row = reconstruct_native_curriculum(plan, result)
    assert row.features == candidate.vector(context, feature_version=4)
    assert row.outcome.completion_gain == pytest.approx(1 / denominator)
    assert row.outcome.action_cost == 1 / 30000
    assert row.outcome.frame_cost == 100 / 3000000
    assert row.outcome.economy is None
    assert row.public_dict()["regression_weight"] == 1
    assert not row.public_dict()["comparative_choice"]


def test_durable_reconstruction_and_future_retention(tmp_path):
    plan, result, _ = records(tmp_path / "fixture")
    _, _, store = _make_store(tmp_path)
    sha = publish_declaration(store, plan)
    item = publish_outcome(store, sha, result)
    row = load_native_curriculum(store, item)
    items, rows = retained_native_curriculum(store, {"native_curriculum": [item.public_dict()]})
    assert items == (item,) and rows == (row,)
    with pytest.raises(ValueError, match="repeats"):
        retained_native_curriculum(store, {"native_curriculum": [item.public_dict()]}, (item,))
    with pytest.raises(ValueError, match="missing"):
        load_native_curriculum(store, NativeCurriculumInput("0" * 64, item.outcome_sha256))


@pytest.mark.parametrize(
    "mutation",
    [
        "development",
        "source_development",
        "question",
        "units",
        "probabilities",
        "teacher",
        "audit",
        "trace_gap",
        "trace_bool",
        "unexecuted",
        "intervention",
        "terminal",
        "reward",
        "budget",
    ],
)
def test_tampering_or_wrong_admission_fails(tmp_path, mutation):
    plan, result, _ = records(tmp_path)
    if mutation == "development":
        plan["partition"] = "development"
    elif mutation == "source_development":
        plan["source"]["partition"] = "development"
    elif mutation == "question":
        plan["question"] = copy.deepcopy(plan["question"])
        plan["question"]["situation"]["need_pressures"]["resources"] = 0.123
    elif mutation == "units":
        plan["maximum_actions"] = True
    elif mutation == "probabilities":
        plan["behavior_probabilities"] = [1]
    elif mutation == "teacher":
        plan["teacher_selected"] = False
    elif mutation == "audit":
        result["native_audit"]["before_sha256"] = "0" * 64
    elif mutation == "trace_gap":
        result["trace"][0]["before_frame"] = 1
    elif mutation == "trace_bool":
        result["trace"][0]["ordinal"] = False
    elif mutation == "unexecuted":
        result["trace"] = []
    elif mutation == "intervention":
        result["interventions_during_execution"] = ["money"]
    elif mutation == "terminal":
        result["terminal_state_sha256"] = "0" * 64
    elif mutation == "reward":
        result["after"] = plan["before"]
    else:
        result["trace"][0]["after_frame"] = 80001
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises((ValueError, GoalManagerCompositionError)):
        reconstruct_native_curriculum(plan, result)


def test_native_failure_is_not_a_success_or_unselected_target(tmp_path):
    plan, result, _ = records(tmp_path)
    result.update(succeeded=False, after=plan["before"])
    row = reconstruct_native_curriculum(plan, result)
    assert not row.outcome.verified_success and row.outcome.completion_gain == 0
    assert row.outcome.action_cost > 0


def test_player_updates_authenticate_and_retain_native_lessons(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from test_red_player_training_fit import _fit

    import pokemon_red_completion.red_player_training_fit as fitting
    from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
    from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

    folder = tmp_path / "fitting"
    folder.mkdir()
    store, rows, prior, request, _ = _fit(folder, monkeypatch)
    current_rows = list(rows)
    monkeypatch.setattr(
        fitting,
        "load_red_player_training_episode",
        lambda *a, **k: SimpleNamespace(
            objective=REGISTERED_OBJECTIVE, examples=tuple(current_rows), curriculum_examples=()
        ),
    )
    args = dict(
        episodes=(request,),
        source_commit="e" * 40,
        source_bundle_sha256="f" * 64,
        registered_objective=True,
    )

    def fit(prior, **kw):
        result = fitting.fit_red_player_update(store, prior=prior, **args, **kw)
        sha = result["model"]["model_sha256"]
        loaded = load_player_goal_model_record_bytes(
            store.find_sealed_record(
                "rpr-model-" + sha, expected_kind="red_player_model"
            ).read_bytes(),
            expected_model_sha256=sha,
        )
        return result, loaded

    _, registered = fit(prior)
    plan, outcome, _ = records(tmp_path / "native")
    item = publish_outcome(store, publish_declaration(store, plan), outcome)
    result, taught = fit(registered, native_curriculum=(item,))
    assert result["new_settled_examples"] == 1 and result["curriculum_outcomes"] == 1
    lesson_hash = canonical_sha256(load_native_curriculum(store, item).public_dict())
    assert lesson_hash in taught.retained_example_sha256
    current_rows.append(replace(rows[0], decision_sha256="9" * 64))
    result, updated = fit(taught)
    assert result["new_settled_examples"] == 1 and result["curriculum_outcomes"] == 1
    assert lesson_hash in updated.retained_example_sha256
    corpus = store.find_sealed_record(
        "rp-corpus-" + updated.corpus_sha256, expected_kind="red_player_training_corpus"
    ).read()
    assert corpus["native_curriculum"] == [item.public_dict()]
    # Removing the authenticated admission cannot be hidden by cached vectors.
    damaged = dict(corpus, native_curriculum=[])
    sha = canonical_sha256(damaged)
    store.publish_sealed_record(
        "rp-corpus-" + sha, kind="red_player_training_corpus", record=damaged
    )
    with pytest.raises(ValueError, match="discard or rewrite"):
        fit(replace(updated, corpus_sha256=sha))
