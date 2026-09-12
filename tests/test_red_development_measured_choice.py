from __future__ import annotations

import random
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from test_living_dex_option_value import _menu
from test_red_player_training import _episode
from test_registered_learning_bridge import observations
from test_registered_runtime_binding import bound_fixture

from pokemon_red_completion.collection import CollectionLocation, LivingSpecimen
from pokemon_red_completion.goal_manager_composition_runtime import GoalManagerCompositionError
from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
from pokemon_red_completion.living_dex_policy_codec import LivingDexPolicyCodecError
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_development_measured_choice import (
    DEVELOPMENT_MEASURED_CHOICE_SCHEMA,
    DEVELOPMENT_MEASURED_RESULT_SCHEMA,
    RedDevelopmentMeasuredChoice,
    load_red_development_measured_choice_example,
    publish_development_measured_choice,
)
from pokemon_red_completion.red_player_incremental_fit import (
    fit_incremental_measured_choice,
    fit_incremental_registered_results,
    load_prior_player_inventory,
)
from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
from pokemon_red_completion.red_player_training_fit import (
    RedPlayerEpisodeInput,
    fit_red_player_update,
)
from pokemon_red_completion.red_player_training_plan import (
    REGISTERED_TRAINING_PLAN_SCHEMA,
    RedPlayerTrainingPlan,
)
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE


def _model_sha(fit_dict: Mapping[str, object]) -> str:
    model_doc = cast(Mapping[str, object], fit_dict["model"])
    return cast(str, model_doc["model_sha256"])


def _safari_observations(tmp_path: Path):
    runtime_path = tmp_path / "safari_runtime"
    runtime_path.mkdir(parents=True, exist_ok=True)
    runtime, _, _ = bound_fixture(runtime_path)
    pol = runtime.registration_policy
    b = runtime.adapter.observe()
    new_species = red_species_ref(115)  # Kangaskhan (Safari zone acquisition)
    new_specimen = LivingSpecimen(
        new_species,
        level=25,
        location=CollectionLocation.BOX,
        container_index=1,
        slot_index=1,
    )
    a = replace(
        b,
        capture_item_count=b.capture_item_count - 1,
        collection_observation=replace(
            b.collection_observation,
            owned_species=b.collection_observation.owned_species | {new_species},
            specimens=(*b.collection_observation.specimens, new_specimen),
        ),
    )
    pb = project_registered_observation(b, pol).public_dict()
    pa = project_registered_observation(a, pol).public_dict()
    return pb, pa


def _valid_choice(tmp_path: Path, *, model_sha256: str = "1" * 64) -> RedDevelopmentMeasuredChoice:
    from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu

    pb, pa = _safari_observations(tmp_path)
    menu = restore_living_dex_policy_menu(_menu("safari").policy_dict())
    return RedDevelopmentMeasuredChoice(
        choice_id="safari-choice-kangaskhan",
        menu=menu,
        selected_candidate_index=0,
        behavior_probabilities=(0.6, 0.3, 0.1, 0.0),
        model_sha256=model_sha256,
        before_observation=pb,
        after_observation=pa,
        parent_state_sha256="2" * 64,
        terminal_state_sha256="3" * 64,
        segments_sha256="4" * 64,
        controller_actions=150,
        emulator_frames=2400,
        resource_costs={"safari_balls_used": 5, "money_spent": 500},
        maximum_actions=30_000,
        maximum_frames=3_000_000,
    )


def _bootstrap_registered_model(tmp_path: Path, monkeypatch):
    root = tmp_path.resolve()
    _, before, _, policy = observations(root / "obs")
    after = replace(before, capture_item_count=before.capture_item_count + 1)
    pair = tuple(project_registered_observation(o, policy) for o in (before, after))

    def declare(store, plan):
        document = dict(plan.document)
        document.update(
            schema=REGISTERED_TRAINING_PLAN_SCHEMA,
            objective=REGISTERED_OBJECTIVE,
            registration_binding_sha256=policy.sha256,
            maximum_actions=30_000,
            maximum_frames=3_000_000,
            origin_state_sha256="a" * 64,
            origin_envelope_sha256="b" * 64,
            restore_profile_sha256="c" * 64,
            continuation_episode_id="parent",
            continuation_checkpoint_sha256="d" * 64,
        )
        return RedPlayerTrainingPlan(document)

    monkeypatch.setattr(
        "pokemon_red_completion.red_player_training_dataset._require_continuation_origin",
        lambda *_: None,
    )
    (root / "fitting").mkdir(parents=True, exist_ok=True)
    store, plan, behavior, completed = _episode(
        root / "fitting",
        plan_transform=declare,
        registration_observations=pair,
        return_inputs=True,
        repeat_registered_choice=True,
    )
    prior = LivingDexGoalModelRecord(behavior, "a" * 64, "b" * 40, "c" * 64, 1, 1)
    request = RedPlayerEpisodeInput(plan, "goal-episode-1", completed.manifest_sha256, prior)

    fit_a = fit_red_player_update(
        store,
        prior=prior,
        episodes=(request,),
        source_commit="b" * 40,
        source_bundle_sha256="c" * 64,
        registered_objective=True,
    )
    sha_a = _model_sha(fit_a)
    rec_a = store.find_sealed_record(f"rpr-model-{sha_a}", expected_kind="red_player_model")
    model_a = load_player_goal_model_record_bytes(rec_a.read_bytes(), expected_model_sha256=sha_a)
    return store, prior, request, model_a


def test_valid_measured_choice_roundtrip_and_properties(tmp_path):
    choice = _valid_choice(tmp_path)
    assert choice.action_trace_available is False
    assert choice.independent_evaluation is False
    assert choice.authority_promotion_eligible is False
    assert choice.teacher_labels == 0
    assert choice.training_only is True

    pub = choice.public_dict()
    assert pub["schema"] == DEVELOPMENT_MEASURED_CHOICE_SCHEMA
    assert pub["choice_id"] == "safari-choice-kangaskhan"
    assert pub["action_trace_available"] is False
    assert pub["independent_evaluation"] is False
    assert pub["authority_promotion_eligible"] is False
    assert pub["teacher_labels"] == 0
    assert pub["training_only"] is True
    assert pub["controller_actions"] == 150
    assert pub["emulator_frames"] == 2400
    assert pub["resource_costs"] == {"safari_balls_used": 5, "money_spent": 500}

    # Deserialization round-trip
    restored = RedDevelopmentMeasuredChoice.from_public(pub)
    assert restored == choice
    assert restored.decision_sha256 == choice.decision_sha256

    # Arm conversion
    arm = choice.to_observed_arm_example()
    assert arm.partition == "train"
    assert arm.decision_sha256 == choice.decision_sha256
    assert arm.outcome.verified_success is True
    assert arm.outcome.target_vector is not None
    assert arm.outcome.action_cost == 150 / 30_000
    assert arm.outcome.frame_cost == 2400 / 3_000_000


def test_adversarial_model_identity_tampering(tmp_path):
    choice = _valid_choice(tmp_path)

    # Corrupt model sha (non-hex, wrong length)
    for bad_sha in ["not-a-hash", "0" * 63, "0" * 65, "G" * 64]:
        with pytest.raises(ValueError, match="model_sha256 must be a 64-character lowercase"):
            replace(choice, model_sha256=bad_sha)

    # Deserializer rejecting bad model_sha256
    doc = choice.public_dict()
    doc["model_sha256"] = "bad"
    with pytest.raises(ValueError, match="model_sha256"):
        RedDevelopmentMeasuredChoice.from_public(doc)


def test_adversarial_menu_tampering(tmp_path):
    choice = _valid_choice(tmp_path)

    # Deserializing menu with fewer than 2 candidates is rejected
    doc = choice.public_dict()
    doc["menu"]["candidates"] = []
    with pytest.raises(LivingDexPolicyCodecError):
        RedDevelopmentMeasuredChoice.from_public(doc)

    doc_single = choice.public_dict()
    doc_single["menu"]["candidates"] = [doc_single["menu"]["candidates"][0]]
    with pytest.raises(LivingDexPolicyCodecError):
        RedDevelopmentMeasuredChoice.from_public(doc_single)

    # Selecting unavailable candidate
    with pytest.raises(ValueError, match="selected candidate is unavailable"):
        replace(choice, selected_candidate_index=3)


def test_adversarial_sample_selection_tampering(tmp_path):
    choice = _valid_choice(tmp_path)

    # Selected index out of bounds or unavailable
    for bad_idx in [-1, 4, 10]:
        with pytest.raises(ValueError, match="selected candidate is unavailable"):
            replace(choice, selected_candidate_index=bad_idx)

    # Selected index as boolean
    with pytest.raises(ValueError, match="selected candidate is unavailable"):
        replace(choice, selected_candidate_index=True)

    # Non-integer in serialized format
    doc = choice.public_dict()
    doc["selected_candidate_index"] = "0"
    match_msg = "selected candidate is unavailable|selected_candidate_index must be an integer"
    with pytest.raises(ValueError, match=match_msg):
        RedDevelopmentMeasuredChoice.from_public(doc)

    # Behavior probabilities length mismatch
    with pytest.raises(ValueError, match="probability length differs"):
        replace(choice, behavior_probabilities=(0.5, 0.5))

    # Probabilities not summing to 1.0
    with pytest.raises(ValueError, match="must sum to 1.0"):
        replace(choice, behavior_probabilities=(0.5, 0.3, 0.1, 0.2))

    # Negative probability
    with pytest.raises(ValueError, match="must be non-negative"):
        replace(choice, behavior_probabilities=(1.1, -0.1, 0.0, 0.0))

    # Selection seed replay mismatch:
    # Deterministic sampling from RNG with seed must reproduce selected_candidate_index
    rng_seed = 12345
    rng = random.Random(rng_seed)
    expected_sample = rng.choices(
        range(len(choice.menu.candidates)), weights=choice.behavior_probabilities, k=1
    )[0]
    mismatched_index = (expected_sample + 1) % len(choice.menu.candidates)
    # Available candidate that does not match seed's draw
    if mismatched_index in choice.menu.available_indices:
        seed_err = "selection seed does not replay the recorded selection"
        with pytest.raises(ValueError, match=seed_err):
            replace(choice, selected_candidate_index=mismatched_index, selection_seed=rng_seed)


def test_adversarial_state_hashes_tampering(tmp_path):
    choice = _valid_choice(tmp_path)

    # Invalid hex hashes
    for bad_hash in ["invalid", "x" * 64, "0" * 63]:
        with pytest.raises(ValueError, match="parent_state_sha256"):
            replace(choice, parent_state_sha256=bad_hash)
        with pytest.raises(ValueError, match="terminal_state_sha256"):
            replace(choice, terminal_state_sha256=bad_hash)
        with pytest.raises(ValueError, match="segments_sha256"):
            replace(choice, segments_sha256=bad_hash)

    # Parent state equal to terminal state
    with pytest.raises(ValueError, match="parent and terminal state hashes must differ"):
        replace(choice, parent_state_sha256=choice.terminal_state_sha256)


def test_adversarial_outcome_and_observation_tampering(tmp_path):
    choice = _valid_choice(tmp_path)

    # Before observation corrupted schema
    bad_before = dict(choice.before_observation)
    bad_before["schema"] = "corrupted.v1"
    with pytest.raises(ValueError, match="schema"):
        replace(choice, before_observation=bad_before)

    # After observation missing required collection fields
    bad_after = deepcopy(choice.after_observation)
    del bad_after["semantic_observation"]["collection"]["registered"]
    with pytest.raises((ValueError, KeyError)):
        replace(choice, after_observation=bad_after)

    # Lost specimen / regressed credit
    # Replace after with before so no acquisition occurred
    with pytest.raises(GoalManagerCompositionError, match="no physical acquisition"):
        replace(choice, after_observation=choice.before_observation)


def test_adversarial_costs_tampering(tmp_path):
    choice = _valid_choice(tmp_path)

    # Actions <= 0
    act_err = "controller actions must be positive integer within bounds"
    with pytest.raises(ValueError, match=act_err):
        replace(choice, controller_actions=0)
    with pytest.raises(ValueError, match=act_err):
        replace(choice, controller_actions=-5)

    # Actions as boolean
    with pytest.raises(ValueError, match=act_err):
        replace(choice, controller_actions=True)

    # Actions > maximum_actions
    with pytest.raises(ValueError, match=act_err):
        replace(choice, controller_actions=30_001)

    # Frames < 0
    frames_err = "emulator frames must be non-negative integer within bounds"
    with pytest.raises(ValueError, match=frames_err):
        replace(choice, emulator_frames=-1)

    # Frames > maximum_frames
    with pytest.raises(ValueError, match=frames_err):
        replace(choice, emulator_frames=3_000_001)

    # Negative resource costs
    with pytest.raises(ValueError, match="resource costs must be non-negative"):
        replace(choice, resource_costs={"balls": -1})


def test_adversarial_trust_flags_tampering(tmp_path):
    choice = _valid_choice(tmp_path)

    # from_public rejects any violated trust flags
    for flag in [
        "action_trace_available",
        "independent_evaluation",
        "authority_promotion_eligible",
    ]:
        doc = choice.public_dict()
        doc[flag] = True
        with pytest.raises(ValueError, match=f"{flag} must be false"):
            RedDevelopmentMeasuredChoice.from_public(doc)

    doc_t = choice.public_dict()
    doc_t["teacher_labels"] = 1
    with pytest.raises(ValueError, match="teacher_labels must be 0"):
        RedDevelopmentMeasuredChoice.from_public(doc_t)

    doc_tr = choice.public_dict()
    doc_tr["training_only"] = False
    with pytest.raises(ValueError, match="training_only must be true"):
        RedDevelopmentMeasuredChoice.from_public(doc_tr)


def test_publish_and_load_measured_choice(tmp_path, monkeypatch):
    store, prior, request, model_a = _bootstrap_registered_model(tmp_path, monkeypatch)
    choice = _valid_choice(tmp_path, model_sha256=model_a.model.model_sha256)

    # Mismatched behavior record rejected on publish
    with pytest.raises(ValueError, match="choice model sha256 does not match"):
        publish_development_measured_choice(store, choice, prior)

    # Successful publish
    meas_input = publish_development_measured_choice(store, choice, model_a)
    assert meas_input.choice_id == choice.choice_id
    assert len(meas_input.record_sha256) == 64

    # Load and verify arm example
    arm = load_red_development_measured_choice_example(
        store, meas_input, objective=REGISTERED_OBJECTIVE
    )
    assert arm.partition == "train"
    assert arm.decision_sha256 == choice.decision_sha256

    # Load with non-registered objective rejected
    with pytest.raises(ValueError, match="development measured choice objective differs"):
        load_red_development_measured_choice_example(store, meas_input, objective="other")


def test_fit_red_player_update_with_measured_choice(tmp_path, monkeypatch):
    store, prior, request, model_a = _bootstrap_registered_model(tmp_path, monkeypatch)
    choice = _valid_choice(tmp_path, model_sha256=model_a.model.model_sha256)
    meas_input = publish_development_measured_choice(store, choice, model_a)

    fit_b = fit_red_player_update(
        store,
        prior=model_a,
        episodes=(request,),
        measured_choices=(meas_input,),
        source_commit="b" * 40,
        source_bundle_sha256="c" * 64,
        registered_objective=True,
    )
    assert fit_b["new_settled_examples"] == 1
    assert fit_b["prior_rows_retained"] is True

    sha_b = _model_sha(fit_b)
    rec_b = store.find_sealed_record(f"rpr-model-{sha_b}", expected_kind="red_player_model")
    model_b = load_player_goal_model_record_bytes(rec_b.read_bytes(), expected_model_sha256=sha_b)
    assert model_b.model.settled_examples == model_a.model.settled_examples + 1

    # Check corpus contains measured_choices
    corpus_rec = store.find_sealed_record(
        f"rp-corpus-{model_b.corpus_sha256}", expected_kind="red_player_training_corpus"
    )
    assert corpus_rec is not None
    corpus_data = corpus_rec.read()
    assert "measured_choices" in corpus_data
    assert len(corpus_data["measured_choices"]) == 1
    assert corpus_data["measured_choices"][0]["choice_id"] == choice.choice_id

    # Check retained hashes include the measured choice arm hash
    arm_hash = canonical_sha256(choice.to_observed_arm_example().public_dict())
    assert arm_hash in model_b.retained_example_sha256


def test_subsequent_fit_retention_preserves_measured_choice_and_all_prior_rows(
    tmp_path, monkeypatch
):
    store, prior, request, model_a = _bootstrap_registered_model(tmp_path, monkeypatch)
    choice_1 = _valid_choice(tmp_path, model_sha256=model_a.model.model_sha256)
    meas_input_1 = publish_development_measured_choice(store, choice_1, model_a)

    # Fit Model B with choice 1
    fit_b = fit_red_player_update(
        store,
        prior=model_a,
        episodes=(request,),
        measured_choices=(meas_input_1,),
        source_commit="b" * 40,
        source_bundle_sha256="c" * 64,
        registered_objective=True,
    )
    sha_b = _model_sha(fit_b)
    rec_b = store.find_sealed_record(f"rpr-model-{sha_b}", expected_kind="red_player_model")
    model_b = load_player_goal_model_record_bytes(rec_b.read_bytes(), expected_model_sha256=sha_b)

    # Build second measured choice for Model C
    pb, _ = _safari_observations(tmp_path)
    runtime_path = tmp_path / "safari_runtime"
    runtime, _, _ = bound_fixture(runtime_path)
    pol = runtime.registration_policy
    b = runtime.adapter.observe()
    new_species_2 = red_species_ref(128)  # Tauros
    new_specimen_2 = LivingSpecimen(
        new_species_2,
        level=28,
        location=CollectionLocation.BOX,
        container_index=1,
        slot_index=2,
    )
    a2 = replace(
        b,
        capture_item_count=b.capture_item_count - 1,
        collection_observation=replace(
            b.collection_observation,
            owned_species=b.collection_observation.owned_species | {new_species_2},
            specimens=(*b.collection_observation.specimens, new_specimen_2),
        ),
    )
    pa2 = project_registered_observation(a2, pol).public_dict()
    choice_2 = RedDevelopmentMeasuredChoice(
        choice_id="safari-choice-tauros",
        menu=_menu("safari"),
        selected_candidate_index=0,
        behavior_probabilities=(0.6, 0.3, 0.1, 0.0),
        model_sha256=model_b.model.model_sha256,
        before_observation=pb,
        after_observation=pa2,
        parent_state_sha256="5" * 64,
        terminal_state_sha256="6" * 64,
        segments_sha256="7" * 64,
        controller_actions=120,
        emulator_frames=1800,
        resource_costs={"safari_balls_used": 6, "money_spent": 500},
    )
    meas_input_2 = publish_development_measured_choice(store, choice_2, model_b)

    # Fit Model C passing ONLY meas_input_2! Choice 1 is NOT passed explicitly!
    fit_c = fit_red_player_update(
        store,
        prior=model_b,
        episodes=(request,),
        measured_choices=(meas_input_2,),
        source_commit="b" * 40,
        source_bundle_sha256="c" * 64,
        registered_objective=True,
    )
    sha_c = _model_sha(fit_c)
    rec_c = store.find_sealed_record(f"rpr-model-{sha_c}", expected_kind="red_player_model")
    model_c = load_player_goal_model_record_bytes(rec_c.read_bytes(), expected_model_sha256=sha_c)
    assert model_c.model.settled_examples == model_b.model.settled_examples + 1

    resolver = {
        prior.model.model_sha256: prior,
        model_a.model.model_sha256: model_a,
        model_b.model.model_sha256: model_b,
        model_c.model.model_sha256: model_c,
    }.__getitem__

    # Verify inventory of Model C preserves BOTH choices
    inv_c = load_prior_player_inventory(store, model_c, resolver)
    assert len(inv_c.measured_choices) == 2
    assert {m.choice_id for m in inv_c.measured_choices} == {
        "safari-choice-kangaskhan",
        "safari-choice-tauros",
    }

    # Verify every old row's hash from Model A and Model B is preserved in Model C
    arm_1_hash = canonical_sha256(choice_1.to_observed_arm_example().public_dict())
    arm_2_hash = canonical_sha256(choice_2.to_observed_arm_example().public_dict())
    assert arm_1_hash in model_c.retained_example_sha256
    assert arm_2_hash in model_c.retained_example_sha256
    assert set(model_a.retained_example_sha256).issubset(set(model_c.retained_example_sha256))
    assert set(model_b.retained_example_sha256).issubset(set(model_c.retained_example_sha256))


def test_incremental_measured_choice_and_registered_results(tmp_path, monkeypatch):
    store, prior, request, model_a = _bootstrap_registered_model(tmp_path, monkeypatch)
    choice = _valid_choice(tmp_path, model_sha256=model_a.model.model_sha256)
    meas_input = publish_development_measured_choice(store, choice, model_a)

    resolver = {
        prior.model.model_sha256: prior,
        model_a.model.model_sha256: model_a,
    }.__getitem__

    # fit_incremental_measured_choice
    fitted = fit_incremental_measured_choice(
        store,
        prior=model_a,
        measured_choice=meas_input,
        resolve=resolver,
        source_commit="b" * 40,
        source_bundle_sha256="c" * 64,
    )
    assert fitted["new_settled_examples"] == 1
    assert fitted["prior_rows_retained"] is True

    sha_b = _model_sha(fitted)
    rec_b = store.find_sealed_record(f"rpr-model-{sha_b}")
    model_b = load_player_goal_model_record_bytes(rec_b.read_bytes(), expected_model_sha256=sha_b)

    resolver_b = {
        prior.model.model_sha256: prior,
        model_a.model.model_sha256: model_a,
        model_b.model.model_sha256: model_b,
    }.__getitem__

    # Re-adding duplicate measured choice is rejected
    with pytest.raises(ValueError, match="already included"):
        fit_incremental_measured_choice(
            store,
            prior=model_b,
            measured_choice=meas_input,
            resolve=resolver_b,
            source_commit="b" * 40,
            source_bundle_sha256="c" * 64,
        )

    # Testing fit_incremental_registered_results with DEVELOPMENT_MEASURED_RESULT_SCHEMA
    result_doc = {
        "schema": DEVELOPMENT_MEASURED_RESULT_SCHEMA,
        "objective": REGISTERED_OBJECTIVE,
        "model_sha256": model_a.model.model_sha256,
        "choice_id": choice.choice_id,
        "record_sha256": meas_input.record_sha256,
        "eligible_examples": 1,
        "action_trace_available": False,
        "independent_evaluation": False,
        "authority_promotion_eligible": False,
        "teacher_labels": 0,
    }

    # Trust flags rejection in incremental registered results
    for bad_flag, bad_val in [
        ("action_trace_available", True),
        ("independent_evaluation", True),
        ("authority_promotion_eligible", True),
        ("teacher_labels", 1),
        ("eligible_examples", 2),
    ]:
        bad_result = dict(result_doc)
        bad_result[bad_flag] = bad_val
        inc_err = "scope differ|trust flags|objective or behavior differs"
        with pytest.raises(ValueError, match=inc_err):
            fit_incremental_registered_results(
                store,
                prior=model_a,
                results=(bad_result,),
                resolve=resolver,
                source_commit="b" * 40,
                source_bundle_sha256="c" * 64,
            )
