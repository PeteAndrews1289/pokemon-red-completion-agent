import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_registered_runtime_binding import bound_fixture

from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import (
    GoalManagerCompositionError,
    require_living_collection_transition,
)
from pokemon_red_completion.red_bounded_player import RedBoundedPlayerObserver
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.red_registered_outcome import red_registered_outcome_from_observations
from pokemon_red_completion.registered_checkpoint import RegisteredCollectionCheckpoint


def observations(tmp_path, *, inherited=(), reserve=0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    runtime, _, _ = bound_fixture(tmp_path, inherited=inherited, reserve=reserve)
    policy = runtime.registration_policy
    before = runtime.adapter.observe()
    source = red_species_ref(77)
    target = red_species_ref(78)
    specimens = tuple(
        replace(s, species_ref=target, level=40) if s.species_ref == source else s
        for s in before.collection_observation.specimens
    )
    after = replace(before, collection_observation=replace(
        before.collection_observation,
        owned_species=before.collection_observation.owned_species | {target}, specimens=specimens,
    ))
    return runtime, before, after, policy


def score(before, after, kind=GoalKind.EVOLVE_SPECIES, succeeded=True):
    return red_registered_outcome_from_observations(
        before.public_dict(), after.public_dict(), selected_kind=kind, succeeded=succeeded,
        actions=20, frames=200, maximum_actions=100, maximum_frames=1000,
    )


def test_single_precursor_evolution_preserves_credit_and_scores_only_registration(tmp_path):
    _, before, after, policy = observations(tmp_path)
    before = project_registered_observation(before, policy)
    after = project_registered_observation(after, policy)
    first, last = before.registered_checkpoint, after.registered_checkpoint
    require_living_collection_transition(first, last, selected_kind=GoalKind.EVOLVE_SPECIES)
    assert red_species_ref(77) not in dict(last.specimen_counts)
    assert red_species_ref(77) in last.global_species
    assert last.registered_species == first.registered_species + 1
    assert last.required_specimens_remaining == first.required_specimens_remaining - 1
    outcome = score(before, after)
    assert outcome.verified_success
    assert outcome.completion_gain == pytest.approx(1 / 124)
    assert outcome.irreversible_loss == 0
    assert outcome.action_cost == 0.2
    assert outcome.frame_cost == 0.2
    assert after.evidence.living_collection.target == 0
    assert after.evidence.level_collection.target == 0


def test_inherited_registration_is_not_local_stock_or_new_novelty(tmp_path):
    _, before, after, policy = observations(tmp_path, inherited=(78,))
    before = project_registered_observation(before, policy)
    after = project_registered_observation(after, policy)
    assert red_species_ref(78) not in before.registered_checkpoint.local_species
    assert red_species_ref(78) in before.registered_checkpoint.global_species
    assert score(before, after).completion_gain == 0
    assert before.situation.collection_pressure == after.situation.collection_pressure


def test_duplicates_legal_without_novelty_or_intrinsic_penalty(tmp_path):
    _, before, _, policy = observations(tmp_path)
    specimen = before.collection_observation.specimens[-1]
    after = replace(before, capture_item_count=before.capture_item_count - 1,
        collection_observation=replace(before.collection_observation, specimens=(
            *before.collection_observation.specimens,
            replace(specimen, slot_index=1, location=CollectionLocation.BOX),
        )))
    first = project_registered_observation(before, policy)
    last = project_registered_observation(after, policy)
    require_living_collection_transition(
        first.registered_checkpoint, last.registered_checkpoint,
        selected_kind=GoalKind.ACQUIRE_SPECIES,
    )
    outcome = score(first, last, GoalKind.ACQUIRE_SPECIES)
    assert outcome.verified_success and outcome.completion_gain == 0
    assert outcome.irreversible_loss == 0
    assert outcome.resource_cost > 0


def test_protected_last_copy_cannot_evolve(tmp_path):
    _, _, after, policy = observations(tmp_path, reserve=1)
    with pytest.raises(ValueError, match="protected physical"):
        project_registered_observation(after, policy)


def test_lost_local_registration_and_unexplained_specimen_loss_rejected(tmp_path):
    _, before, after, policy = observations(tmp_path)
    lost = replace(after, collection_observation=replace(
        after.collection_observation,
        owned_species=after.collection_observation.owned_species - {red_species_ref(77)},
    ))
    with pytest.raises(ValueError, match="lost local owned"):
        project_registered_observation(lost, policy)
    lost = replace(before, collection_observation=replace(
        before.collection_observation, specimens=before.collection_observation.specimens[:-1],
    ))
    with pytest.raises(GoalManagerCompositionError, match="undeclared specimen"):
        score(project_registered_observation(before, policy),
              project_registered_observation(lost, policy), succeeded=False)


def test_checkpoint_roundtrip_keeps_three_views_and_detects_tampering(tmp_path):
    _, before, _, policy = observations(tmp_path, inherited=(78,))
    checkpoint = project_registered_observation(before, policy).registered_checkpoint
    doc = json.loads(json.dumps(checkpoint.public_dict()))
    assert RegisteredCollectionCheckpoint.from_public(doc) == checkpoint
    assert "required_specimens_remaining" not in doc
    for key, value in (
        ("registered_species", 999), ("binding_sha256", "bad"),
        ("local_registered_species", 999), ("objective", "living"),
        ("required_registrations_sha256", "0" * 64),
        ("extra", "ignored-field"),
    ):
        with pytest.raises((ValueError, GoalManagerCompositionError)):
            RegisteredCollectionCheckpoint.from_public({**doc, key: value})


def test_registered_observer_requires_opt_in_and_never_sends_input(tmp_path):
    runtime, _, _, _ = observations(tmp_path)
    actions = CountingExecutor(SimpleNamespace(execute=lambda _: pytest.fail("controller input")))
    observer = RedBoundedPlayerObserver(runtime, actions, registered_objective=True)
    observed = observer()
    assert isinstance(observed.collection, RegisteredCollectionCheckpoint)
    assert observer.last_live_observation.registered_checkpoint == observed.collection
    assert actions.actions_executed == 0
    observer.runtime = replace(runtime, registration_policy=None)
    with pytest.raises(ValueError, match="frozen policy"):
        observer()


def test_no_change_failure_has_costs_but_no_completion_credit(tmp_path):
    _, before, _, policy = observations(tmp_path)
    observed = project_registered_observation(before, policy)
    outcome = score(observed, observed, GoalKind.ACQUIRE_SPECIES, succeeded=False)
    assert not outcome.verified_success and outcome.completion_gain == 0
    assert outcome.action_cost == 0.2
    with pytest.raises(GoalManagerCompositionError, match="no physical acquisition"):
        score(observed, observed, GoalKind.ACQUIRE_SPECIES)


def test_registered_outcome_cannot_accept_legacy_labels_or_unbound_counter(tmp_path):
    _, before, _, policy = observations(tmp_path)
    new = project_registered_observation(before, policy)
    with pytest.raises(ValueError, match="schema"):
        score(before, new, succeeded=False)
    doc = new.public_dict()
    doc["semantic_observation"]["collection"]["registered"] += 1
    with pytest.raises(ValueError, match="projected counts"):
        red_registered_outcome_from_observations(
            doc, new.public_dict(), selected_kind=GoalKind.ACQUIRE_SPECIES, succeeded=False,
            actions=1, frames=1, maximum_actions=10, maximum_frames=10,
        )


def test_registered_training_events_reconstruct_targets_and_reject_tampering(tmp_path, monkeypatch):
    from test_red_player_training import _episode

    from pokemon_red_completion.red_player_training_plan import (
        REGISTERED_TRAINING_PLAN_SCHEMA,
        RedPlayerTrainingPlan,
    )
    from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

    _, before, _, policy = observations(tmp_path / "observations")
    # The existing stochastic fixture chooses resupply, not acquisition. Retain
    # that actual choice and supply outcome; do not fabricate capture credit.
    after = replace(before, capture_item_count=before.capture_item_count + 1)
    pair = tuple(project_registered_observation(o, policy) for o in (before, after))

    def declare(store, plan):
        document = dict(plan.document)
        document.update(
            schema=REGISTERED_TRAINING_PLAN_SCHEMA,
            objective=REGISTERED_OBJECTIVE, registration_binding_sha256=policy.sha256,
            maximum_actions=30_000, maximum_frames=3_000_000,
            origin_state_sha256="a" * 64, origin_envelope_sha256="b" * 64,
            restore_profile_sha256="c" * 64, continuation_episode_id="parent",
            continuation_checkpoint_sha256="d" * 64,
        )
        return RedPlayerTrainingPlan(document)

    # This test targets event writing and reconstruction. The separate test below
    # checks that the new schema cannot bypass real continuation authentication.
    monkeypatch.setattr(
        "pokemon_red_completion.red_player_training_dataset._require_continuation_origin",
        lambda *_: None,
    )
    (tmp_path / "valid").mkdir()
    (tmp_path / "tampered").mkdir()
    dataset = _episode(tmp_path / "valid", plan_transform=declare, registration_observations=pair)
    assert dataset.objective == REGISTERED_OBJECTIVE
    assert len(dataset.examples) == 1
    assert dataset.examples[0].outcome.completion_gain == 0

    def corrupt(streams):
        event = next(e for e in streams["events"]
                     if e["kind"] == "living_dex_player_training_outcome")
        event["payload"]["before"]["registration"]["binding_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="binding differs"):
        _episode(tmp_path / "tampered", plan_transform=declare,
                 registration_observations=pair, mutate=corrupt)

    from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
    from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
    from pokemon_red_completion.red_player_training_fit import (
        RedPlayerEpisodeInput,
        fit_red_player_update,
    )
    (tmp_path / "fitting").mkdir()
    store, plan, behavior, completed = _episode(
        tmp_path / "fitting", plan_transform=declare, registration_observations=pair,
        return_inputs=True, repeat_registered_choice=True,
    )
    prior = LivingDexGoalModelRecord(behavior, "a" * 64, "b" * 40, "c" * 64, 1, 1)
    request = RedPlayerEpisodeInput(plan, "goal-episode-1", completed.manifest_sha256, prior)
    monkeypatch.setattr(
        "pokemon_red_completion.red_player_training_fit.load_living_dex_authenticated_causal_examples",
        lambda _: pytest.fail("registered fitting opened the historical corpus"),
    )
    fit = fit_red_player_update(
        store, prior=prior, episodes=(request,), source_commit="b" * 40,
        source_bundle_sha256="c" * 64, registered_objective=True,
    )
    assert fit["new_settled_examples"] == 2
    assert fit["historical_rewards_reused"] is False
    assert fit["parameter_warm_start"] is False
    assert fit["model"]["settled_examples"] == 2
    sha = fit["model"]["model_sha256"]
    record = store.find_sealed_record(f"rpr-model-{sha}", expected_kind="red_player_model")
    loaded = load_player_goal_model_record_bytes(record.read_bytes(), expected_model_sha256=sha)
    assert loaded.objective == REGISTERED_OBJECTIVE
    from pokemon_red_completion.red_player_incremental_fit import load_prior_player_inventory
    retained, regional = load_prior_player_inventory(store, loaded, lambda _: prior)
    assert retained == (request,) and regional == ()
    with pytest.raises(ValueError, match="additional settled"):
        fit_red_player_update(store, prior=loaded, episodes=(request,),
            source_commit="b" * 40, source_bundle_sha256="c" * 64, registered_objective=True)
    with pytest.raises(ValueError, match="legacy fitting cannot consume"):
        fit_red_player_update(store, prior=loaded, episodes=(request,),
            source_commit="b" * 40, source_bundle_sha256="c" * 64)


def test_registered_plan_requires_real_continuation_parent(tmp_path):
    from test_goal_resource_quote import _supply_model
    from test_red_player_training import _plan

    from pokemon_red_completion.red_player_training_dataset import _require_continuation_origin
    from pokemon_red_completion.red_player_training_plan import (
        REGISTERED_TRAINING_PLAN_SCHEMA,
        RedPlayerTrainingPlan,
    )
    from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

    plan = RedPlayerTrainingPlan({
        **_plan(_supply_model()).document,
        "schema": REGISTERED_TRAINING_PLAN_SCHEMA, "objective": REGISTERED_OBJECTIVE,
        "registration_binding_sha256": "a" * 64,
        "maximum_actions": 30_000, "maximum_frames": 3_000_000,
        "origin_state_sha256": "a" * 64, "origin_envelope_sha256": "b" * 64,
        "restore_profile_sha256": "c" * 64, "continuation_episode_id": "parent",
        "continuation_checkpoint_sha256": "d" * 64,
    })
    assert plan.maximum_actions == 30_000 and plan.maximum_frames == 3_000_000
    with pytest.raises(ValueError, match="continued training checkpoint"):
        _require_continuation_origin(
            SimpleNamespace(find_sealed_record=lambda *_a, **_k: None), plan,
        )


def test_registered_terminal_roundtrip_and_legacy_disguise_rejected(tmp_path):
    from test_red_player_checkpoint import _complete, _open
    from test_red_player_checkpoint import case as checkpoint_case

    from pokemon_red_completion.red_player_checkpoint import (
        CHECKPOINT_SCHEMA,
        REGISTERED_PLAYER_CHECKPOINT_SCHEMA,
        RedPlayerCheckpointError,
        capture_red_player_terminal,
        publish_red_player_checkpoint,
    )

    _, before, _, policy = observations(tmp_path / "observation")
    collection = project_registered_observation(before, policy).registered_checkpoint
    for legacy_disguise in (False, True):
        folder = tmp_path / ("legacy" if legacy_disguise else "registered")
        folder.mkdir()
        store, arguments, observed = checkpoint_case.__wrapped__(folder)
        observed = replace(observed, collection=collection)
        result = arguments["result"]
        arguments.update(observe=lambda value=observed: value, result=replace(result, steps=(
            replace(result.steps[0], collection_before=collection, collection_after=collection),
        )))
        document = capture_red_player_terminal(**arguments)
        assert document["schema"] == REGISTERED_PLAYER_CHECKPOINT_SCHEMA
        if legacy_disguise:
            document["schema"] = CHECKPOINT_SCHEMA
        _complete(store, document)
        summary = publish_red_player_checkpoint(store, document)
        if legacy_disguise:
            with pytest.raises(RedPlayerCheckpointError, match="legacy checkpoint"):
                _open(store, arguments, summary)
        else:
            restored = _open(store, arguments, summary)
            restored.require_restored_observation(observed)
            assert (
                RegisteredCollectionCheckpoint.from_public(dict(restored.collection)) == collection
            )
