"""Physical precursor demand never fabricates registration or retained stock."""

from collections import Counter
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.red_acquisition import summarize_red_area_survey
from pokemon_red_completion.red_autonomous_safari import _safari_physical_demand
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    RED_SOLO_COLLECTION_CONTRACT,
    red_species_ref as ref,
)
from pokemon_red_completion.red_live_safari import (
    _registered_safari_catalog,
    _safari_capture_stock_verified,
)
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)


def _inputs(*extra, missing=(31, 34, 64)):
    credited = frozenset(RED_SOLO_COLLECTION_CONTRACT.target_species) - {ref(n) for n in missing}
    stock = (30, 33, *extra)
    collection = CollectionObservation(
        owned_species=credited,
        specimens=tuple(
            LivingSpecimen(ref(n), 20, CollectionLocation.BOX, container_index=0, slot_index=i)
            for i, n in enumerate(stock)
        ),
        party_size=0,
        party_limit=6,
        box_counts=(len(stock),),
        current_box_index=0,
        box_capacity=20,
    )
    row = observation_from_collection(
        collection,
        seen_species=credited,
        national_ids={ref(n): n for n in range(1, 152)},
        run_id="earned",
        game_id=RED_COLLECTION_GAME_ID,
        adapter_id="red-v1",
        cartridge_sha256="a" * 64,
        snapshot_sha256="b" * 64,
        sequence=0,
    )
    policy = RedRegistrationPolicy(
        RegistrationSnapshot((row,)), "earned", "b" * 64, collection, {ref(30): 1, ref(33): 1}
    )
    return N(
        registration_policy=policy, level_evolution_acquisition_edges=((ref(63), ref(64)),)
    ), N(collection_observation=collection)


@pytest.mark.parametrize(
    "extra,missing,expected",
    [
        ((), (31, 34, 64), {30, 33, 63}),
        ((30,), (31, 34, 64), {33, 63}),
        ((30, 33, 63), (31, 34, 64), set()),
        ((), (34, 64), {33, 63}),
        ((), (), set()),
    ],
)
def test_demand_reuses_actual_spare_stock_and_missing_descendants(extra, missing, expected):
    runtime, observation = _inputs(*extra, missing=missing)
    before = observation.collection_observation
    result = _safari_physical_demand(runtime, observation)
    assert result["required_capture_numbers"] & {30, 33, 63} == expected
    assert not result["required_capture_numbers"] & {29, 32}
    assert observation.collection_observation is before
    assert result["acquisition_catalog"].registered_species == before.owned_species
    assert dict(result["acquisition_catalog"].protected_counts) == {ref(30): 1, ref(33): 1}


def test_survey_preserves_registered_credit_and_original_reservations():
    runtime, observation = _inputs()
    catalog = _safari_physical_demand(runtime, observation)["acquisition_catalog"]
    area = N(offer=N(source_id="wild:SafariZoneNorth:grass", missing_species_numbers=(30, 33)))
    actual = _registered_safari_catalog(
        area, {int(s.rsplit(":", 1)[1]) for s in catalog.registered_species}, catalog
    )
    assert summarize_red_area_survey(
        area.offer.source_id, observation.collection_observation, actual
    ).missing_species_refs == (ref(30), ref(33))
    assert actual.registered_species == catalog.registered_species
    assert actual.protected_counts == catalog.protected_counts


@pytest.mark.parametrize(
    "before,after,captures,expected",
    [
        ((30, 33), (30, 33, 30), 1, True),
        ((30, 33), (30, 33), 1, False),
        ((30, 33), (30, 30), 1, False),
        ((30, 33), (30, 33, 48), 1, False),
        ((30, 33), (30, 33, 30, 33), 1, False),
        ((30, 33), (30, 33), 0, True),
        ((30, 33), (30, 33, 30), 0, False),
    ],
)
def test_stock_proof_requires_exactly_one_useful_retained_copy(before, after, captures, expected):
    assert (
        _safari_capture_stock_verified(
            Counter(map(ref, before)), Counter(map(ref, after)), (30, 33), captures
        )
        is expected
    )


def test_duplicate_safari_offer_is_explicit_and_default_stays_registration_only(monkeypatch):
    import pokemon_red_completion.red_safari_acquisition as m
    from pokemon_red_completion.observation import MapId

    monkeypatch.setattr(m, "internal_to_dex", lambda _: {1: 30})
    monkeypatch.setattr(
        m, "wild_tables", lambda *_a, **_k: {int(MapId.SAFARI_ZONE_NORTH): ((20, 1),) * 10}
    )
    assert m.red_safari_zone_offers(b"fixture", {30}) == ()
    assert m.red_safari_zone_offers(b"fixture", {30}, required_capture_numbers={30})[
        0
    ].missing_species_numbers == (30,)
    assert m.red_safari_zone_offers(b"fixture", {30}, required_capture_numbers=set()) == ()
    with pytest.raises(ValueError, match="physical capture demand"):
        m.red_safari_zone_offers(b"fixture", {30}, required_capture_numbers={True})


def test_duplicate_candidate_reports_dependency_not_new_registration(monkeypatch):
    import pokemon_red_completion.red_live_safari as m
    from test_red_live_safari import _area
    from pokemon_red_completion.goal_manager import GoalSituation
    from pokemon_red_completion.living_dex_option_value import (
        living_dex_option_context_from_goal_situation,
    )
    from pokemon_red_completion.observation import MapId

    runtime, observation = _inputs()
    demand = _safari_physical_demand(runtime, observation)
    area = _area("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER), 3, 4)
    area = replace(
        area, offer=replace(area.offer, slots=((20, 30),) * 10, missing_species_numbers=(30,))
    )
    monkeypatch.setattr(m, "discover_reachable_red_safari_areas", lambda *_a, **_k: (area,))
    monkeypatch.setattr(
        m, "resolve_red_safari_entry_mode", lambda *_a, **_k: m.RedSafariEntryMode.GATE
    )
    inventory = m.build_red_live_safari_inventory(
        b"fixture",
        {30, 33},
        living_dex_option_context_from_goal_situation(GoalSituation(0, 1, 0, 1, 0, 0, 0, 0, 0)),
        free_storage_slots=1,
        world=N(),
        controller=N(),
        actions=N(),
        reader=N(read=lambda: N(player_money=500)),
        **demand,
    )
    features = inventory.supplements[0].candidate.features
    assert features.completion_gain == 0
    assert features.dependency_unlock_gain == pytest.approx(1 / 6)
