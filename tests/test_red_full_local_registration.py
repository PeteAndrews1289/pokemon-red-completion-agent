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


def test_explicit124_planning_is_local_and_does_not_offer_alternate_one_off_targets(tmp_path):
    from pokemon_red_completion.red_collection import red_species_ref
    _, before, _, policy = observations(tmp_path)
    scoped = replace(policy, completion_scope="local_red",
                     target_species=tuple(RED_SOLO_COLLECTION_CONTRACT.target_species))
    assert len(scoped.targets) == 124
    assert red_species_ref(135) in scoped.targets
    assert red_species_ref(134) not in scoped.targets
    assert red_species_ref(136) not in scoped.targets
    checkpoint = project_registered_observation(before, scoped).registered_checkpoint
    assert set(checkpoint.target_species) == scoped.targets
    assert checkpoint.registered_species == len(set(checkpoint.local_species) & scoped.targets)
    assert scoped.document()["schema"].endswith(".v3")
    assert replace(scoped, target_species=None).document()["schema"].endswith(".v2")


@pytest.mark.parametrize("targets", [(), ("bogus",), ["pokemon:national:001"],
                                     ("pokemon:national:001", "pokemon:national:001")])
def test_explicit_planning_targets_fail_closed(tmp_path, targets):
    _, _, _, policy = observations(tmp_path)
    with pytest.raises(ValueError, match="registration targets"):
        replace(policy, completion_scope="local_red", target_species=targets)


def test_target_binding_reaches_live_projection_and_protects_irreversible_eevee_choice(tmp_path):
    from dataclasses import dataclass
    from types import SimpleNamespace
    from pokemon_red_completion.red_player_configuration import _bind_required_registration_targets

    _, before, _, policy = observations(tmp_path, inherited=(78, 151))
    local = replace(policy, completion_scope="local_red")
    @dataclass
    class Runtime:
        registration_policy: object
        adapter: object
    rt = Runtime(local, SimpleNamespace(registration_policy=local))
    assert _bind_required_registration_targets(rt, None) is rt
    bound = _bind_required_registration_targets(rt, tuple(RED_SOLO_COLLECTION_CONTRACT.target_species))
    assert bound.adapter.registration_policy is bound.registration_policy
    checkpoint = project_registered_observation(before, bound.adapter.registration_policy).registered_checkpoint
    assert set(checkpoint.target_species) == set(RED_SOLO_COLLECTION_CONTRACT.target_species)
    assert red_species_ref(78) not in bound.registration_policy.goal_registered(before.collection_observation)
    from pokemon_red_completion.collection import CollectionLocation
    from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID
    from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
    from pokemon_red_completion.registration_memory import RegistrationSnapshot, observation_from_collection

    original = before.collection_observation
    eevee = replace(original.specimens[0], species_ref=red_species_ref(133), location=CollectionLocation.PARTY)
    current = replace(original, owned_species=frozenset({red_species_ref(133)}),
                      specimens=(eevee,), party_size=1, box_counts=(0,) * len(original.box_counts))
    row = observation_from_collection(current, seen_species=current.owned_species,
        national_ids={red_species_ref(n): n for n in range(1, 152)}, run_id="eevee-branch",
        game_id=RED_COLLECTION_GAME_ID, adapter_id="test", cartridge_sha256="a" * 64,
        snapshot_sha256="b" * 64, sequence=0)
    local = RedRegistrationPolicy(RegistrationSnapshot((row,)), "eevee-branch", "b" * 64,
                                  current, {}, completion_scope="local_red")
    scoped = replace(local, target_species=tuple(RED_SOLO_COLLECTION_CONTRACT.target_species))
    assert all(local.evolution_allowed(current, red_species_ref(133), red_species_ref(n)) for n in (134,135,136))
    assert scoped.evolution_allowed(current, red_species_ref(133), red_species_ref(135))
    assert not any(scoped.evolution_allowed(current, red_species_ref(133), red_species_ref(n)) for n in (134,136))
