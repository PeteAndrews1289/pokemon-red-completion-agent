from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_native_boxed_evolution import runtime_fixture

from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import RedPokedexState
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_bounded_player import RedBoundedPlayerObserver
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_context import _RedTeamGoalProvider
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)


def bound_fixture(tmp_path, *, reserve=0, inherited=(), count=1, party_source=False):
    runtime, reader, _ = runtime_fixture(tmp_path, count=count)
    if party_source:
        from pokemon_red_completion.red_collection import red_internal_species_id

        reader.raw = replace(
            reader.raw,
            map_id=22,
            party_species_ids=(*reader.raw.party_species_ids[:5], red_internal_species_id(77)),
        )
    owned = {red_internal_species_number(s) for s in reader.raw.party_species_ids}
    owned.update(red_internal_species_number(s) for b in reader.boxes.boxes for s in b.species_ids)
    reader.read_pokedex_state = lambda: RedPokedexState(frozenset(owned), frozenset(owned))
    collection = runtime.adapter.observe().collection_observation
    mapping = {red_species_ref(n): n for n in range(1, 152)}
    row = observation_from_collection(
        collection,
        seen_species=collection.owned_species,
        national_ids=mapping,
        run_id="current",
        game_id=RED_COLLECTION_GAME_ID,
        adapter_id="red-v1",
        cartridge_sha256="a" * 64,
        snapshot_sha256="b" * 64,
        sequence=0,
    )
    rows = (row,)
    if inherited:
        rows += (
            replace(
                row,
                run_id="prior",
                game_id="blue",
                seen=row.seen | frozenset(inherited),
                owned=row.owned | frozenset(inherited),
            ),
        )
    policy = RedRegistrationPolicy(
        RegistrationSnapshot(rows), "current", "b" * 64, collection, {red_species_ref(77): reserve}
    )
    return replace(runtime, registration_policy=policy), reader, owned


@pytest.fixture(autouse=True)
def encounter_fixture(monkeypatch):
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_evolution.wild_tables",
        lambda _: {22: [(10, 0x21), (15, 0x6C)]},
    )


@pytest.mark.parametrize(
    "reserve,inherited,count,ready",
    [
        (0, (), 1, True),
        (1, (), 1, False),
        (0, (78,), 1, False),
        (1, (), 2, True),
        (0, (), 3, False),
    ],
)
def test_native_offer_uses_registration_and_real_reserves(
    tmp_path, reserve, inherited, count, ready
):
    runtime, _, _ = bound_fixture(tmp_path, reserve=reserve, inherited=inherited, count=count)
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"fixture"))
    actions = CountingExecutor(SimpleNamespace(execute=lambda _: pytest.fail("unexpected input")))
    before = native.adapter.observe()
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(before)
    assert (offer.binding is not None) is ready
    assert actions.actions_executed == 0


def test_binding_identity_differs_and_legacy_episode_cannot_consume_registered_mode(tmp_path):
    runtime, _, _ = bound_fixture(tmp_path)
    original = "c" * 64
    assert runtime.bound_configuration_sha256(original) != original
    legacy = replace(runtime, registration_policy=None)
    assert legacy.bound_configuration_sha256(original) == original
    actions = CountingExecutor(SimpleNamespace(execute=lambda _: None))
    with pytest.raises(ValueError, match="checkpoint and reward"):
        RedBoundedPlayerObserver(runtime, actions)
    observer = RedBoundedPlayerObserver(legacy, actions)
    observer.runtime = runtime
    with pytest.raises(ValueError, match="checkpoint and reward"):
        observer()


def test_registered_survey_recomputes_local_credit_after_a_capture(tmp_path):
    runtime, _, _ = bound_fixture(tmp_path)
    obs = runtime.adapter.observe().collection_observation
    refs = runtime.registration_policy.registered(obs)
    source = "wild:Route1:grass"
    # A fully registered line elsewhere must not be recaught for coexistence.
    catalog = replace(
        RED_ACQUISITION_CATALOG,
        remaining_demand=True,
        registered_species=refs | frozenset(map(red_species_ref, (16, 17, 18))),
        wild_source_species=((source, (red_species_ref(16),)),),
    )
    assert summarize_red_area_survey(source, obs, catalog).complete
    partial = replace(
        catalog, registered_species=refs, wild_source_species=((source, (red_species_ref(21),)),)
    )
    assert not summarize_red_area_survey(source, obs, partial).complete
    after = replace(
        obs, owned_species=obs.owned_species | frozenset(map(red_species_ref, (21, 22)))
    )
    assert summarize_red_area_survey(source, after, partial).complete
    assert red_species_ref(21) not in obs.owned_species


@pytest.mark.parametrize("failure", [None, "lost_registration", "lost_specimen", "protected"])
def test_exact_registered_evolution_verifier_accepts_last_copy_only_with_real_flags(
    tmp_path, failure
):
    runtime, _, _ = bound_fixture(tmp_path, reserve=int(failure == "protected"))
    before = runtime.adapter.observe()
    collection = before.collection_observation
    changed = tuple(
        replace(s, species_ref=red_species_ref(78), level=40)
        if s.species_ref == red_species_ref(77)
        else s
        for s in collection.specimens
    )
    owned = collection.owned_species | {red_species_ref(78)}
    if failure == "lost_registration":
        owned -= {red_species_ref(77)}
    if failure == "lost_specimen":
        changed = tuple(s for s in changed if s.location is CollectionLocation.PARTY)
    after_collection = replace(collection, specimens=changed, owned_species=frozenset(owned))
    policy = runtime.registration_policy
    if failure == "lost_registration":
        with pytest.raises(ValueError, match="lost local owned"):
            policy.verify_evolution(
                collection, after_collection, red_species_ref(77), red_species_ref(78)
            )
    else:
        assert policy.verify_evolution(
            collection, after_collection, red_species_ref(77), red_species_ref(78)
        ) is (failure is None)


def test_provider_verifier_rejects_changed_species_without_registration(tmp_path):
    runtime, _, _ = bound_fixture(tmp_path)
    before = runtime.adapter.observe()
    spec = next(s for s in runtime.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    provider = _RedTeamGoalProvider(
        runtime, spec, CountingExecutor(SimpleNamespace(execute=lambda _: None))
    )
    after_collection = replace(
        before.collection_observation,
        specimens=tuple(
            replace(s, species_ref=red_species_ref(78), level=40)
            if s.species_ref == red_species_ref(77)
            else s
            for s in before.collection_observation.specimens
        ),
    )
    with pytest.raises(ValueError, match="physical stock lacks"):
        provider._verify_boxed_evolution(
            before,
            replace(before, collection_observation=after_collection),
            GoalExecutionReport(1, 1, {}),
        )


@pytest.mark.parametrize("register_target", [True, False])
def test_native_single_copy_training_requires_real_registration(
    tmp_path,
    monkeypatch,
    register_target,
):
    import pokemon_red_completion.red_native_boxed_evolution as native
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.red_collection import red_internal_species_id

    runtime, reader, owned = bound_fixture(tmp_path, count=0, party_source=True)
    before = runtime.adapter.observe().collection_observation
    monkeypatch.setattr(native, "restore_native_center_party", lambda *args: 0)
    monkeypatch.setattr(
        native,
        "PokemonRedPartyReader",
        lambda _: SimpleNamespace(
            read=lambda: replace(
                runtime.adapter.observe().party,
                members=tuple(
                    replace(m, experience=1000) for m in runtime.adapter.observe().party.members
                ),
            ),
        ),
    )
    calls = []

    def train(actions, *args, **kwargs):
        calls.append(kwargs["evolution_target"])
        actions.execute(MacroAction(MacroActionKind.WAIT))
        reader.raw = replace(
            reader.raw,
            party_species_ids=(*reader.raw.party_species_ids[:5], red_internal_species_id(78)),
            party_levels=(*reader.raw.party_levels[:5], 55),
        )
        if register_target:
            owned.add(78)
        return None, 1, 0

    monkeypatch.setattr(native.context, "run_red_team_balancing", train)
    bound = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"fixture"), maximum_quanta=2)
    actions = CountingExecutor(SimpleNamespace(execute=lambda _: None))
    if not register_target:
        with pytest.raises(ValueError, match="physical stock lacks"):
            bound.party_level_evolution_executor(
                red_internal_species_id(77), red_internal_species_id(78), actions
            )
    else:
        report = bound.party_level_evolution_executor(
            red_internal_species_id(77), red_internal_species_id(78), actions
        )
        assert report.actions_executed == 1
        assert report.evidence["registration_policy_sha256"] == runtime.registration_policy.sha256
        after = runtime.adapter.observe().collection_observation
        assert runtime.registration_policy.verify_evolution(
            before,
            after,
            red_species_ref(77),
            red_species_ref(78),
        )
        assert red_species_ref(77) in after.owned_species
        assert all(s.species_ref != red_species_ref(77) for s in after.specimens)
    assert calls == [(red_internal_species_id(77), red_internal_species_id(78))]
