"""Prospective full-local objective; historical shared rewards stay unchanged."""

import json
from dataclasses import replace

import pytest
from test_registered_learning_bridge import observations, score

from pokemon_red_completion.goal_manager_composition_runtime import GoalManagerCompositionError
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT, red_species_ref
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.registered_checkpoint import RegisteredCollectionCheckpoint
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE


def test_historical_shared_policy_serialization_is_exactly_unchanged(tmp_path):
    _, _, _, policy = observations(tmp_path)
    expected = {
        "schema": "pokemon.red.registered-runtime-binding.v1",
        "objective": REGISTERED_OBJECTIVE,
        "initial_memory_sha256": policy.initial_memory.sha256,
        "initial_snapshot_sha256": policy.initial_snapshot_sha256,
        "run_id": policy.run_id,
        "targets": sorted(RED_SOLO_COLLECTION_CONTRACT.target_species),
        "protected_counts": dict(sorted(policy.protected_counts.items())),
    }
    assert len(policy.targets) == 124
    assert policy.document() == expected
    assert policy.sha256 == canonical_sha256(expected)
    assert replace(policy, completion_scope="local_red").sha256 != policy.sha256


def test_local_credit_never_erases_shared_history_and_uses_full151_reward(tmp_path):
    _, before, after, policy = observations(tmp_path, inherited=(78, 151))
    local = replace(policy, completion_scope="local_red")
    assert len(local.targets) == 151
    assert red_species_ref(151) in local.registered(before.collection_observation)
    assert red_species_ref(151) not in local.goal_registered(before.collection_observation)
    assert local.evolution_allowed(before.collection_observation, red_species_ref(77),
                                   red_species_ref(78))
    assert not policy.evolution_allowed(before.collection_observation, red_species_ref(77),
                                       red_species_ref(78))
    old = project_registered_observation(before, local)
    new = project_registered_observation(after, local)
    assert old.registered_checkpoint.global_species == new.registered_checkpoint.global_species
    assert score(old, new).completion_gain == pytest.approx(1 / 151)
    assert score(project_registered_observation(before, policy),
                 project_registered_observation(after, policy)).completion_gain == 0
    assert red_species_ref(151) in old.registered_checkpoint.global_species
    assert red_species_ref(151) not in old.registered_checkpoint.credited_species
    assert old.evidence.registered_collection.target == 151


def test_local_checkpoint_roundtrip_and_scope_tampering_rejected(tmp_path):
    _, before, _, policy = observations(tmp_path, inherited=(78,))
    checkpoint = project_registered_observation(
        before, replace(policy, completion_scope="local_red")).registered_checkpoint
    doc = json.loads(json.dumps(checkpoint.public_dict()))
    assert doc["schema"].endswith(".v2")
    assert RegisteredCollectionCheckpoint.from_public(doc) == checkpoint
    for mutation in ({"completion_scope": "shared"}, {"completion_scope": "bogus"},
                     {"schema": "pokemon.core.registered-collection-checkpoint.v1"}):
        with pytest.raises(ValueError):
            RegisteredCollectionCheckpoint.from_public({**doc, **mutation})


def test_cannot_mix_shared_and_local_outcomes_or_consume_protected_precursor(tmp_path):
    _, before, after, policy = observations(tmp_path, reserve=1)
    local = replace(policy, completion_scope="local_red")
    assert not local.evolution_allowed(before.collection_observation, red_species_ref(77),
                                       red_species_ref(78))
    with pytest.raises(ValueError, match="protected physical"):
        project_registered_observation(after, local)
    with pytest.raises(GoalManagerCompositionError, match="binding or credit"):
        score(project_registered_observation(before, policy),
              project_registered_observation(before, local), succeeded=False)


def test_local_policy_keeps_physical_and_monotonic_owned_guards(tmp_path):
    _, before, _, policy = observations(tmp_path)
    local = replace(policy, completion_scope="local_red")
    with pytest.raises(ValueError, match="lost local owned"):
        local.goal_registered(replace(before.collection_observation, owned_species=frozenset()))
    with pytest.raises(ValueError, match="completion scope"):
        replace(policy, completion_scope="all")
