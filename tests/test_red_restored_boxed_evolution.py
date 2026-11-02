"""Opted-in PC settlement may return an earned target to verified storage."""

from dataclasses import fields, replace
from types import SimpleNamespace as N

import pytest
from test_red_native_boxed_evolution import runtime_fixture

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import RedPokedexState
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.red_collection import (
    RedBoxCollectionState,
    RedCurrentBoxState,
    red_internal_species_id,
)
from pokemon_red_completion.red_player_party_guard import (
    RedPlayerPartyGuard,
    RetainedPartyGoalStateAdapter,
)


def test_no_settlement_callback_retains_historical_behavior_without_input():
    from pokemon_red_completion.red_native_boxed_evolution import settle_native_evolution

    assert settle_native_evolution(N(evolution_settlement=None), None) == {}


@pytest.mark.parametrize("fault", [None, "unguarded", "unrestored", "cash", "bag", "stock"])
def test_settlement_callback_executes_before_report_and_cannot_bypass_identity_or_stock(fault):
    from pokemon_red_completion.party import PartyMemberObservation
    from pokemon_red_completion.red_native_boxed_evolution import settle_native_evolution

    role = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    loan = replace(role, slot=2, species_id=165, level=7, experience=350)
    active_members, active_refs = (role,), ("role",)
    boxed = [N(preparation_ref="loan", species_id=165, level=7, experience=350)]
    guard = RedPlayerPartyGuard(
        N(
            read=lambda: PartyObservation(active_members),
            preparation_specimen_refs=lambda: active_refs,
        ),
        PartyObservation((role, loan)),
        ("role", "loan"),
        frozenset(),
        N(read_box_specimen_identities=lambda: tuple(boxed)),
        frozenset({"loan"}),
    )
    raw = N(battle_state=0, bag_items=((1, 1),), player_money=100)
    specimens = (N(species_ref="species:a"), N(species_ref="species:b"))
    collection = N(owned_species=frozenset({"species:a", "species:b"}), specimens=specimens)
    adapter = N(
        party_guard=None if fault == "unguarded" else guard,
        observe=lambda: N(raw=replace_raw(), collection_observation=collection, input_ready=True),
    )

    def replace_raw():
        return N(**vars(raw))

    calls = []

    def settle(actions):
        nonlocal active_members, active_refs, boxed, collection
        calls.append(actions)
        if fault != "unrestored":
            active_members, active_refs, boxed = (role, loan), ("role", "loan"), []
        if fault == "cash":
            raw.player_money += 1
        if fault == "bag":
            raw.bag_items = ()
        if fault == "stock":
            collection = N(owned_species=collection.owned_species, specimens=specimens[:-1])

    runtime = N(evolution_settlement=settle, adapter=adapter)
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            settle_native_evolution(runtime, "shared-port")
    else:
        assert settle_native_evolution(runtime, "shared-port") == {
            "retained_active_roster_restored": True
        }
    assert calls == ([] if fault == "unguarded" else ["shared-port"])


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "ordinary",
        "no_marker",
        "no_census",
        "unrestored",
        "duplicate_original",
        "underlevel",
        "wrong_stock",
    ],
)
def test_returned_boxed_target_requires_explicit_preserved_and_restored_loan_contract(
    tmp_path, fault
):
    runtime, reader, _ = runtime_fixture(tmp_path)
    before = runtime.adapter.observe()
    level = 39 if fault == "underlevel" else 40
    reader.boxes = RedBoxCollectionState(
        (
            RedCurrentBoxState(
                0, (red_internal_species_id(77), red_internal_species_id(78)), (32, level)
            ),
            *(RedCurrentBoxState(i, (), ()) for i in range(1, 12)),
        ),
        0,
        False,
    )
    if fault == "wrong_stock":
        reader.boxes = replace(
            reader.boxes,
            boxes=(
                RedCurrentBoxState(0, (red_internal_species_id(78),), (level,)),
                *reader.boxes.boxes[1:],
            ),
        )
    reader.read_pokedex_state = lambda: RedPokedexState(
        frozenset({9, 77, 78}), frozenset({9, 77, 78})
    )
    after = runtime.adapter.observe()
    members = tuple(replace(m, experience=1000) for m in before.party.members)
    refs = tuple(f"original-{i}" for i in range(6))
    active_refs = refs[:-1] if fault == "unrestored" else refs
    active_members = members[:-1] if fault == "unrestored" else members
    boxed = [
        N(
            preparation_ref="trainee",
            species_id=red_internal_species_id(78),
            level=level,
            experience=10000,
        )
    ]
    if fault in {"unrestored", "duplicate_original"}:
        original = members[-1]
        boxed.append(
            N(
                preparation_ref=refs[-1],
                species_id=original.species_id,
                level=original.level,
                experience=original.experience,
            )
        )
    guard = RedPlayerPartyGuard(
        N(
            read=lambda: PartyObservation(active_members),
            preparation_specimen_refs=lambda: active_refs,
        ),
        PartyObservation(members),
        refs,
        frozenset(),
        None if fault == "no_census" else N(read_box_specimen_identities=lambda: tuple(boxed)),
        frozenset({refs[-1]}),
    )
    if fault != "ordinary":
        runtime = replace(
            runtime,
            adapter=RetainedPartyGoalStateAdapter(
                **{f.name: getattr(runtime.adapter, f.name) for f in fields(runtime.adapter)},
                party_guard=guard,
            ),
        )
    provider = runtime.provider_for(
        GoalKind.EVOLVE_SPECIES, CountingExecutor(N(execute=lambda a: a))
    )
    report = GoalExecutionReport(1, 1, {"retained_active_roster_restored": fault != "no_marker"})
    verdict = provider._verify_boxed_evolution(before, after, report)
    assert verdict.status.value == ("succeeded" if fault is None else "failed")
