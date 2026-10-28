"""Existing named PC loans must not disappear behind a legacy species rule."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_goal_context import _ActionDelegate
from test_red_native_boxed_evolution import runtime_fixture

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.red_collection import (
    RedBoxCollectionState,
    RedCurrentBoxState,
    red_internal_species_id,
)
from pokemon_red_completion.red_goal_context import (
    RedBoxedItemEvolutionGoalRequest,
    RedBoxedLevelEvolutionGoalRequest,
    RedGoalContextError,
    _RedTeamGoalProvider,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID
from pokemon_red_completion.red_player_party_guard import (
    RedPlayerPartyGuard,
    retained_party_slot_is_declared_loan,
)


def _guarded_runtime(runtime, *, approved, settlement):
    observation = runtime.adapter.observe()
    party = PartyObservation(tuple(
        replace(member, experience=1_000_000) for member in observation.party.members
    ))
    refs = tuple(f"original-{index}" for index in range(party.size))
    reader = N(read=lambda: party, preparation_specimen_refs=lambda: refs)
    guard = RedPlayerPartyGuard(
        reader, party, refs, frozenset(),
        N(read_box_specimen_identities=lambda: ()),
        frozenset({refs[0]}) if approved else frozenset(),
    )
    runtime.reader.read_box_specimen_identities = lambda: ()
    return replace(
        runtime,
        adapter=N(party_guard=guard, observe=runtime.adapter.observe),
        evolution_settlement=(lambda actions: None) if settlement else None,
    )


@pytest.mark.parametrize("mechanic", ("level", "item"))
@pytest.mark.parametrize("approved,settlement", ((True, True), (True, False), (False, True)))
def test_blastoise_storage_needs_its_exact_declared_loan_and_repayment(
    tmp_path, mechanic, approved, settlement,
):
    runtime, reader, _ = runtime_fixture(tmp_path)
    if mechanic == "item":
        reader.boxes = RedBoxCollectionState((
            RedCurrentBoxState(0, (red_internal_species_id(58),) * 2, (32,) * 2),
            *(RedCurrentBoxState(index, (), ()) for index in range(1, 12)),
        ), 0, False)
        profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id=runtime.profile.profile_id,
            providers=tuple(
                (spec.kind, RedGoalMechanic.TARGETED_ITEM_EVOLUTION, {
                    "source_species_ref": "pokemon:national:058",
                    "target_species_ref": "pokemon:national:059",
                    "item_id": int(ItemId.FIRE_STONE),
                }) if spec.kind is GoalKind.EVOLVE_SPECIES
                else (spec.kind, spec.mechanic, dict(spec.parameters))
                for spec in runtime.profile.providers
            ),
        ))
        runtime = replace(runtime, profile=profile)
    runtime = _guarded_runtime(runtime, approved=approved, settlement=settlement)
    spec = next(spec for spec in runtime.profile.providers if spec.kind is GoalKind.EVOLVE_SPECIES)
    actions = CountingExecutor(_ActionDelegate())
    provider = _RedTeamGoalProvider(runtime, spec, actions)
    request_for = (provider._boxed_evolution_request if mechanic == "level"
                   else provider._boxed_item_evolution_request)
    before = reader.read()
    if approved and settlement:
        request = request_for(runtime.adapter.observe())
        assert request.deposit_party_slot == 1
        assert request.deposit_internal_species_id == BLASTOISE_SPECIES_ID
        assert request.declared_blastoise_loan
        assert retained_party_slot_is_declared_loan(runtime.adapter, 1)
        assert not retained_party_slot_is_declared_loan(runtime.adapter, 2)
    else:
        with pytest.raises(RedGoalContextError, match="storage binding"):
            request_for(runtime.adapter.observe())
    assert reader.read() == before
    assert actions.actions_executed == 0


def test_ordinary_unguarded_evolution_still_retains_legacy_blastoise(tmp_path):
    runtime, _, _ = runtime_fixture(tmp_path)
    runtime = replace(runtime, evolution_settlement=lambda actions: None)
    spec = next(spec for spec in runtime.profile.providers if spec.kind is GoalKind.EVOLVE_SPECIES)
    request = _RedTeamGoalProvider(runtime, spec, None)._boxed_evolution_request(
        runtime.adapter.observe()
    )
    assert request.deposit_internal_species_id != BLASTOISE_SPECIES_ID
    assert not retained_party_slot_is_declared_loan(runtime.adapter, 1)


@pytest.mark.parametrize("permission", (False, None, 1, "yes"))
@pytest.mark.parametrize("mechanic", ("level", "item"))
def test_raw_request_cannot_implicitly_remove_the_legacy_escort(permission, mechanic):
    source, target = red_internal_species_id(58), red_internal_species_id(59)
    with pytest.raises(RedGoalContextError):
        if mechanic == "level":
            RedBoxedLevelEvolutionGoalRequest(
                source, target, 0, 1, 1, BLASTOISE_SPECIES_ID,
                declared_blastoise_loan=permission,
            )
        else:
            RedBoxedItemEvolutionGoalRequest(
                source, target, 0, 1, 30, 1, BLASTOISE_SPECIES_ID, int(ItemId.FIRE_STONE),
                declared_blastoise_loan=permission,
            )


@pytest.mark.parametrize("remaining_mentors_cover_venue", (True, False))
def test_loan_admission_cannot_quote_absent_blastoise_as_training_finisher(
    tmp_path, monkeypatch, remaining_mentors_cover_venue,
):
    import pokemon_red_completion.red_native_boxed_evolution as module

    runtime, reader, _ = runtime_fixture(tmp_path)
    runtime = _guarded_runtime(runtime, approved=True, settlement=True)
    venue = module.context.MANSION_TRAINING_VENUE
    monkeypatch.setattr(module, "wild_tables", lambda rom: {venue.map_id: ((10, 165),)})
    quoted = []

    def finisher(party, *args, **kwargs):
        quoted.append(party.species_ids())
        return object() if remaining_mentors_cover_venue else None

    monkeypatch.setattr(module, "collection_finisher", finisher)
    native = bind_native_boxed_evolution(runtime, N(rom=b"test"), training_venues=(venue,))
    actions = CountingExecutor(_ActionDelegate())
    before = reader.read()
    offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(native.adapter.observe())
    assert (offer.binding is not None) is remaining_mentors_cover_venue
    if not remaining_mentors_cover_venue:
        assert offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert quoted and all(BLASTOISE_SPECIES_ID not in members for members in quoted)
    assert reader.read() == before
    assert actions.actions_executed == 0
